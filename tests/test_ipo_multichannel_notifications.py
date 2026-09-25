from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services.ipo.notifier import IpoTelegramNotifier
from app.services.notifications.models import NotificationSendResult


class FakeSender:
    def __init__(self, provider: str, result: NotificationSendResult):
        self.provider_name = provider
        self._result = result
        self.events = []
        self.kwargs = []

    def is_configured(self):
        return True

    def send(self, event, **kwargs):
        self.events.append(event)
        self.kwargs.append(kwargs)
        return self._result


class IpoMultiChannelNotificationTests(unittest.TestCase):
    def test_send_message_dispatches_same_event_to_all_providers(self):
        notifier = IpoTelegramNotifier(
            bot_token="bot",
            chat_id="chat",
            username="alice",
        )
        senders = [
            FakeSender(
                "telegram",
                NotificationSendResult(success=True, provider="telegram"),
            ),
            FakeSender(
                "discord",
                NotificationSendResult(success=True, provider="discord"),
            ),
            FakeSender(
                "kakao",
                NotificationSendResult(success=True, provider="kakao"),
            ),
        ]
        markup = {
            "inline_keyboard": [
                [{"text": "청약 완료", "callback_data": "ipoa:opaque"}],
                [{"text": "Wealth에서 확인", "url": "https://wealth.test/a/token"}],
            ]
        }
        body = "<b>긴 IPO 알림</b><br>" + ("가" * 260)

        with patch.object(
            notifier,
            "_notification_senders",
            return_value=senders,
        ):
            self.assertTrue(
                notifier.send_message(
                    body,
                    reply_markup=markup,
                    event_key="ipo:key",
                )
            )

        for sender in senders:
            self.assertEqual(len(sender.events), 1)
            event = sender.events[0]
            self.assertEqual(event.event_key, "ipo:key")
            self.assertEqual(event.username, "alice")
            self.assertEqual(event.action_url, "https://wealth.test/a/token")
            self.assertEqual(event.action_label, "Wealth에서 확인")
            self.assertLessEqual(len(event.metadata["kakao_body"]), 200)

        self.assertIn("_urlopen", senders[0].kwargs[0])
        self.assertIn("_sleep", senders[0].kwargs[0])
        self.assertEqual(senders[1].kwargs[0], {})
        self.assertEqual(senders[2].kwargs[0], {})

    def test_send_message_records_common_notification_history(self):
        notifier = IpoTelegramNotifier(
            bot_token="bot",
            chat_id="chat",
            username="alice",
        )
        sender = FakeSender(
            "telegram",
            NotificationSendResult(success=True, provider="telegram"),
        )
        with patch.object(
            notifier,
            "_notification_senders",
            return_value=[sender],
        ), patch(
            "app.services.notifications.history.record_notification_history"
        ) as record:
            self.assertTrue(
                notifier.send_message(
                    "IPO history",
                    event_key="ipo:history",
                )
            )

        record.assert_called_once()
        self.assertEqual(record.call_args.args[0], "alice")
        event = record.call_args.args[1]
        report = record.call_args.args[2]
        self.assertEqual(event.event_type, "ipo_alert")
        self.assertEqual(event.event_key, "ipo:history")
        self.assertEqual(report.status, "sent")
        self.assertEqual(report.notifications_sent_count, 1)

    def test_multiple_web_actions_are_not_collapsed_to_one_owner(self):
        markup = {
            "inline_keyboard": [
                [{"text": "아빠 확인", "url": "https://wealth.test/a/one"}],
                [{"text": "엄마 확인", "url": "https://wealth.test/a/two"}],
            ]
        }
        self.assertEqual(
            IpoTelegramNotifier._single_web_action(markup),
            (None, None),
        )

    def test_provider_level_dedupe_retries_only_failed_provider(self):
        notifier = IpoTelegramNotifier(
            bot_token="bot",
            chat_id="chat",
            username="alice",
        )
        state = {"sent_keys": {}, "provider_sent_keys": {}}
        calls = []

        with patch.object(
            notifier,
            "configured_provider_names",
            return_value={"telegram", "discord", "kakao"},
        ):
            def first_send(*args, **kwargs):
                calls.append(set(kwargs["providers"]))
                notifier._last_send_results = [
                    NotificationSendResult(success=True, provider="telegram"),
                    NotificationSendResult(
                        success=False,
                        provider="discord",
                        retryable=True,
                        error_code="SEND_FAILED",
                    ),
                    NotificationSendResult(success=True, provider="kakao"),
                ]
                return True

            with patch.object(
                notifier,
                "send_message",
                side_effect=first_send,
            ):
                sent = notifier.dispatch_message(
                    "ipo:event",
                    "message",
                    state,
                )

            self.assertTrue(sent)
            self.assertEqual(
                set(state["provider_sent_keys"]["ipo:event"]),
                {"telegram", "kakao"},
            )
            self.assertNotIn("ipo:event", state["sent_keys"])

            def second_send(*args, **kwargs):
                calls.append(set(kwargs["providers"]))
                notifier._last_send_results = [
                    NotificationSendResult(success=True, provider="discord")
                ]
                return True

            with patch.object(
                notifier,
                "send_message",
                side_effect=second_send,
            ):
                sent = notifier.dispatch_message(
                    "ipo:event",
                    "message",
                    state,
                )

            self.assertTrue(sent)
            self.assertEqual(calls, [
                {"telegram", "discord", "kakao"},
                {"discord"},
            ])
            self.assertIn("ipo:event", state["sent_keys"])
            self.assertEqual(
                set(state["provider_sent_keys"]["ipo:event"]),
                {"telegram", "discord", "kakao"},
            )

            with patch.object(notifier, "send_message") as send:
                self.assertFalse(
                    notifier.dispatch_message(
                        "ipo:event",
                        "message",
                        state,
                    )
                )
                send.assert_not_called()

    def test_legacy_sent_key_prevents_multichannel_backfill(self):
        notifier = IpoTelegramNotifier(
            bot_token="bot",
            chat_id="chat",
            username="alice",
        )
        state = {
            "sent_keys": {"old:event": "2026-09-25T00:00:00+09:00"},
            "provider_sent_keys": {},
        }
        with patch.object(notifier, "send_message") as send:
            self.assertFalse(
                notifier.dispatch_message("old:event", "message", state)
            )
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
