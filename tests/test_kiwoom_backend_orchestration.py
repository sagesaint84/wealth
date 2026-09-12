import json
import unittest
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from app.services import pnl_records, portfolio, user_openapi
from app.services.user_identity import generate_user_id
from tests.regression_support import IsolatedDataTestCase
from tests.test_request_state_user_id import _import_main_without_loading_real_env


class KiwoomBackendOrchestrationTests(IsolatedDataTestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        super().setUp()
        self.username = "synthetic-kiwoom-user"
        self.user_id = generate_user_id()
        self.source_key = "a" * 64
        self.source_label = "******7890"
        self.destination = {
            "id": "kiwoom-destination", "broker": "키움증권",
            "name": "Synthetic account", "account_name": "Synthetic account", "owner": "본인",
        }
        portfolio.write_portfolio(
            {"accounts": [self.destination], "holdings": [], "settings": {"fx_rates": {"KRW": 1.0}}},
            self.username,
        )
        self.extra_patchers = [
            patch("app.services.user_manager.get_user_by_name", return_value={
                "username": self.username, "id": self.user_id, "role": "user", "must_change_password": False,
            }),
            patch.object(user_openapi, "get_user_openapi_config", return_value={
                "kiwoom": {"app_key": "SYNTHETIC", "app_secret": "SYNTHETIC"},
            }),
            patch(
                "app.services.kiwoom_openapi.KiwoomOpenAPI.get_realized_source_account_state",
                new_callable=AsyncMock, return_value=(self.source_key, self.source_label),
            ),
        ]
        for patcher in self.extra_patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.extra_patchers):
            patcher.stop()
        super().tearDown()

    def headers(self):
        token = self.main._serializer.dumps({"user": self.username, "role": "user"})
        return {"Cookie": f"{self.main.COOKIE_NAME}={token}"}

    @staticmethod
    def raw(market):
        if market == "kr":
            return {
                "dt": "20260901", "stk_cd": "A005930", "stk_nm": "Synthetic Domestic",
                "cntr_qty": "2", "buy_uv": "10", "cntr_pric": "20", "tdy_sel_pl": "17",
                "pl_rt": "85", "tdy_trde_cmsn": "1", "tdy_trde_tax": "2",
            }
        return {
            "sell_dt": "20260902", "stk_cd": "SYNUS", "frgn_stk_nm": "Synthetic Overseas",
            "sell_qty": "2", "avg_buy_uv": "10", "buy_amt": "20",
            "avg_sell_uv": "20", "sell_amt": "40", "pl_amt": "17",
            "pl_rt": "85", "cmsn_tax": "3", "natn_nm": "United States", "stex_nm": "Synthetic Exchange",
        }

    def selected(self, market, rows=None):
        from app.services.kiwoom_feed import build_kiwoom_realized_feed
        feed = build_kiwoom_realized_feed(
            rows or [self.raw(market)], market=market, source_account_key=self.source_key,
            source_account_label=self.source_label, user_id=self.user_id,
        )
        return [{"row": row, "selection_token": token} for row, token in zip(feed["rows"], feed["selection_tokens"])]

    def preview(self, market, selected=None, destination_id=None):
        return self.client.post(
            "/api/kiwoom/realized-feed/import-preview", headers=self.headers(),
            json={
                "market": market, "source_account_key": self.source_key,
                "account_id": destination_id or self.destination["id"],
                "selected_items": selected or self.selected(market),
            },
        )

    def import_payload(self, market, selected):
        preview = self.preview(market, selected)
        self.assertEqual(preview.status_code, 200, preview.text)
        return {
            "market": market, "source_account_key": self.source_key,
            "account_id": self.destination["id"], "selected_items": selected,
            "preview_ticket": preview.json()["preview_ticket"],
        }

    def test_status_and_fetch_routes_are_safe(self):
        status = self.client.get("/api/kiwoom/status", headers=self.headers())
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["source_scope_verified"])
        self.assertNotIn("acctNo", status.text)
        with patch(
            "app.services.kiwoom_openapi.KiwoomOpenAPI.fetch_realized_profit",
            new_callable=AsyncMock, return_value=([self.raw("kr")], self.source_key, self.source_label),
        ):
            fetched = self.client.post(
                "/api/kiwoom/realized-feed/fetch", headers=self.headers(),
                json={"market": "kr", "from_date": "20260901", "to_date": "20260930"},
            )
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["source"], "kiwoom")
        self.assertFalse(fetched.json()["source_scope_verified"])
        self.assertNotIn("acctNo", fetched.text)

    def test_domestic_preview_import_repreview_replay_and_provenance(self):
        selected = self.selected("kr")
        pnl_file = pnl_records._get_pnl_file(self.username)
        preview = self.preview("kr", selected)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["counts"], {"selected": 1, "new": 1, "already_imported": 0, "possible_duplicate": 0, "invalid": 0})
        self.assertFalse(pnl_file.exists())
        self.assertFalse(self.main._kiwoom_mapping_file(self.username).exists())
        payload = {**self.import_payload("kr", selected), "preview_ticket": preview.json()["preview_ticket"]}
        imported = self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["imported"], 1)
        records = pnl_records.read_pnl_records(self.username)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["source"], "kiwoom")
        self.assertFalse(record["source_scope_verified"])
        self.assertEqual(record["pnl"], 17.0)
        self.assertEqual(record["buy_amount"], "20")
        self.assertEqual(record["sell_amount"], "40")
        self.assertEqual(record["source_meta"]["buy_amount_semantics"], "DERIVED")
        self.assertNotEqual(record["pnl"], 14.0)
        for forbidden in ("selection_token", "preview_ticket", "acctNo", "provider_response"):
            self.assertNotIn(forbidden, json.dumps(record))
        self.assertEqual(self.main._read_kiwoom_mapping(self.username)[self.source_key], self.destination["id"])
        self.assertEqual(self.preview("kr", selected).json()["counts"]["already_imported"], 1)
        replay = self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["imported"], 0)
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

    def test_overseas_import_preserves_financial_semantics(self):
        selected = self.selected("us")
        payload = self.import_payload("us", selected)
        response = self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        record = pnl_records.read_pnl_records(self.username)[0]
        self.assertEqual(record["currency"], "USD")
        self.assertEqual(record["expenses_total"], "3")
        self.assertEqual(record["pnl"], 17.0)
        self.assertNotEqual(record["pnl"], 14.0)
        for field in ("fee", "tax", "pnl_krw", "fx_rate"):
            self.assertIsNone(record[field])
        self.assertEqual(record["country"], "United States")
        self.assertEqual(record["exchange"], "Synthetic Exchange")
        self.assertFalse(record["source_scope_verified"])

    def test_same_request_duplicate_and_legitimate_occurrences(self):
        selected = self.selected("kr")
        repeated = selected + [dict(selected[0])]
        preview = self.preview("kr", repeated)
        self.assertEqual(preview.json()["counts"]["new"], 1)
        self.assertEqual(preview.json()["counts"]["invalid"], 1)
        payload = {
            "market": "kr", "source_account_key": self.source_key,
            "account_id": self.destination["id"], "selected_items": repeated,
            "preview_ticket": preview.json()["preview_ticket"],
        }
        self.assertEqual(self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=payload).json()["imported"], 1)
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

        other_user = self.username + "-occurrences"
        portfolio.write_portfolio({"accounts": [self.destination], "holdings": [], "settings": {"fx_rates": {"KRW": 1.0}}}, other_user)
        with patch("app.services.user_manager.get_user_by_name", return_value={"username": other_user, "id": self.user_id, "role": "user", "must_change_password": False}):
            rows = [self.raw("kr"), self.raw("kr")]
            legitimate = self.selected("kr", rows)
            preview2 = self.client.post("/api/kiwoom/realized-feed/import-preview", headers=self.headers(), json={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":legitimate})
            self.assertEqual(preview2.json()["counts"]["new"], 2)

    def test_tamper_manual_duplicate_and_malformed_storage_fail_closed(self):
        selected = self.selected("kr")
        selected[0]["row"]["pnl"] = "99"
        self.assertEqual(self.preview("kr", selected).json()["counts"]["invalid"], 1)
        pnl_records.create_pnl_record({"date": "20260901", "code": "005930", "name": "Manual", "currency": "KRW", "pnl": 17, "pnl_krw": 17}, self.username)
        self.assertEqual(self.preview("kr").json()["counts"]["possible_duplicate"], 1)

        other_username = self.username + "-malformed"
        portfolio.write_portfolio({"accounts": [self.destination], "holdings": [], "settings": {"fx_rates": {"KRW": 1.0}}}, other_username)
        with patch("app.services.user_manager.get_user_by_name", return_value={"username": other_username, "id": self.user_id, "role": "user", "must_change_password": False}):
            selected2 = self.selected("kr")
            preview = self.client.post("/api/kiwoom/realized-feed/import-preview", headers=self.headers(), json={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected2}).json()
            pnl_file = pnl_records._get_pnl_file(other_username)
            original = b'{"records": [malformed synthetic bytes]'
            pnl_file.write_bytes(original)
            response = self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json={"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected2,"preview_ticket":preview["preview_ticket"]})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(pnl_file.read_bytes(), original)

    def test_mapping_partial_success_recovery_and_conflicts(self):
        selected = self.selected("kr")
        payload = self.import_payload("kr", selected)
        with patch.object(self.main, "_write_kiwoom_mapping", side_effect=OSError("synthetic failure")):
            first = self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["imported"], 1)
        self.assertTrue(first.json()["partial_success"])
        self.assertFalse(self.main._kiwoom_mapping_file(self.username).exists())

        second = {"id": "other", "broker": "키움증권", "name": "Other", "account_name": "Other", "owner": "본인"}
        portfolio.write_portfolio({"accounts": [self.destination, second], "holdings": [], "settings": {"fx_rates": {"KRW": 1.0}}}, self.username)
        wrong_preview = self.preview("kr", selected, destination_id=second["id"])
        wrong_payload = {"market":"kr","source_account_key":self.source_key,"account_id":second["id"],"selected_items":selected,"preview_ticket":wrong_preview.json()["preview_ticket"]}
        wrong = self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=wrong_payload)
        self.assertEqual(wrong.status_code, 409)
        self.assertFalse(self.main._kiwoom_mapping_file(self.username).exists())

        retry = self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(retry.json()["imported"], 0)
        self.assertTrue(retry.json()["mapping_repaired"])
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

        self.assertEqual(self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=wrong_payload).status_code, 409)

    def test_preview_and_failed_prewrite_never_write_mapping(self):
        selected = self.selected("kr")
        with patch.object(self.main, "_write_kiwoom_mapping", wraps=self.main._write_kiwoom_mapping) as writer:
            preview = self.preview("kr", selected)
            self.assertEqual(preview.status_code, 200)
            writer.assert_not_called()
            payload = {"market":"kr","source_account_key":self.source_key,"account_id":self.destination["id"],"selected_items":selected,"preview_ticket":preview.json()["preview_ticket"] + "x"}
            self.assertEqual(self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=payload).status_code, 400)
            writer.assert_not_called()

    def test_financial_write_failure_and_scope_mismatch_do_not_map(self):
        selected = self.selected("kr")
        payload = self.import_payload("kr", selected)
        with (
            patch.object(self.main, "create_pnl_record", side_effect=pnl_records.PnlRecordsStorageError("synthetic write failure")),
            patch.object(self.main, "_write_kiwoom_mapping", wraps=self.main._write_kiwoom_mapping) as writer,
        ):
            with self.assertRaises(pnl_records.PnlRecordsStorageError):
                self.client.post("/api/kiwoom/realized-feed/import", headers=self.headers(), json=payload)
            writer.assert_not_called()
        self.assertFalse(self.main._kiwoom_mapping_file(self.username).exists())

        with patch(
            "app.services.kiwoom_openapi.KiwoomOpenAPI.get_realized_source_account_state",
            new_callable=AsyncMock, return_value=("different-source", self.source_label),
        ):
            mismatch = self.preview("kr", selected)
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(mismatch.json()["detail"]["code"], "SCOPE_MISMATCH")


if __name__ == "__main__":
    unittest.main()
