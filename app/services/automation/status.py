"""Secret-safe automation execution status for the settings UI.

Reads the existing persistent automation execution state and projects only
operational metadata needed by the current user.  No raw exceptions, paths,
credentials, notification bodies, or provider responses are exposed.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from app.services.automation.execution_state import (
    DEFAULT_STALE_SECONDS,
    ExecutionStateCorruptError,
    ExecutionStateError,
    load_execution_state,
)
from app.services.settings import _TIME, get_effective_settings
from app.services.system_settings import resolve_toss_wts_settings

KST = timezone(timedelta(hours=9))
STATUS_VERSION = 1
MAX_RECENT = 50
MISSED_GRACE_MINUTES = 5

_JOB_LABELS = {
    "ipo_refresh_morning": "IPO 시장 데이터 오전 갱신",
    "ipo_reminder": "공모주 청약 알림",
    "ipo_listing_reminder": "공모주 상장일 알림",
    "ipo_refresh_evening": "IPO 시장 데이터 장후 갱신",
    "daily_close": "일일 마감",
    "toss_session_maintenance": "Toss WTS 세션 점검",
}

_DETAIL_KEYS = {
    "ipo_refresh_morning": {"total_ipos", "status"},
    "ipo_refresh_evening": {"total_ipos", "status"},
    "ipo_reminder": {
        "notifications_sent_count",
        "eligible_ipos",
        "all_applied_count",
    },
    "ipo_listing_reminder": {
        "notifications_sent_count",
        "eligible_ipos",
    },
    "daily_close": {
        "notification_status",
        "notification_dispatch_status",
        "notifications_sent_count",
        "stock_record_saved",
        "net_record_saved",
    },
    "toss_session_maintenance": {
        "action",
        "active",
        "valid",
        "server_expires_at",
        "hours_remaining",
        "extension_attempted",
        "extension_succeeded",
        "notification_status",
        "notification_dispatch_status",
        "notifications_sent_count",
        "error_code",
    },
}


class AutomationStatusError(RuntimeError):
    pass


def _now_kst(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError("Timezone-aware datetime required")
    return now.astimezone(KST)


def _valid_times(values: Iterable[Any]) -> list[str]:
    return sorted(
        {
            value
            for value in values
            if isinstance(value, str) and _TIME.fullmatch(value)
        }
    )


def _occurrence(day: datetime, value: str) -> datetime:
    hour, minute = (int(part) for part in value.split(":"))
    return datetime.combine(day.date(), time(hour, minute), tzinfo=KST)


def _schedule_window(
    times: list[str],
    *,
    enabled: bool,
    now: datetime,
) -> tuple[str | None, str | None]:
    """Return latest expected occurrence and next occurrence in KST."""
    if not enabled or not times:
        return None, None

    today_occurrences = [_occurrence(now, value) for value in times]
    future = [item for item in today_occurrences if item > now]
    if future:
        next_dt = min(future)
    else:
        tomorrow = now + timedelta(days=1)
        next_dt = _occurrence(tomorrow, times[0])

    past = [item for item in today_occurrences if item <= now]
    if past:
        expected = max(past)
    else:
        yesterday = now - timedelta(days=1)
        expected = _occurrence(yesterday, times[-1])
    return expected.isoformat(), next_dt.isoformat()


def _record_scheduled_at(record: dict[str, Any]) -> str | None:
    day = record.get("scheduled_date")
    raw_time = record.get("scheduled_time")
    if not isinstance(day, str) or not isinstance(raw_time, str) or not _TIME.fullmatch(raw_time):
        key = str(record.get("key") or "")
        parts = key.split(":")
        if len(parts) >= 4:
            possible_day = parts[-2]
            hhmm = parts[-1]
            if len(hhmm) == 4 and hhmm.isdigit():
                day = possible_day
                raw_time = f"{hhmm[:2]}:{hhmm[2:]}"
    if not isinstance(day, str) or not isinstance(raw_time, str) or not _TIME.fullmatch(raw_time):
        return None
    try:
        return datetime.fromisoformat(f"{day}T{raw_time}:00+09:00").isoformat()
    except ValueError:
        return None


def _safe_scalar(value: Any) -> Any:
    if value is None or type(value) in {bool, int, float}:
        return value
    if isinstance(value, str):
        return value[:128]
    return None


def _safe_details(job: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    allowed = _DETAIL_KEYS.get(job, set())
    out: dict[str, Any] = {}
    for key in allowed:
        if key in value:
            safe = _safe_scalar(value.get(key))
            if safe is not None:
                out[key] = safe
    return out


def _duration_seconds(record: dict[str, Any]) -> float | None:
    start = record.get("last_attempt_at") or record.get("first_claimed_at")
    end = record.get("completed_at")
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=KST)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=KST)
        return max(0.0, round((end_dt - start_dt).total_seconds(), 3))
    except (TypeError, ValueError):
        return None


def _project_record(record: dict[str, Any]) -> dict[str, Any]:
    job = str(record.get("job") or "")
    status = str(record.get("status") or "UNKNOWN").upper()
    if status not in {"RUNNING", "SUCCESS", "FAILED"}:
        status = "UNKNOWN"
    return {
        "job": job,
        "label": _JOB_LABELS.get(job, job or "자동화"),
        "scope": "global" if record.get("scope") == "global" else "user",
        "status": status,
        "scheduled_at": _record_scheduled_at(record),
        "started_at": record.get("first_claimed_at") if isinstance(record.get("first_claimed_at"), str) else None,
        "last_attempt_at": record.get("last_attempt_at") if isinstance(record.get("last_attempt_at"), str) else None,
        "completed_at": record.get("completed_at") if isinstance(record.get("completed_at"), str) else None,
        "duration_seconds": _duration_seconds(record),
        "attempt_count": int(record.get("attempt_count") or 0),
        "retryable": record.get("retryable") is not False,
        "error_code": (
            str(record.get("last_error_code"))[:64]
            if record.get("last_error_code")
            else None
        ),
        "details": _safe_details(job, record.get("details")),
    }


def _record_relevant(record: dict[str, Any], username: str) -> bool:
    if record.get("scope") == "global":
        return record.get("job") in {"ipo_refresh_morning", "ipo_refresh_evening"}
    if record.get("username") == username:
        return record.get("job") in _JOB_LABELS
    # Toss session descriptors historically stored the user in owner rather
    # than username while still using user scope.
    return (
        record.get("job") == "toss_session_maintenance"
        and record.get("owner") == username
    )


def _record_sort_value(record: dict[str, Any]) -> datetime:
    for key in ("last_attempt_at", "completed_at", "first_claimed_at"):
        raw = record.get(key)
        if isinstance(raw, str):
            try:
                value = datetime.fromisoformat(raw)
                return value if value.tzinfo else value.replace(tzinfo=KST)
            except ValueError:
                pass
    return datetime.min.replace(tzinfo=KST)


def _health_status(
    *,
    enabled: bool,
    configured: bool,
    expected_at: str | None,
    last_record: dict[str, Any] | None,
    records: list[dict[str, Any]],
    now: datetime,
) -> str:
    if not enabled:
        return "disabled"
    if not configured:
        return "unconfigured"

    if expected_at:
        try:
            expected_dt = datetime.fromisoformat(expected_at)
        except ValueError:
            expected_dt = None
        if expected_dt is not None and now >= expected_dt + timedelta(minutes=MISSED_GRACE_MINUTES):
            matched = any(_record_scheduled_at(rec) == expected_dt.isoformat() for rec in records)
            if not matched:
                return "missed"

    if not last_record:
        return "never_run"
    status = str(last_record.get("status") or "").upper()
    if status == "SUCCESS":
        return "success"
    if status == "FAILED":
        return "failed"
    if status == "RUNNING":
        raw = last_record.get("last_attempt_at") or last_record.get("first_claimed_at")
        if isinstance(raw, str):
            try:
                started = datetime.fromisoformat(raw)
                if started.tzinfo is None:
                    started = started.replace(tzinfo=KST)
                if (now - started.astimezone(KST)).total_seconds() >= DEFAULT_STALE_SECONDS:
                    return "stale"
            except ValueError:
                return "stale"
        return "running"
    return "unknown"


def _job_summary(
    *,
    job: str,
    scope: str,
    enabled: bool,
    configured: bool,
    times: list[str],
    reason: str | None,
    records: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    expected_at, next_at = _schedule_window(times, enabled=enabled and configured, now=now)
    own_records = [record for record in records if record.get("job") == job]
    own_records.sort(key=_record_sort_value, reverse=True)
    last_record = own_records[0] if own_records else None
    health = _health_status(
        enabled=enabled,
        configured=configured,
        expected_at=expected_at,
        last_record=last_record,
        records=own_records,
        now=now,
    )
    return {
        "job": job,
        "label": _JOB_LABELS[job],
        "scope": scope,
        "enabled": bool(enabled),
        "configured": bool(configured),
        "reason": reason,
        "schedules": times,
        "last_expected_at": expected_at,
        "next_run_at": next_at,
        "health": health,
        "last_execution": _project_record(last_record) if last_record else None,
    }


def build_automation_status(
    username: str,
    *,
    now: datetime | None = None,
    state_path: Path | None = None,
    recent_limit: int = 20,
) -> dict[str, Any]:
    """Build the current user's operational automation status projection."""
    if type(recent_limit) is not int or not 1 <= recent_limit <= MAX_RECENT:
        raise ValueError("AUTOMATION_STATUS_LIMIT_INVALID")
    current = _now_kst(now)

    try:
        user_settings = get_effective_settings(username)
        state = load_execution_state(state_path)
    except (ExecutionStateCorruptError, ExecutionStateError, OSError) as exc:
        raise AutomationStatusError("AUTOMATION_STATUS_UNAVAILABLE") from exc
    except Exception as exc:
        raise AutomationStatusError("AUTOMATION_STATUS_UNAVAILABLE") from exc

    relevant_records = [
        dict(record)
        for record in state.get("executions", {}).values()
        if isinstance(record, dict) and _record_relevant(record, username)
    ]

    # Global IPO refresh jobs use the configured global automation owner's
    # schedule, not the viewer's own settings.
    try:
        from app.services.automation.dispatcher import resolve_global_automation_owner

        global_owner = resolve_global_automation_owner()
        global_settings = get_effective_settings(global_owner) if global_owner else None
    except Exception:
        global_owner = None
        global_settings = None

    global_automation = (global_settings or {}).get("automation") or {}
    user_automation = user_settings.get("automation") or {}

    global_configured = global_owner is not None and global_settings is not None
    global_reason = None if global_configured else "NO_GLOBAL_AUTOMATION_OWNER"

    morning = global_automation.get("ipo_refresh_morning") or {}
    evening = global_automation.get("ipo_refresh_evening") or {}
    reminders = user_automation.get("ipo_reminders") or {}
    listing = user_automation.get("ipo_listing_reminders") or {}
    daily = user_automation.get("daily_close") or {}

    try:
        toss_cfg = resolve_toss_wts_settings()
    except Exception:
        toss_cfg = {}
    allowed_users = set(toss_cfg.get("allowed_users") or [])
    toss_allowed = not allowed_users or username in allowed_users
    toss_global_enabled = (
        toss_cfg.get("enabled") is True
        and toss_cfg.get("session_check_enabled") is True
        and toss_allowed
    )
    toss_user_enabled = (
        user_settings.get("toss_wts", {}).get("session_check_enabled") is True
    )
    toss_configured = bool(toss_global_enabled)
    toss_enabled = bool(toss_global_enabled and toss_user_enabled)
    if not toss_allowed:
        toss_reason = "TOSS_WTS_NOT_ALLOWED"
    elif toss_cfg.get("enabled") is not True:
        toss_reason = "TOSS_WTS_DISABLED"
    elif toss_cfg.get("session_check_enabled") is not True:
        toss_reason = "TOSS_WTS_GLOBAL_CHECK_DISABLED"
    else:
        toss_reason = None

    jobs = [
        _job_summary(
            job="ipo_refresh_morning",
            scope="global",
            enabled=morning.get("enabled") is True,
            configured=global_configured,
            times=_valid_times([morning.get("time")]),
            reason=global_reason,
            records=relevant_records,
            now=current,
        ),
        _job_summary(
            job="ipo_reminder",
            scope="user",
            enabled=reminders.get("enabled") is True,
            configured=True,
            times=_valid_times(reminders.get("times") or []),
            reason=None,
            records=relevant_records,
            now=current,
        ),
        _job_summary(
            job="ipo_listing_reminder",
            scope="user",
            enabled=listing.get("enabled") is True,
            configured=True,
            times=_valid_times(listing.get("times") or []),
            reason=None,
            records=relevant_records,
            now=current,
        ),
        _job_summary(
            job="ipo_refresh_evening",
            scope="global",
            enabled=evening.get("enabled") is True,
            configured=global_configured,
            times=_valid_times([evening.get("time")]),
            reason=global_reason,
            records=relevant_records,
            now=current,
        ),
        _job_summary(
            job="daily_close",
            scope="user",
            enabled=daily.get("enabled") is True,
            configured=True,
            times=_valid_times([daily.get("time")]),
            reason=None,
            records=relevant_records,
            now=current,
        ),
        _job_summary(
            job="toss_session_maintenance",
            scope="user",
            enabled=toss_enabled,
            configured=toss_configured,
            times=_valid_times([toss_cfg.get("session_check_time")]),
            reason=toss_reason,
            records=relevant_records,
            now=current,
        ),
    ]

    relevant_records.sort(key=_record_sort_value, reverse=True)
    recent = [_project_record(record) for record in relevant_records[:recent_limit]]

    counts = {
        "success": sum(1 for job in jobs if job["health"] == "success"),
        "warning": sum(
            1 for job in jobs if job["health"] in {"failed", "stale", "missed"}
        ),
        "running": sum(1 for job in jobs if job["health"] == "running"),
        "enabled": sum(1 for job in jobs if job["enabled"]),
    }

    return {
        "version": STATUS_VERSION,
        "timezone": "Asia/Seoul",
        "generated_at": current.isoformat(),
        "state_updated_at": state.get("updated_at") if isinstance(state.get("updated_at"), str) else None,
        "counts": counts,
        "jobs": jobs,
        "recent": recent,
    }
