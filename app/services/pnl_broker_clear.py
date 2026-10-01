from __future__ import annotations

from typing import Any

from app.services import pnl_records, portfolio
from app.services.ipo.link_integrity import linked_pnl_reference_counts_from_file


UNASSIGNED_BROKER_SCOPE = "__unassigned__"


def normalize_broker_scope(value: Any) -> str:
    scope = str(value or "").strip()
    if not scope:
        raise ValueError("BROKER_SCOPE_INVALID")
    return scope


def record_matches_broker_scope(record: dict[str, Any], broker_scope: str) -> bool:
    """Return whether a non-real-estate P/L row belongs to the requested broker scope."""
    if pnl_records.is_real_estate_pnl_record(record):
        return False
    broker = str(record.get("broker") or "").strip()
    if broker_scope == UNASSIGNED_BROKER_SCOPE:
        return not broker
    return broker == broker_scope


def clear_pnl_records_for_broker(
    broker: Any,
    username: str | None = None,
) -> int:
    """Atomically clear only one broker's realized P/L rows.

    IPO links are checked only for records in the requested deletion scope. If
    any target record is referenced by an IPO allocation, the operation fails
    before writing anything. Real-estate sale records are never targets.
    """
    broker_scope = normalize_broker_scope(broker)

    with portfolio._LOCK:
        records = pnl_records.read_pnl_records(username)
        targets = [
            record
            for record in records
            if record_matches_broker_scope(record, broker_scope)
        ]
        if not targets:
            return 0

        target_ids = {
            str(record.get("id") or "").strip()
            for record in targets
            if str(record.get("id") or "").strip()
        }
        references = linked_pnl_reference_counts_from_file(
            portfolio._get_portfolio_file(username)
        )
        if target_ids.intersection(references):
            raise pnl_records.PnlRecordsLinkedToIpoError(
                "PNL_RECORDS_LINKED_TO_IPO"
            )

        preserved = [
            record
            for record in records
            if not record_matches_broker_scope(record, broker_scope)
        ]
        pnl_records.write_pnl_records(preserved, username)
        return len(targets)
