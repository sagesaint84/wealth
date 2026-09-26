from __future__ import annotations

import unittest

from app.services.tax.personal_comprehensive_tax_2026 import (
    PersonalComprehensiveTaxError,
    calculate_personal_comprehensive_tax_basic_rate_2026,
)


class PersonalComprehensiveTax2026Tests(unittest.TestCase):
    def test_basic_rate_comparison_uses_2026_rule_table(self):
        result = calculate_personal_comprehensive_tax_basic_rate_2026(
            tax_base_before_financial_income_krw=14_000_000,
            financial_income_gross_krw=36_000_000,
            assumed_financial_income_included_in_tax_base_krw=36_000_000,
        )

        self.assertEqual(result["national_income_tax_before_krw"], 840_000)
        self.assertEqual(result["national_income_tax_after_krw"], 6_240_000)
        self.assertEqual(result["estimated_national_income_tax_difference_krw"], 5_400_000)
        self.assertEqual(result["tax_base_after_krw"], 50_000_000)
        self.assertTrue(result["financial_income_threshold"]["exceeded"])
        self.assertEqual(result["rule_context"]["year"], 2026)
        self.assertTrue(result["data_quality"]["screening_only"])
        self.assertFalse(result["data_quality"]["legal_tax_determination"])

    def test_exact_twenty_million_is_reached_not_exceeded(self):
        result = calculate_personal_comprehensive_tax_basic_rate_2026(
            tax_base_before_financial_income_krw=0,
            financial_income_gross_krw=20_000_000,
            assumed_financial_income_included_in_tax_base_krw=0,
        )

        threshold = result["financial_income_threshold"]
        self.assertTrue(threshold["at_or_above"])
        self.assertFalse(threshold["exceeded"])
        self.assertEqual(result["estimated_national_income_tax_difference_krw"], 0)

    def test_rejects_unsafe_or_unfounded_assumed_inputs(self):
        invalid_values = [True, -1, float("nan"), float("inf"), "bad"]
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(PersonalComprehensiveTaxError):
                    calculate_personal_comprehensive_tax_basic_rate_2026(
                        tax_base_before_financial_income_krw=value,
                        financial_income_gross_krw=1,
                        assumed_financial_income_included_in_tax_base_krw=0,
                    )

        with self.assertRaisesRegex(
            PersonalComprehensiveTaxError,
            "PERSONAL_COMPREHENSIVE_TAX_INCLUDED_AMOUNT_EXCEEDS_FINANCIAL_INCOME",
        ):
            calculate_personal_comprehensive_tax_basic_rate_2026(
                tax_base_before_financial_income_krw=0,
                financial_income_gross_krw=1,
                assumed_financial_income_included_in_tax_base_krw=2,
            )

    def test_does_not_calculate_withholding_local_or_foreign_tax_credit(self):
        result = calculate_personal_comprehensive_tax_basic_rate_2026(
            tax_base_before_financial_income_krw=10_000_000,
            financial_income_gross_krw=25_000_000,
            assumed_financial_income_included_in_tax_base_krw=5_000_000,
        )

        not_calculated = result["rule_context"]["not_calculated"]
        self.assertIn("withholding tax already paid", not_calculated)
        self.assertIn("personal local income tax", not_calculated)
        self.assertIn("foreign tax credit", not_calculated)
        self.assertFalse(result["data_quality"]["withholding_tax_credit_calculated"])
        self.assertFalse(result["data_quality"]["local_income_tax_calculated"])
        self.assertFalse(result["data_quality"]["foreign_tax_credit_calculated"])


if __name__ == "__main__":
    unittest.main()
