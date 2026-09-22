import json
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.network_policy import require_external_network

logger = logging.getLogger(__name__)


class KrxParserError(RuntimeError):
    """Raised when KRX response format does not match expected schema."""


class KrxClientError(RuntimeError):
    """Raised when KRX transport or communication fails."""


KRX_BASE_URL = "https://data.krx.co.kr"
KRX_JSON_PATH = "/comm/bldAttendant/getJsonData.cmd"
KRX_OFFICIAL_HOST = "data.krx.co.kr"

KRX_SCREEN_NEW_LISTINGS = "MDCSTAT20001"
KRX_SCREEN_OFFER_PRICE_CHANGE = "MDCSTAT20201"
KRX_SCREEN_RETURN_RATE = "MDCSTAT24401"
KRX_SCREEN_INDEX = "MDCSTAT00301"


def _pick_first(item: dict[str, Any], *keys: str) -> Any:
    """Zero-safe property lookup: fallback only when value is None or empty string."""
    for k in keys:
        if k in item:
            val = item[k]
            if val is not None and val != "":
                return val
    return None


def parse_krx_new_listings_json(raw_json_str: str) -> list[dict[str, Any]]:
    """Parse KRX MDCSTAT20001 output for newly listed companies."""
    try:
        data = json.loads(raw_json_str) if isinstance(raw_json_str, str) else raw_json_str
    except Exception as exc:
        raise KrxParserError("Invalid JSON in KRX response") from exc

    if not isinstance(data, dict) or "output" not in data or not isinstance(data["output"], list):
        raise KrxParserError("KRX output field is missing or not a list (schema_mismatch)")
    items = data["output"]

    results: list[dict[str, Any]] = []
    for item in items:
        stock_code = str(_pick_first(item, "ISU_SRT_CD", "ISU_CD", "stock_code") or "").strip()
        comp_name = str(_pick_first(item, "ISU_ABBRV", "ISU_NM", "company_name") or "").strip()
        listing_date = str(_pick_first(item, "LIST_DD", "listing_date") or "").replace("/", "-").strip()
        offer_price_val = _pick_first(item, "IPO_PRC", "offer_price")

        offer_price = None
        if offer_price_val is not None and offer_price_val != "":
            try:
                offer_price = float(str(offer_price_val).replace(",", ""))
            except ValueError:
                pass

        results.append({
            "stock_code": stock_code,
            "company_name": comp_name,
            "actual_listing_date": listing_date[:10] if listing_date else None,
            "final_offer_price": offer_price,
            "market": str(_pick_first(item, "MKT_NM", "market") or "").strip(),
        })

    return results


def parse_krx_returns_json(raw_json_str: str) -> list[dict[str, Any]]:
    """Parse KRX return rates (MDCSTAT24401 / MDCSTAT20201)."""
    try:
        data = json.loads(raw_json_str) if isinstance(raw_json_str, str) else raw_json_str
    except Exception as exc:
        raise KrxParserError("Invalid JSON in KRX response") from exc

    if not isinstance(data, dict) or "output" not in data or not isinstance(data["output"], list):
        raise KrxParserError("KRX output field is missing or not a list (schema_mismatch)")
    items = data["output"]

    results: list[dict[str, Any]] = []
    for item in items:
        stock_code = str(_pick_first(item, "ISU_SRT_CD", "stock_code") or "").strip()
        r0 = _pick_first(item, "R0", "FLUC_RT", "first_day_return")
        r1m = _pick_first(item, "R1M", "r1m_return")
        r3m = _pick_first(item, "R3M", "r3m_return")

        def _to_float(v: Any) -> float | None:
            if v is None or v == "":
                return None
            try:
                return float(str(v).replace(",", ""))
            except ValueError:
                return None

        results.append({
            "stock_code": stock_code,
            "r0": _to_float(r0),
            "r1m": _to_float(r1m),
            "r3m": _to_float(r3m),
        })

    return results


def parse_krx_listed_master_json(raw_json_str: str | dict[str, Any]) -> list[dict[str, Any]]:
    """Parse KRX finder_stkisu output for listed stock master."""
    try:
        data = json.loads(raw_json_str) if isinstance(raw_json_str, str) else raw_json_str
    except Exception as exc:
        raise KrxParserError("Invalid JSON in KRX listed master response") from exc

    if not isinstance(data, dict) or "block1" not in data or not isinstance(data["block1"], list):
        raise KrxParserError("KRX block1 field is missing or not a list (schema_mismatch)")
    items = data["block1"]

    results: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise KrxParserError("Invalid row item in KRX listed master response")
        # Ignore completely blank rows
        if not any(str(v or "").strip() for v in item.values()):
            continue

        short_code = str(item.get("short_code") or "").strip()
        comp_name = str(item.get("codeName") or "").strip()
        if not short_code or not comp_name:
            raise KrxParserError("KRX listed master row missing core fields (short_code or codeName)")

        full_code = str(item.get("full_code") or "").strip()
        market_code = str(item.get("marketCode") or "").strip()
        market_name = str(item.get("marketName") or "").strip()
        market_eng_name = str(item.get("marketEngName") or "").strip()

        results.append({
            "stock_code": short_code,
            "full_code": full_code,
            "company_name": comp_name,
            "market_code": market_code,
            "market_name": market_name,
            "market_eng_name": market_eng_name,
        })

    return results


class KrxClient:
    """Client for KRX market data."""

    def __init__(
        self,
        base_url: str = KRX_BASE_URL,
        timeout: float = 15.0,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme.lower() != "https":
            raise KrxClientError(f"KRX base URL must use HTTPS: {base_url}")
        if parsed.hostname != KRX_OFFICIAL_HOST:
            raise KrxClientError(f"KRX base URL hostname must be {KRX_OFFICIAL_HOST}: {base_url}")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch_listed_master(self) -> list[dict[str, Any]]:
        """Fetch and parse KRX listed stock master (finder_stkisu)."""
        require_external_network("KRX")
        url = f"{self.base_url}{KRX_JSON_PATH}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": f"{self.base_url}/",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        payload = {
            "bld": "dbms/comm/finder/finder_stkisu",
            "mktsel": "ALL",
            "typeNo": "0",
            "searchText": "",
        }
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                resp = client.post(url, headers=headers, data=payload)
                if resp.is_redirect:
                    raise KrxClientError(f"KRX redirected request to {resp.headers.get('location')} (login required)")
                if resp.is_error:
                    raise KrxClientError(f"KRX request failed with HTTP {resp.status_code}")
                content = resp.text
        except httpx.HTTPError as exc:
            raise KrxClientError(f"KRX HTTP communication error: {exc}") from exc

        if not content.strip():
            raise KrxClientError("KRX response body is empty")

        rows = parse_krx_listed_master_json(content)
        if not rows:
            raise KrxClientError("KRX listed master returned zero usable rows")
        return rows

    def fetch_delisted_master(self) -> list[dict[str, Any]]:
        """Fetch and parse KRX delisted stock master (finder_listdelisu)."""
        require_external_network("KRX")
        url = f"{self.base_url}{KRX_JSON_PATH}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": f"{self.base_url}/",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }
        payload = {
            "bld": "dbms/comm/finder/finder_listdelisu",
            "mktsel": "ALL",
            "typeNo": "0",
            "searchText": "",
        }
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                resp = client.post(url, headers=headers, data=payload)
                if resp.is_redirect:
                    raise KrxClientError(f"KRX redirected request to {resp.headers.get('location')} (login required)")
                if resp.is_error:
                    raise KrxClientError(f"KRX request failed with HTTP {resp.status_code}")
                content = resp.text
        except httpx.HTTPError as exc:
            raise KrxClientError(f"KRX HTTP communication error: {exc}") from exc

        if not content.strip():
            raise KrxClientError("KRX response body is empty")

        rows = parse_krx_listed_master_json(content)
        if not rows:
            raise KrxClientError("KRX delisted master returned zero usable rows")
        return rows

    def fetch_screen(self, screen_id: str, params: dict[str, Any]) -> str:
        raise NotImplementedError("Live KRX network call is disabled by design in local/test mode.")
