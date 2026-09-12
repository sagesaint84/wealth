from __future__ import annotations

import json
import hashlib
import hmac
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.network_policy import require_external_network

logger = logging.getLogger(__name__)


class NhPlugOpenAPIError(RuntimeError):
    pass


def as_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def compute_nh_account_key(act_no: str, secret: str | None = None) -> str:
    """Return a deterministic opaque identity for an NH source account."""
    normalized = str(act_no or "").replace("-", "").strip()
    if not normalized:
        return ""
    key = secret if secret is not None else os.getenv("DASHBOARD_SECRET_KEY", "").strip()
    if not key and os.getenv("WEALTH_ENV", "").strip().lower() == "test":
        key = os.getenv("WEALTH_TEST_SIGNING_SECRET", "wealth_synthetic_test_secret_for_nh")
    if not key:
        raise NhPlugOpenAPIError("DASHBOARD_SECRET_KEY가 설정되지 않아 NH 계좌 식별을 진행할 수 없습니다.")
    return hmac.new(key.encode("utf-8"), f"nh:{normalized}".encode("utf-8"), hashlib.sha256).hexdigest()


def mask_nh_account(act_no: str) -> str:
    """Return a display-only NH account label without exposing act_no."""
    normalized = str(act_no or "").replace("-", "").strip()
    if not normalized:
        return ""
    return f"{normalized[:4]}****" if len(normalized) > 4 else "****"


class NhPlugOpenAPI:
    """NH투자증권(NHPLUG) 읽기 전용 잔고 조회 클라이언트."""

    _ALLOWED_HOSTS = {"api.nhplug.com", "moapi.nhplug.com"}
    _SUCCESS_CODES = {"00000", "00165", "00166", "00218", "00221", "13578"}
    _OVERSEAS_COUNTRIES = {
        "200": ("USD", "NH_US"),
        "070": ("JPY", "NH_JP"),
        "120": ("HKD", "NH_HK"),
        "160": ("CNY", "NH_CN"),
        "170": ("CNY", "NH_CN"),
    }

    def __init__(self, username: str = "sagesaint") -> None:
        self.username = username
        from app.services.user_openapi import get_user_openapi_config
        cfg = get_user_openapi_config(username).get("nh", {})

        self.base_url = os.getenv("NHPLUG_BASE_URL", "https://api.nhplug.com:8443").rstrip("/")
        self.auth_url = os.getenv("NHPLUG_AUTH_URL", "https://api.nhplug.com:8443").rstrip("/")
        self.app_key = cfg.get("app_key", "")
        self.app_secret = cfg.get("app_secret", "")
        self._validate_url(self.base_url, "NHPLUG_BASE_URL")
        self._validate_url(self.auth_url, "NHPLUG_AUTH_URL")
        from app.services.user_manager import get_user_data_dir
        user_dir = get_user_data_dir(username)
        self.token_cache_file = user_dir / "nhplug_token_cache.json"
        self.last_accounts: list[dict[str, Any]] = []
        self.account_cash: dict[str, dict[str, float]] = {}

    @staticmethod
    def _validate_url(value: str, setting: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in NhPlugOpenAPI._ALLOWED_HOSTS:
            raise NhPlugOpenAPIError(f"{setting}은 NHPLUG 공식 HTTPS 주소여야 합니다.")

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    @property
    def is_mock(self) -> bool:
        return urlparse(self.base_url).hostname == "moapi.nhplug.com"

    async def _access_token(self, client: httpx.AsyncClient, force_refresh: bool = False) -> str:
        if not self.configured:
            raise NhPlugOpenAPIError("나무증권 NHPLUG 앱 키가 설정되지 않았습니다. 상단 [OpenAPI] 버튼에서 app key와 secret을 먼저 등록하세요.")
        if not force_refresh:
            try:
                cached = json.loads(self.token_cache_file.read_text(encoding="utf-8"))
                if (cached.get("app_key_prefix") == self.app_key[:8]
                        and float(cached.get("expires_at", 0)) > time.time() + 60
                        and cached.get("access_token")):
                    return str(cached["access_token"])
            except (OSError, ValueError, TypeError):
                pass
        self.token_cache_file.unlink(missing_ok=True)
        response = await client.post(
            f"{self.auth_url}/oauth2/token",
            params={
                "appkey": self.app_key,
                "appsecretkey": self.app_secret,
                "grant_type": "client_credentials",
                "scope": "oob",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self._raise_for_response(response)
        token = response.json().get("access_token")
        if not token:
            raise NhPlugOpenAPIError("나무증권 토큰 응답에 access_token이 없습니다.")
        try:
            self.token_cache_file.parent.mkdir(parents=True, exist_ok=True)
            expires_in = float(response.json().get("expires_in", 86400))
            self.token_cache_file.write_text(json.dumps({"app_key_prefix": self.app_key[:8], "access_token": token, "expires_at": time.time() + expires_in}, ensure_ascii=False), encoding="utf-8")
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
            raise NhPlugOpenAPIError(f"나무증권 OpenAPI 요청 실패 ({response.status_code}): {detail}")

    async def _call(self, path: str, input_0: dict[str, Any], *, cts: str = "") -> dict[str, Any]:
        require_external_network("NH/Namuh OpenAPI")
        async with httpx.AsyncClient(timeout=20.0) as client:
            token = await self._access_token(client)
            request_headers = {
                "x-client-id": self.app_key,
                "x-client-secret": self.app_secret,
                "authorization": f"Bearer {token}",
                "content-type": "application/json;charset=utf-8",
            }
            if cts:
                request_headers["cts"] = cts
            response = await client.post(
                f"{self.base_url}{path}",
                headers=request_headers,
                json={"Input_0": input_0},
            )
            # 만약 캐시된 토큰이 무효화되었거나 401/IGW40043 오류인 경우, 토큰을 즉시 재발급받아 1회 재시도
            if response.status_code in (400, 401):
                try:
                    err_payload = response.json()
                    rsp_cd = str(err_payload.get("rsp_cd", ""))
                    rsp_msg = str(err_payload.get("rsp_msg", ""))
                except Exception:
                    rsp_cd, rsp_msg = "", ""
                if rsp_cd == "IGW40043" or "token" in rsp_msg.lower() or "토큰" in rsp_msg or response.status_code == 401:
                    token = await self._access_token(client, force_refresh=True)
                    retry_headers = dict(request_headers)
                    retry_headers["authorization"] = f"Bearer {token}"
                    response = await client.post(
                        f"{self.base_url}{path}",
                        headers=retry_headers,
                        json={"Input_0": input_0},
                    )
            self._raise_for_response(response)
            try:
                payload = response.json()
            except ValueError as exc:
                raise NhPlugOpenAPIError("나무증권 OpenAPI 응답이 올바른 JSON이 아닙니다.") from exc
            if not isinstance(payload, dict):
                raise NhPlugOpenAPIError("나무증권 OpenAPI 응답 형식이 올바르지 않습니다.")
            response_cts = str(response.headers.get("cts", "")).strip()
            response_cts_flag = str(response.headers.get("cts_flag", "")).strip().upper()
        code = str(payload.get("rsp_cd", ""))
        message = str(payload.get("rsp_msg", ""))
        if code not in self._SUCCESS_CODES:
            raise NhPlugOpenAPIError(f"나무증권 OpenAPI 응답 오류 ({code or '코드 없음'}): {message or payload}")
        if not response_cts:
            for value in payload.values():
                if isinstance(value, dict):
                    response_cts = next((str(v).strip() for k, v in value.items() if str(k).lower().startswith("ctsz") and str(v).strip()), "")
                    if response_cts:
                        break
        payload["_wealth_continuation"] = {"cts": response_cts, "flag": response_cts_flag}
        return payload

    async def _call_pages(self, path: str, input_0: dict[str, Any]) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        cts = ""
        seen: set[str] = set()
        for _ in range(20):
            page = await self._call(path, input_0, cts=cts)
            pages.append(page)
            meta = page.get("_wealth_continuation", {})
            if not isinstance(meta, dict):
                raise NhPlugOpenAPIError("나무증권 연속조회 상태가 올바르지 않습니다.")
            raw_cts = meta.get("cts", "")
            raw_flag = meta.get("flag", "")
            if not isinstance(raw_cts, str) or not isinstance(raw_flag, str):
                raise NhPlugOpenAPIError("나무증권 연속조회 상태가 올바르지 않습니다.")
            next_cts = raw_cts.strip()
            flag = raw_flag.strip().upper()
            if flag not in {"", "Y", "N"}:
                raise NhPlugOpenAPIError("나무증권 연속조회 상태가 올바르지 않습니다.")
            if flag == "N":
                return pages
            if flag == "Y":
                if not next_cts:
                    raise NhPlugOpenAPIError("나무증권 연속조회 상태가 올바르지 않습니다.")
            elif next_cts:
                raise NhPlugOpenAPIError("나무증권 연속조회 상태가 올바르지 않습니다.")
            else:
                return pages
            if next_cts in seen:
                return pages
            seen.add(next_cts)
            cts = next_cts
        raise NhPlugOpenAPIError("나무증권 연속조회 한도를 초과했습니다.")

    @staticmethod
    def _active_realized_row(row: dict[str, Any], sell_amount_field: str, pnl_field: str) -> bool:
        """Keep sell/realized adjustment rows; missing values are never treated as data."""
        def nonzero(value: Any) -> bool:
            if value is None or str(value).strip() == "":
                return False
            try:
                return float(str(value).replace(",", "")) != 0
            except (TypeError, ValueError):
                return False
        return nonzero(row.get("sll_qty")) or nonzero(row.get(sell_amount_field)) or nonzero(row.get(pnl_field))

    async def fetch_realized_profit(self, *, act_no: str, market: str, from_date: str, to_date: str) -> tuple[list[dict[str, Any]], str, str]:
        """Retrieve official NH realized-P/L rows through the documented two-tier inquiries.

        Returned rows are provider rows enriched only with retrieval context.  Projection,
        signing, and persistence intentionally remain outside this transport client.
        """
        account = str(act_no or "").replace("-", "").strip()
        if not account:
            raise NhPlugOpenAPIError("나무증권 계좌번호가 필요합니다.")
        if market not in {"kr", "us"}:
            raise NhPlugOpenAPIError("지원하지 않는 NH 실현손익 시장입니다.")
        key = compute_nh_account_key(account)
        label = mask_nh_account(account)
        sta_dt = str(from_date or "").replace("-", "").strip()
        end_dt = str(to_date or "").replace("-", "").strip()

        if market == "kr":
            discovery_pages = await self._call_pages(
                "/krstock/inquiry/v1/dailyPnl",
                {"act_no": account, "iqr_sta_dt": sta_dt, "iqr_end_dt": end_dt},
            )
            dates = sorted({
                str(row.get("sby_dt", "")).strip()
                for page in discovery_pages
                for row in (page.get("Output_1") or [])
                if isinstance(row, dict) and self._active_realized_row(row, "sll_amt", "pls_amt") and str(row.get("sby_dt", "")).strip()
            })
            rows: list[dict[str, Any]] = []
            for date in dates:
                pages = await self._call_pages(
                    "/krstock/inquiry/v1/tradingPnl",
                    {"act_no": account, "iqr_sta_dt": date, "iqr_end_dt": date},
                )
                for page in pages:
                    for row in page.get("Output_1") or []:
                        if isinstance(row, dict):
                            rows.append({**row, "_wealth_date_context": date, "_wealth_market": "kr"})
            return rows, key, label

        discovery_pages = await self._call_pages(
            "/gbstock/inquiry/v1/periodPnl",
            {"act_no": account, "iqr_dit": "1", "sta_orr_dt": sta_dt, "end_orr_dt": end_dt, "fc_sec_trd_nat_cd": "000"},
        )
        targets = sorted({
            (str(row.get("orr_dt", "")).strip(), str(row.get("fc_sec_trd_nat_cd", "")).strip(), str(row.get("trd_cur_cd", "")).strip())
            for page in discovery_pages
            for row in (page.get("Output_1") or [])
            if isinstance(row, dict)
            and self._active_realized_row(row, "fc_sll_amt", "fc_rzt_pls")
            and str(row.get("orr_dt", "")).strip()
            and str(row.get("fc_sec_trd_nat_cd", "")).strip()
            and str(row.get("trd_cur_cd", "")).strip()
        })
        rows = []
        for date, country, currency in targets:
            pages = await self._call_pages(
                "/gbstock/inquiry/v1/periodPnlDetail",
                {"act_no": account, "iqr_dit": "1", "orr_dt": date, "fc_sec_trd_nat_cd": country, "trd_cur_cd": currency},
            )
            for page in pages:
                # NH contract: detail records are Output_0 arrays, not Output_1.
                detail_rows = page.get("Output_0") or []
                if not isinstance(detail_rows, list):
                    raise NhPlugOpenAPIError("나무증권 해외 실현손익 상세 응답 형식이 올바르지 않습니다.")
                for row in detail_rows:
                    if isinstance(row, dict):
                        rows.append({**row, "_wealth_date_context": date, "_wealth_country_context": country, "_wealth_currency_context": currency, "_wealth_market": "us"})
        return rows, key, label

    async def _accounts(self) -> list[dict[str, Any]]:
        payload = await self._call("/n2/acctinfo", {})
        accounts = payload.get("Output_0", [])
        if not isinstance(accounts, list):
            raise NhPlugOpenAPIError("나무증권 계좌 목록 응답 형식이 올바르지 않습니다.")
        allowed_types = {"03"} if self.is_mock else {"01", "02"}
        return [account for account in accounts if str(account.get("acct_type", "")) in allowed_types]

    @staticmethod
    def _account_name(account: dict[str, Any]) -> str:
        account_no = str(account.get("acct_no", ""))
        return f"나무증권 계좌 {account_no[-4:]}" if account_no else "나무증권 계좌"

    async def sync_holdings(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        self.account_cash = {}
        self.last_accounts = await self._accounts()
        if not self.last_accounts:
            raise NhPlugOpenAPIError("현재 API 환경에서 사용할 수 있는 나무증권 계좌가 없습니다.")
        for account in self.last_accounts:
            account_no = str(account.get("acct_no", ""))
            if not account_no:
                continue
            account_name = self._account_name(account)
            domestic_pages = await self._call_pages(
                "/krstock/inquiry/v1/balance",
                {"act_no": account_no, "bnc_bse_cd": "5", "ltg_aot_dit_cd": "9", "aet_bse": "2", "qut_dit_cd": "UNT"},
            )
            domestic = domestic_pages[0]
            out_0 = domestic.get("Output_0") or {}
            domestic_items = [item for page in domestic_pages for item in (page.get("Output_1") or [])]
            if not isinstance(out_0, dict) or not isinstance(domestic_items, list):
                raise NhPlugOpenAPIError("나무증권 국내 잔고 응답 형식이 올바르지 않습니다.")
            
            # 예수금: D+2 결제반영 추정 예수금(nxt2_dd_dca) 또는 원장 예수금(dca) 우선
            krw_cash = 0.0
            if out_0.get("nxt2_dd_dca") is not None and str(out_0.get("nxt2_dd_dca")).strip() != "":
                krw_cash = as_float(out_0.get("nxt2_dd_dca"))
            elif out_0.get("dca") is not None and str(out_0.get("dca")).strip() != "":
                krw_cash = as_float(out_0.get("dca"))
            else:
                found_cash = False
                for k in ("nas_amt", "drn_pbl_amt", "orr_pbl_amt1"):
                    val = out_0.get(k)
                    if val is not None and str(val).strip() != "":
                        krw_cash = as_float(val)
                        found_cash = True
                        break
                if not found_cash:
                    raise NhPlugOpenAPIError("나무증권 국내 잔고 응답에 예수금 필드가 없습니다.")

            usd_cash = 0.0
            self.account_cash[account_no] = {"KRW": krw_cash, "USD": 0.0}

            for item in domestic_items:
                if not isinstance(item, dict):
                    raise NhPlugOpenAPIError("나무증권 국내 보유종목 항목 형식이 올바르지 않습니다.")
                # 수량: 체결기준 잔여수량(rsdl_qty)이 최우선 (당일 매도 체결 시 0으로 반영)
                qty = None
                if item.get("rsdl_qty") is not None and str(item.get("rsdl_qty")).strip() != "":
                    qty = as_float(item.get("rsdl_qty"))
                elif item.get("itg_bnc_qty") is not None:
                    itg = as_float(item.get("itg_bnc_qty"))
                    ny = as_float(item.get("ny_stl_qty", 0))
                    qty = itg + ny if item.get("ny_stl_qty") is not None else itg
                else:
                    qty = as_float(item.get("hldg_qty") or item.get("qty", 0))

                if qty is None or qty <= 0:
                    continue

                code = str(item.get("iem_cd", "")).strip()
                name = str(item.get("iem_nm", "")).strip() or code
                avg_price = as_float(item.get("phs_pr", 0))
                current_price = as_float(item.get("now_pr", 0)) or avg_price

                records.append({
                    "account_key": account_no,
                    "account_name": account_name,
                    "code": code,
                    "name": name,
                    "quantity": qty,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "currency": "KRW",
                    "market": "KRX",
                })

            for country_code, (currency, market) in self._OVERSEAS_COUNTRIES.items():
                try:
                    overseas_pages = await self._call_pages(
                        "/gbstock/inquiry/v1/balance",
                        {"act_no": account_no, "qut_iqr_dit_cd": "9", "fc_sec_trd_nat_cd": country_code, "cur_cd": "KRW", "xns_dit_cd": "1"},
                    )
                    overseas = overseas_pages[0]
                    ov_out0 = overseas.get("Output_0") or {}
                    overseas_items = [item for page in overseas_pages for item in (page.get("Output_1") or [])]
                    if not isinstance(ov_out0, dict) or not isinstance(overseas_items, list):
                        raise NhPlugOpenAPIError("나무증권 해외 잔고 응답 형식이 올바르지 않습니다.")
                    if currency == "USD":
                        for k in ("fc_dca", "fc_ny_stl_xcl_amt", "fc_aet_amt"):
                            val = ov_out0.get(k)
                            if val is not None and str(val).strip() != "":
                                ov_usd = as_float(val)
                                if ov_usd != 0:
                                    usd_cash = ov_usd
                                    break
                        self.account_cash[account_no]["USD"] = usd_cash

                    for item in overseas_items:
                        if not isinstance(item, dict):
                            raise NhPlugOpenAPIError("나무증권 해외 보유종목 항목 형식이 올바르지 않습니다.")
                        ov_qty = None
                        for k in ("cns_bse_bnc_qty", "fc_cns_bse_bnc_qty", "rsdl_qty"):
                            if item.get(k) is not None and str(item.get(k)).strip() != "":
                                ov_qty = as_float(item.get(k))
                                break
                        if ov_qty is None:
                            if item.get("itg_bnc_qty") is not None:
                                itg = as_float(item.get("itg_bnc_qty"))
                                ny = as_float(item.get("ny_stl_qty") or item.get("fc_ny_stl_qty", 0))
                                ov_qty = itg + ny if (item.get("ny_stl_qty") is not None or item.get("fc_ny_stl_qty") is not None) else itg
                            else:
                                ov_qty = as_float(item.get("hldg_qty") or item.get("qty", 0))

                        if ov_qty is None or ov_qty <= 0:
                            continue
                        ov_code = str(item.get("iem_cd", "")).strip()
                        ov_name = str(item.get("iem_nm") or item.get("oss_iem_eng_nm", "")).strip() or ov_code
                        ov_avg = as_float(item.get("fc_avg_phs_pr", 0))
                        ov_curr = as_float(item.get("fc_sec_end_pr", 0)) or ov_avg

                        records.append({
                            "account_key": account_no,
                            "account_name": account_name,
                            "code": ov_code,
                            "name": ov_name,
                            "quantity": ov_qty,
                            "avg_price": ov_avg,
                            "current_price": ov_curr,
                            "currency": item.get("cur_cd") or currency,
                            "market": market,
                        })
                except Exception as e:
                    logger.warning(
                        "나무증권 해외잔고 조회 실패 (%s, %s); 기존 데이터 보호를 위해 동기화를 중단합니다.",
                        country_code,
                        type(e).__name__,
                    )
                    if isinstance(e, NhPlugOpenAPIError):
                        raise
                    raise NhPlugOpenAPIError("나무증권 해외 잔고 처리 중 오류가 발생했습니다.") from e

        return [record for record in records if record["code"] and record["quantity"] > 0]
