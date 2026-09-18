from __future__ import annotations

import asyncio
import os
import unittest
from copy import deepcopy
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

os.environ.setdefault("WEALTH_ENV", "test")

import app.services.nhplug_openapi as nh_transport
from app.services.nhplug_openapi import NhPlugOpenAPI, NhPlugRateLimitError
from regression_support import authenticated_request, empty_portfolio, import_main_without_loading_real_env


class Response:
    def __init__(self, body, status_code=200, headers=None):
        self.body, self.status_code, self.headers = body, status_code, headers or {}
        self.is_error = status_code >= 400
        self.text = str(body)

    def json(self):
        return self.body


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


class NhRateLimitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        nh_transport._nh_next_request_at = 0.0
        nh_transport._nh_cooldown_until = 0.0
        self.client = object.__new__(NhPlugOpenAPI)
        self.client.base_url = "https://api.nhplug.com:8443"
        self.client.app_key = "fixture-key"
        self.client.app_secret = "fixture-secret"

    async def test_every_provider_request_passes_common_rate_gate(self):
        http = Client([Response({"rsp_cd": "00000"}), Response({"rsp_cd": "00000"})])
        gate = AsyncMock()
        with patch("app.services.nhplug_openapi.require_external_network"), \
             patch("app.services.nhplug_openapi.httpx.AsyncClient", return_value=http), \
             patch.object(self.client, "_access_token", new=AsyncMock(return_value="token")), \
             patch.object(self.client, "_rate_gate", new=gate):
            await self.client._call("/one", {})
            await self.client._call("/two", {})
        self.assertEqual(gate.await_count, 2)

    async def test_rate_limit_retries_once_then_succeeds(self):
        http = Client([Response({"rsp_cd": "IGW42903", "rsp_msg": "limit"}), Response({"rsp_cd": "00000"})])
        with patch("app.services.nhplug_openapi.require_external_network"), \
             patch("app.services.nhplug_openapi.httpx.AsyncClient", return_value=http), \
             patch.object(self.client, "_access_token", new=AsyncMock(return_value="token")), \
             patch.object(self.client, "_rate_gate", new=AsyncMock()), \
             patch.dict(os.environ, {"WEALTH_NH_RATE_LIMIT_MAX_RETRIES": "1"}):
            result = await self.client._call("/fixture", {})
        self.assertEqual(result["rsp_cd"], "00000")
        self.assertEqual(len(http.requests), 2)

    async def test_second_rate_limit_stops_after_two_requests_without_refresh(self):
        http = Client([Response({"rsp_cd": "IGW42903"}), Response({"rsp_cd": "IGW42903"})])
        token = AsyncMock(return_value="token")
        with patch("app.services.nhplug_openapi.require_external_network"), \
             patch("app.services.nhplug_openapi.httpx.AsyncClient", return_value=http), \
             patch.object(self.client, "_access_token", new=token), \
             patch.object(self.client, "_rate_gate", new=AsyncMock()), \
             patch.dict(os.environ, {"WEALTH_NH_RATE_LIMIT_MAX_RETRIES": "1"}):
            with self.assertRaises(NhPlugRateLimitError):
                await self.client._call("/fixture", {})
        self.assertEqual(len(http.requests), 2)
        self.assertEqual(token.await_args_list, [unittest.mock.call(http)])

    async def test_http_429_does_not_refresh_token(self):
        http = Client([Response({"rsp_cd": "IGW42903"}, status_code=429)])
        token = AsyncMock(return_value="token")
        with patch("app.services.nhplug_openapi.require_external_network"), \
             patch("app.services.nhplug_openapi.httpx.AsyncClient", return_value=http), \
             patch.object(self.client, "_access_token", new=token), \
             patch.object(self.client, "_rate_gate", new=AsyncMock()), \
             patch.dict(os.environ, {"WEALTH_NH_RATE_LIMIT_MAX_RETRIES": "0"}):
            with self.assertRaises(NhPlugRateLimitError):
                await self.client._call("/fixture", {})
        self.assertEqual(token.await_args_list, [unittest.mock.call(http)])

    async def test_401_still_refreshes_token_once(self):
        http = Client([Response({"rsp_cd": "IGW40043", "rsp_msg": "token expired"}, 401), Response({"rsp_cd": "00000"})])
        token = AsyncMock(side_effect=["old", "new"])
        with patch("app.services.nhplug_openapi.require_external_network"), \
             patch("app.services.nhplug_openapi.httpx.AsyncClient", return_value=http), \
             patch.object(self.client, "_access_token", new=token), \
             patch.object(self.client, "_rate_gate", new=AsyncMock()):
            await self.client._call("/fixture", {})
        self.assertEqual(token.await_args_list, [unittest.mock.call(http), unittest.mock.call(http, force_refresh=True)])
        self.assertEqual(len(http.requests), 2)

    async def test_cooldown_delays_next_shared_request_slot(self):
        nh_transport._nh_cooldown_until = 15.0
        sleep = AsyncMock()
        with patch("app.services.nhplug_openapi.time.monotonic", side_effect=[10.0, 15.0]), \
             patch("app.services.nhplug_openapi.asyncio.sleep", new=sleep), \
             patch.dict(os.environ, {"WEALTH_NH_MIN_CALL_INTERVAL_SEC": "0.25"}):
            await self.client._rate_gate()
        sleep.assert_awaited_once_with(5.0)

    def test_invalid_or_non_finite_environment_values_fall_back_safely(self):
        with patch.dict(os.environ, {"WEALTH_NH_MIN_CALL_INTERVAL_SEC": "inf"}):
            self.assertEqual(nh_transport._nh_positive_setting("WEALTH_NH_MIN_CALL_INTERVAL_SEC", 0.35, minimum=0.25), 0.35)
        with patch.dict(os.environ, {"WEALTH_NH_RATE_LIMIT_MAX_RETRIES": "not-a-number"}):
            self.assertEqual(nh_transport._nh_positive_setting("WEALTH_NH_RATE_LIMIT_MAX_RETRIES", 1.0), 1.0)
        limited, _code, retry_after = self.client._rate_limit_details(Response({"rsp_cd": "IGW42903"}, headers={"Retry-After": "inf"}))
        self.assertTrue(limited)
        self.assertIsNone(retry_after)

    async def test_rate_limit_sync_preserves_existing_portfolio_data(self):
        main = import_main_without_loading_real_env()
        existing = empty_portfolio(holdings=[{"id": "old", "source": "nhplug_api"}], settings={"cash_balances": {"nh": {"KRW": 5000}}})

        class RateLimitedNH:
            configured = True
            async def sync_holdings(self):
                raise NhPlugRateLimitError("IGW42903")

        with patch.object(main, "NhPlugOpenAPI", return_value=RateLimitedNH()), \
             patch.object(main, "read_portfolio", return_value=deepcopy(existing)) as read_portfolio, \
             patch.object(main, "write_portfolio") as write_portfolio:
            with self.assertRaises(HTTPException) as raised:
                await main.sync_namoo(authenticated_request("rate-limit-fixture"))
        self.assertEqual(raised.exception.status_code, 429)
        read_portfolio.assert_not_called()
        write_portfolio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
