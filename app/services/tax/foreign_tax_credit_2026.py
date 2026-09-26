"""2026 national foreign-tax-credit overlay for the Article 62 comparison.

Phase 10.5B-4.5 keeps the existing national/local comparison contract intact and
adds a bounded Income Tax Act Article 57 calculation only when the caller
provides official-form-ready inputs and confirms that no unmodeled Article 60
item must precede the current-year foreign tax credit.
"""

from __future__ import annotations

import math
import re
from typing import Any

from app.services.tax.local_income_tax_2026 import (
    calculate_financial_income_article62_comparison_2026 as _calculate_base,
)
from app.services.tax.personal_comprehensive_tax_2026 import PersonalComprehensiveTaxError
from app.services.tax.rules_2026 import (
    FOREIGN_TAX_CREDIT_VERIFIED_ON,
    OFFICIAL_FOREIGN_TAX_CREDIT_ENFORCEMENT_SOURCE_URL,
    OFFICIAL_FOREIGN_TAX_CREDIT_FORM_SOURCE_URL,
    OFFICIAL_FOREIGN_TAX_CREDIT_LAW_SOURCE_URL,
)


_FOREIGN_TAX_CREDIT_FIELDS = frozenset(
    {
        "comprehensive_income_amount_for_foreign_tax_credit_krw",
        "foreign_tax_credit_items",
        "no_other_article60_preceding_tax_reductions_or_credits_confirmed",
    }
)
_FOREIGN_TAX_CREDIT_ITEM_FIELDS = frozenset(
    {
        "country_code",
        "limit_basis_foreign_source_income_krw",
        "eligible_current_year_foreign_income_tax_krw",
    }
)
_COUNTRY_CODE_RE = re.compile(r"[A-Z]{2}")


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


def _positive_won(value: object, code: str) -> int:
    amount = _nonnegative_won(value, code)
    if amount <= 0:
        raise PersonalComprehensiveTaxError(code)
    return amount


def _article60_scope_confirmation(value: object) -> bool:
    if value is not True:
        raise PersonalComprehensiveTaxError(
            "ARTICLE57_OTHER_ARTICLE60_PRECEDING_ITEMS_UNSUPPORTED"
        )
    return True


def _country_code(value: object) -> str:
    if not isinstance(value, str):
        raise PersonalComprehensiveTaxError(
            "ARTICLE57_FOREIGN_TAX_CREDIT_COUNTRY_CODE_INVALID"
        )
    normalized = value.strip().upper()
    if not _COUNTRY_CODE_RE.fullmatch(normalized):
        raise PersonalComprehensiveTaxError(
            "ARTICLE57_FOREIGN_TAX_CREDIT_COUNTRY_CODE_INVALID"
        )
    return normalized


def _foreign_tax_credit_items(value: object) -> list[dict[str, int | str]]:
    if not isinstance(value, list) or not value:
        raise PersonalComprehensiveTaxError(
            "ARTICLE57_FOREIGN_TAX_CREDIT_ITEMS_INVALID"
        )

    normalized: list[dict[str, int | str]] = []
    seen_country_codes: set[str] = set()
    for raw_item in value:
        if not isinstance(raw_item, dict) or set(raw_item) != set(
            _FOREIGN_TAX_CREDIT_ITEM_FIELDS
        ):
            raise PersonalComprehensiveTaxError(
                "ARTICLE57_FOREIGN_TAX_CREDIT_ITEMS_INVALID"
            )

        country_code = _country_code(raw_item["country_code"])
        if country_code in seen_country_codes:
            raise PersonalComprehensiveTaxError(
                "ARTICLE57_FOREIGN_TAX_CREDIT_COUNTRY_DUPLICATE"
            )
        seen_country_codes.add(country_code)
        normalized.append(
            {
                "country_code": country_code,
                "limit_basis_foreign_source_income_krw": _nonnegative_won(
                    raw_item["limit_basis_foreign_source_income_krw"],
                    "ARTICLE57_FOREIGN_TAX_CREDIT_AMOUNT_INVALID",
                ),
                "eligible_current_year_foreign_income_tax_krw": _nonnegative_won(
                    raw_item["eligible_current_year_foreign_income_tax_krw"],
                    "ARTICLE57_FOREIGN_TAX_CREDIT_AMOUNT_INVALID",
                ),
            }
        )
    return normalized


def calculate_financial_income_article62_comparison_2026(
    **values: object,
) -> dict[str, Any]:
    """Return the existing Article 62/local result plus optional Article 57 credit.

    Foreign-tax-credit inputs are all-or-none.  The caller supplies Form 11
    comprehensive income, one official-form-ready basis amount and eligible
    current-year foreign income tax amount per ISO country, and an explicit
    confirmation that no tax reduction, non-carryforward credit, prior-year
    carryforward credit, or other unmodeled Article 60 item must be applied
    before this current-year foreign tax credit.  If that confirmation cannot
    be made, this narrow increment fails closed instead of overstating credit.
    """

    provided_fields = set(values)
    foreign_fields_present = provided_fields & _FOREIGN_TAX_CREDIT_FIELDS
    if foreign_fields_present and foreign_fields_present != set(
        _FOREIGN_TAX_CREDIT_FIELDS
    ):
        raise PersonalComprehensiveTaxError(
            "ARTICLE57_FOREIGN_TAX_CREDIT_INPUTS_INCOMPLETE"
        )

    foreign_inputs_provided = bool(foreign_fields_present)
    base_values = {
        name: value
        for name, value in values.items()
        if name not in _FOREIGN_TAX_CREDIT_FIELDS
    }
    result = _calculate_base(**base_values)

    comprehensive_income_amount = 0
    article60_scope_confirmed = False
    calculated_items: list[dict[str, int | str]] = []
    total_limit_basis_income = 0
    aggregate_limit = 0
    country_limit_total = 0
    eligible_foreign_tax_total = 0
    within_country_limits_total = 0
    foreign_tax_credit = 0
    reduced_by_preceding_dividend_credit = 0
    uncredited_current_year_foreign_tax = 0

    article62_tax_before_credits = result[
        "article62_comparison_tax_before_credits_krw"
    ]
    tax_after_dividend_credit = result[
        "article62_tax_after_dividend_credit_before_other_credits_krw"
    ]

    if foreign_inputs_provided:
        comprehensive_income_amount = _positive_won(
            values["comprehensive_income_amount_for_foreign_tax_credit_krw"],
            "ARTICLE57_COMPREHENSIVE_INCOME_AMOUNT_INVALID",
        )
        article60_scope_confirmed = _article60_scope_confirmation(
            values[
                "no_other_article60_preceding_tax_reductions_or_credits_confirmed"
            ]
        )
        normalized_items = _foreign_tax_credit_items(
            values["foreign_tax_credit_items"]
        )
        total_limit_basis_income = sum(
            int(item["limit_basis_foreign_source_income_krw"])
            for item in normalized_items
        )
        if total_limit_basis_income > comprehensive_income_amount:
            raise PersonalComprehensiveTaxError(
                "ARTICLE57_FOREIGN_TAX_CREDIT_BASIS_EXCEEDS_COMPREHENSIVE_INCOME"
            )

        aggregate_limit = int(
            round(
                article62_tax_before_credits
                * total_limit_basis_income
                / comprehensive_income_amount
            )
        )

        for item in normalized_items:
            basis_income = int(item["limit_basis_foreign_source_income_krw"])
            eligible_foreign_tax = int(
                item["eligible_current_year_foreign_income_tax_krw"]
            )
            country_limit = int(
                round(
                    article62_tax_before_credits
                    * basis_income
                    / comprehensive_income_amount
                )
            )
            within_country_limit = min(eligible_foreign_tax, country_limit)
            calculated_items.append(
                {
                    **item,
                    "foreign_tax_credit_limit_krw": country_limit,
                    "foreign_tax_credit_within_country_limit_krw": (
                        within_country_limit
                    ),
                    "uncredited_due_to_country_limit_before_article60_order_krw": (
                        eligible_foreign_tax - within_country_limit
                    ),
                }
            )
            country_limit_total += country_limit
            eligible_foreign_tax_total += eligible_foreign_tax
            within_country_limits_total += within_country_limit

        credit_before_article60_cap = min(
            within_country_limits_total,
            aggregate_limit,
        )
        foreign_tax_credit = min(
            credit_before_article60_cap,
            tax_after_dividend_credit,
        )
        reduced_by_preceding_dividend_credit = (
            credit_before_article60_cap - foreign_tax_credit
        )
        uncredited_current_year_foreign_tax = (
            eligible_foreign_tax_total - foreign_tax_credit
        )

    tax_after_dividend_and_foreign_credit = (
        tax_after_dividend_credit - foreign_tax_credit
    )
    prepaid_financial_withholding_total = result[
        "prepaid_financial_income_withholding_tax_total_krw"
    ]
    partial_balance_after_foreign_credit_and_withholding = (
        tax_after_dividend_and_foreign_credit
        - prepaid_financial_withholding_total
    )

    result.update(
        {
            "comprehensive_income_amount_for_foreign_tax_credit_krw": (
                comprehensive_income_amount
            ),
            "no_other_article60_preceding_tax_reductions_or_credits_confirmed": (
                article60_scope_confirmed
            ),
            "foreign_tax_credit_items": calculated_items,
            "foreign_tax_credit_limit_basis_income_total_krw": (
                total_limit_basis_income
            ),
            "foreign_tax_credit_aggregate_limit_krw": aggregate_limit,
            "foreign_tax_credit_country_limit_total_krw": country_limit_total,
            "eligible_current_year_foreign_income_tax_total_krw": (
                eligible_foreign_tax_total
            ),
            "foreign_tax_credit_within_country_limits_total_krw": (
                within_country_limits_total
            ),
            "foreign_tax_credit_reduced_by_preceding_dividend_credit_krw": (
                reduced_by_preceding_dividend_credit
            ),
            "foreign_tax_credit_krw": foreign_tax_credit,
            "uncredited_current_year_foreign_income_tax_total_krw": (
                uncredited_current_year_foreign_tax
            ),
            "article62_tax_after_dividend_and_foreign_tax_credit_before_other_credits_krw": (
                tax_after_dividend_and_foreign_credit
            ),
            "partial_national_income_tax_balance_after_explicit_financial_withholding_krw": (
                partial_balance_after_foreign_credit_and_withholding
            ),
        }
    )

    data_quality = result["data_quality"]
    data_quality.update(
        {
            "foreign_tax_credit_calculated": foreign_inputs_provided,
            "foreign_tax_credit_inputs_provided": foreign_inputs_provided,
            "foreign_tax_credit_country_level_inputs_provided": foreign_inputs_provided,
            "foreign_tax_credit_limit_basis_user_provided": foreign_inputs_provided,
            "foreign_tax_credit_eligibility_user_asserted": foreign_inputs_provided,
            "foreign_tax_credit_article60_scope_confirmed": article60_scope_confirmed,
            "foreign_tax_credit_current_year_only": foreign_inputs_provided,
            "foreign_tax_credit_prior_year_carryforward_calculated": False,
            "foreign_tax_credit_carryforward_calculated": False,
            "foreign_tax_credit_carryforward_exclusion_calculated": False,
            "foreign_tax_credit_corresponding_expense_allocation_calculated": False,
            "foreign_tax_credit_loss_country_adjustment_calculated": False,
            "foreign_tax_credit_treaty_limit_verified_by_service": False,
            "local_income_tax_foreign_tax_credit_calculated": False,
        }
    )

    rule_context = result["rule_context"]
    not_calculated = list(rule_context.get("not_calculated", []))
    if foreign_inputs_provided:
        not_calculated = [
            item for item in not_calculated if item != "foreign tax credit"
        ]
        foreign_scope_items = [
            "current-year excess foreign tax carryforward determination",
            "foreign-tax-credit carryforward eligibility/exclusion",
            "foreign-source-income corresponding-expense allocation",
            "foreign loss-country basis adjustment",
            "foreign tax treaty eligibility verification",
            "local-income-tax foreign tax credit",
        ]
        for item in foreign_scope_items:
            if item not in not_calculated:
                not_calculated.append(item)

    rule_context.update(
        {
            "foreign_tax_credit_verified_on": FOREIGN_TAX_CREDIT_VERIFIED_ON,
            "foreign_tax_credit_legal_basis": "소득세법 제57조 제1항",
            "foreign_tax_credit_carryforward_legal_basis": "소득세법 제57조 제2항",
            "foreign_tax_credit_order_legal_basis": "소득세법 제60조 제1항",
            "foreign_tax_credit_enforcement_legal_basis": (
                "소득세법 시행령 제117조 제1항ㆍ제2항ㆍ제3항ㆍ제7항ㆍ제10항"
            ),
            "official_foreign_tax_credit_law_source_url": (
                OFFICIAL_FOREIGN_TAX_CREDIT_LAW_SOURCE_URL
            ),
            "official_foreign_tax_credit_enforcement_source_url": (
                OFFICIAL_FOREIGN_TAX_CREDIT_ENFORCEMENT_SOURCE_URL
            ),
            "official_foreign_tax_credit_form_source_url": (
                OFFICIAL_FOREIGN_TAX_CREDIT_FORM_SOURCE_URL
            ),
            "foreign_tax_credit_limit_formula": (
                "article62_comparison_tax_before_credits_krw * "
                "foreign_tax_credit_limit_basis_income_total_krw / "
                "comprehensive_income_amount_for_foreign_tax_credit_krw"
            ),
            "foreign_tax_credit_note": (
                "소득세법 제57조와 별지 제11호서식의 국가별 공제한도 구조를 적용합니다. "
                "국가별 기준 국외원천소득은 대응비용ㆍ감면ㆍ결손국가 조정이 끝난 신고서 "
                "기준금액을 사용자가 명시해야 하고, 입력 외국소득세액의 시행령 제117조 "
                "및 조세조약상 공제 적격성도 사용자 확인값으로 취급합니다. 소득세법 "
                "제60조상 현재 모델의 배당세액공제 외에 먼저 적용할 세액감면ㆍ비이월 "
                "세액공제ㆍ전기 이월 세액공제 등이 없다는 명시 확인이 있을 때만 당기 "
                "외국납부세액공제를 계산합니다. 당기 미공제액은 이월배제액 등을 계산하지 "
                "않았으므로 곧바로 10년 이월공제액으로 표시하지 않습니다."
            ),
            "partial_balance_note": (
                "모델링된 배당세액공제, 명시 확인 범위의 당기 국세 외국납부세액공제 및 "
                "금융소득 원천징수 기납부세액을 반영한 부분 계산값입니다. 다른 세액감면ㆍ"
                "세액공제ㆍ기납부세액ㆍ중간예납ㆍ가산세 등이 빠져 있어 최종 납부 또는 "
                "환급세액이 아닙니다."
            ),
            "not_calculated": not_calculated,
        }
    )
    return result


__all__ = ["calculate_financial_income_article62_comparison_2026"]
