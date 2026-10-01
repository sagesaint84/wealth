from pathlib import Path
import unittest


class TimeseriesLabelLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "app/static/wealth-timeseries-label-layout.js").read_text(encoding="utf-8")

    def test_svg_x_labels_are_replaced_by_non_scaled_html_labels(self):
        self.assertIn('svg text[y="262"]', self.js)
        self.assertIn('wealth-timeseries-html-xaxis', self.js)
        self.assertIn('wealth-timeseries-html-xlabel', self.js)
        self.assertIn('bucketCenterPx', self.js)

    def test_dense_x_labels_are_thinned_by_pixel_spacing(self):
        self.assertIn('function minimumSpacing(mode)', self.js)
        self.assertIn('Math.ceil(minimumSpacing(mode) / Math.max(slot, 1))', self.js)
        self.assertIn('gap >= minimumSpacing(mode) * 0.72', self.js)

    def test_state_axis_columns_stay_wide_enough_without_caption_space(self):
        self.assertIn('grid-template-columns: 82px minmax(0, 1fr) 82px', self.js)
        self.assertIn('width: 82px !important', self.js)
        self.assertNotIn('wealth-unified-axis-caption', self.js)

    def test_year_boundaries_render_independently_from_thinned_date_labels(self):
        self.assertIn('const yearIndices = new Set([bounds.start])', self.js)
        self.assertIn('if (buckets[index]?.yearMarker) yearIndices.add(index)', self.js)
        self.assertIn('appendYearMarker(overlay, width, buckets, index)', self.js)
        self.assertIn('year.textContent = `${bucket.year}년`', self.js)

    def test_labels_refresh_on_scroll_zoom_and_resize(self):
        self.assertIn("viewport.addEventListener('scroll', queue", self.js)
        self.assertIn("viewport.addEventListener('wheel'", self.js)
        self.assertIn('new ResizeObserver(queue)', self.js)
        self.assertIn('observer.observe(content)', self.js)

    def test_all_five_chart_kinds_are_captured(self):
        for marker in (
            "'stock'",
            "'networth'",
            "'pnl'",
            "'dividend'",
            "'ledger'",
        ):
            self.assertIn(marker, self.js)


if __name__ == "__main__":
    unittest.main()
