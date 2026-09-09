from pathlib import Path
import re
import unittest


class SectionNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.html = (root / "app/static/index.html").read_text(encoding="utf-8")
        cls.js = (root / "app/static/wealth.js").read_text(encoding="utf-8")
        cls.layout_js = (root / "app/static/wealth-layout.js").read_text(encoding="utf-8")
        cls.css = (root / "app/static/wealth-layout.css").read_text(encoding="utf-8")

    def test_asset_category_tabs_and_existing_panels_remain(self):
        self.assertNotIn('id="assetCategoryTabs"', self.html)
        self.assertIn("assetCategoryTabs.id = 'assetCategoryTabs'", self.layout_js)
        for label in ("증권", "은행", "보험", "부동산"):
            self.assertIn(label, self.html)
        for panel in ("catPanelSecurities", "catPanelBanking", "catPanelInsurance", "catPanelRealEstate"):
            self.assertIn(panel, self.html)
        self.assertIn("switchAccountCategory(category)", self.js)

    def test_asset_tabs_are_moved_before_accounts_panel_at_page_level(self):
        tabs_move = self.layout_js.index("page('assets').append(assetCategoryTabs)")
        panel_move = self.layout_js.index("move('accountsPanel', page('assets'))")
        self.assertLess(tabs_move, panel_move)

    def test_income_tabs_are_siblings_of_content_panels(self):
        self.assertNotIn('id="incomeTabs"', self.html)
        tabs_move = self.layout_js.index("page('income').append(incomeTabs)")
        pnl_move = self.layout_js.index("['realizedPnlPanel', 'dividendPanel']")
        self.assertLess(tabs_move, pnl_move)
        self.assertNotIn("realizedPnlPanel.append", self.layout_js)
        self.assertNotIn("dividendPanel.append", self.layout_js)

    def test_income_tabs_toggle_existing_panels(self):
        self.assertIn('data-income="pnl"', self.layout_js)
        self.assertIn('data-income="dividend"', self.layout_js)
        self.assertIn("realizedPnlPanel", self.js)
        self.assertIn("dividendPanel", self.js)
        self.assertIn("wealth-income-hidden", self.css)

    def test_shared_section_tab_visual_language_and_mobile_overflow(self):
        self.assertIn("wealth-section-tabs", self.layout_js)
        self.assertIn("overflow-x: auto", self.css)
        self.assertIn("white-space: nowrap", self.css)

    def test_tabs_have_no_legacy_global_orphan_markup(self):
        self.assertNotIn('id="assetCategoryTabs"', self.html)
        self.assertNotIn('id="incomeTabs"', self.html)
        for selector in ("wealth-section-tabs", "account-category-tabs", "income-tabs"):
            blocks = re.findall(rf"[^{{}}]*\.{selector}[^{{}}]*\{{([^{{}}]*)\}}", self.css)
            self.assertTrue(blocks)
            for block in blocks:
                self.assertNotRegex(block, r"position\s*:\s*(?:fixed|sticky)")
                self.assertNotRegex(block, r"(?:^|;)\s*bottom\s*:")


if __name__ == "__main__":
    unittest.main()
