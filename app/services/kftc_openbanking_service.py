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
from typing import Any
from urllib.parse import urlencode

import httpx

from app.services.kftc_openbanking_client import (
    KftcAuthError,
    KftcClientError,
    KftcNetworkError,
    KftcProviderError,
    exchange_authorization_code,
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
    load_user_kftc_accounts,
    load_user_token_status,
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
    config = get_effective_kftc_config()
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
    config = get_effective_kftc_config()
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

    config = get_effective_kftc_config()
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

    config = get_effective_kftc_config()
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
    config = get_effective_kftc_config()
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
