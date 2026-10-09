"""Persist account-read execution metadata; financial snapshots belong to close."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from app.services.automation.execution_state import KST, execution_state_lock
from app.services.secure_files import atomic_write_private_json
from app.services.user_manager import get_user_by_name

PROVIDERS = {"KB증권": "kb", "토스증권": "toss", "NH투자증권(나무)": "nh",
             "한국투자증권": "kis", "키움증권": "kiwoom"}
SUCCESS_STATUSES = {"SUCCESS", "CONFIRMED_EMPTY", "PARTIAL_SUCCESS"}
RESULT_STATUSES = SUCCESS_STATUSES | {"API_ERROR", "CONFIG_REQUIRED", "PARSE_ERROR",
                                    "SCOPE_UNVERIFIED", "PERSISTENCE_ERROR", "INTERNAL_ERROR", "TEST_MODE"}
FRESHNESS = timedelta(minutes=15)


def as_kst(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime is required")
    return value.astimezone(KST)


def metadata_path(username: str, path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    root = Path(os.getenv("WEALTH_DATA_DIR", "").strip() or "data")
    # A stored username never becomes a filesystem path component.
    name = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return root / "automation" / "account_pre_sync" / f"{name}.json"


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("PRE_SYNC_METADATA_INVALID")
    return data


def _timestamp(value: str) -> datetime:
    return as_kst(datetime.fromisoformat(value))


def _category(result: dict) -> str | None:
    status = result["status"]
    if status in SUCCESS_STATUSES - {"PARTIAL_SUCCESS"}:
        return None
    if status == "CONFIG_REQUIRED" or result.get("failure_reason", "").endswith(("_HTTP_401", "_HTTP_403")):
        return "CONFIG_ERROR"
    if status == "PERSISTENCE_ERROR":
        return "PERSISTENCE_ERROR"
    if status in {"API_ERROR", "PARTIAL_SUCCESS"} and result.get("retryable") is True:
        return "TRANSIENT_ERROR"
    return "VALIDATION_ERROR"


def _safe_reasons(provider: str) -> set[str]:
    prefix = provider.upper()
    return ({f"{prefix}_HTTP_{code}" for code in (400, 401, 403, 429, 500, 501, 502, 503, 504)}
            | {f"{prefix}_TRANSPORT_ERROR", f"{prefix}_RESPONSE_INVALID",
               f"{prefix}_PROVIDER_OR_RESPONSE_ERROR", "ACCOUNT_SYNC_PERSISTENCE_FAILED"})


def _provider_metadata(result: dict, started: datetime, completed: datetime) -> dict:
    status = result.get("status")
    if status not in RESULT_STATUSES:
        status = "INTERNAL_ERROR"
    success = status in SUCCESS_STATUSES and result.get("holdings_valid") is True
    item = {"provider": PROVIDERS[result["broker"]], "status": status,
            "started_at": as_kst(started).isoformat(), "completed_at": as_kst(completed).isoformat(),
            "success": success, "authoritative_empty": success and status == "CONFIRMED_EMPTY",
            "usable_for_close": success, "cash_valid": result.get("cash_valid") is True,
            "data_preserved": result.get("data_preserved") is True,
            "retry_attempted": result.get("retry_attempted") is True,
            "retry_recovered": success and status != "PARTIAL_SUCCESS" and result.get("retry_recovered") is True,
            "retryable": result.get("retryable") is True}
    # Persist bounded codes only, never result messages, account numbers or bodies.
    reason = result.get("failure_reason", "")
    if reason in _safe_reasons(item["provider"]):
        item["failure_reason"] = reason
    item["error_category"] = _category(item)
    return item


async def run_account_pre_sync_for_user(username: str, *, now: datetime | None = None,
                                        path: Path | None = None, clock=None) -> dict:
    """Call canonical sync once; retries stay inside its read-only fetch boundary."""
    username = (username or "").strip()
    if not username or not get_user_by_name(username):
        raise ValueError("USER_NOT_REGISTERED")
    if now is not None:
        as_kst(now)
    clock = clock or (lambda: datetime.now(KST))
    started = as_kst(clock())
    target = metadata_path(username, path)
    run_id = uuid.uuid4().hex
    state = {"schema_version": 1, "username": username, "run_id": run_id,
             "started_at": started.isoformat(), "completed_at": None,
             "status": "RUNNING", "providers": {}}
    with execution_state_lock(target):
        previous = _read(target)
        if previous.get("status") == "RUNNING":
            age = started - _timestamp(previous["started_at"])
            if age < FRESHNESS:
                return {"ok": False, "status": "failed", "error": "ACCOUNT_PRE_SYNC_ALREADY_RUNNING"}
        atomic_write_private_json(target, state)

    def save():
        with execution_state_lock(target):
            current = _read(target)
            if current.get("run_id") != run_id:
                raise RuntimeError("ACCOUNT_PRE_SYNC_SUPERSEDED")
            atomic_write_private_json(target, state)

    def observe(result, provider_started, provider_completed):
        item = _provider_metadata(result, provider_started, provider_completed)
        state["providers"][item["provider"]] = item
        save()

    try:
        from app.main import sync_all_accounts_for_user
        await sync_all_accounts_for_user(username, retry_account_transient=True,
                                         provider_observer=observe, sync_clock=clock)
    except Exception as exc:
        # Invalidate the entire run on orchestration/metadata failure. No raw exception persists.
        state["status"] = "FAILED"
        state["error_category"] = "PERSISTENCE_ERROR" if isinstance(exc, OSError) else "VALIDATION_ERROR"
        state["completed_at"] = as_kst(clock()).isoformat()
        save()
        return {"ok": False, "status": "failed", "error": "ACCOUNT_PRE_SYNC_FAILED"}
    state["status"] = "COMPLETED"
    state["completed_at"] = as_kst(clock()).isoformat()
    save()
    # Provider failures are completed executions, not a scheduler retry at close time.
    return {"ok": True, "status": "completed", "providers": state["providers"],
            "completed_at": state["completed_at"]}


def read_pre_sync_for_close(username: str, *, now: datetime, path: Path | None = None) -> dict:
    """Read metadata only. Missing/corrupt/stale state never triggers provider fetches."""
    current = as_kst(now)
    try:
        state = _read(metadata_path(username, path))
        if state and state.get("username") != username:
            raise ValueError("PRE_SYNC_METADATA_INVALID")
        providers = state.get("providers", {})
        if not isinstance(providers, dict):
            raise ValueError("PRE_SYNC_METADATA_INVALID")
        invalid = False
    except (OSError, ValueError, TypeError):
        state, providers, invalid = {}, {}, True
    brokers = []
    for label, provider in PROVIDERS.items():
        item = providers.get(provider)
        status = "PRE_SYNC_INVALID" if invalid else "PRE_SYNC_MISSING"
        fresh = usable = False
        metadata_valid = False
        if state.get("status") == "RUNNING":
            status = "PRE_SYNC_RUNNING"
        elif state.get("status") == "FAILED":
            status = "PRE_SYNC_FAILED"
        elif item is not None:
            try:
                if not isinstance(item, dict) or state.get("status") != "COMPLETED":
                    raise ValueError("PRE_SYNC_METADATA_INVALID")
                completed = _timestamp(item["completed_at"])
                started = _timestamp(item["started_at"])
                run_started = _timestamp(state["started_at"])
                run_completed = _timestamp(state["completed_at"])
                if not run_started <= started <= completed <= run_completed:
                    raise ValueError("PRE_SYNC_METADATA_INVALID")
                if item["provider"] != provider or item["status"] not in RESULT_STATUSES:
                    raise ValueError("PRE_SYNC_METADATA_INVALID")
                flags = ("success", "authoritative_empty", "usable_for_close", "cash_valid",
                         "data_preserved", "retry_attempted", "retry_recovered", "retryable")
                if any(type(item.get(key)) is not bool for key in flags):
                    raise ValueError("PRE_SYNC_METADATA_INVALID")
                successful = item["status"] in SUCCESS_STATUSES
                if (item["success"] != successful or item["usable_for_close"] != successful
                        or item["authoritative_empty"] != (item["status"] == "CONFIRMED_EMPTY")):
                    raise ValueError("PRE_SYNC_METADATA_INVALID")
                if item.get("error_category") not in {None, "TRANSIENT_ERROR", "CONFIG_ERROR",
                                                      "VALIDATION_ERROR", "PERSISTENCE_ERROR"}:
                    raise ValueError("PRE_SYNC_METADATA_INVALID")
                if "failure_reason" in item and (not isinstance(item["failure_reason"], str)
                                                  or item["failure_reason"] not in _safe_reasons(provider)):
                    raise ValueError("PRE_SYNC_METADATA_INVALID")
                metadata_valid = True
                age = current - completed
                fresh = timedelta(0) <= age <= FRESHNESS
                usable = fresh and successful
                if not fresh:
                    status = "PRE_SYNC_STALE" if age > FRESHNESS else "PRE_SYNC_INVALID"
                else:
                    status = item["status"]
            except (ValueError, TypeError, KeyError):
                status = "PRE_SYNC_INVALID"
                fresh = usable = False
        row = {"broker": label, "provider": provider, "status": status,
               "source": "account_pre_sync", "fresh": fresh, "usable_for_close": usable,
               "authoritative_empty": usable and status == "CONFIRMED_EMPTY",
               "data_preserved": not usable, "message": "계좌 사전 동기화 상태"}
        if metadata_valid and status != "PRE_SYNC_INVALID":
            # Only allowlisted fields can cross the close boundary.
            for key in ("completed_at", "error_category", "retry_attempted", "retry_recovered", "cash_valid"):
                row[key] = item.get(key)
            if item.get("failure_reason") in _safe_reasons(provider):
                row["failure_reason"] = item["failure_reason"]
        brokers.append(row)
    degraded = any(r["status"] not in SUCCESS_STATUSES | {"CONFIG_REQUIRED"}
                   or r["status"] == "PARTIAL_SUCCESS" for r in brokers)
    return {"source": "account_pre_sync", "degraded": degraded, "brokers": brokers}
