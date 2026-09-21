"""Unit and integration tests for Wealth automation execution state (A3).

Covers:
- Execution key deterministic generation and parsing
- Safe error code sanitization (no secret/URL leakage)
- Atomic state file persistence with crash safety
- First claim creates file with RUNNING status (attempt=1)
- Recording SUCCESS and FAILED transitions
- Same-minute deduplication on SUCCESS (ALREADY_SUCCESS)
- Same-minute deduplication on active RUNNING (ALREADY_RUNNING)
- Stale RUNNING recovery (>15m, attempt count incremented)
- Stale RUNNING max attempts abort (marks FAILED)
- Bounded retry for FAILED executions (< max_attempts)
- Rejection of retries exceeding max_attempts
- Fail-closed behavior on corrupted state JSON
- Thread and process concurrency lock protection
- Pruning policy (30-day retention, 1000 limit, protection of active/today's failed)
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.services.automation.execution_state import (
    DEFAULT_MAX_ATTEMPTS,
    ExecutionStateCorruptError,
    ExecutionStateError,
    ExecutionStateLockError,
    build_execution_key,
    claim_execution,
    execution_state_lock,
    get_execution_state_path,
    get_retryable_executions,
    load_execution_state,
    parse_execution_key,
    prune_execution_state,
    record_execution_failure,
    record_execution_success,
    sanitize_error_code,
    save_execution_state,
)

KST = timezone(timedelta(hours=9))


class AutomationExecutionStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.state_file = Path(self.temp_dir.name) / "automation" / "execution_state.json"

    def _make_kst_dt(
        self,
        hour: int = 9,
        minute: int = 0,
        second: int = 0,
        year: int = 2026,
        month: int = 9,
        day: int = 21,
    ) -> datetime:
        return datetime(year, month, day, hour, minute, second, tzinfo=KST)

    # 1. Target path resolution
    def test_get_execution_state_path_resolution(self):
        custom = Path(self.temp_dir.name) / "custom.json"
        self.assertEqual(get_execution_state_path(custom), custom)

        with patch.dict(os.environ, {"WEALTH_DATA_DIR": self.temp_dir.name}):
            resolved = get_execution_state_path()
            self.assertEqual(resolved, Path(self.temp_dir.name) / "automation" / "execution_state.json")

        with patch.dict(os.environ, {}, clear=True):
            resolved = get_execution_state_path()
            self.assertEqual(resolved, Path("data/automation/execution_state.json"))

    # 2. Execution key generation and parsing
    def test_build_and_parse_execution_key(self):
        # Global key
        g_key = build_execution_key(
            job="ipo_refresh_morning",
            target_date="2026-09-21",
            time_str="07:30",
            scope="global",
        )
        self.assertEqual(g_key, "global:ipo_refresh_morning:2026-09-21:0730")
        g_parsed = parse_execution_key(g_key)
        self.assertEqual(g_parsed["scope"], "global")
        self.assertEqual(g_parsed["job"], "ipo_refresh_morning")
        self.assertEqual(g_parsed["scheduled_date"], "2026-09-21")
        self.assertEqual(g_parsed["time_hhmm"], "0730")

        # User key
        u_key = build_execution_key(
            job="daily_close",
            target_date="2026-09-21",
            time_str="21:00",
            scope="user",
            username="alice",
        )
        self.assertEqual(u_key, "user:alice:daily_close:2026-09-21:2100")
        u_parsed = parse_execution_key(u_key)
        self.assertEqual(u_parsed["scope"], "user")
        self.assertEqual(u_parsed["username"], "alice")
        self.assertEqual(u_parsed["job"], "daily_close")
        self.assertEqual(u_parsed["time_hhmm"], "2100")

        # User reminder key with slot
        r_key = build_execution_key(
            job="ipo_reminder",
            target_date="2026-09-21",
            time_str="14:30",
            scope="user",
            username="bob",
            slot="1430",
        )
        self.assertEqual(r_key, "user:bob:ipo_reminder:2026-09-21:1430")

        # Missing username for user scope
        with self.assertRaises(ValueError):
            build_execution_key(
                job="daily_close",
                target_date="2026-09-21",
                time_str="21:00",
                scope="user",
            )

        # Invalid key format parsing
        with self.assertRaises(ValueError):
            parse_execution_key("invalid:key")

    # 3. Error code sanitization (secret / sensitive safety)
    def test_sanitize_error_code(self):
        self.assertEqual(sanitize_error_code(None), "UNKNOWN_ERROR")
        self.assertEqual(sanitize_error_code(""), "UNKNOWN_ERROR")
        self.assertEqual(sanitize_error_code("NO_GLOBAL_AUTOMATION_OWNER"), "NO_GLOBAL_AUTOMATION_OWNER")
        self.assertEqual(sanitize_error_code("IpoRefreshAlreadyRunning: error"), "IPO_REFRESH_CONTENTION")
        self.assertEqual(sanitize_error_code("IpoNotificationAlreadyRunning"), "IPO_NOTIFICATION_CONTENTION")
        self.assertEqual(sanitize_error_code("Daily close failed at step sync"), "DAILY_CLOSE_FAILED")
        self.assertEqual(sanitize_error_code("HTTP timeout occurred"), "TIMEOUT")
        self.assertEqual(sanitize_error_code("Corrupted settings file"), "SETTINGS_CORRUPT")
        self.assertEqual(sanitize_error_code("User not registered"), "USER_NOT_REGISTERED")

        # Ensure tokens, URLs, or query strings NEVER leak
        leaked_msg = "Failed request to https://api.telegram.org/bot123456:ABC-DEF1234/sendMessage?chat_id=987654"
        clean = sanitize_error_code(leaked_msg)
        self.assertEqual(clean, "NETWORK_ERROR")
        self.assertNotIn("bot", clean.lower())
        self.assertNotIn("123456", clean)
        self.assertNotIn("987654", clean)
        self.assertNotIn("http", clean.lower())

    # 4. Pure read-only load does NOT create file on disk
    def test_load_execution_state_absence_does_not_create_file(self):
        self.assertFalse(self.state_file.exists())
        state = load_execution_state(self.state_file)
        self.assertEqual(state["version"], 1)
        self.assertEqual(state["executions"], {})
        self.assertFalse(self.state_file.exists())

    # 5. First claim creates file with RUNNING status
    def test_first_claim_creates_record(self):
        now = self._make_kst_dt(9, 0, 1)
        key = "user:alice:daily_close:2026-09-21:2100"
        job_desc = {
            "job": "daily_close",
            "scope": "user",
            "username": "alice",
            "scheduled_time": "21:00",
            "scheduled_date": "2026-09-21",
        }

        res = claim_execution(key, job_desc, now=now, state_path=self.state_file)
        self.assertTrue(res["claimed"])
        self.assertEqual(res["reason"], "FIRST_CLAIM")
        self.assertTrue(self.state_file.exists())

        rec = res["record"]
        self.assertEqual(rec["key"], key)
        self.assertEqual(rec["status"], "RUNNING")
        self.assertEqual(rec["attempt_count"], 1)
        self.assertEqual(rec["first_claimed_at"], now.isoformat())
        self.assertEqual(rec["last_attempt_at"], now.isoformat())
        self.assertIsNone(rec["completed_at"])

    # 6. Record SUCCESS transition
    def test_record_success(self):
        now = self._make_kst_dt(9, 0, 1)
        key = "user:alice:daily_close:2026-09-21:2100"
        job_desc = {"job": "daily_close", "scope": "user", "username": "alice", "scheduled_time": "21:00"}
        claim_execution(key, job_desc, now=now, state_path=self.state_file)

        comp_dt = self._make_kst_dt(9, 0, 3)
        details = {"telegram_sent": True, "stock_record_saved": True}
        rec = record_execution_success(key, now=comp_dt, details=details, state_path=self.state_file)

        self.assertEqual(rec["status"], "SUCCESS")
        self.assertEqual(rec["completed_at"], comp_dt.isoformat())
        self.assertEqual(rec["details"], details)
        self.assertIsNone(rec["last_error_code"])

        # Reload from disk and verify
        state = load_execution_state(self.state_file)
        persisted = state["executions"][key]
        self.assertEqual(persisted["status"], "SUCCESS")

    # 7. Deduplication on SUCCESS (ALREADY_SUCCESS)
    def test_deduplication_already_success(self):
        now = self._make_kst_dt(9, 0, 1)
        key = "user:alice:daily_close:2026-09-21:2100"
        job_desc = {"job": "daily_close", "scope": "user", "username": "alice", "scheduled_time": "21:00"}
        claim_execution(key, job_desc, now=now, state_path=self.state_file)
        record_execution_success(key, now=self._make_kst_dt(9, 0, 2), state_path=self.state_file)

        # Same minute or later attempt to claim
        later = self._make_kst_dt(9, 0, 30)
        res = claim_execution(key, job_desc, now=later, state_path=self.state_file)
        self.assertFalse(res["claimed"])
        self.assertEqual(res["reason"], "ALREADY_SUCCESS")

    # 8. Deduplication on active RUNNING (ALREADY_RUNNING)
    def test_deduplication_already_running(self):
        now = self._make_kst_dt(9, 0, 1)
        key = "global:ipo_refresh_morning:2026-09-21:0730"
        job_desc = {"job": "ipo_refresh_morning", "scope": "global", "scheduled_time": "07:30"}
        claim_execution(key, job_desc, now=now, state_path=self.state_file)

        # Concurrent claim 5 seconds later
        now_plus_5s = self._make_kst_dt(9, 0, 6)
        res = claim_execution(key, job_desc, now=now_plus_5s, state_path=self.state_file)
        self.assertFalse(res["claimed"])
        self.assertEqual(res["reason"], "ALREADY_RUNNING")

    # 9. Stale RUNNING recovery (> 15 minutes / 900 seconds)
    def test_stale_running_recovery_increments_attempt(self):
        now = self._make_kst_dt(9, 0, 0)
        key = "user:bob:daily_close:2026-09-21:2100"
        job_desc = {"job": "daily_close", "scope": "user", "username": "bob", "scheduled_time": "21:00"}
        claim_execution(key, job_desc, now=now, state_path=self.state_file)

        # Fast-forward 16 minutes (960 seconds)
        stale_time = now + timedelta(minutes=16)
        res = claim_execution(key, job_desc, now=stale_time, state_path=self.state_file, stale_seconds=900.0)

        self.assertTrue(res["claimed"])
        self.assertEqual(res["reason"], "STALE_RETRY")
        rec = res["record"]
        self.assertEqual(rec["attempt_count"], 2)
        self.assertEqual(rec["status"], "RUNNING")
        self.assertEqual(rec["last_error_code"], "STALE_RECOVERY")
        self.assertEqual(rec["last_attempt_at"], stale_time.isoformat())

    # 10. Stale RUNNING abort when max attempts reached
    def test_stale_running_max_attempts_exceeded(self):
        now = self._make_kst_dt(9, 0, 0)
        key = "user:bob:daily_close:2026-09-21:2100"
        job_desc = {"job": "daily_close", "scope": "user", "username": "bob", "scheduled_time": "21:00"}

        # Simulate job already at attempt 3
        claim_execution(key, job_desc, now=now, state_path=self.state_file)
        state = load_execution_state(self.state_file)
        state["executions"][key]["attempt_count"] = 3
        save_execution_state(state, self.state_file)

        # Fast-forward 16 minutes
        stale_time = now + timedelta(minutes=16)
        res = claim_execution(key, job_desc, now=stale_time, state_path=self.state_file, max_attempts=3, stale_seconds=900.0)

        self.assertFalse(res["claimed"])
        self.assertEqual(res["reason"], "MAX_ATTEMPTS_EXCEEDED")

        rec = load_execution_state(self.state_file)["executions"][key]
        self.assertEqual(rec["status"], "FAILED")
        self.assertEqual(rec["last_error_code"], "STALE_TIMEOUT_MAX_ATTEMPTS_EXCEEDED")

    # 11. Bounded retry for FAILED executions
    def test_bounded_retry_for_failed_executions(self):
        now = self._make_kst_dt(9, 0, 0)
        key = "user:bob:ipo_reminder:2026-09-21:0900"
        job_desc = {"job": "ipo_reminder", "scope": "user", "username": "bob", "scheduled_time": "09:00", "slot": "0900"}

        # Attempt 1 fails
        claim_execution(key, job_desc, now=now, state_path=self.state_file)
        record_execution_failure(key, now=now + timedelta(seconds=2), error_code="TIMEOUT", state_path=self.state_file)

        # Retry at next minute (9:01)
        next_min = now + timedelta(minutes=1)
        res2 = claim_execution(key, job_desc, now=next_min, state_path=self.state_file, max_attempts=3)
        self.assertTrue(res2["claimed"])
        self.assertEqual(res2["reason"], "RETRY")
        self.assertEqual(res2["record"]["attempt_count"], 2)

        # Attempt 2 fails
        record_execution_failure(key, now=next_min + timedelta(seconds=2), error_code="TIMEOUT", state_path=self.state_file)

        # Retry at 9:02
        min_2 = now + timedelta(minutes=2)
        res3 = claim_execution(key, job_desc, now=min_2, state_path=self.state_file, max_attempts=3)
        self.assertTrue(res3["claimed"])
        self.assertEqual(res3["reason"], "RETRY")
        self.assertEqual(res3["record"]["attempt_count"], 3)

        # Attempt 3 fails
        record_execution_failure(key, now=min_2 + timedelta(seconds=2), error_code="TIMEOUT", state_path=self.state_file)

        # Retry at 9:03 (exceeds max_attempts=3)
        min_3 = now + timedelta(minutes=3)
        res4 = claim_execution(key, job_desc, now=min_3, state_path=self.state_file, max_attempts=3)
        self.assertFalse(res4["claimed"])
        self.assertEqual(res4["reason"], "MAX_ATTEMPTS_EXCEEDED")

    # 12. Retryable executions query
    def test_get_retryable_executions(self):
        now = self._make_kst_dt(9, 0, 0)
        key_fail = "user:alice:daily_close:2026-09-21:2100"
        job_desc = {"job": "daily_close", "scope": "user", "username": "alice", "scheduled_time": "21:00", "scheduled_date": "2026-09-21"}

        claim_execution(key_fail, job_desc, now=now, state_path=self.state_file)
        record_execution_failure(key_fail, now=now, error_code="DAILY_CLOSE_FAILED", state_path=self.state_file)

        # Success job should not be retryable
        key_succ = "user:bob:daily_close:2026-09-21:2100"
        claim_execution(key_succ, {"job": "daily_close", "scope": "user", "username": "bob", "scheduled_time": "21:00"}, now=now, state_path=self.state_file)
        record_execution_success(key_succ, now=now, state_path=self.state_file)

        retryables = get_retryable_executions(now + timedelta(minutes=1), path=self.state_file)
        self.assertEqual(len(retryables), 1)
        self.assertEqual(retryables[0]["key"], key_fail)

        # If date is tomorrow, today's failure is not retried
        tomorrow = now + timedelta(days=1)
        retryables_tomorrow = get_retryable_executions(tomorrow, path=self.state_file)
        self.assertEqual(len(retryables_tomorrow), 0)

    # 13. Corrupt state file fails closed
    def test_corrupt_state_file_fails_closed(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text("NOT_VALID_JSON{{{", encoding="utf-8")

        with self.assertRaises(ExecutionStateCorruptError):
            load_execution_state(self.state_file)

        # Invalid schema (missing executions)
        self.state_file.write_text(json.dumps({"version": 2}), encoding="utf-8")
        with self.assertRaises(ExecutionStateCorruptError):
            load_execution_state(self.state_file)

    # 14. Multithreaded claim contention protection
    def test_multithreaded_claim_contention(self):
        now = self._make_kst_dt(9, 0, 0)
        key = "global:ipo_refresh_morning:2026-09-21:0730"
        job_desc = {"job": "ipo_refresh_morning", "scope": "global", "scheduled_time": "07:30"}

        results = []
        threads = []

        def worker():
            res = claim_execution(key, job_desc, now=now, state_path=self.state_file)
            results.append(res)

        for _ in range(8):
            t = threading.Thread(target=worker)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        claimed_count = sum(1 for r in results if r["claimed"])
        self.assertEqual(claimed_count, 1)
        rejections = [r for r in results if not r["claimed"]]
        self.assertEqual(len(rejections), 7)
        for r in rejections:
            self.assertEqual(r["reason"], "ALREADY_RUNNING")

    # 15. Pruning policy (30 days retention, 1000 records max, protection of running/today's failed)
    def test_pruning_policy(self):
        now = self._make_kst_dt(9, 0, 0, year=2026, month=9, day=21)
        state = {
            "version": 1,
            "updated_at": now.isoformat(),
            "executions": {},
        }

        # Old successful record (> 30 days old) -> should be pruned
        old_dt = now - timedelta(days=35)
        state["executions"]["old_succ"] = {
            "key": "old_succ",
            "status": "SUCCESS",
            "last_attempt_at": old_dt.isoformat(),
            "scheduled_date": "2026-08-15",
        }

        # Old RUNNING record (> 30 days old) -> must NEVER be pruned
        state["executions"]["old_running"] = {
            "key": "old_running",
            "status": "RUNNING",
            "last_attempt_at": old_dt.isoformat(),
            "scheduled_date": "2026-08-15",
        }

        # Today's failed record with attempt < 3 -> must NEVER be pruned
        state["executions"]["today_failed"] = {
            "key": "today_failed",
            "status": "FAILED",
            "last_attempt_at": now.isoformat(),
            "scheduled_date": "2026-09-21",
            "attempt_count": 1,
        }

        pruned = prune_execution_state(state, now, retention_days=30)
        self.assertEqual(pruned, 1)
        self.assertNotIn("old_succ", state["executions"])
        self.assertIn("old_running", state["executions"])
        self.assertIn("today_failed", state["executions"])

    # 16. Section 1: TEST — CROSS-PROCESS CLAIM RACE
    def test_cross_process_claim_race(self):
        import subprocess
        import sys

        now = self._make_kst_dt(7, 30, 0)
        key = "global:ipo_refresh_morning:2026-09-21:0730"
        job_desc = {
            "job": "ipo_refresh_morning",
            "scope": "global",
            "owner": "alice",
            "scheduled_time": "07:30",
            "scheduled_date": "2026-09-21",
        }

        # Subprocess script to claim the execution
        worker_code = (
            "import sys, json\n"
            "from datetime import datetime\n"
            "from pathlib import Path\n"
            "from app.services.automation.execution_state import claim_execution\n"
            f"now = datetime.fromisoformat('{now.isoformat()}')\n"
            f"state_path = Path(r'{self.state_file}')\n"
            f"key = '{key}'\n"
            f"job_desc = {json.dumps(job_desc)}\n"
            "res = claim_execution(key, job_desc, now=now, state_path=state_path)\n"
            "print(json.dumps({'claimed': res['claimed'], 'reason': res['reason']}))\n"
        )

        p1 = subprocess.Popen([sys.executable, "-c", worker_code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        p2 = subprocess.Popen([sys.executable, "-c", worker_code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        out1, err1 = p1.communicate(timeout=10)
        out2, err2 = p2.communicate(timeout=10)

        self.assertEqual(p1.returncode, 0, f"Process 1 failed: {err1}")
        self.assertEqual(p2.returncode, 0, f"Process 2 failed: {err2}")

        r1 = json.loads(out1.strip().splitlines()[-1])
        r2 = json.loads(out2.strip().splitlines()[-1])

        results = [r1, r2]
        claimed = [r for r in results if r["claimed"]]
        unclaimed = [r for r in results if not r["claimed"]]

        self.assertEqual(len(claimed), 1, f"Expected exactly 1 claim, got: {results}")
        self.assertEqual(len(unclaimed), 1)
        self.assertEqual(unclaimed[0]["reason"], "ALREADY_RUNNING")

        # Verify state file consistency
        state = load_execution_state(self.state_file)
        self.assertIn(key, state["executions"])
        self.assertEqual(state["executions"][key]["status"], "RUNNING")
        self.assertEqual(state["executions"][key]["attempt_count"], 1)

    # 17. Section 2: TEST — CROSS-PROCESS SUCCESS DEDUPE
    def test_cross_process_success_dedupe(self):
        import subprocess
        import sys

        now = self._make_kst_dt(7, 30, 0)
        key = "global:ipo_refresh_morning:2026-09-21:0730"
        job_desc = {"job": "ipo_refresh_morning", "scope": "global", "owner": "alice", "scheduled_time": "07:30"}

        # Process A claims and completes SUCCESS
        worker_a = (
            "import sys, json\n"
            "from datetime import datetime\n"
            "from pathlib import Path\n"
            "from app.services.automation.execution_state import claim_execution, record_execution_success\n"
            f"now = datetime.fromisoformat('{now.isoformat()}')\n"
            f"state_path = Path(r'{self.state_file}')\n"
            f"key = '{key}'\n"
            f"job_desc = {json.dumps(job_desc)}\n"
            "claim_execution(key, job_desc, now=now, state_path=state_path)\n"
            "record_execution_success(key, now=now, details={'total_ipos': 5}, state_path=state_path)\n"
            "print('OK')\n"
        )
        pa = subprocess.run([sys.executable, "-c", worker_a], capture_output=True, text=True, check=True)
        self.assertIn("OK", pa.stdout)

        # Process B spawns and claims same key -> ALREADY_SUCCESS
        worker_b = (
            "import sys, json\n"
            "from datetime import datetime\n"
            "from pathlib import Path\n"
            "from app.services.automation.execution_state import claim_execution\n"
            f"now = datetime.fromisoformat('{now.isoformat()}')\n"
            f"state_path = Path(r'{self.state_file}')\n"
            f"key = '{key}'\n"
            f"job_desc = {json.dumps(job_desc)}\n"
            "res = claim_execution(key, job_desc, now=now, state_path=state_path)\n"
            "print(json.dumps({'claimed': res['claimed'], 'reason': res['reason']}))\n"
        )
        pb = subprocess.run([sys.executable, "-c", worker_b], capture_output=True, text=True, check=True)
        rb = json.loads(pb.stdout.strip().splitlines()[-1])
        self.assertFalse(rb["claimed"])
        self.assertEqual(rb["reason"], "ALREADY_SUCCESS")

    # 18. Section 8: TEST — STALE RUNNING AUDITABILITY
    def test_stale_running_preserves_audit_info(self):
        t0 = self._make_kst_dt(9, 0, 0)
        key = "user:alice:daily_close:2026-09-21:2100"
        job_desc = {"job": "daily_close", "scope": "user", "username": "alice", "scheduled_time": "21:00"}
        claim_execution(key, job_desc, now=t0, state_path=self.state_file)

        t_stale = t0 + timedelta(minutes=16)
        res = claim_execution(key, job_desc, now=t_stale, state_path=self.state_file, stale_seconds=900.0)
        self.assertTrue(res["claimed"])
        self.assertEqual(res["reason"], "STALE_RETRY")

        rec = res["record"]
        self.assertEqual(rec["attempt_count"], 2)
        self.assertEqual(rec["last_error_code"], "STALE_RECOVERY")
        self.assertEqual(rec["previous_attempt_at"], t0.isoformat())
        self.assertEqual(rec["stale_recovered_at"], t_stale.isoformat())
        self.assertEqual(rec["last_attempt_at"], t_stale.isoformat())

    # 19. Section 9: TEST — STALE BOUNDARY EXACT COMPARISON
    def test_stale_boundary_exact_comparison(self):
        t0 = self._make_kst_dt(9, 0, 0)
        key = "user:bob:daily_close:2026-09-21:2100"
        job_desc = {"job": "daily_close", "scope": "user", "username": "bob", "scheduled_time": "21:00"}
        claim_execution(key, job_desc, now=t0, state_path=self.state_file)

        # Case 1: 14 minutes 59 seconds (899s < 900s) -> NOT STALE -> ALREADY_RUNNING
        t_sub_boundary = t0 + timedelta(minutes=14, seconds=59)
        res1 = claim_execution(key, job_desc, now=t_sub_boundary, state_path=self.state_file, stale_seconds=900.0)
        self.assertFalse(res1["claimed"])
        self.assertEqual(res1["reason"], "ALREADY_RUNNING")

        # Case 2: Exactly 15 minutes (900s >= 900s) -> STALE -> STALE_RETRY
        t_exact_boundary = t0 + timedelta(minutes=15, seconds=0)
        res2 = claim_execution(key, job_desc, now=t_exact_boundary, state_path=self.state_file, stale_seconds=900.0)
        self.assertTrue(res2["claimed"])
        self.assertEqual(res2["reason"], "STALE_RETRY")
        self.assertEqual(res2["record"]["attempt_count"], 2)

    # 20. Section 3 & 6: TEST — PRESERVATION OF OWNER AND IS_LAST_SLOT METADATA
    def test_first_claim_preserves_owner_and_is_last_slot_metadata(self):
        now = self._make_kst_dt(9, 0, 0)
        g_key = "global:ipo_refresh_morning:2026-09-21:0730"
        g_desc = {"job": "ipo_refresh_morning", "scope": "global", "owner": "alice", "scheduled_time": "07:30"}
        r_g = claim_execution(g_key, g_desc, now=now, state_path=self.state_file)
        self.assertEqual(r_g["record"]["owner"], "alice")

        u_key = "user:alice:ipo_reminder:2026-09-21:1500"
        u_desc = {"job": "ipo_reminder", "scope": "user", "username": "alice", "slot": "1500", "is_last_slot": True, "scheduled_time": "15:00"}
        r_u = claim_execution(u_key, u_desc, now=now, state_path=self.state_file)
        self.assertTrue(r_u["record"]["is_last_slot"])
