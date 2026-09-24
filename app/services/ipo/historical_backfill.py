"""Historical IPO backfill engine for 2020~present market data.

Safe, preview-before-write backfill from KRX new listings hydrated by official
OpenDART structured registration data before proposing canonical records.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.ipo.identity import find_matching_ipo, generate_ipo_id, is_spac_ipo, normalize_company_name
from app.services.ipo.krx_client import KrxClient, KrxClientError
from app.services.ipo.dart_client import (
    DartClient,
    DartRateLimitError,
    extract_document_text_from_zip,
    select_point_in_time_filing,
)
from app.services.ipo.dart_parser import DartSemanticParser
from app.services.ipo.normalize import normalize_equity_registration_response
from app.services.ipo.score import calculate_wealth_ipo_score
from app.services.ipo.store import (
    _STORE_LOCK,
    get_market_file,
    read_market_store,
    read_market_store_read_only,
    validate_market_store,
    write_market_store,
)


class HistoricalBackfillError(RuntimeError):
    """Raised when historical backfill encounters an unrecoverable error."""


class Classification(str, Enum):
    NEW = "NEW"
    ALREADY_PRESENT = "ALREADY_PRESENT"
    ENRICHABLE = "ENRICHABLE"
    CONFLICT = "CONFLICT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    EXCLUDED_PENDING = "EXCLUDED_PENDING"
    EXCLUDED_NO_LISTING_EVIDENCE = "EXCLUDED_NO_LISTING_EVIDENCE"
    EXCLUDED_WITHDRAWN = "EXCLUDED_WITHDRAWN"
    INVALID = "INVALID"


@dataclass
class PreviewItem:
    company_name: str
    subscription_start: str | None
    expected_listing_date: str | None
    actual_listing_date: str | None
    stock_code: str | None
    listing_track: str
    classification: str
    reason: str
    match_evidence: str
    candidate_record: dict[str, Any]
    existing_record: dict[str, Any] | None = None
    enrich_diff: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PreviewResult:
    market_digest: str
    from_year: int
    to_year: int
    items: list[PreviewItem] = field(default_factory=list)
    by_year: dict[int, dict[str, int]] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_digest": self.market_digest,
            "from_year": self.from_year,
            "to_year": self.to_year,
            "items": [item.to_dict() for item in self.items],
            "by_year": self.by_year,
            "totals": self.totals,
        }


def get_current_kst_date() -> date:
    """Return the current date in KST (UTC+9)."""
    try:
        kst = ZoneInfo("Asia/Seoul")
    except ZoneInfoNotFoundError:
        kst = timezone(timedelta(hours=9), name="Asia/Seoul")
    return datetime.now(kst).date()


def compute_market_digest(market_file: Path | None = None) -> str:
    """Compute SHA256 hex digest of canonical market store file."""
    f = market_file or get_market_file()
    if not f.exists():
        return ""
    try:
        raw_bytes = f.read_bytes()
        return hashlib.sha256(raw_bytes).hexdigest()
    except OSError:
        return ""


def _parse_iso_date(val: object) -> date | None:
    """Parse strict ISO date (YYYY-MM-DD), returning None if invalid."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        d = date.fromisoformat(s)
        if d.isoformat() != s:
            return None
        return d
    except ValueError:
        return None


def validate_subscription_dates(start: str | None, end: str | None) -> tuple[str | None, str | None, bool]:
    """Validate subscription start and end dates strictly.

    Returns (valid_start, valid_end, is_anomalous).
    - Missing/blank inputs are preserved as None without being flagged as anomalies.
    - If either provided field is an invalid ISO date, that field becomes None and is_anomalous is True.
    - If both dates are valid ISO format but end < start, valid_end becomes None and is_anomalous is True.
    A malformed or inverted date field is never propagated as authoritative.
    """
    has_raw_start = bool(start and str(start).strip())
    has_raw_end = bool(end and str(end).strip())

    if not has_raw_start and not has_raw_end:
        return None, None, False

    parsed_start = _parse_iso_date(start)
    parsed_end = _parse_iso_date(end)

    is_anomalous = False
    valid_start: str | None = None
    valid_end: str | None = None

    if has_raw_start:
        if parsed_start is not None:
            valid_start = parsed_start.isoformat()
        else:
            valid_start = None
            is_anomalous = True

    if has_raw_end:
        if parsed_end is not None:
            valid_end = parsed_end.isoformat()
        else:
            valid_end = None
            is_anomalous = True

    if parsed_start is not None and parsed_end is not None:
        if parsed_end < parsed_start:
            valid_end = None
            is_anomalous = True

    return valid_start, valid_end, is_anomalous


def _parse_dart_date(value: object) -> str | None:
    """Parse only explicit DART date values; never infer from a listing date."""
    raw = str(value or "").strip()
    if not raw:
        return None
    match = __import__("re").search(r"(20\d{2})\D{0,3}(\d{1,2})\D{0,3}(\d{1,2})", raw)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat()
    except ValueError:
        return None


def parse_dart_subscription_schedule(structured: dict[str, Any]) -> dict[str, Any] | None:
    """Extract explicit sbd/pymd schedule fields from normalized estkRs rows."""
    rows = structured.get("general", []) if isinstance(structured, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_sbd = row.get("sbd")
        if not raw_sbd:
            continue
        dates = [
            _parse_dart_date(match.group(0))
            for match in __import__("re").finditer(r"20\d{2}\D{0,3}\d{1,2}\D{0,3}\d{1,2}", str(raw_sbd))
        ]
        dates = [value for value in dates if value]
        if not dates:
            continue
        start, end = dates[0], dates[-1]
        valid_start, valid_end, anomalous = validate_subscription_dates(start, end)
        if anomalous or not valid_start:
            return None
        return {
            "subscription_start": valid_start,
            "subscription_end": valid_end or valid_start,
            "payment_date": _parse_dart_date(row.get("pymd")),
            "subscription_notice_date": _parse_dart_date(row.get("sband")),
            "allocation_notice_date": _parse_dart_date(row.get("asand")),
        }
    return None


class HistoricalBackfillEngine:
    """Backfill engine to inspect and safely commit historical IPO records."""

    MIN_SUPPORTED_YEAR = 2020

    def __init__(
        self,
        krx_client: KrxClient | None = None,
        dart_client: DartClient | None = None,
        username: str | None = None,
    ) -> None:
        self.krx_client = krx_client or KrxClient()
        self.dart_client = dart_client or DartClient(username=username)

    def load_master_evidence(
        self,
        listed_master: list[dict[str, Any]] | None = None,
        delisted_master: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Load listed and delisted company masters from public sources or injected fixtures."""
        if listed_master is None:
            try:
                listed_master = self.krx_client.fetch_listed_master()
            except KrxClientError as exc:
                raise HistoricalBackfillError(f"Failed to fetch KRX listed master: {exc}") from exc

        if delisted_master is None:
            try:
                delisted_master = self.krx_client.fetch_delisted_master()
            except KrxClientError as exc:
                raise HistoricalBackfillError(f"Failed to fetch KRX delisted master: {exc}") from exc

        return listed_master, delisted_master

    @staticmethod
    def _normalize_market(value: object) -> str | None:
        raw = str(value or "").strip().upper()
        if not raw:
            return None
        if "코스닥" in raw or "KOSDAQ" in raw or "KSQ" in raw:
            return "KOSDAQ"
        if "유가증권" in raw or "코스피" in raw or "KOSPI" in raw or "STK" in raw:
            return "KOSPI"
        if "코넥스" in raw or "KONEX" in raw or "KNX" in raw:
            return "KONEX"
        return None

    @classmethod
    def _listed_info(cls, item: dict[str, Any], code: str | None = None) -> dict[str, Any]:
        return {
            "stock_code": code or item.get("stock_code"),
            "company_name": item.get("company_name"),
            "market": cls._normalize_market(item.get("market_code") or item.get("market_eng_name") or item.get("market_name") or item.get("market")),
            # finder_stkisu has no trustworthy IPO listing date.
            "actual_listing_date": None,
        }

    @staticmethod
    def build_evidence_indexes(
        listed_master: list[dict[str, Any]],
        delisted_master: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build exact and normalized lookup indexes for listing evidence."""
        listed_by_code: dict[str, dict[str, Any]] = {}
        listed_by_norm_name: dict[str, list[dict[str, Any]]] = {}
        for item in listed_master:
            code = str(item.get("stock_code") or "").strip()
            name = str(item.get("company_name") or "").strip()
            norm = normalize_company_name(name)
            if code:
                listed_by_code[code] = item
            if norm:
                listed_by_norm_name.setdefault(norm, []).append(item)

        delisted_by_code: dict[str, dict[str, Any]] = {}
        delisted_by_norm_name: dict[str, list[dict[str, Any]]] = {}
        for item in delisted_master:
            code = str(item.get("stock_code") or "").strip()
            name = str(item.get("company_name") or "").strip()
            norm = normalize_company_name(name)
            if code:
                delisted_by_code[code] = item
            if norm:
                delisted_by_norm_name.setdefault(norm, []).append(item)

        return {
            "listed_by_code": listed_by_code,
            "listed_by_norm_name": listed_by_norm_name,
            "delisted_by_code": delisted_by_code,
            "delisted_by_norm_name": delisted_by_norm_name,
        }

    @staticmethod
    def match_listing_evidence(
        candidate: dict[str, Any],
        indexes: dict[str, Any],
    ) -> tuple[bool, dict[str, Any] | None, str, bool]:
        """Match candidate against listed and delisted masters.

        Returns:
            (has_evidence, matched_info, evidence_str, is_ambiguous)
        """
        code = str(candidate.get("stock_code") or "").strip()
        name = str(candidate.get("company_name") or "").strip()
        norm = normalize_company_name(name)

        listed_by_code = indexes["listed_by_code"]
        listed_by_norm = indexes["listed_by_norm_name"]
        delisted_by_code = indexes["delisted_by_code"]
        delisted_by_norm = indexes["delisted_by_norm_name"]

        # 1. Exact stock code in KRX listed master
        if code and code in listed_by_code:
            item = listed_by_code[code]
            return (
                True,
                HistoricalBackfillEngine._listed_info(item, code),
                f"KRX_LISTED_MASTER:{code}",
                False,
            )

        # 2. Exact stock code in KRX delisted master
        if code and code in delisted_by_code:
            item = delisted_by_code[code]
            mkt = HistoricalBackfillEngine._normalize_market(item.get("market_eng_name") or item.get("market_name"))
            return (
                True,
                {
                    "stock_code": code,
                    "company_name": item.get("company_name"),
                    "market": mkt,
                    "actual_listing_date": None,  # delisted master does not provide actual listing date
                },
                f"KRX_DELISTED_MASTER:{code}",
                False,
            )

        # 3. Exact normalized company name in KRX listed master
        if norm in listed_by_norm:
            matched_rows = listed_by_norm[norm]
            if len(matched_rows) == 1:
                item = matched_rows[0]
                m_code = item.get("stock_code")
                return (
                    True,
                    HistoricalBackfillEngine._listed_info(item, m_code),
                    f"KRX_LISTED_MASTER:{m_code}",
                    False,
                )
            # Multiple matches with same normalized name -> ambiguous!
            return False, None, "AMBIGUOUS_LISTED_MASTER_NAME", True

        # 4. Exact normalized company name in KRX delisted master
        if norm in delisted_by_norm:
            matched_rows = delisted_by_norm[norm]
            if len(matched_rows) == 1:
                item = matched_rows[0]
                m_code = item.get("stock_code")
                mkt = HistoricalBackfillEngine._normalize_market(item.get("market_eng_name") or item.get("market_name"))
                return (
                    True,
                    {
                        "stock_code": m_code,
                        "company_name": item.get("company_name"),
                        "market": mkt,
                        "actual_listing_date": None,
                    },
                    f"KRX_DELISTED_MASTER:{m_code}",
                    False,
                )
            return False, None, "AMBIGUOUS_DELISTED_MASTER_NAME", True

        return False, None, "NO_LISTING_EVIDENCE", False

    @staticmethod
    def _resolve_dart_corp_code(candidate: dict[str, Any], master: list[dict[str, Any]]) -> tuple[str | None, str | None]:
        stock_code = str(candidate.get("stock_code") or "").strip()
        company_name = normalize_company_name(str(candidate.get("company_name") or ""))
        stock_matches = [row for row in master if stock_code and str(row.get("stock_code") or "").strip() == stock_code]
        if len(stock_matches) == 1:
            return str(stock_matches[0].get("corp_code") or "").strip() or None, "stock_code"
        if len(stock_matches) > 1:
            return None, "ambiguous_stock_code"
        name_matches = [row for row in master if company_name and normalize_company_name(str(row.get("corp_name") or "")) == company_name]
        if len(name_matches) == 1:
            return str(name_matches[0].get("corp_code") or "").strip() or None, "company_name"
        return None, "ambiguous_company_name" if len(name_matches) > 1 else "not_found"

    def _hydrate_krx_candidate_from_dart(
        self, candidate: dict[str, Any], master: list[dict[str, Any]]
    ) -> tuple[dict[str, Any] | None, str]:
        """Attach only explicit estkRs schedule fields to one KRX candidate."""
        corp_code, match_type = self._resolve_dart_corp_code(candidate, master)
        if not corp_code:
            return None, f"DART corp_code {match_type}"
        listing_day = _parse_iso_date(candidate.get("actual_listing_date"))
        if listing_day is None:
            return None, "KRX actual listing date is invalid"
        try:
            raw = self.dart_client.get_equity_registration_statements(
                corp_code=corp_code,
                bgn_de=(listing_day - timedelta(days=730)).strftime("%Y%m%d"),
                end_de=listing_day.strftime("%Y%m%d"),
            )
        except Exception:
            return None, "DART structured schedule unavailable"
        schedule = parse_dart_subscription_schedule(normalize_equity_registration_response(raw))
        if not schedule:
            return None, "DART subscription date missing or invalid"
        hydrated = dict(candidate)
        hydrated.update(schedule)
        hydrated["corp_code"] = corp_code
        hydrated["_dart_match_type"] = match_type
        return hydrated, ""

    def generate_preview(
        self,
        from_year: int = 2020,
        to_year: int | None = None,
        *,
        listed_master: list[dict[str, Any]] | None = None,
        delisted_master: list[dict[str, Any]] | None = None,
    ) -> PreviewResult:
        """Generate read-only preview of historical backfill candidates.

        Fails closed on unsupported year ranges. Reads current market store without modifying it.
        """
        kst_today = get_current_kst_date()
        current_year = kst_today.year

        if to_year is None:
            to_year = current_year

        if from_year < self.MIN_SUPPORTED_YEAR:
            raise HistoricalBackfillError(
                f"HISTORICAL_RANGE_UNSUPPORTED: Only years >= {self.MIN_SUPPORTED_YEAR} are supported in Stage 2B"
            )

        if to_year > current_year:
            raise HistoricalBackfillError(
                f"HISTORICAL_RANGE_UNSUPPORTED: to_year ({to_year}) cannot exceed current KST year ({current_year})"
            )

        if from_year > to_year:
            raise HistoricalBackfillError(
                f"Invalid year range: from_year ({from_year}) must be <= to_year ({to_year})"
            )

        market_digest = compute_market_digest()
        store = read_market_store_read_only()
        existing_ipos = store.get("ipos", [])

        # Phase A requires the operator's user-scoped DART credential.  KRX
        # discovers authoritative listings; DART alone supplies subscription
        # dates.  Do not manufacture a schedule from a listing date.
        if not self.dart_client.is_configured():
            raise HistoricalBackfillError("DART credential is not configured for historical schedule hydration")
        try:
            dart_master = self.dart_client.get_corp_code_master()
        except Exception as exc:
            raise HistoricalBackfillError("Failed to load OpenDART corp-code master") from exc

        preview_items: list[PreviewItem] = []
        by_year: dict[int, dict[str, int]] = {}
        totals: dict[str, int] = {
            "fetched": 0,
            "auto_eligible": 0,
            "new": 0,
            "enrichable": 0,
            "already_present": 0,
            "conflict": 0,
            "review": 0,
            "excluded": 0,
        }

        seen_preview_stock_codes: set[str] = set()

        for year in range(from_year, to_year + 1):
            year_counts: dict[str, int] = {
                "fetched": 0,
                "listing_verified": 0,
                "NEW": 0,
                "ALREADY_PRESENT": 0,
                "ENRICHABLE": 0,
                "CONFLICT": 0,
                "REVIEW_REQUIRED": 0,
                "EXCLUDED": 0,
            }

            try:
                raw_items = self.krx_client.fetch_new_listings(f"{year}-01-01", f"{year}-12-31")
            except KrxClientError as exc:
                raise HistoricalBackfillError(f"Failed to fetch KRX new listings for {year}: {exc}") from exc
            target_candidates = raw_items

            for cand in target_candidates:
                year_counts["fetched"] += 1
                totals["fetched"] += 1

                company_name = str(cand.get("company_name") or "").strip()
                hydrated, hydrate_reason = self._hydrate_krx_candidate_from_dart(cand, dart_master)
                if hydrated is None:
                    preview_items.append(PreviewItem(
                        company_name=company_name, subscription_start=None, expected_listing_date=None,
                        actual_listing_date=cand.get("actual_listing_date"), stock_code=cand.get("stock_code"),
                        listing_track="spac" if is_spac_ipo(cand) else "general",
                        classification=Classification.REVIEW_REQUIRED.value, reason=hydrate_reason,
                        match_evidence="KRX_NEW_LISTING", candidate_record=cand,
                    ))
                    year_counts["REVIEW_REQUIRED"] += 1; totals["review"] += 1
                    continue
                cand = hydrated
                sub_start = cand.get("subscription_start")
                exp_listing = None
                final_price = cand.get("final_offer_price")
                is_spac = is_spac_ipo(cand)
                listing_track = "spac" if is_spac else "general"
                year_counts["listing_verified"] += 1
                stock_code = str(cand.get("stock_code") or "").strip() or None
                actual_listing = cand.get("actual_listing_date")
                market = self._normalize_market(cand.get("market"))
                evidence_str = f"KRX_NEW_LISTING:{stock_code or normalize_company_name(company_name)}"

                # Validate subscription date range for anomalies
                raw_sub_end = cand.get("subscription_end")
                valid_sub_start, valid_sub_end, is_date_anomalous = validate_subscription_dates(sub_start, raw_sub_end)

                # Build canonical candidate record
                now_iso = datetime.now(timezone(timedelta(hours=9))).isoformat()
                candidate_rec: dict[str, Any] = {
                    "company_name": company_name,
                    "stock_code": stock_code,
                    "corp_code": cand.get("corp_code"),
                    "market": market,
                    "listing_track": listing_track,
                    "filing_date": cand.get("filing_date"),
                    "demand_forecast_start": cand.get("demand_forecast_start"),
                    "demand_forecast_end": cand.get("demand_forecast_end"),
                    "subscription_start": valid_sub_start,
                    "subscription_end": valid_sub_end,
                    "_source_sub_date_anomaly": is_date_anomalous,
                    "payment_date": cand.get("payment_date"),
                    "refund_date": None,  # refund_date remains None; never guessed from payment_date
                    "expected_listing_date": exp_listing,
                    "actual_listing_date": actual_listing,  # only from official master
                    "final_offer_price": final_price,
                    "lead_managers": cand.get("lead_managers") or [],
                    "features": {},
                    "score": {},
                    "sources": {
                            "krx_historical": {
                            "source": "KRX_NEW_LISTING",
                            "observed_at": now_iso,
                            "stock_code": stock_code,
                            "match_evidence": evidence_str,
                        },
                        "dart_schedule_historical": {
                            "source": "OpenDART_estkRs",
                            "corp_code": cand.get("corp_code"),
                            "match_type": cand.get("_dart_match_type"),
                            "subscription_notice_date": cand.get("subscription_notice_date"),
                            "allocation_notice_date": cand.get("allocation_notice_date"),
                        },
                    },
                    "updated_at": now_iso,
                }
                candidate_rec["ipo_id"] = generate_ipo_id(
                    company_name=company_name,
                    stock_code=stock_code,
                    subscription_start=sub_start,
                )

                # Check if pending (listing date > today or active subscription)
                today_str = kst_today.isoformat()
                effective_listing = actual_listing or exp_listing
                is_pending = False
                if effective_listing and effective_listing > today_str:
                    is_pending = True
                elif sub_start and sub_start > today_str:
                    is_pending = True

                if is_pending:
                    item = PreviewItem(
                        company_name=company_name,
                        subscription_start=sub_start,
                        expected_listing_date=exp_listing,
                        actual_listing_date=actual_listing,
                        stock_code=stock_code,
                        listing_track=listing_track,
                        classification=Classification.EXCLUDED_PENDING.value,
                        reason=f"Candidate is pending/future (effective listing {effective_listing} or sub start {sub_start} > {today_str})",
                        match_evidence=evidence_str,
                        candidate_record=candidate_rec,
                    )
                    preview_items.append(item)
                    year_counts["EXCLUDED"] += 1
                    totals["excluded"] += 1
                    continue

                # Check duplicate stock code across preview candidates
                if stock_code and stock_code in seen_preview_stock_codes:
                    item = PreviewItem(
                        company_name=company_name,
                        subscription_start=sub_start,
                        expected_listing_date=exp_listing,
                        actual_listing_date=actual_listing,
                        stock_code=stock_code,
                        listing_track=listing_track,
                        classification=Classification.CONFLICT.value,
                        reason=f"Duplicate stock_code {stock_code} encountered in multiple candidates",
                        match_evidence=evidence_str,
                        candidate_record=candidate_rec,
                    )
                    preview_items.append(item)
                    year_counts["CONFLICT"] += 1
                    totals["conflict"] += 1
                    continue

                # Compare against canonical market store
                matched, review_required = find_matching_ipo(candidate_rec, existing_ipos)

                if review_required:
                    item = PreviewItem(
                        company_name=company_name,
                        subscription_start=sub_start,
                        expected_listing_date=exp_listing,
                        actual_listing_date=actual_listing,
                        stock_code=stock_code,
                        listing_track=listing_track,
                        classification=Classification.REVIEW_REQUIRED.value,
                        reason="Name matches existing record but lacks exact code/procs match",
                        match_evidence=evidence_str,
                        candidate_record=candidate_rec,
                    )
                    preview_items.append(item)
                    year_counts["REVIEW_REQUIRED"] += 1
                    totals["review"] += 1
                    continue

                if matched is None:
                    # NEW candidate!
                    if stock_code:
                        seen_preview_stock_codes.add(stock_code)
                    item = PreviewItem(
                        company_name=company_name,
                        subscription_start=sub_start,
                        expected_listing_date=exp_listing,
                        actual_listing_date=actual_listing,
                        stock_code=stock_code,
                        listing_track=listing_track,
                        classification=Classification.NEW.value,
                        reason="Verified historical IPO with listing evidence; not present in market store",
                        match_evidence=evidence_str,
                        candidate_record=candidate_rec,
                    )
                    preview_items.append(item)
                    year_counts["NEW"] += 1
                    totals["new"] += 1
                    totals["auto_eligible"] += 1
                    continue

                # Existing record matched: compare fields for CONFLICT / ENRICHABLE / ALREADY_PRESENT
                critical_fields = [
                    "stock_code",
                    "company_name",
                    "market",
                    "subscription_start",
                    "subscription_end",
                    "final_offer_price",
                    "expected_listing_date",
                    "actual_listing_date",
                ]

                conflicts: list[str] = []
                enrich_diff: dict[str, Any] = {}

                is_cand_date_anomalous = bool(candidate_rec.get("_source_sub_date_anomaly"))
                for f in critical_fields:
                    ex_v = matched.get(f)
                    cd_v = candidate_rec.get(f)

                    ex_blank = ex_v in (None, "", []) or (f == "final_offer_price" and ex_v == 0)
                    cd_blank = cd_v in (None, "", []) or (f == "final_offer_price" and cd_v == 0)

                    if not ex_blank and not cd_blank:
                        if ex_v != cd_v:
                            conflicts.append(f"{f} mismatch (existing='{ex_v}' vs candidate='{cd_v}')")
                    elif ex_blank and not cd_blank:
                        enrich_diff[f] = cd_v
                    elif not ex_blank and cd_blank and f in ("subscription_start", "subscription_end") and is_cand_date_anomalous:
                        # Existing canonical has a corrected/valid date while raw candidate source had malformed date; preserve canonical
                        pass

                if conflicts:
                    item = PreviewItem(
                        company_name=company_name,
                        subscription_start=sub_start,
                        expected_listing_date=exp_listing,
                        actual_listing_date=actual_listing,
                        stock_code=stock_code,
                        listing_track=listing_track,
                        classification=Classification.CONFLICT.value,
                        reason="; ".join(conflicts),
                        match_evidence=evidence_str,
                        candidate_record=candidate_rec,
                        existing_record=matched,
                    )
                    preview_items.append(item)
                    year_counts["CONFLICT"] += 1
                    totals["conflict"] += 1
                elif enrich_diff:
                    item = PreviewItem(
                        company_name=company_name,
                        subscription_start=sub_start,
                        expected_listing_date=exp_listing,
                        actual_listing_date=actual_listing,
                        stock_code=stock_code,
                        listing_track=listing_track,
                        classification=Classification.ENRICHABLE.value,
                        reason=f"Blank fields can be safely enriched: {list(enrich_diff.keys())}",
                        match_evidence=evidence_str,
                        candidate_record=candidate_rec,
                        existing_record=matched,
                        enrich_diff=enrich_diff,
                    )
                    preview_items.append(item)
                    year_counts["ENRICHABLE"] += 1
                    totals["enrichable"] += 1
                    totals["auto_eligible"] += 1
                else:
                    item = PreviewItem(
                        company_name=company_name,
                        subscription_start=sub_start,
                        expected_listing_date=exp_listing,
                        actual_listing_date=actual_listing,
                        stock_code=stock_code,
                        listing_track=listing_track,
                        classification=Classification.ALREADY_PRESENT.value,
                        reason="All critical fields already present and match in canonical store",
                        match_evidence=evidence_str,
                        candidate_record=candidate_rec,
                        existing_record=matched,
                    )
                    preview_items.append(item)
                    year_counts["ALREADY_PRESENT"] += 1
                    totals["already_present"] += 1

            by_year[year] = year_counts

        return PreviewResult(
            market_digest=market_digest,
            from_year=from_year,
            to_year=to_year,
            items=preview_items,
            by_year=by_year,
            totals=totals,
        )

    def commit_backfill(
        self,
        preview_result: PreviewResult,
    ) -> dict[str, int]:
        """Atomically commit eligible (NEW and ENRICHABLE) records from a valid preview.

        Guarantees:
        - Entire read-verify-merge-write sequence is guarded by _STORE_LOCK.
        - Fails closed with PREVIEW_STALE if market.json changed since preview.
        - Blank-only enrichment: non-empty existing fields are NEVER overwritten.
        - Validates market store before writing.
        """
        with _STORE_LOCK:
            current_digest = compute_market_digest()
            if current_digest != preview_result.market_digest:
                raise HistoricalBackfillError(
                    f"PREVIEW_STALE: market.json has changed since preview was generated "
                    f"(expected {preview_result.market_digest}, got {current_digest})"
                )

            store = read_market_store()
            ipos = store.get("ipos", [])

            applied_new = 0
            applied_enrich = 0

            for item in preview_result.items:
                if item.classification == Classification.NEW.value:
                    rec = deepcopy(item.candidate_record)
                    rec.pop("_source_sub_date_anomaly", None)
                    ipos.append(rec)
                    applied_new += 1
                elif item.classification == Classification.ENRICHABLE.value:
                    matched, _ = find_matching_ipo(item.candidate_record, ipos)
                    if matched is not None and item.enrich_diff:
                        for k, v in item.enrich_diff.items():
                            ex_v = matched.get(k)
                            ex_blank = ex_v in (None, "", []) or (k == "final_offer_price" and ex_v == 0)
                            if ex_blank:
                                matched[k] = v
                        # Safely merge sources provenance without overwriting existing sources
                        if "sources" in item.candidate_record:
                            existing_sources = matched.setdefault("sources", {})
                            for sk, sv in item.candidate_record["sources"].items():
                                if sk not in existing_sources:
                                    existing_sources[sk] = sv
                        applied_enrich += 1

            validate_market_store(store)
            write_market_store(store)

            return {
                "applied_new": applied_new,
                "applied_enrich": applied_enrich,
                "total_committed": applied_new + applied_enrich,
            }

    def enrich_dart(
        self,
        *,
        username: str | None = None,
        from_year: int = MIN_SUPPORTED_YEAR,
        to_year: int | None = None,
        dart_client: DartClient | None = None,
        dry_run: bool = False,
        max_records: int | None = None,
    ) -> dict[str, int | str]:
        """Phase B historical DART enrichment with record-level checkpoints.

        Each successful record receives a ``dart_historical`` source marker and
        is persisted independently.  A later invocation therefore resumes
        without re-fetching already enriched point-in-time records.  A rate
        limit stops the batch cleanly; it never rolls back previous successes.
        """
        current_year = get_current_kst_date().year
        to_year = to_year or current_year
        if from_year < self.MIN_SUPPORTED_YEAR or to_year < from_year:
            raise HistoricalBackfillError("Historical DART enrichment year range is invalid")
        dart = dart_client or DartClient(username=username)
        if not dart.is_configured():
            return {"status": "not_configured", "processed": 0, "enriched": 0, "skipped": 0, "failed": 0}

        store = read_market_store()
        ipos = store.get("ipos", [])
        try:
            from app.services.ipo.orchestrator import _resolve_missing_dart_corp_codes
            unresolved = [
                item for item in ipos
                if not item.get("corp_code") and str(item.get("subscription_start") or "")[:4].isdigit()
            ]
            if unresolved:
                _resolve_missing_dart_corp_codes(ipos, dart.get_corp_code_master())
        except DartRateLimitError:
            return {"status": "rate_limited", "processed": 0, "enriched": 0, "skipped": 0, "failed": 0}
        except Exception:
            # A master failure must not corrupt or block independently resolvable records.
            pass

        processed = enriched = skipped = failed = 0
        parser = DartSemanticParser()
        for ipo in ipos:
            if max_records is not None and processed >= max_records:
                break
            if is_spac_ipo(ipo):
                skipped += 1
                continue
            sub_start = _parse_iso_date(ipo.get("subscription_start"))
            if sub_start is None or not (from_year <= sub_start.year <= to_year):
                continue
            score_day = sub_start - timedelta(days=1)
            checkpoint = (ipo.get("sources") or {}).get("dart_historical", {})
            if checkpoint.get("score_as_of") == score_day.isoformat() and checkpoint.get("status") == "ok":
                skipped += 1
                continue
            corp_code = str(ipo.get("corp_code") or "").strip()
            if not corp_code:
                skipped += 1
                continue

            processed += 1
            try:
                filings = dart.get_filing_list(
                    corp_code=corp_code,
                    bgn_de=(score_day - timedelta(days=365)).strftime("%Y%m%d"),
                    end_de=score_day.strftime("%Y%m%d"),
                    pblntf_detail_ty="C001",
                    last_reprt_at="N",
                ).get("list", [])
                filing = select_point_in_time_filing(filings, score_day.isoformat())
                if not filing or not filing.get("rcept_no"):
                    skipped += 1
                    continue
                source_date = str(filing.get("rcept_dt") or "")
                doc_text = extract_document_text_from_zip(dart.download_document_zip(str(filing["rcept_no"])))
                parsed_features = parser.parse_document(doc_text, str(filing["rcept_no"]), source_date)
                offer_band = parser.extract_offer_band(doc_text)
                if not dry_run:
                    features = ipo.setdefault("features", {})
                    for name, feature in parsed_features.items():
                        existing = features.get(name)
                        if not isinstance(existing, dict) or existing.get("status") != "ok" or existing.get("value") is None:
                            features[name] = feature
                    sources = ipo.setdefault("sources", {})
                    if offer_band:
                        low, high = offer_band
                        if ipo.get("offer_band_low") in (None, ""):
                            ipo["offer_band_low"] = low
                            sources["offer_band_low"] = {"value": low, "source": "dart_document", "source_date": source_date, "confidence": "high"}
                        if ipo.get("offer_band_high") in (None, ""):
                            ipo["offer_band_high"] = high
                            sources["offer_band_high"] = {"value": high, "source": "dart_document", "source_date": source_date, "confidence": "high"}
                    sources["dart_historical"] = {"status": "ok", "score_as_of": score_day.isoformat(), "rcept_no": str(filing["rcept_no"]), "source_date": source_date}
                    ipo["score"] = calculate_wealth_ipo_score(ipo, ipos)
                    # Deliberately persist each completed IPO: this is the resume checkpoint.
                    write_market_store(store)
                enriched += 1
            except DartRateLimitError:
                return {"status": "rate_limited", "processed": processed, "enriched": enriched, "skipped": skipped, "failed": failed}
            except Exception:
                failed += 1
                # One historical filing failure is isolated from the rest of the batch.
                continue
        return {"status": "ok", "processed": processed, "enriched": enriched, "skipped": skipped, "failed": failed}
