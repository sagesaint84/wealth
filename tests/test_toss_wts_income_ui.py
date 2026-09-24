from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/wealth.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/wealth-layout.css").read_text(encoding="utf-8")


class TossWtsIncomeUiTests(unittest.TestCase):
    def test_income_section_is_inside_dividend_panel_not_realized_panel(self):
        realized = HTML.index('id="realizedPnlPanel"')
        dividend = HTML.index('id="dividendPanel"')
        income = HTML.index('id="tossWtsIncomeSection"')
        holdings = HTML.index('id="holdingsPanel"')
        self.assertLess(realized, dividend)
        self.assertGreater(income, dividend)
        self.assertLess(income, holdings)
        self.assertIn("토스 WTS 배당·이자 가져오기", HTML[dividend:holdings])

    def test_dividend_defaults_to_actual_and_income_is_actual_only(self):
        tabs = HTML.index('id="dividendModeTabs"')
        actual = HTML.index('data-div-mode="actual"', tabs)
        estimated = HTML.index('data-div-mode="estimated"', tabs)
        self.assertLess(actual, estimated)
        self.assertIn('class="heatmap-tab active" data-div-mode="actual"', HTML)
        self.assertIn("let currentDividendMode = 'actual'", JS)
        self.assertIn("incomeSection.style.display = currentDividendMode === 'actual' ? 'flex' : 'none';", JS)

    def test_income_controls_table_and_confirmation_modal_exist(self):
        for value in (
            'id="tossWtsIncomeFromDate"',
            'id="tossWtsIncomeToDate"',
            'id="btnFetchTossWtsIncome"',
            'id="wtsIncomeSelectAll"',
            'id="wtsIncomeDestinationAccount"',
            'id="btnWtsIncomeImportSelected"',
            'id="wtsIncomeImportModalOverlay"',
            'id="btnWtsIncomeConfirmCommit"',
        ):
            self.assertIn(value, HTML)

    def test_income_has_same_wts_status_and_runtime_controls_as_realized(self):
        for value in (
            'id="tossWtsIncomeStatusText"',
            'id="btnCheckTossWtsIncomeStatus"',
            'id="btnConfirmTossWtsIncomeSession"',
        ):
            self.assertIn(value, HTML)
        self.assertIn(
            "document.getElementById('btnCheckTossWtsIncomeStatus')?.addEventListener('click', checkTossWtsStatus);",
            JS,
        )
        self.assertIn(
            "document.getElementById('btnConfirmTossWtsIncomeSession')?.addEventListener('click', confirmTossWtsSession);",
            JS,
        )
        self.assertIn("'tossWtsStatusText', 'tossWtsIncomeStatusText'", JS)

    def test_javascript_uses_signed_preview_commit_api_flow(self):
        for value in (
            "tossWtsIncomeState",
            "fetchTossWtsIncomeFeed",
            "openTossWtsIncomeImportPreview",
            "commitTossWtsIncomeImport",
            "initTossWtsIncomeUI",
            "/api/toss-wts/income-feed/fetch",
            "/api/toss-wts/income-feed/import-preview",
            "/api/toss-wts/income-feed/import",
        ):
            self.assertIn(value, JS)
        self.assertIn("initTossWtsIncomeUI();", JS)

    def test_income_feed_is_not_persisted_in_browser_storage(self):
        self.assertNotIn("localStorage.setItem('tossWtsIncome", JS)
        self.assertNotIn('localStorage.setItem("tossWtsIncome', JS)
        self.assertNotIn("sessionStorage.setItem('tossWtsIncome", JS)

    def test_income_styles_exist(self):
        self.assertIn(".toss-wts-income-section", CSS)
        self.assertIn(".toss-wts-income-type", CSS)
        self.assertIn(".income-account_interest", CSS)


if __name__ == "__main__":
    unittest.main()
