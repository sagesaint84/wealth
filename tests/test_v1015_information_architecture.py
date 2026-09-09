from pathlib import Path
import unittest


class WealthV1015InformationArchitectureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.layout = (root / "app/static/wealth-layout.js").read_text(encoding="utf-8")
        cls.js = (root / "app/static/wealth.js").read_text(encoding="utf-8")
        cls.planning = (root / "app/static/wealth-planning.js").read_text(encoding="utf-8")
        cls.css = (root / "app/static/wealth-layout.css").read_text(encoding="utf-8")
        cls.html = (root / "app/static/index.html").read_text(encoding="utf-8")

    def test_stock_page_is_named_stock_status_and_toggle_removed(self):
        self.assertIn("invest: ['투자', '주식 현황'", self.layout)
        self.assertNotIn('id="allocTabs"', self.html)
        self.assertIn("const STOCK_PORTFOLIO_MODE = 'sector'", self.js)
        self.assertNotIn("currentAllocTab", self.js)

    def test_home_asset_portfolio_is_page_local_and_rich(self):
        self.assertIn('id="homeAssetPortfolioPanel"', self.layout)
        home_start = self.layout.index('<section data-wealth-page="home"')
        home_end = self.layout.index('${Object.keys(views)', home_start)
        home = self.layout[home_start:home_end]
        self.assertLess(home.index('class="wealth-home-grid"'), home.index('id="homeAssetPortfolioPanel"'))
        self.assertLess(home.index('id="homeAssetPortfolioPanel"'), home.index('class="wealth-home-secondary"'))
        self.assertIn("home.querySelector('.wealth-home-secondary').before(historyPanel)", self.planning)
        for metric in ("wealthAssetNetWorth", "wealthAssetInvest", "wealthAssetExpected", "wealthAssetRealized", "wealthAssetSafe"):
            self.assertIn(metric, self.layout)
        for detail in (
            "wealthAssetDebtDetail", "wealthAssetInvestDetail", "wealthAssetExpectedRate",
            "wealthAssetDayDetail", "wealthAssetRealizedDetail", "wealthAssetRealizedPeriod",
            "wealthAssetSafeDetail", "wealthAssetSafeBreakdown",
        ):
            self.assertIn(detail, self.layout)
        self.assertIn('id="homeAssetAllocationDonut"', self.layout)
        self.assertIn('id="homeAssetAllocationLegend"', self.layout)
        self.assertIn("wealth-asset-dashboard", self.css)

    def test_summary_detail_links_home_asset_and_assets_page(self):
        self.assertIn('id="wealthNetWorthDetails"', self.layout)
        self.assertIn('href="#homeAssetPortfolioPanel"', self.layout)
        self.assertIn("event.preventDefault();", self.layout)
        self.assertIn("target.scrollIntoView({ behavior: 'smooth', block: 'start' });", self.layout)
        self.assertIn("target.focus({ preventScroll: true });", self.layout)
        self.assertNotIn("showPage('invest')", self.layout)
        self.assertIn('href="#assets">자산 상세보기', self.layout)

    def test_summary_event_reuses_existing_metrics(self):
        for field in (
            "invest: totalInvestAssets", "expected: totalExpectedProfit",
            "expectedRate: combinedReturnRate", "realized: combinedRealizedKrw",
            "safe: totalSafeAssets", "realizedTrade: totalRealizedKrw",
            "dividendInterest: totalActualDivKrw", "classifications: data.classifications",
        ):
            self.assertIn(field, self.js)

    def test_home_allocation_keeps_legacy_asset_details(self):
        for label in (
            "부동산 순에퀴티", "은행 예수금 포함", "예상 수령액/해약환급금",
            "holding_count", "return_rate", "market_value_krw",
        ):
            self.assertIn(label, self.layout)
        self.assertNotIn('id="wealthMix"', self.layout)

    def test_home_detail_projection_does_not_change_stock_mode(self):
        self.assertIn("const STOCK_PORTFOLIO_MODE = 'sector'", self.js)
        self.assertNotIn("currentAllocTab", self.js)
        self.assertIn("if (STOCK_PORTFOLIO_MODE === 'sector')", self.js)

    def test_stock_navigation_remains_six_tabs(self):
        for label in ("포트폴리오", "히트맵", "주식기록", "전략 버킷", "절세계좌", "보유종목"):
            self.assertIn(label, self.planning)


if __name__ == "__main__":
    unittest.main()
