"""Pure mapping of normalized Toss WTS daily-profit rows to import candidates.

This module deliberately does not persist records or create local identities.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping


TOSS_WTS_BROKER = "토스증권"
_SUPPORTED_MARKETS = frozenset({"kr", "us"})
_SUPPORTED_RATE_BASES = frozenset({"KRW", "USD"})
_FINGERPRINT_PREFIX = "toss-wts-realized:v1:"
_FINGERPRINT_RE = re.compile(r"^toss-wts-realized:v1:[0-9a-f]{64}$")


def _require_text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    text = value.strip()
    if not allow_empty and not text:
        raise ValueError(f"{field} must not be empty")
    return text


def _finite_number(value: Any, field: str, *, allow_none: bool = False) -> int | float | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    if not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return value


def _money_pair(value: Any, field: str) -> dict[str, int | float | None]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a money pair")
    return {
        "krw": _finite_number(value.get("krw"), f"{field}.krw", allow_none=True),
        "usd": _finite_number(value.get("usd"), f"{field}.usd", allow_none=True),
    }


def _canonical_number(value: Any, field: str, *, allow_none: bool = False) -> str | None:
    number = _finite_number(value, field, allow_none=allow_none)
    if number is None:
        return None
    try:
        decimal = Decimal(str(number))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not decimal.is_finite():
        raise ValueError(f"{field} must be a finite number")
    if decimal.is_zero():
        return "0"
    normalized = decimal.normalize()
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _fingerprint_identity(candidate: Mapping[str, Any]) -> tuple[list[str | int | None], tuple[str, str, str, str]]:
    if not isinstance(candidate, Mapping):
        raise ValueError("candidate must be a mapping")
    if candidate.get("source") != "toss_wts":
        raise ValueError("candidate source must be toss_wts")
    scope = _require_text(candidate.get("source_account_scope"), "source_account_scope")
    date = _require_text(candidate.get("date"), "date")
    meta = candidate.get("source_meta")
    if not isinstance(meta, Mapping):
        raise ValueError("source_meta must be a mapping")
    market_type = _require_text(meta.get("market_type"), "source_meta.market_type").strip().lower()
    if market_type not in _SUPPORTED_MARKETS:
        raise ValueError("unsupported source_meta.market_type")
    product_code = _require_text(meta.get("product_code"), "source_meta.product_code")
    quantity = _canonical_number(meta.get("quantity"), "source_meta.quantity")

    def canonical_pair(key: str) -> tuple[str | None, str | None]:
        pair = meta.get(key)
        if not isinstance(pair, Mapping):
            raise ValueError(f"source_meta.{key} must be a money pair")
        return (
            _canonical_number(pair.get("krw"), f"source_meta.{key}.krw", allow_none=True),
            _canonical_number(pair.get("usd"), f"source_meta.{key}.usd", allow_none=True),
        )

    profit_krw, profit_usd = canonical_pair("profit_loss")
    buy_krw, buy_usd = canonical_pair("buy_amount")
    sell_krw, sell_usd = canonical_pair("sell_amount")
    payload: list[str | int | None] = [
        "toss-wts-realized", 1, scope, date, market_type, product_code, quantity,
        profit_krw, profit_usd, buy_krw, buy_usd, sell_krw, sell_usd,
    ]
    return payload, (scope, date, market_type, product_code)


def build_toss_wts_realized_fingerprint(candidate: Mapping[str, Any]) -> str:
    """Build a deterministic v1 fingerprint without modifying the candidate."""
    payload, _ = _fingerprint_identity(candidate)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _FINGERPRINT_PREFIX + hashlib.sha256(encoded).hexdigest()


def _coarse_key(candidate: Mapping[str, Any]) -> tuple[str, str, str, str]:
    _, coarse = _fingerprint_identity(candidate)
    return coarse


def _is_trusted_fingerprint(value: Any) -> bool:
    return isinstance(value, str) and _FINGERPRINT_RE.fullmatch(value) is not None


def preview_toss_wts_realized_import(
    candidates: Iterable[Mapping[str, Any]],
    existing_records: Iterable[Mapping[str, Any]],
    *,
    source_account_scope: str,
) -> dict[str, Any]:
    """Classify an in-memory WTS batch without reading, writing, or mutating data."""
    scope = _require_text(source_account_scope, "source_account_scope")
    candidate_list = list(candidates)
    existing_list = list(existing_records)
    existing_counts: Counter[str] = Counter()
    existing_by_coarse: dict[tuple[str, str, str, str], set[str]] = {}
    existing_unresolved_indices: list[int] = []

    for index, record in enumerate(existing_list):
        if not isinstance(record, Mapping) or record.get("source") != "toss_wts":
            continue
        if record.get("source_account_scope") != scope:
            continue
        fingerprint = record.get("source_fingerprint")
        try:
            computed = build_toss_wts_realized_fingerprint(record)
            coarse = _coarse_key(record)
        except ValueError:
            existing_unresolved_indices.append(index)
            continue
        if not _is_trusted_fingerprint(fingerprint) or fingerprint != computed:
            existing_unresolved_indices.append(index)
            continue
        existing_counts[fingerprint] += 1
        existing_by_coarse.setdefault(coarse, set()).add(fingerprint)

    already_indices: list[int] = []
    new_indices: list[int] = []
    ambiguous_indices: list[int] = []
    invalid_indices: list[int] = []
    fingerprints_by_index: dict[int, str] = {}
    fetched_counts: Counter[str] = Counter()
    assigned_existing: Counter[str] = Counter()

    for index, candidate in enumerate(candidate_list):
        try:
            if candidate.get("source_account_scope") != scope:
                raise ValueError("candidate source_account_scope does not match batch scope")
            fingerprint = build_toss_wts_realized_fingerprint(candidate)
            coarse = _coarse_key(candidate)
        except (AttributeError, ValueError):
            invalid_indices.append(index)
            continue

        fingerprints_by_index[index] = fingerprint
        fetched_counts[fingerprint] += 1
        if assigned_existing[fingerprint] < existing_counts[fingerprint]:
            assigned_existing[fingerprint] += 1
            already_indices.append(index)
        elif fingerprint not in existing_by_coarse.get(coarse, set()) and coarse in existing_by_coarse:
            ambiguous_indices.append(index)
        else:
            new_indices.append(index)

    existing_surplus = sum(max(count - fetched_counts[fingerprint], 0) for fingerprint, count in existing_counts.items())
    write_ready = not invalid_indices and not ambiguous_indices and not existing_unresolved_indices and bool(new_indices)
    return {
        "fetched": len(candidate_list),
        "new": len(new_indices),
        "already_imported": len(already_indices),
        "ambiguous": len(ambiguous_indices),
        "invalid": len(invalid_indices),
        "existing_unresolved": len(existing_unresolved_indices),
        "existing_surplus": existing_surplus,
        "manual_affected": 0,
        "write_ready": write_ready,
        "new_indices": new_indices,
        "already_imported_indices": already_indices,
        "ambiguous_indices": ambiguous_indices,
        "invalid_indices": invalid_indices,
        "existing_unresolved_indices": existing_unresolved_indices,
        "fingerprints_by_index": fingerprints_by_index,
    }


def map_toss_wts_profit_row(
    row: Mapping[str, Any],
    *,
    account_name: str,
    source_account_scope: str,
    owner: str,
    profit_rate_basis: str,
    fetched_at: str,
) -> dict[str, Any]:
    """Return an unstored import candidate from one canonical WTS daily-profit row.

    ``is_ipo`` is a Wealth compatibility default, not an assertion that Toss
    classified the transaction as non-IPO.  WTS does not provide that signal.
    """
    if not isinstance(row, Mapping):
        raise ValueError("row must be a mapping")

    market_type = _require_text(row.get("market_type"), "market_type").strip().lower()
    if market_type not in _SUPPORTED_MARKETS:
        raise ValueError("unsupported market_type")

    basis = _require_text(profit_rate_basis, "profit_rate_basis")
    if basis not in _SUPPORTED_RATE_BASES:
        raise ValueError("unsupported profit_rate_basis")

    date = _require_text(row.get("date"), "date")
    code = _require_text(row.get("product_code"), "product_code")
    name = _require_text(row.get("name"), "name")
    symbol = _require_text(row.get("symbol"), "symbol", allow_empty=True)
    quantity = _finite_number(row.get("quantity"), "quantity")
    profit_rate = _finite_number(row.get("profit_rate"), "profit_rate")
    profit_loss = _money_pair(row.get("profit_loss"), "profit_loss")
    buy_amount = _money_pair(row.get("buy_amount"), "buy_amount")
    sell_amount = _money_pair(row.get("sell_amount"), "sell_amount")

    scope = _require_text(source_account_scope, "source_account_scope")
    display_account_name = _require_text(account_name, "account_name", allow_empty=True)
    mapped_owner = _require_text(owner, "owner")
    source_fetched_at = _require_text(fetched_at, "fetched_at")

    if market_type == "kr":
        if profit_loss["krw"] is None:
            raise ValueError("profit_loss.krw is required for kr market")
        currency = "KRW"
        pnl = profit_loss["krw"]
        pnl_krw = profit_loss["krw"]
    else:
        if profit_loss["usd"] is None:
            raise ValueError("profit_loss.usd is required for us market")
        if profit_loss["krw"] is None:
            raise ValueError("profit_loss.krw is required for us market")
        currency = "USD"
        pnl = profit_loss["usd"]
        pnl_krw = profit_loss["krw"]

    return {
        "date": date,
        "code": code,
        "name": name,
        "asset_type": "stock",
        "currency": currency,
        "pnl": pnl,
        "fx_rate": None,
        "fx_pnl_krw": None,
        "pnl_krw": pnl_krw,
        "is_ipo": False,
        "owner": mapped_owner,
        "broker": TOSS_WTS_BROKER,
        "account_name": display_account_name,
        "memo": "",
        "source": "toss_wts",
        "source_account_scope": scope,
        "source_meta": {
            "market_type": market_type,
            "symbol": symbol,
            "product_code": code,
            "quantity": quantity,
            "profit_rate": profit_rate,
            "profit_rate_basis": basis,
            "profit_loss": profit_loss,
            "buy_amount": buy_amount,
            "sell_amount": sell_amount,
            "fetched_at": source_fetched_at,
        },
    }


def preview_toss_wts_realized_selection(
    selected_items: list[Mapping[str, Any]],
    destination_account: Mapping[str, Any],
    existing_records: Iterable[Mapping[str, Any]],
    *,
    user_id: str,
    current_generation_id: str | None = None,
    profit_rate_basis: str = "KRW",
) -> dict[str, Any]:
    """Classify user-selected WTS rows for import into a chosen Wealth account.

    Zero financial writes. Enforces row token integrity and binds rows
    to the current active WTS runtime generation.
    """
    from app.services.toss_wts_feed import verify_realized_feed_row_token

    destination_account_name = str(
        destination_account.get("account_name") or destination_account.get("name") or ""
    ).strip()
    destination_broker = str(destination_account.get("broker") or TOSS_WTS_BROKER).strip()
    destination_owner = str(destination_account.get("owner") or "모두").strip()

    existing_list = list(existing_records)
    existing_wts_counts: Counter[str] = Counter()
    for rec in existing_list:
        if isinstance(rec, Mapping) and rec.get("source") == "toss_wts":
            fp = rec.get("source_fingerprint")
            if fp and _is_trusted_fingerprint(fp):
                existing_wts_counts[fp] += 1

    assigned_wts_counts: Counter[str] = Counter()
    classified_items: list[dict[str, Any]] = []

    counts = {
        "selected": len(selected_items),
        "new": 0,
        "already_imported": 0,
        "possible_duplicate": 0,
        "invalid": 0,
    }

    for idx, item in enumerate(selected_items):
        if not isinstance(item, Mapping):
            counts["invalid"] += 1
            classified_items.append({
                "index": idx,
                "status": "INVALID",
                "reason": "MALFORMED_ITEM",
                "candidate": None,
            })
            continue

        if "row" in item and isinstance(item["row"], Mapping):
            row = item["row"]
            token = item.get("selection_token") or row.get("selection_token")
        else:
            row = item
            token = item.get("selection_token")

        if not isinstance(token, str):
            token = ""

        valid, err_code = verify_realized_feed_row_token(
            row, token, user_id=user_id, current_generation_id=current_generation_id
        )
        if not valid:
            counts["invalid"] += 1
            classified_items.append({
                "index": idx,
                "status": "INVALID",
                "reason": err_code or "TOKEN_INVALID",
                "candidate": None,
            })
            continue

        try:
            candidate = map_toss_wts_profit_row(
                row,
                account_name=destination_account_name,
                source_account_scope="unverified",
                owner=destination_owner,
                profit_rate_basis=profit_rate_basis,
                fetched_at=str(row.get("fetched_at") or "unspecified"),
            )
            candidate["broker"] = destination_broker or TOSS_WTS_BROKER
            fingerprint = build_toss_wts_realized_fingerprint(candidate)
            candidate["source_fingerprint"] = fingerprint
        except (ValueError, TypeError, KeyError):
            counts["invalid"] += 1
            classified_items.append({
                "index": idx,
                "status": "INVALID",
                "reason": "MAPPING_FAILED",
                "candidate": None,
            })
            continue

        if assigned_wts_counts[fingerprint] < existing_wts_counts[fingerprint]:
            assigned_wts_counts[fingerprint] += 1
            counts["already_imported"] += 1
            classified_items.append({
                "index": idx,
                "status": "ALREADY_IMPORTED",
                "reason": "EXACT_WTS_FINGERPRINT_MATCH",
                "fingerprint": fingerprint,
                "candidate": candidate,
            })
            continue

        cand_date = candidate.get("date")
        cand_code = candidate.get("code")
        cand_name = candidate.get("name")
        cand_pnl = float(candidate.get("pnl", 0.0))
        cand_pnl_krw = float(candidate.get("pnl_krw", 0.0))

        manual_match = None
        for rec in existing_list:
            if not isinstance(rec, Mapping) or rec.get("source") == "toss_wts":
                continue
            if str(rec.get("date")) != str(cand_date):
                continue
            rec_code = str(rec.get("code", "")).strip()
            rec_name = str(rec.get("name", "")).strip()
            code_or_name_match = (
                (rec_code and rec_code == cand_code)
                or (rec_name and rec_name == cand_name)
            )
            if not code_or_name_match:
                continue
            rec_pnl = float(rec.get("pnl", 0.0))
            rec_pnl_krw = float(rec.get("pnl_krw", 0.0))
            pnl_match = (
                abs(rec_pnl - cand_pnl) < 0.01
                or abs(rec_pnl_krw - cand_pnl_krw) < 1.0
            )
            if pnl_match:
                manual_match = {
                    "id": rec.get("id"),
                    "date": rec.get("date"),
                    "code": rec.get("code"),
                    "name": rec.get("name"),
                    "pnl": rec_pnl,
                    "account_name": rec.get("account_name"),
                }
                break

        if manual_match:
            counts["possible_duplicate"] += 1
            classified_items.append({
                "index": idx,
                "status": "POSSIBLE_DUPLICATE",
                "reason": "MATCHING_MANUAL_RECORD",
                "matched_record": manual_match,
                "fingerprint": fingerprint,
                "candidate": candidate,
            })
            continue

        counts["new"] += 1
        classified_items.append({
            "index": idx,
            "status": "NEW",
            "fingerprint": fingerprint,
            "candidate": candidate,
        })

    return {
        "counts": counts,
        "items": classified_items,
        "scope_kind": "unverified",
        "scope_verified": False,
        "source_account_scope": "unverified",
        "destination_account": {
            "id": destination_account.get("id"),
            "broker": destination_broker,
            "account_name": destination_account_name,
            "owner": destination_owner,
        },
    }
