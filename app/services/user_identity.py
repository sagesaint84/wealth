"""Pure stable-user-ID helpers.

This module deliberately has no user-storage, authentication, or migration
dependencies.  Callers decide when an ID may be generated and persisted.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import uuid


LEGACY_MISSING_ID = "LEGACY_MISSING_ID"
VALID_ID = "VALID_ID"
INVALID_ID = "INVALID_ID"


def generate_user_id() -> str:
    """Return a fresh canonical UUID4 stable user identifier."""
    return str(uuid.uuid4())


def validate_user_id(value: object) -> str:
    """Return *value* when it is a canonical lowercase UUID4 string.

    Persisted identity values are intentionally not normalized.  Accepting one
    representation prevents equivalent spellings from entering the schema.
    """
    if not isinstance(value, str):
        raise ValueError("user id must be a canonical UUID4 string")

    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("user id must be a canonical UUID4 string") from exc

    if (
        value != str(parsed)
        or parsed.version != 4
        or parsed.variant != uuid.RFC_4122
    ):
        raise ValueError("user id must be a canonical UUID4 string")
    return value


def classify_user_id_state(user_record: Mapping[str, object]) -> str:
    """Classify only the stable-ID field without changing *user_record*."""
    if "id" not in user_record:
        return LEGACY_MISSING_ID
    try:
        validate_user_id(user_record["id"])
    except ValueError:
        return INVALID_ID
    return VALID_ID


def find_duplicate_user_ids(records: Iterable[Mapping[str, object]]) -> frozenset[str]:
    """Return valid canonical IDs occurring more than once, without mutation."""
    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        if classify_user_id_state(record) != VALID_ID:
            continue
        user_id = validate_user_id(record["id"])
        if user_id in seen:
            duplicates.add(user_id)
        else:
            seen.add(user_id)
    return frozenset(duplicates)


def inspect_user_id_states(records: Iterable[Mapping[str, object]]) -> dict[str, int]:
    """Return privacy-safe stable-ID state counts for in-memory records."""
    materialized = list(records)
    states = {
        "legacy_missing_ids": 0,
        "valid_ids": 0,
        "invalid_ids": 0,
        "duplicate_ids": 0,
    }
    for record in materialized:
        state = classify_user_id_state(record)
        if state == LEGACY_MISSING_ID:
            states["legacy_missing_ids"] += 1
        elif state == VALID_ID:
            states["valid_ids"] += 1
        else:
            states["invalid_ids"] += 1
    states["duplicate_ids"] = len(find_duplicate_user_ids(materialized))
    return states


def preview_user_id_migration(records: Sequence[Mapping[str, object]]) -> dict[str, int | bool]:
    """Return deterministic, privacy-safe stable-ID migration readiness counts.

    This is an inspection only: it never generates IDs, changes records, or
    produces a write payload.
    """
    if isinstance(records, (str, bytes, bytearray, Mapping)) or not isinstance(records, Sequence):
        raise ValueError("invalid user migration preview input")
    if any(not isinstance(record, Mapping) for record in records):
        raise ValueError("invalid user migration preview input")

    states = inspect_user_id_states(records)
    validation_ok = states["invalid_ids"] == 0 and states["duplicate_ids"] == 0
    migration_required = states["legacy_missing_ids"] > 0
    return {
        "total_users": len(records),
        **states,
        "migration_required": migration_required,
        "validation_ok": validation_ok,
        "write_ready": validation_ok and migration_required,
    }
