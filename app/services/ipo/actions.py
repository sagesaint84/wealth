"""Internal, provider-independent IPO application actions; no HTTP surface.

Design:
- action_state_lock: same-process threading.Lock + cross-process advisory file lock
- _load / _save: fail-closed on corrupt state; atomic temp→replace write; allow_nan=False
- prune_old_actions: called on every successful save; retention = 7 days post-consumed/expired
- create_mark_applied_action: validates, generates opaque action_id, stores metadata
- execute_action: validate → CAS mark_ipo_owner_applied (1 bounded retry) → consume → prune → save
- mark_ipo_owner_applied: no-write if already_applied; bounded-retry on ApplicationRevisionConflict
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.ipo.applications import (
    ApplicationRevisionConflict,
    get_user_applications,
    update_user_application,
)
from app.services.ipo.store import read_market_store_read_only

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTION_FILE = Path(__file__).resolve().parents[3] / "data" / "ipo" / "action_state.json"

# Actions older than this (post consumed_at or post expires_at) are eligible for pruning.
ACTION_RETENTION_DAYS = 7

KST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class IpoActionError(RuntimeError):
    pass


class IpoActionAlreadyRunning(IpoActionError):
    pass


# ---------------------------------------------------------------------------
# Process-level threading lock
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Advisory file lock (same API as notification_state_lock / _refresh_file_lock)
# ---------------------------------------------------------------------------

@contextmanager
def action_state_lock(path: Path = ACTION_FILE):
    """Non-blocking: same-process threading.Lock + cross-process OS advisory file lock."""
    if not _LOCK.acquire(blocking=False):
        raise IpoActionAlreadyRunning("IPO_ACTION_ALREADY_RUNNING")
    handle = None
    try:
        lock_path = path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+b")
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
        except OSError as exc:
            raise IpoActionAlreadyRunning("IPO_ACTION_ALREADY_RUNNING") from exc
        yield
    finally:
        try:
            if handle is not None:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        if handle is not None:
            handle.close()
        _LOCK.release()


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load(path: Path = ACTION_FILE) -> dict[str, Any]:
    """Load action state. Fail-closed on corrupt/invalid JSON — never silently returns {}."""
    if not path.exists():
        return {"actions": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise IpoActionError("ACTION_STATE_INVALID") from exc
    if not isinstance(data, dict) or not isinstance(data.get("actions", {}), dict):
        raise IpoActionError("ACTION_STATE_INVALID")
    data.setdefault("actions", {})
    return data


def _save(data: dict[str, Any], path: Path = ACTION_FILE) -> None:
    """Atomic temp→replace write; allow_nan=False; .tmp cleaned on failure."""
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
        tmp.replace(path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def prune_old_actions(data: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Remove actions that are safe to prune.

    Pruning eligibility:
    - consumed AND consumed_at <= now - ACTION_RETENTION_DAYS
    - OR unconsumed AND expires_at <= now - ACTION_RETENTION_DAYS

    Active (unconsumed, not yet expired by retention window) actions are always kept.
    """
    if now is None:
        now = _now_utc()
    cutoff = now - timedelta(days=ACTION_RETENTION_DAYS)
    actions = data.get("actions", {})
    kept: dict[str, Any] = {}
    for aid, action in actions.items():
        consumed_at_str = action.get("consumed_at")
        expires_at_str = action.get("expires_at")
        if consumed_at_str:
            # Consumed — prune only after retention window
            try:
                consumed_at = datetime.fromisoformat(consumed_at_str)
                # Make aware if naive (treat as UTC)
                if consumed_at.tzinfo is None:
                    consumed_at = consumed_at.replace(tzinfo=timezone.utc)
                if consumed_at <= cutoff:
                    continue  # prune
            except ValueError:
                pass  # malformed timestamp → keep (fail-safe)
        elif expires_at_str:
            # Unconsumed — prune only if expired AND past retention window
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at <= cutoff:
                    continue  # prune
            except ValueError:
                pass
        kept[aid] = action
    data["actions"] = kept
    return data


# ---------------------------------------------------------------------------
# Expiry helpers
# ---------------------------------------------------------------------------

def _subscription_expiry(subscription_end: date) -> datetime:
    """Return the last valid instant for a subscription: end-day 23:59:59 KST as UTC-aware datetime."""
    end_kst = datetime.combine(subscription_end, time(23, 59, 59), tzinfo=KST)
    return end_kst.astimezone(timezone.utc)


def _is_expired(action: dict[str, Any], today: date) -> bool:
    """Return True if the action's business expiry has passed.

    An action expires at end-of-day KST (23:59:59) on the subscription_end date.
    If expires_at >= start-of-today KST (00:00:00), the action is still valid.
    If expires_at < start-of-today KST, the action belongs to a past day and is expired.
    """
    expires_at_str = action.get("expires_at")
    if not expires_at_str:
        return True
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        # start-of-today 00:00:00 KST: if expires_at is before this, the action is from a prior day
        start_of_today_kst = datetime.combine(today, time(0, 0, 0), tzinfo=KST)
        return expires_at < start_of_today_kst.astimezone(timezone.utc)
    except ValueError:
        return True


# ---------------------------------------------------------------------------
# Market / validation helpers
# ---------------------------------------------------------------------------

def _market_ipo(ipo_id: str) -> dict[str, Any]:
    ipo = next(
        (x for x in read_market_store_read_only().get("ipos", []) if x.get("ipo_id") == ipo_id),
        None,
    )
    if not isinstance(ipo, dict):
        raise IpoActionError("IPO_NOT_FOUND")
    return ipo


def _validate(ipo_id: str, owner: str, username: str | None, today: date) -> tuple:
    """Validate subscription window and owner eligibility. Returns (ipo, apps, app, end)."""
    ipo = _market_ipo(ipo_id)
    try:
        start = date.fromisoformat(str(ipo.get("subscription_start") or "")[:10])
        end = date.fromisoformat(str(ipo.get("subscription_end") or "")[:10])
    except (ValueError, TypeError):
        raise IpoActionError("SUBSCRIPTION_NOT_ACTIVE")
    if end < start or not (start <= today <= end):
        raise IpoActionError("SUBSCRIPTION_NOT_ACTIVE")

    apps = get_user_applications(username)
    app = apps.get("applications", {}).get(ipo_id, {})
    targets = list(app.get("target_owners") or apps.get("family_members") or [])
    if owner not in targets:
        raise IpoActionError("OWNER_NOT_ELIGIBLE")
    return ipo, apps, app, end


# ---------------------------------------------------------------------------
# Core command: mark_ipo_owner_applied (with CAS bounded retry)
# ---------------------------------------------------------------------------

def mark_ipo_owner_applied(
    username: str | None,
    ipo_id: str,
    owner: str,
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Mark one owner as applied.

    CAS policy:
    - Read current revision from get_user_applications()
    - If already applied → return status=already_applied (no write)
    - Call update_user_application() with that revision
    - On ApplicationRevisionConflict: re-read once
        - If now already applied → status=already_applied
        - Else → one bounded retry with fresh revision
        - Second conflict → re-raise
    """
    today = today or datetime.now(KST).date()
    _validate(ipo_id, owner, username, today)

    apps = get_user_applications(username)
    app = apps.get("applications", {}).get(ipo_id, {})
    applied = list(app.get("applied_owners") or [])

    if owner in applied:
        return {"status": "already_applied", "ipo_id": ipo_id, "owner": owner}

    new_applied = list(dict.fromkeys(applied + [owner]))  # deduplicated, ordered
    try:
        result = update_user_application(username, ipo_id, new_applied, int(apps["revision"]))
        return {"status": "applied", "ipo_id": ipo_id, "owner": owner, "revision": result["revision"]}
    except ApplicationRevisionConflict:
        # CAS retry: re-read once
        apps2 = get_user_applications(username)
        app2 = apps2.get("applications", {}).get(ipo_id, {})
        applied2 = list(app2.get("applied_owners") or [])
        if owner in applied2:
            return {"status": "already_applied", "ipo_id": ipo_id, "owner": owner}
        # Owner still pending — one bounded retry with fresh revision
        new_applied2 = list(dict.fromkeys(applied2 + [owner]))
        result2 = update_user_application(username, ipo_id, new_applied2, int(apps2["revision"]))
        return {"status": "applied", "ipo_id": ipo_id, "owner": owner, "revision": result2["revision"]}


# ---------------------------------------------------------------------------
# Action creation
# ---------------------------------------------------------------------------

def create_mark_applied_action(
    username: str | None,
    ipo_id: str,
    owner: str,
    source_channel: str,
    *,
    today: date | None = None,
    path: Path = ACTION_FILE,
) -> dict[str, Any]:
    """Validate and create a MARK_IPO_APPLIED action token. Returns action metadata copy."""
    today = today or datetime.now(KST).date()
    _, _, _, end = _validate(ipo_id, owner, username, today)
    expires_at = _subscription_expiry(end)

    with action_state_lock(path):
        data = _load(path)
        aid = secrets.token_urlsafe(24)
        while aid in data["actions"]:
            aid = secrets.token_urlsafe(24)
        now_iso = _now_utc().isoformat()
        data["actions"][aid] = {
            "action_id": aid,
            "action_type": "MARK_IPO_APPLIED",
            "username": username,
            "ipo_id": ipo_id,
            "owner": owner,
            "created_at": now_iso,
            "expires_at": expires_at.isoformat(),
            "consumed_at": None,
            "source_channel": source_channel,
        }
        _save(data, path)
        return data["actions"][aid].copy()


# ---------------------------------------------------------------------------
# Action execution
# ---------------------------------------------------------------------------

def execute_action(
    action_id: str,
    *,
    today: date | None = None,
    path: Path = ACTION_FILE,
) -> dict[str, Any]:
    """Execute a stored action (MARK_IPO_APPLIED).

    Steps (all within action_state_lock):
    1. Load state (fail-closed)
    2. Look up action_id → ACTION_NOT_FOUND
    3. Already consumed → status=already_processed
    4. Business expiry check → ACTION_EXPIRED
    5. mark_ipo_owner_applied() (with CAS retry)
    6. Mark consumed_at (UTC-aware ISO)
    7. Prune old actions
    8. Atomic save
    9. Return command result
    """
    today = today or datetime.now(KST).date()
    with action_state_lock(path):
        data = _load(path)
        action = data["actions"].get(action_id)
        if action is None:
            raise IpoActionError("ACTION_NOT_FOUND")
        if action.get("consumed_at"):
            return {"status": "already_processed", "action_id": action_id}
        if _is_expired(action, today):
            raise IpoActionError("ACTION_EXPIRED")

        result = mark_ipo_owner_applied(
            action["username"], action["ipo_id"], action["owner"], today=today
        )
        action["consumed_at"] = _now_utc().isoformat()
        prune_old_actions(data)
        _save(data, path)
        return result


def get_action_metadata(action_id: str, *, path: Path = ACTION_FILE) -> dict[str, Any] | None:
    """Provider authorization lookup; read-only and action-store-lock protected."""
    with action_state_lock(path):
        action = _load(path)["actions"].get(action_id)
        return dict(action) if isinstance(action, dict) else None
