from __future__ import annotations

from datetime import date
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.services.ipo.notifier import IpoTelegramNotifier
from app.services.ipo.reminders import run_ipo_subscription_reminders


class SubscriptionReminderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.notifier = IpoTelegramNotifier(bot_token="x", chat_id="y", state_path=Path(self.temp.name) / "state.json")
        self.notifier.send_message = MagicMock(return_value=True)
        self.market = {"ipos": [{"ipo_id": "ipo", "company_name": "테스트", "subscription_start": "2026-09-20", "subscription_end": "2026-09-21", "lead_managers": ["한국투자증권"]}]}
        self.apps = {"family_members": ["본인", "배우자", "자녀"], "applications": {"ipo": {"applied_owners": ["본인"]}}}

    def run_reminder(self, slot, day, apps=None):
        return run_ipo_subscription_reminders(username="test", reminder_slot=slot, today=day,
            notifier=self.notifier, market_store=self.market, applications=apps or self.apps)

    def test_window_slots_and_dedupe(self):
        self.assertEqual(self.run_reminder("0900", date(2026, 9, 19))["notifications_sent_count"], 0)
        self.assertEqual(self.run_reminder("0900", date(2026, 9, 20))["notifications_sent_count"], 1)
        self.assertEqual(self.run_reminder("0900", date(2026, 9, 20))["notifications_sent_count"], 0)
        self.assertEqual(self.run_reminder("1200", date(2026, 9, 20))["notifications_sent_count"], 1)
        self.assertEqual(self.run_reminder("1500", date(2026, 9, 21))["notifications_sent_count"], 1)
        self.assertEqual(self.run_reminder("0900", date(2026, 9, 22))["notifications_sent_count"], 0)

    def test_dynamic_completion_and_frozen_targets(self):
        self.run_reminder("0900", date(2026, 9, 20))
        complete = {"family_members": ["본인", "배우자", "자녀", "새구성원"], "applications": {"ipo": {
            "target_owners": ["본인", "배우자"], "target_frozen_at": "x", "applied_owners": ["본인", "배우자"]}}}
        result = self.run_reminder("1200", date(2026, 9, 20), complete)
        self.assertEqual(result["notifications_sent_count"], 0)
        self.assertEqual(result["all_applied_count"], 1)

    def test_message_and_failure_retry(self):
        self.notifier.send_message.return_value = False
        self.assertEqual(self.run_reminder("1500", date(2026, 9, 20))["notifications_sent_count"], 0)
        self.notifier.send_message.return_value = True
        self.assertEqual(self.run_reminder("1500", date(2026, 9, 20))["notifications_sent_count"], 1)
        message = self.notifier.send_message.call_args[0][0]
        self.assertIn("배우자, 자녀", message)
        self.assertIn("증권사별 실제 청약 접수 마감 시간을 확인", message)
        self.assertNotIn("16:00", message)

    def test_invalid_slot_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "INVALID_REMINDER_SLOT"):
            self.run_reminder("1000", date(2026, 9, 20))
