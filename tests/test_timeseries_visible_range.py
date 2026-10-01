from pathlib import Path
import unittest


class TimeseriesVisibleRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "app/static/wealth-timeseries-visible-range.js").read_text(encoding="utf-8")

    def test_visible_window_drives_scale(self):
        self.assertIn("function visibleBounds(viewport, count)", self.js)
        self.assertIn("const visible = buckets.slice(bounds.start, bounds.end + 1)", self.js)
        self.assertIn("paddedRange(visible.map(bucket => bucket.close), false)", self.js)
        self.assertIn("visibleValues.push(finite(bucket.values?.[key]))", self.js)

    def test_state_charts_split_asset_and_change_axes(self):
        self.assertIn("wealth-unified-axis-right", self.js)
        self.assertIn("kind === 'stock' ? '총자산' : '순자산'", self.js)
        self.assertIn("kind === 'stock' ? '기간 손익' : '기간 변화'", self.js)
        self.assertIn("previousViewportWidth", self.js)
        self.assertIn("content.style.width", self.js)

    def test_daily_labels_are_thinned_by_visible_pixel_spacing(self):
        self.assertIn("function thinXAxisLabels", self.js)
        self.assertIn("Math.ceil(minimum / Math.max(slotPx, 1))", self.js)
        self.assertIn("label.style.visibility", self.js)

    def test_scroll_zoom_and_resize_recompute_visible_scale(self):
        self.assertIn("viewport.addEventListener('scroll', queue", self.js)
        self.assertIn("new ResizeObserver(queue)", self.js)
        self.assertIn("observer.observe(content)", self.js)

    def test_all_five_chart_kinds_are_captured(self):
        for marker in (
            "'stock'",
            "'networth'",
            "'pnl'",
            "'dividend'",
            "'ledger'",
        ):
            self.assertIn(marker, self.js)

    def test_legacy_six_month_ledger_eyebrow_is_removed(self):
        self.assertIn("function hideLegacyLedgerEyebrow", self.js)
        self.assertIn("eyebrow?.remove()", self.js)


if __name__ == "__main__":
    unittest.main()
