from pathlib import Path
import unittest


class NetWorthVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "app/static/wealth-planning.js").read_text(encoding="utf-8")
        cls.main_js = (root / "app/static/wealth.js").read_text(encoding="utf-8")
        cls.planning_js = (root / "app/static/wealth-planning.js").read_text(encoding="utf-8")

    def test_records_heading_changes_for_tax_scope(self):
        self.assertIn("recordsEyebrow.textContent = taxView ? 'TAX-ADVANTAGED ACCOUNTS' : 'STOCK RECORDS'", self.main_js)
        self.assertIn("recordsHeading.textContent = taxView ? '절세계좌' : '주식기록'", self.main_js)

    def test_net_worth_chart_uses_derived_previous_record_delta_bars(self):
        self.assertIn("const deltas=records.map((r,i)=>i ?", self.js)
        self.assertIn("전 기록 대비 변화", self.js)
        self.assertIn("class=\"wealth-history-bar ${deltas[i]>0?'is-positive':'is-negative'}\"", self.js)
        self.assertNotIn("daily_change", self.js)

    def test_net_worth_period_selector_matches_stock_record_periods(self):
        for period, label in (("1D", "일간"), ("1W", "주간"), ("1M", "월간"), ("1Y", "연간"), ("ALL", "전체")):
            self.assertIn(f'data-period="{period}">{label}', self.js)
        for legacy in ("1개월", "3개월", "1년"):
            self.assertNotIn(legacy, self.js)
        self.assertIn("compact-record-tabs", self.js)
        self.assertIn("filterHistoryPeriod", self.js)

    def test_weekly_history_uses_latest_record_calendar_window(self):
        self.assertIn("if (period === '1W') {", self.main_js)
        self.assertIn("return sorted.slice(-5);", self.main_js)
        self.assertNotIn("diffDays <= 7", self.main_js[:self.main_js.index("function renderMarkets(")])

    def test_home_weekly_history_uses_latest_record_calendar_window(self):
        self.assertIn("const anchor = String(valid.at(-1).date);", self.planning_js)
        self.assertIn("const diffDays = (anchorMs - ms) / 86400000;", self.planning_js)
        self.assertIn("diffDays >= 0 && diffDays <= 7", self.planning_js)
        self.assertNotIn("if (period === '1W') return records.slice(-5);", self.planning_js)

    def test_zero_record_history_uses_the_common_bottom_action_row(self):
        self.assertIn('id="wealthHistoryDetails" class="wealth-history-details"', self.planning_js)
        self.assertIn('function renderHistoryDetails(details, records)', self.planning_js)
        self.assertIn('if(!records.length) { summaryBox.replaceChildren(); plot.replaceChildren(); renderHistoryDetails(details, records); return; }', self.planning_js)
        self.assertNotIn('class="wealth-history-actions"', self.planning_js)
        self.assertNotIn('id="wealthAddHistory"', self.planning_js)

    def test_history_action_row_has_one_delegated_record_and_add_control_set(self):
        self.assertEqual(self.planning_js.count('data-history-action="wealthSaveSnapshot"'), 1)
        self.assertEqual(self.planning_js.count('data-history-action="wealthAddHistory"'), 1)
        self.assertIn('${records.length}개 <button type="button" class="button primary tiny"', self.planning_js)
        self.assertIn("if (actionButton.dataset.historyAction === 'wealthAddHistory') openHistory();", self.planning_js)


if __name__ == "__main__":
    unittest.main()
