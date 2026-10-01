from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any

from app.services.ipo.normalize import normalize_equity_registration_response


_RANGE_SEP_RE = re.compile(r"\s*(?:~|∼|～|부터)\s*")
_FULL_DATE_RE = re.compile(
    r"(?<!\d)(?P<year>20\d{2})\s*(?:[.\-/]|년)\s*"
    r"(?P<month>\d{1,2})\s*(?:[.\-/]|월)\s*"
    r"(?P<day>\d{1,2})(?:\s*일)?(?!\d)"
)
_COMPACT_DATE_RE = re.compile(r"(?<!\d)(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})(?!\d)")
_MONTH_DAY_RE = re.compile(
    r"(?<!\d)(?P<month>\d{1,2})\s*(?:[.\-/]|월)\s*"
    r"(?P<day>\d{1,2})(?:\s*일)?(?!\d)"
)
_DAY_ONLY_RE = re.compile(r"(?<!\d)(?P<day>\d{1,2})\s*일?(?!\d)")


def _iso_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _first_full_date(text: str) -> tuple[str | None, tuple[int, int, int] | None]:
    compact = _COMPACT_DATE_RE.search(text)
    normal = _FULL_DATE_RE.search(text)
    match = None
    if compact and normal:
        match = compact if compact.start() <= normal.start() else normal
    else:
        match = compact or normal
    if not match:
        return None, None
    year = int(match.group("year"))
    month = int(match.group("month"))
    day = int(match.group("day"))
    value = _iso_date(year, month, day)
    return value, (year, month, day) if value else None


def parse_dart_date_range(value: object) -> tuple[str | None, str | None]:
    """Parse OpenDART schedule text such as 2026.10.01 ~ 10.02.

    ``estkRs`` exposes ``sbd`` as filing text rather than a strict ISO field.
    Accept common DART date renderings while refusing invalid calendar dates.
    """
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return None, None

    parts = _RANGE_SEP_RE.split(text, maxsplit=1)
    first_text = parts[0]
    start, start_parts = _first_full_date(first_text)
    if not start or not start_parts:
        start, start_parts = _first_full_date(text)
    if not start or not start_parts:
        return None, None

    if len(parts) == 1:
        explicit: list[str] = []
        for regex in (_COMPACT_DATE_RE, _FULL_DATE_RE):
            for match in regex.finditer(text):
                candidate = _iso_date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
                if candidate and candidate not in explicit:
                    explicit.append(candidate)
        return (start, explicit[1]) if len(explicit) >= 2 else (start, start)

    end_text = parts[1]
    end, _ = _first_full_date(end_text)
    if end:
        return start, end

    year, month, _day = start_parts
    md = _MONTH_DAY_RE.search(end_text)
    if md:
        end = _iso_date(year, int(md.group("month")), int(md.group("day")))
        return start, end

    day_only = _DAY_ONLY_RE.search(end_text)
    if day_only:
        end = _iso_date(year, month, int(day_only.group("day")))
        return start, end

    return start, start


def parse_dart_single_date(value: object) -> str | None:
    start, _ = parse_dart_date_range(value)
    return start


def _rows_for_receipt(rows: object, rcept_no: str) -> list[dict[str, Any]]:
    values = [row for row in (rows or []) if isinstance(row, dict)]
    if not rcept_no:
        return values
    return [row for row in values if str(row.get("rcept_no") or "").strip() == rcept_no]


def _number(value: object) -> float | None:
    raw = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if not raw or raw in {"-", ".", "-."}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None



def select_dart_schedule_filing(
    filings: list[dict[str, Any]],
    raw_structured: dict[str, Any] | list[Any],
) -> dict[str, Any] | None:
    """Select the newest C001 receipt that is actually represented by estkRs."""
    structured = normalize_equity_registration_response(raw_structured)

    receipt_nos = {
        str(row.get("rcept_no") or "").strip()
        for row in structured.get("general", [])
        if isinstance(row, dict)
        and str(row.get("rcept_no") or "").strip()
        and (row.get("sbd") or row.get("pymd"))
    }
    if not receipt_nos:
        return None

    # Unicode-safe source spelling:
    # "securities issuance results report"
    issuance_result_report = (
        "\uc99d\uad8c\ubc1c\ud589"
        "\uc2e4\uc801\ubcf4\uace0\uc11c"
    )

    candidates: list[dict[str, Any]] = []
    for filing in filings or []:
        if not isinstance(filing, dict):
            continue

        rcept_no = str(filing.get("rcept_no") or "").strip()
        if rcept_no not in receipt_nos:
            continue

        report_nm = str(filing.get("report_nm") or "")
        if issuance_result_report in report_nm:
            continue

        candidates.append(filing)

    if not candidates:
        return None

    candidates.sort(
        key=lambda row: (
            str(row.get("rcept_dt") or ""),
            str(row.get("rcept_no") or ""),
        )
    )
    return candidates[-1]

def build_dart_offering_schedule(
    raw_structured: dict[str, Any] | list[Any],
    *,
    filing: dict[str, Any],
) -> dict[str, Any] | None:
    """Build canonical schedule facts from the official OpenDART equity filing.

    This is the API-backed equivalent of consuming DART's public offering board:
    ``list.json`` selects the C001 filing/amendment and ``estkRs`` supplies the
    structured subscription/payment/underwriter fields from that exact receipt.
    """
    structured = normalize_equity_registration_response(raw_structured)
    rcept_no = str(filing.get("rcept_no") or "").strip()
    general_rows = _rows_for_receipt(structured.get("general"), rcept_no)
    if not general_rows:
        return None

    general = general_rows[-1]
    subscription_start, subscription_end = parse_dart_date_range(general.get("sbd"))
    payment_date = parse_dart_single_date(general.get("pymd"))
    if not subscription_start and not payment_date:
        return None

    company_name = str(
        general.get("corp_name")
        or filing.get("corp_name")
        or filing.get("company_name")
        or ""
    ).strip()
    corp_code = str(general.get("corp_code") or filing.get("corp_code") or "").strip()
    stock_code = str(filing.get("stock_code") or "").strip()
    corp_cls = str(general.get("corp_cls") or filing.get("corp_cls") or "").strip().upper()

    underwriter_rows = _rows_for_receipt(structured.get("underwriters"), rcept_no)
    lead_managers: list[str] = []
    for row in underwriter_rows:
        name = str(row.get("actnmn") or "").strip()
        if name and name not in lead_managers:
            lead_managers.append(name)

    security_rows = _rows_for_receipt(structured.get("security_classes"), rcept_no)
    prices = [
        value
        for row in security_rows
        if (value := _number(row.get("slprc"))) is not None and value > 0
    ]
    structured_offer_price = (
        prices[0]
        if prices and all(value == prices[0] for value in prices)
        else None
    )

    report_nm = str(filing.get("report_nm") or "")
    final_conditions_marker = (
        "\ubc1c\ud589\uc870\uac74\ud655\uc815"
    )
    final_offer_price = (
        structured_offer_price
        if structured_offer_price is not None
        and final_conditions_marker in report_nm
        else None
    )

    source = {
        "schedule_source": "OpenDART C001 + estkRs",
        "board_reference": "https://dart.fss.or.kr/dsac005/main.do",
        "rcept_no": rcept_no or None,
        "source_date": filing.get("rcept_dt"),
        "report_nm": filing.get("report_nm"),
        "corp_cls": corp_cls or None,
        "structured_offer_price_reference": structured_offer_price,
        "offer_price_confirmed": final_offer_price is not None,
        "subscription_text": general.get("sbd"),
        "payment_text": general.get("pymd"),
        "subscription_notice_text": general.get("sband"),
        "allotment_notice_text": general.get("asand"),
        "observed_at": datetime.now().astimezone().isoformat(),
    }
    item: dict[str, Any] = {
        "company_name": company_name,
        "corp_code": corp_code,
        "listing_track": "spac" if ("스팩" in company_name or "기업인수목적" in company_name) else "general",
        "sources": {"dart_schedule": source},
    }
    if stock_code:
        item["stock_code"] = stock_code
    if subscription_start:
        item["subscription_start"] = subscription_start
    if subscription_end:
        item["subscription_end"] = subscription_end
    if payment_date:
        item["payment_date"] = payment_date
    if lead_managers:
        item["lead_managers"] = lead_managers
    if final_offer_price is not None:
        item["final_offer_price"] = final_offer_price
    return item
