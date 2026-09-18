"""Wealth NAVER IPO Client.

Fetches completed IPO listing records from NAVER domestic market IPO progress endpoint.
Used strictly for corroborating actual listing dates (lcalDate) when ipoStatus == "상장".
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
    """Normalize NAVER ipoCode to canonical 6-character uppercase alphanumeric stock code.

    Examples:
        'A0197V0' -> '0197V0'
        'A468670' -> '468670'
        '0197V0'  -> '0197V0'
    """
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

        lcal_date = str(item.get("lcalDate") or "").strip()
        if not _DATE_PATTERN.match(lcal_date):
            raise NaverIpoClientError(f"Invalid lcalDate format for {stock_code}: {lcal_date}")
        try:
            datetime.strptime(lcal_date, "%Y-%m-%d")
        except ValueError as exc:
            raise NaverIpoClientError(f"Invalid lcalDate calendar date for {stock_code}: {lcal_date}") from exc

        company_name = str(item.get("compName") or "").strip()
        market_type = str(item.get("marketType") or "").strip()
        gsr_class = str(item.get("gsrClass") or "").strip()
        ipo_status = str(item.get("ipoStatus") or "").strip()

        results.append({
            "stock_code": stock_code,
            "raw_ipo_code": raw_code,
            "company_name": company_name,
            "market_type": market_type,
            "listing_track": "spac" if gsr_class == "S" else "general",
            "actual_listing_date": lcal_date,
            "ipo_status": ipo_status,
            "gsr_class": gsr_class,
        })

    return results


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
        """Fetch all completed IPO listings using pagination.

        Raises NaverIpoClientError on network failure, HTTP error, empty body,
        zero listings on first page, repeated signatures, or max_pages exhaustion.
        """
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
                    raise NaverIpoClientError(
                        f"NAVER HTTP error {resp.status_code} on page {page_index}"
                    )

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
                    raise NaverIpoClientError(
                        f"Detected repeated page signature at page {page_index}"
                    )
                seen_signatures.add(page_signature)

                all_listings.extend(page_rows)

                if len(page_rows) < page_size:
                    break
            else:
                # Loop completed without break: max_pages exhausted and last page was still full
                raise NaverIpoClientError(
                    f"max_pages ({max_pages}) exhausted with full pages: listings exceed limit, partial data prohibited"
                )
        finally:
            client.close()

        return all_listings
