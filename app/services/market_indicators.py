"""Official daily yields and an honest unconnected CNN reference.

No quotes are written to a portfolio, asset record, or price-refresh endpoint.
"""
import asyncio
import hashlib
import math
import os
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
import xml.etree.ElementTree as ET

import httpx

from app.services.market_read_cache import MarketReadCache
from app.services.network_policy import require_external_network

TREASURY_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
TREASURY_PAGE = "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed"
ECOS_PAGE = "https://ecos.bok.or.kr/"
_cache = MarketReadCache(ttl=21600, capacity=8)


def parse_treasury_yields(text):
    root = ET.fromstring(text)
    rows = []
    ns = {"a": "http://www.w3.org/2005/Atom", "d": "http://schemas.microsoft.com/ado/2007/08/dataservices"}
    for entry in root.findall("a:entry", ns):
        day, value = entry.find(".//d:NEW_DATE", ns), entry.find(".//d:BC_10YEAR", ns)
        if day is None or value is None or not value.text:
            continue
        rows.append((date.fromisoformat(day.text[:10]).isoformat(), float(value.text)))
    return rows


def parse_ecos_yields(payload):
    data = payload.get("StatisticSearch")
    if not isinstance(data, dict) or not isinstance(data.get("row"), list):
        raise ValueError("ECOS source error")
    if int(data.get("list_total_count", 0)) > 100:
        raise ValueError("ECOS partial response")
    rows = []
    for row in data["row"]:
        if (row.get("STAT_CODE") != "817Y002" or row.get("ITEM_CODE1") != "010210000"
                or str(row.get("UNIT_NAME") or "").strip() != "연%"):
            raise ValueError("ECOS series/unit mismatch")
        if row.get("DATA_VALUE") in (None, "", "-"):
            continue
        raw = str(row.get("TIME") or "")
        if not re.fullmatch(r"\d{8}", raw):
            raise ValueError("ECOS date mismatch")
        day = datetime.strptime(raw, "%Y%m%d").date().isoformat()
        rows.append((day, float(row["DATA_VALUE"])))
    return rows


def yield_observation(rows, today):
    values = {}
    for day, value in rows:
        parsed = date.fromisoformat(day)
        if not math.isfinite(value):
            raise ValueError("invalid yield")
        if parsed > today:
            continue
        if day in values and values[day] != value:
            raise ValueError("conflicting yields")
        values[day] = value
    days = sorted(values)
    if not days:
        raise ValueError("no dated yield")
    previous = values[days[-2]] if len(days) >= 2 else None
    delta = values[days[-1]] - previous if previous is not None else None
    return {"value": values[days[-1]], "unit": "연%", "observed_date": days[-1],
            "previous_observed_date": days[-2] if previous is not None else None,
            "change_pp": round(delta, 6) if delta is not None else None,
            "change_bp": round(delta * 100, 4) if delta is not None else None,
            "series": [values[d] for d in days[-30:]]}


async def _treasury():
    require_external_network("Treasury daily yields")
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date()
    async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
        response = await client.get(TREASURY_URL, params={"data": "daily_treasury_yield_curve", "field_tdr_date_value": today.year})
        response.raise_for_status()
        rows = parse_treasury_yields(response.text)
        if len(rows) < 2:
            previous = await client.get(TREASURY_URL, params={"data": "daily_treasury_yield_curve", "field_tdr_date_value": today.year - 1})
            previous.raise_for_status()
            rows += parse_treasury_yields(previous.text)
    return yield_observation(rows, today)


async def _ecos(key):
    require_external_network("ECOS daily yields")
    from app.logging_security import install_credential_log_redaction
    install_credential_log_redaction()
    today = datetime.now(timezone(timedelta(hours=9))).date()
    begin = today - timedelta(days=45)
    url = (f"https://ecos.bok.or.kr/api/StatisticSearch/{quote(key, safe='')}/json/kr/1/100/"
           f"817Y002/D/{begin:%Y%m%d}/{today:%Y%m%d}/010210000")
    async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
        response = await client.get(url)
        response.raise_for_status()
        rows = parse_ecos_yields(response.json())
    return yield_observation(rows, today)


async def get_market_indicators():
    key = os.environ.get("ECOS_API_KEY", "").strip()
    async def rate(symbol, label, source, url, loader, cache_key, local_today):
        result = await _cache.get(cache_key, loader)
        observation = result.pop("value")
        stale = bool(observation and (local_today - date.fromisoformat(observation["observed_date"])).days > 4)
        return {"symbol": symbol, "label": label, "kind": "yield", "source": source, "source_url": url,
                "frequency": "일별", "status": "source_error" if observation is None else ("stale" if stale else "ok"),
                **(observation or {"value": None, "change_pp": None, "change_bp": None, "observed_date": None, "series": [], "unit": "연%"}),
                **result, "observation_stale": stale}
    from zoneinfo import ZoneInfo
    us_today = datetime.now(ZoneInfo("America/New_York")).date()
    kr_today = datetime.now(timezone(timedelta(hours=9))).date()
    us = rate("US10Y", "미국 10년 국채", "U.S. Treasury", TREASURY_PAGE, _treasury, "US10Y", us_today)
    if key:
        kr = rate("KR10Y", "한국 10년 국채", "한국은행 ECOS", ECOS_PAGE,
                  lambda: _ecos(key), ("KR10Y", hashlib.sha256(key.encode()).hexdigest()), kr_today)
        rates = await asyncio.gather(us, kr)
    else:
        rates = [await us, {"symbol": "KR10Y", "label": "한국 10년 국채", "kind": "yield",
                 "value": None, "unit": "연%", "series": [], "source": "한국은행 ECOS", "source_url": ECOS_PAGE,
                 "frequency": "일별", "status": "not_configured", "reason": "ECOS_API_KEY 미설정",
                 "observed_date": None, "retrieved_at": None, "last_attempt_at": None,
                 "change_pp": None, "change_bp": None, "update_delayed": False}]
    return {"rates": rates, "fear_greed": {"label": "미국 공포·탐욕", "score": None,
            "source": "CNN", "source_url": "https://www.cnn.com/markets/fear-and-greed",
            "status": "not_connected", "reason": "공식 자동 연동 허용 경로 미확인", "observed_date": None}}
