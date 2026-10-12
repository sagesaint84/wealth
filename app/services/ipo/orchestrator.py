"""Wealth IPO Orchestrator Service.

Coordinates:
1. source availability check (KIND, DART, KRX)
2. routine KIND schedule discovery
3. DART structured/filing information
4. DART parsed features
5. Post-listing KRX actual data
6. reconcile with market store
7. canonical feature calculation
8. score calculation
9. untouched application freeze (only for closed subscriptions)
10. schedule / score change detection
11. notification candidates
12. atomic market save
13. Telegram notification dispatch (dry-run supported)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import copy
from contextlib import contextmanager
import logging
import os
import re
import threading
from typing import Any

KST = timezone(timedelta(hours=9))

from app.services.ipo.applications import (
    freeze_untouched_ipo_application,
    get_user_applications,
)
from app.services.ipo.dart_client import (
    DartAuthError,
    DartClient,
    DartClientError,
    DartRateLimitError,
    extract_document_text_from_zip,
    select_point_in_time_filing,
)
from app.services.ipo.dart_parser import DartSemanticParser
from app.services.ipo.kind_client import KindClient
from app.services.ipo.identity import is_spac_ipo, normalize_company_name
from app.services.ipo.krx_client import KrxClient, KrxClientError, KrxParserError
from app.services.ipo.naver_client import NaverIpoClient, NaverIpoClientError
from app.services.network_policy import ExternalNetworkDisabled
from app.services.ipo.normalize import normalize_equity_registration_response
from app.services.ipo.notifier import IpoTelegramNotifier
from app.services.ipo.score import calculate_wealth_ipo_score
from app.services.ipo.store import (
    read_market_store,
    merge_ipo_record,
    write_market_store,
)

logger = logging.getLogger(__name__)
_REFRESH_THREAD_LOCK = threading.Lock()


class IpoRefreshAlreadyRunning(RuntimeError):
    pass


def _clear_spac_offer_bands(ipos: list[dict[str, Any]]) -> int:
    """Remove stale general-IPO offer-band data from SPAC market records.

    The operation is idempotent and only touches the canonical offer-band
    fields and their provenance. Other DART enrichment remains available.
    """
    cleaned = 0
    for ipo in ipos:
        if not is_spac_ipo(ipo):
            continue
        changed = False
        for field in ("offer_band_low", "offer_band_high"):
            if field in ipo:
                ipo.pop(field, None)
                changed = True
        sources = ipo.get("sources")
        if isinstance(sources, dict):
            for field in ("offer_band_low", "offer_band_high"):
                if field in sources:
                    sources.pop(field, None)
                    changed = True
        cleaned += int(changed)
    return cleaned


@contextmanager
def _refresh_file_lock():
    """Non-blocking advisory lock shared by API and host-process refreshes."""
    if not _REFRESH_THREAD_LOCK.acquire(blocking=False):
        raise IpoRefreshAlreadyRunning("IPO_REFRESH_ALREADY_RUNNING")
    from app.services.ipo.store import get_ipo_data_dir
    path = get_ipo_data_dir() / "market.refresh.lock"
    handle = None
    try:
        handle = open(path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise IpoRefreshAlreadyRunning("IPO_REFRESH_ALREADY_RUNNING") from exc
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        if handle is not None:
            handle.close()
        _REFRESH_THREAD_LOCK.release()


def _schedule_window(target_date_str: str) -> tuple[str, str]:
    """Return the current-month + next-month schedule window."""
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    start = target.replace(day=1)
    if start.month == 12:
        month_after_next = start.replace(year=start.year + 1, month=2, day=1)
    elif start.month == 11:
        month_after_next = start.replace(year=start.year + 1, month=1, day=1)
    else:
        month_after_next = start.replace(month=start.month + 2, day=1)
    end = month_after_next - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def _kind_filing_window(target_date_str: str) -> tuple[str, str]:
    """KIND pubofrprogcom filters by filing date, not subscription/listing date."""
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    return (target - timedelta(days=365)).isoformat(), target.isoformat()


def _kind_item_relevant_to_schedule(item: dict[str, Any], from_date: str, to_date: str) -> bool:
    for key in (
        "demand_forecast_start", "demand_forecast_end",
        "subscription_start", "subscription_end", "payment_date",
        "refund_date", "expected_listing_date",
    ):
        value = str(item.get(key) or "")[:10]
        if value and from_date <= value <= to_date:
            return True
    return False


def _resolve_missing_dart_corp_codes(
    ipos: list[dict[str, Any]], corp_master: list[dict[str, Any]],
) -> int:
    """Resolve only unambiguous official DART identities without changing IPO identity.

    Stock-code equality is authoritative.  Name matching is intentionally a
    last resort and may only select exactly one normalized company name.
    """
    by_stock: dict[str, list[dict[str, Any]]] = {}
    by_name: dict[str, list[dict[str, Any]]] = {}
    for entry in corp_master:
        corp_code = str(entry.get("corp_code") or "").strip()
        corp_name = str(entry.get("corp_name") or entry.get("company_name") or "").strip()
        stock_code = str(entry.get("stock_code") or "").strip()
        if not corp_code or not corp_name:
            continue
        if stock_code:
            by_stock.setdefault(stock_code, []).append(entry)
        normalized_name = normalize_company_name(corp_name)
        if normalized_name:
            by_name.setdefault(normalized_name, []).append(entry)

    resolved = 0
    observed_at = datetime.now(KST).isoformat()
    for ipo in ipos:
        if str(ipo.get("corp_code") or "").strip():
            continue
        stock_code = str(ipo.get("stock_code") or "").strip()
        matches = by_stock.get(stock_code, []) if stock_code else []
        if len(matches) == 1:
            match_type = "stock_code"
        elif len(matches) > 1:
            # An ambiguous stock-code master record is never recoverable by
            # the weaker name match.
            continue
        else:
            normalized_name = normalize_company_name(str(ipo.get("company_name") or ""))
            matches = by_name.get(normalized_name, []) if normalized_name else []
            match_type = "company_name_fallback"
        if len(matches) != 1:
            continue
        corp_code = str(matches[0].get("corp_code") or "").strip()
        if not corp_code:
            continue
        ipo["corp_code"] = corp_code
        sources = ipo.setdefault("sources", {})
        sources["dart_corp_code"] = {
            "source": "corpCode.xml",
            "match_type": match_type,
            "observed_at": observed_at,
        }
        resolved += 1
    return resolved


def _dart_error_code(exc: Exception) -> str:
    if isinstance(exc, DartAuthError):
        return "AUTH_ERROR"
    if isinstance(exc, DartRateLimitError):
        return "RATE_LIMIT"
    return "NETWORK_ERROR"


def run_ipo_daily_pipeline(
    kind_client: KindClient | None = None,
    krx_client: KrxClient | None = None,
    dart_client: DartClient | None = None,
    notifier: IpoTelegramNotifier | None = None,
    target_date_str: str | None = None,
    dry_run: bool = False,
    username: str | None = None,
    naver_client: NaverIpoClient | None = None,
    market_only: bool = False,
    user_side_effects: bool = True,
    kind_schedule_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _refresh_file_lock():
        return _run_ipo_daily_pipeline(
            kind_client=kind_client, krx_client=krx_client, dart_client=dart_client,
            notifier=notifier, target_date_str=target_date_str, dry_run=dry_run,
            username=username, naver_client=naver_client,
            market_only=market_only, user_side_effects=user_side_effects,
            kind_schedule_snapshot=kind_schedule_snapshot,
        )


def _run_ipo_daily_pipeline(
    kind_client: KindClient | None = None, krx_client: KrxClient | None = None,
    dart_client: DartClient | None = None, notifier: IpoTelegramNotifier | None = None,
    target_date_str: str | None = None, dry_run: bool = False, username: str | None = None,
    naver_client: NaverIpoClient | None = None,
    market_only: bool = False, user_side_effects: bool = True,
    kind_schedule_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Runs the daily IPO refresh and notification pipeline."""
    if not target_date_str:
        target_date_str = datetime.now(KST).strftime("%Y-%m-%d")

    sources_status: dict[str, str] = {}
    market_only_touched_ids: set[str] = set()
    # Refresh always reconciles one immutable in-memory snapshot and writes once.
    market = copy.deepcopy(read_market_store())

    # Historical snapshots may hold a DART-document number falsely parsed as a
    # general-IPO offer band. Clear that stale data only during enriched
    # refreshes, before score calculation, without changing light refreshes.
    if not market_only:
        _clear_spac_offer_bands(market.get("ipos", []))

    # 1. Source availability check
    kind = kind_client or KindClient()
    krx = krx_client or KrxClient()
    naver = naver_client or NaverIpoClient()
    dart = dart_client or DartClient(username=username)

    # Check DART
    if not dart.is_configured():
        sources_status["dart"] = "source_unavailable (api_key_missing)"
    else:
        sources_status["dart"] = "source_unavailable (implementation_blocker: live DART network disabled)"

    sources_status["kind"] = "pending"

    # Full historical KRX/NAVER scans are intentionally excluded from
    # every routine refresh. They are available only through the explicit
    # Historical Data > KRX full-history reconciliation action.
    sources_status["krx"] = "not_requested (historical_sync_only)"
    sources_status["naver"] = "not_requested (historical_sync_only)"

    # 2. KIND is the routine schedule source in both light and enriched refreshes.
    market_schedule_rows_synced = False
    schedule_from, schedule_to = _schedule_window(target_date_str)
    kind_snapshot: dict[str, Any] = {}
    try:
        kind_from, kind_to = _kind_filing_window(target_date_str)
        parsed_items = kind.fetch_pubofr_schedule_items(from_date=kind_from, to_date=kind_to)
        if not isinstance(parsed_items, list) or any(not isinstance(item, dict) for item in parsed_items):
            raise ValueError("KIND schedule response must be a list of objects")
        # Keep the unmodified provider snapshot for the adapter's wider discovery window.
        kind_snapshot["items"] = copy.deepcopy(parsed_items)
        items = [copy.deepcopy(item) for item in parsed_items
                 if _kind_item_relevant_to_schedule(item, schedule_from, schedule_to)]
        sources_status["kind"] = f"sync_ok (relevant={len(items)}, parsed={len(parsed_items)})"
        observed_at = datetime.now(KST).isoformat()
        schedule_market = copy.deepcopy(market)
        touched_ids: set[str] = set()
        # Share the discovery union's conservative identity reconciliation, including SPAC aliases.
        from app.services.ipo.source_discovery import _apply_observation
        for item in items:
            item.setdefault("listing_track", "spac" if is_spac_ipo(item) else "general")
            item.setdefault("sources", {})["kind"] = {
                "schedule_source": "pubofrprogcom",
                "filing_date": item.get("filing_date"),
                "expected_listing_date": item.get("expected_listing_date"),
                "kind_bz_procs_no": item.get("kind_bz_procs_no"),
                "observed_at": observed_at,
            }
            merged, review_required = _apply_observation(schedule_market, item, source_name="kind")
            if not review_required:
                if merged.get("ipo_id"):
                    touched_ids.add(str(merged["ipo_id"]))
        market = schedule_market
        market_schedule_rows_synced = bool(touched_ids)
        if market_only:
            market_only_touched_ids.update(touched_ids)
    except ExternalNetworkDisabled:
        sources_status["kind"] = "source_unavailable (external_network_disabled)"
        kind_snapshot["error"] = sources_status["kind"]
    except Exception as exc:
        logger.warning("KIND sync error: %s", exc)
        sources_status["kind"] = f"source_error ({type(exc).__name__})"
        kind_snapshot["error"] = sources_status["kind"]

    if kind_schedule_snapshot is not None:
        kind_schedule_snapshot.update(kind_snapshot)

    # 3 & 4. DART structured / filings & parsed features.  Interactive market
    # refreshes intentionally exclude this expensive enrichment and all user data.
    if market_only:
        sources_status["dart"] = "not_requested (market_only)"
    elif not dart.is_configured():
        sources_status["dart"] = "source_unavailable (api_key_missing)"
    else:
        try:
            existing_store = market
            unresolved = [
                ipo for ipo in existing_store.get("ipos", [])
                if not str(ipo.get("corp_code") or "").strip()
                and (str(ipo.get("stock_code") or "").strip() or normalize_company_name(str(ipo.get("company_name") or "")))
            ]
            # corpCode.xml is a large official master; resolve only in the
            # enriched path and only when an IPO still needs a corp code.
            if unresolved:
                corp_master = dart.get_corp_code_master()
                _resolve_missing_dart_corp_codes(existing_store.get("ipos", []), corp_master)

            # Check market store for candidates needing DART filing/feature sync.
            candidates = [
                ipo for ipo in existing_store.get("ipos", [])
                if ipo.get("corp_code")
            ]

            dart_sync_count = 0
            parser = DartSemanticParser()

            for cand in candidates:
                corp_code = str(cand["corp_code"]).strip()
                sub_start = str(cand.get("subscription_start") or "")[:10]
                # Scores may use only information available before subscription opens.
                score_as_of = sub_start if sub_start else target_date_str

                # Determine 1-year search window prior to score_as_of
                try:
                    dt = datetime.strptime(score_as_of, "%Y-%m-%d").date() - timedelta(days=1)
                    bgn_de = (dt - timedelta(days=365)).strftime("%Y%m%d")
                    end_de = dt.strftime("%Y%m%d")
                except Exception:
                    bgn_de = "20210101"
                    end_de = target_date_str.replace("-", "")

                # 1. Fetch filing list
                filings_resp = dart.get_filing_list(
                    corp_code=corp_code,
                    bgn_de=bgn_de,
                    end_de=end_de,
                    pblntf_detail_ty="C001",
                    last_reprt_at="N",
                )
                filings = filings_resp.get("list", [])
                if not filings:
                    continue

                # 2. Point-in-time filing selection
                target_filing = select_point_in_time_filing(filings, score_as_of=score_as_of)
                if not target_filing:
                    continue

                rcept_no = target_filing.get("rcept_no")
                source_date = target_filing.get("rcept_dt", score_as_of)

                # 3. Optional structured data from estkRs
                structured_data: dict[str, Any] = {}
                try:
                    estk_resp = dart.get_equity_registration_statements(
                        corp_code=corp_code,
                        bgn_de=bgn_de,
                        end_de=end_de,
                    )
                    structured_data = normalize_equity_registration_response(estk_resp)
                except Exception:
                    logger.debug("Optional DART structured data fetch failed")

                # 4. Download document ZIP & extract text
                parsed_features: dict[str, Any] = {}
                is_spac = is_spac_ipo(cand)
                offer_band: tuple[float, float] | None = None
                offer_band_from_structured = False
                if not is_spac:
                    offer_band = parser.extract_offer_band_from_structured(structured_data)
                    offer_band_from_structured = offer_band is not None
                if rcept_no:
                    try:
                        zip_bytes = dart.download_document_zip(rcept_no)
                        doc_text = extract_document_text_from_zip(zip_bytes)
                        parsed_features = parser.parse_document(
                            doc_text=doc_text,
                            rcept_no=rcept_no,
                            source_date=source_date,
                        )
                        if not is_spac and offer_band is None:
                            offer_band = parser.extract_offer_band(doc_text)
                    except Exception:
                        logger.warning("DART document extraction/parsing failed")

                if parsed_features or structured_data:
                    dart_meta: dict[str, Any] = {
                        "rcept_no": rcept_no,
                        "source_date": source_date,
                        "report_nm": target_filing.get("report_nm"),
                        "synced_at": datetime.now(KST).isoformat(),
                    }
                    if structured_data:
                        dart_meta["structured"] = structured_data

                    update_payload = {
                        "ipo_id": cand.get("ipo_id"),
                        "company_name": cand.get("company_name"),
                        "corp_code": corp_code,
                        "features": parsed_features,
                        "sources": {
                            "dart": dart_meta,
                        },
                    }
                    if not is_spac and offer_band is not None:
                        low, high = offer_band
                        update_payload["offer_band_low"] = low
                        update_payload["offer_band_high"] = high
                        band_source = {
                            "value": None,
                            "source": "dart_structured" if offer_band_from_structured else "dart_document",
                            "source_date": source_date,
                            "confidence": "high",
                        }
                        update_payload["sources"]["offer_band_low"] = {**band_source, "value": low}
                        update_payload["sources"]["offer_band_high"] = {**band_source, "value": high}
                    merge_ipo_record(market, update_payload)
                    dart_sync_count += 1

            if dart_sync_count > 0:
                sources_status["dart"] = "sync_ok"
            else:
                sources_status["dart"] = "transport_ok"
        except NotImplementedError:
            sources_status["dart"] = "implementation_blocker"
        except DartAuthError as exc:
            logger.warning("DART authentication error")
            sources_status["dart"] = f"configuration_error ({_dart_error_code(exc)})"
        except Exception as exc:
            logger.warning("DART enrichment failed")
            sources_status["dart"] = f"source_error ({_dart_error_code(exc)})"

    # 5. Historical listing confirmation is explicit-only.
    # Do not fetch the all-listed KRX master or NAVER's paginated completed IPO
    # history during normal/manual/daily refreshes. The historical-import dialog
    # owns full-history reconciliation and actually applies reviewed KRX changes.
    krx_master: list[dict[str, Any]] = []
    krx_fetch_ok = False
    naver_completed: list[dict[str, Any]] = []
    naver_fetch_ok = False

    # 6. Reconcile: load existing market store (NEVER overwrite with empty if sources fail)
    ipos = market.get("ipos", [])

    if krx_fetch_ok and naver_fetch_ok:
        krx_by_code: dict[str, list[dict[str, Any]]] = {}
        for row in krx_master:
            c = str(row.get("stock_code") or "").strip()
            if c:
                krx_by_code.setdefault(c, []).append(row)

        naver_by_code: dict[str, list[dict[str, Any]]] = {}
        for row in naver_completed:
            c = str(row.get("stock_code") or "").strip()
            if c:
                naver_by_code.setdefault(c, []).append(row)

        candidates: list[dict[str, Any]] = []
        planned: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]] = []
        ambiguous_count = 0

        for ipo in ipos:
            stock_code = str(ipo.get("stock_code") or "").strip()
            if not stock_code:
                continue
            candidates.append(ipo)

            krx_matches = krx_by_code.get(stock_code, [])
            naver_matches = naver_by_code.get(stock_code, [])

            if len(krx_matches) > 1 or len(naver_matches) > 1:
                ambiguous_count += 1
                continue

            if len(krx_matches) != 1 or len(naver_matches) != 1:
                continue

            krx_row = krx_matches[0]
            naver_row = naver_matches[0]

            # Condition C: ipo_status == "상장"
            if str(naver_row.get("ipo_status") or "").strip() != "상장":
                continue

            # Condition D & E: lcalDate valid YYYY-MM-DD and <= target_date_str
            actual_date = str(naver_row.get("actual_listing_date") or "").strip()
            if not actual_date or not re.match(r"^\d{4}-\d{2}-\d{2}$", actual_date):
                continue
            try:
                actual_dt = datetime.strptime(actual_date, "%Y-%m-%d").date()
                target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
                if actual_dt > target_dt:
                    # Future date guard
                    continue
            except Exception:
                continue

            # Condition G: Market consistency
            naver_mkt = str(naver_row.get("market_type") or "").upper().strip()
            krx_mkt = str(krx_row.get("market_code") or krx_row.get("marketCode") or "").upper().strip()
            if naver_mkt == "KOSDAQ" and krx_mkt == "KSQ":
                pass
            elif naver_mkt == "KOSPI" and krx_mkt == "STK":
                pass
            else:
                # Market mismatch or unsupported market
                continue

            planned.append((ipo, naver_row, krx_row, actual_date))

        # Two-phase mutation: apply all planned promotions
        observed_at = datetime.now(KST).isoformat()
        for ipo, naver_row, krx_row, actual_date in planned:
            ipo["actual_listing_date"] = actual_date
            sources = ipo.setdefault("sources", {})
            sources["naver"] = {
                "listing_confirmation_source": "ipo_progress_LISTING",
                "ipo_code": naver_row.get("raw_ipo_code"),
                "company_name": naver_row.get("company_name"),
                "market_type": naver_row.get("market_type"),
                "ipo_status": naver_row.get("ipo_status"),
                "actual_listing_date": actual_date,
                "gsr_class": naver_row.get("gsr_class"),
                "observed_at": observed_at,
            }
            sources["krx"] = {
                "listing_confirmation_source": "finder_stkisu",
                "short_code": krx_row.get("stock_code"),
                "full_code": krx_row.get("full_code"),
                "company_name": krx_row.get("company_name"),
                "market_code": krx_row.get("market_code") or krx_row.get("marketCode"),
                "observed_at": observed_at,
            }

        sources_status["naver"] = (
            f"sync_ok (completed={len(naver_completed)}, confirmed={len(planned)}, ambiguous={ambiguous_count})"
        )

    # 7. Canonical feature calculation & 8. Score calculation.
    # An interactive market-only refresh must not churn every historical score;
    # recalculate only rows actually touched by the current schedule fetch.
    score_targets = ipos if not market_only else [
        ipo for ipo in ipos
        if str(ipo.get("ipo_id") or "").strip() in market_only_touched_ids
    ]
    for ipo in score_targets:
        score_res = calculate_wealth_ipo_score(ipo, ipos)
        ipo["score"] = score_res

    # 9. Untouched application freeze (only for closed subscriptions).
    # This is a daily-pipeline domain action, never a market-only refresh action.
    frozen_count = 0
    if user_side_effects and not market_only:
        for ipo in ipos:
            ipo_id = ipo.get("ipo_id")
            sub_end = ipo.get("subscription_end")
            if ipo_id and sub_end and sub_end < target_date_str:
                try:
                    frozen = freeze_untouched_ipo_application(username=username, ipo_id=ipo_id)
                    if frozen:
                        frozen_count += 1
                except Exception as e:
                    logger.warning("Failed to freeze untouched app for %s: %s", ipo_id, e)

    # 10. Schedule / score change detection & 11. Notification candidates
    notifications: list[dict[str, Any]] = []
    if user_side_effects and not market_only:
        apps = get_user_applications(username=username)
        notif = notifier or IpoTelegramNotifier(username=username)
        notifications = notif.check_and_notify_events(
            ipos,
            applications=apps,
            target_date_str=target_date_str,
            dry_run=dry_run,
        )

    # 12. Atomic market save (only if we have market store)
    # A failed or unexpectedly empty routine schedule refresh must not
    # touch an already-populated snapshot merely by updating its timestamp.
    if market_only and not market_schedule_rows_synced:
        return {
            "status": "preserved",
            "target_date": target_date_str,
            "dry_run": dry_run,
            "market_only": True,
            "sources": sources_status,
            "total_ipos": len(ipos),
            "frozen_applications_count": 0,
            "notifications_sent_count": 0,
            "notifications_sent": [],
        }
    market["updated_at"] = datetime.now().astimezone().isoformat()
    market["ipos"] = ipos
    write_market_store(market)

    # 13. Return summary
    return {
        "status": "ok",
        "target_date": target_date_str,
        "dry_run": dry_run,
        "market_only": market_only,
        "user_side_effects": bool(user_side_effects and not market_only),
        "sources": sources_status,
        "total_ipos": len(ipos),
        "frozen_applications_count": frozen_count,
        "notifications_sent_count": len(notifications),
        "notifications_sent": notifications,
    }


def refresh_ipo_market(*, username: str | None = None, target_date_str: str | None = None,
                       kind_schedule_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Refresh only shared IPO market data; never notify or mutate applications."""
    return run_ipo_daily_pipeline(
        username=username,
        target_date_str=target_date_str,
        market_only=True,
        kind_schedule_snapshot=kind_schedule_snapshot,
    )


def refresh_ipo_market_enriched(
    *, username: str | None = None, target_date_str: str | None = None,
    kind_schedule_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Refresh and score the shared market store without user-domain effects.

    ``username`` is only a credential-resolution context for shared sources.
    This mode never reads or mutates IPO applications and never sends event
    notifications.
    """
    return run_ipo_daily_pipeline(
        username=username,
        target_date_str=target_date_str,
        market_only=False,
        user_side_effects=False,
        kind_schedule_snapshot=kind_schedule_snapshot,
    )
