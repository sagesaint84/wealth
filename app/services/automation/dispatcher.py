"""Wealth Automation Dispatcher Service.

Evaluates stored automation schedules across registered users, determines due jobs
for the current exact minute (Asia/Seoul), and dispatches corresponding Python services
without HTTP bypass or persistent execution state (A2).
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.services.automation.daily_close import run_daily_close_for_user
from app.services.automation.execution_state import (
    DEFAULT_MAX_ATTEMPTS,
    DEFAULT_STALE_SECONDS,
    ExecutionStateLockError,
    build_execution_key,
    claim_execution,
    get_retryable_executions,
    record_execution_failure,
    record_execution_success,
    sanitize_error_code,
)
from app.services.ipo.orchestrator import refresh_ipo_market_enriched
from app.services.ipo.reminders import run_ipo_listing_reminders, run_ipo_subscription_reminders
from app.services.settings import (
    _TIME,
    get_effective_settings,
    time_to_slot_id,
)
from app.services.system_settings import get_effective_system_settings
from app.services.toss_wts_session import run_toss_session_maintenance
from app.services.user_manager import list_users

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def resolve_global_automation_owner(
    *,
    registered_usernames: set[str] | None = None,
) -> str | None:
    """Deterministically resolve the single global automation owner.

    Precedence:
    1. Stored system settings automation_owner (highest priority).
    2. Optional / legacy environment fallback WEALTH_AUTOMATION_OWNER.
    3. If unconfigured or unregistered, returns None (no silent fallback).
    (Never uses telegram_webhook_owner, users[0], or hardcoded names).
    """
    if registered_usernames is None:
        registered_usernames = {
            u["username"]
            for u in list_users()
            if isinstance(u, dict) and u.get("username")
        }

    try:
        sys_settings = get_effective_system_settings()
        owner = sys_settings.get("automation_owner")
        source = sys_settings.get("automation_owner_source")

        if not owner or source == "none":
            return None

        if owner not in registered_usernames:
            if source == "stored":
                logger.warning(
                    "Stored automation_owner '%s' is not in registered users (INVALID_GLOBAL_AUTOMATION_OWNER). Failing closed.",
                    owner,
                )
            else:
                logger.warning(
                    "Environment WEALTH_AUTOMATION_OWNER '%s' is not in registered users. Failing closed.",
                    owner,
                )
            return None

        return owner
    except Exception as exc:
        logger.warning("Failed to read system settings for automation owner: %s", exc)
        return None


def resolve_due_jobs(
    now: datetime | None = None,
    *,
    state_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Resolve which automation jobs are due at the given exact minute, including retries.

    Pure, side-effect-free function.
    Deterministic order:
    1. Global IPO refresh jobs (morning, evening)
    2. User-scoped jobs (sorted by username, then reminders, then daily close)
    3. Retryable failed or stale jobs from execution state
    """
    if now is None:
        current_dt = datetime.now(KST)
    else:
        if now.tzinfo is None:
            raise ValueError("Timezone-aware datetime required for schedule resolution")
        current_dt = now.astimezone(KST)

    current_time_str = current_dt.strftime("%H:%M")
    current_date_str = current_dt.strftime("%Y-%m-%d")

    # Retrieve valid registered users only
    users = list_users()
    registered_usernames = {
        u["username"]
        for u in users
        if isinstance(u, dict) and u.get("username")
    }

    due_jobs: list[dict[str, Any]] = []

    # 1. Global Jobs: IPO refresh and Toss session maintenance
    global_owner = resolve_global_automation_owner(
        registered_usernames=registered_usernames
    )

    try:
        from app.services.system_settings import resolve_toss_wts_settings as _resolve_toss_cfg
        toss_cfg = _resolve_toss_cfg()
        toss_time = toss_cfg.get("session_check_time", "20:55")
        if toss_cfg.get("session_check_enabled") is True and toss_time == current_time_str:
            # Per-user toss_session_maintenance: one job per registered user.
            # Respects allowed_users allowlist: empty list = all users allowed.
            allowed = set(toss_cfg.get("allowed_users") or [])
            for _u in users:
                _uname = _u.get("username", "") if isinstance(_u, dict) else ""
                if not _uname:
                    continue
                if allowed and _uname not in allowed:
                    continue
                # Automatic extension is an opt-in of the owner of this
                # session.  The system setting is only the global feature
                # gate; it must never schedule every registered user.
                try:
                    if not get_effective_settings(_uname).get("toss_wts", {}).get("session_check_enabled", False):
                        continue
                except Exception:
                    logger.warning("Failed to load Toss session preference for user '%s'", _uname)
                    continue
                due_jobs.append({
                    "job": "toss_session_maintenance",
                    "scope": "user",
                    "owner": _uname,
                    "scheduled_time": toss_time,
                    "retryable": False,
                    "execution_key": build_execution_key(
                        job="toss_session_maintenance",
                        target_date=current_date_str,
                        time_str=toss_time,
                        scope="user",
                        username=_uname,
                    ),
                })
    except Exception:
        logger.warning("Failed to resolve Toss session maintenance settings")


    if global_owner is not None:
        try:
            owner_settings = get_effective_settings(global_owner)
            automation = owner_settings.get("automation") or {}
            morning = automation.get("ipo_refresh_morning") or {}
            if morning.get("enabled") and morning.get("time") == current_time_str:
                m_time = morning.get("time")
                due_jobs.append({
                    "job": "ipo_refresh_morning",
                    "scope": "global",
                    "owner": global_owner,
                    "scheduled_time": m_time,
                    "execution_key": build_execution_key(
                        job="ipo_refresh_morning",
                        target_date=current_date_str,
                        time_str=m_time,
                        scope="global",
                    ),
                })

            evening = automation.get("ipo_refresh_evening") or {}
            if evening.get("enabled") and evening.get("time") == current_time_str:
                e_time = evening.get("time")
                due_jobs.append({
                    "job": "ipo_refresh_evening",
                    "scope": "global",
                    "owner": global_owner,
                    "scheduled_time": e_time,
                    "execution_key": build_execution_key(
                        job="ipo_refresh_evening",
                        target_date=current_date_str,
                        time_str=e_time,
                        scope="global",
                    ),
                })
        except Exception as exc:
            logger.error("Failed to load global owner '%s' settings: %s", global_owner, exc)
            due_jobs.append({
                "job": "global_settings_resolution",
                "scope": "global",
                "owner": global_owner,
                "scheduled_time": current_time_str,
                "status": "failed",
                "error": f"Failed to load global automation owner settings: {exc}",
            })
    else:
        # If owner is absent and time matches default schedule, report unconfigured
        if current_time_str == "07:30":
            due_jobs.append({
                "job": "ipo_refresh_morning",
                "scope": "global",
                "owner": None,
                "scheduled_time": "07:30",
                "status": "unconfigured",
                "error": "NO_GLOBAL_AUTOMATION_OWNER",
            })
        elif current_time_str == "18:30":
            due_jobs.append({
                "job": "ipo_refresh_evening",
                "scope": "global",
                "owner": None,
                "scheduled_time": "18:30",
                "status": "unconfigured",
                "error": "NO_GLOBAL_AUTOMATION_OWNER",
            })

    # 2. Per-User Jobs (sorted deterministically by username)
    sorted_users = sorted(
        [u for u in users if isinstance(u, dict) and u.get("username")],
        key=lambda u: str(u.get("username", "")),
    )

    for user_item in sorted_users:
        username = user_item["username"]
        try:
            user_settings = get_effective_settings(username)
        except Exception as exc:
            logger.error("Corrupt settings for user '%s': %s", username, exc)
            due_jobs.append({
                "job": "user_settings_resolution",
                "scope": "user",
                "username": username,
                "scheduled_time": current_time_str,
                "status": "failed",
                "error": f"Failed to load user settings: {exc}",
            })
            continue

        automation = user_settings.get("automation") or {}

        # 2a. IPO reminders
        reminders_cfg = automation.get("ipo_reminders") or {}
        if reminders_cfg.get("enabled"):
            times = reminders_cfg.get("times") or []
            if current_time_str in times:
                slot = time_to_slot_id(current_time_str)
                configured_slots = [
                    time_to_slot_id(t)
                    for t in times
                    if isinstance(t, str) and _TIME.fullmatch(t)
                ]
                is_last = (slot == max(configured_slots)) if configured_slots else False
                due_jobs.append({
                    "job": "ipo_reminder",
                    "scope": "user",
                    "username": username,
                    "slot": slot,
                    "scheduled_time": current_time_str,
                    "is_last_slot": is_last,
                    "execution_key": build_execution_key(
                        job="ipo_reminder",
                        target_date=current_date_str,
                        time_str=slot,
                        scope="user",
                        username=username,
                        slot=slot,
                    ),
                })

        # 2b. IPO listing-day reminders
        listing_cfg = automation.get("ipo_listing_reminders") or {}
        if listing_cfg.get("enabled") and current_time_str in (listing_cfg.get("times") or []):
            slot = time_to_slot_id(current_time_str)
            due_jobs.append({
                "job": "ipo_listing_reminder",
                "scope": "user",
                "username": username,
                "slot": slot,
                "scheduled_time": current_time_str,
                "execution_key": build_execution_key(
                    job="ipo_listing_reminder", target_date=current_date_str,
                    time_str=slot, scope="user", username=username, slot=slot,
                ),
            })

        # 2c. Daily close
        daily_close_cfg = automation.get("daily_close") or {}
        if daily_close_cfg.get("enabled"):
            close_time = daily_close_cfg.get("time")
            if close_time == current_time_str:
                due_jobs.append({
                    "job": "daily_close",
                    "scope": "user",
                    "username": username,
                    "scheduled_time": close_time,
                    "execution_key": build_execution_key(
                        job="daily_close",
                        target_date=current_date_str,
                        time_str=close_time,
                        scope="user",
                        username=username,
                    ),
                })

    # 3. Check for retryable executions from state
    try:
        retryables = get_retryable_executions(current_dt, path=state_path)
    except Exception as exc:
        logger.warning("Failed to check retryable executions: %s", exc)
        retryables = []

    existing_keys = {j.get("execution_key") for j in due_jobs if j.get("execution_key")}

    for rec in retryables:
        key = rec.get("key")
        if not key or key in existing_keys:
            continue

        scope = rec.get("scope")
        job_type = rec.get("job")

        if scope == "global":
            orig_owner = rec.get("owner") or global_owner
            if not orig_owner or orig_owner not in registered_usernames:
                logger.warning("Original global automation owner '%s' is not registered. Failing closed.", orig_owner)
                due_jobs.append({
                    "job": job_type,
                    "scope": "global",
                    "owner": orig_owner,
                    "scheduled_time": rec.get("scheduled_time"),
                    "execution_key": key,
                    "is_retry": True,
                    "attempt_count": rec.get("attempt_count", 1),
                    "status": "failed",
                    "error": "USER_NOT_REGISTERED",
                })
                existing_keys.add(key)
                continue

            due_jobs.append({
                "job": job_type,
                "scope": "global",
                "owner": orig_owner,
                "scheduled_time": rec.get("scheduled_time"),
                "execution_key": key,
                "is_retry": True,
                "attempt_count": rec.get("attempt_count", 1),
            })
            existing_keys.add(key)
        elif scope == "user":
            rec_user = rec.get("username")
            if rec_user and rec_user in registered_usernames:
                retry_job = {
                    "job": job_type,
                    "scope": "user",
                    "username": rec_user,
                    "scheduled_time": rec.get("scheduled_time"),
                    "execution_key": key,
                    "is_retry": True,
                    "attempt_count": rec.get("attempt_count", 1),
                }
                if rec.get("slot"):
                    retry_job["slot"] = rec["slot"]
                    if job_type == "ipo_reminder":
                        if "is_last_slot" in rec and rec["is_last_slot"] is not None:
                            retry_job["is_last_slot"] = bool(rec["is_last_slot"])
                        else:
                            try:
                                u_cfg = get_effective_settings(rec_user)
                                u_times = u_cfg.get("automation", {}).get("ipo_reminders", {}).get("times") or []
                                u_slots = [
                                    time_to_slot_id(t)
                                    for t in u_times
                                    if isinstance(t, str) and _TIME.fullmatch(t)
                                ]
                                retry_job["is_last_slot"] = (rec["slot"] == max(u_slots)) if u_slots else False
                            except Exception:
                                retry_job["is_last_slot"] = False
                due_jobs.append(retry_job)
                existing_keys.add(key)

    return due_jobs


async def execute_job(
    job: dict[str, Any],
    *,
    now: datetime,
    daily_close_runner: Callable[..., Any] | None = None,
    reminder_runner: Callable[..., Any] | None = None,
    listing_reminder_runner: Callable[..., Any] | None = None,
    ipo_refresh_runner: Callable[..., Any] | None = None,
    toss_session_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Execute a single due job with error isolation and secret-safe result."""
    job_type = job.get("job")
    scheduled_time = job.get("scheduled_time")

    # Handle already-errored/unconfigured job descriptors
    if "status" in job:
        return dict(job)

    if job_type == "toss_session_maintenance":
        owner = job.get("owner")
        scope = job.get("scope", "user")
        runner = toss_session_runner or run_toss_session_maintenance
        try:
            res = await asyncio.to_thread(runner, owner, now=now)
            if res.get("action") in {"not_required", "extended"}:
                return {"job": job_type, "scope": scope, "owner": owner, "scheduled_time": scheduled_time, "status": "success", "details": {key: res.get(key) for key in ("action", "active", "valid", "server_expires_at", "hours_remaining", "extension_attempted", "extension_succeeded", "notification_status", "error_code")}}
            return {"job": job_type, "scope": scope, "owner": owner, "scheduled_time": scheduled_time, "status": "failed", "error": res.get("error_code") or "TOSS_SESSION_MAINTENANCE_FAILED", "details": {key: res.get(key) for key in ("action", "active", "valid", "extension_attempted", "extension_succeeded", "notification_status", "error_code")}}
        except Exception:
            logger.exception("Toss session maintenance failed")
            return {"job": job_type, "scope": scope, "owner": owner, "scheduled_time": scheduled_time, "status": "failed", "error": "TOSS_SESSION_MAINTENANCE_FAILED"}


    if job_type in ("ipo_refresh_morning", "ipo_refresh_evening"):
        owner = job.get("owner")
        target_date_str = now.astimezone(KST).date().isoformat()
        runner = ipo_refresh_runner or refresh_ipo_market_enriched
        try:
            if inspect.iscoroutinefunction(runner):
                res = await runner(username=owner, target_date_str=target_date_str)
            else:
                res = await asyncio.to_thread(runner, username=owner, target_date_str=target_date_str)

            return {
                "job": job_type,
                "scope": "global",
                "owner": owner,
                "scheduled_time": scheduled_time,
                "status": "success",
                "details": {
                    "total_ipos": res.get("total_ipos", 0),
                    "status": res.get("status", "ok"),
                },
            }
        except Exception as exc:
            logger.exception("Global IPO refresh job '%s' failed", job_type)
            return {
                "job": job_type,
                "scope": "global",
                "owner": owner,
                "scheduled_time": scheduled_time,
                "status": "failed",
                "error": str(exc),
            }

    if job_type == "ipo_reminder":
        username = job.get("username")
        slot = job.get("slot")
        is_last_slot = bool(job.get("is_last_slot"))
        today = now.astimezone(KST).date()
        runner = reminder_runner or run_ipo_subscription_reminders
        try:
            if inspect.iscoroutinefunction(runner):
                res = await runner(
                    username=username,
                    reminder_slot=slot,
                    today=today,
                    is_last_slot=is_last_slot,
                )
            else:
                res = await asyncio.to_thread(
                    runner,
                    username=username,
                    reminder_slot=slot,
                    today=today,
                    is_last_slot=is_last_slot,
                )

            return {
                "job": "ipo_reminder",
                "scope": "user",
                "username": username,
                "slot": slot,
                "scheduled_time": scheduled_time,
                "status": "success",
                "is_last_slot": is_last_slot,
                "details": {
                    "notifications_sent_count": res.get("notifications_sent_count", 0),
                    "eligible_ipos": res.get("eligible_ipos", 0),
                    "all_applied_count": res.get("all_applied_count", 0),
                },
            }

        except Exception as exc:
            logger.exception("IPO reminder job failed for '%s' slot %s", username, slot)
            return {
                "job": "ipo_reminder",
                "scope": "user",
                "username": username,
                "slot": slot,
                "scheduled_time": scheduled_time,
                "status": "failed",
                "error": str(exc),
            }

    if job_type == "ipo_listing_reminder":
        username = job.get("username")
        slot = job.get("slot")
        runner = listing_reminder_runner or run_ipo_listing_reminders
        try:
            kwargs = {"username": username, "reminder_slot": slot, "today": now.astimezone(KST).date()}
            res = await runner(**kwargs) if inspect.iscoroutinefunction(runner) else await asyncio.to_thread(runner, **kwargs)
            return {
                "job": job_type, "scope": "user", "username": username,
                "slot": slot, "scheduled_time": scheduled_time, "status": "success",
                "details": {key: res.get(key, 0) for key in ("notifications_sent_count", "eligible_ipos")},
            }
        except Exception as exc:
            logger.exception("IPO listing reminder job failed for '%s' slot %s", username, slot)
            return {"job": job_type, "scope": "user", "username": username,
                    "slot": slot, "scheduled_time": scheduled_time,
                    "status": "failed", "error": str(exc)}

    if job_type == "daily_close":
        username = job.get("username")
        runner = daily_close_runner or run_daily_close_for_user
        try:
            if inspect.iscoroutinefunction(runner):
                res = await runner(username, now=now)
            else:
                res = await asyncio.to_thread(runner, username, now=now)

            if res.get("ok"):
                return {
                    "job": "daily_close",
                    "scope": "user",
                    "username": username,
                    "scheduled_time": scheduled_time,
                    "status": "success",
                    "details": {
                        "telegram_sent": res.get("telegram_sent", False),
                        "notification_status": res.get("notification_status"),
                        "notification_dispatch_status": res.get(
                            "notification_dispatch_status"
                        ),
                        "notifications_sent_count": res.get(
                            "notifications_sent_count", 0
                        ),
                        "stock_record_saved": res.get("stock_record_saved", False),
                        "net_record_saved": res.get("net_record_saved", False),
                    },
                }
            else:
                return {
                    "job": "daily_close",
                    "scope": "user",
                    "username": username,
                    "scheduled_time": scheduled_time,
                    "status": "failed",
                    "error": res.get("error", "daily close failed"),
                    "failed_step": res.get("failed_step"),
                }
        except Exception as exc:
            logger.exception("Daily close job failed for '%s'", username)
            return {
                "job": "daily_close",
                "scope": "user",
                "username": username,
                "scheduled_time": scheduled_time,
                "status": "failed",
                "error": str(exc),
            }

    return {
        "job": job_type,
        "scope": job.get("scope", "unknown"),
        "scheduled_time": scheduled_time,
        "status": "failed",
        "error": f"Unknown job type: {job_type}",
    }


async def run_due_automation(
    *,
    now: datetime | None = None,
    dry_run: bool = False,
    state_path: Path | None = None,
    daily_close_runner: Callable[..., Any] | None = None,
    reminder_runner: Callable[..., Any] | None = None,
    listing_reminder_runner: Callable[..., Any] | None = None,
    ipo_refresh_runner: Callable[..., Any] | None = None,
    toss_session_runner: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Primary automation dispatcher entry point.

    Resolves due jobs for the given exact minute (or current Asia/Seoul time),
    claims execution with persistent state tracking and locking, and executes
    them deterministically with error isolation.
    """
    if now is None:
        current_dt = datetime.now(KST)
    else:
        if now.tzinfo is None:
            raise ValueError("Timezone-aware datetime required for schedule resolution")
        current_dt = now.astimezone(KST)

    due_jobs = resolve_due_jobs(current_dt, state_path=state_path)

    if dry_run:
        return {
            "now": current_dt.isoformat(),
            "dry_run": True,
            "jobs": due_jobs,
        }

    executed_jobs: list[dict[str, Any]] = []
    for job in due_jobs:
        # Pre-errored jobs during resolution (e.g. settings corrupt, unconfigured owner)
        if "status" in job and job["status"] in ("failed", "unconfigured"):
            if job.get("is_retry") and job.get("execution_key"):
                try:
                    record_execution_failure(
                        key=job["execution_key"],
                        now=current_dt,
                        error_code=job.get("error") or "USER_NOT_REGISTERED",
                        state_path=state_path,
                    )
                except Exception:
                    pass
            executed_jobs.append(dict(job))
            continue

        key = job.get("execution_key")
        if not key:
            key = build_execution_key(
                job=job["job"],
                target_date=current_dt.strftime("%Y-%m-%d"),
                time_str=job.get("slot") or job.get("scheduled_time", "00:00"),
                scope=job.get("scope", "user"),
                username=job.get("username"),
                slot=job.get("slot"),
            )
            job["execution_key"] = key

        # Claim execution atomically
        try:
            claim_res = claim_execution(
                key=key,
                job_descriptor=job,
                now=current_dt,
                state_path=state_path,
            )
        except ExecutionStateLockError:
            logger.warning("Execution state lock contention on key '%s'", key)
            skipped_job = dict(job)
            skipped_job["status"] = "skipped"
            skipped_job["reason"] = "EXECUTION_STATE_LOCKED"
            executed_jobs.append(skipped_job)
            continue

        if not claim_res["claimed"]:
            skipped_job = dict(job)
            skipped_job["status"] = "skipped"
            skipped_job["reason"] = claim_res["reason"]
            executed_jobs.append(skipped_job)
            continue

        # Execute claimed job
        try:
            result = await execute_job(
                job,
                now=current_dt,
                daily_close_runner=daily_close_runner,
                reminder_runner=reminder_runner,
                listing_reminder_runner=listing_reminder_runner,
                ipo_refresh_runner=ipo_refresh_runner,
                toss_session_runner=toss_session_runner,
            )
        except Exception as exc:
            logger.exception("Unexpected exception in execute_job for '%s'", key)
            result = {
                "job": job.get("job"),
                "scope": job.get("scope"),
                "scheduled_time": job.get("scheduled_time"),
                "status": "failed",
                "error": str(exc),
            }

        result["execution_key"] = key
        if job.get("is_retry"):
            result["is_retry"] = True
            result["attempt_count"] = job.get("attempt_count", 1)

        # Record outcome to persistent state
        if result.get("status") == "success":
            try:
                record_execution_success(
                    key=key,
                    now=current_dt,
                    details=result.get("details"),
                    state_path=state_path,
                )
            except Exception as exc:
                logger.error("Failed to record execution success for '%s': %s", key, exc)
        else:
            safe_err = sanitize_error_code(result.get("error") or "EXECUTION_FAILED")
            try:
                record_execution_failure(
                    key=key,
                    now=current_dt,
                    error_code=safe_err,
                    state_path=state_path,
                )
            except Exception as exc:
                logger.error("Failed to record execution failure for '%s': %s", key, exc)

        executed_jobs.append(result)

    return {
        "now": current_dt.isoformat(),
        "dry_run": False,
        "jobs": executed_jobs,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for host every-minute contract."""
    parser = argparse.ArgumentParser(description="Wealth Automation Dispatcher")
    parser.add_argument(
        "--now",
        help="ISO format datetime override (e.g. 2026-09-21T09:00:00+09:00)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve due jobs without executing",
    )
    parser.add_argument(
        "--state-file",
        help="Custom execution state JSON file path",
    )
    args = parser.parse_args(argv)

    now = None
    if args.now:
        try:
            now = datetime.fromisoformat(args.now)
        except ValueError:
            sys.stderr.write("Invalid --now datetime format\n")
            return 2
        if now.tzinfo is None:
            sys.stderr.write("Timezone-aware datetime required for --now\n")
            return 2

    state_path = Path(args.state_file) if args.state_file else None

    try:
        result = asyncio.run(
            run_due_automation(
                now=now,
                dry_run=args.dry_run,
                state_path=state_path,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        logger.exception("Fatal dispatcher initialization failure")
        sys.stderr.write(f"Fatal dispatcher error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
