"""Pure NH realized-record identity and duplicate classification."""
from __future__ import annotations
import hashlib
import json
from collections import Counter
from typing import Any, Mapping
from app.services.nh_feed import canonical_nh_row_hash, verify_nh_feed_row

NEW = "NEW"; ALREADY_IMPORTED = "ALREADY_IMPORTED"; POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"; INVALID = "INVALID"

def nh_fingerprint(row: Mapping[str, Any], source_account_key: str, occurrence: int) -> str:
    """Opaque-account-scoped multiset identity; no provider account number is used."""
    canonical = {k:v for k,v in row.items() if k != "source_occurrence"}
    payload = ["nh-realized-v1", str(source_account_key), canonical_nh_row_hash(canonical), occurrence]
    return "nh-realized:v1:" + hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()

def classify_nh_rows(rows: list[Mapping[str, Any]], existing: list[Mapping[str, Any]], source_account_key: str) -> list[dict[str, Any]]:
    """Classify canonical rows without mutation or persistence."""
    seen: Counter[str] = Counter()
    batch_fingerprints: set[str] = set()
    existing_fingerprints = {str(r.get("source_fingerprint")) for r in existing if r.get("source") == "nh"}
    output=[]
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("date") or not row.get("code") or row.get("quantity") is None or row.get("buy_amount") is None or row.get("sell_amount") is None or row.get("pnl") is None:
            output.append({"status": INVALID, "reason": "MISSING_REQUIRED_FIELD"}); continue
        try:
            digest=canonical_nh_row_hash({k:v for k,v in row.items() if k != "source_occurrence"})
        except (TypeError, ValueError):
            output.append({"status": INVALID, "reason": "NUMERIC_PARSE_ERROR"}); continue
        supplied_occurrence=row.get("source_occurrence")
        if supplied_occurrence is not None and (not isinstance(supplied_occurrence,int) or isinstance(supplied_occurrence,bool) or supplied_occurrence < 0):
            output.append({"status": INVALID, "reason": "INVALID_OCCURRENCE"}); continue
        occurrence=supplied_occurrence if supplied_occurrence is not None else seen[digest]
        seen[digest]=max(seen[digest],occurrence+1)
        fingerprint=nh_fingerprint(row, source_account_key, occurrence)
        if fingerprint in batch_fingerprints:
            output.append({"status": INVALID, "reason": "DUPLICATE_SELECTION"}); continue
        batch_fingerprints.add(fingerprint)
        if fingerprint in existing_fingerprints: status=ALREADY_IMPORTED
        else:
            try:
                pnl_hash = canonical_nh_row_hash({"pnl": row.get("pnl")})
            except (TypeError, ValueError):
                output.append({"status": INVALID, "reason": "NUMERIC_PARSE_ERROR"}); continue
            manual_match=False
            for record in existing:
                if record.get("source") == "nh" or str(record.get("date")) != str(row.get("date")) or str(record.get("code")) != str(row.get("code")):
                    continue
                try:
                    if canonical_nh_row_hash({"pnl": record.get("pnl")}) == pnl_hash:
                        manual_match=True
                        break
                except (TypeError, ValueError):
                    continue
            status=POSSIBLE_DUPLICATE if manual_match else NEW
        output.append({"status": status, "fingerprint": fingerprint, "candidate": dict(row)})
    return output


def preview_nh_realized_selection(
    selected_items: list[Mapping[str, Any]], destination_account: Mapping[str, Any],
    existing_records: list[Mapping[str, Any]], *, user_id: str,
    source_account_key: str, source_account_label: str, market: str,
) -> dict[str, Any]:
    """Verify and classify selected canonical NH rows without any writes."""
    verified_rows: list[Mapping[str, Any]] = []
    verified_indices: list[int] = []
    items: list[dict[str, Any]] = []
    seen_selection_tokens: set[str] = set()
    for index, item in enumerate(selected_items):
        row = item.get("row") if isinstance(item, Mapping) else None
        token = item.get("selection_token") if isinstance(item, Mapping) else None
        if not isinstance(row, Mapping) or not isinstance(token, str):
            items.append({"index": index, "status": INVALID, "reason": "TOKEN_INVALID"})
            continue
        valid, reason = verify_nh_feed_row(row, token, user_id=user_id, source_account_key=source_account_key, market=market)
        if not valid:
            items.append({"index": index, "status": INVALID, "reason": reason or "TOKEN_INVALID"})
            continue
        if token in seen_selection_tokens:
            items.append({"index": index, "status": INVALID, "reason": "DUPLICATE_SELECTION"})
            continue
        seen_selection_tokens.add(token)
        verified_rows.append(row); verified_indices.append(index)
    classified = classify_nh_rows(verified_rows, existing_records, source_account_key)
    account_name = str(destination_account.get("account_name") or destination_account.get("name") or "").strip()
    for index, result in zip(verified_indices, classified):
        result = dict(result); result["index"] = index
        candidate = result.get("candidate")
        if isinstance(candidate, dict):
            candidate.update({"account_name": account_name, "owner": str(destination_account.get("owner") or "모두"), "broker": str(destination_account.get("broker") or "NH투자증권")})
        items.append(result)
    items.sort(key=lambda value: value["index"])
    counts = {"selected": len(selected_items), "new": 0, "already_imported": 0, "possible_duplicate": 0, "invalid": 0}
    keys = {NEW:"new", ALREADY_IMPORTED:"already_imported", POSSIBLE_DUPLICATE:"possible_duplicate", INVALID:"invalid"}
    for item in items: counts[keys[item["status"]]] += 1
    return {"counts": counts, "items": items, "scope_kind": "verified", "scope_verified": True,
            "source_account_label": source_account_label,
            "destination_account": {"id": destination_account.get("id"), "account_name": account_name,
                                    "owner": destination_account.get("owner"), "broker": destination_account.get("broker")}}
