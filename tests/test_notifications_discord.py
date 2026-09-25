"""Tests for the Discord notification transport."""
from __future__ import annotations

import io
import json
import logging
import unittest
from urllib.error import HTTPError
from unittest.mock import MagicMock, patch

from app.services.notifications import DiscordSender
from app.services.notifications.dispatcher import NotificationDispatcher
from app.services.notifications.models import NotificationEvent, NotificationSendResult
from app.services.notifications.sender import NotificationSender


WEBHOOK = "https://discord.com/api/webhooks/123456789/VERY_SECRET_WEBHOOK_TOKEN"


class MockResponse:
    def __init__(self, status: int = 204, body: bytes = b"", headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


class DiscordSenderTests(unittest.TestCase):
    def test_configuration_and_provider_name(self):
        self.assertFalse(DiscordSender(webhook_url="").is_configured())
        sender = DiscordSender(webhook_url=WEBHOOK)
        self.assertTrue(sender.is_configured())
        self.assertEqual(sender.provider_name, "discord")

    def test_stored_webhook_is_user_bound(self):
        def stored(username):
            return {"webhook_url": WEBHOOK if username == "alice" else ""}

        with patch(
            "app.services.notifications.discord.load_stored_discord_secrets",
            side_effect=stored,
        ):
            self.assertTrue(DiscordSender(username="alice").is_configured())
            self.assertFalse(DiscordSender(username="bob").is_configured())
            self.assertFalse(DiscordSender(username=None).is_configured())

    def test_invalid_webhook_url_fails_before_network(self):
        opener = MagicMock()
        result = DiscordSender(
            webhook_url="https://example.com/api/webhooks/123/token"
        ).send(
            NotificationEvent(event_key="k", event_type="test", body="hello"),
            _urlopen=opener,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "INVALID_WEBHOOK_URL")
        opener.assert_not_called()

    def test_success_payload_html_mentions_and_action_url(self):
        captured = []

        def opener(req, timeout=10):
            captured.append(req)
            return MockResponse(
                200,
                json.dumps({"id": "message-1"}).encode("utf-8"),
            )

        event = NotificationEvent(
            event_key="k",
            event_type="ipo_alert",
            body="🚀 <b>공모주 오늘 상장</b><br>@everyone @here <i>확인</i>",
            action_url="https://wealth.example/a/token",
            action_label="Wealth에서 확인",
        )
        result = DiscordSender(webhook_url=WEBHOOK).send(event, _urlopen=opener)

        self.assertTrue(result.success)
        self.assertEqual(result.provider, "discord")
        self.assertEqual(result.provider_message_id, "message-1")
        self.assertEqual(len(captured), 1)

        req = captured[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, WEBHOOK)
        self.assertEqual(req.get_header("Content-type"), "application/json")
        payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(payload["allowed_mentions"], {"parse": []})
        self.assertNotIn("<b>", payload["content"])
        self.assertIn("**공모주 오늘 상장**", payload["content"])
        self.assertIn("*확인*", payload["content"])
        self.assertIn("@everyone @here", payload["content"])
        self.assertIn(
            "Wealth에서 확인: https://wealth.example/a/token",
            payload["content"],
        )

    def test_message_too_long_is_fail_closed_without_network(self):
        opener = MagicMock()
        result = DiscordSender(webhook_url=WEBHOOK).send(
            NotificationEvent(event_key="k", event_type="test", body="x" * 2001),
            _urlopen=opener,
        )
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertEqual(result.error_code, "MESSAGE_TOO_LONG")
        opener.assert_not_called()

    def test_retryable_http_failure_is_bounded_and_can_recover(self):
        calls = []
        sleeps = []

        def opener(req, timeout=10):
            calls.append(req)
            if len(calls) < 3:
                raise HTTPError(req.full_url, 500, "server error", {}, None)
            return MockResponse(204)

        result = DiscordSender(webhook_url=WEBHOOK, max_attempts=3).send(
            NotificationEvent(event_key="k", event_type="test", body="hello"),
            _urlopen=opener,
            _sleep=sleeps.append,
        )
        self.assertTrue(result.success)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_rate_limit_retry_after_is_bounded(self):
        calls = []
        sleeps = []

        def opener(req, timeout=10):
            calls.append(req)
            if len(calls) == 1:
                raise HTTPError(
                    req.full_url, 429, "rate limited", {"Retry-After": "99"}, None
                )
            return MockResponse(204)

        result = DiscordSender(webhook_url=WEBHOOK, max_attempts=2).send(
            NotificationEvent(event_key="k", event_type="test", body="hello"),
            _urlopen=opener,
            _sleep=sleeps.append,
        )
        self.assertTrue(result.success)
        self.assertEqual(sleeps, [10.0])

    def test_permanent_4xx_does_not_retry(self):
        calls = []

        def opener(req, timeout=10):
            calls.append(req)
            raise HTTPError(req.full_url, 404, "not found", {}, None)

        result = DiscordSender(webhook_url=WEBHOOK, max_attempts=3).send(
            NotificationEvent(event_key="k", event_type="test", body="hello"),
            _urlopen=opener,
            _sleep=lambda _: self.fail("must not sleep"),
        )
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertEqual(result.error_code, "HTTP_404")
        self.assertEqual(len(calls), 1)

    def test_retry_exhaustion_reports_retryable_send_failed(self):
        calls = []

        def opener(req, timeout=10):
            calls.append(req)
            raise OSError("network unavailable")

        result = DiscordSender(webhook_url=WEBHOOK, max_attempts=3).send(
            NotificationEvent(event_key="k", event_type="test", body="hello"),
            _urlopen=opener,
            _sleep=lambda _: None,
        )
        self.assertFalse(result.success)
        self.assertTrue(result.retryable)
        self.assertEqual(result.error_code, "SEND_FAILED")
        self.assertEqual(len(calls), 3)

    def test_webhook_secret_is_not_logged_on_failure(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        d_logger = logging.getLogger("app.services.notifications.discord")
        old_level = d_logger.level
        d_logger.addHandler(handler)
        d_logger.setLevel(logging.INFO)
        try:
            def opener(req, timeout=10):
                raise RuntimeError(f"{WEBHOOK} connection failed")

            result = DiscordSender(webhook_url=WEBHOOK, max_attempts=1).send(
                NotificationEvent(event_key="k", event_type="test", body="hello"),
                _urlopen=opener,
            )
            self.assertFalse(result.success)
            output = stream.getvalue()
            self.assertIn("Discord send failed", output)
            self.assertNotIn("VERY_SECRET_WEBHOOK_TOKEN", output)
            self.assertNotIn(WEBHOOK, output)
        finally:
            d_logger.removeHandler(handler)
            d_logger.setLevel(old_level)

    def test_dispatcher_keeps_provider_neutral_multi_sender_contract(self):
        telegram = MagicMock(spec=NotificationSender)
        telegram.provider_name = "telegram"
        telegram.is_configured.return_value = True
        telegram.send.return_value = NotificationSendResult(
            success=True, provider="telegram"
        )

        discord = MagicMock(spec=NotificationSender)
        discord.provider_name = "discord"
        discord.is_configured.return_value = True
        discord.send.return_value = NotificationSendResult(
            success=True, provider="discord"
        )

        event = NotificationEvent(event_key="e1", event_type="test", body="body")
        results = NotificationDispatcher([telegram, discord]).dispatch(event)
        self.assertEqual([r.provider for r in results], ["telegram", "discord"])
        telegram.send.assert_called_once_with(event)
        discord.send.assert_called_once_with(event)

    def test_dispatcher_skips_unconfigured_discord_sender(self):
        discord = MagicMock(spec=NotificationSender)
        discord.provider_name = "discord"
        discord.is_configured.return_value = False

        event = NotificationEvent(event_key="e1", event_type="test", body="body")
        results = NotificationDispatcher([discord]).dispatch(event)
        self.assertEqual(results[0].provider, "discord")
        self.assertEqual(results[0].error_code, "NOT_CONFIGURED")
        discord.send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
