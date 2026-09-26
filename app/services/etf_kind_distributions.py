"""Official KIND distribution events for Korean-listed ETFs.

KIND publishes ``ETF이익금분배신고(분배금안내)(일괄공시)`` filings without a
separate API credential.  This module treats those filings as event-level
official evidence and overlays only structurally verified distribution events
onto the existing Naver-based annual forecast.

Safety policy:
- Only rows already identified as ETFs by the existing Naver integration are
  queried/enriched.
- A search-result title is not enough.  The official external document must
  contain the target ETF ISIN, record date, payment date, and per-unit amount.
- Existing heuristic schedule items are matched by the official record-date
  month first, then moved to the official payment month.  This avoids counting
  both the old heuristic month and the official payment event.
- If an existing positive forecast has no safely matchable schedule item, the
  official event is retained as evidence but is not added numerically.
- Network/parser failure preserves the legacy forecast.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import math
import re
from typing import Any, Iterable

import httpx

from app.services.network_policy import external_network_allowed

KST = timezone(timedelta(hours=9))
KIND_BASE_URL = "https://kind.krx.co.kr"
KIND_ETF_SEARCH_PAGE = (
    KIND_BASE_URL
    + "/disclosure/disclosurebystocktype.do?method=searchDisclosureByStockTypeEtf"
)
KIND_ETF_SEARCH_URL = KIND_BASE_URL + "/disclosure/disclosurebystocktype.do"
KIND_VIEWER_URL = KIND_BASE_URL + "/common/disclsviewer.do"
KIND_ETF_DISTRIBUTION_TITLE = "ETF이익금분배신고(분배금안내)(일괄공시)"
KIND_MAX_FILINGS_PER_ETF = 15

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/122 Safari/537.36 Wealth/1.3"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _stock_code(value: object) -> str:
    code = str(value or "").strip().upper()
    if code.startswith("A") and len(code) == 7:
        code = code[1:]
    return code


def _money(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("원", "")
    if not text or text in {"-", "--", "N/A", "n/a", "미정"}:
        return None
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < 0:
        return None
    return result


def _date_value(value: object) -> date | None:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "미정", "N/A", "n/a"}:
        return None
    match = re.search(r"(20\d{2})\D?(\d{1,2})\D?(\d{1,2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def short_code_from_isin(value: object) -> str | None:
    """Convert a Korean ISIN such as KR7379800006 to KRX short code 379800.

    New Korean security short codes may contain letters (for example
    KR70005G0001 -> 0005G0), so this must not be digit-only.
    """
    isin = str(value or "").strip().upper()
    if not re.fullmatch(r"KR[A-Z0-9]{10}", isin):
        return None
    return isin[3:9]


class _RowsParser(HTMLParser):
    """Small table parser used for both KIND result and external documents."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag.lower() == "tr":
            self._row = {"cells": [], "anchors": []}
        elif self._row is not None and tag.lower() in {"td", "th"}:
            self._cell = []
        elif self._row is not None and tag.lower() == "a":
            self._row["anchors"].append(
                {
                    "href": attrs_dict.get("href") or "",
                    "onclick": attrs_dict.get("onclick") or "",
                    "title": attrs_dict.get("title") or "",
                }
            )

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"td", "th"} and self._row is not None and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            self._row["cells"].append(text)
            self._cell = None
        elif lower == "tr" and self._row is not None:
            if self._row["cells"] or self._row["anchors"]:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def parse_kind_etf_search_results(html_text: str) -> list[dict[str, Any]]:
    parser = _RowsParser()
    parser.feed(str(html_text or ""))
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in parser.rows:
        cells = row.get("cells") or []
        if len(cells) < 4:
            continue
        for anchor in row.get("anchors") or []:
            onclick = str(anchor.get("onclick") or "")
            match = re.search(r"openDisclsViewer\(['\"](\d{14})['\"]", onclick)
            if not match:
                continue
            title = str(anchor.get("title") or "").strip()
            normalized = "".join(title.split()).replace("[정정]", "")
            if "ETF이익금분배신고" not in normalized or "분배금안내" not in normalized:
                continue
            receipt = match.group(1)
            if receipt in seen:
                continue
            seen.add(receipt)
            results.append(
                {
                    "receipt_no": receipt,
                    "filing_datetime": str(cells[1] if len(cells) > 1 else "").strip(),
                    "title": title or KIND_ETF_DISTRIBUTION_TITLE,
                    "viewer_url": (
                        f"{KIND_VIEWER_URL}?method=search&acptno={receipt}"
                    ),
                }
            )
    results.sort(
        key=lambda item: (item.get("filing_datetime") or "", item["receipt_no"]),
        reverse=True,
    )
    return results


def extract_external_document_paths(viewer_html: str) -> list[str]:
    """Return unique official /external/*.htm document paths from a viewer."""
    text = str(viewer_html or "")
    paths: list[str] = []
    for match in re.finditer(r"[\"'](/external/[^\"']+?\.html?)[\"']", text, re.I):
        path = match.group(1)
        if path not in paths:
            paths.append(path)
    return paths


def parse_kind_distribution_document(
    html_text: str,
    *,
    target_short_code: str | None = None,
) -> list[dict[str, Any]]:
    """Parse structurally complete ETF distribution rows from official HTML."""
    parser = _RowsParser()
    parser.feed(str(html_text or ""))
    target = _stock_code(target_short_code) if target_short_code else None
    events: list[dict[str, Any]] = []
    for row in parser.rows:
        cells = row.get("cells") or []
        if len(cells) < 5:
            continue
        isin = str(cells[0]).strip().upper()
        short_code = short_code_from_isin(isin)
        if not short_code or (target and short_code != target):
            continue
        record_date = _date_value(cells[2])
        payment_date = _date_value(cells[3])
        amount = _money(cells[4])
        if record_date is None or payment_date is None or amount is None or amount <= 0:
            continue
        events.append(
            {
                "isin": isin,
                "short_code": short_code,
                "name": str(cells[1]).strip(),
                "record_date": record_date.isoformat(),
                "payment_date": payment_date.isoformat(),
                "amount_per_unit_krw": amount,
                "confirmed_amount": True,
                "confirmed_payment_date": True,
                "source": "kind_etf_distribution",
            }
        )
    return events


async def _search_filings(
    client: httpx.AsyncClient,
    code: str,
    *,
    as_of: date,
) -> list[dict[str, Any]]:
    response = await client.post(
        KIND_ETF_SEARCH_URL,
        data={
            "method": "searchDisclosureByStockTypeEtfSub",
            "forward": "disclosurebystocktype_etf_sub",
            "currentPageSize": "100",
            "pageIndex": "1",
            "orderMode": "",
            "orderStat": "",
            "etfIsuSrtCd": f"A{code}",
            "reportCd": "",
            "reportTmp": "",
            "etfIsuSrtNm": "",
            "reportNm": "ETF이익금분배신고",
            "fromDate": f"{as_of.year}-01-01",
            "toDate": as_of.isoformat(),
        },
        headers={
            **_HEADERS,
            "Referer": KIND_ETF_SEARCH_PAGE,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=8.0,
    )
    response.raise_for_status()
    return parse_kind_etf_search_results(response.text)[:KIND_MAX_FILINGS_PER_ETF]


async def _events_from_receipt(
    client: httpx.AsyncClient,
    filing: dict[str, Any],
    *,
    target_code: str,
) -> list[dict[str, Any]]:
    receipt = str(filing.get("receipt_no") or "").strip()
    if not receipt:
        return []
    viewer = await client.get(
        KIND_VIEWER_URL,
        params={"method": "search", "acptno": receipt},
        headers={**_HEADERS, "Referer": KIND_ETF_SEARCH_PAGE},
        timeout=8.0,
    )
    viewer.raise_for_status()
    paths = extract_external_document_paths(viewer.text)
    for path in paths[:6]:
        response = await client.get(
            KIND_BASE_URL + path,
            headers={**_HEADERS, "Referer": str(filing.get("viewer_url") or KIND_ETF_SEARCH_PAGE)},
            timeout=8.0,
        )
        response.raise_for_status()
        parsed = parse_kind_distribution_document(
            response.text,
            target_short_code=target_code,
        )
        if parsed:
            for event in parsed:
                event.update(
                    {
                        "receipt_no": receipt,
                        "filing_datetime": filing.get("filing_datetime"),
                        "viewer_url": filing.get("viewer_url"),
                        "document_url": KIND_BASE_URL + path,
                    }
                )
            return parsed
    return []


async def fetch_kind_etf_distribution_events(
    code: str,
    *,
    as_of: date | datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch current-year official KIND distribution events for one ETF."""
    clean_code = _stock_code(code)
    day = as_of.date() if isinstance(as_of, datetime) else (as_of or _now_kst().date())
    if len(clean_code) != 6:
        return {"status": "invalid_code", "events": []}
    if not external_network_allowed():
        return {"status": "network_disabled", "events": []}

    own_client = client is None
    http = client or httpx.AsyncClient()
    try:
        filings = await _search_filings(http, clean_code, as_of=day)
        if not filings:
            return {"status": "no_official_filing", "events": []}
        tasks = [
            _events_from_receipt(http, filing, target_code=clean_code)
            for filing in filings
        ]
        batches = await asyncio.gather(*tasks, return_exceptions=True)
        events: list[dict[str, Any]] = []
        for batch in batches:
            if isinstance(batch, list):
                events.extend(batch)

        # A correction / later filing for the same economic event wins.
        selected: dict[tuple[str, str, str], dict[str, Any]] = {}
        for event in events:
            key = (
                str(event.get("short_code") or ""),
                str(event.get("record_date") or ""),
                str(event.get("payment_date") or ""),
            )
            existing = selected.get(key)
            if existing is None or (
                str(event.get("filing_datetime") or ""),
                str(event.get("receipt_no") or ""),
            ) > (
                str(existing.get("filing_datetime") or ""),
                str(existing.get("receipt_no") or ""),
            ):
                selected[key] = event
        final_events = sorted(
            selected.values(),
            key=lambda item: (item.get("payment_date") or "", item.get("receipt_no") or ""),
        )
        return {
            "status": "ok" if final_events else "no_structured_distribution",
            "events": final_events,
            "filing_count": len(filings),
        }
    except Exception:
        return {"status": "kind_unavailable", "events": []}
    finally:
        if own_client:
            await http.aclose()


def _schedule_buckets(summary: dict[str, Any]) -> dict[int, dict[str, Any]]:
    schedule = summary.get("monthly_schedule")
    if not isinstance(schedule, list):
        return {}
    result: dict[int, dict[str, Any]] = {}
    for bucket in schedule:
        if not isinstance(bucket, dict):
            continue
        month = bucket.get("month")
        if isinstance(month, (int, float)) and 1 <= int(month) <= 12:
            result[int(month)] = bucket
    return result


def _find_item(bucket: dict[str, Any] | None, code: str) -> dict[str, Any] | None:
    if not isinstance(bucket, dict) or not isinstance(bucket.get("items"), list):
        return None
    return next(
        (
            item
            for item in bucket["items"]
            if isinstance(item, dict) and _stock_code(item.get("code")) == code
        ),
        None,
    )


def _find_replaceable_item(
    bucket: dict[str, Any] | None, code: str
) -> dict[str, Any] | None:
    """Find only a legacy/heuristic item, never a KIND event added earlier."""
    if not isinstance(bucket, dict) or not isinstance(bucket.get("items"), list):
        return None
    return next(
        (
            item
            for item in bucket["items"]
            if isinstance(item, dict)
            and _stock_code(item.get("code")) == code
            and item.get("forecast_source") != "kind_etf_distribution"
        ),
        None,
    )


def _remove_item(bucket: dict[str, Any], item: dict[str, Any]) -> float:
    old = _money(item.get("payout_krw")) or 0.0
    bucket["items"].remove(item)
    bucket["total_krw"] = round((_money(bucket.get("total_krw")) or 0.0) - old)
    return old


def _recompute_row_months(summary: dict[str, Any], row: dict[str, Any]) -> None:
    code = _stock_code(row.get("code"))
    months: list[int] = []
    for month, bucket in _schedule_buckets(summary).items():
        if _find_item(bucket, code) is not None:
            months.append(month)
    row["payout_months"] = sorted(months)


def _apply_kind_events_to_row(
    summary: dict[str, Any],
    row: dict[str, Any],
    events: Iterable[dict[str, Any]],
    *,
    as_of: date,
) -> tuple[int, float]:
    code = _stock_code(row.get("code"))
    qty = _money(row.get("quantity")) or 0.0
    if qty <= 0:
        return 0, 0.0
    buckets = _schedule_buckets(summary)
    if not buckets:
        return 0, 0.0

    original_annual = _money(row.get("annual_payout_krw")) or 0.0
    allow_create = original_annual <= 0
    applied = 0
    total_delta = 0.0

    for event in events:
        amount = _money(event.get("amount_per_unit_krw"))
        record_day = _date_value(event.get("record_date"))
        payment_day = _date_value(event.get("payment_date"))
        if (
            amount is None
            or amount <= 0
            or record_day is None
            or payment_day is None
            or payment_day.year != as_of.year
        ):
            continue

        record_bucket = buckets.get(record_day.month)
        payment_bucket = buckets.get(payment_day.month)
        if payment_bucket is None:
            continue
        existing = _find_replaceable_item(record_bucket, code)
        if existing is None:
            existing = _find_replaceable_item(payment_bucket, code)
            source_bucket = payment_bucket if existing is not None else None
        else:
            source_bucket = record_bucket

        if existing is None and not allow_create:
            event["numeric_override"] = False
            event["numeric_override_reason"] = "no_safe_legacy_schedule_match"
            continue

        old_payout = 0.0
        if existing is not None and source_bucket is not None:
            old_payout = _remove_item(source_bucket, existing)

        new_payout = round(qty * amount)
        target_item = {
            "code": code,
            "name": row.get("name") or code,
            "quantity": qty,
            "currency": "KRW",
            "payout_krw": new_payout,
            "payout_orig": new_payout,
            "div_yield": row.get("div_yield") or 0.0,
            "forecast_source": "kind_etf_distribution",
            "record_date": record_day.isoformat(),
            "payment_date": payment_day.isoformat(),
            "receipt_no": event.get("receipt_no"),
        }
        payment_bucket.setdefault("items", []).append(target_item)
        payment_bucket["items"].sort(
            key=lambda value: value.get("payout_krw") or 0,
            reverse=True,
        )
        payment_bucket["total_krw"] = round(
            (_money(payment_bucket.get("total_krw")) or 0.0) + new_payout
        )

        delta = new_payout - old_payout
        current_annual = _money(row.get("annual_payout_krw")) or 0.0
        row["annual_payout_krw"] = round(current_annual + delta)
        row["annual_payout_orig"] = round(
            (_money(row.get("annual_payout_orig")) or current_annual) + delta,
            2,
        )
        row["annual_div_per_share"] = round(row["annual_payout_orig"] / qty, 4)
        event["numeric_override"] = True
        event["numeric_override_reason"] = None
        total_delta += delta
        applied += 1

    if applied:
        _recompute_row_months(summary, row)
    return applied, total_delta


async def enrich_dividend_summary_with_kind_etf_distributions(
    summary: dict[str, Any],
    holdings: list[dict[str, Any]],
    *,
    as_of: date | datetime | None = None,
    fx_rate: float = 1385.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Overlay structurally verified KIND ETF distribution events."""
    if not isinstance(summary, dict):
        return summary
    day = as_of.date() if isinstance(as_of, datetime) else (as_of or _now_kst().date())
    policy = summary.setdefault("forecast_source_policy", {})
    policy.update(
        {
            "kind_etf_reference_url": KIND_ETF_SEARCH_PAGE,
            "kind_etf_requires_no_additional_credential": True,
            "kind_etf_structured_distribution_required": True,
        }
    )
    rows = summary.get("holding_dividends")
    if not isinstance(rows, list):
        policy["kind_etf_status"] = "no_holding_rows"
        return summary

    etf_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("is_etf") is True
        and str(row.get("currency") or "KRW").upper() == "KRW"
        and len(_stock_code(row.get("code"))) == 6
    ]
    if not etf_rows:
        policy["kind_etf_status"] = "no_domestic_etf"
        return summary
    if not external_network_allowed():
        policy["kind_etf_status"] = "network_disabled"
        return summary

    own_client = client is None
    http = client or httpx.AsyncClient()
    try:
        results = await asyncio.gather(
            *[
                fetch_kind_etf_distribution_events(
                    _stock_code(row.get("code")),
                    as_of=day,
                    client=http,
                )
                for row in etf_rows
            ],
            return_exceptions=True,
        )
        total_delta = 0.0
        total_applied = 0
        structured_count = 0
        for row, result in zip(etf_rows, results):
            source = row.setdefault("forecast_source", {})
            if isinstance(result, Exception) or not isinstance(result, dict):
                source["kind_etf_status"] = "kind_unavailable"
                source["kind_etf_distributions"] = []
                continue
            events = result.get("events") if isinstance(result.get("events"), list) else []
            source["kind_etf_status"] = result.get("status")
            source["kind_etf_distributions"] = events
            source["kind_etf_confirmed_event_count"] = len(events)
            if events:
                source["official_data_available"] = True
            structured_count += len(events)
            applied, delta = _apply_kind_events_to_row(summary, row, events, as_of=day)
            source["kind_etf_numeric_override_count"] = applied
            if applied:
                source["numeric_source"] = "kind_etf_confirmed_overlay"
            total_applied += applied
            total_delta += delta

        if total_applied:
            total = (_money(summary.get("total_annual_dividend_krw")) or 0.0) + total_delta
            summary["total_annual_dividend_krw"] = round(total)
            summary["monthly_avg_dividend_krw"] = round(total / 12.0)
            summary["dividend_paying_count"] = sum(
                1
                for row in rows
                if isinstance(row, dict) and (_money(row.get("annual_payout_krw")) or 0.0) > 0
            )
            total_eval = 0.0
            for holding in holdings:
                if not isinstance(holding, dict):
                    continue
                qty = _money(holding.get("quantity")) or 0.0
                price = _money(holding.get("current_price")) or _money(holding.get("purchase_price")) or 0.0
                currency = str(holding.get("currency") or "KRW").upper()
                total_eval += qty * price * (fx_rate if currency == "USD" else 1.0)
            if total_eval > 0:
                summary["portfolio_yield"] = round(total / total_eval * 100.0, 2)
            rows.sort(key=lambda value: value.get("annual_payout_krw") or 0, reverse=True)

        policy["kind_etf_status"] = "ok"
        policy["kind_etf_structured_event_count"] = structured_count
        policy["kind_etf_numeric_override_count"] = total_applied
        return summary
    except Exception:
        policy["kind_etf_status"] = "kind_unavailable"
        return summary
    finally:
        if own_client:
            await http.aclose()


__all__ = [
    "KIND_ETF_DISTRIBUTION_TITLE",
    "KIND_ETF_SEARCH_PAGE",
    "enrich_dividend_summary_with_kind_etf_distributions",
    "extract_external_document_paths",
    "fetch_kind_etf_distribution_events",
    "parse_kind_distribution_document",
    "parse_kind_etf_search_results",
    "short_code_from_isin",
]
