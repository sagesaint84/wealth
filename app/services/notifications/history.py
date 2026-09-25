"""User-scoped, secret-safe notification delivery history."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.network_policy import is_test_mode
from app.services.settings import _path as settings_path

HISTORY_VERSION = 1
HISTORY_RETENTION = 100
_STATUS_VALUES = {"sent", "partial", "disabled", "unconfigured", "failed", "skipped"}
_PROVIDER_VALUES = ("telegram", "discord", "kakao")
_EVENT_TYPE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_ERROR_CODE = re.compile(r"^[A-Z0-9_]{1,64}$")
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


class NotificationHistoryError(RuntimeError):
    pass


def history_path(username: str) -> Path:
    return settings_path(username).parent / "notifications" / "history.json"


def _empty() -> dict[str, Any]:
    return {"version": HISTORY_VERSION, "events": []}


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


@contextmanager
def _history_lock(path: Path):
    """Serialize read-modify-write cycles across threads and processes."""
    thread_lock = _lock_for(path)
    with thread_lock:
        lock_path = path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(lock_path.parent, 0o700)
        handle = open(lock_path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt

                if lock_path.stat().st_size == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            if os.name == "posix":
                os.chmod(lock_path, 0o600)
            yield
        finally:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


def _sanitize_event_type(value: Any) -> str:
    text = str(value or "").strip()
    return text if _EVENT_TYPE.fullmatch(text) else "notification"


def _sanitize_error(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if _ERROR_CODE.fullmatch(text) else "SEND_FAILED"


def _sanitize_provider_result(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    status = str(data.get("status") or "failed")
    if status not in _STATUS_VALUES:
        status = "failed"
    return {
        "sent": data.get("sent") is True,
        "status": status,
        "retryable": data.get("retryable") is True,
        "error": _sanitize_error(data.get("error")),
    }


def _sanitize_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise NotificationHistoryError("NOTIFICATION_HISTORY_STATE_INVALID")
    created_at = record.get("created_at")
    event_type = record.get("event_type")
    fingerprint = record.get("event_key_fingerprint")
    status = record.get("status")
    sent_count = record.get("notifications_sent_count")
    providers = record.get("providers")
    if (
        not isinstance(created_at, str)
        or not isinstance(fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{12}", fingerprint)
        or status not in _STATUS_VALUES
        or type(sent_count) is not int
        or sent_count < 0
        or not isinstance(providers, dict)
        or set(providers) - set(_PROVIDER_VALUES)
    ):
        raise NotificationHistoryError("NOTIFICATION_HISTORY_STATE_INVALID")
    return {
        "created_at": created_at,
        "event_type": _sanitize_event_type(event_type),
        "event_key_fingerprint": fingerprint,
        "status": status,
        "notifications_sent_count": sent_count,
        "providers": {
            provider: _sanitize_provider_result(providers[provider])
            for provider in _PROVIDER_VALUES
            if provider in providers
        },
    }


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NotificationHistoryError("NOTIFICATION_HISTORY_STATE_INVALID") from exc
    if (
        not isinstance(data, dict)
        or data.get("version") != HISTORY_VERSION
        or not isinstance(data.get("events"), list)
    ):
        raise NotificationHistoryError("NOTIFICATION_HISTORY_STATE_INVALID")
    return {
        "version": HISTORY_VERSION,
        "events": [_sanitize_record(item) for item in data["events"]],
    }


def _save(data: dict[str, Any], path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(path.parent, 0o700)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        if os.name == "posix":
            os.chmod(path, 0o600)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def record_notification_history(
    username: str,
    event: Any,
    report: Any,
    *,
    path: Path | None = None,
    now: datetime | None = None,
) -> None:
    """Persist one delivery report without storing notification content or secrets."""
    if path is None and is_test_mode():
        return
    target = path or history_path(username)
    created_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    raw_key = str(getattr(event, "event_key", "") or "")
    fingerprint = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]
    provider_results = getattr(report, "provider_results", {})
    record = {
        "created_at": created_at,
        "event_type": _sanitize_event_type(getattr(event, "event_type", None)),
        "event_key_fingerprint": fingerprint,
        "status": str(getattr(report, "status", "failed")),
        "notifications_sent_count": int(
            getattr(report, "notifications_sent_count", 0) or 0
        ),
        "providers": {
            provider: _sanitize_provider_result(provider_results.get(provider))
            for provider in _PROVIDER_VALUES
            if provider in provider_results
        },
    }
    if record["status"] not in _STATUS_VALUES:
        record["status"] = "failed"

    with _history_lock(target):
        data = _load(target)
        events = data["events"]
        events.append(record)
        data["events"] = events[-HISTORY_RETENTION:]
        _save(data, target)


def record_single_provider_history(
    username: str,
    event: Any,
    *,
    provider: str,
    success: bool,
    retryable: bool = False,
    error: str | None = None,
    path: Path | None = None,
    now: datetime | None = None,
) -> None:
    """Record a direct/manual provider send without requiring the common service."""
    if provider not in _PROVIDER_VALUES:
        raise ValueError("NOTIFICATION_PROVIDER_INVALID")

    class _Report:
        status = "sent" if success else "failed"
        notifications_sent_count = 1 if success else 0
        provider_results = {
            provider: {
                "sent": bool(success),
                "status": "sent" if success else "failed",
                "retryable": bool(retryable),
                "error": None if success else _sanitize_error(error),
            }
        }

    record_notification_history(
        username,
        event,
        _Report(),
        path=path,
        now=now,
    )


def list_notification_history(
    username: str,
    *,
    limit: int = 20,
    path: Path | None = None,
) -> dict[str, Any]:
    if type(limit) is not int or not 1 <= limit <= HISTORY_RETENTION:
        raise ValueError("NOTIFICATION_HISTORY_LIMIT_INVALID")
    if path is None and is_test_mode():
        return {
            "version": HISTORY_VERSION,
            "retention": HISTORY_RETENTION,
            "count": 0,
            "events": [],
        }
    target = path or history_path(username)
    with _history_lock(target):
        data = _load(target)
    events = list(reversed(data["events"][-limit:]))
    return {
        "version": HISTORY_VERSION,
        "retention": HISTORY_RETENTION,
        "count": len(data["events"]),
        "events": events,
    }


def clear_notification_history(
    username: str,
    *,
    path: Path | None = None,
) -> int:
    if path is None and is_test_mode():
        return 0
    target = path or history_path(username)
    with _history_lock(target):
        try:
            data = _load(target)
            deleted = len(data["events"])
        except NotificationHistoryError:
            # Clearing is also the recovery path for a corrupt history file.
            deleted = 0
        _save(_empty(), target)
    return deleted
