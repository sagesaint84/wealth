"""Official-source enrichment for domestic dividend forecasts.

The existing forecast engine remains the numeric fallback.  This module adds
OpenDART evidence without ever turning a report-title match into a confirmed
future dividend amount.

Policy:
- OpenDART periodic-report dividend data is official historical evidence.
- A recent dividend-decision filing is evidence that a decision exists, but the
  amount is *not* marked confirmed unless it is structurally verified.
- Historical official DPS may fill a missing domestic-stock estimate, but does
  not overwrite a non-zero Naver/Yahoo estimate.
- Missing API credentials, blocked network, or upstream errors must not make the
  existing dividend forecast unavailable.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import io
import math
import time
from typing import Any, Iterable
import xml.etree.ElementTree as ET
import zipfile

import httpx

from app.services.network_policy import external_network_allowed
from app.services.dividend_confirmed_disclosures import parse_dividend_decision_document
from app.services.ipo.dart_client import DartClient, extract_document_text_from_zip

KST = timezone(timedelta(hours=9))

OPENDART_CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
OPENDART_DIVIDEND_URL = "https://opendart.fss.or.kr/api/alotMatter.json"
OPENDART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
OPENDART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
KIND_DIVIDEND_INFO_URL = (
    "https://kind.krx.co.kr/dividendsinfo/dividendinfo.do?method=searchDividendInfoMain"
)
OPENDART_GUIDE_URL = (
    "https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019009"
)

_CORP_CODE_CACHE: dict[str, str] = {}
_CORP_CODE_CACHE_AT = 0.0
_CORP_CODE_CACHE_TTL_SECONDS = 24 * 60 * 60


def _now_kst() -> datetime:
    return datetime.now(KST)


def _money(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("원", "")
    if not text or text in {"-", "--", "N/A", "n/a"}:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _stock_code(value: object) -> str:
    return str(value or "").strip().upper()


def _is_domestic_stock_code(code: str, currency: str) -> bool:
    return currency.upper() == "KRW" and len(code) == 6 and not code.isalpha()


def _parse_corp_code_xml(xml_bytes: bytes) -> dict[str, str]:
    """Return listed stock-code -> OpenDART corp-code mapping."""
    root = ET.fromstring(xml_bytes)
    mapping: dict[str, str] = {}
    for node in root.findall(".//list"):
        stock_code = (node.findtext("stock_code") or "").strip().upper()
        corp_code = (node.findtext("corp_code") or "").strip()
        if stock_code and corp_code:
            mapping[stock_code] = corp_code
    return mapping


def _parse_corp_code_zip(raw: bytes) -> dict[str, str]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
        if not xml_names:
            return {}
        return _parse_corp_code_xml(archive.read(xml_names[0]))


def _normalize_label(value: object) -> str:
    return "".join(str(value or "").split()).lower()


def _extract_ordinary_cash_dps(rows: object) -> float | None:
    """Extract current-term ordinary-share cash DPS from alotMatter rows."""
    if not isinstance(rows, list):
        return None
    candidates: list[float] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        label = _normalize_label(raw.get("se"))
        if "주당현금배당금" not in label:
            continue
        stock_kind = _normalize_label(raw.get("stock_knd"))
        # Prefer ordinary shares, but accept blank stock kind because some
        # issuers omit the classification for a single listed share class.
        if stock_kind and "보통" not in stock_kind and "ordinary" not in stock_kind:
            continue
        value = _money(raw.get("thstrm"))
        if value is not None:
            candidates.append(value)
    if not candidates:
        return None
    # Duplicate report rows occasionally exist; identical values collapse and
    # the largest non-negative value is a conservative representation of the
    # per-share cash dividend line rather than summing duplicate rows.
    return max(candidates)


def _latest_dividend_decision(rows: object) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    matches: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        report_name = str(raw.get("report_nm") or "").strip()
        normalized = _normalize_label(report_name)
        if "배당" not in normalized or "결정" not in normalized:
            continue
        receipt = str(raw.get("rcept_no") or "").strip()
        receipt_date = str(raw.get("rcept_dt") or "").strip()
        if not receipt:
            continue
        matches.append(
            {
                "report_name": report_name,
                "receipt_no": receipt,
                "receipt_date": receipt_date,
                "viewer_url": DART_VIEWER_URL.format(rcept_no=receipt),
                # A list API title only proves that a filing exists.  It does
                # not structurally verify the per-share amount.
                "confirmed_amount": False,
            }
        )
    if not matches:
        return None
    return max(matches, key=lambda item: (item.get("receipt_date") or "", item["receipt_no"]))


async def _load_corp_codes(client: httpx.AsyncClient, api_key: str) -> dict[str, str]:
    global _CORP_CODE_CACHE, _CORP_CODE_CACHE_AT
    now = time.monotonic()
    if _CORP_CODE_CACHE and now - _CORP_CODE_CACHE_AT < _CORP_CODE_CACHE_TTL_SECONDS:
        return dict(_CORP_CODE_CACHE)
    response = await client.get(
        OPENDART_CORP_CODE_URL,
        params={"crtfc_key": api_key},
        timeout=10.0,
    )
    response.raise_for_status()
    mapping = _parse_corp_code_zip(response.content)
    if mapping:
        _CORP_CODE_CACHE = dict(mapping)
        _CORP_CODE_CACHE_AT = now
    return mapping


async def _fetch_periodic_dividend(
    client: httpx.AsyncClient,
    api_key: str,
    corp_code: str,
    business_year: int,
) -> dict[str, Any]:
    response = await client.get(
        OPENDART_DIVIDEND_URL,
        params={
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": str(business_year),
            "reprt_code": "11011",
        },
        timeout=7.0,
    )
    response.raise_for_status()
    payload = response.json()
    status = str(payload.get("status") or "")
    if status not in {"", "000"}:
        return {"available": False, "status": status}
    dps = _extract_ordinary_cash_dps(payload.get("list"))
    return {
        "available": dps is not None,
        "ordinary_cash_dps_krw": dps,
        "business_year": business_year,
        "report_code": "11011",
        "source_url": OPENDART_GUIDE_URL,
    }


async def _fetch_recent_decision(
    client: httpx.AsyncClient,
    api_key: str,
    corp_code: str,
    *,
    as_of: date,
) -> dict[str, Any] | None:
    begin = as_of - timedelta(days=370)
    response = await client.get(
        OPENDART_LIST_URL,
        params={
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bgn_de": begin.strftime("%Y%m%d"),
            "end_de": as_of.strftime("%Y%m%d"),
            "page_count": "100",
            "sort": "date",
            "sort_mth": "desc",
        },
        timeout=7.0,
    )
    response.raise_for_status()
    payload = response.json()
    status = str(payload.get("status") or "")
    if status not in {"", "000"}:
        return None
    return _latest_dividend_decision(payload.get("list"))


async def _fetch_structured_decision(
    client: httpx.AsyncClient,
    api_key: str,
    decision: dict[str, Any],
    *,
    as_of: date,
) -> dict[str, Any] | None:
    receipt_no = str(decision.get("receipt_no") or "").strip()
    if not receipt_no:
        return None
    response = await client.get(
        OPENDART_DOCUMENT_URL,
        params={"crtfc_key": api_key, "rcept_no": receipt_no},
        timeout=10.0,
    )
    response.raise_for_status()
    document_text = extract_document_text_from_zip(response.content)
    return parse_dividend_decision_document(
        document_text,
        report_name=str(decision.get("report_name") or ""),
        receipt_no=receipt_no,
        receipt_date=str(decision.get("receipt_date") or ""),
        viewer_url=str(decision.get("viewer_url") or ""),
        as_of=as_of,
    )


async def get_official_dividend_evidence(
    holdings: Iterable[dict[str, Any]],
    *,
    username: str | None = None,
    api_key: str | None = None,
    as_of: date | datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Return official evidence keyed by domestic stock code.

    The function intentionally degrades to metadata instead of raising when
    OpenDART is not configured or unavailable.
    """
    network_allowed = external_network_allowed()
    if api_key is not None:
        key = api_key.strip()
        credential_source = "explicit" if key else "unconfigured"
    else:
        dart_client = DartClient(username=username)
        key = dart_client.api_key
        credential_source = dart_client.credential_source
    day = as_of.date() if isinstance(as_of, datetime) else (as_of or _now_kst().date())

    domestic_codes = sorted(
        {
            _stock_code(item.get("code"))
            for item in holdings
            if isinstance(item, dict)
            and _is_domestic_stock_code(
                _stock_code(item.get("code")), str(item.get("currency") or "KRW")
            )
        }
    )
    policy = {
        "network_allowed": network_allowed,
        "opendart_configured": bool(key),
        "opendart_credential_source": credential_source,
        "kind_reference_url": KIND_DIVIDEND_INFO_URL,
        "opendart_guide_url": OPENDART_GUIDE_URL,
        "confirmed_amount_requires_structured_verification": True,
        "confirmed_numeric_override_requires_safe_payment_month": True,
        "opendart_document_url": OPENDART_DOCUMENT_URL,
        "priority": [
            "official_confirmed_disclosure",
            "official_periodic_report_history",
            "legacy_naver_or_yahoo_fallback",
        ],
    }
    if not domestic_codes:
        return {"status": "no_domestic_holdings", "evidence": {}, "policy": policy}
    if not network_allowed:
        return {"status": "network_disabled", "evidence": {}, "policy": policy}
    if not key:
        return {"status": "missing_api_key", "evidence": {}, "policy": policy}

    should_close = client is None
    http = client or httpx.AsyncClient()
    evidence: dict[str, Any] = {}
    try:
        mapping = await _load_corp_codes(http, key)
        business_year = day.year - 1
        for code in domestic_codes:
            corp_code = mapping.get(code)
            if not corp_code:
                evidence[code] = {
                    "official_data_available": False,
                    "reason": "corp_code_not_found",
                }
                continue
            try:
                periodic = await _fetch_periodic_dividend(
                    http, key, corp_code, business_year
                )
                recent = await _fetch_recent_decision(
                    http, key, corp_code, as_of=day
                )
                structured = None
                if recent:
                    try:
                        structured = await _fetch_structured_decision(
                            http, key, recent, as_of=day
                        )
                    except Exception:
                        structured = {
                            **recent,
                            "structured_verification": False,
                            "confirmed_amount": False,
                            "confirmed_payment_date": False,
                            "ordinary_cash_dps_krw": None,
                            "record_date": None,
                            "payment_date": None,
                            "future_payment": None,
                            "reason": "document_parse_failed",
                        }
                evidence[code] = {
                    "official_data_available": bool(periodic.get("available") or recent),
                    "corp_code": corp_code,
                    "historical": periodic,
                    "recent_decision_disclosure": recent,
                    "structured_decision_disclosure": structured,
                }
            except Exception:
                evidence[code] = {
                    "official_data_available": False,
                    "corp_code": corp_code,
                    "reason": "opendart_request_failed",
                }
        return {"status": "ok", "evidence": evidence, "policy": policy}
    except Exception:
        return {"status": "opendart_unavailable", "evidence": {}, "policy": policy}
    finally:
        if should_close:
            await http.aclose()


def _rebuild_summary_from_holdings(
    summary: dict[str, Any],
    holdings: list[dict[str, Any]],
    *,
    fx_rate: float,
) -> None:
    """Recalculate totals/schedule after official fill-only overrides."""
    rows = summary.get("holding_dividends")
    if not isinstance(rows, list):
        return
    original_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        key = (_stock_code(holding.get("code")), str(holding.get("currency") or "KRW").upper())
        original_by_key[key] = holding

    total_annual = 0.0
    total_eval = 0.0
    paying_count = 0
    monthly = {m: {"month": m, "total_krw": 0.0, "items": []} for m in range(1, 13)}

    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _stock_code(row.get("code"))
        currency = str(row.get("currency") or "KRW").upper()
        holding = original_by_key.get((code, currency), {})
        qty = _money(row.get("quantity")) or _money(holding.get("quantity")) or 0.0
        price = _money(holding.get("current_price")) or _money(holding.get("purchase_price")) or 0.0
        multiplier = fx_rate if currency == "USD" else 1.0
        total_eval += qty * price * multiplier

        annual_per_share = _money(row.get("annual_div_per_share")) or 0.0
        annual_orig = qty * annual_per_share
        annual_krw = annual_orig * multiplier
        row["annual_payout_orig"] = round(annual_orig, 2)
        row["annual_payout_krw"] = round(annual_krw)
        if price > 0:
            row["div_yield"] = round((annual_per_share / price) * 100.0, 2)
        payout_months = row.get("payout_months") if isinstance(row.get("payout_months"), list) else []
        valid_months = [int(m) for m in payout_months if isinstance(m, (int, float)) and 1 <= int(m) <= 12]
        if annual_krw > 0:
            paying_count += 1
            total_annual += annual_krw
            if valid_months:
                per_month_krw = annual_krw / len(valid_months)
                per_month_orig = annual_orig / len(valid_months)
                for month in valid_months:
                    monthly[month]["total_krw"] += per_month_krw
                    monthly[month]["items"].append(
                        {
                            "code": code,
                            "name": row.get("name") or code,
                            "quantity": qty,
                            "currency": currency,
                            "payout_krw": round(per_month_krw),
                            "payout_orig": round(per_month_orig, 2),
                            "div_yield": row.get("div_yield") or 0.0,
                        }
                    )

    schedule: list[dict[str, Any]] = []
    for month in range(1, 13):
        item = monthly[month]
        item["total_krw"] = round(item["total_krw"])
        item["items"].sort(key=lambda value: value["payout_krw"], reverse=True)
        schedule.append(item)
    summary["total_annual_dividend_krw"] = round(total_annual)
    summary["monthly_avg_dividend_krw"] = round(total_annual / 12.0)
    summary["dividend_paying_count"] = paying_count
    summary["portfolio_yield"] = round((total_annual / total_eval) * 100.0, 2) if total_eval > 0 else 0.0
    summary["monthly_schedule"] = schedule
    rows.sort(key=lambda value: value.get("annual_payout_krw") or 0, reverse=True)


def _apply_confirmed_future_overrides(
    summary: dict[str, Any],
    holdings: list[dict[str, Any]],
    *,
    fx_rate: float,
    as_of: date,
) -> bool:
    rows = summary.get("holding_dividends")
    schedule = summary.get("monthly_schedule")
    if not isinstance(rows, list) or not isinstance(schedule, list):
        return False

    bucket_by_month = {
        int(bucket.get("month")): bucket
        for bucket in schedule
        if isinstance(bucket, dict) and isinstance(bucket.get("month"), (int, float))
    }
    changed = False
    total_delta = 0.0

    for row in rows:
        if not isinstance(row, dict):
            continue
        source = row.get("forecast_source")
        if not isinstance(source, dict):
            continue
        structured = source.get("structured_decision_disclosure")
        if not isinstance(structured, dict) or structured.get("confirmed_amount") is not True:
            continue
        source["confirmed_numeric_override"] = False
        payment_text = str(structured.get("payment_date") or "").strip()
        if not payment_text:
            source["confirmed_numeric_override_reason"] = "payment_date_unavailable"
            continue
        try:
            payment_day = date.fromisoformat(payment_text)
        except ValueError:
            source["confirmed_numeric_override_reason"] = "payment_date_invalid"
            continue
        if payment_day < as_of or payment_day.year != as_of.year:
            source["confirmed_numeric_override_reason"] = "payment_date_outside_current_future_window"
            continue

        dps = _money(structured.get("ordinary_cash_dps_krw"))
        qty = _money(row.get("quantity")) or 0.0
        if dps is None or dps <= 0 or qty <= 0:
            source["confirmed_numeric_override_reason"] = "amount_or_quantity_unavailable"
            continue
        month = payment_day.month
        bucket = bucket_by_month.get(month)
        if not isinstance(bucket, dict):
            source["confirmed_numeric_override_reason"] = "monthly_schedule_unavailable"
            continue
        items = bucket.get("items")
        if not isinstance(items, list):
            items = []
            bucket["items"] = items
        code = _stock_code(row.get("code"))
        existing = next(
            (item for item in items if isinstance(item, dict) and _stock_code(item.get("code")) == code),
            None,
        )
        current_annual = _money(row.get("annual_payout_krw")) or 0.0
        if existing is None and current_annual > 0:
            source["confirmed_numeric_override_reason"] = "payment_month_not_in_existing_schedule"
            continue

        new_payout = round(qty * dps)
        old_payout = _money(existing.get("payout_krw")) if existing else 0.0
        old_payout = old_payout or 0.0
        delta = new_payout - old_payout
        if existing is None:
            existing = {
                "code": code,
                "name": row.get("name") or code,
                "quantity": qty,
                "currency": "KRW",
                "payout_krw": 0,
                "payout_orig": 0,
                "div_yield": row.get("div_yield") or 0.0,
            }
            items.append(existing)
            payout_months = row.get("payout_months")
            if not isinstance(payout_months, list):
                payout_months = []
            if month not in payout_months:
                payout_months.append(month)
                payout_months.sort()
            row["payout_months"] = payout_months

        existing["payout_krw"] = new_payout
        existing["payout_orig"] = new_payout
        existing["forecast_source"] = "opendart_confirmed_disclosure"
        bucket["total_krw"] = round((_money(bucket.get("total_krw")) or 0.0) + delta)
        items.sort(key=lambda value: value.get("payout_krw") or 0, reverse=True)

        row["annual_payout_krw"] = round(current_annual + delta)
        current_orig = _money(row.get("annual_payout_orig")) or current_annual
        row["annual_payout_orig"] = round(current_orig + delta, 2)
        row["annual_div_per_share"] = round(row["annual_payout_orig"] / qty, 4)
        source["numeric_source"] = "opendart_confirmed_disclosure"
        source["confirmed_numeric_override"] = True
        source["confirmed_numeric_override_reason"] = None
        source["confirmed_payment_month"] = month
        total_delta += delta
        changed = True

    if not changed:
        return False

    total = (_money(summary.get("total_annual_dividend_krw")) or 0.0) + total_delta
    summary["total_annual_dividend_krw"] = round(total)
    summary["monthly_avg_dividend_krw"] = round(total / 12.0)

    total_eval = 0.0
    for holding in holdings:
        if not isinstance(holding, dict):
            continue
        qty = _money(holding.get("quantity")) or 0.0
        price = _money(holding.get("current_price")) or _money(holding.get("purchase_price")) or 0.0
        currency = str(holding.get("currency") or "KRW").upper()
        total_eval += qty * price * (fx_rate if currency == "USD" else 1.0)
    if total_eval > 0:
        summary["portfolio_yield"] = round((total / total_eval) * 100.0, 2)
    rows.sort(key=lambda value: value.get("annual_payout_krw") or 0, reverse=True)
    return True


async def enrich_dividend_summary_with_official_sources(
    summary: dict[str, Any],
    holdings: list[dict[str, Any]],
    *,
    username: str | None = None,
    fx_rate: float = 1385.0,
    api_key: str | None = None,
    as_of: date | datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Attach official evidence and fill only missing domestic DPS estimates."""
    if not isinstance(summary, dict):
        return summary
    evidence_result = await get_official_dividend_evidence(
        holdings,
        username=username,
        api_key=api_key,
        as_of=as_of,
        client=client,
    )
    summary["forecast_source_policy"] = {
        **evidence_result.get("policy", {}),
        "status": evidence_result.get("status"),
    }
    evidence_map = evidence_result.get("evidence")
    if not isinstance(evidence_map, dict):
        evidence_map = {}

    rows = summary.get("holding_dividends")
    if not isinstance(rows, list):
        return summary

    changed = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _stock_code(row.get("code"))
        currency = str(row.get("currency") or "KRW").upper()
        if not _is_domestic_stock_code(code, currency):
            row["forecast_source"] = {
                "numeric_source": "yahoo_history" if currency == "USD" else "legacy_fallback",
                "official_data_available": False,
                "confirmed_amount": False,
            }
            continue

        evidence = evidence_map.get(code) if isinstance(evidence_map.get(code), dict) else {}
        historical = evidence.get("historical") if isinstance(evidence.get("historical"), dict) else {}
        structured = (
            evidence.get("structured_decision_disclosure")
            if isinstance(evidence.get("structured_decision_disclosure"), dict)
            else None
        )
        official_dps = _money(historical.get("ordinary_cash_dps_krw"))
        legacy_dps = _money(row.get("annual_div_per_share")) or 0.0
        numeric_source = "naver"
        if legacy_dps <= 0 and official_dps is not None and official_dps > 0:
            row["annual_div_per_share"] = official_dps
            numeric_source = "opendart_historical_fill"
            changed = True

        row["forecast_source"] = {
            "numeric_source": numeric_source,
            "official_data_available": bool(evidence.get("official_data_available")),
            "official_historical_annual_div_per_share_krw": official_dps,
            "official_business_year": historical.get("business_year"),
            "recent_decision_disclosure": evidence.get("recent_decision_disclosure"),
            "structured_decision_disclosure": structured,
            "confirmed_amount": bool(structured and structured.get("confirmed_amount") is True),
            "confirmed_numeric_override": False,
            "kind_reference_url": KIND_DIVIDEND_INFO_URL,
            "opendart_reference_url": OPENDART_GUIDE_URL,
            "safe_fill_only": True,
        }

    if changed:
        _rebuild_summary_from_holdings(summary, holdings, fx_rate=fx_rate)
    day = as_of.date() if isinstance(as_of, datetime) else (as_of or _now_kst().date())
    _apply_confirmed_future_overrides(
        summary, holdings, fx_rate=fx_rate, as_of=day
    )
    return summary


__all__ = [
    "KIND_DIVIDEND_INFO_URL",
    "OPENDART_GUIDE_URL",
    "enrich_dividend_summary_with_official_sources",
    "get_official_dividend_evidence",
]
