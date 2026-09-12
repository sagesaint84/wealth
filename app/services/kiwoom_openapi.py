from __future__ import annotations

import asyncio
import calendar
import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from app.services.network_policy import require_external_network


class KiwoomOpenAPIError(RuntimeError):
    pass


KIWOOM_REALIZED_MAX_PAGES = 10
KIWOOM_DOMESTIC_SAFE_CHUNK_MONTHS = 3
_KIWOOM_NO_DATA_MARKER = "_kiwoom_ust21530_no_data"
_UST21530_NO_DATA_CODE = Decimal("20")
_UST21530_NO_DATA_SUBCODE = "571758"
_UST21530_NO_DATA_MESSAGE = "조회내역이 없습니다"


def compute_kiwoom_account_key(acct_no: str, secret: str | None = None) -> str:
    """Return an opaque deterministic identity without exposing the account number."""
    normalized = str(acct_no or "").replace("-", "").strip()
    if not normalized:
        raise KiwoomOpenAPIError("키움증권 계좌 식별자가 없습니다.")
    key = secret if secret is not None else os.getenv("DASHBOARD_SECRET_KEY", "").strip()
    if not key and os.getenv("WEALTH_ENV", "").strip().lower() == "test":
        key = os.getenv("WEALTH_TEST_SIGNING_SECRET", "").strip()
    if not key:
        raise KiwoomOpenAPIError("키움증권 계좌 식별에 필요한 서버 키가 없습니다.")
    return hmac.new(key.encode("utf-8"), f"kiwoom:{normalized}".encode("utf-8"), hashlib.sha256).hexdigest()


def mask_kiwoom_account(acct_no: str) -> str:
    normalized = str(acct_no or "").replace("-", "").strip()
    if not normalized:
        return ""
    if len(normalized) <= 4:
        return "****"
    return "*" * (len(normalized) - 4) + normalized[-4:]


def as_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Token:
    value: str
    expires_at: float


class KiwoomOpenAPI:
    """키움증권 공식 REST API의 국내 잔고 읽기 전용 클라이언트."""

    _ALLOWED_HOSTS = {"api.kiwoom.com", "mockapi.kiwoom.com"}

    def __init__(self, username: str = "sagesaint") -> None:
        self.username = username
        from app.services.user_openapi import get_user_openapi_config
        cfg = get_user_openapi_config(username).get("kiwoom", {})
        self.base_url = os.getenv("KIWOOM_BASE_URL", "https://api.kiwoom.com").rstrip("/")
        self.app_key = cfg.get("app_key", "").strip()
        self.app_secret = cfg.get("app_secret", "").strip()
        # Legacy UI 값은 호환성 때문에 읽지만, 키움 계좌 API 요청에는 사용하지 않는다.
        self.account_no = cfg.get("account_no", "").replace("-", "").strip()
        self._validate_url(self.base_url, "KIWOOM_BASE_URL")
        from app.services.user_manager import get_user_data_dir
        user_dir = get_user_data_dir(username)
        user_dir.mkdir(parents=True, exist_ok=True)
        self.token_cache_file = user_dir / "kiwoom_token_cache.json"
        self._token: Token | None = None
        self.last_accounts: list[dict[str, Any]] = []
        self.account_cash: dict[str, dict[str, float]] = {}

    @staticmethod
    def _validate_url(value: str, setting: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in KiwoomOpenAPI._ALLOWED_HOSTS:
            raise KiwoomOpenAPIError(f"{setting}은 키움증권 공식 HTTPS 주소여야 합니다.")

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    def _parse_account_no(self) -> tuple[str, str]:
        """기존 설정 호환용 parser. 실제 키움 API request에는 사용하지 않는다."""
        if len(self.account_no) == 10 and self.account_no.isdigit():
            return self.account_no[:8], self.account_no[8:]
        if len(self.account_no) == 8 and self.account_no.isdigit():
            return self.account_no, ""
        return "", ""

    async def _access_token(self, client: httpx.AsyncClient, force_refresh: bool = False) -> str:
        if not self.configured:
            raise KiwoomOpenAPIError("키움증권 AppKey 또는 AppSecret이 설정되지 않았습니다.")
        if not force_refresh:
            if self._token and self._token.expires_at > time.time() + 60:
                return self._token.value
            try:
                cached = json.loads(self.token_cache_file.read_text(encoding="utf-8"))
                if (cached.get("app_key_prefix") == self.app_key[:8]
                        and float(cached.get("expires_at", 0)) > time.time() + 60
                        and cached.get("access_token")):
                    self._token = Token(str(cached["access_token"]), float(cached["expires_at"]))
                    return self._token.value
            except (OSError, ValueError, TypeError):
                pass
        self.token_cache_file.unlink(missing_ok=True)
        response = await client.post(
            f"{self.base_url}/oauth2/token",
            json={"grant_type": "client_credentials", "appkey": self.app_key, "secretkey": self.app_secret},
            headers={"Content-Type": "application/json;charset=UTF-8"},
        )
        self._raise_for_response(response)
        try:
            body = response.json()
        except ValueError as exc:
            raise KiwoomOpenAPIError("키움증권 토큰 응답이 올바른 JSON이 아닙니다.") from exc
        token = body.get("token") or body.get("access_token")
        if not token:
            raise KiwoomOpenAPIError("키움증권 토큰 응답에 token이 없습니다.")
        self._token = Token(str(token), time.time() + as_float(body.get("expires_in", 86400)))
        try:
            self.token_cache_file.write_text(json.dumps({
                "app_key_prefix": self.app_key[:8], "access_token": token,
                "expires_at": self._token.expires_at,
            }), encoding="utf-8")
        except (OSError, ValueError, TypeError):
            pass
        return str(token)

    @staticmethod
    def _raise_for_response(response: httpx.Response) -> None:
        if response.is_error:
            raise KiwoomOpenAPIError(f"키움증권 API HTTP 오류 ({response.status_code})")

    async def _post_api(self, client: httpx.AsyncClient, token: str, api_id: str,
                        body: dict[str, Any], *, cont_yn: str = "", next_key: str = "") -> tuple[dict[str, Any], str, str]:
        headers = {"Content-Type": "application/json;charset=UTF-8", "authorization": f"Bearer {token}", "api-id": api_id}
        if cont_yn:
            headers["cont-yn"] = cont_yn
        if next_key:
            headers["next-key"] = next_key
        response = await client.post(f"{self.base_url}/api/dostk/acnt", headers=headers, json=body)
        self._raise_for_response(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise KiwoomOpenAPIError("키움증권 API 응답이 올바른 JSON이 아닙니다.") from exc
        if not isinstance(payload, dict):
            raise KiwoomOpenAPIError("키움증권 API 응답 형식이 올바르지 않습니다.")
        if "return_code" not in payload:
            raise KiwoomOpenAPIError("키움증권 API 응답에 업무 결과 코드가 없습니다.")
        if as_float(payload.get("return_code", 0)) != 0:
            raise KiwoomOpenAPIError(f"키움증권 API 업무 오류: {payload.get('return_msg') or '조회 실패'}")
        return payload, response.headers.get("cont-yn", ""), response.headers.get("next-key", "")

    async def fetch_account_number(self, client: httpx.AsyncClient, token: str) -> str:
        body, _, _ = await self._post_api(client, token, "ka00001", {})
        account_no = str(body.get("acctNo", "")).strip()
        if not account_no:
            raise KiwoomOpenAPIError("키움증권 계좌번호 조회 응답에 acctNo가 없습니다.")
        return account_no

    @staticmethod
    def _validate_realized_dates(from_date: str, to_date: str) -> tuple[str, str]:
        values = []
        for value in (from_date, to_date):
            text = str(value or "").strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                text = text.replace("-", "")
            elif not re.fullmatch(r"\d{8}", text):
                raise KiwoomOpenAPIError("키움증권 조회 날짜 형식이 올바르지 않습니다.")
            try:
                parsed = datetime.strptime(text, "%Y%m%d")
            except ValueError as exc:
                raise KiwoomOpenAPIError("키움증권 조회 날짜 형식이 올바르지 않습니다.") from exc
            if parsed.strftime("%Y%m%d") != text:
                raise KiwoomOpenAPIError("키움증권 조회 날짜 형식이 올바르지 않습니다.")
            values.append(text)
        if values[0] > values[1]:
            raise KiwoomOpenAPIError("키움증권 조회 시작일이 종료일보다 늦습니다.")
        return values[0], values[1]

    @staticmethod
    def _add_calendar_months(value: date, months: int) -> date:
        month_index = value.month - 1 + months
        year = value.year + month_index // 12
        month = month_index % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    @classmethod
    def _domestic_realized_date_chunks(cls, start: str, end: str) -> list[tuple[str, str]]:
        """Cover a normalized interval with contiguous conservative calendar chunks."""
        current = datetime.strptime(start, "%Y%m%d").date()
        finish = datetime.strptime(end, "%Y%m%d").date()
        chunks: list[tuple[str, str]] = []
        while current <= finish:
            next_boundary = cls._add_calendar_months(current, KIWOOM_DOMESTIC_SAFE_CHUNK_MONTHS)
            chunk_end = min(finish, next_boundary - timedelta(days=1))
            chunks.append((current.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
            current = chunk_end + timedelta(days=1)
        return chunks

    @staticmethod
    def _is_ust21530_no_data_response(api_id: str, payload: dict[str, Any], code: Decimal) -> bool:
        """Recognize only the live-verified US realized-P/L no-data response."""
        message = str(payload.get("return_msg") or "")
        return (
            api_id == "ust21530"
            and code == _UST21530_NO_DATA_CODE
            and re.search(rf"(?<!\d){_UST21530_NO_DATA_SUBCODE}(?!\d)", message) is not None
            and _UST21530_NO_DATA_MESSAGE in message
        )

    @staticmethod
    def _parse_realized_response(response: httpx.Response, *, api_id: str) -> tuple[dict[str, Any], str, str]:
        KiwoomOpenAPI._raise_for_response(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise KiwoomOpenAPIError("키움증권 API 응답이 올바른 JSON이 아닙니다.") from exc
        if not isinstance(payload, dict) or "return_code" not in payload:
            raise KiwoomOpenAPIError("키움증권 API 응답 형식이 올바르지 않습니다.")
        try:
            code = Decimal(str(payload["return_code"]).strip())
        except (InvalidOperation, ValueError) as exc:
            raise KiwoomOpenAPIError("키움증권 API 업무 결과 코드가 올바르지 않습니다.") from exc
        if not code.is_finite():
            raise KiwoomOpenAPIError("키움증권 API 업무 조회에 실패했습니다.")
        if code != 0 and not KiwoomOpenAPI._is_ust21530_no_data_response(api_id, payload, code):
            raise KiwoomOpenAPIError("키움증권 API 업무 조회에 실패했습니다.")
        if code != 0:
            payload[_KIWOOM_NO_DATA_MARKER] = True
        return payload, str(response.headers.get("cont-yn", "")).strip().upper(), str(response.headers.get("next-key", "")).strip()

    async def _post_realized_page(
        self, client: httpx.AsyncClient, token: str, path: str, api_id: str,
        body: dict[str, Any], *, cont_yn: str = "", next_key: str = "",
    ) -> tuple[dict[str, Any], str, str, str]:
        """Post one page, retrying the exact continuation request once on HTTP 401."""
        def headers_for(access_token: str) -> dict[str, str]:
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "authorization": f"Bearer {access_token}",
                "api-id": api_id,
            }
            if cont_yn:
                headers["cont-yn"] = cont_yn
            if next_key:
                headers["next-key"] = next_key
            return headers

        response = await client.post(f"{self.base_url}{path}", headers=headers_for(token), json=body)
        if response.status_code == 401:
            token = await self._access_token(client, force_refresh=True)
            response = await client.post(f"{self.base_url}{path}", headers=headers_for(token), json=body)
        payload, response_cont_yn, response_next_key = self._parse_realized_response(response, api_id=api_id)
        return payload, response_cont_yn, response_next_key, token

    async def _fetch_realized_pages(
        self, client: httpx.AsyncClient, token: str, *, path: str, api_id: str,
        body: dict[str, Any], rows_field: str,
        delay: Callable[[float], Awaitable[Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        rows: list[dict[str, Any]] = []
        cont_yn = next_key = ""
        seen_keys: set[str] = set()
        wait = delay or asyncio.sleep
        for page_index in range(KIWOOM_REALIZED_MAX_PAGES):
            payload, response_cont_yn, response_next_key, token = await self._post_realized_page(
                client, token, path, api_id, body, cont_yn=cont_yn, next_key=next_key,
            )
            page_rows = payload.get(rows_field)
            is_no_data = payload.get(_KIWOOM_NO_DATA_MARKER) is True
            if is_no_data and page_rows is None:
                page_rows = []
            if not isinstance(page_rows, list) or not all(isinstance(row, dict) for row in page_rows):
                raise KiwoomOpenAPIError("키움증권 실현손익 응답 항목 형식이 올바르지 않습니다.")
            if is_no_data and page_rows:
                raise KiwoomOpenAPIError("키움증권 실현손익 no-data 응답 형식이 올바르지 않습니다.")
            rows.extend(page_rows)
            if response_cont_yn != "Y":
                return rows, token
            if not response_next_key:
                raise KiwoomOpenAPIError("PAGINATION_CONTINUATION_KEY_MISSING")
            if response_next_key in seen_keys:
                raise KiwoomOpenAPIError("PAGINATION_CONTINUATION_KEY_REPEATED")
            seen_keys.add(response_next_key)
            if page_index + 1 >= KIWOOM_REALIZED_MAX_PAGES:
                raise KiwoomOpenAPIError("PAGINATION_LIMIT_EXCEEDED")
            cont_yn, next_key = "Y", response_next_key
            await wait(0.2)
        raise KiwoomOpenAPIError("PAGINATION_LIMIT_EXCEEDED")

    async def discover_realized_source_account(
        self, client: httpx.AsyncClient, token: str,
    ) -> tuple[str, str, str, str]:
        payload, _, _, token = await self._post_realized_page(
            client, token, "/api/dostk/acnt", "ka00001", {},
        )
        acct_no = str(payload.get("acctNo") or "").strip()
        if not acct_no:
            raise KiwoomOpenAPIError("키움증권 계좌번호 조회 응답에 acctNo가 없습니다.")
        return acct_no, compute_kiwoom_account_key(acct_no), mask_kiwoom_account(acct_no), token

    async def get_realized_source_account_state(self) -> tuple[str, str]:
        """Return only the opaque key and masked label for the current token scope."""
        require_external_network("Kiwoom OpenAPI account scope")
        if not self.configured:
            raise KiwoomOpenAPIError("키움증권 AppKey/AppSecret이 설정되지 않았습니다.")
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await self._access_token(client)
            _, source_key, source_label, _ = await self.discover_realized_source_account(client, token)
            return source_key, source_label

    async def fetch_realized_profit(
        self, *, market: str, from_date: str, to_date: str, stock_code: str | None = None,
        delay: Callable[[float], Awaitable[Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], str, str]:
        """Fetch read-only Kiwoom realized P/L rows and return only opaque account scope."""
        require_external_network("Kiwoom OpenAPI realized P/L")
        if not self.configured:
            raise KiwoomOpenAPIError("키움증권 AppKey/AppSecret이 설정되지 않았습니다.")
        start, end = self._validate_realized_dates(from_date, to_date)
        if market not in {"kr", "us"}:
            raise KiwoomOpenAPIError("지원하지 않는 키움증권 실현손익 시장입니다.")
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await self._access_token(client)
            _, source_key, source_label, token = await self.discover_realized_source_account(client, token)
            if market == "kr":
                rows = []
                chunks = self._domestic_realized_date_chunks(start, end)
                chunk_wait = delay or asyncio.sleep
                for chunk_index, (chunk_start, chunk_end) in enumerate(chunks):
                    body = {"strt_dt": chunk_start, "end_dt": chunk_end}
                    if stock_code is not None and str(stock_code).strip():
                        body["stk_cd"] = str(stock_code).strip()
                    chunk_rows, token = await self._fetch_realized_pages(
                        client, token, path="/api/dostk/acnt", api_id="ka10073",
                        body=body, rows_field="dt_stk_rlzt_pl", delay=delay,
                    )
                    rows.extend(chunk_rows)
                    if chunk_index + 1 < len(chunks):
                        await chunk_wait(0.2)
            else:
                rows, _ = await self._fetch_realized_pages(
                    client, token, path="/api/us/acnt", api_id="ust21530",
                    body={"strt_dt": start, "end_dt": end, "fc_krw_tp": "0"},
                    rows_field="result_list", delay=delay,
                )
        return rows, source_key, source_label

    async def fetch_domestic_balance(self, client: httpx.AsyncClient, token: str) -> tuple[list[dict[str, Any]], float]:
        rows: list[dict[str, Any]] = []
        cont_yn = next_key = ""
        for _ in range(20):
            body, cont_yn, next_key = await self._post_api(
                client, token, "kt00018", {"qry_tp": "1", "dmst_stex_tp": "KRX"},
                cont_yn="Y" if cont_yn == "Y" else "", next_key=next_key,
            )
            page = body.get("acnt_evlt_remn_indv_tot")
            if not isinstance(page, list):
                raise KiwoomOpenAPIError("키움증권 잔고 응답의 acnt_evlt_remn_indv_tot 형식이 올바르지 않습니다.")
            if not all(isinstance(item, dict) for item in page):
                raise KiwoomOpenAPIError("키움증권 보유종목 항목 형식이 올바르지 않습니다.")
            rows.extend(page)
            if cont_yn != "Y":
                break
            if not next_key:
                raise KiwoomOpenAPIError("키움증권 잔고 연속조회 키가 없습니다.")
        else:
            raise KiwoomOpenAPIError("키움증권 잔고 연속조회 한도를 초과했습니다.")
        deposit, _, _ = await self._post_api(client, token, "kt00001", {"qry_tp": "2"})
        if "entr" not in deposit:
            raise KiwoomOpenAPIError("키움증권 예수금 응답에 entr가 없습니다.")
        holdings: list[dict[str, Any]] = []
        for item in rows:
            qty = as_float(item.get("rmnd_qty"))
            if qty <= 0:
                continue
            raw_code = str(item.get("stk_cd", "")).strip()
            code = raw_code[1:] if len(raw_code) == 7 and raw_code[0] in {"A", "J", "Q"} else raw_code
            if not code:
                raise KiwoomOpenAPIError("키움증권 보유종목 응답에 종목코드가 없습니다.")
            holdings.append({
                "symbol": code, "name": str(item.get("stk_nm") or code), "quantity": qty,
                "avg_price": abs(as_float(item.get("pur_pric"))), "current_price": abs(as_float(item.get("cur_prc"))),
                "currency": "KRW", "market": "KRX", "source": "kiwoom_api",
            })
        return holdings, as_float(deposit["entr"])

    async def sync_holdings(self) -> list[dict[str, Any]]:
        require_external_network("Kiwoom OpenAPI")
        if not self.configured:
            raise KiwoomOpenAPIError("키움증권 AppKey/AppSecret이 설정되지 않았습니다.")
        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)
            account_no = await self.fetch_account_number(client, token)
            holdings, cash_krw = await self.fetch_domestic_balance(client, token)
        masked = f"{account_no[:4]}****"
        self.last_accounts = [{"account_number": account_no, "account_name": f"키움증권 ({masked})"}]
        self.account_cash = {account_no: {"KRW": cash_krw}}
        for holding in holdings:
            holding["account_number"] = account_no
        return holdings
