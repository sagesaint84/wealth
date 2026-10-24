"""Yahoo TNX yield contract and the link-only CNN reference; no finance writes."""
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.market_read_cache import MarketReadCache
from app.services.network_policy import require_external_network

TNX_SOURCE = "Yahoo Finance / CBOE 10-Year Treasury Note Yield"
TNX_PAGE = "https://finance.yahoo.com/quote/%5ETNX/"
_cache = MarketReadCache(ttl=300, capacity=1)


def unavailable_market_indicators():
    return {"rates": [{"symbol": "^TNX", "label": "미국 10년 국채", "kind": "yield",
                       "provider": "YAHOO_TNX", "source": TNX_SOURCE, "source_url": TNX_PAGE,
                       "value": None, "unit": "연%", "change_pp": None, "change_bp": None,
                       "observed_date": None, "observed_at": None, "retrieved_at": None,
                       "quote_delay_minutes": None, "series": [], "status": "source_error",
                       "reason": "조회 불가"}],
            "fear_greed": {"label": "미국 공포·탐욕", "score": None, "source": "CNN",
                           "source_url": "https://www.cnn.com/markets/fear-and-greed",
                           "status": "not_connected", "reason": "공식 자동 연동 허용 경로 미확인",
                           "observed_date": None}}


def parse_yahoo_tnx(payload, *, now=None):
    """Yahoo ^TNX quotes are already percentage yields: 4.15 means 4.15%.

    Do not apply the scaling of a differently quoted Cboe contract. Daily
    closes supply the previous trading observation, never chartPreviousClose
    (which can precede the entire requested range).
    """
    now = now or datetime.now(timezone.utc)
    chart = payload.get("chart") or {}
    if chart.get("error") or len(chart.get("result") or []) != 1:
        raise ValueError("TNX source error")
    entry = chart["result"][0]
    meta = entry.get("meta") or {}
    if meta.get("symbol") != "^TNX" or meta.get("instrumentType") != "INDEX":
        raise ValueError("TNX identity mismatch")
    exchange_timezone = meta.get("exchangeTimezoneName")
    if exchange_timezone not in {"America/Chicago", "America/New_York"}:
        raise ValueError("TNX timezone mismatch")
    def numeric(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("invalid TNX value")
        return float(value)
    value = numeric(meta.get("regularMarketPrice"))
    observed = datetime.fromtimestamp(numeric(meta.get("regularMarketTime")), timezone.utc)
    if observed.timestamp() <= 0 or observed > now + timedelta(minutes=5):
        raise ValueError("invalid TNX observation time")
    local_zone = ZoneInfo(exchange_timezone)
    day = observed.astimezone(local_zone).date().isoformat()
    timestamps = entry.get("timestamp") or []
    closes = entry.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    if len(timestamps) != len(closes):
        raise ValueError("TNX daily series mismatch")
    by_day = {}
    for stamp, close in zip(timestamps, closes):
        if close is None:
            continue
        stamp = numeric(stamp)
        if stamp > observed.timestamp():
            continue
        bar_day = datetime.fromtimestamp(stamp, local_zone).date().isoformat()
        close = numeric(close)
        if bar_day in by_day and by_day[bar_day] != close:
            raise ValueError("conflicting TNX closes")
        by_day[bar_day] = close
    previous_days = sorted(d for d in by_day if d < day)
    previous_day = previous_days[-1] if previous_days else None
    previous = by_day[previous_day] if previous_day else None
    delta = value - previous if previous is not None else None
    delay = meta.get("exchangeDataDelayedBy")
    if delay is not None:
        delay = numeric(delay)
        if delay < 0:
            raise ValueError("invalid TNX delay")
    return {"value": value, "unit": "연%", "exchange_timezone": exchange_timezone,
            "observed_date": day, "observed_at": observed.isoformat(),
            "previous_observed_date": previous_day, "previous_close": previous,
            "change_pp": round(delta, 6) if delta is not None else None,
            "change_bp": round(delta * 100, 4) if delta is not None else None,
            "series": [by_day[d] for d in sorted(by_day)[-30:]], "quote_delay_minutes": delay,
            "observation_stale": now - observed > timedelta(days=4)}


async def get_market_indicators(client):
    """Use market-overview's existing Yahoo HTTP client, with a five-minute cache."""
    from app.services.web_finance import HEADERS
    async def load():
        require_external_network("Yahoo TNX yield")
        response = await client.get("https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX",
                                    params={"interval": "1d", "range": "1mo"}, headers=HEADERS, timeout=6.0)
        response.raise_for_status()
        return parse_yahoo_tnx(response.json())
    fetched = await _cache.get("^TNX", load)
    observation = fetched.pop("value")
    result = unavailable_market_indicators()
    rate = result["rates"][0]
    rate.update(fetched)
    # A failed refresh is never presented as a successful current quote. The
    # cache retains the last successful fetch time for diagnostics only.
    if observation and not fetched.get("update_delayed"):
        observed = datetime.fromisoformat(observation["observed_at"])
        stale = datetime.now(timezone.utc) - observed > timedelta(days=4)
        rate.update(observation, observation_stale=stale, status="stale" if stale else "ok")
        rate.pop("reason", None)
    return result
