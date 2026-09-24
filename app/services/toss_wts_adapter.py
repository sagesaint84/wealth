"""Optional, read-only bridge to a locally provisioned tossctl binary.

This module never installs tossctl, launches a browser, or reads a session file.
It is deliberately limited to local status and an explicit auth-status probe;
financial WTS operations belong to later, separately reviewed phases.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

from app.services.network_policy import is_test_mode
from app.services.system_settings import (
    DEFAULT_TOSS_WTS_EXPECTED_VERSION,
    DEFAULT_TOSS_WTS_TIMEOUT_SECONDS,
    SystemSettingsError,
    resolve_toss_wts_settings,
)


EXPECTED_TOSSCTL_VERSION = DEFAULT_TOSS_WTS_EXPECTED_VERSION
TOSSCTL_DATE_TIMEZONE_CONFLICT = "TOSSCTL_DATE_TIMEZONE_CONFLICT"
_AFFECTED_DATE_VALIDATION_VERSIONS = frozenset({"v0.50.3", "0.50.3"})
_SEOUL = timezone(timedelta(hours=9), name="Asia/Seoul")
_ISO_DATE_IN_TEXT = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
DEFAULT_TIMEOUT_SECONDS = DEFAULT_TOSS_WTS_TIMEOUT_SECONDS
_AUTH_STATUS = "AUTH_STATUS"
_PROFIT_OVERVIEW = "PROFIT_OVERVIEW"
_PROFIT_DAILY = "PROFIT_DAILY"
_TRANSACTIONS_LIST = "TRANSACTIONS_LIST"
_OPERATION_ARGS = {
    _AUTH_STATUS: ("auth", "status"),
    _PROFIT_OVERVIEW: ("profit",),
    _PROFIT_DAILY: ("profit", "daily"),
    _TRANSACTIONS_LIST: ("transactions", "list"),
}
_PROFIT_DAILY_CURRENCIES = frozenset({"KRW", "USD"})
_TRANSACTION_MARKETS = frozenset({"kr", "us"})
_TRANSACTION_FILTERS = frozenset({"all", "trade", "cash", "inout", "cash-alt"})
_TRANSACTION_MAX_DAYS = 200

# Kept as stable, sanitized boundary codes.  Future explicit probes can map
# upstream auth/version states to these without exposing raw CLI output.
ERROR_CODES = frozenset(
    {
        "NOT_CONFIGURED",
        "EXECUTABLE_MISSING",
        "CONFIG_DIR_MISSING",
        "SESSION_MISSING",
        "VERSION_MISMATCH",
        "AUTH_REQUIRED",
        "AUTH_EXPIRED",
        "ACCESS_DENIED",
        "TOSSCTL_TIMEOUT",
        "NONZERO_EXIT",
        TOSSCTL_DATE_TIMEZONE_CONFLICT,
        "INVALID_JSON",
        "UNSUPPORTED_COMMAND",
        "TEST_MODE_DISABLED",
        "INVALID_SCHEMA",
    }
)


class TossWtsAdapterError(RuntimeError):
    """A sanitized adapter error; never includes subprocess output."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def resolve_tossctl_profit_daily_range(
    from_date: str,
    to_date: str,
    *,
    expected_version: str = EXPECTED_TOSSCTL_VERSION,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Resolve the CLI-safe range without changing the user's requested dates.

    tossctl v0.50.3 compares a UTC-midnight parsed date with the current instant.
    Before 09:00 KST, Korean today is therefore rejected. Only that affected
    contract is adjusted, and no future/fictional data is produced.
    """
    try:
        parsed_from = date.fromisoformat(from_date)
        parsed_to = date.fromisoformat(to_date)
    except (TypeError, ValueError) as exc:
        raise TossWtsAdapterError("INVALID_SCHEMA") from exc
    if parsed_from > parsed_to:
        raise TossWtsAdapterError("INVALID_SCHEMA")

    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    kst_today = instant.astimezone(_SEOUL).date()
    utc_today = instant.astimezone(timezone.utc).date()
    if parsed_to > kst_today:
        raise TossWtsAdapterError("INVALID_SCHEMA")

    adjusted = (
        expected_version.strip() in _AFFECTED_DATE_VALIDATION_VERSIONS
        and parsed_to == kst_today
        and kst_today > utc_today
    )
    effective_to = utc_today if adjusted else parsed_to
    if parsed_from > effective_to:
        raise TossWtsAdapterError(TOSSCTL_DATE_TIMEZONE_CONFLICT)
    return {
        "requested_from_date": from_date,
        "requested_to_date": to_date,
        "effective_from_date": from_date,
        "effective_to_date": effective_to.isoformat(),
        "date_range_adjusted": adjusted,
        "compatibility_code": TOSSCTL_DATE_TIMEZONE_CONFLICT if adjusted else None,
    }


def _is_known_tossctl_future_date_rejection(stderr: object) -> bool:
    text = stderr if isinstance(stderr, str) else ""
    return "미래입니다" in text and _ISO_DATE_IN_TEXT.search(text) is not None


@dataclass(frozen=True)
class TossWtsConfig:
    enabled: bool
    executable: Path | None
    config_dir: Path | None
    expected_version: str
    timeout_seconds: int

    @classmethod
    def from_environment(cls, username: str | None = None) -> "TossWtsConfig":
        try:
            effective = resolve_toss_wts_settings()
        except SystemSettingsError:
            return cls(False, None, None, EXPECTED_TOSSCTL_VERSION, DEFAULT_TIMEOUT_SECONDS)
        config_dir = Path(str(effective["config_dir"]))
        if username is not None:
            from app.services.toss_wts_auth_guard import _user_toss_root
            config_dir = _user_toss_root(username) / "config"
        return cls(
            enabled=bool(effective["enabled"]),
            executable=Path(str(effective["executable"])),
            config_dir=config_dir,
            expected_version=str(effective["expected_version"]),
            timeout_seconds=int(effective["timeout_seconds"]),
        )


class TossWtsAdapter:
    """Lazy, read-only tossctl adapter with a deliberately closed command set."""

    def __init__(self, config: TossWtsConfig | None = None, *, username: str | None = None):
        self._config = config or TossWtsConfig.from_environment(username=username)
    def get_local_status(self) -> dict[str, Any]:
        """Return only local configuration booleans; no subprocess or session read."""
        executable_present = bool(self._config.executable and self._config.executable.is_file())
        config_dir_present = bool(self._config.config_dir and self._config.config_dir.is_dir())
        session_present = bool(
            config_dir_present
            and self._config.config_dir
            and (self._config.config_dir / "session.json").is_file()
        )
        configured = bool(self._config.enabled and self._config.executable and self._config.config_dir)
        error_code = None
        if not self._config.enabled:
            error_code = "NOT_CONFIGURED"
        elif not self._config.executable:
            error_code = "EXECUTABLE_MISSING"
        elif not executable_present:
            error_code = "EXECUTABLE_MISSING"
        elif not self._config.config_dir or not config_dir_present:
            error_code = "CONFIG_DIR_MISSING"
        elif not session_present:
            error_code = "SESSION_MISSING"
        return {
            "enabled": self._config.enabled,
            "configured": configured,
            "executable_present": executable_present,
            "config_dir_present": config_dir_present,
            "session_present": session_present,
            "expected_version": self._config.expected_version,
            "adapter_ready": error_code is None,
            "error_code": error_code,
        }

    def probe_auth_status(self) -> dict[str, Any]:
        """Explicitly run only `tossctl auth status`; never invoked automatically."""
        status = self.get_local_status()
        if not status["adapter_ready"]:
            return {
                "authenticated": False,
                "session_present": status["session_present"],
                "error_code": status["error_code"],
            }
        if is_test_mode():
            return {
                "authenticated": False,
                "session_present": status["session_present"],
                "error_code": "TEST_MODE_DISABLED",
            }
        payload = self._run_json(_AUTH_STATUS)
        authenticated = (
            bool(payload.get("active") or payload.get("authenticated") or payload.get("valid"))
            if isinstance(payload, dict)
            else False
        )
        return {
            "authenticated": authenticated,
            "session_present": status["session_present"],
            "error_code": None,
        }

    def get_profit_overview(self) -> dict[str, Any]:
        """Fetch the cumulative realized-profit overview; never valuation P/L.

        This explicit, read-only method has no storage or API side effects.
        It intentionally remains unavailable in test mode except through mocked
        subprocess unit tests with a non-test environment override.
        """
        self._require_ready()
        if is_test_mode():
            raise TossWtsAdapterError("TEST_MODE_DISABLED")
        return self._normalize_profit_overview(self._run_json(_PROFIT_OVERVIEW))

    def get_profit_daily(self, from_date: str, to_date: str, currency: str = "KRW") -> dict[str, Any]:
        """Fetch per-date/per-stock realized P/L without sorting or deduplicating rows."""
        normalized_from, normalized_to, normalized_currency = self._validate_profit_daily_request(
            from_date, to_date, currency
        )
        query_range = resolve_tossctl_profit_daily_range(
            normalized_from,
            normalized_to,
            expected_version=self._config.expected_version,
        )
        self._require_ready()
        if is_test_mode():
            raise TossWtsAdapterError("TEST_MODE_DISABLED")
        payload = self._run_json(
            _PROFIT_DAILY,
            (
                "--from", query_range["effective_from_date"],
                "--to", query_range["effective_to_date"],
                "--currency", normalized_currency,
            ),
        )
        result = self._normalize_profit_daily(
            payload,
            query_range["effective_from_date"],
            query_range["effective_to_date"],
            normalized_currency,
        )
        result.update(query_range)
        return result

    def get_transactions_list(
        self,
        from_date: str,
        to_date: str,
        *,
        market: str,
        transaction_filter: str = "cash",
        page_limit: int = 20,
        size: int = 50,
    ) -> list[dict[str, Any]]:
        normalized_from, normalized_to, normalized_market, normalized_filter = self._validate_transactions_request(
            from_date, to_date, market, transaction_filter, page_limit, size
        )
        self._require_ready()
        if is_test_mode():
            raise TossWtsAdapterError("TEST_MODE_DISABLED")
        payload = self._run_json(
            _TRANSACTIONS_LIST,
            (
                "--market", normalized_market,
                "--filter", normalized_filter,
                "--from", normalized_from,
                "--to", normalized_to,
                "--all",
                "--page-limit", str(page_limit),
                "--size", str(size),
            ),
        )
        if not isinstance(payload, list):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        return [self._normalize_transaction_row(row, normalized_market) for row in payload]

    def get_income_transactions(self, from_date: str, to_date: str) -> dict[str, Any]:
        try:
            parsed_from = date.fromisoformat(from_date)
            parsed_to = date.fromisoformat(to_date)
        except (TypeError, ValueError) as exc:
            raise TossWtsAdapterError("INVALID_SCHEMA") from exc
        if parsed_from > parsed_to:
            raise TossWtsAdapterError("INVALID_SCHEMA")
        rows: list[dict[str, Any]] = []
        windows: list[dict[str, str]] = []
        cursor = parsed_from
        while cursor <= parsed_to:
            end = min(cursor + timedelta(days=_TRANSACTION_MAX_DAYS - 1), parsed_to)
            start_text, end_text = cursor.isoformat(), end.isoformat()
            windows.append({"from": start_text, "to": end_text})
            for market in ("kr", "us"):
                rows.extend(self.get_transactions_list(
                    start_text, end_text, market=market, transaction_filter="cash"
                ))
            cursor = end + timedelta(days=1)
        return {
            "source": "toss_wts",
            "kind": "income_transactions",
            "from": from_date,
            "to": to_date,
            "windows": windows,
            "rows": rows,
        }

    @staticmethod
    def _validate_transactions_request(
        from_date: str,
        to_date: str,
        market: str,
        transaction_filter: str,
        page_limit: int,
        size: int,
    ) -> tuple[str, str, str, str]:
        if not all(isinstance(v, str) for v in (from_date, to_date, market, transaction_filter)):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        try:
            parsed_from = date.fromisoformat(from_date)
            parsed_to = date.fromisoformat(to_date)
        except ValueError as exc:
            raise TossWtsAdapterError("INVALID_SCHEMA") from exc
        if parsed_from > parsed_to or (parsed_to - parsed_from).days + 1 > _TRANSACTION_MAX_DAYS:
            raise TossWtsAdapterError("INVALID_SCHEMA")
        normalized_market = market.strip().lower()
        normalized_filter = transaction_filter.strip().lower()
        if normalized_market not in _TRANSACTION_MARKETS or normalized_filter not in _TRANSACTION_FILTERS:
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if type(page_limit) is not int or not 1 <= page_limit <= 100:
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if type(size) is not int or not 1 <= size <= 200:
            raise TossWtsAdapterError("INVALID_SCHEMA")
        return from_date, to_date, normalized_market, normalized_filter

    @staticmethod
    def _normalize_transaction_row(value: Any, market: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        raw = value.get("raw")
        if not isinstance(raw, dict):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        tx = raw.get("transactionType")
        composite = raw.get("compositeKey")
        if not isinstance(tx, dict) or not isinstance(composite, dict):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if not isinstance(value.get("category"), str) or not isinstance(value.get("currency"), str) or not isinstance(value.get("datetime"), str):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if not _is_financial_number(value.get("amount")) or not _is_financial_number(value.get("adjusted_amount")):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        raw_amount = raw.get("amount")
        raw_adjusted = raw.get("adjustedAmount")
        raw_tax = raw.get("totalTaxAmount")
        if not all(_is_financial_number(v) for v in (raw_amount, raw_adjusted, raw_tax)):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if not isinstance(raw.get("summaryNo"), str):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if not isinstance(tx.get("code"), str) or not isinstance(tx.get("displayName"), str):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if not isinstance(composite.get("date"), str) or type(composite.get("no")) is not int:
            raise TossWtsAdapterError("INVALID_SCHEMA")
        return {
            "market": market,
            "category": value["category"],
            "currency": value["currency"],
            "datetime": value["datetime"],
            "display_type": str(value.get("display_type") or ""),
            "stock_name": str(value.get("stock_name") or ""),
            "amount": value["amount"],
            "adjusted_amount": value["adjusted_amount"],
            "source_meta": {
                "summary_no": raw["summaryNo"],
                "trade_type_name": str(raw.get("tradeTypeName") or ""),
                "transaction_type_code": tx["code"],
                "transaction_type_name": tx["displayName"],
                "display_type": str(raw.get("displayType") or ""),
                "stock_code": str(raw.get("stockCode") or ""),
                "stock_name": str(raw.get("stockName") or ""),
                "product_name": str(raw.get("productName") or ""),
                "quantity": raw.get("quantity") if _is_financial_number(raw.get("quantity")) else None,
                "provider_amount": raw_amount,
                "provider_adjusted_amount": raw_adjusted,
                "provider_tax_amount": raw_tax,
                "composite_key": {"date": composite["date"], "no": composite["no"]},
            },
        }

    def _require_ready(self) -> dict[str, Any]:
        status = self.get_local_status()
        if not status["adapter_ready"]:
            raise TossWtsAdapterError(str(status["error_code"]))
        return status

    def _run_json(self, operation: str, arguments: tuple[str, ...] = ()) -> dict[str, Any] | list[Any]:
        operation_args = _OPERATION_ARGS.get(operation)
        if operation_args is None:
            raise TossWtsAdapterError("UNSUPPORTED_COMMAND")
        executable = self._config.executable
        config_dir = self._config.config_dir
        if not executable or not executable.is_file():
            raise TossWtsAdapterError("EXECUTABLE_MISSING")
        if not config_dir or not config_dir.is_dir():
            raise TossWtsAdapterError("CONFIG_DIR_MISSING")

        argv = [str(executable), "--config-dir", str(config_dir), "--output", "json", *operation_args, *arguments]
        try:
            completed = subprocess.run(
                argv,
                shell=False,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="strict",
                timeout=self._config.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise TossWtsAdapterError("TOSSCTL_TIMEOUT") from exc
        except OSError as exc:
            raise TossWtsAdapterError("NONZERO_EXIT") from exc
        if completed.returncode != 0:
            if operation == _PROFIT_DAILY and _is_known_tossctl_future_date_rejection(completed.stderr):
                raise TossWtsAdapterError(TOSSCTL_DATE_TIMEZONE_CONFLICT)
            raise TossWtsAdapterError("NONZERO_EXIT")
        try:
            parsed = json.loads(completed.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise TossWtsAdapterError("INVALID_JSON") from exc
        if not isinstance(parsed, (dict, list)):
            raise TossWtsAdapterError("INVALID_JSON")
        return parsed

    @staticmethod
    def _normalize_currency_values(value: Any) -> dict[str, int | float | None]:
        if not isinstance(value, dict) or "krw" not in value:
            raise TossWtsAdapterError("INVALID_SCHEMA")
        krw = value["krw"]
        usd = value.get("usd")
        if not _is_financial_number(krw) or (usd is not None and not _is_financial_number(usd)):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        return {"krw": krw, "usd": usd}

    @classmethod
    def _normalize_profit_category(cls, value: Any) -> dict[str, dict[str, int | float | None]]:
        if not isinstance(value, dict):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        required = ("amount", "earning_rate", "purchase_amount")
        if any(field not in value for field in required):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        return {field: cls._normalize_currency_values(value[field]) for field in required}

    @classmethod
    def _normalize_profit_overview(cls, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        required = (
            "sales",
            "dividend",
            "lending",
            "maturity",
            "interest",
            "earning_amount",
            "total_asset_amount",
            "fetched_at",
        )
        if any(field not in payload for field in required):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if not _is_financial_number(payload["interest"]) or not isinstance(payload["fetched_at"], str):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        return {
            "source": "toss_wts",
            "kind": "profit_overview",
            "fetched_at": payload["fetched_at"],
            "sales": cls._normalize_profit_category(payload["sales"]),
            "dividend": cls._normalize_profit_category(payload["dividend"]),
            "lending": cls._normalize_profit_category(payload["lending"]),
            "maturity": cls._normalize_profit_category(payload["maturity"]),
            "interest": payload["interest"],
            "earning_amount": cls._normalize_currency_values(payload["earning_amount"]),
            "total_asset_amount": cls._normalize_currency_values(payload["total_asset_amount"]),
        }

    @staticmethod
    def _validate_profit_daily_request(from_date: str, to_date: str, currency: str) -> tuple[str, str, str]:
        if not isinstance(from_date, str) or not isinstance(to_date, str) or not isinstance(currency, str):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if (
            len(from_date) != 10
            or len(to_date) != 10
            or from_date[4] != "-"
            or from_date[7] != "-"
            or to_date[4] != "-"
            or to_date[7] != "-"
        ):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        try:
            parsed_from = date.fromisoformat(from_date)
            parsed_to = date.fromisoformat(to_date)
        except ValueError as exc:
            raise TossWtsAdapterError("INVALID_SCHEMA") from exc
        if parsed_from > parsed_to:
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if currency not in _PROFIT_DAILY_CURRENCIES:
            raise TossWtsAdapterError("INVALID_SCHEMA")
        return from_date, to_date, currency

    @classmethod
    def _normalize_profit_daily_row(cls, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        string_fields = ("date", "market_type", "symbol", "product_code", "name")
        money_fields = ("profit_loss", "sell_amount", "buy_amount")
        required = (*string_fields, "quantity", "profit_rate", *money_fields)
        if any(field not in value for field in required):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if any(not isinstance(value[field], str) for field in string_fields):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if not _is_financial_number(value["quantity"]) or not _is_financial_number(value["profit_rate"]):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        return {
            **{field: value[field] for field in string_fields},
            "quantity": value["quantity"],
            "profit_loss": cls._normalize_currency_values(value["profit_loss"]),
            "profit_rate": value["profit_rate"],
            "sell_amount": cls._normalize_currency_values(value["sell_amount"]),
            "buy_amount": cls._normalize_currency_values(value["buy_amount"]),
        }

    @classmethod
    def _normalize_profit_daily(
        cls, payload: dict[str, Any] | list[Any], from_date: str, to_date: str, currency: str
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        required = ("currency", "stocks", "fetched_at")
        if any(field not in payload for field in required):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        if payload["currency"] != currency or not isinstance(payload["fetched_at"], str) or not isinstance(payload["stocks"], list):
            raise TossWtsAdapterError("INVALID_SCHEMA")
        return {
            "source": "toss_wts",
            "kind": "profit_daily",
            "from": from_date,
            "to": to_date,
            "currency": currency,
            "fetched_at": payload["fetched_at"],
            "stocks": [cls._normalize_profit_daily_row(row) for row in payload["stocks"]],
        }


def _is_financial_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
