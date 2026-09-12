"""Integration and regression tests for Toss WTS selective import (Wealth v1.1.1).

Covers:
- Test 41: Selective import happy path (destination attribution, provenance fields)
- Test 42: Reimport duplicate protection (ALREADY_IMPORTED multiset match)
- Test 43: Manual duplicate detection & override toggle (POSSIBLE_DUPLICATE)
- Test 44: Client row tampering rejected (INVALID, cannot forge profit)
- Test 45: Post-preview destination alteration blocked (DESTINATION_ACCOUNT_CHANGED)
- Test 46: Concurrent duplicate commit-time recheck
- Test 47: Multiset duplicate safety
- Test 51: Static auth guard (401 / 403)
- Test 52: Unconfirmed runtime session guard (409)
- Test 53: Read-only fetch zero writes
- Test 54: UI selection & preview zero writes
- Test 55: Scope warning presence
- Test 56: Existing v1.1.0 flow preservation
- Test 57: Manual records unaffected
"""

from __future__ import annotations

import copy
from datetime import date
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from app.services import pnl_records, portfolio
from app.services.toss_wts_adapter import TossWtsAdapter
from app.services.toss_wts_feed import (
    build_realized_feed_response,
    sign_realized_feed_row,
)
from app.services.toss_wts_feed_auth import WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID
from app.services.toss_wts_feed_runtime import (
    clear_wts_feed_runtime_confirmation,
    confirm_wts_feed_runtime_session,
    get_current_runtime_generation_id,
)
from app.services.user_identity import generate_user_id
try:
    from regression_support import IsolatedDataTestCase
except ImportError:
    from tests.regression_support import IsolatedDataTestCase
from tests.test_request_state_user_id import _import_main_without_loading_real_env


class TossWtsRealizedImportTests(IsolatedDataTestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        super().setUp()
        clear_wts_feed_runtime_confirmation()
        self.addCleanup(clear_wts_feed_runtime_confirmation)

        self.user_id = generate_user_id()
        self.username = "test-user-v111"
        self.user_record = {
            "username": self.username,
            "id": self.user_id,
            "role": "user",
            "must_change_password": False,
        }

        # Mock binary and config directory for WTS adapter
        self.toss_root = Path(self.temp_dir.name) / "tossctl_env"
        self.toss_root.mkdir(parents=True, exist_ok=True)
        self.exe_path = self.toss_root / "tossctl"
        self.exe_path.write_text("synthetic_tossctl_binary", encoding="utf-8")
        self.config_dir = self.toss_root / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.session_path = self.config_dir / "session.json"
        self.session_path.write_text('{"token": "SYNTHETIC_WTS_TOKEN_V111"}', encoding="utf-8")

        # Set up portfolio with destination accounts
        self.acc1 = {
            "id": "acc-wts-101",
            "broker": "토스증권",
            "name": "토스 종합계좌",
            "account_name": "토스 종합계좌",
            "owner": "본인",
        }
        self.acc2 = {
            "id": "acc-other-202",
            "broker": "미래에셋증권",
            "name": "미래에셋 위탁",
            "account_name": "미래에셋 위탁",
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

    def _env(self) -> dict[str, str]:
        return {
            WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: self.user_id,
            "WEALTH_TOSS_WTS_ENABLED": "1",
            "WEALTH_TOSSCTL_PATH": str(self.exe_path),
            "WEALTH_TOSSCTL_CONFIG_DIR": str(self.config_dir),
        }

    @staticmethod
    def _sample_feed_rows() -> list[dict]:
        return [
            {
                "date": "2026-01-05",
                "market_type": "KR",
                "symbol": "005930",
                "product_code": "KR7005930003",
                "name": "삼성전자",
                "quantity": 10.0,
                "profit_loss": {"krw": 50000.0, "usd": 38.5},
                "profit_rate": 7.5,
                "sell_amount": {"krw": 750000.0, "usd": 576.9},
                "buy_amount": {"krw": 700000.0, "usd": 538.4},
            },
            {
                "date": "2026-01-08",
                "market_type": "US",
                "symbol": "AAPL",
                "product_code": "US0378331005",
                "name": "애플",
                "quantity": 5.0,
                "profit_loss": {"krw": 120000.0, "usd": 92.3},
                "profit_rate": 12.0,
                "sell_amount": {"krw": 1120000.0, "usd": 861.5},
                "buy_amount": {"krw": 1000000.0, "usd": 769.2},
            },
        ]

    def _get_confirmed_client(self):
        with patch.dict(os.environ, self._env(), clear=False):
            confirm_res = confirm_wts_feed_runtime_session(self.user_id)
            self.assertTrue(confirm_res.confirmed, f"confirm failed: {confirm_res.code}")
            gen_id = get_current_runtime_generation_id(self.user_id)
            rows = self._sample_feed_rows()
            tokens = [
                sign_realized_feed_row(r, user_id=self.user_id, generation_id=gen_id)
                for r in rows
            ]
        return rows, tokens, gen_id

    # =========================================================================
    # Test 41: Selective import happy path
    # =========================================================================
    def test_41_selective_import_happy_path(self):
        rows, tokens, gen_id = self._get_confirmed_client()

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            selected_items = [{"row": rows[0], "selection_token": tokens[0]}]

            # 1. Preview
            preview_res = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={
                    "selected_items": selected_items,
                    "account_id": "acc-wts-101",
                    "profit_rate_basis": "KRW",
                },
                headers=self._cookie_header(),
            )
            self.assertEqual(preview_res.status_code, 200)
            preview_data = preview_res.json()
            self.assertEqual(preview_data["counts"]["selected"], 1)
            self.assertEqual(preview_data["counts"]["new"], 1)
            self.assertEqual(preview_data["counts"]["already_imported"], 0)
            self.assertIn("preview_ticket", preview_data)
            preview_ticket = preview_data["preview_ticket"]

            # Verify no writes occurred during preview
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 0)

            # 2. Commit import
            import_res = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={
                    "selected_items": selected_items,
                    "account_id": "acc-wts-101",
                    "preview_ticket": preview_ticket,
                    "profit_rate_basis": "KRW",
                },
                headers=self._cookie_header(),
            )
            self.assertEqual(import_res.status_code, 200)
            import_data = import_res.json()
            self.assertEqual(import_data["selected"], 1)
            self.assertEqual(import_data["imported"], 1)
            self.assertEqual(import_data["already_imported"], 0)
            self.assertEqual(import_data["possible_duplicate_skipped"], 0)
            self.assertEqual(import_data["invalid"], 0)
            self.assertEqual(len(import_data["imported_ids"]), 1)

            # 3. Verify destination account attribution & provenance fields in database
            records = pnl_records.read_pnl_records(self.username)
            self.assertEqual(len(records), 1)
            rec = records[0]
            self.assertEqual(rec["id"], import_data["imported_ids"][0])
            self.assertEqual(rec["date"], "2026-01-05")
            self.assertEqual(rec["name"], "삼성전자")
            self.assertEqual(rec["pnl"], 50000.0)
            self.assertEqual(rec["broker"], "토스증권")
            self.assertEqual(rec["account_name"], "토스 종합계좌")
            self.assertEqual(rec["owner"], "본인")
            self.assertEqual(rec["source"], "toss_wts")
            self.assertTrue(rec["source_fingerprint"].startswith("toss-wts-realized:v1:"))
            self.assertIs(rec["source_scope_verified"], False)
            self.assertIs(rec["imported_by_user_action"], True)
            self.assertTrue(bool(rec["imported_at"]))

    # =========================================================================
    # Test 42: Reimport duplicate protection (ALREADY_IMPORTED)
    # =========================================================================
    def test_42_reimport_duplicate_protection(self):
        rows, tokens, gen_id = self._get_confirmed_client()

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            selected_items = [{"row": rows[0], "selection_token": tokens[0]}]

            # First import
            preview_res = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            ticket = preview_res.json()["preview_ticket"]
            self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={"selected_items": selected_items, "account_id": "acc-wts-101", "preview_ticket": ticket},
                headers=self._cookie_header(),
            )
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

            # Second preview of the same item -> should be ALREADY_IMPORTED
            preview_res2 = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            preview_data2 = preview_res2.json()
            self.assertEqual(preview_data2["counts"]["new"], 0)
            self.assertEqual(preview_data2["counts"]["already_imported"], 1)
            ticket2 = preview_data2["preview_ticket"]

            # Second import attempt -> should skip, zero new records written
            import_res2 = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={"selected_items": selected_items, "account_id": "acc-wts-101", "preview_ticket": ticket2},
                headers=self._cookie_header(),
            )
            import_data2 = import_res2.json()
            self.assertEqual(import_data2["imported"], 0)
            self.assertEqual(import_data2["already_imported"], 1)
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

    # =========================================================================
    # Test 43: Manual duplicate detection & override toggle
    # =========================================================================
    def test_43_manual_duplicate_detection_and_override_toggle(self):
        rows, tokens, gen_id = self._get_confirmed_client()

        # Seed an existing manual PnL record with the same date, symbol, and PnL
        pnl_records.create_pnl_record(
            {
                "date": "2026-01-05",
                "code": "005930",
                "name": "삼성전자",
                "currency": "KRW",
                "pnl": 50000.0,
                "broker": "기타증권",
                "account_name": "기타계좌",
                "owner": "모두",
            },
            username=self.username,
        )
        self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            selected_items = [{"row": rows[0], "selection_token": tokens[0]}]

            # Preview should identify matching manual record as POSSIBLE_DUPLICATE
            preview_res = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            preview_data = preview_res.json()
            self.assertEqual(preview_data["counts"]["possible_duplicate"], 1)
            self.assertEqual(preview_data["counts"]["new"], 0)
            ticket = preview_data["preview_ticket"]

            # Import WITHOUT override -> skipped
            import_res_default = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={
                    "selected_items": selected_items,
                    "account_id": "acc-wts-101",
                    "preview_ticket": ticket,
                    "include_possible_duplicates": False,
                },
                headers=self._cookie_header(),
            )
            self.assertEqual(import_res_default.status_code, 200)
            data_default = import_res_default.json()
            self.assertEqual(data_default["imported"], 0)
            self.assertEqual(data_default["possible_duplicate_skipped"], 1)
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

            # Import WITH override -> imported
            import_res_override = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={
                    "selected_items": selected_items,
                    "account_id": "acc-wts-101",
                    "preview_ticket": ticket,
                    "include_possible_duplicates": True,
                },
                headers=self._cookie_header(),
            )
            self.assertEqual(import_res_override.status_code, 200)
            data_override = import_res_override.json()
            self.assertEqual(data_override["imported"], 1)
            self.assertEqual(data_override["possible_duplicate_skipped"], 0)
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 2)

    # =========================================================================
    # Test 44: Client row tampering rejected
    # =========================================================================
    def test_44_client_row_tampering_rejected(self):
        rows, tokens, gen_id = self._get_confirmed_client()

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            # Attacker modifies profit_loss amount from 50000 to 99999999
            tampered_row = copy.deepcopy(rows[0])
            tampered_row["profit_loss"]["krw"] = 99999999.0
            tampered_items = [{"row": tampered_row, "selection_token": tokens[0]}]

            # Preview detects invalid row token
            preview_res = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": tampered_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            preview_data = preview_res.json()
            self.assertEqual(preview_data["counts"]["invalid"], 1)
            self.assertEqual(preview_data["counts"]["new"], 0)
            self.assertEqual(preview_data["items"][0]["status"], "INVALID")
            ticket = preview_data["preview_ticket"]

            # Import attempt with tampered row is skipped
            import_res = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={"selected_items": tampered_items, "account_id": "acc-wts-101", "preview_ticket": ticket},
                headers=self._cookie_header(),
            )
            import_data = import_res.json()
            self.assertEqual(import_data["imported"], 0)
            self.assertEqual(import_data["invalid"], 1)
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 0)

    # =========================================================================
    # Test 45: Post-preview destination alteration blocked
    # =========================================================================
    def test_45_post_preview_destination_alteration_blocked(self):
        rows, tokens, gen_id = self._get_confirmed_client()

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            selected_items = [{"row": rows[0], "selection_token": tokens[0]}]

            # Preview with account acc-wts-101
            preview_res = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            ticket = preview_res.json()["preview_ticket"]

            # Attempt import targeting account acc-other-202 with ticket signed for acc-wts-101
            import_res = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={
                    "selected_items": selected_items,
                    "account_id": "acc-other-202",
                    "preview_ticket": ticket,
                },
                headers=self._cookie_header(),
            )
            self.assertEqual(import_res.status_code, 400)
            self.assertEqual(import_res.json()["detail"]["code"], "DESTINATION_ACCOUNT_CHANGED")
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 0)

    # =========================================================================
    # Test 46: Concurrent duplicate commit-time recheck
    # =========================================================================
    def test_46_concurrent_duplicate_commit_time_recheck(self):
        rows, tokens, gen_id = self._get_confirmed_client()

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            selected_items = [{"row": rows[0], "selection_token": tokens[0]}]

            # 1. Preview shows row as NEW
            preview_res = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            ticket = preview_res.json()["preview_ticket"]

            # 2. Simulate concurrent tab importing the exact same row before commit
            self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

            # 3. Now the first request tries to commit with its stale ticket
            import_res = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={"selected_items": selected_items, "account_id": "acc-wts-101", "preview_ticket": ticket},
                headers=self._cookie_header(),
            )
            self.assertEqual(import_res.status_code, 200)
            import_data = import_res.json()
            # Commit-time recheck re-evaluated against fresh DB and detected duplicate
            self.assertEqual(import_data["imported"], 0)
            self.assertEqual(import_data["already_imported"], 1)
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

    # =========================================================================
    # Test 47: Multiset duplicate safety
    # =========================================================================
    def test_47_multiset_duplicate_safety(self):
        """Two identical trades in the same batch (same stock, date, amount) are tracked accurately."""
        rows, tokens, gen_id = self._get_confirmed_client()

        # Create two identical trades
        identical_row = copy.deepcopy(rows[0])
        token1 = sign_realized_feed_row(identical_row, user_id=self.user_id, generation_id=gen_id)
        token2 = sign_realized_feed_row(identical_row, user_id=self.user_id, generation_id=gen_id)

        items_pair = [
            {"row": identical_row, "selection_token": token1},
            {"row": identical_row, "selection_token": token2},
        ]

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            # Initial preview: both should be NEW
            preview_res = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": items_pair, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            pdata = preview_res.json()
            self.assertEqual(pdata["counts"]["new"], 2)
            self.assertEqual(pdata["counts"]["already_imported"], 0)

            # Import ONLY the first trade
            import_one_res = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={"selected_items": [items_pair[0]], "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            self.assertEqual(import_one_res.json()["imported"], 1)
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 1)

            # Preview the pair again: exactly 1 should be ALREADY_IMPORTED and 1 NEW
            preview_res2 = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": items_pair, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            pdata2 = preview_res2.json()
            self.assertEqual(pdata2["counts"]["already_imported"], 1)
            self.assertEqual(pdata2["counts"]["new"], 1)

            # Import with items_pair: item 0 skipped as ALREADY_IMPORTED, item 1 imported as NEW
            import_two_res = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={
                    "selected_items": items_pair,
                    "account_id": "acc-wts-101",
                    "preview_ticket": pdata2["preview_ticket"],
                },
                headers=self._cookie_header(),
            )
            self.assertEqual(import_two_res.json()["imported"], 1)
            self.assertEqual(import_two_res.json()["already_imported"], 1)
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 2)

            # Now previewing both: both should be ALREADY_IMPORTED
            preview_res3 = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": items_pair, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            pdata3 = preview_res3.json()
            self.assertEqual(pdata3["counts"]["already_imported"], 2)
            self.assertEqual(pdata3["counts"]["new"], 0)

    # =========================================================================
    # Test 51: Static auth guard (401 / 403)
    # =========================================================================
    def test_51_static_auth_guard(self):
        rows, tokens, gen_id = self._get_confirmed_client()
        selected_items = [{"row": rows[0], "selection_token": tokens[0]}]

        # 1. Unauthenticated -> 401
        res_unauth_preview = self.client.post(
            "/api/toss-wts/realized-feed/import-preview",
            json={"selected_items": selected_items, "account_id": "acc-wts-101"},
        )
        self.assertEqual(res_unauth_preview.status_code, 401)

        res_unauth_import = self.client.post(
            "/api/toss-wts/realized-feed/import",
            json={"selected_items": selected_items, "account_id": "acc-wts-101"},
        )
        self.assertEqual(res_unauth_import.status_code, 401)

        # 2. Authenticated but unauthorized user -> 403 STATIC_AUTHORIZATION_FAILED
        other_user_id = generate_user_id()
        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value={"username": self.username, "id": other_user_id, "role": "user"}):
            res_forbidden_preview = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            self.assertEqual(res_forbidden_preview.status_code, 403)
            self.assertEqual(res_forbidden_preview.json()["detail"]["code"], "STATIC_AUTHORIZATION_FAILED")

            res_forbidden_import = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            self.assertEqual(res_forbidden_import.status_code, 403)
            self.assertEqual(res_forbidden_import.json()["detail"]["code"], "STATIC_AUTHORIZATION_FAILED")

    # =========================================================================
    # Test 52: Unconfirmed runtime session guard (409)
    # =========================================================================
    def test_52_unconfirmed_runtime_session_guard(self):
        clear_wts_feed_runtime_confirmation()
        rows = self._sample_feed_rows()
        selected_items = [{"row": rows[0], "selection_token": "dummy"}]

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            res_preview = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            self.assertEqual(res_preview.status_code, 409)
            self.assertEqual(res_preview.json()["detail"]["code"], "NOT_CONFIRMED")

            res_import = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            self.assertEqual(res_import.status_code, 409)
            self.assertEqual(res_import.json()["detail"]["code"], "NOT_CONFIRMED")

    # =========================================================================
    # Test 53: Read-only fetch zero writes
    # =========================================================================
    def test_53_read_only_fetch_zero_writes(self):
        mock_adapter_result = {
            "source": "toss_wts",
            "kind": "profit_daily",
            "from_date": "2026-01-01",
            "to_date": "2026-01-10",
            "currency": "KRW",
            "fetched_at": "2026-01-10T15:00:00Z",
            "stocks": self._sample_feed_rows(),
        }

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record), \
             patch.object(TossWtsAdapter, "get_profit_daily", return_value=mock_adapter_result):

            confirm_res = confirm_wts_feed_runtime_session(self.user_id)
            self.assertTrue(confirm_res.confirmed)

            response = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                json={"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "KRW"},
                headers=self._cookie_header(),
            )
            self.assertEqual(response.status_code, 200)

            # Assert exactly zero PnL records or portfolio records were written
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 0)

    # =========================================================================
    # Test 54: UI selection & preview zero writes
    # =========================================================================
    def test_54_preview_zero_writes(self):
        rows, tokens, gen_id = self._get_confirmed_client()
        selected_items = [{"row": rows[0], "selection_token": tokens[0]}]

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            response = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(pnl_records.read_pnl_records(self.username)), 0)

    # =========================================================================
    # Test 55: Scope warning presence
    # =========================================================================
    def test_55_scope_warning_presence(self):
        rows, tokens, gen_id = self._get_confirmed_client()
        selected_items = [{"row": rows[0], "selection_token": tokens[0]}]

        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            # 1. Scope kind in preview response
            preview_res = self.client.post(
                "/api/toss-wts/realized-feed/import-preview",
                json={"selected_items": selected_items, "account_id": "acc-wts-101"},
                headers=self._cookie_header(),
            )
            pdata = preview_res.json()
            self.assertEqual(pdata.get("scope_kind"), "unverified")
            self.assertIs(pdata.get("scope_verified"), False)
            self.assertEqual(pdata.get("source_account_scope"), "unverified")

            # 2. Scope kind in commit response
            import_res = self.client.post(
                "/api/toss-wts/realized-feed/import",
                json={"selected_items": selected_items, "account_id": "acc-wts-101", "preview_ticket": pdata["preview_ticket"]},
                headers=self._cookie_header(),
            )
            idata = import_res.json()
            self.assertEqual(idata.get("scope_kind"), "unverified")
            self.assertIs(idata.get("scope_verified"), False)

    # =========================================================================
    # Test 56: Existing v1.1.0 flow preservation
    # =========================================================================
    def test_56_existing_v110_flow_preservation(self):
        with patch.dict(os.environ, self._env(), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=self.user_record):

            # Status endpoint
            status_res = self.client.get("/api/toss-wts/status", headers=self._cookie_header())
            self.assertEqual(status_res.status_code, 200)
            sdata = status_res.json()
            self.assertTrue(sdata["configured"])
            self.assertTrue(sdata["session_present"])

            # Confirm endpoint
            confirm_res = self.client.post("/api/toss-wts/feed/confirm", headers=self._cookie_header())
            self.assertEqual(confirm_res.status_code, 200)
            cdata = confirm_res.json()
            self.assertTrue(cdata["confirmed"])

    # =========================================================================
    # Test 57: Manual records unaffected
    # =========================================================================
    def test_57_manual_records_unaffected(self):
        created = pnl_records.create_pnl_record(
            {
                "date": "2026-03-01",
                "code": "005930",
                "name": "삼성전자",
                "currency": "KRW",
                "pnl": 12345.0,
                "broker": "수동증권",
                "account_name": "수동계좌",
                "owner": "모두",
            },
            username=self.username,
        )
        self.assertTrue(bool(created["id"]))
        self.assertEqual(created["pnl"], 12345.0)

        # Update manual record
        updated = pnl_records.update_pnl_record(
            created["id"],
            {"pnl": 54321.0, "memo": "수동수정"},
            username=self.username,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["pnl"], 54321.0)
        self.assertEqual(updated["memo"], "수동수정")


if __name__ == "__main__":
    unittest.main()
