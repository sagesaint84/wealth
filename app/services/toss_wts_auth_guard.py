"""Shared cross-process auth-operation guard for Toss WTS.

Intentionally minimal so that both ``toss_wts_login.py`` and
``toss_wts_session.py`` can import from here without circular dependencies.

Per-User Namespace
------------------
Every Wealth user gets their own lock and marker so that User A's auth
operation never blocks User B's.  All public functions accept a ``username``
parameter which is validated and mapped to a filesystem-safe identifier.

Exports
-------
TossAuthOperationBusyError
    Raised when ``auth_operation_lock`` cannot be acquired within
    ``acquire_timeout_seconds``.

auth_operation_lock(username, acquire_timeout_seconds)
    Per-user cross-process advisory lock context-manager.
    - Linux/macOS: ``fcntl.flock`` (LOCK_EX | LOCK_NB) with polling.
    - Windows (test env): file-existence sentinel.
    - Per-user ``threading.Lock`` guards intra-process races.
    CALLER decides how long to HOLD the context; the parameter only
    controls the initial acquisition window.

check_active_login_operation(username) -> bool
    True if the durable ``active-auth-op.json`` marker file for ``username``
    exists and belongs to a non-stale attempt.  Suitable for checking inside
    the advisory lock (extend path) or outside it (quick read-only guard).

write_active_op_marker(username, attempt_id, pid, started_at)
clear_active_op_marker(username, attempt_id)
    Atomic marker file write / conditional delete (per-user).

user_login_dir(username) -> Path
    Per-user directory for login attempt metadata and QR files.

_user_toss_root(username) -> Path
    Per-user Toss WTS data root (also used by login and session modules).

_validate_username(username) -> str
    Validate and return the username for safe filesystem use.
    Raises ValueError for invalid usernames (path-traversal protection).

get_pid_start_time(pid) -> str | None
    Linux ``/proc/<pid>/stat`` field 21 (starttime).  Returns None on
    Windows or if ``/proc`` is unavailable.

pid_alive(pid, expected_start_time) -> bool
    True if the process exists AND is the same instance (start-time match).
"""
from __future__ import annotations

import json
import os
import platform
import re
import threading
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator

KST = timezone(timedelta(hours=9))
_IS_WINDOWS = platform.system() == "Windows"

# How long a pending attempt may live before its marker is treated as stale.
_MARKER_STALE_SECONDS = 360  # LOGIN_ATTEMPT_MAX_SECONDS(300) + 60 grace

# Per-user threading locks (dict keyed by username).
# _user_locks_meta guards the dict itself; user locks guard per-user ops.
_user_thread_locks: dict[str, threading.Lock] = {}
_user_locks_meta = threading.Lock()

# Regex for valid username characters (filesystem-safe)
_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class TossAuthOperationBusyError(Exception):
    """Raised when the shared advisory lock cannot be acquired."""


# ---------------------------------------------------------------------------
# Username validation & path helpers
# ---------------------------------------------------------------------------

def _validate_username(username: str) -> str:
    """Validate username and return it for filesystem use.

    Only allows ``[a-zA-Z0-9_-]`` (1–64 chars) to prevent path traversal.
    Raises ``ValueError`` for invalid input.
    """
    if not username or not isinstance(username, str):
        raise ValueError("username must be a non-empty string")
    if not _USERNAME_RE.match(username):
        raise ValueError(
            f"Invalid username {username!r}: only [a-zA-Z0-9_-] (1-64 chars) allowed"
        )
    return username


def _data_root() -> Path:
    root = os.getenv("WEALTH_DATA_DIR", "").strip()
    return Path(root) if root else Path(__file__).resolve().parents[2] / "data"


def _user_toss_root(username: str) -> Path:
    """Per-user Toss WTS data root.

    Structure: ``<WEALTH_DATA_DIR>/toss-wts/users/<safe_uid>/``
    """
    safe = _validate_username(username)
    return _data_root() / "toss-wts" / "users" / safe


def _lock_path(username: str) -> Path:
    return _user_toss_root(username) / "auth-operation.lock"


def _active_op_path(username: str) -> Path:
    return _user_toss_root(username) / "active-auth-op.json"


def user_login_dir(username: str) -> Path:
    """Per-user directory for login attempt metadata and QR files."""
    return _user_toss_root(username) / "toss-login"


# ---------------------------------------------------------------------------
# Per-user thread lock management
# ---------------------------------------------------------------------------

def _get_thread_lock(username: str) -> threading.Lock:
    """Get or create the per-user threading.Lock (created on first use)."""
    with _user_locks_meta:
        if username not in _user_thread_locks:
            _user_thread_locks[username] = threading.Lock()
        return _user_thread_locks[username]


# ---------------------------------------------------------------------------
# Cross-process advisory lock (per-user)
# ---------------------------------------------------------------------------

@contextmanager
def auth_operation_lock(
    username: str,
    acquire_timeout_seconds: float = 5.0,
) -> Generator[None, None, None]:
    """Acquire the per-user Toss auth-operation advisory lock.

    Acquires both the per-user ``threading.Lock`` (intra-process) and an
    OS-level file lock (inter-process).  The caller holds the context for as
    long as needed — acquisition timeout only limits the *initial* wait.

    Users are isolated: User A's lock never contends with User B's.

    Raises ``TossAuthOperationBusyError`` if the lock cannot be acquired
    within ``acquire_timeout_seconds``.
    """
    thread_lock = _get_thread_lock(username)
    if not thread_lock.acquire(timeout=acquire_timeout_seconds):
        raise TossAuthOperationBusyError(
            f"TOSS_AUTH_OPERATION_BUSY: thread-level contention for user {username!r}"
        )
    try:
        lock_file = _lock_path(username)
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        gen = (
            _windows_lock(lock_file, acquire_timeout_seconds)
            if _IS_WINDOWS
            else _posix_lock(lock_file, acquire_timeout_seconds)
        )
        yield from gen
    finally:
        thread_lock.release()


def _posix_lock(
    lock_file: Path, acquire_timeout_seconds: float
) -> Generator[None, None, None]:
    import fcntl

    deadline = time.monotonic() + acquire_timeout_seconds
    fh = open(lock_file, "w")
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fh.close()
                    raise TossAuthOperationBusyError(
                        "TOSS_AUTH_OPERATION_BUSY: file lock held by another process"
                    )
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        try:
            fh.close()
        except OSError:
            pass


def _windows_lock(
    lock_file: Path, acquire_timeout_seconds: float
) -> Generator[None, None, None]:
    """File-existence sentinel lock — Windows / test environment only.

    Production containers run Linux where ``_posix_lock`` is used.
    """
    sentinel = lock_file.with_suffix(".lock.held")
    deadline = time.monotonic() + acquire_timeout_seconds
    while sentinel.exists():
        if time.monotonic() >= deadline:
            raise TossAuthOperationBusyError(
                "TOSS_AUTH_OPERATION_BUSY: sentinel lock held"
            )
        time.sleep(0.02)
    try:
        sentinel.write_text("held")
        yield
    finally:
        sentinel.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Active-login marker helpers (per-user)
# ---------------------------------------------------------------------------

def write_active_op_marker(
    username: str, attempt_id: str, pid: int, started_at: str,
    *, process_boundary: dict | None = None, process_start: str | None = None,
) -> None:
    """Write the durable active-auth-op.json marker (must be called under lock)."""
    path = _active_op_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "attempt_id": attempt_id,
        "pid": pid,
        "pid_start_time": process_start if process_boundary is not None else get_pid_start_time(pid),
        "started_at": started_at,
        "type": "login",
        "owner": username,
    }
    if process_boundary is not None:
        data["process_boundary"] = process_boundary
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        if not _IS_WINDOWS:
            os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(data, ensure_ascii=False))
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def _release_unspawned_reservation_locked(
    username: str, attempt_id: str, *, token: str, boot_id: str,
) -> bool:
    """Only for definite Popen failure, inside the caller's existing auth lock.

    Never acquires the non-reentrant lock. This is not a general marker-clear
    path and must never be called after a process object has been returned.
    """
    from app.services.toss_wts_auth_process import BOUNDARY_KIND
    if (not isinstance(token, str) or not token or not isinstance(boot_id, str) or not boot_id
            or not isinstance(attempt_id, str) or not attempt_id
            or not _get_thread_lock(username).locked()):
        return False
    path = _active_op_path(username)
    try:
        if path.is_symlink():
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        boundary = data.get("process_boundary")
        if (data.get("owner") != username or data.get("attempt_id") != attempt_id
                or data.get("type") != "login" or type(data.get("pid")) is not int
                or data["pid"] != 0 or "pid_start_time" not in data
                or data["pid_start_time"] is not None
                or boundary != {"kind": BOUNDARY_KIND, "token": token, "boot_id": boot_id}):
            return False
        path.unlink()
        return True
    except (OSError, ValueError, TypeError):
        return False  # Corrupt/unreadable/changed reservations remain fail-closed.


def clear_active_op_marker(username: str, attempt_id: str) -> bool:
    """Remove the marker iff it belongs to ``attempt_id`` for ``username`` (idempotent)."""
    path = _active_op_path(username)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        managed = data.get("process_boundary") is not None
        if not managed and not _IS_WINDOWS:
            return False
        # Re-read under the start/extend lock; never remove a newer attempt.
        with (auth_operation_lock(username) if managed else nullcontext()):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("attempt_id") != attempt_id or data.get("owner", username) != username:
                return False
            boundary = data.get("process_boundary")
            if boundary is not None:
                from app.services.toss_wts_auth_process import boundary_complete
                if not boundary_complete(user_login_dir(username), attempt_id, username,
                                         boundary, data.get("pid"), data.get("pid_start_time")):
                    return False
            path.unlink(missing_ok=True)
            return True
    except FileNotFoundError:
        return True
    except (OSError, json.JSONDecodeError, AttributeError, TypeError, TossAuthOperationBusyError):
        # An unreadable/corrupt marker is not evidence of safe completion.
        return False


def _get_active_op_data(username: str) -> dict[str, Any] | None:
    """Read the marker.  Returns None if absent or stale (process dead + old)."""
    path = _active_op_path(username)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        return {"type": "uncertain", "owner": username}

    if not isinstance(data, dict) or data.get("owner", username) != username:
        return {"type": "uncertain", "owner": username}
    if data.get("process_boundary") is not None:
        # Managed receipts are consumed by login finalization, never by age.
        return data
    if not _IS_WINDOWS:
        # Legacy Linux PID-only markers cannot prove orphaned children exited.
        return data

    pid = data.get("pid")
    started_raw = data.get("started_at")
    if pid is not None and started_raw:
        try:
            started = datetime.fromisoformat(started_raw)
            age = (datetime.now(KST) - started).total_seconds()
            if not pid_alive(pid, data.get("pid_start_time")) and age > _MARKER_STALE_SECONDS:
                # Stale orphan — remove silently
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    return data
                return None
        except (ValueError, TypeError):
            pass
    return data


def check_active_login_operation(username: str) -> bool:
    """Return True if a non-stale login attempt is currently active for ``username``.

    Safe to call inside or outside the advisory lock.
    User A's marker never affects User B's result.
    """
    return _get_active_op_data(username) is not None


# ---------------------------------------------------------------------------
# Process liveness / ownership helpers
# ---------------------------------------------------------------------------

def get_pid_start_time(pid: int) -> str | None:
    """Linux ``/proc/<pid>/stat`` field 21 (starttime in clock ticks).

    Used to detect PID reuse.  Returns None on Windows or if /proc is absent.
    """
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text()
        return stat_text.rpartition(")")[2].split()[19]
    except (OSError, IndexError):
        return None


def pid_alive(pid: int, expected_start_time: str | None = None) -> bool:
    """Return True if ``pid`` exists AND is the original process instance.

    On Linux, compares ``/proc/<pid>/stat`` starttime to detect PID reuse.
    On Windows (test env) falls back to plain ``os.kill(pid, 0)`` check.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # EPERM/unknown must not permit a competing auth operation.
    if expected_start_time is not None:
        actual = get_pid_start_time(pid)
        if actual is not None and actual != expected_start_time:
            return False  # Different process has reused this PID
    return True
