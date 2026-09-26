"""Phase 10.5B-1 family financial-income risk view.

The statutory financial-income comprehensive-tax threshold is individual, not a
family threshold. This module therefore builds one existing projection per
configured family member and exposes the family sum only as a non-statutory
reference value.

Safety rules:
- configured family display names are the member boundary;
- the aggregate sentinel ``모두`` is never treated as a person;
- unnamed/unconfigured holdings or current-year income records are reported as
  unassigned instead of being silently allocated;
- if any member forecast is unavailable, the projected family reference total
  remains unavailable rather than becoming a misleading partial sum;
- no scenario is persisted and no final tax liability is calculated.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services.dividend_records import (
    get_actual_dividend_summary,
    read_dividend_records,
)
from app.services.portfolio import get_dashboard, read_portfolio
from app.services.tax.financial_income import (
    FinancialIncomeProjectionError,
    build_financial_income_projection,
)
from app.services.web_finance import get_web_dividend_summary

KST = timezone(timedelta(hours=9))
DEFAULT_FAMILY_MEMBERS = ("아빠", "엄마", "자녀")


class FamilyFinancialIncomeRiskError(ValueError):
    """Stable error raised by the family financial-income risk layer."""


def _coerce_day(value: date | datetime | str | None) -> date:
    if value is None:
        return datetime.now(KST).date()
    if isinstance(value, datetime):
        return value.astimezone(KST).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise FamilyFinancialIncomeRiskError(
                "FAMILY_FINANCIAL_INCOME_AS_OF_INVALID"
            ) from exc
    raise FamilyFinancialIncomeRiskError("FAMILY_FINANCIAL_INCOME_AS_OF_INVALID")


def _configured_members(portfolio: dict[str, Any]) -> list[str]:
    raw = (portfolio.get("settings", {}) or {}).get("family_members")
    candidates = raw if isinstance(raw, list) else list(DEFAULT_FAMILY_MEMBERS)
    members: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        name = str(item or "").strip()
        if not name or name == "모두" or name in seen:
            continue
        seen.add(name)
        members.append(name)
    return members


def _account_owner_map(accounts: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for account in accounts:
        if not isinstance(account, dict) or account.get("id") is None:
            continue
        result[str(account["id"])] = str(account.get("owner") or "모두").strip() or "모두"
    return result


def _holding_owner_resolution(
    holding: dict[str, Any], account_owners: dict[str, str]
) -> tuple[str, bool]:
    """Resolve one family owner without allowing double attribution.

    A named holding owner takes precedence only when it agrees with the named
    account owner. Conflicting named owners are treated as ambiguous and are
    excluded from every member projection until the data is corrected.
    """
    direct = str(holding.get("owner") or "").strip()
    account_owner = account_owners.get(str(holding.get("account_id")), "모두")
    direct_named = direct if direct and direct != "모두" else ""
    account_named = account_owner if account_owner and account_owner != "모두" else ""
    if direct_named and account_named and direct_named != account_named:
        return "소유자 충돌", True
    return direct_named or account_named or "모두", False


def _scoped_holdings_for_member(
    holdings: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
    owner: str,
) -> list[dict[str, Any]]:
    account_owners = _account_owner_map(accounts)
    scoped: list[dict[str, Any]] = []
    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        resolved, conflict = _holding_owner_resolution(holding, account_owners)
        if not conflict and resolved == owner:
            scoped.append(holding)
    return scoped


def _unassigned_income_sources(
    *,
    members: list[str],
    holdings: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
    actual_records: list[dict[str, Any]],
    year: int,
) -> dict[str, Any]:
    allowed = set(members)
    account_owners = _account_owner_map(accounts)

    holding_count = 0
    ownership_conflict_count = 0
    record_count = 0
    labels: set[str] = set()

    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        owner, conflict = _holding_owner_resolution(holding, account_owners)
        if conflict:
            holding_count += 1
            ownership_conflict_count += 1
            labels.add("소유자 충돌")
        elif owner not in allowed:
            holding_count += 1
            labels.add(owner or "모두")

    for record in actual_records:
        if not isinstance(record, dict):
            continue
        if not str(record.get("date") or "").startswith(str(year)):
            continue
        owner = str(record.get("owner") or "모두").strip() or "모두"
        if owner not in allowed:
            record_count += 1
            labels.add(owner)

    return {
        "holding_count": holding_count,
        "ownership_conflict_count": ownership_conflict_count,
        "actual_record_count": record_count,
        "owner_labels": sorted(labels),
        "has_unassigned_income_sources": bool(holding_count or record_count),
    }


def _member_risk_row(projection: dict[str, Any]) -> dict[str, Any]:
    projected = projection.get("projected_gross_screening_income_krw")
    use_projected = projected is not None
    threshold_key = "projected_gross_screening" if use_projected else "known_gross_screening"
    thresholds = projection.get("thresholds") or {}
    watch = (thresholds.get("watch") or {}).get(threshold_key)
    comprehensive = (thresholds.get("comprehensive_tax") or {}).get(threshold_key)
    return {
        "owner": str(projection.get("owner") or ""),
        "risk_basis": "projected" if use_projected else "known",
        "risk_amount_krw": projected if use_projected else projection.get(
            "known_gross_screening_income_krw"
        ),
        "actual_cash_income_krw": projection.get("actual_cash_income_krw"),
        "actual_gross_screening_income_krw": projection.get(
            "actual_gross_screening_income_krw"
        ),
        "known_gross_screening_income_krw": projection.get(
            "known_gross_screening_income_krw"
        ),
        "projected_gross_screening_income_krw": projected,
        "forecast_complete": bool(projection.get("forecast_complete")),
        "components": projection.get("components") or {},
        "thresholds": {
            "watch": watch,
            "comprehensive_tax": comprehensive,
        },
        "data_quality": projection.get("data_quality") or {},
        "source_counts": projection.get("source_counts") or {},
    }


def build_family_financial_income_risk(
    projections: list[dict[str, Any]],
    *,
    unassigned: dict[str, Any] | None = None,
    as_of: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Aggregate already-scoped member projections into a family reference view."""
    day = _coerce_day(as_of)
    if not isinstance(projections, list) or not all(
        isinstance(item, dict) for item in projections
    ):
        raise FamilyFinancialIncomeRiskError("FAMILY_FINANCIAL_INCOME_INPUT_INVALID")

    rows = [_member_risk_row(item) for item in projections]
    known_total = 0
    projected_total = 0
    projected_complete = True
    watch_count = 0
    comprehensive_reached_count = 0
    comprehensive_exceeded_count = 0

    for row in rows:
        try:
            known_total += int(round(float(row["known_gross_screening_income_krw"] or 0)))
        except (TypeError, ValueError) as exc:
            raise FamilyFinancialIncomeRiskError(
                "FAMILY_FINANCIAL_INCOME_MEMBER_INVALID"
            ) from exc

        projected = row.get("projected_gross_screening_income_krw")
        if projected is None:
            projected_complete = False
        else:
            try:
                projected_total += int(round(float(projected)))
            except (TypeError, ValueError) as exc:
                raise FamilyFinancialIncomeRiskError(
                    "FAMILY_FINANCIAL_INCOME_MEMBER_INVALID"
                ) from exc

        watch = row["thresholds"].get("watch") or {}
        comprehensive = row["thresholds"].get("comprehensive_tax") or {}
        if watch.get("at_or_above") is True:
            watch_count += 1
        if comprehensive.get("at_or_above") is True:
            comprehensive_reached_count += 1
        if comprehensive.get("exceeded") is True:
            comprehensive_exceeded_count += 1

    unassigned_state = dict(unassigned or {})
    has_unassigned = bool(unassigned_state.get("has_unassigned_income_sources"))
    family_reference_complete = bool(rows) and projected_complete and not has_unassigned

    return {
        "year": day.year,
        "as_of": day.isoformat(),
        "members": rows,
        "member_count": len(rows),
        "risk_summary": {
            "watch_at_or_above_member_count": watch_count,
            "comprehensive_at_or_above_member_count": comprehensive_reached_count,
            "comprehensive_exceeded_member_count": comprehensive_exceeded_count,
            "projected_unavailable_member_count": sum(
                1
                for row in rows
                if row.get("projected_gross_screening_income_krw") is None
            ),
        },
        "family_reference": {
            "known_gross_screening_income_krw": known_total,
            "projected_gross_screening_income_krw": (
                projected_total if projected_complete else None
            ),
            "projected_member_complete": projected_complete,
            "reference_complete": family_reference_complete,
            "reference_only": True,
            "statutory_threshold_applied": False,
            "legal_tax_determination": False,
            "note": "가족 합계는 참고값이며 금융소득 종합과세 기준은 개인별로 판단합니다.",
        },
        "unassigned": unassigned_state,
        "data_quality": {
            "screening_only": True,
            "legal_tax_determination": False,
            "family_total_reference_only": True,
            "individual_thresholds_only": True,
            "future_interest_automatic_forecast_included": False,
        },
    }


async def get_family_financial_income_risk_for_user(
    username: str,
    *,
    as_of: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build all configured family-member projections without persisting anything."""
    day = _coerce_day(as_of)
    raw_portfolio = read_portfolio(username=username)
    members = _configured_members(raw_portfolio)
    dashboard = get_dashboard(data=raw_portfolio, username=username)
    holdings = dashboard.get("holdings", []) or []
    accounts = dashboard.get("accounts", []) or []
    if not isinstance(holdings, list) or not isinstance(accounts, list):
        raise FamilyFinancialIncomeRiskError("FAMILY_FINANCIAL_INCOME_PORTFOLIO_INVALID")

    fx_rate = (dashboard.get("fx_rates", {}) or {}).get("USD", 1385.0)
    actual_records = read_dividend_records(username=username)
    unassigned = _unassigned_income_sources(
        members=members,
        holdings=holdings,
        accounts=accounts,
        actual_records=actual_records,
        year=day.year,
    )

    async def build_one(owner: str) -> dict[str, Any]:
        scoped_holdings = _scoped_holdings_for_member(holdings, accounts, owner)
        forecast = await get_web_dividend_summary(
            scoped_holdings,
            fx_rate=fx_rate,
            username=username,
        )
        actual = get_actual_dividend_summary(
            owner=owner,
            year=str(day.year),
            username=username,
        )
        try:
            projection = build_financial_income_projection(
                actual,
                forecast,
                as_of=day,
                owner=owner,
            )
        except FinancialIncomeProjectionError as exc:
            raise FamilyFinancialIncomeRiskError(str(exc)) from exc
        projection["source_counts"] = {
            "actual_dividend_records": int(actual.get("record_count") or 0),
            "actual_interest_records": int(actual.get("interest_record_count") or 0),
            "forecast_holdings": len(scoped_holdings),
        }
        return projection

    projections = await asyncio.gather(*(build_one(owner) for owner in members))
    result = build_family_financial_income_risk(
        list(projections),
        unassigned=unassigned,
        as_of=day,
    )
    result["configured_members"] = members
    result["source_context"] = {
        "authenticated_user_scoped": True,
        "configured_family_members_source": "portfolio.settings.family_members",
        "manual_adjustments_applied": False,
    }
    return result


__all__ = [
    "FamilyFinancialIncomeRiskError",
    "build_family_financial_income_risk",
    "get_family_financial_income_risk_for_user",
]
