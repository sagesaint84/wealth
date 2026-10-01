from pathlib import Path
import unittest


class UnifiedTimeseriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "app/static/wealth-timeseries-unified.js").read_text(encoding="utf-8")
        cls.loader = (root / "app/static/wealth-planning-model.js").read_text(encoding="utf-8")

    def test_all_five_requested_chart_hosts_are_supported(self):
        for marker in (
            "assetChart",
            "wealthHistoryPlot",
            "pnlBarChartWrap",
            "dividendBarChartWrap",
            "ledgerTrendContainer",
        ):
            self.assertIn(marker, self.js)

    def test_all_five_period_buttons_share_one_mode_set(self):
        self.assertIn("MODES.DAY, MODES.WEEK, MODES.MONTH, MODES.YEAR, MODES.ALL", self.js)
        for label in ("'일간'", "'주간'", "'월간'", "'연간'", "'전체'"):
            self.assertIn(label, self.js)

    def test_stock_uses_period_close_and_price_change_profit(self):
        self.assertIn("valueField: 'total_value_krw'", self.js)
        self.assertIn("changeField: 'day_profit_krw'", self.js)
        self.assertIn("가격변동", self.js)

    def test_net_worth_uses_bucket_close_to_close_change(self):
        self.assertIn("valueField: 'net_worth'", self.js)
        self.assertIn("순자산 변화", self.js)

    def test_realized_pnl_dividend_interest_and_ledger_are_flow_buckets(self):
        self.assertIn("fields: ['pnl_value']", self.js)
        self.assertIn("fields: ['dividend_value', 'interest_value']", self.js)
        self.assertIn("fields: ['income_value', 'expense_value']", self.js)
        self.assertIn("year=all&trade_type=", self.js)
        self.assertIn("/api/actual-dividends?owner=", self.js)

    def test_ledger_daily_and_weekly_views_use_transaction_records(self):
        self.assertIn("modes.ledger === MODES.DAY || modes.ledger === MODES.WEEK", self.js)
        self.assertIn("cache.ledgerTransactions", self.js)
        self.assertIn("record?.type === 'income' || record?.type === 'expense'", self.js)

    def test_common_charts_have_fixed_amount_axis_scroll_and_panzoom(self):
        for marker in (
            "wealth-unified-axis",
            "overflow-x: auto",
            "addEventListener('wheel'",
            "event.touches.length !== 2",
            "startScrollLeft - (event.clientX - startX)",
            "compactWon",
        ):
            self.assertIn(marker, self.js)

    def test_scale_one_means_all_loaded_buckets_fit_viewport(self):
        self.assertIn("viewport.clientWidth) * state.scale", self.js)
        self.assertNotIn("state.bucketCount * bucketSlot", self.js)

    def test_year_markers_render_under_nonannual_period_labels(self):
        self.assertIn("if (mode === MODES.YEAR) return ''", self.js)
        self.assertIn("`${bucket.year}년`", self.js)
        self.assertIn("y=\"280\"", self.js)

    def test_monthly_pnl_and_dividend_drilldowns_remain_available(self):
        self.assertIn("renderPnlMonthlyDetail(month)", self.js)
        self.assertIn("renderActualDividendDetail(month)", self.js)

    def test_estimated_dividend_keeps_legacy_chart_without_misleading_period_controls(self):
        self.assertIn("if (dividendMode() !== 'actual')", self.js)
        self.assertIn("controls.hidden = true", self.js)

    def test_mutation_observer_does_not_rerender_its_own_owned_chart(self):
        self.assertIn("function hostNeedsUnified(hostId)", self.js)
        self.assertIn("wealth-unified-chart-shell", self.js)
        self.assertIn("if (hostNeedsUnified('assetChart'))", self.js)

    def test_ledger_can_continue_loading_older_history_at_zoom_boundary(self):
        self.assertIn("onNeedOlder: extendLedgerHistory", self.js)
        self.assertIn("shiftMonthKey(earliest, -1)", self.js)

    def test_loader_orders_period_core_visible_range_and_unified_adapter(self):
        self.assertIn("/static/wealth-timeseries-period-core.js?v=10.6k1", self.loader)
        self.assertIn("/static/wealth-timeseries-visible-range.js?v=10.6k2", self.loader)
        self.assertIn("/static/wealth-timeseries-unified.js?v=10.6k2", self.loader)
        self.assertIn("visibleRange.addEventListener('load', loadUnified", self.loader)
        self.assertIn("periodCore.addEventListener('load', loadUnifiedTimeseries", self.loader)


if __name__ == "__main__":
    unittest.main()
