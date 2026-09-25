"""Kakao OAuth helpers for per-user Kakao Talk self-message integration."""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib import error, parse, request

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.services.kakao_app_secrets import (
    kakao_app_secret_status,
    load_stored_kakao_app_secrets,
)
from app.services.kakao_tokens import (
    KakaoTokenState,
    load_kakao_tokens,
    save_kakao_token_response,
    token_status,
)
from app.services.system_secrets import resolve_application_secret
from app.services.system_settings import get_effective_system_settings
from app.services.user_manager import get_user_by_name

UTC = timezone.utc
AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
CALLBACK_PATH = "/api/integrations/kakao/oauth/callback"
STATE_MAX_AGE_SECONDS = 600
ACCESS_REFRESH_SKEW_SECONDS = 60


class KakaoOAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class KakaoAppConfig:
    rest_api_key: str | None = field(default=None, repr=False)
    client_secret: str | None = field(default=None, repr=False)
    public_base_url: str | None = None

    @property
    def redirect_uri(self) -> str | None:
        return f"{self.public_base_url}{CALLBACK_PATH}" if self.public_base_url else None

    @property
    def app_configured(self) -> bool:
        return bool(self.rest_api_key and self.redirect_uri)


def resolve_kakao_app_config(username: str) -> KakaoAppConfig:
    system = get_effective_system_settings()
    stored = load_stored_kakao_app_secrets(username)
    return KakaoAppConfig(
        rest_api_key=stored["rest_api_key"] or None,
        client_secret=stored["client_secret"] or None,
        public_base_url=system.get("public_base_url"),
    )


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        resolve_application_secret(),
        salt="wealth-kakao-oauth-state-v1",
    )


def create_oauth_state(username: str) -> str:
    if not get_user_by_name(username):
        raise KakaoOAuthError("KAKAO_USER_NOT_FOUND")
    return _state_serializer().dumps(
        {"username": username, "nonce": secrets.token_urlsafe(24)}
    )


def consume_oauth_state(state: str) -> str:
    if not isinstance(state, str) or not state:
        raise KakaoOAuthError("KAKAO_OAUTH_STATE_INVALID")
    try:
        payload = _state_serializer().loads(state, max_age=STATE_MAX_AGE_SECONDS)
    except SignatureExpired as exc:
        raise KakaoOAuthError("KAKAO_OAUTH_STATE_EXPIRED") from exc
    except BadSignature as exc:
        raise KakaoOAuthError("KAKAO_OAUTH_STATE_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("username"), str)
        or not isinstance(payload.get("nonce"), str)
        or not payload["nonce"]
        or not get_user_by_name(payload["username"])
    ):
        raise KakaoOAuthError("KAKAO_OAUTH_STATE_INVALID")
    return payload["username"]


def build_authorize_url(username: str) -> str:
    config = resolve_kakao_app_config(username)
    if not config.rest_api_key:
        raise KakaoOAuthError("KAKAO_APP_NOT_CONFIGURED")
    if not config.redirect_uri:
        raise KakaoOAuthError("PUBLIC_BASE_URL_REQUIRED")
    query = parse.urlencode(
        {
            "response_type": "code",
            "client_id": config.rest_api_key,
            "redirect_uri": config.redirect_uri,
            "state": create_oauth_state(username),
            "scope": "talk_message",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def _token_request(
    username: str,
    payload: dict[str, str],
    *,
    opener=request.urlopen,
    timeout: float = 10.0,
) -> dict:
    config = resolve_kakao_app_config()
    if not config.rest_api_key:
        raise KakaoOAuthError("KAKAO_APP_NOT_CONFIGURED")
    form = {**payload, "client_id": config.rest_api_key}
    if config.client_secret:
        form["client_secret"] = config.client_secret
    req = request.Request(
        TOKEN_URL,
        data=parse.urlencode(form).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
            "User-Agent": "Wealth-Kakao/1.0",
        },
        method="POST",
    )
    try:
        with opener(req, timeout=timeout) as response:
            raw = response.read()
    except error.HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        raise KakaoOAuthError(
            "KAKAO_OAUTH_REJECTED" if 400 <= code < 500 else "KAKAO_OAUTH_UNAVAILABLE"
        ) from exc
    except Exception as exc:
        raise KakaoOAuthError("KAKAO_OAUTH_UNAVAILABLE") from exc
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise KakaoOAuthError("KAKAO_OAUTH_RESPONSE_INVALID") from exc
    if not isinstance(result, dict):
        raise KakaoOAuthError("KAKAO_OAUTH_RESPONSE_INVALID")
    return result


def exchange_authorization_code(
    username: str,
    code: str,
    *,
    opener=request.urlopen,
    now: datetime | None = None,
) -> KakaoTokenState:
    config = resolve_kakao_app_config()
    if not config.redirect_uri:
        raise KakaoOAuthError("PUBLIC_BASE_URL_REQUIRED")
    if not isinstance(code, str) or not code:
        raise KakaoOAuthError("KAKAO_AUTHORIZATION_CODE_INVALID")
    result = _token_request(
        username,
        {
            "grant_type": "authorization_code",
            "redirect_uri": config.redirect_uri,
            "code": code,
        },
        opener=opener,
    )
    try:
        return save_kakao_token_response(username, result, now=now)
    except Exception as exc:
        if isinstance(exc, KakaoOAuthError):
            raise
        raise KakaoOAuthError("KAKAO_TOKEN_SAVE_FAILED") from exc


def refresh_kakao_tokens(
    username: str,
    *,
    opener=request.urlopen,
    now: datetime | None = None,
) -> KakaoTokenState:
    current = load_kakao_tokens(username)
    if not current.refresh_token:
        raise KakaoOAuthError("KAKAO_REFRESH_TOKEN_MISSING")
    result = _token_request(
        username,
        {
            "grant_type": "refresh_token",
            "refresh_token": current.refresh_token,
        },
        opener=opener,
    )
    try:
        return save_kakao_token_response(
            username,
            result,
            now=now,
            preserve_refresh=current,
        )
    except Exception as exc:
        raise KakaoOAuthError("KAKAO_TOKEN_SAVE_FAILED") from exc


def get_valid_access_token(
    username: str,
    *,
    opener=request.urlopen,
    now: datetime | None = None,
) -> str:
    current = load_kakao_tokens(username)
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    if current.access_token and current.access_expires_at:
        try:
            expires = datetime.fromisoformat(
                current.access_expires_at.replace("Z", "+00:00")
            ).astimezone(UTC)
        except ValueError:
            expires = current_time
        if expires > current_time + timedelta(seconds=ACCESS_REFRESH_SKEW_SECONDS):
            return current.access_token
    elif current.access_token and not current.refresh_token:
        return current.access_token

    refreshed = refresh_kakao_tokens(username, opener=opener, now=current_time)
    if not refreshed.access_token:
        raise KakaoOAuthError("KAKAO_ACCESS_TOKEN_MISSING")
    return refreshed.access_token


def safe_kakao_status(username: str) -> dict[str, object]:
    config = resolve_kakao_app_config()
    status = token_status(username)
    return {
        "app_configured": config.app_configured,
        "client_secret_configured": bool(config.client_secret),
        "public_base_url_configured": bool(config.public_base_url),
        "redirect_uri": config.redirect_uri,
        **status,
    }
