from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "app" / "static" / "wealth-financial-income-what-if.js"
CSS_PATH = ROOT / "app" / "static" / "wealth-financial-income-what-if.css"


class DividendTaxDashboardFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS_PATH.read_text(encoding="utf-8")
        cls.css = CSS_PATH.read_text(encoding="utf-8")

    def test_dashboard_is_focused_on_dividend_decisions(self):
        self.assertIn("DIVIDEND TAX DASHBOARD", self.js)
        self.assertIn("배당 세금 대시보드", self.js)
        self.assertIn("배당을 더 받는다면?", self.js)
        self.assertIn("2천만원까지 여유", self.js)
        self.assertIn("배당 추가 후", self.js)
        self.assertIn("자산관리 의사결정용", self.js)

    def test_quick_dividend_presets_are_available(self):
        self.assertIn("DIVIDEND_PRESETS = [1e6, 5e6, 10e6]", self.js)
        self.assertIn("data-dividend-preset", self.js)
        self.assertIn(".fi-dividend-presets", self.css)
        self.assertIn(".fi-dividend-preset", self.css)
        self.assertNotIn("10_000_000", self.js)

    def test_existing_what_if_api_contract_is_preserved(self):
        self.assertIn("/api/dividends/financial-income-what-if", self.js)
        for field_id in (
            "fiWhatIfExtraDividend",
            "fiWhatIfExtraInterest",
            "fiWhatIfForeignShareGain",
            "fiWhatIfKrOverseasEtfTaxableGain",
            "fiWhatIfHighDividendEnabled",
            "fiWhatIfInvestmentEnabled",
            "fiWhatIfAssetType",
        ):
            with self.subTest(field_id=field_id):
                self.assertIn(field_id, self.js)

    def test_existing_static_contract_markers_are_preserved(self):
        self.assertIn("2천만원 도달 · 초과 아님", self.js)
        self.assertIn("capital_gain_tax_calculated", self.js)
        self.assertIn("scenario_comprehensive_tax_screening_income_krw", self.js)

    def test_advanced_tax_and_corporation_controls_are_deemphasized(self):
        self.assertIn("이자·매매 등 다른 가정도 추가하기", self.js)
        self.assertIn("고배당 특례 · 개인 vs 가족법인 등 고급 비교", self.js)
        self.assertIn("fi-secondary-scenarios", self.js)
        self.assertIn("fi-advanced-scenarios", self.js)

    def test_dashboard_does_not_claim_final_return_tax(self):
        self.assertIn("최종 납부·환급세액을 확정하지 않습니다", self.js)
        self.assertIn("screening", self.js)


if __name__ == "__main__":
    unittest.main()
