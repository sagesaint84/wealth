"""Wealth IPO Orchestrator Service.

Coordinates:
1. source availability check (KIS, KIND, DART, KRX)
2. discovery/schedule source (KIS primary, KIND fallback)
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
import asyncio
import logging
import re
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
    extract_document_text_from_zip,
    select_point_in_time_filing,
)
from app.services.ipo.dart_parser import DartSemanticParser
from app.services.ipo.kind_client import KindClient
from app.services.ipo.identity import normalize_company_name
from app.services.ipo.krx_client import KrxClient, KrxClientError, KrxParserError
from app.services.ipo.naver_client import NaverIpoClient, NaverIpoClientError
from app.services.kis_openapi import KISOpenAPI, KISOpenAPIError
from app.services.network_policy import ExternalNetworkDisabled
from app.services.ipo.normalize import normalize_equity_registration_response
from app.services.ipo.notifier import IpoTelegramNotifier
from app.services.ipo.score import calculate_wealth_ipo_score
from app.services.ipo.store import (
    read_market_store,
    upsert_ipo_record,
    write_market_store,
)

logger = logging.getLogger(__name__)


def _kis_schedule_window(target_date_str: str) -> tuple[str, str]:
    """Return the current-month + next-month KIS schedule window."""
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


def _kind_search_names_for_kis(item: dict[str, Any]) -> list[str]:
    """Return conservative KIND search aliases without changing global IPO identity rules."""
    company_name = str(item.get("company_name") or "").strip()
    if not company_name:
        return []

    aliases = [company_name]
    is_spac = item.get("listing_track") == "spac" or "기업인수목적" in company_name or "스팩" in company_name
    if not is_spac:
        return aliases

    def _latinize_prefix(value: str) -> str:
        for korean, latin in (("케이비", "KB"), ("엔에이치", "NH"), ("아이비케이", "IBK")):
            if value.startswith(korean):
                return latin + value[len(korean):]
        return value

    if "기업인수목적" in company_name:
        core = re.sub(r"기업인수목적(?:회사)?$", "", company_name).strip()
        if core:
            aliases.extend([core, f"{core}스팩"])
            latin_core = _latinize_prefix(core)
            if latin_core != core:
                aliases.extend([latin_core, f"{latin_core}스팩"])
    elif "스팩" in company_name:
        prefix, suffix = company_name.split("스팩", 1)
        latin_prefix = _latinize_prefix(prefix)
        if latin_prefix != prefix:
            aliases.append(f"{latin_prefix}스팩{suffix}")

    return list(dict.fromkeys(alias for alias in aliases if alias))


def _kind_candidate_matches_kis(kis_item: dict[str, Any], kind_item: dict[str, Any]) -> bool:
    kis_start = str(kis_item.get("subscription_start") or "")[:10]
    kis_end = str(kis_item.get("subscription_end") or "")[:10]
    kind_start = str(kind_item.get("subscription_start") or "")[:10]
    kind_end = str(kind_item.get("subscription_end") or "")[:10]
    if not kis_start or not kis_end or kis_start != kind_start or kis_end != kind_end:
        return False

    kis_payment = str(kis_item.get("payment_date") or "")[:10]
    kind_payment = str(kind_item.get("payment_date") or "")[:10]
    if kis_payment and kind_payment and kis_payment != kind_payment:
        return False

    kis_price = kis_item.get("final_offer_price")
    kind_price = kind_item.get("final_offer_price")
    if kis_price is not None and kind_price is not None:
        try:
            if float(kis_price) != float(kind_price):
                return False
        except (TypeError, ValueError):
            return False

    kis_name = normalize_company_name(str(kis_item.get("company_name") or ""))
    kind_name = normalize_company_name(str(kind_item.get("company_name") or ""))
    if kis_name == kind_name:
        return True

    if kis_item.get("listing_track") != "spac":
        return False

    aliases = {normalize_company_name(name) for name in _kind_search_names_for_kis(kis_item)}
    return bool(kind_name and kind_name in aliases)


def _find_kind_match_for_kis(kis_item: dict[str, Any], kind_items: list[dict[str, Any]]) -> dict[str, Any] | None:
    matched: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for candidate in kind_items:
        if not _kind_candidate_matches_kis(kis_item, candidate):
            continue
        key = (
            candidate.get("company_name"),
            candidate.get("filing_date"),
            candidate.get("subscription_start"),
            candidate.get("subscription_end"),
            candidate.get("expected_listing_date"),
            candidate.get("kind_bz_procs_no"),
        )
        if key in seen:
            continue
        seen.add(key)
        matched.append(candidate)
    return matched[0] if len(matched) == 1 else None


def _enrich_kis_expected_listing_dates(
    kind: KindClient,
    subscription_items: list[dict[str, Any]],
    *,
    from_date: str,
    to_date: str,
) -> tuple[int, int]:
    """Fill only blank KIS expected listing dates from one unambiguous KIND match.

    Network/parser failures abort before mutating any KIS item so a partial KIND refresh
    cannot leave a mixed source snapshot in memory. Zero/ambiguous matches are simply
    left unresolved.
    """
    planned: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    unresolved = 0

    for item in subscription_items:
        if item.get("expected_listing_date"):
            continue

        candidates: list[dict[str, Any]] = []
        for search_name in _kind_search_names_for_kis(item):
            candidates.extend(
                kind.fetch_pubofr_schedule_items(
                    from_date=from_date,
                    to_date=to_date,
                    corp_name=search_name,
                )
            )

        match = _find_kind_match_for_kis(item, candidates)
        expected = str((match or {}).get("expected_listing_date") or "")[:10]
        if not match or not expected:
            unresolved += 1
            continue
        planned.append((item, match, expected))

    observed_at = datetime.now(KST).isoformat()
    for item, match, expected in planned:
        item["expected_listing_date"] = expected
        sources = item.setdefault("sources", {})
        sources["kind"] = {
            "schedule_source": "pubofrprogcom",
            "match_method": "company_alias+subscription_period",
            "matched_company_name": match.get("company_name"),
            "filing_date": match.get("filing_date"),
            "expected_listing_date": expected,
            "kind_bz_procs_no": match.get("kind_bz_procs_no"),
            "observed_at": observed_at,
        }

    return len(planned), unresolved


def _enrich_kis_expected_listing_dates_from_naver(
    subscription_items: list[dict[str, Any]], naver_items: list[dict[str, Any]]
) -> tuple[int, int]:
    """Fill blank KIS listing dates only from one exact NAVER stock-code match."""
    by_code: dict[str, list[dict[str, Any]]] = {}
    for item in naver_items:
        code = str(item.get("stock_code") or "").strip()
        if code:
            by_code.setdefault(code, []).append(item)

    planned: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    unresolved = 0
    for item in subscription_items:
        if item.get("expected_listing_date"):
            continue
        matches = by_code.get(str(item.get("stock_code") or "").strip(), [])
        if len(matches) != 1:
            unresolved += 1
            continue
        expected = str(matches[0].get("expected_listing_date") or "")[:10]
        if not expected:
            unresolved += 1
            continue
        planned.append((item, matches[0], expected))

    observed_at = datetime.now(KST).isoformat()
    for item, match, expected in planned:
        item["expected_listing_date"] = expected
        item.setdefault("sources", {})["naver_progress"] = {
            "schedule_source": "ipo_progress",
            "ipo_code": match.get("raw_ipo_code"),
            "expected_listing_date": expected,
            "observed_at": observed_at,
        }
    return len(planned), unresolved


def _run_kis_schedule_fetch(kis: KISOpenAPI, from_date: str, to_date: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run KIS async schedule calls from the synchronous daily pipeline."""
    async def _fetch() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        subscriptions = await kis.fetch_ipo_subscription_schedule(from_date, to_date)
        listings = await kis.fetch_listing_schedule(from_date, to_date)
        return subscriptions, listings

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_fetch())
    raise RuntimeError("IPO daily pipeline cannot run KIS schedule fetch inside an active event loop")


def _run_kis_stock_info_fetch(kis: KISOpenAPI, stock_codes: list[str]) -> dict[str, dict[str, Any]]:
    """Run KIS async domestic stock info calls from synchronous pipeline."""
    if not stock_codes:
        return {}
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(kis.fetch_multiple_domestic_stock_info(stock_codes))
    raise RuntimeError("IPO daily pipeline cannot run KIS stock info fetch inside an active event loop")


def run_ipo_daily_pipeline(
    kind_client: KindClient | None = None,
    krx_client: KrxClient | None = None,
    dart_client: DartClient | None = None,
    notifier: IpoTelegramNotifier | None = None,
    target_date_str: str | None = None,
    dry_run: bool = False,
    username: str | None = None,
    kis_client: KISOpenAPI | None = None,
    naver_client: NaverIpoClient | None = None,
    market_only: bool = False,
) -> dict[str, Any]:
    """Runs the daily IPO refresh and notification pipeline."""
    if not target_date_str:
        target_date_str = datetime.now(KST).strftime("%Y-%m-%d")

    sources_status: dict[str, str] = {}

    # 1. Source availability check
    kind = kind_client or KindClient()
    krx = krx_client or KrxClient()
    naver = naver_client or NaverIpoClient()
    dart = dart_client or DartClient()
    kis = kis_client or (KISOpenAPI(username=username) if username else KISOpenAPI())

    # Check DART
    if not dart.is_configured():
        sources_status["dart"] = "source_unavailable (api_key_missing)"
    else:
        sources_status["dart"] = "source_unavailable (implementation_blocker: live DART network disabled)"

    # Check KIS/KIND
    sources_status["kis"] = "source_unavailable (credentials_missing)" if not kis.configured else "pending"
    sources_status["kind"] = "not_requested (market_only)" if market_only else "fallback_not_used"

    # Check KRX & NAVER
    sources_status["krx"] = "pending"
    sources_status["naver"] = "pending"

    # 2. discovery/schedule source: KIS primary, KIND fallback
    kis_sync_ok = False
    market_schedule_rows_synced = False
    schedule_from, schedule_to = _kis_schedule_window(target_date_str)
    if kis.configured:
        try:
            subscription_items, listing_items = _run_kis_schedule_fetch(kis, schedule_from, schedule_to)
            kis_sync_ok = True
            market_schedule_rows_synced = bool(subscription_items)

            subscription_by_code: dict[str, dict[str, Any]] = {}
            listing_events_by_code: dict[str, list[dict[str, Any]]] = {}
            for item in subscription_items:
                stock_code = str(item.get("stock_code") or "").strip()
                if stock_code:
                    subscription_by_code[stock_code] = item

            matched_listing_events = 0
            for listing in listing_items:
                stock_code = str(listing.get("stock_code") or "").strip()
                pub = subscription_by_code.get(stock_code)
                if not pub:
                    continue
                if normalize_company_name(str(pub.get("company_name") or "")) != normalize_company_name(str(listing.get("company_name") or "")):
                    continue
                listing_events_by_code.setdefault(stock_code, []).append(listing)
                matched_listing_events += 1

            blank_listing_count = sum(1 for item in subscription_items if not item.get("expected_listing_date"))
            if subscription_items and blank_listing_count:
                try:
                    naver_progress = naver.fetch_ipo_progress_items()
                    enriched_count, unresolved_count = _enrich_kis_expected_listing_dates_from_naver(
                        subscription_items, naver_progress
                    )
                    sources_status["naver_progress"] = (
                        f"sync_ok (items={len(naver_progress)}, filled={enriched_count}, unresolved={unresolved_count})"
                    )
                except ExternalNetworkDisabled:
                    sources_status["naver_progress"] = "source_unavailable (external_network_disabled)"
                except Exception as e:
                    logger.warning("NAVER expected-listing enrichment error: %s", e)
                    sources_status["naver_progress"] = f"source_error ({e})"
            else:
                sources_status["naver_progress"] = "not_requested (kis_listing_dates_present)"

            review_required_count = 0
            for item in subscription_items:
                stock_code = str(item.get("stock_code") or "").strip()
                events = listing_events_by_code.get(stock_code, [])
                if events:
                    sources = item.setdefault("sources", {})
                    kis_source = sources.setdefault("kis", {})
                    kis_source["listing_events"] = events
                _, review_required = upsert_ipo_record(item)
                review_required_count += int(review_required)

            sources_status["kis"] = (
                f"sync_ok (subscriptions={len(subscription_items)}, "
                f"listing_matches={matched_listing_events}, review_required={review_required_count})"
            )
        except KISOpenAPIError as e:
            logger.warning("KIS IPO schedule sync error: %s", e)
            sources_status["kis"] = f"source_error ({e})"
        except Exception as e:
            logger.warning("KIS IPO schedule sync error: %s", e)
            sources_status["kis"] = f"source_error ({e})"

    use_kind_fallback = not market_only and ((not kis_sync_ok) or (kis_sync_ok and not subscription_items))
    if use_kind_fallback:
        try:
            kind_from, kind_to = _kind_filing_window(target_date_str)
            parsed_items = kind.fetch_pubofr_schedule_items(from_date=kind_from, to_date=kind_to)
            items = [
                item for item in parsed_items
                if _kind_item_relevant_to_schedule(item, schedule_from, schedule_to)
            ]
            market_schedule_rows_synced = bool(items)
            sources_status["kind"] = f"sync_ok (relevant={len(items)}, parsed={len(parsed_items)})"
            observed_at = datetime.now(KST).isoformat()
            for item in items:
                sources = item.setdefault("sources", {})
                sources["kind"] = {
                    "schedule_source": "pubofrprogcom",
                    "filing_date": item.get("filing_date"),
                    "expected_listing_date": item.get("expected_listing_date"),
                    "kind_bz_procs_no": item.get("kind_bz_procs_no"),
                    "observed_at": observed_at,
                }
                upsert_ipo_record(item)
        except ExternalNetworkDisabled:
            sources_status["kind"] = "source_unavailable (external_network_disabled)"
        except Exception as e:
            logger.warning("KIND sync error: %s", e)
            sources_status["kind"] = f"source_error ({e})"

    # 3 & 4. DART structured / filings & parsed features.  Interactive market
    # refreshes intentionally exclude this expensive enrichment and all user data.
    if market_only:
        sources_status["dart"] = "not_requested (market_only)"
    elif not dart.is_configured():
        sources_status["dart"] = "source_unavailable (api_key_missing)"
    else:
        try:
            # Check market store for candidate IPOs needing DART filing/feature sync
            existing_store = read_market_store()
            candidates = [
                ipo for ipo in existing_store.get("ipos", [])
                if ipo.get("corp_code")
            ]

            dart_sync_count = 0
            parser = DartSemanticParser()

            for cand in candidates:
                corp_code = str(cand["corp_code"]).strip()
                sub_start = str(cand.get("subscription_start") or "")[:10]
                # Default score_as_of is day before subscription_start or target_date_str
                score_as_of = sub_start if sub_start else target_date_str

                # Determine 1-year search window prior to score_as_of
                try:
                    dt = datetime.strptime(score_as_of, "%Y-%m-%d").date()
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
                except Exception as exc:
                    logger.debug("Optional estkRs fetch failed for %s: %s", corp_code, exc)

                # 4. Download document ZIP & extract text
                parsed_features: dict[str, Any] = {}
                if rcept_no:
                    try:
                        zip_bytes = dart.download_document_zip(rcept_no)
                        doc_text = extract_document_text_from_zip(zip_bytes)
                        parsed_features = parser.parse_document(
                            doc_text=doc_text,
                            rcept_no=rcept_no,
                            source_date=source_date,
                        )
                    except Exception as exc:
                        logger.warning("DART doc extraction/parsing failed for %s (rcept_no=%s): %s", corp_code, rcept_no, exc)

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
                    upsert_ipo_record(update_payload)
                    dart_sync_count += 1

            if dart_sync_count > 0:
                sources_status["dart"] = "sync_ok"
            else:
                sources_status["dart"] = "transport_ok"
        except NotImplementedError:
            sources_status["dart"] = "implementation_blocker"
        except DartAuthError as e:
            logger.warning("DART auth error: %s", e)
            sources_status["dart"] = f"configuration_error ({e})"
        except Exception as e:
            logger.warning("DART sync error: %s", e)
            sources_status["dart"] = f"source_error ({e})"

    # 5. KRX master data fetch
    krx_master: list[dict[str, Any]] = []
    krx_fetch_ok = False
    try:
        if not hasattr(krx, "fetch_listed_master"):
            raise NotImplementedError("KRX listed master client capability unavailable")
        krx_master = krx.fetch_listed_master()
        krx_fetch_ok = True
        sources_status["krx"] = f"sync_ok (master={len(krx_master)})"
    except ExternalNetworkDisabled:
        sources_status["krx"] = "source_unavailable (external_network_disabled)"
    except NotImplementedError:
        sources_status["krx"] = "implementation_blocker"
    except Exception as e:
        logger.warning("KRX sync error: %s", e)
        sources_status["krx"] = f"source_error ({e})"

    # 5.1 NAVER completed listings fetch
    naver_completed: list[dict[str, Any]] = []
    naver_fetch_ok = False
    try:
        if not hasattr(naver, "fetch_completed_listings"):
            raise NotImplementedError("NAVER IPO completed-listing client capability unavailable")
        naver_completed = naver.fetch_completed_listings()
        naver_fetch_ok = True
        sources_status["naver"] = f"sync_ok (completed={len(naver_completed)})"
    except ExternalNetworkDisabled:
        sources_status["naver"] = "source_unavailable (external_network_disabled)"
    except NotImplementedError:
        sources_status["naver"] = "implementation_blocker"
    except Exception as e:
        logger.warning("NAVER sync error: %s", e)
        sources_status["naver"] = f"source_error ({e})"

    # 6. Reconcile: load existing market store (NEVER overwrite with empty if sources fail)
    market = read_market_store()
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

    # 7. Canonical feature calculation & 8. Score calculation
    for ipo in ipos:
        score_res = calculate_wealth_ipo_score(ipo, ipos)
        ipo["score"] = score_res

    # 9. Untouched application freeze (only for closed subscriptions).
    # This is a daily-pipeline domain action, never a market-only refresh action.
    frozen_count = 0
    if not market_only:
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
    if not market_only:
        apps = get_user_applications(username=username)
        notif = notifier or IpoTelegramNotifier()
        notifications = notif.check_and_notify_events(
            ipos,
            applications=apps,
            target_date_str=target_date_str,
            dry_run=dry_run,
        )

    # 12. Atomic market save (only if we have market store)
    # A failed or unexpectedly empty primary/fallback schedule refresh must not
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
        "sources": sources_status,
        "total_ipos": len(ipos),
        "frozen_applications_count": frozen_count,
        "notifications_sent_count": len(notifications),
        "notifications_sent": notifications,
    }


def refresh_ipo_market(*, username: str | None = None, target_date_str: str | None = None) -> dict[str, Any]:
    """Refresh only shared IPO market data; never notify or mutate applications."""
    return run_ipo_daily_pipeline(
        username=username,
        target_date_str=target_date_str,
        market_only=True,
    )
