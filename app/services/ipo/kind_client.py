from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.network_policy import require_external_network


class KindClientError(RuntimeError):
    """Raised when the KIND transport or response contract fails."""


class KindParserError(KindClientError):
    """Raised when KIND HTML table schema fails validation."""


KIND_BASE_URL = "https://kind.krx.co.kr"
KIND_PUB_OFR_PATH = "/listinvstg/pubofrprogcom.do"

# Expected table header synonyms in KIND pubofrprogcom
EXPECTED_HEADER_KEYWORDS = [
    "회사명", "증권구분", "수요예측", "청약일", "납입일", "공모가", "공모금액", "상장예정일", "주관사"
]


def build_kind_request_payload(
    from_date: str,
    to_date: str,
    page_size: int = 100,
    page_index: int = 1,
    corp_name: str | None = None,
) -> dict[str, str]:
    params = {
        "method": "searchPubofrProgComSub",
        "forward": "pubofrprogcom_sub",
        "searchMode": "1",
        "currentPageSize": str(page_size),
        "pageIndex": str(page_index),
        "orderMode": "1",
        "orderStat": "D",
        "fromDate": from_date,
        "toDate": to_date,
    }
    if corp_name:
        params["searchCorpName"] = corp_name
        params["searchCorpNameTmp"] = corp_name
    return params


def parse_schedule_range(text: str) -> tuple[str | None, str | None]:
    """Parse '2026.09.17 ~ 2026.09.18' into ('2026-09-17', '2026-09-18')."""
    if not text:
        return None, None
    matches = re.findall(r"(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})", text)
    if len(matches) >= 2:
        d1 = f"{matches[0][0]}-{int(matches[0][1]):02d}-{int(matches[0][2]):02d}"
        d2 = f"{matches[1][0]}-{int(matches[1][1]):02d}-{int(matches[1][2]):02d}"
        return d1, d2
    elif len(matches) == 1:
        d1 = f"{matches[0][0]}-{int(matches[0][1]):02d}-{int(matches[0][2]):02d}"
        return d1, d1
    return None, None


def parse_single_date(text: str) -> str | None:
    if not text:
        return None
    m = re.search(r"(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})", text)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def _clean_kind_header_text(value: str) -> str:
    clean = re.sub(r"<br\s*/?>", "", value, flags=re.IGNORECASE)
    clean = re.sub(r"<[^>]+>", "", clean)
    clean = clean.replace("곰모가", "공모가")  # KIND live summary typo tolerance
    return clean.strip()


def _extract_kind_headers(html_text: str, table_attrs: str, table_body: str) -> tuple[list[str], bool]:
    """Return (headers, first_row_is_header) for KIND's server-rendered table contract."""
    row_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", table_body, re.DOTALL | re.IGNORECASE)
    if not row_matches:
        return [], False

    first_row = row_matches[0]
    th_matches = re.findall(r"<th[^>]*>(.*?)</th>", first_row, re.DOTALL | re.IGNORECASE)
    if th_matches:
        return [_clean_kind_header_text(v) for v in th_matches], True

    td_matches = re.findall(r"<td[^>]*>(.*?)</td>", first_row, re.DOTALL | re.IGNORECASE)
    td_headers = [_clean_kind_header_text(v) for v in td_matches]
    if td_headers and any(any(k in h for k in ("회사명", "수요예측", "청약", "상장")) for h in td_headers):
        return td_headers, True

    # Current KIND live responses render an empty <thead> and inject titles with fn_InitTitle().
    title_match = re.search(r'fn_InitTitle\(\s*["\'](.*?)["\']\s*,', html_text, re.DOTALL | re.IGNORECASE)
    if title_match:
        headers = [_clean_kind_header_text(v) for v in title_match.group(1).split(",")]
        return headers, not bool(re.sub(r"<[^>]+>", "", first_row).strip())

    # Fallback to the table summary attribute used by KIND. Keep fail-closed validation below.
    summary_match = re.search(r'summary\s*=\s*["\'](.*?)["\']', table_attrs, re.DOTALL | re.IGNORECASE)
    if summary_match:
        headers = [_clean_kind_header_text(v) for v in summary_match.group(1).split(",")]
        return headers, not bool(re.sub(r"<[^>]+>", "", first_row).strip())

    return [], False


def parse_kind_html(html_text: str) -> list[dict[str, Any]]:
    """Parse KIND HTML response and return canonical IPO items.

    Fail-closed: malformed/non-matching tables raise KindParserError, while KIND's
    documented live "no results" envelope returns an authoritative empty list.
    """
    if not html_text or not isinstance(html_text, str):
        raise KindParserError("KIND response HTML is empty or invalid")

    empty_markers = (
        "조회된 내역이 없습니다",
        "검색 결과가 없습니다",
        "조회된 결과값이 없습니다",
    )
    if any(marker in html_text for marker in empty_markers):
        return []

    if "<table" not in html_text:
        raise KindParserError("KIND response does not contain an HTML table (schema_mismatch)")

    table_matches = re.findall(
        r"<table(?P<attrs>[^>]*)>(?P<body>.*?)</table>",
        html_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not table_matches:
        raise KindParserError("Failed to extract table contents from KIND response")

    target_attrs = ""
    target_table = ""
    for attrs, body in table_matches:
        table_contract = f"{attrs} {body}"
        if (
            "공모기업현황" in table_contract
            or ("회사명" in attrs and ("청약" in attrs or "상장예정일" in attrs))
            or all(keyword in table_contract for keyword in ("회사명", "청약"))
        ):
            target_attrs, target_table = attrs, body
            break

    if not target_table:
        raise KindParserError("KIND table does not match required schema headings (schema_mismatch)")

    row_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", target_table, re.DOTALL | re.IGNORECASE)
    if not row_matches:
        return []

    headers, first_row_is_header = _extract_kind_headers(html_text, target_attrs, target_table)

    REQUIRED_HEADING_CATEGORIES = [
        ("회사명", ["회사명", "기업명"]),
        ("수요예측", ["수요예측"]),
        ("청약", ["청약일", "공모일", "청약"]),
        ("납입", ["납입일"]),
        ("공모가", ["공모가", "확정공모가"]),
        ("공모금액", ["공모금액"]),
        ("상장예정일", ["상장일", "상장예정일"]),
        ("상장주선인", ["주관사", "대표주관", "상장주선인"]),
    ]
    matched_cats = sum(
        1 for _, syns in REQUIRED_HEADING_CATEGORIES
        if any(any(s in h for s in syns) for h in headers)
    )
    if matched_cats < 5:
        raise KindParserError(f"KIND table header missing required core headings (schema_mismatch: {matched_cats}/8)")

    results: list[dict[str, Any]] = []
    data_rows = row_matches[1:] if first_row_is_header else row_matches

    for row in data_rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if not tds or len(tds) < 3:
            continue

        raw_cells = [re.sub(r"<[^>]+>", "", td).strip() for td in tds]

        bz_procs_no = None
        procs_match = re.search(r"bzProcsNo[='](\d+)", row) or re.search(r"fnOpen\(['\"](\d+)", row)
        if procs_match:
            bz_procs_no = procs_match.group(1)

        item: dict[str, Any] = {
            "company_name": "",
            "filing_date": None,
            "demand_forecast_start": None,
            "demand_forecast_end": None,
            "subscription_start": None,
            "subscription_end": None,
            "payment_date": None,
            "refund_date": None,
            "final_offer_price": None,
            "offering_amount_million_krw": None,
            "expected_listing_date": None,
            "lead_manager": "",
            "kind_bz_procs_no": bz_procs_no,
        }

        for idx, header in enumerate(headers):
            if idx >= len(raw_cells):
                break
            cell = raw_cells[idx]

            if "회사명" in header or "기업명" in header:
                item["company_name"] = cell
            elif "신고일" in header or "제출일" in header:
                item["filing_date"] = parse_single_date(cell)
            elif "수요예측" in header:
                start, end = parse_schedule_range(cell)
                item["demand_forecast_start"] = start
                item["demand_forecast_end"] = end
            elif "청약일" in header or "공모일" in header or header == "청약":
                start, end = parse_schedule_range(cell)
                item["subscription_start"] = start
                item["subscription_end"] = end
            elif "납입일" in header:
                item["payment_date"] = parse_single_date(cell)
            elif "환불일" in header:
                item["refund_date"] = parse_single_date(cell)
            elif "공모가" in header:
                clean_num = re.sub(r"[^\d.]", "", cell)
                if clean_num:
                    try:
                        item["final_offer_price"] = float(clean_num)
                    except ValueError:
                        pass
            elif "공모금액" in header:
                clean_num = re.sub(r"[^\d.]", "", cell)
                if clean_num:
                    try:
                        item["offering_amount_million_krw"] = float(clean_num)
                    except ValueError:
                        pass
            elif "상장일" in header or "상장예정일" in header:
                item["expected_listing_date"] = parse_single_date(cell)
            elif "주관사" in header or "대표주관" in header or "상장주선인" in header:
                item["lead_manager"] = cell
                managers = [m.strip() for m in re.split(r"[,/·\n]", cell) if m.strip()]
                item["lead_managers"] = managers if managers else ([cell.strip()] if cell.strip() else [])

        if item["company_name"]:
            if "lead_managers" not in item:
                lm = item.get("lead_manager")
                item["lead_managers"] = [lm.strip()] if lm and lm.strip() else []
            results.append(item)

    return results


class KindClient:
    """Read-only client for KIND public-offering schedule data."""

    _ALLOWED_HOSTS = {"kind.krx.co.kr"}

    def __init__(self, base_url: str = KIND_BASE_URL):
        normalized = str(base_url or "").strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme != "https" or (parsed.hostname or "").lower() not in self._ALLOWED_HOSTS:
            raise KindClientError("KIND base URL must use the official HTTPS host.")
        self.base_url = normalized

    def fetch_pubofr_schedule_html(
        self,
        from_date: str,
        to_date: str,
        *,
        corp_name: str | None = None,
        page_size: int = 100,
        page_index: int = 1,
    ) -> str:
        """Fetch one KIND public-offering schedule page as UTF-8 HTML."""
        require_external_network("KIND")
        if page_size < 1 or page_size > 100:
            raise KindClientError("KIND page_size must be between 1 and 100.")
        if page_index < 1:
            raise KindClientError("KIND page_index must be >= 1.")

        payload = build_kind_request_payload(
            from_date=from_date,
            to_date=to_date,
            page_size=page_size,
            page_index=page_index,
            corp_name=corp_name,
        )
        url = f"{self.base_url}{KIND_PUB_OFR_PATH}"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Wealth-KIND/1.0)",
            "Referer": url,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        try:
            with httpx.Client(timeout=15.0, follow_redirects=False) as client:
                response = client.post(url, data=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KindClientError("KIND public-offering schedule request failed.") from exc

        body = response.text
        if not isinstance(body, str) or not body.strip():
            raise KindClientError("KIND public-offering schedule response body is empty.")
        return body

    def fetch_pubofr_schedule_items(
        self,
        from_date: str,
        to_date: str,
        *,
        corp_name: str | None = None,
        page_size: int = 100,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch and parse all KIND pages, failing closed on repeated/partial pagination."""
        if max_pages < 1:
            raise KindClientError("KIND max_pages must be >= 1.")

        items: list[dict[str, Any]] = []
        previous_signature: tuple[tuple[Any, ...], ...] | None = None
        for page_index in range(1, max_pages + 1):
            html = self.fetch_pubofr_schedule_html(
                from_date,
                to_date,
                corp_name=corp_name,
                page_size=page_size,
                page_index=page_index,
            )
            page_items = parse_kind_html(html)
            if not page_items:
                return items

            signature = tuple(
                (
                    item.get("company_name"),
                    item.get("filing_date"),
                    item.get("subscription_start"),
                    item.get("subscription_end"),
                    item.get("expected_listing_date"),
                    item.get("kind_bz_procs_no"),
                )
                for item in page_items
            )
            if previous_signature is not None and signature == previous_signature:
                raise KindClientError("KIND pagination repeated the previous page.")
            previous_signature = signature
            items.extend(page_items)

            if len(page_items) < page_size:
                return items

        raise KindClientError("KIND pagination exceeded the configured page limit.")
