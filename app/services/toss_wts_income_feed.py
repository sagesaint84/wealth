"""Signed transient feed helpers for Toss WTS dividend/interest imports."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re
from typing import Any, Mapping

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ROW_SALT = "toss-wts-income-row-v1"
ROW_MAX_AGE_SECONDS = 86400
PREVIEW_SALT = "toss-wts-income-preview-v1"
PREVIEW_MAX_AGE_SECONDS = 900


def _serializer() -> URLSafeTimedSerializer:
    from app.services.system_secrets import resolve_application_secret
    return URLSafeTimedSerializer(resolve_application_secret())


def validate_income_feed_request(from_date: Any, to_date: Any) -> tuple[str, str]:
    if not isinstance(from_date, str) or not _DATE_RE.fullmatch(from_date):
        raise ValueError("from_date must be in YYYY-MM-DD format")
    if not isinstance(to_date, str) or not _DATE_RE.fullmatch(to_date):
        raise ValueError("to_date must be in YYYY-MM-DD format")
    try:
        parsed_from = date.fromisoformat(from_date)
        parsed_to = date.fromisoformat(to_date)
    except ValueError as exc:
        raise ValueError("invalid date") from exc
    if parsed_from > parsed_to:
        raise ValueError("from_date must be less than or equal to to_date")
    return from_date, to_date


def _canonical_number(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("invalid numeric value")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid numeric value") from exc
    if number.is_zero():
        return "0"
    text = format(number.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def canonical_income_row_hash(row: Mapping[str, Any]) -> str:
    if not isinstance(row, Mapping):
        raise ValueError("row must be an object")
    meta = row.get("source_meta")
    if not isinstance(meta, Mapping):
        raise ValueError("source_meta is required")
    composite = meta.get("composite_key")
    if not isinstance(composite, Mapping):
        raise ValueError("composite_key is required")
    payload = [
        str(row.get("market") or "").lower(),
        str(row.get("currency") or "").upper(),
        str(row.get("datetime") or ""),
        str(row.get("stock_name") or ""),
        _canonical_number(row.get("amount")),
        _canonical_number(row.get("adjusted_amount")),
        str(meta.get("summary_no") or ""),
        str(meta.get("trade_type_name") or ""),
        str(meta.get("transaction_type_code") or ""),
        str(meta.get("transaction_type_name") or ""),
        str(meta.get("stock_code") or ""),
        str(meta.get("stock_name") or ""),
        str(meta.get("product_name") or ""),
        _canonical_number(meta.get("provider_amount")),
        _canonical_number(meta.get("provider_adjusted_amount")),
        _canonical_number(meta.get("provider_tax_amount")),
        str(composite.get("date") or ""),
        composite.get("no"),
    ]
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sign_income_feed_row(row: Mapping[str, Any], *, user_id: str, generation_id: str | None) -> str:
    payload = {
        "v": 1,
        "source": "toss_wts",
        "kind": "income_row",
        "user_id": str(user_id),
        "generation_id": str(generation_id) if generation_id else None,
        "row_hash": canonical_income_row_hash(row),
    }
    return _serializer().dumps(payload, salt=ROW_SALT)


def verify_income_feed_row_token(
    row: Mapping[str, Any], token: str, *, user_id: str, current_generation_id: str | None
) -> tuple[bool, str | None]:
    if not isinstance(token, str) or not token.strip():
        return False, "TOKEN_MISSING"
    try:
        data = _serializer().loads(token, salt=ROW_SALT, max_age=ROW_MAX_AGE_SECONDS)
    except SignatureExpired:
        return False, "TOKEN_EXPIRED"
    except BadSignature:
        return False, "TOKEN_INVALID"
    except Exception:
        return False, "TOKEN_INVALID"
    if not isinstance(data, dict) or data.get("v") != 1 or data.get("kind") != "income_row":
        return False, "TOKEN_INVALID"
    if data.get("user_id") != str(user_id):
        return False, "USER_MISMATCH"
    if current_generation_id is not None and data.get("generation_id") is not None:
        if data.get("generation_id") != str(current_generation_id):
            return False, "RUNTIME_GENERATION_CHANGED"
    try:
        row_hash = canonical_income_row_hash(row)
    except ValueError:
        return False, "ROW_TAMPERED"
    if data.get("row_hash") != row_hash:
        return False, "ROW_TAMPERED"
    return True, None


def compute_income_items_hash(selected_items: list[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for item in selected_items:
        if not isinstance(item, Mapping):
            continue
        row = item.get("row", item)
        if not isinstance(row, Mapping):
            continue
        token = str(item.get("selection_token") or "")
        parts.append(f"{canonical_income_row_hash(row)}:{token}")
    encoded = json.dumps(sorted(parts), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sign_income_preview_ticket(
    *, account_id: str, items_hash: str, user_id: str, generation_id: str | None
) -> str:
    payload = {
        "v": 1,
        "account_id": str(account_id),
        "items_hash": str(items_hash),
        "user_id": str(user_id),
        "generation_id": str(generation_id) if generation_id else None,
    }
    return _serializer().dumps(payload, salt=PREVIEW_SALT)


def verify_income_preview_ticket(
    ticket: str,
    *,
    account_id: str,
    items_hash: str,
    user_id: str,
    current_generation_id: str | None,
) -> tuple[bool, str | None]:
    if not isinstance(ticket, str) or not ticket.strip():
        return False, "PREVIEW_TICKET_MISSING"
    try:
        data = _serializer().loads(ticket, salt=PREVIEW_SALT, max_age=PREVIEW_MAX_AGE_SECONDS)
    except SignatureExpired:
        return False, "PREVIEW_TICKET_EXPIRED"
    except BadSignature:
        return False, "PREVIEW_TICKET_INVALID"
    except Exception:
        return False, "PREVIEW_TICKET_INVALID"
    if not isinstance(data, dict) or data.get("v") != 1:
        return False, "PREVIEW_TICKET_INVALID"
    if data.get("user_id") != str(user_id):
        return False, "USER_MISMATCH"
    if data.get("account_id") != str(account_id):
        return False, "DESTINATION_ACCOUNT_CHANGED"
    if data.get("items_hash") != str(items_hash):
        return False, "ITEMS_TAMPERED"
    if current_generation_id is not None and data.get("generation_id") is not None:
        if data.get("generation_id") != str(current_generation_id):
            return False, "RUNTIME_GENERATION_CHANGED"
    return True, None
