from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "wealth-dividend-source.js"


class DividendCashflowAttribution105HFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS.read_text(encoding="utf-8")

    def test_partial_schedule_allocates_only_proportional_known_cash(self) -> None:
        self.assertIn("const scheduleRatio = Math.min(scheduleGross / annualGross, 1)", self.js)
        self.assertIn("Math.round(annualCash * scheduleRatio)", self.js)
        self.assertIn("partial_monthly_schedule", self.js)
        self.assertIn("monthly_schedule_missing", self.js)

    def test_schedule_exceeding_annual_fails_closed(self) -> None:
        self.assertIn("scheduleGross > annualGross + roundingTolerance", self.js)
        self.assertIn("monthly_schedule_exceeds_annual", self.js)
        self.assertIn("allocatableCash = 0", self.js)

    def test_unassigned_cash_is_explicit_and_never_forced_into_months(self) -> None:
        self.assertIn("unassignedInstruments", self.js)
        self.assertIn("unassignedCash", self.js)
        self.assertIn("월 미정", self.js)
        self.assertIn("임의 배분하지 않습니다", self.js)

    def test_annual_average_uses_canonical_known_after_tax_total(self) -> None:
        self.assertIn("const annualCash = flow.annualAvailable ? flow.canonicalAfterCash : flow.attributedCash", self.js)
        self.assertIn("const monthlyAverage = annualCash / 12", self.js)
        self.assertIn("연간 알려진 세금 후 총액 ÷ 12", self.js)

    def test_partial_goal_state_is_lower_bound_not_false_failure(self) -> None:
        self.assertIn("minimumMetMonths", self.js)
        self.assertIn("pendingMonths", self.js)
        self.assertIn("최소 ✓", self.js)
        self.assertIn("안전하게 귀속된 금액만으로 월 목표 최소 충족", self.js)
        self.assertIn("판정 대기", self.js)
        self.assertIn("연간 총액 기준", self.js)

    def test_no_new_tax_rate_or_month_guessing_is_introduced(self) -> None:
        for forbidden in ("0.154", "0.15", "15.4%", "payout_months = [4]", "defaultPaymentMonth"):
            self.assertNotIn(forbidden, self.js)


if __name__ == "__main__":
    unittest.main()
