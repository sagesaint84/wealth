"""Pure helpers for protecting IPO allocation links from P/L ledger deletion."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def linked_pnl_reference_counts(portfolio_data: dict[str, Any]) -> dict[str, int]:
    """Return reference counts for every P/L record linked by an IPO allocation.

    This deliberately treats malformed links conservatively: a non-empty record
    id still reserves the P/L record until an explicit unlink resolves it.
    """
    counts: dict[str, int] = {}
    applications = (((portfolio_data.get("settings") or {}).get("ipo") or {}).get("applications") or {})
    if not isinstance(applications, dict):
        return counts
    for application in applications.values():
        applicants = application.get("applicants") if isinstance(application, dict) else None
        if not isinstance(applicants, dict):
            continue
        for applicant in applicants.values():
            allocation = applicant.get("allocation") if isinstance(applicant, dict) else None
            links = allocation.get("links") if isinstance(allocation, dict) else None
            if not isinstance(links, list):
                continue
            for link in links:
                record_id = str(link.get("pnl_record_id") or "").strip() if isinstance(link, dict) else ""
                if record_id:
                    counts[record_id] = counts.get(record_id, 0) + 1
    return counts


def linked_pnl_reference_counts_from_file(path: Path) -> dict[str, int]:
    """Read the portfolio snapshot without creating or changing any storage."""
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        # A malformed portfolio must not be used to approve a financial delete.
        raise RuntimeError("IPO_LINK_GUARD_UNAVAILABLE")
    if not isinstance(value, dict):
        raise RuntimeError("IPO_LINK_GUARD_UNAVAILABLE")
    return linked_pnl_reference_counts(value)
