from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from time import perf_counter

from app.services.ipo import orchestrator as _base
from app.services.ipo.source_discovery import discover_and_merge_primary_sources

KST = timezone(timedelta(hours=9))


def _target_date(target_date_str: str | None) -> str:
    return target_date_str or datetime.now(KST).strftime("%Y-%m-%d")


def _refresh_npay_only(*, username: str | None, target_date_str: str | None) -> dict[str, Any]:
    """Run the single-provider schedule refresh under the existing process lock."""
    resolved_target = _target_date(target_date_str)
    started = perf_counter()
    try:
        with _base._refresh_file_lock():
            result = discover_and_merge_primary_sources(
                username=username,
                target_date_str=resolved_target,
            )
    except _base.IpoRefreshAlreadyRunning:
        raise

    statuses = result.get("statuses") if isinstance(result.get("statuses"), dict) else {}
    npay_status = str(statuses.get("npay") or "")
    successful = npay_status.startswith("sync_ok")
    output = {
        "status": "ok" if successful and result.get("failed", 0) == 0 else (
            "partial" if successful else "preserved"
        ),
        "mode": "npay_only",
        "target_date": resolved_target,
        "sources": statuses,
        "total_ipos": result.get("total_ipos", 0),
        "npay": {
            "status": npay_status or "source_error (missing_status)",
            "relevant": result.get("relevant", 0),
            "review_required": result.get("review_required", 0),
            "failed": result.get("failed", 0),
            "observed_at": result.get("npay_observed_at"),
        },
        "timings": dict(result.get("timings") or {}),
    }
    output["timings"]["total_ms"] = round((perf_counter() - started) * 1000, 3)
    return output


def refresh_ipo_market(*, username: str | None = None, target_date_str: str | None = None) -> dict[str, Any]:
    """Interactive manual refresh using Npay only; retained market data survives failures."""
    return _refresh_npay_only(username=username, target_date_str=target_date_str)


def refresh_ipo_market_enriched(
    *, username: str | None = None, target_date_str: str | None = None
) -> dict[str, Any]:
    """Scheduled refresh uses the same Npay-only path and does not recalculate legacy scores."""
    return _refresh_npay_only(username=username, target_date_str=target_date_str)
