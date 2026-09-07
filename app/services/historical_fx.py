from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any
import httpx

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
FX_CACHE_FILE = DATA_DIR / "historical_fx_cache.json"

_HISTORICAL_FX_MAP: dict[str, float] = {}
_LAST_FETCH_TIME: datetime.datetime | None = None


def load_cached_fx() -> dict[str, float]:
    global _HISTORICAL_FX_MAP
    if _HISTORICAL_FX_MAP:
        return _HISTORICAL_FX_MAP

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if FX_CACHE_FILE.exists():
        try:
            with open(FX_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _HISTORICAL_FX_MAP = {k: float(v) for k, v in data.items()}
                return _HISTORICAL_FX_MAP
        except Exception as e:
            logger.warning(f"환율 캐시 파일 로드 실패: {e}")
    return {}


def save_cached_fx(fx_map: dict[str, float]) -> None:
    global _HISTORICAL_FX_MAP
    _HISTORICAL_FX_MAP = fx_map
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(FX_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(fx_map, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"환율 캐시 파일 저장 실패: {e}")


async def sync_historical_fx() -> dict[str, float]:
    """야후 파이낸스에서 5년치 일별 환율(KRW=X)을 비동기로 수집하여 캐싱합니다."""
    global _LAST_FETCH_TIME
    url = "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?interval=1d&range=5y"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                res_data = resp.json().get("chart", {}).get("result", [{}])[0]
                timestamps = res_data.get("timestamp", [])
                quotes = res_data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                
                fx_map = load_cached_fx()
                for ts, close in zip(timestamps, quotes):
                    if ts and close and float(close) > 0:
                        dt = (datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%Y-%m-%d")
                        fx_map[dt] = round(float(close), 2)
                
                save_cached_fx(fx_map)
                _LAST_FETCH_TIME = datetime.datetime.now()
                logger.info(f"과거 환율 데이터 동기화 완료: 총 {len(fx_map)}일자 캐싱됨")
                return fx_map
    except Exception as e:
        logger.error(f"과거 환율 데이터 수집 실패: {e}")

    return load_cached_fx()


def get_historical_fx_rate(target_date: str, fallback: float = 1385.0) -> float:
    """
    특정 일자(YYYY-MM-DD)의 종가 환율을 반환합니다.
    휴일/주말인 경우 직전 가장 최근 영업일의 환율을 반환합니다.
    """
    fx_map = load_cached_fx()
    if not fx_map:
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?interval=1d&range=5y"
            headers = {"User-Agent": "Mozilla/5.0"}
            r = httpx.get(url, headers=headers, timeout=5.0)
            if r.status_code == 200:
                res = r.json().get("chart", {}).get("result", [{}])[0]
                timestamps = res.get("timestamp", [])
                quotes = res.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                for ts, close in zip(timestamps, quotes):
                    if ts and close and float(close) > 0:
                        dt = (datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc) + datetime.timedelta(hours=9)).strftime("%Y-%m-%d")
                        fx_map[dt] = round(float(close), 2)
                save_cached_fx(fx_map)
        except Exception:
            pass

    if not fx_map:
        return fallback

    clean_target = str(target_date).strip()[:10]
    if clean_target in fx_map:
        return fx_map[clean_target]

    sorted_dates = sorted(fx_map.keys())
    past_dates = [d for d in sorted_dates if d <= clean_target]
    if past_dates:
        return fx_map[past_dates[-1]]

    if sorted_dates:
        return fx_map[sorted_dates[0]]

    return fallback
