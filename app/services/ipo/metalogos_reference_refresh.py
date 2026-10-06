from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.ipo.identity import normalize_company_name
from app.services.ipo.metalogos_client import MetalogosIpoClient, metalogos_identity_matches
from app.services.ipo.source_discovery import _month_window, _relevant_schedule
from app.services.ipo.store import read_market_store, write_market_store
from app.services.network_policy import ExternalNetworkDisabled


KST = timezone(timedelta(hours=9))
_DEFAULT_SCAN_LIMIT = 40


def refresh_missing_metalogos_references(
    *,
    target_date_str: str,
    client: MetalogosIpoClient | None = None,
    max_items: int = _DEFAULT_SCAN_LIMIT,
    prefetched_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fill missing 160 source references without promoting them to Wealth features.

    Reuse even an empty discovery result within the same refresh. Standalone
    callers can resolve their candidates from the public schedule index once.
    This fallback copies only exact issuer matches
    into ``sources.metalogos160``. Canonical schedule fields and Wealth score
    features are deliberately untouched.
    """
    market = read_market_store()
    ipos = market.get("ipos", []) if isinstance(market.get("ipos"), list) else []
    start, end = _month_window(target_date_str)

    candidates: dict[str, dict[str, Any]] = {}
    for ipo in ipos:
        if not isinstance(ipo, dict) or not _relevant_schedule(ipo, start, end):
            continue
        name = str(ipo.get("company_name") or "").strip()
        key = normalize_company_name(name)
        if not key:
            continue
        sources = ipo.get("sources") if isinstance(ipo.get("sources"), dict) else {}
        if isinstance(sources.get("metalogos160"), dict):
            continue
        candidates.setdefault(key, ipo)

    if not candidates:
        return {
            "status": "not_needed",
            "candidates": 0,
            "matched": 0,
        }

    metalogos = client or MetalogosIpoClient()
    try:
        if prefetched_rows is not None:
            rows = prefetched_rows
        elif hasattr(metalogos, "fetch_company_items"):
            rows = metalogos.fetch_company_items(
                company_names=[str(ipo.get("company_name") or "") for ipo in candidates.values()],
                target_date_str=target_date_str,
            )
        else:
            # Compatibility for standalone callers with older client adapters.
            rows = metalogos.fetch_calendar_items(
                target_date_str=target_date_str, max_items=max(1, int(max_items)),
            )
    except ExternalNetworkDisabled:
        return {
            "status": "source_unavailable (external_network_disabled)",
            "candidates": len(candidates),
            "matched": 0,
        }
    except Exception as exc:
        return {
            "status": f"source_error ({type(exc).__name__})",
            "candidates": len(candidates),
            "matched": 0,
        }

    matched = 0
    observed_at = datetime.now(KST).isoformat()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = normalize_company_name(str(row.get("company_name") or ""))
        target = candidates.get(key)
        if target is None or not metalogos_identity_matches(target, row):
            continue
        row_sources = row.get("sources") if isinstance(row.get("sources"), dict) else {}
        reference = row_sources.get("metalogos160")
        if not isinstance(reference, dict):
            continue
        target.setdefault("sources", {})["metalogos160"] = copy.deepcopy(reference)
        target["updated_at"] = observed_at
        matched += 1
        candidates.pop(key, None)
        if not candidates:
            break

    if matched:
        write_market_store(market)

    return {
        "status": "ok",
        "candidates": len(candidates) + matched,
        "matched": matched,
        "unmatched": len(candidates),
        "scan_limit": max(1, int(max_items)),
    }
