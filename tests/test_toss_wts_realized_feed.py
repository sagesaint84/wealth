"""Integration unit tests for WTS read-only realized feed MVP and status route guard."""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from starlette.testclient import TestClient

from app.services.toss_wts_adapter import TossWtsAdapter, TossWtsAdapterError
from app.services.toss_wts_feed_auth import WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID
from app.services.toss_wts_feed_runtime import (
    check_wts_feed_runtime_confirmation,
    clear_wts_feed_runtime_confirmation,
    confirm_wts_feed_runtime_session,
)
from app.services.user_identity import generate_user_id
from tests.test_request_state_user_id import _import_main_without_loading_real_env


class TossWtsRealizedFeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = _import_main_without_loading_real_env()
        cls.client = TestClient(cls.main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def setUp(self):
        clear_wts_feed_runtime_confirmation()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(clear_wts_feed_runtime_confirmation)

        root = Path(self.temp_dir.name)
        self.exe_path = root / "tossctl"
        self.exe_path.write_text("synthetic_tossctl_binary", encoding="utf-8")

        self.config_dir = root / "config"
        self.config_dir.mkdir()
        self.session_path = self.config_dir / "session.json"
        self.session_path.write_text('{"token": "SYNTHETIC_WTS_SESSION_TOKEN_123"}', encoding="utf-8")

    def _cookie_header(self, username: str, role: str = "user") -> dict[str, str]:
        token = self.main._serializer.dumps({"user": username, "role": role})
        return {"Cookie": f"{self.main.COOKIE_NAME}={token}"}

    def _env_for(self, user_id: str) -> dict[str, str]:
        return {
            WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID: user_id,
            "WEALTH_TOSS_WTS_ENABLED": "1",
            "WEALTH_TOSSCTL_PATH": str(self.exe_path),
            "WEALTH_TOSSCTL_CONFIG_DIR": str(self.config_dir),
        }

    @staticmethod
    def _sample_stocks() -> list[dict]:
        return [
            {
                "date": "2026-01-05",
                "market_type": "KR",
                "symbol": "005930",
                "product_code": "KR7005930003",
                "name": "삼성전자",
                "quantity": 10.0,
                "profit_loss": {"krw": 50000, "usd": 38.5},
                "profit_rate": 7.5,
                "sell_amount": {"krw": 750000, "usd": 576.9},
                "buy_amount": {"krw": 700000, "usd": 538.4},
            },
            {
                "date": "2026-01-08",
                "market_type": "US",
                "symbol": "AAPL",
                "product_code": "US0378331005",
                "name": "애플",
                "quantity": 5.0,
                "profit_loss": {"krw": 120000, "usd": 92.3},
                "profit_rate": 12.0,
                "sell_amount": {"krw": 1120000, "usd": 861.5},
                "buy_amount": {"krw": 1000000, "usd": 769.2},
            },
        ]

    # =========================================================================
    # 1. STATUS ROUTE TESTS
    # =========================================================================

    def test_status_allowed_user_success(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            response = self.client.get(
                "/api/toss-wts/status",
                headers=self._cookie_header("user-a", "user"),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        payload = response.json()
        self.assertTrue(payload.get("configured"))
        self.assertTrue(payload.get("session_present"))

    def test_status_unauthorized_user_denied_403(self):
        allowed_id = generate_user_id()
        caller_id = generate_user_id()
        caller_record = {"username": "user-other", "id": caller_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=caller_record), \
             patch("app.services.toss_wts_adapter.TossWtsAdapter.get_local_status", side_effect=AssertionError("get_local_status called for unauthorized")):
            response = self.client.get(
                "/api/toss-wts/status",
                headers=self._cookie_header("user-other", "user"),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "STATIC_AUTHORIZATION_FAILED"}})

    def test_status_unauthorized_admin_denied_403(self):
        allowed_id = generate_user_id()
        admin_id = generate_user_id()
        admin_record = {"username": "admin-b", "id": admin_id, "role": "admin", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=admin_record), \
             patch("app.services.toss_wts_adapter.TossWtsAdapter.get_local_status", side_effect=AssertionError("get_local_status called for unauthorized admin")):
            response = self.client.get(
                "/api/toss-wts/status",
                headers=self._cookie_header("admin-b", "admin"),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "STATIC_AUTHORIZATION_FAILED"}})

    def test_status_unauthenticated_denied_401(self):
        allowed_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.toss_wts_adapter.TossWtsAdapter.get_local_status", side_effect=AssertionError("get_local_status called on unauthenticated")):
            response = self.client.get("/api/toss-wts/status")

        self.assertEqual(response.status_code, 401)

    def test_status_missing_static_config_fails_closed(self):
        caller_id = generate_user_id()
        caller_record = {"username": "user-a", "id": caller_id, "role": "user", "must_change_password": False}

        env = self._env_for(caller_id)
        del env[WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID]

        with patch.dict(os.environ, env, clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=caller_record), \
             patch("app.services.toss_wts_adapter.TossWtsAdapter.get_local_status", side_effect=AssertionError("get_local_status called with missing config")):
            response = self.client.get(
                "/api/toss-wts/status",
                headers=self._cookie_header("user-a", "user"),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "STATIC_AUTHORIZATION_FAILED"}})

    def test_status_does_not_require_or_mutate_runtime_confirmation(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            # User has NOT confirmed
            check_before = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_before.confirmed)

            response = self.client.get(
                "/api/toss-wts/status",
                headers=self._cookie_header("user-a", "user"),
            )
            self.assertEqual(response.status_code, 200)

            # User still has NOT confirmed; status endpoint must not auto-confirm
            check_after = check_wts_feed_runtime_confirmation(user_id)
            self.assertFalse(check_after.confirmed)
            self.assertEqual(check_after.code, "NOT_CONFIRMED")

    # =========================================================================
    # 2. REALIZED FEED FETCH TESTS
    # =========================================================================

    def test_feed_happy_path(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}
        canonical_stocks = self._sample_stocks()

        mock_adapter_result = {
            "source": "toss_wts",
            "kind": "profit_daily",
            "from_date": "2026-01-01",
            "to_date": "2026-01-10",
            "currency": "KRW",
            "fetched_at": "2026-01-10T15:00:00Z",
            "stocks": canonical_stocks,
        }

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            # Explicit confirmation first
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", return_value=mock_adapter_result) as mock_get:
                response = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    json={
                        "from_date": "2026-01-01",
                        "to_date": "2026-01-10",
                        "profit_rate_basis": "KRW",
                    },
                    headers=self._cookie_header("user-a", "user"),
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")

        payload = response.json()
        self.assertEqual(payload["source"], "toss_wts")
        self.assertEqual(payload["kind"], "realized_pnl_feed")
        self.assertEqual(payload["scope_kind"], "unverified")
        self.assertIs(payload["scope_verified"], False)
        self.assertIs(payload["read_only"], True)
        self.assertIs(payload["persisted"], False)
        self.assertIs(payload["included_in_accounting_totals"], False)
        self.assertEqual(
            payload["requested"],
            {
                "from_date": "2026-01-01",
                "to_date": "2026-01-10",
                "profit_rate_basis": "KRW",
            },
        )
        self.assertEqual(payload["fetched_at"], "2026-01-10T15:00:00Z")
        self.assertEqual(payload["state"], "ok")
        self.assertEqual(len(payload["rows"]), 2)

        # Verify row contract: exactly the permitted fields, no account/owner/id
        row0 = payload["rows"][0]
        expected_keys = {
            "date", "market_type", "symbol", "product_code", "name",
            "quantity", "profit_loss", "profit_rate", "sell_amount", "buy_amount",
        }
        self.assertEqual(set(row0.keys()), expected_keys)
        self.assertEqual(row0["name"], "삼성전자")
        self.assertEqual(row0["profit_loss"], {"krw": 50000, "usd": 38.5})

        for forbidden in ("id", "fingerprint", "owner", "account_id", "account_name", "source_account_scope", "user_id"):
            self.assertNotIn(forbidden, row0)
            self.assertNotIn(forbidden, payload)

        # Exactly one call to get_profit_daily
        mock_get.assert_called_once_with(
            from_date="2026-01-01",
            to_date="2026-01-10",
            currency="KRW",
        )

    def test_feed_empty_stocks_returns_200_empty(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        mock_empty_result = {
            "source": "toss_wts",
            "kind": "profit_daily",
            "from_date": "2026-01-01",
            "to_date": "2026-01-10",
            "currency": "USD",
            "fetched_at": "2026-01-10T15:00:00Z",
            "stocks": [],
        }

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", return_value=mock_empty_result):
                response = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    json={
                        "from_date": "2026-01-01",
                        "to_date": "2026-01-10",
                        "profit_rate_basis": "USD",
                    },
                    headers=self._cookie_header("user-a", "user"),
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        payload = response.json()
        self.assertEqual(payload["state"], "empty")
        self.assertEqual(payload["rows"], [])
        self.assertIs(payload["scope_verified"], False)
        self.assertIs(payload["persisted"], False)

    def test_feed_denied_static_auth_failure(self):
        allowed_id = generate_user_id()
        other_id = generate_user_id()
        other_record = {"username": "user-other", "id": other_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=other_record), \
             patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", side_effect=AssertionError("WTS called on static auth failure")):
            response = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                json={
                    "from_date": "2026-01-01",
                    "to_date": "2026-01-10",
                    "profit_rate_basis": "KRW",
                },
                headers=self._cookie_header("user-other", "user"),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "STATIC_AUTHORIZATION_FAILED"}})

    def test_feed_denied_not_confirmed(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record), \
             patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", side_effect=AssertionError("WTS called without confirmation")):
            # Caller is statically allowed but NOT confirmed
            response = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                json={
                    "from_date": "2026-01-01",
                    "to_date": "2026-01-10",
                    "profit_rate_basis": "KRW",
                },
                headers=self._cookie_header("user-a", "user"),
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "NOT_CONFIRMED"}})

    def test_feed_denied_generation_changed(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            # 1. Confirm
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # 2. Modify session file (generation changed)
            time.sleep(0.01)
            self.session_path.write_text('{"token": "NEW_GENERATION_SESSION_2"}', encoding="utf-8")

            # 3. Attempt feed fetch
            with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", side_effect=AssertionError("WTS called on generation change")):
                response = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    json={
                        "from_date": "2026-01-01",
                        "to_date": "2026-01-10",
                        "profit_rate_basis": "KRW",
                    },
                    headers=self._cookie_header("user-a", "user"),
                )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "RUNTIME_GENERATION_CHANGED"}})

    def test_feed_allowed_normal_user_succeeds_without_admin(self):
        user_id = generate_user_id()
        user_record = {"username": "normal-user", "id": user_id, "role": "user", "must_change_password": False}

        mock_res = {
            "source": "toss_wts",
            "kind": "profit_daily",
            "from_date": "2026-01-01",
            "to_date": "2026-01-10",
            "currency": "KRW",
            "fetched_at": "2026-01-10T15:00:00Z",
            "stocks": [],
        }

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            confirm_wts_feed_runtime_session(user_id)

            with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", return_value=mock_res):
                response = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    json={
                        "from_date": "2026-01-01",
                        "to_date": "2026-01-10",
                        "profit_rate_basis": "KRW",
                    },
                    headers=self._cookie_header("normal-user", "user"),
                )

        self.assertEqual(response.status_code, 200)

    def test_feed_non_allowed_admin_is_denied(self):
        allowed_id = generate_user_id()
        admin_id = generate_user_id()
        admin_record = {"username": "admin-b", "id": admin_id, "role": "admin", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=admin_record), \
             patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", side_effect=AssertionError("WTS called for admin bypass")):
            response = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                json={
                    "from_date": "2026-01-01",
                    "to_date": "2026-01-10",
                    "profit_rate_basis": "KRW",
                },
                headers=self._cookie_header("admin-b", "admin"),
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": {"code": "STATIC_AUTHORIZATION_FAILED"}})

    def test_feed_client_cannot_select_user_or_account(self):
        allowed_id = generate_user_id()
        spoofed_id = generate_user_id()
        user_record = {"username": "user-a", "id": allowed_id, "role": "user", "must_change_password": False}

        mock_res = {
            "source": "toss_wts",
            "kind": "profit_daily",
            "from_date": "2026-01-01",
            "to_date": "2026-01-10",
            "currency": "KRW",
            "fetched_at": "2026-01-10T15:00:00Z",
            "stocks": [],
        }

        # 1. Allowed caller sending spoofed body/query fields
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            confirm_wts_feed_runtime_session(allowed_id)

            with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", return_value=mock_res):
                response = self.client.post(
                    f"/api/toss-wts/realized-feed/fetch?user_id={spoofed_id}&account_id=acc-1",
                    json={
                        "from_date": "2026-01-01",
                        "to_date": "2026-01-10",
                        "profit_rate_basis": "KRW",
                        "user_id": spoofed_id,
                        "account_id": "acc-1",
                        "owner": "OtherOwner",
                    },
                    headers=self._cookie_header("user-a", "user"),
                )

            self.assertEqual(response.status_code, 200)
            text = response.text
            self.assertNotIn(spoofed_id, text)
            self.assertNotIn("acc-1", text)
            self.assertNotIn("OtherOwner", text)

        # 2. Unauthorized caller trying to spoof allowed user_id in body
        other_record = {"username": "user-b", "id": spoofed_id, "role": "user", "must_change_password": False}
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=other_record):
            response = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                json={
                    "from_date": "2026-01-01",
                    "to_date": "2026-01-10",
                    "profit_rate_basis": "KRW",
                    "user_id": allowed_id,
                },
                headers=self._cookie_header("user-b", "user"),
            )
            self.assertEqual(response.status_code, 403)

    def test_feed_unauthenticated_request_denied(self):
        allowed_id = generate_user_id()
        with patch.dict(os.environ, self._env_for(allowed_id), clear=False), \
             patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", side_effect=AssertionError("WTS called on unauthenticated")):
            response = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                json={
                    "from_date": "2026-01-01",
                    "to_date": "2026-01-10",
                    "profit_rate_basis": "KRW",
                },
            )

        self.assertEqual(response.status_code, 401)

    def test_feed_request_validation(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        invalid_bodies = [
            # Invalid date format
            {"from_date": "2026/01/01", "to_date": "2026-01-10", "profit_rate_basis": "KRW"},
            # Nonexistent date
            {"from_date": "2026-02-30", "to_date": "2026-03-01", "profit_rate_basis": "KRW"},
            # from > to
            {"from_date": "2026-01-10", "to_date": "2026-01-01", "profit_rate_basis": "KRW"},
            # Invalid basis
            {"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "EUR"},
            {"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": "krw"},
            {"from_date": "2026-01-01", "to_date": "2026-01-10", "profit_rate_basis": ""},
            # Missing fields
            {"to_date": "2026-01-10", "profit_rate_basis": "KRW"},
            {"from_date": "2026-01-01", "profit_rate_basis": "KRW"},
            {"from_date": "2026-01-01", "to_date": "2026-01-10"},
            {},
        ]

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            confirm_wts_feed_runtime_session(user_id)

            with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", side_effect=AssertionError("WTS called on invalid request")) as mock_get:
                for body in invalid_bodies:
                    response = self.client.post(
                        "/api/toss-wts/realized-feed/fetch",
                        json=body,
                        headers=self._cookie_header("user-a", "user"),
                    )
                    self.assertEqual(response.status_code, 400, f"Expected 400 for {body}")
                    self.assertEqual(response.headers.get("cache-control"), "no-store")
                    self.assertEqual(response.json().get("detail", {}).get("code"), "INVALID_REQUEST")

                # Non-dict body
                response = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    content="not a json",
                    headers={**self._cookie_header("user-a", "user"), "Content-Type": "application/json"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.headers.get("cache-control"), "no-store")

            mock_get.assert_not_called()

    def test_feed_provider_schema_error_yields_502(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        for error_code in ("INVALID_SCHEMA", "INVALID_JSON"):
            with patch.dict(os.environ, self._env_for(user_id), clear=False), \
                 patch("app.services.user_manager.get_user_by_name", return_value=user_record):
                confirm_wts_feed_runtime_session(user_id)

                with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", side_effect=TossWtsAdapterError(error_code)):
                    response = self.client.post(
                        "/api/toss-wts/realized-feed/fetch",
                        json={
                            "from_date": "2026-01-01",
                            "to_date": "2026-01-10",
                            "profit_rate_basis": "KRW",
                        },
                        headers=self._cookie_header("user-a", "user"),
                    )

            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.headers.get("cache-control"), "no-store")
            self.assertEqual(response.json(), {"detail": {"code": error_code}})

    def test_feed_provider_unavailable_error_yields_503(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        for error_code in ("WTS_NOT_LOGGED_IN", "TOSSCTL_NOT_FOUND", "COMMAND_TIMEOUT"):
            with patch.dict(os.environ, self._env_for(user_id), clear=False), \
                 patch("app.services.user_manager.get_user_by_name", return_value=user_record):
                confirm_wts_feed_runtime_session(user_id)

                with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", side_effect=TossWtsAdapterError(error_code)):
                    response = self.client.post(
                        "/api/toss-wts/realized-feed/fetch",
                        json={
                            "from_date": "2026-01-01",
                            "to_date": "2026-01-10",
                            "profit_rate_basis": "KRW",
                        },
                        headers=self._cookie_header("user-a", "user"),
                    )

            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers.get("cache-control"), "no-store")
            self.assertEqual(response.json(), {"detail": {"code": error_code}})

    def test_feed_runtime_material_unavailable_yields_503(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            # Confirm while material exists
            confirm_res = confirm_wts_feed_runtime_session(user_id)
            self.assertTrue(confirm_res.confirmed)

            # Then remove session file
            self.session_path.unlink()

            response = self.client.post(
                "/api/toss-wts/realized-feed/fetch",
                json={
                    "from_date": "2026-01-01",
                    "to_date": "2026-01-10",
                    "profit_rate_basis": "KRW",
                },
                headers=self._cookie_header("user-a", "user"),
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json(), {"detail": {"code": "RUNTIME_MATERIAL_UNAVAILABLE"}})

    def test_feed_zero_persistence_and_zero_financial_mutation(self):
        user_id = generate_user_id()
        user_record = {"username": "user-a", "id": user_id, "role": "user", "must_change_password": False}

        mock_adapter_result = {
            "source": "toss_wts",
            "kind": "profit_daily",
            "from_date": "2026-01-01",
            "to_date": "2026-01-10",
            "currency": "KRW",
            "fetched_at": "2026-01-10T15:00:00Z",
            "stocks": self._sample_stocks(),
        }

        with patch.dict(os.environ, self._env_for(user_id), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record), \
             patch("app.services.pnl_records.write_pnl_records", side_effect=AssertionError("pnl write called")) as mock_write_pnl, \
             patch("app.services.pnl_records.create_pnl_record", side_effect=AssertionError("pnl create called")) as mock_create_pnl, \
             patch("app.services.portfolio.write_portfolio", side_effect=AssertionError("portfolio write called")) as mock_write_port:
            confirm_wts_feed_runtime_session(user_id)

            with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", return_value=mock_adapter_result):
                response = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    json={
                        "from_date": "2026-01-01",
                        "to_date": "2026-01-10",
                        "profit_rate_basis": "KRW",
                    },
                    headers=self._cookie_header("user-a", "user"),
                )

        self.assertEqual(response.status_code, 200)
        mock_write_pnl.assert_not_called()
        mock_create_pnl.assert_not_called()
        mock_write_port.assert_not_called()

    def test_feed_response_privacy(self):
        sentinel_uuid = "00000000-0000-4000-8000-000000000099"
        user_record = {"username": "sentinel-user", "id": sentinel_uuid, "role": "user", "must_change_password": False}

        mock_adapter_result = {
            "source": "toss_wts",
            "kind": "profit_daily",
            "from_date": "2026-01-01",
            "to_date": "2026-01-10",
            "currency": "KRW",
            "fetched_at": "2026-01-10T15:00:00Z",
            "stocks": self._sample_stocks(),
        }

        with patch.dict(os.environ, self._env_for(sentinel_uuid), clear=False), \
             patch("app.services.user_manager.get_user_by_name", return_value=user_record):
            confirm_wts_feed_runtime_session(sentinel_uuid)

            with patch("app.services.toss_wts_adapter.TossWtsAdapter.get_profit_daily", return_value=mock_adapter_result):
                response = self.client.post(
                    "/api/toss-wts/realized-feed/fetch",
                    json={
                        "from_date": "2026-01-01",
                        "to_date": "2026-01-10",
                        "profit_rate_basis": "KRW",
                    },
                    headers=self._cookie_header("sentinel-user", "user"),
                )

        self.assertEqual(response.status_code, 200)
        body = response.text
        for sensitive in (
            sentinel_uuid,
            "sentinel-user",
            str(self.exe_path),
            str(self.config_dir),
            str(self.session_path),
            "marker",
            "mtime",
            "st_size",
        ):
            self.assertNotIn(sensitive, body)


if __name__ == "__main__":
    unittest.main()
