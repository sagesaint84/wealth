"""Small persistent system-wide settings document (never stores secrets)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.services.settings import SettingsError, settings_lock

SYSTEM_SETTINGS_FILE = (
    Path(__file__).resolve().parents[2] / "data" / "system" / "settings.json"
)


class SystemSettingsError(SettingsError):
    pass


def _target(path: Path | None = None) -> Path:
    root = os.getenv("WEALTH_DATA_DIR", "").strip()
    return (
        path
        or (
            (Path(root) / "system" / "settings.json")
            if root
            else SYSTEM_SETTINGS_FILE
        )
    )


def normalize_public_base_url(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SystemSettingsError("PUBLIC_BASE_URL_INVALID")
    try:
        parts = urlsplit(value.strip())
    except ValueError as exc:
        raise SystemSettingsError("PUBLIC_BASE_URL_INVALID") from exc
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
    ):
        raise SystemSettingsError("PUBLIC_BASE_URL_INVALID")
    if parts.path not in ("", "/"):
        raise SystemSettingsError("PUBLIC_BASE_URL_INVALID")
    try:
        port = parts.port
    except ValueError as exc:
        raise SystemSettingsError("PUBLIC_BASE_URL_INVALID") from exc
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    netloc = f"{host}:{port}" if port else host
    return urlunsplit(("https", netloc, "", "", ""))


def normalize_automation_owner(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SystemSettingsError("AUTOMATION_OWNER_INVALID")
    owner = value.strip()
    if not owner or any(x in owner for x in ("/", "\\", "..")):
        raise SystemSettingsError("AUTOMATION_OWNER_INVALID")
    return owner


def _validate(data: object) -> dict:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise SystemSettingsError("SYSTEM_SETTINGS_INVALID")
    keys = set(data)
    allowed_v1_legacy = {"version", "public_base_url", "telegram_webhook_owner"}
    allowed_v1_current = {
        "version",
        "public_base_url",
        "telegram_webhook_owner",
        "automation_owner",
    }
    if keys not in (allowed_v1_legacy, allowed_v1_current):
        raise SystemSettingsError("SYSTEM_SETTINGS_INVALID")

    url = normalize_public_base_url(data.get("public_base_url"))
    webhook_owner = data.get("telegram_webhook_owner")
    if webhook_owner is not None and (
        not isinstance(webhook_owner, str)
        or not webhook_owner.strip()
        or any(x in webhook_owner for x in ("/", "\\", ".."))
    ):
        raise SystemSettingsError("WEBHOOK_OWNER_INVALID")
    auto_owner = normalize_automation_owner(data.get("automation_owner"))
    return {
        "version": 1,
        "public_base_url": url,
        "telegram_webhook_owner": (
            webhook_owner.strip() if isinstance(webhook_owner, str) else None
        ),
        "automation_owner": auto_owner,
    }


def load_system_settings(*, path: Path | None = None) -> dict | None:
    p = _target(path)
    if not p.exists():
        return None
    try:
        return _validate(json.loads(p.read_text(encoding="utf-8")))
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        SystemSettingsError,
    ) as exc:
        raise SystemSettingsError("SYSTEM_SETTINGS_INVALID") from exc


def get_effective_system_settings(*, path: Path | None = None) -> dict:
    stored = load_system_settings(path=path)
    env_url = os.getenv("WEALTH_PUBLIC_BASE_URL", "").strip()
    env_owner = os.getenv("TELEGRAM_WEALTH_USERNAME", "").strip()
    env_auto_owner = os.getenv("WEALTH_AUTOMATION_OWNER", "").strip()

    stored_auto = stored.get("automation_owner") if stored else None
    if stored_auto:
        auto_owner = stored_auto
        auto_source = "stored"
    elif env_auto_owner:
        auto_owner = env_auto_owner
        auto_source = "environment"
    else:
        auto_owner = None
        auto_source = "none"

    return {
        "version": 1,
        "public_base_url": (
            stored["public_base_url"]
            if stored and stored["public_base_url"]
            else (normalize_public_base_url(env_url) if env_url else None)
        ),
        "public_base_url_source": (
            "stored"
            if stored and stored["public_base_url"]
            else ("environment" if env_url else "none")
        ),
        "telegram_webhook_owner": (
            stored["telegram_webhook_owner"]
            if stored and stored["telegram_webhook_owner"]
            else (env_owner or None)
        ),
        "telegram_webhook_owner_source": (
            "stored"
            if stored and stored["telegram_webhook_owner"]
            else ("environment" if env_owner else "none")
        ),
        "automation_owner": auto_owner,
        "automation_owner_source": auto_source,
    }


def patch_system_settings(
    patch: dict, *, path: Path | None = None, validate_user: bool = True
) -> dict:
    if not isinstance(patch, dict) or set(patch) - {
        "public_base_url",
        "telegram_webhook_owner",
        "automation_owner",
    }:
        raise SystemSettingsError("SYSTEM_SETTINGS_PATCH_INVALID")
    if "automation_owner" in patch:
        auto_owner = normalize_automation_owner(patch["automation_owner"])
        if auto_owner is not None and validate_user:
            try:
                from app.services.user_manager import list_users

                registered = {
                    u["username"]
                    for u in list_users()
                    if isinstance(u, dict) and u.get("username")
                }
                if auto_owner not in registered:
                    raise SystemSettingsError("AUTOMATION_OWNER_INVALID")
            except SystemSettingsError:
                raise
            except Exception:
                pass
    p = _target(path)
    for attempt in range(100):
        try:
            with settings_lock(p):
                current = load_system_settings(path=p) or {
                    "version": 1,
                    "public_base_url": None,
                    "telegram_webhook_owner": None,
                    "automation_owner": None,
                }
                candidate = _validate({**current, **patch})
                tmp = p.with_suffix(".tmp")
                try:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(
                            candidate,
                            f,
                            ensure_ascii=False,
                            indent=2,
                            allow_nan=False,
                        )
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, p)
                except Exception:
                    tmp.unlink(missing_ok=True)
                    raise
            break
        except SettingsError as exc:
            if str(exc) != "SETTINGS_ALREADY_RUNNING" or attempt == 99:
                raise
            time.sleep(0.01)
    return get_effective_system_settings(path=p)


def expected_webhook_url(settings: dict) -> str | None:
    base = settings.get("public_base_url")
    return f"{base}/api/integrations/telegram/webhook" if base else None
