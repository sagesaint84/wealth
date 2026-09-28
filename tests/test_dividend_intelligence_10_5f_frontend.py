from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "wealth-dividend-source.js"


class DividendIntelligence105FFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS.read_text(encoding="utf-8")

    def test_calculation_status_is_localized_for_detail_table(self) -> None:
        self.assertIn("function calculationStatusLabel", self.js)
        self.assertIn("calculated: '계산 완료'", self.js)
        self.assertIn("unsupported: '계산 제외'", self.js)
        self.assertIn("unavailable: '확인 불가'", self.js)
        self.assertIn("calculationStatusLabel(row.calculation_status)", self.js)
        self.assertNotIn("${escapeHtml(row.calculation_status)}", self.js)

    def test_non_applicable_high_dividend_row_hides_official_link(self) -> None:
        self.assertIn("status === 'not_applicable'", self.js)
        self.assertIn("? null", self.js)
        self.assertIn("qualification?.source_url || qualification?.kind_reference_url", self.js)
        self.assertIn("'대상 아님'", self.js)

    def test_existing_qualification_states_remain_visible(self) -> None:
        for text in ("공식 해당", "공식 미해당", "확인 대기", "조회 불가", "대상 아님"):
            self.assertIn(text, self.js)


if __name__ == "__main__":
    unittest.main()
