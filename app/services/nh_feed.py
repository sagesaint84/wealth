"""Pure, transient NH realized-P/L feed projection and row integrity helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from collections import Counter
from typing import Any, Mapping

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

NH_ROW_SELECTION_SALT = "nh-row-selection-v1"
NH_ROW_SELECTION_MAX_AGE_SECONDS = 86400
NH_PREVIEW_TICKET_SALT = "nh-preview-ticket-v1"
NH_PREVIEW_TICKET_MAX_AGE_SECONDS = 900


def _secret() -> str:
    value = os.getenv("DASHBOARD_SECRET_KEY", "").strip()
    if value:
        return value
    if os.getenv("WEALTH_ENV", "").lower() == "test":
        return os.getenv("WEALTH_TEST_SIGNING_SECRET", "wealth_synthetic_test_secret_for_nh")
    raise RuntimeError("DASHBOARD_SECRET_KEY is required for NH integrity signing")


def _canonical_num(value: Any) -> str | None:
    """Return lossless finite decimal text without binary-float expansion."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a financial number")
    text = str(value).replace(",", "").strip()
    if not text:
        raise ValueError("empty financial number")
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid financial number") from exc
    if not parsed.is_finite():
        raise ValueError("non-finite financial number")
    if parsed == 0:
        return "0"
    normalized = format(parsed, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _num(value: Any) -> str | None:
    """Project provider numbers as canonical JSON-safe decimal strings."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return _canonical_num(value)
    except ValueError:
        return None


def project_nh_row(row: Mapping[str, Any], market: str) -> dict[str, Any]:
    """Project official NH fields once; missing financial values remain ``None``."""
    if market == "kr":
        date = str(row.get("_wealth_date_context") or "").strip()
        return {
            "date": date, "market_type": "kr", "code": str(row.get("iem_cd") or "").strip(),
            "name": str(row.get("iem_nm") or "").strip(), "quantity": _num(row.get("sll_qty")),
            "buy_unit_price": _num(row.get("byn_uit_pr")), "buy_amount": _num(row.get("byn_amt")),
            "sell_unit_price": _num(row.get("sll_uit_pr")), "sell_amount": _num(row.get("sll_amt")),
            "pnl": _num(row.get("pls_amt")), "pnl_krw": _num(row.get("pls_amt")),
            "profit_rate": _num(row.get("pft_rt")), "fee": _num(row.get("fee_sum")),
            "tax": _num(row.get("tax_sum")), "expenses_total": None, "currency": "KRW",
            "classification": row.get("iem_mlf_cd"),
        }
    return {
        "date": str(row.get("_wealth_date_context") or "").strip(), "market_type": "us",
        "code": str(row.get("iem_cd") or "").strip(), "name": str(row.get("iem_nm") or "").strip(),
        "country": str(row.get("_wealth_country_context") or "").strip(),
        "currency": str(row.get("_wealth_currency_context") or "").strip(), "exchange": None,
        "quantity": _num(row.get("sll_qty")), "buy_unit_price": _num(row.get("byn_uit_pr")),
        "buy_amount": _num(row.get("fc_byn_amt1")), "sell_unit_price": _num(row.get("sll_uit_pr")),
        "sell_amount": _num(row.get("fc_sll_amt")), "pnl": _num(row.get("fc_rzt_pls")),
        "pnl_krw": None, "fx_rate": None, "profit_rate": _num(row.get("fc_rzt_pft_rt")),
        "fee": None, "tax": None, "expenses_total": _num(row.get("fc_sdr_xps")),
    }


def canonical_nh_row_hash(row: Mapping[str, Any]) -> str:
    """Hash the exact projected row with numeric spelling normalized."""
    normalized = {key: (_canonical_num(value) if key in {"quantity", "buy_unit_price", "buy_amount", "sell_unit_price", "sell_amount", "pnl", "pnl_krw", "profit_rate", "fee", "tax", "expenses_total", "fx_rate"} else value) for key, value in row.items()}
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def sign_nh_feed_row(row: Mapping[str, Any], *, user_id: str, source_account_key: str, market: str) -> str:
    payload = {"v": 1, "source": "nh", "user_id": str(user_id), "source_account_key": str(source_account_key), "market": market, "row_hash": canonical_nh_row_hash(row)}
    return URLSafeTimedSerializer(_secret()).dumps(payload, salt=NH_ROW_SELECTION_SALT)


def verify_nh_feed_row(row: Mapping[str, Any], token: str, *, user_id: str, source_account_key: str, market: str) -> tuple[bool, str | None]:
    try:
        data = URLSafeTimedSerializer(_secret()).loads(token, salt=NH_ROW_SELECTION_SALT, max_age=NH_ROW_SELECTION_MAX_AGE_SECONDS)
    except SignatureExpired:
        return False, "TOKEN_EXPIRED"
    except (BadSignature, Exception):
        return False, "TOKEN_INVALID"
    if not isinstance(data, dict) or data.get("source") != "nh":
        return False, "TOKEN_INVALID"
    if data.get("user_id") != str(user_id): return False, "USER_MISMATCH"
    if data.get("source_account_key") != str(source_account_key): return False, "SCOPE_MISMATCH"
    if data.get("market") != market: return False, "TOKEN_INVALID"
    try:
        row_hash = canonical_nh_row_hash(row)
    except ValueError:
        return False, "NUMERIC_PARSE_ERROR"
    if data.get("row_hash") != row_hash: return False, "ROW_TAMPERED"
    return True, None


def compute_nh_items_hash(selected_items: list[Mapping[str, Any]]) -> str:
    """Bind a preview to the exact selected canonical rows and their tokens."""
    values = []
    for item in selected_items:
        row = item.get("row") if isinstance(item, Mapping) else None
        token = item.get("selection_token") if isinstance(item, Mapping) else None
        if isinstance(row, Mapping) and isinstance(token, str):
            try:
                row_hash = canonical_nh_row_hash(row)
            except ValueError:
                raw = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
                row_hash = "invalid:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
            values.append(f"{row_hash}:{token}")
    return hashlib.sha256(json.dumps(sorted(values), separators=(",", ":")).encode("utf-8")).hexdigest()


def sign_nh_import_preview_ticket(*, account_id: str, items_hash: str, user_id: str, source_account_key: str, market: str) -> str:
    payload = {"v": 1, "source": "nh", "account_id": str(account_id), "items_hash": str(items_hash), "user_id": str(user_id), "source_account_key": str(source_account_key), "market": market}
    return URLSafeTimedSerializer(_secret()).dumps(payload, salt=NH_PREVIEW_TICKET_SALT)


def verify_nh_import_preview_ticket(ticket: str, *, account_id: str, items_hash: str, user_id: str, source_account_key: str, market: str) -> tuple[bool, str | None]:
    try:
        data = URLSafeTimedSerializer(_secret()).loads(ticket, salt=NH_PREVIEW_TICKET_SALT, max_age=NH_PREVIEW_TICKET_MAX_AGE_SECONDS)
    except SignatureExpired:
        return False, "PREVIEW_TICKET_EXPIRED"
    except (BadSignature, Exception):
        return False, "PREVIEW_TICKET_INVALID"
    if not isinstance(data, dict) or data.get("v") != 1 or data.get("source") != "nh": return False, "PREVIEW_TICKET_INVALID"
    if data.get("user_id") != str(user_id): return False, "USER_MISMATCH"
    if data.get("source_account_key") != str(source_account_key): return False, "SCOPE_MISMATCH"
    if data.get("account_id") != str(account_id): return False, "DESTINATION_ACCOUNT_CHANGED"
    if data.get("items_hash") != str(items_hash): return False, "ITEMS_TAMPERED"
    if data.get("market") != market: return False, "MARKET_MISMATCH"
    return True, None


def build_nh_realized_feed(rows_raw: list[Mapping[str, Any]], *, market: str, source_account_key: str, source_account_label: str, user_id: str) -> dict[str, Any]:
    rows = [project_nh_row(row, market) for row in rows_raw]
    occurrences: Counter[str] = Counter()
    for row in rows:
        base_hash = canonical_nh_row_hash(row)
        row["source_occurrence"] = occurrences[base_hash]
        occurrences[base_hash] += 1
    return {"source": "nh", "kind": "realized_pnl_feed", "source_scope_verified": True,
            "read_only": True, "persisted": False, "included_in_accounting_totals": False,
            "market": market, "source_account_label": source_account_label,
            "state": "ok" if rows else "empty", "fetched_at": datetime.now(timezone.utc).isoformat(),
            "rows": rows, "selection_tokens": [sign_nh_feed_row(row, user_id=user_id, source_account_key=source_account_key, market=market) for row in rows]}
