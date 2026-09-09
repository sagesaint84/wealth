from __future__ import annotations

import asyncio
import importlib
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.services import historical_fx
from regression_support import import_main_without_loading_real_env


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, *_args, **_kwargs):
        return self.response


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class StartupIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = import_main_without_loading_real_env()

    def test_test_mode_is_explicit_and_startup_keeps_background_jobs_suppressed(self):
        self.assertEqual(self.main.WEALTH_ENV, "test")
        with patch.object(self.main, "sync_historical_fx", new_callable=AsyncMock) as fx, \
             patch.object(self.main, "sync_stock_master_online", new_callable=AsyncMock) as stocks:
            asyncio.run(self.main.ensure_data_dir())
        fx.assert_not_awaited()
        stocks.assert_not_awaited()

    def test_raw_testclient_startup_does_not_run_background_jobs(self):
        with patch.object(self.main, "sync_historical_fx", new_callable=AsyncMock) as fx, \
             patch.object(self.main, "sync_stock_master_online", new_callable=AsyncMock) as stocks:
            with TestClient(self.main.app) as client:
                response = client.get("/manifest.json")
        self.assertEqual(response.status_code, 200)
        fx.assert_not_awaited()
        stocks.assert_not_awaited()

    def test_app_uses_lifespan_and_runs_existing_startup_contract_once(self):
        self.assertIs(self.main.app.router.lifespan_context, self.main.app_lifespan)
        with patch.object(self.main, "ensure_data_dir", new_callable=AsyncMock) as ensure:
            with TestClient(self.main.app) as client:
                self.assertEqual(client.get("/manifest.json").status_code, 200)
            ensure.assert_awaited_once_with()

    def test_lifespan_exits_cleanly(self):
        async def exercise():
            async with self.main.app.router.lifespan_context(self.main.app):
                return True

        self.assertTrue(asyncio.run(exercise()))

    def test_mocked_fx_response_writes_only_temp_cache(self):
        payload = {"chart": {"result": [{"timestamp": [1704067200], "indicators": {"quote": [{"close": [1300.25]}]}}]}}
        with tempfile.TemporaryDirectory(prefix="wealth-fx-test-") as temp:
            cache = Path(temp) / "historical_fx_cache.json"
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), \
                 patch.object(historical_fx, "FX_CACHE_FILE", cache), \
                 patch.object(historical_fx.httpx, "AsyncClient", return_value=FakeAsyncClient(FakeResponse(payload))), \
                 patch.object(historical_fx, "_HISTORICAL_FX_MAP", {}):
                result = asyncio.run(historical_fx.sync_historical_fx())
            self.assertEqual(result["2024-01-01"], 1300.25)
            self.assertTrue(cache.exists())
            self.assertNotEqual(cache.resolve(), (Path(__file__).resolve().parents[1] / "data" / "historical_fx_cache.json").resolve())

    def test_mocked_fx_failure_preserves_temp_cache(self):
        with tempfile.TemporaryDirectory(prefix="wealth-fx-test-") as temp:
            cache = Path(temp) / "historical_fx_cache.json"
            cache.write_text('{"2024-01-01": 1300.0}', encoding="utf-8")
            before = cache.read_bytes()
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), \
                 patch.object(historical_fx, "FX_CACHE_FILE", cache), \
                 patch.object(historical_fx.httpx, "AsyncClient", side_effect=OSError("synthetic network failure")), \
                 patch.object(historical_fx, "_HISTORICAL_FX_MAP", {}):
                result = asyncio.run(historical_fx.sync_historical_fx())
            self.assertEqual(result["2024-01-01"], 1300.0)
            self.assertEqual(cache.read_bytes(), before)

    def test_external_socket_is_blocked_but_loopback_policy_is_distinct(self):
        sock = socket.socket()
        with self.assertRaises(AssertionError):
            sock.connect(("203.0.113.1", 80))
        sock.close()


if __name__ == "__main__":
    unittest.main()
