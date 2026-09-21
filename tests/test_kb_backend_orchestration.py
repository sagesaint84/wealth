import json
import unittest
from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from app.services import pnl_records, portfolio, user_openapi
from app.services.user_identity import generate_user_id
from tests.regression_support import IsolatedDataTestCase
from tests.test_request_state_user_id import _import_main_without_loading_real_env


class KBBackendOrchestrationTests(IsolatedDataTestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        super().setUp()
        self.username = "synthetic-kb-user"
        self.user_id = generate_user_id()
        self.source_key = "b" * 64
        self.source_label = "****4321-**"
        self.destination = {
            "id": "kb-destination", "broker": "KB증권", "name": "Synthetic account",
            "account_name": "Synthetic account", "owner": "본인",
        }
        portfolio.write_portfolio(
            {"accounts": [self.destination], "holdings": [], "settings": {"fx_rates": {"KRW": 1.0}}},
            self.username,
        )
        def _isolated_kb_init(kb_self, username='sagesaint'):
            kb_self.username = username
            cfg = user_openapi.get_user_openapi_config(username).get('kb', {})
            kb_self.base_url = 'https://developer.kbsec.com:32484'
            kb_self.app_key = cfg.get('app_key', '')
            kb_self.app_secret = cfg.get('app_secret', '')
            kb_self.gnl_ac_no = cfg.get('gnl_ac_no', '').replace('-', '').strip()
            kb_self.gds_no = cfg.get('gds_no', '').strip()
            kb_self._token = None
            user_dir = self.fixture_user_dir(username)
            kb_self.token_cache_file = user_dir / 'kb_token_cache.json'

        self.patchers = [
            patch('app.services.kb_openapi.KBOpenAPI.__init__', _isolated_kb_init),
            patch("app.services.user_manager.get_user_by_name", return_value={
                "username": self.username, "id": self.user_id, "role": "user", "must_change_password": False,
            }),
            patch.object(user_openapi, "get_user_openapi_config", return_value={
                "kb": {
                    "app_key": "SYNTHETIC", "app_secret": "SYNTHETIC",
                    "gnl_ac_no": "123456789", "gds_no": "77",
                },
            }),
            patch(
                "app.services.kb_openapi.KBOpenAPI.get_realized_source_account_state",
                return_value=(self.source_key, self.source_label),
            ),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        super().tearDown()

    def headers(self):
        token = self.main._serializer.dumps({"user": self.username, "role": "user"})
        return {"Cookie": f"{self.main.COOKIE_NAME}={token}"}

    @staticmethod
    def raw(**updates):
        row = {
            "trd_dt": "20260901", "shrt_is_cd": "A005930", "is_nm": "Synthetic Domestic",
            "trd_dl_ccd": "01", "crdt_typ_cd": "00", "dtls_ccls_q": "2",
            "dcml_dl_f": "0", "ccls_uprc": "20", "b_uprc": "10",
            "s_amt": "40", "b_amt": "20", "fee": "1", "svrl_tx": "2",
            "rlztn_pl": "17", "yld": "85",
        }
        row.update(updates)
        return row

    def selected(self, rows=None):
        from app.services.kb_feed import build_kb_realized_feed
        feed = build_kb_realized_feed(
            rows or [self.raw()], market="kr", source_account_key=self.source_key,
            source_account_label=self.source_label, user_id=self.user_id,
        )
        return [{"row": row, "selection_token": token} for row, token in zip(feed["rows"], feed["selection_tokens"])]

    def preview(self, selected=None, destination_id=None, market="kr"):
        return self.client.post(
            "/api/kb/realized-feed/import-preview", headers=self.headers(),
            json={
                "market": market, "source_account_key": self.source_key,
                "account_id": destination_id or self.destination["id"],
                "selected_items": selected or self.selected(),
            },
        )

    def payload(self, selected):
        preview = self.preview(selected)
        self.assertEqual(preview.status_code, 200, preview.text)
        return {
            "market": "kr", "source_account_key": self.source_key,
            "account_id": self.destination["id"], "selected_items": selected,
            "preview_ticket": preview.json()["preview_ticket"],
        }

    def test_status_readiness_privacy_and_unsupported_overseas(self):
        response = self.client.get("/api/kb/status", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertTrue(data["configured"])
        self.assertEqual(data["available_markets"], ["kr"])
        self.assertFalse(data["source_scope_verified"])
        for forbidden in ("123456789", "gnl_ac_no", "gds_no", "app_secret", "access_token"):
            self.assertNotIn(forbidden, response.text)

        overseas = self.client.post(
            "/api/kb/realized-feed/fetch", headers=self.headers(),
            json={"market": "us", "from_date": "20260901", "to_date": "20260930"},
        )
        self.assertEqual(overseas.status_code, 400)
        self.assertEqual(overseas.json()["detail"]["code"], "UNSUPPORTED_MARKET")

    def test_status_requires_credentials_account_and_product(self):
        cases = [
            {"app_key": "", "app_secret": "", "gnl_ac_no": "123", "gds_no": "77"},
            {"app_key": "x", "app_secret": "y", "gnl_ac_no": "", "gds_no": "77"},
            {"app_key": "x", "app_secret": "y", "gnl_ac_no": "123", "gds_no": ""},
        ]
        for config in cases:
            with self.subTest(config=set(k for k, v in config.items() if v)), patch.object(
                user_openapi, "get_user_openapi_config", return_value={"kb": config},
            ):
                data = self.client.get("/api/kb/status", headers=self.headers()).json()
                self.assertFalse(data["configured"])
                self.assertEqual(data["accounts"], [])

    def test_cross_broker_destination_is_rejected(self):
        foreign = {"id": "foreign-nh", "broker": "NH투자증권", "name": "not KB"}
        portfolio.write_portfolio(
            {"accounts": [self.destination, foreign], "holdings": [], "settings": {"fx_rates": {"KRW": 1.0}}},
            self.username,
        )
        response = self.preview(destination_id=foreign["id"])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "DESTINATION_BROKER_MISMATCH")

    def test_fetch_is_transient_signed_and_leak_free(self):
        with patch(
            "app.services.kb_openapi.KBOpenAPI.fetch_domestic_realized_pnl",
            new_callable=AsyncMock, return_value=([self.raw()], self.source_key, self.source_label),
        ):
            response = self.client.post(
                "/api/kb/realized-feed/fetch", headers=self.headers(),
                json={"market": "domestic", "from_date": "20260901", "to_date": "20260930"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["source"], "kb")
        self.assertFalse(data["source_scope_verified"])
        self.assertEqual(data["rows"][0]["pnl"], "17")
        self.assertEqual(len(data["selection_tokens"]), 1)
        self.assertEqual(pnl_records.read_pnl_records_readonly(self.username), [])
        self.assertFalse(self.main._kb_mapping_file(self.username).exists())
        for forbidden in ("123456789", "gnl_ac_no", "gds_no", "raw_provider", "access_token"):
            self.assertNotIn(forbidden, response.text)

    def test_preview_import_repreview_replay_and_provenance(self):
        selected = self.selected()
        preview = self.preview(selected)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.json()["counts"], {
            "selected": 1, "new": 1, "already_imported": 0, "possible_duplicate": 0, "invalid": 0,
        })
        self.assertEqual(pnl_records.read_pnl_records_readonly(self.username), [])
        self.assertFalse(self.main._kb_mapping_file(self.username).exists())

        payload = {**self.payload(selected), "preview_ticket": preview.json()["preview_ticket"]}
        imported = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()["imported"], 1)
        records = pnl_records.read_pnl_records(self.username)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["source"], "kb")
        self.assertEqual(record["account_id"], self.destination["id"])
        self.assertEqual(record["destination_account_id"], self.destination["id"])
        self.assertFalse(record["source_scope_verified"])
        self.assertEqual(record["pnl"], 17)
        self.assertEqual(record["fee"], "1")
        self.assertEqual(record["tax"], "2")
        self.assertNotEqual(record["pnl"], 14)
        self.assertEqual(record["source_meta"], {
            "api_id": "SSQM2442", "pnl_netness": "PROVIDER_AUTHORITATIVE_UNVERIFIED",
        })
        serialized = json.dumps(record, ensure_ascii=False)
        for forbidden in ("123456789", "gnl_ac_no", "gds_no", "selection_token", "preview_ticket", "provider_response"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(self.main._read_kb_mapping(self.username)[self.source_key], self.destination["id"])
        self.assertEqual(self.preview(selected).json()["counts"]["already_imported"], 1)
        replay = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["imported"], 0)
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

    def test_ipo_preference_ticket_binding_and_duplicate_identity(self):
        selected = self.selected()
        selected[0]["wealth_import"] = {"stock_type": "ipo", "ipo_subscription_fee_krw": 2}
        preview = self.preview(selected)
        self.assertEqual(preview.status_code, 200, preview.text)
        detail = preview.json()["items"][0]["wealth_import"]
        self.assertEqual(detail["provider_realized_pnl"], "17")
        self.assertEqual(detail["final_wealth_pnl"], "15")
        self.assertEqual(detail["memo"], "공모수수료 2원 차감")

        changed = json.loads(json.dumps(selected))
        changed[0]["wealth_import"]["ipo_subscription_fee_krw"] = 3
        bad = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json={
            "market": "kr", "source_account_key": self.source_key,
            "account_id": self.destination["id"], "selected_items": changed,
            "preview_ticket": preview.json()["preview_ticket"],
        })
        self.assertEqual(bad.status_code, 400)

        good = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json={
            "market": "kr", "source_account_key": self.source_key,
            "account_id": self.destination["id"], "selected_items": selected,
            "preview_ticket": preview.json()["preview_ticket"],
        })
        self.assertEqual(good.json()["imported"], 1)
        record = pnl_records.read_pnl_records(self.username)[0]
        self.assertEqual(record["pnl"], 15)
        self.assertEqual(record["provider_realized_pnl"], "17")
        self.assertEqual(record["fee"], "1")
        self.assertEqual(record["tax"], "2")

        changed_type = json.loads(json.dumps(selected))
        changed_type[0]["wealth_import"] = {"stock_type": "general", "ipo_subscription_fee_krw": 0}
        second = self.preview(changed_type)
        self.assertEqual(second.json()["counts"]["already_imported"], 1)

    def test_ipo_default_fee_and_general_preference_use_common_layer(self):
        general = self.selected()
        general[0]["wealth_import"] = {"stock_type": "general", "ipo_subscription_fee_krw": 9999}
        general_response = self.preview(general)
        general_preview = general_response.json()["items"][0]["wealth_import"]
        self.assertEqual(general_preview["ipo_subscription_fee_krw"], 0)
        self.assertEqual(general_preview["final_wealth_pnl"], "17")

        ipo = self.selected()
        ipo[0]["wealth_import"] = {"stock_type": "ipo"}
        type_tamper = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json={
            "market": "kr", "source_account_key": self.source_key,
            "account_id": self.destination["id"], "selected_items": ipo,
            "preview_ticket": general_response.json()["preview_ticket"],
        })
        self.assertEqual(type_tamper.status_code, 400)
        preview = self.preview(ipo)
        detail = preview.json()["items"][0]["wealth_import"]
        self.assertEqual(detail["ipo_subscription_fee_krw"], 2000)
        self.assertEqual(detail["final_wealth_pnl"], "-1983")
        self.assertEqual(detail["memo"], "공모수수료 2천원 차감")
        self.assertEqual(
            general_response.json()["items"][0]["fingerprint"],
            preview.json()["items"][0]["fingerprint"],
        )

    def test_same_request_duplicate_occurrences_tamper_and_manual_match(self):
        selected = self.selected()
        repeated = selected + [dict(selected[0])]
        preview = self.preview(repeated)
        self.assertEqual(preview.json()["counts"]["new"], 1)
        self.assertEqual(preview.json()["counts"]["invalid"], 1)
        payload = {
            "market": "kr", "source_account_key": self.source_key,
            "account_id": self.destination["id"], "selected_items": repeated,
            "preview_ticket": preview.json()["preview_ticket"],
        }
        self.assertEqual(self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json=payload).json()["imported"], 1)

        other = self.username + "-occ"
        portfolio.write_portfolio({"accounts": [self.destination], "holdings": []}, other)
        with patch("app.services.user_manager.get_user_by_name", return_value={
            "username": other, "id": self.user_id, "role": "user", "must_change_password": False,
        }):
            legitimate = self.selected([self.raw(), self.raw()])
            result = self.client.post("/api/kb/realized-feed/import-preview", headers=self.headers(), json={
                "market": "kr", "source_account_key": self.source_key,
                "account_id": self.destination["id"], "selected_items": legitimate,
            }).json()
            self.assertEqual(result["counts"]["new"], 2)

        tampered = self.selected()
        tampered[0]["row"]["fee"] = "999"
        self.assertEqual(self.preview(tampered).json()["counts"]["invalid"], 1)

        manual_user = self.username + "-manual"
        portfolio.write_portfolio({"accounts": [self.destination], "holdings": []}, manual_user)
        pnl_records.create_pnl_record({"date": "20260901", "code": "005930", "name": "Manual", "pnl": 17, "pnl_krw": 17}, manual_user)
        with patch("app.services.user_manager.get_user_by_name", return_value={
            "username": manual_user, "id": self.user_id, "role": "user", "must_change_password": False,
        }):
            self.assertEqual(self.preview(self.selected()).json()["counts"]["possible_duplicate"], 1)

    def test_commit_reclassification_and_malformed_storage_fail_closed(self):
        selected = self.selected()
        preview = self.preview(selected).json()
        candidate = dict(selected[0]["row"])
        from app.services.kb_realized import kb_fingerprint
        candidate.update({
            "source": "kb",
            "source_fingerprint": kb_fingerprint(candidate, self.source_key, 1),
            "source_account_key": self.source_key,
            "destination_account_id": self.destination["id"],
        })
        pnl_records.create_pnl_record(candidate, self.username)
        response = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json={
            "market": "kr", "source_account_key": self.source_key,
            "account_id": self.destination["id"], "selected_items": selected,
            "preview_ticket": preview["preview_ticket"],
        })
        self.assertEqual(response.json()["imported"], 0)
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

        malformed_user = self.username + "-malformed"
        portfolio.write_portfolio({"accounts": [self.destination], "holdings": []}, malformed_user)
        with patch("app.services.user_manager.get_user_by_name", return_value={
            "username": malformed_user, "id": self.user_id, "role": "user", "must_change_password": False,
        }):
            selected2 = self.selected()
            preview2 = self.preview(selected2).json()
            path = pnl_records._get_pnl_file(malformed_user)
            original = b'{"records": [malformed synthetic bytes]'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original)
            rejected = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json={
                "market": "kr", "source_account_key": self.source_key,
                "account_id": self.destination["id"], "selected_items": selected2,
                "preview_ticket": preview2["preview_ticket"],
            })
            self.assertEqual(rejected.status_code, 409)
            self.assertEqual(path.read_bytes(), original)

    def test_mapping_partial_success_recovery_and_conflicts(self):
        selected = self.selected()
        payload = self.payload(selected)
        with patch.object(self.main, "_write_kb_mapping", side_effect=OSError("synthetic failure")):
            first = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(first.json()["imported"], 1)
        self.assertTrue(first.json()["partial_success"])
        self.assertFalse(self.main._kb_mapping_file(self.username).exists())

        second = {"id": "other", "broker": "KB증권", "name": "Other", "owner": "본인"}
        portfolio.write_portfolio({"accounts": [self.destination, second], "holdings": []}, self.username)
        wrong_preview = self.preview(selected, destination_id=second["id"])
        wrong = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json={
            "market": "kr", "source_account_key": self.source_key, "account_id": second["id"],
            "selected_items": selected, "preview_ticket": wrong_preview.json()["preview_ticket"],
        })
        self.assertEqual(wrong.status_code, 409)

        retry = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(retry.json()["imported"], 0)
        self.assertTrue(retry.json()["mapping_repaired"])
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)
        self.assertEqual(self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json={
            "market": "kr", "source_account_key": self.source_key, "account_id": second["id"],
            "selected_items": selected, "preview_ticket": wrong_preview.json()["preview_ticket"],
        }).status_code, 409)

    def test_preview_and_failed_import_do_not_map(self):
        selected = self.selected()
        with patch.object(self.main, "_write_kb_mapping", wraps=self.main._write_kb_mapping) as writer:
            preview = self.preview(selected)
            writer.assert_not_called()
            bad = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json={
                "market": "kr", "source_account_key": self.source_key,
                "account_id": self.destination["id"], "selected_items": selected,
                "preview_ticket": preview.json()["preview_ticket"] + "x",
            })
            self.assertEqual(bad.status_code, 400)
            writer.assert_not_called()

        with patch(
            "app.services.kb_openapi.KBOpenAPI.get_realized_source_account_state",
            return_value=("different-source", self.source_label),
        ):
            mismatch = self.preview(selected)
        self.assertEqual(mismatch.status_code, 400)
        self.assertEqual(mismatch.json()["detail"]["code"], "SCOPE_MISMATCH")

    def test_financial_write_failure_and_malformed_mapping_fail_closed(self):
        selected = self.selected()
        payload = self.payload(selected)
        with (
            patch.object(self.main, "create_pnl_record", side_effect=pnl_records.PnlRecordsStorageError("synthetic write failure")),
            patch.object(self.main, "_write_kb_mapping", wraps=self.main._write_kb_mapping) as writer,
        ):
            with self.assertRaises(pnl_records.PnlRecordsStorageError):
                self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json=payload)
            writer.assert_not_called()
        self.assertEqual(pnl_records.read_pnl_records_readonly(self.username), [])

        mapping_file = self.main._kb_mapping_file(self.username)
        mapping_file.write_text("{malformed synthetic mapping", encoding="utf-8")
        rejected = self.client.post("/api/kb/realized-feed/import", headers=self.headers(), json=payload)
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.json()["detail"]["code"], "DESTINATION_MAPPING_INVALID")
        self.assertEqual(pnl_records.read_pnl_records_readonly(self.username), [])


if __name__ == "__main__":
    unittest.main()
