"""Narrow, input-based 2026 personal comprehensive-income tax comparison.

This B-4 increment applies the verified national basic-rate table only to a
tax base explicitly supplied by the caller. It deliberately does not derive a
tax base from portfolio data or claim to reproduce the financial-income
comparison calculation used in a final Korean comprehensive-income return.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.rules_2026 import (
    FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    OFFICIAL_FINANCIAL_INCOME_RETURN_FORM_SOURCE_URL,
    OFFICIAL_PERSONAL_COMPREHENSIVE_TAX_RATE_SOURCE_URL,
    PERSONAL_COMPREHENSIVE_INCOME_TAX_BRACKETS,
    RULE_VERIFIED_ON,
    RULE_YEAR,
)


class PersonalComprehensiveTaxError(ValueError):
    """Stable validation error for the bounded B-4 comparison."""


def _nonnegative_won(value: object, code: str) -> int:
    if isinstance(value, bool):
        raise PersonalComprehensiveTaxError(code)
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise PersonalComprehensiveTaxError(code) from exc
    if not math.isfinite(amount) or amount < 0:
        raise PersonalComprehensiveTaxError(code)
    return int(round(amount))


def _national_basic_rate_tax(tax_base_krw: int) -> int:
    tax = 0.0
    lower_bound = 0
    for upper_bound, rate in PERSONAL_COMPREHENSIVE_INCOME_TAX_BRACKETS:
        bracket_end = tax_base_krw if upper_bound is None else upper_bound
        taxable = max(0, min(tax_base_krw, bracket_end) - lower_bound)
        tax += taxable * rate
        if upper_bound is None or tax_base_krw <= upper_bound:
            return int(round(tax))
        lower_bound = upper_bound
    raise PersonalComprehensiveTaxError("PERSONAL_COMPREHENSIVE_TAX_RULE_INVALID")


def _threshold_state(amount: int) -> dict[str, int | bool]:
    threshold = FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
    return {
        "amount_krw": amount,
        "threshold_krw": threshold,
        "remaining_krw": max(0, threshold - amount),
        "at_or_above": amount >= threshold,
        "exceeded": amount > threshold,
    }


def calculate_personal_comprehensive_tax_basic_rate_2026(
    *,
    tax_base_before_financial_income_krw: object,
    financial_income_gross_krw: object,
    assumed_financial_income_included_in_tax_base_krw: object,
    tax_year: int = RULE_YEAR,
) -> dict[str, Any]:
    """Compare 2026 national basic-rate tax for explicitly supplied tax bases.

    ``assumed_financial_income_included_in_tax_base_krw`` is intentionally an
    explicit scenario input. The service cannot infer it from gross financial
    income because deductions, gross-up, special/separate taxation, and return
    comparison rules require information the product does not yet model.
    """
    if isinstance(tax_year, bool):
        raise PersonalComprehensiveTaxError("PERSONAL_COMPREHENSIVE_TAX_YEAR_INVALID")
    try:
        year = int(tax_year)
    except (TypeError, ValueError) as exc:
        raise PersonalComprehensiveTaxError(
            "PERSONAL_COMPREHENSIVE_TAX_YEAR_INVALID"
        ) from exc
    if year != RULE_YEAR:
        raise PersonalComprehensiveTaxError("PERSONAL_COMPREHENSIVE_TAX_YEAR_UNSUPPORTED")

    base_before = _nonnegative_won(
        tax_base_before_financial_income_krw,
        "PERSONAL_COMPREHENSIVE_TAX_BASE_INVALID",
    )
    financial_income = _nonnegative_won(
        financial_income_gross_krw,
        "PERSONAL_COMPREHENSIVE_TAX_FINANCIAL_INCOME_INVALID",
    )
    included_income = _nonnegative_won(
        assumed_financial_income_included_in_tax_base_krw,
        "PERSONAL_COMPREHENSIVE_TAX_INCLUDED_AMOUNT_INVALID",
    )
    if included_income > financial_income:
        raise PersonalComprehensiveTaxError(
            "PERSONAL_COMPREHENSIVE_TAX_INCLUDED_AMOUNT_EXCEEDS_FINANCIAL_INCOME"
        )

    base_after = base_before + included_income
    tax_before = _national_basic_rate_tax(base_before)
    tax_after = _national_basic_rate_tax(base_after)

    return {
        "year": year,
        "tax_base_before_financial_income_krw": base_before,
        "financial_income_gross_krw": financial_income,
        "assumed_financial_income_included_in_tax_base_krw": included_income,
        "tax_base_after_krw": base_after,
        "financial_income_threshold": _threshold_state(financial_income),
        "national_income_tax_before_krw": tax_before,
        "national_income_tax_after_krw": tax_after,
        "estimated_national_income_tax_difference_krw": tax_after - tax_before,
        "data_quality": {
            "screening_only": True,
            "legal_tax_determination": False,
            "stateless": True,
            "tax_base_provided_by_user": True,
            "withholding_tax_credit_calculated": False,
            "local_income_tax_calculated": False,
            "foreign_tax_credit_calculated": False,
        },
        "rule_context": {
            "year": RULE_YEAR,
            "verified_on": RULE_VERIFIED_ON,
            "official_basic_rate_source_url": (
                OFFICIAL_PERSONAL_COMPREHENSIVE_TAX_RATE_SOURCE_URL
            ),
            "official_financial_income_return_form_source_url": (
                OFFICIAL_FINANCIAL_INCOME_RETURN_FORM_SOURCE_URL
            ),
            "not_calculated": [
                "final financial-income comprehensive-tax comparison formula",
                "income deductions and tax credits",
                "dividend gross-up and dividend tax credit",
                "withholding tax already paid",
                "personal local income tax",
                "foreign tax credit",
                "health-insurance effect",
            ],
        },
    }


__all__ = [
    "PersonalComprehensiveTaxError",
    "calculate_personal_comprehensive_tax_basic_rate_2026",
]
