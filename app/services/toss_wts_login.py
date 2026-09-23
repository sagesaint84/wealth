"""Toss WTS per-user login lifecycle.

Verified tossctl v0.50.3 auth login contract
--------------------------------------------
    tossctl auth login [flags]
    Flags:
        --headless
        --link
        --qr-output string   Path to write the current QR PNG

Canonical Wealth login argv (shell=False):
    <executable>
    --config-dir <user_config_dir>
    auth login
    --headless
    --link
    --qr-output <private QR PNG path>

Per-User Isolation
------------------
Every public function requires a ``username`` parameter (the authenticated
Wealth user).  Attempt metadata and QR files are stored under the user's
private directory so that User A can never read, cancel, or interfere with
User B's attempts.  The advisory lock and active-op marker are also per-user.

Safety invariants
-----------------
1. _AUTH_LOGIN_FLAG_VERIFIED=True  (confirmed from v0.50.3 --help)
2. Cross-process advisory lock (toss_wts_auth_guard.auth_operation_lock):
   - LOGIN START: acquired briefly (per-user).
     - Reject if active-op marker for THIS USER already exists.
     - TOCTOU-safe reauthenticate=False check INSIDE lock.
     - Spawn Popen, write durable marker, then release.
   - AUTH EXTEND: acquired and held for entire subprocess lifetime (per-user).
   - Different users never contend on the same lock.
3. Process reaping: watcher daemon thread calls proc.wait() so child is never
   a zombie.  _check_and_finalize() uses watcher registry (primary); falls
   back to pid_alive() only for server-restart recovery.
4. Terminate-then-cleanup: both cancel and timeout path call
   _terminate_and_reap() and wait for confirmed exit BEFORE clearing the
   active-op marker. If termination cannot be confirmed, the marker remains
   and a safe error is returned so other login/extend cannot start.
5. Spawn failure rollback: if marker or meta write fails after Popen, the
   spawned process is terminated+reaped, marker+artifacts are purged.
6. Post-login verification: subprocess exit alone is NOT success.
   get_toss_session_status() active && valid must be confirmed.
7. Re-auth protection: session active+valid → TossSessionAlreadyValidError
   unless reauthenticate=True.
8. QR cleanup on every terminal path (success/failed/timeout/cancelled).
9. Watcher registry entry removed on every terminal path to prevent memory
   accumulation in long-running server processes.
10. Access control: get_login_attempt / get_login_qr / cancel_login_attempt
    all require requesting_username to match the attempt owner, enforced both
    by path namespacing (implicit) and owner field check (defense-in-depth).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
import uuid

KST = timezone(timedelta(hours=9))

# ---------------------------------------------------------------------------
# Verified tossctl v0.50.3 CLI contract
# ---------------------------------------------------------------------------
_AUTH_LOGIN_FLAG_VERIFIED: bool = True
_AUTH_LOGIN_QR_FLAG: str = "--qr-output"   # confirmed from v0.50.3 --help

STATUS_PENDING = "pending"
STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_TIMEOUT = "timeout"

LOGIN_ATTEMPT_MAX_SECONDS = 300
_IS_WINDOWS = platform.system() == "Windows"

# Termination wait limits (SIGTERM grace + SIGKILL hard)
_SIGTERM_WAIT_SECONDS = 10.0
_SIGKILL_WAIT_SECONDS = 5.0

# ---------------------------------------------------------------------------
# Process watcher registry (prevents zombie processes)
# ---------------------------------------------------------------------------
# Maps attempt_id -> {"reaped": bool, "exit_code": int | None}
# attempt_ids are UUIDs (globally unique) so no username prefix needed.
_watcher_registry: dict[str, dict[str, Any]] = {}
_watcher_lock = threading.Lock()


def _start_watcher(attempt_id: str, proc: subprocess.Popen) -> None:
    """Start a daemon thread that reaps the child and records its exit code.

    Prevents zombie processes: once proc.wait() returns the OS reclaims the
    process table entry so os.kill(pid, 0) correctly raises ProcessLookupError.
    """
    with _watcher_lock:
        _watcher_registry[attempt_id] = {"reaped": False, "exit_code": None}

    def _watch() -> None:
        try:
            exit_code = proc.wait()
        except Exception:
            exit_code = -1
        with _watcher_lock:
            # Tombstone-safe: only update if entry still exists.
            # _terminal_cleanup may have already popped it; do NOT re-create it,
            # as that would permanently leak memory and confuse future state checks.
            if attempt_id in _watcher_registry:
                _watcher_registry[attempt_id] = {"reaped": True, "exit_code": exit_code}

    t = threading.Thread(
        target=_watch,
        daemon=True,
        name=f"toss-login-watcher-{attempt_id[:8]}",
    )
    t.start()


def _is_process_reaped(attempt_id: str) -> bool | None:
    """Return True=reaped, False=still running, None=unknown (server restart)."""
    with _watcher_lock:
        info = _watcher_registry.get(attempt_id)
    if info is None:
        return None  # Server restarted; init will adopt and reap orphan zombies
    return info["reaped"]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TossLoginError(Exception):
    """Base error for Toss login operations."""


class TossLoginLockError(TossLoginError):
    """Another operation holds the lock, or active-op marker already exists."""


class TossLoginNotFoundError(TossLoginError):
    """attempt_id not found on disk (or does not belong to requesting user)."""


class TossLoginFlagUnverifiedError(TossLoginError):
    """_AUTH_LOGIN_FLAG_VERIFIED is False."""


class TossSessionAlreadyValidError(TossLoginError):
    """Session is already active+valid; must pass reauthenticate=True."""


class TossLoginAccessDeniedError(TossLoginError):
    """Requesting user does not own this attempt."""


# ---------------------------------------------------------------------------
# Path helpers (per-user)
# ---------------------------------------------------------------------------

def _meta_path(attempt_id: str, username: str) -> Path:
    """Per-user attempt metadata file."""
    from app.services.toss_wts_auth_guard import user_login_dir
    return user_login_dir(username) / f"{attempt_id}.json"


def _qr_path(attempt_id: str, username: str) -> Path:
    """Per-user QR PNG file."""
    from app.services.toss_wts_auth_guard import user_login_dir
    return user_login_dir(username) / f"{attempt_id}.qr.png"


def _user_config_dir(username: str) -> Path:
    """Per-user tossctl config directory."""
    from app.services.toss_wts_auth_guard import _user_toss_root
    return _user_toss_root(username) / "config"


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def _write_meta(attempt_id: str, username: str, meta: dict[str, Any]) -> None:
    path = _meta_path(attempt_id, username)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _IS_WINDOWS:
        try:
            os.chmod(str(path.parent), 0o700)
        except OSError:
            pass
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if not _IS_WINDOWS:
            try:
                os.chmod(str(tmp), 0o600)
            except OSError:
                pass
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _read_meta(attempt_id: str, username: str) -> dict[str, Any]:
    """Read attempt metadata for the given user.

    Raises ``TossLoginNotFoundError`` if not found (including wrong username).
    The path-namespacing means User B cannot read User A's attempts.
    """
    path = _meta_path(attempt_id, username)
    if not path.exists():
        raise TossLoginNotFoundError(attempt_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TossLoginNotFoundError(attempt_id) from exc


def _safe_public(meta: dict[str, Any]) -> dict[str, Any]:
    """Return only fields safe for API exposure — no paths, PID, or output."""
    return {
        "attempt_id": meta.get("attempt_id"),
        "owner": meta.get("owner"),
        "status": meta.get("status"),
        "started_at": meta.get("started_at"),
        "finished_at": meta.get("finished_at"),
        "error_code": meta.get("error_code"),
    }


def _kst_now(provider: Callable[[], datetime] | None = None) -> datetime:
    dt = provider() if provider is not None else datetime.now(KST)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return dt.astimezone(KST)


# ---------------------------------------------------------------------------
# Cleanup helpers
# ---------------------------------------------------------------------------

def _cleanup_qr(attempt_id: str, username: str) -> None:
    try:
        _qr_path(attempt_id, username).unlink(missing_ok=True)
    except OSError:
        pass


def _terminal_cleanup(attempt_id: str, username: str, meta: dict[str, Any]) -> None:
    """Called on every terminal path: clear marker, delete QR, write meta,
    and remove watcher registry entry (prevents memory accumulation).
    """
    from app.services.toss_wts_auth_guard import clear_active_op_marker
    clear_active_op_marker(username, attempt_id)
    _cleanup_qr(attempt_id, username)
    try:
        _write_meta(attempt_id, username, meta)
    except Exception:
        pass
    # Release watcher registry entry (tombstone prevents resurrection)
    with _watcher_lock:
        _watcher_registry.pop(attempt_id, None)


def _rollback_spawn(
    attempt_id: str, username: str, proc: subprocess.Popen
) -> None:
    """Terminate and reap an orphaned subprocess after setup failure.

    Called when Popen succeeded but marker/meta write failed.
    Uses proc object directly for ownership certainty (no PID lookup).
    """
    try:
        proc.terminate()
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except (OSError, ProcessLookupError):
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
    except Exception:
        pass
    # Remove any partial marker and QR artifacts
    from app.services.toss_wts_auth_guard import clear_active_op_marker
    try:
        clear_active_op_marker(username, attempt_id)
    except Exception:
        pass
    try:
        _cleanup_qr(attempt_id, username)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Process termination with bounded wait
# ---------------------------------------------------------------------------

def _terminate_and_reap(
    attempt_id: str,
    pid: int,
    expected_start_time: str | None,
) -> bool:
    """Terminate the owned process and wait for confirmed exit before returning.

    Steps:
      1. Ownership-verify PID (start-time check on Linux).
      2. SIGTERM (or taskkill on Windows).
      3. Poll watcher/pid_alive up to _SIGTERM_WAIT_SECONDS.
      4. SIGKILL escalation if still alive (Linux/macOS only).
      5. Poll up to _SIGKILL_WAIT_SECONDS.
      6. Return True if confirmed dead, False if uncertain.

    The caller MUST check the return value: if False, the active-op marker
    must be kept so that other login/extend operations remain blocked.
    """
    from app.services.toss_wts_auth_guard import pid_alive as _pa

    def _process_gone() -> bool:
        reaped = _is_process_reaped(attempt_id)
        if reaped is True:
            return True
        if not _pa(pid, expected_start_time):
            return True
        return False

    # Already dead?
    if _process_gone():
        return True

    # SIGTERM (or Windows forced kill)
    if _IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return True  # Already dead

    # Grace period
    deadline = time.monotonic() + _SIGTERM_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _process_gone():
            return True
        time.sleep(0.1)

    if _IS_WINDOWS:
        return _process_gone()

    # SIGKILL escalation (POSIX only)
    try:
        os.kill(pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        return True

    deadline = time.monotonic() + _SIGKILL_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _process_gone():
            return True
        time.sleep(0.1)

    return False  # Could not confirm exit within bounds


# ---------------------------------------------------------------------------
# Post-login verification (lazy import avoids circular dependency)
# ---------------------------------------------------------------------------

def _verify_post_login(settings: dict[str, Any], username: str) -> bool:
    """Return True iff get_toss_session_status() reports active && valid."""
    try:
        from app.services.toss_wts_session import get_toss_session_status
        status = get_toss_session_status(username=username, settings=settings)
        return bool(status.get("active")) and bool(status.get("valid"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Process finalization
# ---------------------------------------------------------------------------

def _check_and_finalize(
    meta: dict[str, Any],
    settings: dict[str, Any],
    now_provider: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """If the background process has exited (per watcher), run post-login verification.

    Primary check: watcher registry (prevents zombie misdetection).
    Fallback (server restart): pid_alive() — safe because init reaps orphans.
    ``username`` is taken from ``meta["owner"]``.
    """
    if meta.get("status") != STATUS_PENDING:
        return meta

    pid = meta.get("_pid")
    if pid is None:
        return meta

    attempt_id = meta["attempt_id"]
    username = meta.get("owner", "")
    reaped = _is_process_reaped(attempt_id)

    if reaped is False:
        return meta  # Watcher confirms still running

    if reaped is None:
        # Server restarted; init has adopted any zombies so pid_alive is safe.
        from app.services.toss_wts_auth_guard import pid_alive
        if pid_alive(pid, meta.get("_pid_start_time")):
            return meta

    # Process has exited. Post-login session verification.
    now = _kst_now(now_provider)
    if _verify_post_login(settings, username):
        meta["status"] = STATUS_SUCCESS
        meta["finished_at"] = now.isoformat()
        meta["error_code"] = None
    else:
        meta["status"] = STATUS_FAILED
        meta["finished_at"] = now.isoformat()
        if not meta.get("error_code"):
            meta["error_code"] = "AUTH_LOGIN_VERIFY_FAILED"

    _terminal_cleanup(attempt_id, username, meta)
    return meta


def _handle_timeout(
    attempt_id: str,
    username: str,
    meta: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Handle timeout: terminate+reap process BEFORE clearing marker.

    If termination cannot be confirmed, keeps marker active and returns a
    safe error so that other login/extend operations remain blocked.
    """
    pid = meta.get("_pid")
    pid_start = meta.get("_pid_start_time")

    terminated = True
    if pid is not None:
        terminated = _terminate_and_reap(attempt_id, pid, pid_start)

    if not terminated:
        # Cannot confirm termination — keep marker, return safe error
        meta["error_code"] = "AUTH_LOGIN_TERMINATION_PENDING"
        try:
            _write_meta(attempt_id, username, meta)
        except Exception:
            pass
        return meta  # Status remains PENDING; marker blocks other ops

    # Confirmed terminated — advance to TIMEOUT terminal state
    meta["status"] = STATUS_TIMEOUT
    meta["finished_at"] = now.isoformat()
    meta["error_code"] = "AUTH_LOGIN_TIMEOUT"
    _terminal_cleanup(attempt_id, username, meta)
    return meta


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_toss_login(
    settings: dict[str, Any],
    *,
    username: str,
    reauthenticate: bool = False,
    now_provider: Callable[[], datetime] | None = None,
    _popen: Callable[..., Any] = subprocess.Popen,
) -> str:
    """Start a per-user background ``tossctl auth login`` attempt.

    Verified tossctl v0.50.3 argv (shell=False):
        <executable> --config-dir <user_config_dir>
        auth login --headless --link --qr-output <qr_path>

    ``username`` is the authenticated Wealth user (from session, never from
    request body).  The attempt is stored under the user's private directory.

    Raises
    ------
    TossLoginFlagUnverifiedError   _AUTH_LOGIN_FLAG_VERIFIED is False.
    TossLoginError                 Toss WTS is disabled or spawn failed.
    TossSessionAlreadyValidError   Session active+valid, reauthenticate=False.
    TossLoginLockError             Active-op marker exists, or lock busy.
    """
    if not _AUTH_LOGIN_FLAG_VERIFIED:
        raise TossLoginFlagUnverifiedError(
            "tossctl auth login QR output flag has not been verified. "
            "Run: docker exec wealth /opt/toss-wts/tossctl auth login --help"
        )
    if not settings.get("enabled"):
        raise TossLoginError("Toss WTS is not enabled")

    # Validate username early (path-traversal protection)
    from app.services.toss_wts_auth_guard import (
        _validate_username,
        auth_operation_lock,
        check_active_login_operation,
        write_active_op_marker,
        get_pid_start_time,
        TossAuthOperationBusyError,
    )
    _validate_username(username)  # raises ValueError on invalid input

    attempt_id = str(uuid.uuid4())
    started_at = _kst_now(now_provider).isoformat()

    # Per-user config dir (derived from username, not from global settings)
    user_config_dir = _user_config_dir(username)

    try:
        with auth_operation_lock(username, acquire_timeout_seconds=5.0):
            # Reject if another login is already active FOR THIS USER (marker exists)
            if check_active_login_operation(username):
                raise TossLoginLockError(
                    "TOSS_AUTH_OPERATION_BUSY: another login attempt is already active"
                )

            # TOCTOU-safe re-auth check INSIDE lock (per-user)
            if not reauthenticate:
                try:
                    from app.services.toss_wts_session import get_toss_session_status
                    current = get_toss_session_status(username=username, settings=settings)
                    if current.get("active") and current.get("valid"):
                        raise TossSessionAlreadyValidError(
                            "TOSS_SESSION_ALREADY_VALID: session is already active and valid. "
                            "Pass reauthenticate=True to force re-authentication."
                        )
                except (TossSessionAlreadyValidError, TossLoginLockError):
                    raise
                except Exception:
                    pass

            # Prepare QR output path (per-user)
            qr = _qr_path(attempt_id, username)
            qr.parent.mkdir(parents=True, exist_ok=True)
            if not _IS_WINDOWS:
                try:
                    os.chmod(str(qr.parent), 0o700)
                except OSError:
                    pass

            # Verified v0.50.3 argv — uses per-user config-dir
            argv = [
                str(settings["executable"]),
                "--config-dir", str(user_config_dir),
                "auth", "login",
                "--headless",
                "--link",
                _AUTH_LOGIN_QR_FLAG, str(qr),
            ]
            try:
                proc = _popen(
                    argv,
                    shell=False,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as exc:
                raise TossLoginError("AUTH_LOGIN_SPAWN_FAILED") from exc

            # Write marker and meta BEFORE releasing lock.
            # Rollback spawned process if either write fails.
            pid_start_time = get_pid_start_time(proc.pid)
            try:
                write_active_op_marker(username, attempt_id, proc.pid, started_at)
                meta: dict[str, Any] = {
                    "attempt_id": attempt_id,
                    "owner": username,
                    "status": STATUS_PENDING,
                    "started_at": started_at,
                    "finished_at": None,
                    "error_code": None,
                    "_pid": proc.pid,
                    "_pid_start_time": pid_start_time,
                }
                _write_meta(attempt_id, username, meta)
            except Exception as setup_exc:
                _rollback_spawn(attempt_id, username, proc)
                raise TossLoginError("AUTH_LOGIN_SETUP_FAILED") from setup_exc

            # Start watcher AFTER meta is successfully written
            _start_watcher(attempt_id, proc)
            # Lock released here; durable marker stays for attempt lifetime

    except TossAuthOperationBusyError as exc:
        raise TossLoginLockError(f"TOSS_AUTH_OPERATION_BUSY: {exc}") from exc

    return attempt_id


def get_login_attempt(
    attempt_id: str,
    *,
    requesting_username: str,
    now_provider: Callable[[], datetime] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the public status dict for a login attempt.

    Access control: only the owner can poll their own attempt.
    Path namespacing provides implicit isolation; owner field check adds
    defense-in-depth.

    Raises ``TossLoginNotFoundError`` if attempt_id is unknown (including
    attempts owned by a different user).
    """
    meta = _read_meta(attempt_id, requesting_username)

    # Defense-in-depth: explicit owner check
    owner = meta.get("owner")
    if owner and owner != requesting_username:
        raise TossLoginNotFoundError(attempt_id)

    if meta.get("status") == STATUS_PENDING:
        cfg = settings or _resolve_settings()
        meta = _check_and_finalize(meta, cfg, now_provider)

        # Timeout check: terminate process BEFORE clearing marker
        if meta["status"] == STATUS_PENDING:
            started_raw = meta.get("started_at")
            if started_raw:
                try:
                    started = datetime.fromisoformat(started_raw)
                    now = _kst_now(now_provider)
                    if (now - started).total_seconds() > LOGIN_ATTEMPT_MAX_SECONDS:
                        meta = _handle_timeout(attempt_id, requesting_username, meta, now)
                except (ValueError, TypeError):
                    pass

        if meta.get("status") != STATUS_PENDING:
            try:
                _write_meta(attempt_id, requesting_username, meta)
            except Exception:
                pass

    return _safe_public(meta)


def get_login_qr(attempt_id: str, *, requesting_username: str) -> bytes | None:
    """Return QR PNG bytes iff the attempt is pending and QR file exists.

    Access control: only the owner can fetch their QR.
    Returns None for non-pending attempts, missing QR, or wrong owner.
    Served with Cache-Control: no-store.
    """
    try:
        meta = _read_meta(attempt_id, requesting_username)
    except TossLoginNotFoundError:
        return None
    # Defense-in-depth: owner check
    if meta.get("owner") and meta["owner"] != requesting_username:
        return None
    if meta.get("status") != STATUS_PENDING:
        return None
    qr = _qr_path(attempt_id, requesting_username)
    if not qr.exists() or qr.stat().st_size == 0:
        return None
    try:
        return qr.read_bytes()
    except OSError:
        return None


def cancel_login_attempt(
    attempt_id: str,
    *,
    requesting_username: str,
    now_provider: Callable[[], datetime] | None = None,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cancel a pending login attempt.

    Access control: only the owner can cancel their attempt.

    Race-safe design:
      1. If the process completed before this cancel was processed, finalize
         with SUCCESS/FAILED (not CANCELLED) based on post-login verification.
      2. Only if the process is confirmed still running: terminate+reap, then
         CANCELLED.
      3. Terminates and reaps BEFORE clearing the active-op marker.
      4. If termination cannot be confirmed, marker is kept and a safe error
         returned so other login/extend cannot start.

    Raises ``TossLoginNotFoundError`` if attempt_id is unknown or not owned
    by ``requesting_username``.
    """
    meta = _read_meta(attempt_id, requesting_username)

    # Defense-in-depth: owner check
    owner = meta.get("owner")
    if owner and owner != requesting_username:
        raise TossLoginNotFoundError(attempt_id)

    if meta.get("status") != STATUS_PENDING:
        return _safe_public(meta)

    # Check if process already completed before this cancel was processed.
    cfg = settings or _resolve_settings()
    meta = _check_and_finalize(meta, cfg, now_provider)
    if meta.get("status") != STATUS_PENDING:
        return _safe_public(meta)

    # Process still running: terminate, wait for reap, then CANCELLED.
    pid = meta.get("_pid")
    pid_start = meta.get("_pid_start_time")
    username = meta.get("owner", requesting_username)

    if pid is not None:
        terminated = _terminate_and_reap(attempt_id, pid, pid_start)
        if not terminated:
            meta["error_code"] = "AUTH_LOGIN_CANCEL_TERMINATION_PENDING"
            try:
                _write_meta(attempt_id, username, meta)
            except Exception:
                pass
            return _safe_public(meta)  # status still "pending"; marker remains

    # Process confirmed terminated — advance to CANCELLED terminal state
    now = _kst_now(now_provider)
    meta["status"] = STATUS_CANCELLED
    meta["finished_at"] = now.isoformat()
    _terminal_cleanup(attempt_id, username, meta)
    return _safe_public(meta)


def check_active_login_operation(username: str) -> bool:
    """Convenience re-export from toss_wts_auth_guard (per-user)."""
    from app.services.toss_wts_auth_guard import check_active_login_operation as _c
    return _c(username)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_settings() -> dict[str, Any]:
    try:
        from app.services.system_settings import resolve_toss_wts_settings
        return resolve_toss_wts_settings()
    except Exception:
        return {}
