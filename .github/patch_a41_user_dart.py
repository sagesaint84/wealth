from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Reuse the established per-user DART credential resolver.
replace_once(
    "app/services/dividend_official_sources.py",
    "import math\nimport os\nimport time\n",
    "import math\nimport time\n",
)
replace_once(
    "app/services/dividend_official_sources.py",
    "from app.services.network_policy import external_network_allowed\n",
    "from app.services.network_policy import external_network_allowed\nfrom app.services.ipo.dart_client import DartClient\n",
)
replace_once(
    "app/services/dividend_official_sources.py",
    "async def get_official_dividend_evidence(\n    holdings: Iterable[dict[str, Any]],\n    *,\n    api_key: str | None = None,\n",
    "async def get_official_dividend_evidence(\n    holdings: Iterable[dict[str, Any]],\n    *,\n    username: str | None = None,\n    api_key: str | None = None,\n",
)
replace_once(
    "app/services/dividend_official_sources.py",
    "    network_allowed = external_network_allowed()\n    key = (api_key if api_key is not None else os.getenv(\"WEALTH_OPENDART_API_KEY\", \"\")).strip()\n    day = as_of.date() if isinstance(as_of, datetime) else (as_of or _now_kst().date())\n",
    "    network_allowed = external_network_allowed()\n    if api_key is not None:\n        key = api_key.strip()\n        credential_source = \"explicit\" if key else \"unconfigured\"\n    else:\n        dart_client = DartClient(username=username)\n        key = dart_client.api_key\n        credential_source = dart_client.credential_source\n    day = as_of.date() if isinstance(as_of, datetime) else (as_of or _now_kst().date())\n",
)
replace_once(
    "app/services/dividend_official_sources.py",
    '        "opendart_configured": bool(key),\n',
    '        "opendart_configured": bool(key),\n        "opendart_credential_source": credential_source,\n',
)
replace_once(
    "app/services/dividend_official_sources.py",
    "async def enrich_dividend_summary_with_official_sources(\n    summary: dict[str, Any],\n    holdings: list[dict[str, Any]],\n    *,\n    fx_rate: float = 1385.0,\n",
    "async def enrich_dividend_summary_with_official_sources(\n    summary: dict[str, Any],\n    holdings: list[dict[str, Any]],\n    *,\n    username: str | None = None,\n    fx_rate: float = 1385.0,\n",
)
replace_once(
    "app/services/dividend_official_sources.py",
    "    evidence_result = await get_official_dividend_evidence(\n        holdings,\n        api_key=api_key,\n",
    "    evidence_result = await get_official_dividend_evidence(\n        holdings,\n        username=username,\n        api_key=api_key,\n",
)

# Thread authenticated username from every user-scoped forecast caller.
replace_once(
    "app/services/web_finance.py",
    "async def get_web_dividend_summary(\n    holdings: list[dict[str, Any]], fx_rate: float = 1385.0\n) -> dict[str, Any]:\n",
    "async def get_web_dividend_summary(\n    holdings: list[dict[str, Any]], fx_rate: float = 1385.0, *, username: str | None = None\n) -> dict[str, Any]:\n",
)
replace_once(
    "app/services/web_finance.py",
    "        return await enrich_dividend_summary_with_official_sources(\n            summary,\n            holdings,\n            fx_rate=fx_rate,\n",
    "        return await enrich_dividend_summary_with_official_sources(\n            summary,\n            holdings,\n            username=username,\n            fx_rate=fx_rate,\n",
)
replace_once(
    "app/main.py",
    "    summary = await get_web_dividend_summary(holdings, fx_rate=fx_rate)\n    return summary\n\n\n@app.post(\"/api/dividends/financial-income-simulation\")",
    "    summary = await get_web_dividend_summary(holdings, fx_rate=fx_rate, username=username)\n    return summary\n\n\n@app.post(\"/api/dividends/financial-income-simulation\")",
)
replace_once(
    "app/services/tax/financial_income.py",
    "    forecast = await get_web_dividend_summary(scoped_holdings, fx_rate=fx_rate)\n",
    "    forecast = await get_web_dividend_summary(\n        scoped_holdings, fx_rate=fx_rate, username=username\n    )\n",
)

# Extend A-4.1 tests with user-scoped credential and forwarding guards.
test_path = Path("tests/test_dividend_official_user_scope.py")
test_path.write_text(
    '''from __future__ import annotations\n\nimport unittest\nfrom unittest.mock import AsyncMock, MagicMock, patch\n\nfrom app.services import dividend_official_sources as official\nfrom app.services import web_finance\n\n\nclass DividendOfficialUserScopeTests(unittest.IsolatedAsyncioTestCase):\n    async def test_user_scoped_dart_client_is_used_when_no_explicit_key(self):\n        resolved = MagicMock()\n        resolved.api_key = \"USER_DART_KEY\"\n        resolved.credential_source = \"user_config\"\n        with (\n            patch.object(official, \"DartClient\", return_value=resolved) as dart_client,\n            patch.object(official, \"external_network_allowed\", return_value=False),\n        ):\n            result = await official.get_official_dividend_evidence(\n                [{\"code\": \"005930\", \"currency\": \"KRW\"}],\n                username=\"user_a\",\n            )\n        dart_client.assert_called_once_with(username=\"user_a\")\n        self.assertTrue(result[\"policy\"][\"opendart_configured\"])\n        self.assertEqual(result[\"policy\"][\"opendart_credential_source\"], \"user_config\")\n\n    async def test_explicit_key_remains_test_injection_and_skips_user_resolver(self):\n        with (\n            patch.object(official, \"DartClient\") as dart_client,\n            patch.object(official, \"external_network_allowed\", return_value=False),\n        ):\n            result = await official.get_official_dividend_evidence(\n                [{\"code\": \"005930\", \"currency\": \"KRW\"}],\n                username=\"user_a\",\n                api_key=\"EXPLICIT_KEY\",\n            )\n        dart_client.assert_not_called()\n        self.assertEqual(result[\"policy\"][\"opendart_credential_source\"], \"explicit\")\n\n    async def test_web_finance_forwards_username_to_official_enrichment(self):\n        legacy = {\"holding_dividends\": [], \"monthly_schedule\": []}\n        enriched = {**legacy, \"forecast_source_policy\": {\"status\": \"ok\"}}\n        with (\n            patch.object(\n                web_finance,\n                \"_legacy_get_web_dividend_summary\",\n                new=AsyncMock(return_value=legacy),\n            ),\n            patch(\n                \"app.services.dividend_official_sources.enrich_dividend_summary_with_official_sources\",\n                new=AsyncMock(return_value=enriched),\n            ) as enrich,\n        ):\n            result = await web_finance.get_web_dividend_summary(\n                [], fx_rate=1400.0, username=\"user_a\"\n            )\n        self.assertIs(result, enriched)\n        self.assertEqual(enrich.await_args.kwargs[\"username\"], \"user_a\")\n\n    def test_user_scoped_callers_pass_username(self):\n        main_source = open(\"app/main.py\", encoding=\"utf-8\").read()\n        tax_source = open(\"app/services/tax/financial_income.py\", encoding=\"utf-8\").read()\n        self.assertIn(\n            \"get_web_dividend_summary(holdings, fx_rate=fx_rate, username=username)\",\n            main_source,\n        )\n        self.assertIn(\"scoped_holdings, fx_rate=fx_rate, username=username\", tax_source)\n\n    def test_no_parallel_wealth_opendart_env_contract(self):\n        for path in (\".env.example\", \"docker-compose.yml\", \"docker-compose.ghcr.yml\"):\n            text = open(path, encoding=\"utf-8\").read()\n            self.assertNotIn(\"WEALTH_OPENDART_API_KEY\", text)\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n''',
    encoding="utf-8",
)
