from __future__ import annotations

import os
import asyncio
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.services.toss_wts_adapter import TossWtsAdapter, TossWtsAdapterError, TossWtsConfig


class TossWtsAdapterTests(unittest.TestCase):
    def configured(self, root: Path) -> TossWtsConfig:
        executable = root / "tossctl"
        executable.write_text("fake", encoding="utf-8")
        config_dir = root / "config"
        config_dir.mkdir()
        (config_dir / "session.json").write_text("FAKE_SESSION_SECRET", encoding="utf-8")
        return TossWtsConfig(True, executable, config_dir, "v0.50.3", 3)

    @staticmethod
    def profit_payload() -> dict:
        pair = {"krw": 101, "usd": 10.5}
        category = {"amount": pair, "earning_rate": {"krw": 2.5, "usd": 0.2}, "purchase_amount": {"krw": 99, "usd": 9.8}}
        return {
            "sales": category,
            "dividend": {"amount": {"krw": 3, "usd": 0.3}, "earning_rate": {"krw": 0.4, "usd": 0.04}, "purchase_amount": {"krw": 2}},
            "lending": {"amount": {"krw": 4, "usd": 0.4}, "earning_rate": {"krw": 0.5, "usd": 0.05}, "purchase_amount": {"krw": 3}},
            "maturity": {"amount": {"krw": 5, "usd": 0.5}, "earning_rate": {"krw": 0.6}, "purchase_amount": {"krw": 4}},
            "interest": 7,
            "earning_amount": {"krw": 120, "usd": 12.0},
            "total_asset_amount": {"krw": 1000, "usd": 100.0},
            "fetched_at": "2026-09-11T00:00:00Z",
        }

    def get_profit_with_payload(self, payload: dict, *, stderr: str = ""):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        adapter = TossWtsAdapter(self.configured(Path(temp.name)))
        completed = Mock(returncode=0, stdout=__import__("json").dumps(payload), stderr=stderr)
        return adapter, completed

    @staticmethod
    def profit_daily_row(*, product_code: str = "FAKE1", profit_loss: int = 12, name: str = "테스트종목") -> dict:
        return {
            "date": "2026-01-01",
            "market_type": "US",
            "symbol": "FAKE",
            "product_code": product_code,
            "name": name,
            "quantity": 1.0,
            "profit_loss": {"krw": profit_loss, "usd": 0.1},
            "profit_rate": -1.25,
            "sell_amount": {"krw": 100, "usd": 1.0},
            "buy_amount": {"krw": 88, "usd": 0.9},
        }

    def profit_daily_payload(self, stocks: list[dict] | None = None) -> dict:
        if stocks is None:
            first = self.profit_daily_row(product_code="DUPLICATE", profit_loss=12)
            duplicate_like = json.loads(json.dumps(first))
            negative = self.profit_daily_row(product_code="OTHER", profit_loss=-5, name="가상株")
            stocks = [first, duplicate_like, negative]
        return {
            "from": "20260101",
            "to": "20260910",
            "currency": "KRW",
            "fetched_at": "2026-09-11T00:00:00Z",
            "stocks": stocks,
        }

    def get_daily_with_payload(self, payload: dict):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        adapter = TossWtsAdapter(self.configured(Path(temp.name)))
        return adapter, Mock(returncode=0, stdout=json.dumps(payload), stderr="")

    def test_unconfigured_status_is_safe_and_does_not_spawn(self):
        with patch("app.services.toss_wts_adapter.subprocess.run") as run:
            status = TossWtsAdapter(TossWtsConfig(False, None, None, "v0.50.3", 3)).get_local_status()
        self.assertFalse(status["configured"])
        self.assertFalse(status["enabled"])
        self.assertEqual(status["error_code"], "NOT_CONFIGURED")
        run.assert_not_called()

    def test_missing_executable_and_config_directory_are_reported(self):
        missing = Path(tempfile.gettempdir()) / "wealth-wts-missing"
        executable_status = TossWtsAdapter(TossWtsConfig(True, missing, Path(tempfile.gettempdir()), "v0.50.3", 3)).get_local_status()
        config_status = TossWtsAdapter(TossWtsConfig(True, Path(__file__), missing, "v0.50.3", 3)).get_local_status()
        self.assertEqual(executable_status["error_code"], "EXECUTABLE_MISSING")
        self.assertEqual(config_status["error_code"], "CONFIG_DIR_MISSING")

    def test_local_status_only_checks_session_presence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self.configured(root)
            with patch("pathlib.Path.read_text", side_effect=AssertionError("session content read")):
                status = TossWtsAdapter(config).get_local_status()
        self.assertTrue(status["session_present"])
        self.assertTrue(status["adapter_ready"])
        self.assertNotIn("session_path", status)

    def test_auth_probe_uses_safe_argv_and_sanitizes_json(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = TossWtsAdapter(self.configured(Path(temp)))
            completed = Mock(returncode=0, stdout='{"active": true, "token": "FAKE_TOKEN_456"}', stderr="cookie=FAKE_SECRET_123")
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch("app.services.toss_wts_adapter.subprocess.run", return_value=completed) as run:
                result = adapter.probe_auth_status()
        self.assertTrue(result["authenticated"])
        self.assertNotIn("FAKE_TOKEN_456", repr(result))
        self.assertNotIn("FAKE_SECRET_123", repr(result))
        args, kwargs = run.call_args
        self.assertIsInstance(args[0], list)
        self.assertFalse(kwargs["shell"])
        self.assertEqual(args[0][-2:], ["auth", "status"])

    def test_invalid_json_nonzero_and_timeout_are_sanitized(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = TossWtsAdapter(self.configured(Path(temp)))
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch("app.services.toss_wts_adapter.subprocess.run", return_value=Mock(returncode=0, stdout="not-json", stderr="token=FAKE_TOKEN_456")):
                with self.assertRaises(TossWtsAdapterError) as invalid_json:
                    adapter.probe_auth_status()
                self.assertEqual(invalid_json.exception.code, "INVALID_JSON")
                self.assertNotIn("FAKE_TOKEN_456", str(invalid_json.exception))
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch("app.services.toss_wts_adapter.subprocess.run", return_value=Mock(returncode=7, stdout="", stderr="cookie=FAKE_SECRET_123")):
                with self.assertRaises(TossWtsAdapterError) as nonzero:
                    adapter.probe_auth_status()
                self.assertEqual(nonzero.exception.code, "NONZERO_EXIT")
                self.assertNotIn("FAKE_SECRET_123", str(nonzero.exception))
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch("app.services.toss_wts_adapter.subprocess.run", side_effect=subprocess.TimeoutExpired(["fake"], 3)):
                with self.assertRaisesRegex(TossWtsAdapterError, "^TOSSCTL_TIMEOUT$"):
                    adapter.probe_auth_status()

    def test_test_mode_blocks_auth_probe_before_subprocess(self):
        with tempfile.TemporaryDirectory() as temp:
            adapter = TossWtsAdapter(self.configured(Path(temp)))
            with patch.dict(os.environ, {"WEALTH_ENV": "test"}), patch("app.services.toss_wts_adapter.subprocess.run") as run:
                result = adapter.probe_auth_status()
        self.assertEqual(result["error_code"], "TEST_MODE_DISABLED")
        run.assert_not_called()

    def test_only_auth_status_operation_is_implemented(self):
        adapter = TossWtsAdapter(TossWtsConfig(False, None, None, "v0.50.3", 3))
        with self.assertRaisesRegex(TossWtsAdapterError, "^UNSUPPORTED_COMMAND$"):
            adapter._run_json("BUY")
        self.assertFalse(hasattr(adapter, "run_any_command"))
        self.assertFalse(hasattr(adapter, "get_dividends"))

    def test_profit_overview_uses_exact_safe_argv_and_normalizes_response(self):
        adapter, completed = self.get_profit_with_payload(self.profit_payload())
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", return_value=completed
        ) as run:
            result = adapter.get_profit_overview()
        self.assertEqual(result["source"], "toss_wts")
        self.assertEqual(result["kind"], "profit_overview")
        self.assertEqual(result["sales"]["amount"]["krw"], 101)
        self.assertEqual(result["sales"]["amount"]["usd"], 10.5)
        self.assertEqual(result["interest"], 7)
        args, kwargs = run.call_args
        self.assertEqual(args[0][-1:], ["profit"])
        self.assertNotIn("auth", args[0])
        self.assertFalse(kwargs["shell"])

    def test_profit_overview_preserves_missing_optional_usd_as_none(self):
        adapter, completed = self.get_profit_with_payload(self.profit_payload())
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", return_value=completed
        ):
            result = adapter.get_profit_overview()
        self.assertIsNone(result["dividend"]["purchase_amount"]["usd"])
        self.assertIsNone(result["maturity"]["earning_rate"]["usd"])

    def test_profit_overview_rejects_missing_root_or_malformed_category(self):
        missing_root = self.profit_payload()
        del missing_root["lending"]
        malformed = self.profit_payload()
        malformed["sales"] = []
        for payload in (missing_root, malformed):
            adapter, completed = self.get_profit_with_payload(payload)
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
                "app.services.toss_wts_adapter.subprocess.run", return_value=completed
            ):
                with self.assertRaisesRegex(TossWtsAdapterError, "^INVALID_SCHEMA$"):
                    adapter.get_profit_overview()

    def test_profit_overview_rejects_string_and_boolean_financial_values(self):
        string_value = self.profit_payload()
        string_value["sales"]["amount"]["krw"] = "101"
        bool_value = self.profit_payload()
        bool_value["interest"] = True
        for payload in (string_value, bool_value):
            adapter, completed = self.get_profit_with_payload(payload)
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
                "app.services.toss_wts_adapter.subprocess.run", return_value=completed
            ):
                with self.assertRaisesRegex(TossWtsAdapterError, "^INVALID_SCHEMA$"):
                    adapter.get_profit_overview()

    def test_profit_overview_reuses_safe_runner_errors_and_missing_session_check(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = self.configured(root)
            (config.config_dir / "session.json").unlink()
            with patch("app.services.toss_wts_adapter.subprocess.run") as run:
                with self.assertRaisesRegex(TossWtsAdapterError, "^SESSION_MISSING$"):
                    TossWtsAdapter(config).get_profit_overview()
            run.assert_not_called()
        adapter, _ = self.get_profit_with_payload(self.profit_payload())
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", return_value=Mock(returncode=2, stdout="", stderr="token=FAKE_SECRET_PROFIT_TEST")
        ):
            with self.assertRaises(TossWtsAdapterError) as failed:
                adapter.get_profit_overview()
        self.assertEqual(failed.exception.code, "NONZERO_EXIT")
        self.assertNotIn("FAKE_SECRET_PROFIT_TEST", str(failed.exception))

    def test_profit_overview_timeout_and_disabled_never_spawn(self):
        adapter, _ = self.get_profit_with_payload(self.profit_payload())
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", side_effect=subprocess.TimeoutExpired(["fake"], 3)
        ):
            with self.assertRaisesRegex(TossWtsAdapterError, "^TOSSCTL_TIMEOUT$"):
                adapter.get_profit_overview()
        with patch("app.services.toss_wts_adapter.subprocess.run") as run:
            with self.assertRaisesRegex(TossWtsAdapterError, "^NOT_CONFIGURED$"):
                TossWtsAdapter(TossWtsConfig(False, None, None, "v0.50.3", 3)).get_profit_overview()
        run.assert_not_called()

    def test_profit_overview_invalid_json_and_test_mode_never_spawn(self):
        adapter, _ = self.get_profit_with_payload(self.profit_payload())
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", return_value=Mock(returncode=0, stdout="not-json", stderr="")
        ):
            with self.assertRaisesRegex(TossWtsAdapterError, "^INVALID_JSON$"):
                adapter.get_profit_overview()
        with patch.dict(os.environ, {"WEALTH_ENV": "test"}), patch(
            "app.services.toss_wts_adapter.subprocess.run"
        ) as run:
            with self.assertRaisesRegex(TossWtsAdapterError, "^TEST_MODE_DISABLED$"):
                adapter.get_profit_overview()
        run.assert_not_called()

    def test_profit_daily_uses_exact_argv_and_preserves_rows_without_dedup(self):
        payload = self.profit_daily_payload()
        del payload["stocks"][2]["buy_amount"]["usd"]
        adapter, completed = self.get_daily_with_payload(payload)
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", return_value=completed
        ) as run:
            result = adapter.get_profit_daily("2026-01-01", "2026-09-10")
        self.assertEqual(result["source"], "toss_wts")
        self.assertEqual(result["kind"], "profit_daily")
        self.assertEqual(len(result["stocks"]), 3)
        self.assertEqual(result["stocks"][0]["product_code"], "DUPLICATE")
        self.assertEqual(result["stocks"][1]["product_code"], "DUPLICATE")
        self.assertLess(result["stocks"][2]["profit_loss"]["krw"], 0)
        self.assertIsNone(result["stocks"][2]["buy_amount"]["usd"])
        self.assertEqual(result["stocks"][0]["name"], "테스트종목")
        self.assertEqual(result["stocks"][2]["name"], "가상株")
        args, kwargs = run.call_args
        self.assertEqual(
            args[0][-8:],
            ["profit", "daily", "--from", "2026-01-01", "--to", "2026-09-10", "--currency", "KRW"],
        )
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["errors"], "strict")

    def test_profit_daily_accepts_empty_stocks_and_zero_values(self):
        adapter, completed = self.get_daily_with_payload(self.profit_daily_payload([]))
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", return_value=completed
        ):
            self.assertEqual(adapter.get_profit_daily("2026-01-01", "2026-09-10")["stocks"], [])
        zero = self.profit_daily_row()
        zero.update({"quantity": 0, "profit_rate": 0, "profit_loss": {"krw": 0, "usd": 0}, "sell_amount": {"krw": 0, "usd": 0}, "buy_amount": {"krw": 0, "usd": 0}})
        adapter, completed = self.get_daily_with_payload(self.profit_daily_payload([zero]))
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", return_value=completed
        ):
            self.assertEqual(adapter.get_profit_daily("2026-01-01", "2026-09-10")["stocks"][0]["quantity"], 0)

    def test_profit_daily_invalid_currency_or_dates_prevent_subprocess(self):
        adapter = TossWtsAdapter(TossWtsConfig(False, None, None, "v0.50.3", 3))
        invalid_args = (
            ("2026-01-01", "2026-09-10", "EUR"),
            ("2026-01-01", "2026-09-10", "KRW; buy"),
            ("2026/01/01", "2026-09-10", "KRW"),
            ("2026-02-30", "2026-09-10", "KRW"),
            ("2026-09-10", "2026-01-01", "KRW"),
        )
        with patch("app.services.toss_wts_adapter.subprocess.run") as run:
            for args in invalid_args:
                with self.assertRaisesRegex(TossWtsAdapterError, "^INVALID_SCHEMA$"):
                    adapter.get_profit_daily(*args)
        run.assert_not_called()

    def test_profit_daily_rejects_malformed_rows_and_financial_types(self):
        cases = []
        malformed_stocks = self.profit_daily_payload()
        malformed_stocks["stocks"] = {}
        cases.append(malformed_stocks)
        missing_field = self.profit_daily_payload([self.profit_daily_row()])
        del missing_field["stocks"][0]["product_code"]
        cases.append(missing_field)
        money_pair = self.profit_daily_payload([self.profit_daily_row()])
        money_pair["stocks"][0]["profit_loss"] = []
        cases.append(money_pair)
        numeric_string = self.profit_daily_payload([self.profit_daily_row()])
        numeric_string["stocks"][0]["profit_loss"]["krw"] = "12"
        cases.append(numeric_string)
        boolean_value = self.profit_daily_payload([self.profit_daily_row()])
        boolean_value["stocks"][0]["sell_amount"]["krw"] = True
        cases.append(boolean_value)
        for payload in cases:
            adapter, completed = self.get_daily_with_payload(payload)
            with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
                "app.services.toss_wts_adapter.subprocess.run", return_value=completed
            ):
                with self.assertRaisesRegex(TossWtsAdapterError, "^INVALID_SCHEMA$"):
                    adapter.get_profit_daily("2026-01-01", "2026-09-10")

    def test_profit_daily_safe_runner_errors_and_disabled_test_mode(self):
        adapter, _ = self.get_daily_with_payload(self.profit_daily_payload())
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", return_value=Mock(returncode=0, stdout="bad-json", stderr="")
        ):
            with self.assertRaisesRegex(TossWtsAdapterError, "^INVALID_JSON$"):
                adapter.get_profit_daily("2026-01-01", "2026-09-10")
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", return_value=Mock(returncode=1, stdout="", stderr="token=FAKE_SECRET_DAILY")
        ):
            with self.assertRaises(TossWtsAdapterError) as failed:
                adapter.get_profit_daily("2026-01-01", "2026-09-10")
        self.assertEqual(failed.exception.code, "NONZERO_EXIT")
        self.assertNotIn("FAKE_SECRET_DAILY", str(failed.exception))
        with patch.dict(os.environ, {"WEALTH_ENV": "test"}), patch(
            "app.services.toss_wts_adapter.subprocess.run"
        ) as run:
            with self.assertRaisesRegex(TossWtsAdapterError, "^TEST_MODE_DISABLED$"):
                adapter.get_profit_daily("2026-01-01", "2026-09-10")
        run.assert_not_called()

    def test_profit_daily_timeout_missing_session_and_disabled_are_safe(self):
        adapter, _ = self.get_daily_with_payload(self.profit_daily_payload())
        with patch.dict(os.environ, {"WEALTH_ENV": "production"}), patch(
            "app.services.toss_wts_adapter.subprocess.run", side_effect=subprocess.TimeoutExpired(["fake"], 3)
        ):
            with self.assertRaisesRegex(TossWtsAdapterError, "^TOSSCTL_TIMEOUT$"):
                adapter.get_profit_daily("2026-01-01", "2026-09-10")
        with tempfile.TemporaryDirectory() as temp:
            config = self.configured(Path(temp))
            (config.config_dir / "session.json").unlink()
            with patch("app.services.toss_wts_adapter.subprocess.run") as run:
                with self.assertRaisesRegex(TossWtsAdapterError, "^SESSION_MISSING$"):
                    TossWtsAdapter(config).get_profit_daily("2026-01-01", "2026-09-10")
            run.assert_not_called()
        with patch("app.services.toss_wts_adapter.subprocess.run") as run:
            with self.assertRaisesRegex(TossWtsAdapterError, "^NOT_CONFIGURED$"):
                TossWtsAdapter(TossWtsConfig(False, None, None, "v0.50.3", 3)).get_profit_daily(
                    "2026-01-01", "2026-09-10"
                )
        run.assert_not_called()

    def test_status_route_uses_local_status_without_auth_probe(self):
        from app import main

        local_status = {"enabled": False, "configured": False, "error_code": "NOT_CONFIGURED"}
        adapter = Mock()
        adapter.get_local_status.return_value = local_status
        with patch("app.main.get_current_username", return_value="fixture"), patch(
            "app.main.check_wts_feed_static_authorization", return_value=Mock(authorized=True)
        ), patch(
            "app.main.TossWtsAdapter", return_value=adapter
        ):
            result = asyncio.run(main.toss_wts_local_status(Mock()))
        self.assertEqual(result, local_status)
        adapter.get_local_status.assert_called_once_with()
        adapter.probe_auth_status.assert_not_called()
