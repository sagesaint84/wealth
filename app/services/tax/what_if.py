"""Stateless Phase 10.5A-3 financial-income What-if orchestration.

This layer combines the verified annual financial-income projection with optional
personal-vs-family-corporation investment-tax screening. It intentionally does
not persist scenarios or turn screening estimates into legal tax determinations.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.financial_income import get_financial_income_projection_for_user
from app.services.tax.high_dividend_2026 import calculate_high_dividend_separate_tax_2026
from app.services.tax.investment_tax import compare_investment_tax_2026
from app.services.tax.investment_tax import rules_2026 as investment_rules
from app.services.tax.rules_2026 import (
    FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    FINANCIAL_INCOME_WATCH_THRESHOLD_KRW,
)


class FinancialIncomeWhatIfError(ValueError):
    """Stable validation error for the stateless What-if layer."""


def _nonnegative(value: object, code: str) -> float:
    if isinstance(value, bool):
        raise FinancialIncomeWhatIfError(code)
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
            "remaining_krw": None,
            "exceeded": None,
            "at_or_above": None,
        }
    return {
        "amount_krw": amount,
        "threshold_krw": threshold,
        "remaining_krw": max(threshold - amount, 0),
        "exceeded": amount > threshold,
        "at_or_above": amount >= threshold,
    }


def _crossed(
    before: dict[str, Any], after: dict[str, Any], *, state_key: str
) -> bool | None:
    before_state = before.get(state_key)
    after_state = after.get(state_key)
    if before_state is None or after_state is None:
        return None
    return (not bool(before_state)) and bool(after_state)


_HIGH_DIVIDEND_SCENARIO_FIELDS = frozenset(
    {
        "special_dividend_income_krw",
        "high_dividend_company_confirmed",
        "separate_taxation_requested",
    }
)


def _high_dividend_special_result(
    scenario: dict[str, Any] | None,
    *,
    additional_dividend_gross_krw: float,
) -> dict[str, Any] | None:
    if scenario is None:
        return None
    if not isinstance(scenario, dict) or set(scenario) - _HIGH_DIVIDEND_SCENARIO_FIELDS:
        raise FinancialIncomeWhatIfError(
            "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_SCENARIO_INVALID"
        )
    amount = _nonnegative(
        scenario.get("special_dividend_income_krw", 0),
        "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_AMOUNT_INVALID",
    )
    if amount > additional_dividend_gross_krw:
        raise FinancialIncomeWhatIfError(
            "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_EXCEEDS_ADDITIONAL_DIVIDEND"
        )
    return calculate_high_dividend_separate_tax_2026(
        amount,
        high_dividend_company_confirmed=scenario.get(
            "high_dividend_company_confirmed", False
        ),
        separate_taxation_requested=scenario.get(
            "separate_taxation_requested", False
        ),
    )


def _trading_impact(
    *,
    foreign_share_realized_gain_krw: float,
    kr_listed_overseas_etf_taxable_gain_krw: float,
) -> dict[str, Any]:
    etf_withholding = (
        kr_listed_overseas_etf_taxable_gain_krw
        * investment_rules.GENERAL_DIVIDEND_WITHHOLDING_RATE
    )
    return {
        "foreign_shares": {
            "realized_gain_krw": _won(foreign_share_realized_gain_krw),
            "financial_income_addition_krw": 0,
            "included_in_financial_income_screening": False,
            "capital_gain_tax_calculated": False,
            "note": (
                "해외주식 실현차익은 금융소득 종합과세 판정에 포함하지 않습니다. "
                "이 빠른 입력만으로는 연간 순손익과 기본공제 사용상태를 확정할 수 없어 "
                "양도소득세는 계산하지 않습니다."
            ),
        },
        "kr_listed_overseas_etf": {
            "taxable_gain_krw": _won(kr_listed_overseas_etf_taxable_gain_krw),
            "financial_income_addition_krw": _won(
                kr_listed_overseas_etf_taxable_gain_krw
            ),
            "included_in_financial_income_screening": True,
            "estimated_withholding_rate": investment_rules.GENERAL_DIVIDEND_WITHHOLDING_RATE,
            "estimated_withholding_krw": _won(etf_withholding),
            "final_tax_calculated": False,
        },
        "screening_only": True,
        "legal_tax_determination": False,
    }



def build_financial_income_what_if(
    baseline_projection: dict[str, Any],
    *,
    additional_dividend_gross_krw: object = 0,
    additional_interest_gross_krw: object = 0,
    additional_foreign_share_realized_gain_krw: object = 0,
    additional_kr_listed_overseas_etf_taxable_gain_krw: object = 0,
    high_dividend_scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply hypothetical extra financial income to an existing projection."""

    if not isinstance(baseline_projection, dict):
        raise FinancialIncomeWhatIfError("FINANCIAL_INCOME_WHAT_IF_BASELINE_INVALID")

    additional_dividend = _nonnegative(
        additional_dividend_gross_krw,
        "FINANCIAL_INCOME_WHAT_IF_DIVIDEND_INVALID",
    )
    additional_interest = _nonnegative(
        additional_interest_gross_krw,
        "FINANCIAL_INCOME_WHAT_IF_INTEREST_INVALID",
    )
    additional_foreign_share_gain = _nonnegative(
        additional_foreign_share_realized_gain_krw,
        "FINANCIAL_INCOME_WHAT_IF_FOREIGN_SHARE_GAIN_INVALID",
    )
    additional_kr_overseas_etf_gain = _nonnegative(
        additional_kr_listed_overseas_etf_taxable_gain_krw,
        "FINANCIAL_INCOME_WHAT_IF_KR_OVERSEAS_ETF_GAIN_INVALID",
    )
    scenario_addition = (
        additional_dividend
        + additional_interest
        + additional_kr_overseas_etf_gain
    )
    trading_impact = _trading_impact(
        foreign_share_realized_gain_krw=additional_foreign_share_gain,
        kr_listed_overseas_etf_taxable_gain_krw=additional_kr_overseas_etf_gain,
    )
    high_dividend_special = _high_dividend_special_result(
        high_dividend_scenario,
        additional_dividend_gross_krw=additional_dividend,
    )
    excluded_from_comprehensive = (
        int(high_dividend_special.get("excluded_from_comprehensive_tax_threshold_krw", 0))
        if high_dividend_special
        else 0
    )

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

    scenario_comprehensive_amount = (
        None
        if scenario_projected is None
        else max(scenario_projected - excluded_from_comprehensive, 0)
    )

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
        scenario_comprehensive_amount, FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
    )

    return {
        "baseline_known_gross_screening_income_krw": baseline_known,
        "baseline_projected_gross_screening_income_krw": baseline_projected,
        "additional_dividend_gross_krw": _won(additional_dividend),
        "additional_interest_gross_krw": _won(additional_interest),
        "additional_foreign_share_realized_gain_krw": _won(
            additional_foreign_share_gain
        ),
        "additional_kr_listed_overseas_etf_taxable_gain_krw": _won(
            additional_kr_overseas_etf_gain
        ),
        "scenario_addition_gross_krw": _won(scenario_addition),
        "trading_impact": trading_impact,
        "scenario_projected_gross_screening_income_krw": scenario_projected,
        "scenario_comprehensive_tax_screening_income_krw": scenario_comprehensive_amount,
        "high_dividend_special_tax": high_dividend_special,
        "thresholds": {
            "watch": {
                "baseline": watch_baseline,
                "scenario": watch_scenario,
                "crossed_by_scenario": _crossed(
                    watch_baseline,
                    watch_scenario,
                    state_key="at_or_above",
                ),
            },
            "comprehensive_tax": {
                "baseline": comprehensive_baseline,
                "scenario": comprehensive_scenario,
                "crossed_by_scenario": _crossed(
                    comprehensive_baseline,
                    comprehensive_scenario,
                    state_key="exceeded",
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
    additional_foreign_share_realized_gain_krw: object = 0,
    additional_kr_listed_overseas_etf_taxable_gain_krw: object = 0,
    high_dividend_scenario: dict[str, Any] | None = None,
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
        additional_foreign_share_realized_gain_krw=(
            additional_foreign_share_realized_gain_krw
        ),
        additional_kr_listed_overseas_etf_taxable_gain_krw=(
            additional_kr_listed_overseas_etf_taxable_gain_krw
        ),
        high_dividend_scenario=high_dividend_scenario,
    )

    result: dict[str, Any] = {
        "owner": owner,
        "baseline_projection": baseline,
        "what_if": what_if,
        "investment_comparison": None,
    }

    if investment_scenario is not None:
        if not isinstance(investment_scenario, dict) or not isinstance(
            investment_scenario.get("asset_type"), str
        ):
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
        # Never trust a client-provided personal baseline. It is always replaced
        # by the authenticated user's scoped projection/known amount.
        compare_kwargs["existing_personal_financial_income_krw"] = (
            personal_financial_income
        )
        comparison = compare_investment_tax_2026(**compare_kwargs)
        comparison["what_if_context"] = {
            "existing_personal_financial_income_source": personal_basis,
            "existing_personal_financial_income_krw": int(
                round(float(personal_financial_income or 0))
            ),
            "server_scoped_from_authenticated_user": True,
            "quick_trading_inputs": {
                "foreign_share_realized_gain_krw": _won(
                    _nonnegative(
                        additional_foreign_share_realized_gain_krw,
                        "FINANCIAL_INCOME_WHAT_IF_FOREIGN_SHARE_GAIN_INVALID",
                    )
                ),
                "kr_listed_overseas_etf_taxable_gain_krw": _won(
                    _nonnegative(
                        additional_kr_listed_overseas_etf_taxable_gain_krw,
                        "FINANCIAL_INCOME_WHAT_IF_KR_OVERSEAS_ETF_GAIN_INVALID",
                    )
                ),
                "server_auto_overwrite": False,
            },
        }
        result["investment_comparison"] = comparison

    return result
