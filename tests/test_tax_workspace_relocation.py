from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RISK_JS = ROOT / "app" / "static" / "wealth-family-financial-income-risk.js"
ALLOCATION_JS = ROOT / "app" / "static" / "wealth-family-financial-income-allocation.js"


class TaxWorkspaceRelocationStaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.risk = RISK_JS.read_text(encoding="utf-8")
        cls.allocation = ALLOCATION_JS.read_text(encoding="utf-8")

    def test_asset_tax_tab_and_panel_are_created(self):
        self.assertIn("taxTab.dataset.cat = 'tax'", self.risk)
        self.assertIn("taxTab.textContent = '🧾 세금'", self.risk)
        self.assertIn("panel.id = 'catPanelTax'", self.risk)
        self.assertIn('id="taxWorkspaceBody"', self.risk)

    def test_family_risk_mounts_into_tax_workspace_not_dividend_panel(self):
        self.assertIn("workspace.insertAdjacentHTML('beforeend', panelMarkup())", self.risk)
        self.assertNotIn("#dividendPanel .dividend-summary-cards", self.risk)
        self.assertIn("!taxWorkspaceActive()", self.risk)

    def test_family_allocation_load_is_tax_workspace_scoped(self):
        self.assertIn("window.WealthTaxWorkspace?.isActive", self.allocation)
        self.assertIn('.account-cat-tab[data-cat="tax"]', self.allocation)
        self.assertNotIn("#dividendModeTabs .heatmap-tab.active", self.allocation)

    def test_after_tax_panel_is_reanchored_to_dividend_summary(self):
        self.assertIn("document.getElementById('divTotalAnnual')", self.risk)
        self.assertIn("portfolioAfterTaxDividendPanel", self.risk)
        self.assertIn("dividendForecastSourceBanner", self.risk)
        self.assertIn("cards.insertAdjacentElement('afterend', afterTax)", self.risk)
        self.assertIn("cards.parentElement.insertBefore(banner, cards)", self.risk)

    def test_dividend_tax_dashboard_is_relocated_and_remains_runnable(self):
        self.assertIn("financialIncomeWhatIfPanel", self.risk)
        self.assertIn("beginWhatIfEstimatedModeSpoof", self.risk)
        self.assertIn("financialIncomeWhatIfForm", self.risk)
        self.assertIn("form.dispatchEvent(new Event('submit'", self.risk)

    def test_late_created_panels_are_relocated(self):
        self.assertIn("new MutationObserver(scheduleRelayout)", self.risk)
        self.assertIn("observer.observe(document.body, {childList: true, subtree: true})", self.risk)


if __name__ == "__main__":
    unittest.main()
