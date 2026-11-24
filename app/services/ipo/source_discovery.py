from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import copy
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from time import perf_counter

from app.services.ipo.dart_client import DartClient, DartAuthError
import httpx
from app.services.ipo.dart_offering_schedule import (
    build_dart_offering_schedule,
    dart_schedule_restriction,
    find_verified_offering_withdrawal,
    select_dart_schedule_filing,
)
from app.services.ipo.display import npay_schedule_field_confirmed, schedule_field_confirmed
from app.services.ipo.identity import is_spac_ipo, normalize_company_name, spac_name_key
from app.services.ipo.kind_client import KindClient
from app.services.ipo.metalogos_client import MetalogosIpoClient, metalogos_identity_matches
from app.services.ipo.naver_client import NaverIpoClient, NaverIpoClientError, normalize_naver_ipo_code
from app.services.ipo.naver_discovery import NaverIpoDiscoveryClient, naver_ipo_offering_status
from app.services.ipo.npay_client import NPAY_IPO_URL, NPAY_STOCK_IPO_URL, NpayIpoCalendarIncomplete, NpayIpoClient
from app.services.ipo.store import merge_ipo_record, read_market_store, write_market_store
from app.services.network_policy import ExternalNetworkDisabled


KST = timezone(timedelta(hours=9))
_NPAY_CALENDAR_FIELDS = ("subscription_start", "subscription_end", "expected_listing_date")


def _shift_month(first: date, months: int) -> date:
    serial = first.year * 12 + (first.month - 1) + months
    return date(serial // 12, serial % 12 + 1, 1)


def _month_window(target_date_str: str) -> tuple[date, date]:
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    current = target.replace(day=1)

    start = _shift_month(current, -1)
    after = _shift_month(current, 2)
    return start, after - timedelta(days=1)


def plan_npay_historical_storage(observations: list[dict[str, Any]], market: dict[str, Any],
                                *, target_date_str: str) -> dict[str, Any]:
    """Pure offering-level plan; validate merges on copies, never write market/users."""
    from app.services.ipo.identity import find_matching_ipo, generate_ipo_id
    target = date.fromisoformat(target_date_str)
    existing = market.get("ipos", [])
    fields = ("subscription_start", "subscription_end", "expected_listing_date",
              "actual_listing_date", "final_offer_price", "lead_managers")
    groups: dict[str, list[dict[str, Any]]] = {}
    for raw in observations:
        item = copy.deepcopy(raw)
        code = str(item.get("stock_code") or "").strip()
        if not code:
            raise ValueError("Historical observation requires a stock code")
        groups.setdefault(code, []).append(item)
    plan = []
    for code, rows in groups.items():
        reasons = []
        names = {normalize_company_name(str(row.get("company_name") or "")) for row in rows}
        if len(names) != 1 or not all(names):
            reasons.append("observed_name_conflict")
        item = {"stock_code": code, "company_name": rows[0].get("company_name", "")}
        evidence = {}
        for field in fields:
            observed = [row for row in rows if row.get(field) not in (None, "", [])]
            if not observed:
                continue
            if any(row[field] != observed[0][field] for row in observed):
                reasons.append(f"observed_field_conflict:{field}")
                continue
            value = copy.deepcopy(observed[0][field])
            source = observed[0].get("sources", {}).get("npay", {})
            if field.endswith("date") or field.startswith("subscription_"):
                try:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError("Noncanonical date")
                except (ValueError, TypeError):
                    reasons.append(f"invalid_date:{field}")
                    continue
            if field == "actual_listing_date" and not all(
                    row.get("sources", {}).get("npay", {}).get("schedule_source") == "npay_stock_completed_ipo"
                    and row.get("sources", {}).get("npay", {}).get("ipo_status") == "상장"
                    and date.fromisoformat(row[field]) <= target for row in observed):
                reasons.append("actual_listing_completion_evidence_missing")
                continue
            if not source.get("url") or not source.get("observed_at"):
                reasons.append(f"field_provenance_missing:{field}")
            item[field] = value
            evidence[field] = {"source": "npay", "value": value,
                               "url": source.get("url"), "observed_at": source.get("observed_at"),
                               "raw_field": source.get("field_paths", {}).get(field)}
        if item.get("subscription_start") and item.get("subscription_end") and item["subscription_start"] > item["subscription_end"]:
            reasons.append("invalid_subscription_period")
        if (item.get("actual_listing_date") and item.get("expected_listing_date")
                and item["actual_listing_date"] != item["expected_listing_date"]):
            reasons.append("expected_actual_listing_conflict")
        coded = [row for row in existing if str(row.get("stock_code") or "").strip() == code]
        named = _exact_name_candidates(item, existing)
        aliases = [row for row in existing if is_spac_ipo(item) and is_spac_ipo(row)
                   and spac_name_key(row) == spac_name_key(item)]
        match = coded[0] if len(coded) == 1 else None
        basis = "stock_code" if match else None
        if len(coded) > 1:
            reasons.append("duplicate_saved_stock_code")
        if match is None and not coded and len(named) == 1:
            candidate = named[0]
            if (not candidate.get("stock_code") and all(item.get(field) and item[field] == candidate.get(field)
                    for field in ("subscription_start", "subscription_end"))):
                match, basis = candidate, "exact_name_and_complete_subscription_period"
        if match:
            if normalize_company_name(match.get("company_name", "")) not in names:
                reasons.append("saved_name_conflict")
            if not match.get("ipo_id") or sum(row.get("ipo_id") == match.get("ipo_id") for row in existing) != 1:
                reasons.append("saved_ipo_id_conflict")
            for field in fields:
                if item.get(field) not in (None, "", []) and match.get(field) not in (None, "", [], item[field]):
                    reasons.append(f"saved_field_conflict:{field}")
            if (item.get("actual_listing_date") and not item.get("subscription_start")
                    and item["actual_listing_date"] not in (match.get("expected_listing_date"), match.get("actual_listing_date"))):
                reasons.append("listing_offering_link_unproven")
        elif named or aliases:
            reasons.append("name_or_spac_alias_requires_review")
        else:
            if not item.get("subscription_start") or not item.get("subscription_end"):
                reasons.append("new_offering_period_missing")
            matched, review = find_matching_ipo(item, existing)
            if matched or review:
                reasons.append("existing_merge_identity_requires_review")
        patch = {field: copy.deepcopy(item[field]) for field in fields
                 if item.get(field) not in (None, "", []) and (match is None or match.get(field) in (None, "", []))}
        if match and not match.get("stock_code"):
            patch["stock_code"] = code
        proposed_id = match.get("ipo_id") if match else generate_ipo_id(
            company_name=item["company_name"], stock_code=code, subscription_start=item.get("subscription_start"))
        if match is None and any(row.get("ipo_id") == proposed_id for row in existing):
            reasons.append("generated_ipo_id_collision")
        decision = "review_required" if reasons else ("no_change" if match and not patch else
                                                      "supplement" if match else "new_candidate")
        payload = None
        if decision in {"supplement", "new_candidate"}:
            # Reuse the existing merger on a private copy, retaining the selected ID.
            scratch = copy.deepcopy(market)
            payload = {"stock_code": code, "company_name": match["company_name"] if match else item["company_name"], **patch}
            if match is None:
                payload["listing_track"] = "spac" if is_spac_ipo(item) else "general"
            sources = copy.deepcopy(match.get("sources", {})) if match else {}
            sources.setdefault("schedule_fields", {}).update({key: evidence[key] for key in patch if key in evidence})
            sources["npay_historical_observations"] = [copy.deepcopy(row.get("sources", {}).get("npay", {})) for row in rows]
            latest = max(sources["npay_historical_observations"], key=lambda row: str(row.get("observed_at") or ""))
            sources["npay"] = {**latest, "schedule_source": "npay_historical_aggregate"}
            payload["sources"] = sources
            # Supply the full proven period for identity resolution, including
            # already-saved values; the resolver must not need an identity bypass.
            identity_input = copy.deepcopy(payload)
            for field in ("subscription_start", "subscription_end"):
                if item.get(field):
                    identity_input[field] = item[field]
            merged, review = _apply_observation(scratch, identity_input, source_name="npay")
            if review or merged.get("ipo_id") != proposed_id or any(merged.get(key) != value for key, value in patch.items()):
                reasons.append("existing_merge_result_mismatch")
                decision = "review_required"
            allowed = set(patch) | {"sources", "updated_at"}
            if (match and any(merged.get(key) != value for key, value in match.items() if key not in allowed)):
                reasons.append("retained_record_would_change")
                decision = "review_required"
            if len(scratch.get("ipos", [])) != len(existing) + (0 if match else 1):
                reasons.append("unexpected_record_count_change")
                decision = "review_required"
            for original in existing:
                if match and original is match:
                    continue
                if original not in scratch.get("ipos", []):
                    reasons.append("unrelated_market_record_would_change")
                    decision = "review_required"
        plan.append({"stock_code": code, "company_name": item["company_name"], "observation_count": len(rows),
                     "ipo_id": match.get("ipo_id") if match else None, "proposed_ipo_id": proposed_id,
                     "identity_basis": basis, "decision": decision, "reasons": sorted(set(reasons)),
                     "patch": patch if decision in {"supplement", "new_candidate"} else {},
                     "merge_input": identity_input if decision in {"supplement", "new_candidate"} else None,
                     "field_evidence": evidence, "observations": rows})
    for entry in plan:
        if entry["ipo_id"] and sum(row["ipo_id"] == entry["ipo_id"] for row in plan) > 1:
            entry.update(decision="review_required", patch={}, merge_input=None)
            entry["reasons"].append("multiple_codes_target_same_ipo_id")
    counts = {key: sum(row["decision"] == key for row in plan)
              for key in ("new_candidate", "supplement", "no_change", "review_required")}
    return {"plan": plan, "summary": counts,
            "expected_market_record_changes": counts["new_candidate"] + counts["supplement"],
            "storage_write": False}


def preview_npay_historical_schedules(*, target_date_str: str | None = None,
                                     npay_client: NpayIpoClient | None = None,
                                     prior_preview: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explicit read-only plan; deliberately not part of automatic refresh."""
    from calendar import monthrange
    from app.services.ipo.store import read_market_store_read_only
    target = date.fromisoformat(target_date_str) if target_date_str else datetime.now(KST).date()
    first_month = _shift_month(target.replace(day=1), -3)
    start = first_month.replace(day=min(target.day, monthrange(first_month.year, first_month.month)[1]))
    npay = npay_client or NpayIpoClient()
    market = read_market_store_read_only()
    if prior_preview is not None:
        if prior_preview.get("to") != target.isoformat() or prior_preview.get("from") != start.isoformat():
            raise ValueError("Prior preview period must match the requested period")
        observations = prior_preview.get("observations")
        if observations is None:
            # Accept the original observation-level preview without refetching.
            observations = [row["observation"] for row in prior_preview.get("plan", [])]
        if not isinstance(observations, list) or not observations:
            raise ValueError("Prior preview must include full observations, not aggregate counts")
        result = plan_npay_historical_storage(observations, market, target_date_str=target.isoformat())
        return {"from": start.isoformat(), "to": target.isoformat(),
                "month_statuses": copy.deepcopy(prior_preview.get("month_statuses", {})),
                "observations": copy.deepcopy(observations), **result}
    statuses, observations, seen = {}, [], set()
    month = first_month
    while month <= target:
        last = month.replace(day=monthrange(month.year, month.month)[1])
        key = month.strftime("%Y-%m")
        try:
            rows = npay.fetch_calendar_month(start_date=month.isoformat(), end_date=last.isoformat())
        except Exception as exc:
            statuses[key] = f"source_error ({type(exc).__name__})"
            month = _shift_month(month, 1)
            continue
        statuses[key] = "read_ok"
        for item in rows:
            if not any(_date_in_window(item.get(field), start, target) for field in
                       ("subscription_start", "subscription_end", "expected_listing_date")):
                continue
            signature = (item.get("stock_code"), item.get("subscription_start"),
                         item.get("subscription_end"), item.get("expected_listing_date"))
            if signature not in seen:
                seen.add(signature)
                observations.append(item)
        month = _shift_month(month, 1)
    try:
        completed = npay.fetch_completed_ipos(target_date_str=target.isoformat())
    except Exception as exc:
        statuses["npay_stock_completed"] = f"source_error ({type(exc).__name__})"
    else:
        statuses["npay_stock_completed"] = "read_ok"
        observations.extend(item for item in completed if _date_in_window(item.get("actual_listing_date"), start, target))
    result = plan_npay_historical_storage(observations, market, target_date_str=target.isoformat())
    return {"from": start.isoformat(), "to": target.isoformat(), "month_statuses": statuses,
            "observations": copy.deepcopy(observations), **result}


def _date_in_window(value: object, start: date, end: date) -> bool:
    text = str(value or "")[:10]
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return False
    return start <= parsed <= end


def _relevant_schedule(item: dict[str, Any], start: date, end: date) -> bool:
    return any(
        _date_in_window(item.get(key), start, end)
        for key in (
            "demand_forecast_start", "demand_forecast_end",
            "subscription_start", "subscription_end", "payment_date", "refund_date",
            "expected_listing_date", "actual_listing_date",
        )
    )


def _fetch_dart_equity_feed(dart: DartClient, *, target_date_str: str) -> list[dict[str, Any]]:
    """Read the official OpenDART C001 feed behind DART's offering disclosures.

    The global feed is identity/provenance evidence, not a standalone IPO universe:
    C001 also contains follow-on equity offerings by already-listed companies.
    Schedules become canonical only when the filing can be reconciled to an IPO
    already discovered by KIND, Npay/Naver, 160, or the retained market store.
    """
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    begin = target - timedelta(days=89)
    rows: list[dict[str, Any]] = []
    page_no = 1
    while page_no <= 20:
        payload = dart._request_json(
            "list.json",
            {
                "bgn_de": begin.strftime("%Y%m%d"),
                "end_de": target.strftime("%Y%m%d"),
                "pblntf_ty": "C",
                "pblntf_detail_ty": "C001",
                "last_reprt_at": "N",
                "sort": "date",
                "sort_mth": "desc",
                "page_no": page_no,
                "page_count": 100,
            },
        )
        page_rows = payload.get("list") if isinstance(payload, dict) else None
        if not isinstance(page_rows, list):
            break
        rows.extend(row for row in page_rows if isinstance(row, dict))
        try:
            total_page = int(payload.get("total_page") or 1)
        except (TypeError, ValueError):
            total_page = 1
        if page_no >= total_page:
            break
        page_no += 1
    return rows


def _latest_dart_by_name(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = normalize_company_name(str(row.get("corp_name") or row.get("company_name") or ""))
        if not key:
            continue
        current = latest.get(key)
        row_sort = (str(row.get("rcept_dt") or ""), str(row.get("rcept_no") or ""))
        cur_sort = (str((current or {}).get("rcept_dt") or ""), str((current or {}).get("rcept_no") or ""))
        if current is None or row_sort > cur_sort:
            latest[key] = row
    return latest


def _attach_dart_identity(item: dict[str, Any], dart_by_name: dict[str, dict[str, Any]]) -> None:
    key = normalize_company_name(str(item.get("company_name") or ""))
    filing = dart_by_name.get(key)
    if not filing:
        return
    corp_code = str(filing.get("corp_code") or "").strip()
    stock_code = str(filing.get("stock_code") or "").strip()
    if corp_code and not item.get("corp_code"):
        item["corp_code"] = corp_code
    if stock_code and not item.get("stock_code"):
        item["stock_code"] = stock_code
    item.setdefault("sources", {})["dart_discovery"] = {
        "source": "OpenDART list.json C001",
        "board_reference": "https://dart.fss.or.kr/dsac005/main.do",
        "rcept_no": filing.get("rcept_no"),
        "source_date": filing.get("rcept_dt"),
        "report_nm": filing.get("report_nm"),
        "corp_code": corp_code or None,
        "stock_code": stock_code or None,
        "observed_at": datetime.now(KST).isoformat(),
    }


def _unique_name_match(item: dict[str, Any], existing: list[dict[str, Any]]) -> dict[str, Any] | None:
    incoming_name = normalize_company_name(str(item.get("company_name") or ""))
    if not incoming_name:
        return None
    def same_name(row: dict[str, Any]) -> bool:
        if normalize_company_name(str(row.get("company_name") or "")) == incoming_name:
            return True
        if not is_spac_ipo(item) or not is_spac_ipo(row):
            return False
        # Aliases alone are insufficient: require an exact, complete subscription period.
        if not all(item.get(key) and item.get(key) == row.get(key)
                   for key in ("subscription_start", "subscription_end")):
            return False
        if any(item.get(key) and row.get(key) and item[key] != row[key]
               for key in ("stock_code", "payment_date")):
            return False
        if (item.get("final_offer_price") is not None and row.get("final_offer_price") is not None
                and item["final_offer_price"] != row["final_offer_price"]):
            return False
        return spac_name_key(item) == spac_name_key(row)
    candidates = [row for row in existing if same_name(row)]
    if len(candidates) != 1:
        return None
    target = candidates[0]
    if any(item.get(key) and target.get(key) and item[key] != target[key]
           for key in ("stock_code", "corp_code")):
        return None
    incoming_start = str(item.get("subscription_start") or "")[:10]
    target_start = str(target.get("subscription_start") or "")[:10]
    if incoming_start and target_start and incoming_start != target_start:
        if not _schedule_change_identity_is_supported(item, target):
            return None
    return target


def _schedule_window(ipo: dict[str, Any]) -> tuple[date, date] | None:
    try:
        start = date.fromisoformat(str(ipo.get("subscription_start") or "")[:10])
        end = date.fromisoformat(str(ipo.get("subscription_end") or "")[:10])
    except ValueError:
        return None
    return (start, end) if start <= end else None


def _schedule_is_current_at(ipo: dict[str, Any], observed_at: str) -> bool:
    window = _schedule_window(ipo)
    if window is None:
        return False
    try:
        observed_day = datetime.fromisoformat(observed_at).astimezone(KST).date()
    except ValueError:
        observed_day = datetime.now(KST).date()
    return window[1] >= observed_day


def _schedule_change_identity_is_supported(item: dict[str, Any], target: dict[str, Any]) -> bool:
    """Require offering evidence before a name-only schedule date can move."""
    if any(item.get(key) and target.get(key) and item[key] != target[key]
           for key in ("market", "listing_track", "stock_code", "corp_code")):
        return False
    source_meta = item.get("sources") if isinstance(item.get("sources"), dict) else {}
    trusted_source = any(isinstance(source_meta.get(key), dict) for key in ("npay", "naver_progress", "kind", "dart"))
    if not trusted_source:
        return False

    stable_pairs = (
        ("stock_code", str(item.get("stock_code") or "").strip()),
        ("corp_code", str(item.get("corp_code") or "").strip()),
        ("kind_bz_procs_no", str(item.get("kind_bz_procs_no") or
            ((source_meta.get("kind") or {}).get("kind_bz_procs_no")
             if isinstance(source_meta.get("kind"), dict) else "") or "").strip()),
    )
    if any(value and value == str(target.get(key) or "").strip() for key, value in stable_pairs):
        return True

    # The public Npay list may only confirm a new start date. A name-only match
    # is safe only when the new date still falls in the stored offering window
    # and both published price-band endpoints corroborate the same offering.
    old_window = _schedule_window(target)
    new_start = str(item.get("subscription_start") or "")[:10]
    try:
        parsed_new_start = date.fromisoformat(new_start)
    except ValueError:
        return False
    if old_window is None or not old_window[0] <= parsed_new_start <= old_window[1]:
        return False
    return all(
        item.get(key) not in (None, "")
        and target.get(key) not in (None, "")
        and item.get(key) == target.get(key)
        for key in ("offer_band_low", "offer_band_high")
    )


def _exact_name_candidates(item: dict[str, Any], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    name = normalize_company_name(str(item.get("company_name") or ""))
    if not name:
        return []
    return [row for row in existing
            if normalize_company_name(str(row.get("company_name") or "")) == name]


def _record_schedule_review(
    store: dict[str, Any], item: dict[str, Any], *, source_name: str,
    reason: str, candidate_ids: list[str], observed_at: str,
    observed_schedule: dict[str, Any] | None = None,
) -> None:
    """Keep ambiguous observations reviewable without creating/mutating an IPO."""
    reviews = store.setdefault("schedule_reviews", [])
    if not isinstance(reviews, list):
        reviews = store["schedule_reviews"] = []
    observed_schedule = observed_schedule or {key: item.get(key) for key in (
        "subscription_start", "subscription_end", "payment_date", "refund_date")
        if item.get(key) not in (None, "")}
    normalized_name = normalize_company_name(str(item.get("company_name") or ""))
    existing_review = next((review for review in reviews if isinstance(review, dict)
        and review.get("status") == "review_required"
        and review.get("source") == source_name
        and review.get("normalized_company_name") == normalized_name
        and review.get("observed_schedule") == observed_schedule), None)
    source_map = item.get("sources") if isinstance(item.get("sources"), dict) else {}
    source_key = {"naver": "naver_progress"}.get(source_name, source_name)
    source_details = source_map.get(source_key)
    record = {
        "status": "review_required", "reason": reason, "source": source_name,
        "company_name": str(item.get("company_name") or ""),
        "normalized_company_name": normalized_name,
        "candidate_ipo_ids": list(dict.fromkeys(value for value in candidate_ids if value)),
        "observed_schedule": observed_schedule, "observed_at": observed_at,
        "source_observed_at": source_details.get("observed_at") if isinstance(source_details, dict) else None,
        "source_url": source_details.get("url") if isinstance(source_details, dict) else None,
    }
    if existing_review is None:
        reviews.append(record)
    else:
        existing_review.update(record)


def _set_schedule_reconciliation(
    target: dict[str, Any], item: dict[str, Any], *, source_name: str,
    status: str, reason: str, observed_at: str,
    observed_schedule: dict[str, Any] | None = None,
) -> None:
    if not isinstance(target.get("sources"), dict):
        target["sources"] = {}
    source_map = item.get("sources") if isinstance(item.get("sources"), dict) else {}
    source_key = {"naver": "naver_progress"}.get(source_name, source_name)
    source_details = source_map.get(source_key)
    target["sources"]["schedule_reconciliation"] = {
        "status": status, "reason": reason, "source": source_name,
        "observed_at": observed_at,
        "source_observed_at": source_details.get("observed_at") if isinstance(source_details, dict) else None,
        "source_url": source_details.get("url") if isinstance(source_details, dict) else None,
        "observed_schedule": observed_schedule or {key: item.get(key) for key in (
            "subscription_start", "subscription_end", "payment_date", "refund_date")
            if item.get(key) not in (None, "")},
    }


def _resolve_schedule_reviews(
    store: dict[str, Any], target: dict[str, Any], item: dict[str, Any], *, resolved_at: str,
) -> None:
    reviews = store.get("schedule_reviews")
    if not isinstance(reviews, list):
        return
    name = normalize_company_name(str(item.get("company_name") or ""))
    incoming_start = str(item.get("subscription_start") or "")[:10]
    for review in reviews:
        if (not isinstance(review, dict) or review.get("status") != "review_required"
                or review.get("normalized_company_name") != name):
            continue
        review_start = str((review.get("observed_schedule") or {}).get("subscription_start") or "")[:10]
        if incoming_start and review_start and incoming_start != review_start:
            continue
        review.update({"status": "resolved", "resolved_at": resolved_at,
                       "resolved_ipo_id": target.get("ipo_id")})


def _record_schedule_attempt(
    market: dict[str, Any], *, source_name: str, start: date, end: date,
    attempted_at: str, outcome: str,
) -> None:
    """Record fetch attempts separately from per-field successful evidence."""
    for ipo in market.get("ipos", []):
        if not isinstance(ipo, dict) or not _relevant_schedule(ipo, start, end):
            continue
        if not isinstance(ipo.get("sources"), dict):
            ipo["sources"] = {}
        attempts = ipo["sources"].setdefault("schedule_refresh_attempts", {})
        if not isinstance(attempts, dict):
            attempts = ipo["sources"]["schedule_refresh_attempts"] = {}
        attempts[source_name] = {"last_attempt_at": attempted_at, "outcome": outcome}


def _unique_stock_match(item: dict[str, Any], existing: list[dict[str, Any]]) -> dict[str, Any] | None:
    stock_code = str(item.get("stock_code") or "").strip()
    if not stock_code:
        return None
    candidates = [row for row in existing if str(row.get("stock_code") or "").strip() == stock_code]
    return candidates[0] if len(candidates) == 1 else None


def _known_observation(item: dict[str, Any], existing: list[dict[str, Any]]) -> bool:
    return _unique_stock_match(item, existing) is not None or _unique_name_match(item, existing) is not None


def _stock_code_owner(
    existing: list[dict[str, Any]],
    stock_code: str,
    *,
    exclude: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    code = str(stock_code or "").strip()
    if not code:
        return None
    for row in existing:
        if row is exclude:
            continue
        if str(row.get("stock_code") or "").strip() == code:
            return row
    return None


def _normalize_confirmed_market(value: object) -> str | None:
    raw = str(value or "").strip().upper()
    if raw in {"KOSDAQ", "KSQ"}:
        return "KOSDAQ"
    if raw in {"KOSPI", "STK"}:
        return "KOSPI"
    if raw in {"KONEX", "KNX"}:
        return "KONEX"
    return None


def _promote_verified_market(ipo: dict[str, Any]) -> bool:
    """Promote stored Naver/KRX market consensus into an empty canonical field.

    This is deliberately local-only: it never performs network I/O and never
    overwrites a non-empty canonical market.
    """
    if str(ipo.get("market") or "").strip():
        return False

    sources = ipo.get("sources")
    if not isinstance(sources, dict):
        return False

    naver = sources.get("naver")
    krx = sources.get("krx")
    if not isinstance(naver, dict) or not isinstance(krx, dict):
        return False

    naver_market = _normalize_confirmed_market(naver.get("market_type"))
    krx_market = _normalize_confirmed_market(krx.get("market_code"))
    if not naver_market or naver_market != krx_market:
        return False

    promoted_at = datetime.now(KST).isoformat()
    ipo["market"] = naver_market
    sources["market_confirmation"] = {
        "source": "stored_naver_krx_consensus",
        "naver_market_type": naver.get("market_type"),
        "krx_market_code": krx.get("market_code"),
        "naver_observed_at": naver.get("observed_at"),
        "krx_observed_at": krx.get("observed_at"),
        "promoted_at": promoted_at,
    }
    ipo["updated_at"] = promoted_at
    return True


def _promote_verified_markets(
    market: dict[str, Any],
    *,
    start: date,
    end: date,
) -> int:
    promoted = 0
    for ipo in market.get("ipos", []):
        if not isinstance(ipo, dict):
            continue
        if not _relevant_schedule(ipo, start, end):
            continue
        promoted += int(_promote_verified_market(ipo))
    return promoted


def _source_priority_present(target: dict[str, Any], source_name: str) -> bool:
    sources = target.get("sources") if isinstance(target.get("sources"), dict) else {}
    if source_name in {"naver", "npay"}:
        return False
    if source_name == "metalogos160":
        return bool(
            sources.get("kind")
            or sources.get("dart_schedule")
            or sources.get("naver_progress")
            or sources.get("npay")
        )
    return False


def _apply_observation(store: dict[str, Any], item: dict[str, Any], *, source_name: str) -> tuple[dict[str, Any], bool]:
    """Merge one source observation under the field-level source priority."""
    item = copy.deepcopy(item)
    observed_schedule = {key: item.get(key) for key in (
        "subscription_start", "subscription_end", "payment_date", "refund_date")
        if item.get(key) not in (None, "")}
    incoming_schedule_invalid = False
    date_fields = {"demand_forecast_start", "demand_forecast_end", "subscription_start",
                   "subscription_end", "payment_date", "refund_date",
                   "expected_listing_date", "actual_listing_date"}
    for key in date_fields & item.keys():
        try:
            valid = date.fromisoformat(str(item[key])).isoformat() == item[key]
        except (TypeError, ValueError):
            valid = False
        if not valid:
            item.pop(key)
    price = item.get("final_offer_price")
    if price is not None and (isinstance(price, bool) or not isinstance(price, (int, float))
                              or not 0 < price < float("inf")):
        item.pop("final_offer_price")
    if (item.get("subscription_start") and item.get("subscription_end")
            and item["subscription_start"] > item["subscription_end"]):
        incoming_schedule_invalid = True
        item.pop("subscription_start")
        item.pop("subscription_end")
    existing = store.get("ipos", [])
    observed_at = datetime.now(KST).isoformat()
    if source_name == "metalogos160":
        # A reference issuer match must never be redirected to a different
        # company merely because the provider reports a conflicting stock code.
        target = _unique_name_match(item, existing)
        if target is None or not metalogos_identity_matches(target, item):
            return item, True
    else:
        if item.get("stock_code") and sum(row.get("stock_code") == item["stock_code"]
                                         for row in existing) > 1:
            duplicate_rows = [row for row in existing if row.get("stock_code") == item["stock_code"]]
            for row in duplicate_rows:
                if _schedule_is_current_at(row, observed_at):
                    _set_schedule_reconciliation(
                        row, item, source_name=source_name, status="review_required",
                        reason="duplicate_stock_identifier", observed_at=observed_at,
                        observed_schedule=observed_schedule,
                    )
            _record_schedule_review(store, item, source_name=source_name,
                reason="duplicate_stock_identifier", candidate_ids=[
                    str(row.get("ipo_id") or "") for row in duplicate_rows], observed_at=observed_at,
                observed_schedule=observed_schedule)
            return item, True
        target = _unique_stock_match(item, existing) or _unique_name_match(item, existing)
        if target is None and item.get("corp_code"):
            # A changed offering period must still take the existing record's
            # stop/field protection path, rather than bypass it via store merge.
            corporate_matches = [row for row in existing
                if str(row.get("corp_code") or "").strip() == str(item["corp_code"]).strip()]
            if len(corporate_matches) > 1:
                for row in corporate_matches:
                    if _schedule_is_current_at(row, observed_at):
                        _set_schedule_reconciliation(
                            row, item, source_name=source_name, status="review_required",
                            reason="ambiguous_corporate_identifier", observed_at=observed_at,
                            observed_schedule=observed_schedule,
                        )
                _record_schedule_review(store, item, source_name=source_name,
                    reason="ambiguous_corporate_identifier", candidate_ids=[
                        str(row.get("ipo_id") or "") for row in corporate_matches], observed_at=observed_at,
                    observed_schedule=observed_schedule)
                return item, True
            if corporate_matches:
                target = corporate_matches[0]
    if target is not None and any(item.get(key) and target.get(key) and item[key] != target[key]
                                  for key in ("stock_code", "corp_code")):
        if _schedule_is_current_at(target, observed_at):
            _set_schedule_reconciliation(
                target, item, source_name=source_name, status="review_required",
                reason="conflicting_official_identifier", observed_at=observed_at,
                observed_schedule=observed_schedule,
            )
        _record_schedule_review(store, item, source_name=source_name,
            reason="conflicting_official_identifier",
            candidate_ids=[str(target.get("ipo_id") or "")], observed_at=observed_at,
            observed_schedule=observed_schedule)
        return item, True
    source_meta = item.get("sources", {}).get(
        {"naver": "naver_progress", "dart": "dart_schedule"}.get(source_name, source_name), {})
    if not isinstance(source_meta, dict):
        source_meta = {}

    schedule_conflict = incoming_schedule_invalid
    if target is not None:
        stable_npay_revision = source_name == "npay" and any(
            item.get(key) and item[key] == target.get(key) for key in ("stock_code", "corp_code")
        )
        revised_start_without_end = (
            stable_npay_revision and item.get("subscription_start")
            and item["subscription_start"] != target.get("subscription_start")
            and not item.get("subscription_end")
        )
        merged_start = str(item.get("subscription_start") or target.get("subscription_start") or "")[:10]
        merged_end = str(item.get("subscription_end") or target.get("subscription_end") or "")[:10]
        if merged_start and merged_end and merged_start > merged_end and not revised_start_without_end:
            schedule_conflict = True
            item.pop("subscription_start", None)
            item.pop("subscription_end", None)

    if target is None:
        name_candidates = _exact_name_candidates(item, existing)
        # A name-only collision is kept outside the IPO list for review. It
        # cannot create a second offering or redirect any applicant records.
        if name_candidates or schedule_conflict:
            review_reason = "invalid_schedule" if schedule_conflict else "identity_or_schedule_ambiguous"
            candidate_ids = [str(row.get("ipo_id") or "") for row in name_candidates]
            if (len(name_candidates) == 1 and not any(
                    item.get(key) and name_candidates[0].get(key)
                    and item[key] != name_candidates[0][key]
                    for key in ("stock_code", "corp_code"))
                    and _schedule_is_current_at(name_candidates[0], observed_at)):
                _set_schedule_reconciliation(
                    name_candidates[0], item, source_name=source_name,
                    status="review_required", reason=review_reason,
                    observed_at=observed_at, observed_schedule=observed_schedule,
                )
            _record_schedule_review(
                store, item, source_name=source_name, reason=review_reason,
                candidate_ids=candidate_ids,
                observed_at=observed_at,
                observed_schedule=observed_schedule,
            )
            return item, True

    if schedule_conflict:
        _set_schedule_reconciliation(
            target, item, source_name=source_name, status="review_required",
            reason="schedule_date_conflict", observed_at=observed_at,
            observed_schedule=observed_schedule,
        )
        _record_schedule_review(
            store, item, source_name=source_name, reason="schedule_date_conflict",
            candidate_ids=[str(target.get("ipo_id") or "")], observed_at=observed_at,
            observed_schedule=observed_schedule,
        )

    def field_evidence(key):
        # A history plan groups several observed surfaces. Preserve each field's
        # validated original provenance rather than assigning the last row's URL.
        supplied = item.get("sources", {}).get("schedule_fields", {}).get(key)
        if (source_name == "npay" and source_meta.get("schedule_source") == "npay_historical_aggregate"
                and isinstance(supplied, dict) and supplied.get("source") == "npay"
                and supplied.get("value") == item[key] and supplied.get("observed_at")
                and supplied.get("url") in {"https://stock.naver.com/market/stock/kr/ipo",
                                            "https://ustock.naver.com/service/ipo?schedule=toBeIPOList"}):
            return copy.deepcopy(supplied)
        seen_at = observation_time(source_meta.get("observed_at") or observed_at)
        return {"source": source_name, "value": copy.deepcopy(item[key]),
                "observed_at": seen_at.isoformat() if seen_at else observed_at,
                "url": source_meta.get("url") or (
                    "https://stock.naver.com/market/stock/kr/ipo" if source_name == "naver" else None)}

    def observation_time(value):
        try:
            parsed = datetime.fromisoformat(str(value))
            return parsed.astimezone(KST) if parsed.tzinfo else parsed.replace(tzinfo=KST)
        except ValueError:
            return None

    def primary_price_evidence(previous=None):
        evidence = field_evidence("final_offer_price")
        evidence["source"] = source_name + "_ipo"
        evidence["source_date"] = evidence["observed_at"][:10]
        # Reobserving an unchanged price must not move its score cutoff forward.
        if (isinstance(previous, dict) and previous.get("source") == evidence["source"]
                and previous.get("value") == evidence["value"]
                and previous.get("url") == evidence["url"]):
            return previous
        return evidence

    if target is None:
        if source_name in {"naver", "npay", "kind", "dart"}:
            item.setdefault("sources", {})["schedule_fields"] = {
                key: field_evidence(key) for key in date_fields | {
                    "final_offer_price", "offer_band_low", "offer_band_high", "lead_managers"}
                if item.get(key) not in (None, "", [])}
        if source_name in {"naver", "npay"} and item.get("final_offer_price"):
            item["sources"]["final_offer_price"] = primary_price_evidence()
        saved, review = merge_ipo_record(store, item)
        if review:
            _record_schedule_review(
                store, item, source_name=source_name, reason="identity_or_schedule_ambiguous",
                candidate_ids=[], observed_at=observed_at,
            )
        return saved, review

    previous_subscription_start = target.get("subscription_start")
    previous_reconciliation = target.get("sources", {}).get("schedule_reconciliation") or {}
    protect = _source_priority_present(target, source_name)
    if (source_name != "dart" and target.get("sources", {}).get(
            "dart_schedule_status", {}).get("status") in {"postponed", "withdrawn"}):
        protect = True
    protected_fields = {
        "demand_forecast_start", "demand_forecast_end",
        "subscription_start", "subscription_end", "payment_date", "refund_date",
        "expected_listing_date", "actual_listing_date", "final_offer_price",
        "offer_band_low", "offer_band_high", "lead_managers", "market",
    }
    accepted_fields: set[str] = set()
    for key, value in item.items():
        if key in {"ipo_id", "sources"}:
            continue
        if source_name == "metalogos160":
            if key in {"features", "score"}:
                continue
            if key == "final_offer_price":
                from app.services.ipo.score import normalize_observation_date
                provenance = item.get("sources", {}).get("final_offer_price", {})
                if (provenance.get("source") != "metalogos_160_public_page"
                        or normalize_observation_date(provenance.get("source_date")) is None):
                    continue
        if value in (None, "", []):
            continue
        if schedule_conflict and key in {"subscription_start", "subscription_end"}:
            continue
        evidence = target.get("sources", {}).get("schedule_fields", {}).get(key, {})
        prior_time = observation_time(evidence.get("observed_at"))
        incoming_time = observation_time(source_meta.get("observed_at") or observed_at)
        if (source_name in {"naver", "npay"} and evidence.get("source") in {"naver", "npay"}
                and prior_time and incoming_time and prior_time > incoming_time):
            continue
        if (source_name in {"kind", "dart"} and key in protected_fields
                and evidence.get("source") in {"naver", "npay"}
                and evidence.get("value") == target.get(key)):
            continue
        if protect and key in protected_fields and target.get(key) not in (None, "", []):
            continue
        if (source_name == "npay" and key in _NPAY_CALENDAR_FIELDS and target.get(key) == value
                and schedule_field_confirmed(target, key) and not npay_schedule_field_confirmed(target, key)):
            # A matching Npay observation does not replace official field provenance.
            continue
        if key in {"stock_code", "corp_code"} and target.get(key) not in (None, ""):
            continue
        if key == "stock_code":
            reported_code = str(value or "").strip()
            owner = _stock_code_owner(existing, reported_code, exclude=target)
            if owner is not None:
                target.setdefault("sources", {}).setdefault(
                    "identity_conflicts", {}
                )["stock_code"] = {
                    "reported_stock_code": reported_code,
                    "existing_ipo_id": owner.get("ipo_id"),
                    "source": source_name,
                }
                continue
        target[key] = copy.deepcopy(value)
        accepted_fields.add(key)

    incoming_sources = item.get("sources") if isinstance(item.get("sources"), dict) else {}
    incoming_sources = copy.deepcopy(incoming_sources)
    if source_name == "metalogos160":
        if "final_offer_price" not in accepted_fields:
            incoming_sources.pop("final_offer_price", None)
        else:
            previous = target.get("sources", {}).get("final_offer_price", {})
            incoming = incoming_sources.get("final_offer_price", {})
            # Preserve the first observation of the same field value/page.
            if (previous.get("source") == "metalogos_160_public_page"
                    and previous.get("value") == incoming.get("value")
                    and previous.get("url") == incoming.get("url")):
                incoming_sources["final_offer_price"] = previous
    target.setdefault("sources", {}).update(incoming_sources)
    if source_name in {"naver", "npay"} and "final_offer_price" in accepted_fields:
        target["sources"]["final_offer_price"] = primary_price_evidence(
            target["sources"].get("final_offer_price"))
    if source_name in {"naver", "npay", "kind", "dart"}:
        fields = target["sources"].setdefault("schedule_fields", {})
        for key in accepted_fields & (protected_fields | date_fields):
            fields[key] = field_evidence(key)
    incoming_start = str(item.get("subscription_start") or "")[:10]
    incoming_end = str(item.get("subscription_end") or "")[:10]
    if source_name == "npay":
        missing = target["sources"].get("npay_schedule_missing")
        if isinstance(missing, dict):
            for key in accepted_fields & set(_NPAY_CALENDAR_FIELDS):
                missing.pop(key, None)
            if not missing:
                target["sources"].pop("npay_schedule_missing")

    disputed_fields = set(previous_reconciliation.get("observed_schedule") or {}) & set(_NPAY_CALENDAR_FIELDS)
    if schedule_conflict:
        pass
    elif (source_name == "npay" and previous_reconciliation.get("reason") == "schedule_date_conflict"
          and disputed_fields and disputed_fields <= accepted_fields
          and ("subscription_start" not in disputed_fields or "subscription_end" in accepted_fields)):
        _set_schedule_reconciliation(
            target, item, source_name=source_name, status="verified",
            reason="complete_schedule_observation", observed_at=observed_at,
        )
        _resolve_schedule_reviews(store, target, item, resolved_at=observed_at)
    elif (source_name == "npay" and "subscription_end" in accepted_fields
          and previous_reconciliation.get("reason") == "end_date_not_confirmed"
          and target.get("subscription_start")):
        _set_schedule_reconciliation(
            target, item, source_name=source_name, status="verified",
            reason="complete_schedule_observation", observed_at=observed_at,
        )
    elif incoming_start and incoming_end and target.get("subscription_start") == incoming_start \
            and target.get("subscription_end") == incoming_end:
        _set_schedule_reconciliation(
            target, item, source_name=source_name, status="verified",
            reason="complete_schedule_observation", observed_at=observed_at,
        )
        _resolve_schedule_reviews(store, target, item, resolved_at=observed_at)
    elif (incoming_start and not incoming_end
            and incoming_start != str(previous_subscription_start or "")[:10]
            and target.get("subscription_start") == incoming_start):
        _set_schedule_reconciliation(
            target, item, source_name=source_name, status="partial",
            reason="end_date_not_confirmed", observed_at=observed_at,
        )
    target["updated_at"] = datetime.now(KST).isoformat()
    return target, schedule_conflict


def _kind_items(kind: KindClient, *, target_date_str: str, start: date, end: date,
                snapshot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    if snapshot and snapshot.get("error"):
        if str(snapshot["error"]).startswith("source_unavailable"):
            raise ExternalNetworkDisabled("KIND schedule unavailable")
        raise RuntimeError("KIND schedule read failed")
    rows = (copy.deepcopy(snapshot["items"]) if snapshot and "items" in snapshot else
            kind.fetch_pubofr_schedule_items(
                from_date=(target - timedelta(days=365)).isoformat(),
                to_date=target.isoformat()))
    relevant: list[dict[str, Any]] = []
    observed_at = datetime.now(KST).isoformat()
    for original in rows:
        if not isinstance(original, dict) or not _relevant_schedule(original, start, end):
            continue
        item = copy.deepcopy(original)
        item.setdefault("listing_track", "spac" if is_spac_ipo(item) else "general")
        item.setdefault("sources", {})["kind"] = {
            "schedule_source": "pubofrprogcom",
            "filing_date": item.get("filing_date"),
            "expected_listing_date": item.get("expected_listing_date"),
            "kind_bz_procs_no": item.get("kind_bz_procs_no"),
            "observed_at": observed_at,
        }
        relevant.append(item)
    return relevant


DART_CANDIDATE_WORKERS = 3


def _fetch_dart_schedules(
    market: dict[str, Any], *, dart: DartClient, target_date_str: str,
    start: date, end: date,
) -> dict[str, Any]:
    """Read candidate schedules from a private snapshot; never mutate the market."""
    failed = 0
    candidates = [
        (index, ipo) for index, ipo in enumerate(market.get("ipos", []))
        if isinstance(ipo, dict) and _relevant_schedule(ipo, start, end)
    ]
    if not candidates:
        return {"candidates": [], "failed": 0}

    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    bgn_de = (start - timedelta(days=120)).strftime("%Y%m%d")
    end_de = target.strftime("%Y%m%d")

    corp_by_name: dict[str, dict[str, Any]] = {}
    ambiguous_names: set[str] = set()
    unresolved = [ipo for _, ipo in candidates if not str(ipo.get("corp_code") or "").strip()]
    if unresolved:
        try:
            corp_master = dart.get_corp_code_master()
            for row in corp_master:
                if not isinstance(row, dict):
                    continue
                key = normalize_company_name(str(row.get("corp_name") or ""))
                if key:
                    previous = corp_by_name.get(key)
                    if previous and previous.get("corp_code") != row.get("corp_code"):
                        ambiguous_names.add(key)
                    elif key not in ambiguous_names:
                        corp_by_name[key] = row
            for key in ambiguous_names:
                corp_by_name.pop(key, None)
        except Exception:
            failed += 1


    prepared = []
    for index, ipo in candidates:
        key = normalize_company_name(str(ipo.get("company_name") or ""))
        master_row = corp_by_name.get(key) or {}
        corp_code = str(ipo.get("corp_code") or master_row.get("corp_code") or "").strip()
        prepared.append({"index": index, "master_row": copy.deepcopy(master_row), "corp_code": corp_code})

    def read_candidate(identity):
        result = copy.deepcopy(identity)
        corp_code = result["corp_code"]
        if not corp_code:
            result["status"] = "ignored"
            return result
        try:
            filings = []
            page = 1
            while True:
                filings_resp = dart.get_filing_list(
                    corp_code=corp_code, bgn_de=bgn_de, end_de=end_de,
                    pblntf_ty="", pblntf_detail_ty="", last_reprt_at="N",
                    page_no=page, page_count=100,
                )
                rows = filings_resp.get("list", [])
                if any(str(row.get("corp_code") or corp_code).strip() != corp_code for row in rows):
                    raise ValueError("DART issuer mismatch")
                filings.extend(rows)
                if page >= int(filings_resp.get("total_page") or 1):
                    break
                page += 1
                if page > 20:
                    raise ValueError("DART schedule disclosure pagination limit exceeded")
            # Retain the official stop notice even if estkRs subsequently fails.
            result["restriction"] = dart_schedule_restriction(filings)
            raw_structured = dart.get_equity_registration_statements(
                corp_code=corp_code, bgn_de=bgn_de, end_de=end_de,
            )
            result.update(status="ok", filing=copy.deepcopy(
                select_dart_schedule_filing(filings, raw_structured)),
                raw_structured=copy.deepcopy(raw_structured))
        except Exception as exc:
            result["status"] = "failed"
            cause = exc.__cause__ or exc
            result["failure_reason"] = (
                "api_key_invalid" if isinstance(exc, DartAuthError) else
                "network_disabled" if isinstance(exc, ExternalNetworkDisabled) else
                "network_error" if isinstance(cause, httpx.RequestError) else "refresh_failed")
        return result

    results = []
    # Bound outstanding futures as well as active reads. Within each company,
    # filing and structured requests remain sequential.
    with ThreadPoolExecutor(max_workers=DART_CANDIDATE_WORKERS) as pool:
        for offset in range(0, len(prepared), DART_CANDIDATE_WORKERS):
            futures = [pool.submit(read_candidate, candidate)
                       for candidate in prepared[offset:offset + DART_CANDIDATE_WORKERS]]
            results.extend(future.result() for future in futures)
    return {"candidates": results, "failed": failed}


def _apply_dart_schedules(
    market: dict[str, Any], *, dart: DartClient, target_date_str: str,
    start: date, end: date, prefetched: dict[str, Any] | None = None,
) -> tuple[int, int, int]:
    """Apply read results on the caller thread in original candidate order."""
    reads = prefetched if prefetched is not None else _fetch_dart_schedules(
        copy.deepcopy(market), dart=dart, target_date_str=target_date_str, start=start, end=end)
    matched = ignored = 0
    failed = reads["failed"]
    for result in reads["candidates"]:
        ipo = market["ipos"][result["index"]]
        master_row = result["master_row"]
        corp_code = result["corp_code"]
        if not corp_code:
            ipo.setdefault("sources", {})["dart_schedule_verification"] = {
                "status": "unverified", "reason": "issuer_unresolved"}
            ignored += 1
            continue
        stock_code = str(master_row.get("stock_code") or "").strip()
        if not ipo.get("corp_code"):
            ipo["corp_code"] = corp_code

        stock_code_conflict = None
        if stock_code and not ipo.get("stock_code"):
            stock_code_conflict = _stock_code_owner(
                market.get("ipos", []),
                stock_code,
                exclude=ipo,
            )
            if stock_code_conflict is None:
                ipo["stock_code"] = stock_code

        ipo.setdefault("sources", {})["dart_identity"] = {
            "source": "OpenDART corpCode.xml" if master_row else "stored corp_code",
            "corp_code": corp_code,
            "stock_code": ipo.get("stock_code") or None,
            "reported_stock_code": stock_code or None,
            "stock_code_conflict_ipo_id": (
                stock_code_conflict.get("ipo_id")
                if isinstance(stock_code_conflict, dict)
                else None
            ),
            "observed_at": datetime.now(KST).isoformat(),
        }

        def order(source):
            return (str(source.get("source_date") or "").replace("-", "")[:8],
                    str(source.get("rcept_no") or ""))

        sources = ipo["sources"]
        restriction = result.get("restriction")
        previous_status = sources.get("dart_schedule_status", {})
        previous_schedule = sources.get("dart_schedule", {})
        if restriction and order(restriction) >= max(order(previous_status), order(previous_schedule)):
            sources["dart_schedule_status"] = copy.deepcopy(restriction)

        if result["status"] == "failed":
            sources["dart_schedule_verification"] = {"status": "unverified",
                "reason": result.get("failure_reason", "refresh_failed"), "last_attempt_date": target_date_str}
            failed += 1
            continue
        try:
            filing = result["filing"]
            raw_structured = result["raw_structured"]
            if not filing:
                sources["dart_schedule_verification"] = {"status": "unverified", "reason": "no_linked_filing"}
                ignored += 1
                continue
            filing = copy.deepcopy(filing)
            filing.setdefault("corp_code", corp_code)
            filing.setdefault("corp_name", ipo.get("company_name"))
            if ipo.get("stock_code"):
                filing.setdefault("stock_code", ipo.get("stock_code"))
            item = build_dart_offering_schedule(raw_structured, filing=filing)
            if item and item.get("corp_code") and str(item["corp_code"]).strip() != corp_code:
                raise ValueError("DART structured issuer mismatch")
            if not item or not _relevant_schedule(item, start, end):
                sources["dart_schedule_verification"] = {"status": "unverified", "reason": "no_usable_schedule"}
                ignored += 1
                continue
            status = sources.get("dart_schedule_status", {})
            schedule_source = item["sources"]["dart_schedule"]
            if order(schedule_source) < order(previous_schedule):
                ignored += 1
                continue
            if status.get("status") in {"postponed", "withdrawn"}:
                # Only a newer, structured equity registration with a usable new
                # subscription date can reopen dates; portal refreshes cannot.
                if (order(schedule_source) <= order(status)
                        or "증권신고서" not in str(filing.get("report_nm") or "")
                        or str(item.get("subscription_start") or "").replace("-", "") < order(schedule_source)[0]):
                    ignored += 1
                    continue
            _, review = _apply_observation(market, item, source_name="dart")
            if review:
                raise ValueError("DART offering identity requires review")
            sources["dart_schedule_verification"] = {"status": "verified", "checked_date": target_date_str}
            if status.get("status") in {"postponed", "withdrawn"}:
                sources["dart_schedule_status"] = {"status": "scheduled",
                    "source_date": schedule_source.get("source_date"),
                    "rcept_no": schedule_source.get("rcept_no"),
                    "report_nm": filing.get("report_nm")}
            matched += 1
        except Exception:
            sources["dart_schedule_verification"] = {"status": "unverified", "reason": "dart_schedule_invalid"}
            failed += 1

    return matched, failed, ignored


def _fetch_metalogos_candidates(metalogos, candidates, *, target_date_str):
    names = []
    seen_names = set()
    for ipo in candidates:
        name = str(ipo.get("company_name") or "").strip()
        key = normalize_company_name(name)
        if key and key not in seen_names:
            seen_names.add(key)
            names.append(name)
    if hasattr(metalogos, "fetch_company_items"):
        items = metalogos.fetch_company_items(company_names=names, target_date_str=target_date_str)
    elif hasattr(metalogos, "fetch_company_item"):
        # Compatibility for legacy clients; production uses one shared index.
        items = [item for name in names if (item := metalogos.fetch_company_item(
            company_name=name, target_date_str=target_date_str))]
    else:
        items = metalogos.fetch_calendar_items(target_date_str=target_date_str)
    return [copy.deepcopy(item) for item in items if isinstance(item, dict)
            and any(metalogos_identity_matches(candidate, item) for candidate in candidates)]


def _provider_read(read):
    """Return isolated provider outcome and its own elapsed read duration."""
    began = perf_counter()
    try:
        return {"data": read(), "error": None,
                "elapsed_ms": round((perf_counter() - began) * 1000, 3)}
    except Exception as exc:
        return {"data": None, "error": (
            "source_unavailable (external_network_disabled)" if isinstance(exc, ExternalNetworkDisabled)
            else f"source_error ({type(exc).__name__})"),
            "elapsed_ms": round((perf_counter() - began) * 1000, 3)}


def _npay_stock_observation(item):
    source = (item.get("sources") or {}).get("npay") or {}
    return source.get("url") == NPAY_STOCK_IPO_URL and source.get("schedule_source") == "npay_stock_public_ipo"


def _same_withdrawal_period(stored, observation):
    boundaries = [(stored[key], observation[key]) for key in ("subscription_start", "subscription_end")
                  if stored.get(key) and observation.get(key)]
    return bool(boundaries) and all(old == new for old, new in boundaries)


def _npay_unlisted_schedule_observation(item):
    source = (item.get("sources") or {}).get("npay") or {}
    return source.get("url") == NPAY_IPO_URL and source.get("subscription_status") in {"active", "upcoming"}


def _contrary_npay_observation(withdrawal, observation):
    observed_code = observation.get("stock_code")
    same_issuer = (
        observed_code == withdrawal["stock_code"] if observed_code else (
            _npay_unlisted_schedule_observation(observation)
            and bool(_exact_name_candidates(withdrawal, [observation]))
        )
    )
    return same_issuer and _same_withdrawal_period(withdrawal, observation)


def _record_npay_withdrawals(market, withdrawals, *, today, observed_at,
                             positive_observations=(), unlisted_read_ok=True):
    existing = market["ipos"]
    reviews = 0
    for item in withdrawals:
        matching = _unique_stock_match(item, existing)
        if matching is None and any(row.get("stock_code") == item["stock_code"] for row in existing):
            continue
        if matching is not None:
            candidates = [matching] if _same_withdrawal_period(matching, item) else []
        else:
            # A matching name and dated period can flag a conflict, never
            # resolve two different provider codes or merge their records.
            candidates = [row for row in _exact_name_candidates(item, existing)
                          if row.get("stock_code") and row.get("subscription_start")
                          and row["subscription_start"] == item.get("subscription_start")
                          and _same_withdrawal_period(row, item)]
        if len(candidates) != 1:
            continue
        ipo = candidates[0]
        if ipo.get("actual_listing_date"):
            continue
        sources = ipo.get("sources")
        sources = sources if isinstance(sources, dict) else {}
        marker = sources.get("npay_offering_restriction") or {}
        if matching is None and marker.get("status") == "withdrawn":
            continue
        same_period = marker.get("stock_code") == item["stock_code"] and _same_withdrawal_period(marker, item)
        # Retrieval order is not publication order. Keep contrary evidence
        # until an explicit later offering or corroborated reopening.
        contrary = [
            {"stock_code": row.get("stock_code"),
             "subscription_start": row.get("subscription_start"),
             "subscription_end": row.get("subscription_end"),
             "reported_status": row.get("ipo_status") or row.get("npay_subscription_status"),
             "observed_at": row["sources"]["npay"].get("observed_at"),
             "url": row["sources"]["npay"].get("url")}
            for row in positive_observations if _contrary_npay_observation(item, row)
        ]
        if not contrary and same_period:
            contrary = marker.get("contrary_observations") or []
        periods = {(row.get("subscription_start"), row.get("subscription_end")) for row in withdrawals
                   if row["stock_code"] == item["stock_code"] and _same_withdrawal_period(ipo, row)}
        if matching is None:
            status = "identity_review"
        elif (contrary or len(periods) > 1
              or (not unlisted_read_ok and not (same_period and marker.get("status") == "withdrawn"))):
            status = "source_review"
        else:
            status = "withdrawn"
        official = None
        if len(periods) <= 1:
            official = find_verified_offering_withdrawal(
                normalize_company_name(ipo.get("company_name") or ""),
                ipo.get("stock_code"), item["stock_code"],
                item.get("subscription_start"), item.get("subscription_end"),
            )
        if not official and not any(
            str(row.get(field) or "") >= today for row in (ipo, item) for field in _NPAY_CALENDAR_FIELDS
        ):
            continue
        effective_date = (marker.get("effective_date") if same_period else None) or observed_at[:10]
        if official:
            status = "withdrawn"
            effective_date = datetime.strptime(official["source_date"], "%Y%m%d").date().isoformat()
        reviews += int(status != "withdrawn")
        ipo["sources"] = sources
        sources["npay_offering_restriction"] = {
            "status": status,
            "stock_code": item["stock_code"],
            "reported_status": item["ipo_status"],
            "subscription_start": item.get("subscription_start"),
            "subscription_end": item.get("subscription_end"),
            "observed_at": (item.get("sources", {}).get("npay") or {}).get("observed_at") or observed_at,
            "effective_date": effective_date,
            "url": NPAY_STOCK_IPO_URL,
            "contrary_observations": contrary,
        }
        if official:
            sources["npay_offering_restriction"]["official_withdrawal"] = official
    return reviews


def _npay_new_offering(item, ipo, restriction, withdrawals, positive_observations):
    start, end = item.get("subscription_start"), item.get("subscription_end")
    if (not _npay_stock_observation(item) or naver_ipo_offering_status(item.get("ipo_status")) != "scheduled"
            or item.get("stock_code") != ipo.get("stock_code") or not (start and end and start <= end)):
        return False
    if any(_contrary_npay_observation(stopped, item) for stopped in withdrawals):
        return False
    previous_end = restriction.get("subscription_end")
    if previous_end and start > previous_end:
        return True
    return (not restriction.get("official_withdrawal")
            and restriction.get("stock_code") == item["stock_code"]
            and _same_withdrawal_period(restriction, item) and any(
        _npay_unlisted_schedule_observation(row) and row.get("stock_code") == item["stock_code"]
        and _same_withdrawal_period(item, row) for row in positive_observations
    ))


def _observation_key(item, existing):
    match = _unique_stock_match(item, existing) or _unique_name_match(item, existing)
    if match is not None:
        return ("ipo_id", match.get("ipo_id"))
    if item.get("stock_code"):
        return ("stock_code", item["stock_code"])
    return ("name", normalize_company_name(item.get("company_name") or ""))


def _conflicting_npay_schedules(items, existing):
    values = {}
    for item in items:
        dates = values.setdefault(_observation_key(item, existing), {})
        for field in _NPAY_CALENDAR_FIELDS:
            if item.get(field):
                dates.setdefault(field, set()).add(item[field])
    return {key for key, dates in values.items() if any(len(days) > 1 for days in dates.values())}


def _reconcile_missing_npay_schedules(npay, market, raw_items, *, target, end, attempted_at, statuses):
    """Require both primary reads and complete, date-bounded calendar evidence."""
    existing = market["ipos"]
    candidates = {}
    for ipo in existing:
        sources = ipo.get("sources") or {}
        stock_code = ipo.get("stock_code")
        try:
            canonical_code = normalize_naver_ipo_code(stock_code)
        except NaverIpoClientError:
            continue
        if stock_code != canonical_code or _unique_stock_match(ipo, existing) is not ipo:
            continue
        if (sources.get("identity_conflicts") or sources.get("npay_offering_restriction")
                or (sources.get("schedule_reconciliation") or {}).get("status") == "review_required"):
            continue
        name = normalize_company_name(ipo.get("company_name") or "")
        spac = spac_name_key(ipo) if is_spac_ipo(ipo) else None
        # A code-less row may be this offering. An unresolved name/alias can
        # block a negative conclusion but never supplies identity for a merge.
        if any(not row.get("stock_code") and (
            normalize_company_name(row.get("company_name") or "") == name
            or (spac and is_spac_ipo(row) and spac_name_key(row) == spac)
        ) for row in raw_items if isinstance(row, dict)):
            continue
        fields = sources.get("schedule_fields")
        for field in _NPAY_CALENDAR_FIELDS:
            value = ipo.get(field)
            npay_field = npay_schedule_field_confirmed(ipo, field)
            if (not npay_field and not sources.get("npay")
                    or (field == "expected_listing_date" and ipo.get("actual_listing_date"))
                    or not _date_in_window(value, target, end)
                    or (npay_field and str(fields[field].get("observed_at") or "") >= attempted_at)):
                continue
            month = date.fromisoformat(value[:10]).replace(day=1)
            candidates.setdefault(month, []).append((ipo, field, value))

    snapshots = {}
    failed = 0
    for month in sorted(candidates):
        last = _shift_month(month, 1) - timedelta(days=1)
        status_key = f"npay_calendar_{month:%Y-%m}"
        partial_reason = None
        try:
            rows = npay.fetch_calendar_month(start_date=month.isoformat(), end_date=last.isoformat(),
                                             require_complete=True)
        except NpayIpoCalendarIncomplete as exc:
            rows = exc.observations
            partial_reason = exc.reason
        except Exception as exc:
            statuses[status_key] = f"source_error ({type(exc).__name__})"
            failed += 1
            continue
        if not isinstance(rows, list) or _conflicting_npay_schedules(rows, existing):
            statuses[status_key] = "source_error (ambiguous_calendar_snapshot)"
            failed += 1
            continue
        if partial_reason:
            statuses[status_key] = f"partial ({partial_reason})"
            failed += 1
        else:
            statuses[status_key] = "read_ok"
        snapshots[month] = (last, rows, datetime.now(KST).isoformat())

    reviews = 0
    for month, (last, rows, observed_at) in snapshots.items():
        for ipo, field, old_value in candidates[month]:
            if ipo.get(field) != old_value:
                continue  # A positive observation for another boundary already revised it.
            sources = ipo["sources"]
            fields = sources.get("schedule_fields") or {}
            npay_field = npay_schedule_field_confirmed(ipo, field)
            if npay_field and str(fields[field].get("observed_at") or "") >= attempted_at:
                continue
            calendar_row = next((row for row in rows if row.get("stock_code") == ipo["stock_code"]
                                 and row.get(field)), None)
            if calendar_row is not None:
                # Do not pair a calendar boundary with a conflicting date
                # freshly observed on a primary surface.
                conflicts = [key for key in _NPAY_CALENDAR_FIELDS if calendar_row.get(key)
                             and calendar_row[key] != ipo.get(key)
                             and schedule_field_confirmed(ipo, key)
                             and (not npay_schedule_field_confirmed(ipo, key)
                                  or str(fields[key].get("observed_at") or "") >= attempted_at)]
                schedule = {key: calendar_row[key] for key in _NPAY_CALENDAR_FIELDS if calendar_row.get(key)}
                if conflicts:
                    _set_schedule_reconciliation(
                        ipo, calendar_row, source_name="npay", status="review_required",
                        reason="schedule_date_conflict", observed_at=observed_at,
                        observed_schedule=schedule,
                    )
                    _record_schedule_review(
                        market, calendar_row, source_name="npay", reason="schedule_date_conflict",
                        candidate_ids=[ipo["ipo_id"]], observed_at=observed_at, observed_schedule=schedule,
                    )
                    reviews += 1
                else:
                    _, review = _apply_observation(market, {"stock_code": ipo["stock_code"],
                        "company_name": ipo["company_name"], "sources": calendar_row["sources"],
                        **schedule}, source_name="npay")
                    reviews += int(review)
                continue
            # The issuer's Npay history only enables supplemental lookup.
            # Hiding a date requires Npay provenance for that exact field.
            if not failed and npay_field and fields[field].get("observed_at"):
                sources.setdefault("npay_schedule_missing", {})[field] = {
                    "value": old_value, "reason": "not_observed_in_npay_calendar",
                    "coverage": "explicit_complete_month",
                    "last_observed_at": fields[field]["observed_at"],
                    "last_complete_at": observed_at, "from": month.isoformat(), "to": last.isoformat(),
                }
    return failed, reviews


def discover_and_merge_primary_sources(
    *,
    username: str | None,
    target_date_str: str,
    kind_client: KindClient | None = None,
    naver_client: Any | None = None,
    npay_client: NpayIpoClient | None = None,
    metalogos_client: MetalogosIpoClient | None = None,
    dart_client: DartClient | None = None,
    kind_schedule_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Refresh the shared IPO schedule from Npay's public schedule only.

    Legacy provider arguments remain accepted for source compatibility but are
    intentionally never instantiated or called. Existing records are merged
    in place and are never deleted when Npay returns an empty result or fails.
    """
    del username, kind_client, naver_client, metalogos_client, dart_client, kind_schedule_snapshot
    start, end = _month_window(target_date_str)
    market = copy.deepcopy(read_market_store())
    statuses = {
        "kind_discovery": "not_requested (npay_only_policy)",
        "naver_progress_discovery": "not_requested (npay_only_policy)",
        "metalogos160": "not_requested (npay_only_policy)",
        "dart_schedule": "not_requested (npay_only_policy)",
        "dart_feed": "not_requested (npay_only_policy)",
    }
    timings: dict[str, float] = {}
    attempted_at = datetime.now(KST).isoformat()
    npay = npay_client or NpayIpoClient()
    began = perf_counter()
    try:
        raw_items = npay.fetch_upcoming_ipos(target_date_str=target_date_str)
        if not isinstance(raw_items, list):
            raise TypeError("Npay IPO response must be a list")
    except Exception as exc:
        source_statuses = getattr(npay, "source_statuses", None)
        if isinstance(source_statuses, dict):
            statuses.update(source_statuses)
        status = ("source_unavailable (external_network_disabled)"
                  if isinstance(exc, ExternalNetworkDisabled)
                  else f"source_error ({type(exc).__name__})")
        statuses["npay"] = status
        _record_schedule_attempt(market, source_name="npay", start=start, end=end,
                                 attempted_at=attempted_at, outcome=status)
        write_market_store(market)
        timings["npay_discovery_ms"] = round((perf_counter() - began) * 1000, 3)
        return {
            "status": "preserved", "statuses": statuses, "timings": timings,
            "window_start": start.isoformat(), "window_end": end.isoformat(),
            "total_ipos": len(market.get("ipos", [])), "relevant": 0,
            "review_required": 0, "failed": 1,
        }

    source_statuses = getattr(npay, "source_statuses", None)
    if isinstance(source_statuses, dict):
        statuses.update(source_statuses)
    observed_at = datetime.now(KST).isoformat()
    relevant_items = [
        copy.deepcopy(item) for item in raw_items
        if isinstance(item, dict) and (
            _relevant_schedule(item, start, end)
            or _unique_stock_match(item, market.get("ipos", [])) is not None
            or bool(_exact_name_candidates(item, market.get("ipos", [])))
        )
    ]
    reviews = 0
    # A successful page must not hide failure of the other Npay page.
    source_errors = getattr(npay, "source_errors", None)
    failed = len(source_errors) if isinstance(source_errors, dict) else 0
    failed += sum(str(statuses.get(key, "")).startswith("partial") for key in ("npay_stock", "npay_unlisted"))
    existing = market.get("ipos", [])
    withdrawals = [item for item in raw_items if isinstance(item, dict)
                   and _npay_stock_observation(item) and naver_ipo_offering_status(item.get("ipo_status")) == "withdrawn"
                   and item.get("stock_code")]
    today = max(date.fromisoformat(target_date_str), datetime.now(KST).date()).isoformat()
    positive_observations = [
        item for item in raw_items if isinstance(item, dict) and (
            _npay_unlisted_schedule_observation(item) or (
                _npay_stock_observation(item) and naver_ipo_offering_status(item.get("ipo_status")) == "scheduled"
            )
        )
    ]
    reviews += _record_npay_withdrawals(
        market, withdrawals, today=today, observed_at=observed_at,
        positive_observations=positive_observations, unlisted_read_ok=statuses.get("npay_unlisted") == "read_ok",
    )
    relevant_items = [
        item for item in relevant_items
        if not any(
            (item.get("stock_code") == stopped["stock_code"] or (
                normalize_company_name(item.get("company_name") or "")
                == normalize_company_name(stopped.get("company_name") or "")))
            and (_same_withdrawal_period(item, stopped)
                 or naver_ipo_offering_status(item.get("ipo_status")) == "withdrawn")
            for stopped in withdrawals
        )
    ]
    keys = [_observation_key(item, existing) for item in relevant_items]
    conflicts = _conflicting_npay_schedules(relevant_items, existing)
    for item, key in zip(relevant_items, keys):
        source_meta = item.setdefault("sources", {}).setdefault("npay", {})
        source_meta.setdefault("schedule_source", "npay_unlisted_public_ipo")
        source_meta.setdefault("url", "https://ustock.naver.com/service/ipo?schedule=toBeIPOList")
        source_meta.setdefault("observed_at", observed_at)
        target_ipo = next((ipo for ipo in existing if key == ("ipo_id", ipo["ipo_id"])), None)
        restriction = ((target_ipo or {}).get("sources") or {}).get("npay_offering_restriction")
        if restriction and not _npay_new_offering(item, target_ipo, restriction, withdrawals, positive_observations):
            continue
        if key in conflicts:
            schedule = {field: item[field] for field in _NPAY_CALENDAR_FIELDS if item.get(field)}
            if target_ipo is not None:
                _set_schedule_reconciliation(
                    target_ipo, item, source_name="npay", status="review_required",
                    reason="schedule_date_conflict", observed_at=observed_at, observed_schedule=schedule,
                )
            _record_schedule_review(
                market, item, source_name="npay", reason="schedule_date_conflict",
                candidate_ids=[target_ipo["ipo_id"]] if target_ipo is not None else [],
                observed_at=observed_at, observed_schedule=schedule,
            )
            reviews += 1
            continue
        try:
            saved, review = _apply_observation(market, item, source_name="npay")
            reviews += int(review)
            if (restriction and not review and saved is target_ipo
                    and all(saved.get(key) == item[key] for key in ("subscription_start", "subscription_end"))):
                saved["sources"].pop("npay_offering_restriction", None)
        except Exception:
            failed += 1

    if failed == 0 and all(statuses.get(key) == "read_ok" for key in ("npay_stock", "npay_unlisted")):
        # Historic refresh targets have no authority to retract today's schedule.
        target = max(date.fromisoformat(target_date_str), datetime.now(KST).date())
        calendar_failures, calendar_reviews = _reconcile_missing_npay_schedules(
            npay, market, raw_items, target=target, end=end, attempted_at=attempted_at, statuses=statuses,
        )
        failed += calendar_failures
        reviews += calendar_reviews
    outcome = "read_ok" if failed == 0 else "partial_item_error"
    _record_schedule_attempt(market, source_name="npay", start=start, end=end,
                             attempted_at=attempted_at, outcome=outcome)
    write_market_store(market)
    timings["npay_discovery_ms"] = round((perf_counter() - began) * 1000, 3)
    summary = "sync_partial" if failed else "sync_ok"
    statuses["npay"] = f"{summary} (relevant={len(relevant_items)}, review_required={reviews}, failed={failed})"
    return {
        "status": "partial" if failed else "ok", "statuses": statuses, "timings": timings,
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "total_ipos": len(market.get("ipos", [])), "relevant": len(relevant_items),
        "review_required": reviews, "failed": failed,
        "npay_observed_at": observed_at,
    }
