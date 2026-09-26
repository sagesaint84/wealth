"""Stateless Phase 10.5A-3 financial-income What-if orchestration.

This layer combines the verified annual financial-income projection with optional
personal-vs-family-corporation investment-tax screening.  It intentionally does
not persist scenarios or turn screening estimates into legal tax determinations.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.financial_income import get_financial_income_projection_for_user
from app.services.tax.investment_tax import compare_investment_tax_2026
from app.services.tax.rules_2026 import (
    FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    FINANCIAL_INCOME_WATCH_THRESHOLD_KRW,
)


class FinancialIncomeWhatIfError(ValueError):
    """Stable validation error for the stateless What-if layer."""


def _nonnegative(value: object, code: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FinancialIncomeWhatIfError(code) from exc
    if not math.isfinite(number) or number < 0:
        raise FinancialIncomeWhatIfError(code)
    return number


def _won(value: float) -> int:
    return int(round(value))


def _threshold_state(amount: int | None, threshold: int) -> dict[str, Any]:
    if amount is None:
        return {
            "amount_krw": None,
            "threshold_krw": threshold,
            "reached": None,
            "remaining_krw": None,
        }
    return {
        "amount_krw": amount,
        "threshold_krw": threshold,
        "reached": amount >= threshold,
        "remaining_krw": max(threshold - amount, 0),
    }


def build_financial_income_what_if(
    baseline_projection: dict[str, Any],
    *,
    additional_dividend_gross_krw: object = 0,
    additional_interest_gross_krw: object = 0,
) -> dict[str, Any]:
    """Apply hypothetical extra financial income to an existing projection."""

    additional_dividend = _nonnegative(
        additional_dividend_gross_krw,
        "FINANCIAL_INCOME_WHAT_IF_DIVIDEND_INVALID",
    )
    additional_interest = _nonnegative(
        additional_interest_gross_krw,
        "FINANCIAL_INCOME_WHAT_IF_INTEREST_INVALID",
    )
    scenario_addition = additional_dividend + additional_interest

    try:
        baseline_known = int(
            round(float(baseline_projection["known_gross_screening_income_krw"]))
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FinancialIncomeWhatIfError(
            "FINANCIAL_INCOME_WHAT_IF_BASELINE_INVALID"
        ) from exc

    raw_projected = baseline_projection.get("projected_gross_screening_income_krw")
    if raw_projected is None:
        baseline_projected: int | None = None
        scenario_projected: int | None = None
    else:
        try:
            baseline_projected = int(round(float(raw_projected)))
        except (TypeError, ValueError) as exc:
            raise FinancialIncomeWhatIfError(
                "FINANCIAL_INCOME_WHAT_IF_BASELINE_INVALID"
            ) from exc
        scenario_projected = _won(baseline_projected + scenario_addition)

    watch_baseline = _threshold_state(
        baseline_projected, FINANCIAL_INCOME_WATCH_THRESHOLD_KRW
    )
    watch_scenario = _threshold_state(
        scenario_projected, FINANCIAL_INCOME_WATCH_THRESHOLD_KRW
    )
    comprehensive_baseline = _threshold_state(
        baseline_projected, FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
    )
    comprehensive_scenario = _threshold_state(
        scenario_projected, FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
    )

    def _crossed(before: dict[str, Any], after: dict[str, Any]) -> bool | None:
        if before["reached"] is None or after["reached"] is None:
            return None
        return (not before["reached"]) and bool(after["reached"])

    return {
        "baseline_known_gross_screening_income_krw": baseline_known,
        "baseline_projected_gross_screening_income_krw": baseline_projected,
        "additional_dividend_gross_krw": _won(additional_dividend),
        "additional_interest_gross_krw": _won(additional_interest),
        "scenario_addition_gross_krw": _won(scenario_addition),
        "scenario_projected_gross_screening_income_krw": scenario_projected,
        "thresholds": {
            "watch": {
                "baseline": watch_baseline,
                "scenario": watch_scenario,
                "crossed_by_scenario": _crossed(watch_baseline, watch_scenario),
            },
            "comprehensive_tax": {
                "baseline": comprehensive_baseline,
                "scenario": comprehensive_scenario,
                "crossed_by_scenario": _crossed(
                    comprehensive_baseline, comprehensive_scenario
                ),
                "screening_only": True,
                "legal_tax_determination": False,
            },
        },
        "data_quality": {
            "screening_only": True,
            "legal_tax_determination": False,
            "scenario_projected_available": scenario_projected is not None,
        },
    }


async def get_financial_income_what_if_for_user(
    username: str,
    *,
    owner: str = "모두",
    expected_remaining_interest_gross_krw: object = 0,
    current_month_remaining_dividend_gross_krw: object = 0,
    additional_dividend_gross_krw: object = 0,
    additional_interest_gross_krw: object = 0,
    investment_scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a user-scoped financial-income What-if response without writes."""

    baseline = await get_financial_income_projection_for_user(
        username,
        owner=owner,
        expected_remaining_interest_gross_krw=expected_remaining_interest_gross_krw,
        current_month_remaining_dividend_gross_krw=current_month_remaining_dividend_gross_krw,
    )
    what_if = build_financial_income_what_if(
        baseline,
        additional_dividend_gross_krw=additional_dividend_gross_krw,
        additional_interest_gross_krw=additional_interest_gross_krw,
    )

    result: dict[str, Any] = {
        "owner": owner,
        "baseline_projection": baseline,
        "what_if": what_if,
        "investment_comparison": None,
    }

    if investment_scenario is not None:
        if not isinstance(investment_scenario, dict):
            raise FinancialIncomeWhatIfError(
                "FINANCIAL_INCOME_WHAT_IF_INVESTMENT_SCENARIO_INVALID"
            )

        projected = baseline.get("projected_gross_screening_income_krw")
        if projected is None:
            personal_financial_income = baseline.get(
                "known_gross_screening_income_krw", 0
            )
            personal_basis = "known_gross_screening_income"
        else:
            personal_financial_income = projected
            personal_basis = "projected_gross_screening_income"

        compare_kwargs = dict(investment_scenario)
        compare_kwargs["existing_personal_financial_income_krw"] = (
            personal_financial_income
        )
        comparison = compare_investment_tax_2026(**compare_kwargs)
        comparison.setdefault("data_quality", {})
        comparison["what_if_context"] = {
            "existing_personal_financial_income_source": personal_basis,
            "existing_personal_financial_income_krw": int(
                round(float(personal_financial_income or 0))
            ),
            "server_scoped_from_authenticated_user": True,
        }
        result["investment_comparison"] = comparison

    return result
