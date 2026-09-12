"""Pure projection and response builder for Toss WTS realized profit feed.

This service is strictly read-only and transient. It does not persist records,
attribute accounts, or modify portfolio totals.
"""

from __future__ import annotations

from datetime import date
import re
from typing import Any, Mapping

_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_RATE_BASES = frozenset({"KRW", "USD"})


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
    """Project one normalized WTS profit daily row into the feed contract.

    Preserves provider row structure without assigning account, owner, or id.
    """
    return {
        "date": row["date"],
        "market_type": row["market_type"],
        "symbol": row["symbol"],
        "product_code": row["product_code"],
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
) -> dict[str, Any]:
    """Build a canonical, transient, unverified-scope feed response."""
    stocks = adapter_result.get("stocks", [])
    rows = [project_realized_feed_row(r) for r in stocks]
    state = "ok" if len(rows) > 0 else "empty"

    return {
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
