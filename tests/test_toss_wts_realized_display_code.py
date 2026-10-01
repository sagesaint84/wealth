from __future__ import annotations

from app.services.toss_wts_feed import project_realized_feed_row


def _row(*, market_type: str, symbol: str, product_code: str) -> dict:
    return {
        "date": "2026-09-22",
        "market_type": market_type,
        "symbol": symbol,
        "product_code": product_code,
        "name": "테스트 종목",
        "quantity": 1,
        "profit_loss": {"krw": 1000, "usd": 1.0},
        "profit_rate": 1.0,
        "sell_amount": {"krw": 11000, "usd": 11.0},
        "buy_amount": {"krw": 10000, "usd": 10.0},
    }


def test_kr_numeric_provider_prefix_is_removed_from_both_display_fields():
    projected = project_realized_feed_row(
        _row(market_type="KR", symbol="A102970", product_code="A102970")
    )
    assert projected["symbol"] == "102970"
    assert projected["product_code"] == "102970"


def test_kr_alphanumeric_provider_prefix_is_removed_from_both_display_fields():
    projected = project_realized_feed_row(
        _row(market_type="kr", symbol="A0193T0", product_code="A0193T0")
    )
    assert projected["symbol"] == "0193T0"
    assert projected["product_code"] == "0193T0"


def test_us_ticker_symbol_remains_unchanged():
    projected = project_realized_feed_row(
        _row(market_type="US", symbol="QQQM", product_code="US46090E1038")
    )
    assert projected["symbol"] == "QQQM"
    assert projected["product_code"] == "US46090E1038"
