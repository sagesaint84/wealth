from __future__ import annotations

import re
from datetime import date


_OFFICIAL_SOURCES = {"opendart", "kind"}
_CODE_PATTERN = re.compile(r"^[A-Z0-9._-]{1,24}$")
_KRX_SHORT_CODE_PATTERN = re.compile(r"^[0-9][A-Z0-9]{5}$")
_EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def normalize_dividend_code(value: object) -> str | None:
    code = str(value or "").strip().upper()
    if (
        len(code) == 7
        and code.startswith("A")
        and _KRX_SHORT_CODE_PATTERN.fullmatch(code[1:]) is not None
    ):
        code = code[1:]
    if not code or _CODE_PATTERN.fullmatch(code) is None:
        return None
    return code


def _iso_date(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return None


def build_dividend_event_identity(
    *,
    code: object,
    record_date: object = None,
    source: object = None,
    source_event_id: object = None,
) -> str | None:
    """Build a stable identity only from structured official event evidence."""
    normalized_code = normalize_dividend_code(code)
    if normalized_code is None:
        return None

    normalized_record_date = _iso_date(record_date)
    if normalized_record_date is not None:
        return f"dividend:v1:{normalized_code}:record:{normalized_record_date}"

    normalized_source = str(source or "").strip().lower()
    event_id = str(source_event_id or "").strip()
    if (
        normalized_source not in _OFFICIAL_SOURCES
        or _EVENT_ID_PATTERN.fullmatch(event_id) is None
    ):
        return None
    return (
        f"dividend:v1:{normalized_source}:{normalized_code}:receipt:{event_id}"
    )
