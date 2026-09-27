from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services.tax import calculate_financial_income_article62_comparison_2026
from app.services.tax.personal_comprehensive_tax_2026 import PersonalComprehensiveTaxError
from tests.test_financial_income_article62_comparison import payload, payload_with_prepaid


class OtherArticle76PrepaymentsTests(unittest.TestCase):
    def test_absent_inputs_keep_b47_partial_balance(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=30_000_000)
        )
        self.assertEqual(result["prepaid_other_comprehensive_income_withholding_tax_krw"], 0)
        self.assertEqual(result["prepaid_tax_association_collected_income_tax_krw"], 0)
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"
            ],
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
        )
        self.assertFalse(
            result["data_quality"]["other_comprehensive_income_withholding_tax_calculated"]
        )
        self.assertFalse(
            result["data_quality"]["tax_association_collected_income_tax_calculated"]
        )
        self.assertFalse(result["data_quality"]["tax_association_credit_calculated"])

    def test_other_comprehensive_income_withholding_reduces_partial_balance(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_other_comprehensive_income_withholding_tax_krw": 1_000_000,
            }
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
            4_200_000,
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"
            ],
            3_200_000,
        )
        self.assertEqual(
            result["article76_other_withholding_and_tax_association_collected_total_krw"],
            1_000_000,
        )

    def test_tax_association_collected_tax_reduces_partial_balance(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_tax_association_collected_income_tax_krw": 700_000,
            }
        )
        self.assertEqual(result["prepaid_tax_association_collected_income_tax_krw"], 700_000)
        self.assertEqual(
            result["article76_other_withholding_and_tax_association_collected_total_krw"],
            700_000,
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"
            ],
            3_500_000,
        )
        self.assertTrue(
            result["data_quality"]["tax_association_collected_income_tax_calculated"]
        )

    def test_other_article76_inputs_coexist_with_financial_withholding_and_interim(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload_with_prepaid(
                    ordinary_interest_14_krw=30_000_000,
                    prepaid_interest_income_withholding_tax_krw=2_800_000,
                ),
                "prepaid_interim_income_tax_krw": 500_000,
                "prepaid_other_comprehensive_income_withholding_tax_krw": 250_000,
                "prepaid_tax_association_collected_income_tax_krw": 100_000,
            }
        )
        self.assertEqual(
            result["partial_national_income_tax_balance_after_explicit_financial_withholding_krw"],
            1_400_000,
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
            900_000,
        )
        self.assertEqual(
            result["article76_other_withholding_and_tax_association_collected_total_krw"],
            350_000,
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"
            ],
            550_000,
        )

    def test_tax_association_credit_is_passed_to_preceding_credit_model(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 30_000,
            }
        )
        self.assertEqual(result["tax_association_credit_krw"], 30_000)
        self.assertEqual(result["tax_association_credit_applied_krw"], 30_000)
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"
            ],
            4_170_000,
        )
        self.assertNotIn("tax association credit", result["rule_context"]["not_calculated"])

    def test_invalid_other_withholding_is_rejected(self):
        for bad_value in (True, -1, float("nan"), float("inf"), "bad"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE76_OTHER_WITHHOLDING_AMOUNT_INVALID",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **{
                            **payload(ordinary_interest_14_krw=30_000_000),
                            "prepaid_other_comprehensive_income_withholding_tax_krw": bad_value,
                        }
                    )

    def test_invalid_tax_association_collected_amount_is_rejected(self):
        for bad_value in (True, -1, float("nan"), float("inf"), "bad"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE76_TAX_ASSOCIATION_AMOUNT_INVALID",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **{
                            **payload(ordinary_interest_14_krw=30_000_000),
                            "prepaid_tax_association_collected_income_tax_krw": bad_value,
                        }
                    )

    def test_explicit_zero_inputs_are_calculated(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_other_comprehensive_income_withholding_tax_krw": 0,
                "prepaid_tax_association_collected_income_tax_krw": 0,
            }
        )
        self.assertTrue(
            result["data_quality"]["other_comprehensive_income_withholding_tax_calculated"]
        )
        self.assertTrue(
            result["data_quality"]["tax_association_collected_income_tax_calculated"]
        )
        self.assertNotIn(
            "other comprehensive-income withholding tax",
            result["rule_context"]["not_calculated"],
        )
        self.assertNotIn(
            "tax association collected income tax",
            result["rule_context"]["not_calculated"],
        )
        self.assertIn("tax association credit", result["rule_context"]["not_calculated"])

    def test_overprepayment_can_make_partial_balance_negative_without_final_refund_claim(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_other_comprehensive_income_withholding_tax_krw": 5_000_000,
            }
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"
            ],
            -800_000,
        )
        self.assertFalse(
            result["data_quality"]["national_income_tax_final_payment_or_refund_calculated"]
        )

    def test_local_income_tax_result_is_unchanged(self):
        base = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=30_000_000)
        )
        with_other = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_other_comprehensive_income_withholding_tax_krw": 1_000_000,
                "prepaid_tax_association_collected_income_tax_krw": 100_000,
            }
        )
        self.assertEqual(
            with_other[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
            base[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
        )

    def test_rule_metadata_is_explicit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_other_comprehensive_income_withholding_tax_krw": 100_000,
                "prepaid_tax_association_collected_income_tax_krw": 50_000,
            }
        )
        quality = result["data_quality"]
        self.assertTrue(
            quality["other_comprehensive_income_withholding_tax_not_inferred_from_income"]
        )
        self.assertTrue(
            quality["tax_association_collected_income_tax_not_inferred_from_income"]
        )
        self.assertFalse(quality["tax_association_credit_calculated"])
        self.assertFalse(
            quality["article76_land_sale_and_special_assessment_prepaid_taxes_calculated"]
        )

        context = result["rule_context"]
        self.assertEqual(context["other_article76_prepaid_tax_verified_on"], "2026-09-27")
        self.assertEqual(
            context["other_withholding_final_return_legal_basis"],
            "소득세법 제76조 제3항 제4호",
        )
        self.assertEqual(
            context["tax_association_final_return_legal_basis"],
            "소득세법 제76조 제3항 제5호",
        )
        self.assertEqual(context["tax_association_collection_legal_basis"], "소득세법 제150조")
        self.assertIn("B-4.9", context["tax_association_credit_note"])
        self.assertIn("자동 추정하지", context["other_article76_prepayment_note"])
        self.assertIn(
            "land-sale scheduled-return prepaid income tax",
            context["not_calculated"],
        )
        self.assertIn(
            "special-assessment prepaid income tax",
            context["not_calculated"],
        )


class OtherArticle76PrepaymentsApiTests(unittest.TestCase):
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

    def test_api_accepts_other_article76_inputs_with_no_store(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_other_comprehensive_income_withholding_tax_krw": 1_000_000,
                "prepaid_tax_association_collected_income_tax_krw": 100_000,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(
            body["article76_other_withholding_and_tax_association_collected_total_krw"],
            1_100_000,
        )
        self.assertEqual(
            body[
                "partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"
            ],
            3_100_000,
        )

    def test_api_accepts_tax_association_credit_with_no_store(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 10_000,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(body["tax_association_credit_krw"], 10_000)
        self.assertEqual(body["tax_association_credit_applied_krw"], 10_000)

    def test_api_rejects_invalid_other_withholding_with_stable_code(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_other_comprehensive_income_withholding_tax_krw": -1,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json()["detail"]["code"],
            "ARTICLE76_OTHER_WITHHOLDING_AMOUNT_INVALID",
        )


if __name__ == "__main__":
    unittest.main()