from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class HistoricalIpoImportFrontendContractTests(unittest.TestCase):
    def test_official_import_is_a_separate_preview_then_commit_action(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
        self.assertIn('id="ipoRefreshBtn"', html)  # Current refresh remains separate.
        self.assertIn('id="ipoHistoricalImportBtn"', html)
        self.assertIn('id="ipoHistoricalImportDialog"', html)
        self.assertIn('.xlsx,.xlsm,.xls,.csv', html)
        self.assertIn('KRX Data Marketplace [20001]', html)
        self.assertIn('/api/ipo/historical-import/preview', js)
        self.assertIn('/api/ipo/historical-import/commit', js)
        self.assertIn('historicalImportTicket', js)
        self.assertIn('historicalImportInFlight', js)
        self.assertIn('window.confirm(', js)

    def test_preview_renders_issues_without_html_injection(self):
        js = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
        view = (ROOT / "app" / "static" / "wealth-ipo-historical-preview-view.js").read_text(encoding="utf-8")
        self.assertIn("renderHistoricalImportPreview(payload);", js)
        self.assertIn("window.WealthIpoHistoricalPreviewView.render(payload)", js)
        self.assertIn("row.textContent =", view)
        self.assertIn("summary.textContent =", view)
        self.assertIn("issues_truncated", view)
        self.assertNotIn(".innerHTML", view, "Historical import server/user text must use safe DOM output")

    def test_historical_cards_use_actual_historical_fields(self):
        js = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
        self.assertIn('official_historical_import', js)
        self.assertIn('과거자료 · 미산정', js)
        self.assertIn('청약일 미수집', js)
        self.assertIn("'공모금액'", js)
        self.assertIn("'상장일'", js)

    def test_commit_resets_past_month_to_latest_imported_month(self):
        js = (ROOT / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
        commit = js.split("async function commitHistoricalImport()", 1)[1].split("let showExcludedSchedules", 1)[0]
        self.assertIn("ipoFilterGroup = 'LISTED';", commit)
        self.assertIn("ipoMonthExplicitlySelected = false;", commit)
        self.assertIn("ipoHistoryInitialized = false;", commit)
        self.assertLess(commit.index("ipoHistoryInitialized = false;"), commit.index("renderIpoList();"))


if __name__ == "__main__":
    unittest.main()
