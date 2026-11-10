"""Deterministic, domain-scoped identities for legacy financial file imports."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import json
import math
import unicodedata
from typing import Any, Callable, Iterable


FILE_IMPORT_FINGERPRINT_FIELD = "file_import_fingerprint"
FILE_IMPORT_OCCURRENCE_FIELD = "file_import_occurrence"


def strip_import_text(val: Any) -> str:
    """Trim file input text while preserving internal whitespace and Unicode."""
    if val is None:
        return ""
    return str(val).strip()


def map_import_columns(
    header: Iterable[Any], rows: Iterable[Iterable[Any]]
) -> list[dict[str, Any]]:
    """Map already decoded and selected rows using trimmed column names."""
    headers = [strip_import_text(value) for value in header]
    return [
        {name: value for name, value in zip(headers, row) if name}
        for row in rows
    ]


def read_csv_import_rows(content: bytes) -> list[dict[str, Any]]:
    """Decode legacy CSV uploads and return selected rows with trimmed headers."""
    text = ""
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = content.decode(encoding)
            break
        except Exception:
            continue

    reader = csv.DictReader(io.StringIO(text))
    return [
        {strip_import_text(key): value for key, value in row.items() if key}
        for row in reader
        if any(row.values())
    ]


def canonical_text(value: Any) -> str:
    """Normalize user/provider text without erasing meaningful content."""
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value)).strip()
    return " ".join(normalized.split())


def canonical_number(value: Any) -> str:
    """Return one stable finite decimal spelling; keep missing distinct from zero."""
    if value is None or value == "":
        return "<missing>"
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("file import identity contains a non-finite number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("file import identity contains an invalid number") from exc
    if not number.is_finite():
        raise ValueError("file import identity contains a non-finite number")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def build_file_import_fingerprint(domain: str, identity: dict[str, Any]) -> str:
    """Hash a stable, domain-versioned canonical economic-event representation."""
    payload = json.dumps(
        {"domain": domain, "version": 1, "identity": identity},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"file-import:{domain}:v1:{hashlib.sha256(payload).hexdigest()}"


def retain_new_occurrences(
    candidates: list[dict[str, Any]],
    existing_records: list[dict[str, Any]],
    fingerprint_for_record: Callable[[dict[str, Any]], str | None],
) -> tuple[list[dict[str, Any]], int]:
    """Apply multiset idempotency while retaining legitimate identical occurrences."""
    existing_counts: Counter[str] = Counter()
    for record in existing_records:
        fingerprint = fingerprint_for_record(record)
        if fingerprint:
            existing_counts[fingerprint] += 1

    incoming_counts: Counter[str] = Counter()
    retained: list[dict[str, Any]] = []
    skipped = 0
    for record in candidates:
        fingerprint = fingerprint_for_record(record)
        if not fingerprint:
            raise ValueError("file import candidate has no stable identity")
        incoming_counts[fingerprint] += 1
        occurrence = incoming_counts[fingerprint]
        if occurrence <= existing_counts[fingerprint]:
            skipped += 1
            continue
        record[FILE_IMPORT_FINGERPRINT_FIELD] = fingerprint
        record[FILE_IMPORT_OCCURRENCE_FIELD] = occurrence
        retained.append(record)
    return retained, skipped
