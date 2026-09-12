"""Optional, read-only bridge to a locally provisioned tossctl binary.

This module never installs tossctl, launches a browser, or reads a session file.
It is deliberately limited to local status and an explicit auth-status probe;
financial WTS operations belong to later, separately reviewed phases.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.services.network_policy import is_test_mode


EXPECTED_TOSSCTL_VERSION = "v0.50.3"
DEFAULT_TIMEOUT_SECONDS = 20
_AUTH_STATUS = "AUTH_STATUS"
_PROFIT_OVERVIEW = "PROFIT_OVERVIEW"
_PROFIT_DAILY = "PROFIT_DAILY"
_OPERATION_ARGS = {
    _AUTH_STATUS: ("auth", "status"),
    _PROFIT_OVERVIEW: ("profit",),
    _PROFIT_DAILY: ("profit", "daily"),
}
_PROFIT_DAILY_CURRENCIES = frozenset({"KRW", "USD"})

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


def _enabled_from_environment() -> bool:
    return os.getenv("WEALTH_TOSS_WTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _timeout_from_environment() -> int:
    try:
        return max(1, int(os.getenv("WEALTH_TOSSCTL_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class TossWtsConfig:
    enabled: bool
    executable: Path | None
    config_dir: Path | None
    expected_version: str
    timeout_seconds: int

    @classmethod
    def from_environment(cls) -> "TossWtsConfig":
        executable = os.getenv("WEALTH_TOSSCTL_PATH", "").strip()
        config_dir = os.getenv("WEALTH_TOSSCTL_CONFIG_DIR", "").strip()
        return cls(
            enabled=_enabled_from_environment(),
            executable=Path(executable).expanduser() if executable else None,
            config_dir=Path(config_dir).expanduser() if config_dir else None,
            expected_version=os.getenv("WEALTH_TOSSCTL_EXPECTED_VERSION", EXPECTED_TOSSCTL_VERSION).strip() or EXPECTED_TOSSCTL_VERSION,
            timeout_seconds=_timeout_from_environment(),
        )


class TossWtsAdapter:
    """Lazy, read-only tossctl adapter with a deliberately closed command set."""

    def __init__(self, config: TossWtsConfig | None = None):
        self._config = config or TossWtsConfig.from_environment()

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
        self._require_ready()
        if is_test_mode():
            raise TossWtsAdapterError("TEST_MODE_DISABLED")
        payload = self._run_json(
            _PROFIT_DAILY,
            ("--from", normalized_from, "--to", normalized_to, "--currency", normalized_currency),
        )
        return self._normalize_profit_daily(payload, normalized_from, normalized_to, normalized_currency)

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
        if parsed_from > parsed_to or parsed_to > date.today():
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
