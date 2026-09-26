from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.tax.what_if import (
    FinancialIncomeWhatIfError,
    build_financial_income_what_if,
    get_financial_income_what_if_for_user,
)


class FinancialIncomeWhatIfTests(unittest.IsolatedAsyncioTestCase):
    def test_extra_income_can_cross_comprehensive_threshold(self):
        result = build_financial_income_what_if(
            {
                "known_gross_screening_income_krw": 17_000_000,
                "projected_gross_screening_income_krw": 18_500_000,
            },
            additional_dividend_gross_krw=1_000_000,
            additional_interest_gross_krw=750_000,
        )

        self.assertEqual(result["scenario_addition_gross_krw"], 1_750_000)
        self.assertEqual(
            result["scenario_projected_gross_screening_income_krw"], 20_250_000
        )
        comprehensive = result["thresholds"]["comprehensive_tax"]
        self.assertFalse(comprehensive["baseline"]["exceeded"])
        self.assertTrue(comprehensive["scenario"]["exceeded"])
        self.assertTrue(comprehensive["crossed_by_scenario"])
        self.assertEqual(comprehensive["scenario"]["remaining_krw"], 0)

    def test_exact_twenty_million_is_at_threshold_but_not_exceeded(self):
        result = build_financial_income_what_if(
            {
                "known_gross_screening_income_krw": 19_000_000,
                "projected_gross_screening_income_krw": 19_500_000,
            },
            additional_dividend_gross_krw=500_000,
        )

        scenario = result["thresholds"]["comprehensive_tax"]["scenario"]
        self.assertTrue(scenario["at_or_above"])
        self.assertFalse(scenario["exceeded"])
        self.assertFalse(
            result["thresholds"]["comprehensive_tax"]["crossed_by_scenario"]
        )

    def test_unavailable_projection_stays_unknown(self):
        result = build_financial_income_what_if(
            {
                "known_gross_screening_income_krw": 9_000_000,
                "projected_gross_screening_income_krw": None,
            },
            additional_dividend_gross_krw=5_000_000,
        )

        self.assertIsNone(result["scenario_projected_gross_screening_income_krw"])
        self.assertIsNone(
            result["thresholds"]["comprehensive_tax"]["scenario"]["exceeded"]
        )
        self.assertFalse(result["data_quality"]["scenario_projected_available"])

    def test_negative_extra_income_is_rejected(self):
        with self.assertRaisesRegex(
            FinancialIncomeWhatIfError,
            "FINANCIAL_INCOME_WHAT_IF_DIVIDEND_INVALID",
        ):
            build_financial_income_what_if(
                {
                    "known_gross_screening_income_krw": 0,
                    "projected_gross_screening_income_krw": 0,
                },
                additional_dividend_gross_krw=-1,
            )

    def test_boolean_money_input_is_rejected(self):
        with self.assertRaisesRegex(
            FinancialIncomeWhatIfError,
            "FINANCIAL_INCOME_WHAT_IF_INTEREST_INVALID",
        ):
            build_financial_income_what_if(
                {
                    "known_gross_screening_income_krw": 0,
                    "projected_gross_screening_income_krw": 0,
                },
                additional_interest_gross_krw=True,
            )

    def test_invalid_baseline_is_rejected(self):
        with self.assertRaisesRegex(
            FinancialIncomeWhatIfError,
            "FINANCIAL_INCOME_WHAT_IF_BASELINE_INVALID",
        ):
            build_financial_income_what_if(
                {"projected_gross_screening_income_krw": 1_000_000}
            )

    async def test_investment_comparison_uses_server_scoped_projected_income(self):
        baseline = {
            "known_gross_screening_income_krw": 12_000_000,
            "projected_gross_screening_income_krw": 16_000_000,
        }
        scenario = {
            "asset_type": "us_direct",
            "annual_distribution_krw": 3_000_000,
            "annual_realized_gain_krw": 5_000_000,
            "existing_personal_financial_income_krw": 1,
        }
        comparison = {"comparison": {"screening_only": True}}

        with patch(
            "app.services.tax.what_if.get_financial_income_projection_for_user",
            new=AsyncMock(return_value=baseline),
        ) as projection_mock, patch(
            "app.services.tax.what_if.compare_investment_tax_2026",
            return_value=comparison,
        ) as comparison_mock:
            result = await get_financial_income_what_if_for_user(
                "alice",
                owner="엄마",
                investment_scenario=scenario,
            )

        projection_mock.assert_awaited_once()
        kwargs = comparison_mock.call_args.kwargs
        self.assertEqual(kwargs["existing_personal_financial_income_krw"], 16_000_000)
        self.assertEqual(kwargs["asset_type"], "us_direct")
        context = result["investment_comparison"]["what_if_context"]
        self.assertEqual(
            context["existing_personal_financial_income_source"],
            "projected_gross_screening_income",
        )
        self.assertTrue(context["server_scoped_from_authenticated_user"])

    async def test_investment_comparison_falls_back_to_known_income(self):
        baseline = {
            "known_gross_screening_income_krw": 7_000_000,
            "projected_gross_screening_income_krw": None,
        }
        comparison = {"comparison": {"screening_only": True}}
        with patch(
            "app.services.tax.what_if.get_financial_income_projection_for_user",
            new=AsyncMock(return_value=baseline),
        ), patch(
            "app.services.tax.what_if.compare_investment_tax_2026",
            return_value=comparison,
        ) as comparison_mock:
            result = await get_financial_income_what_if_for_user(
                "alice",
                investment_scenario={
                    "asset_type": "domestic_dividend_stock",
                    "annual_distribution_krw": 1_000_000,
                },
            )

        self.assertEqual(
            comparison_mock.call_args.kwargs["existing_personal_financial_income_krw"],
            7_000_000,
        )
        self.assertEqual(
            result["investment_comparison"]["what_if_context"][
                "existing_personal_financial_income_source"
            ],
            "known_gross_screening_income",
        )

    async def test_invalid_investment_scenario_is_rejected(self):
        baseline = {
            "known_gross_screening_income_krw": 0,
            "projected_gross_screening_income_krw": 0,
        }
        with patch(
            "app.services.tax.what_if.get_financial_income_projection_for_user",
            new=AsyncMock(return_value=baseline),
        ):
            for scenario in ([], {}, {"asset_type": 123}):
                with self.subTest(scenario=scenario):
                    with self.assertRaisesRegex(
                        FinancialIncomeWhatIfError,
                        "FINANCIAL_INCOME_WHAT_IF_INVESTMENT_SCENARIO_INVALID",
                    ):
                        await get_financial_income_what_if_for_user(
                            "alice", investment_scenario=scenario  # type: ignore[arg-type]
                        )


if __name__ == "__main__":
    unittest.main()
