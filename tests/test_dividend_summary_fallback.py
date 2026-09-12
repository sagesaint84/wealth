from pathlib import Path
import json
import shutil
import subprocess
import unittest


class DividendSummaryFallbackTests(unittest.TestCase):
    MISSING = object()

    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[1] / "app/static/wealth.js").read_text(encoding="utf-8")

    def normalized_schedule(self, value):
        if not shutil.which("node"):
            self.skipTest("node runtime is not available")
        start = self.source.index("function normalizeMonthlyDividendSchedule(")
        end = self.source.index("\nasync function loadDividends", start)
        helper = self.source[start:end]
        invocation = "normalizeMonthlyDividendSchedule()" if value is self.MISSING else "normalizeMonthlyDividendSchedule(JSON.parse(process.argv[1]))"
        script = f"{helper}\nconst result = {invocation};\nprocess.stdout.write(JSON.stringify(result));"
        command = ["node", "-e", script]
        if value is not self.MISSING:
            command.append(json.dumps(value))
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_expected_summary_uses_detailed_schedule_fallback(self):
        self.assertIn("const scheduleTotal = schedule.reduce", self.source)
        self.assertIn("data.total_annual_dividend_krw ?? scheduleTotal", self.source)
        self.assertIn("data.monthly_avg_dividend_krw ?? (totalAnnual / 12)", self.source)
        self.assertIn("holding_dividends || []).filter", self.source)

    def test_valid_zero_summary_is_not_unconditionally_replaced(self):
        self.assertNotIn("Number(data.total_annual_dividend_krw || scheduleTotal)", self.source)

    def test_normalize_monthly_dividend_schedule_static_contract(self):
        self.assertIn("function normalizeMonthlyDividendSchedule(monthlySchedule) {", self.source)
        self.assertIn("if (Array.isArray(monthlySchedule)) return monthlySchedule;", self.source)
        self.assertIn('if (!monthlySchedule || typeof monthlySchedule !== "object") return [];', self.source)
        self.assertIn("Object.entries(monthlySchedule)", self.source)
        self.assertIn(".sort((left, right) => left.month - right.month)", self.source)
        self.assertIn("const schedule = normalizeMonthlyDividendSchedule(data.monthly_schedule);", self.source)
        self.assertIn("const schedule = normalizeMonthlyDividendSchedule(dividendData.monthly_schedule);", self.source)

    def test_array_is_preserved_without_reordering(self):
        schedule = [{"month": 10, "total_krw": 10}, {"month": 1, "total_krw": 1}]
        self.assertEqual(self.normalized_schedule(schedule), schedule)

    def test_month_keyed_object_is_normalized_in_calendar_order(self):
        schedule = {
            "10": {"total_krw": 10},
            "2": {"total_krw": 2},
            "1": {"total_krw": 1},
            "12": {"total_krw": 12},
        }
        normalized = self.normalized_schedule(schedule)
        self.assertEqual([item["month"] for item in normalized], [1, 2, 10, 12])
        self.assertEqual([item["total_krw"] for item in normalized], [1, 2, 10, 12])

    def test_empty_null_missing_and_primitive_schedules_are_safe(self):
        for value in ({}, None, self.MISSING, "unexpected", 7, True):
            with self.subTest(value=value):
                self.assertEqual(self.normalized_schedule(value), [])


if __name__ == "__main__":
    unittest.main()
