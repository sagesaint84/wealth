import json
import unittest
from unittest.mock import patch, AsyncMock
from pathlib import Path
from starlette.testclient import TestClient

from app.services import pnl_records, portfolio
from app.services.kis_feed import (
    sign_kis_feed_row,
    compute_kis_items_hash,
    sign_kis_import_preview_ticket,
)
from app.services.kis_realized import (
    map_kis_domestic_profit_row,
    build_kis_realized_fingerprint,
)
from app.services.user_identity import generate_user_id
try:
    from regression_support import IsolatedDataTestCase
except ImportError:
    from tests.regression_support import IsolatedDataTestCase
from tests.test_request_state_user_id import _import_main_without_loading_real_env


class KISRealizedImportTests(IsolatedDataTestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        super().setUp()
        self.user_id = generate_user_id()
        self._user_patcher = patch("app.services.user_manager.get_user_by_name", return_value={
            "username": "test-kis-user",
            "id": self.user_id,
            "role": "user",
            "must_change_password": False,
        })
        self._user_patcher.start()
        self.addCleanup(self._user_patcher.stop)

        self.mock_openapi_config = {
            "kis": {
                "app_key": "SYNTHETIC_APP_KEY",
                "app_secret": "SYNTHETIC_APP_SECRET",
                "account_no": "12345678-01",
                "is_virtual": False,
            }
        }
        from app.services import user_openapi
        self._openapi_patcher = patch.object(user_openapi, "get_user_openapi_config", return_value=self.mock_openapi_config)
        self._openapi_patcher.start()
        self.addCleanup(self._openapi_patcher.stop)
        self.username = "test-kis-user"
        self.user_record = {
            "username": self.username,
            "id": self.user_id,
            "role": "user",
            "must_change_password": False,
        }

        # Set up user data dir & openapi_config.json
        user_dir = Path(self.temp_dir.name) / "users" / self.username
        user_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = user_dir / "openapi_config.json"
        self.config_data = {
            "app_key": "TEST_APP_KEY",
            "app_secret": "TEST_APP_SECRET",
            "account_no": "12345678-01",
            "is_virtual": False,
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f)

        # Set up portfolio with destination accounts
        self.acc1 = {
            "id": "acc-kis-101",
            "broker": "한국투자증권",
            "name": "한투 주식계좌",
            "account_name": "한투 주식계좌",
            "owner": "본인",
        }
        self.acc2 = {
            "id": "acc-other-202",
            "broker": "토스증권",
            "name": "토스 계좌",
            "account_name": "토스 계좌",
            "owner": "배우자",
        }
        init_portfolio = {
            "accounts": [self.acc1, self.acc2],
            "holdings": [],
            "settings": {"fx_rates": {"KRW": 1.0}},
        }
        portfolio.write_portfolio(init_portfolio, username=self.username)

    def _cookie_header(self) -> dict[str, str]:
        token = self.main._serializer.dumps({"user": self.username, "role": "user"})
        return {"Cookie": f"{self.main.COOKIE_NAME}={token}"}

    def test_kis_status_configured(self):
        res = self.client.get("/api/kis/status", headers=self._cookie_header())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["configured"])
        self.assertTrue(data["has_account"])
        self.assertEqual(data["masked_account"], "1234****-01")
        self.assertEqual(data["source_account_label"], "1234****-01")
        self.assertTrue(data["source_scope_verified"])
        self.assertEqual(len(data["source_account_key"]), 64)
        # Verify NO raw CANO in status response
        self.assertNotIn("12345678", json.dumps(data))
        # First use: no mapped destination account yet
        self.assertIsNone(data.get("mapped_destination_account_id"))

    @patch("app.services.kis_openapi.KISOpenAPI.fetch_realized_profit", new_callable=AsyncMock)
    def test_kis_feed_fetch_domestic_happy_path(self, mock_fetch):
        from app.services.kis_openapi import compute_kis_account_key
        account_key = compute_kis_account_key("12345678", "01")
        mock_rows = [
            {
                "trad_dt": "20240410",
                "pdno": "005930",
                "prdt_name": "삼성전자",
                "sll_qty": "10",
                "sll_amt": "840000",
                "pchs_amt": "700000",
                "rlzt_pfls": "140000",
                "pfls_rt": "20.00",
                "fee": "100",
                "tl_tax": "1500",
            }
        ]
        mock_fetch.return_value = (mock_rows, account_key, "1234****-01")

        payload = {
            "market": "kr",
            "from_date": "2024-04-01",
            "to_date": "2024-04-30",
        }
        res = self.client.post("/api/kis/realized-feed/fetch", json=payload, headers=self._cookie_header())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["source"], "kis")
        self.assertTrue(data["scope_verified"])
        self.assertEqual(data["source_account_key"], account_key)
        self.assertEqual(data["source_account_label"], "1234****-01")
        self.assertEqual(len(data["rows"]), 1)
        self.assertEqual(len(data["selection_tokens"]), 1)
        self.assertEqual(data["rows"][0]["code"], "005930")
        self.assertEqual(data["rows"][0]["profit_loss"], 140000.0)
        self.assertNotIn("raw", data["rows"][0])
        # Verify NO raw CANO in feed response
        self.assertNotIn("12345678", json.dumps(data))

    @patch("app.services.kis_openapi.KISOpenAPI.fetch_realized_profit", new_callable=AsyncMock)
    def test_import_preview_and_commit_flow(self, mock_fetch):
        from app.services.kis_openapi import compute_kis_account_key
        account_key = compute_kis_account_key("12345678", "01")
        # 1. Fetch
        mock_rows = [
            {
                "trad_dt": "20240410",
                "pdno": "005930",
                "prdt_name": "삼성전자",
                "sll_qty": "10",
                "sll_amt": "840000",
                "pchs_amt": "700000",
                "rlzt_pfls": "140000",
                "pfls_rt": "20.00",
                "fee": "100",
                "tl_tax": "1500",
            }
        ]
        mock_fetch.return_value = (mock_rows, account_key, "1234****-01")

        fetch_res = self.client.post(
            "/api/kis/realized-feed/fetch",
            json={"market": "kr", "from_date": "2024-04-01", "to_date": "2024-04-30"},
            headers=self._cookie_header(),
        )
        self.assertEqual(fetch_res.status_code, 200)
        feed = fetch_res.json()
        row = feed["rows"][0]
        token = feed["selection_tokens"][0]

        # 2. Preview
        preview_payload = {
            "selected_items": [{"row": row, "selection_token": token}],
            "account_id": "acc-kis-101",
            "market": "kr",
        }
        preview_res = self.client.post(
            "/api/kis/realized-feed/import-preview",
            json=preview_payload,
            headers=self._cookie_header(),
        )
        self.assertEqual(preview_res.status_code, 200)
        preview_data = preview_res.json()
        self.assertEqual(preview_data["counts"]["new"], 1)
        self.assertEqual(preview_data["counts"]["already_imported"], 0)
        self.assertEqual(preview_data["source_account_key"], account_key)
        self.assertEqual(preview_data["source_account_label"], "1234****-01")
        self.assertNotIn("12345678", json.dumps(preview_data))
        preview_ticket = preview_data["preview_ticket"]
        self.assertTrue(preview_ticket)

        # 3. Import
        import_payload = {
            "selected_items": [{"row": row, "selection_token": token}],
            "account_id": "acc-kis-101",
            "preview_ticket": preview_ticket,
            "market": "kr",
        }
        import_res = self.client.post(
            "/api/kis/realized-feed/import",
            json=import_payload,
            headers=self._cookie_header(),
        )
        self.assertEqual(import_res.status_code, 200)
        import_data = import_res.json()
        self.assertEqual(import_data["imported"], 1)
        self.assertEqual(import_data["already_imported"], 0)
        self.assertEqual(len(import_data["imported_ids"]), 1)
        self.assertNotIn("12345678", json.dumps(import_data))

        # Check records in DB
        records = pnl_records.read_pnl_records(username=self.username)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["code"], "005930")
        self.assertEqual(rec["name"], "삼성전자")
        self.assertEqual(rec["pnl"], 140000.0)
        self.assertEqual(rec["pnl_krw"], 140000.0)
        self.assertEqual(rec["source"], "kis")
        self.assertEqual(rec["source_account_key"], account_key)
        self.assertEqual(rec["source_account_label"], "1234****-01")
        self.assertTrue(rec["source_scope_verified"])
        self.assertTrue(rec["imported_by_user_action"])
        self.assertEqual(rec["account_name"], "한투 주식계좌")
        self.assertEqual(rec["broker"], "한국투자증권")
        self.assertNotIn("raw", rec["source_meta"])
        # CRITICAL: Verify NO raw CANO persisted in PnL record provenance
        self.assertNotIn("12345678", json.dumps(rec))

        # Check persistent mapping created
        status_after = self.client.get("/api/kis/status", headers=self._cookie_header()).json()
        self.assertEqual(status_after["mapped_destination_account_id"], "acc-kis-101")

        # 4. Re-import (Duplicate protection check)
        reimport_res = self.client.post(
            "/api/kis/realized-feed/import",
            json=import_payload,
            headers=self._cookie_header(),
        )
        self.assertEqual(reimport_res.status_code, 200)
        reimport_data = reimport_res.json()
        self.assertEqual(reimport_data["imported"], 0)
        self.assertEqual(reimport_data["already_imported"], 1)
        # Record count still 1
        self.assertEqual(len(pnl_records.read_pnl_records(username=self.username)), 1)

    def test_tampered_preview_ticket_rejected(self):
        from app.services.kis_openapi import compute_kis_account_key
        account_key = compute_kis_account_key("12345678", "01")
        row = {
            "date": "2024-04-10",
            "trad_dt": "20240410",
            "pdno": "005930",
            "name": "삼성전자",
            "quantity": 10.0,
            "sell_amount": 840000.0,
            "buy_amount": 700000.0,
            "profit_loss": 140000.0,
            "profit_rate": 20.0,
            "fee": 100.0,
            "tax": 1500.0,
        }
        token = sign_kis_feed_row(row, user_id=self.user_id, source_account_key=account_key)
        payload = {
            "selected_items": [{"row": row, "selection_token": token}],
            "account_id": "acc-kis-101",
            "preview_ticket": "tampered_ticket",
            "market": "kr",
        }
        res = self.client.post(
            "/api/kis/realized-feed/import",
            json=payload,
            headers=self._cookie_header(),
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("PREVIEW_TICKET_INVALID", res.json()["detail"]["code"])

    def test_kis_status_unconfigured(self):
        from app.services import user_openapi
        with patch.object(user_openapi, "get_user_openapi_config", return_value={}):
            res = self.client.get("/api/kis/status", headers=self._cookie_header())
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertFalse(data["configured"])
            self.assertFalse(data["has_account"])
            self.assertEqual(data["source_account_key"], "")

    @patch("app.services.kis_openapi.KISOpenAPI.fetch_realized_profit", new_callable=AsyncMock)
    def test_overseas_import_flow(self, mock_fetch):
        from app.services.kis_openapi import compute_kis_account_key
        account_key = compute_kis_account_key("12345678", "01")
        mock_rows = [
            {
                "trad_day": "20240320",
                "ovrs_pdno": "TSLA",
                "ovrs_item_name": "테슬라",
                "slcl_qty": "5",
                "frcr_sll_amt_smtl1": "1000.0",
                "frcr_pchs_amt1": "800.0",
                "ovrs_rlzt_pfls_amt": "200.0",
                "pftrt": "25.0",
                "bass_exrt": "1350.0",
                "crcy_cd": "USD",
                "stck_sll_amt_smtl": "1350000",
                "stck_buy_amt_smtl": "1080000",
            }
        ]
        mock_fetch.return_value = (mock_rows, account_key, "1234****-01")

        fetch_res = self.client.post(
            "/api/kis/realized-feed/fetch",
            json={"market": "us", "from_date": "2024-03-01", "to_date": "2024-03-31"},
            headers=self._cookie_header(),
        )
        self.assertEqual(fetch_res.status_code, 200)
        row = fetch_res.json()["rows"][0]
        token = fetch_res.json()["selection_tokens"][0]

        preview_res = self.client.post(
            "/api/kis/realized-feed/import-preview",
            json={"selected_items": [{"row": row, "selection_token": token}], "account_id": "acc-kis-101", "market": "us"},
            headers=self._cookie_header(),
        )
        self.assertEqual(preview_res.status_code, 200)
        preview_ticket = preview_res.json()["preview_ticket"]

        import_res = self.client.post(
            "/api/kis/realized-feed/import",
            json={"selected_items": [{"row": row, "selection_token": token}], "account_id": "acc-kis-101", "preview_ticket": preview_ticket, "market": "us"},
            headers=self._cookie_header(),
        )
        self.assertEqual(import_res.status_code, 200)
        self.assertEqual(import_res.json()["imported"], 1)

        records = pnl_records.read_pnl_records(username=self.username)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["code"], "TSLA")
        self.assertEqual(rec["currency"], "USD")
        self.assertEqual(rec["pnl"], 200.0)
        self.assertEqual(rec["fx_rate"], 1350.0)
        self.assertEqual(rec["pnl_krw"], 270000.0)
        self.assertNotIn("12345678", json.dumps(rec))
        self.assertNotIn("raw", rec["source_meta"])

    @patch("app.services.kis_openapi.KISOpenAPI.fetch_realized_profit", new_callable=AsyncMock)
    def test_overseas_import_without_fx_yields_none_pnl_krw(self, mock_fetch):
        from app.services.kis_openapi import compute_kis_account_key
        account_key = compute_kis_account_key("12345678", "01")
        mock_rows = [
            {
                "trad_day": "20240320",
                "ovrs_pdno": "TSLA",
                "ovrs_item_name": "테슬라",
                "slcl_qty": "5",
                "frcr_sll_amt_smtl1": "1000.0",
                "frcr_pchs_amt1": "800.0",
                "ovrs_rlzt_pfls_amt": "200.0",
                "pftrt": "25.0",
                "crcy_cd": "USD",
            }
        ]
        mock_fetch.return_value = (mock_rows, account_key, "1234****-01")

        fetch_res = self.client.post(
            "/api/kis/realized-feed/fetch",
            json={"market": "us", "from_date": "2024-03-01", "to_date": "2024-03-31"},
            headers=self._cookie_header(),
        )
        self.assertEqual(fetch_res.status_code, 200)
        row = fetch_res.json()["rows"][0]
        token = fetch_res.json()["selection_tokens"][0]

        preview_res = self.client.post(
            "/api/kis/realized-feed/import-preview",
            json={"selected_items": [{"row": row, "selection_token": token}], "account_id": "acc-kis-101", "market": "us"},
            headers=self._cookie_header(),
        )
        self.assertEqual(preview_res.status_code, 200)
        preview_ticket = preview_res.json()["preview_ticket"]

        import_res = self.client.post(
            "/api/kis/realized-feed/import",
            json={"selected_items": [{"row": row, "selection_token": token}], "account_id": "acc-kis-101", "preview_ticket": preview_ticket, "market": "us"},
            headers=self._cookie_header(),
        )
        self.assertEqual(import_res.status_code, 200)

        records = pnl_records.read_pnl_records(username=self.username)
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["code"], "TSLA")
        self.assertEqual(rec["currency"], "USD")
        self.assertEqual(rec["pnl"], 200.0)
        self.assertIsNone(rec["fx_rate"])
        self.assertIsNone(rec["pnl_krw"])  # MUST remain None, NEVER foreign_pnl!

    def test_destination_account_alteration_blocked(self):
        from app.services.kis_openapi import compute_kis_account_key
        account_key = compute_kis_account_key("12345678", "01")
        row = {
            "date": "2024-04-10",
            "trad_dt": "20240410",
            "pdno": "005930",
            "name": "삼성전자",
            "quantity": 10.0,
            "sell_amount": 840000.0,
            "buy_amount": 700000.0,
            "profit_loss": 140000.0,
        }
        token = sign_kis_feed_row(row, user_id=self.user_id, source_account_key=account_key)
        items_hash = compute_kis_items_hash([{"row": row, "selection_token": token}])
        ticket = sign_kis_import_preview_ticket("acc-kis-101", items_hash, self.user_id, account_key)

        payload = {
            "selected_items": [{"row": row, "selection_token": token}],
            "account_id": "acc-other-202",
            "preview_ticket": ticket,
            "market": "kr",
        }
        res = self.client.post(
            "/api/kis/realized-feed/import",
            json=payload,
            headers=self._cookie_header(),
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("DESTINATION_ACCOUNT_CHANGED", res.json()["detail"]["code"])


if __name__ == "__main__":
    unittest.main()
