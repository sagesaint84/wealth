from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.services.notifications.history import (
    NotificationHistoryError,
    clear_notification_history,
    list_notification_history,
    record_notification_history,
    record_single_provider_history,
)
from app.services.notifications.models import NotificationEvent


class NotificationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "notifications" / "history.json"
        self.now = datetime(2026, 9, 26, 0, 1, 2, tzinfo=timezone.utc)

    def _event(self, key="secret:event:key"):
        return NotificationEvent(
            event_key=key,
            event_type="daily_close_summary",
            body="SECRET_MESSAGE_BODY",
            username="alice",
            title="SECRET_TITLE",
            action_url="https://wealth.example.com/action/SECRET_TOKEN",
            metadata={"secret": "SECRET_METADATA"},
        )

    def _report(self):
        return SimpleNamespace(
            status="partial",
            notifications_sent_count=1,
            provider_results={
                "telegram": {
                    "sent": True,
                    "status": "sent",
                    "retryable": False,
                    "error": None,
                },
                "discord": {
                    "sent": False,
                    "status": "failed",
                    "retryable": True,
                    "error": "SEND_FAILED",
                },
                "kakao": {
                    "sent": False,
                    "status": "disabled",
                    "retryable": False,
                    "error": None,
                },
            },
        )

    def test_history_stores_only_secret_safe_delivery_metadata(self):
        record_notification_history(
            "alice",
            self._event(),
            self._report(),
            path=self.path,
            now=self.now,
        )

        raw = self.path.read_text(encoding="utf-8")
        for forbidden in (
            "SECRET_MESSAGE_BODY",
            "SECRET_TITLE",
            "SECRET_TOKEN",
            "SECRET_METADATA",
            "secret:event:key",
        ):
            self.assertNotIn(forbidden, raw)

        body = json.loads(raw)
        self.assertEqual(body["version"], 1)
        self.assertEqual(len(body["events"]), 1)
        item = body["events"][0]
        self.assertEqual(item["event_type"], "daily_close_summary")
        self.assertEqual(item["status"], "partial")
        self.assertEqual(item["notifications_sent_count"], 1)
        self.assertRegex(item["event_key_fingerprint"], r"^[0-9a-f]{12}$")
        self.assertEqual(item["providers"]["telegram"]["status"], "sent")
        self.assertEqual(item["providers"]["discord"]["error"], "SEND_FAILED")
        self.assertEqual(item["providers"]["kakao"]["status"], "disabled")
        self.assertNotIn("body", item)
        self.assertNotIn("title", item)
        self.assertNotIn("action_url", item)
        self.assertNotIn("event_key", item)

    def test_history_returns_newest_first_and_enforces_retention(self):
        with patch("app.services.notifications.history.HISTORY_RETENTION", 3):
            for idx in range(5):
                record_notification_history(
                    "alice",
                    self._event(key=f"event:{idx}"),
                    self._report(),
                    path=self.path,
                    now=self.now,
                )
            result = list_notification_history(
                "alice",
                limit=3,
                path=self.path,
            )

        self.assertEqual(result["retention"], 3)
        self.assertEqual(result["count"], 3)
        self.assertEqual(len(result["events"]), 3)
        fingerprints = [
            item["event_key_fingerprint"]
            for item in result["events"]
        ]
        self.assertEqual(len(set(fingerprints)), 3)

    def test_single_provider_history_records_only_that_provider(self):
        record_single_provider_history(
            "alice",
            self._event("integration_test:discord"),
            provider="discord",
            success=False,
            retryable=True,
            error="HTTP_500",
            path=self.path,
            now=self.now,
        )
        result = list_notification_history("alice", path=self.path)
        item = result["events"][0]
        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["notifications_sent_count"], 0)
        self.assertEqual(set(item["providers"]), {"discord"})
        self.assertEqual(item["providers"]["discord"]["error"], "HTTP_500")
        self.assertTrue(item["providers"]["discord"]["retryable"])

    def test_untrusted_error_text_is_replaced_by_stable_code(self):
        report = self._report()
        report.provider_results["discord"]["error"] = (
            "https://discord.com/api/webhooks/SECRET/TOKEN"
        )
        record_notification_history(
            "alice",
            self._event(),
            report,
            path=self.path,
            now=self.now,
        )
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn("discord.com", raw)
        result = list_notification_history("alice", path=self.path)
        self.assertEqual(
            result["events"][0]["providers"]["discord"]["error"],
            "SEND_FAILED",
        )

    def test_clear_returns_deleted_count_and_keeps_valid_empty_store(self):
        for idx in range(2):
            record_notification_history(
                "alice",
                self._event(key=f"clear:{idx}"),
                self._report(),
                path=self.path,
                now=self.now,
            )
        self.assertEqual(
            clear_notification_history("alice", path=self.path),
            2,
        )
        result = list_notification_history("alice", path=self.path)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["events"], [])

    def test_corrupt_history_fails_closed(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text('{"version":1,"events":"bad"}', encoding="utf-8")
        with self.assertRaisesRegex(
            NotificationHistoryError,
            "NOTIFICATION_HISTORY_STATE_INVALID",
        ):
            list_notification_history("alice", path=self.path)

    def test_clear_recovers_corrupt_history_file(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{bad", encoding="utf-8")
        self.assertEqual(
            clear_notification_history("alice", path=self.path),
            0,
        )
        result = list_notification_history("alice", path=self.path)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["count"], 0)

    def test_invalid_limit_is_rejected(self):
        for limit in (0, 101, "20"):
            with self.assertRaisesRegex(
                ValueError,
                "NOTIFICATION_HISTORY_LIMIT_INVALID",
            ):
                list_notification_history(
                    "alice",
                    limit=limit,
                    path=self.path,
                )

    def test_default_test_mode_storage_is_side_effect_free(self):
        with patch(
            "app.services.notifications.history.history_path",
            side_effect=AssertionError("repository history path must not be touched"),
        ):
            record_notification_history(
                "alice",
                self._event(),
                self._report(),
            )
            result = list_notification_history("alice")
            deleted = clear_notification_history("alice")
        self.assertEqual(result["events"], [])
        self.assertEqual(deleted, 0)


if __name__ == "__main__":
    unittest.main()
