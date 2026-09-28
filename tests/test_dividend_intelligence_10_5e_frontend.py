from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "app" / "static" / "wealth-dividend-source.js"
OFFICIAL = ROOT / "app" / "services" / "dividend_official_sources.py"
QUALIFICATION = ROOT / "app" / "services" / "high_dividend_qualification.py"


class DividendIntelligence105EFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS.read_text(encoding="utf-8")
        cls.official = OFFICIAL.read_text(encoding="utf-8")
        cls.qualification = QUALIFICATION.read_text(encoding="utf-8")

    def test_source_banner_is_compact_and_detail_is_collapsible(self) -> None:
        self.assertIn("배당 예상 근거", self.js)
        self.assertIn("출처별 상세와 확정금액 반영 원칙", self.js)
        self.assertIn("<details", self.js)
        self.assertIn("공식 근거", self.js)
        self.assertIn("확정금액 반영", self.js)
        self.assertIn("이력·시장 추정", self.js)

    def test_intelligence_primary_cards_focus_on_after_known_tax_cash(self) -> None:
        self.assertIn("배당 현금흐름 · 근거 · 공식 자격", self.js)
        self.assertIn("알려진 세금 후 예상 현금", self.js)
        self.assertIn("알려진 세금", self.js)
        self.assertIn("평가금액 기준 세후 배당수익률", self.js)
        self.assertIn("세후 계산 커버리지", self.js)

    def test_after_tax_panel_is_anchored_inside_dividend_panel(self) -> None:
        self.assertIn("document.getElementById('dividendPanel')", self.js)
        self.assertIn("dividendPanel?.querySelector('.dividend-summary-cards')", self.js)
        self.assertNotIn(
            "document.getElementById('dividendModeTabs')?.parentElement?.parentElement",
            self.js,
        )

    def test_high_dividend_official_states_and_source_links_are_visible(self) -> None:
        self.assertIn("고배당기업 공식 자격", self.js)
        for text in ("공식 해당", "공식 미해당", "확인 대기", "조회 불가", "대상 아님"):
            self.assertIn(text, self.js)
        self.assertIn("KIND 고배당기업 현황", self.js)
        self.assertIn("official_qualified_count", self.js)
        self.assertIn("qualified_projected_gross_krw", self.js)
        self.assertIn("qualified_projected_gross_share_pct", self.js)

    def test_high_dividend_status_is_official_only_and_never_auto_applies_tax(self) -> None:
        self.assertIn("wealth_inferred", self.qualification)
        self.assertIn('"absence_means_unqualified": False', self.qualification)
        self.assertIn('"tax_special_treatment_automatically_applied": False', self.qualification)
        self.assertIn("회사가 공식 기업가치 제고 계획 공시에 기재한", self.js)
        self.assertIn("세제특례를 자동 적용하지 않습니다", self.js)

    def test_qualification_runs_after_c5_and_dividend_intelligence(self) -> None:
        c5 = self.official.rfind("_attach_portfolio_after_tax(summary, holdings)")
        intelligence = self.official.rfind("_attach_dividend_intelligence(summary, holdings")
        qualification = self.official.rfind("await _attach_high_dividend_qualification(")
        self.assertGreater(c5, -1)
        self.assertGreater(intelligence, c5)
        self.assertGreater(qualification, intelligence)

    def test_frontend_does_not_add_tax_constants(self) -> None:
        for forbidden in ("0.154", "15.4%", "20_000_000", "20000000"):
            self.assertNotIn(forbidden, self.js)


if __name__ == "__main__":
    unittest.main()
