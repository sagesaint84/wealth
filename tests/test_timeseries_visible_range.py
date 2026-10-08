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

    def test_state_charts_split_asset_and_change_axes_without_titles(self):
        self.assertIn("wealth-unified-axis-right", self.js)
        self.assertIn("leftAxis.innerHTML = axisHtml(lineRange", self.js)
        self.assertIn("rightAxis.innerHTML = axisHtml(changeRange", self.js)
        self.assertNotIn("const leftCaption", self.js)
        self.assertNotIn("const rightCaption", self.js)

    def test_state_axis_middle_ticks_stay_centered(self):
        self.assertIn(".wealth-unified-chart-shell.wealth-visible-state .wealth-unified-axis-label {", self.js)
        self.assertIn("transform: none;", self.js)
        self.assertIn(".wealth-unified-axis-label:first-child", self.js)
        self.assertIn(".wealth-unified-axis-label:last-child", self.js)

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

    def test_legacy_six_month_ledger_eyebrow_has_no_producer_or_remover(self):
        self.assertNotIn("hideLegacyLedgerEyebrow", self.js)
        self.assertNotIn("eyebrow?.remove()", self.js)
        html = (Path(__file__).resolve().parents[1] / 'app/static/index.html').read_text(encoding='utf-8')
        self.assertNotIn('6-MONTH CASHFLOW TREND', html)


if __name__ == "__main__":
    unittest.main()
