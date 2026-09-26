"""2026 comprehensive individual local-income-tax comparison for financial income.

This B-4.4 increment augments the existing national Article 62 comparison with
the Local Tax Act Article 93(2) comparison tax using statutory standard local
rates. It deliberately does not claim to calculate final local income tax,
because ordinance-adjusted rates, local credits/reductions, prepaid special
withholding, additions, and final payment/refund remain outside this increment.
"""

from __future__ import annotations

from typing import Any

from app.services.tax.personal_comprehensive_tax_2026 import (
    calculate_financial_income_article62_comparison_2026 as _calculate_national,
)
from app.services.tax.rules_2026 import (
    FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    LOCAL_INCOME_TAX_COMPARISON_VERIFIED_ON,
    LOCAL_PERSONAL_COMPREHENSIVE_INCOME_TAX_STANDARD_BRACKETS,
    OFFICIAL_LOCAL_FINANCIAL_INCOME_COMPARISON_SOURCE_URL,
    OFFICIAL_LOCAL_INCOME_TAX_BASE_SOURCE_URL,
    OFFICIAL_LOCAL_INCOME_TAX_RATE_SOURCE_URL,
    OFFICIAL_LOCAL_INCOME_TAX_RETURN_FORM_SOURCE_URL,
)

_LOCAL_ORDINARY_FINANCIAL_INCOME_RATE = 0.014
_LOCAL_NONBUSINESS_LOAN_INTEREST_RATE = 0.025


def _local_standard_rate_tax(tax_base_krw: int) -> int:
    tax = 0.0
    lower_bound = 0
    for upper_bound, rate in LOCAL_PERSONAL_COMPREHENSIVE_INCOME_TAX_STANDARD_BRACKETS:
        bracket_end = tax_base_krw if upper_bound is None else upper_bound
        taxable = max(0, min(tax_base_krw, bracket_end) - lower_bound)
        tax += taxable * rate
        if upper_bound is None or tax_base_krw <= upper_bound:
            return int(round(tax))
        lower_bound = upper_bound
    raise RuntimeError("LOCAL_PERSONAL_COMPREHENSIVE_TAX_RULE_INVALID")


def calculate_financial_income_article62_comparison_2026(**values: object) -> dict[str, Any]:
    """Return the existing national result plus bounded Article 93 local tax.

    Input validation and caller-supplied financial-income classification remain
    owned by the national B-4.3 service. The local calculation reuses only the
    validated, rounded inputs from that result and independently applies Local
    Tax Act Articles 91, 92, and 93. Article 92(2) ordinance rate variation is
    not inferred because the request carries no verified taxing jurisdiction.
    """
    result = _calculate_national(**values)
    amounts = result["inputs"]
    financial_income = result["financial_income_taxable_total_krw"]
    exceeded = result["financial_income_threshold"]["exceeded"]
    gross_up = result["dividend_gross_up_amount_krw"]
    other_income = amounts[
        "other_comprehensive_income_excluding_partnership_dividend_krw"
    ]
    deduction = amounts["income_deduction_krw"]

    excess = max(
        0,
        financial_income - FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    )
    progressive_base = max(0, excess + gross_up + other_income - deduction)
    threshold_local_tax = int(
        round(
            FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
            * _LOCAL_ORDINARY_FINANCIAL_INCOME_RATE
        )
    )
    comparison_a = _local_standard_rate_tax(progressive_base) + threshold_local_tax

    ordinary_rate_base = (
        amounts["ordinary_interest_14_krw"]
        + amounts["ordinary_dividend_14_krw"]
        + amounts["online_investment_linked_nonbusiness_loan_interest_14_krw"]
        + amounts["nonwithheld_interest_14_krw"]
        + amounts["nonwithheld_dividend_14_krw"]
        + amounts["gross_up_eligible_dividend_krw"]
    )
    nonbusiness_rate_base = (
        amounts["nonbusiness_loan_interest_25_krw"]
        + amounts["nonwithheld_nonbusiness_loan_interest_25_krw"]
    )
    all_financial_income_local_equivalent = (
        ordinary_rate_base * _LOCAL_ORDINARY_FINANCIAL_INCOME_RATE
        + nonbusiness_rate_base * _LOCAL_NONBUSINESS_LOAN_INTEREST_RATE
    )
    nonwithheld_financial_income_local_equivalent = (
        (
            amounts["nonwithheld_interest_14_krw"]
            + amounts["nonwithheld_dividend_14_krw"]
        )
        * _LOCAL_ORDINARY_FINANCIAL_INCOME_RATE
        + amounts["nonwithheld_nonbusiness_loan_interest_25_krw"]
        * _LOCAL_NONBUSINESS_LOAN_INTEREST_RATE
    )
    local_financial_equivalent = (
        all_financial_income_local_equivalent
        if exceeded
        else nonwithheld_financial_income_local_equivalent
    )
    other_tax_base = max(0, other_income - deduction)
    comparison_b = int(round(local_financial_equivalent)) + _local_standard_rate_tax(
        other_tax_base
    )
    article93_tax_before_credits = (
        max(comparison_a, comparison_b) if exceeded else comparison_b
    )

    result.update(
        {
            "local_income_tax_comparison_a_krw": comparison_a if exceeded else None,
            "local_income_tax_comparison_b_krw": comparison_b,
            "article93_local_income_tax_before_credits_krw": (
                article93_tax_before_credits
            ),
            "article93_local_income_tax_method": (
                "greater_of_a_b" if exceeded else "comparison_b_only"
            ),
        }
    )

    data_quality = result["data_quality"]
    data_quality.update(
        {
            "local_income_tax_article93_comparison_calculated": True,
            "local_income_tax_standard_rate_only": True,
            "local_income_tax_ordinance_rate_adjustment_calculated": False,
            "local_income_tax_dividend_credit_calculated": False,
            "local_income_tax_prepaid_special_withholding_calculated": False,
            "local_income_tax_final_payment_or_refund_calculated": False,
        }
    )

    rule_context = result["rule_context"]
    existing_not_calculated = list(rule_context.get("not_calculated", []))
    existing_not_calculated = [
        item for item in existing_not_calculated if item != "local income tax"
    ]
    existing_not_calculated.extend(
        [
            "local income-tax credits or reductions",
            "local dividend tax credit",
            "local prepaid special withholding tax",
            "local income-tax additions or penalties",
            "final local income-tax payment or refund amount",
        ]
    )
    rule_context.update(
        {
            "local_income_tax_comparison_verified_on": (
                LOCAL_INCOME_TAX_COMPARISON_VERIFIED_ON
            ),
            "local_income_tax_base_legal_basis": "지방세법 제91조 제1항",
            "local_income_tax_standard_rate_legal_basis": "지방세법 제92조 제1항",
            "local_income_tax_ordinance_rate_legal_basis": "지방세법 제92조 제2항",
            "local_financial_income_comparison_legal_basis": "지방세법 제93조 제2항",
            "official_local_income_tax_base_source_url": (
                OFFICIAL_LOCAL_INCOME_TAX_BASE_SOURCE_URL
            ),
            "official_local_income_tax_rate_source_url": (
                OFFICIAL_LOCAL_INCOME_TAX_RATE_SOURCE_URL
            ),
            "official_local_financial_income_comparison_source_url": (
                OFFICIAL_LOCAL_FINANCIAL_INCOME_COMPARISON_SOURCE_URL
            ),
            "official_local_income_tax_return_form_source_url": (
                OFFICIAL_LOCAL_INCOME_TAX_RETURN_FORM_SOURCE_URL
            ),
            "local_income_tax_standard_rate_note": (
                "지방세법 제92조 제1항의 표준세율만 적용합니다. 같은 조 제2항의 "
                "지방자치단체 조례에 따른 세율 가감은 납세지와 조례를 확인하지 않은 "
                "상태에서 자동 추정하지 않습니다."
            ),
            "local_income_tax_scope_note": (
                "지방세법 제93조 제2항 금융소득 비교산출세액까지의 부분 계산입니다. "
                "지방 세액공제ㆍ감면, 특별징수 기납부세액, 가산세 및 최종 납부ㆍ"
                "환급세액은 계산하지 않습니다."
            ),
            "not_calculated": existing_not_calculated,
        }
    )
    return result


__all__ = ["calculate_financial_income_article62_comparison_2026"]
