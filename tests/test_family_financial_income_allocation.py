from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.tax.family_financial_income_allocation import (
    FamilyFinancialIncomeAllocationError,
    build_family_financial_income_allocation_simulation,
    get_family_financial_income_allocation_simulation_for_user,
)


_DEFAULT_FUTURE = object()


def member(owner, amount, *, future=_DEFAULT_FUTURE):
    if future is _DEFAULT_FUTURE:
        future = amount

    def state(limit):
        return (
            None
            if amount is None
            else {
                "amount_krw": amount,
                "threshold_krw": limit,
                "at_or_above": amount >= limit,
                "exceeded": amount > limit,
            }
        )

    return {
        "owner": owner,
        "projected_gross_screening_income_krw": amount,
        "components": {
            "current_month_remaining_dividend_gross_adjustment_krw": 0,
            "future_months_estimated_dividend_gross_krw": future,
            "expected_remaining_interest_gross_krw": 0,
        },
        "thresholds": {
            "watch": {"projected_gross_screening": state(10_000_000)},
            "comprehensive_tax": {
                "projected_gross_screening": state(20_000_000)
            },
        },
    }


def baseline(*rows, reference_complete=None, unassigned=None):
    if reference_complete is None:
        reference_complete = all(
            row.get("projected_gross_screening_income_krw") is not None for row in rows
        ) and not bool((unassigned or {}).get("has_unassigned_income_sources"))
    return {
        "year": 2026,
        "as_of": "2026-09-26",
        "members": list(rows),
        "family_reference": {"reference_complete": reference_complete},
        "unassigned": unassigned or {},
    }


class FamilyFinancialIncomeAllocationTests(unittest.IsolatedAsyncioTestCase):
    def test_moves_future_income_recalculates_thresholds_and_preserves_total(self):
        result = build_family_financial_income_allocation_simulation(
            baseline(
                member("아빠", 25_000_000, future=8_000_000),
                member("엄마", 4_000_000, future=1_000_000),
                member("자녀", 1_000_000, future=500_000),
            ),
            allocations=[
                {
                    "from_owner": "아빠",
                    "to_owner": "엄마",
                    "financial_income_gross_krw": 5_000_000,
                },
                {
                    "from_owner": "아빠",
                    "to_owner": "자녀",
                    "financial_income_gross_krw": 3_000_000,
                },
            ],
        )
        rows = {row["owner"]: row for row in result["members"]}
        self.assertEqual(
            rows["아빠"]["after_projected_gross_screening_income_krw"], 17_000_000
        )
        self.assertEqual(
            rows["엄마"]["after_projected_gross_screening_income_krw"], 9_000_000
        )
        self.assertEqual(
            rows["자녀"]["after_projected_gross_screening_income_krw"], 4_000_000
        )
        self.assertEqual(
            rows["아빠"]["allocatable_future_financial_income_krw"], 8_000_000
        )
        self.assertFalse(
            rows["아빠"]["thresholds"]["comprehensive_tax"]["after"][
                "at_or_above"
            ]
        )
        self.assertEqual(
            result["family_reference"][
                "before_projected_gross_screening_income_krw"
            ],
            30_000_000,
        )
        self.assertEqual(
            result["family_reference"]["after_projected_gross_screening_income_krw"],
            30_000_000,
        )
        self.assertTrue(result["family_reference"]["income_conserved"])
        self.assertFalse(result["family_reference"]["statutory_threshold_applied"])

    def test_realized_income_is_not_treated_as_allocatable_future_income(self):
        base = baseline(
            member("아빠", 25_000_000, future=2_000_000),
            member("엄마", 4_000_000, future=1_000_000),
        )
        with self.assertRaisesRegex(
            FamilyFinancialIncomeAllocationError, "SOURCE_AMOUNT_EXCEEDED"
        ):
            build_family_financial_income_allocation_simulation(
                base,
                allocations=[
                    {
                        "from_owner": "아빠",
                        "to_owner": "엄마",
                        "financial_income_gross_krw": 3_000_000,
                    }
                ],
            )

        result = build_family_financial_income_allocation_simulation(
            base,
            allocations=[
                {
                    "from_owner": "아빠",
                    "to_owner": "엄마",
                    "financial_income_gross_krw": 2_000_000,
                }
            ],
        )
        rows = {row["owner"]: row for row in result["members"]}
        self.assertEqual(
            rows["아빠"]["after_projected_gross_screening_income_krw"], 23_000_000
        )
        self.assertEqual(
            result["data_quality"]["allocation_basis"],
            "future_unrealized_financial_income_only",
        )
        self.assertFalse(result["data_quality"]["realized_income_reallocation_allowed"])

    def test_twenty_million_and_invalid_inputs(self):
        result = build_family_financial_income_allocation_simulation(
            baseline(
                member("아빠", 19_000_000, future=0),
                member("엄마", 1_000_000, future=1_000_000),
            ),
            allocations=[
                {
                    "from_owner": "엄마",
                    "to_owner": "아빠",
                    "financial_income_gross_krw": 1_000_000,
                }
            ],
        )
        state = result["members"][0]["thresholds"]["comprehensive_tax"]["after"]
        self.assertTrue(state["at_or_above"])
        self.assertFalse(state["exceeded"])

        base = baseline(member("아빠", 1), member("엄마", 1))
        for allocations in (
            None,
            [
                {
                    "from_owner": "아빠",
                    "to_owner": "엄마",
                    "financial_income_gross_krw": -1,
                }
            ],
            [
                {
                    "from_owner": "아빠",
                    "to_owner": "엄마",
                    "financial_income_gross_krw": float("nan"),
                }
            ],
            [
                {
                    "from_owner": "아빠",
                    "to_owner": "엄마",
                    "financial_income_gross_krw": True,
                }
            ],
            [
                {
                    "from_owner": "아빠",
                    "to_owner": "아빠",
                    "financial_income_gross_krw": 0,
                }
            ],
            [
                {
                    "from_owner": "모두",
                    "to_owner": "엄마",
                    "financial_income_gross_krw": 0,
                }
            ],
            [
                {
                    "from_owner": "없는사람",
                    "to_owner": "엄마",
                    "financial_income_gross_krw": 0,
                }
            ],
        ):
            with self.assertRaises(FamilyFinancialIncomeAllocationError):
                build_family_financial_income_allocation_simulation(
                    base, allocations=allocations
                )

    def test_excess_and_unavailable_are_not_presented_as_complete(self):
        with self.assertRaisesRegex(
            FamilyFinancialIncomeAllocationError, "SOURCE_AMOUNT_EXCEEDED"
        ):
            build_family_financial_income_allocation_simulation(
                baseline(member("아빠", 10, future=1), member("엄마", 0, future=0)),
                allocations=[
                    {
                        "from_owner": "아빠",
                        "to_owner": "엄마",
                        "financial_income_gross_krw": 2,
                    }
                ],
            )
        with self.assertRaisesRegex(
            FamilyFinancialIncomeAllocationError, "SOURCE_FORECAST_UNAVAILABLE"
        ):
            build_family_financial_income_allocation_simulation(
                baseline(member("아빠", None, future=None), member("엄마", 0, future=0)),
                allocations=[
                    {
                        "from_owner": "아빠",
                        "to_owner": "엄마",
                        "financial_income_gross_krw": 1,
                    }
                ],
            )

        result = build_family_financial_income_allocation_simulation(
            baseline(member("아빠", 1), member("엄마", None, future=None)),
            allocations=[],
        )
        self.assertIsNone(
            result["family_reference"]["after_projected_gross_screening_income_krw"]
        )
        self.assertIsNone(result["family_reference"]["income_conserved"])

    def test_incomplete_baseline_family_reference_stays_incomplete(self):
        unassigned = {
            "has_unassigned_income_sources": True,
            "holding_count": 1,
            "owner_labels": ["모두"],
        }
        result = build_family_financial_income_allocation_simulation(
            baseline(
                member("아빠", 5_000_000, future=1_000_000),
                member("엄마", 4_000_000, future=1_000_000),
                reference_complete=False,
                unassigned=unassigned,
            ),
            allocations=[],
        )
        self.assertFalse(result["family_reference"]["reference_complete"])
        self.assertFalse(result["family_reference"]["baseline_reference_complete"])
        self.assertIsNone(
            result["family_reference"]["before_projected_gross_screening_income_krw"]
        )
        self.assertEqual(result["unassigned"], unassigned)

    async def test_user_scope_and_no_persistence(self):
        with patch(
            "app.services.tax.family_financial_income_allocation.get_family_financial_income_risk_for_user",
            new=AsyncMock(
                return_value=baseline(
                    member("아빠", 1, future=1), member("엄마", 0, future=0)
                )
            ),
        ) as risk:
            result = await get_family_financial_income_allocation_simulation_for_user(
                "alice", allocations=[]
            )
        risk.assert_awaited_once_with("alice")
        self.assertTrue(result["source_context"]["authenticated_user_scoped"])
        self.assertFalse(result["source_context"]["persistence_applied"])
