"""User-scoped KRX Data Marketplace credentials.

KRX login credentials are stored only inside the current user's isolated Wealth
data directory. They are never read from environment variables and the password
is never returned by status APIs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.secure_files import atomic_write_private_json
from app.services.user_manager import get_user_data_dir


_VERSION = 1


def credential_path(username: str) -> Path:
    return get_user_data_dir(username) / "secrets" / "krx_marketplace.json"


def load_user_krx_credentials(username: str, *, path: Path | None = None) -> dict[str, str]:
    target = path or credential_path(username)
    if not target.exists():
        return {"login_id": "", "password": ""}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("KRX_CREDENTIAL_STATE_INVALID") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("version") != _VERSION
        or not isinstance(payload.get("login_id"), str)
        or not isinstance(payload.get("password"), str)
    ):
        raise ValueError("KRX_CREDENTIAL_STATE_INVALID")
    return {
        "login_id": payload["login_id"].strip(),
        "password": payload["password"],
    }


def save_user_krx_credentials(
    username: str,
    patch: dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, object]:
    if not isinstance(patch, dict) or set(patch) - {"login_id", "password"}:
        raise ValueError("KRX_CREDENTIAL_PATCH_INVALID")
    current = load_user_krx_credentials(username, path=path)

    if "login_id" in patch:
        value = patch["login_id"]
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError("KRX_LOGIN_ID_INVALID")
        value = value.strip()
        if value and "*" not in value:
            current["login_id"] = value

    if "password" in patch:
        value = patch["password"]
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError("KRX_PASSWORD_INVALID")
        value = value.strip()
        if value and value != "********":
            current["password"] = value

    target = path or credential_path(username)
    atomic_write_private_json(target, {"version": _VERSION, **current}, indent=2)
    return krx_credential_status(username, path=target)


def clear_user_krx_credentials(username: str, *, path: Path | None = None) -> None:
    target = path or credential_path(username)
    target.unlink(missing_ok=True)


def krx_credential_status(username: str, *, path: Path | None = None) -> dict[str, object]:
    stored = load_user_krx_credentials(username, path=path)
    login_id = stored["login_id"]
    configured = bool(login_id and stored["password"])
    if login_id:
        prefix = login_id[:4] if len(login_id) >= 4 else login_id[:1]
        masked_id = f"{prefix}****"
    else:
        masked_id = ""
    return {
        "login_id": masked_id,
        "login_id_configured": bool(login_id),
        "password_configured": bool(stored["password"]),
        "configured": configured,
        "source": "user" if configured else "unconfigured",
    }
