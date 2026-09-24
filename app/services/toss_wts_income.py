"""Pure Toss WTS cash-ledger classification for dividend/interest imports."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from typing import Any, Mapping

_FINGERPRINT_PREFIX = "toss-wts-income:v1:"
_SUPPORTED_INCOME_TYPES = frozenset({"dividend", "distribution", "account_interest"})


def _finite_number(value: Any, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field} must be a finite number")
    return value


def _canonical_number(value: Any, field: str) -> str:
    number = _finite_number(value, field)
    try:
        decimal = Decimal(str(number))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if decimal.is_zero():
        return "0"
    text = format(decimal.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def classify_toss_wts_income_row(row: Mapping[str, Any]) -> str | None:
    if not isinstance(row, Mapping):
        return None
    market = str(row.get("market") or "").strip().lower()
    currency = str(row.get("currency") or "").strip().upper()
    meta = row.get("source_meta")
    if not isinstance(meta, Mapping):
        return None
    summary_no = str(meta.get("summary_no") or "").strip()
    trade_name = str(meta.get("trade_type_name") or "").strip()
    tx_code = str(meta.get("transaction_type_code") or "").strip()
    tx_name = str(meta.get("transaction_type_name") or "").strip()
    stock_code = str(meta.get("stock_code") or "").strip()
    if tx_code != "1" or tx_name != "입금":
        return None
    if market == "kr" and currency == "KRW":
        if summary_no == "1017" and trade_name == "이자입금" and not stock_code:
            return "account_interest"
        if summary_no == "1104" and trade_name == "배당금입금" and stock_code:
            return "dividend"
        if summary_no == "1117" and trade_name == "결산분배금입금" and stock_code:
            return "distribution"
        return None
    if market == "us" and currency == "USD":
        if summary_no == "1207" and stock_code:
            return "dividend"
        if summary_no == "1204" and not stock_code:
            return "account_interest"
    return None


def build_toss_wts_income_fingerprint(row: Mapping[str, Any]) -> str:
    income_type = classify_toss_wts_income_row(row)
    if income_type not in _SUPPORTED_INCOME_TYPES:
        raise ValueError("row is not supported income")
    meta = row["source_meta"]
    composite = meta.get("composite_key")
    if not isinstance(composite, Mapping):
        raise ValueError("composite key required")
    date_key = str(composite.get("date") or "").strip()
    no = composite.get("no")
    if not date_key or type(no) is not int:
        raise ValueError("invalid composite key")
    payload = [
        "toss-wts-income", 1,
        str(row.get("market") or "").strip().lower(),
        income_type,
        str(meta.get("summary_no") or "").strip(),
        date_key, no,
        str(meta.get("stock_code") or "").strip(),
        str(row.get("currency") or "").strip().upper(),
        _canonical_number(row.get("adjusted_amount"), "adjusted_amount"),
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _FINGERPRINT_PREFIX + hashlib.sha256(encoded).hexdigest()


def map_toss_wts_income_row(row: Mapping[str, Any]) -> dict[str, Any] | None:
    income_type = classify_toss_wts_income_row(row)
    if income_type is None:
        return None
    meta = row["source_meta"]
    dt = str(row.get("datetime") or "").strip()
    if len(dt) < 10:
        raise ValueError("datetime is invalid")
    adjusted = _finite_number(row.get("adjusted_amount"), "adjusted_amount")
    provider_amount = _finite_number(meta.get("provider_amount"), "provider_amount")
    tax = _finite_number(meta.get("provider_tax_amount"), "provider_tax_amount")
    if adjusted <= 0 or provider_amount <= 0 or tax < 0:
        raise ValueError("income amounts are invalid")
    market = str(row["market"]).lower()
    currency = str(row["currency"]).upper()
    stock_code = str(meta.get("stock_code") or "").strip()
    stock_name = str(meta.get("stock_name") or row.get("stock_name") or "").strip()
    product_name = str(meta.get("product_name") or "").strip()
    if income_type == "account_interest":
        code = ""
        name = "토스증권 예탁금 이자" if market == "kr" else "토스증권 외화예탁금 이용료"
    else:
        code = stock_code
        name = stock_name or product_name
        if not code or not name:
            raise ValueError("stock income requires stock identity")
    candidate = {
        "date": dt[:10],
        "code": code,
        "name": name,
        "currency": currency,
        "amount": adjusted,
        "income_type": income_type,
        "broker": "토스증권",
        "source": "toss_wts",
        "source_fingerprint": build_toss_wts_income_fingerprint(row),
        "source_meta": {
            "market": market,
            "summary_no": str(meta.get("summary_no") or ""),
            "trade_type_name": str(meta.get("trade_type_name") or ""),
            "transaction_type_code": str(meta.get("transaction_type_code") or ""),
            "composite_key": dict(meta["composite_key"]),
        },
    }
    if market == "kr" and abs(float(adjusted) - (float(provider_amount) - float(tax))) < 1e-9:
        candidate["gross_amount"] = provider_amount
        candidate["tax"] = tax
    return candidate


def map_toss_wts_income_rows(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    candidates = []
    ignored = 0
    invalid = 0
    for row in rows:
        try:
            candidate = map_toss_wts_income_row(row)
        except (TypeError, ValueError, KeyError):
            invalid += 1
            continue
        if candidate is None:
            ignored += 1
        else:
            candidates.append(candidate)
    return {
        "fetched": len(rows),
        "eligible": len(candidates),
        "ignored": ignored,
        "invalid": invalid,
        "candidates": candidates,
    }
