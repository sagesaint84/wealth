"""Stateless family financial-income allocation screening simulation.

This feature compares a hypothetical future financial-income allocation between
configured family members.  It does not transfer assets, alter owners, or make
any gift-tax, title-trust, beneficial-ownership, or income-attribution finding.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.family_financial_income import (
    FamilyFinancialIncomeRiskError,
    get_family_financial_income_risk_for_user,
)


class FamilyFinancialIncomeAllocationError(ValueError):
    """Stable error raised for unsafe allocation simulation inputs."""


def _amount(value: object) -> int:
    if isinstance(value, bool):
        raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_AMOUNT_INVALID")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FamilyFinancialIncomeAllocationError(
            "FAMILY_ALLOCATION_AMOUNT_INVALID"
        ) from exc
    if not math.isfinite(number) or number < 0:
        raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_AMOUNT_INVALID")
    return int(round(number))


def _threshold(amount: int | None, before: dict[str, Any] | None) -> dict[str, Any] | None:
    if amount is None or not isinstance(before, dict):
        return None
    threshold = before.get("threshold_krw")
    if isinstance(threshold, bool):
        return None
    try:
        limit = int(round(float(threshold)))
    except (TypeError, ValueError):
        return None
    if limit <= 0:
        return None
    return {
        "amount_krw": amount,
        "threshold_krw": limit,
        "remaining_krw": max(0, limit - amount),
        "at_or_above": amount >= limit,
        "exceeded": amount > limit,
        "progress_percent": round((amount / limit) * 100, 1),
    }


def build_family_financial_income_allocation_simulation(
    baseline: dict[str, Any], *, allocations: object
) -> dict[str, Any]:
    """Apply hypothetical income movements to a family-risk response only."""
    if not isinstance(baseline, dict) or not isinstance(allocations, list):
        raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_REQUEST_INVALID")
    members = baseline.get("members")
    if not isinstance(members, list) or not all(isinstance(row, dict) for row in members):
        raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_BASELINE_INVALID")

    by_owner = {str(row.get("owner") or "").strip(): row for row in members}
    if not all(by_owner) or len(by_owner) != len(members):
        raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_BASELINE_INVALID")
    deltas = {owner: 0 for owner in by_owner}
    outgoing = {owner: 0 for owner in by_owner}
    normalized: list[dict[str, Any]] = []
    for item in allocations:
        if not isinstance(item, dict) or set(item) != {
            "from_owner", "to_owner", "financial_income_gross_krw"
        }:
            raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_REQUEST_INVALID")
        source, destination = item.get("from_owner"), item.get("to_owner")
        if not isinstance(source, str) or not isinstance(destination, str):
            raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_OWNER_INVALID")
        source, destination = source.strip(), destination.strip()
        if not source or not destination or source == "모두" or destination == "모두":
            raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_OWNER_INVALID")
        if source == destination:
            raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_SAME_OWNER")
        if source not in by_owner or destination not in by_owner:
            raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_OWNER_INVALID")
        amount = _amount(item.get("financial_income_gross_krw"))
        outgoing[source] += amount
        deltas[source] -= amount
        deltas[destination] += amount
        normalized.append({
            "from_owner": source,
            "to_owner": destination,
            "financial_income_gross_krw": amount,
        })

    for owner, total in outgoing.items():
        before = by_owner[owner].get("projected_gross_screening_income_krw")
        if total and before is None:
            raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_SOURCE_FORECAST_UNAVAILABLE")
        if before is not None and total > int(round(float(before))):
            raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_SOURCE_AMOUNT_EXCEEDED")

    rows = []
    complete = True
    before_total = 0
    after_total = 0
    for owner, before_row in by_owner.items():
        before = before_row.get("projected_gross_screening_income_krw")
        if before is None:
            complete = False
            after = None
        else:
            before = int(round(float(before)))
            after = before + deltas[owner]
            before_total += before
            after_total += after
        thresholds = before_row.get("thresholds") or {}
        rows.append({
            "owner": owner,
            "before_projected_gross_screening_income_krw": before,
            "after_projected_gross_screening_income_krw": after,
            "difference_gross_screening_income_krw": deltas[owner],
            "forecast_complete": before is not None,
            "thresholds": {
                "watch": {
                    "before": (thresholds.get("watch") or {}).get("projected_gross_screening"),
                    "after": _threshold(after, (thresholds.get("watch") or {}).get("projected_gross_screening")),
                },
                "comprehensive_tax": {
                    "before": (thresholds.get("comprehensive_tax") or {}).get("projected_gross_screening"),
                    "after": _threshold(after, (thresholds.get("comprehensive_tax") or {}).get("projected_gross_screening")),
                },
            },
        })
    return {
        "year": baseline.get("year"), "as_of": baseline.get("as_of"),
        "allocations": normalized, "members": rows,
        "family_reference": {
            "before_projected_gross_screening_income_krw": before_total if complete else None,
            "after_projected_gross_screening_income_krw": after_total if complete else None,
            "income_conserved": True if complete else None,
            "reference_complete": complete,
            "reference_only": True, "statutory_threshold_applied": False,
            "note": "가족 합계는 참고값이며 금융소득 종합과세 기준은 개인별로 판단합니다.",
        },
        "data_quality": {
            "screening_only": True, "legal_tax_determination": False,
            "stateless": True, "individual_thresholds_only": True,
            "family_total_reference_only": True,
            "legal_tax_notice": "이 결과는 금융소득 배분 가정에 따른 screening 비교이며, 실제 증여·명의·소득 귀속의 법률/세무 판단을 포함하지 않습니다.",
        },
    }


async def get_family_financial_income_allocation_simulation_for_user(
    username: str, *, allocations: object
) -> dict[str, Any]:
    if not isinstance(allocations, list):
        raise FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_REQUEST_INVALID")
    try:
        baseline = await get_family_financial_income_risk_for_user(username)
    except FamilyFinancialIncomeRiskError as exc:
        raise FamilyFinancialIncomeAllocationError(str(exc)) from exc
    result = build_family_financial_income_allocation_simulation(baseline, allocations=allocations)
    result["source_context"] = {
        "authenticated_user_scoped": True,
        "configured_family_members_source": "portfolio.settings.family_members",
        "persistence_applied": False,
    }
    return result


__all__ = [
    "FamilyFinancialIncomeAllocationError",
    "build_family_financial_income_allocation_simulation",
    "get_family_financial_income_allocation_simulation_for_user",
]
