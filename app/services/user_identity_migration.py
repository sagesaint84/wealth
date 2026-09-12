"""Explicit stable-user-ID migration utilities.

Nothing in this module selects a production path or invokes migration
automatically.  Production callers must provide both an explicit path and an
exact, privacy-safe preview precondition.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from app.services.user_identity import (
    LEGACY_MISSING_ID,
    VALID_ID,
    classify_user_id_state,
    generate_user_id,
    preview_user_id_migration,
    validate_user_id,
)


_PREVIEW_KEYS = frozenset(
    {
        "total_users",
        "legacy_missing_ids",
        "valid_ids",
        "invalid_ids",
        "duplicate_ids",
        "migration_required",
        "validation_ok",
        "write_ready",
    }
)
_COUNT_KEYS = frozenset(
    {
        "total_users",
        "legacy_missing_ids",
        "valid_ids",
        "invalid_ids",
        "duplicate_ids",
    }
)
_BOOL_KEYS = _PREVIEW_KEYS - _COUNT_KEYS


class UserIdMigrationError(ValueError):
    """Safe migration validation or precondition failure."""


def _validate_expected_preview(expected_preview: Mapping[str, object]) -> dict[str, int | bool]:
    if not isinstance(expected_preview, Mapping) or set(expected_preview) != _PREVIEW_KEYS:
        raise UserIdMigrationError("invalid user migration precondition")
    for key in _COUNT_KEYS:
        value = expected_preview[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise UserIdMigrationError("invalid user migration precondition")
    for key in _BOOL_KEYS:
        if not isinstance(expected_preview[key], bool):
            raise UserIdMigrationError("invalid user migration precondition")
    return dict(expected_preview)


def build_user_id_migration(
    records: Sequence[Mapping[str, object]],
    *,
    id_factory: Callable[[], str] = generate_user_id,
) -> tuple[list[dict[str, object]], dict[str, int | bool]]:
    """Build a migrated copy of legacy records after strict prevalidation."""
    pre_preview = preview_user_id_migration(records)
    if not pre_preview["write_ready"]:
        raise UserIdMigrationError("user migration is not write-ready")
    if any(not isinstance(record, dict) for record in records):
        raise UserIdMigrationError("invalid user migration input")

    migrated_records = deepcopy(list(records))
    known_ids = {
        validate_user_id(record["id"])
        for record in migrated_records
        if classify_user_id_state(record) == VALID_ID
    }
    migrated_users = 0
    for record in migrated_records:
        if classify_user_id_state(record) != LEGACY_MISSING_ID:
            continue
        try:
            generated_id = validate_user_id(id_factory())
        except Exception as exc:
            raise UserIdMigrationError("invalid generated stable user identity") from exc
        if generated_id in known_ids:
            raise UserIdMigrationError("duplicate generated stable user identity")
        record["id"] = generated_id
        known_ids.add(generated_id)
        migrated_users += 1

    post_preview = preview_user_id_migration(migrated_records)
    expected_post = {
        "total_users": pre_preview["total_users"],
        "legacy_missing_ids": 0,
        "valid_ids": pre_preview["total_users"],
        "invalid_ids": 0,
        "duplicate_ids": 0,
        "migration_required": False,
        "validation_ok": True,
        "write_ready": False,
    }
    if post_preview != expected_post:
        raise UserIdMigrationError("post-migration user identity validation failed")
    return migrated_records, {
        "total_users": pre_preview["total_users"],
        "migrated_users": migrated_users,
        "preserved_valid_ids": pre_preview["valid_ids"],
        "post_validation_ok": True,
    }


def _read_migration_root(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = handle.read()
        root = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UserIdMigrationError("user migration file unavailable") from exc
    if not isinstance(root, dict) or "users" not in root or not isinstance(root["users"], list):
        raise UserIdMigrationError("invalid user migration file")
    return root


def _atomic_write_json(path: Path, root: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(root, ensure_ascii=False, indent=2).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise UserIdMigrationError("user migration serialization failed") from exc

    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
        ) as handle:
            temp_path = handle.name
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        raise UserIdMigrationError("user migration atomic write failed") from exc
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def execute_user_id_migration_file(
    path: str | Path,
    *,
    expected_preview: Mapping[str, object],
) -> dict[str, int | bool]:
    """Explicitly migrate one users JSON file using an exact preview guard."""
    expected = _validate_expected_preview(expected_preview)
    target = Path(path)
    root = _read_migration_root(target)
    current_preview = preview_user_id_migration(root["users"])
    if current_preview != expected:
        raise UserIdMigrationError("user migration precondition changed")

    if not current_preview["migration_required"]:
        return {
            "total_users": current_preview["total_users"],
            "migrated_users": 0,
            "preserved_valid_ids": current_preview["valid_ids"],
            "write_performed": False,
            "post_validation_ok": current_preview["validation_ok"],
            "precondition_match": True,
        }

    migrated_users, summary = build_user_id_migration(root["users"])
    migrated_root = deepcopy(root)
    migrated_root["users"] = migrated_users
    _atomic_write_json(target, migrated_root)
    return {
        **summary,
        "write_performed": True,
        "post_validation_ok": True,
        "precondition_match": True,
    }
