from pathlib import Path
import unittest


class DividendSummaryFallbackTests(unittest.TestCase):
    def test_expected_summary_uses_detailed_schedule_fallback(self):
        source = (Path(__file__).resolve().parents[1] / "app/static/wealth.js").read_text(encoding="utf-8")
        self.assertIn("const scheduleTotal = schedule.reduce", source)
        self.assertIn("data.total_annual_dividend_krw ?? scheduleTotal", source)
        self.assertIn("data.monthly_avg_dividend_krw ?? (totalAnnual / 12)", source)
        self.assertIn("holding_dividends || []).filter", source)

    def test_valid_zero_summary_is_not_unconditionally_replaced(self):
        source = (Path(__file__).resolve().parents[1] / "app/static/wealth.js").read_text(encoding="utf-8")
        self.assertNotIn("Number(data.total_annual_dividend_krw || scheduleTotal)", source)


if __name__ == "__main__":
    unittest.main()
