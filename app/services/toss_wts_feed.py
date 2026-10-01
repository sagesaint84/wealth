"""Pure projection and response builder for Toss WTS realized profit feed.

This service is strictly read-only and transient. It does not persist records,
attribute accounts, or modify portfolio totals.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import os
import re
from typing import Any, Mapping
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.services.toss_wts_stock_code import canonicalize_toss_wts_stock_code

_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_RATE_BASES = frozenset({"KRW", "USD"})
ROW_SELECTION_SALT = "toss-wts-row-selection-v1"
ROW_SELECTION_MAX_AGE_SECONDS = 86400  # 24 hours


def _get_serializer() -> URLSafeTimedSerializer:
    from app.services.system_secrets import resolve_application_secret
    secret = resolve_application_secret()
    return URLSafeTimedSerializer(secret)


def canonical_row_hash(row: Mapping[str, Any]) -> str:
    """Compute deterministic hash of canonical row fields."""
    date_val = str(row.get("date", "")).strip()
    market_type = str(row.get("market_type", "")).strip().lower()
    product_code = str(row.get("product_code", "")).strip()
    name = str(row.get("name", "")).strip()
    quantity = row.get("quantity")
    profit_rate = row.get("profit_rate")
    profit_loss = row.get("profit_loss", {})
    buy_amount = row.get("buy_amount", {})
    sell_amount = row.get("sell_amount", {})

    payload = [
        date_val,
        market_type,
        product_code,
        name,
        float(quantity) if quantity is not None else None,
        float(profit_rate) if profit_rate is not None else None,
        float(profit_loss.get("krw")) if isinstance(profit_loss, dict) and profit_loss.get("krw") is not None else None,
        float(profit_loss.get("usd")) if isinstance(profit_loss, dict) and profit_loss.get("usd") is not None else None,
        float(buy_amount.get("krw")) if isinstance(buy_amount, dict) and buy_amount.get("krw") is not None else None,
        float(buy_amount.get("usd")) if isinstance(buy_amount, dict) and buy_amount.get("usd") is not None else None,
        float(sell_amount.get("krw")) if isinstance(sell_amount, dict) and sell_amount.get("krw") is not None else None,
        float(sell_amount.get("usd")) if isinstance(sell_amount, dict) and sell_amount.get("usd") is not None else None,
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sign_realized_feed_row(
    row: Mapping[str, Any],
    user_id: str,
    generation_id: str | None = None,
    *,
    provider_product_code: str | None = None,
) -> str:
    """Sign a display row while retaining the provider's raw product identity."""
    serializer = _get_serializer()
    provider_code = (
        str(provider_product_code).strip()
        if provider_product_code is not None
        else str(row.get("product_code") or "").strip()
    )
    payload = {
        "v": 1,
        "source": "toss_wts",
        "kind": "realized_pnl_row",
        "scope_verified": False,
        "user_id": str(user_id),
        "generation_id": str(generation_id) if generation_id else None,
        "row_hash": canonical_row_hash(row),
        "date": str(row.get("date")),
        "product_code": str(row.get("product_code")),
        "provider_product_code": provider_code,
        "market_type": str(row.get("market_type")),
    }
    return serializer.dumps(payload, salt=ROW_SELECTION_SALT)


def _verified_realized_feed_row_token_data(
    row: Mapping[str, Any],
    token: str,
    user_id: str,
    current_generation_id: str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(token, str) or not token.strip():
        return None, "TOKEN_MISSING"
    serializer = _get_serializer()
    try:
        data = serializer.loads(token, salt=ROW_SELECTION_SALT, max_age=ROW_SELECTION_MAX_AGE_SECONDS)
    except SignatureExpired:
        return None, "TOKEN_EXPIRED"
    except BadSignature:
        return None, "TOKEN_INVALID"
    except Exception:
        return None, "TOKEN_INVALID"

    if not isinstance(data, dict):
        return None, "TOKEN_INVALID"
    if data.get("v") != 1 or data.get("source") != "toss_wts" or data.get("scope_verified") is not False:
        return None, "TOKEN_INVALID"
    if data.get("user_id") != str(user_id):
        return None, "USER_MISMATCH"
    if current_generation_id is not None and data.get("generation_id") is not None:
        if data.get("generation_id") != str(current_generation_id):
            return None, "RUNTIME_GENERATION_CHANGED"
    if data.get("row_hash") != canonical_row_hash(row):
        return None, "ROW_TAMPERED"
    return data, None


def verify_realized_feed_row_token(
    row: Mapping[str, Any],
    token: str,
    user_id: str,
    current_generation_id: str | None = None,
) -> tuple[bool, str | None]:
    """Verify that the row has not been tampered with and was fetched by the current session."""
    data, error = _verified_realized_feed_row_token_data(
        row, token, user_id, current_generation_id
    )
    return data is not None, error


def get_verified_realized_feed_provider_product_code(
    row: Mapping[str, Any],
    token: str,
    user_id: str,
    current_generation_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Return signed provider product code after validating the submitted display row.

    Tokens created before provider_product_code was added remain valid by falling
    back to the legacy signed product_code field.
    """
    data, error = _verified_realized_feed_row_token_data(
        row, token, user_id, current_generation_id
    )
    if data is None:
        return None, error
    raw = data.get("provider_product_code")
    if raw is None:
        raw = data.get("product_code")
    if not isinstance(raw, str) or not raw.strip():
        return None, "TOKEN_INVALID"
    return raw.strip(), None


def validate_realized_feed_request(
    from_date: Any,
    to_date: Any,
    profit_rate_basis: Any,
) -> tuple[str, str, str]:
    """Validate request arguments strictly.

    Requires from_date and to_date in YYYY-MM-DD format with from_date <= to_date.
    Requires profit_rate_basis in {'KRW', 'USD'}.
    Raises ValueError on invalid or missing inputs.
    """
    if not isinstance(from_date, str) or not _DATE_REGEX.match(from_date):
        raise ValueError("from_date must be in YYYY-MM-DD format")
    if not isinstance(to_date, str) or not _DATE_REGEX.match(to_date):
        raise ValueError("to_date must be in YYYY-MM-DD format")

    try:
        parsed_from = date.fromisoformat(from_date)
    except ValueError as exc:
        raise ValueError("invalid from_date") from exc

    try:
        parsed_to = date.fromisoformat(to_date)
    except ValueError as exc:
        raise ValueError("invalid to_date") from exc

    if parsed_from > parsed_to:
        raise ValueError("from_date must be less than or equal to to_date")

    if not isinstance(profit_rate_basis, str) or profit_rate_basis not in _ALLOWED_RATE_BASES:
        raise ValueError("profit_rate_basis must be KRW or USD")

    return from_date, to_date, profit_rate_basis


def project_realized_feed_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Project one WTS profit row into the transient display/feed contract.

    The provider product identity remains in the signed selection token. Korean
    display fields use Wealth's canonical short code so the current UI, which
    prefers ``symbol`` over ``product_code``, never exposes Toss' leading ``A``
    provider prefix. Overseas symbols remain untouched.
    """
    market_type = row["market_type"]
    canonical_product_code = canonicalize_toss_wts_stock_code(
        market_type, row["product_code"]
    )
    display_symbol = (
        canonical_product_code
        if str(market_type or "").strip().lower() == "kr"
        else row["symbol"]
    )
    return {
        "date": row["date"],
        "market_type": market_type,
        "symbol": display_symbol,
        "product_code": canonical_product_code,
        "name": row["name"],
        "quantity": row["quantity"],
        "profit_loss": dict(row["profit_loss"]),
        "profit_rate": row["profit_rate"],
        "sell_amount": dict(row["sell_amount"]),
        "buy_amount": dict(row["buy_amount"]),
    }


def build_realized_feed_response(
    from_date: str,
    to_date: str,
    profit_rate_basis: str,
    adapter_result: Mapping[str, Any],
    *,
    user_id: str | None = None,
    generation_id: str | None = None,
) -> dict[str, Any]:
    """Build a canonical, transient, unverified-scope feed response."""
    stocks = adapter_result.get("stocks", [])
    rows = [project_realized_feed_row(r) for r in stocks]
    state = "ok" if len(rows) > 0 else "empty"

    response = {
        "source": "toss_wts",
        "kind": "realized_pnl_feed",
        "scope_kind": "unverified",
        "scope_verified": False,
        "read_only": True,
        "persisted": False,
        "included_in_accounting_totals": False,
        "requested": {
            "from_date": from_date,
            "to_date": to_date,
            "profit_rate_basis": profit_rate_basis,
        },
        "fetched_at": adapter_result["fetched_at"],
        "state": state,
        "rows": rows,
    }
    if user_id:
        response["selection_tokens"] = [
            sign_realized_feed_row(
                display_row,
                user_id=user_id,
                generation_id=generation_id,
                provider_product_code=str(provider_row.get("product_code") or ""),
            )
            for display_row, provider_row in zip(rows, stocks)
        ]
    return response


PREVIEW_TICKET_SALT = "toss-wts-preview-v1"
PREVIEW_TICKET_MAX_AGE_SECONDS = 900  # 15 minutes


def compute_items_hash(selected_items: list[Mapping[str, Any]]) -> str:
    """Deterministic hash of selected items to bind preview and commit."""
    hashes = []
    for it in selected_items:
        if isinstance(it, Mapping):
            row = it.get("row", it)
            token = str(it.get("selection_token") or (row.get("selection_token") if isinstance(row, Mapping) else "") or "")
            hashes.append(f"{canonical_row_hash(row)}:{token}")
    encoded = json.dumps(sorted(hashes), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sign_import_preview_ticket(
    account_id: str,
    items_hash: str,
    user_id: str,
    generation_id: str | None = None,
) -> str:
    """Sign an import preview ticket binding chosen account, items hash, and user."""
    serializer = _get_serializer()
    payload = {
        "v": 1,
        "account_id": str(account_id),
        "items_hash": str(items_hash),
        "user_id": str(user_id),
        "generation_id": str(generation_id) if generation_id else None,
    }
    return serializer.dumps(payload, salt=PREVIEW_TICKET_SALT)


def verify_import_preview_ticket(
    ticket: str,
    account_id: str,
    items_hash: str,
    user_id: str,
    current_generation_id: str | None = None,
) -> tuple[bool, str | None]:
    """Verify preview ticket authenticity and ensure destination account was not altered."""
    if not isinstance(ticket, str) or not ticket.strip():
        return False, "PREVIEW_TICKET_MISSING"
    serializer = _get_serializer()
    try:
        data = serializer.loads(ticket, salt=PREVIEW_TICKET_SALT, max_age=PREVIEW_TICKET_MAX_AGE_SECONDS)
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
    if current_generation_id is not None and data.get("generation_id") is not None:
        if data.get("generation_id") != str(current_generation_id):
            return False, "RUNTIME_GENERATION_CHANGED"
    if data.get("account_id") != str(account_id):
        return False, "DESTINATION_ACCOUNT_CHANGED"
    if data.get("items_hash") != str(items_hash):
        return False, "ITEMS_TAMPERED"
    return True, None
