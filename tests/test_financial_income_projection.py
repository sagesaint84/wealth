from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, patch

from app.services.tax.financial_income import (
    FinancialIncomeProjectionError,
    build_financial_income_projection,
    get_financial_income_projection_for_user,
)


def _schedule(values: dict[int, float] | None = None) -> list[dict]:
    values = values or {}
    return [
        {"month": month, "total_krw": values.get(month, 0), "items": []}
        for month in range(1, 13)
    ]


class FinancialIncomeProjectionTests(unittest.TestCase):
    def test_projection_uses_actual_ytd_and_only_future_month_forecast(self):
        actual = {
            "year": "2026",
            "total_actual_dividend_krw": 6_000_000,
            "total_actual_interest_krw": 1_000_000,
        }
        forecast = {
            "monthly_schedule": _schedule(
                {9: 2_000_000, 10: 3_000_000, 11: 4_000_000, 12: 5_000_000}
            )
        }

        result = build_financial_income_projection(
            actual,
            forecast,
            as_of="2026-09-26",
            owner="아빠",
            expected_remaining_interest_krw=200_000,
            current_month_remaining_dividend_krw=500_000,
        )

        self.assertEqual(result["actual_financial_income_krw"], 7_000_000)
        self.assertEqual(result["known_projection_floor_krw"], 7_700_000)
        self.assertEqual(
            result["components"]["future_months_estimated_dividend_krw"],
            12_000_000,
        )
        self.assertEqual(result["projected_financial_income_krw"], 19_700_000)
        self.assertEqual(
            result["forecast_basis"]["included_future_months"], [10, 11, 12]
        )
        self.assertFalse(result["forecast_basis"]["automatic_current_month_included"])
        self.assertEqual(
            result["thresholds"]["comprehensive_tax"]["projected"]["remaining_krw"],
            300_000,
        )
        self.assertFalse(
            result["thresholds"]["comprehensive_tax"]["projected"]["at_or_above"]
        )
        self.assertFalse(result["rule_context"]["tax_liability_calculated"])

    def test_aware_datetime_is_resolved_in_korea_time(self):
        result = build_financial_income_projection(
            {
                "year": "2026",
                "total_actual_dividend_krw": 0,
                "total_actual_interest_krw": 0,
            },
            {"monthly_schedule": _schedule({2: 1000})},
            as_of=datetime(2025, 12, 31, 16, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result["as_of"], "2026-01-01")
        self.assertEqual(result["forecast_basis"]["included_future_months"], [2])
        self.assertEqual(result["projected_financial_income_krw"], 1000)

    def test_unavailable_forecast_never_silently_becomes_zero(self):
        result = build_financial_income_projection(
            {
                "year": "2026",
                "total_actual_dividend_krw": 3_000_000,
                "total_actual_interest_krw": 1_000_000,
            },
            {"unavailable": True, "monthly_schedule": {}},
            as_of="2026-09-26",
            expected_remaining_interest_krw=500_000,
        )

        self.assertFalse(result["projection_complete"])
        self.assertTrue(result["forecast_unavailable"])
        self.assertEqual(result["known_projection_floor_krw"], 4_500_000)
        self.assertIsNone(result["projected_financial_income_krw"])
        self.assertIsNone(
            result["components"]["future_months_estimated_dividend_krw"]
        )
        self.assertIsNone(result["thresholds"]["comprehensive_tax"]["projected"])

    def test_negative_manual_adjustment_is_rejected(self):
        with self.assertRaisesRegex(
            FinancialIncomeProjectionError,
            "FINANCIAL_INCOME_CURRENT_MONTH_ADJUSTMENT_INVALID",
        ):
            build_financial_income_projection(
                {
                    "year": "2026",
                    "total_actual_dividend_krw": 0,
                    "total_actual_interest_krw": 0,
                },
                {"monthly_schedule": _schedule()},
                as_of="2026-09-26",
                current_month_remaining_dividend_krw=-1,
            )

    def test_malformed_available_forecast_fails_closed(self):
        with self.assertRaisesRegex(
            FinancialIncomeProjectionError,
            "FINANCIAL_INCOME_FORECAST_INVALID",
        ):
            build_financial_income_projection(
                {
                    "year": "2026",
                    "total_actual_dividend_krw": 0,
                    "total_actual_interest_krw": 0,
                },
                {
                    "monthly_schedule": [
                        {"month": 10, "total_krw": 1000},
                        {"month": 10, "total_krw": 2000},
                    ]
                },
                as_of="2026-09-26",
            )

    def test_projection_year_must_match_as_of_year(self):
        with self.assertRaisesRegex(
            FinancialIncomeProjectionError,
            "FINANCIAL_INCOME_YEAR_MISMATCH",
        ):
            build_financial_income_projection(
                {
                    "year": "2025",
                    "total_actual_dividend_krw": 0,
                    "total_actual_interest_krw": 0,
                },
                {"monthly_schedule": _schedule()},
                as_of="2026-09-26",
            )

    def test_user_projection_reuses_existing_owner_scoping_and_actual_summary(self):
        dashboard = {
            "holdings": [
                {"id": "h1", "account_id": "a1", "code": "005930"},
                {"id": "h2", "account_id": "a2", "code": "000660"},
                {"id": "h3", "account_id": "a3", "code": "AAPL", "owner": "아빠"},
            ],
            "accounts": [
                {"id": "a1", "owner": "아빠"},
                {"id": "a2", "owner": "엄마"},
                {"id": "a3", "owner": "엄마"},
            ],
            "fx_rates": {"USD": 1400.0},
        }
        actual = {
            "year": "2026",
            "total_actual_dividend_krw": 1000,
            "total_actual_interest_krw": 200,
            "record_count": 2,
            "interest_record_count": 1,
        }
        forecast = {"monthly_schedule": _schedule({10: 3000})}
        forecast_mock = AsyncMock(return_value=forecast)

        with patch("app.services.portfolio.get_dashboard", return_value=dashboard), patch(
            "app.services.dividend_records.get_actual_dividend_summary",
            return_value=actual,
        ) as actual_mock, patch(
            "app.services.web_finance.get_web_dividend_summary",
            forecast_mock,
        ):
            result = asyncio.run(
                get_financial_income_projection_for_user(
                    "alice", owner="아빠", as_of="2026-09-26"
                )
            )

        scoped_holdings = forecast_mock.await_args.args[0]
        self.assertEqual({item["id"] for item in scoped_holdings}, {"h1", "h3"})
        self.assertEqual(forecast_mock.await_args.kwargs["fx_rate"], 1400.0)
        actual_mock.assert_called_once_with(
            owner="아빠", year="2026", username="alice"
        )
        self.assertEqual(result["source_counts"]["forecast_holdings"], 2)
        self.assertEqual(result["source_counts"]["actual_dividend_records"], 2)
        self.assertEqual(result["source_counts"]["actual_interest_records"], 1)
        self.assertEqual(result["projected_financial_income_krw"], 4200)


if __name__ == "__main__":
    unittest.main()
