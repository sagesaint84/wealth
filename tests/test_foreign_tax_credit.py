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
from tests.test_financial_income_article62_comparison import (
    payload,
    payload_with_prepaid,
)


_ARTICLE60_CONFIRMATION_FIELD = (
    "no_other_article60_preceding_tax_reductions_or_credits_confirmed"
)


def foreign_item(
    *,
    country_code: object = "US",
    limit_basis_foreign_source_income_krw: object = 10_000_000,
    eligible_current_year_foreign_income_tax_krw: object = 1_500_000,
) -> dict[str, object]:
    return {
        "country_code": country_code,
        "limit_basis_foreign_source_income_krw": (
            limit_basis_foreign_source_income_krw
        ),
        "eligible_current_year_foreign_income_tax_krw": (
            eligible_current_year_foreign_income_tax_krw
        ),
    }


def payload_with_foreign_credit(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        **payload(ordinary_interest_14_krw=30_000_000),
        "comprehensive_income_amount_for_foreign_tax_credit_krw": 30_000_000,
        "foreign_tax_credit_items": [foreign_item()],
        _ARTICLE60_CONFIRMATION_FIELD: True,
    }
    values.update(overrides)
    return values


class ForeignTaxCreditTests(unittest.TestCase):
    def test_absent_foreign_inputs_are_zero_and_not_applied(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=30_000_000)
        )
        self.assertEqual(
            result["comprehensive_income_amount_for_foreign_tax_credit_krw"], 0
        )
        self.assertFalse(result[_ARTICLE60_CONFIRMATION_FIELD])
        self.assertEqual(result["foreign_tax_credit_items"], [])
        self.assertEqual(result["foreign_tax_credit_krw"], 0)
        self.assertEqual(
            result[
                "article62_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            4_200_000,
        )
        self.assertFalse(result["data_quality"]["foreign_tax_credit_calculated"])
        self.assertIn("foreign tax credit", result["rule_context"]["not_calculated"])

    def test_single_country_current_year_credit_is_limited_by_article57_formula(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit()
        )
        self.assertEqual(
            result["article62_comparison_tax_before_credits_krw"], 4_200_000
        )
        self.assertEqual(
            result["foreign_tax_credit_limit_basis_income_total_krw"], 10_000_000
        )
        self.assertEqual(result["foreign_tax_credit_country_limit_total_krw"], 1_400_000)
        self.assertEqual(
            result["eligible_current_year_foreign_income_tax_total_krw"], 1_500_000
        )
        self.assertEqual(result["foreign_tax_credit_krw"], 1_400_000)
        self.assertEqual(
            result["uncredited_current_year_foreign_income_tax_total_krw"], 100_000
        )
        self.assertEqual(
            result[
                "article62_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            2_800_000,
        )
        country = result["foreign_tax_credit_items"][0]
        self.assertEqual(country["country_code"], "US")
        self.assertEqual(country["foreign_tax_credit_limit_krw"], 1_400_000)
        self.assertEqual(
            country["foreign_tax_credit_within_country_limit_krw"], 1_400_000
        )

    def test_foreign_credit_applies_before_explicit_prepaid_withholding(self):
        values: dict[str, object] = {
            **payload_with_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_income_withholding_tax_krw=2_800_000,
            ),
            "comprehensive_income_amount_for_foreign_tax_credit_krw": 30_000_000,
            "foreign_tax_credit_items": [foreign_item()],
            _ARTICLE60_CONFIRMATION_FIELD: True,
        }
        result = calculate_financial_income_article62_comparison_2026(**values)
        self.assertEqual(result["foreign_tax_credit_krw"], 1_400_000)
        self.assertEqual(
            result[
                "article62_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw"
            ],
            2_800_000,
        )
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_krw"
            ],
            0,
        )

    def test_multiple_country_limits_are_calculated_separately(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit(
                foreign_tax_credit_items=[
                    foreign_item(
                        country_code="US",
                        limit_basis_foreign_source_income_krw=5_000_000,
                        eligible_current_year_foreign_income_tax_krw=500_000,
                    ),
                    foreign_item(
                        country_code="JP",
                        limit_basis_foreign_source_income_krw=5_000_000,
                        eligible_current_year_foreign_income_tax_krw=500_000,
                    ),
                ]
            )
        )
        self.assertEqual(result["foreign_tax_credit_country_limit_total_krw"], 1_400_000)
        self.assertEqual(
            result["foreign_tax_credit_within_country_limits_total_krw"], 1_000_000
        )
        self.assertEqual(result["foreign_tax_credit_krw"], 1_000_000)

    def test_sum_of_country_basis_may_exceed_comprehensive_income(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit(
                foreign_tax_credit_items=[
                    foreign_item(
                        country_code="US",
                        limit_basis_foreign_source_income_krw=20_000_000,
                        eligible_current_year_foreign_income_tax_krw=3_000_000,
                    ),
                    foreign_item(
                        country_code="JP",
                        limit_basis_foreign_source_income_krw=20_000_000,
                        eligible_current_year_foreign_income_tax_krw=3_000_000,
                    ),
                ]
            )
        )
        self.assertEqual(
            result["foreign_tax_credit_limit_basis_income_total_krw"], 40_000_000
        )
        self.assertEqual(result["foreign_tax_credit_country_limit_total_krw"], 5_600_000)
        self.assertEqual(
            result["foreign_tax_credit_within_country_limits_total_krw"], 5_600_000
        )
        self.assertEqual(result["foreign_tax_credit_krw"], 4_200_000)
        self.assertEqual(
            result[
                "foreign_tax_credit_reduced_by_available_national_income_tax_cap_krw"
            ],
            1_400_000,
        )

    def test_dividend_credit_is_applied_before_current_year_foreign_credit(self):
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
        self.assertEqual(
            result["article62_comparison_tax_before_credits_krw"], 10_360_000
        )
        self.assertEqual(result["dividend_tax_credit_krw"], 500_000)
        self.assertEqual(
            result["article62_tax_after_dividend_credit_before_other_credits_krw"],
            9_860_000,
        )
        self.assertEqual(result["foreign_tax_credit_country_limit_total_krw"], 10_360_000)
        self.assertEqual(result["foreign_tax_credit_krw"], 9_860_000)
        self.assertEqual(
            result[
                "foreign_tax_credit_reduced_by_available_national_income_tax_cap_krw"
            ],
            500_000,
        )
        self.assertEqual(
            result["uncredited_current_year_foreign_income_tax_total_krw"], 500_000
        )

    def test_unmodeled_article60_preceding_items_fail_closed(self):
        for confirmation in (False, None, 0, 1, "true"):
            with self.subTest(confirmation=confirmation):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE57_OTHER_ARTICLE60_PRECEDING_ITEMS_UNSUPPORTED",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **payload_with_foreign_credit(
                            **{_ARTICLE60_CONFIRMATION_FIELD: confirmation}
                        )
                    )

    def test_foreign_credit_applies_corresponding_local_income_tax_credit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit()
        )
        self.assertEqual(
            result[
                "article93_local_income_tax_after_dividend_credit_before_other_credits_krw"
            ],
            420_000,
        )
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
            280_000,
        )
        self.assertTrue(
            result["data_quality"]["local_income_tax_foreign_tax_credit_calculated"]
        )

    def test_national_foreign_credit_national_prepaid_and_local_prepaid_coexist(self):
        values: dict[str, object] = {
            **payload_with_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_income_withholding_tax_krw=2_800_000,
            ),
            "prepaid_interest_local_income_tax_special_withholding_krw": 420_000,
            "prepaid_dividend_local_income_tax_special_withholding_krw": 0,
            "comprehensive_income_amount_for_foreign_tax_credit_krw": 30_000_000,
            "foreign_tax_credit_items": [foreign_item()],
            _ARTICLE60_CONFIRMATION_FIELD: True,
        }
        result = calculate_financial_income_article62_comparison_2026(**values)
        self.assertEqual(result["foreign_tax_credit_krw"], 1_400_000)
        self.assertEqual(result["local_foreign_tax_credit_krw"], 140_000)
        self.assertEqual(
            result[
                "partial_national_income_tax_balance_after_explicit_financial_withholding_krw"
            ],
            0,
        )
        self.assertEqual(
            result[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
            -140_000,
        )

    def test_foreign_tax_credit_fields_are_all_or_none(self):
        incomplete_payloads = (
            {
                **payload(ordinary_interest_14_krw=30_000_000),
                "comprehensive_income_amount_for_foreign_tax_credit_krw": 30_000_000,
            },
            {
                **payload(ordinary_interest_14_krw=30_000_000),
                "comprehensive_income_amount_for_foreign_tax_credit_krw": 30_000_000,
                "foreign_tax_credit_items": [foreign_item()],
            },
        )
        for values in incomplete_payloads:
            with self.subTest(values=values):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE57_FOREIGN_TAX_CREDIT_INPUTS_INCOMPLETE",
                ):
                    calculate_financial_income_article62_comparison_2026(**values)

    def test_comprehensive_income_amount_must_be_positive_finite_number(self):
        for bad_value in (0, True, -1, float("nan"), float("inf"), "bad"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE57_COMPREHENSIVE_INCOME_AMOUNT_INVALID",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **payload_with_foreign_credit(
                            comprehensive_income_amount_for_foreign_tax_credit_krw=bad_value
                        )
                    )

    def test_foreign_tax_credit_items_fail_closed(self):
        invalid_items = (
            [],
            "bad",
            [{"country_code": "US"}],
            [{**foreign_item(), "unexpected": 1}],
        )
        for bad_value in invalid_items:
            with self.subTest(bad_value=bad_value):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE57_FOREIGN_TAX_CREDIT_ITEMS_INVALID",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **payload_with_foreign_credit(
                            foreign_tax_credit_items=bad_value
                        )
                    )

    def test_foreign_tax_credit_amounts_reject_unsafe_values(self):
        for bad_value in (True, -1, float("nan"), float("inf"), "bad"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE57_FOREIGN_TAX_CREDIT_AMOUNT_INVALID",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **payload_with_foreign_credit(
                            foreign_tax_credit_items=[
                                foreign_item(
                                    eligible_current_year_foreign_income_tax_krw=bad_value
                                )
                            ]
                        )
                    )

    def test_country_codes_are_normalized_and_duplicates_rejected(self):
        normalized = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit(
                foreign_tax_credit_items=[foreign_item(country_code=" us ")]
            )
        )
        self.assertEqual(
            normalized["foreign_tax_credit_items"][0]["country_code"], "US"
        )

        with self.assertRaisesRegex(
            PersonalComprehensiveTaxError,
            "ARTICLE57_FOREIGN_TAX_CREDIT_COUNTRY_DUPLICATE",
        ):
            calculate_financial_income_article62_comparison_2026(
                **payload_with_foreign_credit(
                    foreign_tax_credit_items=[
                        foreign_item(country_code="US"),
                        foreign_item(
                            country_code="us",
                            limit_basis_foreign_source_income_krw=1_000_000,
                            eligible_current_year_foreign_income_tax_krw=100_000,
                        ),
                    ]
                )
            )

    def test_country_code_shape_is_fail_closed(self):
        for bad_value in ("", "USA", "U1", "US KR", True, None):
            with self.subTest(bad_value=bad_value):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE57_FOREIGN_TAX_CREDIT_COUNTRY_CODE_INVALID",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **payload_with_foreign_credit(
                            foreign_tax_credit_items=[
                                foreign_item(country_code=bad_value)
                            ]
                        )
                    )

    def test_each_country_basis_cannot_exceed_comprehensive_income_amount(self):
        with self.assertRaisesRegex(
            PersonalComprehensiveTaxError,
            "ARTICLE57_FOREIGN_TAX_CREDIT_COUNTRY_BASIS_EXCEEDS_COMPREHENSIVE_INCOME",
        ):
            calculate_financial_income_article62_comparison_2026(
                **payload_with_foreign_credit(
                    comprehensive_income_amount_for_foreign_tax_credit_krw=9_999_999
                )
            )

    def test_metadata_keeps_unimplemented_carryforward_and_treaty_checks_explicit(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_foreign_credit()
        )
        quality = result["data_quality"]
        self.assertTrue(quality["foreign_tax_credit_calculated"])
        self.assertTrue(quality["foreign_tax_credit_limit_basis_user_provided"])
        self.assertTrue(quality["foreign_tax_credit_eligibility_user_asserted"])
        self.assertTrue(quality["foreign_tax_credit_article60_scope_confirmed"])
        self.assertFalse(
            quality["foreign_tax_credit_country_code_iso_membership_verified_by_service"]
        )
        self.assertFalse(
            quality["foreign_tax_credit_prior_year_carryforward_calculated"]
        )
        self.assertFalse(quality["foreign_tax_credit_carryforward_calculated"])
        self.assertFalse(
            quality["foreign_tax_credit_carryforward_exclusion_calculated"]
        )
        self.assertFalse(
            quality["foreign_tax_credit_treaty_limit_verified_by_service"]
        )

        context = result["rule_context"]
        self.assertEqual(context["foreign_tax_credit_verified_on"], "2026-09-27")
        self.assertEqual(
            context["foreign_tax_credit_legal_basis"], "소득세법 제57조 제1항"
        )
        self.assertEqual(
            context["foreign_tax_credit_order_legal_basis"], "소득세법 제60조 제1항"
        )
        self.assertNotIn("foreign tax credit", context["not_calculated"])
        self.assertIn(
            "current-year excess foreign tax carryforward determination",
            context["not_calculated"],
        )
        self.assertIn(
            "곧바로 10년 이월공제액으로 표시하지 않습니다",
            context["foreign_tax_credit_note"],
        )


class ForeignTaxCreditApiTests(unittest.TestCase):
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

    def test_api_accepts_foreign_credit_inputs_with_no_store(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload_with_foreign_credit(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json()["foreign_tax_credit_krw"], 1_400_000)

    def test_api_rejects_partial_foreign_credit_input_with_stable_code(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                "foreign_tax_credit_items": [foreign_item()],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json()["detail"]["code"],
            "ARTICLE57_FOREIGN_TAX_CREDIT_INPUTS_INCOMPLETE",
        )

    def test_api_rejects_unconfirmed_article60_scope_with_stable_code(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload_with_foreign_credit(
                **{_ARTICLE60_CONFIRMATION_FIELD: False}
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json()["detail"]["code"],
            "ARTICLE57_OTHER_ARTICLE60_PRECEDING_ITEMS_UNSUPPORTED",
        )

    def test_api_rejects_invalid_country_basis_with_stable_code(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload_with_foreign_credit(
                comprehensive_income_amount_for_foreign_tax_credit_krw=1_000_000
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json()["detail"]["code"],
            "ARTICLE57_FOREIGN_TAX_CREDIT_COUNTRY_BASIS_EXCEEDS_COMPREHENSIVE_INCOME",
        )


if __name__ == "__main__":
    unittest.main()
