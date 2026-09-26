from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HighDividendWhatIfStaticTests(unittest.TestCase):
    def test_api_accepts_only_explicit_high_dividend_scenario_fields(self):
        source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn('"high_dividend_scenario"', source)
        self.assertIn('"special_dividend_income_krw"', source)
        self.assertIn('"high_dividend_company_confirmed"', source)
        self.assertIn('"separate_taxation_requested"', source)
        self.assertIn("HighDividendSpecialTaxError", source)

    def test_ui_separates_official_confirmation_from_filing_assumption(self):
        source = (ROOT / "app" / "static" / "wealth-financial-income-what-if.js").read_text(encoding="utf-8")
        self.assertIn("fiWhatIfHighDividendConfirmed", source)
        self.assertIn("fiWhatIfHighDividendRequested", source)
        self.assertIn("공식 공시에서 고배당기업 확인함", source)
        self.assertIn("신고 시 분리과세 신청 가정", source)
        self.assertIn("high_dividend_scenario", source)
        self.assertIn("scenario_comprehensive_tax_screening_income_krw", source)
        self.assertNotIn("고배당 특례, 건강보험료", source)

    def test_ui_does_not_claim_automatic_eligibility(self):
        source = (ROOT / "app" / "static" / "wealth-financial-income-what-if.js").read_text(encoding="utf-8")
        self.assertIn("앱이 배당수익률로 적격 여부를 추정하지 않습니다", source)
        self.assertIn("앱 자동 적격판정 아님", source)


if __name__ == "__main__":
    unittest.main()
