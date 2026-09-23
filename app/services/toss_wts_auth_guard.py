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
from contextlib import contextmanager
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
    return Path(root) if root else Path(__file__).resolve().parents[3] / "data"


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
    username: str, attempt_id: str, pid: int, started_at: str
) -> None:
    """Write the durable active-auth-op.json marker (must be called under lock)."""
    path = _active_op_path(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "attempt_id": attempt_id,
        "pid": pid,
        "pid_start_time": get_pid_start_time(pid),
        "started_at": started_at,
        "type": "login",
        "owner": username,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def clear_active_op_marker(username: str, attempt_id: str) -> None:
    """Remove the marker iff it belongs to ``attempt_id`` for ``username`` (idempotent)."""
    path = _active_op_path(username)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("attempt_id") == attempt_id:
            path.unlink(missing_ok=True)
    except (OSError, json.JSONDecodeError):
        path.unlink(missing_ok=True)


def _get_active_op_data(username: str) -> dict[str, Any] | None:
    """Read the marker.  Returns None if absent or stale (process dead + old)."""
    path = _active_op_path(username)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

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
                    pass
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
        return stat_text.split()[21]
    except (OSError, IndexError):
        return None


def pid_alive(pid: int, expected_start_time: str | None = None) -> bool:
    """Return True if ``pid`` exists AND is the original process instance.

    On Linux, compares ``/proc/<pid>/stat`` starttime to detect PID reuse.
    On Windows (test env) falls back to plain ``os.kill(pid, 0)`` check.
    """
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    if expected_start_time is not None:
        actual = get_pid_start_time(pid)
        if actual is not None and actual != expected_start_time:
            return False  # Different process has reused this PID
    return True
