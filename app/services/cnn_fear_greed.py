"""Personal-use CNN index via one fixed, unofficial GitHub static relay.

No direct CNN request, credentials, browser headers, financial files or timers.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, time, timedelta, timezone
import json
import math
import re

import httpx

from app.services.market_read_cache import MarketReadCache
from app.services.network_policy import external_network_allowed, require_external_network

FEED_URL = 'https://raw.githubusercontent.com/chirag127/fear-greed-index-api/main/data/latest.json'
PROJECT_URL = 'https://github.com/chirag127/fear-greed-index-api'
CNN_URL = 'https://www.cnn.com/markets/fear-and-greed'
MAX_BYTES = 65_536
TTL = 1800
FILE_MAX_AGE = timedelta(hours=36)
DATE_MAX_DAYS = 4
CLOCK_SKEW = timedelta(minutes=5)
RATINGS = {'Extreme Fear', 'Fear', 'Neutral', 'Greed', 'Extreme Greed'}
_cache = MarketReadCache(ttl=TTL, capacity=1)


def utc_now():
    return datetime.now(timezone.utc)


def unavailable(status='source_error', reason='relay_unavailable'):
    return {'label': '미국 공포·탐욕', 'score': None, 'rating': None,
            'status': status, 'reason': reason, 'source': 'CNN 지수 · 비공식 데이터 중계',
            'source_url': CNN_URL, 'relay_url': PROJECT_URL, 'observed_date': None,
            'relay_updated_at': None, 'retrieved_at': None, 'valid_until': None}


def parse_relay(payload, *, now=None):
    """Validate identity and times; age is rechecked on *every* cached read."""
    now = now or utc_now()
    if not isinstance(payload, dict):
        raise ValueError('invalid relay object')
    sources = payload.get('sources')
    if not isinstance(sources, dict) or not isinstance(sources.get('cnn'), dict) or sources['cnn'].get('ok') is not True:
        raise ValueError('CNN source failed')
    missing = payload.get('unavailable')
    if not isinstance(missing, list) or any(not isinstance(x, str) for x in missing):
        raise ValueError('invalid availability')
    if any('cnn' in x.casefold() for x in missing):
        raise ValueError('CNN unavailable')
    headline = payload.get('headline')
    item = headline.get('cnn-fng') if isinstance(headline, dict) else None
    if not isinstance(item, dict):
        raise ValueError('missing CNN headline')
    score = item.get('value')
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100 or not math.isfinite(score):
        raise ValueError('invalid CNN score')
    zone = item.get('zone')
    rating = zone.get('label') if isinstance(zone, dict) else None
    if not isinstance(rating, str) or rating not in RATINGS:
        raise ValueError('invalid CNN rating')
    day_text, updated_text = item.get('date'), payload.get('updated')
    if not isinstance(day_text, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day_text):
        raise ValueError('invalid CNN date')
    day = date.fromisoformat(day_text)
    if not isinstance(updated_text, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)', updated_text):
        raise ValueError('invalid relay timestamp')
    updated = datetime.fromisoformat(updated_text.replace('Z', '+00:00'))
    if updated > now + CLOCK_SKEW or day > now.date() or day > updated.date():
        raise ValueError('future relay observation')
    # The relay supplies a calendar date, not an intraday CNN observation time.
    # Use UTC calendar days conservatively; never invent a US trading timestamp.
    utc_cutoff = datetime.combine(day + timedelta(days=DATE_MAX_DAYS), time(), timezone.utc)
    valid_until = min(updated + FILE_MAX_AGE, utc_cutoff)
    return {'score': score, 'rating': rating, 'observed_date': day_text,
            'relay_updated_at': updated.isoformat(), 'valid_until': valid_until.isoformat()}


def reject_constant(value):
    raise ValueError('nonfinite JSON constant')


async def _download():
    require_external_network('CNN GitHub relay')
    # Dedicated client: Yahoo HEADERS/cookies, auth, proxies and env secrets
    # cannot be inherited. Redirects, including another GitHub URL, fail closed.
    async with asyncio.timeout(6):
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False, trust_env=False,
                                     headers={'User-Agent': 'Wealth-market-relay/1.0', 'Accept': 'application/json'}) as client:
            async with client.stream('GET', FEED_URL) as response:
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError('unexpected relay status')
                length = response.headers.get('Content-Length')
                if length is not None and not 0 <= int(length) <= MAX_BYTES:
                    raise ValueError('relay too large')
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError('relay too large')
    return parse_relay(json.loads(body, parse_constant=reject_constant))


async def get_cnn_fear_greed():
    if not external_network_allowed():
        return unavailable('not_connected', 'external_network_disabled')
    result = await _cache.get('cnn-us-relay', _download)
    value = result.get('value')
    metadata = {k: result.get(k) for k in ('retrieved_at', 'last_attempt_at', 'cache_hit')}
    # MarketReadCache keeps a previous success for diagnostics after failure;
    # never return that cached score/rating as a usable observation.
    if result.get('update_delayed') or not value:
        return {**unavailable(), **metadata}
    now = utc_now()
    updated = datetime.fromisoformat(value['relay_updated_at'])
    if updated > now + CLOCK_SKEW:
        return {**unavailable(reason='invalid_relay_time'), **metadata}
    if now >= datetime.fromisoformat(value['valid_until']):
        return {**unavailable('stale', 'relay_data_stale'), **metadata,
                'observed_date': value['observed_date'], 'relay_updated_at': value['relay_updated_at']}
    return {**unavailable(), **value, **metadata, 'status': 'ok', 'reason': None}
