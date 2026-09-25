"""Action Link V2 Foundation.

Design:
- Provider-independent action models: MARK_IPO_APPLIED, OPEN_IPO_SALE_FLOW
- Secure storage: SHA-256 digest lookup, raw token never persisted
- Safe URL generation using system_settings.public_base_url
- Robust locking and atomic durability via atomic_write_private_json
- Fail-closed on corrupt or expired state
- Read-only lookup and state resolution
- Strict username binding and canonical application CAS dispatch
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import threading
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.ipo.actions import (
    IpoActionAlreadyRunning,
    IpoActionError,
    mark_ipo_owner_applied,
    validate_ipo_subscription_eligibility,
)
from app.services.secure_files import atomic_write_private_json
from app.services.system_settings import get_effective_system_settings

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACTION_V2_FILE = REPO_ROOT / "data" / "system" / "action_v2_state.json"

ACTION_RETENTION_DAYS = 7
_ACTION_V2_LOCK = threading.Lock()

# Supported action types
ACTION_TYPE_MARK_IPO_APPLIED = "MARK_IPO_APPLIED"
ACTION_TYPE_OPEN_IPO_SALE_FLOW = "OPEN_IPO_SALE_FLOW"
SUPPORTED_ACTION_TYPES = {
    ACTION_TYPE_MARK_IPO_APPLIED,
    ACTION_TYPE_OPEN_IPO_SALE_FLOW,
}

_ACTION_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def validate_action_token(token: str) -> str:
    """Validate that token matches [A-Za-z0-9_-]{16,64}. Fail fast on malformed token."""
    if not isinstance(token, str) or not _ACTION_TOKEN_RE.fullmatch(token.strip()):
        raise IpoActionError("ACTION_TOKEN_INVALID")
    return token.strip()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_action_token(token: str) -> str:
    """Return hex-encoded SHA-256 digest of an action token."""
    valid_token = validate_action_token(token)
    return hashlib.sha256(valid_token.encode("utf-8")).hexdigest()


def get_action_v2_file_path(path: Path | str | None = None) -> Path:
    """Resolve target Action V2 state file path.

    Precedence:
    1. Explicit path parameter.
    2. WEALTH_DATA_DIR environment variable (<WEALTH_DATA_DIR>/system/action_v2_state.json).
    3. Default repo path: <repo>/data/system/action_v2_state.json.
    """
    if path is not None:
        return Path(path)
    root = os.getenv("WEALTH_DATA_DIR", "").strip()
    if root:
        return Path(root) / "system" / "action_v2_state.json"
    return DEFAULT_ACTION_V2_FILE


@contextmanager
def action_v2_lock(path: Path | str | None = None):
    """Process-level and cross-process advisory lock for Action V2 store."""
    target = get_action_v2_file_path(path)
    if not _ACTION_V2_LOCK.acquire(blocking=False):
        raise IpoActionAlreadyRunning("ACTION_V2_ALREADY_RUNNING")
    handle = None
    try:
        lock_path = target.with_suffix(".lock")
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
            raise IpoActionAlreadyRunning("ACTION_V2_ALREADY_RUNNING") from exc
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
        _ACTION_V2_LOCK.release()


def _load_v2(path: Path | str | None = None) -> dict[str, Any]:
    target = get_action_v2_file_path(path)
    if not target.exists():
        return {"version": 2, "actions": {}}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        logger.warning("Action V2 state JSON parse failed: %s", exc)
        raise IpoActionError("ACTION_V2_STATE_INVALID") from None
    except Exception as exc:
        logger.warning("Action V2 state load failed: %s", exc)
        raise IpoActionError("ACTION_V2_STATE_INVALID") from None
    if not isinstance(data, dict) or not isinstance(data.get("actions", {}), dict):
        raise IpoActionError("ACTION_V2_STATE_INVALID")
    data.setdefault("version", 2)
    data.setdefault("actions", {})
    return data


def _save_v2(data: dict[str, Any], path: Path | str | None = None) -> None:
    target = get_action_v2_file_path(path)
    atomic_write_private_json(target, data, indent=2)


def prune_old_v2_actions(data: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    if now is None:
        now = _now_utc()
    cutoff = now - timedelta(days=ACTION_RETENTION_DAYS)
    actions = data.get("actions", {})
    kept: dict[str, Any] = {}
    for digest, action in actions.items():
        consumed_at_str = action.get("consumed_at")
        expires_at_str = action.get("expires_at")
        if consumed_at_str:
            try:
                consumed_at = datetime.fromisoformat(consumed_at_str)
                if consumed_at.tzinfo is None:
                    consumed_at = consumed_at.replace(tzinfo=timezone.utc)
                if consumed_at <= cutoff:
                    continue
            except ValueError:
                pass
        elif expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at <= cutoff:
                    continue
            except ValueError:
                pass
        kept[digest] = action
    data["actions"] = kept
    return data


def is_action_expired(action: dict[str, Any], today: date | None = None) -> bool:
    """Check if action is expired based on subscription/business rules."""
    current_today = today or datetime.now(KST).date()
    expires_at_str = action.get("expires_at")
    if not expires_at_str:
        return True
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        # Expires at end-of-day KST (23:59:59). If before start-of-today 00:00:00 KST -> expired
        start_of_today_kst = datetime.combine(current_today, time(0, 0, 0), tzinfo=KST)
        return expires_at < start_of_today_kst.astimezone(timezone.utc)
    except ValueError:
        return True


def create_web_action(
    *,
    action_type: str,
    username: str,
    source_channel: str = "web",
    metadata: dict[str, Any] | None = None,
    expires_at: datetime | None = None,
    today: date | None = None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a new Web Action V2 token and store its SHA-256 digest."""
    norm_user = str(username or "").strip()
    if not norm_user:
        raise IpoActionError("USERNAME_REQUIRED")
    if action_type not in SUPPORTED_ACTION_TYPES:
        raise IpoActionError("UNSUPPORTED_ACTION_TYPE")

    meta = dict(metadata or {})
    current_today = today or datetime.now(KST).date()

    if action_type == ACTION_TYPE_MARK_IPO_APPLIED:
        ipo_id = meta.get("ipo_id")
        owner = meta.get("owner")
        if not ipo_id or not owner:
            raise IpoActionError("MISSING_ACTION_METADATA")
        # Reuse canonical validation helper
        _, _, _, end = validate_ipo_subscription_eligibility(
            ipo_id, owner, norm_user, current_today
        )

        # Expiry matches subscription end 23:59:59 KST
        if expires_at is None:
            end_kst = datetime.combine(end, time(23, 59, 59), tzinfo=KST)
            expires_at = end_kst.astimezone(timezone.utc)
    elif action_type == ACTION_TYPE_OPEN_IPO_SALE_FLOW:
        if expires_at is None:
            # Default 7 days expiry for sale flow skeleton
            expires_at = _now_utc() + timedelta(days=7)

    raw_token = secrets.token_urlsafe(32)
    validate_action_token(raw_token)
    digest = hash_action_token(raw_token)
    target_path = get_action_v2_file_path(path)

    with action_v2_lock(target_path):
        data = _load_v2(target_path)
        while digest in data["actions"]:
            raw_token = secrets.token_urlsafe(32)
            digest = hash_action_token(raw_token)

        now_iso = _now_utc().isoformat()
        action_record = {
            "token_digest": digest,
            "version": 2,
            "action_type": action_type,
            "username": norm_user,
            "source_channel": source_channel,
            "created_at": now_iso,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "consumed_at": None,
            "metadata": meta,
        }
        data["actions"][digest] = action_record
        _save_v2(data, target_path)

    # Return structure containing raw token ONLY to the caller
    return {
        "raw_token": raw_token,
        "token_digest": digest,
        "action_type": action_type,
        "username": norm_user,
        "expires_at": action_record["expires_at"],
        "metadata": meta,
    }


def build_action_url(token: str) -> str:
    """Build full HTTPS action landing URL using system public_base_url."""
    valid_token = validate_action_token(token)
    settings = get_effective_system_settings()
    base_url = settings.get("public_base_url")
    if not base_url:
        raise IpoActionError("PUBLIC_BASE_URL_NOT_CONFIGURED")
    clean_base = base_url.rstrip("/")
    return f"{clean_base}/a/{valid_token}"


def get_web_action_metadata(token: str, *, path: Path | str | None = None) -> dict[str, Any] | None:
    """Read-only lookup of action record by raw token.

    Returns sanitized copy of action data, never mutates state.
    """
    try:
        digest = hash_action_token(token)
    except Exception:
        return None

    target_path = get_action_v2_file_path(path)
    # Read-only check: if file doesn't exist, return None immediately without taking lock
    if not target_path.exists():
        return None

    with action_v2_lock(target_path):
        data = _load_v2(target_path)
        record = data.get("actions", {}).get(digest)
        if not record or not isinstance(record, dict):
            return None
        # Return deep copy of record for read-only inspection
        return json.loads(json.dumps(record))


def execute_web_action(
    token: str,
    *,
    authenticated_username: str,
    today: date | None = None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Execute Web Action V2. Only POST calls should invoke this.

    Enforces:
    1. Token validation & digest lookup
    2. Strict username match
    3. Expiry check
    4. Idempotent check (already consumed -> return already_processed)
    5. Action executability check (OPEN_IPO_SALE_FLOW is not executable in Phase 2)
    6. Canonical business mutation (mark_ipo_owner_applied)
    7. Mark consumed_at and prune old actions on success
    """
    try:
        digest = hash_action_token(token)
    except Exception:
        raise IpoActionError("ACTION_NOT_FOUND")

    target_path = get_action_v2_file_path(path)
    current_today = today or datetime.now(KST).date()

    with action_v2_lock(target_path):
        data = _load_v2(target_path)
        action = data.get("actions", {}).get(digest)
        if not action or not isinstance(action, dict):
            raise IpoActionError("ACTION_NOT_FOUND")

        # Username binding validation
        if action.get("username") != authenticated_username:
            raise IpoActionError("FORBIDDEN")

        # Idempotency: if already consumed
        if action.get("consumed_at"):
            return {
                "status": "already_processed",
                "action_type": action.get("action_type"),
                "consumed_at": action.get("consumed_at"),
            }

        # Expiry check
        if is_action_expired(action, current_today):
            raise IpoActionError("ACTION_EXPIRED")

        action_type = action.get("action_type")
        meta = action.get("metadata", {})

        if action_type == ACTION_TYPE_MARK_IPO_APPLIED:
            ipo_id = meta.get("ipo_id")
            owner = meta.get("owner")
            # Invoke canonical CAS mutation logic
            result = mark_ipo_owner_applied(
                action["username"], ipo_id, owner, today=current_today
            )
            # Only mark consumed after successful canonical mutation
            action["consumed_at"] = _now_utc().isoformat()
            prune_old_v2_actions(data)
            _save_v2(data, target_path)
            return result
        elif action_type == ACTION_TYPE_OPEN_IPO_SALE_FLOW:
            # Phase 2: Not executable. No mutation, no consumed_at update.
            raise IpoActionError("ACTION_NOT_EXECUTABLE")
        else:
            raise IpoActionError("UNSUPPORTED_ACTION_TYPE")
