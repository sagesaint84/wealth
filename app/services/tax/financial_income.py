"""Financial-income projection for Phase 10.5A.

The projection deliberately combines existing realized records with only
future-month dividend estimates. It never subtracts YTD realized dividends from
an annual forward estimate because current holdings may differ from holdings
that produced earlier realized income.

Two concepts are kept separate:
- cash income: the existing ``amount_krw`` values actually recorded as received;
- gross screening income: a best-effort pre-withholding amount used only to
  screen proximity to the statutory 20M KRW financial-income threshold.

The screening result is NOT a legal comprehensive-tax determination. Existing
records do not yet classify every non-taxable / separately-taxed item, including
the 2026 high-dividend special taxation regime. Current-month forecast is also
excluded automatically to avoid double counting against realized records.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
from typing import Any

from app.services.tax.rules_2026 import (
    FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    FINANCIAL_INCOME_WATCH_THRESHOLD_KRW,
    OFFICIAL_HIGH_DIVIDEND_SOURCE_URL,
    OFFICIAL_RULE_SOURCE_URL,
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


def _optional_non_negative_money(
    value: object,
    code: str,
) -> float | None:
    if value is None or value == "":
        return None
    return _non_negative_money(value, code)


def _forecast_months(
    forecast_summary: dict[str, Any], *, after_month: int
) -> tuple[float | None, list[int]]:
    """Return estimated dividends for months strictly after ``after_month``.

    ``None`` means the dividend forecast is unavailable. Malformed available
    data raises instead of silently becoming zero, because that would
    understate the screening projection.
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


def _record_gross_screening_krw(
    record: dict[str, Any],
) -> tuple[float, bool, str]:
    """Resolve one realized record to a gross screening amount in KRW.

    Preferred basis:
    1. explicit positive gross_amount;
    2. deposited amount + explicit tax + fee;
    3. amount_krw cash fallback (basis incomplete).

    ``complete`` only describes whether the pre-withholding amount can be
    reconstructed. It does not mean tax-treatment classification is complete.
    """
    if not isinstance(record, dict):
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_RECORD_INVALID")

    cash_krw = _non_negative_money(
        record.get("amount_krw"), "FINANCIAL_INCOME_RECORD_INVALID"
    )
    currency = str(record.get("currency") or "KRW").strip().upper()
    if currency == "KRW":
        multiplier = 1.0
    elif currency == "USD":
        fx = _optional_non_negative_money(
            record.get("fx_rate"), "FINANCIAL_INCOME_RECORD_INVALID"
        )
        multiplier = fx if fx is not None and fx > 0 else None
    else:
        multiplier = None

    gross = _optional_non_negative_money(
        record.get("gross_amount"), "FINANCIAL_INCOME_RECORD_INVALID"
    )
    if gross is not None and gross > 0 and multiplier is not None:
        return gross * multiplier, True, "gross_amount"

    tax = _optional_non_negative_money(
        record.get("tax"), "FINANCIAL_INCOME_RECORD_INVALID"
    )
    amount = _optional_non_negative_money(
        record.get("amount"), "FINANCIAL_INCOME_RECORD_INVALID"
    )
    fee = _optional_non_negative_money(
        record.get("fee"), "FINANCIAL_INCOME_RECORD_INVALID"
    )
    if (
        tax is not None
        and amount is not None
        and amount > 0
        and multiplier is not None
    ):
        return (amount + tax + (fee or 0.0)) * multiplier, True, "net_plus_tax"

    return cash_krw, False, "cash_fallback"


def _actual_gross_screening_basis(
    actual_summary: dict[str, Any],
    *,
    actual_cash_total: float,
) -> dict[str, Any]:
    dividend_records = actual_summary.get("records")
    interest_records = actual_summary.get("interest_records")
    records: list[dict[str, Any]] = []
    if isinstance(dividend_records, list):
        records.extend(dividend_records)
    if isinstance(interest_records, list):
        records.extend(interest_records)

    expected_count = int(actual_summary.get("record_count") or 0) + int(
        actual_summary.get("interest_record_count") or 0
    )
    if not records:
        return {
            "amount_krw": actual_cash_total,
            "gross_basis_complete": actual_cash_total == 0.0 and expected_count == 0,
            "record_detail_complete": actual_cash_total == 0.0 and expected_count == 0,
            "record_count": expected_count,
            "gross_basis_record_count": 0,
            "fallback_record_count": expected_count,
            "aggregate_cash_floor_applied": actual_cash_total > 0.0,
            "basis_sources": (
                {"aggregate_cash_fallback": 1} if actual_cash_total > 0.0 else {}
            ),
        }

    amount = 0.0
    gross_basis_count = 0
    fallback_count = 0
    basis_sources: dict[str, int] = {}
    for record in records:
        resolved, complete, source = _record_gross_screening_krw(record)
        amount += resolved
        basis_sources[source] = basis_sources.get(source, 0) + 1
        if complete:
            gross_basis_count += 1
        else:
            fallback_count += 1

    missing_count = max(0, expected_count - len(records))
    if missing_count:
        fallback_count += missing_count
        basis_sources["missing_record_detail"] = missing_count

    aggregate_cash_floor_applied = amount < actual_cash_total
    if aggregate_cash_floor_applied:
        amount = actual_cash_total
        basis_sources["aggregate_cash_floor"] = 1

    record_detail_complete = expected_count in {0, len(records)}
    return {
        "amount_krw": amount,
        "gross_basis_complete": (
            fallback_count == 0
            and record_detail_complete
            and not aggregate_cash_floor_applied
        ),
        "record_detail_complete": record_detail_complete,
        "record_count": max(expected_count, len(records)),
        "gross_basis_record_count": gross_basis_count,
        "fallback_record_count": fallback_count,
        "aggregate_cash_floor_applied": aggregate_cash_floor_applied,
        "basis_sources": basis_sources,
    }


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
    actual_screening: float,
    known_screening: float,
    projected_screening: float | None,
) -> dict[str, Any]:
    def one(kind: str, threshold: float, *, statutory: bool) -> dict[str, Any]:
        return {
            "kind": kind,
            "statutory_threshold": statutory,
            "screening_only": True,
            "legal_tax_determination": False,
            "threshold_krw": round(threshold),
            "actual_gross_screening": _threshold_state(actual_screening, threshold),
            "known_gross_screening": _threshold_state(known_screening, threshold),
            "projected_gross_screening": _threshold_state(
                projected_screening, threshold
            ),
        }

    return {
        "watch": one(
            "product_watch",
            float(FINANCIAL_INCOME_WATCH_THRESHOLD_KRW),
            statutory=False,
        ),
        "comprehensive_tax": one(
            "comprehensive_tax_screening",
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
    expected_remaining_interest_gross_krw: float = 0.0,
    current_month_remaining_dividend_gross_krw: float = 0.0,
) -> dict[str, Any]:
    """Build a gross-income screening projection from existing data.

    Realized cash values remain visible, but threshold screening prefers
    pre-withholding gross amounts when the record contains enough information.
    Future automatic dividend forecast includes only months after the current
    month. Manual remaining-interest/current-month adjustments are explicitly
    defined as gross KRW amounts.
    """
    if not isinstance(actual_summary, dict) or not isinstance(
        forecast_summary, dict
    ):
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_INPUT_INVALID")

    day = _coerce_date(as_of)
    if day.year != RULE_YEAR:
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_RULE_YEAR_UNSUPPORTED")

    target_year_raw = actual_summary.get("year") or day.year
    try:
        target_year = int(str(target_year_raw))
    except (TypeError, ValueError) as exc:
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_YEAR_INVALID") from exc
    if target_year != day.year:
        raise FinancialIncomeProjectionError("FINANCIAL_INCOME_YEAR_MISMATCH")

    actual_dividend_cash = _non_negative_money(
        actual_summary.get("total_actual_dividend_krw"),
        "FINANCIAL_INCOME_ACTUAL_DIVIDEND_INVALID",
    )
    actual_interest_cash = _non_negative_money(
        actual_summary.get("total_actual_interest_krw"),
        "FINANCIAL_INCOME_ACTUAL_INTEREST_INVALID",
    )
    expected_interest_gross = _non_negative_money(
        expected_remaining_interest_gross_krw,
        "FINANCIAL_INCOME_EXPECTED_INTEREST_INVALID",
    )
    current_month_dividend_gross = _non_negative_money(
        current_month_remaining_dividend_gross_krw,
        "FINANCIAL_INCOME_CURRENT_MONTH_ADJUSTMENT_INVALID",
    )

    actual_cash_total = actual_dividend_cash + actual_interest_cash
    actual_screening = _actual_gross_screening_basis(
        actual_summary,
        actual_cash_total=actual_cash_total,
    )
    actual_gross_screening = float(actual_screening["amount_krw"])

    future_dividend_gross, included_months = _forecast_months(
        forecast_summary, after_month=day.month
    )

    known_gross_screening = (
        actual_gross_screening
        + expected_interest_gross
        + current_month_dividend_gross
    )
    forecast_complete = future_dividend_gross is not None
    projected_gross_screening = (
        known_gross_screening + future_dividend_gross
        if forecast_complete
        else None
    )

    return {
        "year": target_year,
        "as_of": day.isoformat(),
        "owner": str(owner or "모두"),
        "forecast_complete": forecast_complete,
        "forecast_unavailable": not forecast_complete,
        "actual_cash_income_krw": round(actual_cash_total),
        "actual_gross_screening_income_krw": round(actual_gross_screening),
        "known_gross_screening_income_krw": round(known_gross_screening),
        "projected_gross_screening_income_krw": (
            round(projected_gross_screening)
            if projected_gross_screening is not None
            else None
        ),
        "components": {
            "actual_dividend_cash_krw": round(actual_dividend_cash),
            "actual_interest_cash_krw": round(actual_interest_cash),
            "current_month_remaining_dividend_gross_adjustment_krw": round(
                current_month_dividend_gross
            ),
            "future_months_estimated_dividend_gross_krw": (
                round(future_dividend_gross)
                if future_dividend_gross is not None
                else None
            ),
            "expected_remaining_interest_gross_krw": round(
                expected_interest_gross
            ),
        },
        "forecast_basis": {
            "automatic_current_month_included": False,
            "included_future_months": included_months,
            "method": "realized_gross_screening_plus_future_month_forecast_plus_manual_gross_adjustments",
        },
        "data_quality": {
            "actual_gross_basis_complete": bool(
                actual_screening["gross_basis_complete"]
            ),
            "actual_record_detail_complete": bool(
                actual_screening["record_detail_complete"]
            ),
            "actual_record_count": int(actual_screening["record_count"]),
            "actual_gross_basis_record_count": int(
                actual_screening["gross_basis_record_count"]
            ),
            "actual_cash_fallback_record_count": int(
                actual_screening["fallback_record_count"]
            ),
            "aggregate_cash_floor_applied": bool(
                actual_screening["aggregate_cash_floor_applied"]
            ),
            "actual_basis_sources": dict(actual_screening["basis_sources"]),
            "tax_treatment_classification_complete": False,
            "high_dividend_special_rule_applied": False,
            "screening_only": True,
        },
        "thresholds": _threshold_bundle(
            actual_gross_screening,
            known_gross_screening,
            projected_gross_screening,
        ),
        "rule_context": {
            "year": RULE_YEAR,
            "comprehensive_tax_threshold_krw": (
                FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
            ),
            "watch_threshold_krw": FINANCIAL_INCOME_WATCH_THRESHOLD_KRW,
            "watch_threshold_statutory": False,
            "official_sources": [
                OFFICIAL_RULE_SOURCE_URL,
                OFFICIAL_HIGH_DIVIDEND_SOURCE_URL,
            ],
            "verified_on": RULE_VERIFIED_ON,
            "tax_liability_calculated": False,
            "tax_treatment_classification_applied": False,
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
    expected_remaining_interest_gross_krw: float = 0.0,
    current_month_remaining_dividend_gross_krw: float = 0.0,
) -> dict[str, Any]:
    """Build a screening projection from the user's existing financial data."""
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
        expected_remaining_interest_gross_krw=(
            expected_remaining_interest_gross_krw
        ),
        current_month_remaining_dividend_gross_krw=(
            current_month_remaining_dividend_gross_krw
        ),
    )
    result["source_counts"] = {
        "actual_dividend_records": int(actual.get("record_count") or 0),
        "actual_interest_records": int(actual.get("interest_record_count") or 0),
        "forecast_holdings": len(scoped_holdings),
    }
    return result
