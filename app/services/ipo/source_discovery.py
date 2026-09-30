from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import copy
from typing import Any

from app.services.ipo.dart_client import DartClient
from app.services.ipo.identity import normalize_company_name
from app.services.ipo.kind_client import KindClient
from app.services.ipo.metalogos_client import MetalogosIpoClient
from app.services.ipo.naver_client import NaverIpoClient
from app.services.ipo.npay_client import NpayIpoClient
from app.services.ipo.store import merge_ipo_record, read_market_store, write_market_store
from app.services.network_policy import ExternalNetworkDisabled


KST = timezone(timedelta(hours=9))


def _month_window(target_date_str: str) -> tuple[date, date]:
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    start = target.replace(day=1)
    if start.month == 12:
        month_after_next = start.replace(year=start.year + 1, month=2, day=1)
    elif start.month == 11:
        month_after_next = start.replace(year=start.year + 1, month=1, day=1)
    else:
        month_after_next = start.replace(month=start.month + 2, day=1)
    return start, month_after_next - timedelta(days=1)


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
    """Read the official OpenDART C001 feed corresponding to DART issuance filings.

    OpenDART limits searches without corp_code to three months, so discovery uses
    a conservative 90-day window and includes amendments (`last_reprt_at=N`).
    The feed is identity/provenance evidence only; it never creates an IPO from
    a C001 filing by itself because listed-company follow-on offerings share the
    same disclosure category.
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
    candidates = [
        row for row in existing
        if normalize_company_name(str(row.get("company_name") or "")) == incoming_name
    ]
    if len(candidates) != 1:
        return None
    target = candidates[0]
    incoming_start = str(item.get("subscription_start") or "")[:10]
    target_start = str(target.get("subscription_start") or "")[:10]
    if incoming_start and target_start and incoming_start != target_start:
        return None
    return target


def _source_priority_present(target: dict[str, Any], source_name: str) -> bool:
    sources = target.get("sources") if isinstance(target.get("sources"), dict) else {}
    if source_name in {"naver", "npay"}:
        return bool(sources.get("kind") or sources.get("dart_schedule"))
    if source_name == "metalogos160":
        return bool(
            sources.get("kind")
            or sources.get("dart_schedule")
            or sources.get("naver_progress")
            or sources.get("npay")
        )
    return False


def _apply_observation(store: dict[str, Any], item: dict[str, Any], *, source_name: str) -> tuple[dict[str, Any], bool]:
    """Merge an observation while allowing a safe name+same-start reconciliation.

    Existing identity.py correctly rejects generic name-only merges. Discovery has
    a narrower exception: exactly one normalized-name match with a non-conflicting
    subscription start may receive supplemental source data. This is required for
    public schedule sources that do not expose stock/corp identifiers.
    """
    existing = store.get("ipos", [])
    target = _unique_name_match(item, existing)
    if target is None:
        saved, review = merge_ipo_record(store, item)
        return saved, review

    protect = _source_priority_present(target, source_name)
    protected_fields = {
        "demand_forecast_start", "demand_forecast_end",
        "subscription_start", "subscription_end", "payment_date", "refund_date",
        "expected_listing_date", "actual_listing_date", "final_offer_price",
        "offer_band_low", "offer_band_high", "lead_managers", "market",
    }
    for key, value in item.items():
        if key in {"ipo_id", "sources"}:
            continue
        if value is None:
            continue
        if protect and key in protected_fields and target.get(key) not in (None, "", []):
            continue
        if key in {"stock_code", "corp_code"} and target.get(key) not in (None, ""):
            continue
        target[key] = copy.deepcopy(value)

    incoming_sources = item.get("sources") if isinstance(item.get("sources"), dict) else {}
    target.setdefault("sources", {}).update(copy.deepcopy(incoming_sources))
    target["updated_at"] = datetime.now(KST).isoformat()
    return target, False


def _kind_items(kind: KindClient, *, target_date_str: str, start: date, end: date) -> list[dict[str, Any]]:
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    rows = kind.fetch_pubofr_schedule_items(
        from_date=(target - timedelta(days=365)).isoformat(),
        to_date=target.isoformat(),
    )
    relevant: list[dict[str, Any]] = []
    observed_at = datetime.now(KST).isoformat()
    for original in rows:
        if not isinstance(original, dict) or not _relevant_schedule(original, start, end):
            continue
        item = copy.deepcopy(original)
        item.setdefault("sources", {})["kind"] = {
            "schedule_source": "pubofrprogcom",
            "filing_date": item.get("filing_date"),
            "expected_listing_date": item.get("expected_listing_date"),
            "kind_bz_procs_no": item.get("kind_bz_procs_no"),
            "observed_at": observed_at,
        }
        relevant.append(item)
    return relevant


def discover_and_merge_primary_sources(
    *,
    username: str | None,
    target_date_str: str,
    kind_client: KindClient | None = None,
    naver_client: NaverIpoClient | None = None,
    npay_client: NpayIpoClient | None = None,
    metalogos_client: MetalogosIpoClient | None = None,
    dart_client: DartClient | None = None,
) -> dict[str, Any]:
    """Reconcile the main IPO discovery union into market.json.

    Priority for canonical schedule facts:
      DART/KIND official evidence > Naver/Npay public IPO data > 160 supplement > KIS.
    KIS remains in the base orchestrator as a fallback/cross-check, but cannot
    suppress discovery from these sources.
    """
    start, end = _month_window(target_date_str)
    market = copy.deepcopy(read_market_store())
    statuses: dict[str, str] = {}

    dart = dart_client or DartClient(username=username)
    dart_rows: list[dict[str, Any]] = []
    if dart.is_configured():
        try:
            dart_rows = _fetch_dart_equity_feed(dart, target_date_str=target_date_str)
            statuses["dart_feed"] = f"sync_ok (c001={len(dart_rows)})"
        except ExternalNetworkDisabled:
            statuses["dart_feed"] = "source_unavailable (external_network_disabled)"
        except Exception as exc:
            statuses["dart_feed"] = f"source_error ({type(exc).__name__})"
    else:
        statuses["dart_feed"] = "source_unavailable (api_key_missing)"
    dart_by_name = _latest_dart_by_name(dart_rows)

    # Official KIND schedule is applied first and therefore outranks the base KIS snapshot.
    kind = kind_client or KindClient()
    try:
        items = _kind_items(kind, target_date_str=target_date_str, start=start, end=end)
        reviews = 0
        for item in items:
            _attach_dart_identity(item, dart_by_name)
            _, review = _apply_observation(market, item, source_name="kind")
            reviews += int(review)
        statuses["kind_discovery"] = f"sync_ok (relevant={len(items)}, review_required={reviews})"
    except ExternalNetworkDisabled:
        statuses["kind_discovery"] = "source_unavailable (external_network_disabled)"
    except Exception as exc:
        statuses["kind_discovery"] = f"source_error ({type(exc).__name__})"

    # Naver progress contributes authoritative public stock-code/listing observations
    # independently of whether KIS happened to discover the same IPO.
    naver = naver_client or NaverIpoClient()
    try:
        raw_items = naver.fetch_ipo_progress_items()
        items = [copy.deepcopy(item) for item in raw_items if _relevant_schedule(item, start, end)]
        reviews = 0
        observed_at = datetime.now(KST).isoformat()
        for item in items:
            item.setdefault("sources", {})["naver_progress"] = {
                "schedule_source": "stock.naver.com ipo progress",
                "raw_ipo_code": item.get("raw_ipo_code"),
                "expected_listing_date": item.get("expected_listing_date"),
                "observed_at": observed_at,
            }
            _attach_dart_identity(item, dart_by_name)
            _, review = _apply_observation(market, item, source_name="naver")
            reviews += int(review)
        statuses["naver_progress_discovery"] = f"sync_ok (relevant={len(items)}, review_required={reviews})"
    except ExternalNetworkDisabled:
        statuses["naver_progress_discovery"] = "source_unavailable (external_network_disabled)"
    except Exception as exc:
        statuses["naver_progress_discovery"] = f"source_error ({type(exc).__name__})"

    npay = npay_client or NpayIpoClient()
    try:
        items = [item for item in npay.fetch_upcoming_ipos(target_date_str=target_date_str) if _relevant_schedule(item, start, end)]
        reviews = 0
        for item in items:
            _attach_dart_identity(item, dart_by_name)
            _, review = _apply_observation(market, item, source_name="npay")
            reviews += int(review)
        statuses["npay"] = f"sync_ok (relevant={len(items)}, review_required={reviews})"
    except ExternalNetworkDisabled:
        statuses["npay"] = "source_unavailable (external_network_disabled)"
    except Exception as exc:
        statuses["npay"] = f"source_error ({type(exc).__name__})"

    metalogos = metalogos_client or MetalogosIpoClient()
    try:
        items = metalogos.fetch_calendar_items(target_date_str=target_date_str)
        reviews = 0
        for item in items:
            _attach_dart_identity(item, dart_by_name)
            _, review = _apply_observation(market, item, source_name="metalogos160")
            reviews += int(review)
        statuses["metalogos160"] = f"sync_ok (relevant={len(items)}, review_required={reviews})"
    except ExternalNetworkDisabled:
        statuses["metalogos160"] = "source_unavailable (external_network_disabled)"
    except Exception as exc:
        statuses["metalogos160"] = f"source_error ({type(exc).__name__})"

    # Attach official DART filing identity/provenance to already-known schedules.
    attached = 0
    for ipo in market.get("ipos", []):
        before = bool((ipo.get("sources") or {}).get("dart_discovery"))
        _attach_dart_identity(ipo, dart_by_name)
        after = bool((ipo.get("sources") or {}).get("dart_discovery"))
        attached += int(after and not before)
    statuses["dart_identity_attached"] = str(attached)

    write_market_store(market)
    return {
        "statuses": statuses,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "total_ipos": len(market.get("ipos", [])),
    }
