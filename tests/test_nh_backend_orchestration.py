import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from app.services import pnl_records, portfolio, user_openapi
from app.services.nhplug_openapi import compute_nh_account_key
from app.services.user_identity import generate_user_id
from tests.regression_support import IsolatedDataTestCase
from tests.test_request_state_user_id import _import_main_without_loading_real_env


class NhBackendOrchestrationTests(IsolatedDataTestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls): cls.client.close()

    def setUp(self):
        super().setUp(); self.username="synthetic-nh-user"; self.user_id=generate_user_id()
        self.account_no="1234567890"; self.source_key=compute_nh_account_key(self.account_no)
        self.destination={"id":"nh-destination","broker":"NH투자증권","name":"NH 계좌","account_name":"NH 계좌","owner":"본인"}
        portfolio.write_portfolio({"accounts":[self.destination],"holdings":[],"settings":{"fx_rates":{"KRW":1.0}}},self.username)
        self.patchers2=[
            patch("app.services.user_manager.get_user_by_name",return_value={"username":self.username,"id":self.user_id,"role":"user","must_change_password":False}),
            patch.object(user_openapi,"get_user_openapi_config",return_value={"nh":{"app_key":"SYNTHETIC","app_secret":"SYNTHETIC"}}),
            patch("app.services.nhplug_openapi.NhPlugOpenAPI._accounts",new_callable=AsyncMock,return_value=[{"acct_no":self.account_no}]),
        ]
        for p in self.patchers2: p.start()

    def tearDown(self):
        for p in reversed(self.patchers2): p.stop()
        super().tearDown()

    def headers(self):
        token=self.main._serializer.dumps({"user":self.username,"role":"user"})
        return {"Cookie":f"{self.main.COOKIE_NAME}={token}"}

    def canonical(self, market):
        if market=="kr":
            return {"date":"2026-01-02","market_type":"kr","code":"SYN","name":"Synthetic","quantity":1.0,"buy_unit_price":10.0,"buy_amount":10.0,"sell_unit_price":20.0,"sell_amount":20.0,"pnl":10.0,"pnl_krw":10.0,"profit_rate":100.0,"fee":1.0,"tax":2.0,"expenses_total":None,"currency":"KRW","classification":"01"}
        return {"date":"2026-01-03","market_type":"us","code":"SYNUS","name":"Synthetic US","country":"200","currency":"USD","exchange":None,"quantity":1.0,"buy_unit_price":10.0,"buy_amount":10.0,"sell_unit_price":20.0,"sell_amount":20.0,"pnl":10.0,"pnl_krw":None,"fx_rate":None,"profit_rate":100.0,"fee":None,"tax":None,"expenses_total":3.0}

    def selected(self, market):
        from app.services.nh_feed import sign_nh_feed_row
        row=self.canonical(market)
        return [{"row":row,"selection_token":sign_nh_feed_row(row,user_id=self.user_id,source_account_key=self.source_key,market=market)}]

    def preview(self, market, selected=None):
        return self.client.post("/api/nh/realized-feed/import-preview",headers=self.headers(),json={"market":market,"source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected or self.selected(market)})

    def test_status_and_fetch_are_safe_and_read_only(self):
        status=self.client.get("/api/nh/status",headers=self.headers()); self.assertEqual(status.status_code,200)
        self.assertNotIn(self.account_no,status.text)
        raw={"_wealth_date_context":"20260102","iem_cd":"SYN","iem_nm":"Synthetic","sll_qty":"1","byn_uit_pr":"10","byn_amt":"10","sll_uit_pr":"20","sll_amt":"20","pls_amt":"10","pft_rt":"100","fee_sum":"1","tax_sum":"2"}
        with patch("app.services.nhplug_openapi.NhPlugOpenAPI.fetch_realized_profit",new_callable=AsyncMock,return_value=([raw],self.source_key,"masked")):
            response=self.client.post("/api/nh/realized-feed/fetch",headers=self.headers(),json={"market":"kr","source_account_key":self.source_key,"from_date":"20260101","to_date":"20260131"})
        self.assertEqual(response.status_code,200); self.assertNotIn(self.account_no,response.text)

    def test_domestic_preview_import_repreview_and_replay(self):
        selected=self.selected("kr"); pnl_file=pnl_records._get_pnl_file(self.username); self.assertFalse(pnl_file.exists())
        preview=self.preview("kr",selected); self.assertEqual(preview.status_code,200); pdata=preview.json()
        self.assertEqual(pdata["counts"],{"selected":1,"new":1,"already_imported":0,"possible_duplicate":0,"invalid":0})
        self.assertFalse(pnl_file.exists()); self.assertFalse(self.main._nh_mapping_file(self.username).exists())
        payload={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":pdata["preview_ticket"]}
        imported=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload); self.assertEqual(imported.json()["imported"],1)
        records=pnl_records.read_pnl_records(self.username); self.assertEqual(len(records),1); rec=records[0]
        self.assertEqual(rec["source"],"nh"); self.assertTrue(rec["source_scope_verified"]); self.assertNotIn("selection_token",rec); self.assertNotIn("preview_ticket",rec)
        self.assertNotIn(self.account_no,json.dumps(rec))
        self.assertEqual(self.main._read_nh_mapping(self.username)[self.source_key],self.destination["id"])
        self.assertEqual(self.preview("kr",selected).json()["counts"]["already_imported"],1)
        self.assertEqual(self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload).json()["imported"],0)
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)),1)

    def test_overseas_import_preserves_nullable_financial_semantics(self):
        selected=self.selected("us"); preview=self.preview("us",selected).json()
        payload={"market":"us","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":preview["preview_ticket"]}
        self.assertEqual(self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload).json()["imported"],1)
        rec=pnl_records.read_pnl_records(self.username)[0]
        for key in ("fee","tax","pnl_krw","fx_rate"): self.assertIsNone(rec[key])
        self.assertEqual(rec["expenses_total"],3.0)
        summary=pnl_records.get_pnl_summary(username=self.username)
        self.assertEqual(summary["total_pnl_krw"],0)
        self.assertEqual(summary["record_count"],1)

    def test_same_selection_twice_is_rejected_in_preview_and_import(self):
        selected=self.selected("kr"); selected.append(dict(selected[0]))
        preview=self.preview("kr",selected); self.assertEqual(preview.status_code,200); data=preview.json()
        self.assertEqual(data["counts"]["new"],1); self.assertEqual(data["counts"]["invalid"],1)
        self.assertEqual(data["items"][1]["reason"],"DUPLICATE_SELECTION")
        payload={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":data["preview_ticket"]}
        first=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload)
        self.assertEqual(first.status_code,200); self.assertEqual(first.json()["imported"],1)
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)),1)
        replay=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload)
        self.assertEqual(replay.status_code,200); self.assertEqual(replay.json()["imported"],0)
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)),1)

    def test_malformed_existing_storage_aborts_import_without_overwrite(self):
        selected=self.selected("kr"); preview=self.preview("kr",selected).json()
        payload={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":preview["preview_ticket"]}
        pnl_file=pnl_records._get_pnl_file(self.username); pnl_file.parent.mkdir(parents=True,exist_ok=True)
        original=b'{"records": [malformed synthetic bytes]'
        pnl_file.write_bytes(original)
        response=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()["detail"]["code"],"PNL_STORAGE_INVALID")
        self.assertEqual(pnl_file.read_bytes(),original)
        self.assertFalse(self.main._nh_mapping_file(self.username).exists())

    def test_generic_write_refuses_to_overwrite_malformed_storage(self):
        pnl_file=pnl_records._get_pnl_file(self.username); pnl_file.parent.mkdir(parents=True,exist_ok=True)
        original=b'{"records": "not-a-list"}'
        pnl_file.write_bytes(original)
        with self.assertRaises(pnl_records.PnlRecordsStorageError):
            pnl_records.write_pnl_records([],self.username)
        self.assertEqual(pnl_file.read_bytes(),original)

    def test_tampering_wrong_destination_and_manual_duplicate_fail_safely(self):
        selected=self.selected("kr"); selected[0]["row"]["pnl"]=99
        self.assertEqual(self.preview("kr",selected).json()["counts"]["invalid"],1)
        bad=self.client.post("/api/nh/realized-feed/import-preview",headers=self.headers(),json={"market":"kr","source_account_key":self.source_key,"account_id":"missing","selected_items":self.selected("kr")})
        self.assertEqual(bad.status_code,400)
        wrong_scope=self.client.post("/api/nh/realized-feed/import-preview",headers=self.headers(),json={"market":"kr","source_account_key":"0"*64,"account_id":self.destination["id"],"selected_items":self.selected("kr")})
        self.assertEqual(wrong_scope.status_code,400)
        pnl_records.create_pnl_record({"date":"2026-01-02","code":"SYN","name":"Synthetic","currency":"KRW","pnl":10,"pnl_krw":10},self.username)
        self.assertEqual(self.preview("kr").json()["counts"]["possible_duplicate"],1)

    def test_tampered_ticket_does_not_write_or_map(self):
        selected=self.selected("kr"); ticket=self.preview("kr",selected).json()["preview_ticket"]+"x"
        response=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":ticket})
        self.assertEqual(response.status_code,400); self.assertEqual(pnl_records.read_pnl_records(self.username),[]); self.assertFalse(self.main._nh_mapping_file(self.username).exists())

    def test_mapping_failure_after_record_write_is_reported_and_retry_repairs(self):
        selected=self.selected("kr"); preview=self.preview("kr",selected).json()
        payload={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":preview["preview_ticket"]}
        with patch.object(self.main,"_write_nh_mapping",side_effect=OSError("synthetic mapping failure")):
            first=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload)
        self.assertEqual(first.status_code,200); first_data=first.json()
        self.assertEqual(first_data["imported"],1); self.assertTrue(first_data["partial_success"])
        self.assertEqual(first_data["mapping_status"],"warning")
        self.assertEqual(first_data["mapping_warning"],"MAPPING_PERSISTENCE_FAILED")
        self.assertNotIn(self.account_no,first.text)
        records=pnl_records.read_pnl_records(self.username)
        self.assertEqual(len(records),1); self.assertEqual(records[0]["destination_account_id"],self.destination["id"])
        self.assertFalse(self.main._nh_mapping_file(self.username).exists())
        retry=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload)
        self.assertEqual(retry.status_code,200); retry_data=retry.json()
        self.assertEqual(retry_data["imported"],0); self.assertTrue(retry_data["mapping_repaired"])
        self.assertEqual(retry_data["mapping_status"],"repaired")
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)),1)
        self.assertEqual(self.main._read_nh_mapping(self.username)[self.source_key],self.destination["id"])

    def test_mapping_repair_rejects_wrong_destination_and_existing_conflict(self):
        second={"id":"other-destination","broker":"NH투자증권","name":"다른 계좌","account_name":"다른 계좌","owner":"본인"}
        portfolio.write_portfolio({"accounts":[self.destination,second],"holdings":[],"settings":{"fx_rates":{"KRW":1.0}}},self.username)
        selected=self.selected("kr"); first_preview=self.preview("kr",selected).json()
        first_payload={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":first_preview["preview_ticket"]}
        with patch.object(self.main,"_write_nh_mapping",side_effect=OSError("synthetic mapping failure")):
            self.assertEqual(self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=first_payload).json()["imported"],1)
        wrong_preview=self.client.post("/api/nh/realized-feed/import-preview",headers=self.headers(),json={"market":"kr","source_account_key":self.source_key,"account_id":second["id"],"selected_items":selected}).json()
        wrong_payload={"market":"kr","source_account_key":self.source_key,"account_id":second["id"],"selected_items":selected,"preview_ticket":wrong_preview["preview_ticket"]}
        wrong=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=wrong_payload)
        self.assertEqual(wrong.status_code,409); self.assertEqual(len(pnl_records.read_pnl_records(self.username)),1)
        self.assertFalse(self.main._nh_mapping_file(self.username).exists())
        self.main._write_nh_mapping(self.username,self.source_key,second["id"])
        conflict=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=first_payload)
        self.assertEqual(conflict.status_code,409); self.assertEqual(len(pnl_records.read_pnl_records(self.username)),1)
        self.assertEqual(self.main._read_nh_mapping(self.username)[self.source_key],second["id"])

    def test_preview_and_prewrite_failure_never_write_mapping(self):
        selected=self.selected("kr")
        with patch.object(self.main,"_write_nh_mapping",wraps=self.main._write_nh_mapping) as write_mapping:
            preview=self.preview("kr",selected)
            self.assertEqual(preview.status_code,200); write_mapping.assert_not_called()
            payload={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":preview.json()["preview_ticket"]+"tampered"}
            failed=self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload)
            self.assertEqual(failed.status_code,400); write_mapping.assert_not_called()
        self.assertFalse(self.main._nh_mapping_file(self.username).exists())

    def test_financial_write_failure_does_not_attempt_mapping(self):
        selected=self.selected("kr"); preview=self.preview("kr",selected).json()
        payload={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":preview["preview_ticket"]}
        with (
            patch.object(self.main,"create_pnl_record",side_effect=pnl_records.PnlRecordsStorageError("synthetic write failure")),
            patch.object(self.main,"_write_nh_mapping",wraps=self.main._write_nh_mapping) as write_mapping,
        ):
            with self.assertRaises(pnl_records.PnlRecordsStorageError):
                self.client.post("/api/nh/realized-feed/import",headers=self.headers(),json=payload)
            write_mapping.assert_not_called()
        self.assertFalse(self.main._nh_mapping_file(self.username).exists())


if __name__=="__main__": unittest.main()
