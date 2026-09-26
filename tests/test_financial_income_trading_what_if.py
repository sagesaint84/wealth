from __future__ import annotations

import unittest

from app.services.tax.what_if import (
    FinancialIncomeWhatIfError,
    build_financial_income_what_if,
)


class FinancialIncomeTradingWhatIfTests(unittest.TestCase):
    def baseline(self, projected: int | None = 15_000_000) -> dict:
        return {
            "known_gross_screening_income_krw": 12_000_000,
            "projected_gross_screening_income_krw": projected,
        }

    def test_kr_listed_overseas_etf_taxable_gain_adds_to_financial_income(self):
        result = build_financial_income_what_if(
            self.baseline(18_500_000),
            additional_kr_listed_overseas_etf_taxable_gain_krw=1_500_000,
        )

        self.assertEqual(result["scenario_addition_gross_krw"], 1_500_000)
        self.assertEqual(
            result["scenario_projected_gross_screening_income_krw"], 20_000_000
        )
        state = result["thresholds"]["comprehensive_tax"]["scenario"]
        self.assertTrue(state["at_or_above"])
        self.assertFalse(state["exceeded"])

        impact = result["trading_impact"]["kr_listed_overseas_etf"]
        self.assertEqual(impact["taxable_gain_krw"], 1_500_000)
        self.assertEqual(impact["financial_income_addition_krw"], 1_500_000)
        self.assertEqual(impact["estimated_withholding_krw"], 231_000)
        self.assertAlmostEqual(impact["estimated_withholding_rate"], 0.154)

    def test_foreign_share_realized_gain_does_not_change_financial_income_threshold(self):
        result = build_financial_income_what_if(
            self.baseline(19_900_000),
            additional_foreign_share_realized_gain_krw=10_000_000,
        )

        self.assertEqual(result["scenario_addition_gross_krw"], 0)
        self.assertEqual(
            result["scenario_projected_gross_screening_income_krw"], 19_900_000
        )
        self.assertFalse(
            result["thresholds"]["comprehensive_tax"]["scenario"]["at_or_above"]
        )
        impact = result["trading_impact"]["foreign_shares"]
        self.assertEqual(impact["realized_gain_krw"], 10_000_000)
        self.assertEqual(impact["financial_income_addition_krw"], 0)
        self.assertFalse(impact["capital_gain_tax_calculated"])

    def test_dividend_interest_and_etf_taxable_gain_are_combined(self):
        result = build_financial_income_what_if(
            self.baseline(10_000_000),
            additional_dividend_gross_krw=1_000_000,
            additional_interest_gross_krw=500_000,
            additional_kr_listed_overseas_etf_taxable_gain_krw=2_000_000,
            additional_foreign_share_realized_gain_krw=9_000_000,
        )
        self.assertEqual(result["scenario_addition_gross_krw"], 3_500_000)
        self.assertEqual(result["scenario_projected_gross_screening_income_krw"], 13_500_000)
        self.assertEqual(result["additional_foreign_share_realized_gain_krw"], 9_000_000)
        self.assertEqual(
            result["additional_kr_listed_overseas_etf_taxable_gain_krw"], 2_000_000
        )

    def test_unavailable_projection_remains_unknown_with_trading_inputs(self):
        result = build_financial_income_what_if(
            self.baseline(None),
            additional_kr_listed_overseas_etf_taxable_gain_krw=3_000_000,
            additional_foreign_share_realized_gain_krw=4_000_000,
        )
        self.assertIsNone(result["scenario_projected_gross_screening_income_krw"])
        self.assertEqual(
            result["trading_impact"]["kr_listed_overseas_etf"]["taxable_gain_krw"],
            3_000_000,
        )

    def test_invalid_trading_inputs_are_rejected(self):
        cases = (
            (
                {"additional_foreign_share_realized_gain_krw": -1},
                "FINANCIAL_INCOME_WHAT_IF_FOREIGN_SHARE_GAIN_INVALID",
            ),
            (
                {"additional_kr_listed_overseas_etf_taxable_gain_krw": True},
                "FINANCIAL_INCOME_WHAT_IF_KR_OVERSEAS_ETF_GAIN_INVALID",
            ),
        )
        for kwargs, code in cases:
            with self.subTest(code=code):
                with self.assertRaisesRegex(FinancialIncomeWhatIfError, code):
                    build_financial_income_what_if(self.baseline(), **kwargs)


if __name__ == "__main__":
    unittest.main()
