from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app
from app.services.notifications.history import NotificationHistoryError


class NotificationHistoryApiTests(unittest.TestCase):
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

    def test_get_history_is_user_scoped_and_honors_limit(self):
        payload = {
            "version": 1,
            "retention": 100,
            "count": 2,
            "events": [
                {
                    "created_at": "2026-09-26T00:00:00+00:00",
                    "event_type": "ipo_alert",
                    "event_key_fingerprint": "0123456789ab",
                    "status": "sent",
                    "notifications_sent_count": 1,
                    "providers": {
                        "telegram": {
                            "sent": True,
                            "status": "sent",
                            "retryable": False,
                            "error": None,
                        }
                    },
                }
            ],
        }
        with patch(
            "app.services.notifications.history.list_notification_history",
            return_value=payload,
        ) as read:
            response = self.client.get(
                "/api/settings/notifications/history?limit=7"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        read.assert_called_once_with("alice", limit=7)

    def test_clear_history_is_user_scoped(self):
        with patch(
            "app.services.notifications.history.clear_notification_history",
            return_value=12,
        ) as clear:
            response = self.client.delete(
                "/api/settings/notifications/history"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"ok": True, "deleted_count": 12},
        )
        clear.assert_called_once_with("alice")

    def test_invalid_history_limit_returns_stable_400(self):
        with patch(
            "app.services.notifications.history.list_notification_history",
            side_effect=ValueError("NOTIFICATION_HISTORY_LIMIT_INVALID"),
        ):
            response = self.client.get(
                "/api/settings/notifications/history?limit=0"
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "NOTIFICATION_HISTORY_LIMIT_INVALID",
        )

    def test_corrupt_history_returns_secret_safe_500(self):
        with patch(
            "app.services.notifications.history.list_notification_history",
            side_effect=NotificationHistoryError(
                "NOTIFICATION_HISTORY_STATE_INVALID"
            ),
        ):
            response = self.client.get(
                "/api/settings/notifications/history"
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json()["detail"]["code"],
            "NOTIFICATION_HISTORY_UNAVAILABLE",
        )
        self.assertNotIn("STATE_INVALID", response.text)

    def test_history_requires_authentication(self):
        self.client.cookies.clear()
        self.assertEqual(
            self.client.get(
                "/api/settings/notifications/history"
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.delete(
                "/api/settings/notifications/history"
            ).status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
