from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER_JS = ROOT / "app" / "static" / "wealth-ledger-period-filter.js"
KFTC_JS = ROOT / "app" / "static" / "wealth-kftc-retirement.js"
LOADER_JS = ROOT / "app" / "static" / "wealth-family-financial-income-allocation.js"


class LedgerPeriodFilterAndKftcRetirementFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ledger_js = LEDGER_JS.read_text(encoding="utf-8")
        cls.feature_js = (ROOT / "app/static/wealth-ledger-feature-controller.js").read_text(encoding="utf-8")
        cls.data_js = (ROOT / "app/static/wealth-ledger-data.js").read_text(encoding="utf-8")
        cls.index_html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        cls.wealth_js = (ROOT / "app/static/wealth.js").read_text(encoding="utf-8")
        cls.loader_js = LOADER_JS.read_text(encoding="utf-8")

    def test_loader_keeps_ledger_without_a_kftc_retirement_dependency(self) -> None:
        for marker in (
            "wealthPeriodFilterCoreScript",
            "wealthIncomePeriodBrokerFilterScript",
            "wealthLedgerPeriodFilterScript",
        ):
            self.assertIn(marker, self.loader_js)
        self.assertRegex(self.index_html, r'id="wealthLedgerPeriodFilterScript" data-loaded="true" src="/static/wealth-ledger-period-filter\.js\?v=[^"]+"')
        self.assertLess(self.index_html.index('id="wealthPeriodFilterCoreScript"'),
                        self.index_html.index('id="wealthLedgerPeriodFilterScript"'))
        self.assertLess(self.index_html.index('id="wealthLedgerPeriodFilterScript"'),
                        self.index_html.index('src="/static/wealth-family-financial-income-allocation.js'))
        self.assertNotIn("window.loadLedger =", self.ledger_js)
        self.assertNotIn("wealthKftcRetirementScript", self.loader_js)
        self.assertFalse(KFTC_JS.exists())
        self.assertLess(
            self.loader_js.index("wealthPeriodFilterCoreScript"),
            self.loader_js.index("wealthLedgerPeriodFilterScript"),
        )

    def test_ledger_uses_shared_period_core_and_adds_year_selector(self) -> None:
        self.assertIn("const period = window.WealthPeriodFilter", self.ledger_js)
        self.assertIn("ledgerYearSelect", self.ledger_js)
        self.assertIn("가계부 연도 선택", self.ledger_js)
        self.assertIn("period.fixedYearRange", self.ledger_js)
        self.assertIn("period.scopeLabel", self.ledger_js)

    def test_ledger_annual_view_reads_twelve_months_without_mutating_data(self) -> None:
        read = self.feature_js.split("async function loadLedger()", 1)[1].split("function renderScreen", 1)[0]
        self.assertIn("for (let monthIndex = 1; monthIndex <= 12; monthIndex++)", read)
        self.assertIn("WealthLedgerData.loadMonth(api, year, monthIndex, owner)", read)
        self.assertIn("if (!isCurrent())", read)
        self.assertIn("/api/ledger?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&owner=${encodeURIComponent(owner)}", self.data_js)
        for source in (self.ledger_js, self.data_js, read):
            self.assertNotRegex(source, r"method:\s*['\"](?:POST|PUT|DELETE)['\"]")

    def test_ledger_annual_view_rebuilds_summary_categories_and_monthly_trend(self) -> None:
        self.assertIn("function mergeAnnualLedger", self.data_js)
        for marker in (
            "total_income",
            "total_expense",
            "total_transfer",
            "net_savings",
            "savings_rate",
            "category_expenses",
            "category_incomes",
            "monthly_trend",
            "transactions",
        ):
            self.assertIn(marker, self.data_js)
        self.assertIn("Array.from({ length: 12 }", self.data_js)
        self.assertIn("__ledger_annual_view", self.data_js)

    def test_ledger_month_bar_drills_back_into_monthly_scope(self) -> None:
        self.assertIn("data-ledger-month", self.ledger_js)
        self.assertIn("void ledger.selectMonth(ledger.getYear(), month)", self.ledger_js)
        select_month = self.feature_js.split("function selectMonth(year, month)", 1)[1].split("function setPeriodRenderer", 1)[0]
        self.assertIn("setAnnualView(false)", select_month)
        self.assertIn("currentLedgerMonth = month", select_month)
        self.assertIn("return loadLedger()", select_month)

    def test_retired_ui_is_never_generated_instead_of_removed_afterward(self) -> None:
        for marker in ("kftcOpenBankingCard", "openapiKftcSection", "wealthKftcRetirementStyle"):
            self.assertNotIn(marker, self.index_html)
            self.assertNotIn(marker, self.wealth_js)
            self.assertNotIn(marker, self.loader_js)

    def test_dormant_backend_and_callback_notifications_are_preserved(self) -> None:
        self.assertIn("kftc_connected", self.wealth_js)
        self.assertIn("kftc_error", self.wealth_js)
        self.assertNotIn("/api/kftc", self.wealth_js)
        self.assertNotIn("/api/user/kftc", self.wealth_js)
        routes = (ROOT / "app/main.py").read_text(encoding="utf-8")
        self.assertIn('/api/kftc/openbanking/oauth/callback', routes)
        self.assertIn('/api/user/kftc-openbanking-config', routes)


if __name__ == "__main__":
    unittest.main()
