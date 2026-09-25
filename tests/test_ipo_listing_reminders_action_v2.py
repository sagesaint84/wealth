"""Phase 4 listing reminder eligibility and Action V2 integration tests."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.ipo.notifier import IpoTelegramNotifier
from app.services.ipo.reminders import run_ipo_listing_reminders


class ListingReminderActionV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state_path = Path(self.temp.name) / "state.json"
        self.client = IpoTelegramNotifier(bot_token="x", chat_id="y", state_path=self.state_path)
        self.client.send_message = MagicMock(return_value=True)
        self.today = date(2026, 9, 29)
        self.market = {
            "ipos": [
                {
                    "ipo_id": "ipo-1",
                    "company_name": "테스트상장",
                    "stock_code": "123456",
                    "expected_listing_date": self.today.isoformat(),
                }
            ]
        }
        self.apps = {
            "revision": 1,
            "applications": {
                "ipo-1": {
                    "applied_owners": ["아빠", "엄마", "자녀"],
                    "applicants": {
                        owner: {"broker_id": "mirae", "account_id": f"a-{owner}"}
                        for owner in ("아빠", "엄마", "자녀")
                    },
                }
            },
        }

    def _run(self, *, slot="0850", apps=None):
        return run_ipo_listing_reminders(
            username="alice",
            reminder_slot=slot,
            today=self.today,
            notifier=self.client,
            market_store=self.market,
            applications=apps if apps is not None else self.apps,
        )

    @staticmethod
    def _action_factory():
        counter = {"value": 0}
        def create(**_kwargs):
            counter["value"] += 1
            ch = chr(ord("A") + counter["value"] - 1)
            return {"raw_token": ch * 32}
        return create

    def test_multi_owner_unsold_partial_full_aggregates_one_message(self):
        states = {
            "아빠": {"status": "UNSOLD", "allocation": {"quantity": 4, "sold_quantity": 0, "remaining_quantity": 4}},
            "엄마": {"status": "PARTIALLY_SOLD", "allocation": {"quantity": 4, "sold_quantity": 2, "remaining_quantity": 2}},
            "자녀": {"status": "FULLY_SOLD", "allocation": {"quantity": 2, "sold_quantity": 2, "remaining_quantity": 0}},
        }
        with patch("app.services.ipo.allocation.allocation_summary", side_effect=lambda _u, _i, owner, *_: states[owner]), \
             patch("app.services.action_v2.create_web_action", side_effect=self._action_factory()), \
             patch("app.services.action_v2.build_action_url", side_effect=lambda t: f"https://wealth.test/a/{t}"):
            result = self._run()

        self.assertEqual(result["notifications_sent_count"], 1)
        self.client.send_message.assert_called_once()
        message = self.client.send_message.call_args.args[0]
        self.assertIn("아빠", message)
        self.assertIn("엄마", message)
        self.assertNotIn("자녀", message)
        self.assertIn("배정 4주 · 매도 0주 · 잔여 4주", message)
        self.assertIn("배정 4주 · 매도 2주 · 잔여 2주", message)
        keyboard = self.client.send_message.call_args.kwargs["reply_markup"]["inline_keyboard"]
        self.assertEqual(len(keyboard), 2)
        urls = [row[0]["url"] for row in keyboard]
        self.assertEqual(len(set(urls)), 2)
        for url in urls:
            self.assertTrue(url.startswith("https://wealth.test/a/"))
            for forbidden in ("alice", "아빠", "엄마", "자녀", "ipo-1", "a-아빠", "123456"):
                self.assertNotIn(forbidden, url)

    def test_all_fully_sold_or_no_allocation_suppresses_slot(self):
        states = {
            "아빠": {"status": "FULLY_SOLD", "allocation": {"quantity": 4, "sold_quantity": 4, "remaining_quantity": 0}},
            "엄마": {"status": "NO_ALLOCATION", "allocation": {"quantity": 0, "sold_quantity": 0, "remaining_quantity": 0}},
            "자녀": {"status": "FULLY_SOLD", "allocation": {"quantity": 2, "sold_quantity": 2, "remaining_quantity": 0}},
        }
        with patch("app.services.ipo.allocation.allocation_summary", side_effect=lambda _u, _i, owner, *_: states[owner]):
            result = self._run(slot="1450")
        self.assertEqual(result["notifications_sent_count"], 0)
        self.assertEqual(result["fully_sold_count"], 2)
        self.assertEqual(result["no_allocation_count"], 1)
        self.client.send_message.assert_not_called()

    def test_only_applied_owners_are_considered(self):
        apps = {
            "applications": {
                "ipo-1": {
                    "applied_owners": ["아빠"],
                    "applicants": {
                        "아빠": {"broker_id": "mirae", "account_id": "a-dad"},
                        "엄마": {"broker_id": "mirae", "account_id": "a-mom"},
                    },
                }
            }
        }
        summary = MagicMock(return_value={"status": "UNSOLD", "allocation": {"quantity": 1, "sold_quantity": 0, "remaining_quantity": 1}})
        with patch("app.services.ipo.allocation.allocation_summary", summary), \
             patch("app.services.action_v2.create_web_action", side_effect=self._action_factory()), \
             patch("app.services.action_v2.build_action_url", side_effect=lambda t: f"https://wealth.test/a/{t}"):
            self._run(apps=apps)
        self.assertEqual(summary.call_count, 1)
        self.assertEqual(summary.call_args.args[2], "아빠")
        message = self.client.send_message.call_args.args[0]
        self.assertIn("아빠", message)
        self.assertNotIn("엄마", message)

    def test_unresolved_account_is_visible_without_allocation_lookup(self):
        apps = {
            "applications": {
                "ipo-1": {
                    "applied_owners": ["아빠"],
                    "applicants": {},
                }
            }
        }
        summary = MagicMock()
        with patch("app.services.ipo.allocation.allocation_summary", summary), \
             patch("app.services.action_v2.create_web_action", side_effect=self._action_factory()), \
             patch("app.services.action_v2.build_action_url", side_effect=lambda t: f"https://wealth.test/a/{t}"):
            result = self._run(apps=apps)
        self.assertEqual(result["notifications_sent_count"], 1)
        summary.assert_not_called()
        self.assertIn("청약 계좌 연결 필요", self.client.send_message.call_args.args[0])
        self.assertEqual(self.client.send_message.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["text"], "아빠 상태 확인")

    def test_unresolved_and_link_data_missing_remain_fail_safe_visible(self):
        states = {
            "아빠": {"status": "UNRESOLVED", "allocation": None},
            "엄마": {"status": "LINK_DATA_MISSING", "allocation": {"quantity": 3, "sold_quantity": 1, "remaining_quantity": 2}},
        }
        apps = {
            "applications": {
                "ipo-1": {
                    "applied_owners": ["아빠", "엄마"],
                    "applicants": {
                        "아빠": {"broker_id": "mirae", "account_id": "a1"},
                        "엄마": {"broker_id": "mirae", "account_id": "a2"},
                    },
                }
            }
        }
        with patch("app.services.ipo.allocation.allocation_summary", side_effect=lambda _u, _i, owner, *_: states[owner]), \
             patch("app.services.action_v2.create_web_action", side_effect=self._action_factory()), \
             patch("app.services.action_v2.build_action_url", side_effect=lambda t: f"https://wealth.test/a/{t}"):
            result = self._run(apps=apps)
        self.assertEqual(result["notifications_sent_count"], 1)
        message = self.client.send_message.call_args.args[0]
        self.assertIn("배정수량 미기록", message)
        self.assertIn("매도 연결 데이터 확인 필요", message)
        self.assertEqual(result["unresolved_count"], 1)

    def test_existing_dedupe_key_is_unchanged(self):
        with patch("app.services.ipo.allocation.allocation_summary", return_value={"status": "UNSOLD", "allocation": {"quantity": 1, "sold_quantity": 0, "remaining_quantity": 1}}), \
             patch("app.services.action_v2.create_web_action", side_effect=self._action_factory()), \
             patch("app.services.action_v2.build_action_url", side_effect=lambda t: f"https://wealth.test/a/{t}"):
            first = self._run(slot="0850")
            second = self._run(slot="0850")
        self.assertEqual((first["notifications_sent_count"], second["notifications_sent_count"]), (1, 0))
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertIn("ipo-1:listing_reminder:2026-09-29:0850", state["sent_keys"])

    def test_0850_partial_1450_then_full_suppression(self):
        phase = {"status": "UNSOLD", "sold": 0}
        def summary(_u, _i, _owner, *_):
            if phase["status"] == "FULLY_SOLD":
                return {"status": "FULLY_SOLD", "allocation": {"quantity": 4, "sold_quantity": 4, "remaining_quantity": 0}}
            if phase["status"] == "PARTIALLY_SOLD":
                return {"status": "PARTIALLY_SOLD", "allocation": {"quantity": 4, "sold_quantity": 2, "remaining_quantity": 2}}
            return {"status": "UNSOLD", "allocation": {"quantity": 4, "sold_quantity": 0, "remaining_quantity": 4}}
        apps = {
            "applications": {
                "ipo-1": {
                    "applied_owners": ["아빠"],
                    "applicants": {"아빠": {"broker_id": "mirae", "account_id": "a1"}},
                }
            }
        }
        with patch("app.services.ipo.allocation.allocation_summary", side_effect=summary), \
             patch("app.services.action_v2.create_web_action", side_effect=self._action_factory()), \
             patch("app.services.action_v2.build_action_url", side_effect=lambda t: f"https://wealth.test/a/{t}"):
            morning = self._run(slot="0850", apps=apps)
            phase["status"] = "PARTIALLY_SOLD"
            afternoon = self._run(slot="1450", apps=apps)
            phase["status"] = "FULLY_SOLD"
            after_full = self._run(slot="1550", apps=apps)
        self.assertEqual(morning["notifications_sent_count"], 1)
        self.assertEqual(afternoon["notifications_sent_count"], 1)
        self.assertEqual(after_full["notifications_sent_count"], 0)
        self.assertEqual(self.client.send_message.call_count, 2)


if __name__ == "__main__":
    unittest.main()
