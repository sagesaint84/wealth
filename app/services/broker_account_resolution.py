"""Safe, broker-scoped destination resolution for provider imports.

Provider account values never leave the server.  The public result contains
only existing Wealth account records and their UUIDs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.services.broker_registry import normalize_broker


def canonical_broker_id(value: object) -> str | None:
    """Backward-compatible resolver API backed by the canonical registry."""
    return normalize_broker(str(value) if value is not None else None)


def normalize_provider_account_identity(provider: str, value: object) -> str | None:
    """Normalize a server-side provider identity without discarding its parts."""
    broker = canonical_broker_id(provider)
    raw = str(value or "").replace("-", "").strip()
    if not broker or not raw:
        return None
    if broker == "kis":
        if not raw.isdigit() or len(raw) not in {8, 10}:
            return None
        return raw if len(raw) == 10 else f"{raw}01"
    # NH and Kiwoom account identifiers are provider-owned strings.  Do not
    # coerce leading zeroes or remove meaningful non-digit characters.
    return raw


@dataclass(frozen=True)
class RealizedDestinationResolution:
    candidates: tuple[dict[str, Any], ...]
    auto_selected_account_id: str | None
    reason: str
    mapping_status: str

    @property
    def candidate_account_ids(self) -> tuple[str, ...]:
        return tuple(str(account.get("id")) for account in self.candidates)


def resolve_realized_destination_candidates(
    provider: str,
    portfolio_accounts: Iterable[dict[str, Any]],
    *,
    provider_account_identity: object = None,
    mapped_destination_account_id: object = None,
) -> RealizedDestinationResolution:
    """Return only same-broker accounts and a safe optional automatic choice."""
    broker = canonical_broker_id(provider)
    if not broker:
        return RealizedDestinationResolution((), None, "unknown_provider", "not_checked")

    accounts = [item for item in portfolio_accounts if isinstance(item, dict)]
    candidates = tuple(
        item for item in accounts
        if canonical_broker_id(item.get("broker")) == broker and str(item.get("id") or "").strip()
    )
    by_id = {str(item.get("id")): item for item in accounts if str(item.get("id") or "").strip()}

    mapped_id = str(mapped_destination_account_id or "").strip()
    if mapped_id:
        mapped = by_id.get(mapped_id)
        if mapped is None:
            return RealizedDestinationResolution(candidates, None, "manual_required", "stale")
        if canonical_broker_id(mapped.get("broker")) != broker:
            return RealizedDestinationResolution(candidates, None, "manual_required", "cross_broker")
        return RealizedDestinationResolution(candidates, mapped_id, "existing_mapping", "valid")

    normalized_source = normalize_provider_account_identity(broker, provider_account_identity)
    if normalized_source:
        exact = [
            account for account in candidates
            if normalize_provider_account_identity(broker, account.get("account_no")) == normalized_source
        ]
        if len(exact) == 1:
            return RealizedDestinationResolution(
                candidates, str(exact[0]["id"]), "exact_identity", "absent"
            )
        if len(exact) > 1:
            return RealizedDestinationResolution(candidates, None, "ambiguous_identity", "absent")

    if not candidates:
        return RealizedDestinationResolution((), None, "no_candidate", "absent")
    return RealizedDestinationResolution(candidates, None, "manual_required", "absent")


def validate_realized_destination(
    provider: str,
    portfolio_accounts: Iterable[dict[str, Any]],
    account_id: object,
    *,
    provider_account_identity: object = None,
    mapped_destination_account_id: object = None,
) -> tuple[dict[str, Any], RealizedDestinationResolution]:
    """Validate a selected destination against broker, mapping, and exact scope."""
    selected_id = str(account_id or "").strip()
    resolution = resolve_realized_destination_candidates(
        provider,
        portfolio_accounts,
        provider_account_identity=provider_account_identity,
        mapped_destination_account_id=mapped_destination_account_id,
    )
    selected = next((item for item in resolution.candidates if str(item.get("id")) == selected_id), None)
    if selected is None:
        raise ValueError("DESTINATION_BROKER_MISMATCH")
    if resolution.mapping_status == "cross_broker":
        raise ValueError("CROSS_BROKER_MAPPING")
    if resolution.mapping_status == "valid" and resolution.auto_selected_account_id != selected_id:
        raise ValueError("DESTINATION_MAPPING_CONFLICT")
    if resolution.reason == "exact_identity" and resolution.auto_selected_account_id != selected_id:
        raise ValueError("DESTINATION_IDENTITY_CONFLICT")
    return selected, resolution
