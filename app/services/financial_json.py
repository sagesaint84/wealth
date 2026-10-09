"""Canonical financial JSON: path-scoped transactions and atomic replacement."""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from functools import wraps
from inspect import signature
from importlib import import_module
from pathlib import Path

from app.services.secure_files import atomic_write_private_json
from app.services.test_safety import assert_write_allowed


class FinancialStorageError(RuntimeError):
    """Financial storage is unavailable or structurally corrupt; never bootstrap it."""


_LOCKS: dict[str, threading.RLock] = {}
_GUARD = threading.Lock()
_LOCAL = threading.local()
FINANCIAL_FILENAMES = (
    "portfolio.json", "asset_records.json", "ledger.json",
    "dividend_records.json", "realized_pnl_records.json",
    "dividend_forecast_snapshots.json",
)


def canonical_path(path: Path) -> Path:
    return Path(os.path.normcase(str(Path(path).resolve())))


@contextmanager
def financial_lock(path: Path, *, timeout: float = 5.0):
    """Hold the same reentrant thread and advisory lock for a canonical path.

    Use across read/validate/modify/write, never across an async suspension.
    Sidecar locks persist: unlinking one could split the cross-process domain.
    """
    target = canonical_path(path)
    key = str(target)
    with _GUARD:
        lock = _LOCKS.setdefault(key, threading.RLock())
    if not lock.acquire(timeout=timeout):
        raise FinancialStorageError("FINANCIAL_STORAGE_BUSY")
    held = getattr(_LOCAL, "held", None)
    if held is None:
        held = _LOCAL.held = {}
    handle = None
    acquired = False
    try:
        if key in held:
            held[key] += 1
        else:
            assert_write_allowed(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            sidecar = target.with_name(f".{target.name}.lock")
            handle = sidecar.open("a+b")
            if os.name == "nt":
                if sidecar.stat().st_size == 0:
                    handle.write(b"0")
                    handle.flush()
            deadline = time.monotonic() + timeout
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise FinancialStorageError("FINANCIAL_STORAGE_BUSY") from exc
                    time.sleep(0.02)
            held[key] = 1
        yield
    finally:
        if key in held:
            held[key] -= 1
            if held[key] == 0:
                del held[key]
        try:
            if acquired:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            try:
                if handle is not None:
                    handle.close()
            finally:
                lock.release()


@contextmanager
def financial_locks(paths):
    """Acquire coordinated targets in canonical lexical order before any read."""
    with ExitStack() as stack:
        for path in sorted({canonical_path(path) for path in paths}, key=str):
            stack.enter_context(financial_lock(path))
        yield


@contextmanager
def financial_user_locks(username: str | None, *filenames: str):
    """Resolve each target through its owning service, including storage overrides."""
    getters = {
        "portfolio.json": ("portfolio", "_get_portfolio_file"),
        "asset_records.json": ("asset_records", "_get_records_file"),
        "ledger.json": ("ledger", "get_ledger_path"),
        "dividend_records.json": ("dividend_records", "_get_dividend_file"),
        "realized_pnl_records.json": ("pnl_records", "_get_pnl_file"),
        "dividend_forecast_snapshots.json": ("dividend_forecast_snapshots", "_get_snapshot_file"),
    }
    paths = []
    for filename in filenames:
        module, getter = getters[filename]
        paths.append(getattr(import_module(f"app.services.{module}"), getter)(username))
    with financial_locks(paths):
        yield


def financial_rmw(*filenames: str):
    """Protect a synchronous user service's entire read-modify-write operation."""
    def decorate(function):
        sig = signature(function)

        @wraps(function)
        def locked(*args, **kwargs):
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            with financial_user_locks(bound.arguments.get("username"), *filenames):
                return function(*args, **kwargs)
        return locked
    return decorate


def validate_financial_json(path: Path, value) -> None:
    """Validate storage containers without changing records or financial formulas."""
    name = Path(path).name
    valid = isinstance(value, dict)
    if name == "portfolio.json" and valid:
        valid = isinstance(value.get("settings", {}), dict)
        for field in ("accounts", "holdings", "bank_accounts", "savings_accounts",
                      "insurance_accounts", "loan_accounts", "real_estates"):
            items = value.get(field, [])
            valid = valid and isinstance(items, list) and all(isinstance(x, dict) for x in items)
        settings = value.get("settings", {})
        if not isinstance(settings, dict):
            raise FinancialStorageError("FINANCIAL_STORAGE_INVALID")
        for field in ("fx_rates", "fx_info", "daily_snapshot", "cash_balances", "wealth_planning", "ipo"):
            valid = valid and isinstance(settings.get(field, {}), dict)
        planning = settings.get("wealth_planning", {})
        if isinstance(planning, dict) and "history" in planning:
            history = planning["history"]
            valid = valid and isinstance(history, list) and all(isinstance(x, dict) for x in history)
        ipo = settings.get("ipo", {})
        if isinstance(ipo, dict) and "applications" in ipo:
            apps = ipo["applications"]
            valid = valid and isinstance(apps, dict) and all(isinstance(x, dict) for x in apps.values())
    elif name in ("asset_records.json", "realized_pnl_records.json"):
        # Legacy stock history lists and the old new-user empty P/L template.
        records = value if isinstance(value, list) else value.get("records") if valid else None
        valid = isinstance(records, list) and all(isinstance(x, dict) for x in records)
        if name == "realized_pnl_records.json" and isinstance(value, list):
            valid = value == []
    elif name == "dividend_records.json" and valid:
        valid = "records" in value or {"estimated", "actual"}.issubset(value)
        for field in ("records", "estimated", "actual"):
            if field in value:
                valid = valid and isinstance(value[field], list) and all(isinstance(x, dict) for x in value[field])
    elif name == "ledger.json" and valid:
        for field in ("transactions", "recurring", "cards"):
            items = value.get(field, [])
            valid = valid and isinstance(items, list) and all(isinstance(x, dict) for x in items)
        valid = valid and isinstance(value.get("categories", {}), dict) and isinstance(value.get("budgets", {}), dict)
    elif name == "dividend_forecast_snapshots.json" and valid:
        valid = value.get("schema_version") == 1 and isinstance(value.get("snapshots"), list)
        valid = valid and all(isinstance(x, dict) for x in value.get("snapshots", []))
    if not valid:
        raise FinancialStorageError("FINANCIAL_STORAGE_INVALID")


def read_financial_json(path: Path, *, default=None):
    """Read old or new complete JSON; only a missing file accepts a default."""
    path = canonical_path(path)
    def invalid_constant(_value):
        raise ValueError("Non-finite JSON constant")
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream, parse_constant=invalid_constant)
    except FileNotFoundError:
        if default is not None:
            return deepcopy(default)
        raise FinancialStorageError("FINANCIAL_STORAGE_MISSING") from None
    except (OSError, UnicodeError, ValueError) as exc:
        raise FinancialStorageError("FINANCIAL_STORAGE_UNREADABLE") from exc
    validate_financial_json(path, value)
    return value


def write_financial_json(path: Path, value) -> None:
    """Replace complete JSON under the shared lock; refuse to overwrite corruption.

    The existing private writer supplies unique same-directory temp, flush/fsync,
    atomic replace and restrictive permissions. Callers hold the full RMW lock.
    """
    path = canonical_path(path)
    with financial_lock(path):
        assert_write_allowed(path)
        if path.exists():
            read_financial_json(path)
        validate_financial_json(path, value)
        atomic_write_private_json(path, value, indent=2)


def ensure_financial_json(path: Path, initial) -> Path:
    """Bootstrap a missing file only, with the check inside the writer domain."""
    path = Path(path)
    if not path.exists():
        with financial_lock(path):
            if not path.exists():
                write_financial_json(path, initial)
    return path
