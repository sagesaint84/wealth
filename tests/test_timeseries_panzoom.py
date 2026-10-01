from pathlib import Path
import unittest


class TimeseriesPanzoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "app/static/wealth-timeseries-panzoom.js").read_text(encoding="utf-8")
        cls.loader = (root / "app/static/wealth-planning-model.js").read_text(encoding="utf-8")

    def test_shared_helper_targets_ledger_stock_and_net_worth(self):
        for selector in (
            "#ledgerTrendContainer",
            "#recordsPanel",
            "#wealthHistoryPlot",
            ".ledger-trend-chart",
            "svg.record-chart",
            "svg.wealth-history-chart",
        ):
            self.assertIn(selector, self.js)

    def test_plain_wheel_zooms_without_ctrl_modifier(self):
        self.assertIn("addEventListener('wheel'", self.js)
        self.assertIn("event.deltaY < 0 ? ZOOM_STEP", self.js)
        self.assertNotIn("event.ctrlKey", self.js)
        self.assertNotIn("event.metaKey", self.js)

    def test_wheel_is_only_consumed_when_zoom_changes(self):
        self.assertIn("const changed = setScale", self.js)
        self.assertIn("if (changed) event.preventDefault();", self.js)
        self.assertIn("return false;", self.js)

    def test_horizontal_pan_and_visible_scrollbar_are_enabled(self):
        self.assertIn("overflow-x: auto", self.js)
        self.assertIn("scrollbar-width: thin", self.js)
        self.assertIn("startScrollLeft - delta", self.js)
        self.assertIn("cursor: grab", self.js)

    def test_mobile_pinch_and_native_single_finger_pan_are_supported(self):
        self.assertIn("touch-action: pan-x pan-y", self.js)
        self.assertIn("event.touches.length !== 2", self.js)
        self.assertIn("distance / pinchStartDistance", self.js)
        self.assertIn("touchCenterX(event.touches)", self.js)

    def test_zoom_anchors_to_pointer_and_initial_view_shows_latest_records(self):
        self.assertIn("anchorClientX - rect.left", self.js)
        self.assertIn("logicalRatio * newWidth - anchorX", self.js)
        self.assertIn("scrollWidth - state.viewport.clientWidth", self.js)

    def test_dynamic_rerenders_are_reenhanced(self):
        self.assertIn("new MutationObserver(queueScan)", self.js)
        self.assertIn("wealthPanzoomEnhanced", self.js)

    def test_loader_is_browser_only_and_versioned(self):
        self.assertIn("typeof document !== 'undefined'", self.loader)
        self.assertIn("/static/wealth-timeseries-panzoom.js?v=10.6j1", self.loader)
        self.assertIn("data-wealth-timeseries-panzoom", self.loader)


if __name__ == "__main__":
    unittest.main()
