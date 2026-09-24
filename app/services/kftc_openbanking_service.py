"""Service orchestration for KFTC Open Banking Phase 1.

Orchestrates:
- Authorization Code grant URL generation with state binding
- OAuth callback verification and token exchange
- Token refresh
- Status inquiry
- Disconnection
- Account discovery and mapped storage
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx

from app.services.kftc_openbanking_client import (
    KftcAuthError,
    KftcClientError,
    KftcNetworkError,
    KftcProviderError,
    exchange_authorization_code,
    fetch_account_balance,
    fetch_user_accounts,
    refresh_access_token,
)
from app.services.kftc_openbanking_config import (
    KftcConfigError,
    get_effective_kftc_config,
    get_kftc_callback_url,
    get_kftc_host,
    is_user_allowed_kftc,
)
from app.services.kftc_openbanking_storage import (
    KftcStorageError,
    consume_oauth_state,
    disconnect_user_kftc,
    get_decrypted_user_tokens,
    int_to_base36_9,
    load_user_kftc_accounts,
    load_user_token_status,
    next_bank_tran_sequence,
    resolve_fintech_use_num,
    save_oauth_state,
    save_user_kftc_accounts,
    save_user_tokens,
)

logger = logging.getLogger(__name__)

DEFAULT_SCOPE = "login inquiry"


class KftcServiceError(Exception):
    def __init__(self, message: str, code: str = "KFTC_SERVICE_ERROR"):
        super().__init__(message)
        self.code = code


def compute_session_fingerprint(session_cookie: str | None) -> str:
    """Derive a privacy-preserving session binding token from the active session cookie."""
    if not session_cookie:
        return "no_session"
    return hashlib.sha256(session_cookie.encode("utf-8")).hexdigest()[:32]


def start_oauth_flow(
    username: str,
    *,
    session_id: str,
    scope: str = DEFAULT_SCOPE,
    auth_type: str = "0",
) -> dict[str, str]:
    """Prepare authorize URL and save bound OAuth state.

    Scope is strictly controlled on the server: Phase 1 only allows DEFAULT_SCOPE ('login inquiry').
    """
    # 1. Enforce strict server-controlled scope allowlist (prevent privilege escalation)
    normalized_scope = " ".join(str(scope or "").strip().split())
    if normalized_scope != DEFAULT_SCOPE:
        logger.warning("Rejected non-default OAuth scope '%s' for user %s", scope, username)
        raise KftcServiceError("Invalid or forbidden OAuth scope requested", code="KFTC_SCOPE_FORBIDDEN")

    # 2. Check feature gate & user allowance
    if not is_user_allowed_kftc(username):
        raise KftcServiceError(f"User {username} is not permitted to use KFTC Open Banking", code="KFTC_NOT_ALLOWED")

    # 3. Retrieve config
    config = get_effective_kftc_config(username)
    client_id = config.get("client_id")
    if not client_id:
        raise KftcServiceError("KFTC Client ID is not configured", code="KFTC_NOT_CONFIGURED")

    environment = config["environment"]
    host = get_kftc_host(environment)

    # 4. Generate callback URL
    try:
        redirect_uri = get_kftc_callback_url()
    except KftcConfigError as exc:
        raise KftcServiceError(str(exc), code="PUBLIC_BASE_URL_REQUIRED") from exc

    # 5. Generate CSPRNG state and persist binding
    # KFTC OAuth 2.0 authorization specification: state is a 32-character string.
    # secrets.token_hex(16) produces exactly 32 hexadecimal characters with 128-bit entropy.
    state = secrets.token_hex(16)
    save_oauth_state(username, state=state, session_id=session_id, ttl_seconds=600)

    # 6. Build authorize query parameters per KFTC OAuth 2.0 Authorization Code Grant specification
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": DEFAULT_SCOPE,
        "state": state,
        "auth_type": auth_type,  # 0: 최초인증 / 일반
    }

    authorize_url = f"{host}/oauth/2.0/authorize?{urlencode(params)}"
    return {
        "authorize_url": authorize_url,
        "state": state,
    }


async def handle_oauth_callback(
    username: str,
    *,
    session_id: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Handle callback from KFTC, validate state, and exchange authorization code."""
    # 1. Provider error check
    if error:
        logger.warning("KFTC callback received error: %s", error)
        raise KftcServiceError(f"KFTC authorization denied: {error}", code=f"KFTC_AUTH_ERROR_{error}")

    if not code:
        raise KftcServiceError("Missing authorization code in callback", code="KFTC_MISSING_AUTH_CODE")

    if not state:
        raise KftcServiceError("Missing state in callback", code="KFTC_MISSING_STATE")

    # 2. Check user allowance
    if not is_user_allowed_kftc(username):
        raise KftcServiceError("User is not allowed to use KFTC Open Banking", code="KFTC_NOT_ALLOWED")

    # 3. Validate and atomically consume state (CSRF & Replay prevention)
    valid_state = consume_oauth_state(username, state=state, session_id=session_id)
    if not valid_state:
        logger.warning("KFTC callback state invalid, expired, or mismatch for user %s", username)
        raise KftcServiceError("Invalid, expired, or already used OAuth state", code="KFTC_STATE_INVALID")

    # 4. Exchange authorization code for tokens
    config = get_effective_kftc_config(username)
    client_id = config.get("client_id")
    client_secret = config.get("client_secret")
    environment = config["environment"]

    if not client_id or not client_secret:
        raise KftcServiceError("KFTC credentials are not configured", code="KFTC_NOT_CONFIGURED")

    redirect_uri = get_kftc_callback_url()

    token_data = await exchange_authorization_code(
        environment=environment,
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
        client=client,
    )

    # 5. Encrypt and safely persist tokens
    save_user_tokens(
        username,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        user_seq_no=token_data["user_seq_no"],
        scope=token_data.get("scope", DEFAULT_SCOPE),
        expires_in=token_data["expires_in"],
    )

    logger.info("Successfully connected KFTC Open Banking for user %s", username)

    # 6. Try initial account discovery immediately
    try:
        await refresh_and_sync_accounts(username, client=client)
    except Exception as exc:
        logger.warning("Initial account discovery after token exchange failed for %s: %s", username, exc)

    return {"connected": True}


async def refresh_user_token(
    username: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Refresh the user's access token using their stored refresh token."""
    if not is_user_allowed_kftc(username):
        raise KftcServiceError("User is not allowed to use KFTC Open Banking", code="KFTC_NOT_ALLOWED")

    tokens = get_decrypted_user_tokens(username)
    refresh_tok = tokens.get("refresh_token")
    if not refresh_tok:
        raise KftcServiceError("No refresh token available; re-authentication required", code="REAUTH_REQUIRED")

    config = get_effective_kftc_config(username)
    client_id = config.get("client_id")
    client_secret = config.get("client_secret")
    environment = config["environment"]

    if not client_id or not client_secret:
        raise KftcServiceError("KFTC credentials are not configured", code="KFTC_NOT_CONFIGURED")

    scope = tokens.get("scope") or DEFAULT_SCOPE

    new_token_data = await refresh_access_token(
        environment=environment,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_tok,
        scope=scope,
        client=client,
    )

    # Retain old refresh token if not replaced
    active_refresh = new_token_data.get("refresh_token") or refresh_tok
    user_seq = new_token_data.get("user_seq_no") or tokens.get("user_seq_no") or ""

    save_user_tokens(
        username,
        access_token=new_token_data["access_token"],
        refresh_token=active_refresh,
        user_seq_no=user_seq,
        scope=new_token_data.get("scope", scope),
        expires_in=new_token_data["expires_in"],
    )

    logger.info("Successfully refreshed KFTC Open Banking token for user %s", username)
    return load_user_token_status(username)


async def refresh_and_sync_accounts(
    username: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """Fetch user's registered bank accounts from KFTC and persist encrypted mapping."""
    if not is_user_allowed_kftc(username):
        raise KftcServiceError("User is not allowed to use KFTC Open Banking", code="KFTC_NOT_ALLOWED")

    tokens = get_decrypted_user_tokens(username)
    access_tok = tokens.get("access_token")
    user_seq = tokens.get("user_seq_no")

    if not access_tok or not user_seq:
        raise KftcServiceError("Valid tokens required for account discovery", code="NOT_CONNECTED")

    config = get_effective_kftc_config(username)
    environment = config["environment"]

    raw_accounts = await fetch_user_accounts(
        environment=environment,
        access_token=access_tok,
        user_seq_no=user_seq,
        client=client,
    )

    # Generate stable local IDs based on bank_code + masked number or fintech_use_num hash
    prepared = []
    for item in raw_accounts:
        fintech_num = item["fintech_use_num"]
        local_id_hash = hashlib.sha256(f"kftc:{username}:{fintech_num}".encode("utf-8")).hexdigest()[:16]
        provider_account_id = f"kftc-{local_id_hash}"

        prepared.append({
            "provider_account_id": provider_account_id,
            "fintech_use_num": fintech_num,
            "bank_code_std": item.get("bank_code_std", ""),
            "bank_name": item.get("bank_name", ""),
            "account_num_masked": item.get("account_num_masked", ""),
            "account_alias": item.get("account_alias", ""),
            "account_type": item.get("account_type", ""),
            "product_name": item.get("product_name", ""),
            "inquiry_agree_yn": item.get("inquiry_agree_yn", "N"),
        })

    save_user_kftc_accounts(username, prepared)
    logger.info("Synchronized %d KFTC accounts for user %s", len(prepared), username)
    return load_user_kftc_accounts(username)


def get_user_kftc_status(username: str) -> dict[str, Any]:
    """Build safe metadata status dictionary for frontend /api/kftc/openbanking/status."""
    config = get_effective_kftc_config(username)
    allowed = is_user_allowed_kftc(username)
    configured = bool(config.get("client_id") and config.get("client_secret"))
    environment = config.get("environment", "test")

    cb_url = None
    pub_ready = False
    try:
        cb_url = get_kftc_callback_url()
        pub_ready = True
    except Exception:
        pass

    token_meta = load_user_token_status(username)
    accounts = load_user_kftc_accounts(username) if token_meta.get("connected") else []

    return {
        "enabled": config.get("enabled", False),
        "environment": environment,
        "is_testbed": environment == "test",
        "allowed": allowed,
        "configured": configured,
        "public_base_url_ready": pub_ready,
        "callback_url": cb_url,
        "connected": token_meta.get("connected", False),
        "token_status": token_meta.get("status", "unconnected"),
        "scope": token_meta.get("scope", []),
        "expires_at": token_meta.get("expires_at"),
        "expires_in": token_meta.get("expires_in"),
        "connected_at": token_meta.get("connected_at"),
        "refreshed_at": token_meta.get("refreshed_at"),
        "account_count": len(accounts),
    }


def disconnect_kftc(username: str) -> None:
    """Disconnect and clean up local KFTC state for user."""
    disconnect_user_kftc(username)
    logger.info("Disconnected KFTC Open Banking for user %s", username)


# ==============================================================================
# Phase 2-A: Read-Only Balance Inquiry Preview
# ==============================================================================

ACCOUNT_TYPE_LABELS = {
    "1": "수시입출금",
    "2": "예적금",
    "6": "수익증권",
}


def generate_tran_dtime() -> str:
    """Generate 14-character request timestamp YYYYMMDDhhmmss.

    Note on Timezone:
    The KFTC Open Banking API specification (v3.3.6) defines tran_dtime as N(14)
    format YYYYMMDDhhmmss without specifying a timezone offset.
    Formatting with Asia/Seoul (UTC+9) is an implementation convention matching
    the operational environment of KFTC and participant financial institutions.
    """
    seoul_tz = ZoneInfo("Asia/Seoul")
    now_seoul = datetime.now(seoul_tz)
    return now_seoul.strftime("%Y%m%d%H%M%S")


def generate_bank_tran_id(client_use_code: str, *, tran_date: str | None = None) -> str:
    """Generate 20-character unique bank transaction ID per KFTC v3.3.6 specification.

    Structure per KFTC Open Banking API specification (v3.3.6):
    - client_use_code: 이용기관코드 AN(10) (10 alphanumeric characters)
    - request type: 'U' (고객의뢰) 1 char
    - 이용기관 부여번호: 9 characters (영숫자 9자리, 당일 00:00~24:00 동안 중복 없는 고유 번호)
    Total length MUST be exactly 20 characters: AN(10) + 'U' + AN(9) = AN(20).

    Day-scoped Uniqueness:
    Guaranteed via persistent monotonically increasing base-36 sequence scoped by
    (client_use_code, YYYYMMDD date). Persisted in data/system/kftc_bank_tran_sequence.json
    under cross-process and thread locks.
    """
    code = str(client_use_code or "").strip().upper()
    if not code:
        raise KftcServiceError("이용기관코드가 설정되어 있지 않습니다.", code="KFTC_CLIENT_USE_CODE_REQUIRED")

    if len(code) != 10 or not code.isalnum():
        raise KftcServiceError("이용기관코드 길이가 유효하지 않습니다 (영숫자 10자리 필수).", code="KFTC_CLIENT_USE_CODE_INVALID")

    # Determine calendar date in Asia/Seoul (KFTC business day convention)
    if tran_date:
        date_str = str(tran_date).strip()
    else:
        seoul_tz = ZoneInfo("Asia/Seoul")
        date_str = datetime.now(seoul_tz).strftime("%Y%m%d")

    try:
        seq_num = next_bank_tran_sequence(code, date_str)
        suffix = int_to_base36_9(seq_num)
    except KftcStorageError as exc:
        raise KftcServiceError(f"거래고유번호 채번 실패: {exc}", code="BANK_TRAN_ID_EXHAUSTED") from exc

    return f"{code}U{suffix}"


async def preview_account_balance(
    username: str,
    provider_account_id: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Inquire account balance from KFTC in read-only preview mode.

    Zero mutation:
    - Does NOT mutate bank_accounts, portfolio, ledger, or balance records.
    - Resolves encrypted fintech_use_num internally.
    - Validates token, scope, user allowance, and client_use_code.
    - Automatic token refresh: on 401 or token expired error, refreshes token at most once
      and retries balance inquiry at most once. No recursion or infinite loops.
    """
    # 1. Feature gate check
    if not is_user_allowed_kftc(username):
        raise KftcServiceError("User is not allowed to use KFTC Open Banking", code="KFTC_NOT_ALLOWED")

    # 2. Token status and inquiry scope verification
    token_status = load_user_token_status(username)
    if not token_status.get("connected"):
        raise KftcServiceError("KFTC 오픈뱅킹이 연결되어 있지 않습니다.", code="NOT_CONNECTED")
    if token_status.get("status") == "reauth_required":
        raise KftcServiceError("KFTC 재인증이 필요합니다.", code="REAUTH_REQUIRED")

    # If already marked expired locally, attempt proactive 1-time refresh
    if token_status.get("status") == "expired":
        logger.info("Access token expired locally for %s; attempting refresh before balance preview", username)
        try:
            await refresh_user_token(username, client=client)
            token_status = load_user_token_status(username)
        except Exception as exc:
            logger.warning("Token refresh failed for expired token user %s: %s", username, exc)
            raise KftcServiceError("KFTC 인증 토큰이 만료되었으며 갱신에 실패했습니다. 다시 연결하세요.", code="TOKEN_EXPIRED") from exc

    # Scope check: live token scope may be "login inquiry" or "inquiry login"
    scopes = set(token_status.get("scope", []))
    if "inquiry" not in scopes:
        raise KftcServiceError("조회(inquiry) 권한이 없는 토큰입니다. 다시 동의 연결하세요.", code="KFTC_SCOPE_INSUFFICIENT")

    # 3. Resolve user's effective config
    config = get_effective_kftc_config(username)
    client_use_code = config.get("client_use_code")
    if not client_use_code:
        raise KftcServiceError("이용기관코드가 설정되어 있지 않습니다. OpenAPI 설정에서 등록하세요.", code="KFTC_CLIENT_USE_CODE_REQUIRED")

    # 4. Resolve fintech_use_num
    try:
        fintech_use_num = resolve_fintech_use_num(username, provider_account_id)
    except KftcStorageError as exc:
        raise KftcServiceError("해당 오픈뱅킹 계좌를 찾을 수 없습니다.", code=exc.code) from exc

    # 5. Fetch decrypted access token
    try:
        tokens = get_decrypted_user_tokens(username)
    except KftcStorageError as exc:
        raise KftcServiceError("토큰 복호화에 실패했습니다. 다시 연결하세요.", code=exc.code) from exc

    access_token = tokens.get("access_token")
    if not access_token:
        raise KftcServiceError("유효한 access_token이 없습니다.", code="NOT_CONNECTED")

    # 6. Execute balance inquiry HTTP request with at most 1-time retry on 401
    max_attempts = 2
    raw_balance: dict[str, Any] | None = None

    for attempt in range(1, max_attempts + 1):
        bank_tran_id = generate_bank_tran_id(client_use_code)
        tran_dtime = generate_tran_dtime()

        try:
            raw_balance = await fetch_account_balance(
                environment=config["environment"],
                access_token=access_token,
                fintech_use_num=fintech_use_num,
                bank_tran_id=bank_tran_id,
                tran_dtime=tran_dtime,
                client=client,
            )
            break
        except KftcProviderError as exc:
            # Check for token expiration / unauthorized indicator (401 or A0002 / OAUTH_ERROR / 401)
            is_unauthorized = (
                exc.code in {"401", "A0002", "UNAUTHORIZED", "INVALID_TOKEN", "TOKEN_EXPIRED"}
                or exc.rsp_code in {"401", "A0002"}
            )
            if is_unauthorized and attempt < max_attempts:
                logger.info("Balance inquiry for %s received %s; refreshing token and retrying once", username, exc.code)
                try:
                    await refresh_user_token(username, client=client)
                    refreshed_tokens = get_decrypted_user_tokens(username)
                    access_token = refreshed_tokens.get("access_token")
                    if not access_token:
                        raise KftcServiceError("토큰 갱신 후 access_token이 없습니다.", code="NOT_CONNECTED")
                    continue
                except KftcServiceError:
                    raise
                except Exception as refresh_exc:
                    logger.warning("Token refresh attempt failed for %s during 401 retry: %s", username, refresh_exc)
                    raise KftcServiceError("토큰 만료 후 재발급에 실패했습니다. 다시 연결하세요.", code="TOKEN_EXPIRED") from refresh_exc

            logger.warning("KFTC balance inquiry failed for user %s: code=%s", username, exc.code)
            raise KftcServiceError(f"잔액 조회 실패: {exc.code}", code=exc.code) from exc
        except KftcClientError as exc:
            logger.warning("KFTC client error during balance inquiry for user %s: code=%s", username, exc.code)
            raise KftcServiceError(f"잔액 조회 오류: {exc.code}", code=exc.code) from exc

    if raw_balance is None:
        raise KftcServiceError("잔액 정보를 가져올 수 없습니다.", code="BALANCE_INQUIRY_FAILED")

    # 7. Build sanitized preview response (strictly read-only, NO ledger/portfolio write)
    # Strictly excludes: fintech_use_num, bank_tran_id, api_tran_id, access_token, refresh_token, client_secret, user_seq_no
    account_type_raw = raw_balance.get("account_type", "")
    account_type_label = ACCOUNT_TYPE_LABELS.get(account_type_raw, "계좌")

    now_seoul = datetime.now(ZoneInfo("Asia/Seoul"))
    checked_at_iso = now_seoul.isoformat()

    return {
        "provider_account_id": provider_account_id,
        "bank_name": raw_balance.get("bank_name", ""),
        "product_name": raw_balance.get("product_name", ""),
        "account_num_masked": raw_balance.get("account_num_masked", ""),
        "account_type": account_type_raw,
        "account_type_label": account_type_label,
        "balance_amt": raw_balance["balance_amt"],
        "available_amt": raw_balance["available_amt"],
        "account_issue_date": raw_balance.get("account_issue_date"),
        "maturity_date": raw_balance.get("maturity_date"),
        "last_tran_date": raw_balance.get("last_tran_date"),
        "checked_at": checked_at_iso,
    }
