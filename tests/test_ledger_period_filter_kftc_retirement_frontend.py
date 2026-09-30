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
        cls.kftc_js = KFTC_JS.read_text(encoding="utf-8")
        cls.loader_js = LOADER_JS.read_text(encoding="utf-8")

    def test_loader_registers_ledger_and_kftc_extensions_after_period_core(self) -> None:
        for marker in (
            "wealthPeriodFilterCoreScript",
            "wealthIncomePeriodBrokerFilterScript",
            "wealthLedgerPeriodFilterScript",
            "wealthKftcRetirementScript",
        ):
            self.assertIn(marker, self.loader_js)
        self.assertIn("/static/wealth-ledger-period-filter.js?v=10.6f1", self.loader_js)
        self.assertIn("/static/wealth-kftc-retirement.js?v=10.6f1", self.loader_js)
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
        self.assertIn("for (let month = 1; month <= 12; month += 1)", self.ledger_js)
        self.assertIn("/api/ledger?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&owner=${encodeURIComponent(owner)}", self.ledger_js)
        self.assertIn("requestSequence", self.ledger_js)
        self.assertNotIn("method: 'POST'", self.ledger_js)
        self.assertNotIn("method: 'PUT'", self.ledger_js)
        self.assertNotIn("method: 'DELETE'", self.ledger_js)

    def test_ledger_annual_view_rebuilds_summary_categories_and_monthly_trend(self) -> None:
        self.assertIn("function mergeAnnualLedger", self.ledger_js)
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
            self.assertIn(marker, self.ledger_js)
        self.assertIn("Array.from({ length: 12 }", self.ledger_js)
        self.assertIn("__ledger_annual_view", self.ledger_js)

    def test_ledger_month_bar_drills_back_into_monthly_scope(self) -> None:
        self.assertIn("data-ledger-month", self.ledger_js)
        self.assertIn("currentLedgerMonth = month", self.ledger_js)
        self.assertIn("annualView = false", self.ledger_js)
        self.assertIn("void window.loadLedger()", self.ledger_js)

    def test_kftc_bank_and_openapi_sections_are_removed_from_ui(self) -> None:
        self.assertIn("kftcOpenBankingCard", self.kftc_js)
        self.assertIn("openapiKftcSection", self.kftc_js)
        self.assertIn("document.getElementById(id)?.remove()", self.kftc_js)
        self.assertIn("display:none!important", self.kftc_js)
        self.assertIn("MutationObserver", self.kftc_js)

    def test_kftc_user_facing_actions_are_retired_without_deleting_backend_data(self) -> None:
        for marker in (
            "window.refreshKftcStatus = retiredAsync",
            "window.handleStartKftcOAuth = retiredAction",
            "window.handleFetchKftcAccounts = retiredAsync",
            "window.handlePreviewKftcBalance = retiredAsync",
            "window.handleDisconnectKftc = retiredAsync",
            "window.refreshUserKftcOpenApiStatus = retiredAsync",
            "window.handleSaveUserKftcConfig = retiredAsync",
        ):
            self.assertIn(marker, self.kftc_js)
        self.assertNotIn("/api/kftc", self.kftc_js)
        self.assertNotIn("/api/user/kftc", self.kftc_js)


if __name__ == "__main__":
    unittest.main()
