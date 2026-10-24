"""Confirmed exchange sessions with synthetic prices; no HTTP or finance writes."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
import exchange_calendars as xcals

from app.services.holding_signals import analyze_sessions, holdings_signals


def fixture(values, calendar_name="XNYS", end="2026-10-22"):
    calendar = xcals.get_calendar(calendar_name)
    days = calendar.sessions_in_range("2026-01-02", end)[-len(values):]
    candles = [{"date": day.date().isoformat(), "close": value} for day, value in zip(days, values)]
    now = calendar.session_close(days[-1]).to_pydatetime() + timedelta(minutes=31)
    return candles, now


@pytest.mark.parametrize("calendar", ["XKRX", "XNYS"])
def test_breakdown_and_dead_cross_exact_values(calendar):
    candles, now = fixture([100] * 50 + [90], calendar)
    result = analyze_sessions(candles, calendar, now=now)
    assert result["status"] == "ok"
    assert set(result["events"]) == {"SMA20_BREAKDOWN", "SMA50_BREAKDOWN", "DEAD_CROSS"}
    assert result["sma20"] == pytest.approx(99.5)
    assert result["sma50"] == pytest.approx(99.8)
    assert result["close"] == 90
    assert result["as_of"] == candles[-1]["date"]


def test_golden_cross_and_equality_boundary():
    candles, now = fixture([100] * 50 + [110])
    assert analyze_sessions(candles, "XNYS", now=now)["events"] == ["GOLDEN_CROSS"]
    candles[-1]["close"] = 100
    result = analyze_sessions(candles, "XNYS", now=now)
    assert result["events"] == []
    assert not result["below_sma20"] and not result["below_sma50"]


@pytest.mark.parametrize("count", [20, 21, 50, 51])
def test_minimum_session_counts(count):
    candles, now = fixture([100] * (count - 1) + [90])
    result = analyze_sessions(candles, "XNYS", now=now)
    assert result["status"] == ("ok" if count == 51 else "insufficient_data")
    assert ("SMA20_BREAKDOWN" in result["events"]) == (count >= 21)
    assert ("SMA50_BREAKDOWN" in result["events"]) == (count >= 51)
    assert ("DEAD_CROSS" in result["events"]) == (count >= 51)


def test_already_below_is_not_a_new_breakdown():
    candles, now = fixture([100] * 49 + [90, 89])
    result = analyze_sessions(candles, "XNYS", now=now)
    assert result["below_sma20"] and result["below_sma50"]
    assert result["events"] == []


def test_missing_conflicting_and_bad_prices_do_not_emit_events():
    candles, now = fixture([100] * 50 + [90])
    assert analyze_sessions(candles[:20] + candles[21:], "XNYS", now=now)["status"] == "missing_sessions"
    assert analyze_sessions(candles + [{**candles[-1], "close": 91}], "XNYS", now=now)["status"] == "invalid_data"
    for price in [0, -1, float("nan"), True, None]:
        result = analyze_sessions(candles[:-1] + [{**candles[-1], "close": price}], "XNYS", now=now)
        assert result["events"] == [] and result["status"] == "invalid_data"


@pytest.mark.parametrize("calendar,end,closed_day", [
    ("XKRX", "2026-10-08", "2026-10-09"),  # Hangul Day
    ("XNYS", "2026-11-25", "2026-11-26"),  # Thanksgiving
    ("XNYS", "2026-10-23", "2026-10-24"),  # Weekend
])
def test_holidays_and_weekends_never_create_a_session(calendar, end, closed_day):
    candles, _ = fixture([100] * 50 + [90], calendar, end)
    now = datetime.fromisoformat(closed_day + "T22:00:00+00:00")
    result = analyze_sessions(candles + [{"date": closed_day, "close": 1}], calendar, now=now)
    assert result["status"] == "ok"
    assert result["as_of"] == end and result["close"] == 90


def test_early_close_and_preclose_cached_bar_are_excluded_until_confirmed():
    candles, after_close = fixture([100] * 50 + [90], end="2026-11-27")
    calendar = xcals.get_calendar("XNYS")
    close = calendar.session_close("2026-11-27").to_pydatetime()
    assert close.hour == 18  # 13:00 EST scheduled early close.
    before = close - timedelta(minutes=1)
    result = analyze_sessions(candles, "XNYS", now=before)
    assert result["as_of"] == candles[-2]["date"] and result["events"] == []
    cached = analyze_sessions(candles, "XNYS", now=after_close, observed_at=before)
    assert cached["status"] == "stale" and cached["events"] == []
    assert analyze_sessions(candles, "XNYS", now=after_close)["events"]


def test_kst_close_and_us_day_still_open_are_evaluated_separately():
    # 16:01 KST: KRX closing auction + 30min has completed; US October 23 has not opened.
    now = datetime.fromisoformat("2026-10-23T16:01:00+09:00")
    kr, _ = fixture([100] * 50 + [90], "XKRX", "2026-10-23")
    us, _ = fixture([100] * 50 + [90], "XNYS", "2026-10-22")
    assert analyze_sessions(kr, "XKRX", now=now)["as_of"] == "2026-10-23"
    assert analyze_sessions(us, "XNYS", now=now)["as_of"] == "2026-10-22"


def test_duplicate_equal_bars_are_deduplicated_and_stale_events_suppressed():
    candles, now = fixture([100] * 50 + [90])
    result = analyze_sessions(candles + [candles[-1]], "XNYS", now=now)
    assert result["count"] == 51
    next_day = now + timedelta(days=1)
    stale = analyze_sessions(candles, "XNYS", now=next_day)
    assert stale["status"] == "stale" and stale["events"] == []
    assert stale["historical_events"]


def test_conflicting_exchange_identity_is_not_automatically_merged():
    data = snapshot()
    data["holdings"][0].update(code="005930", currency="KRW", market="KOSPI")
    data["holdings"][1].update(code="005930", currency="KRW", market="KOSDAQ")
    async def forbidden(*key):
        raise AssertionError("conflicting identity must not be fetched")
    result = asyncio.run(holdings_signals(data, loader=forbidden))["items"][0]
    assert result["status"] == "identity_conflict" and result["events"] == []


def snapshot():
    return {"accounts": [{"id": "a", "owner": "아빠"}, {"id": "b", "owner": "엄마"}],
            "holdings": [{"id": "1", "account_id": "a", "code": "TEST", "currency": "USD", "quantity": 2},
                         {"id": "2", "account_id": "b", "code": "TEST", "currency": "USD", "quantity": 3},
                         {"id": "3", "account_id": "a", "code": "SOLD", "currency": "USD", "quantity": 0}]}


def test_dedup_owner_filter_sold_positions_and_no_mutation():
    candles, now = fixture([100] * 50 + [110])
    data = snapshot(); before = deepcopy(data); calls = []
    async def loader(*key):
        calls.append(key)
        return {"value": {"candles": candles, "adjustment": "adjusted_close", "calendar": "XNYS",
                          "source": "synthetic", "source_url": "https://example.invalid/", "exchange": "NMS"},
                "retrieved_at": now.isoformat(), "update_delayed": False}
    result = asyncio.run(holdings_signals(data, now=now, loader=loader))
    assert len(calls) == 1 and len(result["items"][0]["accounts"]) == 2
    result = asyncio.run(holdings_signals(data, "엄마", now=now, loader=loader))
    assert [a["account_id"] for a in result["items"][0]["accounts"]] == ["b"]
    assert data == before


def test_loader_failure_and_delayed_last_good_do_not_become_normal_signals():
    async def failed(*key):
        raise OSError("synthetic failure")
    result = asyncio.run(holdings_signals(snapshot(), loader=failed))["items"][0]
    assert result["status"] == "source_error" and result["events"] == []
    assert "close" not in result
    candles, now = fixture([100] * 50 + [90])
    async def delayed(*key):
        return {"value": {"candles": candles, "adjustment": "adjusted_close", "calendar": "XNYS",
                          "source": "synthetic", "source_url": "https://example.invalid/", "exchange": "NYQ"},
                "retrieved_at": now.isoformat(), "update_delayed": True}
    result = asyncio.run(holdings_signals(snapshot(), now=now, loader=delayed))["items"][0]
    assert result["status"] == "update_delayed" and result["events"] == []
    assert result["historical_events"]
