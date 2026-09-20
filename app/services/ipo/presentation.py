"""Read-only IPO lifecycle and user-position presentation state."""
from __future__ import annotations

from copy import deepcopy
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Any

from app.services import portfolio
from app.services.pnl_records import read_pnl_records_readonly


def current_market_date() -> date:
    """Korean securities-market date; injected explicitly by tests."""
    try:
        market_timezone = ZoneInfo("Asia/Seoul")
    except ZoneInfoNotFoundError:
        # Some Windows test runtimes omit the IANA database.  Korea has no DST,
        # so this preserves the market-date contract without using OS local time.
        market_timezone = timezone(timedelta(hours=9), name="Asia/Seoul")
    return datetime.now(market_timezone).date()


def _date(value: object) -> date | None:
    text = str(value or "").strip()
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == text else None


def derive_market_state(ipo: dict[str, Any], today: date | None = None) -> str:
    today = today or current_market_date()
    start, end = _date(ipo.get("subscription_start")), _date(ipo.get("subscription_end"))
    listing = _date(ipo.get("actual_listing_date")) or _date(ipo.get("expected_listing_date"))
    if start is None or end is None or end < start:
        return "DATE_UNKNOWN"
    if today < start:
        return "UPCOMING"
    if start <= today <= end:
        return "SUBSCRIPTION_OPEN"
    if listing is None:
        return "SUBSCRIPTION_CLOSED"
    return "LISTED" if today >= listing else "LISTING_UPCOMING"


_POSITION_PRECEDENCE = ("LINK_DATA_MISSING", "PARTIALLY_SOLD", "ALLOCATED_UNSOLD", "FULLY_SOLD", "APPLIED", "NOT_APPLIED")


def derive_user_state(application: object, pnl_records: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    """Aggregate applicants without persisting a mutable position status."""
    if not isinstance(application, dict):
        return "NOT_APPLIED", {"not_applied": 0, "applied": 0, "unsold": 0, "partially_sold": 0, "fully_sold": 0, "link_data_missing": 0}
    applied = {str(owner) for owner in application.get("applied_owners") or []}
    applicants = application.get("applicants") if isinstance(application.get("applicants"), dict) else {}
    records_by_id = {str(item.get("id") or ""): item for item in pnl_records}
    states: list[str] = []
    for owner in applied:
        applicant = applicants.get(owner)
        allocation = applicant.get("allocation") if isinstance(applicant, dict) else None
        if not isinstance(allocation, dict):
            states.append("APPLIED"); continue
        try:
            quantity = int(allocation.get("quantity"))
        except (TypeError, ValueError):
            quantity = 0
        if quantity <= 0:
            states.append("APPLIED"); continue
        links = allocation.get("links") if isinstance(allocation.get("links"), list) else []
        dangling = any(not isinstance(link, dict) or str(link.get("pnl_record_id") or "") not in records_by_id for link in links)
        sold = 0
        for link in links:
            if not isinstance(link, dict):
                continue
            try:
                matched = int(link.get("matched_quantity") or 0)
            except (TypeError, ValueError):
                matched = 0
            sold += max(0, matched)
        if dangling: states.append("LINK_DATA_MISSING")
        elif sold <= 0: states.append("ALLOCATED_UNSOLD")
        elif sold < quantity: states.append("PARTIALLY_SOLD")
        else: states.append("FULLY_SOLD")
    if not states:
        state = "NOT_APPLIED"
    else:
        state = next(candidate for candidate in _POSITION_PRECEDENCE if candidate in states)
    counts = {"not_applied": 0, "applied": 0, "unsold": 0, "partially_sold": 0, "fully_sold": 0, "link_data_missing": 0}
    lookup = {"NOT_APPLIED": "not_applied", "APPLIED": "applied", "ALLOCATED_UNSOLD": "unsold", "PARTIALLY_SOLD": "partially_sold", "FULLY_SOLD": "fully_sold", "LINK_DATA_MISSING": "link_data_missing"}
    for item in states:
        counts[lookup[item]] += 1
    return state, counts


def derive_filter_group(market_state: str, user_state: str) -> str:
    if user_state in {"LINK_DATA_MISSING", "ALLOCATED_UNSOLD", "PARTIALLY_SOLD"}:
        return "ACTIVE"
    if market_state == "UPCOMING":
        return "UPCOMING"
    if market_state in {"SUBSCRIPTION_OPEN", "SUBSCRIPTION_CLOSED", "LISTING_UPCOMING"}:
        return "ACTIVE"
    if market_state == "LISTED":
        return "PAST"
    return "UNKNOWN"


def _read_portfolio_for_presentation(username: str | None) -> dict[str, Any]:
    """Read applicant state without creating a user portfolio on GET."""
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}


def present_market_store(username: str | None, market: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Copy and enrich market response; never mutate market storage or portfolio."""
    output = deepcopy(market)
    data = _read_portfolio_for_presentation(username)
    applications = (((data.get("settings") or {}).get("ipo") or {}).get("applications") or {})
    records = read_pnl_records_readonly(username)
    for item in output.get("ipos", []) if isinstance(output.get("ipos"), list) else []:
        if not isinstance(item, dict):
            continue
        application = applications.get(str(item.get("ipo_id") or "")) if isinstance(applications, dict) else None
        market_state = derive_market_state(item, today)
        user_state, applicant_counts = derive_user_state(application, records)
        item["market_state"] = market_state
        item["user_state"] = user_state
        item["filter_group"] = derive_filter_group(market_state, user_state)
        item["applicant_counts"] = applicant_counts
        item["presentation_sort_date"] = str(item.get("subscription_start") or item.get("expected_listing_date") or item.get("actual_listing_date") or "")
    return output
