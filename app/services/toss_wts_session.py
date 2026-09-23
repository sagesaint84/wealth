"""Secret-safe Toss WTS session status and scheduled maintenance.

This module is intentionally separate from the read-only financial adapter.  It
only invokes the two explicit ``tossctl auth`` commands defined below and never
reads or returns session.json, subprocess output, or credentials.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.services.system_settings import resolve_toss_wts_settings
from app.services.telegram_config import resolve_telegram_config
from app.services.telegram_management import TelegramManagementError, send_telegram_message

KST = timezone(timedelta(hours=9))


def _now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(KST)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return value.astimezone(KST)


def _base_status(settings: dict[str, Any], *, checked_at: datetime, config_dir: Path | None = None, error_code: str | None = None) -> dict[str, Any]:
    executable = Path(str(settings["executable"]))
    # Use explicitly provided config_dir; fall back to settings["config_dir"] for legacy/test use
    if config_dir is None:
        config_dir = Path(str(settings.get("config_dir", "")))
    session_present = config_dir.is_dir() and (config_dir / "session.json").is_file()
    return {
        "configured": bool(settings.get("enabled")),
        "session_present": session_present,
        "active": False,
        "valid": False,
        "authenticated": False,
        "server_expires_at": None,
        "hours_remaining": None,
        "checked_at": checked_at.isoformat(),
        "expected_version": settings["expected_version"],
        "error_code": error_code,
        "_executable": executable,
        "_config_dir": config_dir,
    }



def _public(status: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in status.items() if not key.startswith("_")}


def _parse_expiry(payload: dict[str, Any], now: datetime) -> datetime | None:
    raw = payload.get("server_expires_at", payload.get("serverExpiresAt", payload.get("expires_at", payload.get("expiresAt"))))
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        value = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(KST)


def get_toss_session_status(*, username: str, now: datetime | None = None, settings: dict[str, Any] | None = None, run: Callable[..., Any] = subprocess.run) -> dict[str, Any]:
    """Run the explicit JSON auth-status probe and return a narrow safe result.

    ``username`` is the authenticated Wealth user.  The per-user config-dir
    is derived from ``username`` — the ``config_dir`` field in ``settings``
    (if any) is ignored at runtime (it is kept only for admin display/migration).
    """
    from app.services.toss_wts_auth_guard import _user_toss_root
    checked_at = _now(now)
    cfg = settings or resolve_toss_wts_settings()
    # Per-user config dir (derived from username, never from global settings at runtime)
    user_config_dir = _user_toss_root(username) / "config"
    status = _base_status(cfg, checked_at=checked_at, config_dir=user_config_dir)
    if not cfg.get("enabled"):
        status["error_code"] = "NOT_CONFIGURED"
        return _public(status)
    if not status["_executable"].is_file():
        status["error_code"] = "EXECUTABLE_MISSING"
        return _public(status)
    if not status["_config_dir"].is_dir():
        status["error_code"] = "CONFIG_DIR_MISSING"
        return _public(status)
    if not status["session_present"]:
        status["error_code"] = "SESSION_MISSING"
        return _public(status)
    argv = [str(status["_executable"]), "--config-dir", str(status["_config_dir"]), "--output", "json", "auth", "status"]
    try:
        completed = run(argv, shell=False, capture_output=True, text=True, timeout=int(cfg["timeout_seconds"]))
    except subprocess.TimeoutExpired:
        status["error_code"] = "AUTH_STATUS_TIMEOUT"
        return _public(status)
    except OSError:
        status["error_code"] = "AUTH_STATUS_FAILED"
        return _public(status)
    if getattr(completed, "returncode", 1) != 0:
        status["error_code"] = "AUTH_STATUS_FAILED"
        return _public(status)
    try:
        payload = json.loads(getattr(completed, "stdout", ""))
    except (TypeError, json.JSONDecodeError):
        status["error_code"] = "INVALID_JSON"
        return _public(status)
    if not isinstance(payload, dict) or not all(isinstance(payload.get(key), bool) for key in ("active", "valid")):
        status["error_code"] = "INVALID_STATUS_SCHEMA"
        return _public(status)
    expiry = _parse_expiry(payload, checked_at)
    if expiry is None:
        status["error_code"] = "INVALID_STATUS_SCHEMA"
        return _public(status)
    status.update({"active": payload["active"], "valid": payload["valid"], "authenticated": bool(payload.get("authenticated", payload["active"] and payload["valid"])), "server_expires_at": expiry.isoformat(), "hours_remaining": round((expiry - checked_at).total_seconds() / 3600, 2)})
    if not status["active"]:
        status["error_code"] = "SESSION_INACTIVE"
    elif not status["valid"]:
        status["error_code"] = "SESSION_INVALID"
    return _public(status)



def _notify(owner: str, message: str, sender: Callable[..., Any]) -> str:
    try:
        sender(resolve_telegram_config(owner), message)
        return "sent"
    except Exception:
        return "failed"


def run_toss_session_maintenance(
    owner_username: str,
    *,
    now: datetime | None = None,
    now_provider: Callable[[], datetime] | None = None,
    settings: dict[str, Any] | None = None,
    run: Callable[..., Any] = subprocess.run,
    sender: Callable[..., Any] = send_telegram_message,
) -> dict[str, Any]:
    """Perform at most one approval-gated extension and always post-verify it.

    Cross-process race protection
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    The shared ``auth_operation_lock`` from ``toss_wts_auth_guard`` is acquired
    before extension begins and held for the ENTIRE subprocess lifetime
    (including phone-approval wait).  While the lock is held, any concurrent
    admin login-start request fails immediately with TOSS_AUTH_OPERATION_BUSY.

    Conversely, if an admin login is already running (marker file exists),
    this function detects it inside the lock and returns
    ``action="deferred" / AUTH_LOGIN_IN_PROGRESS`` without calling auth extend.

    ``now`` fixes the pre-extension wall-clock time (for deterministic testing).
    ``now_provider`` is called *after* the extension completes to obtain the
    real verification timestamp; defaults to ``lambda: datetime.now(KST)``.
    """
    current = _now(now)
    _post_clock: Callable[[], datetime] = now_provider or (lambda: datetime.now(KST))
    cfg = settings or resolve_toss_wts_settings()

    # Status check (read-only, no lock needed) — uses per-user config dir
    status = get_toss_session_status(username=owner_username, now=current, settings=cfg, run=run)
    result: dict[str, Any] = {
        "action": "status_failed",
        "active": status["active"],
        "valid": status["valid"],
        "server_expires_at": status["server_expires_at"],
        "hours_remaining": status["hours_remaining"],
        "extension_attempted": False,
        "extension_succeeded": False,
        "notification_status": "not_sent",
        "error_code": status["error_code"],
    }

    if not status["active"] or not status["valid"]:
        result["notification_status"] = _notify(
            owner_username,
            "Wealth: Toss WTS 세션이 유효하지 않습니다. 수동 연장 또는 QR 재인증이 필요할 수 있습니다.",
            sender,
        )
        return result

    if status["hours_remaining"] is not None and status["hours_remaining"] > cfg["session_extend_threshold_hours"]:
        result.update({"action": "not_required", "error_code": None})
        return result

    # Extension required.
    # Acquire the shared advisory lock and hold it for the full subprocess.
    # -----------------------------------------------------------------------
    # Race directions closed:
    #   (A) Login marker already exists → we return AUTH_LOGIN_IN_PROGRESS
    #       inside the lock (marker check is atomic with lock acquisition).
    #   (B) We hold the lock during the entire extend subprocess → any
    #       concurrent login start cannot acquire the lock and immediately
    #       gets TOSS_AUTH_OPERATION_BUSY.
    # -----------------------------------------------------------------------
    from app.services.toss_wts_auth_guard import (
        auth_operation_lock,
        check_active_login_operation,
        TossAuthOperationBusyError,
        _user_toss_root,
    )
    user_config_dir = _user_toss_root(owner_username) / "config"
    argv = [
        str(cfg["executable"]),
        "--config-dir", str(user_config_dir),
        "auth", "extend",
        "--if-expiring", f"{cfg['session_extend_threshold_hours']}h",
        "--timeout", f"{cfg['session_extend_timeout_seconds']}s",
    ]
    extend_error: str | None = None
    extended = False

    try:
        with auth_operation_lock(owner_username, acquire_timeout_seconds=5.0):

            # --- Inside lock: marker check is now race-free (per-user) ---
            if check_active_login_operation(owner_username):
                result.update({
                    "action": "deferred",
                    "error_code": "AUTH_LOGIN_IN_PROGRESS",
                })
                return result

            # Flag intention and notify before the blocking subprocess
            result["extension_attempted"] = True
            result["notification_status"] = _notify(
                owner_username,
                "Wealth: Toss WTS 세션 연장을 요청합니다. Toss 앱 승인이 필요할 수 있습니다.",
                sender,
            )

            # Run extend subprocess while holding the advisory lock
            try:
                completed = run(
                    argv,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=int(cfg["session_extend_timeout_seconds"]) + 15,
                )
                if getattr(completed, "returncode", 1) == 0:
                    extended = True
                else:
                    extend_error = "AUTH_EXTEND_FAILED"
            except subprocess.TimeoutExpired:
                extend_error = "AUTH_EXTEND_TIMEOUT"
            except OSError:
                extend_error = "AUTH_EXTEND_FAILED"
        # Lock released here — post-verification runs without the lock

    except TossAuthOperationBusyError:
        # Login holds the lock; extension cannot start
        result.update({
            "action": "deferred",
            "error_code": "TOSS_AUTH_OPERATION_BUSY",
        })
        return result
    except Exception:
        # Failing open here would permit a concurrent interactive extension.
        # Preserve the per-user lock invariant even if its infrastructure is
        # unexpectedly unavailable.
        result.update({"action": "deferred", "error_code": "AUTH_OPERATION_GUARD_FAILED"})
        return result

    if not extended:
        result.update({"action": "extension_failed", "error_code": extend_error})
        result["notification_status"] = _notify(
            owner_username,
            "Wealth: Toss WTS 세션 연장에 실패했습니다. 수동 연장 또는 QR 재인증이 필요할 수 있습니다.",
            sender,
        )
        return result

    # Post-extension verification (no lock needed — read-only)
    verified_at = _now(_post_clock())
    verified = get_toss_session_status(username=owner_username, now=verified_at, settings=cfg, run=run)
    result.update({
        "active": verified["active"],
        "valid": verified["valid"],
        "server_expires_at": verified["server_expires_at"],
        "hours_remaining": verified["hours_remaining"],
        "error_code": verified["error_code"],
    })
    if verified["active"] and verified["valid"]:
        result.update({"action": "extended", "extension_succeeded": True, "error_code": None})
        result["notification_status"] = _notify(
            owner_username,
            f"Wealth: Toss WTS 세션 연장이 확인되었습니다. 서버 만료: {verified['server_expires_at']}",
            sender,
        )
    else:
        result["action"] = "extension_failed"
        result["notification_status"] = _notify(
            owner_username,
            "Wealth: Toss WTS 세션 연장 후 상태 확인에 실패했습니다. 수동 확인이 필요합니다.",
            sender,
        )
    return result
