"""Pure canonical projection and row integrity helpers for KB Securities realized-P/L feeds."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
from typing import Any, Mapping

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


KB_ROW_SELECTION_SALT = "kb-row-selection-v1"
KB_ROW_SELECTION_MAX_AGE_SECONDS = 86400
KB_PREVIEW_TICKET_SALT = "kb-preview-ticket-v1"
KB_PREVIEW_TICKET_MAX_AGE_SECONDS = 900


class KBFeedError(ValueError):
    pass


_NUMERIC_FIELDS = {
    "quantity", "buy_unit_price", "buy_amount", "sell_unit_price", "sell_amount",
    "pnl", "pnl_krw", "profit_rate", "fee", "tax", "expenses_total", "fx_rate",
}
_IDENTITY_FIELDS = {"canonical_hash", "source_occurrence", "future_identity"}


def _secret() -> str:
    from app.services.system_secrets import resolve_application_secret
    return resolve_application_secret()


def canonical_kb_number(value: Any) -> str:
    """Return lossless finite Decimal text without binary-float expansion; missing values are rejected."""
    if value is None or isinstance(value, bool):
        raise KBFeedError("MISSING_OR_INVALID_NUMERIC_VALUE")
    text = str(value).replace(",", "").strip()
    if not text:
        raise KBFeedError("MISSING_OR_INVALID_NUMERIC_VALUE")
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise KBFeedError("MISSING_OR_INVALID_NUMERIC_VALUE") from exc
    if not number.is_finite():
        raise KBFeedError("NON_FINITE_NUMERIC_VALUE")
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
        raise KBFeedError(f"MISSING_{field.upper()}")
    return text


def _date(row: Mapping[str, Any], field: str) -> str:
    text = _required_text(row, field)
    try:
        parsed = datetime.strptime(text, "%Y%m%d")
    except ValueError as exc:
        raise KBFeedError("INVALID_DATE") from exc
    if parsed.strftime("%Y%m%d") != text:
        raise KBFeedError("INVALID_DATE")
    return text


def project_kb_domestic_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project one official KB SSQM2442 Record1 row into Wealth canonical format."""
    if not isinstance(row, Mapping):
        raise KBFeedError("INVALID_PROVIDER_ROW")

    # Authoritative date
    date = _date(row, "trd_dt")

    # Authoritative stock code (strip leading 'A' if 7-character KR ticker e.g. A005930)
    raw_code = _required_text(row, "shrt_is_cd")
    code = raw_code[1:] if re.fullmatch(r"A\d{6}", raw_code) else raw_code

    # Authoritative stock name
    name = _required_text(row, "is_nm")

    # Authoritative lossless quantity from dtls_ccls_q (String(23))
    quantity = canonical_kb_number(row.get("dtls_ccls_q"))

    # Direct prices and amounts
    buy_unit_price = canonical_kb_number(row.get("b_uprc"))
    buy_amount = canonical_kb_number(row.get("b_amt"))
    sell_unit_price = canonical_kb_number(row.get("ccls_uprc"))
    sell_amount = canonical_kb_number(row.get("s_amt"))

    # Authoritative provider realized P/L (netness unverified; retained as-is)
    pnl = canonical_kb_number(row.get("rlztn_pl"))

    # Authoritative profit rate from yld (String(9))
    profit_rate = canonical_kb_number(row.get("yld"))

    # Informational fee and tax breakdowns (NOT subtracted from pnl)
    fee = canonical_kb_number(row.get("fee"))
    tax = canonical_kb_number(row.get("svrl_tx"))

    return {
        "date": date,
        "market_type": "kr",
        "code": code,
        "name": name,
        "quantity": quantity,
        "buy_unit_price": buy_unit_price,
        "buy_amount": buy_amount,
        "sell_unit_price": sell_unit_price,
        "sell_amount": sell_amount,
        "pnl": pnl,
        "pnl_krw": pnl,
        "profit_rate": profit_rate,
        "fee": fee,
        "tax": tax,
        "expenses_total": None,
        "currency": "KRW",
        "fx_rate": None,
        "country": "KR",
        "exchange": None,
        "source_meta": {
            "api_id": "SSQM2442",
            "pnl_netness": "PROVIDER_AUTHORITATIVE_UNVERIFIED",
            "dcml_dl_f": str(row.get("dcml_dl_f") or "0").strip(),
            "trd_dl_ccd": str(row.get("trd_dl_ccd") or "").strip(),
            "crdt_typ_cd": str(row.get("crdt_typ_cd") or "").strip(),
        },
    }


def is_realized_sale_row(row: Mapping[str, Any]) -> tuple[bool, str | None]:
    """Classify whether a raw KB Record1 row represents a realized sale event.

    Projection rule:
    1. Require the official sell transaction direction code (trd_dl_ccd == '01').
       Buy rows (02) and missing/unknown direction codes are not realizations.
    2. Check for finite required realization fields: s_amt, b_amt, dtls_ccls_q.
    3. Check s_amt > 0 (positive gross sales proceeds):
       - If s_amt > 0, quantity > 0, buy_amount >= 0: Valid realized sale.
       - Even if rlztn_pl == 0 (zero profit), this is a valid realization.
    4. If s_amt == 0 and b_amt > 0:
       - This is a buy/non-realization row (e.g. pending buy position row like the JSON sample).
       - Explicitly excluded: (False, 'NON_REALIZATION_BUY_ROW').
    5. If s_amt == 0 and b_amt == 0:
       - Ambiguous row (zero proceeds, zero cost basis).
       - Fail closed: (False, 'AMBIGUOUS_REALIZATION_ROW').
    """
    if not isinstance(row, Mapping):
        return False, "INVALID_PROVIDER_ROW"

    trade_direction = str(row.get("trd_dl_ccd") or "").strip()
    if trade_direction == "02":
        return False, "NON_REALIZATION_BUY_ROW"
    if trade_direction != "01":
        return False, "AMBIGUOUS_TRADE_DIRECTION"

    # Validate essential financial fields are present and valid numbers
    try:
        s_amt = Decimal(str(row.get("s_amt", "")).replace(",", "").strip())
        b_amt = Decimal(str(row.get("b_amt", "")).replace(",", "").strip())
        qty = Decimal(str(row.get("dtls_ccls_q", "")).replace(",", "").strip())
    except (InvalidOperation, TypeError, ValueError):
        return False, "MISSING_OR_INVALID_NUMERIC_VALUE"

    if not all(value.is_finite() for value in (s_amt, b_amt, qty)):
        return False, "NON_FINITE_NUMERIC_VALUE"

    if qty <= 0:
        return False, "NON_POSITIVE_QUANTITY"

    if s_amt > 0 and b_amt >= 0:
        return True, None

    if s_amt == 0 and b_amt > 0:
        return False, "NON_REALIZATION_BUY_ROW"

    if s_amt == 0 and b_amt == 0:
        return False, "AMBIGUOUS_REALIZATION_ROW"

    return False, "AMBIGUOUS_REALIZATION_ROW"


def canonical_kb_row_hash(row: Mapping[str, Any]) -> str:
    """Hash the full canonical row, excluding only derived identity annotations."""
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key in _IDENTITY_FIELDS:
            continue
        normalized[key] = canonical_kb_number(value) if key in _NUMERIC_FIELDS and value is not None else value
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _future_identity(source_account_key: str, row_hash: str, occurrence: int) -> str:
    payload = ["kb-realized:v1", source_account_key, row_hash, occurrence]
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return "kb-realized:v1:" + hashlib.sha256(encoded).hexdigest()


def sign_kb_feed_row(
    row: Mapping[str, Any], *, user_id: str, source_account_key: str, market: str,
) -> str:
    occurrence = row.get("source_occurrence")
    if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
        raise KBFeedError("INVALID_OCCURRENCE")
    payload = {
        "v": 1, "source": "kb", "user_id": str(user_id),
        "source_account_key": str(source_account_key), "market": market,
        "row_hash": canonical_kb_row_hash(row), "occurrence": occurrence,
    }
    return URLSafeTimedSerializer(_secret()).dumps(payload, salt=KB_ROW_SELECTION_SALT)


def verify_kb_feed_row(
    row: Mapping[str, Any], token: str, *, user_id: str,
    source_account_key: str, market: str,
) -> tuple[bool, str | None]:
    try:
        data = URLSafeTimedSerializer(_secret()).loads(
            token, salt=KB_ROW_SELECTION_SALT,
            max_age=KB_ROW_SELECTION_MAX_AGE_SECONDS,
        )
    except SignatureExpired:
        return False, "TOKEN_EXPIRED"
    except (BadSignature, Exception):
        return False, "TOKEN_INVALID"
    if not isinstance(data, dict) or data.get("v") != 1 or data.get("source") != "kb":
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
        row_hash = canonical_kb_row_hash(row)
    except (KBFeedError, TypeError, ValueError):
        return False, "NUMERIC_PARSE_ERROR"
    if data.get("row_hash") != row_hash:
        return False, "ROW_TAMPERED"
    if row.get("canonical_hash") not in (None, row_hash):
        return False, "ROW_TAMPERED"
    if row.get("future_identity") not in (None, _future_identity(source_account_key, row_hash, occurrence)):
        return False, "ROW_TAMPERED"
    return True, None


def compute_kb_items_hash(selected_items: list[Mapping[str, Any]]) -> str:
    """Bind a ticket to the exact selected multiset, including occurrence identity."""
    values: list[str] = []
    for item in selected_items:
        row = item.get("row") if isinstance(item, Mapping) else None
        token = item.get("selection_token") if isinstance(item, Mapping) else None
        if isinstance(row, Mapping) and isinstance(token, str):
            try:
                row_hash = canonical_kb_row_hash(row)
                occurrence = row.get("source_occurrence")
                if not isinstance(occurrence, int) or isinstance(occurrence, bool) or occurrence < 1:
                    raise KBFeedError("INVALID_OCCURRENCE")
                values.append(f"{row_hash}:{occurrence}:{token}")
            except (KBFeedError, TypeError, ValueError):
                raw = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
                values.append("invalid:" + hashlib.sha256(raw.encode("utf-8")).hexdigest() + ":" + token)
        else:
            raw = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
            values.append("invalid-item:" + hashlib.sha256(raw.encode("utf-8")).hexdigest())
    return hashlib.sha256(json.dumps(sorted(values), separators=(",", ":")).encode("utf-8")).hexdigest()


def sign_kb_import_preview_ticket(
    *, account_id: str, items_hash: str, user_id: str,
    source_account_key: str, market: str,
) -> str:
    payload = {
        "v": 1, "source": "kb", "account_id": str(account_id),
        "items_hash": str(items_hash), "user_id": str(user_id),
        "source_account_key": str(source_account_key), "market": market,
    }
    return URLSafeTimedSerializer(_secret()).dumps(payload, salt=KB_PREVIEW_TICKET_SALT)


def verify_kb_import_preview_ticket(
    ticket: str, *, account_id: str, items_hash: str, user_id: str,
    source_account_key: str, market: str,
) -> tuple[bool, str | None]:
    try:
        data = URLSafeTimedSerializer(_secret()).loads(
            ticket, salt=KB_PREVIEW_TICKET_SALT,
            max_age=KB_PREVIEW_TICKET_MAX_AGE_SECONDS,
        )
    except SignatureExpired:
        return False, "PREVIEW_TICKET_EXPIRED"
    except (BadSignature, Exception):
        return False, "PREVIEW_TICKET_INVALID"
    if not isinstance(data, dict) or data.get("v") != 1 or data.get("source") != "kb":
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


def build_kb_realized_feed(
    raw_rows: list[Mapping[str, Any]], *, market: str = "kr",
    source_account_key: str, source_account_label: str, user_id: str,
) -> dict[str, Any]:
    """Build an order-independent transient feed with multiset occurrence identity.

    Only rows that are verified realized sales are included as canonical candidates.
    Buy/non-realization rows and ambiguous rows are excluded with audit reasons.
    """
    if market != "kr":
        raise KBFeedError("KB Securities realized P/L only supports domestic market (kr)")

    from collections import defaultdict
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    excluded_rows: list[dict[str, Any]] = []

    for raw_row in raw_rows:
        is_sale, reason = is_realized_sale_row(raw_row)
        if not is_sale:
            excluded_rows.append({"reason": reason, "raw": dict(raw_row)})
            continue
        canonical = project_kb_domestic_row(raw_row)
        groups[canonical_kb_row_hash(canonical)].append(canonical)

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
        "source": "kb",
        "kind": "realized_pnl_feed",
        "read_only": True,
        "persisted": False,
        "included_in_accounting_totals": False,
        "source_scope_verified": False,
        "market": market,
        "source_account_key": source_account_key,
        "source_account_label": source_account_label,
        "state": "ok" if rows else "empty",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
        "excluded_rows_count": len(excluded_rows),
        "selection_tokens": [
            sign_kb_feed_row(
                row, user_id=user_id, source_account_key=source_account_key, market=market,
            )
            for row in rows
        ],
    }
