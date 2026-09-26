"""2026 high-dividend-company separate-tax screening.

This module intentionally does not determine whether a listed company legally
qualifies as a high-dividend company. That status must be confirmed from the
issuer's official disclosure. The service only calculates the 2026 national
income-tax amount for user-confirmed eligible special dividend income and
reports how much is excluded from the 20M KRW comprehensive-tax threshold when
separate taxation is requested.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.rules_2026 import (
    HIGH_DIVIDEND_DIVIDEND_GROWTH_ROUTE_PCT,
    HIGH_DIVIDEND_PAYOUT_RATIO_GROWTH_ROUTE_PCT,
    HIGH_DIVIDEND_PAYOUT_RATIO_PRIMARY_PCT,
    HIGH_DIVIDEND_SPECIAL_FIRST_PAYMENT_DATE,
    HIGH_DIVIDEND_SPECIAL_LAST_QUALIFYING_BUSINESS_YEAR_END,
    HIGH_DIVIDEND_SPECIAL_TAX_BRACKETS,
    OFFICIAL_HIGH_DIVIDEND_ENFORCEMENT_SOURCE_URL,
    OFFICIAL_HIGH_DIVIDEND_LAW_SOURCE_URL,
    OFFICIAL_HIGH_DIVIDEND_SOURCE_URL,
    RULE_VERIFIED_ON,
    RULE_YEAR,
)


class HighDividendSpecialTaxError(ValueError):
    """Stable validation error for the 2026 high-dividend special rule."""


def _nonnegative_money(value: object, code: str) -> float:
    if isinstance(value, bool):
        raise HighDividendSpecialTaxError(code)
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError) as exc:
        raise HighDividendSpecialTaxError(code) from exc
    if not math.isfinite(number) or number < 0:
        raise HighDividendSpecialTaxError(code)
    return number


def _bool(value: object, code: str) -> bool:
    if not isinstance(value, bool):
        raise HighDividendSpecialTaxError(code)
    return value


def _won(value: float) -> int:
    return int(round(value))


def _bracket_code(upper_bound: int | None, rate: float) -> str:
    if upper_bound == 20_000_000 and rate == 0.14:
        return "14pct_to_20m"
    if upper_bound == 300_000_000 and rate == 0.20:
        return "20pct_to_300m"
    if upper_bound == 5_000_000_000 and rate == 0.25:
        return "25pct_to_5b"
    if upper_bound is None and rate == 0.30:
        return "30pct_over_5b"
    raise HighDividendSpecialTaxError("HIGH_DIVIDEND_RULE_TABLE_INVALID")


def _national_tax(amount: float) -> tuple[float, str]:
    """Return national income tax before local income tax from the rule table."""
    tax = 0.0
    lower_bound = 0.0
    for upper_bound, rate in HIGH_DIVIDEND_SPECIAL_TAX_BRACKETS:
        bracket_end = float(upper_bound) if upper_bound is not None else amount
        taxable = max(0.0, min(amount, bracket_end) - lower_bound)
        tax += taxable * rate
        if upper_bound is None or amount <= upper_bound:
            return tax, _bracket_code(upper_bound, rate)
        lower_bound = float(upper_bound)
    raise HighDividendSpecialTaxError("HIGH_DIVIDEND_RULE_TABLE_INVALID")


def calculate_high_dividend_separate_tax_2026(
    special_dividend_income_krw: object,
    *,
    tax_year: int = RULE_YEAR,
    high_dividend_company_confirmed: bool = False,
    separate_taxation_requested: bool = False,
) -> dict[str, Any]:
    """Calculate the 2026 high-dividend special separate-tax screening result.

    The caller must explicitly confirm company eligibility from official
    disclosure before requesting the special treatment. The output is national
    income tax only; local income tax remains separate.
    """
    if isinstance(tax_year, bool):
        raise HighDividendSpecialTaxError("HIGH_DIVIDEND_RULE_YEAR_INVALID")
    try:
        year = int(tax_year)
    except (TypeError, ValueError) as exc:
        raise HighDividendSpecialTaxError("HIGH_DIVIDEND_RULE_YEAR_INVALID") from exc
    if year != RULE_YEAR:
        raise HighDividendSpecialTaxError("HIGH_DIVIDEND_RULE_YEAR_UNSUPPORTED")

    amount = _nonnegative_money(
        special_dividend_income_krw,
        "HIGH_DIVIDEND_SPECIAL_INCOME_INVALID",
    )
    confirmed = _bool(
        high_dividend_company_confirmed,
        "HIGH_DIVIDEND_COMPANY_CONFIRMATION_INVALID",
    )
    requested = _bool(
        separate_taxation_requested,
        "HIGH_DIVIDEND_SEPARATE_TAX_REQUEST_INVALID",
    )

    if requested and amount > 0 and not confirmed:
        raise HighDividendSpecialTaxError(
            "HIGH_DIVIDEND_COMPANY_CONFIRMATION_REQUIRED"
        )

    applied = bool(requested and confirmed and amount > 0)
    if applied:
        national_tax, bracket = _national_tax(amount)
        effective_rate = (national_tax / amount) * 100.0
    else:
        national_tax = None
        bracket = None
        effective_rate = None

    return {
        "year": year,
        "special_dividend_income_krw": _won(amount),
        "high_dividend_company_confirmed_by_user": confirmed,
        "separate_taxation_requested": requested,
        "special_rule_applied": applied,
        "excluded_from_comprehensive_tax_threshold_krw": _won(amount) if applied else 0,
        "national_income_tax_krw": _won(national_tax) if national_tax is not None else None,
        "effective_national_income_tax_rate_percent": (
            round(effective_rate, 4) if effective_rate is not None else None
        ),
        "applied_bracket": bracket,
        "local_income_tax_included": False,
        "filing_application_required": applied,
        "filing_application_required_for_special_treatment": True,
        "automatic_application": False,
        "eligibility": {
            "determined_by_service": False,
            "confirmation_source": "official_high_dividend_company_disclosure",
            "listed_company_konex_excluded": True,
            "headline_routes": {
                "primary_payout_ratio_percent": HIGH_DIVIDEND_PAYOUT_RATIO_PRIMARY_PCT,
                "growth_route_payout_ratio_percent": HIGH_DIVIDEND_PAYOUT_RATIO_GROWTH_ROUTE_PCT,
                "growth_route_dividend_growth_percent": HIGH_DIVIDEND_DIVIDEND_GROWTH_ROUTE_PCT,
            },
        },
        "rule_context": {
            "first_payment_date": HIGH_DIVIDEND_SPECIAL_FIRST_PAYMENT_DATE,
            "last_qualifying_business_year_end": HIGH_DIVIDEND_SPECIAL_LAST_QUALIFYING_BUSINESS_YEAR_END,
            "verified_on": RULE_VERIFIED_ON,
            "official_law_source_url": OFFICIAL_HIGH_DIVIDEND_LAW_SOURCE_URL,
            "official_enforcement_source_url": OFFICIAL_HIGH_DIVIDEND_ENFORCEMENT_SOURCE_URL,
            "official_nts_source_url": OFFICIAL_HIGH_DIVIDEND_SOURCE_URL,
            "screening_only": True,
            "legal_tax_determination": False,
        },
    }


__all__ = [
    "HighDividendSpecialTaxError",
    "calculate_high_dividend_separate_tax_2026",
]
