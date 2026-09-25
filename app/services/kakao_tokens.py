"""User-scoped Kakao OAuth tokens.

Kakao access/refresh tokens are secrets.  They are stored only under the
authenticated Wealth user's private data directory and are never returned by
safe status helpers.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.settings import SettingsError, _path as settings_path, settings_lock

UTC = timezone.utc


class KakaoTokenError(SettingsError):
    pass


@dataclass(frozen=True)
class KakaoTokenState:
    access_token: str = field(default="", repr=False)
    refresh_token: str = field(default="", repr=False)
    access_expires_at: str | None = None
    refresh_expires_at: str | None = None
    scope: str | None = None
    updated_at: str | None = None

    @property
    def connected(self) -> bool:
        return bool(self.access_token or self.refresh_token)


def token_path(username: str) -> Path:
    return settings_path(username).parent / "secrets" / "kakao.json"


def _parse_time(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise KakaoTokenError("KAKAO_TOKEN_STATE_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise KakaoTokenError("KAKAO_TOKEN_STATE_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KakaoTokenError("KAKAO_TOKEN_STATE_INVALID")
    return parsed.astimezone(UTC).isoformat()


def load_kakao_tokens(username: str, *, path: Path | None = None) -> KakaoTokenState:
    target = path or token_path(username)
    if not target.exists():
        return KakaoTokenState()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise KakaoTokenError("KAKAO_TOKEN_STATE_INVALID") from exc
    required = {
        "version",
        "access_token",
        "refresh_token",
        "access_expires_at",
        "refresh_expires_at",
        "scope",
        "updated_at",
    }
    if (
        not isinstance(data, dict)
        or set(data) != required
        or data.get("version") != 1
        or not isinstance(data.get("access_token"), str)
        or not isinstance(data.get("refresh_token"), str)
        or data.get("scope") is not None
        and not isinstance(data.get("scope"), str)
        or data.get("updated_at") is not None
        and not isinstance(data.get("updated_at"), str)
    ):
        raise KakaoTokenError("KAKAO_TOKEN_STATE_INVALID")
    return KakaoTokenState(
        access_token=data["access_token"],
        refresh_token=data["refresh_token"],
        access_expires_at=_parse_time(data.get("access_expires_at")),
        refresh_expires_at=_parse_time(data.get("refresh_expires_at")),
        scope=data.get("scope"),
        updated_at=_parse_time(data.get("updated_at")),
    )


def _save(state: KakaoTokenState, target: Path) -> None:
    payload = {
        "version": 1,
        "access_token": state.access_token,
        "refresh_token": state.refresh_token,
        "access_expires_at": state.access_expires_at,
        "refresh_expires_at": state.refresh_expires_at,
        "scope": state.scope,
        "updated_at": state.updated_at,
    }
    tmp = target.with_suffix(".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(target.parent, 0o700)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(50):
            try:
                os.replace(tmp, target)
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)
        if os.name == "posix":
            os.chmod(target, 0o600)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def save_kakao_token_response(
    username: str,
    response: dict[str, Any],
    *,
    now: datetime | None = None,
    preserve_refresh: KakaoTokenState | None = None,
    path: Path | None = None,
) -> KakaoTokenState:
    if not isinstance(response, dict):
        raise KakaoTokenError("KAKAO_TOKEN_RESPONSE_INVALID")
    access = response.get("access_token")
    expires_in = response.get("expires_in")
    if not isinstance(access, str) or not access or type(expires_in) is not int or expires_in <= 0:
        raise KakaoTokenError("KAKAO_TOKEN_RESPONSE_INVALID")
    current = preserve_refresh or KakaoTokenState()
    refresh = response.get("refresh_token", current.refresh_token)
    if not isinstance(refresh, str):
        raise KakaoTokenError("KAKAO_TOKEN_RESPONSE_INVALID")
    refresh_seconds = response.get("refresh_token_expires_in")
    if refresh_seconds is not None and (type(refresh_seconds) is not int or refresh_seconds <= 0):
        raise KakaoTokenError("KAKAO_TOKEN_RESPONSE_INVALID")
    scope = response.get("scope", current.scope)
    if scope is not None and not isinstance(scope, str):
        raise KakaoTokenError("KAKAO_TOKEN_RESPONSE_INVALID")

    base = now or datetime.now(UTC)
    if base.tzinfo is None or base.utcoffset() is None:
        raise KakaoTokenError("KAKAO_TOKEN_TIME_INVALID")
    base = base.astimezone(UTC)
    refresh_expiry = (
        (base + timedelta(seconds=refresh_seconds)).isoformat()
        if refresh_seconds is not None
        else current.refresh_expires_at
    )
    state = KakaoTokenState(
        access_token=access,
        refresh_token=refresh,
        access_expires_at=(base + timedelta(seconds=expires_in)).isoformat(),
        refresh_expires_at=refresh_expiry,
        scope=scope,
        updated_at=base.isoformat(),
    )
    target = path or token_path(username)
    for attempt in range(100):
        try:
            with settings_lock(target):
                _save(state, target)
            break
        except SettingsError as exc:
            if str(exc) != "SETTINGS_ALREADY_RUNNING" or attempt == 99:
                raise
            time.sleep(0.01)
    return state


def clear_kakao_tokens(username: str, *, path: Path | None = None) -> None:
    target = path or token_path(username)
    for attempt in range(100):
        try:
            with settings_lock(target):
                try:
                    target.unlink(missing_ok=True)
                except OSError as exc:
                    raise KakaoTokenError("KAKAO_TOKEN_CLEAR_FAILED") from exc
            return
        except SettingsError as exc:
            if str(exc) != "SETTINGS_ALREADY_RUNNING" or attempt == 99:
                raise
            time.sleep(0.01)


def token_status(username: str) -> dict[str, object]:
    state = load_kakao_tokens(username)
    return {
        "connected": state.connected,
        "access_expires_at": state.access_expires_at,
        "refresh_expires_at": state.refresh_expires_at,
        "scope": state.scope,
        "updated_at": state.updated_at,
    }
