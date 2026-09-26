from __future__ import annotations

import unittest

from app.services.tax import calculate_high_dividend_separate_tax_2026


class HighDividendSpecialTaxTest(unittest.TestCase):
    def calculate(self, amount: int):
        return calculate_high_dividend_separate_tax_2026(
            amount,
            high_dividend_company_confirmed=True,
            separate_taxation_requested=True,
        )

    def test_14_percent_bracket_to_20m(self):
        result = self.calculate(10_000_000)
        self.assertEqual(result["national_income_tax_krw"], 1_400_000)
        self.assertEqual(result["applied_bracket"], "14pct_to_20m")
        self.assertEqual(
            result["excluded_from_comprehensive_tax_threshold_krw"], 10_000_000
        )

    def test_20m_boundary(self):
        result = self.calculate(20_000_000)
        self.assertEqual(result["national_income_tax_krw"], 2_800_000)
        self.assertEqual(result["applied_bracket"], "14pct_to_20m")

    def test_20_percent_bracket(self):
        result = self.calculate(30_000_000)
        self.assertEqual(result["national_income_tax_krw"], 4_800_000)
        self.assertEqual(result["applied_bracket"], "20pct_to_300m")

    def test_300m_boundary(self):
        result = self.calculate(300_000_000)
        self.assertEqual(result["national_income_tax_krw"], 58_800_000)
        self.assertEqual(result["applied_bracket"], "20pct_to_300m")

    def test_25_percent_bracket(self):
        result = self.calculate(400_000_000)
        self.assertEqual(result["national_income_tax_krw"], 83_800_000)
        self.assertEqual(result["applied_bracket"], "25pct_to_5b")

    def test_5b_boundary(self):
        result = self.calculate(5_000_000_000)
        self.assertEqual(result["national_income_tax_krw"], 1_233_800_000)
        self.assertEqual(result["applied_bracket"], "25pct_to_5b")

    def test_30_percent_bracket(self):
        result = self.calculate(6_000_000_000)
        self.assertEqual(result["national_income_tax_krw"], 1_533_800_000)
        self.assertEqual(result["applied_bracket"], "30pct_over_5b")

    def test_rule_metadata_is_explicit(self):
        result = self.calculate(30_000_000)
        self.assertTrue(result["special_rule_applied"])
        self.assertFalse(result["automatic_application"])
        self.assertTrue(result["filing_application_required"])
        self.assertFalse(result["local_income_tax_included"])
        self.assertFalse(result["eligibility"]["determined_by_service"])
        self.assertTrue(result["rule_context"]["screening_only"])
        self.assertFalse(result["rule_context"]["legal_tax_determination"])
        self.assertEqual(result["rule_context"]["verified_on"], "2026-09-26")

    def test_not_requested_does_not_exclude_or_calculate_special_tax(self):
        result = calculate_high_dividend_separate_tax_2026(
            30_000_000,
            high_dividend_company_confirmed=True,
            separate_taxation_requested=False,
        )
        self.assertFalse(result["special_rule_applied"])
        self.assertEqual(result["excluded_from_comprehensive_tax_threshold_krw"], 0)
        self.assertIsNone(result["national_income_tax_krw"])
        self.assertIsNone(result["applied_bracket"])

    def test_zero_amount_is_not_applied(self):
        result = calculate_high_dividend_separate_tax_2026(
            0,
            high_dividend_company_confirmed=True,
            separate_taxation_requested=True,
        )
        self.assertFalse(result["special_rule_applied"])
        self.assertEqual(result["excluded_from_comprehensive_tax_threshold_krw"], 0)
        self.assertIsNone(result["national_income_tax_krw"])


if __name__ == "__main__":
    unittest.main()
