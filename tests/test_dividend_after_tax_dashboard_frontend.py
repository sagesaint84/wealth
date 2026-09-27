from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "app" / "static" / "wealth-financial-income-what-if.js"


class DividendAfterTaxDashboardFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS_PATH.read_text(encoding="utf-8")

    def test_after_tax_inputs_are_explicit_and_optional(self):
        self.assertIn("fiWhatIfAfterTaxAssetType", self.js)
        self.assertIn("fiWhatIfAfterTaxInvestment", self.js)
        self.assertIn("계산 안 함", self.js)
        self.assertIn("일반 국내 배당주", self.js)
        self.assertIn("국내상장 해외 ETF 분배금", self.js)
        self.assertIn("미국주식 · 미국 ETF 직투 배당", self.js)

    def test_after_tax_reuses_existing_investment_comparison_contract(self):
        self.assertIn("buildDashboardCashflowScenario", self.js)
        self.assertIn("annual_distribution_krw: extraDividend", self.js)
        self.assertIn("after_known_tax_cash_krw", self.js)
        self.assertIn("known_tax_total_krw", self.js)
        self.assertIn("comprehensive_tax_screening", self.js)
        self.assertNotIn("* 0.154", self.js)
        self.assertNotIn("* 0.15", self.js)

    def test_after_tax_result_is_cashflow_not_final_return_tax(self):
        self.assertIn("추가 배당 세후 현금흐름", self.js)
        self.assertIn("원천징수 후 예상 수령액", self.js)
        self.assertIn("원천징수 후 배당수익률", self.js)
        self.assertIn("최종 신고세액 아님", self.js)
        self.assertIn("한국 최종세액·외국납부세액공제는 계산하지 않습니다", self.js)
        self.assertIn("최종 납부·환급세액을 확정하지 않습니다", self.js)

    def test_investment_amount_only_drives_simple_yield_math(self):
        self.assertIn("afterKnownTaxCash / investmentAmount", self.js)
        self.assertIn("투자금액 입력 필요", self.js)
        self.assertIn("원천징수 후 현금 ÷ 투자금액", self.js)

    def test_advanced_comparison_remains_separate(self):
        self.assertIn("if (boolValue('fiWhatIfInvestmentEnabled')) return null", self.js)
        self.assertIn("comparison && advancedInvestmentEnabled", self.js)
        self.assertIn("투자방법 고급 비교", self.js)


if __name__ == "__main__":
    unittest.main()
