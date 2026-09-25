from __future__ import annotations

from datetime import date
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.ipo.notifier import IpoTelegramNotifier
from app.services.ipo.reminders import run_ipo_listing_reminders, run_ipo_subscription_reminders


class SubscriptionReminderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.action_path = Path(self.temp.name) / "action_state.json"
        self.action_v2_path = Path(self.temp.name) / "action_v2_state.json"
        p_act = patch("app.services.ipo.actions.ACTION_FILE", self.action_path)
        p_act.start(); self.addCleanup(p_act.stop)
        p_act_v2 = patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_v2_path)
        p_act_v2.start(); self.addCleanup(p_act_v2.stop)
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
            self.run_reminder("2500", date(2026, 9, 20))
        with self.assertRaisesRegex(ValueError, "INVALID_REMINDER_SLOT"):
            self.run_reminder("invalid", date(2026, 9, 20))
        with self.assertRaisesRegex(ValueError, "INVALID_REMINDER_SLOT"):
            self.run_reminder("1260", date(2026, 9, 20))

    def test_generalized_slot_and_dynamic_last_slot(self):
        # 1000 is a valid slot (0000-2359)
        res = self.run_reminder("1000", date(2026, 9, 20))
        self.assertEqual(res["notifications_sent_count"], 1)
        self.assertEqual(res["slot"], "1000")
        msg = self.notifier.send_message.call_args[0][0]
        # By default is_last_slot is None, so slot 1000 should not have closing warning
        self.assertNotIn("청약 마감 시간이 가까워지고 있습니다", msg)

        # Non-1500 slot with is_last_slot=True should have closing warning
        self.notifier.send_message.reset_mock()
        run_ipo_subscription_reminders(
            username="test", reminder_slot="1430", today=date(2026, 9, 21),
            notifier=self.notifier, market_store=self.market, applications=self.apps,
            is_last_slot=True,
        )
        msg_last = self.notifier.send_message.call_args[0][0]
        self.assertIn("청약 마감 시간이 가까워지고 있습니다", msg_last)

        # 1500 slot with is_last_slot=False should NOT have closing warning
        self.notifier.send_message.reset_mock()
        run_ipo_subscription_reminders(
            username="test", reminder_slot="1500", today=date(2026, 9, 21),
            notifier=self.notifier, market_store=self.market, applications=self.apps,
            is_last_slot=False,
        )
        msg_not_last = self.notifier.send_message.call_args[0][0]
        self.assertNotIn("청약 마감 시간이 가까워지고 있습니다", msg_not_last)


class ListingReminderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.user_dir = Path(self.temp.name) / "users"
        def _get_user_dir(u=None):
            p = self.user_dir / (u or "alice").strip()
            p.mkdir(parents=True, exist_ok=True)
            return p
        self.user_dir_patches = [
            patch("app.services.user_manager.get_user_data_dir", side_effect=_get_user_dir),
            patch("app.services.settings.get_user_data_dir", side_effect=_get_user_dir),
            patch("app.services.portfolio._get_user_dir", side_effect=_get_user_dir),
        ]
        for p in self.user_dir_patches:
            p.start()
            self.addCleanup(p.stop)

        self.action_v2_path = Path(self.temp.name) / "action_v2_state.json"
        p_act_v2 = patch("app.services.action_v2.get_action_v2_file_path", return_value=self.action_v2_path)
        p_act_v2.start(); self.addCleanup(p_act_v2.stop)

        self.notifier = IpoTelegramNotifier(bot_token="x", chat_id="y", state_path=Path(self.temp.name) / "state.json")
        self.notifier.send_message = MagicMock(return_value=True)

    def run_listing(self, market, slot="0850", day=date(2026, 9, 29), apps=None):
        if apps is None:
            # Default application state where each ipo in market has applied_owners: ["본인"]
            apps = {"applications": {}}
            for item in market.get("ipos", []):
                iid = item.get("ipo_id")
                if iid:
                    apps["applications"][iid] = {
                        "applied_owners": ["본인"],
                        "applicants": {"본인": {"broker_id": "mirae", "account_id": "acc-1"}},
                    }
        return run_ipo_listing_reminders(username="alice", reminder_slot=slot, today=day,
                                         notifier=self.notifier, market_store=market,
                                         applications=apps)

    def test_expected_and_actual_listing_dates_and_slots_are_deduped(self):
        market = {"ipos": [
            {"ipo_id": "expected", "company_name": "예정", "expected_listing_date": "2026-09-29", "final_offer_price": 18000},
            {"ipo_id": "actual", "company_name": "실제", "expected_listing_date": "2026-09-28", "actual_listing_date": "2026-09-29"},
        ]}
        self.assertEqual(self.run_listing(market, "0850")["notifications_sent_count"], 2)
        self.assertEqual(self.run_listing(market, "0850")["notifications_sent_count"], 0)
        self.assertEqual(self.run_listing(market, "1450")["notifications_sent_count"], 2)
        message = self.notifier.send_message.call_args[0][0]
        self.assertIn("상장일 오후 확인", message)

    def test_actual_date_overrides_expected_and_invalid_records_are_ignored(self):
        market = {"ipos": [
            {"ipo_id": "moved", "expected_listing_date": "2026-09-29", "actual_listing_date": "2026-09-30"},
            {"ipo_id": "bad", "expected_listing_date": "not-a-date"},
            {"company_name": "id 없음", "expected_listing_date": "2026-09-29"},
        ]}
        self.assertEqual(self.run_listing(market)["notifications_sent_count"], 0)

    def test_notification_state_is_user_scoped(self):
        market = {"ipos": [{"ipo_id": "ipo", "expected_listing_date": "2026-09-29"}]}
        apps = {"applications": {"ipo": {"applied_owners": ["본인"], "applicants": {"본인": {"broker_id": "mirae", "account_id": "acc-1"}}}}}
        first = self.run_listing(market, apps=apps)
        other = IpoTelegramNotifier(bot_token="x", chat_id="y", state_path=Path(self.temp.name) / "other.json")
        other.send_message = MagicMock(return_value=True)
        second = run_ipo_listing_reminders(username="bob", reminder_slot="0850", today=date(2026, 9, 29), notifier=other, market_store=market, applications=apps)
        self.assertEqual((first["notifications_sent_count"], second["notifications_sent_count"]), (1, 1))

    def test_custom_listing_slot_uses_neutral_message(self):
        market = {"ipos": [{"ipo_id": "ipo", "expected_listing_date": "2026-09-29"}]}
        self.assertEqual(self.run_listing(market, "1030")["notifications_sent_count"], 1)
        message = self.notifier.send_message.call_args[0][0]
        self.assertIn("공모주 오늘 상장 확인", message)
        self.assertNotIn("상장일 오후 확인", message)
