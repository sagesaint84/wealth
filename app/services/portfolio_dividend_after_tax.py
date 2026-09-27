"""Portfolio-level dividend yield after currently known tax layers.

This module is deliberately pure: it combines an already-built dashboard holding
set with an already-enriched dividend forecast. It does not perform network
access and it does not introduce tax rates of its own. Tax amounts come only
from the verified 2026 investment-tax screening engine.
"""

from __future__ import annotations

import math
from typing import Any

from app.services.dividend_event_identity import normalize_dividend_code
from app.services.tax.investment_tax import compare_investment_tax_2026


_ASSET_DOMESTIC_DIVIDEND_STOCK = "domestic_dividend_stock"
_ASSET_KR_LISTED_US_ETF = "kr_listed_us_etf"
_ASSET_US_DIRECT = "us_direct"


class PortfolioDividendAfterTaxError(ValueError):
    """Stable validation error for the pure C-5 aggregation layer."""


def _number(value: object, default: float = 0.0) -> float:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _nonnegative(value: object, default: float = 0.0) -> float:
    return max(_number(value, default), 0.0)


def _won(value: float) -> int:
    return int(round(value))


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100.0, 4)


def _instrument_key(code: object, currency: object) -> tuple[str, str] | None:
    normalized_code = normalize_dividend_code(code)
    normalized_currency = str(currency or "").strip().upper()
    if normalized_code is None or not normalized_currency:
        return None
    return normalized_code, normalized_currency


def _forecast_source_label(value: object) -> str:
    if isinstance(value, str):
        text = value.strip()
        return text or "unknown"
    if not isinstance(value, dict):
        return "unknown"
    for key in ("numeric_source", "source", "status"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return "unknown"


def _asset_contract(currency: str, *, is_etf: bool) -> tuple[str | None, str]:
    if currency == "KRW":
        if is_etf:
            return _ASSET_KR_LISTED_US_ETF, "국내상장 ETF 분배금"
        return _ASSET_DOMESTIC_DIVIDEND_STOCK, "국내 배당주"
    if currency == "USD":
        return _ASSET_US_DIRECT, "미국주식·미국 ETF 직투 배당"
    return None, "지원 범위 밖 통화"


def _aggregate_holdings(
    holdings: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in holdings:
        if not isinstance(raw, dict):
            continue
        key = _instrument_key(raw.get("code"), raw.get("currency") or "KRW")
        if key is None:
            continue
        code, currency = key
        row = grouped.setdefault(
            key,
            {
                "code": code,
                "name": str(raw.get("name") or code),
                "currency": currency,
                "quantity": 0.0,
                "market_value_krw": 0.0,
                "cost_value_krw": 0.0,
                "holding_row_count": 0,
            },
        )
        row["quantity"] += _nonnegative(raw.get("quantity"))
        row["market_value_krw"] += _nonnegative(raw.get("market_value_krw"))
        row["cost_value_krw"] += _nonnegative(raw.get("cost_value_krw"))
        row["holding_row_count"] += 1
        if not row.get("name") or row.get("name") == code:
            row["name"] = str(raw.get("name") or code)
    return grouped


def _aggregate_forecast(
    summary: dict[str, Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], float, int]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    invalid_positive_amount = 0.0
    invalid_positive_count = 0
    rows = summary.get("holding_dividends")
    if not isinstance(rows, list):
        return grouped, invalid_positive_amount, invalid_positive_count

    for raw in rows:
        if not isinstance(raw, dict):
            continue
        gross = _nonnegative(raw.get("annual_payout_krw"))
        key = _instrument_key(raw.get("code"), raw.get("currency") or "KRW")
        if key is None:
            if gross > 0:
                invalid_positive_amount += gross
                invalid_positive_count += 1
            continue
        code, currency = key
        row = grouped.setdefault(
            key,
            {
                "code": code,
                "name": str(raw.get("name") or code),
                "currency": currency,
                "quantity": 0.0,
                "gross_annual_dividend_krw": 0.0,
                "gross_annual_dividend_orig": 0.0,
                "is_etf": False,
                "forecast_sources": set(),
                "forecast_row_count": 0,
            },
        )
        row["quantity"] += _nonnegative(raw.get("quantity"))
        row["gross_annual_dividend_krw"] += gross
        row["gross_annual_dividend_orig"] += _nonnegative(
            raw.get("annual_payout_orig")
        )
        row["is_etf"] = bool(row["is_etf"] or raw.get("is_etf"))
        row["forecast_sources"].add(
            _forecast_source_label(raw.get("forecast_source"))
        )
        row["forecast_row_count"] += 1
        if not row.get("name") or row.get("name") == code:
            row["name"] = str(raw.get("name") or code)
    return grouped, invalid_positive_amount, invalid_positive_count


def _tax_result(*, asset_type: str, gross: float, is_etf: bool) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "asset_type": asset_type,
        "annual_distribution_krw": gross,
        "annual_realized_gain_krw": 0,
        "existing_personal_financial_income_krw": 0,
        "corporation_to_owner_distribution_krw": 0,
    }
    if is_etf:
        # Distribution-only C-5 contract. No ETF trading gain is allowed to
        # leak into the portfolio dividend-yield calculation.
        kwargs["taxable_etf_gain_krw"] = 0
    comparison = compare_investment_tax_2026(**kwargs)
    individual = comparison.get("individual")
    if not isinstance(individual, dict):
        raise PortfolioDividendAfterTaxError(
            "PORTFOLIO_DIVIDEND_TAX_RESULT_INVALID"
        )
    taxes = individual.get("taxes")
    if not isinstance(taxes, dict):
        raise PortfolioDividendAfterTaxError(
            "PORTFOLIO_DIVIDEND_TAX_RESULT_INVALID"
        )
    return {
        "known_tax_krw": _nonnegative(taxes.get("known_tax_total_krw")),
        "after_known_tax_cash_krw": _nonnegative(
            individual.get("after_known_tax_cash_krw")
        ),
        "data_quality": dict(individual.get("data_quality") or {}),
        "notes": list(individual.get("notes") or []),
    }


def build_portfolio_after_tax_dividend_summary(
    holdings: list[dict[str, Any]],
    dividend_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build a portfolio after-known-tax dividend-yield view without I/O.

    The canonical gross total remains ``summary.total_annual_dividend_krw``.
    Holding-level rows are only an attribution layer; when those rows do not
    explain the canonical total, the unexplained residual is never assigned to
    a security or tax category.
    """
    if not isinstance(holdings, list) or not isinstance(dividend_summary, dict):
        raise PortfolioDividendAfterTaxError("PORTFOLIO_DIVIDEND_INPUT_INVALID")

    raw_total = dividend_summary.get("total_annual_dividend_krw")
    if raw_total is None or dividend_summary.get("unavailable") is True:
        return {
            "calculation_status": "unavailable",
            "gross_annual_dividend_krw": None,
            "forecast_total_annual_dividend_krw": None,
            "reason": "forecast_unavailable",
            "screening_only": True,
            "legal_tax_determination": False,
            "instruments": [],
        }

    canonical_gross = _nonnegative(raw_total)
    holding_map = _aggregate_holdings(holdings)
    forecast_map, invalid_forecast_amount, invalid_forecast_count = (
        _aggregate_forecast(dividend_summary)
    )

    # Yield denominators cover every scoped stock holding, even if an invalid or
    # currently unjoinable instrument code prevents tax attribution. Dropping
    # such a holding would silently inflate the portfolio yield.
    market_basis = sum(
        _nonnegative(row.get("market_value_krw"))
        for row in holdings
        if isinstance(row, dict)
    )
    cost_basis = sum(
        _nonnegative(row.get("cost_value_krw"))
        for row in holdings
        if isinstance(row, dict)
    )
    attributed_gross = sum(
        row["gross_annual_dividend_krw"] for row in forecast_map.values()
    ) + invalid_forecast_amount
    forecast_row_count = sum(
        int(row.get("forecast_row_count") or 0)
        for row in forecast_map.values()
    ) + invalid_forecast_count
    # Holding rows are rounded individually while the canonical total is rounded
    # only after aggregation. Allow only the mathematically possible accumulated
    # rounding drift; larger differences remain a real attribution gap.
    rounding_tolerance = max(1.0, (forecast_row_count + 1) * 0.5)
    residual = max(canonical_gross - attributed_gross, 0.0)
    attribution_delta = attributed_gross - canonical_gross
    attribution_complete = (
        abs(attribution_delta) <= rounding_tolerance
        and invalid_forecast_count == 0
    )

    all_keys = set(holding_map) | set(forecast_map)
    instruments: list[dict[str, Any]] = []
    calculable_gross = 0.0
    calculable_known_tax = 0.0
    calculable_after_cash = 0.0
    positive_forecast_count = 0
    supported_positive_count = 0
    unsupported_positive_count = invalid_forecast_count

    for key in all_keys:
        holding = holding_map.get(key)
        forecast = forecast_map.get(key)
        code, currency = key
        gross = _nonnegative((forecast or {}).get("gross_annual_dividend_krw"))
        market_value = _nonnegative((holding or {}).get("market_value_krw"))
        cost_value = _nonnegative((holding or {}).get("cost_value_krw"))
        quantity = _nonnegative((holding or forecast or {}).get("quantity"))
        is_etf = bool((forecast or {}).get("is_etf"))
        asset_type, display_class = _asset_contract(currency, is_etf=is_etf)
        matched_holding = holding is not None
        source_values = sorted(
            (forecast or {}).get("forecast_sources") or {"unknown"}
        )
        forecast_source = (
            source_values[0]
            if len(source_values) == 1
            else ("mixed" if source_values else "unknown")
        )

        known_tax: float | None = 0.0 if gross <= 0 else None
        after_cash: float | None = 0.0 if gross <= 0 else None
        data_quality: dict[str, Any] = {}
        notes: list[str] = []
        status = "no_dividend" if gross <= 0 else "unsupported"

        if gross > 0:
            positive_forecast_count += 1
            if asset_type is None:
                notes.append(
                    "지원 범위 밖 통화이므로 알려진 세금 후 금액을 자동 계산하지 않습니다."
                )
            elif not matched_holding:
                notes.append(
                    "예상 배당 행과 현재 보유종목을 안전하게 연결할 수 없어 포트폴리오 세후 수익률 계산에서 제외합니다."
                )
            else:
                try:
                    tax = _tax_result(
                        asset_type=asset_type,
                        gross=gross,
                        is_etf=is_etf,
                    )
                except Exception:
                    status = "tax_unavailable"
                    notes.append(
                        "기존 투자세금 screening 계산 결과를 사용할 수 없습니다."
                    )
                else:
                    status = "calculated"
                    known_tax = tax["known_tax_krw"]
                    after_cash = tax["after_known_tax_cash_krw"]
                    data_quality = tax["data_quality"]
                    notes.extend(tax["notes"])
                    calculable_gross += gross
                    calculable_known_tax += known_tax
                    calculable_after_cash += after_cash
                    supported_positive_count += 1
                    if currency == "USD":
                        data_quality["usd_holding_tax_scope"] = (
                            "wealth_us_direct_contract"
                        )
                        data_quality[
                            "non_usd_listing_treaty_variation_calculated"
                        ] = False
                        notes.append(
                            "USD 보유자산은 Wealth의 미국직투 배당 screening 계약을 사용합니다. 미국 외 USD 상장자산의 개별 조세조약 차이는 계산하지 않습니다."
                        )
                    if is_etf and currency == "KRW":
                        data_quality["distribution_only"] = True
                        data_quality["taxable_etf_gain_krw"] = 0
            if status != "calculated":
                unsupported_positive_count += 1

        instruments.append(
            {
                "code": code,
                "name": str((holding or forecast or {}).get("name") or code),
                "currency": currency,
                "quantity": quantity,
                "display_asset_class": display_class,
                "market_value_krw": _won(market_value),
                "cost_value_krw": _won(cost_value),
                "gross_annual_dividend_krw": _won(gross),
                "known_tax_krw": None if known_tax is None else _won(known_tax),
                "after_known_tax_cash_krw": (
                    None if after_cash is None else _won(after_cash)
                ),
                "gross_yield_market_pct": _pct(gross, market_value),
                "after_known_tax_yield_market_pct": (
                    None
                    if after_cash is None
                    else _pct(after_cash, market_value)
                ),
                "gross_yield_cost_pct": _pct(gross, cost_value),
                "after_known_tax_yield_cost_pct": (
                    None if after_cash is None else _pct(after_cash, cost_value)
                ),
                "calculation_status": status,
                "tax_engine_asset_type": asset_type,
                "forecast_source": forecast_source,
                "matched_holding": matched_holding,
                "holding_row_count": int(
                    (holding or {}).get("holding_row_count") or 0
                ),
                "forecast_row_count": int(
                    (forecast or {}).get("forecast_row_count") or 0
                ),
                "data_quality": data_quality,
                "notes": notes,
            }
        )

    unsupported_gross = max(canonical_gross - calculable_gross, 0.0)
    if canonical_gross <= 0:
        coverage_pct = 100.0 if attribution_complete else 0.0
    else:
        coverage_pct = round(
            min(calculable_gross / canonical_gross, 1.0) * 100.0,
            2,
        )

    complete = (
        attribution_complete
        and residual <= rounding_tolerance
        and attributed_gross <= canonical_gross + rounding_tolerance
        and unsupported_positive_count == 0
        and abs(calculable_gross - canonical_gross) <= rounding_tolerance
    )
    if canonical_gross <= 0 and attribution_complete:
        complete = True
    calculation_status = (
        "complete"
        if complete
        else ("partial" if canonical_gross > 0 else "unavailable")
    )

    gross_market_yield = _pct(canonical_gross, market_basis)
    gross_cost_yield = _pct(canonical_gross, cost_basis)
    after_market_yield = (
        _pct(calculable_after_cash, market_basis) if complete else None
    )
    after_cost_yield = _pct(calculable_after_cash, cost_basis) if complete else None

    instruments.sort(
        key=lambda row: (
            -int(row.get("gross_annual_dividend_krw") or 0),
            str(row.get("code") or ""),
            str(row.get("currency") or ""),
        )
    )

    return {
        "calculation_status": calculation_status,
        "gross_annual_dividend_krw": _won(canonical_gross),
        "forecast_total_annual_dividend_krw": _won(canonical_gross),
        "attributed_annual_dividend_krw": _won(attributed_gross),
        "unattributed_annual_dividend_krw": _won(residual),
        "forecast_attribution_complete": attribution_complete,
        "forecast_attribution_excess_krw": _won(max(attribution_delta, 0.0)),
        "forecast_rounding_tolerance_krw": round(rounding_tolerance, 2),
        "known_tax_total_krw": (
            _won(calculable_known_tax) if complete else None
        ),
        "after_known_tax_cash_krw": (
            _won(calculable_after_cash) if complete else None
        ),
        "calculable_known_tax_krw": _won(calculable_known_tax),
        "calculable_after_known_tax_cash_krw": _won(calculable_after_cash),
        "calculable_gross_dividend_krw": _won(calculable_gross),
        "unsupported_gross_dividend_krw": _won(unsupported_gross),
        "market_value_basis_krw": _won(market_basis),
        "cost_value_basis_krw": _won(cost_basis),
        "cost_basis_method": "average_price_quantity_current_fx",
        "gross_yield_on_market_value_pct": gross_market_yield,
        "gross_yield_on_cost_pct": gross_cost_yield,
        "after_known_tax_yield_on_market_value_pct": after_market_yield,
        "after_known_tax_yield_on_cost_pct": after_cost_yield,
        "after_tax_dividend_coverage_pct": coverage_pct,
        "positive_forecast_instrument_count": (
            positive_forecast_count + invalid_forecast_count
        ),
        "supported_instrument_count": supported_positive_count,
        "unsupported_instrument_count": unsupported_positive_count,
        "screening_only": True,
        "legal_tax_determination": False,
        "after_tax_scope_label": "원천징수·알려진 세금 후",
        "data_quality": {
            "aggregate_after_tax_yield_requires_full_coverage": True,
            "cash_and_deposits_excluded_from_denominators": True,
            "cost_basis_uses_current_fx_for_foreign_holdings": True,
            "final_comprehensive_income_tax_calculated": False,
            "high_dividend_special_rule_applied": False,
        },
        "instruments": instruments,
    }


__all__ = [
    "PortfolioDividendAfterTaxError",
    "build_portfolio_after_tax_dividend_summary",
]
