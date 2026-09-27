from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.portfolio_dividend_after_tax import (
    build_portfolio_after_tax_dividend_summary,
)
from app.services.tax.investment_tax import compare_investment_tax_2026


def _holding(
    code: str,
    *,
    currency: str = "KRW",
    quantity: float = 10,
    market: float = 1_000_000,
    cost: float = 800_000,
    name: str | None = None,
) -> dict:
    return {
        "code": code,
        "name": name or code,
        "currency": currency,
        "quantity": quantity,
        "market_value_krw": market,
        "cost_value_krw": cost,
    }


def _forecast(
    code: str,
    gross: int,
    *,
    currency: str = "KRW",
    quantity: float = 10,
    is_etf: bool = False,
    source: str = "naver",
    name: str | None = None,
) -> dict:
    return {
        "code": code,
        "name": name or code,
        "currency": currency,
        "quantity": quantity,
        "annual_payout_krw": gross,
        "annual_payout_orig": gross,
        "is_etf": is_etf,
        "forecast_source": {"numeric_source": source},
    }


class PortfolioDividendAfterTaxTests(unittest.TestCase):
    def test_domestic_stock_reuses_verified_individual_result(self):
        gross = 1_000_000
        result = build_portfolio_after_tax_dividend_summary(
            [_holding("005930")],
            {
                "total_annual_dividend_krw": gross,
                "holding_dividends": [_forecast("005930", gross)],
            },
        )
        expected = compare_investment_tax_2026(
            asset_type="domestic_dividend_stock",
            annual_distribution_krw=gross,
            annual_realized_gain_krw=0,
            existing_personal_financial_income_krw=0,
            corporation_to_owner_distribution_krw=0,
        )["individual"]
        row = result["instruments"][0]
        self.assertEqual(
            row["known_tax_krw"], expected["taxes"]["known_tax_total_krw"]
        )
        self.assertEqual(
            row["after_known_tax_cash_krw"], expected["after_known_tax_cash_krw"]
        )
        self.assertEqual(result["calculation_status"], "complete")

    def test_krw_etf_is_distribution_only(self):
        real_compare = compare_investment_tax_2026
        calls: list[dict] = []

        def spy(**kwargs):
            calls.append(dict(kwargs))
            return real_compare(**kwargs)

        with patch(
            "app.services.portfolio_dividend_after_tax.compare_investment_tax_2026",
            side_effect=spy,
        ):
            result = build_portfolio_after_tax_dividend_summary(
                [_holding("379800")],
                {
                    "total_annual_dividend_krw": 500_000,
                    "holding_dividends": [
                        _forecast("379800", 500_000, is_etf=True)
                    ],
                },
            )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["asset_type"], "kr_listed_us_etf")
        self.assertEqual(calls[0]["annual_realized_gain_krw"], 0)
        self.assertEqual(calls[0]["taxable_etf_gain_krw"], 0)
        row = result["instruments"][0]
        self.assertTrue(row["data_quality"]["distribution_only"])
        self.assertEqual(row["display_asset_class"], "국내상장 ETF 분배금")

    def test_usd_direct_reuses_existing_contract_without_final_korean_tax_claim(self):
        gross = 400_000
        result = build_portfolio_after_tax_dividend_summary(
            [_holding("QQQ", currency="USD")],
            {
                "total_annual_dividend_krw": gross,
                "holding_dividends": [
                    _forecast("QQQ", gross, currency="USD", is_etf=True)
                ],
            },
        )
        expected = compare_investment_tax_2026(
            asset_type="us_direct",
            annual_distribution_krw=gross,
            annual_realized_gain_krw=0,
            existing_personal_financial_income_krw=0,
            corporation_to_owner_distribution_krw=0,
        )["individual"]
        row = result["instruments"][0]
        self.assertEqual(
            row["known_tax_krw"], expected["taxes"]["known_tax_total_krw"]
        )
        self.assertEqual(
            row["after_known_tax_cash_krw"], expected["after_known_tax_cash_krw"]
        )
        self.assertEqual(
            row["data_quality"]["usd_holding_tax_scope"],
            "wealth_us_direct_contract",
        )
        self.assertFalse(
            result["data_quality"]["final_comprehensive_income_tax_calculated"]
        )

    def test_duplicate_same_instrument_aggregates_once(self):
        holdings = [
            _holding("005930", quantity=10, market=700_000, cost=600_000),
            _holding("A005930", quantity=5, market=350_000, cost=300_000),
        ]
        summary = {
            "total_annual_dividend_krw": 150_000,
            "holding_dividends": [
                _forecast("005930", 100_000, quantity=10),
                _forecast("A005930", 50_000, quantity=5),
            ],
        }
        result = build_portfolio_after_tax_dividend_summary(holdings, summary)
        rows = [
            row for row in result["instruments"] if row["code"] == "005930"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 15)
        self.assertEqual(rows[0]["market_value_krw"], 1_050_000)
        self.assertEqual(rows[0]["cost_value_krw"], 900_000)
        self.assertEqual(rows[0]["gross_annual_dividend_krw"], 150_000)
        self.assertEqual(rows[0]["holding_row_count"], 2)
        self.assertEqual(rows[0]["forecast_row_count"], 2)

    def test_forecast_residual_prevents_complete_after_tax_yield(self):
        result = build_portfolio_after_tax_dividend_summary(
            [_holding("005930")],
            {
                "total_annual_dividend_krw": 1_000_000,
                "holding_dividends": [_forecast("005930", 800_000)],
            },
        )
        self.assertEqual(result["attributed_annual_dividend_krw"], 800_000)
        self.assertEqual(result["unattributed_annual_dividend_krw"], 200_000)
        self.assertFalse(result["forecast_attribution_complete"])
        self.assertEqual(result["after_tax_dividend_coverage_pct"], 80.0)
        self.assertEqual(result["calculation_status"], "partial")
        self.assertIsNone(result["after_known_tax_yield_on_market_value_pct"])
        self.assertIsNone(result["after_known_tax_yield_on_cost_pct"])

    def test_unsupported_currency_makes_portfolio_partial(self):
        result = build_portfolio_after_tax_dividend_summary(
            [_holding("XYZ", currency="EUR")],
            {
                "total_annual_dividend_krw": 100_000,
                "holding_dividends": [
                    _forecast("XYZ", 100_000, currency="EUR")
                ],
            },
        )
        self.assertEqual(result["after_tax_dividend_coverage_pct"], 0.0)
        self.assertEqual(result["unsupported_gross_dividend_krw"], 100_000)
        self.assertEqual(result["calculation_status"], "partial")
        self.assertIsNone(result["after_known_tax_cash_krw"])
        self.assertIsNone(result["after_known_tax_yield_on_market_value_pct"])

    def test_all_holdings_remain_in_yield_denominator_even_when_code_unjoinable(self):
        holdings = [
            _holding("005930", market=1_000_000, cost=800_000),
            _holding("bad code!", market=500_000, cost=400_000),
        ]
        result = build_portfolio_after_tax_dividend_summary(
            holdings,
            {
                "total_annual_dividend_krw": 100_000,
                "holding_dividends": [_forecast("005930", 100_000)],
            },
        )
        self.assertEqual(result["market_value_basis_krw"], 1_500_000)
        self.assertEqual(result["cost_value_basis_krw"], 1_200_000)
        self.assertAlmostEqual(
            result["gross_yield_on_market_value_pct"], 6.6667
        )

    def test_zero_denominator_never_returns_nan_or_infinity(self):
        result = build_portfolio_after_tax_dividend_summary(
            [_holding("005930", market=0, cost=0)],
            {
                "total_annual_dividend_krw": 100_000,
                "holding_dividends": [_forecast("005930", 100_000)],
            },
        )
        self.assertIsNone(result["gross_yield_on_market_value_pct"])
        self.assertIsNone(result["gross_yield_on_cost_pct"])
        self.assertIsNone(result["after_known_tax_yield_on_market_value_pct"])
        self.assertIsNone(result["after_known_tax_yield_on_cost_pct"])

    def test_no_dividends_is_complete_when_attribution_is_empty(self):
        result = build_portfolio_after_tax_dividend_summary(
            [_holding("005930")],
            {"total_annual_dividend_krw": 0, "holding_dividends": []},
        )
        self.assertEqual(result["calculation_status"], "complete")
        self.assertEqual(result["gross_annual_dividend_krw"], 0)
        self.assertEqual(result["known_tax_total_krw"], 0)
        self.assertEqual(result["after_known_tax_cash_krw"], 0)
        self.assertEqual(result["after_tax_dividend_coverage_pct"], 100.0)
        self.assertEqual(result["gross_yield_on_market_value_pct"], 0.0)
        self.assertEqual(result["after_known_tax_yield_on_market_value_pct"], 0.0)

    def test_attributed_amount_above_canonical_total_is_not_complete(self):
        result = build_portfolio_after_tax_dividend_summary(
            [_holding("005930")],
            {
                "total_annual_dividend_krw": 100_000,
                "holding_dividends": [_forecast("005930", 120_000)],
            },
        )
        self.assertEqual(result["forecast_attribution_excess_krw"], 20_000)
        self.assertFalse(result["forecast_attribution_complete"])
        self.assertEqual(result["calculation_status"], "partial")
        self.assertIsNone(result["after_known_tax_yield_on_market_value_pct"])


if __name__ == "__main__":
    unittest.main()
