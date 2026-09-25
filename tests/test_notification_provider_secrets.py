from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.discord_secrets import (
    DiscordSecretError,
    discord_secret_status,
    load_stored_discord_secrets,
    secret_path as discord_secret_path,
    update_discord_secrets,
)
from app.services.kakao_oauth import resolve_kakao_app_config
from app.services.notifications.discord import DiscordSender
from app.services.kakao_app_secrets import (
    KakaoAppSecretError,
    kakao_app_secret_status,
    load_stored_kakao_app_secrets,
    secret_path as kakao_app_secret_path,
    update_kakao_app_secrets,
)


WEBHOOK = "https://discord.com/api/webhooks/123456789/SECRET_TOKEN"


class NotificationProviderSecretTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_paths_are_under_current_users_secrets_directory(self):
        alice_settings = self.root / "users" / "alice" / "settings.json"
        with patch(
            "app.services.discord_secrets.settings_path",
            return_value=alice_settings,
        ):
            self.assertEqual(
                discord_secret_path("alice"),
                self.root / "users" / "alice" / "secrets" / "discord.json",
            )
        with patch(
            "app.services.kakao_app_secrets.settings_path",
            return_value=alice_settings,
        ):
            self.assertEqual(
                kakao_app_secret_path("alice"),
                self.root / "users" / "alice" / "secrets" / "kakao_app.json",
            )

    def test_discord_webhook_roundtrip_and_clear(self):
        path = self.root / "discord.json"
        saved = update_discord_secrets(
            "alice", {"webhook_url": WEBHOOK}, path=path
        )
        self.assertEqual(saved["webhook_url"], WEBHOOK)
        self.assertEqual(
            load_stored_discord_secrets("alice", path=path)["webhook_url"],
            WEBHOOK,
        )
        update_discord_secrets(
            "alice", {"clear_webhook_url": True}, path=path
        )
        self.assertEqual(
            load_stored_discord_secrets("alice", path=path)["webhook_url"], ""
        )

    def test_discord_rejects_non_discord_webhook(self):
        path = self.root / "discord.json"
        with self.assertRaises(DiscordSecretError):
            update_discord_secrets(
                "alice",
                {"webhook_url": "https://example.com/api/webhooks/1/token"},
                path=path,
            )
        self.assertFalse(path.exists())

    def test_kakao_app_credentials_roundtrip_and_partial_update(self):
        path = self.root / "kakao_app.json"
        update_kakao_app_secrets(
            "alice",
            {"rest_api_key": "REST_KEY", "client_secret": "CLIENT_SECRET"},
            path=path,
        )
        update_kakao_app_secrets(
            "alice", {"client_secret": "NEW_CLIENT_SECRET"}, path=path
        )
        stored = load_stored_kakao_app_secrets("alice", path=path)
        self.assertEqual(stored["rest_api_key"], "REST_KEY")
        self.assertEqual(stored["client_secret"], "NEW_CLIENT_SECRET")
        self.assertNotIn("REST_KEY", json.dumps({
            "rest_api_key_configured": bool(stored["rest_api_key"]),
            "client_secret_configured": bool(stored["client_secret"]),
        }))

    def test_kakao_app_credentials_clear_independently(self):
        path = self.root / "kakao_app.json"
        update_kakao_app_secrets(
            "alice",
            {"rest_api_key": "REST_KEY", "client_secret": "CLIENT_SECRET"},
            path=path,
        )
        update_kakao_app_secrets(
            "alice", {"clear_client_secret": True}, path=path
        )
        stored = load_stored_kakao_app_secrets("alice", path=path)
        self.assertEqual(stored["rest_api_key"], "REST_KEY")
        self.assertEqual(stored["client_secret"], "")

    def test_status_helpers_never_return_raw_secrets(self):
        with patch(
            "app.services.discord_secrets.load_stored_discord_secrets",
            return_value={"webhook_url": WEBHOOK},
        ):
            status = discord_secret_status("alice")
        self.assertEqual(status["webhook_url_source"], "stored")
        self.assertNotIn("SECRET_TOKEN", json.dumps(status))

        with patch(
            "app.services.kakao_app_secrets.load_stored_kakao_app_secrets",
            return_value={
                "rest_api_key": "REST_SECRET",
                "client_secret": "CLIENT_SECRET",
            },
        ):
            status = kakao_app_secret_status("alice")
        self.assertEqual(status["rest_api_key_source"], "stored")
        self.assertEqual(status["client_secret_source"], "stored")
        self.assertNotIn("REST_SECRET", json.dumps(status))
        self.assertNotIn("CLIENT_SECRET", json.dumps(status))

    def test_discord_and_kakao_do_not_fall_back_to_environment_credentials(self):
        env = {
            "DISCORD_WEBHOOK_URL": WEBHOOK,
            "DISCORD_WEALTH_USERNAME": "alice",
            "KAKAO_REST_API_KEY": "ENV_REST_KEY",
            "KAKAO_CLIENT_SECRET": "ENV_CLIENT_SECRET",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "app.services.notifications.discord.load_stored_discord_secrets",
            return_value={"webhook_url": ""},
        ):
            self.assertFalse(DiscordSender(username="alice").is_configured())

        with patch.dict(os.environ, env, clear=False), patch(
            "app.services.kakao_oauth.load_stored_kakao_app_secrets",
            return_value={"rest_api_key": "", "client_secret": ""},
        ), patch(
            "app.services.kakao_oauth.get_effective_system_settings",
            return_value={"public_base_url": "https://wealth.example.com"},
        ):
            config = resolve_kakao_app_config("alice")
        self.assertIsNone(config.rest_api_key)
        self.assertIsNone(config.client_secret)

    def test_invalid_secret_patch_is_fail_closed(self):
        with self.assertRaises(DiscordSecretError):
            update_discord_secrets(
                "alice", {"unexpected": "x"}, path=self.root / "discord.json"
            )
        with self.assertRaises(KakaoAppSecretError):
            update_kakao_app_secrets(
                "alice", {"unexpected": "x"}, path=self.root / "kakao.json"
            )


if __name__ == "__main__":
    unittest.main()
