"""2026 tax-association credit overlay for national comprehensive income tax.

Phase 10.5B-4.9 applies an explicitly supplied tax-association credit before the
current-year foreign-tax credit. The amount comes from the tax-association
receipt / return input and is never inferred from income or the statutory rate.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.local_income_tax_2026 import (
    calculate_financial_income_article62_comparison_2026 as _calculate_base,
)
from app.services.tax.personal_comprehensive_tax_2026 import PersonalComprehensiveTaxError
from app.services.tax.rules_2026 import (
    OFFICIAL_INTERIM_PREPAYMENT_RETURN_FORM_SOURCE_URL,
    OFFICIAL_TAX_ASSOCIATION_LAW_SOURCE_URL,
    OFFICIAL_TAX_CREDIT_ORDER_LAW_SOURCE_URL,
    TAX_ASSOCIATION_CREDIT_VERIFIED_ON,
)

_TAX_ASSOCIATION_CREDIT_FIELD = "tax_association_credit_krw"


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


def calculate_financial_income_article62_comparison_2026(
    **values: object,
) -> dict[str, Any]:
    """Return B-4.4.2/local results plus optional national tax-association credit.

    The caller supplies the credit amount actually shown on the tax-association
    receipt / return. The service does not reconstruct the amount from wages,
    business income, collected tax, or the Article 150 percentage.
    """

    credit_input_provided = _TAX_ASSOCIATION_CREDIT_FIELD in values
    base_values = {
        name: value
        for name, value in values.items()
        if name != _TAX_ASSOCIATION_CREDIT_FIELD
    }
    result = _calculate_base(**base_values)

    credit_input = 0
    if credit_input_provided:
        credit_input = _nonnegative_won(
            values[_TAX_ASSOCIATION_CREDIT_FIELD],
            "ARTICLE150_TAX_ASSOCIATION_CREDIT_AMOUNT_INVALID",
        )

    tax_after_dividend_credit = int(
        result["article62_tax_after_dividend_credit_before_other_credits_krw"]
    )
    credit_applied = min(credit_input, tax_after_dividend_credit)
    reduced_by_available_tax = credit_input - credit_applied
    tax_after_tax_association_credit = tax_after_dividend_credit - credit_applied

    result.update(
        {
            "tax_association_credit_krw": credit_input,
            "tax_association_credit_applied_krw": credit_applied,
            "tax_association_credit_reduced_by_available_national_income_tax_cap_krw": (
                reduced_by_available_tax
            ),
            "article62_tax_after_dividend_and_tax_association_credit_before_foreign_tax_credit_krw": (
                tax_after_tax_association_credit
            ),
        }
    )

    quality = result["data_quality"]
    quality.update(
        {
            "tax_association_credit_calculated": credit_input_provided,
            "tax_association_credit_input_provided": credit_input_provided,
            "tax_association_credit_user_provided": credit_input_provided,
            "tax_association_credit_not_inferred_from_income_or_rate": True,
            "tax_association_credit_statutory_rate_auto_calculated": False,
        }
    )

    rule_context = result["rule_context"]
    not_calculated = list(rule_context.get("not_calculated", []))
    item = "tax association credit"
    if credit_input_provided:
        not_calculated = [existing for existing in not_calculated if existing != item]
    elif item not in not_calculated:
        not_calculated.append(item)

    rule_context.update(
        {
            "tax_association_credit_verified_on": TAX_ASSOCIATION_CREDIT_VERIFIED_ON,
            "tax_association_credit_legal_basis": "소득세법 제150조 제3항",
            "tax_association_credit_order_legal_basis": "소득세법 제60조 제1항",
            "official_tax_association_credit_law_source_url": (
                OFFICIAL_TAX_ASSOCIATION_LAW_SOURCE_URL
            ),
            "official_tax_association_credit_order_source_url": (
                OFFICIAL_TAX_CREDIT_ORDER_LAW_SOURCE_URL
            ),
            "official_tax_association_credit_return_form_source_url": (
                OFFICIAL_INTERIM_PREPAYMENT_RETURN_FORM_SOURCE_URL
            ),
            "tax_association_credit_note": (
                "2026년 현행 소득세법 제150조 제3항의 적용 대상 납세조합은 2027년 "
                "12월 31일까지 매월 징수세액의 3%를 공제하고 징수할 수 있습니다. "
                "별지 제40호서식은 납세조합공제를 세액공제 항목으로 별도 표시합니다. "
                "이 increment는 납세조합영수증 또는 신고서에서 확인된 실제 공제액만 "
                "사용자 명시 입력으로 받고 3%를 자동 계산하지 않습니다. 입력 공제액이 "
                "현재 사용 가능한 국세 산출세액을 초과하면 적용액은 0원 미만으로 내려가지 "
                "않도록 제한하며 초과분을 별도 표시합니다."
            ),
            "not_calculated": not_calculated,
        }
    )
    return result


__all__ = ["calculate_financial_income_article62_comparison_2026"]
