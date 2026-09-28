"""Official high-dividend-company qualification evidence for Phase 10.5E.

This module does not re-compute the legal qualification criteria.  It reads the
issuer's latest official ``기업가치제고계획(자율공시)`` filing through OpenDART
and only reports the structurally stated ``고배당기업 여부`` value.  The KIND
high-dividend page is retained as the official cross-check/reference surface.

Fail-closed policy:
- ``해당`` in the latest structurally parsed official filing => official_qualified.
- ``미해당`` in that filing => official_not_qualified.
- no filing / field not structurally verified => not_confirmed.
- missing credential, blocked network, or upstream failure => source_unavailable.
- foreign securities and Korean-listed ETFs => not_applicable.

Absence from an official list is never converted into an unqualified judgment.
No tax rate, threshold, or eligibility arithmetic is introduced here.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import re
import time
from typing import Any

import httpx

from app.services.ipo.dart_client import DartClient, extract_document_text_from_zip
from app.services.network_policy import external_network_allowed

KST = timezone(timedelta(hours=9))
KIND_HIGH_DIVIDEND_URL = (
    "https://kind.krx.co.kr/valueup/dividend.do?method=valueupHighDividendMain"
)
OPENDART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
OPENDART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"
DART_VIEWER_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
_CACHE_TTL_SECONDS = 30 * 60
_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _normalize(value: object) -> str:
    return "".join(str(value or "").split()).lower()


def _stock_code(value: object) -> str:
    code = str(value or "").strip().upper()
    if code.startswith("A") and len(code) == 7:
        code = code[1:]
    return code


def _money(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if number <= 0 or number != number:
        return 0
    return int(round(number))


def _latest_valueup_filing(rows: object) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    matches: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        report_name = str(raw.get("report_nm") or "").strip()
        if "기업가치제고계획" not in _normalize(report_name):
            continue
        receipt = str(raw.get("rcept_no") or "").strip()
        if not receipt:
            continue
        matches.append(
            {
                "report_name": report_name,
                "receipt_no": receipt,
                "receipt_date": str(raw.get("rcept_dt") or "").strip(),
                "viewer_url": DART_VIEWER_URL.format(rcept_no=receipt),
            }
        )
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: (item.get("receipt_date") or "", item["receipt_no"]),
    )


def parse_high_dividend_valueup_document(
    document_text: str,
    *,
    report_name: str = "",
    receipt_no: str = "",
    receipt_date: str = "",
    viewer_url: str = "",
) -> dict[str, Any]:
    """Parse only an explicit high-dividend qualification field from a filing."""
    text = str(document_text or "")
    compact = " ".join(text.replace("\xa0", " ").split())
    normalized = _normalize(compact)
    if not compact or "고배당기업" not in normalized:
        return {
            "structured_verification": False,
            "qualification_status": "not_confirmed",
            "reason": "high_dividend_field_not_found",
        }

    # The actual filing renders a row equivalent to:
    # "조세특례제한법 제104조의27에 따른 고배당기업 여부 | 해당".
    # Keep the match deliberately narrow so narrative uses of '해당' cannot
    # promote a security to official-qualified status.
    match = re.search(
        r"조세특례제한법\s*제?\s*104\s*조\s*의\s*27[^\n|]{0,120}?"
        r"고배당기업\s*여부\s*(?:\||:|：)?\s*(미해당|해당)",
        compact,
        flags=re.IGNORECASE,
    )
    if match is None:
        # HTML/text extraction can collapse table delimiters.  Use a bounded
        # local window around the exact field label, never a document-wide hit.
        label = re.search(r"고배당기업\s*여부", compact, flags=re.IGNORECASE)
        if label is not None:
            window = compact[label.end() : label.end() + 48]
            value = re.match(r"\s*(?:\||:|：)?\s*(미해당|해당)\b", window)
            if value is not None:
                match = value
    if match is None:
        return {
            "structured_verification": False,
            "qualification_status": "not_confirmed",
            "reason": "high_dividend_value_not_verified",
            "receipt_no": receipt_no or None,
            "receipt_date": receipt_date or None,
            "viewer_url": viewer_url or None,
        }

    value = str(match.group(1)).strip()
    status = "official_not_qualified" if value == "미해당" else "official_qualified"
    business_year = None
    year_match = re.search(r"직전\s*사업연도\s*\(?\s*(20\d{2})\s*\)?", compact)
    if year_match:
        business_year = int(year_match.group(1))
    decision_date = None
    decision_match = re.search(
        r"결정일자\s*(?:\||:|：)?\s*(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})",
        compact,
    )
    if decision_match:
        decision_date = (
            f"{decision_match.group(1)}-{int(decision_match.group(2)):02d}-"
            f"{int(decision_match.group(3)):02d}"
        )
    return {
        "structured_verification": True,
        "qualification_status": status,
        "qualification_value": value,
        "report_name": report_name or None,
        "receipt_no": receipt_no or None,
        "receipt_date": receipt_date or None,
        "viewer_url": viewer_url or None,
        "business_year": business_year,
        "decision_date": decision_date,
        "company_self_determination": True,
    }


async def _load_corp_code_map(client: httpx.AsyncClient, api_key: str) -> dict[str, str]:
    # Reuse the already verified OpenDART listed-code mapping/cache rather than
    # creating a second corp-code contract.
    from app.services.dividend_official_sources import _load_corp_codes

    return await _load_corp_codes(client, api_key)


async def _fetch_company_status(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    corp_code: str,
    stock_code: str,
    as_of: date,
) -> dict[str, Any]:
    cache_key = (stock_code, as_of.isoformat())
    cached = _CACHE.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return dict(cached[1])

    begin = as_of - timedelta(days=450)
    try:
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
            timeout=8.0,
        )
        response.raise_for_status()
        payload = response.json()
        api_status = str(payload.get("status") or "")
        if api_status not in {"", "000"}:
            result = {
                "status": "source_unavailable",
                "reason": f"opendart_list_status_{api_status}",
            }
        else:
            filing = _latest_valueup_filing(payload.get("list"))
            if filing is None:
                result = {
                    "status": "not_confirmed",
                    "reason": "valueup_filing_not_found",
                }
            else:
                document = await client.get(
                    OPENDART_DOCUMENT_URL,
                    params={
                        "crtfc_key": api_key,
                        "rcept_no": filing["receipt_no"],
                    },
                    timeout=12.0,
                )
                document.raise_for_status()
                parsed = parse_high_dividend_valueup_document(
                    extract_document_text_from_zip(document.content),
                    report_name=filing["report_name"],
                    receipt_no=filing["receipt_no"],
                    receipt_date=filing["receipt_date"],
                    viewer_url=filing["viewer_url"],
                )
                result = {
                    "status": parsed.get("qualification_status") or "not_confirmed",
                    "reason": parsed.get("reason"),
                    "evidence": parsed,
                }
    except Exception:
        result = {
            "status": "source_unavailable",
            "reason": "official_valueup_lookup_failed",
        }

    _CACHE[cache_key] = (time.monotonic(), dict(result))
    return result


def _qualification_payload(
    status: str,
    *,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    labels = {
        "official_qualified": "공식 공시 · 고배당기업 해당",
        "official_not_qualified": "공식 공시 · 고배당기업 미해당",
        "not_confirmed": "공식 자격 확인 대기",
        "source_unavailable": "공식 자격 조회 불가",
        "not_applicable": "고배당기업 확인 대상 아님",
    }
    result = result or {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), dict) else {}
    return {
        "status": status,
        "label": labels.get(status, labels["not_confirmed"]),
        "source": "official_valueup_disclosure",
        "source_url": evidence.get("viewer_url") or KIND_HIGH_DIVIDEND_URL,
        "kind_reference_url": KIND_HIGH_DIVIDEND_URL,
        "receipt_no": evidence.get("receipt_no"),
        "receipt_date": evidence.get("receipt_date"),
        "business_year": evidence.get("business_year"),
        "decision_date": evidence.get("decision_date"),
        "company_self_determination": True,
        "wealth_inferred": False,
        "reason": result.get("reason"),
    }


async def enrich_dividend_intelligence_with_high_dividend_qualification(
    summary: dict[str, Any],
    holdings: list[dict[str, Any]],
    *,
    username: str | None = None,
    api_key: str | None = None,
    as_of: date | datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Attach official qualification states to existing Dividend Intelligence."""
    intelligence = summary.get("dividend_intelligence")
    if not isinstance(intelligence, dict):
        return summary
    instruments = intelligence.get("instruments")
    if not isinstance(instruments, list):
        instruments = []

    day = as_of.date() if isinstance(as_of, datetime) else (as_of or _now_kst().date())
    if api_key is not None:
        key = str(api_key).strip()
        credential_source = "explicit" if key else "unconfigured"
    else:
        dart = DartClient(username=username)
        key = dart.api_key
        credential_source = dart.credential_source

    applicable: dict[str, list[dict[str, Any]]] = {}
    for row in instruments:
        if not isinstance(row, dict):
            continue
        code = _stock_code(row.get("code"))
        is_domestic_stock = (
            str(row.get("currency") or "").upper() == "KRW"
            and str(row.get("tax_engine_asset_type") or "") == "domestic_dividend_stock"
            and len(code) == 6
        )
        if not is_domestic_stock:
            row["high_dividend_qualification"] = _qualification_payload("not_applicable")
            continue
        applicable.setdefault(code, []).append(row)

    network_allowed = external_network_allowed()
    source_status = "ok"
    results: dict[str, dict[str, Any]] = {}
    if not applicable:
        source_status = "no_applicable_holdings"
    elif not network_allowed:
        source_status = "network_disabled"
        results = {
            code: {"status": "source_unavailable", "reason": "network_disabled"}
            for code in applicable
        }
    elif not key:
        source_status = "missing_api_key"
        results = {
            code: {"status": "source_unavailable", "reason": "missing_opendart_api_key"}
            for code in applicable
        }
    else:
        own_client = client is None
        http = client or httpx.AsyncClient()
        try:
            try:
                mapping = await _load_corp_code_map(http, key)
            except Exception:
                mapping = {}
                source_status = "opendart_unavailable"
            tasks: list[tuple[str, Any]] = []
            for code in applicable:
                corp_code = mapping.get(code)
                if not corp_code:
                    results[code] = {
                        "status": "not_confirmed",
                        "reason": "corp_code_not_found",
                    }
                    continue
                tasks.append(
                    (
                        code,
                        _fetch_company_status(
                            http,
                            api_key=key,
                            corp_code=corp_code,
                            stock_code=code,
                            as_of=day,
                        ),
                    )
                )
            if tasks:
                fetched = await asyncio.gather(
                    *(task for _, task in tasks), return_exceptions=True
                )
                for (code, _), value in zip(tasks, fetched):
                    if isinstance(value, Exception):
                        results[code] = {
                            "status": "source_unavailable",
                            "reason": "official_valueup_lookup_failed",
                        }
                    else:
                        results[code] = value
        finally:
            if own_client:
                await http.aclose()

    for code, rows in applicable.items():
        result = results.get(code, {"status": "not_confirmed"})
        status = str(result.get("status") or "not_confirmed")
        for row in rows:
            row["high_dividend_qualification"] = _qualification_payload(
                status,
                result=result,
            )

    counts = {
        "official_qualified": 0,
        "official_not_qualified": 0,
        "not_confirmed": 0,
        "source_unavailable": 0,
        "not_applicable": 0,
    }
    qualified_gross = 0
    for row in instruments:
        if not isinstance(row, dict):
            continue
        qualification = row.get("high_dividend_qualification")
        status = (
            str(qualification.get("status") or "not_confirmed")
            if isinstance(qualification, dict)
            else "not_confirmed"
        )
        counts[status] = counts.get(status, 0) + 1
        if status == "official_qualified":
            qualified_gross += _money(row.get("gross_annual_dividend_krw"))

    after_tax = summary.get("portfolio_after_tax")
    canonical_gross = (
        _money(after_tax.get("gross_annual_dividend_krw"))
        if isinstance(after_tax, dict)
        else _money(summary.get("total_annual_dividend_krw"))
    )
    share = (
        round((qualified_gross / canonical_gross) * 100.0, 2)
        if canonical_gross > 0
        else None
    )
    intelligence["high_dividend"] = {
        "schema_version": 1,
        "as_of_date": day.isoformat(),
        "source_status": source_status,
        "source": "official_valueup_disclosure",
        "source_label": "공식 기업가치 제고 계획 공시",
        "kind_reference_url": KIND_HIGH_DIVIDEND_URL,
        "opendart_configured": bool(key),
        "opendart_credential_source": credential_source,
        "company_self_determination": True,
        "wealth_inferred": False,
        "absence_means_unqualified": False,
        "applicable_instrument_count": len(applicable),
        "official_qualified_count": counts.get("official_qualified", 0),
        "official_not_qualified_count": counts.get("official_not_qualified", 0),
        "not_confirmed_count": counts.get("not_confirmed", 0),
        "source_unavailable_count": counts.get("source_unavailable", 0),
        "not_applicable_count": counts.get("not_applicable", 0),
        "qualified_projected_gross_krw": qualified_gross,
        "qualified_projected_gross_share_pct": share,
        "tax_special_treatment_automatically_applied": False,
        "screening_only": True,
    }
    contracts = intelligence.setdefault("contracts", {})
    if isinstance(contracts, dict):
        contracts["high_dividend_qualification_official_only"] = True
        contracts["high_dividend_tax_rule_automatically_applied"] = False
    return summary


__all__ = [
    "KIND_HIGH_DIVIDEND_URL",
    "enrich_dividend_intelligence_with_high_dividend_qualification",
    "parse_high_dividend_valueup_document",
]
