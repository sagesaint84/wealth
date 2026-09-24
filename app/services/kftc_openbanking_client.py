"""Asynchronous HTTP client for KFTC Open Banking API.

Enforces:
- Strict HTTPS host allowlist
- Specific timeouts
- Sanitized exception messages (no secrets or sensitive data leaked)
- Response status code and rsp_code validation
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.services.kftc_openbanking_config import (
    ALLOWED_HOSTS,
    KftcConfigError,
    get_kftc_host,
)

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 15.0
TOTAL_TIMEOUT = 25.0


class KftcClientError(Exception):
    """Base exception for KFTC client errors."""
    def __init__(self, message: str, code: str = "KFTC_CLIENT_ERROR"):
        super().__init__(message)
        self.code = code


class KftcAuthError(KftcClientError):
    def __init__(self, message: str = "KFTC authentication failed", code: str = "KFTC_AUTH_ERROR"):
        super().__init__(message, code=code)


class KftcProviderError(KftcClientError):
    def __init__(self, message: str = "KFTC provider error", code: str = "KFTC_PROVIDER_ERROR", rsp_code: str | None = None):
        super().__init__(message, code=code)
        self.rsp_code = rsp_code


class KftcNetworkError(KftcClientError):
    def __init__(self, message: str = "KFTC network request failed", code: str = "KFTC_NETWORK_ERROR"):
        super().__init__(message, code=code)


def _validate_target_host(url: str, expected_environment: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise KftcClientError("HTTPS required for KFTC calls", code="KFTC_HTTPS_REQUIRED")

    allowed_base = get_kftc_host(expected_environment)
    expected_parts = urlsplit(allowed_base)
    if parts.netloc.lower() != expected_parts.netloc.lower():
        raise KftcClientError(
            f"Host {parts.netloc} not allowed for environment {expected_environment}",
            code="KFTC_OPENBANKING_HOST_NOT_ALLOWED",
        )


async def exchange_authorization_code(
    *,
    environment: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Exchange authorization code for access and refresh tokens.

    POST /oauth/2.0/token (grant_type=authorization_code)
    """
    host = get_kftc_host(environment)
    url = f"{host}/oauth/2.0/token"
    _validate_target_host(url, environment)

    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json",
    }

    own_client = client is None
    async_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(TOTAL_TIMEOUT, connect=CONNECT_TIMEOUT, read=READ_TIMEOUT),
        follow_redirects=False,
    )

    try:
        resp = await async_client.post(url, data=data, headers=headers)
    except httpx.RequestError as exc:
        logger.warning("KFTC token request network error: %s", type(exc).__name__)
        raise KftcNetworkError("Failed to reach KFTC token endpoint") from exc
    finally:
        if own_client:
            await async_client.aclose()

    try:
        body = resp.json()
    except Exception as exc:
        logger.warning("KFTC token response malformed JSON, HTTP status=%d", resp.status_code)
        raise KftcProviderError("Malformed response from KFTC token endpoint", code="MALFORMED_JSON") from exc

    if not isinstance(body, dict):
        raise KftcProviderError("Invalid JSON structure from KFTC token endpoint", code="MALFORMED_JSON")

    if resp.status_code != 200:
        raw_error = str(body.get("error") or body.get("rsp_code") or "").strip().lower()
        if raw_error == "invalid_client":
            sanitized_code = "INVALID_CLIENT"
        elif raw_error == "invalid_grant":
            sanitized_code = "INVALID_GRANT"
        elif raw_error in {"unauthorized_client", "access_denied", "unsupported_response_type", "invalid_scope", "server_error", "temporarily_unavailable"}:
            sanitized_code = f"OAUTH_ERROR_{raw_error.upper()}"
        elif raw_error:
            sanitized_code = "OAUTH_ERROR"
        else:
            sanitized_code = "HTTP_ERROR"

        logger.warning("KFTC token request returned HTTP %d, error %s", resp.status_code, sanitized_code)
        raise KftcAuthError("KFTC authorization code exchange rejected", code=sanitized_code)

    access_token = body.get("access_token")
    user_seq_no = body.get("user_seq_no")
    if not isinstance(access_token, str) or not access_token.strip() or not user_seq_no:
        raise KftcProviderError("Missing access_token or user_seq_no in KFTC response", code="MISSING_ACCESS_TOKEN")

    try:
        expires_in = int(body.get("expires_in", 0))
        if expires_in <= 0:
            raise ValueError("expires_in must be positive")
    except (TypeError, ValueError) as exc:
        raise KftcProviderError("Invalid expires_in value from KFTC", code="INVALID_EXPIRES_IN") from exc

    refresh_token = body.get("refresh_token")

    return {
        "access_token": access_token.strip(),
        "refresh_token": str(refresh_token).strip() if isinstance(refresh_token, str) and refresh_token.strip() else None,
        "user_seq_no": str(user_seq_no).strip(),
        "scope": str(body.get("scope", "login inquiry")).strip(),
        "expires_in": expires_in,
        "token_type": str(body.get("token_type", "Bearer")).strip(),
    }


async def refresh_access_token(
    *,
    environment: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    scope: str = "login inquiry",
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Refresh an access token using a refresh token.

    POST /oauth/2.0/token (grant_type=refresh_token)
    """
    host = get_kftc_host(environment)
    url = f"{host}/oauth/2.0/token"
    _validate_target_host(url, environment)

    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "scope": scope,
        "grant_type": "refresh_token",
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json",
    }

    own_client = client is None
    async_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(TOTAL_TIMEOUT, connect=CONNECT_TIMEOUT, read=READ_TIMEOUT),
        follow_redirects=False,
    )

    try:
        resp = await async_client.post(url, data=data, headers=headers)
    except httpx.RequestError as exc:
        logger.warning("KFTC token refresh network error: %s", type(exc).__name__)
        raise KftcNetworkError("Failed to reach KFTC token endpoint for refresh") from exc
    finally:
        if own_client:
            await async_client.aclose()

    try:
        body = resp.json()
    except Exception as exc:
        raise KftcProviderError("Malformed response from KFTC token refresh", code="MALFORMED_JSON") from exc

    if not isinstance(body, dict):
        raise KftcProviderError("Invalid JSON structure from KFTC token refresh", code="MALFORMED_JSON")

    if resp.status_code != 200:
        raw_error = str(body.get("error") or body.get("rsp_code") or "").strip().lower()
        if raw_error == "invalid_client":
            sanitized_code = "INVALID_CLIENT"
        elif raw_error == "invalid_grant":
            sanitized_code = "INVALID_GRANT"
        elif raw_error in {"unauthorized_client", "access_denied", "unsupported_response_type", "invalid_scope", "server_error", "temporarily_unavailable"}:
            sanitized_code = f"OAUTH_ERROR_{raw_error.upper()}"
        elif raw_error:
            sanitized_code = "OAUTH_ERROR"
        else:
            sanitized_code = "REFRESH_FAILED"

        logger.warning("KFTC token refresh returned HTTP %d, error %s", resp.status_code, sanitized_code)
        raise KftcAuthError("KFTC token refresh rejected", code=sanitized_code)

    access_token = body.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise KftcProviderError("Missing access_token in KFTC refresh response", code="MISSING_ACCESS_TOKEN")

    try:
        expires_in = int(body.get("expires_in", 0))
        if expires_in <= 0:
            raise ValueError("expires_in must be positive")
    except (TypeError, ValueError) as exc:
        raise KftcProviderError("Invalid expires_in value from KFTC refresh", code="INVALID_EXPIRES_IN") from exc

    new_refresh_token = body.get("refresh_token")

    return {
        "access_token": access_token.strip(),
        # If new refresh token is issued, take it; otherwise caller retains old refresh token
        "refresh_token": str(new_refresh_token).strip() if isinstance(new_refresh_token, str) and new_refresh_token.strip() else None,
        "user_seq_no": str(body.get("user_seq_no") or "").strip(),
        "scope": str(body.get("scope", scope)).strip(),
        "expires_in": expires_in,
        "token_type": str(body.get("token_type", "Bearer")).strip(),
    }


async def fetch_user_accounts(
    *,
    environment: str,
    access_token: str,
    user_seq_no: str,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Retrieve registered accounts list for an authenticated user.

    GET /v2.0/user/me?user_seq_no=...
    """
    host = get_kftc_host(environment)
    url = f"{host}/v2.0/user/me"
    _validate_target_host(url, environment)

    params = {"user_seq_no": user_seq_no}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }

    own_client = client is None
    async_client = client or httpx.AsyncClient(
        timeout=httpx.Timeout(TOTAL_TIMEOUT, connect=CONNECT_TIMEOUT, read=READ_TIMEOUT),
        follow_redirects=False,
    )

    try:
        resp = await async_client.get(url, params=params, headers=headers)
    except httpx.RequestError as exc:
        logger.warning("KFTC user/me network error: %s", type(exc).__name__)
        raise KftcNetworkError("Failed to reach KFTC user/me endpoint") from exc
    finally:
        if own_client:
            await async_client.aclose()

    try:
        body = resp.json()
    except Exception as exc:
        raise KftcProviderError("Malformed response from KFTC user/me", code="KFTC_USER_ME_INVALID") from exc

    if not isinstance(body, dict):
        raise KftcProviderError("Invalid response structure from KFTC user/me", code="KFTC_USER_ME_INVALID")

    if resp.status_code != 200:
        error_code = body.get("rsp_code") or "HTTP_ERROR"
        raise KftcProviderError("KFTC user/me request rejected", code=str(error_code), rsp_code=str(error_code))

    rsp_code = body.get("rsp_code")
    if rsp_code and rsp_code != "A0000":
        raise KftcProviderError(f"KFTC user/me error ({rsp_code})", code=str(rsp_code), rsp_code=str(rsp_code))

    res_list = body.get("res_list")
    if not isinstance(res_list, list):
        return []

    accounts = []
    for item in res_list:
        if not isinstance(item, dict):
            continue

        fintech_num = str(item.get("fintech_use_num") or "").strip()
        if not fintech_num:
            continue

        # ======================================================================
        # KFTC Open Banking Joint Work API Specification (v3.3.6):
        # Section: 2. 사용자정보조회 (/v2.0/user/me)
        # Table: [표 2-2] 사용자정보조회 응답 메시지 명세 (계좌목록 res_list 반복부)
        #
        # - account_state (계좌상태구분코드, 2자리 String):
        #     '01': 정상 (Active/Normal account available for inquiry)
        #     '02': 거래중지 (Dormant/Suspended account)
        #     '09': 해지 (Closed/Terminated account)
        #   Rule: Only '01' indicates an active account. Non-'01', empty, missing,
        #   or unknown accounts MUST fail closed and be excluded.
        #
        # - inquiry_agree_yn (조회동의여부, 1자리 String, 필수/Required):
        #     'Y': 동의 (User agreed to account inquiry)
        #     'N': 미동의 (User declined inquiry agreement)
        # ======================================================================
        account_state = str(item.get("account_state") or "").strip()
        if account_state != "01":
            continue

        # inquiry_agree_yn: 'Y' or 'N' (mandatory agreement flag)
        inquiry_agree_yn = str(item.get("inquiry_agree_yn") or "").strip().upper()
        if inquiry_agree_yn not in {"Y", "N"}:
            inquiry_agree_yn = "N"

        accounts.append({
            "fintech_use_num": fintech_num,
            "bank_code_std": str(item.get("bank_code_std") or "").strip(),
            "bank_name": str(item.get("bank_name") or "").strip(),
            "account_num_masked": str(item.get("account_num_masked") or "").strip(),
            "account_alias": str(item.get("account_alias") or "").strip(),
            "account_type": str(item.get("account_type") or "").strip(),
            "product_name": str(item.get("product_name") or "").strip(),
            "inquiry_agree_yn": inquiry_agree_yn,
        })

    return accounts
