from __future__ import annotations

from pathlib import Path
import re


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}: {old[:120]!r}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


PARSER = r'''"""Structured parsing for OpenDART cash-dividend decision filings.

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
'''

TESTS = r'''from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import AsyncMock, patch

from app.services.dividend_confirmed_disclosures import parse_dividend_decision_document
from app.services import dividend_official_sources as official


DISCLOSURE = """
<html><body><table>
<tr><th>구분</th><th>내용</th></tr>
<tr><td>3. 1주당 배당금 (원)</td><td>보통주식</td><td>1,250</td></tr>
<tr><td>배당기준일</td><td>2026년 09월 30일</td></tr>
<tr><td>배당금지급 예정일자</td><td>2026-11-20</td></tr>
</table></body></html>
"""


class ConfirmedDividendDisclosureParserTests(unittest.TestCase):
    def test_structurally_parses_amount_and_dates(self):
        result = parse_dividend_decision_document(
            DISCLOSURE,
            report_name="현금ㆍ현물배당 결정",
            receipt_no="20260926000123",
            receipt_date="20260926",
            viewer_url="https://dart.fss.or.kr/example",
            as_of=date(2026, 9, 26),
        )
        self.assertTrue(result["structured_verification"])
        self.assertTrue(result["confirmed_amount"])
        self.assertEqual(result["ordinary_cash_dps_krw"], 1250.0)
        self.assertEqual(result["record_date"], "2026-09-30")
        self.assertEqual(result["payment_date"], "2026-11-20")
        self.assertTrue(result["future_payment"])

    def test_missing_payment_date_is_not_invented(self):
        result = parse_dividend_decision_document(
            "<table><tr><td>1주당 배당금(원)</td><td>보통주식</td><td>500</td></tr></table>",
            report_name="현금ㆍ현물배당 결정",
            receipt_no="20260926000124",
            as_of=date(2026, 9, 26),
        )
        self.assertTrue(result["confirmed_amount"])
        self.assertIsNone(result["payment_date"])
        self.assertFalse(result["confirmed_payment_date"])
        self.assertIsNone(result["future_payment"])

    def test_title_match_without_structured_amount_is_not_confirmed(self):
        result = parse_dividend_decision_document(
            "<table><tr><td>배당기준일</td><td>2026-09-30</td></tr></table>",
            report_name="현금ㆍ현물배당 결정",
            receipt_no="20260926000125",
        )
        self.assertFalse(result["confirmed_amount"])
        self.assertFalse(result["structured_verification"])

    def test_non_decision_report_is_rejected(self):
        result = parse_dividend_decision_document(
            DISCLOSURE,
            report_name="사업보고서",
            receipt_no="20260926000126",
        )
        self.assertFalse(result["confirmed_amount"])
        self.assertEqual(result["reason"], "not_dividend_decision_report")


class ConfirmedDividendForecastIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_future_amount_replaces_matching_month_estimate(self):
        summary = {
            "holding_dividends": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 10,
                    "currency": "KRW",
                    "annual_div_per_share": 4000,
                    "annual_payout_orig": 40000,
                    "annual_payout_krw": 40000,
                    "payout_months": [4, 5, 8, 11],
                    "div_yield": 5.0,
                }
            ],
            "monthly_schedule": [
                {"month": m, "total_krw": (10000 if m in {4, 5, 8, 11} else 0), "items": ([{
                    "code": "005930", "name": "삼성전자", "quantity": 10,
                    "currency": "KRW", "payout_krw": 10000, "payout_orig": 10000,
                    "div_yield": 5.0,
                }] if m in {4, 5, 8, 11} else [])}
                for m in range(1, 13)
            ],
            "total_annual_dividend_krw": 40000,
            "monthly_avg_dividend_krw": 3333,
            "portfolio_yield": 5.0,
        }
        evidence = {
            "status": "ok",
            "policy": {},
            "evidence": {
                "005930": {
                    "official_data_available": True,
                    "historical": {},
                    "recent_decision_disclosure": {"receipt_no": "20260926000123"},
                    "structured_decision_disclosure": {
                        "confirmed_amount": True,
                        "structured_verification": True,
                        "ordinary_cash_dps_krw": 1250,
                        "payment_date": "2026-11-20",
                        "future_payment": True,
                    },
                }
            },
        }
        with patch.object(
            official,
            "get_official_dividend_evidence",
            new=AsyncMock(return_value=evidence),
        ):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "005930", "currency": "KRW", "quantity": 10, "current_price": 80000}],
                as_of=date(2026, 9, 26),
            )
        row = result["holding_dividends"][0]
        november = result["monthly_schedule"][10]
        self.assertEqual(november["total_krw"], 12500)
        self.assertEqual(row["annual_payout_krw"], 42500)
        self.assertEqual(row["annual_div_per_share"], 4250)
        self.assertEqual(result["total_annual_dividend_krw"], 42500)
        self.assertEqual(row["forecast_source"]["numeric_source"], "opendart_confirmed_disclosure")
        self.assertTrue(row["forecast_source"]["confirmed_amount"])
        self.assertTrue(row["forecast_source"]["confirmed_numeric_override"])

    async def test_confirmed_amount_without_payment_date_keeps_numeric_fallback(self):
        summary = {
            "holding_dividends": [{
                "code": "005930", "name": "삼성전자", "quantity": 10,
                "currency": "KRW", "annual_div_per_share": 1500,
                "annual_payout_orig": 15000, "annual_payout_krw": 15000,
                "payout_months": [11],
            }],
            "monthly_schedule": [{"month": m, "total_krw": 0, "items": []} for m in range(1, 13)],
            "total_annual_dividend_krw": 15000,
        }
        evidence = {
            "status": "ok", "policy": {}, "evidence": {"005930": {
                "official_data_available": True,
                "historical": {},
                "structured_decision_disclosure": {
                    "confirmed_amount": True,
                    "structured_verification": True,
                    "ordinary_cash_dps_krw": 1700,
                    "payment_date": None,
                    "future_payment": None,
                },
            }},
        }
        with patch.object(official, "get_official_dividend_evidence", new=AsyncMock(return_value=evidence)):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "005930", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        source = result["holding_dividends"][0]["forecast_source"]
        self.assertTrue(source["confirmed_amount"])
        self.assertFalse(source["confirmed_numeric_override"])
        self.assertEqual(source["numeric_source"], "naver")
        self.assertEqual(result["total_annual_dividend_krw"], 15000)

    async def test_confirmed_event_can_create_forecast_when_legacy_is_zero(self):
        summary = {
            "holding_dividends": [{
                "code": "005930", "name": "삼성전자", "quantity": 10,
                "currency": "KRW", "annual_div_per_share": 0,
                "annual_payout_orig": 0, "annual_payout_krw": 0,
                "payout_months": [],
            }],
            "monthly_schedule": [{"month": m, "total_krw": 0, "items": []} for m in range(1, 13)],
            "total_annual_dividend_krw": 0,
        }
        evidence = {
            "status": "ok", "policy": {}, "evidence": {"005930": {
                "official_data_available": True,
                "historical": {},
                "structured_decision_disclosure": {
                    "confirmed_amount": True,
                    "structured_verification": True,
                    "ordinary_cash_dps_krw": 600,
                    "payment_date": "2026-12-20",
                    "future_payment": True,
                },
            }},
        }
        with patch.object(official, "get_official_dividend_evidence", new=AsyncMock(return_value=evidence)):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "005930", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        row = result["holding_dividends"][0]
        self.assertEqual(row["annual_payout_krw"], 6000)
        self.assertEqual(result["monthly_schedule"][11]["total_krw"], 6000)
        self.assertEqual(row["payout_months"], [12])
        self.assertTrue(row["forecast_source"]["confirmed_numeric_override"])


if __name__ == "__main__":
    unittest.main()
'''


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser_path = root / "app/services/dividend_confirmed_disclosures.py"
    parser_path.write_text(PARSER, encoding="utf-8")
    tests_path = root / "tests/test_dividend_confirmed_disclosures.py"
    tests_path.write_text(TESTS, encoding="utf-8")

    official = root / "app/services/dividend_official_sources.py"
    replace_once(
        official,
        "from app.services.ipo.dart_client import DartClient\n",
        "from app.services.dividend_confirmed_disclosures import parse_dividend_decision_document\n"
        "from app.services.ipo.dart_client import DartClient, extract_document_text_from_zip\n",
    )
    replace_once(
        official,
        'OPENDART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"\n',
        'OPENDART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"\n'
        'OPENDART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"\n',
    )
    marker = "\n\nasync def get_official_dividend_evidence(\n"
    structured_fetch = r'''

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
'''
    replace_once(official, marker, structured_fetch + marker)

    replace_once(
        official,
        '''                recent = await _fetch_recent_decision(\n                    http, key, corp_code, as_of=day\n                )\n                evidence[code] = {\n                    "official_data_available": bool(periodic.get("available") or recent),\n                    "corp_code": corp_code,\n                    "historical": periodic,\n                    "recent_decision_disclosure": recent,\n                }\n''',
        '''                recent = await _fetch_recent_decision(\n                    http, key, corp_code, as_of=day\n                )\n                structured = None\n                if recent:\n                    try:\n                        structured = await _fetch_structured_decision(\n                            http, key, recent, as_of=day\n                        )\n                    except Exception:\n                        structured = {\n                            **recent,\n                            "structured_verification": False,\n                            "confirmed_amount": False,\n                            "confirmed_payment_date": False,\n                            "ordinary_cash_dps_krw": None,\n                            "record_date": None,\n                            "payment_date": None,\n                            "future_payment": None,\n                            "reason": "document_parse_failed",\n                        }\n                evidence[code] = {\n                    "official_data_available": bool(periodic.get("available") or recent),\n                    "corp_code": corp_code,\n                    "historical": periodic,\n                    "recent_decision_disclosure": recent,\n                    "structured_decision_disclosure": structured,\n                }\n''',
    )
    replace_once(
        official,
        '        "confirmed_amount_requires_structured_verification": True,\n',
        '        "confirmed_amount_requires_structured_verification": True,\n'
        '        "confirmed_numeric_override_requires_safe_payment_month": True,\n'
        '        "opendart_document_url": OPENDART_DOCUMENT_URL,\n',
    )

    enrich_marker = "\n\nasync def enrich_dividend_summary_with_official_sources(\n"
    override_helper = r'''

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
'''
    replace_once(official, enrich_marker, override_helper + enrich_marker)

    replace_once(
        official,
        '''        evidence = evidence_map.get(code) if isinstance(evidence_map.get(code), dict) else {}\n        historical = evidence.get("historical") if isinstance(evidence.get("historical"), dict) else {}\n        official_dps = _money(historical.get("ordinary_cash_dps_krw"))\n''',
        '''        evidence = evidence_map.get(code) if isinstance(evidence_map.get(code), dict) else {}\n        historical = evidence.get("historical") if isinstance(evidence.get("historical"), dict) else {}\n        structured = (\n            evidence.get("structured_decision_disclosure")\n            if isinstance(evidence.get("structured_decision_disclosure"), dict)\n            else None\n        )\n        official_dps = _money(historical.get("ordinary_cash_dps_krw"))\n''',
    )
    replace_once(
        official,
        '''            "recent_decision_disclosure": evidence.get("recent_decision_disclosure"),\n            "confirmed_amount": False,\n            "kind_reference_url": KIND_DIVIDEND_INFO_URL,\n''',
        '''            "recent_decision_disclosure": evidence.get("recent_decision_disclosure"),\n            "structured_decision_disclosure": structured,\n            "confirmed_amount": bool(structured and structured.get("confirmed_amount") is True),\n            "confirmed_numeric_override": False,\n            "kind_reference_url": KIND_DIVIDEND_INFO_URL,\n''',
    )
    replace_once(
        official,
        '''    if changed:\n        _rebuild_summary_from_holdings(summary, holdings, fx_rate=fx_rate)\n    return summary\n''',
        '''    if changed:\n        _rebuild_summary_from_holdings(summary, holdings, fx_rate=fx_rate)\n    day = as_of.date() if isinstance(as_of, datetime) else (as_of or _now_kst().date())\n    _apply_confirmed_future_overrides(\n        summary, holdings, fx_rate=fx_rate, as_of=day\n    )\n    return summary\n''',
    )

    js = root / "app/static/wealth-dividend-source.js"
    replace_once(
        js,
        "  function sourceLabel(source) {\n    if (source === 'opendart_historical_fill') return 'OpenDART 공식 이력 보정';\n",
        "  function sourceLabel(source) {\n    if (source === 'opendart_confirmed_disclosure') return 'OpenDART 확정 공시';\n    if (source === 'opendart_historical_fill') return 'OpenDART 공식 이력 보정';\n",
    )
    replace_once(
        js,
        "    let confirmedAmountCount = 0;\n",
        "    let confirmedAmountCount = 0;\n    let confirmedOverrideCount = 0;\n",
    )
    replace_once(
        js,
        "      if (source.confirmed_amount === true) confirmedAmountCount += 1;\n",
        "      if (source.confirmed_amount === true) confirmedAmountCount += 1;\n      if (source.confirmed_numeric_override === true) confirmedOverrideCount += 1;\n",
    )
    replace_once(
        js,
        "    if (confirmedAmountCount > 0) {\n      pieces.push(`구조 검증된 확정금액 ${confirmedAmountCount}종목`);\n    }\n",
        "    if (confirmedAmountCount > 0) {\n      pieces.push(`구조 검증된 확정금액 ${confirmedAmountCount}종목`);\n    }\n    if (confirmedOverrideCount > 0) {\n      pieces.push(`확정 공시 금액 반영 ${confirmedOverrideCount}종목`);\n    }\n",
    )
    replace_once(
        js,
        "      note.textContent = '공식 과거 DPS는 기존 추정이 없을 때만 보정하며, 배당결정 공시가 존재해도 금액이 구조적으로 검증되지 않으면 확정금액으로 표시하지 않습니다.';\n",
        "      note.textContent = '배당결정 원문에서 주당배당금이 구조 검증된 경우만 확정금액으로 표시합니다. 지급예정일이 확인되고 기존 예상월과 안전하게 매칭될 때만 해당 월 추정금액을 확정 공시값으로 교체하며, 지급일은 임의 생성하지 않습니다.';\n",
    )

    static_test = root / "tests/test_dividend_official_source_static.py"
    replace_once(
        static_test,
        '        self.assertIn("confirmed_amount", js)\n',
        '        self.assertIn("confirmed_amount", js)\n'
        '        self.assertIn("opendart_confirmed_disclosure", js)\n'
        '        self.assertIn("confirmed_numeric_override", js)\n'
        '        self.assertIn("지급예정일", js)\n',
    )

    state = root / "docs/PROJECT_STATE.md"
    state_text = state.read_text(encoding="utf-8")
    state_text = state_text.replace(
        "현재 작업 단계는 **Phase 10.5A-4.2 — 고배당 분리과세 What-if 연결**입니다.",
        "현재 작업 단계는 **Phase 10.5A-4.3 — 미래 배당 확정공시 구조화**입니다.",
    )
    state_text = re.sub(
        r"현재 작업:\n\n- branch:.*?\n\nA-4\.2 목표:\n\n.*?\n\n## 2\.",
        "현재 작업:\n\n"
        "- branch: `phase10-5a43-confirmed-dividend-disclosures`\n"
        "- base: `main`\n"
        "- 상태: 구현/검증 중\n"
        "- 작업 시작 기준 main: `0f5f25a` (PR #23 merge)\n\n"
        "A-4.3 목표:\n\n"
        "1. OpenDART 배당결정 공시 원문에서 주당배당금·기준일·지급예정일을 구조 검증한다.\n"
        "2. 제목 매칭만으로 `confirmed_amount=true`를 만들지 않는다.\n"
        "3. 지급예정일이 없으면 날짜를 추정하거나 생성하지 않는다.\n"
        "4. 현재 연도 미래 지급월과 기존 예상월이 안전하게 매칭될 때만 확정 금액으로 월별 예상을 교체한다.\n"
        "5. 원문 조회/파싱 실패 시 기존 Naver/Yahoo/공식 과거 이력 fallback을 유지한다.\n\n"
        "## 2.",
        state_text,
        flags=re.S,
    )
    state_text = state_text.replace(
        "- [ ] 10.5A-4.2 고배당 분리과세 What-if 연결 — 진행 중",
        "- [x] 10.5A-4.2 고배당 분리과세 What-if 연결 — PR #23 merge (`0f5f25a`)\n"
        "- [ ] 10.5A-4.3 미래 배당 확정공시 구조화 — 진행 중",
    )
    state.write_text(state_text, encoding="utf-8")

    roadmap = root / "docs/ROADMAP.md"
    roadmap_text = roadmap.read_text(encoding="utf-8")
    roadmap_text = re.sub(
        r"## 1\. 현재 우선순위\n\n.*?\n\n## 2\. 다음 단계",
        "## 1. 현재 우선순위\n\n"
        "### Phase 10.5A-4.3 — 미래 배당 확정공시 구조화\n\n"
        "상태: 구현/검증 중\n\n"
        "A-4.2 고배당 분리과세 What-if 연결은 PR #23 (`0f5f25a`)로 완료되었습니다.\n\n"
        "목표:\n\n"
        "- OpenDART 배당결정 공시 원문 ZIP을 접수번호로 조회한다.\n"
        "- 보통주 1주당 현금배당금, 배당기준일, 지급예정일을 구조 검증한다.\n"
        "- 구조 검증 성공 시에만 `confirmed_amount=true`로 처리한다.\n"
        "- 지급예정일은 공시에 명시된 경우에만 사용한다.\n"
        "- 안전한 월 매칭이 가능한 경우 확정 공시 금액을 휴리스틱 월 예상보다 우선한다.\n"
        "- 정정공시는 최신 유효 접수번호를 우선한다.\n"
        "- 실패 시 기존 Naver/Yahoo/과거 OpenDART fallback을 유지한다.\n\n"
        "완료 기준:\n\n"
        "- 제목만 존재하는 공시는 확정금액으로 승격되지 않음\n"
        "- 보통주 주당배당금 구조 파싱 테스트\n"
        "- 기준일/지급일 미기재 시 날짜 생성 금지 테스트\n"
        "- 현재 연도 미래 지급월 안전 override 테스트\n"
        "- 기존 A-4.1 source/fallback 회귀 통과\n"
        "- 전체 unittest suite 통과\n"
        "- 사용자 로컬 검증 완료\n"
        "- PR Ready → merge\n"
        "- GHCR build success\n\n"
        "## 2. 다음 단계",
        roadmap_text,
        flags=re.S,
    )
    roadmap_text = re.sub(
        r"\n### Phase 10\.5A-4\.3 — 미래 배당 확정공시 구조화\n\n.*?(?=\n### Phase 10\.5A-4\.4)",
        "",
        roadmap_text,
        flags=re.S,
    )
    roadmap.write_text(roadmap_text, encoding="utf-8")


if __name__ == "__main__":
    main()
