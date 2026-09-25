from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import settings
from app.services.ipo.notifier import IpoTelegramNotifier


class ProviderEnabledSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "settings.json"

    def test_defaults_preserve_existing_discord_and_kakao_delivery(self):
        value = settings.default_settings()
        self.assertFalse(value["telegram"]["enabled"])
        self.assertTrue(value["discord"]["enabled"])
        self.assertTrue(value["kakao"]["enabled"])

    def test_legacy_version_one_document_normalizes_provider_switches(self):
        legacy = settings.default_settings()
        legacy.pop("discord")
        legacy.pop("kakao")
        settings._save(legacy, self.path)

        loaded = settings.load_stored_settings("alice", path=self.path)
        self.assertTrue(loaded["discord"]["enabled"])
        self.assertTrue(loaded["kakao"]["enabled"])

    def test_provider_switches_persist_without_touching_secrets(self):
        result = settings.patch_settings(
            "alice",
            {
                "discord": {"enabled": False},
                "kakao": {"enabled": False},
            },
            path=self.path,
        )
        self.assertFalse(result["discord"]["enabled"])
        self.assertFalse(result["kakao"]["enabled"])
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["discord"], {"enabled": False})
        self.assertEqual(raw["kakao"], {"enabled": False})

    def test_provider_switches_reject_non_boolean_values(self):
        with self.assertRaisesRegex(
            settings.SettingsValidationError,
            "INVALID_DISCORD_SETTINGS",
        ):
            settings.patch_settings(
                "alice",
                {"discord": {"enabled": 1}},
                path=self.path,
            )
        with self.assertRaisesRegex(
            settings.SettingsValidationError,
            "INVALID_KAKAO_SETTINGS",
        ):
            settings.patch_settings(
                "alice",
                {"kakao": {"enabled": "yes"}},
                path=self.path,
            )

    def test_automatic_ipo_dispatch_honors_user_switches(self):
        notifier = IpoTelegramNotifier(
            bot_token="bot",
            chat_id="chat",
            username="alice",
        )
        effective = settings.default_settings()
        effective["telegram"]["enabled"] = True
        effective["discord"]["enabled"] = False
        effective["kakao"]["enabled"] = True

        class Sender:
            def __init__(self, provider_name):
                self.provider_name = provider_name

            def is_configured(self):
                return True

        with patch(
            "app.services.settings.get_effective_settings",
            return_value=effective,
        ), patch.object(
            notifier,
            "_notification_senders",
            return_value=[
                Sender("telegram"),
                Sender("discord"),
                Sender("kakao"),
            ],
        ):
            configured = notifier.configured_provider_names()

        self.assertEqual(configured, {"telegram", "kakao"})

    def test_legacy_direct_notifier_remains_telegram_only(self):
        notifier = IpoTelegramNotifier(
            bot_token="bot",
            chat_id="chat",
            username=None,
        )
        senders = notifier._notification_senders()
        self.assertEqual(
            [sender.provider_name for sender in senders],
            ["telegram"],
        )


if __name__ == "__main__":
    unittest.main()
