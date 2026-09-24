"""User token and account mapping secure storage for KFTC Open Banking.

Stored files per user:
- data/users/<username>/kftc_openbanking_token.json
- data/users/<username>/kftc_openbanking_accounts.json
- data/users/<username>/kftc_openbanking_oauth_state.json
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.kftc_openbanking_crypto import (
    KftcCryptoError,
    decrypt_string,
    encrypt_string,
)
from app.services.secure_files import atomic_write_private_json
from app.services.user_manager import get_user_data_dir

logger = logging.getLogger(__name__)

ACCOUNT_CONTEXT = "wealth:kftc-openbanking-account:v1"


class KftcStorageError(Exception):
    """Raised when token or account storage operation fails."""


def _get_user_kftc_file(username: str, filename: str) -> Path:
    user_dir = get_user_data_dir(username)
    return user_dir / filename


# ==============================================================================
# OAuth State Storage
# ==============================================================================

def save_oauth_state(
    username: str,
    *,
    state: str,
    session_id: str,
    ttl_seconds: int = 600,
) -> None:
    """Save an unconsumed OAuth state with username/session binding and TTL."""
    file_path = _get_user_kftc_file(username, "kftc_openbanking_oauth_state.json")
    now_ts = int(datetime.now(timezone.utc).timestamp())
    payload = {
        "version": 1,
        "username": username,
        "session_id": session_id,
        "state": state,
        "created_at": now_ts,
        "expires_at": now_ts + ttl_seconds,
    }
    atomic_write_private_json(file_path, payload, indent=2)


def consume_oauth_state(
    username: str,
    *,
    state: str,
    session_id: str,
) -> bool:
    """Validate and atomically consume one-time OAuth state.

    Order of operations:
    1. If file does not exist, return False.
    2. Read and parse state metadata. If corrupt, remove corrupt file and raise KftcStorageError.
    3. Validate username, session_id, state (CSPRNG), and TTL.
       If any check fails (e.g. wrong session, state mismatch):
       - If expired, purge the expired file and return False.
       - If mismatch (wrong state/session), DO NOT destroy the valid pending state file, return False.
    4. Only when all validations pass:
       - Atomically unlink (consume) the state file before token exchange.
       - Replay is strictly blocked since file is unlinked.
       - Even if token exchange fails later, state is not restored.
    """
    file_path = _get_user_kftc_file(username, "kftc_openbanking_oauth_state.json")
    if not file_path.exists():
        return False

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        raise KftcStorageError("OAUTH_STATE_CORRUPT") from exc

    if not isinstance(data, dict) or data.get("version") != 1:
        file_path.unlink(missing_ok=True)
        return False

    # Check expiration first: if expired, purge and fail
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if now_ts > int(data.get("expires_at", 0)):
        file_path.unlink(missing_ok=True)
        return False

    # Check identity and state match without deleting valid pending state on mismatch
    if data.get("username") != username:
        return False
    if data.get("session_id") != session_id:
        return False
    if not state or not secrets.compare_digest(str(data.get("state")), str(state)):
        return False

    # All validations succeeded: atomically consume (unlink) the state file
    file_path.unlink(missing_ok=True)
    return True


# ==============================================================================
# Token Storage
# ==============================================================================

def save_user_tokens(
    username: str,
    *,
    access_token: str,
    refresh_token: str | None,
    user_seq_no: str,
    scope: str,
    expires_in: int,
) -> dict[str, Any]:
    """Encrypt and safely store OAuth tokens on disk."""
    if not access_token or not user_seq_no:
        raise KftcStorageError("INVALID_TOKEN_PAYLOAD")

    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    expires_at = now_ts + int(expires_in)

    enc_access = encrypt_string(access_token)
    enc_refresh = encrypt_string(refresh_token) if refresh_token else None

    file_path = _get_user_kftc_file(username, "kftc_openbanking_token.json")

    # Read existing to preserve connected_at if refreshing
    connected_at = now.isoformat()
    if file_path.exists():
        try:
            old = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(old, dict) and old.get("connected_at"):
                connected_at = old["connected_at"]
        except Exception:
            pass

    payload = {
        "version": 1,
        "user_seq_no": str(user_seq_no).strip(),
        "scope": str(scope).strip(),
        "connected_at": connected_at,
        "refreshed_at": now.isoformat(),
        "expires_at": expires_at,
        "encrypted_access_token": enc_access,
        "encrypted_refresh_token": enc_refresh,
    }

    atomic_write_private_json(file_path, payload, indent=2)
    return payload


def load_user_token_status(username: str) -> dict[str, Any]:
    """Return non-sensitive token connection and validity metadata."""
    file_path = _get_user_kftc_file(username, "kftc_openbanking_token.json")
    if not file_path.exists():
        return {
            "connected": False,
            "status": "unconnected",
            "expires_at": None,
            "expires_in": None,
            "scope": [],
            "user_seq_no": None,
            "connected_at": None,
            "refreshed_at": None,
        }

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise KftcStorageError("TOKEN_STORE_CORRUPT") from exc

    if not isinstance(data, dict) or data.get("version") != 1:
        raise KftcStorageError("TOKEN_STORE_INVALID")

    now_ts = int(datetime.now(timezone.utc).timestamp())
    expires_at = data.get("expires_at", 0)
    expires_in = max(0, expires_at - now_ts)

    # Test decryptability to fail closed on secret key rotation
    try:
        decrypt_string(data["encrypted_access_token"])
    except KftcCryptoError:
        return {
            "connected": False,
            "status": "reauth_required",
            "expires_at": expires_at,
            "expires_in": 0,
            "scope": [s for s in data.get("scope", "").split() if s],
            "user_seq_no": None,
            "connected_at": data.get("connected_at"),
            "refreshed_at": data.get("refreshed_at"),
        }

    status = "valid"
    if expires_in <= 0:
        status = "expired"
    elif expires_in < 86400 * 7:  # less than 7 days
        status = "expiring_soon"

    return {
        "connected": True,
        "status": status,
        "expires_at": expires_at,
        "expires_in": expires_in,
        "scope": [s for s in data.get("scope", "").split() if s],
        "user_seq_no": data.get("user_seq_no"),
        "connected_at": data.get("connected_at"),
        "refreshed_at": data.get("refreshed_at"),
    }


def get_decrypted_user_tokens(username: str) -> dict[str, str | None]:
    """Retrieve and decrypt tokens for HTTP client use only. Never expose to API or log."""
    file_path = _get_user_kftc_file(username, "kftc_openbanking_token.json")
    if not file_path.exists():
        raise KftcStorageError("NOT_CONNECTED")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise KftcStorageError("TOKEN_STORE_CORRUPT") from exc

    if not isinstance(data, dict) or data.get("version") != 1:
        raise KftcStorageError("TOKEN_STORE_INVALID")

    try:
        access_token = decrypt_string(data["encrypted_access_token"])
        refresh_token = (
            decrypt_string(data["encrypted_refresh_token"])
            if data.get("encrypted_refresh_token")
            else None
        )
    except KftcCryptoError as exc:
        raise KftcStorageError("REAUTH_REQUIRED") from exc

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_seq_no": data.get("user_seq_no"),
        "scope": data.get("scope"),
    }


# ==============================================================================
# Accounts Mapping Storage
# ==============================================================================

def save_user_kftc_accounts(
    username: str,
    accounts: list[dict[str, Any]],
) -> None:
    """Save discovered KFTC accounts with protected fintech_use_num and stable local IDs."""
    file_path = _get_user_kftc_file(username, "kftc_openbanking_accounts.json")
    now_iso = datetime.now(timezone.utc).isoformat()

    records = []
    for acc in accounts:
        provider_account_id = acc["provider_account_id"]
        raw_fin_num = acc.get("fintech_use_num", "")
        enc_fin_num = (
            encrypt_string(raw_fin_num, context=ACCOUNT_CONTEXT)
            if raw_fin_num
            else ""
        )

        records.append({
            "version": 1,
            "provider_account_id": provider_account_id,
            "encrypted_fintech_use_num": enc_fin_num,
            "bank_code_std": acc.get("bank_code_std", ""),
            "bank_name": acc.get("bank_name", ""),
            "account_num_masked": acc.get("account_num_masked", ""),
            "account_alias": acc.get("account_alias", ""),
            "account_type": acc.get("account_type", ""),
            "product_name": acc.get("product_name", ""),
            "inquiry_agree_yn": acc.get("inquiry_agree_yn", "N"),
            "wealth_bank_account_id": acc.get("wealth_bank_account_id"),
            "owner": acc.get("owner"),
            "linked_at": acc.get("linked_at", now_iso),
            "last_refreshed_at": now_iso,
            "last_synced_at": acc.get("last_synced_at"),
        })

    payload = {
        "version": 1,
        "updated_at": now_iso,
        "accounts": records,
    }
    atomic_write_private_json(file_path, payload, indent=2)


def load_user_kftc_accounts(username: str) -> list[dict[str, Any]]:
    """Load safe representation of user accounts (without plaintext fintech_use_num)."""
    file_path = _get_user_kftc_file(username, "kftc_openbanking_accounts.json")
    if not file_path.exists():
        return []

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise KftcStorageError("ACCOUNT_STORE_CORRUPT") from exc

    if not isinstance(data, dict) or data.get("version") != 1:
        raise KftcStorageError("ACCOUNT_STORE_INVALID")

    raw_list = data.get("accounts", [])
    safe_list = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        safe_list.append({
            "provider_account_id": item.get("provider_account_id"),
            "bank_code_std": item.get("bank_code_std", ""),
            "bank_name": item.get("bank_name", ""),
            "account_num_masked": item.get("account_num_masked", ""),
            "account_alias": item.get("account_alias", ""),
            "account_type": item.get("account_type", ""),
            "product_name": item.get("product_name", ""),
            "inquiry_agree_yn": item.get("inquiry_agree_yn", "N"),
            "inquiry_available": item.get("inquiry_agree_yn") == "Y",
            "wealth_bank_account_id": item.get("wealth_bank_account_id"),
            "owner": item.get("owner"),
            "linked_at": item.get("linked_at"),
            "last_refreshed_at": item.get("last_refreshed_at"),
        })
    return safe_list


def resolve_fintech_use_num(username: str, provider_account_id: str) -> str:
    """Internal server-side helper to resolve protected fintech_use_num for Phase 2/3."""
    file_path = _get_user_kftc_file(username, "kftc_openbanking_accounts.json")
    if not file_path.exists():
        raise KftcStorageError("ACCOUNT_NOT_FOUND")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise KftcStorageError("ACCOUNT_STORE_CORRUPT") from exc

    target = next(
        (a for a in data.get("accounts", []) if a.get("provider_account_id") == provider_account_id),
        None,
    )
    if not target or not target.get("encrypted_fintech_use_num"):
        raise KftcStorageError("ACCOUNT_NOT_FOUND")

    try:
        return decrypt_string(target["encrypted_fintech_use_num"], context=ACCOUNT_CONTEXT)
    except KftcCryptoError as exc:
        raise KftcStorageError("FINTECH_NUM_DECRYPT_FAILED") from exc


# ==============================================================================
# Disconnect
# ==============================================================================

def disconnect_user_kftc(username: str) -> None:
    """Delete local connection tokens, OAuth temporary states, and discovery accounts."""
    for filename in (
        "kftc_openbanking_token.json",
        "kftc_openbanking_oauth_state.json",
        "kftc_openbanking_accounts.json",
    ):
        path = _get_user_kftc_file(username, filename)
        path.unlink(missing_ok=True)


# ==============================================================================
# Bank Transaction ID Sequence Storage (System-wide, day-scoped uniqueness)
# ==============================================================================

MAX_BASE36_9DIGIT = 36**9 - 1  # 101,559,956,668,415
_BASE36_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_BANK_TRAN_SEQ_LOCK = threading.Lock()


def int_to_base36_9(val: int) -> str:
    """Convert an integer to a zero-padded 9-character uppercase base-36 string."""
    if val < 0 or val > MAX_BASE36_9DIGIT:
        raise KftcStorageError(f"Sequence value {val} out of 9-digit base-36 bounds")
    if val == 0:
        return "000000000"
    digits = []
    n = val
    while n > 0:
        n, rem = divmod(n, 36)
        digits.append(_BASE36_CHARS[rem])
    res = "".join(reversed(digits))
    return res.zfill(9)


def get_bank_tran_sequence_file() -> Path:
    """Return absolute path to system-wide bank_tran_sequence storage."""
    root = os.getenv("WEALTH_DATA_DIR", "").strip()
    base_dir = Path(root) if root else (Path(__file__).resolve().parents[2] / "data")
    return base_dir / "system" / "kftc_bank_tran_sequence.json"


def next_bank_tran_sequence(client_use_code: str, date_str: str) -> int:
    """Acquire next strictly unique, monotonically increasing sequence number.

    Enforces:
    - client_use_code scope (isolated sequences per client_use_code).
    - date_str scope (reset sequence each calendar day YYYYMMDD).
    - Monotonically increasing counter with no wrap/truncation.
    - Day-scoped uniqueness guaranteed across restarts and processes.
    - Thread-level and cross-process file-locking (Windows msvcrt / POSIX flock).
    """
    code = str(client_use_code or "").strip().upper()
    if not code:
        raise KftcStorageError("CLIENT_USE_CODE_REQUIRED")
    if not date_str or len(date_str) != 8 or not date_str.isdigit():
        raise KftcStorageError("INVALID_DATE_FORMAT")

    seq_file = get_bank_tran_sequence_file()
    lock_file = seq_file.with_suffix(".lock")
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    with _BANK_TRAN_SEQ_LOCK:
        lock_handle = open(lock_file, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if lock_file.stat().st_size == 0:
                    lock_handle.write(b"0")
                    lock_handle.flush()
                lock_handle.seek(0)
                msvcrt.locking(lock_handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

            # Read existing sequence document
            doc: dict[str, Any] = {"version": 1, "entries": {}}
            if seq_file.exists():
                try:
                    loaded = json.loads(seq_file.read_text(encoding="utf-8"))
                except Exception as exc:
                    raise KftcStorageError("BANK_TRAN_SEQUENCE_STORE_CORRUPT") from exc

                if not isinstance(loaded, dict) or loaded.get("version") != 1 or not isinstance(loaded.get("entries"), dict):
                    raise KftcStorageError("BANK_TRAN_SEQUENCE_STORE_CORRUPT")
                doc = loaded

            entries = doc.setdefault("entries", {})
            entry = entries.get(code)
            if entry is None:
                # First time seeing this client_use_code
                current_seq = 1
            else:
                if not isinstance(entry, dict):
                    raise KftcStorageError("BANK_TRAN_SEQUENCE_STORE_CORRUPT")
                entry_date = entry.get("date")
                if not isinstance(entry_date, str) or len(entry_date) != 8 or not entry_date.isdigit():
                    raise KftcStorageError("BANK_TRAN_SEQUENCE_STORE_CORRUPT")

                raw_seq = entry.get("next_sequence")
                # Must be a strict integer, >= 1, not bool
                if isinstance(raw_seq, bool) or not isinstance(raw_seq, int) or raw_seq < 1:
                    raise KftcStorageError("BANK_TRAN_SEQUENCE_STORE_CORRUPT")

                if entry_date != date_str:
                    # New calendar day: reset sequence for this client_use_code
                    current_seq = 1
                else:
                    current_seq = raw_seq

            if current_seq > MAX_BASE36_9DIGIT:
                raise KftcStorageError(f"Sequence capacity exceeded for {code} on {date_str}")

            allocated_seq = current_seq
            entries[code] = {
                "date": date_str,
                "next_sequence": current_seq + 1,
            }

            atomic_write_private_json(seq_file, doc, indent=2)
            return allocated_seq
        finally:
            try:
                lock_handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                lock_handle.close()
            except Exception:
                pass
