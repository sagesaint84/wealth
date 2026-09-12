"""Pure Kiwoom realized-record identity, verification, and duplicate classification."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from app.services.kiwoom_feed import (
    KiwoomFeedError,
    canonical_kiwoom_number,
    canonical_kiwoom_row_hash,
    verify_kiwoom_feed_row,
)

NEW = "NEW"
ALREADY_IMPORTED = "ALREADY_IMPORTED"
POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
INVALID = "INVALID"


def kiwoom_fingerprint(row: Mapping[str, Any], source_account_key: str, occurrence: int) -> str:
    row_hash = canonical_kiwoom_row_hash(row)
    payload = ["kiwoom-realized:v1", str(source_account_key), row_hash, occurrence]
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return "kiwoom-realized:v1:" + hashlib.sha256(encoded).hexdigest()


def classify_kiwoom_rows(
    rows: list[Mapping[str, Any]], existing: list[Mapping[str, Any]], source_account_key: str,
) -> list[dict[str, Any]]:
    """Classify verified canonical rows without mutation or persistence."""
    existing_fingerprints = {
        str(record.get("source_fingerprint"))
        for record in existing
        if record.get("source") == "kiwoom" and record.get("source_fingerprint")
    }
    batch_fingerprints: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or not row.get("date")
            or not row.get("code")
            or row.get("quantity") is None
            or row.get("buy_amount") is None
            or row.get("sell_amount") is None
            or row.get("pnl") is None
        ):
            output.append({"status": INVALID, "reason": "MISSING_REQUIRED_FIELD"})
            continue
        occurrence = row.get("source_occurrence")
        if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
            output.append({"status": INVALID, "reason": "INVALID_OCCURRENCE"})
            continue
        try:
            row_hash = canonical_kiwoom_row_hash(row)
            if row.get("canonical_hash") not in (None, row_hash):
                output.append({"status": INVALID, "reason": "ROW_TAMPERED"})
                continue
            fingerprint = kiwoom_fingerprint(row, source_account_key, occurrence)
            if row.get("future_identity") not in (None, fingerprint):
                output.append({"status": INVALID, "reason": "ROW_TAMPERED"})
                continue
        except (KiwoomFeedError, TypeError, ValueError):
            output.append({"status": INVALID, "reason": "NUMERIC_PARSE_ERROR"})
            continue
        if fingerprint in batch_fingerprints:
            output.append({"status": INVALID, "reason": "DUPLICATE_SELECTION"})
            continue
        batch_fingerprints.add(fingerprint)
        if fingerprint in existing_fingerprints:
            status = ALREADY_IMPORTED
        else:
            manual_match = False
            try:
                expected_pnl = canonical_kiwoom_number(row.get("pnl"))
            except KiwoomFeedError:
                output.append({"status": INVALID, "reason": "NUMERIC_PARSE_ERROR"})
                continue
            for record in existing:
                if (
                    record.get("source") == "kiwoom"
                    or str(record.get("date")) != str(row.get("date"))
                    or str(record.get("code")) != str(row.get("code"))
                ):
                    continue
                try:
                    if canonical_kiwoom_number(record.get("pnl")) == expected_pnl:
                        manual_match = True
                        break
                except KiwoomFeedError:
                    continue
            status = POSSIBLE_DUPLICATE if manual_match else NEW
        output.append({"status": status, "fingerprint": fingerprint, "candidate": dict(row)})
    return output


def preview_kiwoom_realized_selection(
    selected_items: list[Mapping[str, Any]], destination_account: Mapping[str, Any],
    existing_records: list[Mapping[str, Any]], *, user_id: str,
    source_account_key: str, source_account_label: str, market: str,
) -> dict[str, Any]:
    """Verify and classify selected Kiwoom rows while performing zero writes."""
    verified_rows: list[Mapping[str, Any]] = []
    verified_indices: list[int] = []
    items: list[dict[str, Any]] = []
    seen_identities: set[tuple[str, int]] = set()
    for index, item in enumerate(selected_items):
        row = item.get("row") if isinstance(item, Mapping) else None
        token = item.get("selection_token") if isinstance(item, Mapping) else None
        if not isinstance(row, Mapping) or not isinstance(token, str):
            items.append({"index": index, "status": INVALID, "reason": "TOKEN_INVALID"})
            continue
        valid, reason = verify_kiwoom_feed_row(
            row, token, user_id=user_id, source_account_key=source_account_key, market=market,
        )
        if not valid:
            items.append({"index": index, "status": INVALID, "reason": reason or "TOKEN_INVALID"})
            continue
        identity = (str(row.get("canonical_hash") or canonical_kiwoom_row_hash(row)), int(row["source_occurrence"]))
        if identity in seen_identities:
            items.append({"index": index, "status": INVALID, "reason": "DUPLICATE_SELECTION"})
            continue
        seen_identities.add(identity)
        verified_rows.append(row)
        verified_indices.append(index)

    classified = classify_kiwoom_rows(verified_rows, existing_records, source_account_key)
    account_name = str(destination_account.get("account_name") or destination_account.get("name") or "").strip()
    for index, result in zip(verified_indices, classified):
        result = dict(result)
        result["index"] = index
        candidate = result.get("candidate")
        if isinstance(candidate, dict):
            candidate.update({
                "account_name": account_name,
                "owner": str(destination_account.get("owner") or "모두"),
                "broker": str(destination_account.get("broker") or "키움증권"),
            })
        items.append(result)
    items.sort(key=lambda value: value["index"])
    counts = {"selected": len(selected_items), "new": 0, "already_imported": 0, "possible_duplicate": 0, "invalid": 0}
    count_keys = {NEW: "new", ALREADY_IMPORTED: "already_imported", POSSIBLE_DUPLICATE: "possible_duplicate", INVALID: "invalid"}
    for item in items:
        counts[count_keys[item["status"]]] += 1
    return {
        "counts": counts,
        "items": items,
        "scope_kind": "unverified",
        "scope_verified": False,
        "source_account_label": source_account_label,
        "destination_account": {
            "id": destination_account.get("id"), "account_name": account_name,
            "owner": destination_account.get("owner"), "broker": destination_account.get("broker"),
        },
    }
