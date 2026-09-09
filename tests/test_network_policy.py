from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import historical_fx, stock_master, web_finance
from app.services.network_policy import ExternalNetworkDisabled, external_network_allowed, network_target_allowed


class TestModeNetworkPolicyTests(unittest.TestCase):
    def test_policy_disables_external_but_allows_loopback(self):
        with patch.dict(os.environ, {"WEALTH_ENV": "test"}):
            self.assertFalse(external_network_allowed())
            self.assertTrue(network_target_allowed("http://127.0.0.1:4829"))
            self.assertTrue(network_target_allowed("localhost"))
            self.assertTrue(network_target_allowed("::1"))
            self.assertFalse(network_target_allowed("https://query1.finance.yahoo.com"))

    def test_production_and_unset_allow_external_network(self):
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}):
            self.assertTrue(external_network_allowed())
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(external_network_allowed())

    def test_web_integrations_short_circuit_before_http_client(self):
        holdings = [{"id": "h1", "code": "005930", "currency": "KRW", "current_price": 70000}]
        with patch.dict(os.environ, {"WEALTH_ENV": "test"}), patch.object(
            web_finance.httpx, "AsyncClient", side_effect=AssertionError("HTTP client constructed")
        ):
            market = asyncio.run(web_finance.get_web_market_overview())
            dividends = asyncio.run(web_finance.get_web_dividend_summary(holdings))
            prices = asyncio.run(web_finance.refresh_all_holdings_prices(holdings))
            chart = asyncio.run(web_finance.fetch_stock_chart_data("005930"))
        self.assertTrue(market["unavailable"])
        self.assertTrue(dividends["unavailable"])
        self.assertTrue(prices["unavailable"])
        self.assertTrue(chart["unavailable"])
        self.assertEqual(prices["prices"], {})
        self.assertIsNone(prices["fx_rate"])

    def test_historical_fx_uses_only_local_cache(self):
        with tempfile.TemporaryDirectory(prefix="wealth-network-policy-") as temp:
            cache = Path(temp) / "historical_fx_cache.json"
            cache.write_text('{"2026-09-08": 1380.5}', encoding="utf-8")
            with patch.dict(os.environ, {"WEALTH_ENV": "test"}), patch.object(
                historical_fx, "FX_CACHE_FILE", cache
            ), patch.object(historical_fx, "_HISTORICAL_FX_MAP", {}), patch.object(
                historical_fx.httpx, "AsyncClient", side_effect=AssertionError("HTTP client constructed")
            ), patch.object(historical_fx.httpx, "get", side_effect=AssertionError("HTTP request attempted")):
                synced = asyncio.run(historical_fx.sync_historical_fx())
                rate = historical_fx.get_historical_fx_rate("2026-09-09")
            self.assertEqual(synced, {"2026-09-08": 1380.5})
            self.assertEqual(rate, 1380.5)

    def test_historical_fx_missing_cache_does_not_fetch_or_write(self):
        with tempfile.TemporaryDirectory(prefix="wealth-network-policy-") as temp:
            cache = Path(temp) / "missing.json"
            with patch.dict(os.environ, {"WEALTH_ENV": "test"}), patch.object(
                historical_fx, "FX_CACHE_FILE", cache
            ), patch.object(historical_fx, "_HISTORICAL_FX_MAP", {}), patch.object(
                historical_fx.httpx, "AsyncClient", side_effect=AssertionError("HTTP client constructed")
            ), patch.object(historical_fx.httpx, "get", side_effect=AssertionError("HTTP request attempted")):
                self.assertEqual(asyncio.run(historical_fx.sync_historical_fx()), {})
            self.assertFalse(cache.exists())

    def test_stock_master_online_paths_use_local_data_only(self):
        with patch.dict(os.environ, {"WEALTH_ENV": "test"}), patch.object(
            stock_master.httpx, "AsyncClient", side_effect=AssertionError("HTTP client constructed")
        ), patch.object(stock_master.httpx, "Client", side_effect=AssertionError("HTTP client constructed")):
            asyncio.run(stock_master.sync_stock_master_online())
            self.assertEqual(stock_master.search_naver_finance("삼성전자"), [])
            self.assertEqual(asyncio.run(stock_master.search_naver_finance_async("삼성전자")), [])

    def test_broker_clients_stop_before_http(self):
        from app.services.kb_openapi import KBOpenAPI
        from app.services.kis_openapi import KISOpenAPI
        from app.services.kiwoom_openapi import KiwoomOpenAPI
        from app.services.nhplug_openapi import NhPlugOpenAPI
        from app.services.toss_openapi import TossOpenAPI

        with patch.dict(os.environ, {"WEALTH_ENV": "test"}), patch(
            "app.services.user_openapi.get_user_openapi_config", return_value={}
        ):
            calls = [KBOpenAPI().call("/test", {}), TossOpenAPI()._get("/test"), NhPlugOpenAPI()._call("/test", {}), KISOpenAPI().sync_holdings(), KiwoomOpenAPI().sync_holdings()]
            for coroutine in calls:
                with self.assertRaises(ExternalNetworkDisabled):
                    asyncio.run(coroutine)

    def test_refresh_and_sync_endpoints_preserve_existing_data(self):
        from app import main

        existing = {
            "holdings": [{"id": "h1", "current_price": 70000}],
            "settings": {"fx_rates": {"KRW": 1.0, "USD": 1380.0}},
        }
        before = repr(existing)
        with patch.dict(os.environ, {"WEALTH_ENV": "test"}), patch.object(
            main, "get_current_username", return_value="fixture"
        ), patch.object(main, "read_portfolio", return_value=existing), patch.object(
            main, "write_portfolio", side_effect=AssertionError("test-mode endpoint wrote data")
        ), patch.object(
            main, "refresh_all_holdings_prices", new_callable=unittest.mock.AsyncMock,
        ) as refresh_external:
            refresh_result = asyncio.run(main.refresh_prices(unittest.mock.Mock()))
            sync_result = asyncio.run(main.sync_all_accounts(unittest.mock.Mock()))
        refresh_external.assert_not_awaited()
        self.assertEqual(repr(existing), before)
        self.assertEqual(refresh_result["status"], "TEST_MODE")
        self.assertTrue(refresh_result["data_preserved"])
        self.assertEqual(sync_result["status"], "TEST_MODE")
        self.assertTrue(sync_result["data_preserved"])
        self.assertTrue(all(item["data_preserved"] for item in sync_result["brokers"]))


if __name__ == "__main__":
    unittest.main()
