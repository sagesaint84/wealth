from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app


def _effective(*, discord=True, kakao=True):
    return {
        "version": 1,
        "telegram": {
            "enabled": True,
            "chat_id": 123,
            "allowed_user_id": 456,
            "allowed_chat_id": 123,
        },
        "discord": {"enabled": discord},
        "kakao": {"enabled": kakao},
        "automation": {},
        "toss_wts": {"session_check_enabled": False},
    }


class NotificationProviderEnabledApiTests(unittest.TestCase):
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
        self.secret_status = {
            "bot_token_configured": True,
            "bot_token_source": "stored",
            "webhook_secret_configured": True,
            "webhook_secret_source": "stored",
        }

    def test_notifications_get_returns_all_provider_switches(self):
        with patch(
            "app.services.settings.get_effective_settings",
            return_value=_effective(discord=False, kakao=True),
        ), patch(
            "app.services.telegram_config.telegram_secret_status",
            return_value=self.secret_status,
        ):
            response = self.client.get("/api/settings/notifications")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["discord"]["enabled"])
        self.assertTrue(body["kakao"]["enabled"])
        self.assertTrue(body["telegram"]["enabled"])

    def test_notifications_patch_updates_discord_and_kakao_together(self):
        updated = _effective(discord=False, kakao=False)
        with patch(
            "app.services.settings.patch_settings",
            return_value=updated,
        ) as save, patch(
            "app.services.telegram_config.telegram_secret_status",
            return_value=self.secret_status,
        ):
            response = self.client.patch(
                "/api/settings/notifications",
                json={
                    "discord": {"enabled": False},
                    "kakao": {"enabled": False},
                },
            )

        self.assertEqual(response.status_code, 200)
        save.assert_called_once_with(
            "alice",
            {
                "discord": {"enabled": False},
                "kakao": {"enabled": False},
            },
        )
        self.assertFalse(response.json()["discord"]["enabled"])
        self.assertFalse(response.json()["kakao"]["enabled"])

    def test_notifications_patch_rejects_mixed_unknown_keys(self):
        with patch("app.services.settings.patch_settings") as save:
            response = self.client.patch(
                "/api/settings/notifications",
                json={
                    "discord": {"enabled": False},
                    "unexpected": True,
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "INVALID_PATCH")
        save.assert_not_called()

    def test_notifications_api_requires_authentication(self):
        self.client.cookies.clear()
        self.assertEqual(
            self.client.get("/api/settings/notifications").status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
