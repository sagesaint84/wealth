from __future__ import annotations

import unittest

from app.services.tax import calculate_financial_income_article62_comparison_2026
from tests.test_financial_income_article62_comparison import payload, payload_with_prepaid


class LocalDividendTaxCreditTests(unittest.TestCase):
    def test_credit_is_ten_percent_of_national_dividend_gross_up(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(gross_up_eligible_dividend_krw=30_000_000)
        )

        self.assertEqual(result["gross_up_target_dividend_krw"], 10_000_000)
        self.assertEqual(result["dividend_gross_up_amount_krw"], 1_000_000)
        self.assertEqual(result["article93_local_income_tax_before_credits_krw"], 420_000)
        self.assertEqual(result["local_dividend_tax_credit_krw"], 100_000)
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_credit_before_other_credits_krw"
            ],
            320_000,
        )

    def test_exact_threshold_has_no_local_dividend_credit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(gross_up_eligible_dividend_krw=20_000_000)
        )

        self.assertFalse(result["financial_income_threshold"]["exceeded"])
        self.assertEqual(result["dividend_gross_up_amount_krw"], 0)
        self.assertEqual(result["local_dividend_tax_credit_krw"], 0)
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_credit_before_other_credits_krw"
            ],
            result["article93_local_income_tax_before_credits_krw"],
        )

    def test_credit_depends_on_explicit_gross_up_eligible_classification(self):
        ordinary = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_dividend_14_krw=30_000_000)
        )
        eligible = calculate_financial_income_article62_comparison_2026(
            **payload(gross_up_eligible_dividend_krw=30_000_000)
        )

        self.assertEqual(ordinary["local_dividend_tax_credit_krw"], 0)
        self.assertEqual(eligible["local_dividend_tax_credit_krw"], 100_000)
        self.assertTrue(
            eligible["data_quality"][
                "local_income_tax_dividend_credit_user_classification_dependent"
            ]
        )

    def test_national_prepaid_withholding_does_not_change_local_dividend_credit(self):
        base = calculate_financial_income_article62_comparison_2026(
            **payload(gross_up_eligible_dividend_krw=30_000_000)
        )
        prepaid = calculate_financial_income_article62_comparison_2026(
            **payload_with_prepaid(
                gross_up_eligible_dividend_krw=30_000_000,
                prepaid_dividend_income_withholding_tax_krw=4_200_000,
            )
        )

        self.assertEqual(
            base["local_dividend_tax_credit_krw"],
            prepaid["local_dividend_tax_credit_krw"],
        )
        self.assertEqual(
            base[
                "article93_local_income_tax_after_dividend_credit_before_other_credits_krw"
            ],
            prepaid[
                "article93_local_income_tax_after_dividend_credit_before_other_credits_krw"
            ],
        )

    def test_rule_context_records_official_basis_and_partial_scope(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(gross_up_eligible_dividend_krw=30_000_000)
        )
        context = result["rule_context"]

        self.assertEqual(
            context["local_dividend_tax_credit_legal_basis"],
            "지방세특례제한법 제95조",
        )
        self.assertEqual(
            context["local_dividend_tax_credit_formula"],
            "round(dividend_gross_up_amount_krw * 0.10)",
        )
        self.assertTrue(context["official_local_dividend_tax_credit_law_source_url"])
        self.assertIn("특별징수 기납부세액", context["local_income_tax_scope_note"])
        self.assertIn("local prepaid special withholding tax", context["not_calculated"])
        self.assertIn("final local income-tax payment or refund amount", context["not_calculated"])


if __name__ == "__main__":
    unittest.main()
