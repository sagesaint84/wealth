from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import copy
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from time import perf_counter

from app.services.ipo.dart_client import DartClient, DartAuthError
import httpx
from app.services.ipo.dart_offering_schedule import build_dart_offering_schedule, select_dart_schedule_filing, dart_schedule_restriction
from app.services.ipo.identity import is_spac_ipo, normalize_company_name, spac_name_key
from app.services.ipo.kind_client import KindClient
from app.services.ipo.metalogos_client import MetalogosIpoClient, metalogos_identity_matches
from app.services.ipo.naver_client import NaverIpoClient
from app.services.ipo.naver_discovery import NaverIpoDiscoveryClient
from app.services.ipo.npay_client import NpayIpoClient
from app.services.ipo.store import merge_ipo_record, read_market_store, write_market_store
from app.services.network_policy import ExternalNetworkDisabled


KST = timezone(timedelta(hours=9))


def _month_window(target_date_str: str) -> tuple[date, date]:
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    current = target.replace(day=1)

    def shift(first: date, months: int) -> date:
        serial = first.year * 12 + (first.month - 1) + months
        return date(serial // 12, serial % 12 + 1, 1)

    start = shift(current, -1)
    after = shift(current, 2)
    return start, after - timedelta(days=1)


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
        merged_start = str(item.get("subscription_start") or target.get("subscription_start") or "")[:10]
        merged_end = str(item.get("subscription_end") or target.get("subscription_end") or "")[:10]
        if merged_start and merged_end and merged_start > merged_end:
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
    if schedule_conflict:
        pass
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
    return target, False


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

    observed_at = datetime.now(KST).isoformat()
    relevant_items = [
        copy.deepcopy(item) for item in raw_items
        if isinstance(item, dict) and (
            _relevant_schedule(item, start, end)
            or bool(_exact_name_candidates(item, market.get("ipos", [])))
        )
    ]
    reviews = 0
    failed = 0
    for item in relevant_items:
        source_meta = item.setdefault("sources", {}).setdefault("npay", {})
        source_meta.setdefault("schedule_source", "npay_unlisted_public_ipo")
        source_meta.setdefault("url", "https://ustock.naver.com/service/ipo?schedule=toBeIPOList")
        source_meta.setdefault("observed_at", observed_at)
        try:
            _, review = _apply_observation(market, item, source_name="npay")
            reviews += int(review)
        except Exception:
            failed += 1

    outcome = "read_ok" if failed == 0 else "partial_item_error"
    _record_schedule_attempt(market, source_name="npay", start=start, end=end,
                             attempted_at=attempted_at, outcome=outcome)
    write_market_store(market)
    timings["npay_discovery_ms"] = round((perf_counter() - began) * 1000, 3)
    statuses["npay"] = (
        f"sync_ok (relevant={len(relevant_items)}, review_required={reviews}, failed={failed})"
    )
    return {
        "status": "partial" if failed else "ok", "statuses": statuses, "timings": timings,
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "total_ipos": len(market.get("ipos", [])), "relevant": len(relevant_items),
        "review_required": reviews, "failed": failed,
        "npay_observed_at": observed_at,
    }
