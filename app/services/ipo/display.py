"""Read-only compatibility projection; never migrates IPO/application IDs."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import re


def market_day():
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def _schedule_field_evidence(ipo, key):
    sources = ipo.get("sources")
    fields = sources.get("schedule_fields") if isinstance(sources, dict) else None
    evidence = fields.get(key) if isinstance(fields, dict) else None
    return evidence if isinstance(evidence, dict) else {}


def schedule_field_confirmed(ipo, key):
    evidence = _schedule_field_evidence(ipo, key)
    return (evidence.get("source") in {"naver", "npay", "kind", "dart"}
            and bool(ipo.get(key)) and evidence.get("value") == ipo.get(key))


def npay_schedule_field_confirmed(ipo, key):
    evidence = _schedule_field_evidence(ipo, key)
    return (evidence.get("source") == "npay"
            and bool(ipo.get(key)) and evidence.get("value") == ipo.get(key))


def _schedule_timestamp(value):
    try:
        timestamp = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    kst = timezone(timedelta(hours=9))
    return timestamp.astimezone(kst) if timestamp.tzinfo else timestamp.replace(tzinfo=kst)


def npay_schedule_field_currently_confirmed(ipo, key):
    """Require field evidence from the latest successful Npay refresh attempt."""
    if not npay_schedule_field_confirmed(ipo, key):
        return False
    sources = ipo.get("sources") if isinstance(ipo.get("sources"), dict) else {}
    evidence = _schedule_field_evidence(ipo, key)
    attempts = sources.get("schedule_refresh_attempts")
    attempt = attempts.get("npay") if isinstance(attempts, dict) else None
    if not isinstance(attempt, dict):
        return True
    if not str(attempt.get("outcome") or "").startswith(("read_ok", "partial_item_error")):
        return False
    observed_at = _schedule_timestamp(evidence.get("observed_at"))
    attempted_at = _schedule_timestamp(attempt.get("last_attempt_at"))
    return observed_at is not None and attempted_at is not None and observed_at >= attempted_at


def schedule_condition(ipo):
    sources = ipo.get("sources") or {}
    if not isinstance(sources, dict):
        sources = {}
    state = sources.get("dart_schedule_status")
    verification = sources.get("dart_schedule_verification")
    reconciliation = sources.get("schedule_reconciliation")
    status = state.get("status") if isinstance(state, dict) else None
    if status in {"postponed", "withdrawn"}:
        return status
    reconciliation_status = reconciliation.get("status") if isinstance(reconciliation, dict) else None
    if reconciliation_status in {"partial", "review_required"}:
        return "unverified"
    # DART linkage is disclosure evidence, not a veto on another provider's
    # observed dates. Require field evidence so a provider logo alone cannot
    # turn unrelated retained dates into a confirmed schedule.
    observed = all(schedule_field_confirmed(ipo, key)
                   for key in ("subscription_start", "subscription_end"))
    if not observed and isinstance(verification, dict) and verification.get("status") == "unverified":
        return "unverified"
    return "scheduled"


_NPAY_SCHEDULE_FIELDS = {"subscription_start", "subscription_end", "expected_listing_date"}


def _npay_disputed_fields(ipo, reconciliation):
    """Return unresolved fields, or None for reconciliation from another path."""
    if not isinstance(reconciliation, dict) or reconciliation.get("source") != "npay":
        return None
    reason = reconciliation.get("reason")
    if reason == "end_date_not_confirmed":
        end = ipo.get("subscription_end")
        start = ipo.get("subscription_start")
        revision_at = _schedule_timestamp(reconciliation.get("source_observed_at")
                                          or reconciliation.get("observed_at"))
        evidence_at = _schedule_timestamp(_schedule_field_evidence(ipo, "subscription_end").get("observed_at"))
        if (start and end and start <= end
                and schedule_field_confirmed(ipo, "subscription_end")
                and not npay_schedule_field_confirmed(ipo, "subscription_end")
                and revision_at is not None and evidence_at is not None and evidence_at >= revision_at):
            return set()
        return {"subscription_end"}
    if reason == "schedule_date_conflict":
        observed = reconciliation.get("observed_schedule") or {}
        disputed = set(observed) & _NPAY_SCHEDULE_FIELDS
        if disputed & {"subscription_start", "subscription_end"}:
            disputed.update(("subscription_start", "subscription_end"))
        if disputed:
            return {key for key in disputed
                    if not schedule_field_confirmed(ipo, key) or npay_schedule_field_confirmed(ipo, key)}
    return None


def _valid_npay_absence(ipo, key, marker):
    if (not isinstance(marker, dict) or marker.get("coverage") != "explicit_complete_month"
            or not npay_schedule_field_confirmed(ipo, key) or marker.get("value") != ipo.get(key)):
        return False
    value = ipo[key]
    if not str(marker.get("from") or "") <= value <= str(marker.get("to") or ""):
        return False
    observed = _schedule_timestamp(_schedule_field_evidence(ipo, key).get("observed_at"))
    complete = _schedule_timestamp(marker.get("last_complete_at"))
    return observed is not None and complete is not None and observed < complete


def current_schedule(ipo, today=None):
    """Read projection shared by the market list and integrated calendar."""
    today = today.isoformat() if today is not None else market_day()
    sources = ipo.get("sources") or {}
    missing = sources.get("npay_schedule_missing")
    if not isinstance(missing, dict):
        missing = {}
    valid_missing = {key: missing[key] for key in _NPAY_SCHEDULE_FIELDS
                     if _valid_npay_absence(ipo, key, missing.get(key))}
    suppressed = set(valid_missing)
    reconciliation = sources.get("schedule_reconciliation")
    disputed = _npay_disputed_fields(ipo, reconciliation)
    if disputed:
        if reconciliation.get("reason") == "end_date_not_confirmed":
            suppressed.update(disputed)
        else:
            suppressed.update(key for key in disputed if str(ipo.get(key) or "") >= today)

    # Keep the raw evidence intact while exposing only current notices to both
    # readers. Markers from the old, unverified coverage gate cannot hide dates.
    resolved = disputed is not None and not disputed
    if "npay_schedule_missing" in sources or resolved:
        sources = dict(sources)
        if valid_missing:
            sources["npay_schedule_missing"] = valid_missing
        else:
            sources.pop("npay_schedule_missing", None)
        if resolved:
            sources.pop("schedule_reconciliation", None)
    return {**ipo, "sources": sources, **dict.fromkeys(suppressed)}


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
        for key in ("dart", "dart_schedule", "dart_schedule_status", "dart_schedule_verification",
                    "kind", "schedule_fields", "schedule_reconciliation", "schedule_refresh_attempts"):
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
