from __future__ import annotations

import csv
import io
import re
import urllib.request
from typing import Any

# 기본 구글 스프레드시트 웹 게시 CSV URL (gid=1737697913: 📈주식현황상세)
DEFAULT_GOOGLE_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vTEAJjUsiTqdPRVPMkYnb6qFi-HeejyZOIm5l-2SHvcML54c0ZArUrOiGmRVZTbfhPB_BmvF5Q8oYGv/pub?gid=1737697913&single=true&output=csv"
)


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    s = str(val).replace(",", "").replace("$", "").replace("₩", "").replace("▲", "").replace("▼", "").replace("(", "").replace(")", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def fetch_google_sheet_data(url: str = DEFAULT_GOOGLE_SHEET_CSV_URL) -> dict[str, Any]:
    """
    구글 스프레드시트 웹 발행 CSV 데이터를 파싱하여
    환율(USD/KRW) 및 종목별 현재가/정보를 딕셔너리로 반환합니다.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        text = resp.read().decode("utf-8")

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        return {"fx_usd_krw": 0.0, "quotes": {}}

    # 1. 환율 추출 (Row 0의 평균/현재 환율 위치 등)
    fx_rate = 0.0
    for cell in rows[0]:
        val = _to_float(cell)
        if 1000.0 <= val <= 2500.0:
            fx_rate = val
            break

    quotes: dict[str, dict[str, Any]] = {}

    # 2. 종목 정보 파싱 (Row 2부터)
    # Row 1 헤더: ['시장', '종목명', '섹터', '코드', '보유량', '매수평단가', '매수총액($)', '매수평단가(원)', '매수총액(원)', '평균환율', '현재가', '', '', '평가총액', ...]
    for row in rows[2:]:
        if len(row) < 12:
            continue
        market = row[0].strip() if len(row) > 0 else ""
        name = row[1].strip() if len(row) > 1 else ""
        code = row[3].strip().upper() if len(row) > 3 else ""

        # 현재가 파싱: row[11]이 실제 수치 (예: '368.45', '31,750.00' 등)
        price_str = row[11] if len(row) > 11 else row[10]
        current_price = _to_float(price_str)

        if not code or current_price <= 0:
            continue

        # 등락 표시 파싱 (예: '(▲ 173.11)')
        change_str = row[12] if len(row) > 12 else ""
        diff_val = _to_float(change_str)
        if "▼" in change_str:
            diff_val = -diff_val

        quotes[code] = {
            "code": code,
            "name": name,
            "market": market,
            "current_price": current_price,
            "currency": "USD" if market == "미국" else "KRW",
            "diff": diff_val,
        }

    return {
        "fx_usd_krw": fx_rate,
        "quotes": quotes,
    }


def refresh_prices_from_google_sheet(holdings: list[dict[str, Any]]) -> tuple[dict[str, float], list[dict[str, Any]], float]:
    """
    보유 종목 리스트를 받아 구글 시트에서 시세를 매칭하여
    (매칭된 holding_id: 가격 딕셔너리, 미매칭 종목 리스트, 환율)을 반환합니다.
    """
    data = fetch_google_sheet_data()
    quotes = data.get("quotes", {})
    fx_rate = data.get("fx_usd_krw", 0.0)

    matched_prices: dict[str, float] = {}
    missing_holdings: list[dict[str, Any]] = []

    for h in holdings:
        code = str(h.get("code") or "").strip().upper()
        h_id = h.get("id")
        if code and code in quotes:
            matched_prices[h_id] = quotes[code]["current_price"]
        else:
            missing_holdings.append(h)

    return matched_prices, missing_holdings, fx_rate
