from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.services.automation.status import (
    AutomationStatusError,
    build_automation_status,
)
from app.services.settings import default_settings

KST = timezone(timedelta(hours=9))


class AutomationStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "execution_state.json"
        self.now = datetime(2026, 9, 26, 12, 10, tzinfo=KST)
        self.settings = default_settings()
        self.settings["toss_wts"]["session_check_enabled"] = True

    def _write(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "updated_at": "2026-09-26T12:05:00+09:00",
                    "executions": {record["key"]: record for record in records},
                }
            ),
            encoding="utf-8",
        )

    def _record(
        self,
        *,
        key,
        job,
        scope="user",
        username="alice",
        owner=None,
        scheduled_time="12:00",
        status="SUCCESS",
        attempt_count=1,
        first_claimed_at="2026-09-26T12:00:00+09:00",
        last_attempt_at="2026-09-26T12:00:00+09:00",
        completed_at="2026-09-26T12:00:02+09:00",
        last_error_code=None,
        details=None,
        retryable=True,
    ):
        return {
            "key": key,
            "scope": scope,
            "job": job,
            "username": username,
            "owner": owner,
            "scheduled_date": "2026-09-26",
            "scheduled_time": scheduled_time,
            "status": status,
            "attempt_count": attempt_count,
            "first_claimed_at": first_claimed_at,
            "last_attempt_at": last_attempt_at,
            "completed_at": completed_at,
            "last_error_code": last_error_code,
            "details": details,
            "retryable": retryable,
        }

    def _patch_system(self):
        return patch.multiple(
            "app.services.automation.status",
            get_effective_system_settings=lambda: {
                "automation_owner": "alice",
                "automation_owner_source": "stored",
            },
            resolve_toss_wts_settings=lambda: {
                "enabled": True,
                "session_check_enabled": True,
                "session_check_time": "20:55",
                "allowed_users": [],
            },
        )

    def test_projects_global_and_current_user_records_only(self):
        records = [
            self._record(
                key="global:ipo_refresh_morning:2026-09-26:0730",
                job="ipo_refresh_morning",
                scope="global",
                username=None,
                owner="alice",
                scheduled_time="07:30",
                first_claimed_at="2026-09-26T07:30:00+09:00",
                last_attempt_at="2026-09-26T07:30:00+09:00",
                completed_at="2026-09-26T07:30:03+09:00",
                details={"total_ipos": 14, "status": "ok", "secret": "NOPE"},
            ),
            self._record(
                key="user:alice:ipo_reminder:2026-09-26:1200",
                job="ipo_reminder",
                scheduled_time="12:00",
                details={"notifications_sent_count": 2, "eligible_ipos": 3},
            ),
            self._record(
                key="user:bob:ipo_reminder:2026-09-26:1200",
                job="ipo_reminder",
                username="bob",
                details={"notifications_sent_count": 999},
            ),
        ]
        self._write(records)
        with self._patch_system():
            result = build_automation_status(
                "alice",
                settings=self.settings,
                now=self.now,
                state_path=self.path,
            )

        recent_keys = {(item["job"], item["scope"]) for item in result["recent"]}
        self.assertIn(("ipo_refresh_morning", "global"), recent_keys)
        self.assertIn(("ipo_reminder", "user"), recent_keys)
        self.assertEqual(len(result["recent"]), 2)
        self.assertNotIn("secret", json.dumps(result))
        morning = next(job for job in result["jobs"] if job["job"] == "ipo_refresh_morning")
        self.assertEqual(morning["health"], "success")
        self.assertEqual(morning["last_execution"]["duration_seconds"], 3.0)
        self.assertEqual(morning["last_execution"]["details"]["total_ipos"], 14)

    def test_detects_missed_expected_slot_after_grace(self):
        self.settings["automation"]["daily_close"] = {
            "enabled": True,
            "time": "12:00",
        }
        self._write([])
        with self._patch_system():
            result = build_automation_status(
                "alice",
                settings=self.settings,
                now=self.now,
                state_path=self.path,
            )
        daily = next(job for job in result["jobs"] if job["job"] == "daily_close")
        self.assertEqual(daily["health"], "missed")
        self.assertEqual(daily["last_expected_at"], "2026-09-26T12:00:00+09:00")
        self.assertEqual(daily["next_run_at"], "2026-09-27T12:00:00+09:00")

    def test_before_first_slot_uses_previous_day_as_expected(self):
        settings = default_settings()
        settings["automation"]["ipo_reminders"]["times"] = ["09:00", "12:00"]
        self._write([])
        now = datetime(2026, 9, 26, 8, 0, tzinfo=KST)
        with self._patch_system():
            result = build_automation_status(
                "alice", settings=settings, now=now, state_path=self.path
            )
        reminder = next(job for job in result["jobs"] if job["job"] == "ipo_reminder")
        self.assertEqual(reminder["last_expected_at"], "2026-09-25T12:00:00+09:00")
        self.assertEqual(reminder["next_run_at"], "2026-09-26T09:00:00+09:00")
        self.assertEqual(reminder["health"], "missed")

    def test_running_record_becomes_stale_after_execution_timeout(self):
        record = self._record(
            key="user:alice:daily_close:2026-09-26:1200",
            job="daily_close",
            status="RUNNING",
            completed_at=None,
            first_claimed_at="2026-09-26T11:40:00+09:00",
            last_attempt_at="2026-09-26T11:40:00+09:00",
        )
        self.settings["automation"]["daily_close"] = {"enabled": True, "time": "12:00"}
        self._write([record])
        with self._patch_system():
            result = build_automation_status(
                "alice", settings=self.settings, now=self.now, state_path=self.path
            )
        daily = next(job for job in result["jobs"] if job["job"] == "daily_close")
        self.assertEqual(daily["health"], "stale")
        self.assertEqual(daily["last_execution"]["status"], "RUNNING")

    def test_toss_owner_fallback_is_user_scoped(self):
        record = self._record(
            key="user:alice:toss_session_maintenance:2026-09-26:2055",
            job="toss_session_maintenance",
            username=None,
            owner="alice",
            scheduled_time="20:55",
            first_claimed_at="2026-09-25T20:55:00+09:00",
            last_attempt_at="2026-09-25T20:55:00+09:00",
            completed_at="2026-09-25T20:55:01+09:00",
            details={"action": "not_required", "hours_remaining": 96.5},
        )
        record["scheduled_date"] = "2026-09-25"
        self._write([record])
        with self._patch_system():
            result = build_automation_status(
                "alice", settings=self.settings, now=self.now, state_path=self.path
            )
        recent = [item for item in result["recent"] if item["job"] == "toss_session_maintenance"]
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["details"]["action"], "not_required")

    def test_failure_code_and_details_are_secret_safe(self):
        record = self._record(
            key="user:alice:daily_close:2026-09-26:1200",
            job="daily_close",
            status="FAILED",
            last_error_code="https://token.example/SECRET_TOKEN",
            details={
                "notification_status": "failed",
                "notifications_sent_count": 0,
                "webhook": "https://discord.com/api/webhooks/SECRET",
            },
        )
        self.settings["automation"]["daily_close"] = {"enabled": True, "time": "12:00"}
        self._write([record])
        with self._patch_system():
            result = build_automation_status(
                "alice", settings=self.settings, now=self.now, state_path=self.path
            )
        raw = json.dumps(result)
        self.assertNotIn("SECRET", raw)
        self.assertNotIn("discord.com", raw)

    def test_disabled_jobs_do_not_report_missed(self):
        settings = default_settings()
        settings["automation"]["daily_close"]["enabled"] = False
        self._write([])
        with self._patch_system():
            result = build_automation_status(
                "alice", settings=settings, now=self.now, state_path=self.path
            )
        daily = next(job for job in result["jobs"] if job["job"] == "daily_close")
        self.assertEqual(daily["health"], "disabled")
        self.assertIsNone(daily["next_run_at"])

    def test_invalid_limit_and_corrupt_state_fail_with_stable_codes(self):
        with self.assertRaisesRegex(ValueError, "AUTOMATION_STATUS_LIMIT_INVALID"):
            build_automation_status(
                "alice",
                settings=self.settings,
                now=self.now,
                state_path=self.path,
                recent_limit=0,
            )
        self.path.write_text("{bad", encoding="utf-8")
        with self._patch_system(), self.assertRaisesRegex(
            AutomationStatusError,
            "AUTOMATION_STATUS_UNAVAILABLE",
        ):
            build_automation_status(
                "alice",
                settings=self.settings,
                now=self.now,
                state_path=self.path,
            )


if __name__ == "__main__":
    unittest.main()
