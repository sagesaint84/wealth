"""Pure mapping and duplicate classification of Korea Investment & Securities (KIS) realized profit rows.

This module deliberately does not persist records or mutate state.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

KIS_BROKER = "한국투자증권"
_SUPPORTED_MARKETS = frozenset({"kr", "us"})
_FINGERPRINT_PREFIX = "kis-realized:v1:"
_FINGERPRINT_RE = re.compile(r"^kis-realized:v1:[0-9a-f]{64}$")


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
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError(f"{field} must be a finite number")
        return value
    if isinstance(value, str):
        clean = value.strip().replace(",", "")
        if not clean:
            if allow_none:
                return None
            raise ValueError(f"{field} must be a finite number")
        try:
            num = float(clean)
            if not math.isfinite(num):
                raise ValueError(f"{field} must be a finite number")
            return int(clean) if (clean.isdigit() or (clean.startswith("-") and clean[1:].isdigit())) else num
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{field} must be a finite number") from exc
    raise ValueError(f"{field} must be a finite number")


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


def _format_date(raw: Any) -> str:
    text = str(raw or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _fingerprint_identity(candidate: Mapping[str, Any]) -> tuple[list[str | int | None], tuple[str, str, str, str]]:
    if not isinstance(candidate, Mapping):
        raise ValueError("candidate must be a mapping")
    if candidate.get("source") != "kis":
        raise ValueError("candidate source must be kis")
    account_key = _require_text(
        candidate.get("source_account_key") or candidate.get("source_account_scope"),
        "source_account_key",
    )
    date = _require_text(candidate.get("date"), "date")
    meta = candidate.get("source_meta")
    if not isinstance(meta, Mapping):
        raise ValueError("source_meta must be a mapping")
    market_type = _require_text(meta.get("market_type"), "source_meta.market_type").strip().lower()
    if market_type not in _SUPPORTED_MARKETS:
        raise ValueError(f"unsupported source_meta.market_type: {market_type}")
    product_code = _require_text(meta.get("product_code"), "source_meta.product_code")
    quantity = _canonical_number(meta.get("quantity"), "source_meta.quantity")
    pnl = _canonical_number(candidate.get("pnl"), "pnl")
    pnl_krw = _canonical_number(candidate.get("pnl_krw"), "pnl_krw", allow_none=True)
    buy_amount = _canonical_number(meta.get("buy_amount") if meta.get("buy_amount") is not None else meta.get("foreign_buy_amount"), "buy_amount", allow_none=True)
    sell_amount = _canonical_number(meta.get("sell_amount") if meta.get("sell_amount") is not None else meta.get("foreign_sell_amount"), "sell_amount", allow_none=True)

    payload: list[str | int | None] = [
        "kis-realized", 1, account_key, date, market_type, product_code, quantity,
        pnl, pnl_krw, buy_amount, sell_amount,
    ]
    return payload, (account_key, date, market_type, product_code)


def build_kis_realized_fingerprint(candidate: Mapping[str, Any]) -> str:
    """Build a deterministic v1 fingerprint for a KIS realized PnL candidate."""
    payload, _ = _fingerprint_identity(candidate)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _FINGERPRINT_PREFIX + hashlib.sha256(encoded).hexdigest()


def _is_trusted_fingerprint(value: Any) -> bool:
    return isinstance(value, str) and _FINGERPRINT_RE.fullmatch(value) is not None


def map_kis_domestic_profit_row(
    row: Mapping[str, Any],
    *,
    account_name: str,
    source_account_key: str = "",
    source_account_label: str = "",
    owner: str,
    fetched_at: str,
    broker: str = KIS_BROKER,
    source_account_scope: str | None = None,
) -> dict[str, Any]:
    """Map one KIS domestic profit row (TTTC8715R) to an unstored import candidate."""
    if not isinstance(row, Mapping):
        raise ValueError("row must be a mapping")

    raw_date = row.get("trad_dt") or row.get("date")
    date_val = _format_date(raw_date)
    if not date_val:
        raise ValueError("MISSING_DATE")

    code_raw = row.get("pdno") or row.get("stck_shrn_iscd") or row.get("code")
    if not code_raw or not str(code_raw).strip():
        raise ValueError("MISSING_CODE")
    code = str(code_raw).strip()

    name_raw = row.get("prdt_name") or row.get("name")
    if not name_raw or not str(name_raw).strip():
        raise ValueError("MISSING_NAME")
    name = str(name_raw).strip()

    qty_raw = row.get("sll_qty") if row.get("sll_qty") is not None else row.get("quantity")
    if qty_raw is None or str(qty_raw).strip() == "":
        raise ValueError("MISSING_QUANTITY")
    try:
        qty = _finite_number(qty_raw, "quantity")
    except Exception:
        raise ValueError("NUMERIC_PARSE_ERROR")

    sll_amt_raw = row.get("sll_amt") if row.get("sll_amt") is not None else row.get("sell_amount")
    if sll_amt_raw is None or str(sll_amt_raw).strip() == "":
        raise ValueError("MISSING_SELL_AMOUNT")
    try:
        sll_amt = _finite_number(sll_amt_raw, "sell_amount")
    except Exception:
        raise ValueError("NUMERIC_PARSE_ERROR")

    # Official primary is buy_amt; fall back to buy_amount or legacy pchs_amt
    buy_amt_raw = None
    if row.get("buy_amt") is not None and str(row.get("buy_amt")).strip() != "":
        buy_amt_raw = row.get("buy_amt")
    elif row.get("buy_amount") is not None and str(row.get("buy_amount")).strip() != "":
        buy_amt_raw = row.get("buy_amount")
    elif row.get("pchs_amt") is not None and str(row.get("pchs_amt")).strip() != "":
        buy_amt_raw = row.get("pchs_amt")

    if buy_amt_raw is None:
        raise ValueError("MISSING_BUY_AMOUNT")
    try:
        buy_amt = _finite_number(buy_amt_raw, "buy_amount")
    except Exception:
        raise ValueError("NUMERIC_PARSE_ERROR")

    pnl_raw = None
    if row.get("rlzt_pfls") is not None and str(row.get("rlzt_pfls")).strip() != "":
        pnl_raw = row.get("rlzt_pfls")
    elif row.get("profit_loss") is not None and str(row.get("profit_loss")).strip() != "":
        pnl_raw = row.get("profit_loss")
    elif row.get("rlzt_pl") is not None and str(row.get("rlzt_pl")).strip() != "":
        pnl_raw = row.get("rlzt_pl")

    if pnl_raw is None:
        raise ValueError("MISSING_REALIZED_PNL")
    try:
        pnl = _finite_number(pnl_raw, "profit_loss")
    except Exception:
        raise ValueError("NUMERIC_PARSE_ERROR")

    rate_raw = row.get("pfls_rt") if row.get("pfls_rt") is not None else (row.get("profit_rate") if row.get("profit_rate") is not None else row.get("erng_rt"))
    rate = _finite_number(rate_raw, "profit_rate", allow_none=True)
    fee = _finite_number(row.get("fee"), "fee", allow_none=True)
    tax = _finite_number(row.get("tl_tax") if row.get("tl_tax") is not None else row.get("tax"), "tax", allow_none=True)

    key = _require_text(source_account_key or source_account_scope, "source_account_key")
    label = str(source_account_label or "").strip()
    display_account_name = _require_text(account_name, "account_name", allow_empty=True)
    mapped_owner = _require_text(owner, "owner")
    source_fetched_at = _require_text(fetched_at, "fetched_at")

    return {
        "date": date_val,
        "code": code,
        "name": name,
        "asset_type": "stock",
        "currency": "KRW",
        "pnl": pnl,
        "fx_rate": None,
        "fx_pnl_krw": None,
        "pnl_krw": pnl,
        "is_ipo": False,
        "owner": mapped_owner,
        "broker": broker or KIS_BROKER,
        "account_name": display_account_name,
        "memo": "",
        "source": "kis",
        "source_account_key": key,
        "source_account_label": label,
        "source_account_scope": f"kis:{key}",
        "source_scope_verified": True,
        "source_meta": {
            "market_type": "kr",
            "product_code": code,
            "quantity": qty,
            "sell_amount": sll_amt,
            "buy_amount": buy_amt,
            "profit_loss": pnl,
            "profit_rate": rate,
            "fee": fee,
            "tax": tax,
            "fetched_at": source_fetched_at,
        },
    }


def map_kis_overseas_profit_row(
    row: Mapping[str, Any],
    *,
    account_name: str,
    source_account_key: str = "",
    source_account_label: str = "",
    owner: str,
    fetched_at: str,
    broker: str = KIS_BROKER,
    source_account_scope: str | None = None,
) -> dict[str, Any]:
    """Map one KIS overseas profit row (TTTS3039R) to an unstored import candidate."""
    if not isinstance(row, Mapping):
        raise ValueError("row must be a mapping")

    raw_date = row.get("trad_day") or row.get("trad_dt") or row.get("date")
    date_val = _format_date(raw_date)
    if not date_val:
        raise ValueError("date is required")

    code = _require_text(row.get("ovrs_pdno") or row.get("pdno") or row.get("code"), "code")
    name = _require_text(row.get("ovrs_item_name") or row.get("item_name") or row.get("prdt_name") or row.get("name") or code, "name")
    qty = _finite_number(row.get("slcl_qty") if row.get("slcl_qty") is not None else (row.get("sll_qty") if row.get("sll_qty") is not None else row.get("quantity")), "quantity")
    sll_amt = _finite_number(row.get("frcr_sll_amt_smtl1") if row.get("frcr_sll_amt_smtl1") is not None else (row.get("sll_amt") if row.get("sll_amt") is not None else row.get("foreign_sell_amount")), "foreign_sell_amount")
    buy_amt = _finite_number(row.get("frcr_pchs_amt1") if row.get("frcr_pchs_amt1") is not None else (row.get("buy_amt") if row.get("buy_amt") is not None else row.get("foreign_buy_amount")), "foreign_buy_amount")
    pnl = _finite_number(row.get("ovrs_rlzt_pfls_amt") if row.get("ovrs_rlzt_pfls_amt") is not None else (row.get("rlzt_pfls") if row.get("rlzt_pfls") is not None else (row.get("foreign_profit_loss") if row.get("foreign_profit_loss") is not None else row.get("profit_loss"))), "foreign_profit_loss")

    exrt_val = row.get("bass_exrt") if row.get("bass_exrt") is not None else (row.get("exrt") if row.get("exrt") is not None else (row.get("frst_bltn_exrt") if row.get("frst_bltn_exrt") is not None else row.get("fx_rate")))
    fx_rate = float(exrt_val) if exrt_val not in (None, "", 0, "0") else None

    won_sell = float(row.get("stck_sll_amt_smtl") or 0.0)
    won_buy = float(row.get("stck_buy_amt_smtl") or 0.0)
    if won_sell > 0 and won_buy > 0:
        won_pnl = round(won_sell - won_buy, 2)
    elif "profit_loss_krw" in row and row["profit_loss_krw"] is not None:
        won_pnl = float(row["profit_loss_krw"])
    elif fx_rate is not None and fx_rate > 0:
        won_pnl = round(pnl * fx_rate, 2)
    else:
        won_pnl = None

    rate = _finite_number(row.get("pftrt") if row.get("pftrt") is not None else (row.get("rlzt_erng_rt") if row.get("rlzt_erng_rt") is not None else row.get("profit_rate")), "profit_rate", allow_none=True)
    currency = str(row.get("crcy_cd") or row.get("foreign_currency") or row.get("currency") or "USD").strip() or "USD"

    key = _require_text(source_account_key or source_account_scope, "source_account_key")
    label = str(source_account_label or "").strip()
    display_account_name = _require_text(account_name, "account_name", allow_empty=True)
    mapped_owner = _require_text(owner, "owner")
    source_fetched_at = _require_text(fetched_at, "fetched_at")

    return {
        "date": date_val,
        "code": code,
        "name": name,
        "asset_type": "stock",
        "currency": currency,
        "pnl": pnl,
        "fx_rate": fx_rate,
        "fx_pnl_krw": None,
        "pnl_krw": won_pnl,
        "is_ipo": False,
        "owner": mapped_owner,
        "broker": broker or KIS_BROKER,
        "account_name": display_account_name,
        "memo": "",
        "source": "kis",
        "source_account_key": key,
        "source_account_label": label,
        "source_account_scope": f"kis:{key}",
        "source_scope_verified": True,
        "source_meta": {
            "market_type": "us",
            "product_code": code,
            "quantity": qty,
            "foreign_currency": currency,
            "foreign_sell_amount": sll_amt,
            "foreign_buy_amount": buy_amt,
            "foreign_profit_loss": pnl,
            "profit_rate": rate,
            "fx_rate": fx_rate,
            "exchange_code": str(row.get("ovrs_excg_cd") or "").strip(),
            "fetched_at": source_fetched_at,
        },
    }


def preview_kis_realized_selection(
    selected_items: list[Mapping[str, Any]],
    destination_account: Mapping[str, Any],
    existing_records: Iterable[Mapping[str, Any]],
    *,
    user_id: str,
    source_account_key: str = "",
    source_account_label: str = "",
    market: str = "kr",
    source_account_scope: str | None = None,
) -> dict[str, Any]:
    """Classify user-selected KIS rows for import into a chosen Wealth account.

    Zero financial writes. Enforces row token integrity and verifies opaque account key.
    """
    from app.services.kis_feed import verify_kis_feed_row_token

    destination_account_name = str(
        destination_account.get("account_name") or destination_account.get("name") or ""
    ).strip()
    destination_broker = str(destination_account.get("broker") or KIS_BROKER).strip()
    destination_owner = str(destination_account.get("owner") or "모두").strip()

    key = str(source_account_key or source_account_scope or "").strip()

    existing_list = list(existing_records)
    existing_kis_counts: Counter[str] = Counter()
    for rec in existing_list:
        if isinstance(rec, Mapping) and rec.get("source") == "kis":
            fp = rec.get("source_fingerprint")
            if fp and _is_trusted_fingerprint(fp):
                existing_kis_counts[fp] += 1

    assigned_kis_counts: Counter[str] = Counter()
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

        valid, err_code = verify_kis_feed_row_token(
            row, token, user_id=user_id, expected_account_key=key
        )
        if not valid:
            counts["invalid"] += 1
            classified_items.append({
                "index": idx,
                "status": "INVALID",
                "reason": err_code or "TOKEN_INVALID",
                "candidate": None,
                "row": row if isinstance(row, Mapping) else None,
            })
            continue

        row_market = str(row.get("market_type") or market).lower().strip()
        if row_market not in ("kr", "us"):
            row_market = "kr" if market in ("kr", "domestic") else "us"

        try:
            if row_market == "kr":
                candidate = map_kis_domestic_profit_row(
                    row,
                    account_name=destination_account_name,
                    source_account_key=key,
                    source_account_label=source_account_label,
                    owner=destination_owner,
                    fetched_at=str(row.get("fetched_at") or "unspecified"),
                    broker=destination_broker or KIS_BROKER,
                )
            else:
                candidate = map_kis_overseas_profit_row(
                    row,
                    account_name=destination_account_name,
                    source_account_key=key,
                    source_account_label=source_account_label,
                    owner=destination_owner,
                    fetched_at=str(row.get("fetched_at") or "unspecified"),
                    broker=destination_broker or KIS_BROKER,
                )
            fingerprint = build_kis_realized_fingerprint(candidate)
            candidate["source_fingerprint"] = fingerprint
        except (ValueError, TypeError, KeyError) as exc:
            err_msg = str(exc).strip()
            safe_reason = "MAPPING_INVALID"
            for code_cand in (
                "MISSING_DATE", "MISSING_CODE", "MISSING_NAME",
                "MISSING_QUANTITY", "MISSING_BUY_AMOUNT",
                "MISSING_SELL_AMOUNT", "MISSING_REALIZED_PNL",
                "NUMERIC_PARSE_ERROR",
            ):
                if code_cand in err_msg:
                    safe_reason = code_cand
                    break
            counts["invalid"] += 1
            classified_items.append({
                "index": idx,
                "status": "INVALID",
                "reason": safe_reason,
                "candidate": None,
                "row": row if isinstance(row, Mapping) else None,
            })
            continue

        # Exact KIS duplicate check
        if assigned_kis_counts[fingerprint] < existing_kis_counts[fingerprint]:
            assigned_kis_counts[fingerprint] += 1
            counts["already_imported"] += 1
            classified_items.append({
                "index": idx,
                "status": "ALREADY_IMPORTED",
                "reason": "EXACT_KIS_FINGERPRINT_MATCH",
                "fingerprint": fingerprint,
                "candidate": candidate,
            })
            continue

        # Collision / duplicate check against manual or other broker records
        cand_date = candidate.get("date")
        cand_code = candidate.get("code")
        cand_name = candidate.get("name")
        cand_pnl = float(candidate.get("pnl", 0.0))
        cand_pnl_krw = float(candidate.get("pnl_krw", 0.0) if candidate.get("pnl_krw") is not None else 0.0)

        manual_match = None
        for rec in existing_list:
            if not isinstance(rec, Mapping) or rec.get("source") == "kis":
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
        "scope_kind": "verified",
        "scope_verified": True,
        "source_account_key": key,
        "source_account_label": source_account_label,
        "source_account_scope": f"kis:{key}",
        "destination_account": {
            "id": destination_account.get("id"),
            "broker": destination_broker,
            "account_name": destination_account_name,
            "owner": destination_owner,
        },
    }
