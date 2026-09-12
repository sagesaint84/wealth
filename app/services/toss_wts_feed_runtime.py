"""Process-local runtime session confirmation guard for Toss WTS feed access.

This module enforces explicit runtime confirmation of the local WTS session
material for the deployment-authorized Wealth user.

SECURITY ARCHITECTURE CONTRACT:
1. PROCESS_LOCAL_CONFIRMATION_ONLY:
   Confirmation exists solely in Python process memory. It is never persisted
   to disk, cache, users.json, .env, or browser cookies. Process restart
   naturally yields NOT_CONFIRMED.
2. CHANGE-DETECTION ONLY (NO PROVIDER IDENTITY CLAIM):
   Metadata confirmation only proves that the locally observed WTS runtime
   material (executable, config directory, session file) has not changed since
   explicit confirmation. It does NOT prove that the session belongs to Wealth
   user X; that ownership assertion comes solely from explicit confirmation
   by the statically allowed Wealth user.
3. SESSION CONTENTS NEVER READ:
   The session file is inspected exclusively through filesystem metadata
   (size, mtime, file identity). Contents are never opened, read, parsed, or hashed.
4. ZERO PROVIDER/TRANSPORT CALLS:
   This module never executes tossctl, launches browser auth, or makes financial
   requests.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import threading

from app.services.toss_wts_adapter import EXPECTED_TOSSCTL_VERSION
from app.services.toss_wts_feed_auth import (
    _get_allowed_user_id,
    check_wts_feed_static_authorization,
)

PROCESS_LOCAL_CONFIRMATION_ONLY = True
MULTI_PROCESS_SHARED_CONFIRMATION = False

SESSION_FILENAME = "session.json"

# Decision codes
CONFIRMED = "CONFIRMED"
STATIC_AUTHORIZATION_FAILED = "STATIC_AUTHORIZATION_FAILED"
NOT_CONFIRMED = "NOT_CONFIRMED"
RUNTIME_MATERIAL_UNAVAILABLE = "RUNTIME_MATERIAL_UNAVAILABLE"
RUNTIME_GENERATION_CHANGED = "RUNTIME_GENERATION_CHANGED"
CONFIRMATION_IDENTITY_CHANGED = "CONFIRMATION_IDENTITY_CHANGED"


@dataclass(frozen=True)
class WtsFeedRuntimeDecision:
    """Privacy-safe runtime confirmation decision.

    Attributes:
        confirmed: True if and only if runtime confirmation is valid and current.
        code: Safe public status code explaining the decision without leaking
            identifiers, paths, or file metadata.
    """

    confirmed: bool
    code: str

    def as_dict(self) -> dict[str, object]:
        return {"confirmed": self.confirmed, "code": self.code}

    def __bool__(self) -> bool:
        return self.confirmed

    def __getitem__(self, item: str) -> object:
        if item == "confirmed":
            return self.confirmed
        if item == "code":
            return self.code
        raise KeyError(item)


@dataclass(frozen=True)
class _RuntimeGenerationMarker:
    """Internal change-detection generation marker.

    Never exposed to callers or serialized outside process memory.
    """

    allowed_user_id: str
    expected_version: str
    executable_meta: tuple[str, int, int, int, int]
    config_dir_meta: tuple[str, int, int]
    session_meta: tuple[str, int, int, int, int]


@dataclass(frozen=True)
class _ActiveConfirmation:
    """In-memory binding of confirming Wealth user and runtime generation."""

    user_id: str
    allowed_user_id: str
    marker: _RuntimeGenerationMarker


_LOCK = threading.RLock()
_ACTIVE_CONFIRMATION: _ActiveConfirmation | None = None


def _is_wts_enabled() -> bool:
    return os.getenv("WEALTH_TOSS_WTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_runtime_generation_marker() -> _RuntimeGenerationMarker | None:
    """Resolve current metadata-only generation marker.

    Returns None if WTS is disabled or any runtime material (executable,
    config directory, session file) is missing or unreadable.
    Never reads session file content.
    """
    if not _is_wts_enabled():
        return None

    allowed_user_id, err = _get_allowed_user_id()
    if err is not None or allowed_user_id is None:
        return None

    executable_env = os.getenv("WEALTH_TOSSCTL_PATH", "").strip()
    config_dir_env = os.getenv("WEALTH_TOSSCTL_CONFIG_DIR", "").strip()
    if not executable_env or not config_dir_env:
        return None

    expected_version = (
        os.getenv("WEALTH_TOSSCTL_EXPECTED_VERSION", EXPECTED_TOSSCTL_VERSION).strip()
        or EXPECTED_TOSSCTL_VERSION
    )

    try:
        executable_path = Path(executable_env).expanduser()
        config_dir_path = Path(config_dir_env).expanduser()
        session_path = config_dir_path / SESSION_FILENAME

        if not executable_path.is_file():
            return None
        if not config_dir_path.is_dir():
            return None
        if not session_path.is_file():
            return None

        exe_stat = executable_path.stat()
        dir_stat = config_dir_path.stat()
        session_stat = session_path.stat()

        exe_meta = (
            os.path.normcase(str(executable_path.resolve())),
            exe_stat.st_size,
            exe_stat.st_mtime_ns,
            getattr(exe_stat, "st_dev", 0),
            getattr(exe_stat, "st_ino", 0),
        )

        dir_meta = (
            os.path.normcase(str(config_dir_path.resolve())),
            getattr(dir_stat, "st_dev", 0),
            getattr(dir_stat, "st_ino", 0),
        )

        session_meta = (
            os.path.normcase(str(session_path.resolve())),
            session_stat.st_size,
            session_stat.st_mtime_ns,
            getattr(session_stat, "st_dev", 0),
            getattr(session_stat, "st_ino", 0),
        )

        return _RuntimeGenerationMarker(
            allowed_user_id=allowed_user_id,
            expected_version=expected_version,
            executable_meta=exe_meta,
            config_dir_meta=dir_meta,
            session_meta=session_meta,
        )
    except OSError:
        return None


def confirm_wts_feed_runtime_session(
    user_id: object = None,
) -> WtsFeedRuntimeDecision:
    """Explicitly confirm the current WTS runtime session material for *user_id*.

    Requires static allowed-user authorization. Captures the current
    metadata-only runtime generation marker and stores confirmation in
    process-local memory.

    Does not read session contents, launch browser auth, or make provider calls.
    """
    global _ACTIVE_CONFIRMATION

    static_auth = check_wts_feed_static_authorization(user_id)
    if not static_auth.authorized:
        return WtsFeedRuntimeDecision(
            confirmed=False, code=STATIC_AUTHORIZATION_FAILED
        )

    marker = _resolve_runtime_generation_marker()
    if marker is None:
        with _LOCK:
            _ACTIVE_CONFIRMATION = None
        return WtsFeedRuntimeDecision(
            confirmed=False, code=RUNTIME_MATERIAL_UNAVAILABLE
        )

    with _LOCK:
        _ACTIVE_CONFIRMATION = _ActiveConfirmation(
            user_id=str(user_id),
            allowed_user_id=marker.allowed_user_id,
            marker=marker,
        )

    return WtsFeedRuntimeDecision(confirmed=True, code=CONFIRMED)


def check_wts_feed_runtime_confirmation(
    user_id: object = None,
) -> WtsFeedRuntimeDecision:
    """Determine whether *user_id* holds a valid, current runtime session confirmation.

    Requires static allowed-user authorization. Verifies that process-local
    confirmation exists, belongs to *user_id*, and that runtime generation
    material has not changed since confirmation.
    """
    global _ACTIVE_CONFIRMATION

    static_auth = check_wts_feed_static_authorization(user_id)
    if not static_auth.authorized:
        current_allowed, _ = _get_allowed_user_id()
        with _LOCK:
            if (
                _ACTIVE_CONFIRMATION is not None
                and current_allowed != _ACTIVE_CONFIRMATION.allowed_user_id
            ):
                _ACTIVE_CONFIRMATION = None
        return WtsFeedRuntimeDecision(
            confirmed=False, code=STATIC_AUTHORIZATION_FAILED
        )

    with _LOCK:
        active = _ACTIVE_CONFIRMATION

    if active is None:
        return WtsFeedRuntimeDecision(confirmed=False, code=NOT_CONFIRMED)

    if active.user_id != str(user_id) or active.allowed_user_id != str(user_id):
        with _LOCK:
            _ACTIVE_CONFIRMATION = None
        return WtsFeedRuntimeDecision(
            confirmed=False, code=CONFIRMATION_IDENTITY_CHANGED
        )

    current_marker = _resolve_runtime_generation_marker()
    if current_marker is None:
        with _LOCK:
            _ACTIVE_CONFIRMATION = None
        return WtsFeedRuntimeDecision(
            confirmed=False, code=RUNTIME_MATERIAL_UNAVAILABLE
        )

    if current_marker != active.marker:
        with _LOCK:
            _ACTIVE_CONFIRMATION = None
        return WtsFeedRuntimeDecision(
            confirmed=False, code=RUNTIME_GENERATION_CHANGED
        )

    return WtsFeedRuntimeDecision(confirmed=True, code=CONFIRMED)


def clear_wts_feed_runtime_confirmation() -> None:
    """Explicitly clear process-local runtime confirmation state.

    Performs no filesystem, network, or provider operations.
    """
    global _ACTIVE_CONFIRMATION
    with _LOCK:
        _ACTIVE_CONFIRMATION = None


def get_current_runtime_generation_id(user_id: object = None) -> str | None:
    """Return a deterministic generation identifier for the confirmed session.

    Returns None if the session is not confirmed or runtime material has changed.
    """
    decision = check_wts_feed_runtime_confirmation(user_id)
    if not decision.confirmed:
        return None
    with _LOCK:
        active = _ACTIVE_CONFIRMATION
        if active is None:
            return None
        marker_repr = (
            f"{active.user_id}:{active.allowed_user_id}:"
            f"{active.marker.executable_meta}:{active.marker.config_dir_meta}:{active.marker.session_meta}"
        )
        return hashlib.sha256(marker_repr.encode("utf-8")).hexdigest()
