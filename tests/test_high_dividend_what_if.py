from __future__ import annotations

import unittest

from app.services.tax.high_dividend_2026 import HighDividendSpecialTaxError
from app.services.tax.what_if import (
    FinancialIncomeWhatIfError,
    build_financial_income_what_if,
)


BASELINE = {
    "known_gross_screening_income_krw": 10_000_000,
    "projected_gross_screening_income_krw": 19_000_000,
}


class HighDividendWhatIfTests(unittest.TestCase):
    def test_no_special_scenario_preserves_existing_screening(self):
        result = build_financial_income_what_if(
            BASELINE, additional_dividend_gross_krw=2_000_000
        )
        self.assertEqual(result["scenario_projected_gross_screening_income_krw"], 21_000_000)
        self.assertEqual(result["scenario_comprehensive_tax_screening_income_krw"], 21_000_000)
        self.assertTrue(result["thresholds"]["comprehensive_tax"]["scenario"]["exceeded"])
        self.assertIsNone(result["high_dividend_special_tax"])

    def test_applied_special_dividend_reduces_only_comprehensive_screening(self):
        result = build_financial_income_what_if(
            BASELINE,
            additional_dividend_gross_krw=2_000_000,
            high_dividend_scenario={
                "special_dividend_income_krw": 2_000_000,
                "high_dividend_company_confirmed": True,
                "separate_taxation_requested": True,
            },
        )
        self.assertEqual(result["scenario_projected_gross_screening_income_krw"], 21_000_000)
        self.assertEqual(result["scenario_comprehensive_tax_screening_income_krw"], 19_000_000)
        self.assertFalse(result["thresholds"]["comprehensive_tax"]["scenario"]["exceeded"])
        self.assertTrue(result["thresholds"]["watch"]["scenario"]["at_or_above"])
        special = result["high_dividend_special_tax"]
        self.assertTrue(special["special_rule_applied"])
        self.assertEqual(special["excluded_from_comprehensive_tax_threshold_krw"], 2_000_000)
        self.assertEqual(special["national_income_tax_krw"], 280_000)

    def test_not_requested_preserves_comprehensive_screening(self):
        result = build_financial_income_what_if(
            BASELINE,
            additional_dividend_gross_krw=2_000_000,
            high_dividend_scenario={
                "special_dividend_income_krw": 2_000_000,
                "high_dividend_company_confirmed": True,
                "separate_taxation_requested": False,
            },
        )
        self.assertEqual(result["scenario_comprehensive_tax_screening_income_krw"], 21_000_000)
        self.assertFalse(result["high_dividend_special_tax"]["special_rule_applied"])

    def test_requested_without_official_confirmation_fails_closed(self):
        with self.assertRaisesRegex(
            HighDividendSpecialTaxError, "HIGH_DIVIDEND_COMPANY_CONFIRMATION_REQUIRED"
        ):
            build_financial_income_what_if(
                BASELINE,
                additional_dividend_gross_krw=1_000_000,
                high_dividend_scenario={
                    "special_dividend_income_krw": 1_000_000,
                    "high_dividend_company_confirmed": False,
                    "separate_taxation_requested": True,
                },
            )

    def test_special_amount_cannot_exceed_additional_dividend(self):
        with self.assertRaisesRegex(
            FinancialIncomeWhatIfError,
            "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_EXCEEDS_ADDITIONAL_DIVIDEND",
        ):
            build_financial_income_what_if(
                BASELINE,
                additional_dividend_gross_krw=500_000,
                high_dividend_scenario={
                    "special_dividend_income_krw": 500_001,
                    "high_dividend_company_confirmed": True,
                    "separate_taxation_requested": True,
                },
            )

    def test_unknown_special_field_is_rejected(self):
        with self.assertRaisesRegex(
            FinancialIncomeWhatIfError,
            "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_SCENARIO_INVALID",
        ):
            build_financial_income_what_if(
                BASELINE,
                high_dividend_scenario={"save": True},
            )

    def test_unavailable_projection_stays_unknown_after_special_rule(self):
        result = build_financial_income_what_if(
            {
                "known_gross_screening_income_krw": 10_000_000,
                "projected_gross_screening_income_krw": None,
            },
            additional_dividend_gross_krw=1_000_000,
            high_dividend_scenario={
                "special_dividend_income_krw": 1_000_000,
                "high_dividend_company_confirmed": True,
                "separate_taxation_requested": True,
            },
        )
        self.assertIsNone(result["scenario_projected_gross_screening_income_krw"])
        self.assertIsNone(result["scenario_comprehensive_tax_screening_income_krw"])
        self.assertIsNone(result["thresholds"]["comprehensive_tax"]["scenario"]["exceeded"])


if __name__ == "__main__":
    unittest.main()
