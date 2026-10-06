from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from time import perf_counter

from app.services.ipo import orchestrator as _base
from app.services.ipo.dart_client import DartClient, extract_document_text_from_zip, select_point_in_time_filing
from app.services.ipo.dart_parser import DartSemanticParser
from app.services.ipo.identity import is_spac_ipo
from app.services.ipo.metalogos_reference_refresh import refresh_missing_metalogos_references
from app.services.ipo.normalize import normalize_equity_registration_response
from app.services.ipo.score import calculate_wealth_ipo_score
from app.services.ipo.source_discovery import discover_and_merge_primary_sources
from app.services.ipo.store import merge_ipo_record, read_market_store, write_market_store


KST = timezone(timedelta(hours=9))
_BASE_REFRESH_MARKET = _base.refresh_ipo_market
_BASE_REFRESH_ENRICHED = _base.refresh_ipo_market_enriched
_DISCOVERY_PRIORITY = "DART/KIND + NAVER/Npay > Metalogos160 > KIS fallback"
_MAIN_DISCOVERY_KEYS = ("dart_schedule", "kind_discovery", "naver_progress_discovery", "npay")
_INTERACTIVE_SCORE_RECOVERY_LIMIT = 4
_INTERACTIVE_SCORE_RECOVERY_MAX_AGE_DAYS = 14


def _target_date(target_date_str: str | None) -> str:
    return target_date_str or datetime.now(KST).strftime("%Y-%m-%d")


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
    try:
        parsed = date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return False
    return start <= parsed <= end


def _is_target_candidate(ipo: dict[str, Any], start: date, end: date) -> bool:
    return any(
        _date_in_window(ipo.get(key), start, end)
        for key in (
            "demand_forecast_start", "demand_forecast_end",
            "subscription_start", "subscription_end", "payment_date", "refund_date",
            "expected_listing_date", "actual_listing_date",
        )
    )


def _score_needs_recovery(ipo: dict[str, Any]) -> bool:
    if is_spac_ipo(ipo):
        return False
    score = ipo.get("score")
    if not isinstance(score, dict):
        return True
    if str(score.get("status") or "") == "NOT_APPLICABLE":
        return False
    return score.get("is_calculating") is True or score.get("score") is None


def _interactive_score_recovery_candidates(
    ipos: list[dict[str, Any]],
    *,
    target_date_str: str,
) -> list[dict[str, Any]]:
    """Return only near-term IPOs whose point-in-time score can now be completed.

    Interactive refresh must stay bounded. Deep DART parsing is therefore
    limited to unscored, non-SPAC IPOs whose subscription cutoff has arrived,
    and stale subscriptions older than two weeks are left to scheduled/full
    refresh.
    """
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    oldest = target - timedelta(days=_INTERACTIVE_SCORE_RECOVERY_MAX_AGE_DAYS)
    eligible: list[tuple[date, dict[str, Any]]] = []

    for ipo in ipos:
        if not _score_needs_recovery(ipo):
            continue
        raw_start = str(ipo.get("subscription_start") or "")[:10]
        try:
            subscription_start = date.fromisoformat(raw_start)
        except ValueError:
            continue
        score_cutoff = subscription_start - timedelta(days=1)
        if score_cutoff > target or subscription_start < oldest:
            continue
        eligible.append((subscription_start, ipo))

    eligible.sort(key=lambda pair: (abs((pair[0] - target).days), pair[0]))
    return [ipo for _subscription_start, ipo in eligible]


def _targeted_dart_enrichment(
    *,
    username: str | None,
    target_date_str: str,
    score_recovery_only: bool = False,
    max_candidates: int | None = None,
) -> dict[str, Any]:
    """Refresh DART score features for a bounded set of nearby IPOs.

    The schedule discovery path may use current official amendments, while this
    score path keeps the stricter pre-subscription point-in-time rule. Normal
    interactive refresh uses the recovery-only mode with a hard candidate cap;
    scheduled/full refresh keeps the broader three-month mode.
    """
    dart = DartClient(username=username)
    if not dart.is_configured():
        return {"status": "source_unavailable (api_key_missing)", "candidates": 0, "enriched": 0}

    market = read_market_store()
    ipos = market.get("ipos", []) if isinstance(market.get("ipos"), list) else []
    start, end = _month_window(target_date_str)
    candidates = [ipo for ipo in ipos if isinstance(ipo, dict) and _is_target_candidate(ipo, start, end)]
    if score_recovery_only:
        candidates = _interactive_score_recovery_candidates(
            candidates,
            target_date_str=target_date_str,
        )
    if max_candidates is not None:
        candidates = candidates[:max(0, int(max_candidates))]

    unresolved = [
        ipo for ipo in candidates
        if not str(ipo.get("corp_code") or "").strip()
        and (str(ipo.get("stock_code") or "").strip() or str(ipo.get("company_name") or "").strip())
    ]
    if unresolved:
        try:
            corp_master = dart.get_corp_code_master()
            _base._resolve_missing_dart_corp_codes(unresolved, corp_master)
        except Exception:
            pass

    parser = DartSemanticParser()
    enriched = 0
    failed = 0
    skipped = 0
    for cand in candidates:
        corp_code = str(cand.get("corp_code") or "").strip()
        sub_start = str(cand.get("subscription_start") or "")[:10]
        if not corp_code or not sub_start:
            skipped += 1
            continue
        try:
            score_day = datetime.strptime(sub_start, "%Y-%m-%d").date() - timedelta(days=1)
        except ValueError:
            skipped += 1
            continue
        bgn_de = (score_day - timedelta(days=365)).strftime("%Y%m%d")
        end_de = score_day.strftime("%Y%m%d")

        try:
            filings_resp = dart.get_filing_list(
                corp_code=corp_code,
                bgn_de=bgn_de,
                end_de=end_de,
                pblntf_detail_ty="C001",
                last_reprt_at="N",
            )
            filings = filings_resp.get("list", []) if isinstance(filings_resp, dict) else []
            target_filing = select_point_in_time_filing(filings, score_as_of=sub_start)
            if not target_filing:
                skipped += 1
                continue
            rcept_no = target_filing.get("rcept_no")
            source_date = target_filing.get("rcept_dt", sub_start)

            structured_data: dict[str, Any] = {}
            try:
                structured_data = normalize_equity_registration_response(
                    dart.get_equity_registration_statements(
                        corp_code=corp_code,
                        bgn_de=bgn_de,
                        end_de=end_de,
                    )
                )
            except Exception:
                structured_data = {}

            parsed_features: dict[str, Any] = {}
            post_offer_shares: int | None = None
            offer_band: tuple[float, float] | None = None
            offer_band_from_structured = False
            is_spac = is_spac_ipo(cand)
            if not is_spac:
                offer_band = parser.extract_offer_band_from_structured(structured_data)
                offer_band_from_structured = offer_band is not None

            if rcept_no:
                zip_bytes = dart.download_document_zip(rcept_no)
                doc_text = extract_document_text_from_zip(zip_bytes)
                parsed_features = parser.parse_document(
                    doc_text=doc_text,
                    rcept_no=rcept_no,
                    source_date=source_date,
                )
                if not is_spac:
                    post_offer_shares = parser.extract_post_offer_shares(doc_text)
                if not is_spac and offer_band is None:
                    offer_band = parser.extract_offer_band(doc_text)

            if not parsed_features and not structured_data and offer_band is None and post_offer_shares is None:
                skipped += 1
                continue

            dart_meta: dict[str, Any] = {
                "rcept_no": rcept_no,
                "source_date": source_date,
                "report_nm": target_filing.get("report_nm"),
                "synced_at": datetime.now(KST).isoformat(),
                "interactive_targeted": True,
            }
            if structured_data:
                dart_meta["structured"] = structured_data
            update_payload: dict[str, Any] = {
                "ipo_id": cand.get("ipo_id"),
                "company_name": cand.get("company_name"),
                "corp_code": corp_code,
                "features": parsed_features,
                "sources": {"dart": dart_meta},
            }
            if not is_spac and post_offer_shares is not None:
                update_payload["post_offer_shares"] = post_offer_shares
                update_payload["sources"]["post_offer_shares"] = {
                    "source": "dart_document",
                    "source_date": source_date,
                    "rcept_no": rcept_no,
                    "confidence": "high",
                }
            if not is_spac and offer_band is not None:
                low, high = offer_band
                update_payload["offer_band_low"] = low
                update_payload["offer_band_high"] = high
                band_source = {
                    "source": "dart_structured" if offer_band_from_structured else "dart_document",
                    "source_date": source_date,
                    "confidence": "high",
                }
                update_payload["sources"]["offer_band_low"] = {**band_source, "value": low}
                update_payload["sources"]["offer_band_high"] = {**band_source, "value": high}
            merge_ipo_record(market, update_payload)
            enriched += 1
        except Exception:
            failed += 1
            continue

    for ipo in ipos:
        if isinstance(ipo, dict):
            ipo["score"] = calculate_wealth_ipo_score(ipo, ipos)
    write_market_store(market)
    return {
        "status": "ok" if failed == 0 else "partial",
        "mode": "score_recovery" if score_recovery_only else "bounded_full",
        "candidates": len(candidates),
        "enriched": enriched,
        "failed": failed,
        "skipped": skipped,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
    }


def _record_metalogos_reference_status(
    supplement: dict[str, Any],
    reference: dict[str, Any],
) -> None:
    statuses = supplement.setdefault("statuses", {})
    statuses["metalogos160_reference_fallback"] = (
        f"{reference.get('status', 'unknown')} "
        f"(matched={reference.get('matched', 0)}, "
        f"unmatched={reference.get('unmatched', 0)})"
    )


def _run_supplement_and_targeted(*, username: str | None, target_date_str: str) -> tuple[dict[str, Any], dict[str, Any]]:
    supplement: dict[str, Any] = {}
    targeted: dict[str, Any] = {}
    try:
        with _base._refresh_file_lock():
            supplement = discover_and_merge_primary_sources(
                username=username,
                target_date_str=target_date_str,
            )
            reference = refresh_missing_metalogos_references(
                target_date_str=target_date_str,
                prefetched_rows=supplement.get("metalogos_rows", []),
            )
            _record_metalogos_reference_status(supplement, reference)
            targeted = _targeted_dart_enrichment(
                username=username,
                target_date_str=target_date_str,
            )
    except _base.IpoRefreshAlreadyRunning:
        supplement = {"statuses": {"supplemental": "busy"}}
        targeted = {"status": "busy"}
    return supplement, targeted


def _main_discovery_succeeded(supplement: dict[str, Any]) -> bool:
    statuses = supplement.get("statuses") if isinstance(supplement.get("statuses"), dict) else {}
    return any(str(statuses.get(key) or "").startswith("sync_ok") for key in _MAIN_DISCOVERY_KEYS)


def _merge_refresh_result(
    result: dict[str, Any] | None,
    supplement: dict[str, Any],
    targeted: dict[str, Any],
) -> dict[str, Any]:
    output = dict(result or {})
    base_status = str(output.get("status") or "")
    output.setdefault("sources", {}).update(supplement.get("statuses") or {})
    output["targeted_dart"] = targeted
    output["discovery_priority"] = _DISCOVERY_PRIORITY
    output["total_ipos"] = supplement.get("total_ipos", output.get("total_ipos"))
    if base_status and base_status != "ok" and _main_discovery_succeeded(supplement):
        # KIS/base preservation must not make the API fail when the preferred
        # discovery union successfully refreshed the shared market snapshot.
        output["base_refresh_status"] = base_status
        output["status"] = "ok"
    return output


def refresh_ipo_market(*, username: str | None = None, target_date_str: str | None = None) -> dict[str, Any]:
    """Interactive refresh with bounded source sync and capped score recovery.

    Schedule/reference discovery remains limited to the moving three-month
    window. Deep DART parsing is allowed only for a small set of near-term IPOs
    whose score cutoff has already arrived and whose Wealth score is still
    calculating.
    """
    resolved_target = _target_date(target_date_str)
    total_started = perf_counter()
    result = _BASE_REFRESH_MARKET(username=username, target_date_str=resolved_target)
    timings = {"base_refresh_ms": round((perf_counter() - total_started) * 1000, 3),
               "metalogos_reference_ms": 0.0, "targeted_dart_ms": 0.0}
    supplement: dict[str, Any] = {}
    targeted: dict[str, Any] = {}
    try:
        with _base._refresh_file_lock():
            supplement = discover_and_merge_primary_sources(
                username=username,
                target_date_str=resolved_target,
            )
            timings.update(supplement.get("timings", {}))
            stage_started = perf_counter()
            reference = refresh_missing_metalogos_references(
                target_date_str=resolved_target,
                prefetched_rows=supplement.get("metalogos_rows", []),
            )
            timings["metalogos_reference_ms"] = round((perf_counter() - stage_started) * 1000, 3)
            stage_started = perf_counter()
            _record_metalogos_reference_status(supplement, reference)
            targeted = _targeted_dart_enrichment(
                username=username,
                target_date_str=resolved_target,
                score_recovery_only=True,
                max_candidates=_INTERACTIVE_SCORE_RECOVERY_LIMIT,
            )
            timings["targeted_dart_ms"] = round((perf_counter() - stage_started) * 1000, 3)
    except _base.IpoRefreshAlreadyRunning:
        supplement = {"statuses": {"supplemental": "busy"}}
        targeted = {"status": "busy"}
    output = _merge_refresh_result(result, supplement, targeted)
    timings.setdefault("metalogos_discovery_ms", 0.0)
    timings["total_ms"] = round((perf_counter() - total_started) * 1000, 3)
    output["timings"] = timings
    if supplement.get("window_start"):
        output["interactive_window_start"] = supplement["window_start"]
    if supplement.get("window_end"):
        output["interactive_window_end"] = supplement["window_end"]
    return output


def refresh_ipo_market_enriched(
    *, username: str | None = None, target_date_str: str | None = None
) -> dict[str, Any]:
    """Scheduled full refresh with main-source discovery as the final schedule authority.

    The proven base pipeline runs first (including KIS and full DART scoring).
    DART/KIND + NAVER/Npay + 160 are then reconciled over that snapshot so a
    successful-but-partial KIS response cannot overwrite the preferred schedule
    sources. Targeted DART runs once more for newly discovered current/future IPOs.
    """
    resolved_target = _target_date(target_date_str)
    result = _BASE_REFRESH_ENRICHED(username=username, target_date_str=resolved_target)
    supplement, targeted = _run_supplement_and_targeted(
        username=username,
        target_date_str=resolved_target,
    )
    return _merge_refresh_result(result, supplement, targeted)
