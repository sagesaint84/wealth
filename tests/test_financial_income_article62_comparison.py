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
    def test_twenty_million_withheld_interest_uses_b_only_without_readding_withheld_tax(self):
        exact = calculate_financial_income_article62_comparison_2026(**payload(ordinary_interest_14_krw=20_000_000))
        self.assertFalse(exact["financial_income_threshold"]["exceeded"])
        self.assertEqual(exact["article62_method"], "comparison_b_only")
        self.assertEqual(exact["comparison_b_krw"], 0)
        self.assertEqual(exact["article62_comparison_tax_before_credits_krw"], 0)
        self.assertTrue(exact["data_quality"]["withheld_financial_income_separate_tax_below_threshold_not_included"])

    def test_twenty_million_plus_one_uses_greater_of_a_and_b(self):
        above = calculate_financial_income_article62_comparison_2026(**payload(ordinary_interest_14_krw=20_000_001))
        self.assertTrue(above["financial_income_threshold"]["exceeded"])
        self.assertEqual(above["article62_comparison_tax_before_credits_krw"], max(above["comparison_a_krw"], above["comparison_b_krw"]))
        self.assertEqual(above["comparison_a_krw"], above["comparison_b_krw"])

    def test_below_threshold_nonwithheld_categories_use_their_explicit_rates(self):
        cases = (
            ("nonwithheld_interest_14_krw", 10_000_000, 1_400_000),
            ("nonwithheld_dividend_14_krw", 10_000_000, 1_400_000),
            ("nonwithheld_nonbusiness_loan_interest_25_krw", 10_000_000, 2_500_000),
        )
        for field, amount, expected in cases:
            with self.subTest(field=field):
                result = calculate_financial_income_article62_comparison_2026(**payload(**{field: amount}))
                self.assertEqual(result["comparison_b_krw"], expected)
        combined = calculate_financial_income_article62_comparison_2026(**payload(
            nonwithheld_interest_14_krw=10_000_000,
            nonwithheld_nonbusiness_loan_interest_25_krw=5_000_000,
        ))
        self.assertEqual(combined["comparison_b_krw"], 2_650_000)

    def test_gross_up_uses_only_excess_eligible_dividend(self):
        official_example = calculate_financial_income_article62_comparison_2026(**payload(
            ordinary_interest_14_krw=10_000_000,
            gross_up_eligible_dividend_krw=15_000_000,
        ))
        self.assertEqual(official_example["financial_income_taxable_total_krw"], 25_000_000)
        self.assertEqual(official_example["gross_up_eligible_dividend_krw"], 15_000_000)
        self.assertEqual(official_example["gross_up_target_dividend_krw"], 5_000_000)
        self.assertEqual(official_example["dividend_gross_up_amount_krw"], 500_000)
        at_threshold = calculate_financial_income_article62_comparison_2026(**payload(gross_up_eligible_dividend_krw=20_000_000))
        self.assertEqual(at_threshold["gross_up_target_dividend_krw"], 0)
        self.assertEqual(at_threshold["dividend_gross_up_amount_krw"], 0)
        fully_above = calculate_financial_income_article62_comparison_2026(**payload(
            ordinary_interest_14_krw=30_000_000,
            gross_up_eligible_dividend_krw=10_000_000,
        ))
        self.assertEqual(fully_above["gross_up_target_dividend_krw"], 10_000_000)
        self.assertEqual(fully_above["dividend_gross_up_amount_krw"], 1_000_000)

    def test_metadata_is_explicit_and_not_a_final_tax_payable_calculation(self):
        result = calculate_financial_income_article62_comparison_2026(**payload())
        self.assertFalse(result["data_quality"]["dividend_tax_credit_calculated"])
        self.assertTrue(result["data_quality"]["financial_income_categories_user_classified"])
        self.assertTrue(result["data_quality"]["non_taxable_or_separate_tax_income_excluded_by_caller"])
        self.assertFalse(result["data_quality"]["legal_tax_determination"])
        self.assertEqual(result["rule_context"]["article62_legal_basis"], "소득세법 제62조")

    def test_a_b_and_equal_outcomes_are_preserved_above_threshold(self):
        a_wins = calculate_financial_income_article62_comparison_2026(**payload(ordinary_interest_14_krw=100_000_000, other_comprehensive_income_krw=1_000_000_000))
        self.assertGreater(a_wins["comparison_a_krw"], a_wins["comparison_b_krw"])
        b_wins = calculate_financial_income_article62_comparison_2026(**payload(nonbusiness_loan_interest_25_krw=20_000_001))
        self.assertGreater(b_wins["comparison_b_krw"], b_wins["comparison_a_krw"])
        equal = calculate_financial_income_article62_comparison_2026(**payload(ordinary_interest_14_krw=20_000_001))
        self.assertEqual(equal["comparison_a_krw"], equal["comparison_b_krw"])

    def test_inputs_fail_closed(self):
        for bad in (-1, True, float("nan"), float("inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(PersonalComprehensiveTaxError):
                    calculate_financial_income_article62_comparison_2026(**payload(ordinary_interest_14_krw=bad))
        with self.assertRaises(PersonalComprehensiveTaxError):
            calculate_financial_income_article62_comparison_2026(**{**payload(), "unknown": 0})
