from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services.tax import calculate_financial_income_article62_comparison_2026
from app.services.tax.personal_comprehensive_tax_2026 import PersonalComprehensiveTaxError
from tests.test_financial_income_article62_comparison import payload
from tests.test_foreign_tax_credit import foreign_item


class TaxAssociationCreditTests(unittest.TestCase):
    def test_absent_input_preserves_existing_result(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=30_000_000)
        )
        self.assertEqual(result["tax_association_credit_krw"], 0)
        self.assertEqual(result["tax_association_credit_applied_krw"], 0)
        self.assertEqual(
            result[
                "article62_tax_after_dividend_and_tax_association_credit_before_foreign_tax_credit_krw"
            ],
            4_200_000,
        )
        self.assertFalse(result["data_quality"]["tax_association_credit_calculated"])
        self.assertIn("tax association credit", result["rule_context"]["not_calculated"])

    def test_explicit_credit_reduces_national_tax_before_foreign_credit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 100_000,
            }
        )
        self.assertEqual(result["tax_association_credit_krw"], 100_000)
        self.assertEqual(result["tax_association_credit_applied_krw"], 100_000)
        self.assertEqual(
            result[
                "article62_tax_after_dividend_and_tax_association_credit_before_foreign_tax_credit_krw"
            ],
            4_100_000,
        )
        self.assertEqual(
            result[
                "article62_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            4_100_000,
        )
        self.assertEqual(
            result["partial_national_income_tax_balance_after_explicit_financial_withholding_krw"],
            4_100_000,
        )

    def test_credit_is_capped_by_available_national_income_tax(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 5_000_000,
            }
        )
        self.assertEqual(result["tax_association_credit_krw"], 5_000_000)
        self.assertEqual(result["tax_association_credit_applied_krw"], 4_200_000)
        self.assertEqual(
            result[
                "tax_association_credit_reduced_by_available_national_income_tax_cap_krw"
            ],
            800_000,
        )
        self.assertEqual(
            result[
                "article62_tax_after_dividend_and_tax_association_credit_before_foreign_tax_credit_krw"
            ],
            0,
        )
        self.assertEqual(
            result["partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"],
            0,
        )

    def test_tax_association_credit_precedes_and_reduces_foreign_tax_credit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 300_000,
                "comprehensive_income_amount_for_foreign_tax_credit_krw": 30_000_000,
                "foreign_tax_credit_items": [
                    foreign_item(
                        limit_basis_foreign_source_income_krw=30_000_000,
                        eligible_current_year_foreign_income_tax_krw=4_200_000,
                    )
                ],
                "no_other_article60_preceding_tax_reductions_or_credits_confirmed": True,
            }
        )
        self.assertEqual(result["tax_association_credit_applied_krw"], 300_000)
        self.assertEqual(result["foreign_tax_credit_country_limit_total_krw"], 4_200_000)
        self.assertEqual(result["foreign_tax_credit_krw"], 3_900_000)
        self.assertEqual(
            result[
                "foreign_tax_credit_reduced_by_available_national_income_tax_cap_krw"
            ],
            300_000,
        )
        self.assertEqual(
            result["uncredited_current_year_foreign_income_tax_total_krw"],
            300_000,
        )
        self.assertEqual(
            result[
                "article62_tax_after_dividend_tax_association_and_foreign_tax_credit_before_other_credits_krw"
            ],
            0,
        )
        self.assertTrue(
            result["data_quality"][
                "foreign_tax_credit_modeled_tax_association_credit_preceded"
            ]
        )

    def test_reduced_national_foreign_credit_reduces_local_foreign_credit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 300_000,
                "comprehensive_income_amount_for_foreign_tax_credit_krw": 30_000_000,
                "foreign_tax_credit_items": [
                    foreign_item(
                        limit_basis_foreign_source_income_krw=30_000_000,
                        eligible_current_year_foreign_income_tax_krw=4_200_000,
                    )
                ],
                "no_other_article60_preceding_tax_reductions_or_credits_confirmed": True,
            }
        )
        self.assertEqual(result["foreign_tax_credit_krw"], 3_900_000)
        self.assertEqual(result["local_foreign_tax_credit_krw"], 390_000)
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            30_000,
        )

    def test_credit_and_tax_association_collected_tax_are_separate_stages(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 100_000,
                "prepaid_tax_association_collected_income_tax_krw": 700_000,
            }
        )
        self.assertEqual(result["tax_association_credit_applied_krw"], 100_000)
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
            4_100_000,
        )
        self.assertEqual(result["prepaid_tax_association_collected_income_tax_krw"], 700_000)
        self.assertEqual(
            result["partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"],
            3_400_000,
        )

    def test_explicit_zero_is_calculated_and_not_inferred(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 0,
            }
        )
        self.assertTrue(result["data_quality"]["tax_association_credit_calculated"])
        self.assertTrue(result["data_quality"]["tax_association_credit_user_provided"])
        self.assertTrue(
            result["data_quality"]["tax_association_credit_not_inferred_from_income_or_rate"]
        )
        self.assertFalse(
            result["data_quality"]["tax_association_credit_statutory_rate_auto_calculated"]
        )
        self.assertNotIn("tax association credit", result["rule_context"]["not_calculated"])

    def test_invalid_credit_amount_is_rejected(self):
        for bad_value in (True, -1, float("nan"), float("inf"), "bad"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE150_TAX_ASSOCIATION_CREDIT_AMOUNT_INVALID",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **{
                            **payload(ordinary_interest_14_krw=30_000_000),
                            "tax_association_credit_krw": bad_value,
                        }
                    )

    def test_rule_metadata_is_explicit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 100_000,
            }
        )
        context = result["rule_context"]
        self.assertEqual(context["tax_association_credit_verified_on"], "2026-09-27")
        self.assertEqual(context["tax_association_credit_legal_basis"], "소득세법 제150조 제3항")
        self.assertEqual(context["tax_association_credit_order_legal_basis"], "소득세법 제60조 제1항")
        self.assertIn("3%", context["tax_association_credit_note"])
        self.assertIn("자동 계산하지 않습니다", context["tax_association_credit_note"])


class TaxAssociationCreditApiTests(unittest.TestCase):
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

    def test_api_accepts_tax_association_credit_with_no_store(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": 100_000,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(body["tax_association_credit_applied_krw"], 100_000)
        self.assertEqual(
            body["partial_national_income_tax_balance_after_explicit_article76_prepayments_krw"],
            4_100_000,
        )

    def test_api_rejects_invalid_credit_with_stable_code(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                "tax_association_credit_krw": -1,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json()["detail"]["code"],
            "ARTICLE150_TAX_ASSOCIATION_CREDIT_AMOUNT_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
