from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services.kakao_oauth import KakaoAppConfig
from app.services.notifications.models import NotificationSendResult


class KakaoSettingsApiTests(unittest.TestCase):
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

    def test_status_is_authenticated_and_secret_free(self):
        safe = {
            "app_configured": True,
            "client_secret_configured": True,
            "public_base_url_configured": True,
            "redirect_uri": "https://wealth.example.com/api/integrations/kakao/oauth/callback",
            "connected": True,
            "access_expires_at": "2026-09-26T00:00:00+00:00",
            "refresh_expires_at": "2026-11-01T00:00:00+00:00",
            "scope": "talk_message",
            "updated_at": "2026-09-25T00:00:00+00:00",
        }
        with patch("app.services.kakao_oauth.safe_kakao_status", return_value=safe):
            response = self.client.get("/api/settings/kakao")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["connected"])
        self.assertNotIn("access_token", response.text)
        self.assertNotIn("refresh_token", response.text)
        self.assertNotIn("CLIENT_SECRET", response.text)

        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/settings/kakao").status_code, 401)

    def test_oauth_start_redirects_only_for_authenticated_user(self):
        with patch(
            "app.services.kakao_oauth.build_authorize_url",
            return_value="https://kauth.kakao.com/oauth/authorize?state=signed",
        ):
            response = self.client.get(
                "/api/settings/kakao/oauth/start", follow_redirects=False
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["location"].startswith("https://kauth.kakao.com/"))

        self.client.cookies.clear()
        self.assertEqual(
            self.client.get(
                "/api/settings/kakao/oauth/start", follow_redirects=False
            ).status_code,
            401,
        )

    def test_callback_is_public_and_exchanges_only_signed_state_user(self):
        self.client.cookies.clear()
        config = KakaoAppConfig(
            rest_api_key="REST",
            client_secret="SECRET",
            public_base_url="https://wealth.example.com",
        )
        with patch(
            "app.services.kakao_oauth.consume_oauth_state", return_value="alice"
        ) as state, patch(
            "app.services.kakao_oauth.exchange_authorization_code"
        ) as exchange, patch(
            "app.services.kakao_oauth.resolve_kakao_app_config",
            return_value=config,
        ):
            response = self.client.get(
                "/api/integrations/kakao/oauth/callback?code=AUTH&state=SIGNED"
            )
        self.assertEqual(response.status_code, 200)
        state.assert_called_once_with("SIGNED")
        exchange.assert_called_once_with("alice", "AUTH")
        self.assertNotIn("SECRET", response.text)
        self.assertNotIn("AUTH", response.text)

    def test_test_message_uses_current_user_sender(self):
        with patch(
            "app.services.notifications.kakao.KakaoSender.send",
            return_value=NotificationSendResult(success=True, provider="kakao"),
        ) as send:
            response = self.client.post("/api/settings/kakao/test")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        event = send.call_args.args[0]
        self.assertEqual(event.username, "alice")
        self.assertEqual(event.event_type, "integration_test")

    def test_disconnect_clears_only_current_users_tokens(self):
        with patch("app.services.kakao_tokens.clear_kakao_tokens") as clear:
            response = self.client.post("/api/settings/kakao/disconnect")
        self.assertEqual(response.status_code, 200)
        clear.assert_called_once_with("alice")


if __name__ == "__main__":
    unittest.main()
