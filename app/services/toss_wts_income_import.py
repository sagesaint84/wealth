"""Preview-only classification for selected Toss WTS income rows."""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from app.services.toss_wts_income import map_toss_wts_income_row
from app.services.toss_wts_income_feed import verify_income_feed_row_token


def _is_trusted_income_fp(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("toss-wts-income:v1:") and len(value) == len("toss-wts-income:v1:") + 64


def preview_toss_wts_income_selection(
    selected_items: list[Mapping[str, Any]],
    destination_account: Mapping[str, Any],
    existing_records: Iterable[Mapping[str, Any]],
    *,
    user_id: str,
    current_generation_id: str | None,
) -> dict[str, Any]:
    account_name = str(destination_account.get("account_name") or destination_account.get("name") or "").strip()
    owner = str(destination_account.get("owner") or "모두").strip()
    broker = str(destination_account.get("broker") or "토스증권").strip()
    existing = list(existing_records)
    exact_counts: Counter[str] = Counter()
    for rec in existing:
        if not isinstance(rec, Mapping) or rec.get("source") != "toss_wts":
            continue
        fp = rec.get("source_fingerprint")
        if _is_trusted_income_fp(fp):
            exact_counts[str(fp)] += 1
    assigned: Counter[str] = Counter()
    counts = {"selected": len(selected_items), "new": 0, "already_imported": 0, "possible_duplicate": 0, "invalid": 0}
    items: list[dict[str, Any]] = []

    for index, item in enumerate(selected_items):
        if not isinstance(item, Mapping):
            counts["invalid"] += 1
            items.append({"index": index, "status": "INVALID", "reason": "MALFORMED_ITEM", "candidate": None})
            continue
        row = item.get("row", item)
        token = item.get("selection_token")
        if not isinstance(row, Mapping):
            counts["invalid"] += 1
            items.append({"index": index, "status": "INVALID", "reason": "MALFORMED_ROW", "candidate": None})
            continue
        valid, error = verify_income_feed_row_token(
            row, str(token or ""), user_id=user_id, current_generation_id=current_generation_id
        )
        if not valid:
            counts["invalid"] += 1
            items.append({"index": index, "status": "INVALID", "reason": error or "TOKEN_INVALID", "candidate": None})
            continue
        try:
            candidate = map_toss_wts_income_row(row)
            if candidate is None:
                raise ValueError("unsupported row")
            candidate = dict(candidate)
            candidate["owner"] = owner
            candidate["broker"] = broker or "토스증권"
            candidate["account_name"] = account_name
            candidate["source_account_scope"] = "unverified"
            fingerprint = str(candidate["source_fingerprint"])
        except (KeyError, TypeError, ValueError):
            counts["invalid"] += 1
            items.append({"index": index, "status": "INVALID", "reason": "MAPPING_FAILED", "candidate": None})
            continue

        if assigned[fingerprint] < exact_counts[fingerprint]:
            assigned[fingerprint] += 1
            counts["already_imported"] += 1
            items.append({"index": index, "status": "ALREADY_IMPORTED", "reason": "EXACT_WTS_FINGERPRINT_MATCH", "fingerprint": fingerprint, "candidate": candidate})
            continue

        possible = False
        for rec in existing:
            if not isinstance(rec, Mapping) or rec.get("source") == "toss_wts":
                continue
            if str(rec.get("date") or "") != str(candidate.get("date") or ""):
                continue
            if str(rec.get("currency") or "").upper() != str(candidate.get("currency") or "").upper():
                continue
            try:
                amount_match = abs(float(rec.get("amount", 0)) - float(candidate.get("amount", 0))) < 0.000001
            except (TypeError, ValueError):
                amount_match = False
            if not amount_match:
                continue
            rec_code = str(rec.get("code") or "").strip()
            rec_name = str(rec.get("name") or "").strip()
            cand_code = str(candidate.get("code") or "").strip()
            cand_name = str(candidate.get("name") or "").strip()
            if (rec_code and cand_code and rec_code == cand_code) or (rec_name and rec_name == cand_name):
                possible = True
                break

        if possible:
            counts["possible_duplicate"] += 1
            status = "POSSIBLE_DUPLICATE"
            reason = "SIMILAR_EXISTING_RECORD"
        else:
            counts["new"] += 1
            status = "NEW"
            reason = None
        items.append({"index": index, "status": status, "reason": reason, "fingerprint": fingerprint, "candidate": candidate})

    return {"counts": counts, "items": items, "write_ready": counts["new"] > 0 and counts["invalid"] == 0}
