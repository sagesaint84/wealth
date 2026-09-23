"""Small persistent system-wide settings document (never stores secrets)."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.services.settings import SettingsError, settings_lock
from app.services.user_identity import validate_user_id

SYSTEM_SETTINGS_FILE = (
    Path(__file__).resolve().parents[2] / "data" / "system" / "settings.json"
)

DEFAULT_TOSS_WTS_EXECUTABLE = "/opt/toss-wts/tossctl"
DEFAULT_TOSS_WTS_CONFIG_DIR = "/opt/toss-wts/config"
DEFAULT_TOSS_WTS_EXPECTED_VERSION = "v0.50.3"
DEFAULT_TOSS_WTS_TIMEOUT_SECONDS = 20
DEFAULT_TOSS_SESSION_CHECK_TIME = "20:55"
DEFAULT_TOSS_SESSION_EXTEND_THRESHOLD_HOURS = 48
DEFAULT_TOSS_SESSION_EXTEND_TIMEOUT_SECONDS = 300
_TOSS_VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+$")
_SYSTEM_KEYS = {
    "version",
    "public_base_url",
    "telegram_webhook_owner",
    "automation_owner",
    "toss_wts",
}
_TOSS_KEYS = {
    "enabled",
    "executable",
    "config_dir",
    "expected_version",
    "timeout_seconds",
    "allowed_user_id",
    "allowed_users",
    "session_check_enabled",
    "session_check_time",
    "session_extend_threshold_hours",
    "session_extend_timeout_seconds",
}


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


def _normalize_absolute_path(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SystemSettingsError(code)
    normalized = value.strip()
    path = Path(normalized).expanduser()
    if not path.is_absolute() and not normalized.startswith("/"):
        raise SystemSettingsError(code)
    return normalized if normalized.startswith("/") else str(path)


def _validate_toss_wts(data: object) -> dict:
    if not isinstance(data, dict) or set(data) - _TOSS_KEYS:
        raise SystemSettingsError("TOSS_WTS_SETTINGS_INVALID")
    enabled = data.get("enabled", False)
    if type(enabled) is not bool:
        raise SystemSettingsError("TOSS_WTS_SETTINGS_INVALID")
    executable = _normalize_absolute_path(
        data.get("executable", DEFAULT_TOSS_WTS_EXECUTABLE),
        "TOSS_WTS_EXECUTABLE_INVALID",
    )
    config_dir = _normalize_absolute_path(
        data.get("config_dir", DEFAULT_TOSS_WTS_CONFIG_DIR),
        "TOSS_WTS_CONFIG_DIR_INVALID",
    )
    expected_version = data.get(
        "expected_version", DEFAULT_TOSS_WTS_EXPECTED_VERSION
    )
    if not isinstance(expected_version, str) or not _TOSS_VERSION_RE.fullmatch(
        expected_version.strip()
    ):
        raise SystemSettingsError("TOSS_WTS_VERSION_INVALID")
    timeout = data.get("timeout_seconds", DEFAULT_TOSS_WTS_TIMEOUT_SECONDS)
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise SystemSettingsError("TOSS_WTS_TIMEOUT_INVALID")
    allowed = data.get("allowed_user_id")
    if allowed in (None, ""):
        allowed = None
    else:
        try:
            allowed = validate_user_id(allowed)
        except ValueError as exc:
            raise SystemSettingsError("TOSS_WTS_ALLOWED_USER_INVALID") from exc
    allowed_users = data.get("allowed_users", [])
    if not isinstance(allowed_users, list) or any(
        not isinstance(username, str) or not username.strip()
        or any(part in username for part in ("/", "\\", ".."))
        for username in allowed_users
    ) or len(set(allowed_users)) != len(allowed_users):
        raise SystemSettingsError("TOSS_WTS_ALLOWED_USERS_INVALID")
    session_check_enabled = data.get("session_check_enabled", False)
    if type(session_check_enabled) is not bool:
        raise SystemSettingsError("TOSS_WTS_SESSION_CHECK_ENABLED_INVALID")
    session_check_time = data.get("session_check_time", DEFAULT_TOSS_SESSION_CHECK_TIME)
    if not isinstance(session_check_time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", session_check_time):
        raise SystemSettingsError("TOSS_WTS_SESSION_CHECK_TIME_INVALID")
    threshold = data.get("session_extend_threshold_hours", DEFAULT_TOSS_SESSION_EXTEND_THRESHOLD_HOURS)
    if type(threshold) is not int or not 1 <= threshold <= 168:
        raise SystemSettingsError("TOSS_WTS_SESSION_EXTEND_THRESHOLD_INVALID")
    extend_timeout = data.get("session_extend_timeout_seconds", DEFAULT_TOSS_SESSION_EXTEND_TIMEOUT_SECONDS)
    if type(extend_timeout) is not int or not 30 <= extend_timeout <= 600:
        raise SystemSettingsError("TOSS_WTS_SESSION_EXTEND_TIMEOUT_INVALID")
    return {
        "enabled": enabled,
        "executable": executable,
        "config_dir": config_dir,
        "expected_version": expected_version.strip(),
        "timeout_seconds": timeout,
        "allowed_user_id": allowed,
        "allowed_users": allowed_users,
        "session_check_enabled": session_check_enabled,
        "session_check_time": session_check_time,
        "session_extend_threshold_hours": threshold,
        "session_extend_timeout_seconds": extend_timeout,
    }


def _validate(data: object) -> dict:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise SystemSettingsError("SYSTEM_SETTINGS_INVALID")
    if set(data) - _SYSTEM_KEYS:
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
        "toss_wts": (
            _validate_toss_wts(data["toss_wts"])
            if data.get("toss_wts") is not None
            else None
        ),
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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise SystemSettingsError("TOSS_WTS_ENABLED_INVALID")


def resolve_toss_wts_settings(
    *, path: Path | None = None, stored: dict | None = None
) -> dict:
    """Resolve stored Toss WTS settings, then legacy env, then safe defaults."""
    if stored is None:
        stored = load_system_settings(path=path)
    stored_wts = stored.get("toss_wts") if stored else None
    env_values = {
        "enabled": os.getenv("WEALTH_TOSS_WTS_ENABLED"),
        "executable": os.getenv("WEALTH_TOSSCTL_PATH"),
        "config_dir": os.getenv("WEALTH_TOSSCTL_CONFIG_DIR"),
        "expected_version": os.getenv("WEALTH_TOSSCTL_EXPECTED_VERSION"),
        "timeout_seconds": os.getenv("WEALTH_TOSSCTL_TIMEOUT_SECONDS"),
        "allowed_user_id": os.getenv("WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID"),
    }
    defaults = {
        "enabled": False,
        "executable": DEFAULT_TOSS_WTS_EXECUTABLE,
        "config_dir": DEFAULT_TOSS_WTS_CONFIG_DIR,
        "expected_version": DEFAULT_TOSS_WTS_EXPECTED_VERSION,
        "timeout_seconds": DEFAULT_TOSS_WTS_TIMEOUT_SECONDS,
        "allowed_user_id": None,
        "allowed_users": [],
        "session_check_enabled": False,
        "session_check_time": DEFAULT_TOSS_SESSION_CHECK_TIME,
        "session_extend_threshold_hours": DEFAULT_TOSS_SESSION_EXTEND_THRESHOLD_HOURS,
        "session_extend_timeout_seconds": DEFAULT_TOSS_SESSION_EXTEND_TIMEOUT_SECONDS,
    }
    result: dict[str, object] = {}
    sources: dict[str, str] = {}
    for key, default in defaults.items():
        if stored_wts is not None and key in stored_wts:
            result[key], sources[key] = stored_wts[key], "stored"
            continue
        raw = env_values.get(key)
        if raw is None or raw == "":
            result[key], sources[key] = default, "default"
            continue
        if key == "enabled":
            value = _env_bool("WEALTH_TOSS_WTS_ENABLED", False)
        elif key == "timeout_seconds":
            try:
                value = int(str(raw).strip())
            except ValueError as exc:
                raise SystemSettingsError("TOSS_WTS_TIMEOUT_INVALID") from exc
            if not 1 <= value <= 300:
                raise SystemSettingsError("TOSS_WTS_TIMEOUT_INVALID")
        elif key in {"executable", "config_dir"}:
            value = _normalize_absolute_path(
                str(raw), f"TOSS_WTS_{key.upper()}_INVALID"
            )
        elif key == "expected_version":
            value = str(raw).strip()
            if not _TOSS_VERSION_RE.fullmatch(value):
                raise SystemSettingsError("TOSS_WTS_VERSION_INVALID")
        else:
            try:
                value = validate_user_id(raw)
            except ValueError as exc:
                raise SystemSettingsError("TOSS_WTS_ALLOWED_USER_INVALID") from exc
        result[key], sources[key] = value, "environment"
    result["sources"] = sources
    return result


def patch_system_settings(
    patch: dict, *, path: Path | None = None, validate_user: bool = True
) -> dict:
    if not isinstance(patch, dict) or set(patch) - {
        "public_base_url",
        "telegram_webhook_owner",
        "automation_owner",
        "toss_wts",
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
                    "toss_wts": None,
                }
                merged = {**current, **patch}
                if "toss_wts" in patch:
                    if not isinstance(patch["toss_wts"], dict):
                        raise SystemSettingsError("TOSS_WTS_SETTINGS_INVALID")
                    merged["toss_wts"] = {
                        **(current.get("toss_wts") or {}),
                        **patch["toss_wts"],
                    }
                candidate = _validate(merged)
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
