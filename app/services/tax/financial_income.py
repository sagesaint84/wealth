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
records distinguish selected capital exclusions and 2026 high-dividend filing
assumptions, but do not classify every other non-taxable / separately-taxed item. Current-month forecast is also
excluded automatically to avoid double counting against realized records.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
from typing import Any

from app.services.dividend_event_identity import normalize_dividend_code

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
    forecast_summary: dict[str, Any], *, after_month: int, actual_records: object = None
) -> tuple[float | None, list[int], int, float]:
    """Return estimated dividends for months strictly after ``after_month``.

    ``None`` means the dividend forecast is unavailable. Malformed available
    data raises instead of silently becoming zero, because that would
    understate the screening projection. ``included_months`` contains only
    future months with a positive forecast amount.
    """
    if forecast_summary.get("unavailable") is True:
        return None, [], 0, 0.0

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
    future_buckets: list[tuple[int, float, list[dict[str, Any]]]] = []
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
            raw_items = raw.get("items")
            official_items = (
                [item for item in raw_items if isinstance(item, dict)]
                if isinstance(raw_items, list)
                else []
            )
            future_buckets.append((month, amount, official_items))

    actuals = (
        [record for record in actual_records if isinstance(record, dict)]
        if isinstance(actual_records, list)
        else []
    )
    candidates: list[tuple[int, dict[str, Any]]] = []
    for bucket_index, (_, _, bucket_items) in enumerate(future_buckets):
        for item in bucket_items:
            if item.get("event_identity_confidence") == "official":
                candidates.append((bucket_index, item))

    consumed_candidates: set[int] = set()
    matched_by_bucket: dict[int, float] = {}
    dedup_count = 0
    for actual in actuals:
        actual_identity = str(actual.get("event_identity") or "").strip()
        actual_code = normalize_dividend_code(actual.get("code"))
        actual_date = str(actual.get("date") or "").strip()
        match_index: int | None = None

        if actual_identity:
            for index, (_, item) in enumerate(candidates):
                if index in consumed_candidates:
                    continue
                if str(item.get("event_identity") or "").strip() == actual_identity:
                    match_index = index
                    break
        if match_index is None and actual_code and actual_date:
            for index, (_, item) in enumerate(candidates):
                if index in consumed_candidates:
                    continue
                if (
                    normalize_dividend_code(item.get("code")) == actual_code
                    and str(item.get("payment_date") or "").strip() == actual_date
                ):
                    match_index = index
                    break
        if match_index is None:
            continue

        bucket_index, item = candidates[match_index]
        payout = _non_negative_money(
            item.get("payout_krw"), "FINANCIAL_INCOME_FORECAST_INVALID"
        )
        consumed_candidates.add(match_index)
        matched_by_bucket[bucket_index] = (
            matched_by_bucket.get(bucket_index, 0.0) + payout
        )
        dedup_count += 1

    dedup_amount = 0.0
    for bucket_index, (month, amount, _) in enumerate(future_buckets):
        deducted = min(amount, matched_by_bucket.get(bucket_index, 0.0))
        remaining = amount - deducted
        total += remaining
        dedup_amount += deducted
        if remaining > 0:
            included_months.append(month)

    return total, sorted(included_months), dedup_count, dedup_amount


def _record_gross_screening_krw(
    record: dict[str, Any],
) -> tuple[float, bool, str]:
    """Resolve one realized record to a gross screening amount in KRW.

    Preferred basis:
    1. explicit gross_amount (including zero);
    2. deposited amount + explicit tax + fee;
    3. existing actual-record net-to-gross estimate; cash fallback if FX is unknown.

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

    # Preserve validation of recorded figures, including explicit zero. Estimates
    # reuse the actual-record UI calculator; inferred values never get persisted.
    for field in ('gross_amount', 'tax', 'amount', 'fee', 'estimated_tax_rate', 'capital_exempt_amount', 'high_dividend_amount'):
        _optional_non_negative_money(record.get(field), 'FINANCIAL_INCOME_RECORD_INVALID')
    if multiplier is None:
        return cash_krw, False, 'cash_fallback'
    from app.services.dividend_records import estimate_record_dividend
    copy = dict(record)
    if copy.get('amount') is None:
        copy['amount'] = cash_krw / multiplier
    estimate = estimate_record_dividend(copy)
    source = ('gross_amount' if record.get('gross_amount') is not None else
        'net_plus_tax' if record.get('tax') is not None else 'estimated_from_net')
    return float(estimate['gross_amount_krw']), not estimate['estimated'], source


def _actual_gross_screening_basis(
    actual_summary: dict[str, Any],
    *,
    actual_cash_total: float,
    official_evidence: dict[str, Any] | None = None,
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
            "total_gross_krw": actual_cash_total,
            "capital_excluded_krw": 0, "high_dividend_excluded_krw": 0,
            "high_dividend_special_tax": None,
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
    capital_excluded = high_excluded = 0
    gross_basis_count = 0
    fallback_count = 0
    basis_sources: dict[str, int] = {}
    for record in records:
        # Interest never inherits dividend tax selections, even on legacy rows.
        is_interest = any(record is r for r in (interest_records or []))
        normalized = ({**record, 'capital_dividend_mode': 'MANUAL_OFF', 'high_dividend_mode': 'MANUAL_OFF'}
            if is_interest else record)
        resolved, complete, source = _record_gross_screening_krw(normalized)
        from app.services.dividend_records import estimate_record_dividend
        if not is_interest:
            estimate_record = dict(record)
            if estimate_record.get('amount') is None:
                multiplier = 1 if record.get('currency', 'KRW') == 'KRW' else record.get('fx_rate')
                if multiplier:
                    estimate_record['amount'] = float(record.get('amount_krw') or 0) / float(multiplier)
            estimate = estimate_record_dividend(estimate_record, (official_evidence or {}).get(str(record.get('code'))))
            if estimate_record.get('amount') is not None:
                resolved = estimate['gross_amount_krw']
            capital_excluded += min(resolved, estimate['capital_exempt_amount_krw'])
            high_excluded += min(max(0, resolved - estimate['capital_exempt_amount_krw']), estimate['high_dividend_applied_amount_krw'])
        if resolved < float(record.get('amount_krw') or 0):
            complete, source = False, 'cash_fallback'
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

    # The cash safety floor belongs to TOTAL gross, before exclusions. Applying
    # it to the final threshold amount would incorrectly add excluded cash back.
    total_gross = amount
    from app.services.tax.what_if import build_financial_income_what_if
    calculation = build_financial_income_what_if(
        {'known_gross_screening_income_krw': 0, 'projected_gross_screening_income_krw': 0},
        additional_dividend_gross_krw=max(0, total_gross - capital_excluded),
        high_dividend_scenario={'special_dividend_income_krw': high_excluded,
            'high_dividend_company_confirmed': True, 'separate_taxation_requested': True} if high_excluded else None)
    special = calculation['high_dividend_special_tax']
    if special:
        # The existing calculator requires eligibility as an input assumption;
        # a saved manual selection does not establish an official qualification.
        special['application_basis'] = 'user_selection_and_filing_assumption'
        special['eligibility']['confirmation_source'] = 'user_assumption'
    record_detail_complete = expected_count in {0, len(records)}
    return {
        "amount_krw": calculation['scenario_comprehensive_tax_screening_income_krw'],
        "total_gross_krw": total_gross,
        "capital_excluded_krw": capital_excluded, "high_dividend_excluded_krw": high_excluded,
        "high_dividend_special_tax": calculation['high_dividend_special_tax'],
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
    *, personal: bool = True,
) -> dict[str, Any]:
    def one(kind: str, threshold: float, *, statutory: bool) -> dict[str, Any]:
        def state(amount):
            result = _threshold_state(amount, threshold)
            if result is not None and not personal:
                for key in ('remaining_krw', 'exceeded', 'at_or_above', 'progress_percent'):
                    result[key] = None
            return result
        return {
            "kind": kind,
            "statutory_threshold": statutory,
            "screening_only": True,
            "legal_tax_determination": False,
            "threshold_krw": round(threshold),
            "personal_threshold_applied": personal,
            "actual_gross_screening": state(actual_screening),
            "known_gross_screening": state(known_screening),
            "projected_gross_screening": state(projected_screening),
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
    official_evidence: dict[str, Any] | None = None,
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
        official_evidence=official_evidence,
    )
    actual_gross_screening = float(actual_screening["amount_krw"])

    future_dividend_gross, included_months, dedup_count, dedup_amount = _forecast_months(
        forecast_summary,
        after_month=day.month,
        actual_records=actual_summary.get("records"),
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
        "actual_financial_income": {
            'total_gross_krw': round(actual_screening['total_gross_krw']),
            'capital_excluded_krw': round(actual_screening['capital_excluded_krw']),
            'high_dividend_excluded_krw': round(actual_screening['high_dividend_excluded_krw']),
            'included_krw': round(actual_gross_screening),
            'remaining_krw': max(0, FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW - round(actual_gross_screening)) if owner != '모두' else None,
            'exceeded': actual_gross_screening > FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW if owner != '모두' else None,
            'status': ('기준 초과' if actual_gross_screening > FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW else '기준 이내') if owner != '모두' else '가족 참고 합계',
            'personal_threshold_applied': owner != '모두',
            'high_dividend_special_tax': actual_screening['high_dividend_special_tax'] if owner != '모두' else None,
            'high_dividend_application_basis': 'user_selection_and_filing_assumption',
            'basis': 'registered_records_only',
        },
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
            "dividend_event_dedup_applied_count": dedup_count,
            "dividend_event_dedup_amount_krw": round(dedup_amount),
            "dividend_event_dedup_high_confidence_only": True,
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
            "high_dividend_special_rule_applied": actual_screening["high_dividend_excluded_krw"] > 0,
            "screening_only": True,
            "dividend_event_identity_supported": True,
            "heuristic_forecast_event_dedup_applied": False,
        },
        "thresholds": _threshold_bundle(
            actual_gross_screening,
            known_gross_screening,
            projected_gross_screening,
            personal=owner != '모두',
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
            "tax_treatment_classification_applied": bool(actual_screening["capital_excluded_krw"] or actual_screening["high_dividend_excluded_krw"]),
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
    forecast = await get_web_dividend_summary(
        scoped_holdings, fx_rate=fx_rate, username=username
    )
    actual = get_actual_dividend_summary(
        owner=normalized_owner,
        year=str(day.year),
        username=username,
    )

    from app.services.dividend_records import get_record_tax_evidence
    evidence = await get_record_tax_evidence(actual.get('records') or [], username)
    result = build_financial_income_projection(
        actual,
        forecast,
        as_of=day,
        owner=normalized_owner,
        official_evidence=evidence,
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
