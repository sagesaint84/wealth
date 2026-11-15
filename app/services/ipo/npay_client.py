from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import unescape
import json
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.network_policy import require_external_network


NPAY_STOCK_IPO_URL = "https://stock.naver.com/market/stock/kr/ipo"
NPAY_IPO_URL = "https://ustock.naver.com/service/ipo?schedule=toBeIPOList"
NPAY_OFFICIAL_HOSTS = frozenset({"ustock.naver.com", "www.ustock.naver.com"})
KST = timezone(timedelta(hours=9))


class NpayIpoClientError(RuntimeError):
    pass


def _visible_text(html_text: str) -> str:
    # The public IPO schedule is server-rendered today. Strip executable/style
    # blocks rather than parsing application state from private implementation
    # details; if the visible contract disappears, fail closed below.
    text = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", " ", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _infer_schedule_date(month: int, day: int, target: date) -> date:
    candidates: list[date] = []
    for year in (target.year - 1, target.year, target.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        raise NpayIpoClientError(f"invalid Npay IPO date: {month:02d}.{day:02d}")
    candidates.sort(key=lambda item: (abs((item - target).days), item < target, item))
    return candidates[0]


def _clean_company_name(value: str) -> str:
    text = re.sub(r"^(?:logo\s+)+", "", str(value or "").strip(), flags=re.IGNORECASE)
    # Npay may append trading/profile badges to the displayed company name.
    # These are presentation labels, not part of the issuer identity.
    text = re.sub(r"\s+(?:매수가능|IPO\s*전문|IPO\s*일반|전문|일반)\s*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def _listing_track(company_name: str) -> str:
    compact = re.sub(r"\s+", "", str(company_name or "")).upper()
    return "spac" if ("스팩" in compact or "기업인수목적" in compact or "SPAC" in compact) else "general"


def _parse_price(text: str) -> tuple[float | None, float | None, float | None]:
    numbers = [float(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", text or "")]
    if "~" in (text or "") and len(numbers) >= 2:
        low, high = sorted(numbers[:2])
        return None, low, high
    if numbers:
        return numbers[0], None, None
    return None, None, None


def parse_npay_ipo_html(html_text: str, *, target_date_str: str) -> list[dict[str, Any]]:
    """Parse the visible upcoming and active Npay IPO rows into discovery rows.

    This parser intentionally consumes only facts visibly exposed by the public
    IPO schedule page. It does not infer subscription end dates, listing dates,
    market, or broker data that are absent from that summary.
    """
    if not isinstance(html_text, str) or not html_text.strip():
        raise NpayIpoClientError("Npay IPO response is empty")
    try:
        target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError as exc:
        raise NpayIpoClientError("target_date_str must be YYYY-MM-DD") from exc

    text = _visible_text(html_text)
    if "다가오는 청약 종목" not in text:
        raise NpayIpoClientError("Npay IPO page contract marker is missing")

    upcoming_pattern = re.compile(
        r"D-(?P<dminus>\d+)\s+"
        r"(?P<month>\d{1,2})\.(?P<day>\d{1,2})\s+예정\s+"
        r"(?P<body>.*?)"
        r"(?=(?:진행중\s+\d{1,2}\.\d{1,2}\s+마감)|(?:D-\d+\s+\d{1,2}\.\d{1,2}\s+예정)|(?:청약 전에도)|(?:지금 거래 많은)|$)",
        flags=re.IGNORECASE,
    )
    active_pattern = re.compile(
        r"진행중\s+(?P<month>\d{1,2})\.(?P<day>\d{1,2})\s+마감\s+"
        r"(?P<body>.*?)"
        r"(?=(?:D-\d+\s+\d{1,2}\.\d{1,2}\s+예정)|(?:청약 전에도)|(?:지금 거래 많은)|$)",
        flags=re.IGNORECASE,
    )

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    observed_at = datetime.now(KST).isoformat()

    def append_row(match: re.Match[str], *, status: str) -> None:
        body = match.group("body").strip()
        if "공모가" not in body:
            return
        name_part, remainder = body.split("공모가", 1)
        company_name = _clean_company_name(name_part)
        if not company_name:
            return

        price_part, competition_part = (remainder.split("기관경쟁률", 1) + [""])[:2]
        schedule_date = _infer_schedule_date(int(match.group("month")), int(match.group("day")), target)
        schedule_field = "subscription_start" if status == "upcoming" else "subscription_end"
        signature = (company_name, f"{status}:{schedule_date.isoformat()}")
        if signature in seen:
            return
        seen.add(signature)

        final_offer_price, offer_band_low, offer_band_high = _parse_price(price_part)
        competition_match = re.search(r"([\d,.]+)\s*:\s*1", competition_part)
        competition_ratio = None
        if competition_match:
            try:
                competition_ratio = float(competition_match.group(1).replace(",", ""))
            except ValueError:
                competition_ratio = None

        source = {
            "schedule_source": "npay_unlisted_public_ipo",
            "url": NPAY_IPO_URL,
            "observed_at": observed_at,
            "subscription_status": status,
            "institutional_competition_ratio_reference": competition_ratio,
        }
        item: dict[str, Any] = {
            "company_name": company_name,
            schedule_field: schedule_date.isoformat(),
            "npay_subscription_status": status,
            "listing_track": _listing_track(company_name),
            "sources": {"npay": source},
        }
        if status == "upcoming":
            item["sources"]["npay"]["d_minus"] = int(match.group("dminus"))
        if final_offer_price is not None:
            item["final_offer_price"] = final_offer_price
        if offer_band_low is not None and offer_band_high is not None:
            item["offer_band_low"] = offer_band_low
            item["offer_band_high"] = offer_band_high
        results.append(item)

    for match in active_pattern.finditer(text):
        append_row(match, status="active")
    for match in upcoming_pattern.finditer(text):
        append_row(match, status="upcoming")

    # The same public page embeds full-year upcoming dates and security codes.
    # Join only a unique name AND exact observed date, never by name alone.
    state_match = re.search(r'<script\b(?=[^>]*\bid=["\']__NEXT_DATA__["\'])[^>]*>(.*?)</script>',
                            html_text, flags=re.IGNORECASE | re.DOTALL)
    if state_match:
        try:
            state = json.loads(state_match.group(1))
            queries = state["props"]["pageProps"]["dehydratedState"]["queries"]
        except (ValueError, KeyError, TypeError):
            queries = []
        from app.services.ipo.naver_client import normalize_naver_ipo_code, NaverIpoClientError
        candidates = {}
        for query in queries:
            if not isinstance(query, dict) or query.get("queryKey") != ["upcomingStocks"]:
                continue
            query_state = query.get("state")
            data = query_state.get("data") if isinstance(query_state, dict) else None
            if not isinstance(data, dict) or not isinstance(data.get("toBeIPOList"), list):
                continue
            for raw in data["toBeIPOList"]:
                if not isinstance(raw, dict):
                    continue
                day = str(raw.get("offeringStartAt") or "")
                try:
                    if datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d") != day:
                        continue
                    code = normalize_naver_ipo_code(raw.get("stockCode"))
                except (ValueError, NaverIpoClientError):
                    continue
                key = (_clean_company_name(raw.get("stockName")), day)
                candidates.setdefault(key, []).append(code)
        for item in results:
            key = (item["company_name"], item.get("subscription_start"))
            codes = candidates.get(key, [])
            if len(codes) == 1:
                item["stock_code"] = codes[0]
                item["sources"]["npay"]["field_paths"] = {
                    "subscription_start": "upcomingStocks.toBeIPOList.offeringStartAt",
                    "stock_code": "upcomingStocks.toBeIPOList.stockCode",
                }

    # An intact page with both schedule section labels and no listings is a
    # successful empty result. A changed or blocked page still fails closed.
    if not results and not ("청약진행중" in text and "청약예정" in text):
        raise NpayIpoClientError("Npay IPO page contained no parsable schedule sections")
    return results


class NpayIpoClient:
    def __init__(self, url: str = NPAY_IPO_URL, timeout_seconds: float = 15.0) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in NPAY_OFFICIAL_HOSTS:
            raise NpayIpoClientError("Npay IPO client requires an official Npay HTTPS host")
        if url != NPAY_IPO_URL:
            raise NpayIpoClientError("Npay IPO URL is not an approved schedule page")
        self.url = url
        self.timeout_seconds = timeout_seconds

    def fetch_upcoming_ipos(self, *, target_date_str: str) -> list[dict[str, Any]]:
        """Collect the two Npay surfaces without fallback to other providers."""
        from app.services.ipo.naver_discovery import NaverIpoDiscoveryClient

        self.source_errors: dict[str, str] = {}
        self.source_statuses: dict[str, str] = {}
        errors: list[Exception] = []
        rows: list[dict[str, Any]] = []
        successful = 0
        for url, read in (
            (self.url, lambda: self._fetch_unlisted_ipos(target_date_str=target_date_str)),
            (NPAY_STOCK_IPO_URL, lambda: NaverIpoDiscoveryClient(
                timeout_seconds=self.timeout_seconds).fetch_ipo_discovery_items()),
        ):
            key = "npay_stock" if url == NPAY_STOCK_IPO_URL else "npay_unlisted"
            try:
                items = read()
                if not isinstance(items, list):
                    raise NpayIpoClientError("Npay IPO response must be a list")
            except Exception as exc:
                # Keep diagnostics free of response bodies, credentials and headers.
                self.source_errors[url] = type(exc).__name__
                self.source_statuses[key] = f"source_error ({type(exc).__name__})"
                errors.append(exc)
                continue
            successful += 1
            self.source_statuses[key] = "read_ok"
            for item in items:
                if url == NPAY_STOCK_IPO_URL:
                    item = {**item, "sources": {"npay": {
                        **item.get("sources", {}).get("npay", {}),
                        "schedule_source": "npay_stock_public_ipo",
                        "url": url, "observed_at": datetime.now(KST).isoformat(),
                    }}}
                rows.append(item)
        if not successful:
            # Retain the existing network-policy exception contract.
            from app.services.network_policy import ExternalNetworkDisabled
            if all(isinstance(exc, ExternalNetworkDisabled) for exc in errors):
                raise errors[0]
            raise NpayIpoClientError("Both Npay IPO sources unavailable")
        return rows

    def fetch_completed_ipos(self, *, target_date_str: str) -> list[dict[str, Any]]:
        """Explicit history read using the existing bounded Npay stock paginator."""
        from app.services.ipo.naver_client import NaverIpoClient
        target = date.fromisoformat(target_date_str)
        observations = []
        for row in NaverIpoClient().fetch_completed_listings():
            # The unfiltered listingList is not a completion signal.
            if row.get("ipo_status") != "상장" or date.fromisoformat(row["actual_listing_date"]) > target:
                continue
            observations.append({"stock_code": row["stock_code"], "company_name": row["company_name"],
                "actual_listing_date": row["actual_listing_date"], "sources": {"npay": {
                    "url": NPAY_STOCK_IPO_URL,
                    "response_url": "https://stock.naver.com/api/domestic/market/ipo/progress?IpoProgressType=LISTING",
                    "observed_at": datetime.now(KST).isoformat(),
                    "schedule_source": "npay_stock_completed_ipo", "ipo_status": row["ipo_status"],
                    "field_paths": {"actual_listing_date": "lcalDate (LISTING response, ipoStatus=상장)"}}}})
        return observations

    def fetch_calendar_month(self, *, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Read the public month calendar. No storage or recurring-refresh effects."""
        from app.services.ipo.naver_client import normalize_naver_ipo_code
        begin, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
        if begin.day != 1 or (begin.year, begin.month) != (end.year, end.month) or end < begin:
            raise NpayIpoClientError("Calendar read requires one calendar month")
        require_external_network("Npay IPO calendar")
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
            response = client.get("https://api.ustockplus.com/v2/ipo/calendars",
                                  params={"startDate": start_date, "endDate": end_date},
                                  headers={"X-App-Device": "WEB", "Referer": NPAY_IPO_URL})
        if response.status_code != 200:
            raise NpayIpoClientError(f"Npay calendar HTTP error {response.status_code}")
        payload = response.json()
        rows = payload.get("ipoCalendarResponses") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise NpayIpoClientError("Npay calendar response contract missing")
        observations = []
        observed_at = datetime.now(KST).isoformat()
        for raw in rows:
            kind = raw.get("calendarStockType") if isinstance(raw, dict) else None
            if kind not in {"OFFER_SUBSCRIPTION", "TO_BE_LISTED"}:
                continue
            code = normalize_naver_ipo_code(raw.get("stockCode"))
            first = date.fromisoformat(raw["startDate"]).isoformat()
            last = date.fromisoformat(raw["endDate"]).isoformat()
            name = str(raw.get("stockName") or "").strip()
            if not name or last < first or (kind == "TO_BE_LISTED" and first != last):
                raise NpayIpoClientError("Npay calendar identity/date is invalid")
            item = {"stock_code": code, "company_name": name}
            if kind == "OFFER_SUBSCRIPTION":
                item.update(subscription_start=first, subscription_end=last)
            else:
                item["expected_listing_date"] = first
            extra = raw.get("extraInfo")
            price = extra.get("finalOfferPrice") if isinstance(extra, dict) else None
            if isinstance(price, (int, float)) and not isinstance(price, bool) and 0 < price < float("inf"):
                item["final_offer_price"] = price
            item["sources"] = {"npay": {"url": NPAY_IPO_URL,
                "response_url": str(response.url), "observed_at": observed_at,
                "schedule_source": "npay_public_calendar", "calendar_type": kind,
                "field_paths": ({"subscription_start": "startDate", "subscription_end": "endDate"}
                                if kind == "OFFER_SUBSCRIPTION" else {"expected_listing_date": "startDate"})}}
            observations.append(item)
        return observations

    def _fetch_unlisted_ipos(self, *, target_date_str: str) -> list[dict[str, Any]]:
        require_external_network("Npay IPO")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Wealth-Npay-IPO/1.0)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
                response = client.get(self.url, headers=headers)
        except Exception as exc:
            raise NpayIpoClientError(f"Npay IPO request failed: {exc}") from exc
        if response.is_redirect:
            raise NpayIpoClientError(f"Npay IPO redirect refused (HTTP {response.status_code})")
        if response.status_code != 200:
            raise NpayIpoClientError(f"Npay IPO HTTP error {response.status_code}")
        return parse_npay_ipo_html(response.text, target_date_str=target_date_str)
