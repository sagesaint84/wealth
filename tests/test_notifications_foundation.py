"""Unit and integration tests for provider-neutral notification subsystem foundation."""
from __future__ import annotations

import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.notifications.dispatcher import NotificationDispatcher
from app.services.notifications.models import NotificationEvent, NotificationSendResult
from app.services.notifications.sender import NotificationSender
from app.services.notifications.telegram import TelegramSender
from app.services.ipo.notifier import IpoTelegramNotifier


class NotificationFoundationTests(unittest.TestCase):
    def test_notification_event_creation_and_immutability(self):
        meta = {"reply_markup": {"inline_keyboard": []}, "custom": 123}
        event = NotificationEvent(
            event_key="ipo:123",
            event_type="subscription_reminder",
            body="<b>Hello</b>",
            username="alice",
            title="Notice",
            parse_mode="HTML",
            metadata=meta,
        )

        self.assertEqual(event.event_key, "ipo:123")
        self.assertEqual(event.event_type, "subscription_reminder")
        self.assertEqual(event.body, "<b>Hello</b>")
        self.assertEqual(event.username, "alice")
        self.assertEqual(event.title, "Notice")
        self.assertEqual(event.parse_mode, "HTML")
        self.assertEqual(event.metadata["custom"], 123)

        # Mutating original dictionary does not mutate event.metadata
        meta["custom"] = 999
        self.assertEqual(event.metadata["custom"], 123)

        # Frozen dataclass cannot be assigned to
        with self.assertRaises(Exception):
            event.body = "changed"  # type: ignore

    def test_notification_event_validation(self):
        with self.assertRaises(ValueError):
            NotificationEvent(event_key="", event_type="type", body="body")
        with self.assertRaises(ValueError):
            NotificationEvent(event_key="key", event_type="", body="body")
        with self.assertRaises(ValueError):
            NotificationEvent(event_key="key", event_type="type", body=123)  # type: ignore
        with self.assertRaises(ValueError):
            NotificationEvent(event_key="key", event_type="type", body="body", metadata="bad")  # type: ignore

    def test_telegram_sender_configured_check(self):
        sender_none = TelegramSender(bot_token="", chat_id="")
        self.assertFalse(sender_none.is_configured())

        sender_token_only = TelegramSender(bot_token="tok", chat_id="")
        self.assertFalse(sender_token_only.is_configured())

        sender_chat_only = TelegramSender(bot_token="", chat_id="123")
        self.assertFalse(sender_chat_only.is_configured())

        sender_ok = TelegramSender(bot_token="tok", chat_id="123")
        self.assertTrue(sender_ok.is_configured())
        self.assertEqual(sender_ok.provider_name, "telegram")

    def test_telegram_sender_unconfigured_skips_without_network(self):
        sender = TelegramSender(bot_token="", chat_id="")
        event = NotificationEvent(event_key="k1", event_type="t1", body="hello")
        res = sender.send(event)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "NOT_CONFIGURED")

    def test_telegram_sender_success_flow(self):
        captured_requests = []

        class MockResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def mock_urlopen(req, timeout=10):
            captured_requests.append(req)
            return MockResponse()

        sender = TelegramSender(bot_token="BOT123", chat_id="CHAT456")
        event = NotificationEvent(
            event_key="k1",
            event_type="ipo_alert",
            body="Hello <b>World</b>",
            parse_mode="HTML",
            metadata={"reply_markup": {"inline_keyboard": [[{"text": "Btn", "callback_data": "data"}]]}},
        )

        res = sender.send(event, _urlopen=mock_urlopen)
        self.assertTrue(res.success)
        self.assertEqual(res.provider, "telegram")
        self.assertEqual(len(captured_requests), 1)

        req = captured_requests[0]
        self.assertEqual(req.full_url, "https://api.telegram.org/botBOT123/sendMessage")
        # Check payload
        body_decoded = req.data.decode("utf-8")
        self.assertIn("chat_id=CHAT456", body_decoded)
        self.assertIn("parse_mode=HTML", body_decoded)
        self.assertIn("disable_web_page_preview=True", body_decoded)
        self.assertIn("reply_markup=", body_decoded)

    def test_telegram_sender_retry_and_failure(self):
        sleep_calls = []

        def mock_sleep(secs):
            sleep_calls.append(secs)

        def mock_urlopen_fail(req, timeout=10):
            raise OSError("Network unreachable")

        sender = TelegramSender(bot_token="BOT123", chat_id="CHAT456", max_attempts=3)
        event = NotificationEvent(event_key="k1", event_type="ipo_alert", body="test")

        res = sender.send(event, _urlopen=mock_urlopen_fail, _sleep=mock_sleep)
        self.assertFalse(res.success)
        self.assertEqual(res.error_code, "SEND_FAILED")
        self.assertEqual(len(sleep_calls), 2)  # Slept after attempt 1 and attempt 2

    def test_telegram_sender_security_no_token_in_logs(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        t_logger = logging.getLogger("app.services.notifications.telegram")
        t_logger.addHandler(handler)
        old_level = t_logger.level
        t_logger.setLevel(logging.INFO)

        fake_token = "FAKE_TOKEN_FOR_TEST_ONLY_123"
        fake_chat = "123456789"

        try:
            def mock_urlopen_error(req, timeout=10):
                raise RuntimeError(f"https://api.telegram.org/bot{fake_token}/sendMessage connection failed")

            sender = TelegramSender(bot_token=fake_token, chat_id=fake_chat, max_attempts=1)
            event = NotificationEvent(event_key="k1", event_type="ipo_alert", body="safe text")
            res = sender.send(event, _urlopen=mock_urlopen_error)
            self.assertFalse(res.success)

            log_output = stream.getvalue()
            self.assertNotIn(fake_token, log_output)
            self.assertNotIn(fake_chat, log_output)
            self.assertNotIn(f"/bot{fake_token}", log_output)
            self.assertIn("Telegram send failed", log_output)
        finally:
            t_logger.removeHandler(handler)
            t_logger.setLevel(old_level)

    def test_legacy_notifier_patches_urlopen_directly(self):
        """Verify that patching app.services.ipo.notifier.request.urlopen directly reaches the sender."""
        captured_requests = []

        class MockResp:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def legacy_mock_urlopen(req, timeout=10):
            captured_requests.append(req)
            return MockResp()

        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        state_path = Path(temp_dir.name) / "state.json"

        notifier = IpoTelegramNotifier(
            bot_token="LEGACY_BOT_TOKEN_999",
            chat_id="LEGACY_CHAT_ID_888",
            state_path=state_path,
        )

        with patch("app.services.ipo.notifier.request.urlopen", side_effect=legacy_mock_urlopen):
            res = notifier.send_message("<b>Direct patched test</b>")
            self.assertTrue(res)

        self.assertEqual(len(captured_requests), 1)
        self.assertIn("botLEGACY_BOT_TOKEN_999", captured_requests[0].full_url)
        self.assertIn("chat_id=LEGACY_CHAT_ID_888", captured_requests[0].data.decode("utf-8"))

    def test_notification_dispatcher_multi_sender(self):
        mock_sender1 = MagicMock(spec=NotificationSender)
        mock_sender1.provider_name = "telegram"
        mock_sender1.is_configured.return_value = True
        mock_sender1.send.return_value = NotificationSendResult(success=True, provider="telegram")

        mock_sender2 = MagicMock(spec=NotificationSender)
        mock_sender2.provider_name = "discord"
        mock_sender2.is_configured.return_value = False

        dispatcher = NotificationDispatcher([mock_sender1, mock_sender2])
        event = NotificationEvent(event_key="e1", event_type="test", body="body")

        results = dispatcher.dispatch(event)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].provider, "telegram")
        self.assertFalse(results[1].success)
        self.assertEqual(results[1].provider, "discord")
        self.assertEqual(results[1].error_code, "NOT_CONFIGURED")

        mock_sender1.send.assert_called_once_with(event)
        mock_sender2.send.assert_not_called()

    def test_notification_dispatcher_send_direct(self):
        mock_sender = MagicMock(spec=NotificationSender)
        mock_sender.send.return_value = NotificationSendResult(success=True, provider="mock")

        event = NotificationEvent(event_key="e1", event_type="test", body="body")
        res = NotificationDispatcher.send_direct(mock_sender, event)
        self.assertTrue(res.success)
        mock_sender.send.assert_called_once_with(event)

    def test_ipo_telegram_notifier_facade_integration(self):
        """Verify legacy IpoTelegramNotifier uses TelegramSender under the hood."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        state_path = Path(temp_dir.name) / "state.json"

        notifier = IpoTelegramNotifier(
            bot_token="LEGACY_BOT",
            chat_id="LEGACY_CHAT",
            state_path=state_path,
        )

        with patch("app.services.notifications.telegram.TelegramSender.send") as mock_send:
            mock_send.return_value = NotificationSendResult(success=True, provider="telegram")
            success = notifier.send_message("<b>Legacy Alert</b>", reply_markup={"inline_keyboard": []})
            self.assertTrue(success)

            mock_send.assert_called_once()
            called_event = mock_send.call_args[0][0]
            self.assertEqual(called_event.body, "<b>Legacy Alert</b>")
            self.assertEqual(called_event.parse_mode, "HTML")
            self.assertEqual(called_event.metadata["reply_markup"], {"inline_keyboard": []})


if __name__ == "__main__":
    unittest.main()
