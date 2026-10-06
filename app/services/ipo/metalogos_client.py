from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from html import unescape
from html.parser import HTMLParser
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from app.services.ipo.identity import normalize_company_name
from app.services.network_policy import require_external_network


METALOGOS_BASE_URL = "https://metalogos.ai"
METALOGOS_CALENDAR_URL = f"{METALOGOS_BASE_URL}/160ipo/calendar"
METALOGOS_SITEMAP_URL = f"{METALOGOS_BASE_URL}/sitemap-0.xml"
METALOGOS_OFFICIAL_HOSTS = frozenset({"metalogos.ai", "www.metalogos.ai"})


_DETAIL_WORKERS = 4


def _trusted_stock_url(url: str) -> bool:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() in METALOGOS_OFFICIAL_HOSTS
        and parsed.username is None and parsed.password is None
        and port in (None, 443)
        and re.fullmatch(r"/160ipo/stock/[A-Za-z0-9_-]+/?", parsed.path) is not None
    )


def _get_official(client: httpx.Client, url: str, *, headers: dict[str, str], detail: bool = False):
    """Follow only official HTTPS redirects, checking before each external read."""
    for _ in range(6):
        parsed = urlparse(url)
        if (parsed.scheme.lower() != "https"
                or (parsed.hostname or "").lower() not in METALOGOS_OFFICIAL_HOSTS
                or parsed.username is not None or parsed.password is not None
                or (detail and not _trusted_stock_url(url))):
            raise MetalogosIpoClientError("160 IPO redirect requires an official HTTPS URL")
        response = client.get(url, headers=headers)
        if not response.is_redirect:
            return response
        url = urljoin(url, response.headers.get("location", ""))
    raise MetalogosIpoClientError("160 IPO redirect limit exceeded")


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



def parse_metalogos_sitemap_stock_urls(
    xml_text: str,
    *,
    base_url: str = METALOGOS_BASE_URL,
) -> list[str]:
    """Return public 160 stock-detail URLs ordered newest-first.

    The calendar page is client-rendered and does not expose stock anchors in
    its initial HTML. Metalogos' public sitemap provides stable detail-page
    discovery while factual IPO values continue to come from each stock page.
    """
    if not isinstance(xml_text, str) or not xml_text.strip():
        return []

    parsed_base = urlparse(base_url)
    allowed_host = (parsed_base.hostname or "").lower()
    entries: list[tuple[str, str]] = []

    try:
        root = ET.fromstring(xml_text)
        for node in root.iter():
            if not str(node.tag).endswith("url"):
                continue
            loc = ""
            lastmod = ""
            for child in node:
                tag = str(child.tag)
                if tag.endswith("loc"):
                    loc = str(child.text or "").strip()
                elif tag.endswith("lastmod"):
                    lastmod = str(child.text or "").strip()

            if not loc:
                continue
            parsed = urlparse(loc)
            if parsed.scheme.lower() != "https":
                continue
            if (parsed.hostname or "").lower() != allowed_host:
                continue
            if not _trusted_stock_url(loc):
                continue
            entries.append((lastmod, loc))
    except ET.ParseError:
        for loc in re.findall(
            r"https://[^<\\s]+/160ipo/stock/[A-Za-z0-9_-]+",
            xml_text,
        ):
            parsed = urlparse(loc)
            if (parsed.hostname or "").lower() == allowed_host and _trusted_stock_url(loc):
                entries.append(("", loc))

    deduped: dict[str, str] = {}
    for lastmod, loc in entries:
        if loc not in deduped or lastmod > deduped[loc]:
            deduped[loc] = lastmod

    def discovery_order(entry: tuple[str, str]) -> tuple[str, str, str]:
        loc, lastmod = entry
        # Production lastmod reflects sitemap regeneration, including old IPOs.
        # Dated stock IDs provide stable newest-issuer ordering instead.
        identifier = urlparse(loc).path.rstrip('/').rsplit('/', 1)[-1]
        dated_id = re.fullmatch(r"B(\d{8})\d+", identifier)
        return (dated_id.group(1) if dated_id else lastmod[:10].replace('-', ''), lastmod, loc)

    ordered = sorted(
        deduped.items(),
        key=discovery_order,
        reverse=True,
    )
    return [loc for loc, _lastmod in ordered]


def parse_metalogos_search_stock_urls(
    html_text: str,
    *,
    base_url: str = METALOGOS_BASE_URL,
) -> list[str]:
    """Extract official 160 stock detail links from public search HTML."""
    if not isinstance(html_text, str) or not html_text.strip():
        return []

    parsed_base = urlparse(base_url)
    allowed_host = (parsed_base.hostname or "").lower()

    results: list[str] = []
    seen: set[str] = set()

    for href in re.findall(
        r'href=["\']([^"\']*/160ipo/stock/[A-Za-z0-9_-]+)["\']',
        html_text,
        flags=re.IGNORECASE,
    ):
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)

        if parsed.scheme.lower() != "https":
            continue
        if (parsed.hostname or "").lower() != allowed_host:
            continue
        if not _trusted_stock_url(absolute):
            continue
        if absolute in seen:
            continue

        seen.add(absolute)
        results.append(absolute)

    return results

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

    company_name = ""

    # Prefer the semantic H1. Whole-document visible text can contain an SEO
    # description before the actual issuer heading.
    for raw_heading in re.findall(
        r"<h1\b[^>]*>(.*?)</h1>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        heading = re.sub(r"<[^>]+>", " ", raw_heading)
        heading = re.sub(
            r"\s+",
            " ",
            unescape(heading),
        ).strip()

        match = re.match(
            r"(.+?)\s+\uacf5\ubaa8\uc8fc"
            r"(?:\s+\ud575\uc2ec\s+\uc694\uc57d)?"
            r"(?:\s|$)",
            heading,
        )
        if match:
            company_name = match.group(1).strip()
            break

    # Fallback to the issuer immediately preceding market + stock code.
    if not company_name:
        match = re.search(
            r"("
            r"[\uac00-\ud7a3A-Za-z0-9\u321c()?&.\-]+"
            r"(?:\s+[\uac00-\ud7a3A-Za-z0-9\u321c()?&.\-]+){0,3}"
            r")\s+"
            r"(?:\ucf54\uc2a4\ub2e5|\ucf54\uc2a4\ud53c|\ucf54\ub125\uc2a4)"
            r"\s+[A-Z0-9]{6}",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            company_name = match.group(1).strip()

    if not company_name:
        raise MetalogosIpoClientError(
            "160 IPO company name is missing"
        )

    market_match = re.search(r"(코스닥|코스피|코넥스)\s+([A-Z0-9]{6})", text, flags=re.IGNORECASE)
    market_map = {"코스닥": "KOSDAQ", "코스피": "KOSPI", "코넥스": "KONEX"}
    market = market_map.get(market_match.group(1)) if market_match else None
    stock_code = market_match.group(2).upper() if market_match else None

    subscription_start, subscription_end = _parse_subscription_range(text)
    listing_match = re.search(r"상장일\s*:?\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    expected_listing_date = _parse_full_date(*listing_match.groups()) if listing_match else None
    forecast_match = re.search(r"수요예측일\s*:?\s*(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    demand_forecast_start = _parse_full_date(*forecast_match.groups()) if forecast_match else None

    price_match = re.search(
        r"(?<![가-힣A-Za-z])(?<!희망 )(?<!예상 )공모가\s*:?\s*([\d,]+)\s*원(?!\s*[~～–-])",
        text,
    )
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
    return (start - timedelta(days=1)).replace(day=1), month_after_next - timedelta(days=1)


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

    def fetch_company_items(
        self,
        *,
        company_names: list[str],
        target_date_str: str,
        max_items: int = 40,
    ) -> list[dict[str, Any]]:
        """Discover once; never treat the client-rendered search shell as results."""
        keys = {normalize_company_name(str(name or "")) for name in company_names}
        keys.discard("")
        if not keys:
            return []
        rows = self.fetch_calendar_items(
            target_date_str=target_date_str, max_items=max_items, company_keys=keys,
        )
        index = {normalize_company_name(str(row.get("company_name") or "")): row for row in rows}
        return [index[key] for key in dict.fromkeys(
            normalize_company_name(str(name or "")) for name in company_names
        ) if key in index]

    def fetch_company_item(
        self,
        *,
        company_name: str,
        target_date_str: str,
    ) -> dict[str, Any] | None:
        rows = self.fetch_company_items(
            company_names=[company_name],
            target_date_str=target_date_str,
        )
        return rows[0] if rows else None

    def fetch_calendar_items(
        self,
        *,
        target_date_str: str,
        max_items: int = 40,
        company_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        require_external_network("Metalogos 160 IPO")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Wealth-160-IPO/1.0)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        }
        try:
            with httpx.Client(
                timeout=self.timeout_seconds,
                follow_redirects=False,
            ) as client:
                links: list[str] = []

                # Prefer static calendar links if Metalogos exposes them again.
                calendar = _get_official(client,
                    f"{self.base_url}/160ipo/calendar",
                    headers=headers,
                )
                if calendar.status_code == 200:
                    collector = _LinkCollector()
                    collector.feed(calendar.text)
                    links = list(
                        dict.fromkeys(
                            urljoin(self.base_url, href)
                            for href in collector.links
                            if _trusted_stock_url(urljoin(self.base_url, href))
                        )
                    )

                # Calendar HTML is client-rendered, and the production sitemap
                # can lag current issuers. Read the shared public stock list once
                # (the ?query= route serves this same list for every company).
                if not links:
                    listing = _get_official(client, f"{self.base_url}/160ipo/stock", headers=headers)
                    if listing.status_code == 200:
                        links = parse_metalogos_search_stock_urls(listing.text, base_url=self.base_url)
                    sitemap = _get_official(client,
                        f"{self.base_url}/sitemap-0.xml",
                        headers=headers,
                    )
                    if sitemap.status_code != 200 and not links:
                        raise MetalogosIpoClientError(
                            f"160 IPO sitemap HTTP error {sitemap.status_code}"
                        )
                    if sitemap.status_code == 200:
                        links = list(dict.fromkeys(links + parse_metalogos_sitemap_stock_urls(
                            sitemap.text, base_url=self.base_url,
                        )))

                links = links[:max(0, int(max_items))]
                if not links:
                    return []

                start, end = _month_window(target_date_str)
                results: list[dict[str, Any]] = []

                def fetch_detail(link: str) -> dict[str, Any] | None:
                    try:
                        response = _get_official(client, link, headers=headers, detail=True)
                        if response.status_code != 200:
                            return None
                        # Redirects must not turn trusted discovery into an off-site fetch.
                        if not _trusted_stock_url(str(response.url)):
                            return None
                        item = parse_metalogos_stock_html(response.text, source_url=str(response.url))
                        key = normalize_company_name(str(item.get("company_name") or ""))
                        if company_keys is not None and key not in company_keys:
                            return None
                        return item if _relevant(item, start, end) else None
                    except Exception:
                        return None

                # A bounded batch avoids scheduling the entire historical sitemap.
                # executor.map preserves discovery order regardless of completion order.
                remaining = set(company_keys) if company_keys is not None else None
                with ThreadPoolExecutor(max_workers=_DETAIL_WORKERS) as pool:
                    for offset in range(0, len(links), _DETAIL_WORKERS):
                        for item in pool.map(fetch_detail, links[offset:offset + _DETAIL_WORKERS]):
                            if item is not None:
                                key = normalize_company_name(str(item.get("company_name") or ""))
                                if remaining is None or key in remaining:
                                    results.append(item)
                                    if remaining is not None:
                                        remaining.discard(key)
                        if remaining is not None and not remaining:
                            break

                return results

        except MetalogosIpoClientError:
            raise
        except Exception as exc:
            raise MetalogosIpoClientError(
                f"160 IPO request failed: {exc}"
            ) from exc
