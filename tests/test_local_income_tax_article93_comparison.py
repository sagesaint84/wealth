from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services.tax import (
    PersonalComprehensiveTaxError,
    calculate_financial_income_article62_comparison_2026,
)
from tests.test_financial_income_article62_comparison import payload, payload_with_prepaid


class LocalIncomeTaxArticle93ComparisonTests(unittest.TestCase):
    def test_twenty_million_withheld_interest_uses_local_b_only(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=20_000_000)
        )
        self.assertFalse(result["financial_income_threshold"]["exceeded"])
        self.assertIsNone(result["local_income_tax_comparison_a_krw"])
        self.assertEqual(result["local_income_tax_comparison_b_krw"], 0)
        self.assertEqual(result["article93_local_income_tax_before_credits_krw"], 0)
        self.assertEqual(result["article93_local_income_tax_method"], "comparison_b_only")

    def test_twenty_million_plus_one_uses_greater_of_local_a_and_b(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=20_000_001)
        )
        self.assertEqual(result["local_income_tax_comparison_a_krw"], 280_000)
        self.assertEqual(result["local_income_tax_comparison_b_krw"], 280_000)
        self.assertEqual(
            result["article93_local_income_tax_before_credits_krw"],
            280_000,
        )
        self.assertEqual(result["article93_local_income_tax_method"], "greater_of_a_b")

    def test_local_comparison_b_can_win(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(
                ordinary_interest_14_krw=10_000_000,
                gross_up_eligible_dividend_krw=15_000_000,
            )
        )
        self.assertEqual(result["local_income_tax_comparison_a_krw"], 313_000)
        self.assertEqual(result["local_income_tax_comparison_b_krw"], 350_000)
        self.assertEqual(
            result["article93_local_income_tax_before_credits_krw"],
            350_000,
        )

    def test_local_comparison_a_can_win(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(
                ordinary_interest_14_krw=10_000_000,
                gross_up_eligible_dividend_krw=15_000_000,
                other_comprehensive_income_excluding_partnership_dividend_krw=50_000_000,
            )
        )
        self.assertEqual(result["local_income_tax_comparison_a_krw"], 1_036_000)
        self.assertEqual(result["local_income_tax_comparison_b_krw"], 974_000)
        self.assertEqual(
            result["article93_local_income_tax_before_credits_krw"],
            1_036_000,
        )

    def test_nonbusiness_loan_interest_uses_local_2_5_percent_equivalent(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(nonbusiness_loan_interest_25_krw=20_000_001)
        )
        self.assertEqual(result["local_income_tax_comparison_a_krw"], 280_000)
        self.assertEqual(result["local_income_tax_comparison_b_krw"], 500_000)
        self.assertEqual(
            result["article93_local_income_tax_before_credits_krw"],
            500_000,
        )

    def test_national_prepaid_withholding_does_not_change_local_tax_before_credits(self):
        without_prepaid = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=30_000_000)
        )
        with_prepaid = calculate_financial_income_article62_comparison_2026(
            **payload_with_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_income_withholding_tax_krw=4_200_000,
            )
        )
        self.assertEqual(
            without_prepaid["article93_local_income_tax_before_credits_krw"],
            with_prepaid["article93_local_income_tax_before_credits_krw"],
        )

    def test_local_scope_metadata_is_explicit(self):
        result = calculate_financial_income_article62_comparison_2026(**payload())
        quality = result["data_quality"]
        self.assertTrue(quality["local_income_tax_calculated"])
        self.assertTrue(quality["local_income_tax_article93_comparison_calculated"])
        self.assertTrue(quality["local_income_tax_standard_rate_only"])
        self.assertFalse(quality["local_income_tax_ordinance_rate_adjustment_calculated"])
        self.assertFalse(quality["local_income_tax_dividend_credit_calculated"])
        self.assertFalse(quality["local_income_tax_prepaid_special_withholding_calculated"])
        self.assertFalse(quality["local_income_tax_final_payment_or_refund_calculated"])
        context = result["rule_context"]
        self.assertEqual(
            context["local_financial_income_comparison_legal_basis"],
            "지방세법 제93조 제2항",
        )
        self.assertEqual(
            context["local_income_tax_comparison_verified_on"],
            "2026-09-27",
        )
        self.assertIn("표준세율", context["local_income_tax_standard_rate_note"])
        self.assertIn("조례", context["local_income_tax_standard_rate_note"])
        self.assertIn("local dividend tax credit", context["not_calculated"])

    def test_local_prepaid_input_remains_fail_closed_until_later_increment(self):
        with self.assertRaisesRegex(PersonalComprehensiveTaxError, "ARTICLE62_REQUEST_INVALID"):
            calculate_financial_income_article62_comparison_2026(
                **{
                    **payload(ordinary_interest_14_krw=30_000_000),
                    "prepaid_local_income_tax_krw": 420_000,
                }
            )


class LocalIncomeTaxArticle93ApiTests(unittest.TestCase):
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

    def test_api_returns_local_article93_fields_with_no_store(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload(
                ordinary_interest_14_krw=10_000_000,
                gross_up_eligible_dividend_krw=15_000_000,
                other_comprehensive_income_excluding_partnership_dividend_krw=50_000_000,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(body["local_income_tax_comparison_a_krw"], 1_036_000)
        self.assertEqual(body["local_income_tax_comparison_b_krw"], 974_000)
        self.assertEqual(
            body["article93_local_income_tax_before_credits_krw"],
            1_036_000,
        )
        self.assertTrue(body["data_quality"]["local_income_tax_calculated"])
        self.assertTrue(
            body["data_quality"]["local_income_tax_article93_comparison_calculated"]
        )
        self.assertFalse(
            body["data_quality"]["local_income_tax_final_payment_or_refund_calculated"]
        )

    def test_api_rejects_local_prepaid_field_for_this_increment(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_local_income_tax_krw": 420_000,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json()["detail"]["code"], "ARTICLE62_REQUEST_INVALID")


if __name__ == "__main__":
    unittest.main()
