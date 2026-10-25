from pathlib import Path
import unittest


class HomeDashboardBatch2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.html = (root / "app/static/index.html").read_text(encoding="utf-8")
        cls.layout = (root / "app/static/wealth-layout.js").read_text(encoding="utf-8")
        cls.css = (root / "app/static/wealth-layout.css").read_text(encoding="utf-8")
        cls.main = (root / "app/static/wealth.js").read_text(encoding="utf-8")
        cls.planning = (root / "app/static/wealth-planning.js").read_text(encoding="utf-8")

    def test_debt_is_a_secondary_existing_value_with_non_profit_color(self):
        self.assertIn("wealthAssetDebtDetail", self.layout)
        self.assertIn('class="wealth-asset-secondary-row is-debt"', self.html)
        self.assertIn(".wealth-asset-secondary-row.is-debt", self.css)
        self.assertIn("#d6a85f", self.css)
        self.assertIn(".wealth-asset-secondary-row.is-debt em, .wealth-asset-secondary-row.is-debt small", self.css)

    def test_expected_return_uses_existing_property_and_stock_domain_values(self):
        self.assertIn('<em>부동산 기대수익</em><small id="wealthAssetPropertyExpected">', self.html)
        self.assertIn('<em>주식 기대수익</em><small id="wealthAssetStockExpected">', self.html)
        self.assertIn("propertyExpected: totalREProfit", self.main)
        self.assertIn("stockExpected: Number(s.profit_krw) || 0", self.main)
        self.assertIn("propertyExpectedRate: realEstateReturnRate", self.main)
        self.assertIn("stockExpectedRate: Number(s.return_rate) || 0", self.main)
        self.assertIn("totalExpectedProfit = (Number(s.profit_krw) || 0) + totalREProfit", self.main)

    def test_real_estate_allocation_wording_and_return_are_distinct(self):
        # Classification is current_price × ownership, before debt deduction.
        # Net worth is a separate summary value, not this row's amount.
        self.assertIn("부동산 평가액 · 비중", self.layout)
        self.assertNotIn("부동산 순자산 ·", self.layout)
        self.assertNotIn("부동산 순에퀴티 ·", self.layout)
        self.assertIn("window.WealthAssetReturnDisplay(item, {", self.layout)
        self.assertIn("rate: s.propertyExpectedRate, profit: s.propertyExpected, cost: s.propertyPurchaseValue", self.layout)
        self.assertIn("rate: item.return_rate, profit: item.profit_krw, cost: item.cost_value_krw", self.layout)
        self.assertIn("metric.textContent = returnRate === null ? '—' : pct(returnRate)", self.layout)
        self.assertIn("propertyExpected: totalREProfit, propertyExpectedRate: realEstateReturnRate", self.main)
        self.assertIn("propertyPurchaseValue: totalREPurchaseVal", self.main)
        self.assertIn("const netWorth = (totalInvestAssets + totalSafeAssets) - totalAllDebt", self.main)

    def test_history_removes_summary_cards_and_uses_desktop_chart_list_split(self):
        for label in ("기간 시작", "최근 기록", "최저 / 최고", "기간 증감"):
            self.assertNotIn(label, self.planning)
        self.assertIn('class="wealth-history-main"', self.planning)
        self.assertIn("grid-template-columns:minmax(0,2fr) minmax(280px,1fr)", self.css)
        self.assertIn("@media (max-width: 980px)", self.css)
        self.assertIn(".wealth-history-main { grid-template-columns:1fr; }", self.css)

    def test_every_filtered_record_gets_point_amount_and_date_labels(self):
        self.assertIn("const pointLabels=points.map((p,i)=>", self.planning)
        self.assertIn("${won(records[i].net_worth)}", self.planning)
        self.assertIn("${esc(records[i].date)}", self.planning)
        self.assertIn('class="wealth-history-point"', self.planning)
        self.assertIn("left = pad, right = width - pad", self.planning)
        self.assertIn("const width = containerWidth;", self.planning)

    def test_compact_record_cards_preserve_all_fields_and_actions(self):
        for field in ("총자산", "총부채", "구분 ·", "메모 ·"):
            self.assertIn(field, self.planning)
        self.assertIn("${won(r.net_worth)}", self.planning)
        self.assertIn("data-history-edit", self.planning)
        self.assertIn("data-history-delete", self.planning)
        self.assertIn("data-history-action=\"wealthSaveSnapshot\"", self.planning)
        self.assertIn("data-history-action=\"wealthAddHistory\"", self.planning)
        for selector in (
            "#wealthHistoryPlot",
            ".wealth-history-record-list",
            ".wealth-history-record-head",
            ".wealth-history-record-note",
            ".wealth-history-record-actions",
        ):
            self.assertIn(selector, self.css)
        self.assertIn("overflow:hidden", self.css)
        self.assertIn("overflow-y:auto", self.css)
        self.assertNotIn(".wealth-history-details table", self.css)

    def test_period_and_owner_record_semantics_remain_intact(self):
        for period in ("1D", "1W", "1M", "1Y", "ALL"):
            self.assertIn(f'data-period="{period}"', self.planning)
        self.assertIn("state.history.filter(r=>r.owner===summary.owner)", self.planning)
        self.assertIn("const records=filterHistoryPeriod(allRecords,range)", self.planning)
        self.assertIn("net_worth:assets-debt", self.planning)


if __name__ == "__main__":
    unittest.main()
