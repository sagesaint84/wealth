from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.kiwoom_openapi import (
    TOKEN_SAFETY_MARGIN_SECONDS,
    KiwoomOpenAPI,
    KiwoomOpenAPIError,
    Token,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    @property
    def is_error(self):
        return self.status_code >= 400

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        if not self.responses:
            raise RuntimeError(f"Unexpected request to {url}; no more fake responses available")
        return self.responses.pop(0)


class KiwoomTokenRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_path = Path(self.temp_dir.name) / "kiwoom_token_cache.json"
        self.client = object.__new__(KiwoomOpenAPI)
        self.client.base_url = "https://api.kiwoom.com"
        self.client.app_key = "12345678appkey"
        self.client.app_secret = "secret12345678"
        self.client.token_cache_file = self.cache_path
        self.client._token = None
        self.client.last_accounts = []
        self.client.account_cash = {}

    def tearDown(self):
        self.temp_dir.cleanup()

    # 1. Valid cached token encounters 8005 -> force refresh -> succeeds on 2nd attempt
    def test_valid_cached_token_encounters_8005_refreshes_and_succeeds(self):
        fake = FakeClient([
            FakeResponse({"return_code": 8005, "return_msg": "8005: Token이 유효하지 않습니다"}),
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
        ])
        refresh_mock = AsyncMock(return_value="new-token-5678")
        with patch.object(self.client, "_access_token", new=refresh_mock):
            payload, cont_yn, next_key = asyncio.run(
                self.client._post_api(fake, "old-token-1234", "ka00001", {})
            )
        self.assertEqual(payload, {"return_code": 0, "acctNo": "1234567890"})
        refresh_mock.assert_awaited_once_with(fake, force_refresh=True)
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(fake.requests[0][1]["headers"]["authorization"], "Bearer old-token-1234")
        self.assertEqual(fake.requests[1][1]["headers"]["authorization"], "Bearer new-token-5678")

    # 2. First 8005, second 8005 -> fails closed after exactly 2 requests (no 3rd request)
    def test_first_8005_second_8005_fails_after_exactly_two_requests(self):
        fake = FakeClient([
            FakeResponse({"return_code": 8005, "return_msg": "8005: Token이 유효하지 않습니다"}),
            FakeResponse({"return_code": 8005, "return_msg": "8005: Token이 유효하지 않습니다"}),
        ])
        refresh_mock = AsyncMock(return_value="new-token-5678")
        with patch.object(self.client, "_access_token", new=refresh_mock):
            with self.assertRaises(KiwoomOpenAPIError) as ctx:
                asyncio.run(self.client._post_api(fake, "old-token-1234", "ka00001", {}))
        self.assertIn("8005", str(ctx.exception))
        refresh_mock.assert_awaited_once_with(fake, force_refresh=True)
        self.assertEqual(len(fake.requests), 2)

    # 3. HTTP 401 -> force refresh -> succeeds on 2nd attempt
    def test_http_401_refreshes_and_succeeds(self):
        fake = FakeClient([
            FakeResponse({}, status_code=401),
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
        ])
        refresh_mock = AsyncMock(return_value="new-token-401")
        with patch.object(self.client, "_access_token", new=refresh_mock):
            payload, _, _ = asyncio.run(self.client._post_api(fake, "initial-token", "ka00001", {}))
        self.assertEqual(payload["acctNo"], "1234567890")
        refresh_mock.assert_awaited_once_with(fake, force_refresh=True)
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(fake.requests[1][1]["headers"]["authorization"], "Bearer new-token-401")

    # 4. HTTP 401 -> refresh -> second 401 fails closed after exactly 2 requests
    def test_http_401_refreshes_and_second_401_fails(self):
        fake = FakeClient([
            FakeResponse({}, status_code=401),
            FakeResponse({}, status_code=401),
        ])
        refresh_mock = AsyncMock(return_value="new-token-401")
        with patch.object(self.client, "_access_token", new=refresh_mock):
            with self.assertRaises(KiwoomOpenAPIError) as ctx:
                asyncio.run(self.client._post_api(fake, "initial-token", "ka00001", {}))
        self.assertIn("401", str(ctx.exception))
        self.assertEqual(len(fake.requests), 2)

    # 5. General business error does NOT refresh token
    def test_general_business_error_does_not_refresh_token(self):
        fake = FakeClient([
            FakeResponse({"return_code": 1, "return_msg": "조회할 내역이 없습니다."}),
        ])
        refresh_mock = AsyncMock(return_value="should-not-be-called")
        with patch.object(self.client, "_access_token", new=refresh_mock):
            with self.assertRaises(KiwoomOpenAPIError) as ctx:
                asyncio.run(self.client._post_api(fake, "token", "kt00018", {}))
        self.assertIn("조회할 내역이 없습니다", str(ctx.exception))
        refresh_mock.assert_not_called()
        self.assertEqual(len(fake.requests), 1)

    # 6. Malformed JSON does NOT refresh token
    def test_malformed_json_does_not_refresh_token(self):
        fake = FakeClient([
            FakeResponse(ValueError("Invalid JSON"), status_code=200),
        ])
        refresh_mock = AsyncMock(return_value="should-not-be-called")
        with patch.object(self.client, "_access_token", new=refresh_mock):
            with self.assertRaises(KiwoomOpenAPIError) as ctx:
                asyncio.run(self.client._post_api(fake, "token", "kt00018", {}))
        self.assertIn("올바른 JSON이 아닙니다", str(ctx.exception))
        refresh_mock.assert_not_called()
        self.assertEqual(len(fake.requests), 1)

    # 7. Pagination 8005 preserves continuation headers and body
    def test_pagination_8005_preserves_continuation_headers_and_body(self):
        fake = FakeClient([
            FakeResponse({"return_code": 8005, "return_msg": "8005: Token이 유효하지 않습니다"}),
            FakeResponse(
                {"return_code": 0, "acnt_evlt_remn_indv_tot": []},
                headers={"cont-yn": "Y", "next-key": "NEXT-PAGE-3"},
            ),
        ])
        refresh_mock = AsyncMock(return_value="page2-refreshed-token")
        with patch.object(self.client, "_access_token", new=refresh_mock):
            payload, cont_yn, next_key = asyncio.run(
                self.client._post_api(
                    fake,
                    "page2-old-token",
                    "kt00018",
                    {"qry_tp": "1", "dmst_stex_tp": "KRX"},
                    cont_yn="Y",
                    next_key="KEY-PAGE-2",
                )
            )
        self.assertEqual(cont_yn, "Y")
        self.assertEqual(next_key, "NEXT-PAGE-3")
        self.assertEqual(len(fake.requests), 2)
        # Both attempts must preserve continuation headers and body
        for req in fake.requests:
            self.assertEqual(req[1]["headers"]["cont-yn"], "Y")
            self.assertEqual(req[1]["headers"]["next-key"], "KEY-PAGE-2")
            self.assertEqual(req[1]["headers"]["api-id"], "kt00018")
            self.assertEqual(req[1]["json"], {"qry_tp": "1", "dmst_stex_tp": "KRX"})
        self.assertEqual(fake.requests[0][1]["headers"]["authorization"], "Bearer page2-old-token")
        self.assertEqual(fake.requests[1][1]["headers"]["authorization"], "Bearer page2-refreshed-token")

    # 8. Official expires_dt="YYYYMMDDHHMMSS" parsing
    def test_official_expires_dt_parsing(self):
        body = {
            "expires_dt": "20260917150000",
            "token_type": "Bearer",
            "token": "tok123",
            "return_code": 0,
            "return_msg": "",
        }
        expires_at = KiwoomOpenAPI._parse_token_expires_at(body)
        kst = timezone(timedelta(hours=9))
        expected_dt = datetime(2026, 9, 17, 15, 0, 0, tzinfo=kst)
        expected_ts = expected_dt.timestamp() - TOKEN_SAFETY_MARGIN_SECONDS
        self.assertEqual(expires_at, expected_ts)

    # 9. Malformed expires_dt fail closed and fallback handling
    def test_malformed_expires_dt_and_fallback(self):
        # Invalid lengths and characters fail closed
        for malformed in ("202411", "not-a-number", "20240230120000", "20261301120000"):
            with self.subTest(malformed=malformed):
                with self.assertRaises(KiwoomOpenAPIError):
                    KiwoomOpenAPI._parse_token_expires_at({"expires_dt": malformed})

        # Empty without fallback fails closed
        with self.assertRaises(KiwoomOpenAPIError):
            KiwoomOpenAPI._parse_token_expires_at({"expires_dt": ""})
        with self.assertRaises(KiwoomOpenAPIError):
            KiwoomOpenAPI._parse_token_expires_at({})

        # Explicit fallback with valid expires_in works
        now = time.time()
        ts = KiwoomOpenAPI._parse_token_expires_at({"expires_in": 3600})
        self.assertAlmostEqual(ts, now + 3600 - TOKEN_SAFETY_MARGIN_SECONDS, delta=2.0)

        # Invalid expires_in values fail closed
        with self.assertRaises(KiwoomOpenAPIError):
            KiwoomOpenAPI._parse_token_expires_at({"expires_in": -10})
        with self.assertRaises(KiwoomOpenAPIError):
            KiwoomOpenAPI._parse_token_expires_at({"expires_in": "not-a-number"})

    # 10. Expired token cache triggers new token issuance
    def test_expired_token_cache_triggers_new_token_issuance(self):
        # Write expired cache file
        self.cache_path.write_text(json.dumps({
            "app_key_prefix": "12345678",
            "access_token": "expired-cached-token",
            "expires_at": time.time() - 3600,
        }), encoding="utf-8")

        fake = FakeClient([
            FakeResponse({
                "expires_dt": "20261231235959",
                "token_type": "Bearer",
                "token": "fresh-token-from-provider",
                "return_code": 0,
            }),
        ])
        token = asyncio.run(self.client._access_token(fake))
        self.assertEqual(token, "fresh-token-from-provider")
        self.assertEqual(len(fake.requests), 1)
        self.assertTrue(fake.requests[0][0].endswith("/oauth2/token"))

    # 11. Token cache App Key prefix mismatch ignores cache
    def test_app_key_prefix_mismatch_ignores_cache(self):
        # Valid timestamp, but wrong app key prefix
        self.cache_path.write_text(json.dumps({
            "app_key_prefix": "DIFFERNT",
            "access_token": "cached-token-different-key",
            "expires_at": time.time() + 86400,
        }), encoding="utf-8")

        fake = FakeClient([
            FakeResponse({
                "expires_dt": "20261231235959",
                "token_type": "Bearer",
                "token": "fresh-token-for-my-key",
                "return_code": 0,
            }),
        ])
        token = asyncio.run(self.client._access_token(fake))
        self.assertEqual(token, "fresh-token-for-my-key")
        self.assertEqual(len(fake.requests), 1)

    # 12. Realized P/L _post_realized_page 8005 recovery
    def test_realized_post_page_8005_recovery(self):
        fake = FakeClient([
            FakeResponse({"return_code": 8005, "return_msg": "8005: Token이 유효하지 않습니다"}),
            FakeResponse({"return_code": 0, "dt_stk_rlzt_pl": []}, headers={"cont-yn": "N", "next-key": ""}),
        ])
        refresh_mock = AsyncMock(return_value="realized-new-token")
        with patch.object(self.client, "_access_token", new=refresh_mock):
            payload, cont_yn, next_key, ret_token = asyncio.run(
                self.client._post_realized_page(
                    fake, "realized-old-token", "/api/dostk/acnt", "ka10073",
                    {"strt_dt": "20260901", "end_dt": "20260930"},
                )
            )
        self.assertEqual(ret_token, "realized-new-token")
        self.assertEqual(payload["return_code"], 0)
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(fake.requests[1][1]["headers"]["authorization"], "Bearer realized-new-token")

    # 13. End-to-end sync_holdings with 8005 recovery and token propagation
    def test_sync_holdings_8005_recovery_and_token_propagation(self):
        # 1st call: fetch_account_number gets 8005 -> refreshes token -> gets acctNo
        # 2nd call: fetch_domestic_balance uses the refreshed token directly
        fake = FakeClient([
            FakeResponse({"return_code": 8005, "return_msg": "8005: Token이 유효하지 않습니다"}),
            FakeResponse({"return_code": 0, "acctNo": "1234567890"}),
            FakeResponse({"return_code": 0, "acnt_evlt_remn_indv_tot": []}),
            FakeResponse({"return_code": 0, "entr": "100000"}),
        ])
        initial_token = "stale-cached-token"
        refreshed_token = "freshly-recovered-token"

        call_count = 0

        async def mock_access_token(_client, force_refresh=False):
            nonlocal call_count
            call_count += 1
            if force_refresh:
                self.client._token = Token(refreshed_token, time.time() + 3600)
                return refreshed_token
            self.client._token = Token(initial_token, time.time() + 3600)
            return initial_token

        with patch("app.services.kiwoom_openapi.require_external_network"), \
             patch("httpx.AsyncClient", return_value=fake), \
             patch.object(self.client, "_access_token", side_effect=mock_access_token):
            result = asyncio.run(self.client.sync_holdings())

        self.assertEqual(result.state.name, "AUTHORITATIVE_EMPTY")
        self.assertEqual(self.client.account_cash["1234567890"]["KRW"], 100000.0)
        # Verify requests
        # Request 0: ka00001 with stale token -> 8005
        # Request 1: ka00001 with refreshed token -> 200
        # Request 2: kt00018 with refreshed token -> 200 (not stale token!)
        # Request 3: kt00001 with refreshed token -> 200
        self.assertEqual(fake.requests[0][1]["headers"]["authorization"], f"Bearer {initial_token}")
        self.assertEqual(fake.requests[1][1]["headers"]["authorization"], f"Bearer {refreshed_token}")
        self.assertEqual(fake.requests[2][1]["headers"]["authorization"], f"Bearer {refreshed_token}")
        self.assertEqual(fake.requests[3][1]["headers"]["authorization"], f"Bearer {refreshed_token}")


if __name__ == "__main__":
    unittest.main()
