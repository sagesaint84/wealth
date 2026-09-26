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
    DIVIDEND_GROSS_UP_RATE,
    DIVIDEND_TAX_CREDIT_VERIFIED_ON,
    FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    OFFICIAL_DIVIDEND_TAX_CREDIT_ENFORCEMENT_SOURCE_URL,
    OFFICIAL_DIVIDEND_TAX_CREDIT_LAW_SOURCE_URL,
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
            "basic_rate_legal_basis": "소득세법 제55조 제1항",
            "financial_income_threshold_legal_basis": "소득세법 제14조 제3항 제6호",
            "financial_income_threshold_amount_only_screening": True,
            "nonwithheld_financial_income_exception_evaluated": False,
            "financial_income_threshold_note": (
                "2천만원 이하라는 금액만으로 최종 종합과세 제외 여부를 판정하지 않습니다."
            ),
            "official_basic_rate_source_url": (
                OFFICIAL_PERSONAL_COMPREHENSIVE_TAX_RATE_SOURCE_URL
            ),
            "official_financial_income_return_form_source_url": (
                OFFICIAL_FINANCIAL_INCOME_RETURN_FORM_SOURCE_URL
            ),
            "not_calculated": [
                "final financial-income comprehensive-tax comparison formula",
                "nonwithheld financial-income exception",
                "income deductions and tax credits",
                "dividend gross-up and dividend tax credit",
                "withholding tax already paid",
                "personal local income tax",
                "foreign tax credit",
                "health-insurance effect",
            ],
        },
    }


_ARTICLE62_FIELDS = frozenset({
    "ordinary_interest_14_krw", "ordinary_dividend_14_krw",
    "nonbusiness_loan_interest_25_krw",
    "online_investment_linked_nonbusiness_loan_interest_14_krw",
    "nonwithheld_interest_14_krw", "nonwithheld_nonbusiness_loan_interest_25_krw",
    "nonwithheld_dividend_14_krw", "gross_up_eligible_dividend_krw",
    "other_comprehensive_income_excluding_partnership_dividend_krw",
    "income_deduction_krw",
})


def calculate_financial_income_article62_comparison_2026(**values: object) -> dict[str, Any]:
    """Return bounded Article 62 tax plus the Article 56 dividend tax credit.

    Financial-income categories and gross-up eligibility are explicit caller
    assumptions; no portfolio or withholding classification is inferred. The
    returned post-credit amount is still before other credits and is not a
    final tax-payable determination.
    """
    if set(values) != _ARTICLE62_FIELDS:
        raise PersonalComprehensiveTaxError("ARTICLE62_REQUEST_INVALID")
    amounts = {
        name: _nonnegative_won(value, "ARTICLE62_AMOUNT_INVALID")
        for name, value in values.items()
    }
    financial_keys = _ARTICLE62_FIELDS - {
        "other_comprehensive_income_excluding_partnership_dividend_krw",
        "income_deduction_krw",
    }
    financial_income = sum(amounts[name] for name in financial_keys)
    gross_up_eligible_dividend = amounts["gross_up_eligible_dividend_krw"]
    other_income = amounts[
        "other_comprehensive_income_excluding_partnership_dividend_krw"
    ]
    deduction = amounts["income_deduction_krw"]
    excess = max(0, financial_income - FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW)
    gross_up_target_dividend = min(gross_up_eligible_dividend, excess)
    gross_up = int(round(gross_up_target_dividend * DIVIDEND_GROSS_UP_RATE))
    progressive_base = max(0, excess + gross_up + other_income - deduction)
    comparison_a = _national_basic_rate_tax(progressive_base) + 2_800_000
    all_financial_income_withholding_equivalent = (
        (amounts["ordinary_interest_14_krw"] + amounts["ordinary_dividend_14_krw"]
         + amounts["online_investment_linked_nonbusiness_loan_interest_14_krw"]
         + amounts["nonwithheld_interest_14_krw"]
         + amounts["nonwithheld_dividend_14_krw"] + amounts["gross_up_eligible_dividend_krw"]) * 0.14
        + (amounts["nonbusiness_loan_interest_25_krw"]
           + amounts["nonwithheld_nonbusiness_loan_interest_25_krw"]) * 0.25
    )
    nonwithheld_financial_income_withholding_equivalent = (
        (amounts["nonwithheld_interest_14_krw"]
         + amounts["nonwithheld_dividend_14_krw"]) * 0.14
        + amounts["nonwithheld_nonbusiness_loan_interest_25_krw"] * 0.25
    )
    other_tax_base = max(0, other_income - deduction)
    exceeded = financial_income > FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
    withholding_equivalent = (
        all_financial_income_withholding_equivalent
        if exceeded
        else nonwithheld_financial_income_withholding_equivalent
    )
    comparison_b = int(round(withholding_equivalent)) + _national_basic_rate_tax(other_tax_base)
    article62_tax_before_credits = (
        max(comparison_a, comparison_b) if exceeded else comparison_b
    )

    # Official Form 40(1), financial-income schedule row 40:
    # dividend tax credit = min(gross-up amount, comprehensive tax - comparison B).
    dividend_tax_credit_limit = max(
        0, article62_tax_before_credits - comparison_b
    )
    dividend_tax_credit = min(gross_up, dividend_tax_credit_limit)
    tax_after_dividend_credit = article62_tax_before_credits - dividend_tax_credit

    return {
        "year": RULE_YEAR,
        "financial_income_taxable_total_krw": financial_income,
        "financial_income_threshold": _threshold_state(financial_income),
        "inputs": amounts,
        "gross_up_eligible_dividend_krw": gross_up_eligible_dividend,
        "gross_up_target_dividend_krw": gross_up_target_dividend,
        "dividend_gross_up_amount_krw": gross_up,
        "gross_up_eligibility_user_asserted": gross_up_eligible_dividend > 0,
        "comparison_a_krw": comparison_a if exceeded else None,
        "comparison_b_krw": comparison_b,
        "article62_comparison_tax_before_credits_krw": article62_tax_before_credits,
        "article62_method": "greater_of_a_b" if exceeded else "comparison_b_only",
        "dividend_tax_credit_limit_krw": dividend_tax_credit_limit,
        "dividend_tax_credit_krw": dividend_tax_credit,
        "article62_tax_after_dividend_credit_before_other_credits_krw": (
            tax_after_dividend_credit
        ),
        "data_quality": {
            "screening_only": True,
            "legal_tax_determination": False,
            "stateless": True,
            "dividend_tax_credit_calculated": True,
            "dividend_tax_credit_user_classification_dependent": True,
            "other_tax_credits_calculated": False,
            "withholding_tax_paid_credit_calculated": False,
            "local_income_tax_calculated": False,
            "foreign_tax_credit_calculated": False,
            "withheld_financial_income_separate_tax_below_threshold_not_included": (
                not exceeded
            ),
            "financial_income_categories_user_classified": True,
            "non_taxable_or_separate_tax_income_excluded_by_caller": True,
            "partnership_dividend_article62_special_rule_calculated": False,
            "other_comprehensive_income_excludes_partnership_dividend": True,
        },
        "rule_context": {
            "year": RULE_YEAR,
            "verified_on": RULE_VERIFIED_ON,
            "dividend_tax_credit_verified_on": DIVIDEND_TAX_CREDIT_VERIFIED_ON,
            "article62_legal_basis": "소득세법 제62조",
            "withholding_rate_legal_basis": "소득세법 제129조",
            "gross_up_legal_basis": "소득세법 제17조 제3항",
            "dividend_tax_credit_legal_basis": "소득세법 제56조",
            "dividend_tax_credit_order_legal_basis": "소득세법 시행령 제116조의2",
            "partnership_dividend_special_rule_legal_basis": "소득세법 제62조 제2호 나목",
            "official_financial_income_return_form_source_url": (
                OFFICIAL_FINANCIAL_INCOME_RETURN_FORM_SOURCE_URL
            ),
            "official_dividend_tax_credit_law_source_url": (
                OFFICIAL_DIVIDEND_TAX_CREDIT_LAW_SOURCE_URL
            ),
            "official_dividend_tax_credit_enforcement_source_url": (
                OFFICIAL_DIVIDEND_TAX_CREDIT_ENFORCEMENT_SOURCE_URL
            ),
            "dividend_tax_credit_formula": (
                "min(dividend_gross_up_amount_krw, "
                "article62_comparison_tax_before_credits_krw - comparison_b_krw)"
            ),
            "not_calculated": [
                "withholding tax paid credit",
                "other income-tax credits or reductions",
                "local income tax",
                "foreign tax credit",
                "final legal/tax determination",
                "Article 17(1)(8) partnership-dividend Article 62 special comparison",
            ],
            "below_threshold_withheld_income_note": (
                "20,000,000원 이하의 원천징수 금융소득은 이 Article 62 종합과세 비교에 포함하지 않습니다."
            ),
        },
    }


__all__ = [
    "PersonalComprehensiveTaxError",
    "calculate_personal_comprehensive_tax_basic_rate_2026",
    "calculate_financial_income_article62_comparison_2026",
]
