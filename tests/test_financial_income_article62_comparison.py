from __future__ import annotations

import unittest

from app.services.tax.personal_comprehensive_tax_2026 import (
    PersonalComprehensiveTaxError,
    calculate_financial_income_article62_comparison_2026,
)


def payload(**overrides):
    result = {
        "ordinary_interest_14_krw": 0, "ordinary_dividend_14_krw": 0,
        "nonbusiness_loan_interest_25_krw": 0, "nonbusiness_loan_interest_14_krw": 0,
        "nonwithheld_interest_14_krw": 0, "nonwithheld_nonbusiness_loan_interest_25_krw": 0,
        "nonwithheld_dividend_14_krw": 0, "gross_up_eligible_dividend_krw": 0,
        "other_comprehensive_income_krw": 0, "income_deduction_krw": 0,
    }
    result.update(overrides)
    return result


class Article62ComparisonTests(unittest.TestCase):
    def test_twenty_million_uses_b_only_and_plus_one_uses_greater(self):
        exact = calculate_financial_income_article62_comparison_2026(**payload(ordinary_interest_14_krw=20_000_000))
        self.assertFalse(exact["financial_income_threshold"]["exceeded"])
        self.assertEqual(exact["article62_method"], "comparison_b_only")
        above = calculate_financial_income_article62_comparison_2026(**payload(ordinary_interest_14_krw=20_000_001))
        self.assertTrue(above["financial_income_threshold"]["exceeded"])
        self.assertEqual(above["article62_comparison_tax_before_credits_krw"], max(above["comparison_a_krw"], above["comparison_b_krw"]))
        self.assertEqual(above["comparison_a_krw"], above["comparison_b_krw"])

    def test_rates_gross_up_and_metadata_are_explicit(self):
        result = calculate_financial_income_article62_comparison_2026(**payload(
            ordinary_interest_14_krw=100, ordinary_dividend_14_krw=100,
            nonbusiness_loan_interest_25_krw=100, nonbusiness_loan_interest_14_krw=100,
            nonwithheld_interest_14_krw=100, nonwithheld_nonbusiness_loan_interest_25_krw=100,
            nonwithheld_dividend_14_krw=100, gross_up_eligible_dividend_krw=100,
        ))
        self.assertEqual(result["comparison_b_krw"], 134)
        self.assertEqual(result["dividend_gross_up_amount_krw"], 10)
        self.assertTrue(result["gross_up_eligibility_user_asserted"])
        self.assertFalse(result["data_quality"]["dividend_tax_credit_calculated"])
        self.assertEqual(result["rule_context"]["article62_legal_basis"], "소득세법 제62조")

    def test_a_can_win_with_other_income_and_inputs_fail_closed(self):
        result = calculate_financial_income_article62_comparison_2026(**payload(ordinary_interest_14_krw=100_000_000, other_comprehensive_income_krw=1_000_000_000))
        self.assertGreater(result["comparison_a_krw"], result["comparison_b_krw"])
        for bad in (-1, True, float("nan"), float("inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(PersonalComprehensiveTaxError):
                    calculate_financial_income_article62_comparison_2026(**payload(ordinary_interest_14_krw=bad))
        with self.assertRaises(PersonalComprehensiveTaxError):
            calculate_financial_income_article62_comparison_2026(**{**payload(), "unknown": 0})
