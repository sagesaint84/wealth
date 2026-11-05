"""Secret-safe Toss WTS session status and scheduled maintenance.

This module is intentionally separate from the read-only financial adapter.  It
only invokes the two explicit ``tossctl auth`` commands defined below and never
reads or returns session.json, subprocess output, or credentials.
"""
from __future__ import annotations

import json
import subprocess
import time
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.services.system_settings import resolve_toss_wts_settings
from app.services.telegram_config import resolve_telegram_config
from app.services.telegram_management import TelegramManagementError, send_telegram_message
from app.services.notifications.models import NotificationEvent
from app.services.notifications.service import UserNotificationService

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



def _compact_kakao_message(message: str) -> str:
    text = " ".join(message.split()).strip()
    if len(text) <= 200:
        return text
    return text[:199].rstrip() + "…"


def _provider_payload(
    *,
    sent: bool,
    status: str,
    retryable: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "sent": bool(sent),
        "status": status,
        "retryable": bool(retryable),
        "error": error,
    }


def _legacy_notification_result(
    owner: str,
    message: str,
    sender: Callable[..., Any],
) -> dict[str, Any]:
    status = _notify(owner, message, sender)
    return {
        "status": status,
        "notifications_sent_count": 1 if status == "sent" else 0,
        "provider_results": {
            "telegram": _provider_payload(
                sent=status == "sent",
                status=status,
                retryable=status == "failed",
                error=None if status == "sent" else "TELEGRAM_SEND_FAILED",
            )
        },
    }


def send_toss_session_notifications(
    owner: str,
    message: str,
    *,
    event_key: str,
    event_type: str,
) -> dict[str, Any]:
    """Dispatch a Toss session event through the common notification service."""
    service = UserNotificationService(
        owner,
        telegram_resolver=resolve_telegram_config,
    )
    event = NotificationEvent(
        event_key=event_key,
        event_type=event_type,
        body=message,
        username=owner,
        metadata={"kakao_body": _compact_kakao_message(message)},
    )
    report = service.dispatch(event)
    return {
        "status": report.status,
        "notifications_sent_count": report.notifications_sent_count,
        "provider_results": report.provider_results,
    }


def _apply_notification_result(
    result: dict[str, Any],
    notification: dict[str, Any],
) -> None:
    result["notification_status"] = notification["status"]
    result["notification_dispatch_status"] = notification["status"]
    result["notifications_sent_count"] = notification["notifications_sent_count"]
    result["notification_provider_results"] = notification["provider_results"]


def _notify_maintenance_event(
    result: dict[str, Any],
    *,
    owner: str,
    message: str,
    event_key: str,
    event_type: str,
    sender: Callable[..., Any] | None,
) -> None:
    try:
        notification = (
            _legacy_notification_result(owner, message, sender)
            if sender is not None
            else send_toss_session_notifications(
                owner,
                message,
                event_key=event_key,
                event_type=event_type,
            )
        )
    except Exception:
        # Notification failures must never alter the Toss session maintenance
        # outcome. Do not log exception text because provider exceptions may
        # contain credentials or webhook URLs.
        notification = {
            "status": "failed",
            "notifications_sent_count": 0,
            "provider_results": {},
        }
    _apply_notification_result(result, notification)


def run_toss_session_maintenance(
    owner_username: str,
    *,
    now: datetime | None = None,
    now_provider: Callable[[], datetime] | None = None,
    settings: dict[str, Any] | None = None,
    run: Callable[..., Any] = subprocess.run,
    sender: Callable[..., Any] | None = None,
    _start_extension: Callable[..., Any] | None = None,
    _observe_extension: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Perform at most one approval-gated extension and always post-verify it.

    Cross-process race protection
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Automatic and manual extension share the QR lifecycle: reserve a durable
    owner marker under auth_operation_lock before spawning the supervisor.
    That marker blocks QR and extension until descendant-completion receipt
    and supervisor exit are proven. Caller disconnect/restart cannot release it.

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
        "notification_dispatch_status": "not_sent",
        "notifications_sent_count": 0,
        "notification_provider_results": {},
        "error_code": status["error_code"],
    }

    if not status["active"] or not status["valid"]:
        _notify_maintenance_event(
            result,
            owner=owner_username,
            message="Wealth: Toss WTS 세션이 유효하지 않습니다. 수동 연장 또는 QR 재인증이 필요할 수 있습니다.",
            event_key=f"toss_wts:{owner_username}:{current.date().isoformat()}:session_invalid",
            event_type="toss_wts_session_invalid",
            sender=sender,
        )
        return result

    if status["hours_remaining"] is not None and status["hours_remaining"] > cfg["session_extend_threshold_hours"]:
        result.update({"action": "not_required", "error_code": None})
        return result

    if (_start_extension is None) != (_observe_extension is None):
        raise ValueError("Both supervised-boundary dependencies are required")
    if run is not subprocess.run and _start_extension is None:
        # A legacy injected auth-status runner must not accidentally launch a
        # real background CLI. Supervisor lifecycle injection needs its own
        # explicit regression contract when dynamic testing resumes.
        result.update(action="deferred", error_code="AUTH_PROCESS_RUNNER_UNSUPPORTED")
        return result

    # Automatic and manual requests enter the SAME durable QR auth lifecycle.
    started = (_start_extension or start_toss_session_extension)(owner_username)
    result.update(started)
    if started.get("action") != "pending":
        if started.get("action") in {"status_failed", "reauth_required"}:
            _notify_maintenance_event(
                result, owner=owner_username,
                message="Wealth: Toss WTS 세션 연장에 실패했습니다. 세션 상태 확인 또는 QR 재인증이 필요할 수 있습니다.",
                event_key=f"toss_wts:{owner_username}:{current.date().isoformat()}:extension_failed",
                event_type="toss_wts_extension_failed", sender=sender,
            )
        return result
    _notify_maintenance_event(
        result, owner=owner_username,
        message="Wealth: Toss WTS 세션 연장을 요청합니다. Toss 앱 승인이 필요할 수 있습니다.",
        event_key=f"toss_wts:{owner_username}:{current.date().isoformat()}:extension_requested",
        event_type="toss_wts_extension_requested", sender=sender,
    )
    # Poll evidence, never retry auth extend. The supervisor independently owns
    # its deadline; uncertainty at this bounded caller deadline retains marker.
    deadline = time.monotonic() + int(cfg["session_extend_timeout_seconds"]) + 60
    while time.monotonic() < deadline:
        observed = (_observe_extension or get_toss_session_extension)(owner_username, attempt_id=started["attempt_id"],
                                                                     now_provider=_post_clock)
        result.update(observed)
        if observed.get("action") != "pending":
            break
        time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
    if result.get("action") == "pending":
        result.update(action="deferred", error_code="AUTH_EXTEND_TERMINATION_PENDING")
        return result
    succeeded = result.get("action") == "extended"
    unchanged = result.get("action") == "unchanged"
    post_verify_failed = not succeeded and not unchanged and result.get("error_code") not in {
        "AUTH_EXTEND_TIMEOUT", "AUTH_EXTEND_FAILED"
    }
    _notify_maintenance_event(
        result, owner=owner_username,
        message=(f"Wealth: Toss WTS 세션 연장이 확인되었습니다. 서버 만료: {result.get('server_expires_at')}"
                 if succeeded else "Wealth: Toss WTS 세션 만료 시각이 변경되지 않았습니다. 상태 확인이 필요합니다."
                 if unchanged else "Wealth: Toss WTS 세션 연장 후 상태 확인에 실패했습니다. 수동 확인이 필요합니다."),
        event_key=f"toss_wts:{owner_username}:{_now(_post_clock()).date().isoformat()}:" +
                  ("extension_succeeded" if succeeded else "extension_unchanged" if unchanged else
                   "post_verify_failed" if post_verify_failed else "extension_failed"),
        event_type="toss_wts_extension_succeeded" if succeeded else
                   "toss_wts_post_verify_failed" if post_verify_failed else "toss_wts_extension_failed",
        sender=sender,
    )
    return result


def get_toss_session_extension(username: str, *, attempt_id: str | None = None,
                               now_provider: Callable[[], datetime] | None = None) -> dict[str, Any]:
    """Owner-scoped durable evidence lookup; never starts or retries auth."""
    if sys.platform != "linux":
        return {"action": "unavailable", "supported": False, "extension_succeeded": False,
                "error_code": "AUTH_PROCESS_BOUNDARY_UNAVAILABLE"}
    from app.services.toss_wts_auth_guard import user_login_dir, _get_active_op_data
    from app.services.toss_wts_auth_process import private_receipt
    from app.services.toss_wts_login import _read_meta, get_login_attempt, TossLoginNotFoundError
    import uuid
    marker = _get_active_op_data(username)
    try:
        if attempt_id is not None:
            pass  # Internal scheduled caller pins its own attempt, never a later job.
        elif marker and marker.get("type") == "extend":
            attempt_id = marker["attempt_id"]
        else:
            pointer = private_receipt(user_login_dir(username) / "extension-latest.json")
            if pointer.get("owner") != username:
                raise ValueError("OWNER_MISMATCH")
            attempt_id = pointer["attempt_id"]
        if str(uuid.UUID(attempt_id)) != attempt_id:
            raise ValueError("INVALID_ATTEMPT")
        meta = _read_meta(attempt_id, username)
        if meta.get("owner") != username or meta.get("operation") != "extend":
            raise ValueError("OPERATION_MISMATCH")
        return get_login_attempt(attempt_id, requesting_username=username, now_provider=now_provider)
    except FileNotFoundError:
        if not marker:
            return {"action": "idle", "extension_attempted": False, "extension_succeeded": False}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, TossLoginNotFoundError):
        pass
    # Missing/corrupt metadata or missing completion proof must never release guard.
    return {"action": "pending" if marker and marker.get("type") == "extend" else "unknown",
            "extension_succeeded": False, "error_code": "AUTH_EXTEND_RESULT_UNCONFIRMED"}


def start_toss_session_extension(username: str) -> dict[str, Any]:
    """Shared entry for scheduled and user-requested extension, Linux only."""
    from app.services.toss_wts_login import _start_toss_auth, TossLoginLockError, TossLoginError
    # Reconcile completed prior attempt after restart before trying the same guard.
    get_toss_session_extension(username)
    try:
        started = _start_toss_auth(resolve_toss_wts_settings(), username=username, operation="extend")
        if isinstance(started, dict):
            return started
        return {"attempt_id": started, "action": "pending", "extension_attempted": True,
                "extension_succeeded": False}
    except TossLoginLockError:
        from app.services.toss_wts_auth_guard import _get_active_op_data
        marker = _get_active_op_data(username)
        return {"action": "deferred", "error_code": "AUTH_LOGIN_IN_PROGRESS" if marker and marker.get("type") == "login" else "TOSS_AUTH_OPERATION_BUSY",
                "extension_attempted": False, "extension_succeeded": False}
    except TossLoginError:
        return {"action": "status_failed", "error_code": "AUTH_EXTEND_START_FAILED",
                "extension_attempted": False, "extension_succeeded": False}


def classify_toss_extension(before: str | None, verified: dict[str, Any], *,
                            cli_exit_code: int, timed_out: bool, now: datetime) -> dict[str, Any]:
    """Pure result policy, called only AFTER the lifecycle proves whole-tree exit.

    This function produces no receipt and cannot release a marker or spawn auth.
    Orchestration unit tests may exercise it without claiming Linux exit proof.
    """
    previous = _parse_expiry({"server_expires_at": before}, now)
    expiry = _parse_expiry(verified, now)
    valid = verified["active"] and verified["valid"]
    extended = bool(valid and previous and expiry and expiry > previous)
    unchanged = bool(cli_exit_code == 0 and valid and previous is not None and expiry == previous)
    needs_qr = verified.get("error_code") in {"SESSION_INACTIVE", "SESSION_INVALID", "SESSION_MISSING", "CONFIG_DIR_MISSING"}
    return {"active": verified["active"], "valid": verified["valid"],
            "server_expires_at": verified["server_expires_at"], "hours_remaining": verified["hours_remaining"],
            "action": "extended" if extended else "unchanged" if unchanged else "reauth_required" if needs_qr else "extension_failed",
            "status": "success" if extended or unchanged else "failed",
            "error_code": None if extended or unchanged else "AUTH_EXTEND_TIMEOUT" if timed_out else
                          "AUTH_EXTEND_FAILED" if cli_exit_code != 0 else verified.get("error_code") or "AUTH_EXTEND_VERIFY_FAILED"}
