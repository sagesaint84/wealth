from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class IpoEventMonthsFrontendTests(unittest.TestCase):
    def test_event_month_extension_projects_month_local_sort_date(self):
        source = (ROOT / "app" / "static" / "wealth-ipo-event-months.js").read_text(encoding="utf-8")
        self.assertIn("presentation_month_sort_dates", source)
        self.assertIn("state.setMarketIpos?.(projectedForMonth(key))", source)
        self.assertIn("date.shiftIpoMonth(year, month, 1).key", source)
        self.assertIn("wrapper.addEventListener('click'", source)
        self.assertIn("}, true);", source)

    def test_event_month_extension_loads_before_compact_view(self):
        loader = (ROOT / "app" / "static" / "wealth-family-financial-income-allocation.js").read_text(encoding="utf-8")
        event_pos = loader.index("wealthIpoEventMonthsScript")
        compact_pos = loader.index("wealthIpoCompactViewScript")
        self.assertLess(event_pos, compact_pos)
        self.assertIn("wealth-ipo-event-months.js?v=10.6i1", loader)


if __name__ == "__main__":
    unittest.main()
