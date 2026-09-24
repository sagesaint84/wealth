from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "app/static/wealth.js").read_text(encoding="utf-8")
CSS = (ROOT / "app/static/wealth-layout.css").read_text(encoding="utf-8")


class TossWtsIncomeUiTests(unittest.TestCase):
    def test_income_section_is_directly_inside_toss_card_before_kis_card(self):
        toss = HTML.index('id="tossWtsCard"')
        income = HTML.index('id="tossWtsIncomeSection"')
        kis = HTML.index('id="kisRealizedCard"')
        self.assertGreater(income, toss)
        self.assertLess(income, kis)
        self.assertIn("토스 WTS 배당·이자 가져오기", HTML[toss:kis])

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
