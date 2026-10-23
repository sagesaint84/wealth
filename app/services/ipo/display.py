"""Read-only compatibility projection; never migrates IPO/application IDs."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re


def market_day():
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def schedule_field_confirmed(ipo, key):
    sources = ipo.get("sources")
    fields = sources.get("schedule_fields") if isinstance(sources, dict) else None
    evidence = fields.get(key) if isinstance(fields, dict) else None
    return (isinstance(evidence, dict)
            and evidence.get("source") in {"naver", "npay", "kind", "dart"}
            and bool(ipo.get(key)) and evidence.get("value") == ipo.get(key))


def schedule_condition(ipo):
    sources = ipo.get("sources") or {}
    if not isinstance(sources, dict):
        sources = {}
    state = sources.get("dart_schedule_status")
    verification = sources.get("dart_schedule_verification")
    status = state.get("status") if isinstance(state, dict) else None
    if status in {"postponed", "withdrawn"}:
        return status
    # DART linkage is disclosure evidence, not a veto on another provider's
    # observed dates. Require field evidence so a provider logo alone cannot
    # turn unrelated retained dates into a confirmed schedule.
    observed = all(schedule_field_confirmed(ipo, key)
                   for key in ("subscription_start", "subscription_end"))
    if not observed and isinstance(verification, dict) and verification.get("status") == "unverified":
        return "unverified"
    return "scheduled"


def _same_offering(a, b):
    # Never merge by a name suffix; conflicting authoritative IDs fail closed.
    for field in ("corp_code", "stock_code"):
        if a.get(field) and b.get(field) and a[field] != b[field]:
            return False
    sa, sb = a.get("sources") or {}, b.get("sources") or {}
    identifiers = [(a.get("corp_code"), b.get("corp_code"), r"\d{8}"),
                   (a.get("stock_code"), b.get("stock_code"), r"\d{6}"),
                   (a.get("kind_bz_procs_no") or sa.get("kind_bz_procs_no") or sa.get("kind", {}).get("kind_bz_procs_no"),
                    b.get("kind_bz_procs_no") or sb.get("kind_bz_procs_no") or sb.get("kind", {}).get("kind_bz_procs_no"), r"[A-Za-z0-9_-]+")]
    provider_a = {key for key in visibility_keys(a) if key.startswith("metalogos:")}
    provider_b = {key for key in visibility_keys(b) if key.startswith("metalogos:")}
    if not (provider_a & provider_b) and not any(x and x == y and re.fullmatch(pattern, str(x)) for x, y, pattern in identifiers):
        return False
    for field in ("subscription_start", "subscription_end", "actual_listing_date"):
        if a.get(field) and b.get(field) and a[field] != b[field]:
            return False
    return any(a.get(field) and a[field] == b.get(field) for field in
               ("subscription_start", "actual_listing_date", "expected_listing_date"))


def display_records(records, today=None):
    """One display row per proven offering; all original IDs remain writable.

    This is an in-memory preview, not a persisted merge. Pairwise evidence
    prevents a third ambiguous record from bridging two incompatible issuers.
    """
    groups = []
    for original in records:
        row = deepcopy(original)
        if not isinstance(row.get("sources"), dict):
            row["sources"] = {}
        sources = row["sources"]
        for key in ("dart", "dart_schedule", "dart_schedule_status", "dart_schedule_verification", "kind", "schedule_fields"):
            if key in sources and not isinstance(sources[key], dict):
                sources[key] = {}
        if not row.get("actual_listing_date") and not sources.get("dart_schedule_verification"):
            sources["dart_schedule_verification"] = {"status": "unverified", "reason": "legacy_not_checked"}
        group = next((g for g in groups if all(_same_offering(row, other) for other in g)), None)
        if group is None:
            groups.append([row])
        else:
            group.append(row)
    result = []
    for group in groups:
        def rank(row):
            source = row.get("sources", {}).get("dart_schedule", {})
            primary = any(e.get("source") in {"naver", "npay"} for e in
                          (row.get("sources", {}).get("schedule_fields") or {}).values()
                          if isinstance(e, dict))
            return (primary, bool(source), str(source.get("source_date") or ""), str(source.get("rcept_no") or ""))
        canonical = max(group, key=rank)
        ids = list(dict.fromkeys(str(value) for r in group for value in
                   ([r["ipo_id"]] + r.get("application_record_ids", [])) if value))
        ids = [str(canonical["ipo_id"])] + sorted(value for value in ids if value != canonical["ipo_id"])
        canonical["application_record_ids"] = ids
        canonical["identity_alias_ids"] = [value for value in ids if value != canonical.get("ipo_id")]
        official_name = canonical.get("sources", {}).get("dart_schedule", {}).get("company_name")
        if official_name:
            canonical["company_name"] = official_name
        # The newest official stop notice wins even when another alias has old dates.
        stops = [r["sources"]["dart_schedule_status"] for r in group
                 if schedule_condition(r) in {"postponed", "withdrawn"}]
        if stops:
            order = lambda r: (str(r.get("source_date") or "").replace("-", ""), str(r.get("rcept_no") or ""))
            stop = max(stops, key=order)
            if order(stop) >= order(canonical["sources"].get("dart_schedule", {})):
                canonical["sources"]["dart_schedule_status"] = stop
        if len(group) > 1:
            canonical["identity_resolution"] = "official_identifiers_same_offering"
        result.append(canonical)
    return result


def visibility_keys(ipo):
    """Stable explicit identities only; never infer identity from a similar name."""
    keys = ["id:" + str(i) for i in ipo.get("application_record_ids", [ipo["ipo_id"]])]
    for field, pattern in (("corp_code", r"\d{8}"), ("stock_code", r"\d{6}")):
        value = str(ipo.get(field) or "")
        if re.fullmatch(pattern, value):
            keys.append(field + ":" + value)
    source = (ipo.get("sources") or {}).get("metalogos160") or {}
    url = source.get("url", "") if isinstance(source, dict) else ""
    if re.fullmatch(r"https://(?:www\.)?metalogos\.ai/160ipo/stock/[A-Za-z0-9_-]+/?", url):
        keys.append("metalogos:" + url.rstrip("/").split("/")[-1])
    return keys


def schedule_snapshot(ipo):
    return {key: ipo.get(key) for key in ("subscription_start", "subscription_end",
            "expected_listing_date", "actual_listing_date")}


def annotate_visibility(ipo, exclusions):
    entries = [exclusions[key] for key in visibility_keys(ipo) if key in exclusions]
    ipo["user_excluded"] = bool(entries)
    ipo["excluded_schedule_changed"] = bool(entries and any(
        entry.get("schedule") != schedule_snapshot(ipo) for entry in entries))
    return ipo
