"""2026 comprehensive individual local-income-tax comparison for financial income.

B-4.4 calculates the Local Tax Act Article 93(2) comparison tax using statutory
standard local rates. B-4.4.1 then applies the dividend tax credit under Local
Tax Special Treatment Control Act Article 95. It deliberately does not claim to
calculate final local income tax because ordinance-adjusted rates, other local
credits/reductions, prepaid special withholding, additions, and final
payment/refund remain outside this increment.
"""

from __future__ import annotations

from typing import Any

from app.services.tax.personal_comprehensive_tax_2026 import (
    calculate_financial_income_article62_comparison_2026 as _calculate_national,
)
from app.services.tax.rules_2026 import (
    FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    LOCAL_DIVIDEND_TAX_CREDIT_RATE_ON_GROSS_UP,
    LOCAL_DIVIDEND_TAX_CREDIT_VERIFIED_ON,
    LOCAL_INCOME_TAX_COMPARISON_VERIFIED_ON,
    LOCAL_PERSONAL_COMPREHENSIVE_INCOME_TAX_STANDARD_BRACKETS,
    OFFICIAL_LOCAL_DIVIDEND_TAX_CREDIT_LAW_SOURCE_URL,
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
    """Return national results plus bounded local Article 93/95 calculations.

    Input validation and caller-supplied financial-income classification remain
    owned by the national B-4.3 service. The local calculation reuses only the
    validated, rounded inputs from that result and independently applies Local
    Tax Act Articles 91, 92, and 93. Article 92(2) ordinance rate variation is
    not inferred because the request carries no verified taxing jurisdiction.

    The local dividend credit uses the already-validated national gross-up
    amount because Local Tax Special Treatment Control Act Article 95 defines
    its credit as 10% of the amount added to gross receipts under Income Tax Act
    Article 17(3), limited to dividend income above the comprehensive financial-
    income threshold. Other local credits and prepaid taxes remain out of scope.
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

    local_dividend_tax_credit = int(
        round(gross_up * LOCAL_DIVIDEND_TAX_CREDIT_RATE_ON_GROSS_UP)
    )
    if local_dividend_tax_credit > article93_tax_before_credits:
        raise RuntimeError("LOCAL_DIVIDEND_TAX_CREDIT_EXCEEDS_LOCAL_TAX")
    local_tax_after_dividend_credit = (
        article93_tax_before_credits - local_dividend_tax_credit
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
            "local_dividend_tax_credit_krw": local_dividend_tax_credit,
            "article93_local_income_tax_after_dividend_credit_before_other_credits_krw": (
                local_tax_after_dividend_credit
            ),
        }
    )

    data_quality = result["data_quality"]
    data_quality.update(
        {
            "local_income_tax_calculated": True,
            "local_income_tax_article93_comparison_calculated": True,
            "local_income_tax_standard_rate_only": True,
            "local_income_tax_ordinance_rate_adjustment_calculated": False,
            "local_income_tax_dividend_credit_calculated": True,
            "local_income_tax_dividend_credit_user_classification_dependent": True,
            "local_income_tax_other_credits_or_reductions_calculated": False,
            "local_income_tax_prepaid_special_withholding_calculated": False,
            "local_income_tax_final_payment_or_refund_calculated": False,
        }
    )

    rule_context = result["rule_context"]
    existing_not_calculated = list(rule_context.get("not_calculated", []))
    existing_not_calculated = [
        item
        for item in existing_not_calculated
        if item
        not in {
            "local income tax",
            "local income-tax credits or reductions",
            "local dividend tax credit",
        }
    ]
    existing_not_calculated.extend(
        [
            "other local income-tax credits or reductions",
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
            "local_dividend_tax_credit_verified_on": (
                LOCAL_DIVIDEND_TAX_CREDIT_VERIFIED_ON
            ),
            "local_income_tax_base_legal_basis": "지방세법 제91조 제1항",
            "local_income_tax_standard_rate_legal_basis": "지방세법 제92조 제1항",
            "local_income_tax_ordinance_rate_legal_basis": "지방세법 제92조 제2항",
            "local_financial_income_comparison_legal_basis": "지방세법 제93조 제2항",
            "local_dividend_tax_credit_legal_basis": "지방세특례제한법 제95조",
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
            "official_local_dividend_tax_credit_law_source_url": (
                OFFICIAL_LOCAL_DIVIDEND_TAX_CREDIT_LAW_SOURCE_URL
            ),
            "local_dividend_tax_credit_formula": (
                "round(dividend_gross_up_amount_krw * 0.10)"
            ),
            "local_dividend_tax_credit_note": (
                "소득세법 제17조 제3항에 따라 총수입금액에 더한 배당가산액의 10%를 "
                "지방세특례제한법 제95조에 따라 공제합니다. 배당가산 대상 분류와 "
                "종합과세기준금액 초과분은 기존 명시 입력 분류를 그대로 사용합니다."
            ),
            "local_income_tax_standard_rate_note": (
                "지방세법 제92조 제1항의 표준세율만 적용합니다. 같은 조 제2항의 "
                "지방자치단체 조례에 따른 세율 가감은 납세지와 조례를 확인하지 않은 "
                "상태에서 자동 추정하지 않습니다."
            ),
            "local_income_tax_scope_note": (
                "지방세법 제93조 제2항 금융소득 비교산출세액과 지방세특례제한법 "
                "제95조 배당세액공제까지의 부분 계산입니다. 다른 지방 세액공제ㆍ감면, "
                "특별징수 기납부세액, 가산세 및 최종 납부ㆍ환급세액은 계산하지 않습니다."
            ),
            "not_calculated": existing_not_calculated,
        }
    )
    return result


__all__ = ["calculate_financial_income_article62_comparison_2026"]
