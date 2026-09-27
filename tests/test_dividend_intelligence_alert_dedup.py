from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.dividend_intelligence import _dispatch_events
from app.services.notifications.models import NotificationEvent


class DividendIntelligenceAlertDedupTests(unittest.TestCase):
    def test_successful_event_key_is_not_sent_twice(self) -> None:
        event = NotificationEvent(
            event_key="dividend_intelligence:test:event",
            event_type="dividend_confirmed_forecast",
            body="test",
            username="tester",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alert-state.json"
            service = MagicMock()
            service.dispatch.return_value = SimpleNamespace(
                status="sent",
                notifications_sent_count=1,
            )
            with (
                patch(
                    "app.services.dividend_intelligence._alert_state_path",
                    return_value=state_path,
                ),
                patch(
                    "app.services.notifications.service.UserNotificationService",
                    return_value=service,
                ),
            ):
                first = _dispatch_events("tester", [event])
                second = _dispatch_events("tester", [event])

        self.assertEqual(first["sent_count"], 1)
        self.assertEqual(second["status"], "no_new_events")
        self.assertEqual(service.dispatch.call_count, 1)

    def test_failed_event_key_is_not_consumed(self) -> None:
        event = NotificationEvent(
            event_key="dividend_intelligence:test:retry",
            event_type="dividend_confirmed_forecast",
            body="test",
            username="tester",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "alert-state.json"
            service = MagicMock()
            service.dispatch.return_value = SimpleNamespace(
                status="failed",
                notifications_sent_count=0,
            )
            with (
                patch(
                    "app.services.dividend_intelligence._alert_state_path",
                    return_value=state_path,
                ),
                patch(
                    "app.services.notifications.service.UserNotificationService",
                    return_value=service,
                ),
            ):
                _dispatch_events("tester", [event])
                _dispatch_events("tester", [event])

        self.assertEqual(service.dispatch.call_count, 2)


if __name__ == "__main__":
    unittest.main()
