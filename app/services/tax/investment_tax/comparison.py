"""Personal versus family-corporation investment-tax screening for 2026.

This module deliberately reports known/estimated tax layers separately from
items that require a full return, payer classification, or professional tax
judgment.  It must not be used as a legal tax determination.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.investment_tax import rules_2026 as rules


ASSET_DOMESTIC_DIVIDEND_STOCK = "domestic_dividend_stock"
ASSET_KR_LISTED_US_ETF = "kr_listed_us_etf"
ASSET_US_DIRECT = "us_direct"
SUPPORTED_ASSET_TYPES = {
    ASSET_DOMESTIC_DIVIDEND_STOCK,
    ASSET_KR_LISTED_US_ETF,
    ASSET_US_DIRECT,
}


class InvestmentTaxComparisonError(ValueError):
    """Stable validation error used by later API/UI layers."""


def _nonnegative(value: object, code: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvestmentTaxComparisonError(code) from exc
    if not math.isfinite(number) or number < 0:
        raise InvestmentTaxComparisonError(code)
    return number


def _percentage(value: object, code: str) -> float:
    number = _nonnegative(value, code)
    if number > 100:
        raise InvestmentTaxComparisonError(code)
    return number


def _won(value: float) -> int:
    return int(round(value))


def _progressive_tax(base: float, brackets: tuple[tuple[int | None, float], ...]) -> float:
    remaining = max(base, 0.0)
    lower = 0.0
    tax = 0.0
    for upper, rate in brackets:
        if upper is None:
            tax += max(remaining - lower, 0.0) * rate
            break
        taxable = min(max(remaining - lower, 0.0), float(upper) - lower)
        tax += taxable * rate
        if remaining <= upper:
            break
        lower = float(upper)
    return tax


def _domestic_dividend_exclusion_rate(
    *,
    eligible: bool,
    ownership_pct: float,
    holding_months: float,
) -> float:
    if not eligible or holding_months < rules.DOMESTIC_DIVIDEND_MIN_HOLDING_MONTHS:
        return 0.0
    for minimum_pct, exclusion_rate in rules.DOMESTIC_DIVIDEND_EXCLUSION_TIERS:
        if ownership_pct >= minimum_pct:
            return exclusion_rate
    return 0.0


def _individual_projection(
    *,
    asset_type: str,
    annual_distribution_krw: float,
    annual_realized_gain_krw: float,
    taxable_etf_gain_krw: float | None,
    existing_financial_income_krw: float,
) -> dict[str, Any]:
    gross_cash_return = annual_distribution_krw + annual_realized_gain_krw
    notes: list[str] = []
    data_quality: dict[str, Any] = {
        "legal_tax_determination": False,
        "comprehensive_income_final_tax_calculated": False,
        "health_insurance_calculated": False,
        "high_dividend_special_rule_calculated": False,
    }

    dividend_withholding = 0.0
    foreign_dividend_withholding = 0.0
    capital_gain_income_tax = 0.0
    capital_gain_local_tax = 0.0
    taxable_capital_gain = 0.0

    if asset_type == ASSET_DOMESTIC_DIVIDEND_STOCK:
        financial_income_addition = annual_distribution_krw
        dividend_withholding = (
            financial_income_addition * rules.GENERAL_DIVIDEND_WITHHOLDING_RATE
        )
        if annual_realized_gain_krw > 0:
            notes.append(
                "Domestic listed-stock sale-gain tax is not calculated because major-shareholder and security-specific status is not provided."
            )
            data_quality["domestic_stock_sale_gain_tax_calculated"] = False
        else:
            data_quality["domestic_stock_sale_gain_tax_calculated"] = True

    elif asset_type == ASSET_KR_LISTED_US_ETF:
        if taxable_etf_gain_krw is None:
            taxable_gain_basis = annual_realized_gain_krw
            data_quality["taxable_etf_gain_basis"] = "realized_gain_conservative_fallback"
            notes.append(
                "ETF taxable gain basis was not supplied; realized gain is used as a conservative screening fallback."
            )
        else:
            taxable_gain_basis = taxable_etf_gain_krw
            data_quality["taxable_etf_gain_basis"] = "provided"
        financial_income_addition = annual_distribution_krw + taxable_gain_basis
        dividend_withholding = (
            financial_income_addition * rules.GENERAL_DIVIDEND_WITHHOLDING_RATE
        )
        data_quality["domestic_stock_sale_gain_tax_calculated"] = True

    else:  # ASSET_US_DIRECT
        financial_income_addition = annual_distribution_krw
        foreign_dividend_withholding = (
            annual_distribution_krw * rules.US_TREATY_GENERAL_DIVIDEND_RATE
        )
        taxable_capital_gain = max(
            annual_realized_gain_krw - rules.FOREIGN_SHARE_CAPITAL_GAIN_DEDUCTION_KRW,
            0.0,
        )
        capital_gain_income_tax = (
            taxable_capital_gain * rules.FOREIGN_SHARE_CAPITAL_GAIN_INCOME_TAX_RATE
        )
        capital_gain_local_tax = (
            taxable_capital_gain * rules.FOREIGN_SHARE_CAPITAL_GAIN_LOCAL_TAX_RATE
        )
        notes.append(
            "US dividend Korean final settlement and foreign-tax-credit limit are not calculated; treaty withholding is shown separately."
        )
        data_quality["us_dividend_korean_final_tax_calculated"] = False

    projected_financial_income = existing_financial_income_krw + financial_income_addition
    comprehensive_screening = (
        projected_financial_income
        > rules.FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
    )
    if comprehensive_screening:
        notes.append(
            "Projected financial income exceeds the 20 million KRW comprehensive-tax screening threshold; final progressive income tax is not calculated."
        )

    known_tax = (
        dividend_withholding
        + foreign_dividend_withholding
        + capital_gain_income_tax
        + capital_gain_local_tax
    )
    return {
        "asset_type": asset_type,
        "gross_cash_return_krw": _won(gross_cash_return),
        "financial_income_addition_krw": _won(financial_income_addition),
        "projected_financial_income_krw": _won(projected_financial_income),
        "comprehensive_tax_threshold_krw": rules.FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
        "comprehensive_tax_screening": comprehensive_screening,
        "taxable_foreign_share_gain_krw": _won(taxable_capital_gain),
        "taxes": {
            "domestic_dividend_withholding_krw": _won(dividend_withholding),
            "us_dividend_withholding_krw": _won(foreign_dividend_withholding),
            "foreign_share_capital_gain_income_tax_krw": _won(capital_gain_income_tax),
            "foreign_share_capital_gain_local_tax_krw": _won(capital_gain_local_tax),
            "known_tax_total_krw": _won(known_tax),
        },
        "after_known_tax_cash_krw": _won(gross_cash_return - known_tax),
        "data_quality": data_quality,
        "notes": notes,
    }


def _corporation_projection(
    *,
    asset_type: str,
    annual_distribution_krw: float,
    annual_realized_gain_krw: float,
    existing_corporate_taxable_income_krw: float,
    corporate_deductible_expenses_krw: float,
    domestic_dividend_exclusion_eligible: bool,
    domestic_dividend_ownership_pct: float,
    domestic_dividend_holding_months: float,
    us_treaty_parent_rate_qualified: bool,
    foreign_subsidiary_exclusion_qualified: bool,
    foreign_ownership_pct: float,
) -> dict[str, Any]:
    notes: list[str] = []
    exclusion_rate = 0.0
    foreign_subsidiary_exclusion_rate = 0.0
    us_withholding_rate = 0.0
    foreign_withholding = 0.0

    taxable_distribution = annual_distribution_krw
    if asset_type == ASSET_DOMESTIC_DIVIDEND_STOCK:
        exclusion_rate = _domestic_dividend_exclusion_rate(
            eligible=domestic_dividend_exclusion_eligible,
            ownership_pct=domestic_dividend_ownership_pct,
            holding_months=domestic_dividend_holding_months,
        )
        taxable_distribution = annual_distribution_krw * (1.0 - exclusion_rate)
        if exclusion_rate > 0:
            notes.append(
                "Domestic received-dividend exclusion is a screening estimate and does not adjust for borrowing-interest or payer-specific exclusions."
            )

    elif asset_type == ASSET_US_DIRECT:
        if (
            foreign_subsidiary_exclusion_qualified
            and foreign_ownership_pct >= rules.FOREIGN_SUBSIDIARY_MIN_OWNERSHIP_PCT
        ):
            foreign_subsidiary_exclusion_rate = (
                rules.FOREIGN_SUBSIDIARY_DIVIDEND_EXCLUSION_RATE
            )
            taxable_distribution = annual_distribution_krw * (
                1.0 - foreign_subsidiary_exclusion_rate
            )
            notes.append(
                "The 95% foreign-subsidiary dividend exclusion is applied only because eligibility was explicitly asserted."
            )

        if us_treaty_parent_rate_qualified and foreign_ownership_pct >= 10.0:
            us_withholding_rate = rules.US_TREATY_QUALIFIED_CORPORATE_DIVIDEND_RATE
        else:
            us_withholding_rate = rules.US_TREATY_GENERAL_DIVIDEND_RATE
        foreign_withholding = annual_distribution_krw * us_withholding_rate

    taxable_investment_income = (
        taxable_distribution
        + annual_realized_gain_krw
        - corporate_deductible_expenses_krw
    )
    baseline_base = max(existing_corporate_taxable_income_krw, 0.0)
    total_base = max(baseline_base + taxable_investment_income, 0.0)

    baseline_national = _progressive_tax(
        baseline_base, rules.CORPORATE_INCOME_TAX_BRACKETS
    )
    total_national_before_credit = _progressive_tax(
        total_base, rules.CORPORATE_INCOME_TAX_BRACKETS
    )
    baseline_local = _progressive_tax(
        baseline_base, rules.CORPORATE_LOCAL_INCOME_TAX_BRACKETS
    )
    total_local = _progressive_tax(
        total_base, rules.CORPORATE_LOCAL_INCOME_TAX_BRACKETS
    )

    foreign_tax_credit = 0.0
    foreign_tax_credit_limit = 0.0
    foreign_tax_credit_estimated = False
    if asset_type == ASSET_US_DIRECT and annual_distribution_krw > 0:
        if foreign_subsidiary_exclusion_rate > 0:
            notes.append(
                "Foreign tax credit is not estimated when the 95% foreign-subsidiary dividend exclusion is applied."
            )
        elif total_base > 0:
            foreign_tax_credit_limit = total_national_before_credit * min(
                annual_distribution_krw / total_base, 1.0
            )
            foreign_tax_credit = min(
                foreign_withholding, foreign_tax_credit_limit
            )
            foreign_tax_credit_estimated = True
            notes.append(
                "Corporate foreign tax credit is a national-corporate-tax screening estimate; local-tax credit and detailed country-basket rules are not calculated."
            )

    total_national_after_credit = max(
        total_national_before_credit - foreign_tax_credit, 0.0
    )
    incremental_national = total_national_after_credit - baseline_national
    incremental_local = total_local - baseline_local
    known_tax_total = incremental_national + incremental_local + foreign_withholding
    gross_cash_return = annual_distribution_krw + annual_realized_gain_krw
    after_corporate_tax_return = (
        gross_cash_return - corporate_deductible_expenses_krw - known_tax_total
    )

    return {
        "asset_type": asset_type,
        "gross_cash_return_krw": _won(gross_cash_return),
        "investment_related_deductible_expenses_krw": _won(
            corporate_deductible_expenses_krw
        ),
        "taxable_investment_income_krw": _won(taxable_investment_income),
        "baseline_corporate_taxable_income_krw": _won(baseline_base),
        "projected_corporate_taxable_income_krw": _won(total_base),
        "domestic_received_dividend_exclusion_rate": exclusion_rate,
        "foreign_subsidiary_dividend_exclusion_rate": foreign_subsidiary_exclusion_rate,
        "us_dividend_withholding_rate": us_withholding_rate,
        "taxes": {
            "incremental_corporate_income_tax_krw": _won(incremental_national),
            "incremental_corporate_local_income_tax_krw": _won(incremental_local),
            "us_dividend_withholding_krw": _won(foreign_withholding),
            "estimated_foreign_tax_credit_krw": _won(foreign_tax_credit),
            "estimated_foreign_tax_credit_limit_krw": _won(foreign_tax_credit_limit),
            "known_tax_total_krw": _won(known_tax_total),
        },
        "after_corporate_tax_return_krw": _won(after_corporate_tax_return),
        "data_quality": {
            "legal_tax_determination": False,
            "foreign_tax_credit_estimated": foreign_tax_credit_estimated,
            "corporate_local_foreign_tax_credit_calculated": False,
            "borrowing_interest_dividend_exclusion_adjustment_calculated": False,
            "indirect_fund_foreign_tax_credit_calculated": False,
        },
        "notes": notes,
    }


def compare_investment_tax_2026(
    *,
    asset_type: str,
    annual_distribution_krw: object = 0,
    annual_realized_gain_krw: object = 0,
    taxable_etf_gain_krw: object | None = None,
    existing_personal_financial_income_krw: object = 0,
    existing_corporate_taxable_income_krw: object = 0,
    corporate_deductible_expenses_krw: object = 0,
    corporation_to_owner_distribution_krw: object = 0,
    domestic_dividend_exclusion_eligible: bool = False,
    domestic_dividend_ownership_pct: object = 0,
    domestic_dividend_holding_months: object = 0,
    us_treaty_parent_rate_qualified: bool = False,
    foreign_subsidiary_exclusion_qualified: bool = False,
    foreign_ownership_pct: object = 0,
    year: int = rules.RULE_YEAR,
) -> dict[str, Any]:
    """Compare personal and family-corporation tax layers for one annual scenario.

    All outputs are screening estimates.  The function intentionally avoids a
    final comprehensive-income-tax calculation because salary/business income,
    deductions, dividend gross-up, special high-dividend treatment and other
    return-level facts are outside this phase.
    """

    if year != rules.RULE_YEAR:
        raise InvestmentTaxComparisonError("INVESTMENT_TAX_RULE_YEAR_UNSUPPORTED")
    if asset_type not in SUPPORTED_ASSET_TYPES:
        raise InvestmentTaxComparisonError("INVESTMENT_TAX_ASSET_TYPE_INVALID")
    if not isinstance(domestic_dividend_exclusion_eligible, bool):
        raise InvestmentTaxComparisonError("INVESTMENT_TAX_DOMESTIC_DIVIDEND_ELIGIBILITY_INVALID")
    if not isinstance(us_treaty_parent_rate_qualified, bool):
        raise InvestmentTaxComparisonError("INVESTMENT_TAX_US_TREATY_QUALIFICATION_INVALID")
    if not isinstance(foreign_subsidiary_exclusion_qualified, bool):
        raise InvestmentTaxComparisonError("INVESTMENT_TAX_FOREIGN_SUBSIDIARY_QUALIFICATION_INVALID")

    distribution = _nonnegative(
        annual_distribution_krw, "INVESTMENT_TAX_DISTRIBUTION_INVALID"
    )
    realized_gain = _nonnegative(
        annual_realized_gain_krw, "INVESTMENT_TAX_REALIZED_GAIN_INVALID"
    )
    etf_gain = (
        None
        if taxable_etf_gain_krw is None
        else _nonnegative(taxable_etf_gain_krw, "INVESTMENT_TAX_ETF_GAIN_INVALID")
    )
    existing_personal = _nonnegative(
        existing_personal_financial_income_krw,
        "INVESTMENT_TAX_PERSONAL_FINANCIAL_INCOME_INVALID",
    )
    existing_corporate = _nonnegative(
        existing_corporate_taxable_income_krw,
        "INVESTMENT_TAX_CORPORATE_INCOME_INVALID",
    )
    deductible_expenses = _nonnegative(
        corporate_deductible_expenses_krw,
        "INVESTMENT_TAX_CORPORATE_EXPENSE_INVALID",
    )
    owner_distribution = _nonnegative(
        corporation_to_owner_distribution_krw,
        "INVESTMENT_TAX_OWNER_DISTRIBUTION_INVALID",
    )
    domestic_ownership = _percentage(
        domestic_dividend_ownership_pct,
        "INVESTMENT_TAX_DOMESTIC_OWNERSHIP_INVALID",
    )
    domestic_holding_months = _nonnegative(
        domestic_dividend_holding_months,
        "INVESTMENT_TAX_DOMESTIC_HOLDING_INVALID",
    )
    foreign_ownership = _percentage(
        foreign_ownership_pct,
        "INVESTMENT_TAX_FOREIGN_OWNERSHIP_INVALID",
    )

    individual = _individual_projection(
        asset_type=asset_type,
        annual_distribution_krw=distribution,
        annual_realized_gain_krw=realized_gain,
        taxable_etf_gain_krw=etf_gain,
        existing_financial_income_krw=existing_personal,
    )
    corporation = _corporation_projection(
        asset_type=asset_type,
        annual_distribution_krw=distribution,
        annual_realized_gain_krw=realized_gain,
        existing_corporate_taxable_income_krw=existing_corporate,
        corporate_deductible_expenses_krw=deductible_expenses,
        domestic_dividend_exclusion_eligible=domestic_dividend_exclusion_eligible,
        domestic_dividend_ownership_pct=domestic_ownership,
        domestic_dividend_holding_months=domestic_holding_months,
        us_treaty_parent_rate_qualified=us_treaty_parent_rate_qualified,
        foreign_subsidiary_exclusion_qualified=foreign_subsidiary_exclusion_qualified,
        foreign_ownership_pct=foreign_ownership,
    )

    available_after_corporate_tax = max(
        float(corporation["after_corporate_tax_return_krw"]), 0.0
    )
    if owner_distribution > available_after_corporate_tax + 0.5:
        raise InvestmentTaxComparisonError(
            "INVESTMENT_TAX_OWNER_DISTRIBUTION_EXCEEDS_RETURN"
        )

    owner_withholding = owner_distribution * rules.GENERAL_DIVIDEND_WITHHOLDING_RATE
    owner_projected_financial_income = existing_personal + owner_distribution
    owner_comprehensive_screening = (
        owner_projected_financial_income
        > rules.FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
    )
    retained = available_after_corporate_tax - owner_distribution
    owner_cash = owner_distribution - owner_withholding
    combined_known_value = retained + owner_cash
    individual_known_value = float(individual["after_known_tax_cash_krw"])

    return {
        "rule_year": rules.RULE_YEAR,
        "asset_type": asset_type,
        "inputs": {
            "annual_distribution_krw": _won(distribution),
            "annual_realized_gain_krw": _won(realized_gain),
            "taxable_etf_gain_krw": None if etf_gain is None else _won(etf_gain),
            "existing_personal_financial_income_krw": _won(existing_personal),
            "existing_corporate_taxable_income_krw": _won(existing_corporate),
            "corporate_deductible_expenses_krw": _won(deductible_expenses),
        },
        "individual": individual,
        "family_corporation": corporation,
        "corporation_to_owner": {
            "distributed_gross_krw": _won(owner_distribution),
            "estimated_dividend_withholding_krw": _won(owner_withholding),
            "owner_cash_after_withholding_krw": _won(owner_cash),
            "retained_in_corporation_krw": _won(retained),
            "combined_known_after_tax_value_krw": _won(combined_known_value),
            "owner_projected_financial_income_krw": _won(
                owner_projected_financial_income
            ),
            "comprehensive_tax_screening": owner_comprehensive_screening,
            "final_owner_income_tax_calculated": False,
        },
        "comparison": {
            "individual_known_after_tax_value_krw": _won(individual_known_value),
            "family_corporation_known_after_tax_value_krw": _won(
                combined_known_value
            ),
            "family_corporation_minus_individual_krw": _won(
                combined_known_value - individual_known_value
            ),
            "screening_only": True,
            "legal_tax_determination": False,
        },
        "rule_context": {
            "verified_on": rules.RULE_VERIFIED_ON,
            "official_sources": dict(rules.OFFICIAL_SOURCES),
            "not_calculated": [
                "final comprehensive personal income tax",
                "2026 high-dividend special separate taxation",
                "health-insurance premium impact",
                "salary/bonus/retirement extraction from corporation",
                "gift and inheritance tax",
                "corporate accounting and registration costs unless supplied as deductible expenses",
                "detailed foreign tax credit baskets and local-tax foreign credit",
            ],
        },
    }
