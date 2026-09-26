from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services import dividend_official_sources as official
from app.services import web_finance


class DividendOfficialUserScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_scoped_dart_client_is_used_when_no_explicit_key(self):
        resolved = MagicMock()
        resolved.api_key = "USER_DART_KEY"
        resolved.credential_source = "user_config"
        with (
            patch.object(official, "DartClient", return_value=resolved) as dart_client,
            patch.object(official, "external_network_allowed", return_value=False),
        ):
            result = await official.get_official_dividend_evidence(
                [{"code": "005930", "currency": "KRW"}],
                username="user_a",
            )
        dart_client.assert_called_once_with(username="user_a")
        self.assertTrue(result["policy"]["opendart_configured"])
        self.assertEqual(result["policy"]["opendart_credential_source"], "user_config")

    async def test_explicit_key_remains_test_injection_and_skips_user_resolver(self):
        with (
            patch.object(official, "DartClient") as dart_client,
            patch.object(official, "external_network_allowed", return_value=False),
        ):
            result = await official.get_official_dividend_evidence(
                [{"code": "005930", "currency": "KRW"}],
                username="user_a",
                api_key="EXPLICIT_KEY",
            )
        dart_client.assert_not_called()
        self.assertEqual(result["policy"]["opendart_credential_source"], "explicit")

    async def test_web_finance_forwards_username_to_official_enrichment(self):
        legacy = {"holding_dividends": [], "monthly_schedule": []}
        enriched = {**legacy, "forecast_source_policy": {"status": "ok"}}
        with (
            patch.object(
                web_finance,
                "_legacy_get_web_dividend_summary",
                new=AsyncMock(return_value=legacy),
            ),
            patch(
                "app.services.dividend_official_sources.enrich_dividend_summary_with_official_sources",
                new=AsyncMock(return_value=enriched),
            ) as enrich,
        ):
            result = await web_finance.get_web_dividend_summary(
                [], fx_rate=1400.0, username="user_a"
            )
        self.assertIs(result, enriched)
        self.assertEqual(enrich.await_args.kwargs["username"], "user_a")

    def test_user_scoped_callers_pass_username(self):
        main_source = open("app/main.py", encoding="utf-8").read()
        tax_source = open("app/services/tax/financial_income.py", encoding="utf-8").read()
        self.assertIn(
            "get_web_dividend_summary(holdings, fx_rate=fx_rate, username=username)",
            main_source,
        )
        self.assertIn("scoped_holdings, fx_rate=fx_rate, username=username", tax_source)

    def test_no_parallel_wealth_opendart_env_contract(self):
        for path in (".env.example", "docker-compose.yml", "docker-compose.ghcr.yml"):
            text = open(path, encoding="utf-8").read()
            self.assertNotIn("WEALTH_OPENDART_API_KEY", text)


if __name__ == "__main__":
    unittest.main()
