from __future__ import annotations

import hashlib
import re
from typing import Any


def normalize_company_name(name: str) -> str:
    if not name:
        return ""
    # Strip spaces, parenthesis notes like (주), (유), 코스닥, etc.
    cleaned = re.sub(r"\((주|유|특수목적|스팩|유가|코스닥)\)", "", name)
    cleaned = re.sub(r"[\s\-_.,]", "", cleaned)
    return cleaned.strip()


def generate_ipo_id(
    company_name: str,
    stock_code: str | None = None,
    corp_code: str | None = None,
    subscription_start: str | None = None,
) -> str:
    key_parts = []
    if stock_code and str(stock_code).strip():
        key_parts.append(f"s:{str(stock_code).strip()}")
    elif corp_code and str(corp_code).strip():
        key_parts.append(f"c:{str(corp_code).strip()}")
    else:
        norm_name = normalize_company_name(company_name)
        key_parts.append(f"n:{norm_name}")
        if subscription_start:
            key_parts.append(f"d:{subscription_start}")

    raw_key = "_".join(key_parts)
    hash_suffix = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]
    # Human-readable prefix if available
    slug = normalize_company_name(company_name)[:10] or "co"
    # Keep alphanumeric characters only for slug
    slug = re.sub(r"[^\w]", "", slug)
    return f"ipo_{slug}_{hash_suffix}"


def find_matching_ipo(
    incoming: dict[str, Any],
    existing_records: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, bool]:
    """Match an incoming IPO record against existing records by priority.

    Returns:
        (matched_record, review_required)
        - If matched by stock_code, corp_code, or kind_bz_procs_no: (record, False)
        - If matched by corp_code + offering period: (record, False)
        - If only company_name matches (name-only): (None, True) -> DO NOT auto merge
        - If no match found: (None, False)
    """
    in_stock = str(incoming.get("stock_code") or "").strip()
    in_corp = str(incoming.get("corp_code") or "").strip()
    in_sources = incoming.get("sources", {}) or {}
    in_procs = str(incoming.get("kind_bz_procs_no") or in_sources.get("kind_bz_procs_no") or "").strip()
    in_name = normalize_company_name(str(incoming.get("company_name") or ""))
    in_sub_start = str(incoming.get("subscription_start") or "")[:10]

    # Priority 1: stock_code exact
    if in_stock:
        for ex in existing_records:
            ex_stock = str(ex.get("stock_code") or "").strip()
            if ex_stock and ex_stock == in_stock:
                return ex, False

    # Priority 2: corp_code exact
    if in_corp:
        for ex in existing_records:
            ex_corp = str(ex.get("corp_code") or "").strip()
            if ex_corp and ex_corp == in_corp:
                return ex, False

    # Priority 3: kind_bz_procs_no exact
    if in_procs:
        for ex in existing_records:
            ex_sources = ex.get("sources", {}) or {}
            ex_procs = str(ex.get("kind_bz_procs_no") or ex_sources.get("kind_bz_procs_no") or "").strip()
            if ex_procs and ex_procs == in_procs:
                return ex, False

    # Priority 4: corp_code + offering period
    if in_corp and in_sub_start:
        for ex in existing_records:
            ex_corp = str(ex.get("corp_code") or "").strip()
            ex_sub_start = str(ex.get("subscription_start") or "")[:10]
            if ex_corp and ex_corp == in_corp and ex_sub_start == in_sub_start:
                return ex, False

    # Priority 5: company name only -> Automatic merge FORBIDDEN!
    if in_name:
        for ex in existing_records:
            ex_name = normalize_company_name(str(ex.get("company_name") or ""))
            if ex_name and ex_name == in_name:
                # Same name but distinct or missing identifiers: review required, no auto-merge
                return None, True

    return None, False
