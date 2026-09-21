from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.secure_files import atomic_write_private_json

from app.services.broker_holdings_sync import (
    BrokerHoldingsResult,
    DOMESTIC_MARKET,
    ProviderHoldingScope,
    optional_finite_number,
    required_finite_number,
    required_text,
)
from app.services.network_policy import require_external_network

logger = logging.getLogger(__name__)


class KISOpenAPIError(RuntimeError):
    pass


KIS_IPO_PUB_OFFER_PATH = "/uapi/domestic-stock/v1/ksdinfo/pub-offer"
KIS_IPO_PUB_OFFER_TR_ID = "HHKDB669108C0"
KIS_LIST_INFO_PATH = "/uapi/domestic-stock/v1/ksdinfo/list-info"
KIS_LIST_INFO_TR_ID = "HHKDB669107C0"
KIS_STOCK_INFO_PATH = "/uapi/domestic-stock/v1/quotations/search-stock-info"
KIS_STOCK_INFO_TR_ID = "CTPF1002R"
KIS_SCHEDULE_MAX_PAGES = 10


def _normalize_kis_yyyymmdd(value: Any, *, field: str, allow_blank: bool = True) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        if allow_blank:
            return None
        raise KISOpenAPIError(f"한국투자증권 {field} 값이 비어 있습니다.")
    digits = re.sub(r"[^0-9]", "", raw)
    if len(digits) != 8:
        raise KISOpenAPIError(f"한국투자증권 {field} 날짜 형식이 올바르지 않습니다: {raw}")
    try:
        parsed = datetime.strptime(digits, "%Y%m%d")
    except ValueError as exc:
        raise KISOpenAPIError(f"한국투자증권 {field} 날짜가 올바르지 않습니다: {raw}") from exc
    return parsed.strftime("%Y-%m-%d")


def _normalize_kis_query_date(value: str, *, field: str) -> str:
    normalized = _normalize_kis_yyyymmdd(value, field=field, allow_blank=False)
    assert normalized is not None
    return normalized.replace("-", "")


def _normalize_kis_date_range(value: Any, *, field: str) -> tuple[str | None, str | None]:
    raw = str(value or "").strip()
    if not raw:
        return None, None
    parts = [part.strip() for part in re.split(r"\s*~\s*", raw) if part.strip()]
    if len(parts) == 1:
        date_value = _normalize_kis_yyyymmdd(parts[0], field=field, allow_blank=False)
        return date_value, date_value
    if len(parts) != 2:
        raise KISOpenAPIError(f"한국투자증권 {field} 기간 형식이 올바르지 않습니다: {raw}")
    start = _normalize_kis_yyyymmdd(parts[0], field=f"{field} 시작일", allow_blank=False)
    end = _normalize_kis_yyyymmdd(parts[1], field=f"{field} 종료일", allow_blank=False)
    if start and end and start > end:
        raise KISOpenAPIError(f"한국투자증권 {field} 시작일이 종료일보다 늦습니다: {raw}")
    return start, end


def _optional_kis_number(value: Any, *, field: str) -> float | None:
    raw = str(value or "").replace(",", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise KISOpenAPIError(f"한국투자증권 {field} 숫자 형식이 올바르지 않습니다: {value}") from exc


def _split_kis_lead_managers(value: Any) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    result: list[str] = []
    for item in re.split(r"[,/·ㆍ\n]+", raw):
        name = item.strip()
        if name and name not in result:
            result.append(name)
    return result


def _kis_listing_track(company_name: str) -> str:
    compact = re.sub(r"\s+", "", str(company_name or "")).upper()
    return "spac" if ("스팩" in compact or "기업인수목적" in compact or "SPAC" in compact) else "general"


def normalize_kis_ipo_subscription_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one KIS KSD public-offering row to the Wealth IPO schedule contract.

    Completely blank placeholder rows are ignored. Any non-blank row that is missing the
    core company/code/subscription contract fails closed instead of becoming partial data.
    """
    if not isinstance(row, dict):
        raise KISOpenAPIError("한국투자증권 공모주청약일정 항목 형식이 올바르지 않습니다.")
    if not any(str(v or "").strip() for v in row.values()):
        return None

    company_name = str(row.get("isin_name") or "").strip()
    stock_code = str(row.get("sht_cd") or "").strip()
    subscr_raw = str(row.get("subscr_dt") or "").strip()
    if not company_name or not stock_code or not subscr_raw:
        raise KISOpenAPIError("한국투자증권 공모주청약일정 핵심 필드(isin_name/sht_cd/subscr_dt)가 누락되었습니다.")

    subscription_start, subscription_end = _normalize_kis_date_range(subscr_raw, field="청약기간")
    payment_date = _normalize_kis_yyyymmdd(row.get("pay_dt"), field="납입일")
    refund_date = _normalize_kis_yyyymmdd(row.get("refund_dt"), field="환불일")
    expected_listing_date = _normalize_kis_yyyymmdd(row.get("list_dt"), field="상장일")
    final_offer_price = _optional_kis_number(row.get("fix_subscr_pri"), field="확정공모가")
    lead_managers = _split_kis_lead_managers(row.get("lead_mgr"))

    return {
        "company_name": company_name,
        "stock_code": stock_code,
        "listing_track": _kis_listing_track(company_name),
        "subscription_start": subscription_start,
        "subscription_end": subscription_end,
        "payment_date": payment_date,
        "refund_date": refund_date,
        "expected_listing_date": expected_listing_date,
        "final_offer_price": final_offer_price,
        "lead_managers": lead_managers,
        "sources": {
            "kis": {
                "schedule_source": "ksdinfo_pub_offer",
                "record_date": _normalize_kis_yyyymmdd(row.get("record_date"), field="기준일"),
                "pub_bf_cap": _optional_kis_number(row.get("pub_bf_cap"), field="공모전자본금"),
                "pub_af_cap": _optional_kis_number(row.get("pub_af_cap"), field="공모후자본금"),
                "assign_stk_qty": _optional_kis_number(row.get("assign_stk_qty"), field="배정주식수"),
            }
        },
    }


def normalize_kis_listing_schedule_row(row: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize one KIS KSD listing-info row. Blank placeholder rows are ignored."""
    if not isinstance(row, dict):
        raise KISOpenAPIError("한국투자증권 상장정보일정 항목 형식이 올바르지 않습니다.")
    if not any(str(v or "").strip() for v in row.values()):
        return None

    stock_code = str(row.get("sht_cd") or "").strip()
    company_name = str(row.get("isin_name") or "").strip()
    list_dt = _normalize_kis_yyyymmdd(row.get("list_dt"), field="상장/등록일", allow_blank=False)
    if not stock_code or not company_name:
        raise KISOpenAPIError("한국투자증권 상장정보일정 핵심 필드(isin_name/sht_cd)가 누락되었습니다.")

    return {
        "stock_code": stock_code,
        "company_name": company_name,
        "listing_date": list_dt,
        "stock_kind": str(row.get("stk_kind") or "").strip(),
        "issue_type": str(row.get("issue_type") or "").strip(),
        "issue_stock_qty": _optional_kis_number(row.get("issue_stk_qty"), field="상장주식수"),
        "total_issue_stock_qty": _optional_kis_number(row.get("tot_issue_stk_qty"), field="총발행주식수"),
        "issue_price": _optional_kis_number(row.get("issue_price"), field="발행가"),
    }


def as_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def normalize_kis_stock_info_response(
    body: Any,
    *,
    requested_stock_code: str,
) -> dict[str, Any]:
    """Normalize KIS domestic stock basic info (CTPF1002R)."""
    if not isinstance(body, dict):
        raise KISOpenAPIError("한국투자증권 주식기본조회 응답 형식이 올바르지 않습니다.")
    if "rt_cd" not in body:
        raise KISOpenAPIError("한국투자증권 주식기본조회 응답에 업무 결과 코드가 없습니다.")
    if str(body.get("rt_cd")) != "0":
        raise KISOpenAPIError(
            f"한국투자증권 주식기본조회 응답 오류: {body.get('msg1') or body.get('msg_cd') or '업무 오류'}"
        )

    output = body.get("output")
    if not isinstance(output, dict):
        raise KISOpenAPIError("한국투자증권 주식기본조회 output 응답 형식이 올바르지 않습니다.")

    mket_id_cd = str(output.get("mket_id_cd") or "").strip().upper()
    if not mket_id_cd:
        raise KISOpenAPIError("한국투자증권 주식기본조회 시장코드(mket_id_cd)가 누락되었습니다.")

    raw_pdno = str(output.get("pdno") or "").strip()
    prdt_name = str(output.get("prdt_name") or "").strip()
    issue_price = _optional_kis_number(output.get("issu_pric"), field="발행가")

    if mket_id_cd == "KSQ":
        raw_listing_date = output.get("kosdaq_mket_lstg_dt")
    elif mket_id_cd == "STK":
        raw_listing_date = output.get("scts_mket_lstg_dt")
    else:
        raw_listing_date = None

    listing_date = _normalize_kis_yyyymmdd(raw_listing_date, field="상장일", allow_blank=True)

    return {
        "stock_code": requested_stock_code,
        "product_code": raw_pdno,
        "company_name": prdt_name,
        "market_code": mket_id_cd,
        "listing_date": listing_date,
        "issue_price": issue_price,
    }


@dataclass
class Token:
    value: str
    expires_at: float


def compute_kis_account_key(cano: str, prdt_cd: str, secret: str | None = None) -> str:
    """Compute deterministic opaque server-side account key from CANO + PRDT_CD."""
    if not cano:
        return ""
    from app.services.kis_feed import get_kis_signing_secret
    key_secret = secret if secret is not None else get_kis_signing_secret()
    message = f"kis-account-v1:{cano}:{prdt_cd}".encode("utf-8")
    return hmac.new(key_secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


class KISOpenAPI:
    """한국투자증권 (KIS) Open Trading API 읽기 전용 클라이언트.
    
    공식 레포지토리: https://github.com/koreainvestment/open-trading-api
    """

    _ALLOWED_HOSTS = {
        "openapi.koreainvestment.com",
        "openapivts.koreainvestment.com",
    }

    def __init__(self, username: str = "sagesaint") -> None:
        self.username = username
        from app.services.user_openapi import get_user_openapi_config
        cfg = get_user_openapi_config(username).get("kis", {})

        self.base_url = os.getenv("KIS_BASE_URL", "https://openapi.koreainvestment.com:9443").rstrip("/")
        self.app_key = cfg.get("app_key", "")
        self.app_secret = cfg.get("app_secret", "")
        self.account_no = cfg.get("account_no", "").replace("-", "").strip()

        self._validate_url(self.base_url, "KIS_BASE_URL")
        user_dir = Path(__file__).resolve().parents[2] / "data" / "users" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        self.token_cache_file = user_dir / "kis_token_cache.json"

        self._token: Token | None = None
        self.last_accounts: list[dict[str, Any]] = []
        self.account_cash: dict[str, dict[str, float]] = {}

    @staticmethod
    def _validate_url(value: str, setting: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in KISOpenAPI._ALLOWED_HOSTS:
            raise KISOpenAPIError(f"{setting}은 한국투자증권 공식 HTTPS 주소(openapi.koreainvestment.com 등)여야 합니다.")

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    @property
    def is_virtual(self) -> bool:
        return "openapivts" in urlparse(self.base_url).hostname

    def _parse_account_no(self) -> tuple[str, str]:
        """계좌번호를 CANO(8자리)와 ACNT_PRDT_CD(2자리)로 분리합니다."""
        acc = self.account_no.replace("-", "").strip()
        if len(acc) == 10 and acc.isdigit():
            return acc[:8], acc[8:10]
        elif len(acc) == 8 and acc.isdigit():
            return acc, "01"
        return "", ""

    def get_masked_account(self) -> str:
        """프론트엔드 노출용 마스킹 계좌번호를 반환합니다."""
        cano, prdt_cd = self._parse_account_no()
        if not cano:
            return ""
        return f"{cano[:4]}****-{prdt_cd}" if prdt_cd else f"{cano[:4]}****"

    def get_source_account_key(self, secret: str | None = None) -> str:
        """서버 비밀키 기반의 결정론적 불투명 계좌 고유 식별키를 반환합니다."""
        cano, prdt_cd = self._parse_account_no()
        return compute_kis_account_key(cano, prdt_cd, secret=secret)

    def get_account_scope(self) -> str:
        """불투명 계좌 식별 범위를 반환합니다 (CANO 비노출)."""
        key = self.get_source_account_key()
        if not key:
            return ""
        return f"kis:{key}"

    @staticmethod
    def _validate_balance_body(body: Any, label: str) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise KISOpenAPIError(f"한국투자증권 {label} 응답 형식이 올바르지 않습니다.")
        if "rt_cd" not in body:
            raise KISOpenAPIError(f"한국투자증권 {label} 응답에 업무 결과 코드가 없습니다.")
        if str(body.get("rt_cd", "0")) != "0":
            raise KISOpenAPIError(f"한국투자증권 {label} 응답 오류: {body.get('msg1') or body.get('msg_cd') or '업무 오류'}")
        if not isinstance(body.get("output1"), list):
            raise KISOpenAPIError(f"한국투자증권 {label} 보유종목 응답 형식이 올바르지 않습니다.")
        output2 = body.get("output2")
        if not isinstance(output2, (list, dict)):
            raise KISOpenAPIError(f"한국투자증권 {label} 예수금 응답 형식이 올바르지 않습니다.")
        return body

    async def _access_token(self, client: httpx.AsyncClient, force_refresh: bool = False) -> str:
        if not self.configured:
            raise KISOpenAPIError("한국투자증권 AppKey 또는 AppSecret이 설정되지 않았습니다. 상단 [OpenAPI] 버튼에서 키를 먼저 등록하세요.")

        if not force_refresh:
            if self._token and self._token.expires_at > time.time() + 60:
                return self._token.value
            try:
                cached = json.loads(self.token_cache_file.read_text(encoding="utf-8"))
                if (
                    cached.get("app_key_prefix") == self.app_key[:8]
                    and float(cached.get("expires_at", 0)) > time.time() + 60
                    and cached.get("access_token")
                ):
                    self._token = Token(str(cached["access_token"]), float(cached["expires_at"]))
                    return self._token.value
            except (OSError, ValueError, TypeError):
                pass

        self.token_cache_file.unlink(missing_ok=True)
        response = await client.post(
            f"{self.base_url}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
            },
            headers={"Content-Type": "application/json"},
        )
        self._raise_for_response(response)
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise KISOpenAPIError("한국투자증권 OAuth 토큰 응답에 access_token이 없습니다.")

        expires_in = as_float(data.get("expires_in", 86400))
        self._token = Token(token, time.time() + expires_in)
        try:
            atomic_write_private_json(
                self.token_cache_file,
                {
                    "app_key_prefix": self.app_key[:8],
                    "access_token": token,
                    "expires_at": self._token.expires_at,
                },
            )
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
            raise KISOpenAPIError(f"한국투자증권 API 요청 실패 ({response.status_code}): {detail}")

    @staticmethod
    def _validate_ksdinfo_body(body: Any, label: str) -> dict[str, Any]:
        if not isinstance(body, dict):
            raise KISOpenAPIError(f"한국투자증권 {label} 응답 형식이 올바르지 않습니다.")
        if "rt_cd" not in body:
            raise KISOpenAPIError(f"한국투자증권 {label} 응답에 업무 결과 코드가 없습니다.")
        if str(body.get("rt_cd")) != "0":
            raise KISOpenAPIError(
                f"한국투자증권 {label} 응답 오류: {body.get('msg1') or body.get('msg_cd') or '업무 오류'}"
            )
        output1 = body.get("output1")
        if not isinstance(output1, list):
            raise KISOpenAPIError(f"한국투자증권 {label} output1 응답 형식이 올바르지 않습니다.")
        return body

    async def _fetch_ksdinfo_pages(
        self,
        client: httpx.AsyncClient,
        token: str,
        *,
        path: str,
        tr_id: str,
        from_date: str,
        to_date: str,
        stock_code: str = "",
        label: str,
        max_pages: int = KIS_SCHEDULE_MAX_PAGES,
    ) -> list[dict[str, Any]]:
        f_dt = _normalize_kis_query_date(from_date, field="조회 시작일")
        t_dt = _normalize_kis_query_date(to_date, field="조회 종료일")
        if f_dt > t_dt:
            raise KISOpenAPIError("한국투자증권 일정 조회 시작일이 종료일보다 늦습니다.")
        if max_pages < 1:
            raise KISOpenAPIError("한국투자증권 일정 조회 페이지 한도가 올바르지 않습니다.")

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        params = {
            "SHT_CD": str(stock_code or "").strip(),
            "CTS": "",
            "F_DT": f_dt,
            "T_DT": t_dt,
        }

        rows: list[dict[str, Any]] = []
        for _ in range(max_pages):
            response = await client.get(f"{self.base_url}{path}", headers=headers, params=params)
            self._raise_for_response(response)
            try:
                body = self._validate_ksdinfo_body(response.json(), label)
            except ValueError as exc:
                raise KISOpenAPIError(f"한국투자증권 {label} 응답이 올바른 JSON이 아닙니다.") from exc

            for row in body["output1"]:
                if not isinstance(row, dict):
                    raise KISOpenAPIError(f"한국투자증권 {label} 항목 형식이 올바르지 않습니다.")
                rows.append(row)

            continuation = str(response.headers.get("tr_cont", "")).upper().strip()
            # The official KSD schedule examples recurse only when tr_cont == "M".
            if continuation != "M":
                return rows
            headers["tr_cont"] = "N"
            await asyncio.sleep(0.05)

        raise KISOpenAPIError(f"한국투자증권 {label} 연속조회 한도를 초과했습니다.")

    async def fetch_ipo_subscription_schedule(
        self,
        from_date: str,
        to_date: str,
        stock_code: str = "",
    ) -> list[dict[str, Any]]:
        """Fetch and normalize KSD public-offering subscription schedules (SPAC included)."""
        require_external_network("KIS OpenAPI")
        if not self.configured:
            raise KISOpenAPIError("한국투자증권 AppKey/AppSecret이 설정되지 않았습니다.")
        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)
            rows = await self._fetch_ksdinfo_pages(
                client, token, path=KIS_IPO_PUB_OFFER_PATH, tr_id=KIS_IPO_PUB_OFFER_TR_ID,
                from_date=from_date, to_date=to_date, stock_code=stock_code, label="공모주청약일정",
            )

        normalized: list[dict[str, Any]] = []
        for row in rows:
            item = normalize_kis_ipo_subscription_row(row)
            if item is not None:
                normalized.append(item)
        return normalized

    async def fetch_listing_schedule(
        self,
        from_date: str,
        to_date: str,
        stock_code: str = "",
    ) -> list[dict[str, Any]]:
        """Fetch KSD listing-information events. This is not an IPO-only universe."""
        require_external_network("KIS OpenAPI")
        if not self.configured:
            raise KISOpenAPIError("한국투자증권 AppKey/AppSecret이 설정되지 않았습니다.")
        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)
            rows = await self._fetch_ksdinfo_pages(
                client, token, path=KIS_LIST_INFO_PATH, tr_id=KIS_LIST_INFO_TR_ID,
                from_date=from_date, to_date=to_date, stock_code=stock_code, label="상장정보일정",
            )

        normalized: list[dict[str, Any]] = []
        for row in rows:
            item = normalize_kis_listing_schedule_row(row)
            if item is not None:
                normalized.append(item)
        return normalized

    async def fetch_multiple_domestic_stock_info(
        self,
        stock_codes: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Fetch multiple domestic stock basic infos within a single client/token session (CTPF1002R)."""
        require_external_network("KIS OpenAPI")
        if not self.configured:
            raise KISOpenAPIError("한국투자증권 AppKey/AppSecret이 설정되지 않았습니다.")

        results: dict[str, dict[str, Any]] = {}
        if not stock_codes:
            return results

        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {token}",
                "appkey": self.app_key,
                "appsecret": self.app_secret,
                "tr_id": KIS_STOCK_INFO_TR_ID,
                "custtype": "P",
            }
            for code in stock_codes:
                clean_code = str(code or "").strip()
                if not clean_code:
                    continue
                params = {
                    "PRDT_TYPE_CD": "300",
                    "PDNO": clean_code,
                }
                response = await client.get(f"{self.base_url}{KIS_STOCK_INFO_PATH}", headers=headers, params=params)
                self._raise_for_response(response)
                try:
                    body = response.json()
                except ValueError as exc:
                    raise KISOpenAPIError("한국투자증권 주식기본조회 응답이 올바른 JSON이 아닙니다.") from exc
                results[clean_code] = normalize_kis_stock_info_response(body, requested_stock_code=clean_code)

        return results

    async def fetch_domestic_stock_info(
        self,
        stock_code: str,
    ) -> dict[str, Any]:
        """Fetch and normalize basic domestic stock information (CTPF1002R)."""
        clean_code = str(stock_code or "").strip()
        if not clean_code:
            raise KISOpenAPIError("종목코드가 비어 있습니다.")
        results = await self.fetch_multiple_domestic_stock_info([clean_code])
        if clean_code not in results:
            raise KISOpenAPIError(f"한국투자증권 주식기본조회 결과를 찾을 수 없습니다: {clean_code}")
        return results[clean_code]

    async def fetch_domestic_balance(self, client: httpx.AsyncClient, token: str) -> tuple[list[dict[str, Any]], float]:
        """국내주식 잔고 및 예수금 조회 (TTTC8434R / VTTC8434R)"""
        cano, prdt_cd = self._parse_account_no()
        if not cano:
            return [], 0.0

        tr_id = "VTTC8434R" if self.is_virtual else "TTTC8434R"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        holdings: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
        for page in range(10):
            response = await client.get(
                f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=headers,
                params=params,
            )
            self._raise_for_response(response)
            try:
                body = self._validate_balance_body(response.json(), "국내 잔고")
            except ValueError as exc:
                raise KISOpenAPIError("한국투자증권 국내 잔고 응답이 올바른 JSON이 아닙니다.") from exc
            output2 = body.get("output2", [])
            summaries.extend(output2 if isinstance(output2, list) else [output2])
            for item in body["output1"]:
                if not isinstance(item, dict):
                    raise KISOpenAPIError("한국투자증권 국내 보유종목 항목 형식이 올바르지 않습니다.")
                holdings.append(item)
            continuation = str(response.headers.get("tr_cont", "")).upper()
            if continuation not in {"M", "F"}:
                break
            fk = str(body.get("ctx_area_fk100", ""))
            nk = str(body.get("ctx_area_nk100", ""))
            if not fk and not nk:
                raise KISOpenAPIError("한국투자증권 국내 잔고 연속조회 키가 없습니다.")
            params["CTX_AREA_FK100"], params["CTX_AREA_NK100"] = fk, nk
            headers["tr_cont"] = "N"
        else:
            raise KISOpenAPIError("한국투자증권 국내 잔고 연속조회 한도를 초과했습니다.")

        parsed_holdings: list[dict[str, Any]] = []
        for item in holdings:
            try:
                code = required_text(item, "pdno")
                hldg = required_finite_number(item, "hldg_qty")
                sll = optional_finite_number(item, "thdt_sll_qty")
            except ValueError as exc:
                raise KISOpenAPIError(f"한국투자증권 국내 보유종목 항목 형식이 올바르지 않습니다: {exc}") from exc
            qty = max(0.0, hldg - sll) if sll > 0 else hldg
            if qty <= 0:
                continue

            name = str(item.get("prdt_name", "")).strip() or code
            avg_price = as_float(item.get("pchs_avg_pric", 0))
            current_price = as_float(item.get("prpr", 0)) or avg_price

            parsed_holdings.append({
                "symbol": code,
                "name": name,
                "quantity": qty,
                "avg_price": avg_price,
                "current_price": current_price,
                "currency": "KRW",
                "market": "KR",
                "source": "kis_api",
            })

        # output2 예수금 정보: D+2 결제반영 추정예수금(prvs_rcdl_excc_amt) 우선
        cash_krw = 0.0
        summary = summaries[0] if summaries else {}
        if summary.get("prvs_rcdl_excc_amt") is not None and str(summary.get("prvs_rcdl_excc_amt")).strip() != "":
            cash_krw = as_float(summary.get("prvs_rcdl_excc_amt"))
        elif summary.get("dnca_tot_amt") is not None and str(summary.get("dnca_tot_amt")).strip() != "":
            cash_krw = as_float(summary.get("dnca_tot_amt"))
        else:
            raise KISOpenAPIError("한국투자증권 국내 잔고 응답에 예수금 필드가 없습니다.")

        return parsed_holdings, cash_krw

    async def fetch_overseas_balance(self, client: httpx.AsyncClient, token: str) -> tuple[list[dict[str, Any]], float]:
        """해외주식 (미국 등) 잔고 및 외화예수금 조회 (TTTS3012R / VTTS3012R)"""
        cano, prdt_cd = self._parse_account_no()
        if not cano:
            return [], 0.0

        tr_id = "VTTS3012R" if self.is_virtual else "TTTS3012R"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt_cd,
            "OVRS_EXCG_CD": "NASD",
            "TR_CRCY_CD": "USD",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }

        holdings: list[dict[str, Any]] = []
        cash_usd = 0.0
        raw_items: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
        for _ in range(10):
            response = await client.get(
                f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-balance",
                headers=headers,
                params=params,
            )
            self._raise_for_response(response)
            try:
                body = self._validate_balance_body(response.json(), "해외 잔고")
            except ValueError as exc:
                raise KISOpenAPIError("한국투자증권 해외 잔고 응답이 올바른 JSON이 아닙니다.") from exc
            raw_items.extend(body["output1"])
            output2 = body.get("output2", {})
            summaries.extend(output2 if isinstance(output2, list) else [output2])
            continuation = str(response.headers.get("tr_cont", "")).upper()
            if continuation not in {"M", "F"}:
                break
            fk = str(body.get("ctx_area_fk200", ""))
            nk = str(body.get("ctx_area_nk200", ""))
            if not fk and not nk:
                raise KISOpenAPIError("한국투자증권 해외 잔고 연속조회 키가 없습니다.")
            params["CTX_AREA_FK200"], params["CTX_AREA_NK200"] = fk, nk
            headers["tr_cont"] = "N"
        else:
            raise KISOpenAPIError("한국투자증권 해외 잔고 연속조회 한도를 초과했습니다.")
        for item in raw_items:
            if not isinstance(item, dict):
                raise KISOpenAPIError("한국투자증권 해외 보유종목 항목 형식이 올바르지 않습니다.")
            try:
                code = required_text(item, "ovrs_pdno")
                ovrs_cblc = required_finite_number(item, "ovrs_cblc_qty")
                sll = optional_finite_number(item, "thdt_sll_qty")
            except ValueError as exc:
                raise KISOpenAPIError(f"한국투자증권 해외 보유종목 항목 형식이 올바르지 않습니다: {exc}") from exc
            qty = max(0.0, ovrs_cblc - sll) if sll > 0 else ovrs_cblc
            if qty <= 0:
                continue
            name = str(item.get("ovrs_item_name", "")).strip() or code
            avg_price = as_float(item.get("pchs_avg_pric", 0))
            current_price = as_float(item.get("now_pric2", 0)) or avg_price
            holdings.append({
                "symbol": code,
                "name": name,
                "quantity": qty,
                "avg_price": avg_price,
                "current_price": current_price,
                "currency": "USD",
                "market": "US",
                "source": "kis_api",
            })

        summary = summaries[0] if summaries else {}
        if summary.get("frcr_dncl_amt_2") is not None and str(summary.get("frcr_dncl_amt_2")).strip() != "":
            cash_usd = as_float(summary.get("frcr_dncl_amt_2"))
        elif any(summary.get(key) is not None for key in ("frcr_drwg_psbl_amt_1", "ovrs_tot_pfls")):
            cash_usd = as_float(summary.get("frcr_drwg_psbl_amt_1") or summary.get("ovrs_tot_pfls", 0))
        else:
            raise KISOpenAPIError("한국투자증권 해외 잔고 응답에 외화예수금 필드가 없습니다.")

        return holdings, cash_usd

    async def sync_holdings(self) -> BrokerHoldingsResult:
        require_external_network("KIS OpenAPI")
        """한국투자증권 국내 및 해외 주식 잔고와 예수금을 일괄 조회합니다."""
        if not self.configured:
            raise KISOpenAPIError("한국투자증권 AppKey/AppSecret이 설정되지 않았습니다.")

        cano, prdt_cd = self._parse_account_no()
        if not cano:
            raise KISOpenAPIError("한국투자증권 계좌번호(8자리 또는 종합계좌번호-상품코드)를 설정해 주세요. 상단 [OpenAPI] 버튼에서 등록할 수 있습니다.")

        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)

            domestic_holdings, cash_krw = await self.fetch_domestic_balance(client, token)
            overseas_holdings, cash_usd = await self.fetch_overseas_balance(client, token)

            all_holdings = domestic_holdings + overseas_holdings

            # 계좌 정보 기록
            full_acc_no = f"{cano}-{prdt_cd}" if prdt_cd else cano
            self.last_accounts = [{
                "account_number": full_acc_no,
                "cano": cano,
                "acnt_prdt_cd": prdt_cd,
                "account_name": f"한국투자증권 ({full_acc_no[:4]}****)",
                "cash_krw": cash_krw,
                "cash_usd": cash_usd,
            }]
            self.account_cash = {
                full_acc_no: {"KRW": cash_krw, "USD": cash_usd}
            }
            for holding in all_holdings:
                holding["account_number"] = full_acc_no

            return BrokerHoldingsResult.authoritative_result(
                all_holdings,
                (
                    ProviderHoldingScope(full_acc_no, DOMESTIC_MARKET),
                    ProviderHoldingScope(full_acc_no, "US"),
                ),
                cash_valid=True,
            )

    async def fetch_domestic_period_trade_profit(
        self,
        client: httpx.AsyncClient,
        token: str,
        inqr_strt_dt: str,
        inqr_end_dt: str,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """국내주식 기간별 매매손익 조회 (TTTC8715R / VTTC8715R)"""
        cano, prdt_cd = self._parse_account_no()
        if not cano:
            return []

        tr_id = "VTTC8715R" if self.is_virtual else "TTTC8715R"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt_cd,
            "SORT_DVSN": "02",
            "INQR_STRT_DT": inqr_strt_dt.replace("-", "").strip(),
            "INQR_END_DT": inqr_end_dt.replace("-", "").strip(),
            "CBLC_DVSN": "00",
            "PDNO": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        rows: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()

        for _ in range(max_pages):
            response = await client.get(
                f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-period-trade-profit",
                headers=headers,
                params=params,
            )
            self._raise_for_response(response)
            try:
                body = response.json()
            except ValueError as exc:
                raise KISOpenAPIError("한국투자증권 국내 기간매매손익 응답이 올바른 JSON이 아닙니다.") from exc

            if not isinstance(body, dict):
                raise KISOpenAPIError("한국투자증권 국내 기간매매손익 응답 형식이 올바르지 않습니다.")
            if str(body.get("rt_cd", "0")) != "0":
                raise KISOpenAPIError(f"한국투자증권 국내 기간매매손익 조회 오류: {body.get('msg1') or body.get('msg_cd') or '업무 오류'}")

            items = body.get("output1", [])
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        rows.append(it)
            elif isinstance(items, dict):
                rows.append(items)

            continuation = str(response.headers.get("tr_cont", "")).upper()
            if continuation not in {"M", "F"}:
                break

            fk = str(body.get("ctx_area_fk100", "")).strip()
            nk = str(body.get("ctx_area_nk100", "")).strip()
            if not fk and not nk:
                break
            if (fk, nk) in seen_keys:
                break
            seen_keys.add((fk, nk))

            params["CTX_AREA_FK100"] = fk
            params["CTX_AREA_NK100"] = nk
            headers["tr_cont"] = "N"

        return rows

    async def fetch_overseas_period_profit(
        self,
        client: httpx.AsyncClient,
        token: str,
        inqr_strt_dt: str,
        inqr_end_dt: str,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """해외주식 기간손익 조회 (TTTS3039R / VTTS3039R)"""
        cano, prdt_cd = self._parse_account_no()
        if not cano:
            return []

        tr_id = "VTTS3039R" if self.is_virtual else "TTTS3039R"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": prdt_cd,
            "OVRS_EXCG_CD": "%",
            "NATN_CD": "",
            "CRCY_CD": "",
            "PDNO": "",
            "INQR_STRT_DT": inqr_strt_dt.replace("-", "").strip(),
            "INQR_END_DT": inqr_end_dt.replace("-", "").strip(),
            "WCRC_FRCR_DVSN_CD": "01",
            "CTX_AREA_FK200": "",
            "CTX_AREA_NK200": "",
        }

        rows: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()

        for _ in range(max_pages):
            response = await client.get(
                f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-period-profit",
                headers=headers,
                params=params,
            )
            self._raise_for_response(response)
            try:
                body = response.json()
            except ValueError as exc:
                raise KISOpenAPIError("한국투자증권 해외 기간손익 응답이 올바른 JSON이 아닙니다.") from exc

            if not isinstance(body, dict):
                raise KISOpenAPIError("한국투자증권 해외 기간손익 응답 형식이 올바르지 않습니다.")
            if str(body.get("rt_cd", "0")) != "0":
                raise KISOpenAPIError(f"한국투자증권 해외 기간손익 조회 오류: {body.get('msg1') or body.get('msg_cd') or '업무 오류'}")

            items = body.get("output1", [])
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict):
                        rows.append(it)
            elif isinstance(items, dict):
                rows.append(items)

            continuation = str(response.headers.get("tr_cont", "")).upper()
            if continuation not in {"M", "F"}:
                break

            fk = str(body.get("ctx_area_fk200", "")).strip()
            nk = str(body.get("ctx_area_nk200", "")).strip()
            if not fk and not nk:
                break
            if (fk, nk) in seen_keys:
                break
            seen_keys.add((fk, nk))

            params["CTX_AREA_FK200"] = fk
            params["CTX_AREA_NK200"] = nk
            headers["tr_cont"] = "N"

        return rows

    async def fetch_realized_profit(
        self,
        market: str,
        from_date: str,
        to_date: str,
    ) -> tuple[list[dict[str, Any]], str, str]:
        """한국투자증권 실현손익 내역을 조회합니다 (읽기 전용)."""
        require_external_network("KIS OpenAPI")
        if not self.configured:
            raise KISOpenAPIError("한국투자증권 AppKey/AppSecret이 설정되지 않았습니다.")

        cano, prdt_cd = self._parse_account_no()
        if not cano:
            raise KISOpenAPIError("한국투자증권 계좌번호가 설정되지 않았습니다. 상단 [OpenAPI] 버튼에서 등록할 수 있습니다.")

        market_clean = market.strip().lower()
        if market_clean not in {"domestic", "overseas", "kr", "us"}:
            raise KISOpenAPIError(f"지원하지 않는 시장 구분입니다: {market}")

        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await self._access_token(client)
            if market_clean in {"domestic", "kr"}:
                rows = await self.fetch_domestic_period_trade_profit(client, token, from_date, to_date)
            else:
                rows = await self.fetch_overseas_period_profit(client, token, from_date, to_date)

        return rows, self.get_source_account_key(), self.get_masked_account()
