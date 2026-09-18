import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.services.ipo.notifier import IpoTelegramNotifier


class IpoNotifierTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp_dir.name) / "test_notification_state.json"
        self.notifier = IpoTelegramNotifier(
            bot_token="test_bot_token",
            chat_id="123456789",
            state_path=self.state_path,
        )
        self.notifier.send_message = MagicMock(return_value=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_subscription_tomorrow_notification(self):
        # Canonical schema
        ipos = [{
            "ipo_id": "test_ipo_1",
            "company_name": "알파솔루션",
            "subscription_start": "2026-09-19",
            "subscription_end": "2026-09-20",
            "expected_listing_date": "2026-09-28",
            "final_offer_price": 25000,
            "lead_managers": ["미래에셋증권"],
            "score": {"score": 78.5, "grade": "B"},
        }]

        sent = self.notifier.check_and_notify_events(ipos, target_date_str="2026-09-18")
        self.assertEqual(len(sent), 2)  # sub_tomorrow + initial score
        self.notifier.send_message.assert_called()

        # Re-running with same target_date must deduplicate
        sent_again = self.notifier.check_and_notify_events(ipos, target_date_str="2026-09-18")
        self.assertEqual(len(sent_again), 0)

    def test_subscription_last_day_family_incomplete_warning(self):
        ipos = [{
            "ipo_id": "test_ipo_2",
            "company_name": "베타바이오",
            "subscription_start": "2026-09-17",
            "subscription_end": "2026-09-18",
            "expected_listing_date": "2026-09-26",
            "final_offer_price": 15000,
            "lead_managers": ["한국투자증권"],
        }]
        apps = {
            "applications": {
                "test_ipo_2": {
                    "applied_owners": ["아빠"],
                    "target_owners": ["아빠", "엄마", "자녀"],
                    "all_applied": False,
                }
            }
        }

        sent = self.notifier.check_and_notify_events(ipos, applications=apps, target_date_str="2026-09-18")
        self.assertEqual(len(sent), 1)

        calls = self.notifier.send_message.call_args_list
        last_msg = calls[-1][0][0]
        self.assertIn("미신청 가족 구성원", last_msg)
        self.assertIn("엄마, 자녀", last_msg)
        self.assertIn("✅ 아빠", last_msg)
        self.assertIn("⬜ 엄마", last_msg)

    def test_subscription_last_day_family_all_applied_no_warning(self):
        ipos = [{
            "ipo_id": "test_ipo_2",
            "company_name": "베타바이오",
            "subscription_start": "2026-09-17",
            "subscription_end": "2026-09-18",
            "expected_listing_date": "2026-09-26",
            "final_offer_price": 15000,
            "lead_managers": ["한국투자증권"],
        }]
        apps = {
            "applications": {
                "test_ipo_2": {
                    "applied_owners": ["아빠", "엄마", "자녀"],
                    "target_owners": ["아빠", "엄마", "자녀"],
                    "all_applied": True,
                }
            }
        }

        sent = self.notifier.check_and_notify_events(ipos, applications=apps, target_date_str="2026-09-18")
        self.assertEqual(len(sent), 1)

        calls = self.notifier.send_message.call_args_list
        last_msg = calls[-1][0][0]
        self.assertNotIn("미신청", last_msg)
        self.assertIn("가족 전원 신청 완료", last_msg)

    def test_listing_today_notification(self):
        ipos = [{
            "ipo_id": "test_ipo_3",
            "company_name": "감마테크",
            "subscription_start": "2026-09-10",
            "subscription_end": "2026-09-11",
            "actual_listing_date": "2026-09-18",
            "final_offer_price": 30000,
            "lead_managers": ["NH투자증권"],
        }]

        sent = self.notifier.check_and_notify_events(ipos, target_date_str="2026-09-18")
        self.assertEqual(len(sent), 1)
        self.assertIn("오늘 상장", self.notifier.send_message.call_args[0][0])

    def test_score_change_notification_thresholds(self):
        # 1. Initial calculation: 70.0 (B)
        ipo_base = {
            "ipo_id": "test_score_ipo",
            "company_name": "스코어기업",
            "subscription_start": "2026-09-25",
            "subscription_end": "2026-09-26",
            "score": {"score": 70.0, "grade": "B"},
        }
        sent1 = self.notifier.check_and_notify_events([ipo_base], target_date_str="2026-09-18")
        self.assertEqual(len(sent1), 1)
        self.assertIn("산정 완료", self.notifier.send_message.call_args[0][0])

        # 2. Change +4.0 points (70.0 -> 74.0), grade still B -> MUST NOT notify!
        ipo_base["score"] = {"score": 74.0, "grade": "B"}
        sent2 = self.notifier.check_and_notify_events([ipo_base], target_date_str="2026-09-18")
        self.assertEqual(len(sent2), 0)

        # 3. Change +5.0 points from last recorded 70.0 (70.0 -> 75.0), grade still B -> MUST notify!
        ipo_base["score"] = {"score": 75.0, "grade": "B"}
        sent3 = self.notifier.check_and_notify_events([ipo_base], target_date_str="2026-09-18")
        self.assertEqual(len(sent3), 1)
        self.assertIn("변동", self.notifier.send_message.call_args[0][0])

        # 4. Grade change with small score difference (75.0 B -> 80.0 A) -> MUST notify!
        ipo_base["score"] = {"score": 80.0, "grade": "A"}
        sent4 = self.notifier.check_and_notify_events([ipo_base], target_date_str="2026-09-18")
        self.assertEqual(len(sent4), 1)

    def test_corrupted_state_file_raises_error(self):
        from app.services.ipo.notifier import IpoNotifierStateError
        with open(self.state_path, "w", encoding="utf-8") as f:
            f.write("{invalid_json: true,")

        with self.assertRaises(IpoNotifierStateError):
            self.notifier.load_state()

    def test_schedule_and_price_change_notifications(self):
        ipo_initial = {
            "ipo_id": "test_change_ipo",
            "company_name": "변동테크",
            "subscription_start": "2026-10-01",
            "subscription_end": "2026-10-02",
            "expected_listing_date": "2026-10-10",
            "final_offer_price": 20000,
        }
        # Initial crawl establishes baseline snapshot, no change alert fired
        sent1 = self.notifier.check_and_notify_events([ipo_initial], target_date_str="2026-09-18")
        change_alerts = [k for k in sent1 if ":schedule_change:" in k]
        self.assertEqual(len(change_alerts), 0)

        # Subsequent crawl: price and listing date change
        ipo_modified = dict(ipo_initial)
        ipo_modified["final_offer_price"] = 25000
        ipo_modified["expected_listing_date"] = "2026-10-15"

        sent2 = self.notifier.check_and_notify_events([ipo_modified], target_date_str="2026-09-19")
        change_alerts2 = [k for k in sent2 if ":schedule_change:" in k]
        self.assertEqual(len(change_alerts2), 2)
        self.assertIn("test_change_ipo:schedule_change:final_offer_price:20000:25000", change_alerts2)
        self.assertIn("test_change_ipo:schedule_change:expected_listing_date:2026-10-10:2026-10-15", change_alerts2)

        # Deduplication check: same changed data on another run does not re-alert
        sent3 = self.notifier.check_and_notify_events([ipo_modified], target_date_str="2026-09-19")
        change_alerts3 = [k for k in sent3 if ":schedule_change:" in k]
        self.assertEqual(len(change_alerts3), 0)


if __name__ == "__main__":
    unittest.main()
