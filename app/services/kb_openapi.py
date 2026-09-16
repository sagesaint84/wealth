from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

import httpx

from app.services.broker_holdings_sync import (
    BrokerHoldingsResult,
    DOMESTIC_MARKET,
    OVERSEAS_MARKET,
    ProviderHoldingScope,
    optional_finite_number,
    required_finite_number,
    required_text,
)
from app.services.network_policy import require_external_network

logger = logging.getLogger(__name__)


class KBOpenAPIError(RuntimeError):
    pass


KB_REALIZED_MAX_PAGES = 500


def as_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Token:
    value: str
    expires_at: float


def compute_kb_account_key(gnl_ac_no: str, gds_no: str, secret: str | None = None) -> str:
    """Return a deterministic opaque identity without exposing the raw account number or product code.

    Format: HMAC-SHA256(server_secret, 'kb:' + normalized_gnl_ac_no + ':' + normalized_gds_no)
    """
    normalized_acct = str(gnl_ac_no or "").replace("-", "").strip()
    normalized_gds = str(gds_no or "").strip()
    if not normalized_acct:
        raise KBOpenAPIError("KB증권 계좌번호가 없습니다.")
    if not normalized_gds:
        raise KBOpenAPIError("KB증권 상품번호(gds_no)가 없습니다.")

    key = secret if secret is not None else os.getenv("DASHBOARD_SECRET_KEY", "").strip()
    if not key and os.getenv("WEALTH_ENV", "").strip().lower() == "test":
        key = os.getenv("WEALTH_TEST_SIGNING_SECRET", "").strip()
    if not key:
        raise KBOpenAPIError("KB증권 계좌 식별에 필요한 서버 서명 키(DASHBOARD_SECRET_KEY)가 없습니다.")

    message = f"kb:{normalized_acct}:{normalized_gds}".encode("utf-8")
    return hmac.new(key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def mask_kb_account(gnl_ac_no: str, gds_no: str = "") -> str:
    """Return a display-only masked account label without exposing raw credentials."""
    normalized = str(gnl_ac_no or "").replace("-", "").strip()
    if not normalized:
        return ""
    masked_acct = f"****{normalized[-4:]}" if len(normalized) >= 4 else "****"
    if gds_no:
        return f"{masked_acct}-**"
    return masked_acct


class KBOpenAPI:
    """KB B2C OpenAPI client. Credentials live only in the server environment."""

    _ALLOWED_HOSTS = {
        "developer.kbsec.com",
    }

    def __init__(self, username: str = "sagesaint") -> None:
        self.username = username
        from app.services.user_openapi import get_user_openapi_config
        cfg = get_user_openapi_config(username).get("kb", {})

        self.base_url = os.getenv("KB_OPENAPI_BASE_URL", "https://developer.kbsec.com:32484").rstrip("/")
        self.app_key = cfg.get("app_key", "")
        self.app_secret = cfg.get("app_secret", "")
        self.gnl_ac_no = cfg.get("gnl_ac_no", "").replace("-", "").strip()
        self.gds_no = cfg.get("gds_no", "").strip()
        self._token: Token | None = None
        user_dir = Path(__file__).resolve().parents[2] / "data" / "users" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        self.token_cache_file = user_dir / "kb_token_cache.json"

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    @property
    def realized_configured(self) -> bool:
        """Whether all server-held SSQM2442 account context is present."""
        return bool(self.configured and self.gnl_ac_no and self.gds_no)

    def get_realized_source_account_state(self) -> tuple[str, str]:
        """Resolve the configured source to opaque and display-only forms without a provider call."""
        if not self.realized_configured:
            raise KBOpenAPIError("KB증권 실현손익 조회에 필요한 계좌 및 상품번호 설정이 없습니다.")
        return (
            compute_kb_account_key(self.gnl_ac_no, self.gds_no),
            mask_kb_account(self.gnl_ac_no, self.gds_no),
        )

    @staticmethod
    def _validate_url(value: str, setting: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in KBOpenAPI._ALLOWED_HOSTS:
            raise KBOpenAPIError(f"{setting}은 KB증권 공식 HTTPS 개발자 주소(developer.kbsec.com)여야 합니다.")

    @staticmethod
    def _payload(data_body: dict[str, Any]) -> dict[str, Any]:
        return {"dataHeader": {"ipAddr": "", "macAddr": ""}, "dataBody": data_body}

    async def _access_token(self, client: httpx.AsyncClient, force_refresh: bool = False) -> str:
        if not self.configured:
            raise KBOpenAPIError("KB OpenAPI 키가 설정되지 않았습니다. 상단 [OpenAPI] 버튼에서 appKey와 appSecret을 먼저 등록하세요.")
        now = time.time()
        if not force_refresh and self._token and self._token.expires_at > now + 60:
            return self._token.value
        if not force_refresh:
            try:
                cached = json.loads(self.token_cache_file.read_text(encoding="utf-8"))
                if (cached.get("app_key_prefix") == self.app_key[:8]
                        and float(cached.get("expires_at", 0)) > now + 60
                        and cached.get("access_token")):
                    self._token = Token(str(cached["access_token"]), float(cached["expires_at"]))
                    return self._token.value
            except (OSError, ValueError, TypeError):
                pass
        response = await client.post(
            f"{self.base_url}/oauth2/token",
            json=self._payload({"appKey": self.app_key, "appSecret": self.app_secret, "grantType": "client_credentials"}),
        )
        self._raise_for_response(response)
        body = response.json().get("dataBody", response.json())
        token = body.get("access_token")
        if not token:
            raise KBOpenAPIError("KB OpenAPI 토큰 응답에 access_token이 없습니다.")
        self._token = Token(token, now + as_float(body.get("expires_in", 86400)))
        try:
            self.token_cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_cache_file.write_text(json.dumps({"app_key_prefix": self.app_key[:8], "access_token": token, "expires_at": self._token.expires_at}), encoding="utf-8")
        except (OSError, ValueError, TypeError):
            pass
        return token

    @staticmethod
    def _raise_for_response(response: httpx.Response) -> None:
        if response.is_error:
            try:
                detail = response.json()
            except ValueError:
                detail = response.text
            raise KBOpenAPIError(f"KB OpenAPI 요청 실패 ({response.status_code}): {detail}")

    @staticmethod
    def _normalize_response(payload: Any, *, require_data_body: bool = False) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise KBOpenAPIError("KB OpenAPI 응답 형식이 올바르지 않습니다.")
        if require_data_body and "dataBody" not in payload:
            raise KBOpenAPIError("KB OpenAPI가 잔고 데이터 없이 상태 응답만 반환했습니다.")
        body = payload.get("dataBody", payload)
        if not isinstance(body, dict):
            raise KBOpenAPIError("KB OpenAPI dataBody 형식이 올바르지 않습니다.")
        code = str(body.get("o_clsf", body.get("clsfP", "0")))
        if code not in {"", "0", "00"}:
            raise KBOpenAPIError("KB OpenAPI 업무 응답이 실패했습니다.")
        return body

    async def call(self, endpoint: str, data_body: dict[str, Any], *, require_data_body: bool = False) -> dict[str, Any]:
        require_external_network("KB OpenAPI")
        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)
            response = await client.post(
                f"{self.base_url}{endpoint}",
                headers={"Content-Type": "application/json", "appKey": self.app_key, "Authorization": f"bearer {token}"},
                json=self._payload(data_body),
            )
            self._raise_for_response(response)
            try:
                payload = response.json()
            except ValueError as exc:
                raise KBOpenAPIError("KB OpenAPI 응답이 올바른 JSON이 아닙니다.") from exc
        return self._normalize_response(payload, require_data_body=require_data_body)

    async def sync_holdings(self) -> BrokerHoldingsResult:
        domestic, overseas = await asyncio.gather(
            self.call("/api/v1/ssqm1801", {"inq_clsf": "0", "mkt_tm_ccd": "1", "is_no": "", "nxt_key": ""}, require_data_body=True),
            self.call("/api/v1/spqm2226", {"std_crncy_f": "2", "exch_r_aplc_f": "2", "fee_clsf": "0", "cn_f": "0", "nxt_key": "", "mktpr_aplc_clsf": ""}, require_data_body=True),
        )
        domestic_rows = domestic.get("Record1")
        overseas_rows = overseas.get("Record2")
        if not isinstance(domestic_rows, list) or not isinstance(overseas_rows, list):
            raise KBOpenAPIError("KB OpenAPI 잔고 응답의 보유종목 목록 형식이 올바르지 않습니다.")
        for label, body in (("국내", domestic), ("해외", overseas)):
            continuation = body.get("nxt_key")
            if continuation is not None and str(continuation).strip() not in {"", "0"}:
                raise KBOpenAPIError(f"KB OpenAPI {label} 잔고 응답에 처리되지 않은 연속조회 상태가 있습니다.")
        records: list[dict[str, Any]] = []
        for row in domestic_rows:
            if not isinstance(row, dict):
                raise KBOpenAPIError("KB OpenAPI 국내 보유종목 항목 형식이 올바르지 않습니다.")
            try:
                code = required_text(row, "is_no")[-6:]
                gross_qty = required_finite_number(row, "gnrl_q")
                sell_key = "sll_q" if row.get("sll_q") is not None else "tdy_sll_q"
                sold_qty = optional_finite_number(row, sell_key)
            except ValueError as exc:
                raise KBOpenAPIError(f"KB OpenAPI 국내 보유종목 항목 형식이 올바르지 않습니다: {exc}") from exc
            qty = max(0.0, gross_qty - sold_qty)
            if qty <= 0:
                continue
            records.append({"code": code, "name": row.get("is_nm", code), "quantity": qty, "avg_price": 0, "current_price": 0, "currency": "KRW", "market": "KRX"})
        for row in overseas_rows:
            if not isinstance(row, dict):
                raise KBOpenAPIError("KB OpenAPI 해외 보유종목 항목 형식이 올바르지 않습니다.")
            try:
                code = required_text(row, "is_cd")
                gross_qty = required_finite_number(row, "frgn_hld_q_p6")
                sell_key = "sll_q" if row.get("sll_q") is not None else "tdy_sll_q"
                sold_qty = optional_finite_number(row, sell_key)
                currency = required_text(row, "crncy_clsf_nm")
                market = required_text(row, "mkt_clsf")
            except ValueError as exc:
                raise KBOpenAPIError(f"KB OpenAPI 해외 보유종목 항목 형식이 올바르지 않습니다: {exc}") from exc
            qty = max(0.0, gross_qty - sold_qty)
            if qty <= 0:
                continue
            records.append({"code": code, "name": row.get("is_nm", ""), "quantity": qty, "avg_price": as_float(row.get("byng_avr_prc_p4")), "current_price": as_float(row.get("now_prc_p4")), "currency": currency, "market": market})
        return BrokerHoldingsResult.authoritative_result(
            records,
            (
                ProviderHoldingScope("kb_primary", DOMESTIC_MARKET),
                ProviderHoldingScope("kb_primary", OVERSEAS_MARKET),
            ),
            cash_valid=False,
        )

    async def refresh_prices(self, holdings: list[dict[str, Any]]) -> tuple[dict[str, float], list[str]]:
        prices: dict[str, float] = {}
        errors: list[str] = []

        async def refresh(holding: dict[str, Any]) -> None:
            key = holding["id"]
            try:
                if holding.get("market") == "KRX" and str(holding.get("code", "")).isdigit():
                    body = await self.call("/api/v1/ivu10140", {"excg_clsf": "0", "shrt_cd": str(holding["code"])[-6:]})
                    price = as_float(body.get("now_prc"))
                elif holding.get("market"):
                    body = await self.call("/api/v1/gss10030", {"krx_cd": holding["market"], "is_cd": holding["code"]})
                    price = as_float(body.get("now_prc_p4"))
                else:
                    errors.append(f"{holding['name']}: 거래소 코드가 없어 시세를 조회하지 못했습니다.")
                    return
                if price > 0:
                    prices[key] = price
                else:
                    errors.append(f"{holding['name']}: 유효한 현재가가 응답되지 않았습니다.")
            except KBOpenAPIError as exc:
                errors.append(f"{holding['name']}: {exc}")

        await asyncio.gather(*(refresh(holding) for holding in holdings))
        return prices, errors

    # =========================================================================
    # SSQM2442 Domestic Realized P/L Transport (Milestone 1)
    # =========================================================================

    @staticmethod
    def validate_and_normalize_dates(from_date: str, to_date: str) -> tuple[str, str]:
        """Validate and normalize YYYYMMDD or YYYY-MM-DD losslessly to YYYYMMDD. Requires start <= end."""
        def parse_date(val: str, label: str) -> tuple[str, datetime]:
            raw = str(val or "").strip()
            for fmt in ("%Y%m%d", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    if fmt == "%Y%m%d" and dt.strftime("%Y%m%d") == raw:
                        return dt.strftime("%Y%m%d"), dt
                    if fmt == "%Y-%m-%d" and dt.strftime("%Y-%m-%d") == raw:
                        return dt.strftime("%Y%m%d"), dt
                except ValueError:
                    continue
            raise KBOpenAPIError(f"{label} 날짜 형식이 올바르지 않습니다: {raw} (YYYYMMDD 또는 YYYY-MM-DD 필요)")

        start_str, start_dt = parse_date(from_date, "시작")
        end_str, end_dt = parse_date(to_date, "종료")
        if start_dt > end_dt:
            raise KBOpenAPIError(f"시작일자({start_str})가 종료일자({end_str})보다 늦을 수 없습니다.")
        return start_str, end_str

    @staticmethod
    def _parse_realized_response(response: httpx.Response) -> tuple[dict[str, Any], str]:
        """Parse official KB SSQM2442 response envelope.

        Requires:
        - HTTP 200
        - valid JSON
        - dataHeader.resultCode == "200"
        - dataBody is dict
        - extracts nxt_key from dataBody

        Returns: (dataBody, raw_nxt_key)
        """
        if response.status_code != 200:
            raise KBOpenAPIError(f"KB증권 API HTTP 오류 ({response.status_code}): {response.text[:200]}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise KBOpenAPIError("KB증권 API 응답이 올바른 JSON이 아닙니다.") from exc

        if not isinstance(payload, dict):
            raise KBOpenAPIError("KB증권 API 응답 형식이 올바르지 않습니다.")

        data_header = payload.get("dataHeader")
        if not isinstance(data_header, dict):
            raise KBOpenAPIError("KB증권 API 응답에 dataHeader가 없습니다.")

        result_code = str(data_header.get("resultCode", "")).strip()
        if result_code != "200":
            msg = str(data_header.get("resultMessage") or "").strip()
            proc_code = str(data_header.get("processCode") or "").strip()
            raise KBOpenAPIError(f"KB증권 API 조회 실패 (code={result_code}/{proc_code}): {msg}")

        data_body = payload.get("dataBody")
        if not isinstance(data_body, dict):
            raise KBOpenAPIError("KB증권 API 성공 응답에 dataBody가 없습니다.")

        if "nxt_key" not in data_body:
            raise KBOpenAPIError("KB증권 API 응답 dataBody에 nxt_key 필드가 누락되었습니다.")

        nxt_key = data_body["nxt_key"]
        if nxt_key is None:
            raise KBOpenAPIError("KB증권 API 응답 nxt_key가 null입니다 (fail closed).")
        if not isinstance(nxt_key, str):
            raise KBOpenAPIError("KB증권 API 응답 nxt_key가 문자열이 아닙니다 (fail closed).")

        return data_body, nxt_key

    @staticmethod
    def is_terminal_nxt_key(nxt_key: str) -> bool:
        """Classify continuation key terminal state.

        - All-whitespace string (e.g. 24 spaces) is the officially verified terminal state.
        - Empty string is accepted as a defensive terminal state (WEALTH POLICY, explicitly documented).
        - Non-whitespace non-empty string is a valid continuation token.
        """
        if not isinstance(nxt_key, str):
            raise KBOpenAPIError("PAGINATION_MALFORMED_NON_STRING_KEY")
        return len(nxt_key.strip()) == 0

    async def _post_ssqm2442_page(
        self,
        client: httpx.AsyncClient,
        token: str,
        *,
        inq_strt_dt: str,
        inq_end_dt: str,
        gnl_ac_no: str,
        gds_no: str,
        is_cd: str = "",
        md_clsf: str = "2",
        nxt_key: str = "",
    ) -> tuple[dict[str, Any], str, str]:
        """Post one SSQM2442 page with single 401 retry preserving all continuation parameters.

        Returns: (data_body, nxt_key, current_token)
        """
        def make_headers(tok: str) -> dict[str, str]:
            return {
                "Content-Type": "application/json",
                "appKey": self.app_key,
                "Authorization": f"bearer {tok}",
            }

        body = {
            "dataHeader": {"ipAddr": "", "macAddr": ""},
            "dataBody": {
                "inq_strt_dt": inq_strt_dt,
                "inq_end_dt": inq_end_dt,
                "is_cd": is_cd,
                "md_clsf": md_clsf,
                "nxt_key": nxt_key,
                "gnl_ac_no": gnl_ac_no,
                "gds_no": gds_no,
            },
        }

        url = f"{self.base_url}/api/v1/ssqm2442"
        response = await client.post(url, headers=make_headers(token), json=body, timeout=20.0)

        if response.status_code == 401:
            token = await self._access_token(client, force_refresh=True)
            response = await client.post(url, headers=make_headers(token), json=body, timeout=20.0)

        data_body, returned_nxt_key = self._parse_realized_response(response)
        return data_body, returned_nxt_key, token

    async def fetch_domestic_realized_pnl(
        self,
        *,
        from_date: str,
        to_date: str,
        gnl_ac_no: str | None = None,
        gds_no: str | None = None,
        stock_code: str | None = None,
        delay: Callable[[float], Awaitable[Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], str, str]:
        """Fetch all domestic realized P/L pages for the configured account and date range.

        Fail-safe requirements:
        - gnl_ac_no and gds_no must be non-empty; missing gds_no fails closed before network request.
        - Neither gnl_ac_no nor gds_no are ever exposed to the client.
        - md_clsf = '2' (verified ONLINE channel semantics).
        - Returns: (raw_records, source_account_key, source_account_label)
        """
        require_external_network("KB OpenAPI SSQM2442 realized P/L")

        if not self.configured:
            raise KBOpenAPIError("KB증권 AppKey / AppSecret이 설정되지 않았습니다.")

        # Account fail-closed validation
        acct_no = str(gnl_ac_no if gnl_ac_no is not None else self.gnl_ac_no).replace("-", "").strip()
        product_no = str(gds_no if gds_no is not None else self.gds_no).strip()

        if not acct_no:
            raise KBOpenAPIError("KB증권 계좌번호가 설정되지 않았습니다.")
        if not product_no:
            raise KBOpenAPIError("KB증권 상품번호(gds_no)가 설정되지 않아 조회를 진행할 수 없습니다. (fail-closed: 하드코딩 금지)")

        start_dt, end_dt = self.validate_and_normalize_dates(from_date, to_date)
        is_cd = str(stock_code or "").strip()

        source_key = compute_kb_account_key(acct_no, product_no)
        source_label = mask_kb_account(acct_no, product_no)

        rows: list[dict[str, Any]] = []
        current_nxt_key = ""
        seen_keys: set[str] = set()
        wait = delay or asyncio.sleep

        async with httpx.AsyncClient(timeout=25.0) as client:
            token = await self._access_token(client)

            for page_index in range(KB_REALIZED_MAX_PAGES):
                data_body, next_key, token = await self._post_ssqm2442_page(
                    client,
                    token,
                    inq_strt_dt=start_dt,
                    inq_end_dt=end_dt,
                    gnl_ac_no=acct_no,
                    gds_no=product_no,
                    is_cd=is_cd,
                    md_clsf="2",  # Online channel
                    nxt_key=current_nxt_key,
                )

                record1 = data_body.get("Record1")
                if record1 is None:
                    record1 = []
                if not isinstance(record1, list) or not all(isinstance(r, dict) for r in record1):
                    raise KBOpenAPIError("KB증권 SSQM2442 응답의 Record1 형식이 올바르지 않습니다.")

                rows.extend(record1)

                # Termination check
                if self.is_terminal_nxt_key(next_key):
                    return rows, source_key, source_label

                # Non-terminal continuation validation
                if next_key == current_nxt_key:
                    raise KBOpenAPIError("KB증권 연속조회 키가 이전 페이지와 동일합니다 (PAGINATION_CONTINUATION_KEY_REPEATED fail-closed).")
                if next_key in seen_keys:
                    raise KBOpenAPIError("KB증권 연속조회 키가 이미 처리된 키입니다 (PAGINATION_LOOP_DETECTED fail-closed).")

                seen_keys.add(next_key)

                if page_index + 1 >= KB_REALIZED_MAX_PAGES:
                    raise KBOpenAPIError("KB증권 실현손익 연속조회 안전 한도(500페이지)를 초과했습니다.")

                current_nxt_key = next_key
                await wait(0.2)

            raise KBOpenAPIError("KB증권 실현손익 연속조회 안전 한도를 초과했습니다.")
