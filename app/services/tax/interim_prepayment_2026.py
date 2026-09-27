"""2026 interim-prepayment overlay for comprehensive national income tax.

Phase 10.5B-4.7 subtracts an explicitly supplied interim-prepayment amount from
the existing partial national income-tax balance. The service does not estimate
the amount from a prior-year tax base; callers must provide the amount actually
reflected as interim prepaid income tax for the current return.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.local_foreign_tax_credit_2026 import (
    calculate_financial_income_article62_comparison_2026 as _calculate_base,
)
from app.services.tax.personal_comprehensive_tax_2026 import PersonalComprehensiveTaxError
from app.services.tax.rules_2026 import (
    INTERIM_PREPAID_INCOME_TAX_VERIFIED_ON,
    OFFICIAL_FINAL_RETURN_PREPAID_TAX_LAW_SOURCE_URL,
    OFFICIAL_INCOME_TAX_REFUND_LAW_SOURCE_URL,
    OFFICIAL_INTERIM_PREPAYMENT_LAW_SOURCE_URL,
    OFFICIAL_RULE_SOURCE_URL,
)

_INTERIM_PREPAYMENT_FIELD = "prepaid_interim_income_tax_krw"


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
    """Return B-4.6 results plus optional interim prepaid national income tax.

    Income Tax Act Article 76(3)(1) requires the Article 65 interim-prepayment
    amount to be deducted when making the final return payment. This increment
    accepts only the amount explicitly supplied by the caller and deliberately
    does not derive the amount from prior-year tax or the Article 65 formula.
    """

    interim_input_provided = _INTERIM_PREPAYMENT_FIELD in values
    base_values = {
        name: value for name, value in values.items() if name != _INTERIM_PREPAYMENT_FIELD
    }
    result = _calculate_base(**base_values)

    prepaid_interim_income_tax = 0
    if interim_input_provided:
        prepaid_interim_income_tax = _nonnegative_won(
            values[_INTERIM_PREPAYMENT_FIELD],
            "ARTICLE76_INTERIM_PREPAYMENT_AMOUNT_INVALID",
        )

    partial_before_interim = int(
        result[
            "partial_national_income_tax_balance_after_explicit_financial_withholding_krw"
        ]
    )
    partial_after_interim = partial_before_interim - prepaid_interim_income_tax

    result.update(
        {
            "prepaid_interim_income_tax_krw": prepaid_interim_income_tax,
            "partial_national_income_tax_balance_after_explicit_financial_withholding_and_interim_prepayment_krw": (
                partial_after_interim
            ),
        }
    )

    quality = result["data_quality"]
    quality.update(
        {
            "national_income_tax_interim_prepayment_calculated": (
                interim_input_provided
            ),
            "national_income_tax_interim_prepayment_input_provided": (
                interim_input_provided
            ),
            "national_income_tax_interim_prepayment_user_provided": (
                interim_input_provided
            ),
            "national_income_tax_interim_prepayment_not_inferred_from_prior_year_tax": True,
            "other_article76_prepaid_income_taxes_calculated": False,
            "national_income_tax_final_payment_or_refund_calculated": False,
        }
    )

    rule_context = result["rule_context"]
    not_calculated = list(rule_context.get("not_calculated", []))
    interim_item = "interim prepaid income tax"
    if interim_input_provided:
        not_calculated = [item for item in not_calculated if item != interim_item]
    elif interim_item not in not_calculated:
        not_calculated.append(interim_item)

    for item in (
        "other Article 76 prepaid income taxes",
        "national income-tax additions or penalties",
        "final national income-tax payment or refund amount",
    ):
        if item not in not_calculated:
            not_calculated.append(item)

    if interim_input_provided:
        partial_balance_note = (
            "모델링된 배당세액공제, 당기 국세 외국납부세액공제, 금융소득 원천징수 "
            "기납부세액 및 사용자가 명시한 중간예납세액까지 반영한 부분 계산값입니다. "
            "토지등 매매차익 예정신고세액, 수시부과세액, 다른 소득 원천징수세액, "
            "납세조합 징수세액ㆍ공제액, 가산세 및 다른 미구현 세액공제ㆍ감면이 빠져 "
            "있어 최종 납부 또는 환급세액이 아닙니다."
        )
    else:
        partial_balance_note = (
            "모델링된 배당세액공제, 당기 국세 외국납부세액공제 및 금융소득 원천징수 "
            "기납부세액까지 반영한 부분 계산값입니다. 중간예납세액, 토지등 매매차익 "
            "예정신고세액, 수시부과세액, 다른 소득 원천징수세액, 납세조합 징수세액ㆍ"
            "공제액, 가산세 및 다른 미구현 세액공제ㆍ감면이 빠져 있어 최종 납부 또는 "
            "환급세액이 아닙니다."
        )

    rule_context.update(
        {
            "interim_prepaid_income_tax_verified_on": (
                INTERIM_PREPAID_INCOME_TAX_VERIFIED_ON
            ),
            "interim_prepayment_legal_basis": "소득세법 제65조",
            "interim_prepayment_final_return_credit_legal_basis": (
                "소득세법 제76조 제3항 제1호"
            ),
            "interim_prepayment_refund_legal_basis": "소득세법 제85조 제4항",
            "official_interim_prepayment_law_source_url": (
                OFFICIAL_INTERIM_PREPAYMENT_LAW_SOURCE_URL
            ),
            "official_final_return_prepaid_tax_law_source_url": (
                OFFICIAL_FINAL_RETURN_PREPAID_TAX_LAW_SOURCE_URL
            ),
            "official_income_tax_refund_law_source_url": (
                OFFICIAL_INCOME_TAX_REFUND_LAW_SOURCE_URL
            ),
            "official_income_tax_return_form_source_url": OFFICIAL_RULE_SOURCE_URL,
            "interim_prepayment_note": (
                "소득세법 제76조 제3항 제1호에 따라 제65조의 중간예납세액은 "
                "확정신고납부 시 공제되는 기납부세액입니다. 별지 제40호서식(1)도 "
                "중간예납세액을 기납부세액으로 별도 표시합니다. 이 increment는 "
                "신고서 또는 홈택스 등에서 확인된 실제 반영액만 사용자 명시 입력으로 "
                "받고 전년도 세액의 2분의 1이나 중간예납추계액을 자동 계산하지 않습니다."
            ),
            "partial_balance_note": partial_balance_note,
            "not_calculated": not_calculated,
        }
    )
    return result


__all__ = ["calculate_financial_income_article62_comparison_2026"]
