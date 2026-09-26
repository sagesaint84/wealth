"""Structured parsing for OpenDART cash-dividend decision filings.

This parser is intentionally conservative.  A filing-title match is not enough:
`confirmed_amount` becomes true only when an ordinary-share per-share cash
amount is found in the original disclosure document.  Dates are returned only
when they are explicitly present in the filing; no payment date is inferred.
"""

from __future__ import annotations

from datetime import date
from html import unescape
from html.parser import HTMLParser
import math
import re
from typing import Any

PARSER_VERSION = "2026-09-26-a43-v1"


class _DisclosureTableParser(HTMLParser):
    _CELL_TAGS = {"td", "th", "te", "tu"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[no-untyped-def]
        tag = tag.lower()
        if tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = []
        elif tag in self._CELL_TAGS:
            if self._row is None:
                self._row = []
            self._cell_parts = []
        elif tag == "br" and self._cell_parts is not None:
            self._cell_parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._CELL_TAGS and self._cell_parts is not None:
            text = " ".join("".join(self._cell_parts).split())
            if self._row is None:
                self._row = []
            self._row.append(text)
            self._cell_parts = None
        elif tag == "tr":
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell_parts = None

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def close(self) -> None:
        super().close()
        if self._row:
            self.rows.append(self._row)
            self._row = None


def _normalize(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _money(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("원", "")
    text = text.replace("₩", "").strip()
    if not text or text in {"-", "--", "해당없음", "없음"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        number = float(match.group(0))
    except ValueError:
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _parse_date(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "미정", "추후결정", "해당없음"}:
        return None
    match = re.search(
        r"(?P<y>20\d{2})\s*(?:[./-]|년)\s*(?P<m>\d{1,2})\s*(?:[./-]|월)\s*(?P<d>\d{1,2})\s*(?:일)?",
        text,
    )
    if not match:
        match = re.search(r"(?P<y>20\d{2})(?P<m>\d{2})(?P<d>\d{2})", text)
    if not match:
        return None
    try:
        parsed = date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
    except ValueError:
        return None
    return parsed.isoformat()


def _fallback_rows(markup: str) -> list[list[str]]:
    text = re.sub(r"(?i)</(?:td|th|te|tu)\s*>", "\t", markup)
    text = re.sub(r"(?i)</tr\s*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    rows: list[list[str]] = []
    for raw_row in unescape(text).splitlines():
        cells = [" ".join(cell.split()) for cell in raw_row.split("\t")]
        cells = [cell for cell in cells if cell]
        if cells:
            rows.append(cells)
    return rows


def _table_rows(markup: str) -> list[list[str]]:
    parser = _DisclosureTableParser()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:
        pass
    rows = [row for row in parser.rows if row]
    rows.extend(_fallback_rows(markup))
    deduped: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        key = tuple(row)
        if key and key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped


def _ordinary_cash_dps(rows: list[list[str]]) -> float | None:
    for row in rows:
        normalized = [_normalize(cell) for cell in row]
        if not any("1주당배당금" in cell or "주당배당금" in cell for cell in normalized):
            continue
        ordinary_indexes = [
            idx for idx, cell in enumerate(normalized)
            if "보통주" in cell or "ordinary" in cell
        ]
        if ordinary_indexes:
            for idx in ordinary_indexes:
                for cell in row[idx + 1 :]:
                    amount = _money(cell)
                    if amount is not None:
                        return amount
        # Some single-class issuers omit the stock-kind cell.  Accept the row
        # only when it does not mention a preferred/class share at all.
        if not any("우선주" in cell or "종류주" in cell for cell in normalized):
            label_index = next(
                (idx for idx, cell in enumerate(normalized) if "주당배당금" in cell),
                -1,
            )
            if label_index >= 0:
                for cell in row[label_index + 1 :]:
                    amount = _money(cell)
                    if amount is not None:
                        return amount
    return None


def _date_after_label(rows: list[list[str]], labels: tuple[str, ...]) -> str | None:
    normalized_labels = tuple(_normalize(label) for label in labels)
    for row in rows:
        normalized = [_normalize(cell) for cell in row]
        for idx, cell in enumerate(normalized):
            if not any(label in cell for label in normalized_labels):
                continue
            for value in row[idx + 1 :]:
                parsed = _parse_date(value)
                if parsed:
                    return parsed
    return None


def parse_dividend_decision_document(
    document_text: str,
    *,
    report_name: str,
    receipt_no: str,
    receipt_date: str = "",
    viewer_url: str = "",
    as_of: date | None = None,
) -> dict[str, Any]:
    """Parse one dividend-decision disclosure into structurally verified fields."""
    normalized_report = _normalize(report_name)
    base = {
        "report_name": report_name,
        "receipt_no": receipt_no,
        "receipt_date": receipt_date,
        "viewer_url": viewer_url,
        "parser_version": PARSER_VERSION,
        "structured_verification": False,
        "confirmed_amount": False,
        "confirmed_payment_date": False,
        "ordinary_cash_dps_krw": None,
        "record_date": None,
        "payment_date": None,
        "future_payment": None,
    }
    if "배당" not in normalized_report or "결정" not in normalized_report:
        return {**base, "reason": "not_dividend_decision_report"}
    if not isinstance(document_text, str) or not document_text.strip():
        return {**base, "reason": "empty_document"}

    rows = _table_rows(document_text)
    dps = _ordinary_cash_dps(rows)
    record_date = _date_after_label(rows, ("배당기준일",))
    payment_date = _date_after_label(
        rows,
        ("배당금지급예정일자", "배당금 지급 예정일자", "지급예정일자"),
    )
    if dps is None:
        return {
            **base,
            "record_date": record_date,
            "payment_date": payment_date,
            "confirmed_payment_date": payment_date is not None,
            "reason": "ordinary_cash_dps_not_structurally_verified",
        }

    future_payment: bool | None = None
    if payment_date and as_of:
        future_payment = date.fromisoformat(payment_date) >= as_of

    return {
        **base,
        "structured_verification": True,
        "confirmed_amount": True,
        "confirmed_payment_date": payment_date is not None,
        "ordinary_cash_dps_krw": dps,
        "record_date": record_date,
        "payment_date": payment_date,
        "future_payment": future_payment,
        "reason": None,
    }


__all__ = ["PARSER_VERSION", "parse_dividend_decision_document"]
