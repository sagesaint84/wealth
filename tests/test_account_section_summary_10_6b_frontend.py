from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_JS = ROOT / "app" / "static" / "wealth-account-section-summary.js"
LOADER_JS = ROOT / "app" / "static" / "wealth-accountinfo-owner-options.js"


class AccountSectionSummary106BFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.summary_js = SUMMARY_JS.read_text(encoding="utf-8")
        cls.loader_js = LOADER_JS.read_text(encoding="utf-8")

    def test_loader_registers_versioned_summary_script_once(self) -> None:
        self.assertIn("wealthAccountSectionSummaryScript", self.loader_js)
        self.assertIn("/static/wealth-account-section-summary.js?v=10.6b2", self.loader_js)
        self.assertIn("window.WealthAccountSectionSummary", self.loader_js)

    def test_securities_summary_has_requested_account_and_asset_metrics(self) -> None:
        for marker in ("총 증권계좌", "총 증권자산", "주식자산", "예수금"):
            self.assertIn(marker, self.summary_js)
        self.assertIn("stock_value_krw", self.summary_js)
        self.assertIn("market_value_krw", self.summary_js)
        self.assertIn("cash_krw", self.summary_js)
        self.assertIn("cash_usd", self.summary_js)

    def test_bank_summary_separates_real_accounts_from_loan_agreements(self) -> None:
        for marker in ("총 은행계좌", "자유입출금", "예·적금", "대출·한도약정", "현재 부채"):
            self.assertIn(marker, self.summary_js)
        self.assertIn("const bankAccounts = [...banks, ...savings]", self.summary_js)
        self.assertIn("bankAccounts.length", self.summary_js)
        self.assertIn("loans.length", self.summary_js)
        self.assertNotIn("const allItems = [...banks, ...savings, ...loans]", self.summary_js)

    def test_bank_summary_uses_actual_debt_not_agreement_count_as_debt(self) -> None:
        self.assertIn("current_balance", self.summary_js)
        self.assertIn("const currentDebt = loanDebt + legacyMinusDebt", self.summary_js)
        self.assertIn("balance < 0 ? Math.abs(balance) : 0", self.summary_js)
        self.assertIn("moneyKrw(currentDebt)", self.summary_js)

    def test_summary_follows_family_owner_filter_and_shows_breakdown_for_all(self) -> None:
        self.assertIn(".family-tab.active[data-owner]", self.summary_js)
        self.assertIn("filterOwner", self.summary_js)
        self.assertIn("owner === '모두' ? ownerBreakdown", self.summary_js)
        self.assertIn("소유자별 계좌", self.summary_js)
        self.assertIn("ownerBreakdown(bankAccounts)", self.summary_js)

    def test_summary_refresh_uses_complete_dashboard_for_bank_composition(self) -> None:
        self.assertIn("/api/accounts?group=All&owner=모두", self.summary_js)
        self.assertIn("/api/dashboard", self.summary_js)
        self.assertNotIn("jsonFetch('/api/savings')", self.summary_js)
        self.assertIn("renderBankSummary(dashboardPayload || {}, owner)", self.summary_js)
        self.assertIn("credentials: 'same-origin'", self.summary_js)

    def test_summary_observers_are_scoped_to_existing_render_hosts(self) -> None:
        self.assertIn("document.getElementById('accountList')", self.summary_js)
        self.assertIn("document.getElementById('savingsSummaryCards')", self.summary_js)
        self.assertNotIn("observer.observe(document.body", self.summary_js)
        self.assertIn("host.innerHTML === markup", self.summary_js)

    def test_pdf_reported_balance_is_not_reused_as_broker_cash(self) -> None:
        self.assertNotIn("reported_balance_krw", self.summary_js)
        self.assertIn("주식자산 + 예수금", self.summary_js)
        self.assertIn("$${", self.summary_js)


if __name__ == "__main__":
    unittest.main()
