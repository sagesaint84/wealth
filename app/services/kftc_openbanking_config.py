"""External credentials and per-user configuration for KFTC Open Banking.

Configurations live strictly per user:
data/users/<username>/kftc_openbanking_config.json

Isolated using app.services.user_manager.get_user_data_dir(username).
Client secret is encrypted at rest using AES-256-GCM + HKDF with context:
wealth:kftc-openbanking-config-secret:v1

Global system setting public_base_url is used to construct callback_url.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.services.kftc_openbanking_crypto import (
    KftcCryptoError,
    decrypt_string,
    encrypt_string,
    get_kftc_config_secret_context,
)
from app.services.secure_files import atomic_write_private_json
from app.services.system_settings import (
    SystemSettingsError,
    get_effective_system_settings,
    normalize_public_base_url,
)
from app.services.user_manager import get_user_data_dir

logger = logging.getLogger(__name__)

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
    "client_secret_encrypted",
    "client_use_code",
}

_PATCH_KEYS = {
    "enabled",
    "environment",
    "client_id",
    "client_secret",
    "client_use_code",
}


class KftcConfigError(Exception):
    """Raised when KFTC Open Banking configuration is invalid or missing."""


def get_user_kftc_config_file(username: str) -> Path:
    """Return the absolute path to the user's kftc_openbanking_config.json file."""
    user_dir = get_user_data_dir(username)
    return user_dir / "kftc_openbanking_config.json"


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

    secret_enc = data.get("client_secret_encrypted")
    if secret_enc is not None and not isinstance(secret_enc, str):
        raise KftcConfigError("KFTC_CLIENT_SECRET_INVALID")
    secret_enc_val = secret_enc.strip() if isinstance(secret_enc, str) else ""

    client_use_code = data.get("client_use_code")
    if client_use_code is not None and not isinstance(client_use_code, str):
        raise KftcConfigError("KFTC_CLIENT_USE_CODE_INVALID")
    client_use_code_val = client_use_code.strip() if isinstance(client_use_code, str) else ""

    return {
        "version": 1,
        "enabled": enabled,
        "environment": env,
        "client_id": client_id_val,
        "client_secret_encrypted": secret_enc_val,
        "client_use_code": client_use_code_val,
    }


def load_user_kftc_config(username: str, *, path: Path | None = None) -> dict[str, Any] | None:
    """Load and validate stored per-user KFTC configuration file."""
    p = path or get_user_kftc_config_file(username)
    if not p.exists():
        return None
    try:
        return _validate_stored_config(json.loads(p.read_text(encoding="utf-8")))
    except KftcConfigError:
        raise
    except Exception as exc:
        raise KftcConfigError("KFTC_CONFIG_INVALID") from exc


def get_effective_kftc_config(username: str, *, path: Path | None = None) -> dict[str, Any]:
    """Resolve user-specific configuration and decrypt client_secret for service operations.

    User credential isolation: Never falls back to other users' configs or global files.
    """
    stored = load_user_kftc_config(username, path=path)

    if stored is None:
        return {
            "version": 1,
            "enabled": False,
            "environment": "test",
            "client_id": "",
            "client_secret": "",
            "client_use_code": "",
            "configured": False,
        }

    secret_plaintext = ""
    secret_enc = stored.get("client_secret_encrypted", "")
    if secret_enc:
        try:
            secret_plaintext = decrypt_string(
                secret_enc,
                context=get_kftc_config_secret_context(username),
            )
        except KftcCryptoError as exc:
            logger.error("Failed to decrypt KFTC client_secret for user %s: %s", username, exc)
            raise KftcConfigError("KFTC_CLIENT_SECRET_DECRYPT_FAILED") from exc

    return {
        "version": 1,
        "enabled": stored["enabled"],
        "environment": stored["environment"],
        "client_id": stored["client_id"],
        "client_secret": secret_plaintext,
        "client_use_code": stored["client_use_code"],
        "configured": bool(stored["client_id"] and secret_plaintext),
    }


def patch_user_kftc_config(
    username: str,
    patch: dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    """Update current user's stored KFTC configuration.

    - Blank client_secret preserves existing secret.
    - Blank client_use_code preserves existing code (unless explicit clear).
    - Encrypts client_secret with CONFIG_SECRET_CONTEXT at rest.
    - Atomic write with 0600 POSIX permissions.
    """
    if not isinstance(patch, dict) or set(patch) - _PATCH_KEYS:
        raise KftcConfigError("KFTC_CONFIG_PATCH_INVALID")

    p = path or get_user_kftc_config_file(username)
    current = load_user_kftc_config(username, path=p) or {
        "version": 1,
        "enabled": False,
        "environment": "test",
        "client_id": "",
        "client_secret_encrypted": "",
        "client_use_code": "",
    }

    # Enabled
    enabled = current["enabled"]
    if "enabled" in patch:
        val = patch["enabled"]
        if type(val) is not bool:
            raise KftcConfigError("KFTC_CONFIG_INVALID")
        enabled = val

    # Environment
    environment = current["environment"]
    if "environment" in patch:
        val = str(patch["environment"] or "test").strip().lower()
        if val not in ALLOWED_HOSTS:
            raise KftcConfigError("KFTC_ENVIRONMENT_INVALID")
        environment = val

    # Client ID
    client_id = current["client_id"]
    if "client_id" in patch:
        val = patch["client_id"]
        if val is not None and not isinstance(val, str):
            raise KftcConfigError("KFTC_CLIENT_ID_INVALID")
        client_id = val.strip() if isinstance(val, str) else ""

    # Client Secret: blank preserves existing secret; non-blank encrypts and replaces
    client_secret_encrypted = current["client_secret_encrypted"]
    if "client_secret" in patch:
        val = patch["client_secret"]
        if val is not None and not isinstance(val, str):
            raise KftcConfigError("KFTC_CLIENT_SECRET_INVALID")
        new_secret = val.strip() if isinstance(val, str) else ""
        if new_secret:
            try:
                client_secret_encrypted = encrypt_string(
                    new_secret,
                    context=get_kftc_config_secret_context(username),
                )
            except KftcCryptoError as exc:
                logger.error("Failed to encrypt KFTC client_secret for user %s: %s", username, exc)
                raise KftcConfigError("KFTC_CLIENT_SECRET_ENCRYPT_FAILED") from exc

    # Client Use Code: blank preserves existing; non-blank replaces
    client_use_code = current["client_use_code"]
    if "client_use_code" in patch:
        val = patch["client_use_code"]
        if val is not None and not isinstance(val, str):
            raise KftcConfigError("KFTC_CLIENT_USE_CODE_INVALID")
        new_code = val.strip() if isinstance(val, str) else ""
        if new_code:
            client_use_code = new_code

    new_config = {
        "version": 1,
        "enabled": enabled,
        "environment": environment,
        "client_id": client_id,
        "client_secret_encrypted": client_secret_encrypted,
        "client_use_code": client_use_code,
    }
    validated = _validate_stored_config(new_config)

    # Atomic write with 0600 POSIX permissions
    atomic_write_private_json(p, validated, indent=2)
    return get_user_kftc_status_metadata(username, path=p)


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


def get_user_kftc_status_metadata(
    username: str, *, path: Path | None = None
) -> dict[str, Any]:
    """Return safe metadata for the user's OpenAPI settings UI without plaintext secrets."""
    stored = load_user_kftc_config(username, path=path)

    sys_settings = get_effective_system_settings()
    base_url = sys_settings.get("public_base_url")
    cb_url = None
    pub_ready = False
    try:
        cb_url = get_kftc_callback_url(public_base_url=base_url)
        pub_ready = True
    except Exception:
        pass

    if stored is None:
        return {
            "enabled": False,
            "environment": "test",
            "host": TEST_HOST,
            "client_id": "",
            "client_id_configured": False,
            "client_secret_configured": False,
            "client_use_code": "",
            "client_use_code_configured": False,
            "callback_url": cb_url,
            "public_base_url_ready": pub_ready,
        }

    return {
        "enabled": stored["enabled"],
        "environment": stored["environment"],
        "host": ALLOWED_HOSTS.get(stored["environment"], TEST_HOST),
        "client_id": stored["client_id"],
        "client_id_configured": bool(stored["client_id"]),
        "client_secret_configured": bool(stored["client_secret_encrypted"]),
        "client_use_code": stored["client_use_code"],
        "client_use_code_configured": bool(stored["client_use_code"]),
        "callback_url": cb_url,
        "public_base_url_ready": pub_ready,
    }


def is_user_allowed_kftc(username: str, *, path: Path | None = None) -> bool:
    """Check if the user has enabled their per-user KFTC configuration.

    Per-user config itself functions as the feature gate.
    """
    stored = load_user_kftc_config(username, path=path)
    if stored is None:
        return False
    return stored.get("enabled", False) is True
