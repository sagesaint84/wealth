"""Tests for Wealth Automation Dispatcher (A2).

Covers:
- Exact-minute Asia/Seoul matching and naive datetime rejection
- No job due when minute doesn't match
- Global IPO refresh morning & evening (single global execution)
- Deterministic global owner resolution (env var > system setting > fail closed)
- Owner absent behavior (safe unconfigured status, no silent users[0])
- User-scoped IPO reminders (default 09:00, custom slots like 16:20)
- Dynamic last-slot reminder semantics (max configured slot, not hardcoded 1500)
- Daily close service dispatch for matching users
- Multi-user schedule evaluation and user isolation
- Error isolation across jobs and users
- Corrupt settings isolation
- Deterministic job ordering in same minute (refresh -> reminder -> daily close)
- Dry-run inspectability
- Secret safety in results
- CLI entrypoint behavior (--now, --dry-run, error codes)
- Absence of persistent execution state (no data/automation/execution_state.json)
- Absence of FastAPI Request or legacy shell invocation in dispatcher path
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.automation.dispatcher import (
    KST,
    execute_job,
    main as cli_main,
    resolve_due_jobs,
    resolve_global_automation_owner,
    run_due_automation,
)
from app.services.settings import default_settings, patch_settings


class AutomationDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.data_dir = Path(self.temp_dir.name)

        env_patcher = patch.dict(os.environ, {"WEALTH_DATA_DIR": self.temp_dir.name})
        env_patcher.start()
        self.addCleanup(env_patcher.stop)

        # Base registered users
        self.mock_users = [
            {"username": "alice", "role": "user"},
            {"username": "bob", "role": "user"},
            {"username": "admin", "role": "admin"},
        ]

    def _make_kst_dt(self, hour: int, minute: int, year: int = 2026, month: int = 9, day: int = 21) -> datetime:
        return datetime(year, month, day, hour, minute, 0, tzinfo=KST)

    # 1. Section 49: TEST — NO JOB DUE
    def test_no_job_due_at_odd_minute(self):
        # 08:12 Asia/Seoul
        now = self._make_kst_dt(8, 12)
        with patch("app.services.automation.dispatcher.list_users", return_value=self.mock_users), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.refresh_ipo_market_enriched") as mock_refresh, \
             patch("app.services.automation.dispatcher.run_ipo_subscription_reminders") as mock_reminder, \
             patch("app.services.automation.dispatcher.run_daily_close_for_user") as mock_close:

            due = resolve_due_jobs(now)
            self.assertEqual(len(due), 0)

            result = asyncio.run(run_due_automation(now=now))
            self.assertEqual(len(result["jobs"]), 0)
            mock_refresh.assert_not_called()
            mock_reminder.assert_not_called()
            mock_close.assert_not_called()

    # 2. Section 50: TEST — MORNING REFRESH (07:30 default, exactly 1 call)
    def test_morning_refresh_dispatches_once_for_global_owner(self):
        now = self._make_kst_dt(7, 30)
        with patch("app.services.automation.dispatcher.list_users", return_value=self.mock_users), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.refresh_ipo_market_enriched", return_value={"status": "ok", "total_ipos": 5}) as mock_refresh:

            due = resolve_due_jobs(now)
            refresh_jobs = [j for j in due if j["job"] == "ipo_refresh_morning"]
            self.assertEqual(len(refresh_jobs), 1)
            self.assertEqual(refresh_jobs[0]["owner"], "alice")
            self.assertEqual(refresh_jobs[0]["scope"], "global")

            result = asyncio.run(run_due_automation(now=now))
            self.assertEqual(mock_refresh.call_count, 1)
            mock_refresh.assert_called_once_with(username="alice", target_date_str="2026-09-21")

            # Verify result structure
            executed_refresh = [j for j in result["jobs"] if j["job"] == "ipo_refresh_morning"]
            self.assertEqual(len(executed_refresh), 1)
            self.assertEqual(executed_refresh[0]["status"], "success")
            self.assertEqual(executed_refresh[0]["details"]["total_ipos"], 5)

    # 3. Section 51: TEST — EVENING REFRESH (18:30 default, exactly 1 call)
    def test_evening_refresh_dispatches_once_for_global_owner(self):
        now = self._make_kst_dt(18, 30)
        with patch("app.services.automation.dispatcher.list_users", return_value=self.mock_users), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.refresh_ipo_market_enriched", return_value={"status": "ok", "total_ipos": 6}) as mock_refresh:

            due = resolve_due_jobs(now)
            evening_jobs = [j for j in due if j["job"] == "ipo_refresh_evening"]
            self.assertEqual(len(evening_jobs), 1)
            self.assertEqual(evening_jobs[0]["owner"], "alice")

            result = asyncio.run(run_due_automation(now=now))
            self.assertEqual(mock_refresh.call_count, 1)
            mock_refresh.assert_called_once_with(username="alice", target_date_str="2026-09-21")

            executed_evening = [j for j in result["jobs"] if j["job"] == "ipo_refresh_evening"]
            self.assertEqual(len(executed_evening), 1)
            self.assertEqual(executed_evening[0]["status"], "success")

    # 4. Section 52: TEST — REMINDER 09:00
    def test_reminder_0900_dispatches_for_users(self):
        now = self._make_kst_dt(9, 0)
        with patch("app.services.automation.dispatcher.list_users", return_value=self.mock_users), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_ipo_subscription_reminders", return_value={"notifications_sent_count": 1, "eligible_ipos": 1, "all_applied_count": 0}) as mock_reminder:

            due = resolve_due_jobs(now)
            reminders = [j for j in due if j["job"] == "ipo_reminder"]
            # 3 registered users all have default 09:00 reminder enabled
            self.assertEqual(len(reminders), 3)
            self.assertEqual({r["slot"] for r in reminders}, {"0900"})
            # 0900 is NOT the last slot (1500 is max of 0900, 1200, 1500)
            self.assertFalse(any(r["is_last_slot"] for r in reminders))

            result = asyncio.run(run_due_automation(now=now))
            self.assertEqual(mock_reminder.call_count, 3)

    def test_listing_reminders_resolve_per_user_at_each_configured_slot(self):
        cfg = default_settings()
        users = [{"username": "alice", "role": "user"}, {"username": "bob", "role": "user"}]
        with patch("app.services.automation.dispatcher.list_users", return_value=users), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=cfg), \
             patch("app.services.automation.dispatcher.run_ipo_listing_reminders", return_value={"notifications_sent_count": 1, "eligible_ipos": 1}) as runner:
            due_0850 = [job for job in resolve_due_jobs(self._make_kst_dt(8, 50)) if job["job"] == "ipo_listing_reminder"]
            self.assertEqual(len(due_0850), 2)
            self.assertEqual({job["slot"] for job in due_0850}, {"0850"})
            self.assertTrue(all(job["execution_key"].startswith("user:") for job in due_0850))
            due_1450 = [job for job in resolve_due_jobs(self._make_kst_dt(14, 50)) if job["job"] == "ipo_listing_reminder"]
            self.assertEqual(len(due_1450), 2)
            self.assertEqual({job["slot"] for job in due_1450}, {"1450"})
            self.assertFalse(any(job["job"] == "ipo_listing_reminder" for job in resolve_due_jobs(self._make_kst_dt(8, 51))))
            result = asyncio.run(run_due_automation(now=self._make_kst_dt(8, 50)))
            self.assertEqual(runner.call_count, 2)
            self.assertTrue(all(job["status"] == "success" for job in result["jobs"] if job["job"] == "ipo_listing_reminder"))

    def test_listing_reminder_disabled_and_user_settings_are_isolated(self):
        alice = default_settings()
        bob = default_settings()
        bob["automation"]["ipo_listing_reminders"] = {"enabled": False, "times": ["08:50", "14:50"]}
        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice"}, {"username": "bob"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", side_effect=lambda username: alice if username == "alice" else bob):
            due = [job for job in resolve_due_jobs(self._make_kst_dt(8, 50)) if job["job"] == "ipo_listing_reminder"]
        self.assertEqual([job["username"] for job in due], ["alice"])

    # 5. Section 53: TEST — CUSTOM REMINDER (09:15, 13:40, 16:20)
    def test_custom_reminder_times_and_last_slot(self):
        custom_cfg = default_settings()
        custom_cfg["automation"]["ipo_reminders"]["times"] = ["09:15", "13:40", "16:20"]

        now_1620 = self._make_kst_dt(16, 20)
        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=custom_cfg), \
             patch("app.services.automation.dispatcher.run_ipo_subscription_reminders", return_value={"notifications_sent_count": 1}) as mock_reminder:

            due = resolve_due_jobs(now_1620)
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["job"], "ipo_reminder")
            self.assertEqual(due[0]["slot"], "1620")
            self.assertTrue(due[0]["is_last_slot"])

            result = asyncio.run(run_due_automation(now=now_1620))
            self.assertEqual(mock_reminder.call_count, 1)
            call_kwargs = mock_reminder.call_args[1]
            self.assertEqual(call_kwargs["reminder_slot"], "1620")
            self.assertTrue(call_kwargs["is_last_slot"])

    # 6. Section 54: TEST — LAST SLOT NOT HARDCODED TO 1500
    def test_last_slot_is_dynamic_max_configured(self):
        cfg = default_settings()
        cfg["automation"]["ipo_reminders"]["times"] = ["08:30", "11:00", "14:30"]

        now_1430 = self._make_kst_dt(14, 30)
        now_1100 = self._make_kst_dt(11, 0)

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=cfg):

            due_1100 = resolve_due_jobs(now_1100)
            self.assertEqual(len(due_1100), 1)
            self.assertEqual(due_1100[0]["slot"], "1100")
            self.assertFalse(due_1100[0]["is_last_slot"])

            due_1430 = resolve_due_jobs(now_1430)
            self.assertEqual(len(due_1430), 1)
            self.assertEqual(due_1430[0]["slot"], "1430")
            self.assertTrue(due_1430[0]["is_last_slot"])

    # 7. Section 55: TEST — DAILY CLOSE DISPATCH
    def test_daily_close_dispatches_for_matching_time(self):
        cfg = default_settings()
        cfg["automation"]["daily_close"]["time"] = "20:45"

        now = self._make_kst_dt(20, 45)
        mock_close = AsyncMock(return_value={
            "ok": True,
            "telegram_sent": True,
            "notification_status": "sent",
            "notification_dispatch_status": "sent",
            "notifications_sent_count": 3,
            "stock_record_saved": True,
            "net_record_saved": True,
        })

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=cfg), \
             patch("app.services.automation.dispatcher.run_daily_close_for_user", mock_close):

            due = resolve_due_jobs(now)
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["job"], "daily_close")
            self.assertEqual(due[0]["username"], "alice")
            self.assertEqual(due[0]["scheduled_time"], "20:45")

            result = asyncio.run(run_due_automation(now=now))
            mock_close.assert_called_once_with("alice", now=now)
            self.assertEqual(result["jobs"][0]["status"], "success")
            self.assertTrue(result["jobs"][0]["details"]["telegram_sent"])
            self.assertEqual(
                result["jobs"][0]["details"]["notification_dispatch_status"],
                "sent",
            )
            self.assertEqual(
                result["jobs"][0]["details"]["notifications_sent_count"],
                3,
            )

    def test_toss_session_job_surfaces_multichannel_notification_status(self):
        now = self._make_kst_dt(20, 55)
        runner = MagicMock(return_value={
            "action": "extended",
            "active": True,
            "valid": True,
            "server_expires_at": "2026-09-30T20:55:00+09:00",
            "hours_remaining": 120.0,
            "extension_attempted": True,
            "extension_succeeded": True,
            "notification_status": "partial",
            "notification_dispatch_status": "partial",
            "notifications_sent_count": 2,
            "error_code": None,
        })
        job = {
            "job": "toss_session_maintenance",
            "scope": "user",
            "owner": "alice",
            "scheduled_time": "20:55",
        }

        result = asyncio.run(
            execute_job(
                job,
                now=now,
                toss_session_runner=runner,
            )
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(
            result["details"]["notification_dispatch_status"],
            "partial",
        )
        self.assertEqual(
            result["details"]["notifications_sent_count"],
            2,
        )
        runner.assert_called_once_with("alice", now=now)

    # 8. Section 56: TEST — DISABLED TASKS DO NOT DISPATCH
    def test_disabled_tasks_not_due(self):
        cfg = default_settings()
        cfg["automation"]["ipo_refresh_morning"]["enabled"] = False
        cfg["automation"]["ipo_reminders"]["enabled"] = False
        cfg["automation"]["daily_close"]["enabled"] = False

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=cfg):

            self.assertEqual(len(resolve_due_jobs(self._make_kst_dt(7, 30))), 0)
            self.assertEqual(len(resolve_due_jobs(self._make_kst_dt(9, 0))), 0)
            self.assertEqual(len(resolve_due_jobs(self._make_kst_dt(21, 0))), 0)

    # 9. Section 57: TEST — MULTI USER PER-USER DISPATCH
    def test_multi_user_distinct_schedules(self):
        alice_cfg = default_settings()
        alice_cfg["automation"]["daily_close"]["time"] = "20:00"

        bob_cfg = default_settings()
        bob_cfg["automation"]["daily_close"]["time"] = "21:00"

        def get_cfg(u):
            return alice_cfg if u == "alice" else bob_cfg

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}, {"username": "bob", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", side_effect=get_cfg):

            due_2000 = resolve_due_jobs(self._make_kst_dt(20, 0))
            self.assertEqual(len(due_2000), 1)
            self.assertEqual(due_2000[0]["username"], "alice")

            due_2100 = resolve_due_jobs(self._make_kst_dt(21, 0))
            self.assertEqual(len(due_2100), 1)
            self.assertEqual(due_2100[0]["username"], "bob")

    # 10. Section 58: TEST — GLOBAL REFRESH MULTI USER (Single execution)
    def test_global_refresh_single_execution_under_multi_user(self):
        now = self._make_kst_dt(7, 30)
        with patch("app.services.automation.dispatcher.list_users", return_value=self.mock_users), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.refresh_ipo_market_enriched", return_value={"status": "ok"}) as mock_refresh:

            result = asyncio.run(run_due_automation(now=now))
            self.assertEqual(mock_refresh.call_count, 1)

    # 11. Section 59: TEST — OWNER ABSENT (No silent fallback, unconfigured status)
    def test_global_owner_absent_fails_closed_safely(self):
        now = self._make_kst_dt(7, 30)
        with patch("app.services.automation.dispatcher.list_users", return_value=self.mock_users), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value=None), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.refresh_ipo_market_enriched") as mock_refresh:

            due = resolve_due_jobs(now)
            self.assertEqual(len(due), 1)
            self.assertEqual(due[0]["job"], "ipo_refresh_morning")
            self.assertEqual(due[0]["status"], "unconfigured")
            self.assertEqual(due[0]["error"], "NO_GLOBAL_AUTOMATION_OWNER")
            self.assertIsNone(due[0]["owner"])

            result = asyncio.run(run_due_automation(now=now))
            mock_refresh.assert_not_called()
            self.assertEqual(result["jobs"][0]["status"], "unconfigured")

    def test_resolve_global_automation_owner_rules(self):
        registered = {"alice", "bob"}

        # 1. Stored system automation_owner > env fallback
        with patch.dict(os.environ, {"WEALTH_AUTOMATION_OWNER": "bob"}, clear=False), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value={"automation_owner": "alice", "automation_owner_source": "stored"}):
            self.assertEqual(resolve_global_automation_owner(registered_usernames=registered), "alice")

        # 2. Env fallback when stored is None
        with patch.dict(os.environ, {"WEALTH_AUTOMATION_OWNER": "bob"}, clear=False), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value={"automation_owner": "bob", "automation_owner_source": "environment"}):
            self.assertEqual(resolve_global_automation_owner(registered_usernames=registered), "bob")

        # 3. None when both absent
        with patch.dict(os.environ, {"WEALTH_AUTOMATION_OWNER": ""}, clear=False), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value={"automation_owner": None, "automation_owner_source": "none"}):
            self.assertIsNone(resolve_global_automation_owner(registered_usernames=registered))

        # 4. Stored invalid / unknown user fails closed (never falls back or guesses)
        with patch.dict(os.environ, {"WEALTH_AUTOMATION_OWNER": ""}, clear=False), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value={"automation_owner": "ghost", "automation_owner_source": "stored"}):
            self.assertIsNone(resolve_global_automation_owner(registered_usernames=registered))

        # 5. Env invalid / unknown user fails closed
        with patch.dict(os.environ, {"WEALTH_AUTOMATION_OWNER": "ghost"}, clear=False), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value={"automation_owner": "ghost", "automation_owner_source": "environment"}):
            self.assertIsNone(resolve_global_automation_owner(registered_usernames=registered))

        # 6. Telegram webhook owner independence: webhook owner has zero effect on automation
        with patch.dict(os.environ, {"WEALTH_AUTOMATION_OWNER": ""}, clear=False), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value={"telegram_webhook_owner": "alice", "automation_owner": None, "automation_owner_source": "none"}):
            self.assertIsNone(resolve_global_automation_owner(registered_usernames=registered))

        # 7. Distinct owners: telegram_webhook_owner=alice, automation_owner=bob
        with patch.dict(os.environ, {"WEALTH_AUTOMATION_OWNER": ""}, clear=False), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value={"telegram_webhook_owner": "alice", "automation_owner": "bob", "automation_owner_source": "stored"}):
            self.assertEqual(resolve_global_automation_owner(registered_usernames=registered), "bob")

        # 8. No .env required: works entirely with stored data when env is empty
        with patch.dict(os.environ, {}, clear=True), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value={"automation_owner": "alice", "automation_owner_source": "stored"}):
            self.assertEqual(resolve_global_automation_owner(registered_usernames=registered), "alice")

    # 12. Section 60: TEST — USER FAILURE ISOLATION
    def test_user_failure_isolation(self):
        now = self._make_kst_dt(21, 0)

        async def mock_daily_close(username, **kwargs):
            if username == "alice":
                raise RuntimeError("Alice DB boom")
            return {"ok": True, "telegram_sent": True, "notification_status": "sent", "stock_record_saved": True, "net_record_saved": True}

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}, {"username": "bob", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_daily_close_for_user", side_effect=mock_daily_close):

            result = asyncio.run(run_due_automation(now=now))
            self.assertEqual(len(result["jobs"]), 2)

            alice_job = next(j for j in result["jobs"] if j["username"] == "alice")
            bob_job = next(j for j in result["jobs"] if j["username"] == "bob")

            self.assertEqual(alice_job["status"], "failed")
            self.assertIn("Alice DB boom", alice_job["error"])

            self.assertEqual(bob_job["status"], "success")

    # 13. Section 61: TEST — EXACT MINUTE
    def test_exact_minute_matching(self):
        # Default reminder 09:00
        now_exact = self._make_kst_dt(9, 0)
        now_before = self._make_kst_dt(8, 59)
        now_after = self._make_kst_dt(9, 1)

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()):

            self.assertEqual(len(resolve_due_jobs(now_exact)), 1)
            self.assertEqual(len(resolve_due_jobs(now_before)), 0)
            self.assertEqual(len(resolve_due_jobs(now_after)), 0)

    # 14. Section 62: TEST — CLI ENTRYPOINT
    def test_cli_entrypoint_success(self):
        with patch("app.services.automation.dispatcher.run_due_automation", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"now": "2026-09-21T09:00:00+09:00", "dry_run": False, "jobs": []}
            code = cli_main(["--now", "2026-09-21T09:00:00+09:00"])
            self.assertEqual(code, 0)
            mock_run.assert_called_once()

    def test_cli_entrypoint_invalid_now(self):
        # Invalid format
        code = cli_main(["--now", "not-a-datetime"])
        self.assertEqual(code, 2)

        # Naive datetime
        code = cli_main(["--now", "2026-09-21T09:00:00"])
        self.assertEqual(code, 2)

    def test_cli_entrypoint_dry_run(self):
        with patch("app.services.automation.dispatcher.run_due_automation", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"now": "2026-09-21T09:00:00+09:00", "dry_run": True, "jobs": []}
            code = cli_main(["--now", "2026-09-21T09:00:00+09:00", "--dry-run"])
            self.assertEqual(code, 0)
            self.assertTrue(mock_run.call_args[1]["dry_run"])

    # 15. Section 63: TEST — EXECUTION STATE PERSISTENCE & ISOLATION
    def test_no_execution_state_created(self):
        prod_state_file = Path("data/automation/execution_state.json")
        self.assertFalse(prod_state_file.exists())
        temp_state_file = self.data_dir / "automation" / "execution_state.json"

        now = self._make_kst_dt(9, 0)
        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_ipo_subscription_reminders", return_value={"notifications_sent_count": 0}):

            # dry_run=True must NEVER create any execution state file
            asyncio.run(run_due_automation(now=now, dry_run=True))
            self.assertFalse(prod_state_file.exists())
            self.assertFalse(temp_state_file.exists())

            # dry_run=False creates file only in WEALTH_DATA_DIR, never in production repo data dir
            asyncio.run(run_due_automation(now=now, dry_run=False))
            self.assertFalse(prod_state_file.exists())
            self.assertTrue(temp_state_file.exists())

    # 16. Section 64: TEST — NO FASTAPI REQUEST OR SHELL IN DISPATCHER PATH
    def test_no_fastapi_or_shell_dependencies(self):
        import inspect
        import app.services.automation.dispatcher as disp_mod

        src = inspect.getsource(disp_mod)
        self.assertNotIn("FastAPI", src)
        self.assertNotIn("Request", src)
        self.assertNotIn("TestClient", src)
        self.assertNotIn("curl", src)
        self.assertNotIn("wealth-daily-close.sh", src)

    # 17. Section 42: Corrupt settings isolation
    def test_corrupt_settings_isolation(self):
        now = self._make_kst_dt(21, 0)

        def get_cfg(u):
            if u == "alice":
                raise ValueError("Corrupt settings JSON")
            return default_settings()

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}, {"username": "bob", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="bob"), \
             patch("app.services.automation.dispatcher.get_effective_settings", side_effect=get_cfg), \
             patch("app.services.automation.dispatcher.run_daily_close_for_user", new_callable=AsyncMock) as mock_close:

            mock_close.return_value = {"ok": True, "telegram_sent": False, "stock_record_saved": True, "net_record_saved": True}
            result = asyncio.run(run_due_automation(now=now))

            alice_job = next(j for j in result["jobs"] if j.get("username") == "alice")
            bob_job = next(j for j in result["jobs"] if j.get("username") == "bob")

            self.assertEqual(alice_job["status"], "failed")
            self.assertEqual(bob_job["status"], "success")

    # 18. Section 44-46: Deterministic job ordering in same minute
    def test_deterministic_job_ordering_same_minute(self):
        # Configure both morning refresh, reminder, and daily close at 09:00 for alice and bob
        alice_cfg = default_settings()
        alice_cfg["automation"]["ipo_refresh_morning"]["time"] = "09:00"
        alice_cfg["automation"]["ipo_reminders"]["times"] = ["09:00"]
        alice_cfg["automation"]["daily_close"]["time"] = "09:00"

        now = self._make_kst_dt(9, 0)
        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "bob", "role": "user"}, {"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=alice_cfg):

            due = resolve_due_jobs(now)
            job_types = [j["job"] for j in due]

            # 1. Global refresh must be first
            self.assertEqual(job_types[0], "ipo_refresh_morning")
            # 2. Then alice (alphabetical order) reminder then close
            self.assertEqual(job_types[1], "ipo_reminder")
            self.assertEqual(due[1]["username"], "alice")
            self.assertEqual(job_types[2], "daily_close")
            self.assertEqual(due[2]["username"], "alice")
            # 3. Then bob reminder then close
            self.assertEqual(job_types[3], "ipo_reminder")
            self.assertEqual(due[3]["username"], "bob")
            self.assertEqual(job_types[4], "daily_close")
            self.assertEqual(due[4]["username"], "bob")

    # 19. Section 48: Secret safety in results
    def test_secret_safety_in_result(self):
        now = self._make_kst_dt(21, 0)
        mock_close = AsyncMock(return_value={
            "ok": True,
            "telegram_sent": True,
            "notification_status": "sent",
            "stock_record_saved": True,
            "net_record_saved": True,
            "bot_token": "SUPER_SECRET_TOKEN_123",
            "webhook_secret": "TOP_SECRET_WEBHOOK_456",
        })

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_daily_close_for_user", mock_close):

            result = asyncio.run(run_due_automation(now=now))
            dumped = json.dumps(result)
            self.assertNotIn("SUPER_SECRET_TOKEN_123", dumped)
            self.assertNotIn("TOP_SECRET_WEBHOOK_456", dumped)

    # 20. Section A3: TEST — DISPATCHER DEDUPLICATION (ALREADY_SUCCESS)
    def test_dispatcher_deduplication_same_minute(self):
        now = self._make_kst_dt(21, 0)
        mock_close = AsyncMock(return_value={"ok": True, "telegram_sent": True, "stock_record_saved": True, "net_record_saved": True})

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_daily_close_for_user", mock_close):

            # First run: job executes successfully
            res1 = asyncio.run(run_due_automation(now=now))
            self.assertEqual(len(res1["jobs"]), 1)
            self.assertEqual(res1["jobs"][0]["status"], "success")
            self.assertEqual(mock_close.call_count, 1)

            # Second run within same minute: deduplicated, skipped, runner NOT called again
            res2 = asyncio.run(run_due_automation(now=now))
            self.assertEqual(len(res2["jobs"]), 1)
            self.assertEqual(res2["jobs"][0]["status"], "skipped")
            self.assertEqual(res2["jobs"][0]["reason"], "ALREADY_SUCCESS")
            self.assertEqual(mock_close.call_count, 1)

    # 21. Section A3: TEST — DISPATCHER RETRY OF FAILED JOB NEXT MINUTE
    def test_dispatcher_retries_failed_job_next_minute(self):
        t0 = self._make_kst_dt(21, 0)
        t1 = self._make_kst_dt(21, 1)
        mock_close = AsyncMock()

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_daily_close_for_user", mock_close):

            # First run at 21:00 fails
            mock_close.return_value = {"ok": False, "error": "network timeout"}
            res1 = asyncio.run(run_due_automation(now=t0))
            self.assertEqual(res1["jobs"][0]["status"], "failed")
            self.assertEqual(mock_close.call_count, 1)

            # Second run at 21:01 (no scheduled job, but retry from state)
            mock_close.return_value = {"ok": True, "telegram_sent": True, "stock_record_saved": True, "net_record_saved": True}
            res2 = asyncio.run(run_due_automation(now=t1))
            self.assertEqual(len(res2["jobs"]), 1)
            self.assertTrue(res2["jobs"][0].get("is_retry"))
            self.assertEqual(res2["jobs"][0]["status"], "success")
            self.assertEqual(mock_close.call_count, 2)

    # 22. Section 4: TEST — OWNER CHANGE AFTER FAILURE PRESERVES ORIGINAL OWNER
    def test_owner_change_after_failure_preserves_original_owner(self):
        t0 = self._make_kst_dt(7, 30)
        t1 = self._make_kst_dt(7, 31)
        mock_refresh = MagicMock()

        current_owner = "alice"

        def get_owner(*args, **kwargs):
            return current_owner

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}, {"username": "bob", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", side_effect=get_owner), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.refresh_ipo_market_enriched", mock_refresh):

            # Attempt 1 at 07:30 with owner alice fails
            mock_refresh.side_effect = RuntimeError("Network timeout")
            res1 = asyncio.run(run_due_automation(now=t0))
            self.assertEqual(res1["jobs"][0]["owner"], "alice")
            self.assertEqual(res1["jobs"][0]["status"], "failed")
            mock_refresh.assert_called_once_with(username="alice", target_date_str="2026-09-21")

            # Owner changes to bob before retry
            current_owner = "bob"
            mock_refresh.reset_mock()
            mock_refresh.side_effect = None
            mock_refresh.return_value = {"status": "ok", "total_ipos": 5}

            # Attempt 2 at 07:31 retry: must still use alice as runner username
            res2 = asyncio.run(run_due_automation(now=t1))
            self.assertEqual(len(res2["jobs"]), 1)
            self.assertTrue(res2["jobs"][0].get("is_retry"))
            self.assertEqual(res2["jobs"][0]["owner"], "alice")
            self.assertEqual(res2["jobs"][0]["status"], "success")
            mock_refresh.assert_called_once_with(username="alice", target_date_str="2026-09-21")

    # 23. Section 5: TEST — INVALID ORIGINAL OWNER ON RETRY FAILS CLOSED
    def test_invalid_original_owner_on_retry_fails_closed(self):
        t0 = self._make_kst_dt(7, 30)
        t1 = self._make_kst_dt(7, 31)
        mock_refresh = MagicMock(side_effect=RuntimeError("Fail"))

        current_users = [{"username": "alice", "role": "user"}, {"username": "bob", "role": "user"}]

        with patch("app.services.automation.dispatcher.list_users", side_effect=lambda: list(current_users)), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.refresh_ipo_market_enriched", mock_refresh):

            # Attempt 1 fails for alice
            res1 = asyncio.run(run_due_automation(now=t0))
            self.assertEqual(res1["jobs"][0]["status"], "failed")

            # Alice deleted from user registry
            current_users = [{"username": "bob", "role": "user"}]
            mock_refresh.reset_mock()

            # Attempt 2 at 07:31: must NOT substitute bob, must fail closed with USER_NOT_REGISTERED
            res2 = asyncio.run(run_due_automation(now=t1))
            self.assertEqual(len(res2["jobs"]), 1)
            self.assertEqual(res2["jobs"][0]["status"], "failed")
            self.assertEqual(res2["jobs"][0]["error"], "USER_NOT_REGISTERED")
            mock_refresh.assert_not_called()

    # 24. Section 6 & 7: TEST — REMINDER SETTINGS CHANGE AFTER FAILURE PRESERVES ORIGINAL METADATA
    def test_reminder_settings_change_after_failure_preserves_original_metadata(self):
        t0 = self._make_kst_dt(15, 0)
        t1 = self._make_kst_dt(15, 1)
        mock_reminder = MagicMock()

        # Initial settings: 09:00, 12:00, 15:00 (15:00 is last slot)
        cfg = default_settings()
        cfg["automation"]["ipo_reminders"]["times"] = ["09:00", "12:00", "15:00"]

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", side_effect=lambda u: cfg), \
             patch("app.services.automation.dispatcher.run_ipo_subscription_reminders", mock_reminder):

            # Run at 15:00 fails
            mock_reminder.side_effect = RuntimeError("Reminder fail")
            res1 = asyncio.run(run_due_automation(now=t0))
            self.assertEqual(res1["jobs"][0]["status"], "failed")
            mock_reminder.assert_called_once_with(
                username="alice",
                reminder_slot="1500",
                today=t0.date(),
                is_last_slot=True,
            )

            # User changes settings before retry to add 16:00 (so 15:00 would normally not be last slot anymore)
            cfg["automation"]["ipo_reminders"]["times"] = ["09:00", "12:00", "16:00"]
            mock_reminder.reset_mock()
            mock_reminder.side_effect = None
            mock_reminder.return_value = {"notifications_sent_count": 1, "eligible_ipos": 1, "all_applied_count": 0}

            # Retry at 15:01 must preserve original is_last_slot=True and slot=1500
            res2 = asyncio.run(run_due_automation(now=t1))
            self.assertEqual(len(res2["jobs"]), 1)
            self.assertTrue(res2["jobs"][0]["is_last_slot"])
            self.assertEqual(res2["jobs"][0]["slot"], "1500")
            self.assertEqual(res2["jobs"][0]["status"], "success")
            mock_reminder.assert_called_once_with(
                username="alice",
                reminder_slot="1500",
                today=t1.date(),
                is_last_slot=True,
            )

    # 25. Section 10: TEST — FAILED NEXT-MINUTE RETRY USES SAME ORIGINAL EXECUTION KEY
    def test_failed_next_minute_retry_uses_same_execution_key(self):
        t0 = self._make_kst_dt(21, 0)
        t1 = self._make_kst_dt(21, 1)
        mock_close = AsyncMock()

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_daily_close_for_user", mock_close):

            mock_close.return_value = {"ok": False, "error": "close failed"}
            res1 = asyncio.run(run_due_automation(now=t0))
            key_t0 = res1["jobs"][0]["execution_key"]
            self.assertEqual(key_t0, "user:alice:daily_close:2026-09-21:2100")

            mock_close.return_value = {"ok": True, "telegram_sent": True, "stock_record_saved": True, "net_record_saved": True}
            res2 = asyncio.run(run_due_automation(now=t1))
            key_t1 = res2["jobs"][0]["execution_key"]
            self.assertEqual(key_t1, key_t0)
            self.assertNotIn("2101", key_t1)

    # 26. Section 11: TEST — MAX ATTEMPTS EXCEEDED DISPATCHES ZERO RUNNER CALLS
    def test_max_attempts_exceeded_dispatches_zero_runner_calls(self):
        t0 = self._make_kst_dt(21, 0)
        t1 = self._make_kst_dt(21, 1)
        t2 = self._make_kst_dt(21, 2)
        t3 = self._make_kst_dt(21, 3)
        mock_close = AsyncMock(return_value={"ok": False, "error": "fatal"})

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_daily_close_for_user", mock_close):

            # Attempt 1 (21:00)
            res1 = asyncio.run(run_due_automation(now=t0))
            self.assertEqual(res1["jobs"][0]["status"], "failed")

            # Attempt 2 (21:01)
            res2 = asyncio.run(run_due_automation(now=t1))
            self.assertEqual(res2["jobs"][0]["status"], "failed")

            # Attempt 3 (21:02)
            res3 = asyncio.run(run_due_automation(now=t2))
            self.assertEqual(res3["jobs"][0]["status"], "failed")
            self.assertEqual(mock_close.call_count, 3)

            # At 21:03: max attempts reached -> 0 runner calls made!
            mock_close.reset_mock()
            res4 = asyncio.run(run_due_automation(now=t3))
            mock_close.assert_not_called()
            # If job was in due_jobs, status is skipped with MAX_ATTEMPTS_EXCEEDED
            for j in res4["jobs"]:
                self.assertIn(j.get("status"), ("skipped", "failed"))

    # 27. Section 12: TEST — MISSED FIRST MINUTE NOT EXECUTED (NO INITIAL MISSED-MINUTE CATCH-UP)
    def test_missed_first_minute_not_executed(self):
        # 09:00 reminder was scheduled, but dispatcher was NOT invoked at 09:00.
        # First invocation occurs at 09:01.
        t_missed = self._make_kst_dt(9, 1)
        mock_reminder = MagicMock()

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_ipo_subscription_reminders", mock_reminder):

            res = asyncio.run(run_due_automation(now=t_missed))
            # No jobs due at 09:01, 09:00 job is NOT created or executed
            self.assertEqual(len(res["jobs"]), 0)
            mock_reminder.assert_not_called()

    # 28. Section 13: TEST — DRY RUN WITH EXISTING STATE FILE IS IMMUTABLE
    def test_dry_run_with_existing_state_file_is_immutable(self):
        import hashlib

        now = self._make_kst_dt(9, 0)
        mock_reminder = MagicMock(return_value={"notifications_sent_count": 1})

        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice", "role": "user"}]), \
             patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value=default_settings()), \
             patch("app.services.automation.dispatcher.run_ipo_subscription_reminders", mock_reminder):

            # First normal run to create state file
            res1 = asyncio.run(run_due_automation(now=now, dry_run=False))
            self.assertEqual(res1["jobs"][0]["status"], "success")

            temp_state_file = self.data_dir / "automation" / "execution_state.json"
            self.assertTrue(temp_state_file.exists())
            hash_before = hashlib.sha256(temp_state_file.read_bytes()).hexdigest()

            # Now run dry-run with existing state file
            mock_reminder.reset_mock()
            res2 = asyncio.run(run_due_automation(now=now, dry_run=True))
            self.assertTrue(res2["dry_run"])
            mock_reminder.assert_not_called()

            hash_after = hashlib.sha256(temp_state_file.read_bytes()).hexdigest()
            self.assertEqual(hash_before, hash_after)


if __name__ == "__main__":
    unittest.main()
