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
        self.assertIn("let body = panel.querySelector('#taxWorkspaceBody')", self.risk)
        self.assertIn("body.id = 'taxWorkspaceBody'", self.risk)
        self.assertIn('if (!body)', self.risk)

    def test_product_information_renderer_preserves_tax_workspace(self):
        core = (ROOT / 'app/static/wealth.js').read_text(encoding='utf-8')
        renderer = core.split('function renderAssetTaxInformation() {', 1)[1].split('// Check URL query parameters', 1)[0]
        self.assertIn("panel.querySelector('#assetTaxInformation')", renderer)
        self.assertIn('information.replaceChildren()', renderer)
        self.assertIn('information.append(card)', renderer)
        self.assertNotIn('panel.replaceChildren()', renderer)
        self.assertNotIn('panel.innerHTML', renderer)
        self.assertIn("['national_pension','yellow_umbrella','pension','irp']", renderer)

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
        what_if = (ROOT / 'app/static/wealth-financial-income-what-if.js').read_text(encoding='utf-8')
        self.assertIn("window.WealthFinancialIncomeWhatIf?.syncVisibility()", self.risk)
        self.assertIn("window.WealthFinancialIncomeWhatIf?.runSimulation()", self.risk)
        self.assertNotIn("beginWhatIfEstimatedModeSpoof", self.risk)
        self.assertNotIn("whatIfSpoofSnapshot", self.risk)
        self.assertIn("taxBody.appendChild(panel)", what_if)
        self.assertIn("summary.insertAdjacentElement('afterend', panel)", what_if)
        self.assertIn("visibilityContext === 'actual'", what_if)

    def test_late_created_panels_are_relocated(self):
        self.assertIn("new MutationObserver(scheduleRelayout)", self.risk)
        self.assertIn("observer.observe(document.body, {childList: true, subtree: true})", self.risk)


if __name__ == "__main__":
    unittest.main()
