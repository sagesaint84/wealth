from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "app" / "static" / "wealth-financial-income-what-if.js"


class FinancialIncomeTradingWhatIfStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = JS_PATH.read_text(encoding="utf-8")

    def test_quick_trading_inputs_exist(self):
        for marker in (
            "fiWhatIfForeignShareGain",
            "fiWhatIfKrOverseasEtfTaxableGain",
            "additional_foreign_share_realized_gain_krw",
            "additional_kr_listed_overseas_etf_taxable_gain_krw",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.source)

    def test_money_inputs_use_common_krw_hint(self):
        self.assertIn(
            'id="fiWhatIfForeignShareGain" type="number"', self.source
        )
        self.assertIn(
            'id="fiWhatIfKrOverseasEtfTaxableGain" type="number"', self.source
        )
        foreign_fragment = self.source.split('id="fiWhatIfForeignShareGain"', 1)[1][:220]
        etf_fragment = self.source.split(
            'id="fiWhatIfKrOverseasEtfTaxableGain"', 1
        )[1][:220]
        self.assertIn("data-korean-currency", foreign_fragment)
        self.assertIn("data-korean-currency", etf_fragment)

    def test_result_distinguishes_foreign_gain_from_financial_income(self):
        self.assertIn("trading_impact", self.source)
        self.assertIn("capital_gain_tax_calculated", self.source)
        self.assertIn("estimated_withholding_krw", self.source)
        self.assertIn("금융소득 판정 미포함", self.source)
        self.assertIn("금융소득에 포함", self.source)

    def test_quick_trading_can_seed_investment_comparison_without_overwrite(self):
        self.assertIn("fiWhatIfUseQuickTrading", self.source)
        self.assertIn("fiWhatIfForeignShareGain", self.source)
        self.assertIn("fiWhatIfKrOverseasEtfTaxableGain", self.source)
        self.assertIn("etfInput.value === ''", self.source)

    def test_scenario_remains_stateless(self):
        lowered = self.source.lower()
        self.assertNotIn("localstorage.setitem", lowered)
        self.assertNotIn("sessionstorage.setitem", lowered)


if __name__ == "__main__":
    unittest.main()
