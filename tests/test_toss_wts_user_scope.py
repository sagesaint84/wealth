"""Security and isolation tests for user-scoped Toss WTS architecture.

Requirements verified:
- user A login does not modify user B session/config
- user A cannot read B status
- user A cannot fetch B QR
- user A cannot cancel B attempt
- simultaneous A/B login use independent guards
- A login blocks A extend
- A login does not block B login/extend
- maintenance uses correct per-user config-dir
- dispatcher execution key user-scoped
- filesystem traversal username rejected/impossible
- no session/cookie/path/raw stdout/stderr exposure
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 23, 20, 55, tzinfo=KST)

USER_A = "alice"
USER_B = "bob"


def _make_settings(tmp: Path) -> dict:
    exe = tmp / "tossctl"
    exe.write_text("x")
    return {
        "enabled": True,
        "executable": str(exe),
        "expected_version": "v0.50.3",
        "timeout_seconds": 20,
        "session_check_enabled": True,
        "session_check_time": "20:55",
        "session_extend_threshold_hours": 48,
        "session_extend_timeout_seconds": 300,
    }


def _create_user_config(tmp: Path, username: str, session_data: str = "{}") -> Path:
    cfg = tmp / "toss-wts" / "users" / username / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "session.json").write_text(session_data, encoding="utf-8")
    return cfg


class UserScopeSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = {"WEALTH_DATA_DIR": str(self.root)}
        self.settings = _make_settings(self.root)
        _create_user_config(self.root, USER_A, '{"user": "alice_session"}')
        _create_user_config(self.root, USER_B, '{"user": "bob_session"}')
        self.pid_alive = patch(
            "app.services.toss_wts_auth_guard.pid_alive", return_value=True
        )
        self.pid_alive.start()
        self.addCleanup(self.pid_alive.stop)
        import app.services.toss_wts_login as login
        self._started_attempt_ids = []

        def register_pending_watcher(attempt_id, _proc):
            with login._watcher_lock:
                login._watcher_registry[attempt_id] = {
                    "reaped": False,
                    "exit_code": None,
                }
            self._started_attempt_ids.append(attempt_id)

        self.watcher = patch.object(
            login, "_start_watcher", side_effect=register_pending_watcher
        )
        self.watcher.start()
        self.addCleanup(self.watcher.stop)

    def tearDown(self):
        import app.services.toss_wts_auth_guard as g
        import app.services.toss_wts_login as login
        with login._watcher_lock:
            for attempt_id in self._started_attempt_ids:
                login._watcher_registry.pop(attempt_id, None)
        for u in (USER_A, USER_B):
            lock = g._get_thread_lock(u)
            if lock.locked():
                try:
                    lock.release()
                except RuntimeError:
                    pass
            try:
                with patch.dict(os.environ, self.env):
                    g._lock_path(u).with_suffix(".lock.held").unlink(missing_ok=True)
            except Exception:
                pass
        self.temp.cleanup()

    # -----------------------------------------------------------------------
    # 1. user A login does not modify user B session/config
    # -----------------------------------------------------------------------
    def test_user_a_login_does_not_modify_user_b_session(self):
        import app.services.toss_wts_login as m

        b_session_path = self.root / "toss-wts" / "users" / USER_B / "config" / "session.json"
        b_content_before = b_session_path.read_text(encoding="utf-8")

        proc_a = Mock()
        proc_a.pid = 10001
        proc_a.wait = Mock(return_value=0)

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time", return_value=None), \
             patch("app.services.toss_wts_session.get_toss_session_status", return_value={"active": False, "valid": False}):
            aid_a = m.start_toss_login(self.settings, username=USER_A, _popen=Mock(return_value=proc_a), now_provider=lambda: NOW)

        b_content_after = b_session_path.read_text(encoding="utf-8")
        self.assertEqual(b_content_before, b_content_after, "User B's session.json must remain completely untouched")

        # Cleanup
        with m._watcher_lock:
            m._watcher_registry.pop(aid_a, None)

    # -----------------------------------------------------------------------
    # 2. user A cannot read B status
    # -----------------------------------------------------------------------
    def test_user_a_cannot_read_user_b_attempt_status(self):
        import app.services.toss_wts_login as m

        proc_b = Mock()
        proc_b.pid = 10002
        proc_b.wait = Mock(return_value=0)

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time", return_value=None), \
             patch("app.services.toss_wts_session.get_toss_session_status", return_value={"active": False, "valid": False}):
            aid_b = m.start_toss_login(self.settings, username=USER_B, _popen=Mock(return_value=proc_b), now_provider=lambda: NOW)

        # Alice attempts to inspect Bob's attempt ID
        with patch.dict(os.environ, self.env):
            with self.assertRaises(m.TossLoginNotFoundError):
                m.get_login_attempt(aid_b, requesting_username=USER_A, settings=self.settings)

            # Bob can inspect his own
            res_b = m.get_login_attempt(aid_b, requesting_username=USER_B, settings=self.settings)
            self.assertEqual(res_b["attempt_id"], aid_b)
            self.assertEqual(res_b["owner"], USER_B)

        with m._watcher_lock:
            m._watcher_registry.pop(aid_b, None)

    # -----------------------------------------------------------------------
    # 3. user A cannot fetch B QR
    # -----------------------------------------------------------------------
    def test_user_a_cannot_fetch_user_b_qr(self):
        import app.services.toss_wts_login as m
        from app.services.toss_wts_auth_guard import user_login_dir

        proc_b = Mock()
        proc_b.pid = 10003
        proc_b.wait = Mock(return_value=0)

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time", return_value=None), \
             patch("app.services.toss_wts_session.get_toss_session_status", return_value={"active": False, "valid": False}):
            aid_b = m.start_toss_login(self.settings, username=USER_B, _popen=Mock(return_value=proc_b), now_provider=lambda: NOW)

        # Create mock QR file in Bob's login dir
        with patch.dict(os.environ, self.env):
            qr_b = user_login_dir(USER_B) / f"{aid_b}.qr.png"
            qr_b.write_bytes(b"\x89PNG\r\n\x1a\nfakeqr")

            # Alice tries to fetch Bob's QR -> None
            qr_alice_fetch = m.get_login_qr(aid_b, requesting_username=USER_A)
            self.assertIsNone(qr_alice_fetch)

            # Bob fetches his own QR -> returns bytes
            qr_bob_fetch = m.get_login_qr(aid_b, requesting_username=USER_B)
            self.assertEqual(qr_bob_fetch, b"\x89PNG\r\n\x1a\nfakeqr")

        with m._watcher_lock:
            m._watcher_registry.pop(aid_b, None)

    # -----------------------------------------------------------------------
    # 4. user A cannot cancel B attempt
    # -----------------------------------------------------------------------
    def test_user_a_cannot_cancel_user_b_attempt(self):
        import app.services.toss_wts_login as m

        proc_b = Mock()
        proc_b.pid = 10004
        proc_b.wait = Mock(return_value=0)

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time", return_value=None), \
             patch("app.services.toss_wts_session.get_toss_session_status", return_value={"active": False, "valid": False}):
            aid_b = m.start_toss_login(self.settings, username=USER_B, _popen=Mock(return_value=proc_b), now_provider=lambda: NOW)

        with m._watcher_lock:
            m._watcher_registry[aid_b] = {"reaped": False, "exit_code": None}


        with patch.dict(os.environ, self.env):
            with self.assertRaises(m.TossLoginNotFoundError):
                m.cancel_login_attempt(aid_b, requesting_username=USER_A)

            # Bob's attempt must still be pending
            status_b = m.get_login_attempt(aid_b, requesting_username=USER_B, settings=self.settings)
            self.assertEqual(status_b["status"], m.STATUS_PENDING)

        with m._watcher_lock:
            m._watcher_registry.pop(aid_b, None)

    # -----------------------------------------------------------------------
    # 5. simultaneous A/B login use independent guards
    # -----------------------------------------------------------------------
    def test_simultaneous_ab_login_use_independent_guards(self):
        import app.services.toss_wts_login as m

        proc_a = Mock(); proc_a.pid = 10005; proc_a.wait = Mock(return_value=0)
        proc_b = Mock(); proc_b.pid = 10006; proc_b.wait = Mock(return_value=0)

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time", return_value=None), \
             patch("app.services.toss_wts_session.get_toss_session_status", return_value={"active": False, "valid": False}):
            aid_a = m.start_toss_login(self.settings, username=USER_A, _popen=Mock(return_value=proc_a), now_provider=lambda: NOW)
            aid_b = m.start_toss_login(self.settings, username=USER_B, _popen=Mock(return_value=proc_b), now_provider=lambda: NOW)

        self.assertNotEqual(aid_a, aid_b)
        with m._watcher_lock:
            self.assertIn(aid_a, m._watcher_registry)
            self.assertIn(aid_b, m._watcher_registry)
            m._watcher_registry.pop(aid_a, None)
            m._watcher_registry.pop(aid_b, None)

    # -----------------------------------------------------------------------
    # 6. A login blocks A extend, but does NOT block B login/extend
    # -----------------------------------------------------------------------
    def test_a_login_blocks_a_extend_but_does_not_block_b_login_or_extend(self):
        import app.services.toss_wts_login as m
        import app.services.toss_wts_auth_guard as g
        from app.services.toss_wts_session import run_toss_session_maintenance

        # Start Alice login
        proc_a = Mock(); proc_a.pid = 10007; proc_a.wait = Mock(return_value=0)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time", return_value=None), \
             patch("app.services.toss_wts_session.get_toss_session_status", return_value={"active": False, "valid": False}):
            aid_a = m.start_toss_login(self.settings, username=USER_A, _popen=Mock(return_value=proc_a), now_provider=lambda: NOW)

        # Alice extend is deferred because Alice login marker is active
        expiry = (NOW + timedelta(hours=24)).isoformat()
        st_json = f'{{"active": true, "valid": true, "server_expires_at": "{expiry}"}}'
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, st_json, ""))

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
            res_a = run_toss_session_maintenance(USER_A, now=NOW, settings=self.settings, run=runner, sender=Mock())
            self.assertEqual(res_a["action"], "deferred")
            self.assertEqual(res_a["error_code"], "AUTH_LOGIN_IN_PROGRESS")

            # But Bob's extend is NOT blocked by Alice's login!
            # Bob has valid session with hours_remaining=72 -> not_required
            st_b_json = f'{{"active": true, "valid": true, "server_expires_at": "{(NOW + timedelta(hours=72)).isoformat()}"}}'
            runner_b = Mock(return_value=subprocess.CompletedProcess([], 0, st_b_json, ""))
            res_b = run_toss_session_maintenance(USER_B, now=NOW, settings=self.settings, run=runner_b, sender=Mock())
            self.assertEqual(res_b["action"], "not_required")

        with m._watcher_lock:
            m._watcher_registry.pop(aid_a, None)

    # -----------------------------------------------------------------------
    # 7. maintenance uses correct per-user config-dir
    # -----------------------------------------------------------------------
    def test_maintenance_uses_correct_per_user_config_dir(self):
        from app.services.toss_wts_session import run_toss_session_maintenance

        captured_args = []
        def run_capture(argv, **kwargs):
            captured_args.append(list(argv))
            expiry = (NOW + timedelta(hours=24)).isoformat()
            if "extend" in argv:
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 0, f'{{"active": true, "valid": true, "server_expires_at": "{expiry}"}}', "")

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
            run_toss_session_maintenance(USER_A, now=NOW, settings=self.settings, run=run_capture, sender=Mock())

        # Verify that all calls used USER_A config dir
        for argv in captured_args:
            idx = argv.index("--config-dir")
            cfg_dir = argv[idx + 1]
            self.assertIn(USER_A, cfg_dir)
            self.assertNotIn(USER_B, cfg_dir)

    # -----------------------------------------------------------------------
    # 8. dispatcher execution key user-scoped
    # -----------------------------------------------------------------------
    def test_dispatcher_execution_key_user_scoped(self):
        from app.services.automation.dispatcher import resolve_due_jobs

        state_path = self.root / "execution.json"
        with patch.dict(os.environ, self.env), \
             patch("app.services.automation.dispatcher.list_users", return_value=[{"username": USER_A}, {"username": USER_B}]), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value={}), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value={"automation": {}, "toss_wts": {"session_check_enabled": True}}), \
             patch("app.services.system_settings.resolve_toss_wts_settings", return_value=self.settings):
            jobs = resolve_due_jobs(NOW, state_path=state_path)

        toss_jobs = [j for j in jobs if j.get("job") == "toss_session_maintenance"]
        self.assertEqual(len(toss_jobs), 2, "Must generate one job per registered user")

        owners = {j["owner"] for j in toss_jobs}
        self.assertEqual(owners, {USER_A, USER_B})

        for j in toss_jobs:
            self.assertEqual(j["scope"], "user")
            self.assertEqual(j["execution_key"], f"user:{j['owner']}:toss_session_maintenance:2026-09-23:2055")

    # -----------------------------------------------------------------------
    # 9. filesystem traversal username rejected/impossible
    # -----------------------------------------------------------------------
    def test_filesystem_traversal_username_rejected(self):
        from app.services.toss_wts_auth_guard import _validate_username
        import app.services.toss_wts_login as m

        dangerous_usernames = [
            "../etc/passwd",
            "..\\windows\\system32",
            "user/../admin",
            "user/name",
            "",
            "a" * 65,  # too long
            "user;rm -rf /",
            "user$NAME",
            "user name",
        ]
        for bad_name in dangerous_usernames:
            with self.assertRaises(ValueError):
                _validate_username(bad_name)

            with patch.dict(os.environ, self.env):
                with self.assertRaises(ValueError):
                    m.start_toss_login(self.settings, username=bad_name)

    # -----------------------------------------------------------------------
    # 10. no session/cookie/path/raw stdout/stderr exposure
    # -----------------------------------------------------------------------
    def test_no_sensitive_metadata_exposure_in_public_status(self):
        import app.services.toss_wts_login as m

        meta = {
            "attempt_id": "test-id-123",
            "owner": USER_A,
            "status": "pending",
            "started_at": NOW.isoformat(),
            "finished_at": None,
            "error_code": None,
            "_pid": 9999,
            "_pid_start_time": "123456",
            "stdout": "raw output from subprocess",
            "stderr": "raw stderr from subprocess",
            "cookie": "session_token_12345",
            "config_dir": "/app/data/toss-wts/users/alice/config",
        }
        public_dict = m._safe_public(meta)
        self.assertNotIn("_pid", public_dict)
        self.assertNotIn("_pid_start_time", public_dict)
        self.assertNotIn("stdout", public_dict)
        self.assertNotIn("stderr", public_dict)
        self.assertNotIn("cookie", public_dict)
        self.assertNotIn("config_dir", public_dict)
        self.assertEqual(public_dict["owner"], USER_A)
        self.assertEqual(public_dict["attempt_id"], "test-id-123")


if __name__ == "__main__":
    unittest.main()
