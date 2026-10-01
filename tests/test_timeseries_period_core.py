from pathlib import Path
import unittest


class TimeseriesPeriodCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "app/static/wealth-timeseries-period-core.js").read_text(encoding="utf-8")

    def test_supports_day_week_month_year_and_all_modes(self):
        for marker in (
            "DAY: '1D'",
            "WEEK: '1W'",
            "MONTH: '1M'",
            "YEAR: '1Y'",
            "ALL: 'ALL'",
        ):
            self.assertIn(marker, self.js)

    def test_week_buckets_start_on_monday(self):
        self.assertIn("const offset = weekday === 0 ? -6 : 1 - weekday", self.js)
        self.assertIn("startOfWeek(date)", self.js)

    def test_bucket_keys_cover_each_requested_granularity(self):
        self.assertIn("if (mode === MODES.DAY) return isoDate(date)", self.js)
        self.assertIn("if (mode === MODES.WEEK) return isoDate(startOfWeek(date))", self.js)
        self.assertIn("if (mode === MODES.MONTH)", self.js)
        self.assertIn("if (mode === MODES.YEAR) return String(date.getUTCFullYear())", self.js)

    def test_all_mode_uses_span_aware_granularity(self):
        self.assertIn("if (spanDays <= 120) return MODES.DAY", self.js)
        self.assertIn("if (spanDays <= 730) return MODES.WEEK", self.js)
        self.assertIn("if (spanDays <= 3650) return MODES.MONTH", self.js)
        self.assertIn("return MODES.YEAR", self.js)

    def test_state_series_close_each_bucket_and_aggregate_period_change(self):
        self.assertIn("const last = bucket.items.at(-1)", self.js)
        self.assertIn("const close = finite(last?.[valueField])", self.js)
        self.assertIn("bucket.items.reduce((sum, item) => sum + finite(item?.[changeField]), 0)", self.js)
        self.assertIn("close - previousClose", self.js)

    def test_flow_series_sum_each_field_inside_bucket(self):
        self.assertIn("function aggregateFlow", self.js)
        self.assertIn("values[field] = bucket.items.reduce", self.js)

    def test_year_markers_are_emitted_at_year_boundaries(self):
        self.assertIn("yearMarker:", self.js)
        self.assertIn("bucketYear(key, resolved)", self.js)


if __name__ == "__main__":
    unittest.main()
