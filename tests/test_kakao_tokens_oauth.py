from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from app.services.kakao_oauth import (
    KakaoAppConfig,
    build_authorize_url,
    consume_oauth_state,
    exchange_authorization_code,
    refresh_kakao_tokens,
)
from app.services.kakao_tokens import (
    KakaoTokenState,
    load_kakao_tokens,
    save_kakao_token_response,
)


class FakeResponse:
    def __init__(self, payload: dict, status: int = 200):
        self.status = status
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


class KakaoTokenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "kakao.json"
        self.now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)

    def test_save_load_roundtrip_and_repr_hides_secrets(self):
        state = save_kakao_token_response(
            "alice",
            {
                "access_token": "ACCESS_SECRET",
                "refresh_token": "REFRESH_SECRET",
                "expires_in": 3600,
                "refresh_token_expires_in": 86400,
                "scope": "talk_message",
            },
            now=self.now,
            path=self.path,
        )
        loaded = load_kakao_tokens("alice", path=self.path)
        self.assertEqual(loaded.access_token, "ACCESS_SECRET")
        self.assertEqual(loaded.refresh_token, "REFRESH_SECRET")
        self.assertEqual(loaded.scope, "talk_message")
        self.assertNotIn("ACCESS_SECRET", repr(state))
        self.assertNotIn("REFRESH_SECRET", repr(state))

    def test_refresh_response_preserves_existing_refresh_token(self):
        previous = KakaoTokenState(
            access_token="old-access",
            refresh_token="keep-refresh",
            access_expires_at=self.now.isoformat(),
            refresh_expires_at=self.now.isoformat(),
            scope="talk_message",
            updated_at=self.now.isoformat(),
        )
        state = save_kakao_token_response(
            "alice",
            {"access_token": "new-access", "expires_in": 3600},
            now=self.now,
            preserve_refresh=previous,
            path=self.path,
        )
        self.assertEqual(state.refresh_token, "keep-refresh")


class KakaoOAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.token_path = Path(self.temp.name) / "kakao.json"
        self.config = KakaoAppConfig(
            rest_api_key="REST_KEY",
            client_secret="CLIENT_SECRET",
            public_base_url="https://wealth.example.com",
        )

    def test_authorize_url_is_user_bound_and_requests_talk_message_scope(self):
        with patch("app.services.kakao_oauth.resolve_kakao_app_config", return_value=self.config), \
             patch("app.services.kakao_oauth.resolve_application_secret", return_value="signing-secret"), \
             patch("app.services.kakao_oauth.get_user_by_name", return_value={"username": "alice"}):
            url = build_authorize_url("alice")
            parts = urlsplit(url)
            params = parse_qs(parts.query)
            self.assertEqual(parts.scheme, "https")
            self.assertEqual(parts.netloc, "kauth.kakao.com")
            self.assertEqual(params["client_id"], ["REST_KEY"])
            self.assertEqual(params["scope"], ["talk_message"])
            self.assertEqual(
                params["redirect_uri"],
                ["https://wealth.example.com/api/integrations/kakao/oauth/callback"],
            )
            self.assertEqual(consume_oauth_state(params["state"][0]), "alice")

    def test_exchange_posts_expected_form_and_saves_user_tokens(self):
        captured = {}

        def opener(req, timeout=10):
            captured["url"] = req.full_url
            captured["form"] = parse_qs(req.data.decode("utf-8"))
            return FakeResponse(
                {
                    "access_token": "access-1",
                    "refresh_token": "refresh-1",
                    "expires_in": 3600,
                    "refresh_token_expires_in": 86400,
                    "scope": "talk_message",
                }
            )

        with patch("app.services.kakao_oauth.resolve_kakao_app_config", return_value=self.config), \
             patch("app.services.kakao_tokens.token_path", return_value=self.token_path):
            state = exchange_authorization_code("alice", "AUTH_CODE", opener=opener)

        self.assertEqual(captured["url"], "https://kauth.kakao.com/oauth/token")
        self.assertEqual(captured["form"]["grant_type"], ["authorization_code"])
        self.assertEqual(captured["form"]["client_id"], ["REST_KEY"])
        self.assertEqual(captured["form"]["client_secret"], ["CLIENT_SECRET"])
        self.assertEqual(captured["form"]["code"], ["AUTH_CODE"])
        self.assertEqual(state.access_token, "access-1")
        self.assertEqual(
            load_kakao_tokens("alice", path=self.token_path).refresh_token,
            "refresh-1",
        )

    def test_refresh_preserves_old_refresh_token_when_kakao_omits_new_one(self):
        save_kakao_token_response(
            "alice",
            {
                "access_token": "expired",
                "refresh_token": "refresh-old",
                "expires_in": 1,
                "refresh_token_expires_in": 86400,
                "scope": "talk_message",
            },
            path=self.token_path,
        )

        def opener(req, timeout=10):
            return FakeResponse({"access_token": "fresh", "expires_in": 3600})

        with patch("app.services.kakao_oauth.resolve_kakao_app_config", return_value=self.config), \
             patch("app.services.kakao_tokens.token_path", return_value=self.token_path):
            state = refresh_kakao_tokens("alice", opener=opener)
        self.assertEqual(state.access_token, "fresh")
        self.assertEqual(state.refresh_token, "refresh-old")


if __name__ == "__main__":
    unittest.main()
