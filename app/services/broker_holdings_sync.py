from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import math
from typing import Any, Iterable


class HoldingsResultState(str, Enum):
    CONFIRMED_NONEMPTY = "CONFIRMED_NONEMPTY"
    AUTHORITATIVE_EMPTY = "AUTHORITATIVE_EMPTY"
    PAYLOAD_MISSING = "PAYLOAD_MISSING"
    STATUS_ONLY = "STATUS_ONLY"
    MALFORMED = "MALFORMED"
    ACCOUNT_SCOPE_UNVERIFIED = "ACCOUNT_SCOPE_UNVERIFIED"
    MARKET_SCOPE_PARTIAL = "MARKET_SCOPE_PARTIAL"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    UNKNOWN_EMPTY = "UNKNOWN_EMPTY"


ALL_MARKETS = "ALL"
DOMESTIC_MARKET = "DOMESTIC"
OVERSEAS_MARKET = "OVERSEAS"


@dataclass(frozen=True)
class ProviderHoldingScope:
    account_key: str
    market_scope: str

    def __post_init__(self) -> None:
        if not str(self.account_key).strip() or not str(self.market_scope).strip():
            raise ValueError("holding replacement scope must include account and market")


@dataclass(frozen=True)
class ResolvedHoldingScope:
    account_id: str
    market_scope: str

    def __post_init__(self) -> None:
        if not str(self.account_id).strip() or not str(self.market_scope).strip():
            raise ValueError("resolved holding scope must include account and market")


class BrokerHoldingsResult(list):
    """List-compatible provider result carrying deletion authority separately.

    Existing callers may continue iterating over holdings. Persistence code must
    additionally verify ``authoritative`` and resolve every provider scope to a
    Wealth account before deleting anything.
    """

    def __init__(
        self,
        rows: Iterable[dict[str, Any]] = (),
        *,
        state: HoldingsResultState,
        scopes: Iterable[ProviderHoldingScope] = (),
        cash_valid: bool = False,
    ) -> None:
        super().__init__(rows)
        self.state = HoldingsResultState(state)
        self.scopes = tuple(scopes)
        self.cash_valid = bool(cash_valid)

    @property
    def authoritative(self) -> bool:
        return self.state in {
            HoldingsResultState.CONFIRMED_NONEMPTY,
            HoldingsResultState.AUTHORITATIVE_EMPTY,
        } and bool(self.scopes)

    @classmethod
    def authoritative_result(
        cls,
        rows: Iterable[dict[str, Any]],
        scopes: Iterable[ProviderHoldingScope],
        *,
        cash_valid: bool,
    ) -> "BrokerHoldingsResult":
        materialized = list(rows)
        return cls(
            materialized,
            state=(
                HoldingsResultState.CONFIRMED_NONEMPTY
                if materialized
                else HoldingsResultState.AUTHORITATIVE_EMPTY
            ),
            scopes=scopes,
            cash_valid=cash_valid,
        )


def required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"required holding field is missing: {key}")
    return text


def required_finite_number(row: dict[str, Any], key: str) -> float:
    value = row.get(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"required holding field is missing: {key}")
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"required holding field is malformed: {key}") from exc
    if not parsed.is_finite():
        raise ValueError(f"required holding field is non-finite: {key}")
    number = float(parsed)
    if not math.isfinite(number):
        raise ValueError(f"required holding field is non-finite: {key}")
    return number


def optional_finite_number(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    if value is None or str(value).strip() == "":
        return default
    return required_finite_number(row, key)


def resolve_scopes(
    scopes: Iterable[ProviderHoldingScope], account_map: dict[str, tuple[str, str]],
) -> tuple[ResolvedHoldingScope, ...] | None:
    resolved: list[ResolvedHoldingScope] = []
    seen: set[tuple[str, str]] = set()
    for scope in scopes:
        account = account_map.get(str(scope.account_key))
        if not account:
            return None
        key = (str(account[0]), str(scope.market_scope).upper())
        if key not in seen:
            seen.add(key)
            resolved.append(ResolvedHoldingScope(*key))
    return tuple(resolved) if resolved else None


def _is_domestic(holding: dict[str, Any]) -> bool:
    market = str(holding.get("market") or "").strip().upper()
    if market in {"KR", "KRX", "KOSPI", "KOSDAQ"}:
        return True
    if market:
        return False
    currency = str(holding.get("currency") or "").strip().upper()
    return currency == "KRW"


def holding_matches_scope(holding: dict[str, Any], scope: ResolvedHoldingScope) -> bool:
    if str(holding.get("account_id") or "") != scope.account_id:
        return False
    target = scope.market_scope.upper()
    if target == ALL_MARKETS:
        return True
    if target == DOMESTIC_MARKET:
        return _is_domestic(holding)
    if target == OVERSEAS_MARKET:
        return not _is_domestic(holding)
    return str(holding.get("market") or "").strip().upper() == target


def replace_holdings_in_scopes(
    data: dict[str, Any],
    holdings: Iterable[dict[str, Any]],
    *,
    source: str,
    scopes: Iterable[ResolvedHoldingScope],
) -> int:
    """Replace only explicitly verified provider/account/market scopes."""
    from app.services.portfolio import upsert_holdings

    rows = list(holdings)
    scope_list = tuple(scopes)
    if not scope_list:
        raise ValueError("authoritative holdings replacement requires a scope")
    for row in rows:
        if row.get("source") != source or not any(holding_matches_scope(row, scope) for scope in scope_list):
            raise ValueError("returned holding falls outside the verified replacement scope")
    existing_ids = {
        (
            str(holding.get("account_id") or ""),
            str(holding.get("market") or "").strip().upper(),
            str(holding.get("code") or ""),
        ): holding.get("id")
        for holding in data.get("holdings", [])
        if holding.get("source") == source and holding.get("id")
    }
    for row in rows:
        existing_id = existing_ids.get((
            str(row.get("account_id") or ""),
            str(row.get("market") or "").strip().upper(),
            str(row.get("code") or ""),
        ))
        if existing_id:
            row["id"] = existing_id
    data["holdings"] = [
        holding
        for holding in data.get("holdings", [])
        if not (
            holding.get("source") == source
            and any(holding_matches_scope(holding, scope) for scope in scope_list)
        )
    ]
    return upsert_holdings(data, rows)
