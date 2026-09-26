"""Financial-income projection for Phase 10.5A.

The projection deliberately combines authoritative realized records with only
future-month dividend estimates. It never subtracts YTD realized dividends from
an annual forward estimate because current holdings may differ from holdings
that produced earlier realized income.

Current-month forecast is excluded by default to avoid double counting against
realized records. A caller may supply an explicit current-month remaining
adjustment when it has better information.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
from typing import Any

from app.services.tax.rules_2026 import (
    FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    FINANCIAL_INCOME_WATCH_THRESHOLD_KRW,
    OFFICIAL_SOURCE_URL,
    RULE_VERIFIED_ON,
    RULE_YEAR,
)

KST = timezone(timedelta(hours=9))


class FinancialIncomeProjectionError(ValueError):
    """Raised when projection inputs are unsafe or internally inconsistent."""


def _coerce_date(value: date | datetime | str | None) -> date:
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
            raise FinancialIncomeProjectionError("FINANCIAL_INCOME_AS_OF_INVALID") from exc
    raise FinancialIncomeProjectionError("FINANCIAL_INCOME_AS_OF_INVALID")


def _non_negative_money(value: object, code: str) -> float:
    if isinstance(value, bool):
        raise FinancialIncomeProjectionError(code)
    try:
        amount = float(value or 0.0)
    except (TypeError, ValueError) as exc:
        raise FinancialIncomeProjectionError(code) from exc
    if not math.isfinite(amount) or amount < 0:
        raise FinancialIncomeProjectionError(code)
    return amount


def _forecast_months(
    forecast_summary: dict[str, Any], *, after_month: int
) -> tuple[float | None, list[int]]:
    """Return estimated dividends for months strictly after ``after_month``.

    ``None`` means the dividend forecast is unavailable. Malformed available
    data raises instead of silently becoming zero, because that would
    understate projected financial income.
    """
    if forecast_summary.get("unavailable") is True:
        return None, []

    schedule = forecast_summary.get("monthly_schedule")
    if isinstance(schedule, dict):
        items = list(schedule.values())
    elif isinstance(schedule, list):
        items = schedule
    else:
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_FORECAST_INVALID")

    total = 0.0
    included_months: list[int] = []
    seen_months: set[int] = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise FinancialIncomeProjectionError("FINANCIAL_INCOME_FORECAST_INVALID")
        try:
            month = int(raw.get("month"))
        except (TypeError, ValueError) as exc:
            raise FinancialIncomeProjectionError("FINANCIAL_INCOME_FORECAST_INVALID") from exc
        if not 1 <= month <= 12 or month in seen_months:
            raise FinancialIncomeProjectionError("FINANCIAL_INCOME_FORECAST_INVALID")
        seen_months.add(month)
        amount = _non_negative_money(
            raw.get("total_krw"), "FINANCIAL_INCOME_FORECAST_INVALID"
        )
        if month > after_month:
            total += amount
            included_months.append(month)

    return total, sorted(included_months)


def _threshold_state(
    amount: float | None, threshold: float
) -> dict[str, Any] | None:
    if amount is None:
        return None
    remaining = max(0.0, threshold - amount)
    return {
        "amount_krw": round(amount),
        "threshold_krw": round(threshold),
        "remaining_krw": round(remaining),
        "exceeded": amount > threshold,
        "at_or_above": amount >= threshold,
        "progress_percent": (
            round((amount / threshold) * 100.0, 1) if threshold > 0 else None
        ),
    }


def _threshold_bundle(
    actual_amount: float,
    known_floor: float,
    projected_amount: float | None,
) -> dict[str, Any]:
    def one(kind: str, threshold: float, *, statutory: bool) -> dict[str, Any]:
        return {
            "kind": kind,
            "statutory": statutory,
            "threshold_krw": round(threshold),
            "actual": _threshold_state(actual_amount, threshold),
            "known_projection_floor": _threshold_state(known_floor, threshold),
            "projected": _threshold_state(projected_amount, threshold),
        }

    return {
        "watch": one(
            "product_watch",
            float(FINANCIAL_INCOME_WATCH_THRESHOLD_KRW),
            statutory=False,
        ),
        "comprehensive_tax": one(
            "comprehensive_tax",
            float(FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW),
            statutory=True,
        ),
    }


def build_financial_income_projection(
    actual_summary: dict[str, Any],
    forecast_summary: dict[str, Any],
    *,
    as_of: date | datetime | str | None = None,
    owner: str = "모두",
    expected_remaining_interest_krw: float = 0.0,
    current_month_remaining_dividend_krw: float = 0.0,
) -> dict[str, Any]:
    """Combine realized financial income with remaining-year estimates.

    Realized dividend and interest amounts come from the existing dividend
    record store. Automatic dividend forecast includes only months after the
    current month; the current month is deliberately excluded because realized
    records may already contain part of it.
    """
    if not isinstance(actual_summary, dict) or not isinstance(
        forecast_summary, dict
    ):
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_INPUT_INVALID")

    day = _coerce_date(as_of)
    target_year_raw = actual_summary.get("year") or day.year
    try:
        target_year = int(str(target_year_raw))
    except (TypeError, ValueError) as exc:
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_YEAR_INVALID") from exc
    if target_year != day.year:
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_YEAR_MISMATCH")

    actual_dividend = _non_negative_money(
        actual_summary.get("total_actual_dividend_krw"),
        "FINANCIAL_INCOME_ACTUAL_DIVIDEND_INVALID",
    )
    actual_interest = _non_negative_money(
        actual_summary.get("total_actual_interest_krw"),
        "FINANCIAL_INCOME_ACTUAL_INTEREST_INVALID",
    )
    expected_interest = _non_negative_money(
        expected_remaining_interest_krw,
        "FINANCIAL_INCOME_EXPECTED_INTEREST_INVALID",
    )
    current_month_adjustment = _non_negative_money(
        current_month_remaining_dividend_krw,
        "FINANCIAL_INCOME_CURRENT_MONTH_ADJUSTMENT_INVALID",
    )

    future_dividend, included_months = _forecast_months(
        forecast_summary, after_month=day.month
    )

    actual_total = actual_dividend + actual_interest
    known_floor = actual_total + expected_interest + current_month_adjustment
    projection_complete = future_dividend is not None
    projected_total = (
        known_floor + future_dividend if projection_complete else None
    )

    components = {
        "actual_dividend_krw": round(actual_dividend),
        "actual_interest_krw": round(actual_interest),
        "current_month_remaining_dividend_adjustment_krw": round(
            current_month_adjustment
        ),
        "future_months_estimated_dividend_krw": (
            round(future_dividend) if future_dividend is not None else None
        ),
        "expected_remaining_interest_krw": round(expected_interest),
    }

    return {
        "year": target_year,
        "as_of": day.isoformat(),
        "owner": str(owner or "모두"),
        "projection_complete": projection_complete,
        "forecast_unavailable": not projection_complete,
        "actual_financial_income_krw": round(actual_total),
        "known_projection_floor_krw": round(known_floor),
        "projected_financial_income_krw": (
            round(projected_total) if projected_total is not None else None
        ),
        "components": components,
        "forecast_basis": {
            "automatic_current_month_included": False,
            "included_future_months": included_months,
            "method": "actual_ytd_plus_future_month_forecast_plus_manual_adjustments",
        },
        "thresholds": _threshold_bundle(actual_total, known_floor, projected_total),
        "rule_context": {
            "year": RULE_YEAR,
            "comprehensive_tax_threshold_krw": (
                FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
            ),
            "watch_threshold_krw": FINANCIAL_INCOME_WATCH_THRESHOLD_KRW,
            "watch_threshold_statutory": False,
            "official_source": OFFICIAL_SOURCE_URL,
            "verified_on": RULE_VERIFIED_ON,
            "tax_liability_calculated": False,
        },
    }


def _filter_holdings_for_owner(
    holdings: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
    owner: str,
) -> list[dict[str, Any]]:
    if owner == "모두":
        return list(holdings)
    account_owner = {
        str(account.get("id")): account.get("owner", "모두")
        for account in accounts
        if account.get("id") is not None
    }
    return [
        holding
        for holding in holdings
        if holding.get("owner") == owner
        or account_owner.get(str(holding.get("account_id"))) == owner
    ]


async def get_financial_income_projection_for_user(
    username: str,
    *,
    owner: str = "모두",
    as_of: date | datetime | str | None = None,
    expected_remaining_interest_krw: float = 0.0,
    current_month_remaining_dividend_krw: float = 0.0,
) -> dict[str, Any]:
    """Build a projection from the user's existing realized and forecast data."""
    from app.services.dividend_records import get_actual_dividend_summary
    from app.services.portfolio import get_dashboard
    from app.services.web_finance import get_web_dividend_summary

    day = _coerce_date(as_of)
    normalized_owner = str(owner or "모두").strip() or "모두"
    dashboard = get_dashboard(username=username)
    holdings = dashboard.get("holdings", []) or []
    accounts = dashboard.get("accounts", []) or []
    if not isinstance(holdings, list) or not isinstance(accounts, list):
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_PORTFOLIO_INVALID")

    scoped_holdings = _filter_holdings_for_owner(
        holdings, accounts, normalized_owner
    )
    fx_rate = dashboard.get("fx_rates", {}).get("USD", 1385.0)
    forecast = await get_web_dividend_summary(scoped_holdings, fx_rate=fx_rate)
    actual = get_actual_dividend_summary(
        owner=normalized_owner,
        year=str(day.year),
        username=username,
    )

    result = build_financial_income_projection(
        actual,
        forecast,
        as_of=day,
        owner=normalized_owner,
        expected_remaining_interest_krw=expected_remaining_interest_krw,
        current_month_remaining_dividend_krw=current_month_remaining_dividend_krw,
    )
    result["source_counts"] = {
        "actual_dividend_records": int(actual.get("record_count") or 0),
        "actual_interest_records": int(actual.get("interest_record_count") or 0),
        "forecast_holdings": len(scoped_holdings),
    }
    return result
