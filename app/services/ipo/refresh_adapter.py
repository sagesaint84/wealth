from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services.ipo import orchestrator as _base
from app.services.ipo.dart_client import DartClient, extract_document_text_from_zip, select_point_in_time_filing
from app.services.ipo.dart_parser import DartSemanticParser
from app.services.ipo.identity import is_spac_ipo
from app.services.ipo.normalize import normalize_equity_registration_response
from app.services.ipo.score import calculate_wealth_ipo_score
from app.services.ipo.source_discovery import discover_and_merge_primary_sources
from app.services.ipo.store import merge_ipo_record, read_market_store, write_market_store


KST = timezone(timedelta(hours=9))
_BASE_REFRESH_MARKET = _base.refresh_ipo_market
_BASE_REFRESH_ENRICHED = _base.refresh_ipo_market_enriched


def _target_date(target_date_str: str | None) -> str:
    return target_date_str or datetime.now(KST).strftime("%Y-%m-%d")


def _month_window(target_date_str: str) -> tuple[date, date]:
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    start = target.replace(day=1)
    if start.month == 12:
        after = start.replace(year=start.year + 1, month=2, day=1)
    elif start.month == 11:
        after = start.replace(year=start.year + 1, month=1, day=1)
    else:
        after = start.replace(month=start.month + 2, day=1)
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


def _targeted_dart_enrichment(*, username: str | None, target_date_str: str) -> dict[str, Any]:
    """Refresh DART features only for current/next-month IPOs.

    This keeps the interactive button responsive while retaining the exact
    point-in-time filing rule used by the full scheduled enriched pipeline.
    """
    dart = DartClient(username=username)
    if not dart.is_configured():
        return {"status": "source_unavailable (api_key_missing)", "candidates": 0, "enriched": 0}

    market = read_market_store()
    ipos = market.get("ipos", []) if isinstance(market.get("ipos"), list) else []
    start, end = _month_window(target_date_str)
    candidates = [ipo for ipo in ipos if isinstance(ipo, dict) and _is_target_candidate(ipo, start, end)]

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
            # Discovery remains useful even if the corp master is temporarily unavailable.
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
                if not is_spac and offer_band is None:
                    offer_band = parser.extract_offer_band(doc_text)

            if not parsed_features and not structured_data and offer_band is None:
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

    # Score computation is cheap and keeps cohort/coverage coherent after the
    # targeted feature updates. External 160/Npay reference metrics never enter
    # `features`, so they cannot alter the Wealth score.
    for ipo in ipos:
        if isinstance(ipo, dict):
            ipo["score"] = calculate_wealth_ipo_score(ipo, ipos)
    write_market_store(market)
    return {
        "status": "ok" if failed == 0 else "partial",
        "candidates": len(candidates),
        "enriched": enriched,
        "failed": failed,
        "skipped": skipped,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
    }


def refresh_ipo_market(*, username: str | None = None, target_date_str: str | None = None) -> dict[str, Any]:
    """Interactive refresh: base reconciliation + main discovery union + targeted DART."""
    resolved_target = _target_date(target_date_str)
    result = _BASE_REFRESH_MARKET(username=username, target_date_str=resolved_target)
    supplement: dict[str, Any] = {}
    targeted: dict[str, Any] = {}
    try:
        with _base._refresh_file_lock():
            supplement = discover_and_merge_primary_sources(
                username=username,
                target_date_str=resolved_target,
            )
            targeted = _targeted_dart_enrichment(
                username=username,
                target_date_str=resolved_target,
            )
    except _base.IpoRefreshAlreadyRunning:
        supplement = {"statuses": {"supplemental": "busy"}}
        targeted = {"status": "busy"}

    output = dict(result or {})
    output.setdefault("sources", {}).update(supplement.get("statuses") or {})
    output["targeted_dart"] = targeted
    output["discovery_priority"] = "DART/KIND + Npay > Metalogos160 > KIS fallback"
    output["total_ipos"] = supplement.get("total_ipos", output.get("total_ipos"))
    return output


def refresh_ipo_market_enriched(
    *, username: str | None = None, target_date_str: str | None = None
) -> dict[str, Any]:
    """Scheduled full enrichment after main-source discovery has populated the universe."""
    resolved_target = _target_date(target_date_str)
    supplement: dict[str, Any] = {}
    try:
        with _base._refresh_file_lock():
            supplement = discover_and_merge_primary_sources(
                username=username,
                target_date_str=resolved_target,
            )
    except _base.IpoRefreshAlreadyRunning:
        supplement = {"statuses": {"supplemental": "busy"}}

    result = _BASE_REFRESH_ENRICHED(username=username, target_date_str=resolved_target)
    output = dict(result or {})
    output.setdefault("sources", {}).update(supplement.get("statuses") or {})
    output["discovery_priority"] = "DART/KIND + Npay > Metalogos160 > KIS fallback"
    output["total_ipos"] = supplement.get("total_ipos", output.get("total_ipos"))
    return output
