"""Wealth NAVER IPO Client.

Fetches IPO progress records for discovery/expected-listing enrichment and
completed listing records for corroborating actual listing dates.
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.network_policy import require_external_network

logger = logging.getLogger(__name__)

NAVER_STOCK_BASE_URL = "https://stock.naver.com"
NAVER_IPO_PROGRESS_PATH = "/api/domestic/market/ipo/progress"
NAVER_OFFICIAL_HOSTS = frozenset({"stock.naver.com"})

_STOCK_CODE_PATTERN = re.compile(r"^[A-Z0-9]{6}$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class NaverIpoClientError(RuntimeError):
    """Base exception for NAVER IPO client and parser errors."""
    pass


def normalize_naver_ipo_code(value: Any) -> str:
    """Normalize NAVER ipoCode to canonical 6-character uppercase alphanumeric stock code."""
    if not isinstance(value, str):
        raise NaverIpoClientError(f"NAVER ipoCode must be string, got: {type(value).__name__}")

    raw = value.strip()
    if not raw:
        raise NaverIpoClientError("NAVER ipoCode is blank")

    if raw.startswith("A") and len(raw) > 1:
        code = raw[1:].strip().upper()
    else:
        code = raw.upper()

    if not _STOCK_CODE_PATTERN.match(code):
        raise NaverIpoClientError(
            f"NAVER stock code format invalid (expected 6 ASCII uppercase alphanumeric): {value}"
        )
    return code


def _valid_iso_date(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or not _DATE_PATTERN.match(text):
        return None
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return text


def _market_name(value: object) -> str | None:
    raw = str(value or "").strip().upper()
    if raw in {"KOSDAQ", "KOSPI", "KONEX"}:
        return raw
    return None


def _listing_track(company_name: str, gsr_class: str) -> str:
    compact = re.sub(r"\s+", "", company_name).upper()
    return "spac" if (gsr_class == "S" or "스팩" in compact or "기업인수목적" in compact or "SPAC" in compact) else "general"


def parse_naver_ipo_listing_json(raw_json_str: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Parse NAVER domestic IPO completed listings (IpoProgressType=LISTING)."""
    try:
        data = json.loads(raw_json_str) if isinstance(raw_json_str, str) else raw_json_str
    except Exception as exc:
        raise NaverIpoClientError("NAVER IPO response is not valid JSON") from exc

    if not isinstance(data, dict):
        raise NaverIpoClientError("NAVER IPO response root must be a dict")
    if data.get("ipoStatusType") != "LISTING":
        raise NaverIpoClientError(
            f"Unexpected ipoStatusType (expected LISTING): {data.get('ipoStatusType')}"
        )
    if "listingList" not in data:
        raise NaverIpoClientError("NAVER IPO response missing listingList")

    listing_list = data["listingList"]
    if not isinstance(listing_list, list):
        raise NaverIpoClientError("listingList must be a list")

    results: list[dict[str, Any]] = []
    for item in listing_list:
        if not isinstance(item, dict):
            raise NaverIpoClientError(f"listingList item must be dict, got: {type(item).__name__}")
        raw_code = item.get("ipoCode")
        if not raw_code:
            raise NaverIpoClientError("Missing ipoCode in listingList item")
        stock_code = normalize_naver_ipo_code(raw_code)
        lcal_date = _valid_iso_date(item.get("lcalDate"))
        if not lcal_date:
            raise NaverIpoClientError(f"Invalid lcalDate format for {stock_code}: {item.get('lcalDate') or ''}")

        company_name = str(item.get("compName") or "").strip()
        market_type = str(item.get("marketType") or "").strip()
        gsr_class = str(item.get("gsrClass") or "").strip()
        ipo_status = str(item.get("ipoStatus") or "").strip()
        results.append({
            "stock_code": stock_code,
            "raw_ipo_code": raw_code,
            "company_name": company_name,
            "market_type": market_type,
            "listing_track": _listing_track(company_name, gsr_class),
            "actual_listing_date": lcal_date,
            "ipo_status": ipo_status,
            "gsr_class": gsr_class,
        })
    return results


def parse_naver_ipo_progress_json(raw_json_str: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Parse unfiltered NAVER IPO progress for discovery and schedule enrichment.

    A blank ``lcalDate`` is normal before an expected listing date is announced.
    Such rows must remain discoverable: stock code, company, market and progress
    stage are still useful when reconciled with Npay/KIND/DART. Invalid nonblank
    dates are ignored at field scope rather than discarding the entire issuer.
    """
    try:
        data = json.loads(raw_json_str) if isinstance(raw_json_str, str) else raw_json_str
    except Exception as exc:
        raise NaverIpoClientError("NAVER IPO response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise NaverIpoClientError("NAVER IPO response root must be a dict")

    containers = [(key, value) for key, value in data.items() if key.endswith("List")]
    if not containers:
        raise NaverIpoClientError("NAVER IPO progress response missing list containers")

    by_code: dict[str, dict[str, Any]] = {}
    for key, rows in containers:
        if not isinstance(rows, list):
            raise NaverIpoClientError(f"{key} must be a list")
        for item in rows:
            if not isinstance(item, dict):
                raise NaverIpoClientError(f"{key} item must be dict, got: {type(item).__name__}")
            try:
                stock_code = normalize_naver_ipo_code(item.get("ipoCode"))
            except NaverIpoClientError:
                continue

            company_name = str(item.get("compName") or "").strip()
            market_type = str(item.get("marketType") or "").strip()
            market = _market_name(market_type)
            gsr_class = str(item.get("gsrClass") or "").strip()
            ipo_status = str(item.get("ipoStatus") or "").strip()
            expected_listing_date = _valid_iso_date(item.get("lcalDate"))

            current = by_code.setdefault(
                stock_code,
                {
                    "stock_code": stock_code,
                    "raw_ipo_code": item.get("ipoCode"),
                    "company_name": company_name,
                    "listing_track": _listing_track(company_name, gsr_class),
                    "progress_container": key,
                },
            )
            if company_name:
                current["company_name"] = company_name
            if market:
                current["market"] = market
            if market_type:
                current["market_type"] = market_type
            if ipo_status:
                current["ipo_status"] = ipo_status
            if gsr_class:
                current["gsr_class"] = gsr_class
                current["listing_track"] = _listing_track(company_name or str(current.get("company_name") or ""), gsr_class)
            if expected_listing_date:
                current["expected_listing_date"] = expected_listing_date
            current["progress_container"] = key

    return list(by_code.values())


class NaverIpoClient:
    """Client for NAVER Finance domestic IPO progress API."""

    def __init__(self, base_url: str = NAVER_STOCK_BASE_URL) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme.lower() != "https":
            raise NaverIpoClientError(f"NAVER client requires https: {base_url}")
        if (parsed.hostname or "").lower() not in NAVER_OFFICIAL_HOSTS:
            raise NaverIpoClientError(f"Host not in official NAVER allowlist: {parsed.hostname}")
        self.base_url = f"https://{parsed.netloc}".rstrip("/")

    def fetch_completed_listings(
        self,
        *,
        page_size: int = 100,
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch all completed IPO listings using pagination."""
        require_external_network("NAVER IPO")
        if page_size < 1 or page_size > 100:
            raise NaverIpoClientError(f"Invalid page_size: {page_size}")
        if max_pages < 1:
            raise NaverIpoClientError(f"Invalid max_pages: {max_pages}")

        all_listings: list[dict[str, Any]] = []
        seen_signatures: set[tuple[tuple[Any, ...], ...]] = set()
        client = httpx.Client(timeout=15.0, follow_redirects=False)
        try:
            for page_index in range(max_pages):
                params = {
                    "IpoProgressType": "LISTING",
                    "startIdx": page_index,
                    "pageSize": page_size,
                }
                headers = {
                    "User-Agent": "Mozilla/5.0 (compatible; Wealth-NAVER-IPO/1.0)",
                    "Referer": "https://stock.naver.com/market/stock/kr/ipo/recent",
                }
                try:
                    resp = client.get(
                        f"{self.base_url}{NAVER_IPO_PROGRESS_PATH}",
                        params=params,
                        headers=headers,
                    )
                except Exception as exc:
                    raise NaverIpoClientError(f"NAVER request failed on page {page_index}: {exc}") from exc
                if resp.status_code != 200:
                    raise NaverIpoClientError(f"NAVER HTTP error {resp.status_code} on page {page_index}")
                if not resp.text.strip():
                    raise NaverIpoClientError(f"Empty response body on page {page_index}")

                page_rows = parse_naver_ipo_listing_json(resp.text)
                if page_index == 0 and len(page_rows) == 0:
                    raise NaverIpoClientError("Zero listings on first page from NAVER IPO completed endpoint")
                if len(page_rows) == 0:
                    break

                page_signature = tuple(
                    (row["raw_ipo_code"], row["actual_listing_date"], row["ipo_status"])
                    for row in page_rows
                )
                if page_signature in seen_signatures:
                    raise NaverIpoClientError(f"Detected repeated page signature at page {page_index}")
                seen_signatures.add(page_signature)
                all_listings.extend(page_rows)
                if len(page_rows) < page_size:
                    break
            else:
                raise NaverIpoClientError(
                    f"max_pages ({max_pages}) exhausted with full pages: listings exceed limit, partial data prohibited"
                )
        finally:
            client.close()
        return all_listings

    def fetch_ipo_progress_items(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        """Fetch current IPO progress without ``IpoProgressType`` filtering."""
        require_external_network("NAVER IPO")
        if page_size < 1 or page_size > 100:
            raise NaverIpoClientError(f"Invalid page_size: {page_size}")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Wealth-NAVER-IPO/1.0)",
            "Referer": "https://stock.naver.com/market/stock/kr/ipo/recent",
        }
        try:
            with httpx.Client(timeout=15.0, follow_redirects=False) as client:
                resp = client.get(
                    f"{self.base_url}{NAVER_IPO_PROGRESS_PATH}",
                    params={"startIdx": 0, "pageSize": page_size},
                    headers=headers,
                )
        except Exception as exc:
            raise NaverIpoClientError(f"NAVER progress request failed: {exc}") from exc
        if resp.status_code != 200:
            raise NaverIpoClientError(f"NAVER progress HTTP error {resp.status_code}")
        if not resp.text.strip():
            raise NaverIpoClientError("Empty response body from NAVER IPO progress endpoint")
        return parse_naver_ipo_progress_json(resp.text)
