"""Phase 10 reliability policy tests.

The general test suite keeps the legacy exact-minute dispatcher contract by
setting WEALTH_ENV=test.  These tests explicitly opt into the Phase 10 policy.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from app.services.automation.execution_state import build_execution_key
from app.services.automation.reliability import (
    KST,
    get_retryable_executions_reliable,
    resolve_catch_up_records,
)
from app.services.settings import default_settings


class AutomationReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.policy_env = patch.dict(
            os.environ,
            {"WEALTH_AUTOMATION_RELIABILITY_TEST": "1"},
        )
        self.policy_env.start()
        self.addCleanup(self.policy_env.stop)

    @staticmethod
    def _dt(hour: int, minute: int, second: int = 0) -> datetime:
        return datetime(2026, 9, 26, hour, minute, second, tzinfo=KST)

    @staticmethod
    def _state(*records: dict) -> dict:
        return {
            "version": 1,
            "updated_at": None,
            "executions": {record["key"]: record for record in records},
        }

    def _failed_record(
        self,
        *,
        attempt_count: int,
        completed_at: datetime,
        error_code: str = "TIMEOUT",
    ) -> dict:
        key = "user:alice:daily_close:2026-09-26:2100"
        return {
            "key": key,
            "scope": "user",
            "job": "daily_close",
            "username": "alice",
            "scheduled_date": "2026-09-26",
            "scheduled_time": "21:00",
            "status": "FAILED",
            "attempt_count": attempt_count,
            "last_attempt_at": completed_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "last_error_code": error_code,
            "retryable": True,
        }

    def test_first_failure_waits_one_minute_before_retry(self):
        failed_at = self._dt(9, 0)
        state = self._state(
            self._failed_record(attempt_count=1, completed_at=failed_at)
        )

        with patch("app.services.automation.reliability.list_users", return_value=[]):
            too_soon = get_retryable_executions_reliable(
                failed_at + timedelta(seconds=59), state=state
            )
            ready = get_retryable_executions_reliable(
                failed_at + timedelta(seconds=60), state=state
            )

        self.assertEqual(too_soon, [])
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["attempt_count"], 1)

    def test_second_failure_waits_five_minutes_before_retry(self):
        failed_at = self._dt(9, 1)
        state = self._state(
            self._failed_record(attempt_count=2, completed_at=failed_at)
        )

        with patch("app.services.automation.reliability.list_users", return_value=[]):
            too_soon = get_retryable_executions_reliable(
                failed_at + timedelta(minutes=4, seconds=59), state=state
            )
            ready = get_retryable_executions_reliable(
                failed_at + timedelta(minutes=5), state=state
            )

        self.assertEqual(too_soon, [])
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["attempt_count"], 2)

    def test_configuration_failures_do_not_burn_retry_attempts(self):
        failed_at = self._dt(9, 0)
        state = self._state(
            self._failed_record(
                attempt_count=1,
                completed_at=failed_at,
                error_code="USER_NOT_REGISTERED",
            )
        )

        with patch("app.services.automation.reliability.list_users", return_value=[]):
            retryables = get_retryable_executions_reliable(
                failed_at + timedelta(hours=2), state=state
            )

        self.assertEqual(retryables, [])

    def test_morning_refresh_is_caught_up_within_three_hours(self):
        now = self._dt(8, 0)
        cfg = default_settings()
        with patch(
            "app.services.automation.reliability.list_users",
            return_value=[{"username": "alice", "role": "user"}],
        ), patch(
            "app.services.automation.reliability.get_effective_system_settings",
            return_value={
                "automation_owner": "alice",
                "automation_owner_source": "stored",
            },
        ), patch(
            "app.services.automation.reliability.get_effective_settings",
            return_value=cfg,
        ):
            records = resolve_catch_up_records(now, self._state())

        morning = [r for r in records if r["job"] == "ipo_refresh_morning"]
        self.assertEqual(len(morning), 1)
        self.assertEqual(morning[0]["scheduled_time"], "07:30")
        self.assertEqual(morning[0]["scope"], "global")
        self.assertTrue(morning[0]["catch_up"])

    def test_reminder_catch_up_replays_only_latest_missed_slot(self):
        now = self._dt(9, 25)
        cfg = default_settings()
        cfg["automation"]["ipo_reminders"] = {
            "enabled": True,
            "times": ["09:00", "09:15", "15:00"],
        }
        cfg["automation"]["ipo_listing_reminders"]["enabled"] = False
        with patch(
            "app.services.automation.reliability.list_users",
            return_value=[{"username": "alice"}],
        ), patch(
            "app.services.automation.reliability.get_effective_system_settings",
            return_value={"automation_owner": None, "automation_owner_source": "none"},
        ), patch(
            "app.services.automation.reliability.get_effective_settings",
            return_value=cfg,
        ):
            records = resolve_catch_up_records(now, self._state())

        reminders = [r for r in records if r["job"] == "ipo_reminder"]
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["slot"], "0915")
        self.assertFalse(reminders[0]["is_last_slot"])

    def test_existing_execution_key_is_never_synthesized_again(self):
        now = self._dt(8, 0)
        cfg = default_settings()
        key = build_execution_key(
            job="ipo_refresh_morning",
            target_date="2026-09-26",
            time_str="07:30",
            scope="global",
        )
        existing = {
            "key": key,
            "scope": "global",
            "job": "ipo_refresh_morning",
            "scheduled_date": "2026-09-26",
            "scheduled_time": "07:30",
            "status": "FAILED",
            "attempt_count": 1,
            "retryable": True,
        }
        with patch(
            "app.services.automation.reliability.list_users",
            return_value=[{"username": "alice"}],
        ), patch(
            "app.services.automation.reliability.get_effective_system_settings",
            return_value={
                "automation_owner": "alice",
                "automation_owner_source": "stored",
            },
        ), patch(
            "app.services.automation.reliability.get_effective_settings",
            return_value=cfg,
        ):
            records = resolve_catch_up_records(now, self._state(existing))

        self.assertNotIn(key, {record["key"] for record in records})

    def test_previous_day_daily_close_is_not_replayed(self):
        # Catch-up always constructs today's schedule.  At 00:10 today's 21:00
        # is still in the future, so yesterday's close can never be synthesized.
        now = self._dt(0, 10)
        cfg = default_settings()
        with patch(
            "app.services.automation.reliability.list_users",
            return_value=[{"username": "alice"}],
        ), patch(
            "app.services.automation.reliability.get_effective_system_settings",
            return_value={"automation_owner": None, "automation_owner_source": "none"},
        ), patch(
            "app.services.automation.reliability.get_effective_settings",
            return_value=cfg,
        ):
            records = resolve_catch_up_records(now, self._state())

        self.assertFalse(any(r["job"] == "daily_close" for r in records))

    def test_toss_session_maintenance_is_never_caught_up(self):
        now = self._dt(21, 10)
        cfg = default_settings()
        cfg["toss_wts"]["session_check_enabled"] = True
        cfg["automation"]["daily_close"]["enabled"] = False
        cfg["automation"]["ipo_reminders"]["enabled"] = False
        cfg["automation"]["ipo_listing_reminders"]["enabled"] = False
        cfg["automation"]["ipo_refresh_morning"]["enabled"] = False
        cfg["automation"]["ipo_refresh_evening"]["enabled"] = False
        with patch(
            "app.services.automation.reliability.list_users",
            return_value=[{"username": "alice"}],
        ), patch(
            "app.services.automation.reliability.get_effective_system_settings",
            return_value={"automation_owner": None, "automation_owner_source": "none"},
        ), patch(
            "app.services.automation.reliability.get_effective_settings",
            return_value=cfg,
        ):
            records = resolve_catch_up_records(now, self._state())

        self.assertFalse(any(r["job"] == "toss_session_maintenance" for r in records))


if __name__ == "__main__":
    unittest.main()
