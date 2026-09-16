from pathlib import Path
import unittest


class MoneyLogNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.html = (root / "app/static/index.html").read_text(encoding="utf-8")
        cls.layout = (root / "app/static/wealth-layout.js").read_text(encoding="utf-8")
        cls.js = (root / "app/static/wealth.js").read_text(encoding="utf-8")
        cls.css = (root / "app/static/wealth-layout.css").read_text(encoding="utf-8")

    def test_primary_navigation_uses_five_requested_labels(self):
        for definition in (
            "home: ['홈'",
            "invest: ['주식 투자'",
            "assets: ['종합 자산'",
            "income: ['머니 로그'",
            "settings: ['설정'",
        ):
            with self.subTest(definition=definition):
                self.assertIn(definition, self.layout)
        views_block = self.layout[self.layout.index("const views = {"):self.layout.index("const icons = {")]
        self.assertNotIn("ledger:", views_block)
        self.assertIn("filter(key => key !== 'settings')", self.layout)
        self.assertIn(".wealth-nav-bottom { display: contents; }", self.css)

    def test_money_log_has_exactly_three_primary_tabs(self):
        tab_block = self.layout[self.layout.index("incomeTabs.innerHTML"):self.layout.index("page('income').append(incomeTabs)")]
        self.assertEqual(tab_block.count('class="income-tab'), 3)
        self.assertIn('data-income="pnl"', tab_block)
        self.assertIn('data-income="dividend"', tab_block)
        self.assertIn('data-income="ledger"', tab_block)
        for label in ("실현손익", "배당·이자", "가계부"):
            self.assertIn(label, tab_block)

    def test_existing_financial_panels_are_moved_without_replacement(self):
        self.assertIn("['realizedPnlPanel', 'dividendPanel', 'ledgerSectionPanel'].forEach", self.layout)
        for panel_id in ("realizedPnlPanel", "dividendPanel", "ledgerSectionPanel"):
            with self.subTest(panel_id=panel_id):
                self.assertEqual(self.html.count(f'id="{panel_id}"'), 1)
        for owner_tabs in ("pnlFamilyTabs", "dividendFamilyTabs", "ledgerFamilyTabs"):
            self.assertIn(f'id="{owner_tabs}"', self.html)

    def test_tab_switching_only_changes_presentation_and_loads_existing_ledger(self):
        self.assertIn("['pnl', 'dividend', 'ledger'].includes(tab)", self.js)
        self.assertIn("classList.toggle('wealth-income-hidden', currentIncomeTab !== 'ledger')", self.js)
        self.assertIn("currentIncomeTab === 'ledger'", self.js)
        self.assertIn("loadLedger()", self.js)
        for existing_action in (
            "openLedgerTxModal()",
            "saveLedgerTransaction()",
            "deleteLedgerTransaction",
            "openLedgerExcelModal()",
        ):
            with self.subTest(existing_action=existing_action):
                self.assertIn(existing_action, self.js + self.html)

    def test_legacy_hashes_remain_compatible(self):
        self.assertIn("legacyMoneyLogTabs = { ledger: 'ledger', dividend: 'dividend', pnl: 'pnl' }", self.layout)
        self.assertIn("? 'income'", self.layout)
        self.assertIn("location.hash === '#ledger'", self.js)
        self.assertIn("currentIncomeTab === 'pnl' ? '#income'", self.js)

    def test_header_and_responsive_tab_contract(self):
        self.assertIn("['머니 로그', '머니 로그', '실현손익, 배당·이자, 수입·지출 내역을 한곳에서 확인하세요.']", self.layout)
        self.assertIn("overflow-x: auto", self.css)
        self.assertIn("white-space: nowrap", self.css)


if __name__ == "__main__":
    unittest.main()
