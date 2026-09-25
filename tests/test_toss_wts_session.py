from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from app.services import system_settings
from app.services.toss_wts_session import (
    get_toss_session_status,
    run_toss_session_maintenance,
    send_toss_session_notifications,
)
from app.services.notifications.models import NotificationSendResult
from app.services.automation import dispatcher
from app.services.automation.execution_state import claim_execution, get_retryable_executions, record_execution_failure

KST = timezone(timedelta(hours=9))
USERNAME = "owner"


class TossWtsSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.exe = root / "tossctl"; self.exe.write_text("x")
        # Per-user config directory setup
        self.user_config = root / "toss-wts" / "users" / USERNAME / "config"
        self.user_config.mkdir(parents=True, exist_ok=True)
        (self.user_config / "session.json").write_text("secret")
        self.now = datetime(2026, 9, 23, 20, 55, tzinfo=KST)
        self.settings = {"enabled": True, "executable": str(self.exe), "expected_version": "v0.50.3", "timeout_seconds": 20, "session_check_enabled": False, "session_check_time": "20:55", "session_extend_threshold_hours": 48, "session_extend_timeout_seconds": 300}
        self.env = {"WEALTH_DATA_DIR": self.temp.name}

    def tearDown(self):
        import app.services.toss_wts_auth_guard as _g
        import time as _t
        lock = _g._get_thread_lock(USERNAME)
        if lock.locked():
            _t.sleep(0.25)
            if lock.locked():
                try: lock.release()
                except RuntimeError: pass
        try:
            with patch.dict(os.environ, self.env):
                _g._lock_path(USERNAME).with_suffix(".lock.held").unlink(missing_ok=True)
        except Exception: pass
        self.temp.cleanup()

    def _status(self, *, active=True, valid=True, hours=72):
        expiry = (self.now + timedelta(hours=hours)).isoformat()
        return subprocess.CompletedProcess([], 0, f'{{"active": {str(active).lower()}, "valid": {str(valid).lower()}, "server_expires_at": "{expiry}"}}', "")

    def test_status_is_safe_and_calculates_hours(self):
        with patch.dict(os.environ, self.env):
            status = get_toss_session_status(username=USERNAME, now=self.now, settings=self.settings, run=Mock(return_value=self._status(hours=24)))
        self.assertTrue(status["active"]); self.assertEqual(status["hours_remaining"], 24.0)
        self.assertNotIn("stdout", status); self.assertNotIn("stderr", status); self.assertNotIn("session.json", str(status))

    def test_status_errors_are_stable(self):
        with patch.dict(os.environ, self.env):
            self.assertEqual(get_toss_session_status(username=USERNAME, now=self.now, settings={**self.settings,"executable":str(self.exe)+"-missing"})["error_code"], "EXECUTABLE_MISSING")
            self.assertEqual(get_toss_session_status(username=USERNAME, now=self.now, settings=self.settings, run=Mock(side_effect=subprocess.TimeoutExpired([], 1)))["error_code"], "AUTH_STATUS_TIMEOUT")
            self.assertEqual(get_toss_session_status(username=USERNAME, now=self.now, settings=self.settings, run=Mock(return_value=subprocess.CompletedProcess([],0,"not json","")))["error_code"], "INVALID_JSON")

    def test_maintenance_only_extends_within_threshold_and_post_checks(self):
        runner = Mock(return_value=self._status(hours=72))
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
            result = run_toss_session_maintenance(USERNAME, now=self.now, settings=self.settings, run=runner, sender=Mock())
        self.assertEqual(result["action"], "not_required"); self.assertEqual(runner.call_count, 1)
        runner = Mock(side_effect=[self._status(hours=24), subprocess.CompletedProcess([], 0, "", ""), self._status(hours=168)])
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
            result = run_toss_session_maintenance(USERNAME, now=self.now, settings=self.settings, run=runner, sender=Mock())
        self.assertEqual(result["action"], "extended"); self.assertTrue(result["extension_succeeded"]); self.assertEqual(runner.call_count, 3)
        self.assertIn("auth", runner.call_args_list[1].args[0]); self.assertIn("extend", runner.call_args_list[1].args[0])

    def test_system_session_defaults_and_validation(self):
        path = Path(self.temp.name) / "system.json"
        defaults = system_settings.resolve_toss_wts_settings(path=path)
        self.assertFalse(defaults["session_check_enabled"]); self.assertEqual(defaults["session_check_time"], "20:55")
        system_settings.patch_system_settings({"toss_wts": {"session_check_enabled": True, "session_check_time": "21:05", "session_extend_threshold_hours": 24, "session_extend_timeout_seconds": 301}}, path=path, validate_user=False)
        saved_wts = system_settings.resolve_toss_wts_settings(path=path)
        self.assertTrue(saved_wts["session_check_enabled"])
        with self.assertRaises(system_settings.SystemSettingsError): system_settings.patch_system_settings({"toss_wts":{"session_extend_timeout_seconds":29}},path=path)

    def test_dispatcher_user_job_and_non_retryable_state(self):
        cfg = {**self.settings, "session_check_enabled": True}
        system = {"automation_owner": "alice", "automation_owner_source": "stored"}
        state_path = Path(self.temp.name) / "execution.json"
        with patch("app.services.automation.dispatcher.list_users", return_value=[{"username":"alice"}]), \
             patch("app.services.automation.dispatcher.get_effective_system_settings", return_value=system), \
             patch("app.services.automation.dispatcher.get_effective_settings", return_value={"automation": {}, "toss_wts": {"session_check_enabled": True}}), \
             patch("app.services.system_settings.resolve_toss_wts_settings", return_value=cfg):
            jobs = dispatcher.resolve_due_jobs(self.now, state_path=state_path)
        job = next(job for job in jobs if job["job"] == "toss_session_maintenance" and job["owner"] == "alice")
        self.assertEqual(job["execution_key"], "user:alice:toss_session_maintenance:2026-09-23:2055")
        self.assertEqual(job["scope"], "user")
        self.assertFalse(job["retryable"])
        claim_execution(job["execution_key"], job, now=self.now, state_path=state_path)
        record_execution_failure(job["execution_key"], now=self.now, state_path=state_path)
        self.assertEqual(get_retryable_executions(self.now + timedelta(minutes=1), path=state_path), [])
        self.assertFalse(claim_execution(job["execution_key"], job, now=self.now + timedelta(minutes=1), state_path=state_path)["claimed"])

    # ------------------------------------------------------------------
    # A1 — get_effective_system_settings must NOT leak toss_wts
    # ------------------------------------------------------------------
    def test_get_effective_system_settings_does_not_expose_toss_wts(self):
        path = Path(self.temp.name) / "system.json"
        result = system_settings.get_effective_system_settings(path=path)
        self.assertNotIn("toss_wts", result, "toss_wts must not be in get_effective_system_settings()")

    # ------------------------------------------------------------------
    # A2 — _notify must never propagate any Exception to the caller
    # ------------------------------------------------------------------
    def test_notify_isolates_all_exception_subclasses(self):
        from app.services.toss_wts_session import _notify
        for exc_class in (RuntimeError, AttributeError, TypeError, KeyError, MemoryError):
            bad_sender = Mock(side_effect=exc_class("boom"))
            with patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
                result = _notify(USERNAME, "msg", bad_sender)
            self.assertEqual(result, "failed", f"{exc_class.__name__} must result in 'failed'")

    def test_notify_does_not_isolate_base_exception_subclasses(self):
        """KeyboardInterrupt / SystemExit must NOT be silenced."""
        from app.services.toss_wts_session import _notify
        for exc_class in (KeyboardInterrupt, SystemExit):
            bad_sender = Mock(side_effect=exc_class())
            with patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
                with self.assertRaises(exc_class):
                    _notify(USERNAME, "msg", bad_sender)

    def test_maintenance_telegram_failure_does_not_corrupt_result(self):
        """Telegram exception must set notification_status='failed', not raise or drop result."""
        runner = Mock(return_value=self._status(hours=72))
        bad_sender = Mock(side_effect=RuntimeError("telegram down"))
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
            result = run_toss_session_maintenance(USERNAME, now=self.now, settings=self.settings, run=runner, sender=bad_sender)
        self.assertIn("action", result)

    # ------------------------------------------------------------------
    # A3 — post-extension verification uses real (later) timestamp
    # ------------------------------------------------------------------
    def test_post_extension_timestamp_uses_now_provider(self):
        """now_provider is called after auth extend to get the real clock time."""
        pre_now = self.now
        post_now = self.now + timedelta(minutes=6)

        pre_expiry = (pre_now + timedelta(hours=24)).isoformat()
        pre_json = f'{{"active": true, "valid": true, "server_expires_at": "{pre_expiry}"}}'

        post_expiry = (post_now + timedelta(hours=168)).isoformat()
        post_json = f'{{"active": true, "valid": true, "server_expires_at": "{post_expiry}"}}'

        call_count = [0]
        def run_stub(argv, **kwargs):
            call_count[0] += 1
            if "extend" in argv:
                return subprocess.CompletedProcess(argv, 0, "", "")
            return subprocess.CompletedProcess(argv, 0, pre_json if call_count[0] == 1 else post_json, "")

        now_provider_called = []
        def now_prov():
            now_provider_called.append(1)
            return post_now

        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
            result = run_toss_session_maintenance(
                USERNAME, now=pre_now, now_provider=now_prov,
                settings=self.settings, run=run_stub, sender=Mock()
            )
        self.assertGreater(len(now_provider_called), 0, "now_provider must be called post-extension")
        self.assertEqual(result["action"], "extended")
        expected_hours = round((post_now + timedelta(hours=168) - post_now).total_seconds() / 3600, 2)
        self.assertAlmostEqual(result["hours_remaining"], expected_hours, delta=0.1)

    # ------------------------------------------------------------------
    # A4 — AUTH_EXTEND_TIMEOUT vs AUTH_EXTEND_FAILED differentiation
    # ------------------------------------------------------------------
    def test_extend_timeout_yields_auth_extend_timeout_code(self):
        def run_stub(argv, **kwargs):
            if "extend" in argv:
                raise subprocess.TimeoutExpired(argv, 315)
            return self._status(hours=24)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
            result = run_toss_session_maintenance(USERNAME, now=self.now, settings=self.settings, run=run_stub, sender=Mock())
        self.assertEqual(result["action"], "extension_failed")
        self.assertEqual(result["error_code"], "AUTH_EXTEND_TIMEOUT")

    def test_extend_nonzero_exit_yields_auth_extend_failed_code(self):
        def run_stub(argv, **kwargs):
            if "extend" in argv:
                return subprocess.CompletedProcess(argv, 1, "", "error")
            return self._status(hours=24)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
            result = run_toss_session_maintenance(USERNAME, now=self.now, settings=self.settings, run=run_stub, sender=Mock())
        self.assertEqual(result["action"], "extension_failed")
        self.assertEqual(result["error_code"], "AUTH_EXTEND_FAILED")

    def test_extend_oserror_yields_auth_extend_failed_code(self):
        def run_stub(argv, **kwargs):
            if "extend" in argv:
                raise OSError("binary not found")
            return self._status(hours=24)
        with patch.dict(os.environ, self.env), \
             patch("app.services.toss_wts_session.resolve_telegram_config", return_value=Mock()):
            result = run_toss_session_maintenance(USERNAME, now=self.now, settings=self.settings, run=run_stub, sender=Mock())
        self.assertEqual(result["action"], "extension_failed")
        self.assertEqual(result["error_code"], "AUTH_EXTEND_FAILED")

    # ------------------------------------------------------------------
    # Extend-holds-lock: deferral detected INSIDE advisory lock
    # ------------------------------------------------------------------
    def test_extend_deferred_while_login_active(self):
        """Login marker exists with hours=24 < threshold -> deferred inside lock."""
        import app.services.toss_wts_auth_guard as g
        import os as _os
        with patch.dict(_os.environ, self.env), \
             patch("app.services.toss_wts_auth_guard.pid_alive", return_value=True):
            g.write_active_op_marker(USERNAME, "test-login", 12345, self.now.isoformat())
            runner = Mock(return_value=self._status(hours=24))
            with patch("app.services.toss_wts_session.resolve_telegram_config",
                       return_value=Mock()):
                result = run_toss_session_maintenance(
                    USERNAME, now=self.now, settings=self.settings,
                    run=runner, sender=Mock(),
                )
        self.assertEqual(result["action"], "deferred")
        self.assertEqual(result["error_code"], "AUTH_LOGIN_IN_PROGRESS")
        self.assertFalse(result["extension_attempted"])
        for call in runner.call_args_list:
            argv = call.args[0] if call.args else []
            self.assertNotIn("extend", argv)

    def test_extend_deferred_when_advisory_lock_held(self):
        """Another thread holds advisory lock when extend tries to acquire it."""
        import app.services.toss_wts_auth_guard as g
        import os as _os
        lock_held = threading.Event()
        extender_done = threading.Event()
        results = []

        def hold_lock():
            try:
                with g.auth_operation_lock(USERNAME, acquire_timeout_seconds=2.0):
                    lock_held.set()
                    extender_done.wait(timeout=7.0)
            except Exception:
                pass

        def run_extend():
            lock_held.wait(timeout=2.0)
            runner = Mock(return_value=self._status(hours=24))
            try:
                with patch(
                    "app.services.toss_wts_session.resolve_telegram_config",
                    return_value=Mock(),
                ):
                    r = run_toss_session_maintenance(
                        USERNAME,
                        now=self.now,
                        settings=self.settings,
                        run=runner,
                        sender=Mock(),
                    )
                results.append(r)
            except Exception as e:
                results.append({"_exc": str(e)})
            finally:
                extender_done.set()

        # os.environ is process-global. Patch once around both threads instead
        # of mutating it independently from concurrently running threads.
        with patch.dict(_os.environ, self.env):
            t1 = threading.Thread(target=hold_lock)
            t2 = threading.Thread(target=run_extend)
            t1.start()
            t2.start()
            t1.join(timeout=10.0)
            t2.join(timeout=10.0)

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertNotIn("_exc", r, f"Unexpected exception: {r}")
        self.assertEqual(r["action"], "deferred")
        self.assertIn(
            r["error_code"],
            ("TOSS_AUTH_OPERATION_BUSY", "AUTH_LOGIN_IN_PROGRESS"),
        )
        self.assertFalse(r["extension_attempted"])


    # ------------------------------------------------------------------
    # Phase 8B — provider-neutral Toss session notifications
    # ------------------------------------------------------------------
    def test_toss_session_multichannel_dispatch_success(self):
        events = {}

        class FakeSender:
            def __init__(self, provider):
                self.provider_name = provider

            def is_configured(self):
                return True

            def send(self, event, **_kwargs):
                events[self.provider_name] = event
                return NotificationSendResult(
                    success=True,
                    provider=self.provider_name,
                )

        effective = {
            "telegram": {"enabled": True},
            "discord": {"enabled": True},
            "kakao": {"enabled": True},
        }
        tg_cfg = Mock(bot_token="BOT_TOKEN", chat_id=123)

        with patch(
            "app.services.settings.get_effective_settings",
            return_value=effective,
        ), patch(
            "app.services.toss_wts_session.resolve_telegram_config",
            return_value=tg_cfg,
        ), patch(
            "app.services.notifications.telegram.TelegramSender",
            return_value=FakeSender("telegram"),
        ), patch(
            "app.services.notifications.discord.DiscordSender",
            return_value=FakeSender("discord"),
        ), patch(
            "app.services.notifications.kakao.KakaoSender",
            return_value=FakeSender("kakao"),
        ):
            result = send_toss_session_notifications(
                USERNAME,
                "Wealth: " + ("Toss WTS 세션 상태 알림 " * 30),
                event_key="toss_wts:owner:2026-09-23:test",
                event_type="toss_wts_test",
            )

        self.assertEqual(result["status"], "sent")
        self.assertEqual(result["notifications_sent_count"], 3)
        self.assertEqual(set(events), {"telegram", "discord", "kakao"})
        self.assertEqual(
            events["telegram"].event_key,
            "toss_wts:owner:2026-09-23:test",
        )
        self.assertEqual(events["kakao"].event_type, "toss_wts_test")
        self.assertEqual(events["kakao"].username, USERNAME)
        self.assertLessEqual(
            len(events["kakao"].metadata["kakao_body"]),
            200,
        )

    def test_toss_session_provider_failure_isolated(self):
        calls = []

        class FakeSender:
            def __init__(self, provider, *, raises=False):
                self.provider_name = provider
                self.raises = raises

            def is_configured(self):
                return True

            def send(self, event, **_kwargs):
                calls.append(self.provider_name)
                if self.raises:
                    raise RuntimeError("credential-bearing failure")
                return NotificationSendResult(
                    success=True,
                    provider=self.provider_name,
                )

        effective = {
            "telegram": {"enabled": True},
            "discord": {"enabled": True},
            "kakao": {"enabled": True},
        }
        tg_cfg = Mock(bot_token="BOT_TOKEN", chat_id=123)

        with patch(
            "app.services.settings.get_effective_settings",
            return_value=effective,
        ), patch(
            "app.services.toss_wts_session.resolve_telegram_config",
            return_value=tg_cfg,
        ), patch(
            "app.services.notifications.telegram.TelegramSender",
            return_value=FakeSender("telegram"),
        ), patch(
            "app.services.notifications.discord.DiscordSender",
            return_value=FakeSender("discord", raises=True),
        ), patch(
            "app.services.notifications.kakao.KakaoSender",
            return_value=FakeSender("kakao"),
        ):
            result = send_toss_session_notifications(
                USERNAME,
                "연장 상태",
                event_key="toss_wts:owner:2026-09-23:partial",
                event_type="toss_wts_test",
            )

        self.assertEqual(calls, ["telegram", "discord", "kakao"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["notifications_sent_count"], 2)
        self.assertEqual(
            result["provider_results"]["discord"]["status"],
            "failed",
        )
        self.assertTrue(
            result["provider_results"]["discord"]["retryable"]
        )
        self.assertEqual(
            result["provider_results"]["discord"]["error"],
            "SEND_FAILED",
        )
        self.assertTrue(result["provider_results"]["kakao"]["sent"])

    def test_toss_session_disabled_providers_are_not_constructed(self):
        effective = {
            "telegram": {"enabled": False},
            "discord": {"enabled": False},
            "kakao": {"enabled": False},
        }
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=effective,
        ), patch(
            "app.services.toss_wts_session.resolve_telegram_config"
        ) as telegram_config, patch(
            "app.services.notifications.telegram.TelegramSender"
        ) as telegram_sender, patch(
            "app.services.notifications.discord.DiscordSender"
        ) as discord_sender, patch(
            "app.services.notifications.kakao.KakaoSender"
        ) as kakao_sender:
            result = send_toss_session_notifications(
                USERNAME,
                "알림",
                event_key="toss_wts:owner:2026-09-23:disabled",
                event_type="toss_wts_test",
            )

        telegram_config.assert_not_called()
        telegram_sender.assert_not_called()
        discord_sender.assert_not_called()
        kakao_sender.assert_not_called()
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["notifications_sent_count"], 0)
        for provider in ("telegram", "discord", "kakao"):
            self.assertEqual(
                result["provider_results"][provider]["status"],
                "disabled",
            )

    def test_toss_session_provider_constructor_failure_isolated(self):
        class FakeKakao:
            provider_name = "kakao"

            def is_configured(self):
                return True

            def send(self, event, **_kwargs):
                return NotificationSendResult(
                    success=True,
                    provider="kakao",
                )

        effective = {
            "telegram": {"enabled": False},
            "discord": {"enabled": True},
            "kakao": {"enabled": True},
        }
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=effective,
        ), patch(
            "app.services.notifications.discord.DiscordSender",
            side_effect=RuntimeError("secret-bearing constructor failure"),
        ), patch(
            "app.services.notifications.kakao.KakaoSender",
            return_value=FakeKakao(),
        ):
            result = send_toss_session_notifications(
                USERNAME,
                "알림",
                event_key="toss_wts:owner:2026-09-23:constructor",
                event_type="toss_wts_test",
            )

        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["notifications_sent_count"], 1)
        self.assertEqual(
            result["provider_results"]["discord"]["error"],
            "CONFIGURATION_ERROR",
        )
        self.assertTrue(result["provider_results"]["kakao"]["sent"])

    def test_maintenance_default_path_uses_multichannel_notification(self):
        runner = Mock(
            return_value=self._status(active=False, valid=False, hours=24)
        )
        notification = {
            "status": "partial",
            "notifications_sent_count": 2,
            "provider_results": {
                "telegram": {
                    "sent": True,
                    "status": "sent",
                    "retryable": False,
                    "error": None,
                },
                "discord": {
                    "sent": False,
                    "status": "failed",
                    "retryable": True,
                    "error": "SEND_FAILED",
                },
                "kakao": {
                    "sent": True,
                    "status": "sent",
                    "retryable": False,
                    "error": None,
                },
            },
        }

        with patch.dict(os.environ, self.env), patch(
            "app.services.toss_wts_session.send_toss_session_notifications",
            return_value=notification,
        ) as notify:
            result = run_toss_session_maintenance(
                USERNAME,
                now=self.now,
                settings=self.settings,
                run=runner,
            )

        self.assertEqual(result["action"], "status_failed")
        self.assertEqual(result["notification_status"], "partial")
        self.assertEqual(
            result["notification_dispatch_status"],
            "partial",
        )
        self.assertEqual(result["notifications_sent_count"], 2)
        self.assertTrue(
            result["notification_provider_results"]["telegram"]["sent"]
        )
        notify.assert_called_once()
        self.assertEqual(
            notify.call_args.kwargs["event_type"],
            "toss_wts_session_invalid",
        )

    def test_maintenance_extension_events_have_distinct_event_keys(self):
        runner = Mock(side_effect=[
            self._status(hours=24),
            subprocess.CompletedProcess([], 0, "", ""),
            self._status(hours=168),
        ])
        notifications = []

        def notify(owner, message, *, event_key, event_type):
            notifications.append((event_key, event_type, message))
            return {
                "status": "sent",
                "notifications_sent_count": 3,
                "provider_results": {
                    "telegram": {
                        "sent": True,
                        "status": "sent",
                        "retryable": False,
                        "error": None,
                    },
                    "discord": {
                        "sent": True,
                        "status": "sent",
                        "retryable": False,
                        "error": None,
                    },
                    "kakao": {
                        "sent": True,
                        "status": "sent",
                        "retryable": False,
                        "error": None,
                    },
                },
            }

        with patch.dict(os.environ, self.env), patch(
            "app.services.toss_wts_session.send_toss_session_notifications",
            side_effect=notify,
        ):
            result = run_toss_session_maintenance(
                USERNAME,
                now=self.now,
                now_provider=lambda: self.now + timedelta(minutes=1),
                settings=self.settings,
                run=runner,
            )

        self.assertEqual(result["action"], "extended")
        self.assertEqual(len(notifications), 2)
        self.assertTrue(
            notifications[0][0].endswith(":extension_requested")
        )
        self.assertEqual(
            notifications[0][1],
            "toss_wts_extension_requested",
        )
        self.assertTrue(
            notifications[1][0].endswith(":extension_succeeded")
        )
        self.assertEqual(
            notifications[1][1],
            "toss_wts_extension_succeeded",
        )
        self.assertNotEqual(notifications[0][0], notifications[1][0])
        self.assertEqual(result["notification_status"], "sent")
        self.assertEqual(result["notifications_sent_count"], 3)

    def test_multichannel_notification_exception_never_changes_session_result(self):
        runner = Mock(
            return_value=self._status(active=False, valid=False, hours=24)
        )
        secret_text = "https://discord.com/api/webhooks/SECRET_TEST_URL"

        with patch.dict(os.environ, self.env), patch(
            "app.services.toss_wts_session.send_toss_session_notifications",
            side_effect=RuntimeError(secret_text),
        ):
            result = run_toss_session_maintenance(
                USERNAME,
                now=self.now,
                settings=self.settings,
                run=runner,
            )

        self.assertEqual(result["action"], "status_failed")
        self.assertEqual(result["notification_status"], "failed")
        self.assertEqual(result["notification_dispatch_status"], "failed")
        self.assertEqual(result["notifications_sent_count"], 0)
        self.assertNotIn(secret_text, str(result))

    def test_maintenance_injected_sender_preserves_legacy_contract(self):
        runner = Mock(
            return_value=self._status(active=False, valid=False, hours=24)
        )
        legacy_sender = Mock()

        with patch.dict(os.environ, self.env), patch(
            "app.services.toss_wts_session.resolve_telegram_config",
            return_value=Mock(),
        ):
            result = run_toss_session_maintenance(
                USERNAME,
                now=self.now,
                settings=self.settings,
                run=runner,
                sender=legacy_sender,
            )

        legacy_sender.assert_called_once()
        self.assertEqual(result["notification_status"], "sent")
        self.assertEqual(result["notification_dispatch_status"], "sent")
        self.assertEqual(result["notifications_sent_count"], 1)
        self.assertEqual(
            set(result["notification_provider_results"]),
            {"telegram"},
        )

if __name__ == "__main__":
    unittest.main()
