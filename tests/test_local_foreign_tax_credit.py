from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services.tax import calculate_financial_income_article62_comparison_2026
from tests.test_financial_income_article62_comparison import payload_with_prepaid
from tests.test_foreign_tax_credit import foreign_item, payload_with_foreign_credit


class LocalForeignTaxCreditTests(unittest.TestCase):
    def test_absent_national_foreign_credit_inputs_leave_local_credit_unapplied(self):
        result = calculate_financial_income_article62_comparison_2026(
            ordinary_interest_14_krw=30_000_000,
            ordinary_dividend_14_krw=0,
            nonbusiness_loan_interest_25_krw=0,
            online_investment_linked_nonbusiness_loan_interest_14_krw=0,
            nonwithheld_interest_14_krw=0,
            nonwithheld_dividend_14_krw=0,
            nonwithheld_nonbusiness_loan_interest_25_krw=0,
            gross_up_eligible_dividend_krw=0,
            partnership_dividend_krw=0,
            other_comprehensive_income_excluding_partnership_dividend_krw=0,
            income_deduction_krw=0,
        )
        self.assertEqual(result["foreign_tax_credit_krw"], 0)
        self.assertEqual(result["local_foreign_tax_credit_krw"], 0)
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            420_000,
        )
        self.assertFalse(
            result["data_quality"]["local_income_tax_foreign_tax_credit_calculated"]
        )
        self.assertIn(
            "local-income-tax foreign tax credit",
            result["rule_context"]["not_calculated"],
        )

    def test_local_credit_is_ten_percent_of_actual_national_credit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit()
        )
        self.assertEqual(result["foreign_tax_credit_krw"], 1_400_000)
        self.assertEqual(
            result["local_foreign_tax_credit_target_10pct_of_national_krw"],
            140_000,
        )
        self.assertEqual(result["local_foreign_tax_credit_krw"], 140_000)
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_credit_before_other_credits_krw"
            ],
            420_000,
        )
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            280_000,
        )
        self.assertEqual(
            result[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
            280_000,
        )

    def test_local_credit_uses_national_credit_after_dividend_credit_cap(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit(
                ordinary_interest_14_krw=10_000_000,
                gross_up_eligible_dividend_krw=15_000_000,
                other_comprehensive_income_excluding_partnership_dividend_krw=50_000_000,
                comprehensive_income_amount_for_foreign_tax_credit_krw=50_000_000,
                foreign_tax_credit_items=[
                    foreign_item(
                        limit_basis_foreign_source_income_krw=50_000_000,
                        eligible_current_year_foreign_income_tax_krw=10_360_000,
                    )
                ],
            )
        )
        self.assertEqual(result["foreign_tax_credit_krw"], 9_860_000)
        self.assertEqual(result["local_dividend_tax_credit_krw"], 50_000)
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_credit_before_other_credits_krw"
            ],
            986_000,
        )
        self.assertEqual(result["local_foreign_tax_credit_krw"], 986_000)
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            0,
        )

    def test_local_credit_applies_before_explicit_local_special_withholding(self):
        values: dict[str, object] = {
            **payload_with_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_income_withholding_tax_krw=2_800_000,
            ),
            "prepaid_interest_local_income_tax_special_withholding_krw": 420_000,
            "prepaid_dividend_local_income_tax_special_withholding_krw": 0,
            "comprehensive_income_amount_for_foreign_tax_credit_krw": 30_000_000,
            "foreign_tax_credit_items": [foreign_item()],
            "no_other_article60_preceding_tax_reductions_or_credits_confirmed": True,
        }
        result = calculate_financial_income_article62_comparison_2026(**values)
        self.assertEqual(result["local_foreign_tax_credit_krw"], 140_000)
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            280_000,
        )
        self.assertEqual(
            result[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
            -140_000,
        )

    def test_zero_national_credit_with_inputs_is_calculated_zero_local_credit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit(
                foreign_tax_credit_items=[
                    foreign_item(eligible_current_year_foreign_income_tax_krw=0)
                ]
            )
        )
        self.assertEqual(result["foreign_tax_credit_krw"], 0)
        self.assertEqual(result["local_foreign_tax_credit_krw"], 0)
        self.assertTrue(
            result["data_quality"]["local_income_tax_foreign_tax_credit_calculated"]
        )

    def test_metadata_is_explicit_about_five_year_carryforward_scope(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit()
        )
        quality = result["data_quality"]
        self.assertTrue(quality["local_income_tax_foreign_tax_credit_calculated"])
        self.assertTrue(
            quality["local_income_tax_foreign_tax_credit_based_on_national_credit"]
        )
        self.assertTrue(
            quality["local_income_tax_foreign_tax_credit_current_year_only"]
        )
        self.assertFalse(
            quality[
                "local_income_tax_foreign_tax_credit_prior_year_carryforward_calculated"
            ]
        )
        self.assertFalse(
            quality["local_income_tax_foreign_tax_credit_carryforward_calculated"]
        )

        context = result["rule_context"]
        self.assertEqual(
            context["local_foreign_tax_credit_legal_basis"],
            "지방세특례제한법 제97조 제1항",
        )
        self.assertEqual(
            context["local_foreign_tax_credit_carryforward_legal_basis"],
            "지방세특례제한법 제97조 제2항",
        )
        self.assertEqual(context["local_foreign_tax_credit_carryforward_years"], 5)
        self.assertNotIn(
            "local-income-tax foreign tax credit",
            context["not_calculated"],
        )
        self.assertIn(
            "local foreign-tax-credit carryforward determination",
            context["not_calculated"],
        )
        self.assertIn("5년 이월공제", context["local_foreign_tax_credit_note"])


class LocalForeignTaxCreditApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user = patch(
            "app.services.user_manager.get_user_by_name",
            return_value={"username": "alice", "role": "user"},
        )
        self.user.start()
        self.addCleanup(self.user.stop)
        self.client.cookies.set(
            main.COOKIE_NAME,
            main._serializer.dumps({"user": "alice"}),
        )

    def test_api_returns_local_foreign_credit_with_no_store(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload_with_foreign_credit(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(body["foreign_tax_credit_krw"], 1_400_000)
        self.assertEqual(body["local_foreign_tax_credit_krw"], 140_000)
        self.assertEqual(
            body[
                "article93_local_income_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            280_000,
        )


if __name__ == "__main__":
    unittest.main()
