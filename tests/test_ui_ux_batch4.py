from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"
WEALTH_LAYOUT_JS = ROOT / "app" / "static" / "wealth-layout.js"
WEALTH_PLANNING_JS = ROOT / "app" / "static" / "wealth-planning.js"
WEALTH_LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"


class WealthBatch4PolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wealth_js = WEALTH_JS.read_text(encoding="utf-8")
        cls.layout_js = WEALTH_LAYOUT_JS.read_text(encoding="utf-8")
        cls.planning_js = WEALTH_PLANNING_JS.read_text(encoding="utf-8")
        cls.layout_css = WEALTH_LAYOUT_CSS.read_text(encoding="utf-8")

    # ── 1. Strategy Bucket Preset Names ───────────────────────────────────────
    def test_strategy_bucket_presets_are_exact_eight_names(self) -> None:
        expected_names = ["코어", "성장", "배당", "섹터", "테마", "전술", "방어", "현금"]
        for name in expected_names:
            self.assertIn(f"['{name}',", self.planning_js)
        # Ensure deprecated compound preset names are not in BUCKET_PRESETS
        presets_start = self.planning_js.index("const BUCKET_PRESETS = [")
        presets_end = self.planning_js.index("];", presets_start)
        presets_block = self.planning_js[presets_start:presets_end]
        self.assertNotIn("배당·인컴", presets_block)
        self.assertNotIn("방어·안전자산", presets_block)
        self.assertNotIn("현금·대기자금", presets_block)

    # ── 2. Redundant Home Quick Access Removal ────────────────────────────────
    def test_home_quick_access_is_removed(self) -> None:
        self.assertNotIn("wealth-shortcuts", self.layout_js)
        self.assertNotIn("wealth-home-secondary", self.layout_js)
        self.assertNotIn("QUICK ACCESS", self.layout_js)
        self.assertNotIn("오늘의 자산 관리", self.layout_js)
        # historyPanel attaches cleanly without referencing wealth-home-secondary
        self.assertNotIn("wealth-home-secondary", self.planning_js)
        self.assertIn("(home.querySelector('#wealthMarketSlot') || home).before(historyPanel)", self.planning_js)

    # ── 3. Net Worth History Chart Responsiveness ──────────────────────────────
    def test_net_worth_history_uses_responsive_width_and_adaptive_padding(self) -> None:
        self.assertIn("containerWidth = plot.clientWidth || 800", self.planning_js)
        self.assertIn("width = containerWidth", self.planning_js)
        self.assertNotIn("records.length * minSpacing", self.planning_js)
        self.assertIn("pad = Math.max(48, Math.min(64, Math.round(width * 0.06)))", self.planning_js)
        self.assertIn("left = pad, right = width - pad", self.planning_js)
        # Old hardcoded 150px spacing and fixed 92px padding are removed
        self.assertNotIn("records.length*150", self.planning_js)
        self.assertNotIn("left=92, right=width-92", self.planning_js)

    # ── 4. P0: Per-Account Cumulative Tax-Saving Display Regression Fix ───────
    def run_tax_helpers(self, accounts: list[dict]) -> dict:
        if not shutil.which("node"):
            self.skipTest("node runtime is not available")
        script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const deductibleStart = source.indexOf('function isAccountTaxDeductible');
const deductibleEnd = source.indexOf('\nfunction isTaxAdvantagedAccount', deductibleStart);
const advantagedStart = deductibleEnd + 1;
const advantagedEnd = source.indexOf('\n// ── 4.', advantagedStart);
const categoryStart = source.indexOf('function getTaxCategory');
const categoryEnd = source.indexOf('\nfunction renderTaxAccountHoldings', categoryStart);
const sandbox = {};
vm.runInNewContext(
  source.slice(deductibleStart, deductibleEnd) + '\n' +
  source.slice(advantagedStart, advantagedEnd) + '\n' +
  source.slice(categoryStart, categoryEnd) +
  '\nthis.calculateOwnerYearPensionTaxBenefits = calculateOwnerYearPensionTaxBenefits;' +
  '\nthis.calcAccountCumulativeTaxSaved = calcAccountCumulativeTaxSaved;',
  sandbox
);
const input = JSON.parse(process.argv[2]);
const out = {
  ownerBenefits: sandbox.calculateOwnerYearPensionTaxBenefits(input.accounts),
  perAccount: input.accounts.map(a => ({
    id: a.id,
    allocatedSaved: sandbox.calculateOwnerYearPensionTaxBenefits(input.accounts).cumulative.byAccount[String(a.id || '')]?.taxSaved || 0,
    ownerAggregateSaved: sandbox.calcAccountCumulativeTaxSaved(a, input.accounts),
  })),
};
process.stdout.write(JSON.stringify(out));
"""
        res = subprocess.run(
            ["node", "-e", script, str(WEALTH_JS), json.dumps({"accounts": accounts})],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(res.stdout)

    def test_account_cards_use_authoritative_owner_allocation_under_combined_cap(self) -> None:
        """Account allocations must reconcile to the capped owner total."""
        accounts = [
            {
                "id": "pension-1",
                "name": "연금저축A",
                "owner": "홍길동",
                "account_type": "pension_savings",
                "tax_deductible": True,
                "income_level": "low",
                "annual_deposit": 6_000_000,
            },
            {
                "id": "irp-1",
                "name": "IRP B",
                "owner": "홍길동",
                "account_type": "irp",
                "tax_deductible": True,
                "income_level": "low",
                "annual_deposit": 9_000_000,
            },
        ]
        res = self.run_tax_helpers(accounts)
        per_acct = {item["id"]: item for item in res["perAccount"]}

        self.assertEqual(per_acct["pension-1"]["allocatedSaved"], 990_000)
        self.assertEqual(per_acct["irp-1"]["allocatedSaved"], 495_000)
        self.assertEqual(
            sum(item["allocatedSaved"] for item in per_acct.values()),
            res["ownerBenefits"]["cumulative"]["byOwner"]["홍길동"]["taxSaved"],
        )
        self.assertNotIn("function calcSingleAccountCumulativeTaxSaved", self.wealth_js)
        self.assertIn("accountTaxBenefits.cumulative.byAccount[accountKey]?.taxSaved", self.wealth_js)

    def test_non_deductible_account_shows_zero_cumulative_tax_savings(self) -> None:
        """P0 Regression Test: Non-deductible accounts must show 0 and not fabricate tax savings."""
        accounts = [
            {
                "id": "pension-deductible",
                "name": "연금저축 공제",
                "owner": "홍길동",
                "account_type": "pension_savings",
                "tax_deductible": True,
                "income_level": "low",
                "annual_deposit": 6_000_000,
            },
            {
                "id": "pension-non-deductible",
                "name": "연금저축 비공제",
                "owner": "홍길동",
                "account_type": "pension_savings_non_deductible",
                "tax_deductible": False,
                "income_level": "low",
                "annual_deposit": 10_000_000,
            },
        ]
        res = self.run_tax_helpers(accounts)
        per_acct = {item["id"]: item for item in res["perAccount"]}

        self.assertEqual(per_acct["pension-deductible"]["allocatedSaved"], 990_000)
        self.assertEqual(per_acct["pension-non-deductible"]["allocatedSaved"], 0)

        # In renderAccounts, non-deductible accounts must not render cumSaved
        render_start = self.wealth_js.index("function renderAccounts(items)")
        render_end = self.wealth_js.index("function renderSavings", render_start)
        render_body = self.wealth_js[render_start:render_end]
        self.assertIn("🌿 비공제 계좌", render_body)
        # The non-deductible branch must not contain cumSaved
        nonded_start = render_body.index("if (!isTaxDeductible) {")
        nonded_end = render_body.index("} else {", nonded_start)
        nonded_branch = render_body[nonded_start:nonded_end]
        self.assertNotIn("cumSaved", nonded_branch)

    # ── 5. Standardized Major Page-Header Styling ─────────────────────────────
    def test_comprehensive_assets_page_header_displays_eyebrow(self) -> None:
        # Verify wealth-eyebrow is NOT suppressed in CSS for assets view
        self.assertNotIn(
            '.wealth-workspace[data-active-view="assets"] .wealth-page-head .wealth-eyebrow { display: none; }',
            self.layout_css,
        )
        # Verify the global page head contains the standard eyebrow
        self.assertIn('<p class="wealth-eyebrow">YOUR FINANCIAL OVERVIEW</p>', self.layout_js)
        self.assertIn('<h2 id="wealthPageTitle"', self.layout_js)
        self.assertIn('<p id="wealthPageDescription"', self.layout_js)

    # ── 6. Standardized Secondary Tab Navigation ──────────────────────────────
    def test_secondary_tab_navigation_styling_is_standardized(self) -> None:
        # .wealth-section-tabs matches .wealth-invest-tabs flex layout and spacing
        self.assertIn(".wealth-layout .wealth-section-tabs { display: flex; flex-wrap: nowrap; width: 100%;", self.layout_css)
        self.assertIn(".wealth-layout .wealth-section-tabs > button { flex: 1 1 0;", self.layout_css)
        self.assertIn("min-height: 38px;", self.layout_css)
        self.assertIn("padding: 9px 13px;", self.layout_css)
        self.assertIn(".wealth-layout .income-tabs { margin: 0 0 18px; }", self.layout_css)
        self.assertIn(".wealth-layout .account-category-tabs { margin: 0 0 18px !important;", self.layout_css)

    # ── 7. Small Semantic Icons/Emojis in Secondary Tabs ──────────────────────
    def test_stock_investment_and_money_log_tabs_have_semantic_icons(self) -> None:
        # Stock Investment tabs
        stock_tabs = ["📊 포트폴리오", "🗺️ 히트맵", "🗓️ 주식기록", "🎯 전략 버킷", "🧾 절세계좌", "📋 보유종목"]
        for tab in stock_tabs:
            self.assertIn(tab, self.planning_js)

        # Money Log tabs
        income_tabs = ["📈 실현손익", "💰 배당·이자", "🧾 가계부"]
        for tab in income_tabs:
            self.assertIn(tab, self.layout_js)

        # Comprehensive Assets tabs (already present)
        asset_tabs = ["📈 증권", "🏦 은행", "🛡️ 보험", "🏠 부동산"]
        for tab in asset_tabs:
            self.assertIn(tab, self.layout_js)


if __name__ == "__main__":
    unittest.main()
