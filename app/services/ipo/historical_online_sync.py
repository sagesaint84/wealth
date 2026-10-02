"""Explicit online historical IPO reconciliation from KRX.

This service is intentionally separate from the interactive IPO schedule refresh.
A full KRX historical scan happens only when a user explicitly asks for the
online historical preview from the historical-import dialog.  Preview never
mutates canonical data; commit is user-bound, digest-checked, and atomic.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import secrets
import threading
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.ipo.identity import generate_ipo_id, is_spac_ipo, normalize_company_name
from app.services.ipo.krx_client import KrxClient
from app.services.ipo.score import calculate_wealth_ipo_score
from app.services.ipo.store import _STORE_LOCK, _read_market_store_unlocked, _write_market_store_unlocked

MIN_SUPPORTED_YEAR = 2020
PREVIEW_TTL_SECONDS = 30 * 60
MAX_SERVER_PREVIEWS = 32
_SOURCE = "KRX_MDCSTAT20001"
_AUTHORITATIVE_FIELDS = ("market", "actual_listing_date", "final_offer_price", "lead_managers")
_CODE_RE = re.compile(r"^[A-Z0-9]{6}$")

_PREVIEWS: dict[str, dict[str, Any]] = {}
_PREVIEW_LOCK = threading.RLock()
_SYNC_LOCK = threading.Lock()


class HistoricalOnlineSyncError(RuntimeError):
    def __init__(self, code: str, message: str = "KRX 과거 공모주 자료를 확인할 수 없습니다."):
        super().__init__(message)
        self.code = code


class HistoricalOnlineSyncAlreadyRunning(HistoricalOnlineSyncError):
    def __init__(self) -> None:
        super().__init__("HISTORICAL_SYNC_ALREADY_RUNNING", "과거 공모주 전체 조회가 이미 진행 중입니다.")


def _current_kst_date() -> date:
    try:
        tz = ZoneInfo("Asia/Seoul")
    except ZoneInfoNotFoundError:
        tz = timezone(timedelta(hours=9), name="Asia/Seoul")
    return datetime.now(tz).date()


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _market_digest(market: dict[str, Any]) -> str:
    return _digest({
        "schema_version": market.get("schema_version"),
        "ipos": market.get("ipos") if isinstance(market.get("ipos"), list) else [],
    })


def _normalize_market(value: object) -> str | None:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    if "코스닥" in raw or "KOSDAQ" in raw or raw == "KSQ":
        return "KOSDAQ"
    if "유가증권" in raw or "코스피" in raw or "KOSPI" in raw or raw == "STK":
        return "KOSPI"
    if "코넥스" in raw or "KONEX" in raw or raw == "KNX":
        return "KONEX"
    return None


def _normalize_date(value: object, *, today: date) -> str | None:
    raw = str(value or "").strip()[:10]
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.isoformat() != raw or parsed > today:
        return None
    return raw


def _normalize_price(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_managers(value: object) -> list[str]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _normalize_candidate(row: dict[str, Any], *, today: date) -> tuple[dict[str, Any] | None, str | None]:
    code = str(row.get("stock_code") or "").strip().upper()
    if code.startswith("A") and len(code) == 7:
        code = code[1:]
    name = str(row.get("company_name") or "").strip()
    if not _CODE_RE.fullmatch(code):
        return None, "STOCK_CODE_INVALID"
    if not name:
        return None, "COMPANY_NAME_MISSING"

    raw_listing = str(row.get("actual_listing_date") or "").strip()
    listing_date = _normalize_date(raw_listing, today=today)
    if not listing_date:
        return None, "ACTUAL_LISTING_DATE_INVALID"

    market = _normalize_market(row.get("market"))
    price = _normalize_price(row.get("final_offer_price"))
    managers = _normalize_managers(row.get("lead_managers"))
    return {
        "stock_code": code,
        "company_name": name,
        "actual_listing_date": listing_date,
        "final_offer_price": price,
        "market": market,
        "lead_managers": managers,
    }, None


def _same_value(field: str, left: object, right: object) -> bool:
    if field == "final_offer_price":
        try:
            return float(left) == float(right)
        except (TypeError, ValueError):
            return left in (None, "") and right in (None, "")
    if field == "lead_managers":
        return _normalize_managers(left) == _normalize_managers(right)
    return left == right


def _source_has_value(field: str, value: object) -> bool:
    if field == "lead_managers":
        return bool(_normalize_managers(value))
    return value not in (None, "")


def _provenance(*, observed_at: str, from_year: int, to_year: int) -> dict[str, Any]:
    return {
        "source": _SOURCE,
        "observed_at": observed_at,
        "from_year": from_year,
        "to_year": to_year,
    }


def _purge_previews_unlocked(now: float) -> None:
    expired = [ticket for ticket, state in _PREVIEWS.items() if float(state.get("expires") or 0) < now]
    for ticket in expired:
        _PREVIEWS.pop(ticket, None)
    if len(_PREVIEWS) >= MAX_SERVER_PREVIEWS:
        oldest = sorted(_PREVIEWS, key=lambda key: float(_PREVIEWS[key].get("expires") or 0))
        for ticket in oldest[: max(1, len(_PREVIEWS) - MAX_SERVER_PREVIEWS + 1)]:
            _PREVIEWS.pop(ticket, None)


def _fetch_full_history(
    client: KrxClient,
    *,
    from_year: int,
    to_year: int,
    today: date,
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    if from_year < MIN_SUPPORTED_YEAR or to_year < from_year or to_year > today.year:
        raise HistoricalOnlineSyncError("YEAR_RANGE_INVALID", "과거 공모주 조회 연도 범위를 확인해 주세요.")

    rows: list[dict[str, Any]] = []
    by_year: dict[int, int] = {}
    for year in range(from_year, to_year + 1):
        start = date(year, 1, 1)
        end = min(date(year, 12, 31), today)
        try:
            fetched = client.fetch_new_listings(start.isoformat(), end.isoformat())
        except Exception as exc:
            raise HistoricalOnlineSyncError(
                "KRX_HISTORY_FETCH_FAILED",
                f"KRX {year}년 신규상장 자료 조회에 실패했습니다. 일부 연도만 반영하지 않습니다.",
            ) from exc
        if not isinstance(fetched, list) or not fetched:
            raise HistoricalOnlineSyncError(
                "KRX_HISTORY_EMPTY",
                f"KRX {year}년 신규상장 자료가 비어 있어 전체 조회를 중단했습니다.",
            )
        by_year[year] = len(fetched)
        rows.extend(fetched)
    return rows, by_year


def create_online_historical_preview(
    username: str,
    *,
    krx_client: KrxClient | None = None,
    from_year: int = MIN_SUPPORTED_YEAR,
    to_year: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Fetch complete supported KRX history and build a no-write reconciliation preview."""
    if not _SYNC_LOCK.acquire(blocking=False):
        raise HistoricalOnlineSyncAlreadyRunning()
    try:
        current = today or _current_kst_date()
        end_year = to_year if to_year is not None else current.year
        client = krx_client or KrxClient()
        raw_rows, by_year = _fetch_full_history(
            client, from_year=from_year, to_year=end_year, today=current,
        )

        with _STORE_LOCK:
            market = deepcopy(_read_market_store_unlocked())
        existing = market.get("ipos") if isinstance(market.get("ipos"), list) else []
        existing_by_code: dict[str, list[dict[str, Any]]] = {}
        for item in existing:
            code = str(item.get("stock_code") or "").strip().upper()
            if code:
                existing_by_code.setdefault(code, []).append(item)

        normalized_by_code: dict[str, list[dict[str, Any]]] = {}
        issues: list[dict[str, Any]] = []
        invalid = 0
        for row in raw_rows:
            candidate, reason = _normalize_candidate(row, today=current)
            if candidate is None:
                invalid += 1
                issues.append({
                    "company_name": str(row.get("company_name") or "").strip(),
                    "stock_code": str(row.get("stock_code") or "").strip(),
                    "reason": reason or "INVALID",
                })
                continue
            normalized_by_code.setdefault(candidate["stock_code"], []).append(candidate)

        observed_at = datetime.now().astimezone().isoformat()
        plans: list[dict[str, Any]] = []
        summary = {
            "fetched": len(raw_rows),
            "valid": 0,
            "new": 0,
            "updated": 0,
            "unchanged": 0,
            "review_required": 0,
            "invalid": invalid,
            "duplicate_rows": 0,
        }

        for code, grouped in sorted(normalized_by_code.items()):
            summary["valid"] += len(grouped)
            candidate = grouped[0]
            if len(grouped) > 1:
                signatures = {_digest(item) for item in grouped}
                if len(signatures) != 1:
                    summary["review_required"] += 1
                    issues.append({
                        "company_name": candidate["company_name"],
                        "stock_code": code,
                        "reason": "KRX_DUPLICATE_CONFLICT",
                    })
                    continue
                summary["duplicate_rows"] += len(grouped) - 1

            matches = existing_by_code.get(code, [])
            if len(matches) > 1:
                summary["review_required"] += 1
                issues.append({"company_name": candidate["company_name"], "stock_code": code, "reason": "DUPLICATE_STOCK_CODE"})
                continue

            source_meta = _provenance(observed_at=observed_at, from_year=from_year, to_year=end_year)
            if not matches:
                record: dict[str, Any] = {
                    "ipo_id": generate_ipo_id(
                        company_name=candidate["company_name"],
                        stock_code=code,
                        subscription_start=None,
                    ),
                    "company_name": candidate["company_name"],
                    "stock_code": code,
                    "listing_track": "spac" if is_spac_ipo(candidate) else "general",
                    "lead_managers": deepcopy(candidate["lead_managers"]),
                    "features": {},
                    "score": {},
                    "sources": {"official_historical_online": deepcopy(source_meta)},
                    "updated_at": observed_at,
                }
                for field in ("actual_listing_date", "final_offer_price", "market"):
                    if _source_has_value(field, candidate.get(field)):
                        record[field] = deepcopy(candidate[field])
                plans.append({"classification": "NEW", "stock_code": code, "record": record, "changes": []})
                summary["new"] += 1
                continue

            target = matches[0]
            if normalize_company_name(str(target.get("company_name") or "")) != normalize_company_name(candidate["company_name"]):
                summary["review_required"] += 1
                issues.append({
                    "company_name": candidate["company_name"],
                    "stock_code": code,
                    "reason": "COMPANY_NAME_CONFLICT",
                })
                continue

            changes: list[dict[str, Any]] = []
            for field in _AUTHORITATIVE_FIELDS:
                incoming = candidate.get(field)
                if not _source_has_value(field, incoming):
                    continue
                current_value = target.get(field)
                if not _same_value(field, current_value, incoming):
                    changes.append({"field": field, "before": deepcopy(current_value), "after": deepcopy(incoming)})

            if not target.get("listing_track"):
                derived_track = "spac" if is_spac_ipo(candidate) else "general"
                changes.append({"field": "listing_track", "before": target.get("listing_track"), "after": derived_track})

            if changes:
                plans.append({
                    "classification": "UPDATE",
                    "stock_code": code,
                    "company_name": candidate["company_name"],
                    "changes": changes,
                    "source": source_meta,
                })
                summary["updated"] += 1
            else:
                summary["unchanged"] += 1

        ticket = secrets.token_urlsafe(32)
        now = datetime.now().timestamp()
        state = {
            "username": username,
            "expires": now + PREVIEW_TTL_SECONDS,
            "market_digest": _market_digest(market),
            "plans": plans,
            "plans_digest": _digest(plans),
            "in_use": False,
        }
        with _PREVIEW_LOCK:
            _purge_previews_unlocked(now)
            _PREVIEWS[ticket] = state

        preview_changes = []
        for plan in plans[:50]:
            preview_changes.append({
                "classification": plan["classification"],
                "stock_code": plan["stock_code"],
                "company_name": plan.get("company_name") or plan.get("record", {}).get("company_name"),
                "changes": plan.get("changes") or [],
            })

        return {
            "source": "KRX_HISTORICAL_ONLINE",
            "from_year": from_year,
            "to_year": end_year,
            "by_year": by_year,
            "summary": summary,
            "changes": preview_changes,
            "changes_truncated": max(0, len(plans) - len(preview_changes)),
            "issues": issues[:20],
            "issues_truncated": max(0, len(issues) - 20),
            "preview_ticket": ticket,
        }
    finally:
        _SYNC_LOCK.release()


def commit_online_historical_preview(ticket: str, username: str) -> dict[str, Any]:
    """Atomically apply the exact reviewed online reconciliation plan."""
    token = str(ticket or "").strip()
    now = datetime.now().timestamp()
    with _PREVIEW_LOCK:
        state = _PREVIEWS.get(token)
        if not state or state.get("username") != username:
            _purge_previews_unlocked(now)
            raise HistoricalOnlineSyncError("PREVIEW_TICKET_INVALID", "과거자료 미리보기를 다시 실행해 주세요.")
        if float(state.get("expires") or 0) < now:
            _PREVIEWS.pop(token, None)
            raise HistoricalOnlineSyncError("PREVIEW_TICKET_EXPIRED", "과거자료 미리보기가 만료되었습니다. 다시 조회해 주세요.")
        if state.get("in_use"):
            raise HistoricalOnlineSyncError("PREVIEW_TICKET_IN_USE", "이미 반영 중인 미리보기입니다.")
        if _digest(state.get("plans")) != state.get("plans_digest"):
            _PREVIEWS.pop(token, None)
            raise HistoricalOnlineSyncError("PREVIEW_TICKET_INVALID", "과거자료 미리보기 검증에 실패했습니다.")
        state["in_use"] = True

    try:
        with _STORE_LOCK:
            market = _read_market_store_unlocked()
            if _market_digest(market) != state["market_digest"]:
                with _PREVIEW_LOCK:
                    _PREVIEWS.pop(token, None)
                raise HistoricalOnlineSyncError(
                    "PREVIEW_STALE",
                    "공모주 데이터가 변경되어 과거자료를 다시 조회해야 합니다.",
                )

            working = deepcopy(market)
            working.setdefault("ipos", [])
            changed_records: list[dict[str, Any]] = []
            committed_new = updated = fields_changed = 0
            observed_at = datetime.now().astimezone().isoformat()

            for plan in state["plans"]:
                code = plan["stock_code"]
                if plan["classification"] == "NEW":
                    record = deepcopy(plan["record"])
                    record["updated_at"] = observed_at
                    working["ipos"].append(record)
                    changed_records.append(record)
                    committed_new += 1
                    continue

                matches = [
                    item for item in working["ipos"]
                    if str(item.get("stock_code") or "").strip().upper() == code
                ]
                if len(matches) != 1:
                    raise HistoricalOnlineSyncError("PREVIEW_STALE", "공모주 데이터가 변경되어 과거자료를 다시 조회해야 합니다.")
                target = matches[0]
                for change in plan.get("changes") or []:
                    field = str(change.get("field") or "")
                    if field not in {*_AUTHORITATIVE_FIELDS, "listing_track"}:
                        raise HistoricalOnlineSyncError("PREVIEW_TICKET_INVALID", "허용되지 않은 과거자료 변경 항목입니다.")
                    after = deepcopy(change.get("after"))
                    if field in _AUTHORITATIVE_FIELDS and not _source_has_value(field, after):
                        continue
                    target[field] = after
                    fields_changed += 1
                sources = target.setdefault("sources", {})
                if not isinstance(sources, dict):
                    sources = {}
                    target["sources"] = sources
                sources["official_historical_online"] = deepcopy(plan.get("source") or {})
                target["updated_at"] = observed_at
                changed_records.append(target)
                updated += 1

            if changed_records:
                for record in changed_records:
                    record["score"] = calculate_wealth_ipo_score(record, working["ipos"])
                _write_market_store_unlocked(working)
    except Exception:
        with _PREVIEW_LOCK:
            if token in _PREVIEWS:
                _PREVIEWS[token]["in_use"] = False
        raise

    with _PREVIEW_LOCK:
        _PREVIEWS.pop(token, None)

    return {
        "status": "ok",
        "committed_new": committed_new,
        "updated": updated,
        "fields_changed": fields_changed,
        "total_after": len(working["ipos"]),
    }
