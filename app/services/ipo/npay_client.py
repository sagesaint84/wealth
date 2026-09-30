from __future__ import annotations

from datetime import date, datetime
from html import unescape
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.network_policy import require_external_network


NPAY_IPO_URL = "https://ustock.naver.com/service/ipo?schedule=toBeIPOList"
NPAY_OFFICIAL_HOSTS = frozenset({"ustock.naver.com", "www.ustock.naver.com"})


class NpayIpoClientError(RuntimeError):
    pass


def _visible_text(html_text: str) -> str:
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
    # The page is an upcoming schedule. Prefer the nearest not-too-old candidate,
    # but keep year-boundary dates deterministic (Dec -> Jan).
    candidates.sort(key=lambda item: (abs((item - target).days), item < target, item))
    return candidates[0]


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
    """Parse the public Npay unlisted IPO upcoming list into discovery rows.

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

    pattern = re.compile(
        r"D-(?P<dminus>\d+)\s+"
        r"(?P<month>\d{1,2})\.(?P<day>\d{1,2})\s+예정\s+"
        r"(?P<body>.*?)"
        r"(?=(?:D-\d+\s+\d{1,2}\.\d{1,2}\s+예정)|(?:청약 전에도)|(?:지금 거래 많은)|$)",
        flags=re.IGNORECASE,
    )

    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for match in pattern.finditer(text):
        body = match.group("body").strip()
        if "공모가" not in body:
            continue
        name_part, remainder = body.split("공모가", 1)
        company_name = re.sub(r"^(?:logo\s+)+", "", name_part.strip(), flags=re.IGNORECASE).strip()
        if not company_name:
            continue

        price_part, competition_part = (remainder.split("기관경쟁률", 1) + [""])[:2]
        schedule_date = _infer_schedule_date(int(match.group("month")), int(match.group("day")), target)
        subscription_start = schedule_date.isoformat()
        signature = (company_name, subscription_start)
        if signature in seen:
            continue
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
            "observed_at": datetime.now().astimezone().isoformat(),
            "d_minus": int(match.group("dminus")),
            "institutional_competition_ratio_reference": competition_ratio,
        }
        item: dict[str, Any] = {
            "company_name": company_name,
            "subscription_start": subscription_start,
            "listing_track": _listing_track(company_name),
            "sources": {"npay": source},
        }
        if final_offer_price is not None:
            item["final_offer_price"] = final_offer_price
        if offer_band_low is not None and offer_band_high is not None:
            item["offer_band_low"] = offer_band_low
            item["offer_band_high"] = offer_band_high
        results.append(item)

    if not results:
        raise NpayIpoClientError("Npay IPO page contained no parsable upcoming rows")
    return results


class NpayIpoClient:
    def __init__(self, url: str = NPAY_IPO_URL, timeout_seconds: float = 15.0) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in NPAY_OFFICIAL_HOSTS:
            raise NpayIpoClientError("Npay IPO client requires an official Npay HTTPS host")
        self.url = url
        self.timeout_seconds = timeout_seconds

    def fetch_upcoming_ipos(self, *, target_date_str: str) -> list[dict[str, Any]]:
        require_external_network("Npay IPO")
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Wealth-Npay-IPO/1.0)",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(self.url, headers=headers)
        except Exception as exc:
            raise NpayIpoClientError(f"Npay IPO request failed: {exc}") from exc
        if response.status_code != 200:
            raise NpayIpoClientError(f"Npay IPO HTTP error {response.status_code}")
        return parse_npay_ipo_html(response.text, target_date_str=target_date_str)
