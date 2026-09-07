from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class KiwoomOpenAPIError(RuntimeError):
    pass


def as_float(value: Any) -> float:
    try:
        val_str = str(value).replace(",", "").strip()
        if val_str.startswith("+"):
            val_str = val_str[1:]
        return float(val_str)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class Token:
    value: str
    expires_at: float


class KiwoomOpenAPI:
    """키움증권 (Kiwoom Securities) 공식 오픈 REST API 클라이언트.
    
    공식 레포지토리: https://github.com/Kiwoom-Securities/Kiwoom-REST-API
    """

    _ALLOWED_HOSTS = {
        "api.kiwoom.com",
        "openapi.kiwoom.com",
        "mockapi.kiwoom.com",
        "openapivts.kiwoom.com",
    }

    def __init__(self, username: str = "sagesaint") -> None:
        self.username = username
        from app.services.user_openapi import get_user_openapi_config
        cfg = get_user_openapi_config(username).get("kiwoom", {})

        self.base_url = os.getenv("KIWOOM_BASE_URL", "https://api.kiwoom.com").rstrip("/")
        self.app_key = cfg.get("app_key", "").strip()
        self.app_secret = cfg.get("app_secret", "").strip()
        self.account_no = cfg.get("account_no", "").replace("-", "").strip()

        self._validate_url(self.base_url, "KIWOOM_BASE_URL")
        user_dir = Path(__file__).resolve().parents[2] / "data" / "users" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        self.token_cache_file = user_dir / "kiwoom_token_cache.json"

        self._token: Token | None = None
        self.last_accounts: list[dict[str, Any]] = []
        self.account_cash: dict[str, dict[str, float]] = {}

    @staticmethod
    def _validate_url(value: str, setting: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.hostname not in KiwoomOpenAPI._ALLOWED_HOSTS:
            raise KiwoomOpenAPIError(f"{setting}은 키움증권 공식 HTTPS 주소(api.kiwoom.com 등)여야 합니다.")

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    @property
    def is_virtual(self) -> bool:
        hostname = urlparse(self.base_url).hostname or ""
        return "mockapi" in hostname or "openapivts" in hostname

    def _parse_account_no(self) -> tuple[str, str]:
        """계좌번호를 CANO(8자리)와 ACNT_PRDT_CD(2자리)로 분리합니다."""
        acc = self.account_no.replace("-", "").strip()
        if len(acc) >= 10:
            return acc[:8], acc[8:10]
        elif len(acc) == 8:
            return acc, "01"
        return acc, "01"

    async def _access_token(self, client: httpx.AsyncClient, force_refresh: bool = False) -> str:
        if not self.configured:
            raise KiwoomOpenAPIError("키움증권 AppKey 또는 AppSecret이 설정되지 않았습니다. 상단 [OpenAPI] 버튼에서 키를 먼저 등록하세요.")

        if not force_refresh:
            if self._token and self._token.expires_at > time.time() + 60:
                return self._token.value
            try:
                if self.token_cache_file.exists():
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
        
        # 키움증권 OAuth2 토큰 발급 명세:
        # Request body: {"grant_type": "client_credentials", "appkey": app_key, "secretkey": app_secret}
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret,
            "appsecret": self.app_secret,  # 호환성을 위해 둘 다 전송
        }
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (AssetDashboard)",
        }

        try:
            response = await client.post(
                f"{self.base_url}/oauth2/token",
                json=payload,
                headers=headers,
            )
        except Exception as e:
            raise KiwoomOpenAPIError(f"키움증권 토큰 서버 연결 실패: {e}") from e

        if response.is_error:
            try:
                err_detail = response.json()
            except Exception:
                err_detail = response.text
            raise KiwoomOpenAPIError(f"키움증권 토큰 발급 실패 ({response.status_code}): {err_detail}")

        data = response.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            msg = data.get("message") or data.get("msg") or data.get("return_msg") or str(data)
            raise KiwoomOpenAPIError(f"키움증권 토큰 발급 응답에 access_token이 없습니다: {msg}")

        expires_in = as_float(data.get("expires_in", 86400))
        self._token = Token(token, time.time() + expires_in)
        try:
            self.token_cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_cache_file.write_text(
                json.dumps({
                    "app_key_prefix": self.app_key[:8],
                    "access_token": token,
                    "expires_at": self._token.expires_at,
                }, ensure_ascii=False),
                encoding="utf-8",
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
            raise KiwoomOpenAPIError(f"키움증권 API 요청 실패 ({response.status_code}): {detail}")

    async def fetch_domestic_balance(self, client: httpx.AsyncClient, token: str) -> tuple[list[dict[str, Any]], float]:
        """키움증권 국내주식 잔고 및 예수금 조회 (POST /api/dostk/acnt - TR: kt00018)"""
        cano, prdt_cd = self._parse_account_no()
        if not cano:
            return [], 0.0

        full_acc = f"{cano}{prdt_cd}" if len(cano) == 8 and prdt_cd else cano

        # 1. 키움 표준 REST API (POST /api/dostk/acnt, api-id: kt00018)
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "api-id": "kt00018",
            "appkey": self.app_key,
        }
        payload = {
            "acnt_no": cano,
            "qry_tp": "1",
            "dmst_stex_tp": "KRX",
        }

        holdings: list[dict[str, Any]] = []
        cash_krw = 0.0

        try:
            response = await client.post(
                f"{self.base_url}/api/dostk/acnt",
                headers=headers,
                json=payload,
            )
            if response.status_code == 200:
                body = response.json()
                
                # 키움 응답 리스트 추출 (다양한 응답 키 포맷 지원)
                raw_items = []
                for candidate in ("output", "output1", "acnt_evlt_remn_indv_tot", "output2", "items"):
                    val = body.get(candidate)
                    if isinstance(val, list) and val:
                        raw_items = val
                        break
                    elif isinstance(val, dict):
                        raw_items = [val]
                        break

                for item in raw_items:
                    hldg = as_float(item.get("hldg_qty") or item.get("hold_qty") or item.get("qty") or item.get("bal_qty", 0))
                    sll = as_float(item.get("thdt_sll_qty") or item.get("sll_qty", 0))
                    qty = max(0.0, hldg - sll) if sll > 0 else hldg
                    if qty <= 0:
                        continue

                    raw_code = str(item.get("stk_cd") or item.get("pdno") or item.get("item_code") or "").strip()
                    # A005930 -> 005930 정규화
                    code = raw_code[1:] if raw_code.startswith("A") and len(raw_code) == 7 else raw_code
                    name = str(item.get("stk_nm") or item.get("prdt_name") or item.get("item_name") or "").strip() or code
                    avg_price = as_float(item.get("pchs_avg_pric") or item.get("avg_pchs_prc") or item.get("pchs_amt", 0))
                    current_price = as_float(item.get("cur_prc") or item.get("prpr") or item.get("now_pric", 0)) or avg_price

                    holdings.append({
                        "symbol": code,
                        "name": name,
                        "quantity": qty,
                        "avg_price": avg_price,
                        "current_price": current_price,
                        "currency": "KRW",
                        "market": "KR",
                        "source": "kiwoom_api",
                    })

                # 예수금 추출: D+2 결제반영 추정 예수금(d2_evlt_amt, prvs_rcdl_excc_amt) 우선
                cash_candidates = [
                    body.get("d2_evlt_amt"),
                    body.get("prvs_rcdl_excc_amt"),
                    body.get("dnca_tot_amt"),
                    body.get("entr_amt"),
                    body.get("deposit"),
                ]
                for c in cash_candidates:
                    if c is not None:
                        val = as_float(c)
                        if val > 0:
                            cash_krw = val
                            break

                return holdings, cash_krw
        except Exception as e:
            logger.warning("키움 /api/dostk/acnt 조회 중: %s. Fallback uapi 시도합니다.", e)

        # 2. Fallback: uapi inquire-balance 방식
        try:
            tr_id = "VTTC8434R" if self.is_virtual else "TTTC8434R"
            uapi_headers = {
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
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
            }
            res_uapi = await client.get(
                f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
                headers=uapi_headers,
                params=params,
            )
            if res_uapi.status_code == 200:
                body = res_uapi.json()
                raw_items = body.get("output1", [])
                for item in raw_items:
                    hldg = as_float(item.get("hldg_qty", 0) or item.get("hold_qty", 0))
                    sll = as_float(item.get("thdt_sll_qty") or item.get("sll_qty", 0))
                    qty = max(0.0, hldg - sll) if sll > 0 else hldg
                    if qty <= 0:
                        continue
                    code = str(item.get("pdno", "") or item.get("item_code", "")).strip()
                    name = str(item.get("prdt_name", "") or item.get("item_name", "")).strip() or code
                    avg_price = as_float(item.get("pchs_avg_pric", 0) or item.get("avg_price", 0))
                    current_price = as_float(item.get("prpr", 0) or item.get("current_price", 0)) or avg_price
                    holdings.append({
                        "symbol": code,
                        "name": name,
                        "quantity": qty,
                        "avg_price": avg_price,
                        "current_price": current_price,
                        "currency": "KRW",
                        "market": "KR",
                        "source": "kiwoom_api",
                    })
                output2 = body.get("output2", [])
                if isinstance(output2, list) and output2:
                    cash_krw = as_float(output2[0].get("prvs_rcdl_excc_amt", 0)) or as_float(output2[0].get("dnca_tot_amt", 0))
                elif isinstance(output2, dict):
                    cash_krw = as_float(output2.get("prvs_rcdl_excc_amt", 0)) or as_float(output2.get("dnca_tot_amt", 0))
        except Exception as e:
            logger.warning("키움 uapi fallback 조회 중 오류: %s", e)

        return holdings, cash_krw

    async def fetch_overseas_balance(self, client: httpx.AsyncClient, token: str) -> tuple[list[dict[str, Any]], float]:
        """키움증권 해외주식 (미국 등) 잔고 및 외화예수금 조회"""
        cano, prdt_cd = self._parse_account_no()
        if not cano:
            return [], 0.0

        holdings: list[dict[str, Any]] = []
        cash_usd = 0.0

        # 1. 키움 해외주식 REST API (POST /api/ovstk/acnt, api-id: kt00019)
        try:
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "authorization": f"Bearer {token}",
                "api-id": "kt00019",
                "appkey": self.app_key,
            }
            payload = {
                "acnt_no": cano,
                "qry_tp": "1",
                "ovrs_excg_cd": "NASD",
            }
            response = await client.post(
                f"{self.base_url}/api/ovstk/acnt",
                headers=headers,
                json=payload,
            )
            if response.status_code == 200:
                body = response.json()
                raw_items = body.get("output", []) or body.get("output1", [])
                if isinstance(raw_items, dict):
                    raw_items = [raw_items]
                for item in raw_items:
                    ovrs_cblc = as_float(item.get("ovrs_cblc_qty") or item.get("hldg_qty") or item.get("qty", 0))
                    sll = as_float(item.get("thdt_sll_qty") or item.get("sll_qty", 0))
                    qty = max(0.0, ovrs_cblc - sll) if sll > 0 else ovrs_cblc
                    if qty <= 0:
                        continue
                    code = str(item.get("ovrs_pdno") or item.get("stk_cd") or item.get("symbol", "")).strip()
                    name = str(item.get("ovrs_item_name") or item.get("stk_nm") or code).strip()
                    avg_price = as_float(item.get("pchs_avg_pric") or item.get("avg_price", 0))
                    current_price = as_float(item.get("now_pric2") or item.get("cur_prc", 0)) or avg_price

                    holdings.append({
                        "symbol": code,
                        "name": name,
                        "quantity": qty,
                        "avg_price": avg_price,
                        "current_price": current_price,
                        "currency": "USD",
                        "market": "US",
                        "source": "kiwoom_api",
                    })

                cash_usd = as_float(body.get("frcr_dncl_amt_2") or body.get("deposit_usd") or body.get("entr_amt_usd", 0))
                return holdings, cash_usd
        except Exception as e:
            logger.warning("키움 해외주식 /api/ovstk/acnt 조회 알림: %s", e)

        # 2. Fallback: uapi inquire-balance
        try:
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
            res_uapi = await client.get(
                f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-balance",
                headers=headers,
                params=params,
            )
            if res_uapi.status_code == 200:
                body = res_uapi.json()
                raw_items = body.get("output1", [])
                for item in raw_items:
                    ovrs_cblc = as_float(item.get("ovrs_cblc_qty", 0) or item.get("hold_qty", 0))
                    sll = as_float(item.get("thdt_sll_qty") or item.get("sll_qty", 0))
                    qty = max(0.0, ovrs_cblc - sll) if sll > 0 else ovrs_cblc
                    if qty <= 0:
                        continue
                    code = str(item.get("ovrs_pdno", "") or item.get("item_code", "")).strip()
                    name = str(item.get("ovrs_item_name", "") or item.get("item_name", "")).strip() or code
                    avg_price = as_float(item.get("pchs_avg_pric", 0) or item.get("avg_price", 0))
                    current_price = as_float(item.get("now_pric2", 0) or item.get("current_price", 0)) or avg_price
                    holdings.append({
                        "symbol": code,
                        "name": name,
                        "quantity": qty,
                        "avg_price": avg_price,
                        "current_price": current_price,
                        "currency": "USD",
                        "market": "US",
                        "source": "kiwoom_api",
                    })
                output2 = body.get("output2", {})
                if isinstance(output2, dict):
                    cash_usd = as_float(output2.get("frcr_dncl_amt_2", 0) or output2.get("ovrs_tot_pfls", 0) or output2.get("deposit_usd", 0))
        except Exception as e:
            logger.warning("키움 해외주식 uapi fallback 조회 알림: %s", e)

        return holdings, cash_usd

    async def sync_holdings(self) -> list[dict[str, Any]]:
        """키움증권 국내 및 해외 주식 잔고와 예수금을 일괄 조회합니다."""
        if not self.configured:
            raise KiwoomOpenAPIError("키움증권 AppKey/AppSecret이 설정되지 않았습니다.")

        cano, prdt_cd = self._parse_account_no()
        if not cano:
            raise KiwoomOpenAPIError("키움증권 계좌번호(8자리 또는 계좌번호-01)를 설정해 주세요. 상단 [OpenAPI] 버튼에서 등록할 수 있습니다.")

        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)

            domestic_holdings, cash_krw = await self.fetch_domestic_balance(client, token)
            overseas_holdings, cash_usd = await self.fetch_overseas_balance(client, token)

            all_holdings = domestic_holdings + overseas_holdings

            full_acc_no = f"{cano}-{prdt_cd}" if prdt_cd else cano
            self.last_accounts = [{
                "account_number": full_acc_no,
                "cano": cano,
                "acnt_prdt_cd": prdt_cd,
                "account_name": f"키움증권 ({full_acc_no})",
                "cash_krw": cash_krw,
                "cash_usd": cash_usd,
            }]
            self.account_cash = {
                full_acc_no: {"KRW": cash_krw, "USD": cash_usd}
            }

            return all_holdings
