"""External credentials and global configuration for KFTC Open Banking.

External credentials live strictly in data/system/external_credentials/kftc_openbanking.json,
isolated from internal signing secrets (app/services/system_secrets.py) and user configs.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.services.secure_files import atomic_write_private_json
from app.services.system_settings import (
    SystemSettingsError,
    get_effective_system_settings,
    normalize_public_base_url,
)

CONFIG_FILE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "system"
    / "external_credentials"
    / "kftc_openbanking.json"
)

PRODUCTION_HOST = "https://openapi.openbanking.or.kr"
TEST_HOST = "https://testapi.openbanking.or.kr"

ALLOWED_HOSTS: dict[str, str] = {
    "production": PRODUCTION_HOST,
    "test": TEST_HOST,
}

_CONFIG_KEYS = {
    "version",
    "enabled",
    "environment",
    "client_id",
    "client_secret",
    "client_use_code",
    "allowed_users",
}


class KftcConfigError(Exception):
    """Raised when KFTC Open Banking configuration is invalid or missing."""


def _target(path: Path | None = None) -> Path:
    root = os.getenv("WEALTH_DATA_DIR", "").strip()
    return (
        path
        or (
            (Path(root) / "system" / "external_credentials" / "kftc_openbanking.json")
            if root
            else CONFIG_FILE
        )
    )


def get_kftc_host(environment: str) -> str:
    """Strictly return allowed HTTPS host for environment or fail closed."""
    env_norm = str(environment or "").strip().lower()
    if env_norm not in ALLOWED_HOSTS:
        raise KftcConfigError("KFTC_OPENBANKING_HOST_NOT_ALLOWED")
    return ALLOWED_HOSTS[env_norm]


def _validate_stored_config(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise KftcConfigError("KFTC_CONFIG_INVALID")
    if set(data) - _CONFIG_KEYS:
        raise KftcConfigError("KFTC_CONFIG_INVALID")

    enabled = data.get("enabled", False)
    if type(enabled) is not bool:
        raise KftcConfigError("KFTC_CONFIG_INVALID")

    env = str(data.get("environment") or "test").strip().lower()
    if env not in ALLOWED_HOSTS:
        raise KftcConfigError("KFTC_ENVIRONMENT_INVALID")

    client_id = data.get("client_id")
    if client_id is not None and not isinstance(client_id, str):
        raise KftcConfigError("KFTC_CLIENT_ID_INVALID")
    client_id_val = client_id.strip() if isinstance(client_id, str) else ""

    client_secret = data.get("client_secret")
    if client_secret is not None and not isinstance(client_secret, str):
        raise KftcConfigError("KFTC_CLIENT_SECRET_INVALID")
    client_secret_val = client_secret.strip() if isinstance(client_secret, str) else ""

    client_use_code = data.get("client_use_code")
    if client_use_code is not None and not isinstance(client_use_code, str):
        raise KftcConfigError("KFTC_CLIENT_USE_CODE_INVALID")
    client_use_code_val = client_use_code.strip() if isinstance(client_use_code, str) else ""

    allowed_users = data.get("allowed_users", [])
    if not isinstance(allowed_users, list) or any(
        not isinstance(u, str) or not u.strip() or any(p in u for p in ("/", "\\", ".."))
        for u in allowed_users
    ) or len(set(allowed_users)) != len(allowed_users):
        raise KftcConfigError("KFTC_ALLOWED_USERS_INVALID")

    return {
        "version": 1,
        "enabled": enabled,
        "environment": env,
        "client_id": client_id_val,
        "client_secret": client_secret_val,
        "client_use_code": client_use_code_val,
        "allowed_users": [u.strip() for u in allowed_users],
    }


def load_kftc_config(*, path: Path | None = None) -> dict[str, Any] | None:
    p = _target(path)
    if not p.exists():
        return None
    try:
        return _validate_stored_config(json.loads(p.read_text(encoding="utf-8")))
    except KftcConfigError:
        raise
    except Exception as exc:
        raise KftcConfigError("KFTC_CONFIG_INVALID") from exc


def get_effective_kftc_config(*, path: Path | None = None) -> dict[str, Any]:
    """Resolve stored external credentials, falling back to environment variables.

    Precedence: stored config > environment fallback.
    """
    stored = load_kftc_config(path=path)

    env_enabled_raw = os.getenv("KFTC_OPENBANKING_ENABLED")
    env_enabled = False
    if env_enabled_raw is not None and env_enabled_raw.strip():
        norm = env_enabled_raw.strip().lower()
        if norm in {"1", "true", "yes", "on"}:
            env_enabled = True
        elif norm in {"0", "false", "no", "off"}:
            env_enabled = False
        else:
            raise KftcConfigError("KFTC_CONFIG_INVALID")

    env_environment = os.getenv("KFTC_OPENBANKING_ENVIRONMENT", "test").strip().lower()
    if env_environment not in ALLOWED_HOSTS:
        env_environment = "test"

    env_client_id = os.getenv("KFTC_OPENBANKING_CLIENT_ID", "").strip()
    env_client_secret = os.getenv("KFTC_OPENBANKING_CLIENT_SECRET", "").strip()
    env_client_use_code = os.getenv("KFTC_OPENBANKING_CLIENT_USE_CODE", "").strip()
    env_allowed_raw = os.getenv("KFTC_OPENBANKING_ALLOWED_USERS", "").strip()
    env_allowed = [u.strip() for u in env_allowed_raw.split(",") if u.strip()] if env_allowed_raw else []

    if stored is not None:
        return {
            "version": 1,
            "enabled": stored["enabled"],
            "environment": stored["environment"],
            "client_id": stored["client_id"] or env_client_id,
            "client_secret": stored["client_secret"] or env_client_secret,
            "client_use_code": stored["client_use_code"] or env_client_use_code,
            "allowed_users": stored["allowed_users"] or env_allowed,
            "sources": {
                "enabled": "stored",
                "environment": "stored",
                "client_id": "stored" if stored["client_id"] else ("environment" if env_client_id else "none"),
                "client_secret": "stored" if stored["client_secret"] else ("environment" if env_client_secret else "none"),
                "client_use_code": "stored" if stored["client_use_code"] else ("environment" if env_client_use_code else "none"),
                "allowed_users": "stored" if stored["allowed_users"] else ("environment" if env_allowed else "none"),
            },
        }

    return {
        "version": 1,
        "enabled": env_enabled,
        "environment": env_environment,
        "client_id": env_client_id,
        "client_secret": env_client_secret,
        "client_use_code": env_client_use_code,
        "allowed_users": env_allowed,
        "sources": {
            "enabled": "environment" if env_enabled_raw else "default",
            "environment": "environment" if os.getenv("KFTC_OPENBANKING_ENVIRONMENT") else "default",
            "client_id": "environment" if env_client_id else "none",
            "client_secret": "environment" if env_client_secret else "none",
            "client_use_code": "environment" if env_client_use_code else "none",
            "allowed_users": "environment" if env_allowed else "none",
        },
    }


def patch_kftc_config(
    patch: dict[str, Any], *, path: Path | None = None
) -> dict[str, Any]:
    """Admin-only update to stored external credentials and config."""
    if not isinstance(patch, dict) or set(patch) - _CONFIG_KEYS:
        raise KftcConfigError("KFTC_CONFIG_PATCH_INVALID")

    p = _target(path)
    current = load_kftc_config(path=p) or {
        "version": 1,
        "enabled": False,
        "environment": "test",
        "client_id": "",
        "client_secret": "",
        "client_use_code": "",
        "allowed_users": [],
    }

    merged = {**current, **patch, "version": 1}
    validated = _validate_stored_config(merged)

    # Atomic write with 0600 POSIX permissions
    atomic_write_private_json(p, validated, indent=2)
    return get_effective_kftc_config(path=p)


def get_kftc_callback_url(*, public_base_url: str | None = None) -> str:
    """Build the exact callback URL using public_base_url."""
    base = public_base_url
    if not base:
        sys_settings = get_effective_system_settings()
        base = sys_settings.get("public_base_url")

    if not base:
        raise KftcConfigError("PUBLIC_BASE_URL_REQUIRED")

    norm_base = normalize_public_base_url(base)
    if not norm_base:
        raise KftcConfigError("PUBLIC_BASE_URL_REQUIRED")

    return f"{norm_base}/api/kftc/openbanking/oauth/callback"


def get_kftc_admin_status(
    *, current_role: str = "admin", path: Path | None = None
) -> dict[str, Any]:
    """Safe status metadata for admin without revealing client_secret."""
    can_manage = current_role == "admin"
    eff = get_effective_kftc_config(path=path)

    sys_settings = get_effective_system_settings()
    base_url = sys_settings.get("public_base_url")
    cb_url = None
    try:
        cb_url = get_kftc_callback_url(public_base_url=base_url)
    except Exception:
        pass

    return {
        "enabled": eff["enabled"],
        "environment": eff["environment"],
        "host": ALLOWED_HOSTS.get(eff["environment"], TEST_HOST),
        "client_id_configured": bool(eff["client_id"]),
        "client_secret_configured": bool(eff["client_secret"]),
        "client_use_code_configured": bool(eff["client_use_code"]),
        "allowed_users": eff["allowed_users"],
        "callback_url": cb_url,
        "public_base_url_ready": bool(base_url),
        "can_manage": can_manage,
        "sources": eff.get("sources", {}),
    }


def is_user_allowed_kftc(username: str, *, path: Path | None = None) -> bool:
    """Check if the user is authorized by the global feature gate and user allowlist."""
    eff = get_effective_kftc_config(path=path)
    if not eff.get("enabled"):
        return False
    allowed = eff.get("allowed_users") or []
    return (not allowed) or (username in allowed)
