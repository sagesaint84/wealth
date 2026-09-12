"""Pure canonical projection for transient Kiwoom realized-P/L feeds."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
from typing import Any, Mapping

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


KIWOOM_ROW_SELECTION_SALT = "kiwoom-row-selection-v1"
KIWOOM_ROW_SELECTION_MAX_AGE_SECONDS = 86400
KIWOOM_PREVIEW_TICKET_SALT = "kiwoom-preview-ticket-v1"
KIWOOM_PREVIEW_TICKET_MAX_AGE_SECONDS = 900


class KiwoomFeedError(ValueError):
    pass


_NUMERIC_FIELDS = {
    "quantity", "buy_unit_price", "buy_amount", "sell_unit_price", "sell_amount",
    "pnl", "pnl_krw", "profit_rate", "fee", "tax", "expenses_total", "fx_rate",
}
_IDENTITY_FIELDS = {"canonical_hash", "source_occurrence", "future_identity"}


def _secret() -> str:
    value = os.getenv("DASHBOARD_SECRET_KEY", "").strip()
    if value:
        return value
    if os.getenv("WEALTH_ENV", "").lower() == "test":
        value = os.getenv("WEALTH_TEST_SIGNING_SECRET", "").strip()
        if value:
            return value
    raise RuntimeError("DASHBOARD_SECRET_KEY is required for Kiwoom integrity signing")


def canonical_kiwoom_number(value: Any) -> str:
    """Return lossless finite Decimal text; missing values are rejected."""
    if value is None or isinstance(value, bool):
        raise KiwoomFeedError("MISSING_OR_INVALID_NUMERIC_VALUE")
    text = str(value).replace(",", "").strip()
    if not text:
        raise KiwoomFeedError("MISSING_OR_INVALID_NUMERIC_VALUE")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise KiwoomFeedError("MISSING_OR_INVALID_NUMERIC_VALUE") from exc
    if not number.is_finite():
        raise KiwoomFeedError("NON_FINITE_NUMERIC_VALUE")
    if number == 0:
        return "0"
    normalized = format(number, "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return normalized


def _required_text(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    text = str(value).strip() if value is not None else ""
    if not text:
        raise KiwoomFeedError(f"MISSING_{field.upper()}")
    return text


def _date(row: Mapping[str, Any], field: str) -> str:
    text = _required_text(row, field)
    try:
        parsed = datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise KiwoomFeedError("INVALID_DATE") from exc
    if parsed.strftime("%Y%m%d") != text:
        raise KiwoomFeedError("INVALID_DATE")
    return text


def _multiply(left: str, right: str) -> str:
    return canonical_kiwoom_number(Decimal(left) * Decimal(right))


def project_kiwoom_row(row: Mapping[str, Any], market: str) -> dict[str, Any]:
    """Project one official provider row without retaining the raw response."""
    if not isinstance(row, Mapping):
        raise KiwoomFeedError("INVALID_PROVIDER_ROW")
    if market == "kr":
        quantity = canonical_kiwoom_number(row.get("cntr_qty"))
        buy_unit_price = canonical_kiwoom_number(row.get("buy_uv"))
        sell_unit_price = canonical_kiwoom_number(row.get("cntr_pric"))
        raw_code = _required_text(row, "stk_cd")
        code = raw_code[1:] if re.fullmatch(r"A\d{6}", raw_code) else raw_code
        pnl = canonical_kiwoom_number(row.get("tdy_sel_pl"))
        return {
            "date": _date(row, "dt"), "market_type": "kr", "code": code,
            "name": _required_text(row, "stk_nm"), "quantity": quantity,
            "buy_unit_price": buy_unit_price, "buy_amount": _multiply(quantity, buy_unit_price),
            "sell_unit_price": sell_unit_price, "sell_amount": _multiply(quantity, sell_unit_price),
            "pnl": pnl, "pnl_krw": pnl, "profit_rate": canonical_kiwoom_number(row.get("pl_rt")),
            "fee": canonical_kiwoom_number(row.get("tdy_trde_cmsn")),
            "tax": canonical_kiwoom_number(row.get("tdy_trde_tax")), "expenses_total": None,
            "currency": "KRW", "fx_rate": None, "country": "KR", "exchange": None,
            "source_meta": {"api_id": "ka10073", "buy_amount_semantics": "DERIVED", "sell_amount_semantics": "DERIVED"},
        }
    if market == "us":
        return {
            "date": _date(row, "sell_dt"), "market_type": "us",
            "code": _required_text(row, "stk_cd"), "name": _required_text(row, "frgn_stk_nm"),
            "quantity": canonical_kiwoom_number(row.get("sell_qty")),
            "buy_unit_price": canonical_kiwoom_number(row.get("avg_buy_uv")),
            "buy_amount": canonical_kiwoom_number(row.get("buy_amt")),
            "sell_unit_price": canonical_kiwoom_number(row.get("avg_sell_uv")),
            "sell_amount": canonical_kiwoom_number(row.get("sell_amt")),
            "pnl": canonical_kiwoom_number(row.get("pl_amt")), "pnl_krw": None,
            "profit_rate": canonical_kiwoom_number(row.get("pl_rt")), "fee": None, "tax": None,
            "expenses_total": canonical_kiwoom_number(row.get("cmsn_tax")), "currency": "USD",
            "fx_rate": None, "country": _required_text(row, "natn_nm"),
            "exchange": _required_text(row, "stex_nm"),
            "source_meta": {"api_id": "ust21530", "currency_basis": "foreign"},
        }
    raise KiwoomFeedError("INVALID_MARKET")


def canonical_kiwoom_row_hash(row: Mapping[str, Any]) -> str:
    """Hash the full canonical row, excluding only derived identity annotations."""
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key in _IDENTITY_FIELDS:
            continue
        normalized[key] = canonical_kiwoom_number(value) if key in _NUMERIC_FIELDS and value is not None else value
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _future_identity(source_account_key: str, row_hash: str, occurrence: int) -> str:
    payload = ["kiwoom-realized:v1", source_account_key, row_hash, occurrence]
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return "kiwoom-realized:v1:" + hashlib.sha256(encoded).hexdigest()


def sign_kiwoom_feed_row(
    row: Mapping[str, Any], *, user_id: str, source_account_key: str, market: str,
) -> str:
    occurrence = row.get("source_occurrence")
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
        raise KiwoomFeedError("INVALID_OCCURRENCE")
    payload = {
        "v": 1, "source": "kiwoom", "user_id": str(user_id),
        "source_account_key": str(source_account_key), "market": market,
        "row_hash": canonical_kiwoom_row_hash(row), "occurrence": occurrence,
    }
    return URLSafeTimedSerializer(_secret()).dumps(payload, salt=KIWOOM_ROW_SELECTION_SALT)


def verify_kiwoom_feed_row(
    row: Mapping[str, Any], token: str, *, user_id: str,
    source_account_key: str, market: str,
) -> tuple[bool, str | None]:
    try:
        data = URLSafeTimedSerializer(_secret()).loads(
            token, salt=KIWOOM_ROW_SELECTION_SALT,
            max_age=KIWOOM_ROW_SELECTION_MAX_AGE_SECONDS,
        )
    except SignatureExpired:
        return False, "TOKEN_EXPIRED"
    except (BadSignature, Exception):
        return False, "TOKEN_INVALID"
    if not isinstance(data, dict) or data.get("v") != 1 or data.get("source") != "kiwoom":
        return False, "TOKEN_INVALID"
    if data.get("user_id") != str(user_id):
        return False, "USER_MISMATCH"
    if data.get("source_account_key") != str(source_account_key):
        return False, "SCOPE_MISMATCH"
    if data.get("market") != market:
        return False, "MARKET_MISMATCH"
    occurrence = row.get("source_occurrence")
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
        return False, "INVALID_OCCURRENCE"
    if data.get("occurrence") != occurrence:
        return False, "ROW_TAMPERED"
    try:
        row_hash = canonical_kiwoom_row_hash(row)
    except (KiwoomFeedError, TypeError, ValueError):
        return False, "NUMERIC_PARSE_ERROR"
    if data.get("row_hash") != row_hash:
        return False, "ROW_TAMPERED"
    if row.get("canonical_hash") not in (None, row_hash):
        return False, "ROW_TAMPERED"
    if row.get("future_identity") not in (None, _future_identity(source_account_key, row_hash, occurrence)):
        return False, "ROW_TAMPERED"
    return True, None


def compute_kiwoom_items_hash(selected_items: list[Mapping[str, Any]]) -> str:
    """Bind a ticket to the exact selected multiset, including occurrence identity."""
    values: list[str] = []
    for item in selected_items:
        row = item.get("row") if isinstance(item, Mapping) else None
        token = item.get("selection_token") if isinstance(item, Mapping) else None
        if isinstance(row, Mapping) and isinstance(token, str):
            try:
                row_hash = canonical_kiwoom_row_hash(row)
                occurrence = row.get("source_occurrence")
                if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
                    raise KiwoomFeedError("INVALID_OCCURRENCE")
                values.append(f"{row_hash}:{occurrence}:{token}")
            except (KiwoomFeedError, TypeError, ValueError):
                raw = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
                values.append("invalid:" + hashlib.sha256(raw.encode("utf-8")).hexdigest() + ":" + token)
        else:
            raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
            values.append("invalid-item:" + hashlib.sha256(raw.encode("utf-8")).hexdigest())
    return hashlib.sha256(json.dumps(sorted(values), separators=(",", ":")).encode("utf-8")).hexdigest()


def sign_kiwoom_import_preview_ticket(
    *, account_id: str, items_hash: str, user_id: str,
    source_account_key: str, market: str,
) -> str:
    payload = {
        "v": 1, "source": "kiwoom", "account_id": str(account_id),
        "items_hash": str(items_hash), "user_id": str(user_id),
        "source_account_key": str(source_account_key), "market": market,
    }
    return URLSafeTimedSerializer(_secret()).dumps(payload, salt=KIWOOM_PREVIEW_TICKET_SALT)


def verify_kiwoom_import_preview_ticket(
    ticket: str, *, account_id: str, items_hash: str, user_id: str,
    source_account_key: str, market: str,
) -> tuple[bool, str | None]:
    try:
        data = URLSafeTimedSerializer(_secret()).loads(
            ticket, salt=KIWOOM_PREVIEW_TICKET_SALT,
            max_age=KIWOOM_PREVIEW_TICKET_MAX_AGE_SECONDS,
        )
    except SignatureExpired:
        return False, "PREVIEW_TICKET_EXPIRED"
    except (BadSignature, Exception):
        return False, "PREVIEW_TICKET_INVALID"
    if not isinstance(data, dict) or data.get("v") != 1 or data.get("source") != "kiwoom":
        return False, "PREVIEW_TICKET_INVALID"
    if data.get("user_id") != str(user_id):
        return False, "USER_MISMATCH"
    if data.get("source_account_key") != str(source_account_key):
        return False, "SCOPE_MISMATCH"
    if data.get("account_id") != str(account_id):
        return False, "DESTINATION_ACCOUNT_CHANGED"
    if data.get("items_hash") != str(items_hash):
        return False, "ITEMS_TAMPERED"
    if data.get("market") != market:
        return False, "MARKET_MISMATCH"
    return True, None


def build_kiwoom_realized_feed(
    raw_rows: list[Mapping[str, Any]], *, market: str,
    source_account_key: str, source_account_label: str, user_id: str,
) -> dict[str, Any]:
    """Build an order-independent transient feed with multiset occurrence identity."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_row in raw_rows:
        canonical = project_kiwoom_row(raw_row, market)
        groups[canonical_kiwoom_row_hash(canonical)].append(canonical)

    rows: list[dict[str, Any]] = []
    for row_hash in sorted(groups):
        representative = groups[row_hash][0]
        for occurrence in range(1, len(groups[row_hash]) + 1):
            item = dict(representative)
            item["canonical_hash"] = row_hash
            item["source_occurrence"] = occurrence
            item["future_identity"] = _future_identity(source_account_key, row_hash, occurrence)
            rows.append(item)

    return {
        "source": "kiwoom", "kind": "realized_pnl_feed", "read_only": True,
        "persisted": False, "included_in_accounting_totals": False,
        "source_scope_verified": False, "market": market,
        "source_account_key": source_account_key, "source_account_label": source_account_label,
        "state": "ok" if rows else "empty", "fetched_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "selection_tokens": [
            sign_kiwoom_feed_row(
                row, user_id=user_id, source_account_key=source_account_key, market=market,
            )
            for row in rows
        ],
    }
