from __future__ import annotations

import unittest
from unittest.mock import MagicMock, Mock, patch

from app.services.notifications.models import NotificationEvent, NotificationSendResult
from app.services.notifications.service import UserNotificationService


class FakeSender:
    def __init__(self, provider: str, *, configured: bool = True, fail: bool = False):
        self.provider_name = provider
        self.configured = configured
        self.fail = fail
        self.events = []

    def is_configured(self):
        return self.configured

    def send(self, event, **kwargs):
        self.events.append((event, kwargs))
        if self.fail:
            raise RuntimeError("credential-bearing failure")
        return NotificationSendResult(
            success=True,
            provider=self.provider_name,
        )


class UserNotificationServiceTests(unittest.TestCase):
    def _event(self):
        return NotificationEvent(
            event_key="test:event",
            event_type="test",
            body="hello",
            username="alice",
        )

    def test_enabled_provider_names_follow_user_switches(self):
        settings = {
            "telegram": {"enabled": True},
            "discord": {"enabled": False},
            "kakao": {"enabled": True},
        }
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=settings,
        ):
            service = UserNotificationService("alice")
            self.assertEqual(
                service.enabled_provider_names(),
                {"telegram", "kakao"},
            )

    def test_dispatch_aggregates_success_disabled_and_unconfigured(self):
        telegram = FakeSender("telegram")
        discord = FakeSender("discord")
        kakao = FakeSender("kakao", configured=False)
        settings = {
            "telegram": {"enabled": True},
            "discord": {"enabled": False},
            "kakao": {"enabled": True},
        }
        service = UserNotificationService(
            "alice",
            sender_overrides={
                "telegram": telegram,
                "discord": discord,
                "kakao": kakao,
            },
        )
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=settings,
        ):
            report = service.dispatch(self._event())

        self.assertEqual(report.status, "partial")
        self.assertEqual(report.notifications_sent_count, 1)
        self.assertEqual(
            report.provider_results["telegram"]["status"],
            "sent",
        )
        self.assertEqual(
            report.provider_results["discord"]["status"],
            "disabled",
        )
        self.assertEqual(
            report.provider_results["kakao"]["status"],
            "unconfigured",
        )
        self.assertEqual(len(telegram.events), 1)
        self.assertEqual(len(discord.events), 0)
        self.assertEqual(len(kakao.events), 0)

    def test_provider_exception_isolated_and_next_provider_continues(self):
        telegram = FakeSender("telegram")
        discord = FakeSender("discord", fail=True)
        kakao = FakeSender("kakao")
        settings = {
            "telegram": {"enabled": True},
            "discord": {"enabled": True},
            "kakao": {"enabled": True},
        }
        service = UserNotificationService(
            "alice",
            sender_overrides={
                "telegram": telegram,
                "discord": discord,
                "kakao": kakao,
            },
        )
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=settings,
        ):
            report = service.dispatch(self._event())

        self.assertEqual(report.status, "partial")
        self.assertEqual(report.notifications_sent_count, 2)
        self.assertTrue(report.provider_results["telegram"]["sent"])
        self.assertEqual(
            report.provider_results["discord"]["error"],
            "SEND_FAILED",
        )
        self.assertTrue(
            report.provider_results["discord"]["retryable"]
        )
        self.assertTrue(report.provider_results["kakao"]["sent"])

    def test_settings_failure_fails_closed_with_stable_error_codes(self):
        with patch(
            "app.services.settings.get_effective_settings",
            side_effect=RuntimeError("secret settings failure"),
        ):
            report = UserNotificationService("alice").dispatch(
                self._event()
            )

        self.assertEqual(report.status, "failed")
        self.assertEqual(report.notifications_sent_count, 0)
        for provider in ("telegram", "discord", "kakao"):
            self.assertEqual(
                report.provider_results[provider]["error"],
                "CONFIGURATION_ERROR",
            )
        self.assertNotIn("secret settings failure", str(report))

    def test_configured_provider_names_excludes_disabled_and_unconfigured(self):
        settings = {
            "telegram": {"enabled": True},
            "discord": {"enabled": False},
            "kakao": {"enabled": True},
        }
        service = UserNotificationService(
            "alice",
            sender_overrides={
                "telegram": FakeSender("telegram", configured=True),
                "discord": FakeSender("discord", configured=True),
                "kakao": FakeSender("kakao", configured=False),
            },
        )
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=settings,
        ):
            configured = service.configured_provider_names()

        self.assertEqual(configured, {"telegram"})

    def test_direct_dispatch_can_bypass_usage_switches_for_legacy_transport(self):
        telegram = FakeSender("telegram")
        settings = {
            "telegram": {"enabled": False},
            "discord": {"enabled": False},
            "kakao": {"enabled": False},
        }
        service = UserNotificationService(
            "alice",
            sender_overrides={"telegram": telegram},
        )
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=settings,
        ):
            report = service.dispatch(
                self._event(),
                providers={"telegram"},
                respect_enabled=False,
            )

        self.assertEqual(report.status, "sent")
        self.assertEqual(report.notifications_sent_count, 1)
        self.assertTrue(report.provider_results["telegram"]["sent"])

    def test_disabled_telegram_does_not_resolve_credentials(self):
        resolver = MagicMock()
        settings = {
            "telegram": {"enabled": False},
            "discord": {"enabled": False},
            "kakao": {"enabled": False},
        }
        service = UserNotificationService(
            "alice",
            telegram_resolver=resolver,
        )
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=settings,
        ):
            report = service.dispatch(self._event())

        resolver.assert_not_called()
        self.assertEqual(report.status, "disabled")

    def test_enabled_telegram_resolves_credentials_lazily(self):
        resolver = MagicMock()
        resolver.return_value = Mock(
            bot_token="TOKEN",
            chat_id=123,
        )
        sender = FakeSender("telegram")
        settings = {
            "telegram": {"enabled": True},
            "discord": {"enabled": False},
            "kakao": {"enabled": False},
        }
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=settings,
        ), patch(
            "app.services.notifications.telegram.TelegramSender",
            return_value=sender,
        ):
            report = UserNotificationService(
                "alice",
                telegram_resolver=resolver,
            ).dispatch(self._event())

        resolver.assert_called_once_with("alice")
        self.assertEqual(report.status, "sent")
        self.assertTrue(report.provider_results["telegram"]["sent"])

    def test_sender_constructor_failure_isolated(self):
        kakao = FakeSender("kakao")
        settings = {
            "telegram": {"enabled": False},
            "discord": {"enabled": True},
            "kakao": {"enabled": True},
        }
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=settings,
        ), patch(
            "app.services.notifications.discord.DiscordSender",
            side_effect=RuntimeError("secret webhook failure"),
        ), patch(
            "app.services.notifications.kakao.KakaoSender",
            return_value=kakao,
        ):
            report = UserNotificationService("alice").dispatch(
                self._event()
            )

        self.assertEqual(report.status, "partial")
        self.assertEqual(report.notifications_sent_count, 1)
        self.assertEqual(
            report.provider_results["discord"]["error"],
            "CONFIGURATION_ERROR",
        )
        self.assertTrue(report.provider_results["kakao"]["sent"])
        self.assertNotIn("secret webhook failure", str(report))

    def test_send_options_are_forwarded_only_to_matching_provider(self):
        telegram = FakeSender("telegram")
        kakao = FakeSender("kakao")
        settings = {
            "telegram": {"enabled": True},
            "discord": {"enabled": False},
            "kakao": {"enabled": True},
        }
        hook = object()
        service = UserNotificationService(
            "alice",
            sender_overrides={
                "telegram": telegram,
                "kakao": kakao,
            },
        )
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=settings,
        ):
            report = service.dispatch(
                self._event(),
                send_options={"telegram": {"_sleep": hook}},
            )

        self.assertEqual(report.status, "sent")
        self.assertEqual(telegram.events[0][1], {"_sleep": hook})
        self.assertEqual(kakao.events[0][1], {})


if __name__ == "__main__":
    unittest.main()
