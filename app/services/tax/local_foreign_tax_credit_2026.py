"""2026 local foreign-tax-credit overlay for comprehensive individual local tax.

Phase 10.5B-4.6 links the national current-year foreign tax credit calculated in
B-4.5 to the corresponding comprehensive individual local-income-tax credit.
The local credit is calculated only when the national Article 57 tax-credit path
was actually calculated. Local carryforwards remain outside this increment.
"""

from __future__ import annotations

from typing import Any

from app.services.tax.foreign_tax_credit_2026 import (
    calculate_financial_income_article62_comparison_2026 as _calculate_base,
)
from app.services.tax.rules_2026 import (
    LOCAL_FOREIGN_TAX_CREDIT_CARRYFORWARD_YEARS,
    LOCAL_FOREIGN_TAX_CREDIT_RATE_ON_NATIONAL_CREDIT,
    LOCAL_FOREIGN_TAX_CREDIT_VERIFIED_ON,
    OFFICIAL_LOCAL_FOREIGN_TAX_CREDIT_ENFORCEMENT_SOURCE_URL,
    OFFICIAL_LOCAL_FOREIGN_TAX_CREDIT_LAW_SOURCE_URL,
    OFFICIAL_LOCAL_INCOME_TAX_GENERAL_CREDIT_LINK_SOURCE_URL,
)


def calculate_financial_income_article62_comparison_2026(
    **values: object,
) -> dict[str, Any]:
    """Return B-4.5 results plus the current-year local foreign tax credit.

    Local Tax Special Treatment Control Act Article 97(1) allows a local credit
    equal to 10% of the national foreign tax credit actually taken under Income
    Tax Act Article 57(1)(1). Because the B-4.5 overlay models only that tax-credit
    path, no additional election input is needed here. If B-4.5 foreign-tax-credit
    inputs are absent, this overlay reports the local credit as not calculated.

    Article 97(2)'s five-year local carryforward is not calculated in this
    increment because B-4.5 deliberately does not determine authoritative
    national/local carryforward eligibility or exclusion amounts.
    """

    result = _calculate_base(**values)

    quality = result["data_quality"]
    national_foreign_tax_credit_calculated = bool(
        quality.get("foreign_tax_credit_calculated")
    )
    national_foreign_tax_credit = int(result.get("foreign_tax_credit_krw", 0))
    local_tax_after_dividend_credit = int(
        result[
            "article93_local_income_tax_after_dividend_credit_before_other_credits_krw"
        ]
    )

    local_foreign_tax_credit_target = 0
    if national_foreign_tax_credit_calculated:
        local_foreign_tax_credit_target = int(
            round(
                national_foreign_tax_credit
                * LOCAL_FOREIGN_TAX_CREDIT_RATE_ON_NATIONAL_CREDIT
            )
        )

    local_foreign_tax_credit = min(
        local_foreign_tax_credit_target,
        local_tax_after_dividend_credit,
    )
    reduced_by_available_local_tax_cap = (
        local_foreign_tax_credit_target - local_foreign_tax_credit
    )
    local_tax_after_dividend_and_foreign_credit = (
        local_tax_after_dividend_credit - local_foreign_tax_credit
    )

    prepaid_local_special_withholding_total = int(
        result["prepaid_financial_local_income_tax_special_withholding_total_krw"]
    )
    partial_local_balance_after_foreign_credit_and_special_withholding = (
        local_tax_after_dividend_and_foreign_credit
        - prepaid_local_special_withholding_total
    )

    result.update(
        {
            "local_foreign_tax_credit_target_10pct_of_national_krw": (
                local_foreign_tax_credit_target
            ),
            "local_foreign_tax_credit_reduced_by_available_local_income_tax_cap_krw": (
                reduced_by_available_local_tax_cap
            ),
            "local_foreign_tax_credit_krw": local_foreign_tax_credit,
            "article93_local_income_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw": (
                local_tax_after_dividend_and_foreign_credit
            ),
            "partial_local_income_tax_balance_after_explicit_financial_special_withholding_krw": (
                partial_local_balance_after_foreign_credit_and_special_withholding
            ),
        }
    )

    quality.update(
        {
            "local_income_tax_foreign_tax_credit_calculated": (
                national_foreign_tax_credit_calculated
            ),
            "local_income_tax_foreign_tax_credit_based_on_national_credit": (
                national_foreign_tax_credit_calculated
            ),
            "local_income_tax_foreign_tax_credit_current_year_only": (
                national_foreign_tax_credit_calculated
            ),
            "local_income_tax_foreign_tax_credit_prior_year_carryforward_calculated": False,
            "local_income_tax_foreign_tax_credit_carryforward_calculated": False,
            "local_income_tax_foreign_tax_credit_expense_method_supported": False,
        }
    )

    rule_context = result["rule_context"]
    not_calculated = list(rule_context.get("not_calculated", []))
    local_foreign_item = "local-income-tax foreign tax credit"
    if national_foreign_tax_credit_calculated:
        not_calculated = [
            item for item in not_calculated if item != local_foreign_item
        ]
        for item in (
            "local foreign-tax-credit carryforward determination",
            "prior-year local foreign-tax-credit carryforward",
        ):
            if item not in not_calculated:
                not_calculated.append(item)
    elif local_foreign_item not in not_calculated:
        not_calculated.append(local_foreign_item)

    rule_context.update(
        {
            "local_foreign_tax_credit_verified_on": (
                LOCAL_FOREIGN_TAX_CREDIT_VERIFIED_ON
            ),
            "local_foreign_tax_credit_legal_basis": (
                "지방세특례제한법 제97조 제1항"
            ),
            "local_foreign_tax_credit_carryforward_legal_basis": (
                "지방세특례제한법 제97조 제2항"
            ),
            "local_foreign_tax_credit_general_linkage_legal_basis": (
                "지방세특례제한법 제167조의2 제1항"
            ),
            "local_foreign_tax_credit_enforcement_legal_basis": (
                "지방세특례제한법 시행령 제48조"
            ),
            "local_foreign_tax_credit_carryforward_years": (
                LOCAL_FOREIGN_TAX_CREDIT_CARRYFORWARD_YEARS
            ),
            "official_local_foreign_tax_credit_law_source_url": (
                OFFICIAL_LOCAL_FOREIGN_TAX_CREDIT_LAW_SOURCE_URL
            ),
            "official_local_foreign_tax_credit_enforcement_source_url": (
                OFFICIAL_LOCAL_FOREIGN_TAX_CREDIT_ENFORCEMENT_SOURCE_URL
            ),
            "official_local_income_tax_general_credit_link_source_url": (
                OFFICIAL_LOCAL_INCOME_TAX_GENERAL_CREDIT_LINK_SOURCE_URL
            ),
            "local_foreign_tax_credit_formula": (
                "min(round(foreign_tax_credit_krw * 0.10), "
                "article93_local_income_tax_after_dividend_credit_before_other_credits_krw)"
            ),
            "local_foreign_tax_credit_note": (
                "지방세특례제한법 제97조 제1항에 따라 소득세법 제57조 제1항 제1호로 "
                "실제 공제된 국세 외국납부세액공제액의 10%를 종합소득분 개인지방소득세에서 "
                "공제합니다. 국세에서 같은 조 제1항 제2호의 필요경비 산입 방식을 선택한 "
                "경우에는 적용되지 않지만, B-4.5는 해당 비용처리 방식을 계산하지 않고 "
                "세액공제 방식만 명시적으로 모델링합니다. 제97조 제2항의 5년 이월공제는 "
                "이번 increment에서 계산하지 않습니다."
            ),
            "local_income_tax_scope_note": (
                "지방세법 제93조 비교산출세액, 지방 배당세액공제, 당기 지방 외국납부세액공제 "
                "및 사용자가 명시한 금융소득 특별징수 기납부세액까지 반영한 부분 계산입니다. "
                "지방 외국납부세액공제의 전기 이월액ㆍ당기 이월가능액, 다른 지방 세액공제ㆍ"
                "감면, 다른 기납부세액, 가산세 및 최종 납부ㆍ환급세액은 계산하지 않습니다."
            ),
            "not_calculated": not_calculated,
        }
    )
    return result


__all__ = ["calculate_financial_income_article62_comparison_2026"]
