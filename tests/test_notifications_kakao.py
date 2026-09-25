from __future__ import annotations

import io
import json
import logging
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs
from unittest.mock import MagicMock, patch

from app.services.kakao_oauth import KakaoAppConfig
from app.services.kakao_tokens import KakaoTokenState
from app.services.notifications import KakaoSender
from app.services.notifications.models import NotificationEvent


class FakeResponse:
    def __init__(self, status: int = 200, payload: dict | None = None, headers=None):
        self.status = status
        self.headers = headers or {}
        self._body = json.dumps(payload or {"result_code": 0}).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


class KakaoSenderTests(unittest.TestCase):
    def setUp(self):
        self.config = KakaoAppConfig(
            rest_api_key="REST_KEY",
            client_secret="CLIENT_SECRET",
            public_base_url="https://wealth.example.com",
        )
        self.tokens = KakaoTokenState(
            access_token="ACCESS_SECRET",
            refresh_token="REFRESH_SECRET",
            access_expires_at="2099-01-01T00:00:00+00:00",
            refresh_expires_at="2099-02-01T00:00:00+00:00",
            scope="talk_message",
        )
        self.config_patch = patch(
            "app.services.notifications.kakao.resolve_kakao_app_config",
            return_value=self.config,
        )
        self.token_patch = patch(
            "app.services.notifications.kakao.load_kakao_tokens",
            return_value=self.tokens,
        )
        self.config_patch.start()
        self.token_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.addCleanup(self.token_patch.stop)

    def test_provider_and_configuration(self):
        sender = KakaoSender(username="alice")
        self.assertEqual(sender.provider_name, "kakao")
        self.assertTrue(sender.is_configured())

    def test_success_uses_official_self_message_endpoint_and_text_template(self):
        captured = {}

        def opener(req, timeout=10):
            captured["req"] = req
            return FakeResponse()

        event = NotificationEvent(
            event_key="ipo-1",
            event_type="ipo_alert",
            body="<b>공모주 상장</b><br>확인하세요 &amp; 기록하세요",
            action_url="https://wealth.example.com/a/token",
            action_label="매도 기록",
        )
        with patch(
            "app.services.notifications.kakao.get_valid_access_token",
            return_value="ACCESS_SECRET",
        ):
            result = KakaoSender(username="alice").send(event, _urlopen=opener)

        self.assertTrue(result.success)
        req = captured["req"]
        self.assertEqual(
            req.full_url,
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        )
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Authorization"), "Bearer ACCESS_SECRET")
        form = parse_qs(req.data.decode("utf-8"))
        template = json.loads(form["template_object"][0])
        self.assertEqual(template["object_type"], "text")
        self.assertEqual(template["text"], "공모주 상장\n확인하세요 & 기록하세요")
        self.assertEqual(
            template["link"]["web_url"],
            "https://wealth.example.com/a/token",
        )
        self.assertEqual(template["button_title"], "매도 기록")

    def test_empty_message_fails_before_token_or_network(self):
        opener = MagicMock()
        token = MagicMock()
        with patch(
            "app.services.notifications.kakao.get_valid_access_token", token
        ):
            result = KakaoSender(username="alice").send(
                NotificationEvent(
                    event_key="empty",
                    event_type="test",
                    body="<br>",
                ),
                _urlopen=opener,
            )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "MESSAGE_EMPTY")
        token.assert_not_called()
        opener.assert_not_called()

    def test_compact_kakao_body_metadata_allows_long_generic_event(self):
        captured = {}

        def opener(req, timeout=10):
            captured["req"] = req
            return FakeResponse()

        with patch(
            "app.services.notifications.kakao.get_valid_access_token",
            return_value="ACCESS_SECRET",
        ):
            result = KakaoSender(username="alice").send(
                NotificationEvent(
                    event_key="compact",
                    event_type="ipo_alert",
                    body="가" * 500,
                    metadata={"kakao_body": "공모주 알림 요약"},
                ),
                _urlopen=opener,
            )

        self.assertTrue(result.success)
        form = parse_qs(captured["req"].data.decode("utf-8"))
        template = json.loads(form["template_object"][0])
        self.assertEqual(template["text"], "공모주 알림 요약")

    def test_message_over_200_chars_fails_before_token_or_network(self):
        opener = MagicMock()
        token = MagicMock()
        with patch(
            "app.services.notifications.kakao.get_valid_access_token", token
        ):
            result = KakaoSender(username="alice").send(
                NotificationEvent(
                    event_key="long",
                    event_type="test",
                    body="가" * 201,
                ),
                _urlopen=opener,
            )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "MESSAGE_TOO_LONG")
        token.assert_not_called()
        opener.assert_not_called()

    def test_external_action_url_is_rejected_before_network(self):
        opener = MagicMock()
        result = KakaoSender(username="alice").send(
            NotificationEvent(
                event_key="bad-link",
                event_type="test",
                body="hello",
                action_url="https://evil.example/a/token",
            ),
            _urlopen=opener,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "ACTION_URL_NOT_ALLOWED")
        opener.assert_not_called()

    def test_401_refreshes_once_and_retries_with_new_token(self):
        calls = []

        def opener(req, timeout=10):
            calls.append(req)
            if len(calls) == 1:
                raise HTTPError(req.full_url, 401, "expired", {}, None)
            return FakeResponse()

        refreshed = KakaoTokenState(
            access_token="NEW_ACCESS",
            refresh_token="REFRESH_SECRET",
        )
        with patch(
            "app.services.notifications.kakao.get_valid_access_token",
            return_value="OLD_ACCESS",
        ), patch(
            "app.services.notifications.kakao.refresh_kakao_tokens",
            return_value=refreshed,
        ) as refresh:
            result = KakaoSender(username="alice", max_attempts=2).send(
                NotificationEvent(event_key="k", event_type="test", body="hello"),
                _urlopen=opener,
            )

        self.assertTrue(result.success)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].get_header("Authorization"), "Bearer OLD_ACCESS")
        self.assertEqual(calls[1].get_header("Authorization"), "Bearer NEW_ACCESS")
        refresh.assert_called_once()

    def test_permanent_4xx_is_nonretryable(self):
        calls = []

        def opener(req, timeout=10):
            calls.append(req)
            raise HTTPError(req.full_url, 403, "forbidden", {}, None)

        with patch(
            "app.services.notifications.kakao.get_valid_access_token",
            return_value="ACCESS_SECRET",
        ):
            result = KakaoSender(username="alice", max_attempts=3).send(
                NotificationEvent(event_key="k", event_type="test", body="hello"),
                _urlopen=opener,
                _sleep=lambda _: self.fail("must not sleep"),
            )
        self.assertFalse(result.success)
        self.assertFalse(result.retryable)
        self.assertEqual(result.error_code, "HTTP_403")
        self.assertEqual(len(calls), 1)

    def test_network_retry_is_bounded(self):
        calls = []

        def opener(req, timeout=10):
            calls.append(req)
            raise OSError("network down ACCESS_SECRET")

        with patch(
            "app.services.notifications.kakao.get_valid_access_token",
            return_value="ACCESS_SECRET",
        ):
            result = KakaoSender(username="alice", max_attempts=3).send(
                NotificationEvent(event_key="k", event_type="test", body="hello"),
                _urlopen=opener,
                _sleep=lambda _: None,
            )
        self.assertFalse(result.success)
        self.assertTrue(result.retryable)
        self.assertEqual(result.error_code, "SEND_FAILED")
        self.assertEqual(len(calls), 3)

    def test_secrets_are_not_logged_on_failure(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        target = logging.getLogger("app.services.notifications.kakao")
        old_level = target.level
        target.addHandler(handler)
        target.setLevel(logging.INFO)
        try:
            def opener(req, timeout=10):
                raise RuntimeError(
                    "ACCESS_SECRET REFRESH_SECRET CLIENT_SECRET should not log"
                )

            with patch(
                "app.services.notifications.kakao.get_valid_access_token",
                return_value="ACCESS_SECRET",
            ):
                result = KakaoSender(username="alice", max_attempts=1).send(
                    NotificationEvent(
                        event_key="k", event_type="test", body="hello"
                    ),
                    _urlopen=opener,
                )
            self.assertFalse(result.success)
            output = stream.getvalue()
            self.assertIn("Kakao send failed", output)
            for secret in ("ACCESS_SECRET", "REFRESH_SECRET", "CLIENT_SECRET"):
                self.assertNotIn(secret, output)
        finally:
            target.removeHandler(handler)
            target.setLevel(old_level)


if __name__ == "__main__":
    unittest.main()
