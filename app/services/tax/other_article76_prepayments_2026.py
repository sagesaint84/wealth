"""2026 other Article 76 prepaid-tax deductions for national income tax.

Phase 10.5B-4.8 extends the existing partial national income-tax balance with
explicitly supplied non-financial comprehensive-income withholding tax and tax
association amounts. The service never derives those amounts from gross income.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.interim_prepayment_2026 import (
    calculate_financial_income_article62_comparison_2026 as _calculate_base,
)
from app.services.tax.personal_comprehensive_tax_2026 import PersonalComprehensiveTaxError
from app.services.tax.rules_2026 import (
    OFFICIAL_FINAL_RETURN_PREPAID_TAX_LAW_SOURCE_URL,
    OFFICIAL_INTERIM_PREPAYMENT_RETURN_FORM_SOURCE_URL,
    OFFICIAL_TAX_ASSOCIATION_LAW_SOURCE_URL,
    OTHER_ARTICLE76_PREPAID_TAX_VERIFIED_ON,
)

_OTHER_WITHHOLDING_FIELD = "prepaid_other_comprehensive_income_withholding_tax_krw"
_TAX_ASSOCIATION_FIELDS = frozenset(
    {
        "prepaid_tax_association_collected_income_tax_krw",
        "tax_association_credit_krw",
    }
)


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
    """Return B-4.7 results plus explicit Article 76(3)(4)-(5) deductions."""

    other_withholding_input_provided = _OTHER_WITHHOLDING_FIELD in values
    association_inputs_present = _TAX_ASSOCIATION_FIELDS.intersection(values)
    if association_inputs_present and association_inputs_present != _TAX_ASSOCIATION_FIELDS:
        raise PersonalComprehensiveTaxError("ARTICLE76_TAX_ASSOCIATION_INPUTS_INCOMPLETE")
    tax_association_inputs_provided = association_inputs_present == _TAX_ASSOCIATION_FIELDS

    base_values = {
        name: value
        for name, value in values.items()
        if name != _OTHER_WITHHOLDING_FIELD and name not in _TAX_ASSOCIATION_FIELDS
    }
    result = _calculate_base(**base_values)

    other_withholding = 0
    if other_withholding_input_provided:
        other_withholding = _nonnegative_won(
            values[_OTHER_WITHHOLDING_FIELD],
            "ARTICLE76_OTHER_WITHHOLDING_AMOUNT_INVALID",
        )

    association_collected = 0
    association_credit = 0
    if tax_association_inputs_provided:
        association_collected = _nonnegative_won(
            values["prepaid_tax_association_collected_income_tax_krw"],
            "ARTICLE76_TAX_ASSOCIATION_AMOUNT_INVALID",
        )
        association_credit = _nonnegative_won(
            values["tax_association_credit_krw"],
            "ARTICLE76_TAX_ASSOCIATION_AMOUNT_INVALID",
        )

    article76_other_total = other_withholding + association_collected + association_credit
    partial_before_other = int(
        result[
            "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw"
        ]
    )
    partial_after_other = partial_before_other - article76_other_total

    result.update(
        {
            "prepaid_other_comprehensive_income_withholding_tax_krw": other_withholding,
            "prepaid_tax_association_collected_income_tax_krw": association_collected,
            "tax_association_credit_krw": association_credit,
            "article76_other_withholding_and_tax_association_deduction_total_krw": (
                article76_other_total
            ),
            "partial_national_income_tax_balance_after_explicit_article76_deductions_krw": (
                partial_after_other
            ),
        }
    )

    quality = result["data_quality"]
    quality.update(
        {
            "other_comprehensive_income_withholding_tax_calculated": (
                other_withholding_input_provided
            ),
            "other_comprehensive_income_withholding_tax_user_provided": (
                other_withholding_input_provided
            ),
            "other_comprehensive_income_withholding_tax_not_inferred_from_income": True,
            "tax_association_final_return_deductions_calculated": (
                tax_association_inputs_provided
            ),
            "tax_association_inputs_provided": tax_association_inputs_provided,
            "tax_association_amounts_user_provided": tax_association_inputs_provided,
            "tax_association_amounts_not_inferred_from_income": True,
            "article76_land_sale_and_special_assessment_prepaid_taxes_calculated": False,
            "other_article76_prepaid_income_taxes_calculated": False,
            "national_income_tax_final_payment_or_refund_calculated": False,
        }
    )

    rule_context = result["rule_context"]
    not_calculated = list(rule_context.get("not_calculated", []))
    legacy_item = "other Article 76 prepaid income taxes"
    not_calculated = [item for item in not_calculated if item != legacy_item]

    scoped_items = (
        (
            "other comprehensive-income withholding tax",
            other_withholding_input_provided,
        ),
        (
            "tax association collected income tax and tax association credit",
            tax_association_inputs_provided,
        ),
    )
    for item, calculated in scoped_items:
        if calculated:
            not_calculated = [existing for existing in not_calculated if existing != item]
        elif item not in not_calculated:
            not_calculated.append(item)

    for item in (
        "land-sale scheduled-return prepaid income tax",
        "special-assessment prepaid income tax",
        "national income-tax additions or penalties",
        "final national income-tax payment or refund amount",
    ):
        if item not in not_calculated:
            not_calculated.append(item)

    reflected_parts = [
        "금융소득 원천징수 기납부세액",
    ]
    if result["data_quality"].get("national_income_tax_interim_prepayment_calculated"):
        reflected_parts.append("중간예납세액")
    if other_withholding_input_provided:
        reflected_parts.append("금융소득 외 종합소득 원천징수세액")
    if tax_association_inputs_provided:
        reflected_parts.append("납세조합 징수세액과 납세조합공제")

    rule_context.update(
        {
            "other_article76_prepaid_tax_verified_on": (
                OTHER_ARTICLE76_PREPAID_TAX_VERIFIED_ON
            ),
            "other_withholding_final_return_legal_basis": "소득세법 제76조 제3항 제4호",
            "tax_association_final_return_legal_basis": "소득세법 제76조 제3항 제5호",
            "tax_association_collection_legal_basis": "소득세법 제150조",
            "official_other_article76_final_return_law_source_url": (
                OFFICIAL_FINAL_RETURN_PREPAID_TAX_LAW_SOURCE_URL
            ),
            "official_tax_association_law_source_url": OFFICIAL_TAX_ASSOCIATION_LAW_SOURCE_URL,
            "official_other_article76_return_form_source_url": (
                OFFICIAL_INTERIM_PREPAYMENT_RETURN_FORM_SOURCE_URL
            ),
            "other_article76_prepayment_note": (
                "소득세법 제76조 제3항 제4호는 제127조 원천징수세액을, 같은 항 제5호는 "
                "제150조 납세조합의 징수세액과 그 공제액을 확정신고납부 시 공제하도록 "
                "합니다. 별지 제40호서식(1)은 사업ㆍ근로ㆍ연금ㆍ기타소득의 원천징수 또는 "
                "납세조합징수세액을 기납부세액명세서에 구분해 적도록 합니다. 이 increment는 "
                "실제 확인된 금액만 사용자 명시 입력으로 받고 gross 소득에서 자동 추정하지 "
                "않습니다."
            ),
            "partial_balance_note": (
                "모델링된 배당세액공제와 당기 국세 외국납부세액공제 후 "
                + ", ".join(reflected_parts)
                + "을 반영한 부분 계산값입니다. 토지등 매매차익 예정신고세액, 수시부과세액, "
                "가산세 및 다른 미구현 세액공제ㆍ감면이 빠져 있어 최종 납부 또는 환급세액이 "
                "아닙니다."
            ),
            "not_calculated": not_calculated,
        }
    )
    return result


__all__ = ["calculate_financial_income_article62_comparison_2026"]
