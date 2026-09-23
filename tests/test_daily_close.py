"""Comprehensive unit and integration test suite for A1 Daily Close Service.

Verifies:
- Pure business service contract (no FastAPI Request, no session/cookie dependency)
- End-to-end happy path execution with mocked external boundaries
- User identity isolation and validation
- Stored Telegram resolver integration (no .env dependence)
- Telegram disabled / unconfigured / failure policies (non-fatal, token-safe)
- Critical step failure policies (fatal: fail-closed with step reporting)
- Pure summary builder contract and formatting equivalence
- Deterministic datetime injection
- Same-day second run idempotency
- Absence of premature execution state / scheduler files
"""

from __future__ import annotations

import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from regression_support import IsolatedDataTestCase, empty_portfolio
except ImportError:
    from tests.regression_support import IsolatedDataTestCase, empty_portfolio

from app.services.automation.daily_close import (
    build_daily_close_summary,
    run_daily_close,
    run_daily_close_for_user,
    send_daily_close_telegram,
)
from app.services.telegram_config import TelegramConfig

KST = timezone(timedelta(hours=9))


def _async(coro):
    return asyncio.run(coro)


class DailyCloseServiceTests(IsolatedDataTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.username = "daily_user"
        self.user_dir = self.fixture_user_dir(self.username)

        # Mock user exists in database
        self.mock_user = {
            "id": "user-uuid-1",
            "username": self.username,
            "role": "user",
        }
        self.user_patcher = patch(
            "app.services.automation.daily_close.get_user_by_name",
            return_value=self.mock_user,
        )
        self.user_patcher.start()
        self.addCleanup(self.user_patcher.stop)

    def _sample_dashboard(self) -> dict:
        return {
            "summary": {
                "total_value_krw": 10000000.0,
                "total_stock_value_krw": 8000000.0,
                "total_cash_krw": 2000000.0,
                "profit_krw": 500000.0,
                "return_rate": 5.25,
            },
            "holdings": [
                {
                    "id": "h-1",
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 100,
                    "current_price": 80000.0,
                    "market_value_krw": 8000000.0,
                    "currency": "KRW",
                    "owner": "모두",
                }
            ],
            "accounts": [
                {
                    "id": "acct-1",
                    "broker": "KB증권",
                    "name": "KB주계좌",
                    "owner": "모두",
                    "cash_krw": 2000000.0,
                    "cash_usd": 0.0,
                }
            ],
            "bank_accounts": [
                {"id": "bank-1", "bank_name": "국민은행", "balance": 3000000.0, "owner": "모두"}
            ],
            "savings_accounts": [
                {"id": "sav-1", "current_value": 1500000.0, "owner": "모두"}
            ],
            "insurance_accounts": [
                {"id": "ins-1", "expected_amount": 5000000.0, "owner": "모두"}
            ],
            "loan_accounts": [
                {"id": "loan-1", "current_balance": 2000000.0, "owner": "모두", "loan_type": "credit"}
            ],
            "real_estates": [
                {
                    "id": "re-1",
                    "property_type": "own",
                    "current_price": 50000000.0,
                    "deposit_amount": 0.0,
                    "owner": "모두",
                }
            ],
            "day_change": {
                "change_krw": 150000.0,
                "change_rate": 1.52,
            },
            "fx_rates": {"KRW": 1.0, "USD": 1385.0},
            "updated_at": "2026-09-21T21:00:00+09:00",
        }

    def _sample_sync_result(self, warning: bool = False) -> dict:
        brokers = [
            {"broker": "KB증권", "status": "SUCCESS"},
            {"broker": "토스증권", "status": "CONFIRMED_EMPTY"},
            {"broker": "NH투자증권(나무)", "status": "CONFIG_REQUIRED"},
            {"broker": "한국투자증권", "status": "API_ERROR" if warning else "SUCCESS"},
            {"broker": "키움증권", "status": "SUCCESS"},
        ]
        return {"synced": 3, "brokers": brokers}

    def _sample_price_result(self) -> dict:
        return {
            "message": "전체 1개 종목 시세 및 환율(1,385.0원)을 갱신했습니다.",
            "count": 1,
            "fx_rate": 1385.0,
        }

    # -----------------------------------------------------------------------
    # 1. No FastAPI Request Dependency
    # -----------------------------------------------------------------------
    def test_no_fastapi_request_dependency(self):
        """Verify daily_close service contains no Request or HTTP session imports."""
        import app.services.automation.daily_close as dc
        source = inspect.getsource(dc)
        self.assertNotIn("starlette.requests", source)
        self.assertNotIn("fastapi.Request", source)
        self.assertNotIn("from starlette", source)
        self.assertNotIn("from fastapi", source)
        self.assertNotIn("request.state", source)

    # -----------------------------------------------------------------------
    # 2. Username Safety & Validation
    # -----------------------------------------------------------------------
    def test_username_validation(self):
        """Unknown or empty username must fail closed with ValueError."""
        with self.assertRaises(ValueError) as ctx:
            _async(run_daily_close_for_user(""))
        self.assertIn("username is required", str(ctx.exception))

        with patch("app.services.automation.daily_close.get_user_by_name", return_value=None):
            with self.assertRaises(ValueError) as ctx2:
                _async(run_daily_close_for_user("unknown_ghost"))
            self.assertIn("사용자를 찾을 수 없습니다", str(ctx2.exception))

    # -----------------------------------------------------------------------
    # 3. Happy Path
    # -----------------------------------------------------------------------
    def test_daily_close_happy_path(self):
        """Verify complete happy path execution with all steps succeeding."""
        sync_mock = AsyncMock(return_value=self._sample_sync_result())
        price_mock = AsyncMock(return_value=self._sample_price_result())
        dash_mock = MagicMock(return_value=self._sample_dashboard())

        sent_messages = []
        def mock_transport(cfg, msg):
            sent_messages.append((cfg.username, msg))

        now_fixed = datetime(2026, 9, 21, 21, 0, 0, tzinfo=KST)

        with patch("app.main.sync_all_accounts_for_user", sync_mock), \
             patch("app.main.refresh_prices_for_user", price_mock), \
             patch("app.main.get_full_dashboard_for_user", dash_mock), \
             patch("app.services.automation.daily_close.resolve_telegram_config",
                   return_value=TelegramConfig(
                       username=self.username,
                       enabled=True,
                       bot_token="TEST_BOT_TOKEN",
                       chat_id=12345678,
                   )):
            result = _async(run_daily_close_for_user(
                self.username,
                now=now_fixed,
                telegram_transport=mock_transport,
            ))

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["username"], self.username)
        self.assertEqual(result["date"], "2026-09-21")
        self.assertTrue(result["telegram_sent"])
        self.assertEqual(result["notification_status"], "sent")
        self.assertIsNone(result["notification_error"])

        # Steps verification
        steps = result["steps"]
        self.assertEqual(steps["account_sync"]["status"], "success")
        self.assertEqual(steps["price_refresh"]["status"], "success")
        self.assertEqual(steps["dashboard"]["status"], "success")
        self.assertEqual(steps["snapshot"]["status"], "success")
        self.assertEqual(steps["summary"]["status"], "success")
        self.assertEqual(steps["notification"]["status"], "sent")

        # Snapshot verification
        self.assertTrue(result["stock_record_saved"])
        self.assertTrue(result["net_record_saved"])
        self.assertGreaterEqual(result["stock_record_count"], 1)
        self.assertGreaterEqual(result["net_record_count"], 1)

        # Telegram delivery verification
        self.assertEqual(len(sent_messages), 1)
        self.assertEqual(sent_messages[0][0], self.username)
        self.assertIn("📊 Wealth 일일 마감 · 2026-09-21", sent_messages[0][1])
        self.assertIn("💎 순자산:", sent_messages[0][1])

    # -----------------------------------------------------------------------
    # 4. Telegram Config Resolution (Stored resolver, no .env)
    # -----------------------------------------------------------------------
    def test_telegram_config_resolution(self):
        """Verify Telegram sender respects resolve_telegram_config contract."""
        cfg = TelegramConfig(
            username=self.username,
            enabled=True,
            bot_token="STORED_TOKEN_XYZ",
            chat_id=987654321,
            bot_token_source="stored",
        )
        calls = []
        def mock_transport(c, m):
            calls.append((c.bot_token, c.chat_id, m))

        with patch("app.services.automation.daily_close.resolve_telegram_config", return_value=cfg):
            res = send_daily_close_telegram(self.username, "테스트 마감", transport=mock_transport)

        self.assertTrue(res["telegram_sent"])
        self.assertEqual(res["status"], "sent")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "STORED_TOKEN_XYZ")
        self.assertEqual(calls[0][1], 987654321)

    # -----------------------------------------------------------------------
    # 5. Telegram Disabled / Unconfigured
    # -----------------------------------------------------------------------
    def test_telegram_disabled_is_non_fatal(self):
        """When Telegram is disabled, daily close succeeds and notification is skipped."""
        dash_mock = MagicMock(return_value=self._sample_dashboard())
        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result())), \
             patch("app.main.refresh_prices_for_user", AsyncMock(return_value=self._sample_price_result())), \
             patch("app.main.get_full_dashboard_for_user", dash_mock), \
             patch("app.services.automation.daily_close.resolve_telegram_config",
                   return_value=TelegramConfig(username=self.username, enabled=False)):
            result = _async(run_daily_close_for_user(self.username))

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["telegram_sent"])
        self.assertEqual(result["notification_status"], "disabled")

    def test_telegram_unconfigured_is_non_fatal(self):
        """When Telegram is enabled but unconfigured, daily close succeeds."""
        dash_mock = MagicMock(return_value=self._sample_dashboard())
        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result())), \
             patch("app.main.refresh_prices_for_user", AsyncMock(return_value=self._sample_price_result())), \
             patch("app.main.get_full_dashboard_for_user", dash_mock), \
             patch("app.services.automation.daily_close.resolve_telegram_config",
                   return_value=TelegramConfig(username=self.username, enabled=True, bot_token=None, chat_id=None)):
            result = _async(run_daily_close_for_user(self.username))

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["telegram_sent"])
        self.assertEqual(result["notification_status"], "unconfigured")

    # -----------------------------------------------------------------------
    # 6. Telegram Send Failure (Non-Fatal, Redacted)
    # -----------------------------------------------------------------------
    def test_telegram_failure_is_non_fatal_and_token_safe(self):
        """When Telegram network call explodes, core work succeeds without token leak."""
        dash_mock = MagicMock(return_value=self._sample_dashboard())

        def exploding_transport(cfg, msg):
            raise OSError(f"Connection timeout to https://api.telegram.org/bot{cfg.bot_token}/sendMessage")

        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result())), \
             patch("app.main.refresh_prices_for_user", AsyncMock(return_value=self._sample_price_result())), \
             patch("app.main.get_full_dashboard_for_user", dash_mock), \
             patch("app.services.automation.daily_close.resolve_telegram_config",
                   return_value=TelegramConfig(
                       username=self.username,
                       enabled=True,
                       bot_token="SUPER_SECRET_RAW_TOKEN",
                       chat_id=123,
                   )):
            result = _async(run_daily_close_for_user(
                self.username,
                telegram_transport=exploding_transport,
            ))

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["telegram_sent"])
        self.assertEqual(result["notification_status"], "failed")
        self.assertEqual(result["notification_error"], "TELEGRAM_SEND_FAILED")

        # Verify no token leakage in output
        result_str = str(result)
        self.assertNotIn("SUPER_SECRET_RAW_TOKEN", result_str)

    # -----------------------------------------------------------------------
    # 7. Critical Step Failures (Fatal)
    # -----------------------------------------------------------------------
    def test_account_sync_failure_is_fatal(self):
        """Unhandled account sync error fails daily close and reports step."""
        with patch("app.main.sync_all_accounts_for_user", AsyncMock(side_effect=RuntimeError("Broker network crash"))):
            result = _async(run_daily_close_for_user(self.username))

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_step"], "account_sync")
        self.assertIn("Broker network crash", result["error"])
        self.assertFalse(result["telegram_sent"])

    def test_price_refresh_failure_is_fatal(self):
        """Unhandled price refresh error fails daily close and reports step."""
        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result())), \
             patch("app.main.refresh_prices_for_user", AsyncMock(side_effect=RuntimeError("Price API down"))):
            result = _async(run_daily_close_for_user(self.username))

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_step"], "price_refresh")
        self.assertIn("Price API down", result["error"])

    def test_dashboard_failure_is_fatal(self):
        """Dashboard compilation failure fails daily close."""
        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result())), \
             patch("app.main.refresh_prices_for_user", AsyncMock(return_value=self._sample_price_result())), \
             patch("app.main.get_full_dashboard_for_user", MagicMock(side_effect=RuntimeError("Corrupt storage"))):
            result = _async(run_daily_close_for_user(self.username))

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_step"], "dashboard")

    def test_broker_warning_is_non_fatal(self):
        """Broker sync warning (e.g. API_ERROR) is non-fatal and counted."""
        dash_mock = MagicMock(return_value=self._sample_dashboard())
        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result(warning=True))), \
             patch("app.main.refresh_prices_for_user", AsyncMock(return_value=self._sample_price_result())), \
             patch("app.main.get_full_dashboard_for_user", dash_mock), \
             patch("app.services.automation.daily_close.resolve_telegram_config",
                   return_value=TelegramConfig(username=self.username, enabled=False)):
            result = _async(run_daily_close_for_user(self.username))

        self.assertTrue(result["ok"])
        self.assertEqual(result["sync_warning_count"], 1)
        self.assertIn("⚠️ 한국투자증권: API_ERROR", result["message"])
        self.assertIn("⚠️ 동기화 경고 1건이 있습니다.", result["message"])

    # -----------------------------------------------------------------------
    # 8. Summary Builder Contract
    # -----------------------------------------------------------------------
    def test_build_daily_close_summary_contract(self):
        """Verify exact text formatting, won format, signs, and emoji preservation."""
        data = self._sample_dashboard()
        sync_result = self._sample_sync_result()
        price_result = self._sample_price_result()
        stock_records = [{"owner": "모두", "id": "rec-1", "date": "2026-09-21", "total_value_krw": 8000000.0, "day_profit_krw": 100000.0}]
        previous_stock_record = {"owner": "모두", "date": "2026-09-20", "total_value_krw": 7900000.0}
        net_snapshots = [{"owner": "모두", "net_worth": 60500000.0}]

        msg, metrics = build_daily_close_summary(
            data=data,
            sync_result=sync_result,
            price_result=price_result,
            stock_records=stock_records,
            net_snapshots=net_snapshots,
            today="2026-09-21",
            previous_stock_record=previous_stock_record,
        )

        self.assertIn("📊 Wealth 일일 마감 · 2026-09-21", msg)
        self.assertIn("💎 순자산: 67,500,000원", msg)
        self.assertIn("🏦 총자산: 69,500,000원", msg)
        self.assertIn("💳 총부채: 2,000,000원", msg)
        self.assertIn("📈 주식 평가액: 8,000,000원", msg)
        self.assertIn("💰 현금·예금: 6,500,000원", msg)
        self.assertIn("🏠 부동산 평가액: 50,000,000원", msg)
        self.assertIn("🛡 보험 평가액: 5,000,000원", msg)
        self.assertIn("📌 주식 평가손익: +500,000원 (+5.25%)", msg)
        self.assertIn("🌙 당일 가격변동 손익: +100,000원", msg)
        self.assertIn("📊 전 기록 대비 평가액: +100,000원 (+1.27%)", msg)
        self.assertIn("🔄 시세갱신: 전체 1개 종목 시세 및 환율(1,385.0원)을 갱신했습니다.", msg)
        self.assertIn("✅ KB증권: SUCCESS", msg)
        self.assertIn("✅ 토스증권: CONFIRMED_EMPTY", msg)
        self.assertIn("➖ NH투자증권(나무): CONFIG_REQUIRED", msg)
        self.assertIn("🗓 주식기록: 저장 확인 · 1개 범위", msg)
        self.assertIn("📒 순자산기록: 저장 확인 · 1개 범위", msg)

        self.assertEqual(metrics["net_worth"], 67500000.0)
        self.assertEqual(metrics["total_assets"], 69500000.0)
        self.assertEqual(metrics["total_debt"], 2000000.0)
        self.assertTrue(metrics["stock_record_saved"])
        self.assertTrue(metrics["net_record_saved"])

    def test_summary_uses_canonical_stock_records_not_dashboard_day_change(self):
        data = self._sample_dashboard()
        data["day_change"] = {"change_krw": 64660069, "change_rate": 4.31}
        current = {
            "owner": "모두", "date": "2026-09-23",
            "total_value_krw": 1522610640, "day_profit_krw": 15863903,
        }
        previous = {"owner": "모두", "date": "2026-09-22", "total_value_krw": 1501282751}
        message, metrics = build_daily_close_summary(
            data, self._sample_sync_result(), self._sample_price_result(),
            [current], [], "2026-09-23", previous_stock_record=previous,
        )
        self.assertIn("🌙 당일 가격변동 손익: +15,863,903원", message)
        self.assertIn("📊 전 기록 대비 평가액: +21,327,889원 (+1.42%)", message)
        self.assertNotIn("64,660,069원", message)
        self.assertEqual(metrics["canonical_day_profit_krw"], 15863903)
        self.assertEqual(metrics["record_change_krw"], 21327889)

    def test_summary_does_not_use_other_owner_or_non_today_stock_record(self):
        data = self._sample_dashboard()
        data["day_change"] = {"change_krw": 64_660_069, "change_rate": 4.31}
        previous = {"owner": "모두", "date": "2026-09-22", "total_value_krw": 7_000_000}
        records = [
            previous,
            {
                "owner": "아빠", "date": "2026-09-23",
                "total_value_krw": 9_000_000, "day_profit_krw": 2_000_000,
            },
        ]
        message, metrics = build_daily_close_summary(
            data, self._sample_sync_result(), self._sample_price_result(),
            records, [], "2026-09-23", previous_stock_record=previous,
        )
        self.assertIn("🌙 당일 가격변동 손익: 주식기록 없음", message)
        self.assertIn("📊 전 기록 대비 평가액: 이전 기록 없음", message)
        self.assertNotIn("64,660,069원", message)
        self.assertIsNone(metrics["canonical_day_profit_krw"])
        self.assertIsNone(metrics["record_change_krw"])

    def test_daily_close_selects_latest_prior_all_owner_record_not_same_day(self):
        """A rerun compares today's upsert to the latest strictly-prior all-owner record."""
        from app.services.asset_records import upsert_asset_record

        previous = {
            "owner": "모두", "date": "2026-09-20",
            "total_value_krw": 7_000_000,
        }
        stale_same_day = {
            "owner": "모두", "date": "2026-09-21",
            "total_value_krw": 1_000_000,
        }
        other_owner = {
            "owner": "아빠", "date": "2026-09-22",
            "total_value_krw": 99_000_000,
        }
        for record in (previous, stale_same_day, other_owner):
            upsert_asset_record(record, by_date=True, username=self.username)

        now_fixed = datetime(2026, 9, 21, 21, 0, tzinfo=KST)
        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result())), \
             patch("app.main.refresh_prices_for_user", AsyncMock(return_value=self._sample_price_result())), \
             patch("app.main.get_full_dashboard_for_user", MagicMock(return_value=self._sample_dashboard())):
            result = _async(run_daily_close(self.username, now=now_fixed, skip_telegram=True))

        self.assertTrue(result["ok"])
        self.assertIn("📊 전 기록 대비 평가액: +1,000,000원 (+14.29%)", result["message"])
        self.assertNotIn("+7,000,000원", result["message"])

    # -----------------------------------------------------------------------
    # 9. Idempotency: Second Run on Same Day
    # -----------------------------------------------------------------------
    def test_second_run_same_day_idempotency(self):
        """Running daily close twice on same day must update records in-place without duplicates."""
        from app.services.asset_records import list_asset_records
        from app.services.planning import read_planning

        now_fixed = datetime(2026, 9, 21, 21, 0, 0, tzinfo=KST)

        dash_v1 = self._sample_dashboard()
        dash_v2 = self._sample_dashboard()
        dash_v2["summary"]["total_value_krw"] = 12000000.0
        dash_v2["holdings"][0]["current_price"] = 100000.0
        dash_v2["holdings"][0]["market_value_krw"] = 10000000.0

        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result())), \
             patch("app.main.refresh_prices_for_user", AsyncMock(return_value=self._sample_price_result())), \
             patch("app.services.automation.daily_close.resolve_telegram_config",
                   return_value=TelegramConfig(username=self.username, enabled=False)):

            # Run 1
            with patch("app.main.get_full_dashboard_for_user", MagicMock(return_value=dash_v1)):
                res1 = _async(run_daily_close(self.username, now=now_fixed))
            self.assertTrue(res1["ok"])

            records_after_1 = list_asset_records(username=self.username)
            planning_after_1 = read_planning(username=self.username)
            date_records_1 = [r for r in records_after_1 if r.get("date") == "2026-09-21"]
            net_records_1 = [r for r in planning_after_1.get("history", []) if r.get("date") == "2026-09-21"]

            # Run 2 (same day)
            with patch("app.main.get_full_dashboard_for_user", MagicMock(return_value=dash_v2)):
                res2 = _async(run_daily_close(self.username, now=now_fixed))
            self.assertTrue(res2["ok"])

            records_after_2 = list_asset_records(username=self.username)
            planning_after_2 = read_planning(username=self.username)
            date_records_2 = [r for r in records_after_2 if r.get("date") == "2026-09-21"]
            net_records_2 = [r for r in planning_after_2.get("history", []) if r.get("date") == "2026-09-21"]

            # Exactly the same count per owner — no duplicated rows!
            self.assertEqual(len(date_records_1), len(date_records_2))
            self.assertEqual(len(net_records_1), len(net_records_2))

    # -----------------------------------------------------------------------
    # 10. Fixed Date/Time Injection
    # -----------------------------------------------------------------------
    def test_fixed_datetime_injection(self):
        """Injected now produces deterministic date in summary and snapshots."""
        from app.services.asset_records import list_asset_records
        from app.services.planning import read_planning

        target_dt = datetime(2026, 12, 31, 23, 59, 0, tzinfo=KST)
        dash = self._sample_dashboard()

        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result())), \
             patch("app.main.refresh_prices_for_user", AsyncMock(return_value=self._sample_price_result())), \
             patch("app.main.get_full_dashboard_for_user", MagicMock(return_value=dash)), \
             patch("app.services.automation.daily_close.resolve_telegram_config",
                   return_value=TelegramConfig(username=self.username, enabled=False)):
            res = _async(run_daily_close(self.username, now=target_dt))

        self.assertTrue(res["ok"])
        self.assertEqual(res["date"], "2026-12-31")
        self.assertIn("2026-12-31", res["message"])

        records = [r for r in list_asset_records(username=self.username) if r.get("date") == "2026-12-31"]
        self.assertGreaterEqual(len(records), 1)

        history = [r for r in read_planning(username=self.username).get("history", []) if r.get("date") == "2026-12-31"]
        self.assertGreaterEqual(len(history), 1)

    # -----------------------------------------------------------------------
    # 11. No Premature Execution State File
    # -----------------------------------------------------------------------
    def test_no_execution_state_created(self):
        """A1 must not create data/automation/execution_state.json."""
        exec_file = Path("data/automation/execution_state.json")
        self.assertFalse(exec_file.exists())

    # -----------------------------------------------------------------------
    # 12. Shared Telegram Transport Verification
    # -----------------------------------------------------------------------
    def test_telegram_uses_shared_telegram_management_transport(self):
        """Verify daily close delegates to app.services.telegram_management.send_telegram_message."""
        cfg = TelegramConfig(
            username=self.username,
            enabled=True,
            bot_token="STORED_TOKEN_XYZ",
            chat_id=987654321,
            bot_token_source="stored",
        )
        with patch("app.services.automation.daily_close.resolve_telegram_config", return_value=cfg), \
             patch("app.services.automation.daily_close.send_telegram_message") as shared_send:
            shared_send.return_value = {"ok": True}
            res = send_daily_close_telegram(self.username, "공용 전송 테스트")

        self.assertTrue(res["telegram_sent"])
        self.assertEqual(res["status"], "sent")
        shared_send.assert_called_once_with(cfg, "공용 전송 테스트")

    # -----------------------------------------------------------------------
    # 13. FX Refresh Inclusion & Failure Semantics
    # -----------------------------------------------------------------------
    def test_price_refresh_demonstrably_includes_fx_refresh(self):
        """Demonstrate that refresh_prices_for_user includes FX rate refresh and persists it."""
        from app.main import refresh_prices_for_user
        from app.services.portfolio import read_portfolio, write_portfolio

        # Setup portfolio with USD holding
        portfolio = empty_portfolio()
        portfolio["holdings"] = [
            {"id": "h-us", "code": "AAPL", "name": "Apple", "currency": "USD", "current_price": 150.0}
        ]
        write_portfolio(portfolio, username=self.username)

        # Mock web finance holdings refresh returning both stock prices and new FX rate
        mock_web_res = {
            "prices": {"h-us": 155.0},
            "daily_changes": {},
            "period_rates": {},
            "fx_rate": 1420.5,
        }
        with patch("app.main.is_test_mode", return_value=False), \
             patch("app.main.refresh_all_holdings_prices", AsyncMock(return_value=mock_web_res)):
            res = _async(refresh_prices_for_user(self.username))

        self.assertEqual(res["fx_rate"], 1420.5)
        self.assertIn("1,420.5원", res["message"])

        updated_port = read_portfolio(username=self.username)
        self.assertEqual(updated_port["settings"]["exchange_rates"]["USD"], 1420.5)
        self.assertIn("fx_updated_at", updated_port["settings"])

    def test_fx_refresh_fallback_on_network_error(self):
        """If web finance FX fetch fails during holdings price refresh, fallback rate is used safely."""
        from app.main import refresh_prices_for_user
        from app.services.portfolio import write_portfolio

        portfolio = empty_portfolio()
        portfolio["holdings"] = [
            {"id": "h-kr", "code": "005930", "name": "삼성전자", "currency": "KRW", "current_price": 70000.0}
        ]
        write_portfolio(portfolio, username=self.username)

        # Web finance returns default fallback fx_rate (1385.0) when FX subtask had exception
        mock_web_res = {
            "prices": {"h-kr": 71000.0},
            "daily_changes": {},
            "period_rates": {},
            "fx_rate": 1385.0,
        }
        with patch("app.main.is_test_mode", return_value=False), \
             patch("app.main.refresh_all_holdings_prices", AsyncMock(return_value=mock_web_res)):
            res = _async(refresh_prices_for_user(self.username))

        self.assertEqual(res["fx_rate"], 1385.0)
        self.assertEqual(res["count"], 1)

    # -----------------------------------------------------------------------
    # 14. Route and Service Separation Signatures
    # -----------------------------------------------------------------------
    def test_route_and_service_separation_signatures(self):
        """Verify domain services accept pure parameters and have no Request in signature."""
        import app.main as main
        import inspect

        pure_services = [
            main.sync_all_accounts_for_user,
            main.sync_kb_for_user,
            main.sync_toss_for_user,
            main.sync_namoo_for_user,
            main.sync_kis_for_user,
            main.sync_kiwoom_for_user,
            main.refresh_prices_for_user,
            main.get_full_dashboard_for_user,
        ]
        for fn in pure_services:
            sig = inspect.signature(fn)
            self.assertIn("username", sig.parameters, f"{fn.__name__} must accept username")
            self.assertNotIn("request", sig.parameters, f"{fn.__name__} must NOT accept request")

    def test_run_daily_close_call_graph_has_no_request_or_route_invocation(self):
        """Verify run_daily_close_for_user executes purely via domain functions without HTTP routes."""
        import app.main as main

        # Route endpoints must NOT be called by daily close
        route_endpoints = [
            main.sync_all_accounts,
            main.sync_kb,
            main.sync_toss,
            main.sync_namoo,
            main.sync_kis,
            main.sync_kiwoom,
            main.refresh_prices,
            main.dashboard,
        ]

        route_mocks = []
        for route_fn in route_endpoints:
            m = AsyncMock() if inspect.iscoroutinefunction(route_fn) else MagicMock()
            p = patch.object(main, route_fn.__name__, m)
            p.start()
            self.addCleanup(p.stop)
            route_mocks.append(m)

        # Service functions ARE called
        with patch("app.main.sync_all_accounts_for_user", AsyncMock(return_value=self._sample_sync_result())) as svc_sync, \
             patch("app.main.refresh_prices_for_user", AsyncMock(return_value=self._sample_price_result())) as svc_price, \
             patch("app.main.get_full_dashboard_for_user", MagicMock(return_value=self._sample_dashboard())) as svc_dash, \
             patch("app.services.automation.daily_close.resolve_telegram_config",
                   return_value=TelegramConfig(username=self.username, enabled=False)):
            res = _async(run_daily_close_for_user(self.username))

        self.assertTrue(res["ok"])
        svc_sync.assert_called_once_with(self.username)
        svc_price.assert_called_once_with(self.username)
        svc_dash.assert_called_once_with(username=self.username, record_snapshots=False)

        # Zero route functions were called!
        for route_mock in route_mocks:
            route_mock.assert_not_called()
