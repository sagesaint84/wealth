from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class KBOpenAPIError(RuntimeError):
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


class KBOpenAPI:
    """KB B2C OpenAPI client. Credentials live only in the server environment."""

    def __init__(self, username: str = "sagesaint") -> None:
        self.username = username
        from app.services.user_openapi import get_user_openapi_config
        cfg = get_user_openapi_config(username).get("kb", {})

        self.base_url = os.getenv("KB_OPENAPI_BASE_URL", "https://developer.kbsec.com:32484").rstrip("/")
        self.app_key = cfg.get("app_key", "")
        self.app_secret = cfg.get("app_secret", "")
        self._token: Token | None = None
        user_dir = Path(__file__).resolve().parents[2] / "data" / "users" / username
        user_dir.mkdir(parents=True, exist_ok=True)
        self.token_cache_file = user_dir / "kb_token_cache.json"

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    @staticmethod
    def _payload(data_body: dict[str, Any]) -> dict[str, Any]:
        return {"dataHeader": {"ipAddr": "", "macAddr": ""}, "dataBody": data_body}

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if not self.configured:
            raise KBOpenAPIError("KB OpenAPI 키가 설정되지 않았습니다. 상단 [OpenAPI] 버튼에서 appKey와 appSecret을 먼저 등록하세요.")
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
        response = await client.post(
            f"{self.base_url}/oauth2/token",
            json=self._payload({"appKey": self.app_key, "appSecret": self.app_secret, "grantType": "client_credentials"}),
        )
        self._raise_for_response(response)
        body = response.json().get("dataBody", response.json())
        token = body.get("access_token")
        if not token:
            raise KBOpenAPIError("KB OpenAPI 토큰 응답에 access_token이 없습니다.")
        self._token = Token(token, time.time() + as_float(body.get("expires_in", 3600)))
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

    async def call(self, endpoint: str, data_body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token = await self._access_token(client)
            response = await client.post(
                f"{self.base_url}{endpoint}",
                headers={"Content-Type": "application/json", "appKey": self.app_key, "Authorization": f"bearer {token}"},
                json=self._payload(data_body),
            )
            self._raise_for_response(response)
            payload = response.json()
        body = payload.get("dataBody", payload)
        code = str(body.get("o_clsf", body.get("clsfP", "0")))
        if code not in {"", "0", "00"}:
            raise KBOpenAPIError(body.get("o_msg", body.get("msg", "KB OpenAPI가 오류를 반환했습니다.")))
        return body

    async def sync_holdings(self) -> list[dict[str, Any]]:
        domestic, overseas = await asyncio.gather(
            self.call("/api/v1/ssqm1801", {"inq_clsf": "0", "mkt_tm_ccd": "1", "is_no": "", "nxt_key": ""}),
            self.call("/api/v1/spqm2226", {"std_crncy_f": "2", "exch_r_aplc_f": "2", "fee_clsf": "0", "cn_f": "0", "nxt_key": "", "mktpr_aplc_clsf": ""}),
        )
        records: list[dict[str, Any]] = []
        for row in domestic.get("Record1", []):
            code = str(row.get("is_no", ""))[-6:]
            qty = max(0.0, as_float(row.get("gnrl_q", 0)) - as_float(row.get("sll_q", 0) or row.get("tdy_sll_q", 0)))
            if qty <= 0:
                continue
            records.append({"code": code, "name": row.get("is_nm", code), "quantity": qty, "avg_price": 0, "current_price": 0, "currency": "KRW", "market": "KRX"})
        for row in overseas.get("Record2", []):
            qty = max(0.0, as_float(row.get("frgn_hld_q_p6", 0)) - as_float(row.get("sll_q", 0) or row.get("tdy_sll_q", 0)))
            if qty <= 0:
                continue
            records.append({"code": row.get("is_cd", ""), "name": row.get("is_nm", ""), "quantity": qty, "avg_price": as_float(row.get("byng_avr_prc_p4")), "current_price": as_float(row.get("now_prc_p4")), "currency": row.get("crncy_clsf_nm", "USD"), "market": row.get("mkt_clsf", "")})
        return [row for row in records if row["code"] and row["quantity"] > 0]

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
