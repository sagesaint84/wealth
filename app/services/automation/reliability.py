"""Reliability policy for Wealth scheduled automation.

This module deliberately sits in front of the existing execution-state retry
query instead of replacing dispatcher/claim semantics.  It adds two bounded
behaviours:

* retry backoff for already-tracked failures; and
* same-day catch-up descriptors for jobs whose exact cron minute was missed.

Catch-up is intentionally conservative.  Jobs are never replayed from a prior
day, reminder catch-up is limited to the most recent missed slot, and Toss WTS
session maintenance is excluded because an unexpected late execution may
require interactive mobile approval.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.services.automation import execution_state as _execution_state
from app.services.settings import _TIME, get_effective_settings, time_to_slot_id
from app.services.system_settings import get_effective_system_settings
from app.services.user_manager import list_users

KST = _execution_state.KST

# Attempt 1 failure -> wait at least 1 minute before attempt 2.
# Attempt 2 failure -> wait at least 5 minutes before attempt 3.
RETRY_BACKOFF_SECONDS: dict[int, float] = {1: 60.0, 2: 300.0}

# Same-day replay windows.  These windows are deliberately short enough that a
# restarted host cannot unexpectedly replay stale work much later in the day.
CATCH_UP_WINDOWS_SECONDS: dict[str, float] = {
    "ipo_refresh_morning": 3 * 60 * 60,
    "ipo_refresh_evening": 3 * 60 * 60,
    "ipo_reminder": 30 * 60,
    "ipo_listing_reminder": 30 * 60,
    "daily_close": 3 * 60 * 60,
}

# Configuration/authorization failures do not become healthy merely because
# one minute passed.  Keep them visible in Phase 9 instead of burning attempts.
NON_RETRYABLE_ERROR_CODES = {
    "NO_GLOBAL_AUTOMATION_OWNER",
    "PERMISSION_DENIED",
    "SETTINGS_CORRUPT",
    "USER_NOT_REGISTERED",
}

_ORIGINAL_GET_RETRYABLE_EXECUTIONS = _execution_state.get_retryable_executions


def _test_policy_disabled() -> bool:
    """Preserve legacy exact-minute unit contracts unless a Phase 10 test opts in."""
    return (
        os.getenv("WEALTH_ENV", "").strip().lower() == "test"
        and os.getenv("WEALTH_AUTOMATION_RELIABILITY_TEST", "").strip() != "1"
    )


def _as_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timezone-aware datetime required for automation reliability")
    return value.astimezone(KST)


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _retry_backoff_satisfied(record: dict[str, Any], now: datetime) -> bool:
    if record.get("status") != "FAILED":
        return True

    error_code = str(record.get("last_error_code") or "").strip().upper()
    if error_code in NON_RETRYABLE_ERROR_CODES:
        return False

    attempt_count = int(record.get("attempt_count") or 1)
    delay = RETRY_BACKOFF_SECONDS.get(attempt_count, 300.0)
    anchor = _parse_iso(record.get("completed_at")) or _parse_iso(
        record.get("last_attempt_at")
    )
    if anchor is None:
        # Malformed legacy records fail closed instead of triggering a burst.
        return False
    return (now - anchor).total_seconds() >= delay


def _scheduled_datetime(now: datetime, time_str: str) -> datetime | None:
    if not isinstance(time_str, str) or not _TIME.fullmatch(time_str):
        return None
    hour, minute = (int(part) for part in time_str.split(":"))
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _is_missed_within_window(
    now: datetime,
    time_str: str,
    *,
    window_seconds: float,
) -> bool:
    scheduled = _scheduled_datetime(now, time_str)
    if scheduled is None:
        return False
    age = (now - scheduled).total_seconds()
    return 0 <= age <= window_seconds


def _resolve_global_owner(registered_usernames: set[str]) -> str | None:
    try:
        settings = get_effective_system_settings()
    except Exception:
        return None
    owner = settings.get("automation_owner")
    source = settings.get("automation_owner_source")
    if not owner or source == "none" or owner not in registered_usernames:
        return None
    return str(owner)


def _catch_up_record(
    *,
    key: str,
    job: str,
    scheduled_date: str,
    scheduled_time: str,
    scope: str,
    owner: str | None = None,
    username: str | None = None,
    slot: str | None = None,
    is_last_slot: bool | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "job": job,
        "scope": scope,
        "owner": owner,
        "username": username,
        "slot": slot,
        "is_last_slot": is_last_slot,
        "scheduled_date": scheduled_date,
        "scheduled_time": scheduled_time,
        "attempt_count": 1,
        "status": "MISSED",
        "catch_up": True,
    }


def resolve_catch_up_records(
    now: datetime,
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return safe same-day jobs that missed their exact dispatcher minute.

    Existing execution keys are never synthesized again; an existing FAILED or
    RUNNING record remains the responsibility of normal retry/stale recovery.
    """
    now_kst = _as_kst(now)
    scheduled_date = now_kst.strftime("%Y-%m-%d")
    executions = state.get("executions") if isinstance(state, dict) else {}
    if not isinstance(executions, dict):
        return []
    existing_keys = set(executions)

    try:
        users = [
            item
            for item in list_users()
            if isinstance(item, dict) and item.get("username")
        ]
    except Exception:
        return []
    users.sort(key=lambda item: str(item.get("username", "")))
    registered = {str(item["username"]) for item in users}

    catch_ups: list[dict[str, Any]] = []

    # Global IPO refreshes use the same deterministic global key as the exact
    # minute dispatcher.  Owner changes therefore cannot duplicate execution.
    global_owner = _resolve_global_owner(registered)
    if global_owner is not None:
        try:
            owner_settings = get_effective_settings(global_owner)
            automation = owner_settings.get("automation") or {}
        except Exception:
            automation = {}
        for job_name in ("ipo_refresh_morning", "ipo_refresh_evening"):
            cfg = automation.get(job_name) or {}
            scheduled_time = cfg.get("time")
            if not cfg.get("enabled") or not _is_missed_within_window(
                now_kst,
                scheduled_time,
                window_seconds=CATCH_UP_WINDOWS_SECONDS[job_name],
            ):
                continue
            key = _execution_state.build_execution_key(
                job=job_name,
                target_date=scheduled_date,
                time_str=scheduled_time,
                scope="global",
            )
            if key in existing_keys:
                continue
            catch_ups.append(
                _catch_up_record(
                    key=key,
                    job=job_name,
                    scheduled_date=scheduled_date,
                    scheduled_time=scheduled_time,
                    scope="global",
                    owner=global_owner,
                )
            )
            existing_keys.add(key)

    for user in users:
        username = str(user["username"])
        try:
            user_settings = get_effective_settings(username)
        except Exception:
            continue
        automation = user_settings.get("automation") or {}

        # For reminder families replay only the latest missed slot.  Replaying
        # every missed reminder after a short outage would create notification
        # bursts even though the underlying notifier is idempotent.
        for job_name, config_name in (
            ("ipo_reminder", "ipo_reminders"),
            ("ipo_listing_reminder", "ipo_listing_reminders"),
        ):
            cfg = automation.get(config_name) or {}
            if not cfg.get("enabled"):
                continue
            valid_times = [
                value
                for value in (cfg.get("times") or [])
                if isinstance(value, str) and _TIME.fullmatch(value)
            ]
            eligible = [
                value
                for value in valid_times
                if _is_missed_within_window(
                    now_kst,
                    value,
                    window_seconds=CATCH_UP_WINDOWS_SECONDS[job_name],
                )
            ]
            if not eligible:
                continue
            scheduled_time = max(eligible)
            slot = time_to_slot_id(scheduled_time)
            key = _execution_state.build_execution_key(
                job=job_name,
                target_date=scheduled_date,
                time_str=slot,
                scope="user",
                username=username,
                slot=slot,
            )
            if key in existing_keys:
                continue
            is_last_slot = None
            if job_name == "ipo_reminder":
                all_slots = [time_to_slot_id(value) for value in valid_times]
                is_last_slot = slot == max(all_slots) if all_slots else False
            catch_ups.append(
                _catch_up_record(
                    key=key,
                    job=job_name,
                    scheduled_date=scheduled_date,
                    scheduled_time=scheduled_time,
                    scope="user",
                    username=username,
                    slot=slot,
                    is_last_slot=is_last_slot,
                )
            )
            existing_keys.add(key)

        daily_close = automation.get("daily_close") or {}
        close_time = daily_close.get("time")
        if daily_close.get("enabled") and _is_missed_within_window(
            now_kst,
            close_time,
            window_seconds=CATCH_UP_WINDOWS_SECONDS["daily_close"],
        ):
            key = _execution_state.build_execution_key(
                job="daily_close",
                target_date=scheduled_date,
                time_str=close_time,
                scope="user",
                username=username,
            )
            if key not in existing_keys:
                catch_ups.append(
                    _catch_up_record(
                        key=key,
                        job="daily_close",
                        scheduled_date=scheduled_date,
                        scheduled_time=close_time,
                        scope="user",
                        username=username,
                    )
                )
                existing_keys.add(key)

        # Toss WTS session maintenance is deliberately NOT synthesized here.
        # A delayed run may unexpectedly ask for mobile approval.  It remains
        # exact-minute, non-retryable work and will run again at the next normal
        # schedule if one day is missed.

    return catch_ups


def get_retryable_executions_reliable(
    now: datetime,
    state: dict[str, Any] | None = None,
    *,
    path: Path | None = None,
    max_attempts: int = _execution_state.DEFAULT_MAX_ATTEMPTS,
    stale_seconds: float = _execution_state.DEFAULT_STALE_SECONDS,
) -> list[dict[str, Any]]:
    """Apply bounded backoff and catch-up around the existing retry query."""
    now_kst = _as_kst(now)
    base = _ORIGINAL_GET_RETRYABLE_EXECUTIONS(
        now_kst,
        state=state,
        path=path,
        max_attempts=max_attempts,
        stale_seconds=stale_seconds,
    )
    if _test_policy_disabled():
        return base

    filtered = [
        dict(record)
        for record in base
        if _retry_backoff_satisfied(record, now_kst)
    ]

    try:
        loaded_state = state if state is not None else _execution_state.load_execution_state(path)
        catch_ups = resolve_catch_up_records(now_kst, loaded_state)
    except Exception:
        # Reliability helpers must never prevent exact-minute scheduling.
        catch_ups = []

    existing = {record.get("key") for record in filtered if record.get("key")}
    for record in catch_ups:
        key = record.get("key")
        if key and key not in existing:
            filtered.append(record)
            existing.add(key)
    return filtered


def install_execution_state_reliability() -> None:
    """Install policy before dispatcher imports get_retryable_executions."""
    current = _execution_state.get_retryable_executions
    if getattr(current, "_wealth_reliability_policy", False):
        return
    setattr(get_retryable_executions_reliable, "_wealth_reliability_policy", True)
    _execution_state.get_retryable_executions = get_retryable_executions_reliable


__all__ = [
    "CATCH_UP_WINDOWS_SECONDS",
    "NON_RETRYABLE_ERROR_CODES",
    "RETRY_BACKOFF_SECONDS",
    "get_retryable_executions_reliable",
    "install_execution_state_reliability",
    "resolve_catch_up_records",
]
