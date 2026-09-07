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


class KISOpenAPIError(RuntimeError):
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


class KISOpenAPI:
    """한국투자증권 (KIS) Open Trading API 읽기 전용 잔고 조회 클라이언트.
    
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
        if len(acc) >= 10:
            return acc[:8], acc[8:10]
        elif len(acc) == 8:
            return acc, "01"
        return acc, "01"

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
            raise KISOpenAPIError(f"한국투자증권 API 요청 실패 ({response.status_code}): {detail}")

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

        response = await client.get(
            f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=headers,
            params=params,
        )
        self._raise_for_response(response)
        body = response.json()

        holdings: list[dict[str, Any]] = []
        raw_items = body.get("output1", [])
        for item in raw_items:
            hldg = as_float(item.get("hldg_qty", 0))
            sll = as_float(item.get("thdt_sll_qty", 0))
            qty = max(0.0, hldg - sll) if sll > 0 else hldg
            if qty <= 0:
                continue

            code = str(item.get("pdno", "")).strip()
            name = str(item.get("prdt_name", "")).strip() or code
            avg_price = as_float(item.get("pchs_avg_pric", 0))
            current_price = as_float(item.get("prpr", 0)) or avg_price

            holdings.append({
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
        output2 = body.get("output2", [])
        cash_krw = 0.0
        summary = output2[0] if isinstance(output2, list) and output2 else (output2 if isinstance(output2, dict) else {})
        if summary.get("prvs_rcdl_excc_amt") is not None and str(summary.get("prvs_rcdl_excc_amt")).strip() != "":
            cash_krw = as_float(summary.get("prvs_rcdl_excc_amt"))
        elif summary.get("dnca_tot_amt") is not None and str(summary.get("dnca_tot_amt")).strip() != "":
            cash_krw = as_float(summary.get("dnca_tot_amt"))

        return holdings, cash_krw

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

        try:
            response = await client.get(
                f"{self.base_url}/uapi/overseas-stock/v1/trading/inquire-balance",
                headers=headers,
                params=params,
            )
            if response.status_code == 200:
                body = response.json()
                raw_items = body.get("output1", [])
                for item in raw_items:
                    ovrs_cblc = as_float(item.get("ovrs_cblc_qty", 0))
                    sll = as_float(item.get("thdt_sll_qty", 0))
                    qty = max(0.0, ovrs_cblc - sll) if sll > 0 else ovrs_cblc
                    if qty <= 0:
                        continue

                    code = str(item.get("ovrs_pdno", "")).strip()
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

                output2 = body.get("output2", {})
                if isinstance(output2, dict):
                    if output2.get("frcr_dncl_amt_2") is not None and str(output2.get("frcr_dncl_amt_2")).strip() != "":
                        cash_usd = as_float(output2.get("frcr_dncl_amt_2"))
                    else:
                        cash_usd = as_float(output2.get("frcr_drwg_psbl_amt_1") or output2.get("ovrs_tot_pfls", 0))
        except Exception as e:
            logger.warning("한국투자증권 해외주식 잔고 조회 중 알림: %s", e)

        return holdings, cash_usd

    async def sync_holdings(self) -> list[dict[str, Any]]:
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
                "account_name": f"한국투자증권 ({full_acc_no})",
                "cash_krw": cash_krw,
                "cash_usd": cash_usd,
            }]
            self.account_cash = {
                full_acc_no: {"KRW": cash_krw, "USD": cash_usd}
            }

            return all_holdings
