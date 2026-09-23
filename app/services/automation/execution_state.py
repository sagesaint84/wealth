"""Persistent Execution State Tracking for Wealth Automation (A3).

Manages execution state, cross-process and thread locking, claim transactions,
same-minute deduplication, stale execution recovery, bounded retries, and retention pruning.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
DEFAULT_EXECUTION_STATE_PATH = Path("data/automation/execution_state.json")
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_STALE_SECONDS = 900.0  # 15 minutes
RETENTION_DAYS = 30
MAX_EXECUTIONS_RECORDS = 1000

# Thread-level reentrancy / mutual exclusion within process
_PROCESS_LOCK = threading.Lock()


class ExecutionStateError(Exception):
    """Base exception for automation execution state operations."""
    pass


class ExecutionStateLockError(ExecutionStateError):
    """Raised when execution state lock cannot be acquired within timeout."""
    pass


class ExecutionStateCorruptError(ExecutionStateError):
    """Raised when execution state JSON is corrupted or structurally invalid."""
    pass


def get_execution_state_path(path: Path | str | None = None) -> Path:
    """Resolve target execution state file path.

    Precedence:
    1. Explicit path parameter.
    2. WEALTH_DATA_DIR environment variable (root / "automation" / "execution_state.json").
    3. Default relative path: data/automation/execution_state.json.
    """
    if path is not None:
        return Path(path)
    root = os.getenv("WEALTH_DATA_DIR", "").strip()
    if root:
        return Path(root) / "automation" / "execution_state.json"
    return DEFAULT_EXECUTION_STATE_PATH


def build_execution_key(
    job: str,
    target_date: str,
    time_str: str,
    *,
    scope: str = "user",
    username: str | None = None,
    slot: str | None = None,
) -> str:
    """Generate deterministic execution key.

    Global: global:<job>:<YYYY-MM-DD>:<HHMM>
    User:   user:<username>:<job>:<YYYY-MM-DD>:<HHMM>

    Note: Global keys strictly omit automation_owner to prevent duplicate executions
    if the owner configuration changes.
    """
    raw_time = (slot or time_str).replace(":", "")
    if len(raw_time) == 4 and raw_time.isdigit():
        clean_time = raw_time
    else:
        parts = time_str.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            clean_time = f"{int(parts[0]):02d}{int(parts[1]):02d}"
        else:
            clean_time = "0000"

    if scope == "global":
        return f"global:{job}:{target_date}:{clean_time}"

    if not username:
        raise ValueError("username is required for user-scoped execution key")

    return f"user:{username}:{job}:{target_date}:{clean_time}"


def parse_execution_key(key: str) -> dict[str, str]:
    """Parse execution key components."""
    parts = key.split(":")
    if len(parts) == 4 and parts[0] == "global":
        return {
            "scope": "global",
            "job": parts[1],
            "scheduled_date": parts[2],
            "time_hhmm": parts[3],
        }
    if len(parts) == 5 and parts[0] == "user":
        return {
            "scope": "user",
            "username": parts[1],
            "job": parts[2],
            "scheduled_date": parts[3],
            "time_hhmm": parts[4],
        }
    raise ValueError(f"Invalid execution key format: {key}")


def sanitize_error_code(error: Any) -> str:
    """Map exception or error string to a bounded, secret-safe uppercase error code.

    Guarantees no tokens, chat IDs, file paths, or raw stack traces leak into state.
    """
    if not error:
        return "UNKNOWN_ERROR"
    s = str(error).strip()
    s_upper = s.upper()

    if "NO_GLOBAL_AUTOMATION_OWNER" in s_upper:
        return "NO_GLOBAL_AUTOMATION_OWNER"
    if "IPO_REFRESH_ALREADY_RUNNING" in s_upper or "IPOREFRESHALREADYRUNNING" in s_upper:
        return "IPO_REFRESH_CONTENTION"
    if "IPO_NOTIFICATION_ALREADY_RUNNING" in s_upper or "IPONOTIFICATIONALREADYRUNNING" in s_upper:
        return "IPO_NOTIFICATION_CONTENTION"
    if "EXECUTION_STATE_LOCKED" in s_upper:
        return "EXECUTION_STATE_LOCKED"
    if "CORRUPT" in s_upper:
        return "SETTINGS_CORRUPT"
    if "DAILY_CLOSE_FAILED" in s_upper or "daily close failed" in s.lower():
        return "DAILY_CLOSE_FAILED"
    if "TIMEOUT" in s_upper:
        return "TIMEOUT"
    if "NOT_REGISTERED" in s_upper or "NOT REGISTERED" in s_upper or "INVALID_GLOBAL_AUTOMATION_OWNER" in s_upper:
        return "USER_NOT_REGISTERED"
    if "PERMISSION" in s_upper:
        return "PERMISSION_DENIED"
    if "CONNECTION" in s_upper or "NETWORK" in s_upper or "TELEGRAM" in s_upper:
        return "NETWORK_ERROR"

    return "EXECUTION_FAILED"


@contextmanager
def execution_state_lock(state_path: Path | None = None, timeout: float = 5.0):
    """Process threading.Lock + cross-process advisory file lock with bounded timeout.

    Compatible with Windows (msvcrt) and Unix (fcntl).
    """
    target_path = get_execution_state_path(state_path)
    acquired = _PROCESS_LOCK.acquire(blocking=True, timeout=timeout)
    if not acquired:
        raise ExecutionStateLockError("EXECUTION_STATE_LOCKED")

    handle = None
    start_time = time.monotonic()
    try:
        lock_path = target_path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+b")
        locked = False

        while (time.monotonic() - start_time) < timeout:
            try:
                if os.name == "nt":
                    import msvcrt
                    if lock_path.stat().st_size == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                time.sleep(0.02)

        if not locked:
            raise ExecutionStateLockError("EXECUTION_STATE_LOCKED")

        yield
    finally:
        if handle is not None:
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                handle.close()
            except OSError:
                pass
        _PROCESS_LOCK.release()


def load_execution_state(path: Path | None = None) -> dict[str, Any]:
    """Load execution state from disk (pure read-only).

    If the file does not exist, returns an empty default state structure without
    creating any file on disk.
    If the file exists but contains corrupted JSON or invalid structure,
    raises ExecutionStateCorruptError (fail-closed).
    """
    target_path = get_execution_state_path(path)
    if not target_path.exists():
        return {
            "version": 1,
            "updated_at": None,
            "executions": {},
        }

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise ExecutionStateCorruptError(
            f"Corrupted execution state JSON at {target_path}: {exc}"
        ) from exc

    if (
        not isinstance(data, dict)
        or data.get("version") != 1
        or "executions" not in data
        or not isinstance(data["executions"], dict)
    ):
        raise ExecutionStateCorruptError(
            f"Invalid execution state schema at {target_path}"
        )

    return data


def save_execution_state(
    state: dict[str, Any],
    path: Path | None = None,
) -> None:
    """Atomically save execution state with fsync and Windows retry loop."""
    target_path = get_execution_state_path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        try:
            os.chmod(target_path.parent, 0o700)
        except OSError:
            pass

    state["version"] = 1
    state["updated_at"] = datetime.now(KST).isoformat()

    pid = os.getpid()
    tid = threading.get_ident()
    now_ns = time.time_ns()
    tmp_path = target_path.with_suffix(f".tmp.{pid}.{tid}.{now_ns}")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        for attempt in range(50):
            try:
                os.replace(tmp_path, target_path)
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)

        if os.name == "posix":
            try:
                os.chmod(target_path, 0o600)
            except OSError:
                pass
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def claim_execution(
    key: str,
    job_descriptor: dict[str, Any],
    *,
    now: datetime | None = None,
    state_path: Path | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    stale_seconds: float = DEFAULT_STALE_SECONDS,
) -> dict[str, Any]:
    """Perform atomic claim transaction for a scheduled execution key.

    Returns:
        {
            "claimed": bool,
            "reason": str ("FIRST_CLAIM" | "RETRY" | "STALE_RETRY" | "ALREADY_SUCCESS" | "ALREADY_RUNNING" | "MAX_ATTEMPTS_EXCEEDED"),
            "record": dict[str, Any],
        }
    """
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    now_iso = now_kst.isoformat()

    with execution_state_lock(state_path):
        state = load_execution_state(state_path)
        executions = state.setdefault("executions", {})

        record = executions.get(key)
        if record is not None:
            status = record.get("status")
            attempt_count = record.get("attempt_count", 1)

            if status == "SUCCESS":
                return {
                    "claimed": False,
                    "reason": "ALREADY_SUCCESS",
                    "record": record,
                }

            if status == "RUNNING":
                if record.get("retryable") is False:
                    return {
                        "claimed": False,
                        "reason": "NON_RETRYABLE_RUNNING",
                        "record": record,
                    }
                last_attempt_str = record.get("last_attempt_at") or record.get("first_claimed_at")
                is_stale = False
                if last_attempt_str:
                    try:
                        last_attempt_dt = datetime.fromisoformat(last_attempt_str)
                        if last_attempt_dt.tzinfo is None:
                            last_attempt_dt = last_attempt_dt.replace(tzinfo=KST)
                        elapsed = (now_kst - last_attempt_dt).total_seconds()
                        if elapsed >= stale_seconds:
                            is_stale = True
                    except (ValueError, TypeError):
                        is_stale = True

                if not is_stale:
                    return {
                        "claimed": False,
                        "reason": "ALREADY_RUNNING",
                        "record": record,
                    }

                # Stale RUNNING: check attempts
                if attempt_count >= max_attempts:
                    record["status"] = "FAILED"
                    record["completed_at"] = now_iso
                    record["last_error_code"] = "STALE_TIMEOUT_MAX_ATTEMPTS_EXCEEDED"
                    save_execution_state(state, state_path)
                    return {
                        "claimed": False,
                        "reason": "MAX_ATTEMPTS_EXCEEDED",
                        "record": record,
                    }

                # Stale recovery allowed
                prev_attempt = record.get("last_attempt_at")
                record["previous_attempt_at"] = prev_attempt
                record["stale_recovered_at"] = now_iso
                record["attempt_count"] = attempt_count + 1
                record["status"] = "RUNNING"
                record["last_attempt_at"] = now_iso
                record["last_error_code"] = "STALE_RECOVERY"
                save_execution_state(state, state_path)
                return {
                    "claimed": True,
                    "reason": "STALE_RETRY",
                    "record": record,
                }

            if status == "FAILED":
                if record.get("retryable") is False:
                    return {
                        "claimed": False,
                        "reason": "NON_RETRYABLE_FAILED",
                        "record": record,
                    }
                if attempt_count >= max_attempts:
                    return {
                        "claimed": False,
                        "reason": "MAX_ATTEMPTS_EXCEEDED",
                        "record": record,
                    }

                # Bounded retry allowed
                record["attempt_count"] = attempt_count + 1
                record["status"] = "RUNNING"
                record["last_attempt_at"] = now_iso
                record["completed_at"] = None
                save_execution_state(state, state_path)
                return {
                    "claimed": True,
                    "reason": "RETRY",
                    "record": record,
                }

        # First claim
        new_record = {
            "key": key,
            "scope": job_descriptor.get("scope", "user"),
            "job": job_descriptor.get("job"),
            "username": job_descriptor.get("username"),
            "owner": job_descriptor.get("owner"),
            "slot": job_descriptor.get("slot"),
            "is_last_slot": job_descriptor.get("is_last_slot"),
            "scheduled_date": job_descriptor.get("scheduled_date") or now_kst.strftime("%Y-%m-%d"),
            "scheduled_time": job_descriptor.get("scheduled_time"),
            "status": "RUNNING",
            "attempt_count": 1,
            "first_claimed_at": now_iso,
            "last_attempt_at": now_iso,
            "completed_at": None,
            "last_error_code": None,
            "details": None,
            "retryable": job_descriptor.get("retryable", True) is not False,
        }
        executions[key] = new_record
        prune_execution_state(state, now_kst)
        save_execution_state(state, state_path)
        return {
            "claimed": True,
            "reason": "FIRST_CLAIM",
            "record": new_record,
        }


def record_execution_success(
    key: str,
    *,
    now: datetime | None = None,
    details: dict[str, Any] | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Record successful completion of an execution."""
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    now_iso = now_kst.isoformat()

    with execution_state_lock(state_path):
        state = load_execution_state(state_path)
        executions = state.setdefault("executions", {})

        record = executions.get(key)
        if record is None:
            logger.warning("Recording success for untracked execution key '%s'", key)
            record = {"key": key}
            executions[key] = record

        record["status"] = "SUCCESS"
        record["completed_at"] = now_iso
        record["last_error_code"] = None
        if details is not None:
            record["details"] = details

        prune_execution_state(state, now_kst)
        save_execution_state(state, state_path)
        return record


def record_execution_failure(
    key: str,
    *,
    now: datetime | None = None,
    error_code: str = "EXECUTION_FAILED",
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Record failed attempt or completion of an execution."""
    now_kst = (now or datetime.now(KST)).astimezone(KST)
    now_iso = now_kst.isoformat()
    safe_code = sanitize_error_code(error_code)

    with execution_state_lock(state_path):
        state = load_execution_state(state_path)
        executions = state.setdefault("executions", {})

        record = executions.get(key)
        if record is None:
            logger.warning("Recording failure for untracked execution key '%s'", key)
            record = {"key": key}
            executions[key] = record

        record["status"] = "FAILED"
        record["completed_at"] = now_iso
        record["last_error_code"] = safe_code

        save_execution_state(state, state_path)
        return record


def get_retryable_executions(
    now: datetime,
    state: dict[str, Any] | None = None,
    *,
    path: Path | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    stale_seconds: float = DEFAULT_STALE_SECONDS,
) -> list[dict[str, Any]]:
    """Return records eligible for retry at current datetime.

    Rules:
    - scheduled_date == today in Asia/Seoul.
    - Either:
      - status == "FAILED" and attempt_count < max_attempts
      - status == "RUNNING" and (now - last_attempt_at) >= stale_seconds and attempt_count < max_attempts
    """
    if state is None:
        state = load_execution_state(path)

    now_kst = now.astimezone(KST)
    today_str = now_kst.strftime("%Y-%m-%d")

    retryables: list[dict[str, Any]] = []
    executions = state.get("executions", {})

    for key, rec in executions.items():
        if rec.get("scheduled_date") != today_str:
            continue
        if rec.get("retryable") is False:
            continue

        status = rec.get("status")
        attempt_count = rec.get("attempt_count", 1)

        if status == "FAILED" and attempt_count < max_attempts:
            retryables.append(dict(rec))
        elif status == "RUNNING":
            last_attempt = rec.get("last_attempt_at") or rec.get("first_claimed_at")
            if last_attempt:
                try:
                    dt = datetime.fromisoformat(last_attempt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=KST)
                    if (now_kst - dt).total_seconds() >= stale_seconds and attempt_count < max_attempts:
                        retryables.append(dict(rec))
                except (ValueError, TypeError):
                    pass

    return retryables


def prune_execution_state(
    state: dict[str, Any],
    now: datetime,
    *,
    retention_days: int = RETENTION_DAYS,
    max_records: int = MAX_EXECUTIONS_RECORDS,
) -> int:
    """Prune execution state records according to retention policy.

    Rules:
    - Never prune records with status == "RUNNING".
    - Never prune records with status == "FAILED" from today that are still under max_attempts.
    - Prune terminal records older than retention_days.
    - If total count still exceeds max_records, prune oldest eligible records down to max_records.
    """
    executions = state.get("executions", {})
    if not executions:
        return 0

    now_kst = now.astimezone(KST)
    today_str = now_kst.strftime("%Y-%m-%d")
    cutoff = now_kst - timedelta(days=retention_days)

    to_prune: set[str] = set()

    for key, rec in executions.items():
        status = rec.get("status")
        if status == "RUNNING":
            continue
        if status == "FAILED" and rec.get("scheduled_date") == today_str and rec.get("attempt_count", 0) < DEFAULT_MAX_ATTEMPTS:
            continue

        last_attempt = rec.get("last_attempt_at") or rec.get("first_claimed_at")
        if last_attempt:
            try:
                dt = datetime.fromisoformat(last_attempt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=KST)
                if dt < cutoff:
                    to_prune.add(key)
            except (ValueError, TypeError):
                to_prune.add(key)

    for key in to_prune:
        del executions[key]

    pruned_count = len(to_prune)

    # Enforce max records limit on eligible records
    if len(executions) > max_records:
        eligible: list[tuple[datetime, str]] = []
        for key, rec in executions.items():
            status = rec.get("status")
            if status == "RUNNING":
                continue
            if status == "FAILED" and rec.get("scheduled_date") == today_str and rec.get("attempt_count", 0) < DEFAULT_MAX_ATTEMPTS:
                continue

            last_attempt = rec.get("last_attempt_at") or rec.get("first_claimed_at")
            try:
                dt = datetime.fromisoformat(last_attempt) if last_attempt else datetime.min.replace(tzinfo=KST)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=KST)
            except Exception:
                dt = datetime.min.replace(tzinfo=KST)
            eligible.append((dt, key))

        eligible.sort(key=lambda x: x[0])
        excess = len(executions) - max_records
        for _, key in eligible[:excess]:
            del executions[key]
            pruned_count += 1

    return pruned_count
