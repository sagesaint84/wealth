"""User-scoped Kakao application credentials."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from app.services.settings import SettingsError, _path as settings_path, settings_lock


class KakaoAppSecretError(SettingsError):
    pass


def secret_path(username: str) -> Path:
    return settings_path(username).parent / "secrets" / "kakao_app.json"


def load_stored_kakao_app_secrets(
    username: str, *, path: Path | None = None
) -> dict[str, str]:
    target = path or secret_path(username)
    if not target.exists():
        return {"rest_api_key": "", "client_secret": ""}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise KakaoAppSecretError("KAKAO_APP_SECRET_STATE_INVALID") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"version", "rest_api_key", "client_secret"}
        or data.get("version") != 1
        or not isinstance(data.get("rest_api_key"), str)
        or not isinstance(data.get("client_secret"), str)
    ):
        raise KakaoAppSecretError("KAKAO_APP_SECRET_STATE_INVALID")
    return {
        "rest_api_key": data["rest_api_key"],
        "client_secret": data["client_secret"],
    }


def _save(data: dict[str, Any], target: Path) -> None:
    tmp = target.with_suffix(".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(target.parent, 0o700)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, allow_nan=False)
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


def _clean_secret(value: Any, code: str) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise KakaoAppSecretError(code)
    value = value.strip()
    if len(value) > 512:
        raise KakaoAppSecretError(code)
    return value


def update_kakao_app_secrets(
    username: str,
    patch: dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, str]:
    allowed = {
        "rest_api_key",
        "client_secret",
        "clear_rest_api_key",
        "clear_client_secret",
    }
    if not isinstance(patch, dict) or set(patch) - allowed:
        raise KakaoAppSecretError("INVALID_KAKAO_APP_SECRET_PATCH")
    target = path or secret_path(username)
    for attempt in range(100):
        try:
            with settings_lock(target):
                current = load_stored_kakao_app_secrets(username, path=target)
                if patch.get("rest_api_key") is not None:
                    value = _clean_secret(
                        patch["rest_api_key"], "INVALID_KAKAO_REST_API_KEY"
                    )
                    if value:
                        current["rest_api_key"] = value
                if patch.get("client_secret") is not None:
                    value = _clean_secret(
                        patch["client_secret"], "INVALID_KAKAO_CLIENT_SECRET"
                    )
                    if value:
                        current["client_secret"] = value
                if patch.get("clear_rest_api_key") is True:
                    current["rest_api_key"] = ""
                if patch.get("clear_client_secret") is True:
                    current["client_secret"] = ""
                _save({"version": 1, **current}, target)
            return current
        except SettingsError as exc:
            if str(exc) != "SETTINGS_ALREADY_RUNNING" or attempt == 99:
                raise
            time.sleep(0.01)
    raise KakaoAppSecretError("KAKAO_APP_SECRET_SAVE_FAILED")


def kakao_app_secret_status(username: str) -> dict[str, object]:
    stored = load_stored_kakao_app_secrets(username)
    rest = bool(stored["rest_api_key"])
    client = bool(stored["client_secret"])
    return {
        "rest_api_key_configured": rest,
        "rest_api_key_source": "stored" if rest else "none",
        "client_secret_configured": client,
        "client_secret_source": "stored" if client else "none",
    }
