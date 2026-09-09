from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.network_policy import require_external_network


class KiwoomOpenAPIError(RuntimeError):
    pass


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
