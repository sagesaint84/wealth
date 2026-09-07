from __future__ import annotations

import asyncio
import json
import unittest
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch

from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer

from regression_support import import_main_without_loading_real_env


main = import_main_without_loading_real_env()


TEST_USERS = {"user_a", "user_b"}


def fake_user_lookup(username: str):
    if username not in TEST_USERS:
        return None
    return {
        "username": username,
        "role": "user",
        "must_change_password": False,
    }


def request_without_auth() -> Request:
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/export",
            "raw_path": b"/api/export",
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )


class ExportSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original_serializer = main._serializer
        main._serializer = URLSafeTimedSerializer("test-only-session-secret")
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        main._serializer = cls.original_serializer

    def auth_headers(self, username: str) -> dict[str, str]:
        token = main._serializer.dumps({"user": username, "role": "user"})
        return {"Cookie": f"{main.COOKIE_NAME}={token}"}

    def test_export_rejects_unauthenticated_requests_without_reading_default_user(self) -> None:
        with patch("app.services.portfolio.read_portfolio") as read_portfolio:
            response = self.client.get("/api/export")

        self.assertEqual(response.status_code, 401)
        read_portfolio.assert_not_called()

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.export_data(request_without_auth()))
        self.assertEqual(raised.exception.status_code, 401)

        with self.assertRaises(HTTPException) as fallback_raised:
            main.get_current_username(request_without_auth())
        self.assertEqual(fallback_raised.exception.status_code, 401)

    def test_export_is_scoped_to_the_authenticated_user(self) -> None:
        def owned_data(username: str | None = None):
            return {"owner": username, "marker": f"only-{username}"}

        with ExitStack() as stack:
            stack.enter_context(patch("app.services.user_manager.get_user_by_name", side_effect=fake_user_lookup))
            readers = [
                stack.enter_context(patch(path, side_effect=owned_data))
                for path in (
                    "app.services.portfolio.read_portfolio",
                    "app.services.asset_records.read_asset_records",
                    "app.services.dividend_records.read_dividend_records",
                    "app.services.pnl_records.read_pnl_records",
                    "app.services.ledger.read_ledger",
                )
            ]
            response_a = self.client.get("/api/export", headers=self.auth_headers("user_a"))
            response_b = self.client.get("/api/export", headers=self.auth_headers("user_b"))

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)
        bundle_a = response_a.json()
        bundle_b = response_b.json()
        self.assertEqual(bundle_a["user"], "user_a")
        self.assertEqual(bundle_a["portfolio"]["marker"], "only-user_a")
        self.assertNotIn("only-user_b", response_a.text)
        self.assertEqual(bundle_b["user"], "user_b")
        self.assertEqual(bundle_b["portfolio"]["marker"], "only-user_b")
        self.assertNotIn("only-user_a", response_b.text)
        for reader in readers:
            self.assertEqual(
                [call.kwargs["username"] for call in reader.call_args_list],
                ["user_a", "user_b"],
            )

    def test_export_removes_credentials_and_preserves_asset_data(self) -> None:
        fake_secret_values = {
            "fake-app-key",
            "fake-app-secret",
            "fake-access-token",
            "fake-refresh-token",
            "fake-password-hash",
            "fake-session-secret",
            "fake-api-key",
        }
        portfolio = {
            "holdings": [
                {
                    "symbol": "SAFE",
                    "name": "가상 자산",
                    "quantity": 7,
                    "app_key": "fake-app-key",
                    "appSecret": "fake-app-secret",
                    "nested": {"accessToken": "fake-access-token"},
                }
            ],
            "accounts": [{"name": "가상 계좌", "balance": 12345}],
            "bank_accounts": [{"id": "bank-safe", "balance": 0, "currency": "KRW"}],
            "loan_accounts": [
                {
                    "id": "loan-safe",
                    "loan_type": "minus",
                    "current_balance": 100,
                    "limit_amount": 1000,
                    "overdraft_bank_account_id": "bank-safe",
                }
            ],
        }
        asset_records = [
            {
                "date": "2026-01-02",
                "total": 12345,
                "refresh-token": "fake-refresh-token",
            }
        ]
        dividend_records = [{"symbol": "SAFE", "amount": 321}]
        pnl_records = [{"symbol": "SAFE", "pnl": 99, "password_hash": "fake-password-hash"}]
        ledger = {
            "transactions": [{"description": "가상 지출", "amount": 1000}],
            "sessionSecret": "fake-session-secret",
            "credentials": {"apiKey": "fake-api-key"},
        }

        with ExitStack() as stack:
            stack.enter_context(patch("app.services.user_manager.get_user_by_name", side_effect=fake_user_lookup))
            stack.enter_context(patch("app.services.portfolio.read_portfolio", return_value=deepcopy(portfolio)))
            stack.enter_context(patch("app.services.asset_records.read_asset_records", return_value=deepcopy(asset_records)))
            stack.enter_context(patch("app.services.dividend_records.read_dividend_records", return_value=deepcopy(dividend_records)))
            stack.enter_context(patch("app.services.pnl_records.read_pnl_records", return_value=deepcopy(pnl_records)))
            stack.enter_context(patch("app.services.ledger.read_ledger", return_value=deepcopy(ledger)))
            read_openapi = stack.enter_context(patch("app.services.user_openapi.get_user_openapi_config"))
            response = self.client.get("/api/export", headers=self.auth_headers("user_a"))

        self.assertEqual(response.status_code, 200)
        bundle = response.json()
        self.assertNotIn("openapi_config", bundle)
        self.assertEqual(bundle["backup_policy"], "general_data_only")
        read_openapi.assert_not_called()
        for fake_value in fake_secret_values:
            self.assertNotIn(fake_value, response.text)

        self.assertEqual(bundle["portfolio"]["holdings"][0]["symbol"], "SAFE")
        self.assertEqual(bundle["portfolio"]["holdings"][0]["quantity"], 7)
        self.assertEqual(bundle["portfolio"]["accounts"][0]["balance"], 12345)
        self.assertEqual(
            bundle["portfolio"]["loan_accounts"][0]["overdraft_bank_account_id"],
            "bank-safe",
        )
        self.assertEqual(bundle["asset_records"][0]["total"], 12345)
        self.assertEqual(bundle["dividend_records"][0]["amount"], 321)
        self.assertEqual(bundle["realized_pnl_records"][0]["pnl"], 99)
        self.assertEqual(bundle["ledger"]["transactions"][0]["amount"], 1000)

    def test_restore_accepts_backup_without_credentials(self) -> None:
        backup = {
            "version": "2.2",
            "user": "user_a",
            "backup_policy": "general_data_only",
            "portfolio": {
                "holdings": [{"symbol": "SAFE", "quantity": 7}],
                "bank_accounts": [{"id": "bank-safe", "balance": 0, "currency": "KRW"}],
                "loan_accounts": [
                    {
                        "id": "loan-safe",
                        "loan_type": "minus",
                        "current_balance": 100,
                        "limit_amount": 1000,
                        "overdraft_bank_account_id": "bank-safe",
                    }
                ],
            },
            "asset_records": [{"date": "2026-01-02", "total": 12345}],
            "dividend_records": [{"symbol": "SAFE", "amount": 321}],
            "realized_pnl_records": [{"symbol": "SAFE", "pnl": 99}],
            "ledger": {"transactions": [{"description": "가상 지출", "amount": 1000}]},
        }

        with ExitStack() as stack:
            stack.enter_context(patch("app.services.user_manager.get_user_by_name", side_effect=fake_user_lookup))
            write_portfolio = stack.enter_context(patch("app.services.portfolio.write_portfolio"))
            write_assets = stack.enter_context(patch("app.services.asset_records.write_asset_records"))
            write_dividends = stack.enter_context(patch("app.services.dividend_records.write_dividend_records"))
            write_pnl = stack.enter_context(patch("app.services.pnl_records.write_pnl_records"))
            write_ledger = stack.enter_context(patch("app.services.ledger.write_ledger"))
            save_openapi = stack.enter_context(patch("app.services.user_openapi.save_user_openapi_config"))
            response = self.client.post(
                "/api/import-backup",
                headers=self.auth_headers("user_a"),
                files={
                    "file": (
                        "credential-free-backup.json",
                        json.dumps(backup, ensure_ascii=False).encode("utf-8"),
                        "application/json",
                    )
                },
            )

        self.assertEqual(response.status_code, 200)
        write_portfolio.assert_called_once_with(backup["portfolio"], username="user_a")
        write_assets.assert_called_once_with(backup["asset_records"], username="user_a")
        write_dividends.assert_called_once_with(backup["dividend_records"], username="user_a")
        write_pnl.assert_called_once_with(backup["realized_pnl_records"], username="user_a")
        self.assertEqual(write_ledger.call_args.kwargs["username"], "user_a")
        save_openapi.assert_not_called()


if __name__ == "__main__":
    unittest.main()
