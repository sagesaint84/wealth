from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import copy
from typing import Any

from app.services.ipo.dart_client import DartClient
from app.services.ipo.dart_offering_schedule import build_dart_offering_schedule, select_dart_schedule_filing
from app.services.ipo.identity import normalize_company_name
from app.services.ipo.kind_client import KindClient
from app.services.ipo.metalogos_client import MetalogosIpoClient
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
    for key, value in item.items():
        if key in {"ipo_id", "sources"}:
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

    incoming_sources = item.get("sources") if isinstance(item.get("sources"), dict) else {}
    target.setdefault("sources", {}).update(copy.deepcopy(incoming_sources))
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


def _apply_dart_schedules(
    market: dict[str, Any],
    *,
    dart: DartClient,
    target_date_str: str,
    start: date,
    end: date,
) -> tuple[int, int, int]:
    """Overlay OpenDART schedule facts for only the bounded three-month candidates."""
    matched = 0
    failed = 0
    ignored = 0
    candidates = [
        ipo for ipo in market.get("ipos", [])
        if isinstance(ipo, dict) and _relevant_schedule(ipo, start, end)
    ]
    if not candidates:
        return 0, 0, 0

    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    bgn_de = (start - timedelta(days=120)).strftime("%Y%m%d")
    end_de = target.strftime("%Y%m%d")

    corp_by_name: dict[str, dict[str, Any]] = {}
    unresolved = [ipo for ipo in candidates if not str(ipo.get("corp_code") or "").strip()]
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

    for ipo in candidates:
        key = normalize_company_name(str(ipo.get("company_name") or ""))
        master_row = corp_by_name.get(key) or {}
        corp_code = str(ipo.get("corp_code") or master_row.get("corp_code") or "").strip()
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

        try:
            filings_resp = dart.get_filing_list(
                corp_code=corp_code, bgn_de=bgn_de, end_de=end_de,
                pblntf_detail_ty="C001", last_reprt_at="N", page_count=100,
            )
            filings = filings_resp.get("list", []) if isinstance(filings_resp, dict) else []
            raw_structured = dart.get_equity_registration_statements(
                corp_code=corp_code, bgn_de=bgn_de, end_de=end_de,
            )
            filing = select_dart_schedule_filing(filings, raw_structured)
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

    # The dedicated discovery parser retains Naver identities even before an
    # expected listing date exists. Test doubles/legacy callers may expose the
    # older expected-listing method, which remains a supported fallback here.
    naver = naver_client or NaverIpoDiscoveryClient()
    try:
        if hasattr(naver, "fetch_ipo_discovery_items"):
            raw_items = naver.fetch_ipo_discovery_items()
        else:
            raw_items = naver.fetch_ipo_progress_items()
        items = [
            copy.deepcopy(item) for item in raw_items
            if _relevant_schedule(item, start, end) or _known_observation(item, market.get("ipos", []))
        ]
        reviews = 0
        observed_at = datetime.now(KST).isoformat()
        for item in items:
            item.setdefault("sources", {})["naver_progress"] = {
                "schedule_source": "stock.naver.com ipo progress",
                "raw_ipo_code": item.get("raw_ipo_code"),
                "progress_container": item.get("progress_container"),
                "expected_listing_date": item.get("expected_listing_date"),
                "market_type": item.get("market"),
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

    metalogos = metalogos_client or MetalogosIpoClient()
    try:
        reviews = 0

        candidates = [
            ipo
            for ipo in market.get("ipos", [])
            if isinstance(ipo, dict)
            and _relevant_schedule(ipo, start, end)
            and str(ipo.get("company_name") or "").strip()
        ]

        names: list[str] = []
        seen_names: set[str] = set()

        for ipo in candidates:
            company_name = str(
                ipo.get("company_name") or ""
            ).strip()
            key = normalize_company_name(company_name)

            if not key or key in seen_names:
                continue

            seen_names.add(key)
            names.append(company_name)

        if hasattr(metalogos, "fetch_company_items"):
            items = metalogos.fetch_company_items(
                company_names=names,
                target_date_str=target_date_str,
            )
        elif hasattr(metalogos, "fetch_company_item"):
            items = []
            for company_name in names:
                item = metalogos.fetch_company_item(
                    company_name=company_name,
                    target_date_str=target_date_str,
                )
                if item:
                    items.append(item)
        else:
            # Compatibility for legacy test doubles only.
            items = metalogos.fetch_calendar_items(
                target_date_str=target_date_str
            )

        for item in items:
            _, review = _apply_observation(
                market,
                item,
                source_name="metalogos160",
            )
            reviews += int(review)

        statuses["metalogos160"] = (
            f"sync_ok (matched={len(items)}, "
            f"review_required={reviews})"
        )

    except ExternalNetworkDisabled:
        statuses["metalogos160"] = (
            "source_unavailable (external_network_disabled)"
        )
    except Exception as exc:
        statuses["metalogos160"] = (
            f"source_error ({type(exc).__name__})"
        )

    statuses["dart_identity_attached"] = "company_scoped"

    if dart.is_configured():
        matched, failed, ignored = _apply_dart_schedules(
            market,
            dart=dart,
            target_date_str=target_date_str,
            start=start,
            end=end,
        )
        statuses["dart_schedule"] = (
            f"sync_ok (matched={matched}, failed={failed}, ignored={ignored})"
        )
    else:
        statuses["dart_schedule"] = "source_unavailable (api_key_missing)"

    write_market_store(market)
    return {
        "statuses": statuses,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "total_ipos": len(market.get("ipos", [])),
    }
