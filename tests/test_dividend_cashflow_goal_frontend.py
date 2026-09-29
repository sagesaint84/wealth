from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "wealth-dividend-source.js"


class DividendCashflowGoalFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS.read_text(encoding="utf-8")

    def test_selected_year_cashflow_reuses_existing_monthly_schedule(self) -> None:
        self.assertIn("function scheduleMonths", self.js)
        self.assertIn("data?.monthly_schedule", self.js)
        self.assertIn("function buildMonthlyAfterTaxCashflow", self.js)
        self.assertIn("item?.payout_krw", self.js)
        self.assertIn("instrument.after_known_tax_cash_krw", self.js)
        self.assertIn("calculation_status !== 'calculated'", self.js)

    def test_monthly_after_tax_allocation_preserves_existing_tax_results(self) -> None:
        self.assertIn("allocatableCash * item.value / scheduleGross", self.js)
        self.assertIn("view?.calculation_status === 'complete'", self.js)
        self.assertIn("trust?.unattributed_residual_krw", self.js)
        self.assertIn("residual === 0", self.js)
        self.assertIn("annualCashReconciled", self.js)
        for forbidden in ("0.154", "0.15", "15.4%"):
            self.assertNotIn(forbidden, self.js)

    def test_goal_is_user_defined_owner_scoped_and_client_only(self) -> None:
        self.assertIn("wealth_dividend_monthly_goal_krw_v1", self.js)
        self.assertIn("dividend_intelligence?.owner", self.js)
        self.assertIn("localStorage.setItem", self.js)
        self.assertIn("localStorage.removeItem", self.js)
        self.assertIn("id=\"dividendMonthlyNetGoal\"", self.js)
        self.assertIn("data-korean-currency", self.js)
        self.assertIn("value=\"${goal || ''}\"", self.js)
        self.assertNotIn("const goal = 1000000", self.js)

    def test_incomplete_monthly_attribution_keeps_annual_goal_information(self) -> None:
        self.assertIn("최소 ${minimumMetMonths}개월 충족", self.js)
        self.assertIn("${pendingMonths}개월 판정 대기", self.js)
        self.assertIn("연간 총액 기준 부족", self.js)
        self.assertIn("연간 총액 기준 초과", self.js)
        self.assertIn("월 미정 ${money(flow.unassignedCash)}", self.js)
        self.assertIn("residual과 월 미정 금액은 특정 월·종목에 임의 배분하지 않습니다", self.js)

    def test_decision_view_contains_monthly_balance_and_contributors(self) -> None:
        for text in (
            "선택 연도 12개월 배당 현금흐름",
            "월평균 예상 수령",
            "최대 / 최소 월",
            "최대월 편중",
            "상위 예상 수령 기여 종목",
            "월 목표 상태",
        ):
            self.assertIn(text, self.js)


if __name__ == "__main__":
    unittest.main()
