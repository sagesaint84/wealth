"""Restore general backup stores together, with rollback on a failed write."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Any

from app.services.settings import settings_lock
from app.services.financial_json import financial_locks, read_financial_json
from app.services.secure_files import atomic_write_private_bytes
from app.services.test_safety import assert_write_allowed
from app.services.user_manager import get_user_data_dir


# Match the existing bounded official-file upload policy.
MAX_BACKUP_UPLOAD_BYTES = 16 * 1024 * 1024


def _file_digest(path: Path) -> bytes | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.digest()


def restore_general_data(username: str, bundle: dict[str, Any]) -> list[str]:
    from app.services.portfolio import write_portfolio
    from app.services.asset_records import write_asset_records
    from app.services.dividend_records import write_dividend_records
    from app.services.pnl_records import write_pnl_records
    from app.services.ledger import write_ledger, DEFAULT_CATEGORIES

    user_dir = get_user_data_dir(username)
    targets: list[tuple[str, Any, Any, str]] = []
    if bundle.get("portfolio"):
        targets.append(("portfolio.json", bundle["portfolio"], lambda value: write_portfolio(value, username=username, replace_planning=True), "포트폴리오"))
    if bundle.get("asset_records"):
        targets.append(("asset_records.json", bundle["asset_records"], lambda value: write_asset_records(value, username=username), "자산기록"))
    if bundle.get("dividend_records"):
        targets.append(("dividend_records.json", bundle["dividend_records"], lambda value: write_dividend_records(value, username=username), "배당내역"))
    if bundle.get("realized_pnl_records"):
        targets.append(("realized_pnl_records.json", bundle["realized_pnl_records"], lambda value: write_pnl_records(value, username=username), "매도실현손익"))
    if isinstance(bundle.get("ledger"), dict):
        ledger = dict(bundle["ledger"])
        ledger.setdefault("version", "1.0")
        ledger.setdefault("categories", DEFAULT_CATEGORIES)
        ledger.setdefault("transactions", [])
        ledger.setdefault("recurring", [])
        ledger.setdefault("cards", [])
        ledger.setdefault("budgets", {})
        targets.append(("ledger.json", ledger, lambda value: write_ledger(value, username=username), "가계부"))

    # Restore and rollback hold the same sorted domains as normal financial writers.
    with settings_lock(user_dir / ".backup-restore"), financial_locks(
        user_dir / filename for filename, _, _, _ in targets
    ):
        with tempfile.TemporaryDirectory(prefix=".backup-restore-", dir=user_dir) as temporary:
            snapshots: dict[Path, Path | None] = {}
            for filename, _, _, _ in targets:
                destination = user_dir / filename
                assert_write_allowed(destination)
                snapshot = Path(temporary) / filename
                if destination.exists():
                    read_financial_json(destination)
                    shutil.copy2(destination, snapshot)
                    snapshots[destination] = snapshot
                else:
                    snapshots[destination] = None

            attempted: list[Path] = []
            completed: dict[Path, bytes | None] = {}
            try:
                for filename, value, writer, _ in targets:
                    destination = user_dir / filename
                    attempted.append(destination)
                    writer(value)
                    completed[destination] = _file_digest(destination)
            except Exception as original_error:
                rollback_errors = []
                concurrent_changes = []
                for destination in attempted:
                    snapshot = snapshots[destination]
                    try:
                        # A normal writer can update a completed restore target
                        # without taking this lock. Never replace that newer state.
                        if destination in completed and _file_digest(destination) != completed[destination]:
                            concurrent_changes.append(destination.name)
                            continue
                        if snapshot is None:
                            destination.unlink(missing_ok=True)
                        else:
                            atomic_write_private_bytes(destination, snapshot.read_bytes())
                    except OSError as exc:
                        rollback_errors.append(exc)
                if rollback_errors:
                    error = RuntimeError("BACKUP_RESTORE_ROLLBACK_FAILED")
                    error.add_note(f"Rollback error: {type(rollback_errors[0]).__name__}")
                    raise error from original_error
                if concurrent_changes:
                    error = RuntimeError("BACKUP_RESTORE_CONCURRENT_WRITE_CONFLICT")
                    error.add_note(f"Preserved newer writes: {', '.join(concurrent_changes)}")
                    raise error from original_error
                raise

    return [label for _, _, _, label in targets]
