from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import copy
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from time import perf_counter

from app.services.ipo.dart_client import DartClient
from app.services.ipo.dart_offering_schedule import build_dart_offering_schedule, select_dart_schedule_filing
from app.services.ipo.identity import normalize_company_name
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
    """Merge one source observation under the field-level source priority."""
    existing = store.get("ipos", [])
    if source_name == "metalogos160":
        # A reference issuer match must never be redirected to a different
        # company merely because the provider reports a conflicting stock code.
        target = _unique_name_match(item, existing)
        if target is None or not metalogos_identity_matches(target, item):
            return item, True
    else:
        target = _unique_stock_match(item, existing) or _unique_name_match(item, existing)
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
        if value is None:
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
    target["updated_at"] = datetime.now(KST).isoformat()
    return target, False


def _kind_items(kind: KindClient, *, target_date_str: str, start: date, end: date) -> list[dict[str, Any]]:
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    rows = kind.fetch_pubofr_schedule_items(
        from_date=(start - timedelta(days=90)).isoformat(),
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
    unresolved = [ipo for _, ipo in candidates if not str(ipo.get("corp_code") or "").strip()]
    if unresolved:
        try:
            corp_master = dart.get_corp_code_master()
            for row in corp_master:
                if not isinstance(row, dict):
                    continue
                key = normalize_company_name(str(row.get("corp_name") or ""))
                if key and key not in corp_by_name:
                    corp_by_name[key] = row
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
            filings_resp = dart.get_filing_list(
                corp_code=corp_code, bgn_de=bgn_de, end_de=end_de,
                pblntf_detail_ty="C001", last_reprt_at="N", page_count=100,
            )
            filings = filings_resp.get("list", []) if isinstance(filings_resp, dict) else []
            raw_structured = dart.get_equity_registration_statements(
                corp_code=corp_code, bgn_de=bgn_de, end_de=end_de,
            )
            result.update(status="ok", filing=copy.deepcopy(
                select_dart_schedule_filing(filings, raw_structured)),
                raw_structured=copy.deepcopy(raw_structured))
        except Exception:
            result["status"] = "failed"
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

        if result["status"] == "failed":
            failed += 1
            continue
        try:
            filing = result["filing"]
            raw_structured = result["raw_structured"]
            if not filing:
                ignored += 1
                continue
            filing = copy.deepcopy(filing)
            filing.setdefault("corp_code", corp_code)
            filing.setdefault("corp_name", ipo.get("company_name"))
            if ipo.get("stock_code"):
                filing.setdefault("stock_code", ipo.get("stock_code"))
            item = build_dart_offering_schedule(raw_structured, filing=filing)
            if not item or not _relevant_schedule(item, start, end):
                ignored += 1
                continue
            _apply_observation(market, item, source_name="dart")
            matched += 1
        except Exception:
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
) -> dict[str, Any]:
    """Reconcile the main IPO discovery union into market.json.

    Canonical schedule priority:
      DART/OpenDART + KIND > NAVER/Npay > Metalogos 160 > retained KIS fallback.
    KIS remains in the base orchestrator for cross-check/fallback but can no
    longer suppress discovery from the main sources.
    """
    start, end = _month_window(target_date_str)
    market = copy.deepcopy(read_market_store())
    statuses: dict[str, str] = {}
    timings: dict[str, float] = {}
    metalogos_rows: list[dict[str, Any]] = []

    dart = dart_client or DartClient(username=username)
    dart_rows: list[dict[str, Any]] = []
    dart_by_name: dict[str, dict[str, Any]] = {}
    if dart.is_configured():
        # Schedule reconciliation is intentionally company-scoped. The prior
        # global C001 feed could truncate at the artificial 20-page/2,000-row
        # cap and is not needed once Npay/NAVER/KIND discover issuer identity.
        statuses["dart_feed"] = "not_requested (company_scoped)"
    else:
        statuses["dart_feed"] = "source_unavailable (api_key_missing)"

    kind = kind_client or KindClient()
    npay = npay_client or NpayIpoClient()
    naver = naver_client or NaverIpoDiscoveryClient()

    def timed_read(name, read):
        began = perf_counter()
        try:
            return read()
        finally:
            timings[f"{name}_discovery_ms"] = round((perf_counter() - began) * 1000, 3)

    def naver_read():
        if hasattr(naver, "fetch_ipo_discovery_items"):
            return naver.fetch_ipo_discovery_items()
        return naver.fetch_ipo_progress_items()

    # Only independent external reads overlap. Reconciliation and store writes
    # remain on this thread in canonical source order, under the caller's lock.
    with ThreadPoolExecutor(max_workers=3) as pool:
        reads = {
            "kind": pool.submit(timed_read, "kind", lambda: _kind_items(
                kind, target_date_str=target_date_str, start=start, end=end)),
            "npay": pool.submit(timed_read, "npay", lambda: npay.fetch_upcoming_ipos(
                target_date_str=target_date_str)),
            "naver": pool.submit(timed_read, "naver", naver_read),
        }
        for source, status_key in (("kind", "kind_discovery"), ("npay", "npay"),
                                   ("naver", "naver_progress_discovery")):
            try:
                raw_items = reads[source].result()
                items = [copy.deepcopy(item) for item in raw_items
                         if _relevant_schedule(item, start, end)
                         or (source == "naver" and _known_observation(item, market.get("ipos", [])))]
                reviews = 0
                observed_at = datetime.now(KST).isoformat()
                for item in items:
                    if source == "naver":
                        item.setdefault("sources", {})["naver_progress"] = {
                            "schedule_source": "stock.naver.com ipo progress",
                            "raw_ipo_code": item.get("raw_ipo_code"),
                            "progress_container": item.get("progress_container"),
                            "expected_listing_date": item.get("expected_listing_date"),
                            "market_type": item.get("market"),
                            "observed_at": observed_at,
                        }
                    _attach_dart_identity(item, dart_by_name)
                    _, review = _apply_observation(market, item, source_name=source)
                    reviews += int(review)
                statuses[status_key] = f"sync_ok (relevant={len(items)}, review_required={reviews})"
            except ExternalNetworkDisabled:
                statuses[status_key] = "source_unavailable (external_network_disabled)"
            except Exception as exc:
                statuses[status_key] = f"source_error ({type(exc).__name__})"

    metalogos = metalogos_client or MetalogosIpoClient()
    # Both providers see independent snapshots after initial reconciliation.
    # No worker receives the shared mutable market or persists any result.
    snapshot = copy.deepcopy(market)
    candidates = [ipo for ipo in copy.deepcopy(snapshot["ipos"])
                  if isinstance(ipo, dict) and _relevant_schedule(ipo, start, end)
                  and str(ipo.get("company_name") or "").strip()]
    dart_configured = dart.is_configured()
    parallel_started = perf_counter()
    with ThreadPoolExecutor(max_workers=2) as pool:
        metalogos_future = pool.submit(_provider_read, lambda: _fetch_metalogos_candidates(
            metalogos, candidates, target_date_str=target_date_str))
        dart_future = pool.submit(_provider_read, lambda: _fetch_dart_schedules(
            snapshot, dart=dart, target_date_str=target_date_str, start=start, end=end)
            if dart_configured else None)
        metalogos_result = metalogos_future.result()
        dart_result = dart_future.result()
    timings["primary_provider_parallel_wall_ms"] = round((perf_counter() - parallel_started) * 1000, 3)
    timings["metalogos_discovery_ms"] = metalogos_result["elapsed_ms"]
    timings["dart_schedule_ms"] = dart_result["elapsed_ms"]

    # Completion order is irrelevant: preserve the existing Metalogos then DART
    # reconciliation order and canonical field/provenance authority.
    if metalogos_result["error"]:
        statuses["metalogos160"] = metalogos_result["error"]
    else:
        metalogos_rows = metalogos_result["data"]
        try:
            reviews = 0
            for item in metalogos_rows:
                _, review = _apply_observation(market, item, source_name="metalogos160")
                reviews += int(review)
            statuses["metalogos160"] = (f"sync_ok (matched={len(metalogos_rows)}, "
                                        f"review_required={reviews})")
        except Exception as exc:
            statuses["metalogos160"] = f"source_error ({type(exc).__name__})"

    statuses["dart_identity_attached"] = "company_scoped"
    if not dart_configured:
        statuses["dart_schedule"] = "source_unavailable (api_key_missing)"
    elif dart_result["error"]:
        statuses["dart_schedule"] = dart_result["error"]
    else:
        matched, failed, ignored = _apply_dart_schedules(
            market, dart=dart, target_date_str=target_date_str, start=start, end=end,
            prefetched=dart_result["data"])
        statuses["dart_schedule"] = f"sync_ok (matched={matched}, failed={failed}, ignored={ignored})"

    promoted_markets = _promote_verified_markets(
        market,
        start=start,
        end=end,
    )
    statuses["market_confirmation"] = (
        f"sync_ok (promoted={promoted_markets})"
    )

    from app.services.ipo.score import calculate_wealth_ipo_score
    for ipo in market.get("ipos", []):
        if isinstance(ipo, dict):
            ipo["score"] = calculate_wealth_ipo_score(ipo, market["ipos"])
    write_market_store(market)
    return {
        "statuses": statuses,
        "timings": timings,
        "metalogos_rows": metalogos_rows,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "total_ipos": len(market.get("ipos", [])),
    }
