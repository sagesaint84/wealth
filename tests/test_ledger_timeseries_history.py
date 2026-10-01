from pathlib import Path
import unittest


class LedgerTimeseriesHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "app/static/wealth-ledger-timeseries-history.js").read_text(encoding="utf-8")
        cls.loader = (root / "app/static/wealth-planning-model.js").read_text(encoding="utf-8")

    def test_expansion_is_triggered_only_at_loaded_widest_range(self):
        self.assertIn("atWidestLoadedRange(viewport)", self.js)
        self.assertIn("event.deltaY <= 0", self.js)
        self.assertIn("event.preventDefault();", self.js)
        self.assertIn("event.stopPropagation();", self.js)

    def test_history_expands_in_older_six_month_chunks_without_period_cap(self):
        self.assertIn("shiftMonth(Number(first.year), Number(first.month), -1)", self.js)
        self.assertIn("response.monthly_trend", self.js)
        self.assertIn("mergeTrend(older, oldTrend)", self.js)
        self.assertNotIn("maxMonths", self.js)
        self.assertNotIn("MAX_MONTHS", self.js)

    def test_expanded_trend_is_stored_and_rerendered(self):
        self.assertIn("rawLedgerData = { ...data, monthly_trend: merged };", self.js)
        self.assertIn("renderLedgerTrend(merged);", self.js)
        self.assertIn("updateTrendHeader(merged);", self.js)

    def test_zoom_continues_from_previous_visible_range_after_fetch(self):
        self.assertIn("previousCount * ZOOM_STEP", self.js)
        self.assertIn("viewportScale(viewport, chart)", self.js)
        self.assertIn("new WheelEvent('wheel'", self.js)
        self.assertIn("if (!event.isTrusted", self.js)

    def test_annual_current_year_month_links_are_preserved(self):
        self.assertIn("restoreAnnualMonthLinks", self.js)
        self.assertIn("Number(row.year) === selectedYear", self.js)
        self.assertIn("col.dataset.ledgerMonth = String(row.month)", self.js)

    def test_header_reports_actual_loaded_history_range(self):
        self.assertIn("${trend.length}-MONTH CASHFLOW TREND", self.js)
        self.assertIn("${first.year}년 ${first.month}월", self.js)
        self.assertIn("${last.year}년 ${last.month}월", self.js)

    def test_loader_adds_history_extension_after_shared_panzoom(self):
        panzoom = self.loader.index("/static/wealth-timeseries-panzoom.js?v=10.6j2")
        history = self.loader.index("/static/wealth-ledger-timeseries-history.js?v=10.6j3")
        self.assertLess(panzoom, history)
        self.assertIn("data-wealth-ledger-timeseries-history", self.loader)


if __name__ == "__main__":
    unittest.main()
