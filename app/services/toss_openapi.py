from __future__ import annotations

import asyncio
import calendar
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

ROOT_DIR = Path(__file__).resolve().parents[2]


class TossOpenAPIError(RuntimeError):
    pass


def as_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Token:
    value: str
    expires_at: float


class TossOpenAPI:
    """토스증권 Open API의 읽기 전용 계좌·보유종목 클라이언트."""

    def __init__(self, username: str = "sagesaint") -> None:
        self.username = username
        from app.services.user_openapi import get_user_openapi_config
        cfg = get_user_openapi_config(username).get("toss", {})

        self.base_url = os.getenv("TOSSINVEST_OPENAPI_BASE_URL", "https://openapi.tossinvest.com").rstrip("/")
        self.client_id = cfg.get("app_key", "")
        self.client_secret = cfg.get("app_secret", "")
        self._token: Token | None = None
        self.last_accounts: list[dict[str, Any]] = []

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if not self.configured:
            raise TossOpenAPIError("토스증권 OpenAPI 키가 설정되지 않았습니다. 상단 [OpenAPI] 버튼에서 Client ID와 Secret을 먼저 등록하세요.")
        if self._token and self._token.expires_at > time.time() + 60:
            return self._token.value
        response = await client.post(
            f"{self.base_url}/oauth2/token",
            data={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self._raise_for_response(response)
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise TossOpenAPIError("토스증권 토큰 응답에 access_token이 없습니다.")
        self._token = Token(token, time.time() + as_float(payload.get("expires_in", 3600)))
        return token

    @staticmethod
    def _raise_for_response(response: httpx.Response) -> None:
        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            if isinstance(payload, dict):
                error_obj = payload.get("error")
                if isinstance(error_obj, dict):
                    detail = error_obj.get("message") or payload.get("error_description") or payload
                else:
                    detail = error_obj or payload.get("error_description") or payload
            else:
                detail = payload
            raise TossOpenAPIError(
                f"토스증권 OpenAPI 요청 실패 ({response.status_code}) [{response.request.method} {response.request.url}]: {detail}"
            )

    async def _get(self, path: str, params: dict[str, Any] | None = None, account_seq: int | None = None) -> Any:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            if account_seq is not None:
                headers["X-Tossinvest-Account"] = str(account_seq)
            response = await client.get(f"{self.base_url}{path}", params=params, headers=headers)
            self._raise_for_response(response)
            payload = response.json()
        if "result" not in payload:
            raise TossOpenAPIError("토스증권 API 응답에 result가 없습니다.")
        return payload["result"]

    async def sync_holdings(self) -> list[dict[str, Any]]:
        accounts = await self._get("/api/v1/accounts")
        if isinstance(accounts, dict):
            accounts = accounts.get("items") or accounts.get("accounts") or []
        self.last_accounts = accounts
        records: list[dict[str, Any]] = []
        for account in accounts:
            account_seq = account.get("accountSeq")
            if account_seq is None:
                continue
            overview = await self._get("/api/v1/holdings", account_seq=int(account_seq))
            if isinstance(overview, list):
                overview = {"items": overview}
            account_no = str(account.get("accountNo", ""))
            account_name = f"토스증권 계좌 {account_no[-4:]}" if account_no else f"토스증권 계좌 {account_seq}"
            for item in overview.get("items", []):
                country = item.get("marketCountry", "")
                records.append({
                    "account_key": str(account_seq),
                    "account_name": account_name,
                    "code": item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "quantity": as_float(item.get("quantity")),
                    "avg_price": as_float(item.get("averagePurchasePrice")),
                    "current_price": as_float(item.get("lastPrice")),
                    "currency": item.get("currency", "KRW"),
                    "market": "KRX" if country == "KR" else "TOSS_US",
                })
        return [record for record in records if record["code"] and record["quantity"] > 0]

    async def get_buying_power(self, account_seq: int) -> dict[str, float]:
        res: dict[str, float] = {"KRW": 0.0, "USD": 0.0}
        for cur in ["KRW", "USD"]:
            try:
                data = await self._get("/api/v1/buying-power", params={"currency": cur}, account_seq=account_seq)
                if isinstance(data, dict):
                    res[cur] = as_float(data.get("cashBuyingPower") or data.get("orderableAmount") or data.get("buyingPower") or 0.0)
            except Exception:
                pass
        return res

    async def get_exchange_rate(self, base_currency: str, quote_currency: str = "KRW") -> dict[str, Any]:
        """토스증권의 가장 최근 기준환율을 가져온다."""
        base_currency = base_currency.upper()
        quote_currency = quote_currency.upper()
        result = await self._get(
            "/api/v1/exchange-rate",
            params={"baseCurrency": base_currency, "quoteCurrency": quote_currency},
        )
        rate = as_float(result.get("rate"))
        if rate <= 0:
            raise TossOpenAPIError(f"토스증권 환율 응답에 유효한 {base_currency}/{quote_currency} 환율이 없습니다.")
        return {
            "rate": rate,
            "mid_rate": as_float(result.get("midRate")),
            "valid_from": result.get("validFrom"),
            "valid_until": result.get("validUntil"),
        }

    async def get_usd_krw_rate(self) -> dict[str, Any]:
        """기존 호출부와의 호환성을 위한 USD/KRW 편의 메서드."""
        return await self.get_exchange_rate("USD", "KRW")

    @staticmethod
    def _daily_change(candles: list[dict[str, Any]]) -> float | None:
        if len(candles) < 2:
            return None
        latest = as_float(candles[0].get("closePrice"))
        previous = as_float(candles[1].get("closePrice"))
        if previous <= 0:
            return None
        return (latest - previous) / previous * 100

    @staticmethod
    def _sparkline(candles: list[dict[str, Any]]) -> list[float]:
        return [as_float(item.get("closePrice")) for item in reversed(candles) if as_float(item.get("closePrice")) > 0]

    @staticmethod
    async def _fetch_us_index(ticker: str, label: str, note: str) -> dict[str, Any] | None:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=2m&range=1d"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    res = r.json().get("chart", {}).get("result", [])[0]
                    meta = res.get("meta", {})
                    price = as_float(meta.get("regularMarketPrice"))
                    prev = as_float(meta.get("previousClose") or meta.get("chartPreviousClose"))
                    change = (price - prev) if prev > 0 else 0.0
                    change_rate = (change / prev * 100) if prev > 0 else 0.0
                    raw_quotes = res.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                    series = [round(as_float(q), 2) for q in raw_quotes if q is not None and as_float(q) > 0]
                    if len(series) > 60:
                        step = max(1, len(series) // 60)
                        series = series[::step]
                    if price > 0:
                        return {
                            "symbol": "NASDAQ" if "IXIC" in ticker else "S&P 500",
                            "label": label,
                            "note": note,
                            "price": round(price, 2),
                            "currency": "USD",
                            "change": round(change, 2),
                            "change_rate": round(change_rate, 2),
                            "series": series,
                            "updated_at": meta.get("regularMarketTime"),
                        }
        except Exception:
            pass
        return None

    async def get_market_overview(self) -> list[dict[str, Any]]:
        """대시보드 상단에 표시할 주요 시장 지표(나스닥, S&P 500, 코스피)를 조회한다."""
        # 1. 미국 나스닥 및 S&P 500 공식 지수 비동기 조회
        us_tasks = [
            self._fetch_us_index("%5EIXIC", "나스닥", "나스닥 종합 지수"),
            self._fetch_us_index("%5EGSPC", "S&P 500", "S&P 500 지수"),
        ]
        us_results = await asyncio.gather(*us_tasks)
        nasdaq_idx, sp500_idx = us_results[0], us_results[1]

        # 2. 토스 증권 시장지표(코스피) 및 ETF 폴백 조회
        indicator_prices = await self._get("/api/v1/market-indicators/prices", params={"symbols": "KOSPI"})
        stock_prices = await self._get("/api/v1/prices", params={"symbols": "QQQ,SPY"})

        async def candle_pair(path: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
            daily = await self._get(path, params={**params, "interval": "1d", "count": 2})
            try:
                intraday = await self._get(path, params={**params, "interval": "1m", "count": 60})
            except TossOpenAPIError:
                intraday = daily
            if len(intraday.get("candles", [])) < 3:
                intraday = daily
            return daily, intraday

        qqq_daily, qqq_intraday = await candle_pair("/api/v1/candles", {"symbol": "QQQ"})
        spy_daily, spy_intraday = await candle_pair("/api/v1/candles", {"symbol": "SPY"})
        kospi_daily, kospi_intraday = await candle_pair("/api/v1/market-indicators/KOSPI/candles", {})

        indicator_by_symbol = {str(item.get("symbol", "")).upper(): item for item in indicator_prices}
        price_by_symbol = {str(item.get("symbol", "")).upper(): item for item in stock_prices}

        # 코스피 지표 계산
        k_candles_d = kospi_daily.get("candles", [])
        k_latest = as_float(k_candles_d[0].get("closePrice")) if k_candles_d else as_float(indicator_by_symbol.get("KOSPI", {}).get("lastPrice"))
        k_prev = as_float(k_candles_d[1].get("closePrice")) if len(k_candles_d) >= 2 else 0.0
        k_chg = (k_latest - k_prev) if k_prev > 0 else 0.0
        k_rate = (k_chg / k_prev * 100) if k_prev > 0 else 0.0
        k_series = self._sparkline(kospi_intraday.get("candles", [])) or self._sparkline(k_candles_d)

        kospi_row = {
            "symbol": "KOSPI",
            "label": "코스피",
            "note": "국내 대표 지수",
            "price": k_latest,
            "currency": "KRW",
            "change": round(k_chg, 2),
            "change_rate": round(k_rate, 2),
            "series": k_series,
            "updated_at": indicator_by_symbol.get("KOSPI", {}).get("timestamp"),
        }

        # QQQ / SPY 폴백 구성
        def fallback_item(sym, label, note, quote, d_page, i_page):
            c_d = d_page.get("candles", [])
            latest = as_float(c_d[0].get("closePrice")) if c_d else as_float(quote.get("lastPrice"))
            prev = as_float(c_d[1].get("closePrice")) if len(c_d) >= 2 else 0.0
            chg = (latest - prev) if prev > 0 else 0.0
            rate = (chg / prev * 100) if prev > 0 else 0.0
            ser = self._sparkline(i_page.get("candles", [])) or self._sparkline(c_d)
            return {
                "symbol": sym,
                "label": label,
                "note": note,
                "price": latest,
                "currency": "USD",
                "change": round(chg, 2),
                "change_rate": round(rate, 2),
                "series": ser,
                "updated_at": quote.get("timestamp"),
            }

        final_nasdaq = nasdaq_idx or fallback_item("QQQ", "나스닥", "나스닥 100 (QQQ)", price_by_symbol.get("QQQ", {}), qqq_daily, qqq_intraday)
        final_sp500 = sp500_idx or fallback_item("SPY", "S&P 500", "S&P 500 (SPY)", price_by_symbol.get("SPY", {}), spy_daily, spy_intraday)

        return [final_nasdaq, final_sp500, kospi_row]

    async def refresh_prices(self, holdings: list[dict[str, Any]]) -> tuple[dict[str, float], list[str]]:
        symbol_to_ids: dict[str, list[str]] = {}
        for holding in holdings:
            symbol = str(holding.get("code", "")).upper()
            if symbol:
                symbol_to_ids.setdefault(symbol, []).append(holding["id"])
        prices: dict[str, float] = {}
        warnings: list[str] = []
        symbols = list(symbol_to_ids)
        for start in range(0, len(symbols), 200):
            batch = symbols[start : start + 200]
            try:
                items = await self._get("/api/v1/prices", params={"symbols": ",".join(batch)})
            except TossOpenAPIError as exc:
                warnings.append(str(exc))
                continue
            found = set()
            for item in items:
                symbol = str(item.get("symbol", "")).upper()
                price = as_float(item.get("lastPrice"))
                if symbol and price > 0:
                    found.add(symbol)
                    for holding_id in symbol_to_ids.get(symbol, []):
                        prices[holding_id] = price
            for symbol in set(batch) - found:
                warnings.append(f"{symbol}: 토스증권 시세 응답이 없습니다.")
        return prices, warnings

    async def get_multi_period_changes(self, symbols: list[str]) -> dict[str, dict[str, float]]:
        """종목별 다중 기간(1D, 1W, 1M, YTD, 1Y) 등락률(%)을 조회하고 캐싱한다."""
        if not symbols or not self.configured:
            return {}
        clean_symbols = list({s.strip().upper() for s in symbols if s.strip()})
        results: dict[str, dict[str, float]] = {}
        sem = asyncio.Semaphore(4)
        current_year = datetime.now().year
        cache_file = ROOT_DIR / "data" / "period_rates.json"

        # 1. 실시간 현재가 수집
        try:
            stock_prices_items = await self._get("/api/v1/prices", params={"symbols": ",".join(clean_symbols)})
            last_prices = {item["symbol"].upper(): as_float(item.get("lastPrice")) for item in stock_prices_items if item.get("symbol")}
        except Exception:
            last_prices = {}

        # 2. 토스 공식 랭킹 API에서 1D changeRate 수집
        kr_rank_rates: dict[str, float] = {}
        try:
            kr_ranks = await self._get("/api/v1/rankings", params={"type": "MARKET_TRADING_VOLUME", "marketCountry": "KR", "duration": "1d", "count": 100})
            for r in kr_ranks.get("rankings", []):
                sym = str(r.get("symbol", "")).upper()
                if sym in clean_symbols and r.get("price", {}).get("changeRate") is not None:
                    kr_rank_rates[sym] = round(as_float(r["price"]["changeRate"]) * 100, 2)
        except Exception:
            pass

        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            async def process_symbol(sym: str):
                is_kr = sym.isalnum() and (len(sym) == 6 or sym[:5].isdigit())
                r_1d = kr_rank_rates.get(sym)

                # 일봉 캔들 조회 (최대 200봉)
                for attempt in range(4):
                    try:
                        async with sem:
                            r = await client.get(f"{self.base_url}/api/v1/candles", params={"symbol": sym, "interval": "1d", "count": 200}, headers=headers)
                            if r.status_code == 200:
                                candles = r.json().get("result", {}).get("candles", [])
                                if candles:
                                    last = last_prices.get(sym, as_float(candles[0].get("closePrice")))
                                    if r_1d is None:
                                        p_1d = as_float(candles[1].get("closePrice")) if len(candles) >= 2 else last
                                        r_1d = round((last - p_1d) / p_1d * 100, 2) if p_1d > 0 else 0.0

                                    # 날짜 기준: 7일 전, 1달 전, 1년 전, YTD
                                    now = datetime.now()
                                    d_1w = (now - timedelta(days=7)).strftime("%Y%m%d")

                                    m_year = now.year
                                    m_month = now.month - 1
                                    if m_month == 0:
                                        m_month = 12
                                        m_year -= 1
                                    max_day_1m = calendar.monthrange(m_year, m_month)[1]
                                    d_1m = f"{m_year:04d}{m_month:02d}{min(now.day, max_day_1m):02d}"

                                    y_year = now.year - 1
                                    max_day_1y = calendar.monthrange(y_year, now.month)[1]
                                    d_1y = f"{y_year:04d}{now.month:02d}{min(now.day, max_day_1y):02d}"
                                    d_ytd = f"{now.year - 1}1231"

                                    def find_toss_close(target_ymd: str) -> float:
                                        for c in candles:
                                            ts_str = str(c.get("timestamp", "")).replace("-", "")[:8]
                                            if ts_str and ts_str <= target_ymd:
                                                return as_float(c.get("closePrice"))
                                        return as_float(candles[-1].get("closePrice"))

                                    p_1w = find_toss_close(d_1w)
                                    r_1w = round((last - p_1w) / p_1w * 100, 2) if p_1w > 0 else 0.0

                                    p_1m = find_toss_close(d_1m)
                                    r_1m = round((last - p_1m) / p_1m * 100, 2) if p_1m > 0 else 0.0

                                    p_ytd = find_toss_close(d_ytd)
                                    r_ytd = round((last - p_ytd) / p_ytd * 100, 2) if p_ytd > 0 else 0.0

                                    p_1y = find_toss_close(d_1y)
                                    r_1y = round((last - p_1y) / p_1y * 100, 2) if p_1y > 0 else 0.0

                                    results[sym] = {
                                        "1D": r_1d,
                                        "1W": r_1w,
                                        "1M": r_1m,
                                        "YTD": r_ytd,
                                        "1Y": r_1y,
                                    }
                                    return
                            elif r.status_code == 429:
                                await asyncio.sleep(0.3 * (attempt + 1))
                                continue
                    except Exception:
                        await asyncio.sleep(0.2)
                    await asyncio.sleep(0.04)

            tasks = [process_symbol(s) for s in clean_symbols]
            await asyncio.gather(*tasks, return_exceptions=True)

        if results:
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
        return results

    async def get_daily_changes(self, symbols: list[str]) -> dict[str, float]:
        """종목별 전일 대비 등락률(%)을 조회한다."""
        multi = await self.get_multi_period_changes(symbols)
        return {s: data["1D"] for s, data in multi.items() if "1D" in data}

        sem = asyncio.Semaphore(4)
        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}

            async def fetch_one(sym: str):
                is_kr = sym.isalnum() and (len(sym) == 6 or sym[:5].isdigit())
                for attempt in range(4):
                    async with sem:
                        if is_kr:
                            try:
                                r = await client.get(
                                    f"{self.base_url}/api/v1/price-limits",
                                    params={"symbol": sym},
                                    headers=headers,
                                )
                                if r.status_code == 200:
                                    lim = r.json().get("result", {})
                                    u = as_float(lim.get("upperLimitPrice"))
                                    l = as_float(lim.get("lowerLimitPrice"))
                                    if u > 0 and l > 0:
                                        base = (u + l) / 2
                                        last = last_prices.get(sym, 0)
                                        if base > 0 and last > 0:
                                            res[sym] = round((last - base) / base * 100, 2)
                                            return
                            except Exception:
                                pass

                        try:
                            r = await client.get(
                                f"{self.base_url}/api/v1/candles",
                                params={"symbol": sym, "interval": "1d", "count": 2},
                                headers=headers,
                            )
                            if r.status_code == 200:
                                payload = r.json().get("result", {})
                                candles = payload.get("candles", [])
                                if len(candles) >= 2:
                                    c0 = as_float(candles[0].get("closePrice"))
                                    c1 = as_float(candles[1].get("closePrice"))
                                    last = last_prices.get(sym, c0)
                                    if c1 > 0:
                                        res[sym] = round((last - c1) / c1 * 100, 2)
                                        return
                                elif len(candles) == 1:
                                    c0 = as_float(candles[0].get("closePrice"))
                                    o0 = as_float(candles[0].get("openPrice"))
                                    if o0 > 0:
                                        res[sym] = round((c0 - o0) / o0 * 100, 2)
                                        return
                            elif r.status_code == 429:
                                await asyncio.sleep(0.3 * (attempt + 1))
                                continue
                        except Exception:
                            await asyncio.sleep(0.2)
                    await asyncio.sleep(0.04)

            tasks = [fetch_one(s) for s in remaining]
            await asyncio.gather(*tasks, return_exceptions=True)
        return res
