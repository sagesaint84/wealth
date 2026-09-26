from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.tax.family_financial_income import (
    build_family_financial_income_risk,
    get_family_financial_income_risk_for_user,
)


def projection(
    owner: str,
    projected: int | None,
    *,
    known: int = 0,
    watch_at_or_above: bool = False,
    comprehensive_at_or_above: bool = False,
    comprehensive_exceeded: bool = False,
) -> dict:
    return {
        "owner": owner,
        "forecast_complete": projected is not None,
        "actual_cash_income_krw": 0,
        "actual_gross_screening_income_krw": known,
        "known_gross_screening_income_krw": known,
        "projected_gross_screening_income_krw": projected,
        "components": {},
        "data_quality": {"screening_only": True},
        "source_counts": {},
        "thresholds": {
            "watch": {
                "projected_gross_screening": (
                    None
                    if projected is None
                    else {"at_or_above": watch_at_or_above, "exceeded": False}
                ),
                "known_gross_screening": {
                    "at_or_above": known >= 10_000_000,
                    "exceeded": known > 10_000_000,
                },
            },
            "comprehensive_tax": {
                "projected_gross_screening": (
                    None
                    if projected is None
                    else {
                        "at_or_above": comprehensive_at_or_above,
                        "exceeded": comprehensive_exceeded,
                    }
                ),
                "known_gross_screening": {
                    "at_or_above": known >= 20_000_000,
                    "exceeded": known > 20_000_000,
                },
            },
        },
    }


class FamilyFinancialIncomeRiskBuilderTests(unittest.TestCase):
    def test_family_total_is_reference_only_and_has_no_statutory_threshold(self):
        result = build_family_financial_income_risk(
            [
                projection("아빠", 15_000_000, watch_at_or_above=True),
                projection("엄마", 12_000_000, watch_at_or_above=True),
            ],
            as_of="2026-09-26",
        )

        self.assertEqual(
            result["family_reference"]["projected_gross_screening_income_krw"],
            27_000_000,
        )
        self.assertTrue(result["family_reference"]["reference_only"])
        self.assertFalse(result["family_reference"]["statutory_threshold_applied"])
        self.assertEqual(
            result["risk_summary"]["comprehensive_at_or_above_member_count"], 0
        )

    def test_exact_twenty_million_is_reached_but_not_exceeded(self):
        result = build_family_financial_income_risk(
            [
                projection(
                    "아빠",
                    20_000_000,
                    watch_at_or_above=True,
                    comprehensive_at_or_above=True,
                    comprehensive_exceeded=False,
                )
            ],
            as_of="2026-09-26",
        )

        member = result["members"][0]
        self.assertTrue(member["thresholds"]["comprehensive_tax"]["at_or_above"])
        self.assertFalse(member["thresholds"]["comprehensive_tax"]["exceeded"])
        self.assertEqual(
            result["risk_summary"]["comprehensive_at_or_above_member_count"], 1
        )
        self.assertEqual(
            result["risk_summary"]["comprehensive_exceeded_member_count"], 0
        )

    def test_unavailable_member_makes_family_projected_total_unavailable(self):
        result = build_family_financial_income_risk(
            [projection("아빠", 5_000_000), projection("엄마", None, known=2_000_000)],
            as_of="2026-09-26",
        )

        self.assertIsNone(
            result["family_reference"]["projected_gross_screening_income_krw"]
        )
        self.assertFalse(result["family_reference"]["projected_member_complete"])
        self.assertEqual(result["risk_summary"]["projected_unavailable_member_count"], 1)
        self.assertEqual(
            result["members"][1]["risk_basis"],
            "known",
        )

    def test_unassigned_income_sources_mark_reference_incomplete(self):
        result = build_family_financial_income_risk(
            [projection("아빠", 5_000_000)],
            unassigned={
                "holding_count": 1,
                "actual_record_count": 2,
                "owner_labels": ["모두"],
                "has_unassigned_income_sources": True,
            },
            as_of="2026-09-26",
        )

        self.assertFalse(result["family_reference"]["reference_complete"])
        self.assertTrue(result["unassigned"]["has_unassigned_income_sources"])


class FamilyFinancialIncomeRiskOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_configured_member_order_and_keeps_unassigned_separate(self):
        raw = {
            "settings": {"family_members": ["엄마", "아빠"]},
            "accounts": [
                {"id": "a1", "owner": "엄마"},
                {"id": "a2", "owner": "아빠"},
                {"id": "a3", "owner": "모두"},
            ],
            "holdings": [],
        }
        dashboard = {
            "accounts": raw["accounts"],
            "holdings": [
                {"code": "AAA", "account_id": "a1", "quantity": 1},
                {"code": "BBB", "account_id": "a2", "quantity": 1},
                {"code": "CCC", "account_id": "a3", "quantity": 1},
            ],
            "fx_rates": {"USD": 1400.0},
        }
        actual_records = [
            {"date": "2026-01-01", "owner": "모두", "amount_krw": 1000},
        ]

        async def forecast_for(scoped, **_kwargs):
            total = 3_000_000 if scoped and scoped[0]["code"] == "AAA" else 4_000_000
            return {
                "monthly_schedule": [
                    {"month": month, "total_krw": total if month == 12 else 0}
                    for month in range(1, 13)
                ]
            }

        def actual_for(owner, **_kwargs):
            amount = 1_000_000 if owner == "엄마" else 2_000_000
            return {
                "year": "2026",
                "total_actual_dividend_krw": amount,
                "total_actual_interest_krw": 0,
                "record_count": 0,
                "interest_record_count": 0,
                "records": [],
                "interest_records": [],
            }

        with (
            patch(
                "app.services.tax.family_financial_income.read_portfolio",
                return_value=raw,
            ),
            patch(
                "app.services.tax.family_financial_income.get_dashboard",
                return_value=dashboard,
            ),
            patch(
                "app.services.tax.family_financial_income.read_dividend_records",
                return_value=actual_records,
            ),
            patch(
                "app.services.tax.family_financial_income.get_actual_dividend_summary",
                side_effect=actual_for,
            ),
            patch(
                "app.services.tax.family_financial_income.get_web_dividend_summary",
                new=AsyncMock(side_effect=forecast_for),
            ) as web_mock,
        ):
            result = await get_family_financial_income_risk_for_user(
                "user_a", as_of="2026-09-26"
            )

        self.assertEqual(result["configured_members"], ["엄마", "아빠"])
        self.assertEqual([row["owner"] for row in result["members"]], ["엄마", "아빠"])
        self.assertEqual(web_mock.await_count, 2)
        self.assertEqual(result["unassigned"]["holding_count"], 1)
        self.assertEqual(result["unassigned"]["actual_record_count"], 1)
        self.assertNotIn("모두", result["configured_members"])
        self.assertFalse(result["family_reference"]["reference_complete"])

    async def test_no_writes_or_manual_adjustments_are_applied(self):
        raw = {
            "settings": {"family_members": ["아빠"]},
            "accounts": [],
            "holdings": [],
        }
        dashboard = {"accounts": [], "holdings": [], "fx_rates": {"USD": 1400.0}}
        actual = {
            "year": "2026",
            "total_actual_dividend_krw": 0,
            "total_actual_interest_krw": 0,
            "record_count": 0,
            "interest_record_count": 0,
            "records": [],
            "interest_records": [],
        }
        forecast = {
            "monthly_schedule": [
                {"month": month, "total_krw": 0} for month in range(1, 13)
            ]
        }

        with (
            patch(
                "app.services.tax.family_financial_income.read_portfolio",
                return_value=raw,
            ),
            patch(
                "app.services.tax.family_financial_income.get_dashboard",
                return_value=dashboard,
            ),
            patch(
                "app.services.tax.family_financial_income.read_dividend_records",
                return_value=[],
            ),
            patch(
                "app.services.tax.family_financial_income.get_actual_dividend_summary",
                return_value=actual,
            ),
            patch(
                "app.services.tax.family_financial_income.get_web_dividend_summary",
                new=AsyncMock(return_value=forecast),
            ),
        ):
            result = await get_family_financial_income_risk_for_user(
                "user_a", as_of="2026-09-26"
            )

        self.assertFalse(result["source_context"]["manual_adjustments_applied"])
        self.assertTrue(result["source_context"]["authenticated_user_scoped"])
        self.assertEqual(
            result["family_reference"]["projected_gross_screening_income_krw"], 0
        )


if __name__ == "__main__":
    unittest.main()
