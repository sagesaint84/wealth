from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any
import xml.etree.ElementTree as ET

import httpx

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    s = str(val).replace(",", "").replace("$", "").replace("₩", "").replace("%", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


import calendar

def _get_target_dates() -> tuple[str, str, str, str]:
    """
    (target_1w, target_1m, target_1y, target_ytd)를 'YYYYMMDD' 문자열로 반환합니다.
    """
    now = datetime.now()
    # 1W: 정확히 7일 전 날짜
    d_1w = now - timedelta(days=7)
    target_1w = d_1w.strftime("%Y%m%d")

    # 1M: 정확히 1개월 전 날짜 (월말 일자 보정)
    m_year = now.year
    m_month = now.month - 1
    if m_month == 0:
        m_month = 12
        m_year -= 1
    max_day_1m = calendar.monthrange(m_year, m_month)[1]
    day_1m = min(now.day, max_day_1m)
    target_1m = f"{m_year:04d}{m_month:02d}{day_1m:02d}"

    # 1Y: 정확히 1년 전 날짜 (윤년 2월 29일 보정)
    y_year = now.year - 1
    max_day_1y = calendar.monthrange(y_year, now.month)[1]
    day_1y = min(now.day, max_day_1y)
    target_1y = f"{y_year:04d}{now.month:02d}{day_1y:02d}"

    # YTD: 작년 12월 31일
    target_ytd = f"{now.year - 1}1231"

    return target_1w, target_1m, target_1y, target_ytd


def calculate_period_changes(candles: list[dict[str, Any]], current_price: float) -> dict[str, float]:
    """
    일별 캔들 종가 리스트[{'date': 'YYYY-MM-DD' or 'YYYYMMDD', 'close': float}, ...]를 바탕으로
    1D(전일 종가), 1W(7일 전 날짜), 1M(1개월 전 날짜), YTD(연초), 1Y(1년 전 날짜) 수익률(%)을
    실제 캘린더 날짜(휴일이면 직전 최근 거래일 종가) 기준으로 계산합니다.
    """
    if not candles or current_price <= 0:
        return {"1D": 0.0, "1W": 0.0, "1M": 0.0, "YTD": 0.0, "1Y": 0.0}

    target_1w, target_1m, target_1y, target_ytd = _get_target_dates()

    # 1D: 직전 거래일 종가
    close_1d = float(candles[-2]["close"]) if len(candles) >= 2 else float(candles[-1]["close"])

    def find_close_on_or_before(target_ymd: str) -> float:
        for c in reversed(candles):
            c_date = str(c.get("date", "")).replace("-", "")[:8]
            if c_date <= target_ymd:
                return float(c["close"])
        return float(candles[0]["close"])

    close_1w = find_close_on_or_before(target_1w)
    close_1m = find_close_on_or_before(target_1m)
    close_ytd = find_close_on_or_before(target_ytd)
    close_1y = find_close_on_or_before(target_1y)

    def calc_rate(base_price: float) -> float:
        if base_price > 0:
            return round(((current_price - base_price) / base_price) * 100, 2)
        return 0.0

    return {
        "1D": calc_rate(close_1d),
        "1W": calc_rate(close_1w),
        "1M": calc_rate(close_1m),
        "YTD": calc_rate(close_ytd),
        "1Y": calc_rate(close_1y),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. 국내 주식 및 국내 상장 ETF (네이버 증권 웹 API)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_kr_stock_info(client: httpx.AsyncClient, code: str) -> dict[str, Any] | None:
    clean_code = str(code).strip().zfill(6)
    url = f"https://m.stock.naver.com/api/stock/{clean_code}/basic"
    try:
        resp = await client.get(url, headers=HEADERS, timeout=6.0)
        if resp.status_code != 200:
            return None
        data = resp.json()
        now_price = _to_float(data.get("closePrice"))
        rate = _to_float(data.get("fluctuationsRatio"))
        compare = data.get("compareToPreviousPrice") or {}
        if compare.get("name") in {"FALLING", "LOWER_LIMIT"} and rate > 0:
            rate = -rate

        return {
            "code": clean_code,
            "name": data.get("stockName") or "",
            "current_price": now_price,
            "day_change_rate": rate,
            "currency": "KRW",
        }
    except Exception:
        return None


async def fetch_kr_stock_candles(client: httpx.AsyncClient, code: str, current_price: float) -> dict[str, float]:
    clean_code = str(code).strip().zfill(6)
    url = f"https://fchart.stock.naver.com/sise.nhn?symbol={clean_code}&timeframe=day&count=300&requestType=0"
    try:
        resp = await client.get(url, headers=HEADERS, timeout=6.0)
        if resp.status_code != 200:
            return {"1D": 0.0, "1W": 0.0, "1M": 0.0, "YTD": 0.0, "1Y": 0.0}
        root = ET.fromstring(resp.text)
        items = root.findall(".//item")
        candles = []
        for it in items:
            raw = it.attrib.get("data", "")
            parts = raw.split("|")
            if len(parts) >= 6:
                d_str = parts[0]
                if len(d_str) == 8:
                    d_str = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
                candles.append({
                    "date": d_str,
                    "close": float(parts[4]),
                })
        return calculate_period_changes(candles, current_price)
    except Exception:
        return {"1D": 0.0, "1W": 0.0, "1M": 0.0, "YTD": 0.0, "1Y": 0.0}


# ─────────────────────────────────────────────────────────────────────────────
# 2. 미국 주식 및 미국 상장 ETF (야후 파이낸스 v8 API)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_us_stock_info(client: httpx.AsyncClient, symbol: str) -> dict[str, Any] | None:
    clean_sym = str(symbol).strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_sym}?interval=1d&range=1y"
    try:
        resp = await client.get(url, headers=HEADERS, timeout=7.0)
        if resp.status_code != 200:
            return None
        res_json = resp.json()
        result = res_json.get("chart", {}).get("result", [])
        if not result:
            return None
        meta = result[0].get("meta", {})
        timestamps = result[0].get("timestamp", [])
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        candles = []
        for ts, c_val in zip(timestamps, quotes):
            if c_val is not None and float(c_val) > 0:
                dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y%m%d")
                candles.append({"date": dt_str, "close": float(c_val)})

        price = float(meta.get("regularMarketPrice") or (candles[-1]["close"] if candles else 0.0))
        
        # 야후 파이낸스 정규장 전일 종가 정밀 결정
        prev_close = 0.0
        if meta.get("previousClose") is not None and float(meta.get("previousClose")) > 0:
            prev_close = float(meta.get("previousClose"))
        elif len(candles) >= 2:
            prev_close = float(candles[-2]["close"])
        elif candles:
            prev_close = float(candles[-1]["close"])

        day_rate = round(((price - prev_close) / prev_close) * 100, 2) if prev_close > 0 else 0.0

        period_changes = calculate_period_changes(candles, price)
        period_changes["1D"] = day_rate

        return {
            "code": clean_sym,
            "name": meta.get("shortName") or meta.get("symbol") or clean_sym,
            "current_price": price,
            "day_change_rate": day_rate,
            "currency": "USD",
            "period_changes": period_changes,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. 실시간 환율 (USD/KRW 등)
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_fx_rate_usd_krw(client: httpx.AsyncClient | None = None) -> float:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?interval=1d&range=5d"
    should_close = False
    if client is None:
        client = httpx.AsyncClient()
        should_close = True
    try:
        resp = await client.get(url, headers=HEADERS, timeout=6.0)
        if resp.status_code == 200:
            res_json = resp.json()
            meta = res_json.get("chart", {}).get("result", [{}])[0].get("meta", {})
            rate = float(meta.get("regularMarketPrice") or 0.0)
            if rate > 500:
                return round(rate, 2)
    except Exception:
        pass
    finally:
        if should_close:
            await client.aclose()
    return 1385.0


# ─────────────────────────────────────────────────────────────────────────────
# 4. 주요 시장 지수 (시장 스냅샷 및 스파크라인 차트)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_quotes(resp: Any) -> list[float]:
    if isinstance(resp, Exception) or getattr(resp, "status_code", None) != 200:
        return []
    try:
        raw = resp.json().get("chart", {}).get("result", [{}])[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
        return [float(v) for v in raw if v is not None and float(v) > 0]
    except Exception:
        return []


def _calculate_market_periods(
    valid_quotes_1y: list[tuple[float, float]],
    prev_close: float,
    current_price: float,
    quotes_5m: list[float] | None = None,
    quotes_60m: list[float] | None = None,
    quotes_monthly: list[float] | None = None,
) -> dict[str, Any]:
    """
    valid_quotes_1y: [(timestamp, close_price), ...]
    quotes_5m: 당일 5분봉 종가 리스트
    quotes_60m: 1주 60분봉 종가 리스트
    quotes_monthly: 전체 월봉(1mo) 종가 리스트 (3Y/5Y/10Y/MAX 장기용)
    """
    p = current_price or (valid_quotes_1y[-1][1] if valid_quotes_1y else (quotes_5m[-1] if quotes_5m else 0.0))
    if not valid_quotes_1y and not quotes_5m and not quotes_monthly:
        empty_stat = {"change": 0.0, "change_rate": 0.0, "series": [p, p] if p else []}
        return {k: empty_stat for k in ["1D", "1W", "1M", "3M", "YTD", "1Y", "3Y", "5Y", "10Y", "MAX", "ALL"]}

    now = datetime.now()
    cur_year = now.year
    last_price = p

    # 1D: 직전 거래일 대비 (5분봉 시리즈 적용)
    prev_1d = prev_close or (valid_quotes_1y[-2][1] if len(valid_quotes_1y) >= 2 else (quotes_5m[0] if quotes_5m else last_price))
    diff_1d = last_price - prev_1d
    rate_1d = (diff_1d / prev_1d * 100) if prev_1d else 0.0
    series_1d = quotes_5m if (quotes_5m and len(quotes_5m) >= 2) else [prev_1d, last_price]

    def _get_slice(days: int) -> list[float]:
        cutoff = (now - timedelta(days=days)).timestamp()
        sub = [v[1] for v in valid_quotes_1y if v[0] >= cutoff]
        if len(sub) < 2:
            sub = [v[1] for v in valid_quotes_1y[-min(len(valid_quotes_1y), max(2, days // 2)):]]
        return sub

    # 1W: 1주일 전 대비 (60분봉 시리즈 적용)
    if quotes_60m and len(quotes_60m) >= 2:
        base_1w = quotes_60m[0]
        diff_1w = last_price - base_1w
        rate_1w = (diff_1w / base_1w * 100) if base_1w else 0.0
        series_1w = quotes_60m
    else:
        sub_1w = _get_slice(7)
        base_1w = sub_1w[0] if sub_1w else last_price
        diff_1w = last_price - base_1w
        rate_1w = (diff_1w / base_1w * 100) if base_1w else 0.0
        series_1w = sub_1w

    # 1M (30일)
    sub_1m = _get_slice(30)
    base_1m = sub_1m[0] if sub_1m else last_price
    diff_1m = last_price - base_1m
    rate_1m = (diff_1m / base_1m * 100) if base_1m else 0.0

    # 3M (90일)
    sub_3m = _get_slice(90)
    base_3m = sub_3m[0] if sub_3m else last_price
    diff_3m = last_price - base_3m
    rate_3m = (diff_3m / base_3m * 100) if base_3m else 0.0

    # YTD (연초부터)
    sub_ytd = [v[1] for v in valid_quotes_1y if datetime.fromtimestamp(v[0]).year == cur_year]
    if len(sub_ytd) < 2:
        sub_ytd = _get_slice(60)
    base_ytd = sub_ytd[0] if sub_ytd else last_price
    diff_ytd = last_price - base_ytd
    rate_ytd = (diff_ytd / base_ytd * 100) if base_ytd else 0.0

    # 1Y (365일)
    sub_1y = [v[1] for v in valid_quotes_1y]
    base_1y = sub_1y[0] if sub_1y else last_price
    diff_1y = last_price - base_1y
    rate_1y = (diff_1y / base_1y * 100) if base_1y else 0.0

    # ── 월봉 기반 장기/전체 기간 (3Y, 5Y, 10Y, MAX) ─────────────────────────
    qm = quotes_monthly or []

    # 3Y: 최근 37개월
    sub_3y = qm[-37:] if len(qm) >= 2 else (sub_1y or [last_price, last_price])
    base_3y = sub_3y[0] if sub_3y else last_price
    diff_3y = last_price - base_3y
    rate_3y = (diff_3y / base_3y * 100) if base_3y else 0.0

    # 5Y: 최근 61개월
    sub_5y = qm[-61:] if len(qm) >= 2 else sub_3y
    base_5y = sub_5y[0] if sub_5y else last_price
    diff_5y = last_price - base_5y
    rate_5y = (diff_5y / base_5y * 100) if base_5y else 0.0

    # 10Y: 최근 121개월
    sub_10y = qm[-121:] if len(qm) >= 2 else sub_5y
    base_10y = sub_10y[0] if sub_10y else last_price
    diff_10y = last_price - base_10y
    rate_10y = (diff_10y / base_10y * 100) if base_10y else 0.0

    # MAX: 전체 월봉 (지수 전체 역사)
    sub_max = qm if len(qm) >= 2 else sub_10y
    base_max = sub_max[0] if sub_max else last_price
    diff_max = last_price - base_max
    rate_max = (diff_max / base_max * 100) if base_max else 0.0

    return {
        "1D": {"change": round(diff_1d, 2), "change_rate": round(rate_1d, 2), "series": series_1d},
        "1W": {"change": round(diff_1w, 2), "change_rate": round(rate_1w, 2), "series": series_1w},
        "1M": {"change": round(diff_1m, 2), "change_rate": round(rate_1m, 2), "series": sub_1m},
        "3M": {"change": round(diff_3m, 2), "change_rate": round(rate_3m, 2), "series": sub_3m},
        "YTD": {"change": round(diff_ytd, 2), "change_rate": round(rate_ytd, 2), "series": sub_ytd},
        "1Y": {"change": round(diff_1y, 2), "change_rate": round(rate_1y, 2), "series": sub_1y},
        "3Y": {"change": round(diff_3y, 2), "change_rate": round(rate_3y, 2), "series": sub_3y},
        "5Y": {"change": round(diff_5y, 2), "change_rate": round(rate_5y, 2), "series": sub_5y},
        "10Y": {"change": round(diff_10y, 2), "change_rate": round(rate_10y, 2), "series": sub_10y},
        "MAX": {"change": round(diff_max, 2), "change_rate": round(rate_max, 2), "series": sub_max},
        "ALL": {"change": round(diff_3y, 2), "change_rate": round(rate_3y, 2), "series": sub_3y},
    }


async def get_web_market_overview() -> dict[str, Any]:
    """
    코스피, 코스닥, S&P 500, 나스닥 종합 4개 지수 및 USD/KRW 환율에 대해
    1D(5분봉), 1W(60분봉), 1M/3M/YTD/1Y(일봉)를 비동기 병렬 조회하여 제공합니다.
    """
    indices = [
        {"symbol": "^KS11", "label": "코스피", "market": "KRX", "currency": "KRW"},
        {"symbol": "^KQ11", "label": "코스닥", "market": "KRX", "currency": "KRW"},
        {"symbol": "^GSPC", "label": "S&P", "market": "US", "currency": "USD"},
        {"symbol": "^IXIC", "label": "나스닥", "market": "US", "currency": "USD"},
        {"symbol": "^SOX", "label": "반도체", "market": "US", "currency": "USD"},
    ]
    symbols = [idx["symbol"] for idx in indices] + ["KRW=X"]

    async with httpx.AsyncClient() as client:
        tasks = []
        for sym in symbols:
            # 1) 당일 5분봉
            tasks.append(client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=5m&range=1d", headers=HEADERS, timeout=6.0))
            # 2) 1주 60분봉
            tasks.append(client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=60m&range=5d", headers=HEADERS, timeout=6.0))
            # 3) 1년 일봉
            tasks.append(client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=1y", headers=HEADERS, timeout=6.0))
            # 4) 전체 월봉 (3Y, 5Y, 10Y, MAX 장기용)
            tasks.append(client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1mo&range=max", headers=HEADERS, timeout=6.0))
        responses = await asyncio.gather(*tasks, return_exceptions=True)

    overview = []
    for i, idx in enumerate(indices):
        r_5m = responses[i * 4]
        r_60m = responses[i * 4 + 1]
        r_1y = responses[i * 4 + 2]
        r_max = responses[i * 4 + 3]

        q_5m = _extract_quotes(r_5m)
        q_60m = _extract_quotes(r_60m)
        q_max = _extract_quotes(r_max)

        price = 0.0
        prev_close = 0.0
        valid_quotes_1y: list[tuple[float, float]] = []
        if not isinstance(r_1y, Exception) and getattr(r_1y, "status_code", None) == 200:
            try:
                res_data = r_1y.json().get("chart", {}).get("result", [{}])[0]
                meta = res_data.get("meta", {})
                timestamps = res_data.get("timestamp", [])
                raw_quotes = res_data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                for t, q in zip(timestamps, raw_quotes):
                    if q is not None and float(q) > 0:
                        valid_quotes_1y.append((float(t), float(q)))
                price = float(meta.get("regularMarketPrice") or (valid_quotes_1y[-1][1] if valid_quotes_1y else 0.0))
                prev_close = float(meta.get("previousClose") or (valid_quotes_1y[-2][1] if len(valid_quotes_1y) >= 2 else price))
            except Exception:
                pass

        if not price and q_5m:
            price = q_5m[-1]

        periods = _calculate_market_periods(valid_quotes_1y, prev_close, price, quotes_5m=q_5m, quotes_60m=q_60m, quotes_monthly=q_max)
        stat_1d = periods.get("1D", {})

        overview.append({
            "symbol": idx["symbol"],
            "label": idx["label"],
            "name": idx["label"],
            "market": idx["market"],
            "currency": idx["currency"],
            "price": price,
            "current_price": price,
            "change": stat_1d.get("change", 0.0),
            "change_price": stat_1d.get("change", 0.0),
            "change_rate": stat_1d.get("change_rate", 0.0),
            "series": stat_1d.get("series", [price, price]),
            "periods": periods,
        })

    # USD/KRW 환율 처리 (마지막 심볼)
    fx_idx = len(indices)
    fx_5m = responses[fx_idx * 4]
    fx_60m = responses[fx_idx * 4 + 1]
    fx_1y = responses[fx_idx * 4 + 2]
    fx_max = responses[fx_idx * 4 + 3]

    fx_q_5m = _extract_quotes(fx_5m)
    fx_q_60m = _extract_quotes(fx_60m)
    fx_q_max = _extract_quotes(fx_max)

    fx_price = 1385.0
    fx_prev = 1385.0
    fx_valid_quotes_1y: list[tuple[float, float]] = []
    if not isinstance(fx_1y, Exception) and getattr(fx_1y, "status_code", None) == 200:
        try:
            res_data = fx_1y.json().get("chart", {}).get("result", [{}])[0]
            meta = res_data.get("meta", {})
            timestamps = res_data.get("timestamp", [])
            raw_quotes = res_data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
            for t, q in zip(timestamps, raw_quotes):
                if q is not None and float(q) > 0:
                    fx_valid_quotes_1y.append((float(t), float(q)))
            fx_price = float(meta.get("regularMarketPrice") or (fx_valid_quotes_1y[-1][1] if fx_valid_quotes_1y else 1385.0))
            fx_prev = float(meta.get("previousClose") or (fx_valid_quotes_1y[-2][1] if len(fx_valid_quotes_1y) >= 2 else fx_price))
        except Exception:
            pass

    if not fx_price and fx_q_5m:
        fx_price = fx_q_5m[-1]

    fx_periods = _calculate_market_periods(fx_valid_quotes_1y, fx_prev, fx_price, quotes_5m=fx_q_5m, quotes_60m=fx_q_60m, quotes_monthly=fx_q_max)
    fx_stat_1d = fx_periods.get("1D", {})

    return {
        "markets": overview,
        "exchange_rate": {
            "rate": fx_price,
            "change": fx_stat_1d.get("change", 0.0),
            "change_rate": fx_stat_1d.get("change_rate", 0.0),
            "series": fx_stat_1d.get("series", [fx_price, fx_price]),
            "periods": fx_periods,
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. 종목별 가격 & 거래량 인터랙티브 차트 데이터 조회
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_stock_chart_data(code: str, period: str = "3M") -> dict[str, Any]:
    """
    종목 코드와 기간(1D, 1W, 1M, 3M, YTD, 1Y)을 받아
    1D(5분봉), 1W(60분봉), 1M/3M/YTD/1Y(일봉) 데이터를 정확한 기간 크기로 반환합니다.
    """
    clean_code = str(code).strip().upper()
    is_kr = len(clean_code) == 6 and any(ch.isdigit() for ch in clean_code)

    candles: list[dict[str, Any]] = []
    stock_name = clean_code
    currency = "KRW" if is_kr else "USD"
    current_price = 0.0

    async with httpx.AsyncClient() as client:
        # 1) 국내 주식 1D(5분봉) 또는 1W(60분봉)
        if is_kr and period in ("1D", "1W"):
            interval = "5m" if period == "1D" else "60m"
            range_param = "1d" if period == "1D" else "5d"
            tasks = [
                client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_code}.KS?interval={interval}&range={range_param}", headers=HEADERS, timeout=5.0),
                client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_code}.KQ?interval={interval}&range={range_param}", headers=HEADERS, timeout=5.0)
            ]
            resps = await asyncio.gather(*tasks, return_exceptions=True)
            for r in resps:
                if not isinstance(r, Exception) and getattr(r, "status_code", None) == 200:
                    try:
                        res = r.json().get("chart", {}).get("result", [{}])[0]
                        meta = res.get("meta", {})
                        stock_name = meta.get("shortName") or clean_code
                        ts_list = res.get("timestamp", [])
                        q = res.get("indicators", {}).get("quote", [{}])[0]
                        opens = q.get("open", [])
                        highs = q.get("high", [])
                        lows = q.get("low", [])
                        closes = q.get("close", [])
                        volumes = q.get("volume", [])
                        valid = []
                        for i, ts in enumerate(ts_list):
                            c_val = closes[i] if i < len(closes) else None
                            if c_val is not None and float(c_val) > 0:
                                dt = datetime.fromtimestamp(ts, timezone(timedelta(hours=9)))
                                d_str = dt.strftime("%H:%M" if period == "1D" else "%m-%d %H:%M")
                                valid.append({
                                    "date": d_str,
                                    "open": float(opens[i]) if i < len(opens) and opens[i] is not None else float(c_val),
                                    "high": float(highs[i]) if i < len(highs) and highs[i] is not None else float(c_val),
                                    "low": float(lows[i]) if i < len(lows) and lows[i] is not None else float(c_val),
                                    "close": round(float(c_val), 2),
                                    "volume": int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
                                })
                        if valid:
                            candles = valid
                            current_price = candles[-1]["close"]
                            break
                    except Exception:
                        pass

        # 2) 해외 주식 1D(5분봉) 또는 1W(60분봉)
        elif not is_kr and period in ("1D", "1W"):
            interval = "5m" if period == "1D" else "60m"
            range_param = "1d" if period == "1D" else "5d"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_code}?interval={interval}&range={range_param}"
            try:
                r = await client.get(url, headers=HEADERS, timeout=6.0)
                if r.status_code == 200:
                    res = r.json().get("chart", {}).get("result", [{}])[0]
                    meta = res.get("meta", {})
                    stock_name = meta.get("shortName") or clean_code
                    ts_list = res.get("timestamp", [])
                    q = res.get("indicators", {}).get("quote", [{}])[0]
                    opens = q.get("open", [])
                    highs = q.get("high", [])
                    lows = q.get("low", [])
                    closes = q.get("close", [])
                    volumes = q.get("volume", [])
                    for i, ts in enumerate(ts_list):
                        c_val = closes[i] if i < len(closes) else None
                        if c_val is not None and float(c_val) > 0:
                            dt = datetime.fromtimestamp(ts, timezone(timedelta(hours=9)))
                            d_str = dt.strftime("%H:%M" if period == "1D" else "%m-%d %H:%M")
                            candles.append({
                                "date": d_str,
                                "open": float(opens[i]) if i < len(opens) and opens[i] is not None else float(c_val),
                                "high": float(highs[i]) if i < len(highs) and highs[i] is not None else float(c_val),
                                "low": float(lows[i]) if i < len(lows) and lows[i] is not None else float(c_val),
                                "close": round(float(c_val), 2),
                                "volume": int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
                            })
                    if candles:
                        current_price = candles[-1]["close"]
            except Exception:
                pass

        # 3) 1M, 3M, YTD, 1Y 또는 1D/1W fallback (일봉 데이터)
        if not candles:
            if is_kr:
                url = f"https://fchart.stock.naver.com/sise.nhn?symbol={clean_code}&timeframe=day&count=300&requestType=0"
                try:
                    resp = await client.get(url, headers=HEADERS, timeout=6.0)
                    if resp.status_code == 200:
                        root = ET.fromstring(resp.text)
                        items = root.findall(".//item")
                        for it in items:
                            raw = it.attrib.get("data", "")
                            parts = raw.split("|")
                            if len(parts) >= 6:
                                d_str = parts[0]
                                if len(d_str) == 8:
                                    d_str = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
                                candles.append({
                                    "date": d_str,
                                    "open": float(parts[1]),
                                    "high": float(parts[2]),
                                    "low": float(parts[3]),
                                    "close": float(parts[4]),
                                    "volume": int(parts[5]),
                                })
                        if candles:
                            current_price = candles[-1]["close"]
                except Exception:
                    pass
            else:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_code}?interval=1d&range=1y"
                try:
                    resp = await client.get(url, headers=HEADERS, timeout=7.0)
                    if resp.status_code == 200:
                        res_json = resp.json()
                        result = res_json.get("chart", {}).get("result", [{}])[0]
                        meta = result.get("meta", {})
                        stock_name = meta.get("shortName") or clean_code
                        current_price = float(meta.get("regularMarketPrice") or 0.0)

                        timestamps = result.get("timestamp", [])
                        quote = result.get("indicators", {}).get("quote", [{}])[0]
                        opens = quote.get("open", [])
                        highs = quote.get("high", [])
                        lows = quote.get("low", [])
                        closes = quote.get("close", [])
                        volumes = quote.get("volume", [])

                        for i, ts in enumerate(timestamps):
                            c_val = closes[i] if i < len(closes) else None
                            if c_val is not None and float(c_val) > 0:
                                d_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                                candles.append({
                                    "date": d_str,
                                    "open": float(opens[i]) if i < len(opens) and opens[i] is not None else float(c_val),
                                    "high": float(highs[i]) if i < len(highs) and highs[i] is not None else float(c_val),
                                    "low": float(lows[i]) if i < len(lows) and lows[i] is not None else float(c_val),
                                    "close": round(float(c_val), 2),
                                    "volume": int(volumes[i]) if i < len(volumes) and volumes[i] is not None else 0,
                                })
                except Exception:
                    pass

            # 일봉 캔들인 경우 기간별 슬라이싱
            if candles and period not in ("1D", "1W"):
                if period == "1M":
                    candles = candles[-22:] if len(candles) >= 22 else candles
                elif period == "3M":
                    candles = candles[-65:] if len(candles) >= 65 else candles
                elif period == "YTD":
                    now_year = datetime.now().year
                    ytd_str = f"{now_year}-01-01"
                    ytd_list = [c for c in candles if c.get("date", "") >= ytd_str]
                    candles = ytd_list if ytd_list else candles[-60:]
                elif period == "1Y":
                    candles = candles[-250:] if len(candles) >= 250 else candles
            elif candles and period in ("1D", "1W"):
                candles = candles[-5:] if period == "1W" else candles[-2:]

    return {
        "code": clean_code,
        "name": stock_name,
        "currency": currency,
        "period": period,
        "current_price": current_price,
        "candles": candles,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. 전종목 일괄 병렬 시세 갱신
# ─────────────────────────────────────────────────────────────────────────────

async def refresh_all_holdings_prices(holdings: list[dict[str, Any]]) -> dict[str, Any]:
    if not holdings:
        return {"prices": {}, "daily_changes": {}, "period_rates": {}, "fx_rate": 1385.0}

    async with httpx.AsyncClient() as client:
        fx_task = fetch_fx_rate_usd_krw(client)

        unique_codes = list({str(h.get("code", "")).strip() for h in holdings if h.get("code")})

        def is_kr_symbol(c: str) -> bool:
            return len(c) == 6 and any(ch.isdigit() for ch in c)

        kr_codes = [c for c in unique_codes if is_kr_symbol(c)]
        us_symbols = [c for c in unique_codes if not is_kr_symbol(c)]

        kr_tasks = {c: fetch_kr_stock_info(client, c) for c in kr_codes}
        us_tasks = {s: fetch_us_stock_info(client, s) for s in us_symbols}

        all_tasks = list(kr_tasks.values()) + list(us_tasks.values()) + [fx_task]
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        fx_rate = results[-1] if isinstance(results[-1], (int, float)) else 1385.0
        stock_results = results[:-1]

        code_to_info: dict[str, dict[str, Any]] = {}
        all_codes = list(kr_tasks.keys()) + list(us_tasks.keys())
        for code, res in zip(all_codes, stock_results):
            if isinstance(res, dict) and res.get("current_price", 0) > 0:
                code_to_info[code] = res

        # 국내 종목 기간별 캔들 병렬 조회
        kr_candle_tasks = {}
        for c in kr_codes:
            if c in code_to_info:
                p = code_to_info[c]["current_price"]
                kr_candle_tasks[c] = fetch_kr_stock_candles(client, c, p)

        if kr_candle_tasks:
            kr_candle_results = await asyncio.gather(*kr_candle_tasks.values(), return_exceptions=True)
            for c, c_res in zip(kr_candle_tasks.keys(), kr_candle_results):
                if isinstance(c_res, dict):
                    code_to_info[c]["period_changes"] = c_res

    prices_by_holding_id: dict[str, float] = {}
    daily_changes: dict[str, float] = {}
    period_rates: dict[str, dict[str, float]] = {}

    for h in holdings:
        c = str(h.get("code", "")).strip()
        h_id = h.get("id")
        if c in code_to_info:
            info = code_to_info[c]
            p = info["current_price"]
            if p > 0:
                prices_by_holding_id[h_id] = p
            daily_changes[c.upper()] = info.get("day_change_rate", 0.0)
            if "period_changes" in info:
                period_rates[c.upper()] = info["period_changes"]

    return {
        "prices": prices_by_holding_id,
        "daily_changes": daily_changes,
        "period_rates": period_rates,
        "fx_rate": fx_rate,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. 배당(분배금) 수집 및 1월~12월 캘린더 분석 엔진
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_us_dividend(client: httpx.AsyncClient, symbol: str) -> dict[str, Any]:
    """미국 주식/ETF의 1년치 배당 이력, 배당월, 주당 배당금 수집"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1y&events=div"
    try:
        resp = await client.get(url, headers=HEADERS, timeout=6.0)
        if resp.status_code != 200:
            return {"annual_div": 0.0, "payout_months": [], "div_yield": 0.0, "div_count": 0}
        data = resp.json()
        result = (data.get("chart", {}).get("result") or [{}])[0]
        meta = result.get("meta", {})
        price = _to_float(meta.get("regularMarketPrice"))
        divs = result.get("events", {}).get("dividends", {})
        if not divs:
            return {"annual_div": 0.0, "payout_months": [], "div_yield": 0.0, "div_count": 0}

        amounts = [float(d["amount"]) for d in divs.values() if "amount" in d]
        annual_div = round(sum(amounts), 4)
        div_count = len(amounts)

        months = set()
        for d in divs.values():
            if "date" in d:
                dt = datetime.fromtimestamp(d["date"], tz=timezone.utc)
                months.add(dt.month)

        payout_months = sorted(list(months))
        if not payout_months and div_count >= 10:
            payout_months = list(range(1, 13))
        elif not payout_months and div_count == 4:
            payout_months = [3, 6, 9, 12]

        div_yield = round((annual_div / price * 100), 2) if price > 0 else 0.0

        return {
            "annual_div": annual_div,
            "payout_months": payout_months,
            "div_yield": div_yield,
            "div_count": div_count,
        }
    except Exception:
        return {"annual_div": 0.0, "payout_months": [], "div_yield": 0.0, "div_count": 0}


async def fetch_kr_dividend(client: httpx.AsyncClient, code: str, current_price: float) -> dict[str, Any]:
    """국내 주식/ETF의 배당수익률 및 배당월 수집 (일반 주식 + 국내 상장 ETF TTM 배당수익률 지원)"""
    clean_code = str(code).strip().zfill(6)
    dvd_yield = 0.0
    dvd_amt = 0.0
    is_etf = False
    stock_name = ""

    # 1. 네이버 모바일 증권 API (ETF 배당수익률 TTM 수집)
    try:
        m_url = f"https://m.stock.naver.com/api/stock/{clean_code}/integration"
        m_resp = await client.get(m_url, headers=HEADERS, timeout=5.0)
        if m_resp.status_code == 200:
            m_data = m_resp.json()
            stock_name = m_data.get("stockName", "")
            if m_data.get("stockEndType") == "etf":
                is_etf = True
                etf_info = m_data.get("etfKeyIndicator") or {}
                etf_yield_raw = etf_info.get("dividendYieldTtm")
                if etf_yield_raw is not None:
                    dvd_yield = _to_float(etf_yield_raw)
    except Exception:
        pass

    # 2. 일반 주식이거나 ETF에서 배당수익률을 못 찾은 경우 PC 웹(main.naver) 파싱
    if dvd_yield == 0.0:
        url = f"https://finance.naver.com/item/main.naver?code={clean_code}"
        try:
            resp = await client.get(url, headers=HEADERS, timeout=6.0)
            if resp.status_code == 200:
                import re
                html = resp.text
                dvd_yield_match = re.findall(r"배당수익률.*?<em[^>]*>([^<]+)</em>", html, re.DOTALL)
                dvd_yield = _to_float(dvd_yield_match[0]) if dvd_yield_match else 0.0

                dvd_amt_match = re.findall(r"주당배당금.*?<td[^>]*>([^<]+)</td>", html, re.DOTALL)
                dvd_amt = _to_float(dvd_amt_match[0]) if dvd_amt_match else 0.0
        except Exception:
            pass

    if dvd_amt == 0.0 and dvd_yield > 0.0 and current_price > 0:
        dvd_amt = round(current_price * (dvd_yield / 100), 0)

    # 주요 분기배당 및 ETF 분배금 지급월 판별
    quarterly_codes = {"005930", "005935", "005380", "005385", "005387", "005490", "055550", "105560", "086790"}
    if clean_code in quarterly_codes:
        payout_months = [4, 5, 8, 11]  # 국내 분기배당 실제 지급월 (4월, 5월, 8월, 11월)
    elif is_etf and dvd_yield > 0:
        # 하나자산운용 1Q ETF (3, 6, 9, 12월 분기분배 추구)
        if "1q" in stock_name.lower():
            payout_months = [3, 6, 9, 12]
        elif any(w in stock_name for w in ["월배당", "커버드콜", "7%"]):
            payout_months = list(range(1, 13))
        else:
            payout_months = [1, 4, 7, 10]  # 국내 ETF 일반 분기분배월 (1, 4, 7, 10월)
    elif dvd_yield > 0:
        payout_months = [4]  # 12월 결산법인 일반 배당 지급월 (4월)
    else:
        payout_months = []

    return {
        "annual_div": dvd_amt,
        "payout_months": payout_months,
        "div_yield": dvd_yield,
        "div_count": len(payout_months),
    }


async def get_web_dividend_summary(holdings: list[dict[str, Any]], fx_rate: float = 1385.0) -> dict[str, Any]:
    """
    전체 보유 종목에 대해 실시간 배당 정보를 집계하고,
    1월부터 12월까지의 월별 예상 배당금 캘린더 데이터를 계산합니다.
    """
    if not holdings:
        return {
            "total_annual_dividend_krw": 0.0,
            "portfolio_yield": 0.0,
            "monthly_avg_dividend_krw": 0.0,
            "dividend_paying_count": 0,
            "monthly_schedule": {m: {"total_krw": 0.0, "items": []} for m in range(1, 13)},
            "holding_dividends": [],
        }

    async with httpx.AsyncClient(timeout=8.0) as client:
        # 중복 종목 코드 제거 후 병렬 조회
        unique_stocks = {}
        for h in holdings:
            code = str(h.get("code", "")).strip()
            if code and code not in unique_stocks:
                currency = str(h.get("currency", "KRW")).upper()
                curr_p = _to_float(h.get("current_price") or h.get("purchase_price"))
                unique_stocks[code] = (currency, curr_p)

        div_tasks = {}
        for code, (currency, curr_p) in unique_stocks.items():
            # 국내 종목 판별: 통화가 KRW이거나 6자리 단축코드(국내 신규 ETF 코드 0069M0, 0015B0, 0026S0 등 포함)
            is_kr = (currency == "KRW") or (len(code) == 6 and not code.isalpha())
            if is_kr:
                div_tasks[code] = fetch_kr_dividend(client, code, curr_p)
            else:
                div_tasks[code] = fetch_us_dividend(client, code)

        results = await asyncio.gather(*div_tasks.values(), return_exceptions=True)
        div_map = {}
        for code, res in zip(div_tasks.keys(), results):
            if isinstance(res, dict):
                div_map[code] = res
            else:
                div_map[code] = {"annual_div": 0.0, "payout_months": [], "div_yield": 0.0, "div_count": 0}

    total_annual_krw = 0.0
    total_eval_krw = 0.0
    dividend_paying_count = 0
    monthly_schedule = {m: {"month": m, "total_krw": 0.0, "items": []} for m in range(1, 13)}
    holding_dividends = []

    for h in holdings:
        code = str(h.get("code", "")).strip()
        name = str(h.get("name", code))
        qty = _to_float(h.get("quantity", 0))
        currency = str(h.get("currency", "KRW")).upper()
        curr_p = _to_float(h.get("current_price") or h.get("purchase_price"))
        market_val_krw = qty * curr_p * (fx_rate if currency == "USD" else 1.0)
        total_eval_krw += market_val_krw

        d_info = div_map.get(code, {"annual_div": 0.0, "payout_months": [], "div_yield": 0.0, "div_count": 0})
        annual_div_per_share = d_info.get("annual_div", 0.0)
        div_yield = d_info.get("div_yield", 0.0)
        payout_months = d_info.get("payout_months", [])

        annual_payout_orig = qty * annual_div_per_share
        annual_payout_krw = annual_payout_orig * (fx_rate if currency == "USD" else 1.0)

        if annual_payout_krw > 0:
            dividend_paying_count += 1
            total_annual_krw += annual_payout_krw

            # 월별 분배
            if payout_months:
                per_month_krw = annual_payout_krw / len(payout_months)
                per_month_orig = annual_payout_orig / len(payout_months)
                for m in payout_months:
                    if 1 <= m <= 12:
                        monthly_schedule[m]["total_krw"] += per_month_krw
                        monthly_schedule[m]["items"].append({
                            "code": code,
                            "name": name,
                            "quantity": qty,
                            "currency": currency,
                            "payout_krw": round(per_month_krw, 0),
                            "payout_orig": round(per_month_orig, 2),
                            "div_yield": div_yield,
                        })

        holding_dividends.append({
            "code": code,
            "name": name,
            "quantity": qty,
            "currency": currency,
            "annual_div_per_share": annual_div_per_share,
            "div_yield": div_yield,
            "annual_payout_krw": round(annual_payout_krw, 0),
            "annual_payout_orig": round(annual_payout_orig, 2),
            "payout_months": payout_months,
        })

    portfolio_yield = round((total_annual_krw / total_eval_krw * 100), 2) if total_eval_krw > 0 else 0.0
    monthly_avg_krw = round(total_annual_krw / 12, 0)

    # 월별 일정 정렬
    monthly_list = []
    for m in range(1, 13):
        item = monthly_schedule[m]
        item["total_krw"] = round(item["total_krw"], 0)
        item["items"].sort(key=lambda x: x["payout_krw"], reverse=True)
        monthly_list.append(item)

    return {
        "total_annual_dividend_krw": round(total_annual_krw, 0),
        "portfolio_yield": portfolio_yield,
        "monthly_avg_dividend_krw": monthly_avg_krw,
        "dividend_paying_count": dividend_paying_count,
        "monthly_schedule": monthly_list,
        "holding_dividends": sorted(holding_dividends, key=lambda x: x["annual_payout_krw"], reverse=True),
    }

