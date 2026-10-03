"""Authenticated KRX client for explicit historical IPO reconciliation.

KRX Data Marketplace credentials are resolved from the current Wealth user's
isolated data directory. Routine IPO refreshes never use this client.
"""
from __future__ import annotations

from datetime import datetime
import threading
import time
from typing import Any

import httpx

from app.services.network_policy import require_external_network
from app.services.user_krx_credentials import load_user_krx_credentials
from app.services.ipo.krx_client import (
    KRX_JSON_PATH,
    KRX_NEW_LISTINGS_BLD,
    KRX_NEW_LISTINGS_MENU_ID,
    KrxClient,
    KrxClientError,
    parse_krx_new_listings_json,
)


KRX_LOGIN_PAGE_PATH = "/contents/MDC/COMS/client/MDCCOMS001.cmd"
KRX_LOGIN_JSP_PATH = "/contents/MDC/COMS/client/view/login.jsp?site=mdc"
KRX_LOGIN_PATH = "/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
KRX_SESSION_TTL_SECONDS = 20 * 60
KRX_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)


class KrxAuthenticationError(KrxClientError):
    """Raised when KRX credentials are missing or the login is rejected."""


class AuthenticatedKrxHistoricalClient(KrxClient):
    """KRX historical client that maintains one authenticated HTTP session."""

    def __init__(self, *, username: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.username = str(username or "").strip()
        if not self.username:
            raise KrxAuthenticationError("KRX 사용자 컨텍스트를 확인할 수 없습니다.")
        self._session: httpx.Client | None = None
        self._session_expires_at = 0.0
        self._session_lock = threading.RLock()

    @staticmethod
    def credentials_configured(username: str) -> bool:
        credentials = load_user_krx_credentials(username)
        return bool(credentials["login_id"] and credentials["password"])

    def close(self) -> None:
        with self._session_lock:
            if self._session is not None:
                self._session.close()
            self._session = None
            self._session_expires_at = 0.0

    def _credentials(self) -> tuple[str, str]:
        credentials = load_user_krx_credentials(self.username)
        login_id = credentials["login_id"].strip()
        login_pw = credentials["password"]
        if not login_id or not login_pw:
            raise KrxAuthenticationError(
                "KRX 전체 과거자료 조회에는 KRX Data Marketplace 로그인 정보가 필요합니다. "
                "OpenAPI 설정에서 KRX 아이디와 비밀번호를 저장한 뒤 다시 시도해 주세요."
            )
        return login_id, login_pw

    def _login(self) -> httpx.Client:
        login_id, login_pw = self._credentials()
        client = httpx.Client(
            timeout=self.timeout,
            follow_redirects=False,
            headers={
                "User-Agent": KRX_USER_AGENT,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        login_page = f"{self.base_url}{KRX_LOGIN_PAGE_PATH}"
        login_jsp = f"{self.base_url}{KRX_LOGIN_JSP_PATH}"
        login_url = f"{self.base_url}{KRX_LOGIN_PATH}"
        try:
            first = client.get(login_page)
            if first.is_error:
                raise KrxAuthenticationError(
                    f"KRX 로그인 페이지 연결에 실패했습니다 (HTTP {first.status_code})."
                )
            second = client.get(login_jsp, headers={"Referer": login_page})
            if second.is_error:
                raise KrxAuthenticationError(
                    f"KRX 로그인 화면 연결에 실패했습니다 (HTTP {second.status_code})."
                )

            payload = {
                "mbrNm": "",
                "telNo": "",
                "di": "",
                "certType": "",
                "mbrId": login_id,
                "pw": login_pw,
            }
            response = client.post(login_url, data=payload, headers={"Referer": login_page})
            if response.is_error:
                raise KrxAuthenticationError(
                    f"KRX 로그인 요청에 실패했습니다 (HTTP {response.status_code})."
                )
            try:
                result = response.json()
            except Exception as exc:
                raise KrxAuthenticationError("KRX 로그인 응답 형식을 확인할 수 없습니다.") from exc

            code = str(result.get("_error_code") or "") if isinstance(result, dict) else ""
            if code == "CD011":
                payload["skipDup"] = "Y"
                response = client.post(login_url, data=payload, headers={"Referer": login_page})
                if response.is_error:
                    raise KrxAuthenticationError(
                        f"KRX 중복 로그인 처리에 실패했습니다 (HTTP {response.status_code})."
                    )
                try:
                    result = response.json()
                except Exception as exc:
                    raise KrxAuthenticationError("KRX 중복 로그인 응답 형식을 확인할 수 없습니다.") from exc
                code = str(result.get("_error_code") or "") if isinstance(result, dict) else ""

            if code == "CD010":
                raise KrxAuthenticationError(
                    "KRX 비밀번호 변경이 필요합니다. KRX Data Marketplace에서 비밀번호를 변경한 뒤 "
                    "Wealth OpenAPI 설정의 KRX 비밀번호를 갱신해 주세요."
                )
            if code != "CD001":
                raise KrxAuthenticationError(
                    "KRX 로그인에 실패했습니다. 저장된 아이디/비밀번호 또는 KRX 계정 상태를 확인해 주세요."
                )
            return client
        except Exception:
            client.close()
            raise

    def verify_credentials(self) -> None:
        """Verify the current user's stored login without fetching historical rows."""
        self._authenticated_session()

    def _authenticated_session(self) -> httpx.Client:
        with self._session_lock:
            now = time.monotonic()
            if self._session is not None and now < self._session_expires_at:
                return self._session
            if self._session is not None:
                self._session.close()
            self._session = self._login()
            self._session_expires_at = now + KRX_SESSION_TTL_SECONDS
            return self._session

    def _invalidate_session(self) -> None:
        with self._session_lock:
            if self._session is not None:
                self._session.close()
            self._session = None
            self._session_expires_at = 0.0

    def fetch_new_listings(self, from_date: str, to_date: str) -> list[dict[str, Any]]:
        """Fetch authenticated MDCSTAT20001 data for a bounded date range."""
        require_external_network("KRX")
        try:
            start = datetime.strptime(from_date, "%Y-%m-%d").strftime("%Y%m%d")
            end = datetime.strptime(to_date, "%Y-%m-%d").strftime("%Y%m%d")
        except ValueError as exc:
            raise KrxClientError("KRX new-listings date range is invalid") from exc
        if start > end:
            raise KrxClientError("KRX new-listings date range is invalid")

        url = f"{self.base_url}{KRX_JSON_PATH}"
        headers = {
            "Referer": (
                f"{self.base_url}/contents/MDC/MDI/mdiLoader/"
                f"index.cmd?menuId={KRX_NEW_LISTINGS_MENU_ID}"
            ),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        payload = {
            "bld": KRX_NEW_LISTINGS_BLD,
            "locale": "ko_KR",
            "strtDd": start,
            "endDd": end,
            "mktId": "ALL",
            "isurCd": "ALL",
            "isurCd2": "ALL",
            "listClssCd": "ALL",
            "secugrpTp": "ALL",
            "cntrIsoCd": "ALL",
        }

        for attempt in range(2):
            client = self._authenticated_session()
            try:
                response = client.post(url, headers=headers, data=payload)
            except httpx.HTTPError as exc:
                raise KrxClientError("KRX new-listings HTTP communication error") from exc

            body = response.text or ""
            session_rejected = response.status_code in {401, 403} or "LOGOUT" in body.upper()
            if session_rejected and attempt == 0:
                self._invalidate_session()
                continue
            if response.is_redirect:
                location = str(response.headers.get("location") or "")
                lowered = location.lower()
                if "login" in lowered or "mdccoms001" in lowered:
                    raise KrxAuthenticationError(
                        "KRX historical query session was redirected to the login page."
                    )
                raise KrxClientError(
                    "KRX historical query was redirected to another KRX service page"
                    + (f" ({location})" if location else ".")
                )
            if response.is_error:
                raise KrxClientError(
                    f"KRX new-listings request failed with HTTP {response.status_code}"
                )
            if not body.strip():
                raise KrxClientError("KRX new-listings response body is empty")

            rows = parse_krx_new_listings_json(body)
            if not rows:
                raise KrxClientError("KRX new-listings returned zero usable rows")
            return rows

        raise KrxAuthenticationError("KRX 로그인 세션을 확인할 수 없습니다. 다시 로그인해 주세요.")
