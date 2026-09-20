"""Safe Wealth account resolution for IPO applicants.

This module only resolves Wealth account UUIDs.  It never accepts or exposes
provider account numbers, and it does not modify market/reference IPO data.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.services.broker_registry import normalize_broker


@dataclass(frozen=True)
class IpoAccountResolution:
    broker_id: str | None
    candidates: tuple[dict[str, Any], ...]
    auto_selected_account_id: str | None
    resolution_status: str
    mapping_status: str


def _candidate_payload(account: dict[str, Any], broker_id: str) -> dict[str, Any]:
    return {
        "account_id": str(account["id"]),
        "broker_id": broker_id,
        "account_name": str(account.get("account_name") or account.get("name") or ""),
        "owner": str(account.get("owner") or ""),
        "account_type": str(account.get("account_type") or ""),
    }


def resolve_ipo_account_candidates(
    broker_value: str | None,
    portfolio_accounts: Iterable[dict[str, Any]],
    *,
    existing_mapping: dict[str, Any] | None = None,
) -> IpoAccountResolution:
    """Resolve only same-broker Wealth accounts for one IPO applicant."""
    broker_id = normalize_broker(broker_value)
    if broker_id is None:
        return IpoAccountResolution(None, (), None, "BROKER_UNKNOWN", "not_checked")

    accounts = [account for account in portfolio_accounts if isinstance(account, dict)]
    candidates = tuple(
        _candidate_payload(account, broker_id)
        for account in accounts
        if str(account.get("id") or "").strip()
        and normalize_broker(str(account.get("broker") or "")) == broker_id
    )
    account_ids = {candidate["account_id"] for candidate in candidates}

    if existing_mapping:
        mapped_id = str(existing_mapping.get("account_id") or "").strip()
        mapped_broker = normalize_broker(existing_mapping.get("broker_id"))
        if mapped_broker != broker_id:
            return IpoAccountResolution(broker_id, candidates, None, "MAPPING_CONFLICT", "conflict")
        if not mapped_id or mapped_id not in account_ids:
            return IpoAccountResolution(broker_id, candidates, None, "MAPPING_CONFLICT", "stale")
        return IpoAccountResolution(broker_id, candidates, mapped_id, "MAPPED", "valid")

    if len(candidates) == 1:
        return IpoAccountResolution(broker_id, candidates, candidates[0]["account_id"], "AUTO_SELECTED", "absent")
    if not candidates:
        return IpoAccountResolution(broker_id, (), None, "NO_ACCOUNT_CANDIDATE", "absent")
    return IpoAccountResolution(broker_id, candidates, None, "AMBIGUOUS_ACCOUNT", "absent")


def validate_ipo_account_selection(
    broker_value: str | None,
    portfolio_accounts: Iterable[dict[str, Any]],
    account_id: object,
    *,
    existing_mapping: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], IpoAccountResolution]:
    """Validate a user-selected UUID at the persistent mapping boundary."""
    resolution = resolve_ipo_account_candidates(
        broker_value, portfolio_accounts, existing_mapping=existing_mapping,
    )
    if resolution.resolution_status == "MAPPING_CONFLICT":
        raise ValueError("MAPPING_CONFLICT")

    selected_id = str(account_id or "").strip()
    if resolution.resolution_status == "MAPPED" and selected_id != resolution.auto_selected_account_id:
        # A stable applicant mapping cannot be silently remapped by a later
        # request, even when both UUIDs belong to the same broker.
        raise ValueError("MAPPING_CONFLICT")
    selected = next((item for item in resolution.candidates if item["account_id"] == selected_id), None)
    if selected is None:
        raise ValueError("DESTINATION_BROKER_MISMATCH")
    return selected, resolution
