from __future__ import annotations

from datetime import date, datetime
from html import unescape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.services.network_policy import require_external_network


METALOGOS_BASE_URL = "https://metalogos.ai"
METALOGOS_CALENDAR_URL = f"{METALOGOS_BASE_URL}/160ipo/calendar"
METALOGOS_OFFICIAL_HOSTS = frozenset({"metalogos.ai", "www.metalogos.ai"})


class MetalogosIpoClientError(RuntimeError):
    pass


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href and "/160ipo/stock/" in href:
            self.links.append(href)


def _visible_text(html_text: str) -> str:
    text = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", " ", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _parse_full_date(year: str, month: str, day: str) -> str | None:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def _parse_subscription_range(text: str) -> tuple[str | None, str | None]:
    match = re.search(
        r"청약일\s*:?\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"
        r"(?:\s*\([^)]*\))?(?:\s*~\s*)+"
        r"(?:(\d{4})[.\-/])?(\d{1,2})[.\-/](\d{1,2})",
        text,
    )
    if not match:
        return None, None
    start = _parse_full_date(match.group(1), match.group(2), match.group(3))
    end_year = match.group(4) or match.group(1)
    end = _parse_full_date(end_year, match.group(5), match.group(6))
    return start, end


def _parse_money(text: str) -> float | None:
    match = re.search(r"([\d,]+)\s*원", text or "")
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_metalogos_stock_html(html_text: str, *, source_url: str) -> dict[str, Any]:
    """Parse factual IPO schedule/reference metrics from one public 160 stock page.

    The 160 attractiveness score and demand metrics are stored only as source
    references. They are never converted into Wealth score features.
    """
    if not isinstance(html_text, str) or not html_text.strip():
        raise MetalogosIpoClientError("160 IPO stock response is empty")
    text = _visible_text(html_text)
    if "공모주" not in text or "청약" not in text:
        raise MetalogosIpoClientError("160 IPO stock page contract marker is missing")

    name_match = re.search(r"([^|]{1,80}?)\s+공모주\s+핵심\s+요약", text)
    if not name_match:
        name_match = re.search(r"([가-힣A-Za-z0-9㈜()·&.\- ]{1,60})\s+(?:코스닥|코스피|코넥스)\s+[A-Z0-9]{6}", text)
    if not name_match:
        raise MetalogosIpoClientError("160 IPO company name is missing")
    company_name = name_match.group(1).strip()

    market_match = re.search(r"(코스닥|코스피|코넥스)\s+([A-Z0-9]{6})", text, flags=re.IGNORECASE)
    market_map = {"코스닥": "KOSDAQ", "코스피": "KOSPI", "코넥스": "KONEX"}
    market = market_map.get(market_match.group(1)) if market_match else None
    stock_code = market_match.group(2).upper() if market_match else None

    subscription_start, subscription_end = _parse_subscription_range(text)
    listing_match = re.search(r"상장일\s*:?\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    expected_listing_date = _parse_full_date(*listing_match.groups()) if listing_match else None
    forecast_match = re.search(r"수요예측일\s*:?\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    demand_forecast_start = _parse_full_date(*forecast_match.groups()) if forecast_match else None

    price_match = re.search(r"공모가\s*:?\s*([\d,]+)\s*원", text)
    final_offer_price = _parse_money(price_match.group(0)) if price_match else None
    score_match = re.search(r"매력지수\s*(\d{1,3})", text)
    attractiveness_score = int(score_match.group(1)) if score_match else None

    def _metric(label: str) -> float | None:
        match = re.search(rf"{label}\s*([\d,]+(?:\.\d+)?)", text)
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None

    tradable_match = re.search(r"유통가능비율\s*([\d.]+)\s*%", text)
    tradable_reference = float(tradable_match.group(1)) if tradable_match else None
    source = {
        "schedule_source": "metalogos_160_public_page",
        "url": source_url,
        "observed_at": datetime.now().astimezone().isoformat(),
        "attractiveness_score": attractiveness_score,
        "demand_participant_count_reference": _metric("수요예측 참여기관 수"),
        "high_bid_participant_count_reference": _metric("공모가 상단 이상 참여기관 수"),
        "lockup_participant_count_reference": _metric("의무보유 확약기관 수"),
        "tradable_share_ratio_reference": tradable_reference,
    }
    result: dict[str, Any] = {
        "company_name": company_name,
        "listing_track": "spac" if ("스팩" in company_name or "기업인수목적" in company_name) else "general",
        "sources": {"metalogos160": source},
    }
    if stock_code:
        result["stock_code"] = stock_code
    if market:
        result["market"] = market
    if subscription_start:
        result["subscription_start"] = subscription_start
    if subscription_end:
        result["subscription_end"] = subscription_end
    if expected_listing_date:
        result["expected_listing_date"] = expected_listing_date
    if demand_forecast_start:
        result["demand_forecast_start"] = demand_forecast_start
        result["demand_forecast_end"] = demand_forecast_start
    if final_offer_price is not None:
        result["final_offer_price"] = final_offer_price
    return result


def _month_window(target_date_str: str) -> tuple[date, date]:
    target = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    start = target.replace(day=1)
    if start.month == 12:
        month_after_next = start.replace(year=start.year + 1, month=2, day=1)
    elif start.month == 11:
        month_after_next = start.replace(year=start.year + 1, month=1, day=1)
    else:
        month_after_next = start.replace(month=start.month + 2, day=1)
    from datetime import timedelta
    return start, month_after_next - timedelta(days=1)


def _relevant(item: dict[str, Any], start: date, end: date) -> bool:
    for key in ("demand_forecast_start", "subscription_start", "subscription_end", "expected_listing_date"):
        value = str(item.get(key) or "")[:10]
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            continue
        if start <= parsed <= end:
            return True
    return False


class MetalogosIpoClient:
    def __init__(self, base_url: str = METALOGOS_BASE_URL, timeout_seconds: float = 15.0) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in METALOGOS_OFFICIAL_HOSTS:
            raise MetalogosIpoClientError("160 IPO client requires an official Metalogos HTTPS host")
        self.base_url = f"https://{parsed.netloc}".rstrip("/")
        self.timeout_seconds = timeout_seconds

    def fetch_calendar_items(self, *, target_date_str: str, max_items: int = 40) -> list[dict[str, Any]]:
        require_external_network("Metalogos 160 IPO")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Wealth-160-IPO/1.0)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                calendar = client.get(f"{self.base_url}/160ipo/calendar", headers=headers)
                if calendar.status_code != 200:
                    raise MetalogosIpoClientError(f"160 IPO calendar HTTP error {calendar.status_code}")
                collector = _LinkCollector()
                collector.feed(calendar.text)
                links = list(dict.fromkeys(urljoin(self.base_url, href) for href in collector.links))[:max_items]
                if not links:
                    return []

                start, end = _month_window(target_date_str)
                results: list[dict[str, Any]] = []
                for link in links:
                    try:
                        response = client.get(link, headers=headers)
                        if response.status_code != 200:
                            continue
                        item = parse_metalogos_stock_html(response.text, source_url=link)
                    except Exception:
                        continue
                    if _relevant(item, start, end):
                        results.append(item)
                return results
        except MetalogosIpoClientError:
            raise
        except Exception as exc:
            raise MetalogosIpoClientError(f"160 IPO request failed: {exc}") from exc
