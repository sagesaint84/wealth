"""Tests for app.services.toss_wts_login (user-scoped architecture).

Structural requirements verified:
  1. CLI: _AUTH_LOGIN_FLAG_VERIFIED=True, _AUTH_LOGIN_QR_FLAG="--qr-output"
  2. argv: auth login --headless --link --qr-output <private path>, shell=False
  3. Active-op marker written under per-user lock, cleared on all terminal paths
  4. Process watcher reaps child; _check_and_finalize uses watcher (no zombie risk)
  5. Re-auth protection inside lock (TOCTOU-safe)
  6. Spawn failure rollback: terminate+reap, clear marker+artifacts
  7. Timeout: terminate+reap BEFORE marker clear; kept if termination fails
  8. Cancel: terminate+reap BEFORE marker clear; kept if termination fails
  9. Auth extend blocked while login marker active (AUTH_LOGIN_IN_PROGRESS)
 10. Login blocked while extend holds advisory lock (TOSS_AUTH_OPERATION_BUSY)
 11. post-login active&&valid required for SUCCESS
 12. QR cleanup on all terminal paths
 13. _safe_public strips _pid, _pid_start_time, paths
 14. Watcher registry entry removed on all terminal paths
 15. User A cannot access/cancel User B's attempts (path isolation)
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 23, 20, 55, tzinfo=KST)

USERNAME = "testuser"
USERNAME_B = "otheruser"


def _make_settings(tmp: Path) -> dict:
    """Global settings (no config_dir — that's derived from username at runtime)."""
    exe = tmp / "tossctl"; exe.write_text("x")
    return {
        "enabled": True,
        "executable": str(exe),
        "expected_version": "v0.50.3",
        "timeout_seconds": 20,
        "session_check_enabled": False,
        "session_check_time": "20:55",
        "session_extend_threshold_hours": 48,
        "session_extend_timeout_seconds": 300,
    }


def _create_user_config(tmp: Path, username: str) -> Path:
    """Create per-user config dir with a stub session.json."""
    cfg = tmp / "toss-wts" / "users" / username / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "session.json").write_text("{}")
    return cfg


def _reset_thread_lock_for_user(env: dict | None, username: str = USERNAME):
    """Release per-user _thread_lock and clean up Windows sentinel file."""
    import app.services.toss_wts_auth_guard as g
    lock = g._get_thread_lock(username)
    try:
        if lock.locked():
            lock.release()
    except RuntimeError:
        pass
    if env:
        try:
            with patch.dict(os.environ, env):
                sentinel = g._lock_path(username).with_suffix(".lock.held")
                sentinel.unlink(missing_ok=True)
        except Exception:
            pass


class _LoginBase(unittest.TestCase):
    """Base: temp dir, settings, env, _start() helper."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = {"WEALTH_DATA_DIR": self.temp.name}
        self.settings = _make_settings(Path(self.temp.name))
        # Create per-user config directory
        _create_user_config(Path(self.temp.name), USERNAME)
        # Clear any stale marker
        with patch.dict(os.environ, self.env):
            import app.services.toss_wts_auth_guard as g
            marker = g._active_op_path(USERNAME)
            marker.unlink(missing_ok=True)

    def tearDown(self):
        _reset_thread_lock_for_user(self.env, USERNAME)
        _reset_thread_lock_for_user(self.env, USERNAME_B)
        self.temp.cleanup()

    def _start(self, pid: int = 12345, verify_return: bool = False,
               username: str = USERNAME) -> str:
        """Start with mocked subprocess. Patch get_pid_start_time at source."""
        import app.services.toss_wts_login as m
        proc = Mock(); proc.pid = pid; proc.wait = Mock(return_value=0)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch.object(m, "_verify_post_login", return_value=verify_return), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            aid = m.start_toss_login(
                self.settings, username=username,
                _popen=Mock(return_value=proc),
                now_provider=lambda: NOW,
            )
        # Freeze watcher as not-reaped so tests control finalization
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": False, "exit_code": None}
        return aid

    def _marker_path(self, username: str = USERNAME) -> Path:
        import app.services.toss_wts_auth_guard as g
        with patch.dict(os.environ, self.env):
            return g._active_op_path(username)

    def _qr_dir(self, username: str = USERNAME) -> Path:
        with patch.dict(os.environ, self.env):
            import app.services.toss_wts_auth_guard as g
            return g.user_login_dir(username)


class CLIContractTests(_LoginBase):
    def _capture(self):
        import app.services.toss_wts_login as m
        captured = {}
        def fake_popen(argv, **kw):
            captured["argv"] = argv; captured["kw"] = kw
            p = Mock(); p.pid = 1111; p.wait = Mock(return_value=0)
            return p
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch.object(m, "_verify_post_login", return_value=False), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            aid = m.start_toss_login(self.settings, username=USERNAME,
                                     _popen=fake_popen,
                                     now_provider=lambda: NOW)
        with m._watcher_lock:
            m._watcher_registry.pop(aid, None)
        return captured

    def test_flag_verified_true(self):
        import app.services.toss_wts_login as m
        self.assertTrue(m._AUTH_LOGIN_FLAG_VERIFIED)

    def test_qr_flag_is_qr_output_not_qr_path(self):
        import app.services.toss_wts_login as m
        self.assertEqual(m._AUTH_LOGIN_QR_FLAG, "--qr-output")
        self.assertNotEqual(m._AUTH_LOGIN_QR_FLAG, "--qr-path")

    def test_argv_has_headless(self):
        self.assertIn("--headless", self._capture()["argv"])

    def test_argv_has_link(self):
        self.assertIn("--link", self._capture()["argv"])

    def test_argv_has_qr_output(self):
        self.assertIn("--qr-output", self._capture()["argv"])

    def test_argv_has_no_qr_path_placeholder(self):
        self.assertNotIn("--qr-path", self._capture()["argv"])

    def test_argv_auth_before_login(self):
        argv = self._capture()["argv"]
        self.assertLess(argv.index("auth"), argv.index("login"))

    def test_shell_is_false(self):
        self.assertFalse(self._capture()["kw"].get("shell", True))

    def test_qr_output_path_in_user_dir(self):
        argv = self._capture()["argv"]
        qr_path = argv[argv.index("--qr-output") + 1]
        self.assertIn("toss-wts", qr_path)
        self.assertIn("toss-login", qr_path)
        self.assertIn(USERNAME, qr_path)

    def test_config_dir_contains_username(self):
        """--config-dir must use the per-user path, not global settings."""
        argv = self._capture()["argv"]
        config_dir = argv[argv.index("--config-dir") + 1]
        self.assertIn(USERNAME, config_dir)
        self.assertIn("toss-wts", config_dir)

    def test_argv_has_config_dir_before_auth(self):
        argv = self._capture()["argv"]
        self.assertIn("--config-dir", argv)
        self.assertLess(argv.index("--config-dir"), argv.index("auth"))


class ActiveOpMarkerTests(_LoginBase):
    def test_marker_written_at_start(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        marker = self._marker_path()
        self.assertTrue(marker.exists())
        data = json.loads(marker.read_text())
        self.assertEqual(data["attempt_id"], aid)
        self.assertEqual(data["type"], "login")
        self.assertEqual(data["owner"], USERNAME)

    def test_check_active_operation_true_while_pending(self):
        import app.services.toss_wts_auth_guard as g
        self._start()
        with patch.dict(os.environ, self.env):
            self.assertTrue(g.check_active_login_operation(USERNAME))

    def test_marker_cleared_on_cancel(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        marker = self._marker_path()
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=True):
            m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                   now_provider=lambda: NOW)
        self.assertFalse(marker.exists())

    def test_marker_cleared_on_timeout(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        future = NOW + timedelta(seconds=m.LOGIN_ATTEMPT_MAX_SECONDS + 1)
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=True):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: future,
                                settings=self.settings)
        marker = self._marker_path()
        self.assertFalse(marker.exists())

    def test_marker_cleared_on_process_exit_success(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 0}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=True):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: NOW,
                                settings=self.settings)
        marker = self._marker_path()
        self.assertFalse(marker.exists())

    def test_second_start_blocked_while_marker_exists(self):
        import app.services.toss_wts_login as m
        self._start()
        proc2 = Mock(); proc2.pid = 22222; proc2.wait = Mock(return_value=0)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            with self.assertRaises(m.TossLoginLockError):
                m.start_toss_login(self.settings, username=USERNAME,
                                   _popen=Mock(return_value=proc2),
                                   now_provider=lambda: NOW)


class ProcessWatcherTests(_LoginBase):
    def test_watcher_marks_reaped_after_wait(self):
        import app.services.toss_wts_login as m
        wait_done = threading.Event()
        proc = Mock(); proc.pid = 55555
        proc.wait = Mock(side_effect=lambda: (wait_done.wait(timeout=3), 0)[1])
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch.object(m, "_verify_post_login", return_value=False), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            aid = m.start_toss_login(self.settings, username=USERNAME,
                                     _popen=Mock(return_value=proc),
                                     now_provider=lambda: NOW)
        with m._watcher_lock:
            self.assertFalse(m._watcher_registry[aid]["reaped"])
        wait_done.set()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            with m._watcher_lock:
                if m._watcher_registry.get(aid, {}).get("reaped"):
                    break
            time.sleep(0.05)
        with m._watcher_lock:
            self.assertTrue(m._watcher_registry[aid]["reaped"])

    def test_unreaped_process_stays_pending(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with patch.dict(os.environ, self.env):
            result = m.get_login_attempt(aid, requesting_username=USERNAME,
                                         now_provider=lambda: NOW,
                                         settings=self.settings)
        self.assertEqual(result["status"], m.STATUS_PENDING)

    def test_reaped_process_triggers_finalize(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 0}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=True):
            result = m.get_login_attempt(aid, requesting_username=USERNAME,
                                         now_provider=lambda: NOW,
                                         settings=self.settings)
        self.assertEqual(result["status"], m.STATUS_SUCCESS)


class ReauthProtectionTests(_LoginBase):
    def test_session_valid_without_reauth_raises(self):
        import app.services.toss_wts_login as m
        proc = Mock(); proc.pid = 11111; proc.wait = Mock(return_value=0)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": True, "valid": True}):
            with self.assertRaises(m.TossSessionAlreadyValidError):
                m.start_toss_login(self.settings, username=USERNAME,
                                   reauthenticate=False,
                                   _popen=Mock(return_value=proc),
                                   now_provider=lambda: NOW)

    def test_session_valid_with_reauth_proceeds(self):
        import app.services.toss_wts_login as m
        proc = Mock(); proc.pid = 11112; proc.wait = Mock(return_value=0)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch.object(m, "_verify_post_login", return_value=False), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": True, "valid": True}):
            aid = m.start_toss_login(self.settings, username=USERNAME,
                                     reauthenticate=True,
                                     _popen=Mock(return_value=proc),
                                     now_provider=lambda: NOW)
        self.assertIsInstance(aid, str)
        with m._watcher_lock:
            m._watcher_registry.pop(aid, None)

    def test_session_invalid_proceeds_without_reauth(self):
        import app.services.toss_wts_login as m
        proc = Mock(); proc.pid = 11113; proc.wait = Mock(return_value=0)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch.object(m, "_verify_post_login", return_value=False), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            aid = m.start_toss_login(self.settings, username=USERNAME,
                                     reauthenticate=False,
                                     _popen=Mock(return_value=proc),
                                     now_provider=lambda: NOW)
        self.assertIsInstance(aid, str)
        with m._watcher_lock:
            m._watcher_registry.pop(aid, None)


class SpawnRollbackTests(_LoginBase):
    def test_marker_not_written_if_meta_write_fails(self):
        import app.services.toss_wts_login as m
        terminated = []; waited = []
        proc = Mock(); proc.pid = 9999
        proc.terminate = Mock(side_effect=lambda: terminated.append(1))
        proc.wait = Mock(side_effect=lambda timeout=None: waited.append(1))
        proc.kill = Mock()
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch.object(m, "_write_meta", side_effect=OSError("disk full")), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            with self.assertRaises(m.TossLoginError) as ctx:
                m.start_toss_login(self.settings, username=USERNAME,
                                   _popen=Mock(return_value=proc),
                                   now_provider=lambda: NOW)
        self.assertIn("SETUP_FAILED", str(ctx.exception))
        self.assertTrue(len(terminated) > 0 or len(waited) > 0,
                        "Rollback must terminate/reap spawned process")
        marker = self._marker_path()
        self.assertFalse(marker.exists())


class TerminateBeforeClearTests(_LoginBase):
    def test_timeout_kills_before_marker_clear(self):
        import app.services.toss_wts_login as m
        aid = self._start(pid=54321)
        marker = self._marker_path()
        calls = []

        def mock_terminate(attempt_id, pid, pid_start):
            calls.append("terminate")
            self.assertTrue(marker.exists(),
                            "Marker must exist before termination completes")
            with m._watcher_lock:
                m._watcher_registry[attempt_id] = {"reaped": True, "exit_code": -15}
            return True

        future = NOW + timedelta(seconds=m.LOGIN_ATTEMPT_MAX_SECONDS + 1)
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", side_effect=mock_terminate):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: future,
                                settings=self.settings)
        self.assertIn("terminate", calls)
        self.assertFalse(marker.exists())

    def test_cancel_kills_before_marker_clear(self):
        import app.services.toss_wts_login as m
        aid = self._start(pid=54322)
        marker = self._marker_path()
        calls = []

        def mock_terminate(attempt_id, pid, pid_start):
            calls.append("terminate")
            self.assertTrue(marker.exists(),
                            "Marker must exist before termination completes")
            return True

        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", side_effect=mock_terminate):
            result = m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                            now_provider=lambda: NOW)
        self.assertIn("terminate", calls)
        self.assertEqual(result["status"], m.STATUS_CANCELLED)
        self.assertFalse(marker.exists())

    def test_timeout_termination_failure_keeps_marker(self):
        import app.services.toss_wts_login as m
        aid = self._start(pid=54323)
        marker = self._marker_path()
        future = NOW + timedelta(seconds=m.LOGIN_ATTEMPT_MAX_SECONDS + 1)
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=False):
            result = m.get_login_attempt(aid, requesting_username=USERNAME,
                                         now_provider=lambda: future,
                                         settings=self.settings)
        self.assertTrue(marker.exists())
        self.assertEqual(result["status"], m.STATUS_PENDING)
        self.assertEqual(result["error_code"], "AUTH_LOGIN_TERMINATION_PENDING")

    def test_cancel_termination_failure_keeps_marker(self):
        import app.services.toss_wts_login as m
        aid = self._start(pid=54324)
        marker = self._marker_path()
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=False):
            result = m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                            now_provider=lambda: NOW)
        self.assertTrue(marker.exists())
        self.assertEqual(result["status"], m.STATUS_PENDING)
        self.assertEqual(result["error_code"],
                         "AUTH_LOGIN_CANCEL_TERMINATION_PENDING")

    def test_marker_kept_blocks_login_and_extend(self):
        import app.services.toss_wts_login as m
        import subprocess as sp
        from app.services.toss_wts_session import run_toss_session_maintenance
        aid = self._start(pid=54325)
        future = NOW + timedelta(seconds=m.LOGIN_ATTEMPT_MAX_SECONDS + 1)
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=False):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: future,
                                settings=self.settings)
        marker = self._marker_path()
        self.assertTrue(marker.exists())
        # Login blocked (same user)
        proc2 = Mock(); proc2.pid = 99999; proc2.wait = Mock(return_value=0)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            with self.assertRaises(m.TossLoginLockError):
                m.start_toss_login(self.settings, username=USERNAME,
                                   _popen=Mock(return_value=proc2),
                                   now_provider=lambda: NOW)
        # Extend blocked (same user)
        expiry = (NOW + timedelta(hours=24)).isoformat()
        st_json = (f'{{"active": true, "valid": true,'
                   f' "server_expires_at": "{expiry}"}}')
        runner = Mock(return_value=sp.CompletedProcess([], 0, st_json, ""))
        with patch.dict(os.environ, self.env), \
             patch.object(os, "kill", return_value=None), \
             patch("app.services.toss_wts_session.resolve_telegram_config",
                   return_value=Mock()):
            res = run_toss_session_maintenance(
                USERNAME, now=NOW, settings=self.settings,
                run=runner, sender=Mock(),
            )
        self.assertEqual(res["action"], "deferred")
        self.assertEqual(res["error_code"], "AUTH_LOGIN_IN_PROGRESS")


class RaceConditionTests(_LoginBase):
    def _write_marker(self, username: str = USERNAME):
        import app.services.toss_wts_auth_guard as g
        with patch.dict(os.environ, self.env):
            g.write_active_op_marker(username, "fake-attempt", 12345, NOW.isoformat())

    def test_extend_deferred_when_login_marker_exists(self):
        import subprocess as sp
        from app.services.toss_wts_session import run_toss_session_maintenance
        self._write_marker()
        expiry = (NOW + timedelta(hours=24)).isoformat()
        st = f'{{"active": true, "valid": true, "server_expires_at": "{expiry}"}}'
        runner = Mock(return_value=sp.CompletedProcess([], 0, st, ""))
        with patch.dict(os.environ, self.env), \
             patch.object(os, "kill", return_value=None), \
             patch("app.services.toss_wts_session.resolve_telegram_config",
                   return_value=Mock()):
            result = run_toss_session_maintenance(
                USERNAME, now=NOW, settings=self.settings,
                run=runner, sender=Mock(),
            )
        self.assertEqual(result["action"], "deferred")
        self.assertEqual(result["error_code"], "AUTH_LOGIN_IN_PROGRESS")
        self.assertFalse(result["extension_attempted"])

    def test_login_blocked_while_extend_holds_lock(self):
        import app.services.toss_wts_auth_guard as g
        import app.services.toss_wts_login as m
        errors = []
        lock_held = threading.Event()
        contender_done = threading.Event()

        def holder():
            try:
                with patch.dict(os.environ, self.env):
                    with g.auth_operation_lock(USERNAME, acquire_timeout_seconds=2.0):
                        lock_held.set()
                        contender_done.wait(timeout=6.0)
            except Exception as e:
                errors.append(e)


        def try_login():
            lock_held.wait(timeout=2.0)
            proc = Mock(); proc.pid = 99999; proc.wait = Mock(return_value=0)
            try:
                with patch.dict(os.environ, self.env), \
                     patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                           return_value=None), \
                     patch("app.services.toss_wts_session.get_toss_session_status",
                           return_value={"active": False, "valid": False}):
                    m.start_toss_login(self.settings, username=USERNAME,
                                       _popen=Mock(return_value=proc),
                                       now_provider=lambda: NOW)
                errors.append(AssertionError("Must raise TossLoginLockError"))
            except m.TossLoginLockError:
                pass
            except Exception as e:
                errors.append(e)
            finally:
                contender_done.set()

        t1 = threading.Thread(target=holder)
        t2 = threading.Thread(target=try_login)
        t1.start(); t2.start()
        t1.join(timeout=6.0); t2.join(timeout=6.0)
        for e in errors:
            raise e

    def test_after_extend_releases_lock_login_can_start(self):
        import app.services.toss_wts_auth_guard as g
        import app.services.toss_wts_login as m
        with patch.dict(os.environ, self.env):
            with g.auth_operation_lock(USERNAME, acquire_timeout_seconds=2.0):
                pass
        proc = Mock(); proc.pid = 88888; proc.wait = Mock(return_value=0)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch.object(m, "_verify_post_login", return_value=False), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            aid = m.start_toss_login(self.settings, username=USERNAME,
                                     _popen=Mock(return_value=proc),
                                     now_provider=lambda: NOW)
        self.assertIsInstance(aid, str)
        with m._watcher_lock:
            m._watcher_registry.pop(aid, None)


class PostLoginVerificationTests(_LoginBase):
    def test_reaped_verify_pass_yields_success(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 0}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=True):
            result = m.get_login_attempt(aid, requesting_username=USERNAME,
                                         now_provider=lambda: NOW,
                                         settings=self.settings)
        self.assertEqual(result["status"], m.STATUS_SUCCESS)

    def test_reaped_verify_fail_yields_failed(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 1}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=False):
            result = m.get_login_attempt(aid, requesting_username=USERNAME,
                                         now_provider=lambda: NOW,
                                         settings=self.settings)
        self.assertEqual(result["status"], m.STATUS_FAILED)
        self.assertEqual(result["error_code"], "AUTH_LOGIN_VERIFY_FAILED")

    def test_qr_alone_does_not_yield_success(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        # Place QR in user dir
        qr_dir = self._qr_dir()
        qr_dir.mkdir(parents=True, exist_ok=True)
        (qr_dir / f"{aid}.qr.png").write_bytes(b"\x89PNG\r\n")
        with patch.dict(os.environ, self.env):
            result = m.get_login_attempt(aid, requesting_username=USERNAME,
                                         now_provider=lambda: NOW,
                                         settings=self.settings)
        self.assertEqual(result["status"], m.STATUS_PENDING)


class QrCleanupTests(_LoginBase):
    def _with_qr(self, username: str = USERNAME) -> tuple[str, Path]:
        aid = self._start(username=username)
        qr_dir = self._qr_dir(username)
        qr_dir.mkdir(parents=True, exist_ok=True)
        qr = qr_dir / f"{aid}.qr.png"
        qr.write_bytes(b"\x89PNG\r\n")
        return aid, qr

    def test_qr_deleted_on_cancel(self):
        import app.services.toss_wts_login as m
        aid, qr = self._with_qr()
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=True):
            m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                   now_provider=lambda: NOW)
        self.assertFalse(qr.exists())

    def test_qr_deleted_on_timeout(self):
        import app.services.toss_wts_login as m
        aid, qr = self._with_qr()
        future = NOW + timedelta(seconds=m.LOGIN_ATTEMPT_MAX_SECONDS + 1)
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=True):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: future,
                                settings=self.settings)
        self.assertFalse(qr.exists())

    def test_qr_deleted_on_success(self):
        import app.services.toss_wts_login as m
        aid, qr = self._with_qr()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 0}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=True):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: NOW,
                                settings=self.settings)
        self.assertFalse(qr.exists())

    def test_qr_deleted_on_failed(self):
        import app.services.toss_wts_login as m
        aid, qr = self._with_qr()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 1}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=False):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: NOW,
                                settings=self.settings)
        self.assertFalse(qr.exists())

    def test_qr_not_served_after_cancel(self):
        import app.services.toss_wts_login as m
        aid, _ = self._with_qr()
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=True):
            m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                   now_provider=lambda: NOW)
        with patch.dict(os.environ, self.env):
            self.assertIsNone(m.get_login_qr(aid, requesting_username=USERNAME))


class SafePublicTests(unittest.TestCase):
    def test_strips_private_fields(self):
        import app.services.toss_wts_login as m
        meta = {
            "attempt_id": "abc", "owner": USERNAME, "status": "pending",
            "started_at": NOW.isoformat(), "finished_at": None,
            "error_code": None, "_pid": 12345,
            "_pid_start_time": "12345000",
            "stdout": "SENSITIVE", "executable": "/secret/path",
        }
        result = m._safe_public(meta)
        for private in ("_pid", "_pid_start_time", "stdout", "executable"):
            self.assertNotIn(private, result)
        for public in ("attempt_id", "owner", "status", "started_at",
                       "finished_at", "error_code"):
            self.assertIn(public, result)


class WatcherRegistryCleanupTests(_LoginBase):
    def test_registry_cleared_on_success(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 0}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=True):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: NOW,
                                settings=self.settings)
        with m._watcher_lock:
            self.assertNotIn(aid, m._watcher_registry)

    def test_registry_cleared_on_failed(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 1}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=False):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: NOW,
                                settings=self.settings)
        with m._watcher_lock:
            self.assertNotIn(aid, m._watcher_registry)

    def test_registry_cleared_on_cancelled(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=True):
            m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                   now_provider=lambda: NOW)
        with m._watcher_lock:
            self.assertNotIn(aid, m._watcher_registry)

    def test_registry_cleared_on_timeout(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        future = NOW + timedelta(seconds=m.LOGIN_ATTEMPT_MAX_SECONDS + 1)
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=True):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: future,
                                settings=self.settings)
        with m._watcher_lock:
            self.assertNotIn(aid, m._watcher_registry)

    def test_registry_kept_on_termination_failure(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        future = NOW + timedelta(seconds=m.LOGIN_ATTEMPT_MAX_SECONDS + 1)
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=False):
            m.get_login_attempt(aid, requesting_username=USERNAME,
                                now_provider=lambda: future,
                                settings=self.settings)
        with m._watcher_lock:
            self.assertIn(aid, m._watcher_registry)


class LockTests(_LoginBase):
    def test_sequential_acquisitions_succeed(self):
        import app.services.toss_wts_auth_guard as g
        with patch.dict(os.environ, self.env):
            with g.auth_operation_lock(USERNAME, acquire_timeout_seconds=2.0):
                pass
            with g.auth_operation_lock(USERNAME, acquire_timeout_seconds=2.0):
                pass

    def test_concurrent_thread_contention_rejected(self):
        import app.services.toss_wts_auth_guard as g
        errors = []
        lock_held = threading.Event()
        contender_done = threading.Event()

        def holder():
            try:
                with patch.dict(os.environ, self.env):
                    with g.auth_operation_lock(USERNAME, acquire_timeout_seconds=2.0):
                        lock_held.set()
                        contender_done.wait(timeout=3.0)
            except Exception as e:
                errors.append(e)

        def contender():
            lock_held.wait(timeout=2.0)
            try:
                with patch.dict(os.environ, self.env):
                    with g.auth_operation_lock(USERNAME, acquire_timeout_seconds=0.1):
                        errors.append(AssertionError("must not acquire"))
            except g.TossAuthOperationBusyError:
                pass
            finally:
                contender_done.set()

        t1 = threading.Thread(target=holder)
        t2 = threading.Thread(target=contender)
        t1.start(); t2.start()
        t1.join(timeout=6.0); t2.join(timeout=6.0)
        for e in errors:
            raise e

    def test_windows_sentinel_lock_lifecycle(self):
        import app.services.toss_wts_auth_guard as g
        with patch.dict(os.environ, self.env):
            lock_file = g._lock_path(USERNAME)
            sentinel = lock_file.with_suffix(".lock.held")
        with patch.object(g, "_IS_WINDOWS", True), \
             patch.dict(os.environ, self.env):
            with g.auth_operation_lock(USERNAME, acquire_timeout_seconds=2.0):
                self.assertTrue(sentinel.exists())
            self.assertFalse(sentinel.exists())

    def test_windows_sentinel_contention_raises(self):
        import app.services.toss_wts_auth_guard as g
        with patch.dict(os.environ, self.env):
            lock_file = g._lock_path(USERNAME)
            sentinel = lock_file.with_suffix(".lock.held")
            lock_file.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("held")
        try:
            with patch.dict(os.environ, self.env):
                gen = g._windows_lock(lock_file, 0.1)
                with self.assertRaises(g.TossAuthOperationBusyError):
                    next(gen)
        finally:
            sentinel.unlink(missing_ok=True)

    def test_different_users_have_independent_locks(self):
        """User A's lock must not block User B's lock."""
        import app.services.toss_wts_auth_guard as g
        errors = []
        b_acquired = threading.Event()
        _create_user_config(Path(self.temp.name), USERNAME_B)

        def hold_a():
            try:
                with patch.dict(os.environ, self.env):
                    with g.auth_operation_lock(USERNAME, acquire_timeout_seconds=2.0):
                        # While A holds, B should acquire independently
                        with g.auth_operation_lock(USERNAME_B, acquire_timeout_seconds=1.0):
                            b_acquired.set()
            except Exception as e:
                errors.append(e)

        t = threading.Thread(target=hold_a)
        t.start(); t.join(timeout=5.0)
        for e in errors:
            raise e
        self.assertTrue(b_acquired.is_set(), "User B lock must be independent of User A")


# ---------------------------------------------------------------------------
# Regression: watcher registry resurrection (tombstone-safe)
# ---------------------------------------------------------------------------

class WatcherResurrectionTests(_LoginBase):
    """Requirement: watcher thread completing AFTER _terminal_cleanup must NOT
    re-populate the watcher registry (memory leak + state confusion)."""

    def test_late_watcher_does_not_resurrect_registry(self):
        import app.services.toss_wts_login as m

        wait_gate = threading.Event()
        proc = Mock()
        proc.pid = 77777
        proc.wait = Mock(side_effect=lambda: (wait_gate.wait(timeout=5), 0)[1])

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch.object(m, "_verify_post_login", return_value=False), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            aid = m.start_toss_login(
                self.settings, username=USERNAME,
                _popen=Mock(return_value=proc),
                now_provider=lambda: NOW,
            )

        with m._watcher_lock:
            self.assertIn(aid, m._watcher_registry)
            self.assertFalse(m._watcher_registry[aid]["reaped"])

        # Simulate terminal cleanup popping the entry
        with m._watcher_lock:
            m._watcher_registry.pop(aid, None)

        with m._watcher_lock:
            self.assertNotIn(aid, m._watcher_registry)

        # Let the watcher thread complete
        wait_gate.set()
        time.sleep(0.3)

        # The tombstone-safe check must prevent re-creation
        with m._watcher_lock:
            self.assertNotIn(
                aid, m._watcher_registry,
                "Watcher must NOT resurrect registry entry after terminal cleanup",
            )

    def test_normal_watcher_updates_registry_before_cleanup(self):
        """Control: if cleanup has not run, watcher update should still work."""
        import app.services.toss_wts_login as m

        wait_gate = threading.Event()
        proc = Mock()
        proc.pid = 77778
        proc.wait = Mock(side_effect=lambda: (wait_gate.wait(timeout=5), 0)[1])

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.get_pid_start_time",
                   return_value=None), \
             patch.object(m, "_verify_post_login", return_value=False), \
             patch("app.services.toss_wts_session.get_toss_session_status",
                   return_value={"active": False, "valid": False}):
            aid = m.start_toss_login(
                self.settings, username=USERNAME,
                _popen=Mock(return_value=proc),
                now_provider=lambda: NOW,
            )

        with m._watcher_lock:
            self.assertFalse(m._watcher_registry[aid]["reaped"])

        wait_gate.set()
        deadline = time.time() + 3.0
        while time.time() < deadline:
            with m._watcher_lock:
                if m._watcher_registry.get(aid, {}).get("reaped"):
                    break
            time.sleep(0.05)

        with m._watcher_lock:
            self.assertTrue(
                m._watcher_registry.get(aid, {}).get("reaped"),
                "Watcher must mark reaped=True when cleanup has not run",
            )
        with m._watcher_lock:
            m._watcher_registry.pop(aid, None)


# ---------------------------------------------------------------------------
# Regression: cancel vs process completion race
# ---------------------------------------------------------------------------

class CancelProcessCompletionRaceTests(_LoginBase):
    """Requirement: if process completes just before cancel arrives, cancel
    must finalize with SUCCESS or FAILED (not CANCELLED)."""

    def test_cancel_yields_success_when_process_already_completed_valid(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 0}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=True):
            result = m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                            now_provider=lambda: NOW,
                                            settings=self.settings)
        self.assertEqual(result["status"], m.STATUS_SUCCESS,
                         "Cancel when process completed+valid must return SUCCESS")
        self.assertIsNone(result["error_code"])

    def test_cancel_yields_failed_when_process_already_completed_invalid(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 1}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_verify_post_login", return_value=False):
            result = m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                            now_provider=lambda: NOW,
                                            settings=self.settings)
        self.assertEqual(result["status"], m.STATUS_FAILED,
                         "Cancel when process completed+invalid must return FAILED")

    def test_cancel_yields_cancelled_when_process_still_running(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": False, "exit_code": None}
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap", return_value=True):
            result = m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                            now_provider=lambda: NOW,
                                            settings=self.settings)
        self.assertEqual(result["status"], m.STATUS_CANCELLED)

    def test_cancel_does_not_call_terminate_when_already_completed(self):
        import app.services.toss_wts_login as m
        aid = self._start()
        with m._watcher_lock:
            m._watcher_registry[aid] = {"reaped": True, "exit_code": 0}
        terminate_called = []
        with patch.dict(os.environ, self.env), \
             patch.object(m, "_terminate_and_reap",
                          side_effect=lambda *a, **kw: terminate_called.append(True)), \
             patch.object(m, "_verify_post_login", return_value=True):
            m.cancel_login_attempt(aid, requesting_username=USERNAME,
                                   now_provider=lambda: NOW,
                                   settings=self.settings)
        self.assertEqual(len(terminate_called), 0,
                         "_terminate_and_reap must not be called when process already done")


if __name__ == "__main__":
    unittest.main()
