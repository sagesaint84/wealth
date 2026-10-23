"""Read-only SMA events over complete, adjusted exchange sessions."""
import asyncio
import math
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache


@lru_cache(maxsize=4)
def exchange_calendar(name):
    import exchange_calendars
    return exchange_calendars.get_calendar(name)


def analyze_sessions(candles, calendar_name, *, now=None, calendar=None, observed_at=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("timezone-aware now required")
    observed_at = observed_at or now
    try:
        calendar = calendar if calendar is not None else exchange_calendar(calendar_name)
        # A closing auction/provider update can arrive after the exchange close.
        # Exclude same-session bars until 30 minutes after the scheduled close.
        local_day = now.astimezone(calendar.tz).date().isoformat()
        latest_session = calendar.date_to_session(local_day, direction="previous")
        while calendar.session_close(latest_session).to_pydatetime() + timedelta(minutes=30) > now:
            latest_session = calendar.previous_session(latest_session)
        expected = latest_session.date().isoformat()
        by_day = {}
        for row in candles:
            day = str(row.get("date") or "")
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError("invalid session date")
            close = row.get("close")
            if isinstance(close, bool) or not isinstance(close, (int, float)) or not math.isfinite(close) or close <= 0:
                raise ValueError("invalid adjusted close")
            if not calendar.is_session(day) or day > expected:
                continue
            if calendar.session_close(day).to_pydatetime() + timedelta(minutes=30) > observed_at:
                continue
            if day in by_day and by_day[day] != close:
                raise ValueError("conflicting session closes")
            by_day[day] = float(close)
        days = sorted(by_day)[-51:]
        if not days:
            return {"status": "insufficient_data", "events": [], "count": 0, "expected_session": expected}
        # Missing bars cannot silently turn a 50-observation average into an
        # average over an unknown, longer trading period. No forward filling.
        required = [s.date().isoformat() for s in calendar.sessions_in_range(days[0], days[-1])]
        if days != required:
            return {"status": "missing_sessions", "events": [], "count": len(days), "as_of": days[-1], "expected_session": expected}
        closes = [by_day[d] for d in days]
        n = len(closes)
        def sma(window, offset=0):
            return sum(closes[n-window-offset:n-offset if offset else n]) / window
        s20 = sma(20) if n >= 20 else None
        s50 = sma(50) if n >= 50 else None
        events = []
        if n >= 21 and closes[-2] >= sma(20, 1) and closes[-1] < s20:
            events.append("SMA20_BREAKDOWN")
        if n >= 51:
            prev20, prev50 = sma(20, 1), sma(50, 1)
            if closes[-2] >= prev50 and closes[-1] < s50:
                events.append("SMA50_BREAKDOWN")
            if prev20 <= prev50 and s20 > s50:
                events.append("GOLDEN_CROSS")
            if prev20 >= prev50 and s20 < s50:
                events.append("DEAD_CROSS")
        stale = days[-1] != expected
        return {"status": "stale" if stale else ("ok" if n >= 51 else "insufficient_data"),
                "count": n, "as_of": days[-1], "previous_session": days[-2] if n >= 2 else None,
                "expected_session": expected, "close": closes[-1], "sma20": s20, "sma50": s50,
                "below_sma20": closes[-1] < s20 if s20 is not None else None,
                "below_sma50": closes[-1] < s50 if s50 is not None else None,
                "available": {"SMA20_BREAKDOWN": n >= 21, "SMA50_BREAKDOWN": n >= 51,
                              "GOLDEN_CROSS": n >= 51, "DEAD_CROSS": n >= 51},
                "events": events if not stale else [], "historical_events": events if stale else []}
    except (ImportError, KeyError):
        return {"status": "calendar_unavailable", "events": []}
    except Exception:
        return {"status": "invalid_data", "events": []}


async def holdings_signals(snapshot, owner="모두", *, now=None, loader=None):
    from app.services.web_finance import fetch_signal_daily_series
    loader = loader or fetch_signal_daily_series
    accounts = {a["id"]: a for a in snapshot.get("accounts", []) if a.get("id")}
    groups = {}
    for holding in snapshot.get("holdings", []):
        quantity = holding.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not math.isfinite(quantity) or quantity <= 0:
            continue
        account = accounts.get(holding.get("account_id"))
        if not account:  # unresolved ownership is never silently assigned
            continue
        if owner != "모두" and (account.get("owner") or "모두") != owner:
            continue
        code = str(holding.get("code") or "").strip().upper()
        if not code:
            continue
        currency = str(holding.get("currency") or "").upper()
        market = str(holding.get("market") or "").upper()
        key = (code, currency)
        row = groups.setdefault(key, {"code": code, "name": holding.get("name") or code,
                                      "currency": currency, "markets": set(), "accounts": []})
        row["markets"].add(market)
        row["accounts"].append({"account_id": account["id"], "owner": account.get("owner") or "모두",
                                "broker": account.get("broker"), "account_name": account.get("name"), "quantity": quantity})
    limit = asyncio.Semaphore(4)
    async def analyze(key, row):
        async with limit:
            hints = row.pop("markets")
            kr_hints = {"KOSDAQ" if h in {"KOSDAQ", "KQ"} else "KOSPI" for h in hints if h in {"KOSDAQ", "KQ", "KOSPI", "KS"}}
            row["market"] = next(iter(kr_hints)) if len(kr_hints) == 1 else "KRX" if key[1] == "KRW" else "US"
            if len(kr_hints) > 1:
                return {**row, "status": "identity_conflict", "events": []}
            try:
                fetched = await loader(*key, row["market"])
                series = fetched.get("value")
                if not series:
                    return {**row, "status": "source_error", "events": [], **{k: v for k, v in fetched.items() if k != "value"}}
                if series.get("adjustment") != "adjusted_close":
                    return {**row, "status": "adjustment_unverified", "events": []}
                seen_at = datetime.fromisoformat(fetched["retrieved_at"]) if fetched.get("retrieved_at") else None
                result = analyze_sessions(series["candles"], series["calendar"], now=now, observed_at=seen_at)
                if fetched.get("update_delayed"):
                    result["historical_events"] = result.get("events", [])
                    result.update(status="update_delayed", events=[])
                return {**row, **result, "price_basis": "adjusted_close", "source": series["source"],
                        "source_url": series["source_url"], "exchange": series["exchange"],
                        **{k: v for k, v in fetched.items() if k != "value"}}
            except Exception:
                return {**row, "status": "source_error", "events": []}
    return {"owner": owner, "items": await asyncio.gather(*(analyze(k, r) for k, r in groups.items()))}
