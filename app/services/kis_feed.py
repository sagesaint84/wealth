"""Pure projection and response builder for Korea Investment & Securities (KIS) realized profit feed.

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

_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_MARKETS = frozenset({"kr", "us", "domestic", "overseas"})

KIS_ROW_SELECTION_SALT = "kis-row-selection-v1"
KIS_ROW_SELECTION_MAX_AGE_SECONDS = 86400  # 24 hours

KIS_PREVIEW_TICKET_SALT = "kis-preview-ticket-v1"
KIS_PREVIEW_TICKET_MAX_AGE_SECONDS = 900  # 15 minutes


def get_kis_signing_secret() -> str:
    """Return the signing secret for KIS tokens and HMAC identities.

    Fails closed in production environments if DASHBOARD_SECRET_KEY is not configured.
    """
    secret = os.getenv("DASHBOARD_SECRET_KEY", "").strip()
    if secret:
        return secret
    if os.getenv("WEALTH_ENV", "").strip().lower() == "test":
        return os.getenv("WEALTH_TEST_SIGNING_SECRET", "").strip() or "wealth_synthetic_test_secret_for_kis"
    raise RuntimeError("DASHBOARD_SECRET_KEY가 설정되지 않아 KIS 무결성 서명 처리를 진행할 수 없습니다.")


def _get_serializer() -> URLSafeTimedSerializer:
    secret = get_kis_signing_secret()
    return URLSafeTimedSerializer(secret)


def _canonical_num_str(val: Any) -> str:
    """Convert number or numeric string to deterministic normalized string."""
    if val is None or val == "":
        return ""
    try:
        f = float(str(val).replace(",", "").strip())
        if f.is_integer():
            return str(int(f))
        return f"{f:.6f}".rstrip("0").rstrip(".")
    except (ValueError, TypeError):
        return str(val).strip()


def _canonical_date_str(val: Any) -> str:
    """Normalize date representation to YYYY-MM-DD."""
    raw = str(val or "").strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def canonical_kis_row_hash(row: Mapping[str, Any]) -> str:
    """Compute deterministic hash of canonical KIS row fields invariant to JSON integer/float roundtripping."""
    date_val = _canonical_date_str(row.get("trad_dt") or row.get("trad_day") or row.get("date") or "")
    code = str(row.get("pdno") or row.get("ovrs_pdno") or row.get("stck_shrn_iscd") or row.get("code") or "").strip()
    name = str(row.get("prdt_name") or row.get("ovrs_item_name") or row.get("name") or "").strip()

    qty_val = row.get("sll_qty") if row.get("sll_qty") is not None else (row.get("slcl_qty") if row.get("slcl_qty") is not None else row.get("quantity"))
    qty = _canonical_num_str(qty_val)

    pnl_val = row.get("rlzt_pfls") if row.get("rlzt_pfls") is not None else (row.get("rlzt_pl") if row.get("rlzt_pl") is not None else (row.get("ovrs_rlzt_pfls_amt") if row.get("ovrs_rlzt_pfls_amt") is not None else (row.get("profit_loss") if row.get("profit_loss") is not None else row.get("pnl"))))
    pnl = _canonical_num_str(pnl_val)

    rate_val = row.get("pfls_rt") if row.get("pfls_rt") is not None else (row.get("erng_rt") if row.get("erng_rt") is not None else (row.get("pftrt") if row.get("pftrt") is not None else row.get("profit_rate")))
    rate = _canonical_num_str(rate_val)

    sell_val = row.get("sll_amt") if row.get("sll_amt") is not None else (row.get("frcr_sll_amt_smtl1") if row.get("frcr_sll_amt_smtl1") is not None else (row.get("sell_amount") if row.get("sell_amount") is not None else row.get("foreign_sell_amount")))
    sell_amt = _canonical_num_str(sell_val)

    # Official primary is buy_amt; fall back to buy_amount, frcr_pchs_amt1, foreign_buy_amount, or legacy pchs_amt
    buy_val = row.get("buy_amt") if row.get("buy_amt") is not None else (row.get("buy_amount") if row.get("buy_amount") is not None else (row.get("frcr_pchs_amt1") if row.get("frcr_pchs_amt1") is not None else (row.get("foreign_buy_amount") if row.get("foreign_buy_amount") is not None else row.get("pchs_amt"))))
    buy_amt = _canonical_num_str(buy_val)

    payload = [date_val, code, name, qty, pnl, rate, sell_amt, buy_amt]
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sign_kis_feed_row(
    row: Mapping[str, Any],
    user_id: str,
    source_account_key: str,
) -> str:
    """Sign a canonical KIS feed row token binding content, user identity, and verified opaque account key."""
    serializer = _get_serializer()
    date_val = _canonical_date_str(row.get("trad_dt") or row.get("trad_day") or row.get("date") or "")
    code = str(row.get("pdno") or row.get("ovrs_pdno") or row.get("code") or "").strip()
    payload = {
        "v": 1,
        "source": "kis",
        "kind": "realized_pnl_row",
        "scope_verified": True,
        "source_account_key": str(source_account_key),
        "user_id": str(user_id),
        "row_hash": canonical_kis_row_hash(row),
        "date": date_val,
        "code": code,
    }
    return serializer.dumps(payload, salt=KIS_ROW_SELECTION_SALT)


def verify_kis_feed_row_token(
    row: Mapping[str, Any],
    token: str,
    user_id: str,
    expected_account_key: str | None = None,
) -> tuple[bool, str | None]:
    """Verify that the row has not been tampered with and was fetched for this verified account key."""
    if not isinstance(token, str) or not token.strip():
        return False, "TOKEN_MISSING"
    try:
        serializer = _get_serializer()
        data = serializer.loads(token, salt=KIS_ROW_SELECTION_SALT, max_age=KIS_ROW_SELECTION_MAX_AGE_SECONDS)
    except SignatureExpired:
        return False, "TOKEN_EXPIRED"
    except (BadSignature, Exception):
        return False, "TOKEN_INVALID"

    if not isinstance(data, dict):
        return False, "TOKEN_INVALID"
    if data.get("v") != 1 or data.get("source") != "kis" or data.get("scope_verified") is not True:
        return False, "TOKEN_INVALID"
    if data.get("user_id") != str(user_id):
        return False, "USER_MISMATCH"
    if expected_account_key is not None:
        token_key = data.get("source_account_key") or data.get("scope")
        if token_key != str(expected_account_key):
            return False, "SCOPE_MISMATCH"
    if data.get("row_hash") != canonical_kis_row_hash(row):
        return False, "ROW_TAMPERED"
    return True, None


def validate_kis_feed_request(
    market: Any,
    from_date: Any,
    to_date: Any,
) -> tuple[str, str, str]:
    """Validate request arguments strictly."""
    if not isinstance(market, str) or market.strip().lower() not in _ALLOWED_MARKETS:
        raise ValueError("market must be kr or us")
    clean_market = "kr" if market.strip().lower() in ("kr", "domestic") else "us"

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

    return clean_market, from_date, to_date


def project_kis_feed_row(row: Mapping[str, Any], market: str) -> dict[str, Any]:
    """Project one raw KIS profit row into the feed contract.

    Uses verified official KIS TTTC8715R fields for domestic (buy_amt, sll_amt, sll_qty, rlzt_pfls, pfls_rt, fee, tl_tax).
    Preserves genuine '0' as 0.0, and sets missing values to None.
    """
    if market == "kr":
        raw_dt = str(row.get("trad_dt") or row.get("date") or "").strip()
        formatted_dt = f"{raw_dt[:4]}-{raw_dt[4:6]}-{raw_dt[6:]}" if len(raw_dt) == 8 and raw_dt.isdigit() else raw_dt

        # Quantity: sll_qty (official) or quantity
        qty_raw = row.get("sll_qty") if row.get("sll_qty") is not None else row.get("quantity")
        if qty_raw is not None and str(qty_raw).strip() != "":
            try:
                quantity = float(str(qty_raw).replace(",", "").strip())
            except (ValueError, TypeError):
                quantity = None
        else:
            quantity = None

        # Sell amount: sll_amt (official) or sell_amount
        sell_raw = row.get("sll_amt") if row.get("sll_amt") is not None else row.get("sell_amount")
        if sell_raw is not None and str(sell_raw).strip() != "":
            try:
                sell_amount = float(str(sell_raw).replace(",", "").strip())
            except (ValueError, TypeError):
                sell_amount = None
        else:
            sell_amount = None

        # Buy amount: buy_amt (official primary) or buy_amount or pchs_amt (legacy fallback)
        buy_raw = None
        if row.get("buy_amt") is not None and str(row.get("buy_amt")).strip() != "":
            buy_raw = row.get("buy_amt")
        elif row.get("buy_amount") is not None and str(row.get("buy_amount")).strip() != "":
            buy_raw = row.get("buy_amount")
        elif row.get("pchs_amt") is not None and str(row.get("pchs_amt")).strip() != "":
            buy_raw = row.get("pchs_amt")

        if buy_raw is not None:
            try:
                buy_amount = float(str(buy_raw).replace(",", "").strip())
            except (ValueError, TypeError):
                buy_amount = None
        else:
            buy_amount = None

        # Profit / Loss: rlzt_pfls (official) or profit_loss or rlzt_pl
        pnl_raw = None
        if row.get("rlzt_pfls") is not None and str(row.get("rlzt_pfls")).strip() != "":
            pnl_raw = row.get("rlzt_pfls")
        elif row.get("profit_loss") is not None and str(row.get("profit_loss")).strip() != "":
            pnl_raw = row.get("profit_loss")
        elif row.get("rlzt_pl") is not None and str(row.get("rlzt_pl")).strip() != "":
            pnl_raw = row.get("rlzt_pl")

        if pnl_raw is not None:
            try:
                profit_loss = float(str(pnl_raw).replace(",", "").strip())
            except (ValueError, TypeError):
                profit_loss = None
        else:
            profit_loss = None

        # Profit rate: pfls_rt (official) or profit_rate or erng_rt
        rate_raw = row.get("pfls_rt") if row.get("pfls_rt") is not None else (row.get("profit_rate") if row.get("profit_rate") is not None else row.get("erng_rt"))
        if rate_raw is not None and str(rate_raw).strip() != "":
            try:
                profit_rate = float(str(rate_raw).replace(",", "").strip())
            except (ValueError, TypeError):
                profit_rate = None
        else:
            profit_rate = None

        # Fee & Tax
        fee_raw = row.get("fee")
        try:
            fee = float(str(fee_raw).replace(",", "").strip()) if fee_raw not in (None, "") else 0.0
        except (ValueError, TypeError):
            fee = 0.0

        tax_raw = row.get("tl_tax") if row.get("tl_tax") is not None else row.get("tax")
        try:
            tax = float(str(tax_raw).replace(",", "").strip()) if tax_raw not in (None, "") else 0.0
        except (ValueError, TypeError):
            tax = 0.0

        return {
            "date": formatted_dt,
            "market_type": "kr",
            "code": str(row.get("pdno") or row.get("stck_shrn_iscd") or row.get("code") or "").strip(),
            "name": str(row.get("prdt_name") or row.get("name") or "").strip(),
            "quantity": quantity,
            "sell_amount": sell_amount,
            "buy_amount": buy_amount,
            "profit_loss": profit_loss,
            "profit_rate": profit_rate,
            "fee": fee,
            "tax": tax,
            "currency": "KRW",
        }
    else:
        raw_dt = str(row.get("trad_day") or row.get("trad_dt") or row.get("date") or "").strip()
        formatted_dt = f"{raw_dt[:4]}-{raw_dt[4:6]}-{raw_dt[6:]}" if len(raw_dt) == 8 and raw_dt.isdigit() else raw_dt
        exrt_val = row.get("bass_exrt") or row.get("exrt") or row.get("frst_bltn_exrt") or row.get("fx_rate")
        fx_rate = float(exrt_val) if exrt_val not in (None, "", 0, "0") else None
        foreign_pnl = float(row.get("ovrs_rlzt_pfls_amt") or row.get("rlzt_pfls") or row.get("profit_loss") or 0.0)

        won_sell = float(row.get("stck_sll_amt_smtl") or 0.0)
        won_buy = float(row.get("stck_buy_amt_smtl") or 0.0)
        if won_sell > 0 and won_buy > 0:
            won_pnl = round(won_sell - won_buy, 2)
        elif "profit_loss_krw" in row and row["profit_loss_krw"] is not None:
            won_pnl = float(row["profit_loss_krw"])
        elif fx_rate is not None and fx_rate > 0:
            won_pnl = round(foreign_pnl * fx_rate, 2)
        else:
            won_pnl = None

        return {
            "date": formatted_dt,
            "market_type": "us",
            "code": str(row.get("ovrs_pdno") or row.get("pdno") or row.get("code") or "").strip(),
            "name": str(row.get("ovrs_item_name") or row.get("item_name") or row.get("prdt_name") or row.get("name") or "").strip(),
            "quantity": float(row.get("slcl_qty") or row.get("sll_qty") or row.get("quantity") or 0.0),
            "foreign_currency": str(row.get("crcy_cd") or row.get("currency") or "USD").strip() or "USD",
            "foreign_sell_amount": float(row.get("frcr_sll_amt_smtl1") or row.get("sll_amt") or row.get("foreign_sell_amount") or 0.0),
            "foreign_buy_amount": float(row.get("frcr_pchs_amt1") or row.get("buy_amt") or row.get("foreign_buy_amount") or 0.0),
            "foreign_profit_loss": foreign_pnl,
            "profit_loss": foreign_pnl,
            "profit_loss_krw": won_pnl,
            "profit_rate": float(row.get("pftrt") or row.get("rlzt_erng_rt") or row.get("profit_rate") or 0.0),
            "fx_rate": fx_rate,
            "currency": str(row.get("crcy_cd") or row.get("currency") or "USD").strip() or "USD",
        }


def build_kis_realized_feed_response(
    market: str,
    from_date: str,
    to_date: str,
    rows_raw: list[dict[str, Any]],
    source_account_key: str,
    source_account_label: str,
    *,
    user_id: str | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    """Build a canonical, transient, verified-scope feed response."""
    from datetime import datetime, timezone
    now_iso = fetched_at or datetime.now(timezone.utc).isoformat()
    rows = [project_kis_feed_row(r, market) for r in rows_raw]
    state = "ok" if len(rows) > 0 else "empty"

    response: dict[str, Any] = {
        "source": "kis",
        "kind": "realized_pnl_feed",
        "scope_kind": "verified",
        "scope_verified": True,
        "source_account_key": source_account_key,
        "source_account_label": source_account_label,
        "masked_account": source_account_label,
        "read_only": True,
        "persisted": False,
        "included_in_accounting_totals": False,
        "market": market,
        "requested": {
            "market": market,
            "from_date": from_date,
            "to_date": to_date,
        },
        "fetched_at": now_iso,
        "state": state,
        "rows": rows,
    }
    if user_id:
        response["selection_tokens"] = [
            sign_kis_feed_row(r, user_id=user_id, source_account_key=source_account_key)
            for r in rows
        ]
    return response


def compute_kis_items_hash(selected_items: list[Mapping[str, Any]]) -> str:
    """Deterministic hash of selected items to bind preview and commit."""
    hashes = []
    for it in selected_items:
        if isinstance(it, Mapping):
            row = it.get("row", it)
            token = str(it.get("selection_token") or (row.get("selection_token") if isinstance(row, Mapping) else "") or "")
            hashes.append(f"{canonical_kis_row_hash(row)}:{token}")
    encoded = json.dumps(sorted(hashes), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sign_kis_import_preview_ticket(
    account_id: str,
    items_hash: str,
    user_id: str,
    source_account_key: str,
) -> str:
    """Sign an import preview ticket binding chosen account, items hash, user, and verified opaque account key."""
    serializer = _get_serializer()
    payload = {
        "v": 1,
        "source": "kis",
        "account_id": str(account_id),
        "items_hash": str(items_hash),
        "user_id": str(user_id),
        "source_account_key": str(source_account_key),
    }
    return serializer.dumps(payload, salt=KIS_PREVIEW_TICKET_SALT)


def verify_kis_import_preview_ticket(
    ticket: str,
    account_id: str,
    items_hash: str,
    user_id: str,
    expected_account_key: str | None = None,
) -> tuple[bool, str | None]:
    """Verify preview ticket authenticity and ensure destination account and account key were not altered."""
    if not isinstance(ticket, str) or not ticket.strip():
        return False, "PREVIEW_TICKET_MISSING"
    try:
        serializer = _get_serializer()
        data = serializer.loads(ticket, salt=KIS_PREVIEW_TICKET_SALT, max_age=KIS_PREVIEW_TICKET_MAX_AGE_SECONDS)
    except SignatureExpired:
        return False, "PREVIEW_TICKET_EXPIRED"
    except (BadSignature, Exception):
        return False, "PREVIEW_TICKET_INVALID"

    if not isinstance(data, dict) or data.get("v") != 1 or data.get("source") != "kis":
        return False, "PREVIEW_TICKET_INVALID"
    if data.get("user_id") != str(user_id):
        return False, "USER_MISMATCH"
    if expected_account_key is not None:
        token_key = data.get("source_account_key") or data.get("account_scope")
        if token_key != str(expected_account_key):
            return False, "SCOPE_MISMATCH"
    if data.get("account_id") != str(account_id):
        return False, "DESTINATION_ACCOUNT_CHANGED"
    if data.get("items_hash") != str(items_hash):
        return False, "ITEMS_TAMPERED"
    return True, None
