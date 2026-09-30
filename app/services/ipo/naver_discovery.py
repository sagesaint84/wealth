from __future__ import annotations

from datetime import datetime
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.network_policy import require_external_network
from app.services.ipo.naver_client import (
    NAVER_IPO_PROGRESS_PATH,
    NAVER_OFFICIAL_HOSTS,
    NAVER_STOCK_BASE_URL,
    NaverIpoClientError,
    normalize_naver_ipo_code,
)


_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_date(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or not _DATE_PATTERN.match(text):
        return None
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    return text


def _listing_track(company_name: str, gsr_class: str) -> str:
    compact = re.sub(r"\s+", "", company_name).upper()
    return "spac" if (gsr_class == "S" or "스팩" in compact or "기업인수목적" in compact or "SPAC" in compact) else "general"


def parse_naver_ipo_discovery_json(raw_json_str: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Keep Naver IPO progress identities even before ``lcalDate`` is announced.

    The existing expected-listing parser intentionally filters blank dates. This
    discovery parser has a different contract: a valid IPO code/company remains
    useful when joined to Npay/KIND/DART, while only a valid calendar value may
    populate ``expected_listing_date``.
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
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            try:
                stock_code = normalize_naver_ipo_code(raw.get("ipoCode"))
            except NaverIpoClientError:
                continue
            company_name = str(raw.get("compName") or "").strip()
            if not company_name:
                continue
            gsr_class = str(raw.get("gsrClass") or "").strip()
            current = by_code.setdefault(
                stock_code,
                {
                    "stock_code": stock_code,
                    "raw_ipo_code": raw.get("ipoCode"),
                    "company_name": company_name,
                    "listing_track": _listing_track(company_name, gsr_class),
                    "progress_container": key,
                },
            )
            current["company_name"] = company_name
            current["progress_container"] = key
            market = str(raw.get("marketType") or "").strip().upper()
            if market in {"KOSPI", "KOSDAQ", "KONEX"}:
                current["market"] = market
            ipo_status = str(raw.get("ipoStatus") or "").strip()
            if ipo_status:
                current["ipo_status"] = ipo_status
            if gsr_class:
                current["gsr_class"] = gsr_class
                current["listing_track"] = _listing_track(company_name, gsr_class)
            listing_date = _valid_date(raw.get("lcalDate"))
            if listing_date:
                current["expected_listing_date"] = listing_date
    return list(by_code.values())


class NaverIpoDiscoveryClient:
    def __init__(self, base_url: str = NAVER_STOCK_BASE_URL, timeout_seconds: float = 15.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme.lower() != "https":
            raise NaverIpoClientError("NAVER discovery client requires https")
        if (parsed.hostname or "").lower() not in NAVER_OFFICIAL_HOSTS:
            raise NaverIpoClientError("NAVER discovery host is not official")
        self.base_url = f"https://{parsed.netloc}".rstrip("/")
        self.timeout_seconds = timeout_seconds

    def fetch_ipo_discovery_items(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        require_external_network("NAVER IPO")
        if page_size < 1 or page_size > 100:
            raise NaverIpoClientError(f"Invalid page_size: {page_size}")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Wealth-NAVER-IPO/1.0)",
            "Referer": "https://stock.naver.com/market/stock/kr/ipo/recent",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
                response = client.get(
                    f"{self.base_url}{NAVER_IPO_PROGRESS_PATH}",
                    params={"startIdx": 0, "pageSize": page_size},
                    headers=headers,
                )
        except Exception as exc:
            raise NaverIpoClientError(f"NAVER discovery request failed: {exc}") from exc
        if response.status_code != 200:
            raise NaverIpoClientError(f"NAVER discovery HTTP error {response.status_code}")
        if not response.text.strip():
            raise NaverIpoClientError("Empty response body from NAVER IPO discovery endpoint")
        return parse_naver_ipo_discovery_json(response.text)
