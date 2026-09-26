from __future__ import annotations

import math
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


_LOCAL_INTEREST_FIELD = (
    "prepaid_interest_local_income_tax_special_withholding_krw"
)
_LOCAL_DIVIDEND_FIELD = (
    "prepaid_dividend_local_income_tax_special_withholding_krw"
)


def payload_with_local_prepaid(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        **payload(),
        _LOCAL_INTEREST_FIELD: 0,
        _LOCAL_DIVIDEND_FIELD: 0,
    }
    values.update(overrides)
    return values


def payload_with_national_and_local_prepaid(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        **payload_with_prepaid(),
        _LOCAL_INTEREST_FIELD: 0,
        _LOCAL_DIVIDEND_FIELD: 0,
    }
    values.update(overrides)
    return values


class LocalPrepaidSpecialWithholdingTests(unittest.TestCase):
    def test_absent_local_prepaid_inputs_are_zero_and_not_applied(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload(ordinary_interest_14_krw=30_000_000)
        )
        self.assertEqual(result[_LOCAL_INTEREST_FIELD], 0)
        self.assertEqual(result[_LOCAL_DIVIDEND_FIELD], 0)
        self.assertEqual(
            result["prepaid_financial_local_income_tax_special_withholding_total_krw"],
            0,
        )
        self.assertEqual(
            result[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
            420_000,
        )
        quality = result["data_quality"]
        self.assertFalse(
            quality["local_income_tax_prepaid_special_withholding_calculated"]
        )
        self.assertFalse(
            quality["local_income_tax_prepaid_special_withholding_inputs_provided"]
        )
        self.assertIn(
            "local prepaid special withholding tax",
            result["rule_context"]["not_calculated"],
        )

    def test_explicit_interest_local_special_withholding_is_subtracted(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_local_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_local_income_tax_special_withholding_krw=420_000,
            )
        )
        self.assertEqual(
            result["article93_local_income_tax_after_dividend_credit_before_other_credits_krw"],
            420_000,
        )
        self.assertEqual(
            result["prepaid_financial_local_income_tax_special_withholding_total_krw"],
            420_000,
        )
        self.assertEqual(
            result[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
            0,
        )
        quality = result["data_quality"]
        self.assertTrue(
            quality["local_income_tax_prepaid_special_withholding_calculated"]
        )
        self.assertTrue(
            quality["local_income_tax_prepaid_special_withholding_user_provided"]
        )
        self.assertTrue(
            quality[
                "local_income_tax_prepaid_special_withholding_not_inferred_from_national_withholding"
            ]
        )
        self.assertNotIn(
            "local prepaid special withholding tax",
            result["rule_context"]["not_calculated"],
        )

    def test_national_and_local_prepaid_inputs_are_independent(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_national_and_local_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_income_withholding_tax_krw=4_200_000,
                prepaid_interest_local_income_tax_special_withholding_krw=420_000,
            )
        )
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
            0,
        )

    def test_negative_partial_local_balance_is_allowed_but_not_final_refund(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_local_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_local_income_tax_special_withholding_krw=500_000,
            )
        )
        self.assertEqual(
            result[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
            -80_000,
        )
        self.assertFalse(
            result["data_quality"]["local_income_tax_final_payment_or_refund_calculated"]
        )
        self.assertIn(
            "final local income-tax payment or refund amount",
            result["rule_context"]["not_calculated"],
        )

    def test_local_prepaid_fields_are_all_or_none(self):
        with self.assertRaisesRegex(
            PersonalComprehensiveTaxError,
            "ARTICLE93_LOCAL_PREPAID_WITHHOLDING_INPUTS_INCOMPLETE",
        ):
            calculate_financial_income_article62_comparison_2026(
                **{
                    **payload(ordinary_interest_14_krw=30_000_000),
                    _LOCAL_INTEREST_FIELD: 420_000,
                }
            )

    def test_local_prepaid_values_reject_unsafe_amounts(self):
        for bad_value in (True, -1, float("nan"), float("inf"), "bad"):
            with self.subTest(bad_value=bad_value):
                with self.assertRaisesRegex(
                    PersonalComprehensiveTaxError,
                    "ARTICLE93_LOCAL_PREPAID_WITHHOLDING_AMOUNT_INVALID",
                ):
                    calculate_financial_income_article62_comparison_2026(
                        **payload_with_local_prepaid(
                            ordinary_interest_14_krw=30_000_000,
                            prepaid_interest_local_income_tax_special_withholding_krw=(
                                bad_value
                            ),
                        )
                    )

    def test_local_prepaid_rejects_below_threshold_readdition(self):
        with self.assertRaisesRegex(
            PersonalComprehensiveTaxError,
            "ARTICLE93_LOCAL_PREPAID_WITHHOLDING_BELOW_THRESHOLD_INVALID",
        ):
            calculate_financial_income_article62_comparison_2026(
                **payload_with_local_prepaid(
                    ordinary_interest_14_krw=20_000_000,
                    prepaid_interest_local_income_tax_special_withholding_krw=280_000,
                )
            )

    def test_zero_local_prepaid_pair_is_allowed_at_threshold(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_local_prepaid(ordinary_interest_14_krw=20_000_000)
        )
        self.assertFalse(result["financial_income_threshold"]["exceeded"])
        self.assertEqual(
            result["prepaid_financial_local_income_tax_special_withholding_total_krw"],
            0,
        )
        self.assertTrue(
            result["data_quality"][
                "local_income_tax_prepaid_special_withholding_inputs_provided"
            ]
        )

    def test_generic_local_prepaid_field_remains_rejected(self):
        with self.assertRaisesRegex(
            PersonalComprehensiveTaxError,
            "ARTICLE62_REQUEST_INVALID",
        ):
            calculate_financial_income_article62_comparison_2026(
                **{
                    **payload(ordinary_interest_14_krw=30_000_000),
                    "prepaid_local_income_tax_krw": 420_000,
                }
            )

    def test_local_prepaid_metadata_has_current_official_bases(self):
        result = calculate_financial_income_article62_comparison_2026(
            **payload_with_local_prepaid(ordinary_interest_14_krw=30_000_000)
        )
        context = result["rule_context"]
        self.assertEqual(
            context["local_prepaid_special_withholding_verified_on"],
            "2026-09-27",
        )
        self.assertEqual(
            context["local_prepaid_special_withholding_credit_legal_basis"],
            "지방세법 제95조 제3항 제4호",
        )
        self.assertEqual(
            context["local_special_withholding_duty_legal_basis"],
            "지방세법 제103조의13",
        )
        self.assertIn("자동 추정하지 않습니다", context["local_prepaid_special_withholding_note"])


class LocalPrepaidSpecialWithholdingApiTests(unittest.TestCase):
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

    def test_api_accepts_explicit_local_prepaid_pair_with_no_store(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload_with_local_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_local_income_tax_special_withholding_krw=420_000,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(
            body["prepaid_financial_local_income_tax_special_withholding_total_krw"],
            420_000,
        )
        self.assertEqual(
            body[
                "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw"
            ],
            0,
        )

    def test_api_rejects_partial_local_prepaid_pair(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload(ordinary_interest_14_krw=30_000_000),
                _LOCAL_INTEREST_FIELD: 420_000,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json()["detail"]["code"],
            "ARTICLE93_LOCAL_PREPAID_WITHHOLDING_INPUTS_INCOMPLETE",
        )

    def test_api_rejects_below_threshold_local_prepaid(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload_with_local_prepaid(
                ordinary_interest_14_krw=20_000_000,
                prepaid_interest_local_income_tax_special_withholding_krw=280_000,
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json()["detail"]["code"],
            "ARTICLE93_LOCAL_PREPAID_WITHHOLDING_BELOW_THRESHOLD_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
