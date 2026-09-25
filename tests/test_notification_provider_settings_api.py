from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services.notifications.models import NotificationSendResult


class NotificationProviderSettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user = patch(
            "app.services.user_manager.get_user_by_name",
            return_value={"username": "alice", "id": "a", "role": "user"},
        )
        self.user.start()
        self.addCleanup(self.user.stop)
        self.client.cookies.set(
            main.COOKIE_NAME,
            main._serializer.dumps({"user": "alice", "role": "user"}),
        )

    def test_discord_status_and_secret_patch_are_user_scoped_and_secret_free(self):
        safe = {
            "webhook_url_configured": True,
            "webhook_url_source": "stored",
        }
        with patch(
            "app.services.discord_secrets.discord_secret_status",
            return_value=safe,
        ):
            response = self.client.get("/api/settings/discord")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("discord.com/api/webhooks", response.text)

        with patch(
            "app.services.discord_secrets.update_discord_secrets"
        ) as update, patch(
            "app.services.discord_secrets.discord_secret_status",
            return_value=safe,
        ):
            response = self.client.patch(
                "/api/settings/discord/secrets",
                json={"webhook_url": "https://discord.com/api/webhooks/1/TOKEN"},
            )
        self.assertEqual(response.status_code, 200)
        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], "alice")
        self.assertNotIn("TOKEN", response.text)

    def test_discord_test_uses_current_user_sender(self):
        with patch(
            "app.services.notifications.discord.DiscordSender.send",
            return_value=NotificationSendResult(success=True, provider="discord"),
        ) as send, patch(
            "app.services.notifications.history.record_single_provider_history"
        ) as record:
            response = self.client.post("/api/settings/discord/test")
        self.assertEqual(response.status_code, 200)
        event = send.call_args.args[0]
        self.assertEqual(event.username, "alice")
        self.assertEqual(event.event_type, "integration_test")
        record.assert_called_once()
        self.assertEqual(record.call_args.args[:2], ("alice", event))
        self.assertEqual(record.call_args.kwargs["provider"], "discord")
        self.assertTrue(record.call_args.kwargs["success"])

    def test_kakao_secret_patch_is_user_scoped_and_never_returns_values(self):
        before = {"rest_api_key": "OLD", "client_secret": "OLD_SECRET"}
        after = {"rest_api_key": "NEW", "client_secret": "NEW_SECRET"}
        safe = {
            "rest_api_key_configured": True,
            "rest_api_key_source": "stored",
            "client_secret_configured": True,
            "client_secret_source": "stored",
        }
        with patch(
            "app.services.kakao_app_secrets.load_stored_kakao_app_secrets",
            return_value=before,
        ), patch(
            "app.services.kakao_app_secrets.update_kakao_app_secrets",
            return_value=after,
        ) as update, patch(
            "app.services.kakao_app_secrets.kakao_app_secret_status",
            return_value=safe,
        ), patch("app.services.kakao_tokens.clear_kakao_tokens") as clear:
            response = self.client.patch(
                "/api/settings/kakao/secrets",
                json={
                    "rest_api_key": "NEW",
                    "client_secret": "NEW_SECRET",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.args[0], "alice")
        clear.assert_called_once_with("alice")
        self.assertNotIn("NEW_SECRET", response.text)
        self.assertNotIn('"NEW"', response.text)

    def test_kakao_client_secret_only_change_keeps_oauth_tokens(self):
        before = {"rest_api_key": "SAME", "client_secret": "OLD_SECRET"}
        after = {"rest_api_key": "SAME", "client_secret": "NEW_SECRET"}
        with patch(
            "app.services.kakao_app_secrets.load_stored_kakao_app_secrets",
            return_value=before,
        ), patch(
            "app.services.kakao_app_secrets.update_kakao_app_secrets",
            return_value=after,
        ), patch(
            "app.services.kakao_app_secrets.kakao_app_secret_status",
            return_value={
                "rest_api_key_configured": True,
                "rest_api_key_source": "stored",
                "client_secret_configured": True,
                "client_secret_source": "stored",
            },
        ), patch("app.services.kakao_tokens.clear_kakao_tokens") as clear:
            response = self.client.patch(
                "/api/settings/kakao/secrets",
                json={"client_secret": "NEW_SECRET"},
            )
        self.assertEqual(response.status_code, 200)
        clear.assert_not_called()

    def test_secret_apis_require_authentication(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/settings/discord").status_code, 401)
        self.assertEqual(
            self.client.patch("/api/settings/discord/secrets", json={}).status_code,
            401,
        )
        self.assertEqual(
            self.client.patch("/api/settings/kakao/secrets", json={}).status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
