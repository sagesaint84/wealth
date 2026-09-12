from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"
PLANNING_JS = ROOT / "app" / "static" / "wealth-planning.js"


class InvestmentFilterPeriodTests(unittest.TestCase):
    def test_investment_screen_retains_5_day_weekly_semantics(self):
        source = WEALTH_JS.read_text(encoding="utf-8")
        start = source.index("function filterRecordsByPeriod(records, period) {")
        end = source.index("function renderMarkets(", start)
        fn_code = source[start:end]

        self.assertIn("if (period === '1W') {", fn_code)
        self.assertIn("return sorted.slice(-5);", fn_code)
        self.assertNotIn("diffDays <= 7", fn_code)
        self.assertNotIn("anchorMs", fn_code)

    def test_home_weekly_filter_remains_in_planning_script(self):
        source = PLANNING_JS.read_text(encoding="utf-8")
        self.assertIn("function filterHistoryPeriod(records, period) {", source)
        self.assertIn("diffDays >= 0 && diffDays <= 7", source)


if __name__ == "__main__":
    unittest.main()
