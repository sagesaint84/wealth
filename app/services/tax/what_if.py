"""Stateless Phase 10.5A-3 financial-income What-if orchestration.

This layer combines the verified annual financial-income projection with optional
personal-vs-family-corporation investment-tax screening. It intentionally does
not persist scenarios or turn screening estimates into legal tax determinations.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.tax.financial_income import get_financial_income_projection_for_user
from app.services.tax.high_dividend_2026 import calculate_high_dividend_separate_tax_2026
from app.services.tax.investment_tax import compare_investment_tax_2026
from app.services.tax.investment_tax import rules_2026 as investment_rules
from app.services.tax.rules_2026 import (
    FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW,
    FINANCIAL_INCOME_WATCH_THRESHOLD_KRW,
)


class FinancialIncomeWhatIfError(ValueError):
    """Stable validation error for the stateless What-if layer."""


def _nonnegative(value: object, code: str) -> float:
    if isinstance(value, bool):
        raise FinancialIncomeWhatIfError(code)
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise FinancialIncomeWhatIfError(code) from exc
    if not math.isfinite(number) or number < 0:
        raise FinancialIncomeWhatIfError(code)
    return number


def _won(value: float) -> int:
    return int(round(value))


def _threshold_state(amount: int | None, threshold: int) -> dict[str, Any]:
    if amount is None:
        return {
            "amount_krw": None,
            "threshold_krw": threshold,
            "remaining_krw": None,
            "exceeded": None,
            "at_or_above": None,
        }
    return {
        "amount_krw": amount,
        "threshold_krw": threshold,
        "remaining_krw": max(threshold - amount, 0),
        "exceeded": amount > threshold,
        "at_or_above": amount >= threshold,
    }


def _crossed(
    before: dict[str, Any], after: dict[str, Any], *, state_key: str
) -> bool | None:
    before_state = before.get(state_key)
    after_state = after.get(state_key)
    if before_state is None or after_state is None:
        return None
    return (not bool(before_state)) and bool(after_state)


_HIGH_DIVIDEND_SCENARIO_FIELDS = frozenset(
    {
        "special_dividend_income_krw",
        "high_dividend_company_confirmed",
        "separate_taxation_requested",
    }
)


def _high_dividend_special_result(
    scenario: dict[str, Any] | None,
    *,
    additional_dividend_gross_krw: float,
) -> dict[str, Any] | None:
    if scenario is None:
        return None
    if not isinstance(scenario, dict) or set(scenario) - _HIGH_DIVIDEND_SCENARIO_FIELDS:
        raise FinancialIncomeWhatIfError(
            "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_SCENARIO_INVALID"
        )
    amount = _nonnegative(
        scenario.get("special_dividend_income_krw", 0),
        "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_AMOUNT_INVALID",
    )
    if amount > additional_dividend_gross_krw:
        raise FinancialIncomeWhatIfError(
            "FINANCIAL_INCOME_WHAT_IF_HIGH_DIVIDEND_EXCEEDS_ADDITIONAL_DIVIDEND"
        )
    return calculate_high_dividend_separate_tax_2026(
        amount,
        high_dividend_company_confirmed=scenario.get(
            "high_dividend_company_confirmed", False
        ),
        separate_taxation_requested=scenario.get(
            "separate_taxation_requested", False
        ),
    )


def _trading_impact(
    *,
    foreign_share_realized_gain_krw: float,
    kr_listed_overseas_etf_taxable_gain_krw: float,
) -> dict[str, Any]:
    etf_withholding = (
        kr_listed_overseas_etf_taxable_gain_krw
        * investment_rules.GENERAL_DIVIDEND_WITHHOLDING_RATE
    )
    return {
        "foreign_shares": {
            "realized_gain_krw": _won(foreign_share_realized_gain_krw),
            "financial_income_addition_krw": 0,
            "included_in_financial_income_screening": False,
            "capital_gain_tax_calculated": False,
            "note": (
                "해외주식 실현차익은 금융소득 종합과세 판정에 포함하지 않습니다. "
                "이 빠른 입력만으로는 연간 순손익과 기본공제 사용상태를 확정할 수 없어 "
                "양도소득세는 계산하지 않습니다."
            ),
        },
        "kr_listed_overseas_etf": {
            "taxable_gain_krw": _won(kr_listed_overseas_etf_taxable_gain_krw),
            "financial_income_addition_krw": _won(
                kr_listed_overseas_etf_taxable_gain_krw
            ),
            "included_in_financial_income_screening": True,
            "estimated_withholding_rate": investment_rules.GENERAL_DIVIDEND_WITHHOLDING_RATE,
            "estimated_withholding_krw": _won(etf_withholding),
            "final_tax_calculated": False,
        },
        "screening_only": True,
        "legal_tax_determination": False,
    }



def build_financial_income_what_if(
    baseline_projection: dict[str, Any],
    *,
    additional_dividend_gross_krw: object = 0,
    additional_interest_gross_krw: object = 0,
    additional_foreign_share_realized_gain_krw: object = 0,
    additional_kr_listed_overseas_etf_taxable_gain_krw: object = 0,
    high_dividend_scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply hypothetical extra financial income to an existing projection."""

    if not isinstance(baseline_projection, dict):
        raise FinancialIncomeWhatIfError("FINANCIAL_INCOME_WHAT_IF_BASELINE_INVALID")

    additional_dividend = _nonnegative(
        additional_dividend_gross_krw,
        "FINANCIAL_INCOME_WHAT_IF_DIVIDEND_INVALID",
    )
    additional_interest = _nonnegative(
        additional_interest_gross_krw,
        "FINANCIAL_INCOME_WHAT_IF_INTEREST_INVALID",
    )
    additional_foreign_share_gain = _nonnegative(
        additional_foreign_share_realized_gain_krw,
        "FINANCIAL_INCOME_WHAT_IF_FOREIGN_SHARE_GAIN_INVALID",
    )
    additional_kr_overseas_etf_gain = _nonnegative(
        additional_kr_listed_overseas_etf_taxable_gain_krw,
        "FINANCIAL_INCOME_WHAT_IF_KR_OVERSEAS_ETF_GAIN_INVALID",
    )
    scenario_addition = (
        additional_dividend
        + additional_interest
        + additional_kr_overseas_etf_gain
    )
    trading_impact = _trading_impact(
        foreign_share_realized_gain_krw=additional_foreign_share_gain,
        kr_listed_overseas_etf_taxable_gain_krw=additional_kr_overseas_etf_gain,
    )
    high_dividend_special = _high_dividend_special_result(
        high_dividend_scenario,
        additional_dividend_gross_krw=additional_dividend,
    )
    excluded_from_comprehensive = (
        int(high_dividend_special.get("excluded_from_comprehensive_tax_threshold_krw", 0))
        if high_dividend_special
        else 0
    )

    recorded_special = (baseline_projection.get('actual_financial_income') or {}).get('high_dividend_special_tax')
    if recorded_special and recorded_special.get('special_rule_applied'):
        recorded_amount = recorded_special['special_dividend_income_krw']
        high_dividend_special = calculate_high_dividend_separate_tax_2026(
            recorded_amount + excluded_from_comprehensive,
            high_dividend_company_confirmed=True, separate_taxation_requested=True)
        high_dividend_special['recorded_selection_amount_krw'] = recorded_amount
        high_dividend_special['application_basis'] = 'user_selection_and_filing_assumption'
        high_dividend_special['eligibility']['confirmation_source'] = 'user_assumption'

    try:
        baseline_known = int(
            round(float(baseline_projection["known_gross_screening_income_krw"]))
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise FinancialIncomeWhatIfError(
            "FINANCIAL_INCOME_WHAT_IF_BASELINE_INVALID"
        ) from exc

    raw_projected = baseline_projection.get("projected_gross_screening_income_krw")
    if raw_projected is None:
        baseline_projected: int | None = None
        scenario_projected: int | None = None
    else:
        try:
            baseline_projected = int(round(float(raw_projected)))
        except (TypeError, ValueError) as exc:
            raise FinancialIncomeWhatIfError(
                "FINANCIAL_INCOME_WHAT_IF_BASELINE_INVALID"
            ) from exc
        scenario_projected = _won(baseline_projected + scenario_addition)

    scenario_comprehensive_amount = (
        None
        if scenario_projected is None
        else max(scenario_projected - excluded_from_comprehensive, 0)
    )

    watch_baseline = _threshold_state(
        baseline_projected, FINANCIAL_INCOME_WATCH_THRESHOLD_KRW
    )
    watch_scenario = _threshold_state(
        scenario_projected, FINANCIAL_INCOME_WATCH_THRESHOLD_KRW
    )
    comprehensive_baseline = _threshold_state(
        baseline_projected, FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
    )
    comprehensive_scenario = _threshold_state(
        scenario_comprehensive_amount, FINANCIAL_INCOME_COMPREHENSIVE_TAX_THRESHOLD_KRW
    )
    if (baseline_projection.get('owner') == '모두'
            and (baseline_projection.get('actual_financial_income') or {}).get('personal_threshold_applied') is False):
        for state in (watch_baseline, watch_scenario, comprehensive_baseline, comprehensive_scenario):
            if state is not None:
                for key in ('remaining_krw', 'exceeded', 'at_or_above', 'progress_percent'):
                    state[key] = None
        high_dividend_special = None

    return {
        "baseline_known_gross_screening_income_krw": baseline_known,
        "baseline_projected_gross_screening_income_krw": baseline_projected,
        "additional_dividend_gross_krw": _won(additional_dividend),
        "additional_interest_gross_krw": _won(additional_interest),
        "additional_foreign_share_realized_gain_krw": _won(
            additional_foreign_share_gain
        ),
        "additional_kr_listed_overseas_etf_taxable_gain_krw": _won(
            additional_kr_overseas_etf_gain
        ),
        "scenario_addition_gross_krw": _won(scenario_addition),
        "trading_impact": trading_impact,
        "scenario_projected_gross_screening_income_krw": scenario_projected,
        "scenario_comprehensive_tax_screening_income_krw": scenario_comprehensive_amount,
        "high_dividend_special_tax": high_dividend_special,
        "thresholds": {
            "watch": {
                "baseline": watch_baseline,
                "scenario": watch_scenario,
                "crossed_by_scenario": _crossed(
                    watch_baseline,
                    watch_scenario,
                    state_key="at_or_above",
                ),
            },
            "comprehensive_tax": {
                "baseline": comprehensive_baseline,
                "scenario": comprehensive_scenario,
                "crossed_by_scenario": _crossed(
                    comprehensive_baseline,
                    comprehensive_scenario,
                    state_key="exceeded",
                ),
                "screening_only": True,
                "legal_tax_determination": False,
            },
        },
        "data_quality": {
            "screening_only": True,
            "legal_tax_determination": False,
            "scenario_projected_available": scenario_projected is not None,
        },
    }


async def get_financial_income_what_if_for_user(
    username: str,
    *,
    owner: str = "모두",
    as_of=None,
    expected_remaining_interest_gross_krw: object = 0,
    current_month_remaining_dividend_gross_krw: object = 0,
    additional_dividend_gross_krw: object = 0,
    additional_interest_gross_krw: object = 0,
    additional_foreign_share_realized_gain_krw: object = 0,
    additional_kr_listed_overseas_etf_taxable_gain_krw: object = 0,
    high_dividend_scenario: dict[str, Any] | None = None,
    investment_scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a user-scoped financial-income What-if response without writes."""

    baseline = await get_financial_income_projection_for_user(
        username,
        owner=owner,
        **({"as_of": as_of} if as_of is not None else {}),
        expected_remaining_interest_gross_krw=expected_remaining_interest_gross_krw,
        current_month_remaining_dividend_gross_krw=current_month_remaining_dividend_gross_krw,
    )
    what_if = build_financial_income_what_if(
        baseline,
        additional_dividend_gross_krw=additional_dividend_gross_krw,
        additional_interest_gross_krw=additional_interest_gross_krw,
        additional_foreign_share_realized_gain_krw=(
            additional_foreign_share_realized_gain_krw
        ),
        additional_kr_listed_overseas_etf_taxable_gain_krw=(
            additional_kr_listed_overseas_etf_taxable_gain_krw
        ),
        high_dividend_scenario=high_dividend_scenario,
    )

    result: dict[str, Any] = {
        "owner": owner,
        "baseline_projection": baseline,
        "what_if": what_if,
        "investment_comparison": None,
    }

    if investment_scenario is not None:
        if not isinstance(investment_scenario, dict) or not isinstance(
            investment_scenario.get("asset_type"), str
        ):
            raise FinancialIncomeWhatIfError(
                "FINANCIAL_INCOME_WHAT_IF_INVESTMENT_SCENARIO_INVALID"
            )

        projected = baseline.get("projected_gross_screening_income_krw")
        if projected is None:
            personal_financial_income = baseline.get(
                "known_gross_screening_income_krw", 0
            )
            personal_basis = "known_gross_screening_income"
        else:
            personal_financial_income = projected
            personal_basis = "projected_gross_screening_income"

        compare_kwargs = dict(investment_scenario)
        # Never trust a client-provided personal baseline. It is always replaced
        # by the authenticated user's scoped projection/known amount.
        compare_kwargs["existing_personal_financial_income_krw"] = (
            personal_financial_income
        )
        comparison = compare_investment_tax_2026(**compare_kwargs)
        comparison["what_if_context"] = {
            "existing_personal_financial_income_source": personal_basis,
            "existing_personal_financial_income_krw": int(
                round(float(personal_financial_income or 0))
            ),
            "server_scoped_from_authenticated_user": True,
            "quick_trading_inputs": {
                "foreign_share_realized_gain_krw": _won(
                    _nonnegative(
                        additional_foreign_share_realized_gain_krw,
                        "FINANCIAL_INCOME_WHAT_IF_FOREIGN_SHARE_GAIN_INVALID",
                    )
                ),
                "kr_listed_overseas_etf_taxable_gain_krw": _won(
                    _nonnegative(
                        additional_kr_listed_overseas_etf_taxable_gain_krw,
                        "FINANCIAL_INCOME_WHAT_IF_KR_OVERSEAS_ETF_GAIN_INVALID",
                    )
                ),
                "server_auto_overwrite": False,
            },
        }
        result["investment_comparison"] = comparison

    return result


# Stateless event choices: official metadata is always read from server summaries.
# These previews never update actual receipts, withholding, or forecast totals.
def build_dividend_benefit_preview(summary, *, owner, tax_year, selections=None, as_of=None):
    from datetime import date
    from collections import Counter
    from app.services.dividend_event_identity import build_dividend_event_identity
    from urllib.parse import urlsplit

    if isinstance(tax_year, bool) or not isinstance(tax_year, int) or not 1900 <= tax_year <= 2100:
        raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_YEAR_INVALID')
    if not isinstance(owner, str) or not owner.strip() or owner == '모두':
        raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_OWNER_REQUIRED')
    if selections is None:
        selections = {}
    if not isinstance(selections, dict) or len(selections) > 500:
        raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_SELECTION_INVALID')
    day = as_of or date.today()
    supported = tax_year == investment_rules.RULE_YEAR

    def amount(value):
        try:
            result = _nonnegative(value, 'DIVIDEND_BENEFIT_AMOUNT_INVALID')
            return result if value is not None and result <= 1e15 else None
        except FinancialIncomeWhatIfError:
            return None

    def parsed_day(value):
        try:
            return date.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    def official_link(value):
        try:
            url = urlsplit(str(value or ''))
            return value if url.scheme == 'https' and url.hostname in {
                'dart.fss.or.kr', 'opendart.fss.or.kr', 'kind.krx.co.kr'} and not url.username else None
        except ValueError:
            return None

    instruments = {str(row.get('code')): row for row in
        (summary.get('dividend_intelligence') or {}).get('instruments', []) if isinstance(row, dict)}
    capital_map = summary.get('capital_dividend_evidence') or {}
    etfs = {str(row.get('code')) for row in summary.get('holding_dividends', []) if row.get('is_etf')}
    events = []
    for bucket in summary.get('monthly_schedule', []):
        for item in bucket.get('items', []):
            code = str(item.get('code') or '')
            gross = amount(item.get('payout_krw'))
            if (item.get('currency') != 'KRW' or item.get('is_etf') or code in etfs
                    or len(code) != 6 or not code[0].isdigit() or not code.isalnum() or gross is None or gross <= 0):
                continue
            paid = parsed_day(item.get('payment_date'))
            if (paid and paid.year != tax_year) or (not paid and tax_year != day.year):
                continue
            identity = build_dividend_event_identity(code=code, record_date=item.get('record_date'),
                source='opendart', source_event_id=item.get('receipt_no'))
            official_event = bool(identity and identity == item.get('event_identity')
                and item.get('event_identity_confidence') == 'official' and paid)
            event_id = identity or f"forecast:{code}:{bucket.get('month')}"
            # The owner/year scope is deliberately part of the selection key.
            key = f'{owner}:{tax_year}:{event_id}'
            capital = capital_map.get(code) or {}
            components = capital.get('payment_components') or {}
            record = parsed_day(item.get('record_date'))
            qualification = (instruments.get(code) or {}).get('high_dividend_qualification') or {}
            quantity = amount(item.get('quantity'))
            dps = amount(components.get('disclosed_capital_reduction_dps_krw'))
            total_dps = amount(components.get('total_cash_dps_krw'))
            matched_capital = bool(official_event and capital.get('receipt_no') == item.get('receipt_no')
                and components.get('amount_status') == 'verified' and quantity is not None
                and total_dps is not None and abs(quantity * total_dps - gross) <= 1)
            candidate_capital = min(gross, quantity * dps) if matched_capital and dps is not None else None
            # B1 has not_assessed and unresolved correction lineage: composition
            # verified is not personal tax eligibility, so capital AUTO stays off.
            assessment = capital.get('tax_assessment') or {}
            assessed_amount = amount(assessment.get('eligible_amount_krw'))
            capital_eligible = bool(matched_capital and supported
                and candidate_capital is not None and assessed_amount is not None
                and 0 < assessed_amount <= candidate_capital
                and capital.get('reserve_evidence_status') == 'disclosed'
                and capital.get('payment_event_status') == 'single_event_scoped'
                and (capital.get('correction_relationship') or {}).get('status') == 'resolved'
                and assessment.get('status') == 'eligibility_confirmed'
                and assessment.get('tax_year') == tax_year
                and assessment.get('event_identity') == identity)
            # Reuse the official company verdict, but only the same declared
            # business-year event paid in the supported 2026 screening year.
            decision = parsed_day(qualification.get('decision_date'))
            published = parsed_day(qualification.get('receipt_date'))
            high_eligible = bool(supported and official_event and record and decision and published
                and quantity is not None and quantity > 0
                and (instruments.get(code) or {}).get('tax_engine_asset_type') == 'domestic_dividend_stock'
                and decision.year == published.year == tax_year and published <= day
                and qualification.get('status') == 'official_qualified'
                and qualification.get('source') == 'official_valueup_disclosure'
                and qualification.get('correction_review') == 'no_correction_indicated'
                and qualification.get('receipt_no') and official_link(qualification.get('source_url'))
                and qualification.get('business_year') == tax_year - 1 == record.year
                and record <= decision <= paid and decision <= day
                and not (capital.get('correction_relationship') or {}).get('later_correction_indicated')
                and not (capital.get('correction_relationship') or {}).get('withdrawal_in_search_results')
                and not (capital.get('correction_relationship') or {}).get('selected_metadata_conflict'))
            event = {'key': key, 'event_identity': identity, 'code': code,
                'name': str(item.get('name') or code), 'owner': owner, 'tax_year': tax_year,
                'gross_amount_krw': _won(gross), 'payment_date': item.get('payment_date'),
                'capital': {'official_eligible': capital_eligible, 'candidate_amount_krw': candidate_capital,
                    'auto_amount_krw': assessed_amount if capital_eligible else None,
                    'official_status': assessment.get('status') or 'not_assessed',
                    'source_url': official_link(capital.get('viewer_url'))},
                'high_dividend': {'official_eligible': high_eligible,
                    'candidate_amount_krw': (gross - (candidate_capital or 0)) if high_eligible else None,
                    'auto_amount_krw': (gross - (candidate_capital or 0)) if high_eligible else None,
                    'official_status': qualification.get('status') or 'not_confirmed',
                    'source_url': official_link(qualification.get('source_url'))}}
            events.append(event)
    counts = Counter(e['key'] for e in events)
    # Ambiguous duplicate events must not double-count a tax benefit.
    events = [e for e in events if counts[e['key']] == 1]
    if set(selections) - {e['key'] for e in events}:
        raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_EVENT_SCOPE_INVALID')
    total_capital = total_high = total_gross = 0
    pending = False
    for event in events:
        selected = selections.get(event['key'], {})
        if not isinstance(selected, dict) or set(selected) - {'capital', 'high_dividend'}:
            raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_SELECTION_INVALID')
        gross = event['gross_amount_krw']
        for kind in ('capital', 'high_dividend'):
            choice = selected.get(kind, {})
            if not isinstance(choice, dict) or set(choice) - {'mode', 'amount_krw'}:
                raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_SELECTION_INVALID')
            mode = choice.get('mode', 'AUTO')
            if not isinstance(mode, str) or mode not in {'AUTO', 'MANUAL_ON', 'MANUAL_OFF'}:
                raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_MODE_INVALID')
            view = event[kind]
            target = view['auto_amount_krw'] if mode == 'AUTO' else view['candidate_amount_krw']
            if mode == 'MANUAL_ON' and 'amount_krw' in choice:
                target = amount(choice['amount_krw'])
                if target is None:
                    raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_AMOUNT_INVALID')
            if target is not None and not 0 <= target <= gross:
                raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_AMOUNT_EXCEEDS_EVENT')
            applied = supported and (mode == 'MANUAL_ON' or (mode == 'AUTO' and view['official_eligible']))
            needs_amount = bool(applied and target is None)
            pending = pending or needs_amount
            view.update(mode=mode, applied=bool(applied and target is not None and target > 0),
                assumed=bool(mode == 'MANUAL_ON' and (not view['official_eligible'] or target != view['auto_amount_krw'])),
                needs_amount=needs_amount, selected_amount_krw=target,
                applied_amount_krw=_won(target) if applied and target is not None else 0)
        capital_amount = event['capital']['applied_amount_krw']
        high = event['high_dividend']
        high['applied_amount_krw'] = min(high['applied_amount_krw'], gross - capital_amount)
        high['overlap_removed'] = high['applied_amount_krw'] != (high['selected_amount_krw'] or 0) if high['applied'] else False
        high['applied'] = high['applied_amount_krw'] > 0
        event['estimated_capital_withholding_difference_krw'] = _won(capital_amount * investment_rules.GENERAL_DIVIDEND_WITHHOLDING_RATE)
        total_capital += capital_amount
        total_high += high['applied_amount_krw']
        total_gross += gross
    # Reuse the existing What-if exclusion and progressive-tax orchestration on
    # this event subtotal only; do not add forecasts to the user's baseline twice.
    event_what_if = build_financial_income_what_if(
        {'known_gross_screening_income_krw': 0, 'projected_gross_screening_income_krw': 0},
        additional_dividend_gross_krw=total_gross - total_capital,
        high_dividend_scenario={'special_dividend_income_krw': total_high,
            'high_dividend_company_confirmed': True, 'separate_taxation_requested': True}
            if supported and total_high else None)
    special = event_what_if['high_dividend_special_tax']
    high_tax = special['national_income_tax_krw'] if special else 0
    high_difference = _won(total_high * investment_rules.GENERAL_DIVIDEND_INCOME_TAX_RATE) - high_tax
    return {'owner': owner, 'tax_year': tax_year, 'supported_year': supported,
        'events': events, 'needs_amount': pending, 'session_only': True,
        'gross_amount_krw': total_gross, 'capital_applied_amount_krw': total_capital,
        'general_taxable_dividend_krw': event_what_if['scenario_comprehensive_tax_screening_income_krw'],
        'calculation_basis': 'selected_events_only',
        'high_dividend_applied_amount_krw': total_high,
        'estimated_capital_withholding_difference_krw': _won(total_capital * investment_rules.GENERAL_DIVIDEND_WITHHOLDING_RATE),
        'high_dividend_national_tax_krw': high_tax,
        'high_dividend_national_difference_vs_withholding_krw': high_difference,
        'high_dividend_local_tax_included': False, 'filing_application_required': bool(total_high),
        'favorable_vs_comprehensive_confirmed': False, 'actual_records_modified': False,
        'ambiguous_events_excluded': sum(count > 1 for count in counts.values())}
