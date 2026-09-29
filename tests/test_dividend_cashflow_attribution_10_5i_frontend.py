from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "wealth-dividend-source.js"


class DividendCashflowAttribution105IFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS.read_text(encoding="utf-8")

    def test_month_unknown_reasons_have_user_facing_labels(self) -> None:
        self.assertIn("function monthlyAttributionReasonLabel", self.js)
        self.assertIn("지급월 없음", self.js)
        self.assertIn("일부 지급월만 연결", self.js)
        self.assertIn("월별 합계 불일치", self.js)
        self.assertIn("반올림 잔액", self.js)

    def test_month_unknown_rows_expose_schedule_coverage_without_guessing(self) -> None:
        self.assertIn("schedule_coverage_pct", self.js)
        self.assertIn("scheduled_gross_krw", self.js)
        self.assertIn("annual_gross_krw", self.js)
        self.assertIn("지급월 연결", self.js)
        self.assertIn("월 미정 ${money(row.unassigned_after_known_tax_cash_krw)}", self.js)

    def test_month_card_status_uses_compact_non_wrapping_badges(self) -> None:
        self.assertIn("최소 ✓", self.js)
        self.assertIn(">대기</span>", self.js)
        self.assertIn("white-space:nowrap", self.js)
        self.assertIn("월 미정 금액이 있어 최종 판정 대기", self.js)

    def test_diagnostics_are_explanatory_only(self) -> None:
        self.assertIn("월 미정 원인", self.js)
        self.assertIn("임의 배분하지 않습니다", self.js)
        for forbidden in ("0.154", "0.15", "15.4%", "defaultPaymentMonth", "guessPaymentMonth"):
            self.assertNotIn(forbidden, self.js)


if __name__ == "__main__":
    unittest.main()
