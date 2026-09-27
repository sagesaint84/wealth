from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services.tax import calculate_financial_income_article62_comparison_2026
from app.services.tax.personal_comprehensive_tax_2026 import PersonalComprehensiveTaxError
from tests.test_financial_income_article62_comparison import payload, payload_with_prepaid
from tests.test_foreign_tax_credit import foreign_item


class InterimPrepaymentTests(unittest.TestCase):
    def test_absent_input_keeps_existing_national_partial_balance(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=30_000_000)
        )
        self.assertEqual(result["prepaid_interim_income_tax_krw"], 0)
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_krw"
            ],
        )
        self.assertFalse(
            result["data_quality"]["national_income_tax_interim_prepayment_calculated"]
        )
        self.assertIn(
            "interim prepaid income tax",
            result["rule_context"]["not_calculated"],
        )

    def test_explicit_interim_prepayment_reduces_national_partial_balance(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_interim_income_tax_krw": 1_000_000,
            }
        )
        self.assertEqual(result["prepaid_interim_income_tax_krw"], 1_000_000)
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_krw"
            ],
            4_200_000,
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
            3_200_000,
        )
        self.assertTrue(
            result["data_quality"]["national_income_tax_interim_prepayment_calculated"]
        )
        self.assertNotIn(
            "interim prepaid income tax",
            result["rule_context"]["not_calculated"],
        )

    def test_interim_prepayment_applies_after_financial_withholding(self):
        values = {
            **payload_with_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_income_withholding_tax_krw=2_800_000,
            ),
            "prepaid_interim_income_tax_krw": 1_000_000,
        }
        result = calculate_financial_income_article62_comparison_2026(**values)
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_krw"
            ],
            1_400_000,
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
            400_000,
        )

    def test_interim_prepayment_coexists_with_foreign_tax_credit(self):
        values: dict[str, object] = {
            **payload(ordinary_interest_14_krw=30_000_000),
            "comprehensive_income_amount_for_foreign_tax_credit_krw": 30_000_000,
            "foreign_tax_credit_items": [foreign_item()],
            "no_other_article60_preceding_tax_reductions_or_credits_confirmed": True,
            "prepaid_interim_income_tax_krw": 500_000,
        }
        result = calculate_financial_income_article62_comparison_2026(**values)
        self.assertEqual(result["foreign_tax_credit_krw"], 1_400_000)
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_krw"
            ],
            2_800_000,
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
            2_300_000,
        )

    def test_interim_prepayment_does_not_change_local_income_tax_result(self):
        without_interim = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=30_000_000)
        )
        with_interim = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_interim_income_tax_krw": 1_000_000,
            }
        )
        self.assertEqual(
            with_interim[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
            without_interim[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
        )

    def test_overprepayment_can_make_partial_balance_negative_without_final_refund_claim(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_interim_income_tax_krw": 5_000_000,
            }
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
            -800_000,
        )
        self.assertFalse(
            result["data_quality"]["national_income_tax_final_payment_or_refund_calculated"]
        )

    def test_zero_input_is_explicitly_calculated(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_interim_income_tax_krw": 0,
            }
        )
        self.assertEqual(result["prepaid_interim_income_tax_krw"], 0)
        self.assertTrue(
            result["data_quality"]["national_income_tax_interim_prepayment_calculated"]
        )
        self.assertNotIn(
            "interim prepaid income tax",
            result["rule_context"]["not_calculated"],
        )

    def test_unsafe_amounts_are_rejected(self):
        for bad_value in (True, -1, float("nan"), float("inf"), "bad"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE76_INTERIM_PREPAYMENT_AMOUNT_INVALID",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **{
                            **payload(ordinary_interest_14_krw=30_000_000),
                            "prepaid_interim_income_tax_krw": bad_value,
                        }
                    )

    def test_rule_metadata_is_explicit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **{
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_interim_income_tax_krw": 1_000_000,
            }
        )
        quality = result["data_quality"]
        self.assertTrue(quality["national_income_tax_interim_prepayment_user_provided"])
        self.assertTrue(
            quality["national_income_tax_interim_prepayment_not_inferred_from_prior_year_tax"]
        )
        self.assertFalse(quality["other_article76_prepaid_income_taxes_calculated"])

        context = result["rule_context"]
        self.assertEqual(context["interim_prepaid_income_tax_verified_on"], "2026-09-27")
        self.assertEqual(context["interim_prepayment_legal_basis"], "소득세법 제65조")
        self.assertEqual(
            context["interim_prepayment_final_return_credit_legal_basis"],
            "소득세법 제76조 제3항 제1호",
        )
        self.assertEqual(
            context["interim_prepayment_refund_legal_basis"],
            "소득세법 제85조 제4항",
        )
        self.assertIn("자동 계산하지 않습니다", context["interim_prepayment_note"])
        self.assertIn(
            "other Article 76 prepaid income taxes",
            context["not_calculated"],
        )


class InterimPrepaymentApiTests(unittest.TestCase):
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

    def test_api_accepts_interim_prepayment_with_no_store(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_interim_income_tax_krw": 1_000_000,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(body["prepaid_interim_income_tax_krw"], 1_000_000)
        self.assertEqual(
            body[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
            ],
            3_200_000,
        )

    def test_api_rejects_invalid_interim_prepayment_with_stable_code(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                "prepaid_interim_income_tax_krw": -1,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json()["detail"]["code"],
            "ARTICLE76_INTERIM_PREPAYMENT_AMOUNT_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
