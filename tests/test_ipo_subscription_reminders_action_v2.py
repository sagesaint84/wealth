"""Tests for Phase 3 — IPO Subscription Action Link Integration.

Verifies:
A. Progressive completion across slots (09:00 -> applied -> 12:00 -> applied -> 15:00 no reminder)
B. Single remaining owner display in subsequent reminders
C. All applied stops reminder delivery and increments all_applied_count
D. Action URL opacity (no PII, no owner, no username, no plaintext in query or path)
E. Fallback when public_base_url is missing (reminder succeeds with legacy callbacks, no crash)
F. Fallback when Action V2 creation fails (generic log, reminder succeeds)
G. Stale/re-opened link handling after external completion (landing renders already applied, POST returns already_applied)
H. Cross-user isolation (token bound to alice rejected by bob)
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import _serializer, app, COOKIE_NAME
from app.services.action_v2 import (
    ACTION_TYPE_MARK_IPO_APPLIED,
    build_action_url,
    create_web_action,
    get_action_v2_file_path,
    get_web_action_metadata,
)
from app.services.ipo.actions import mark_ipo_owner_applied
from app.services.ipo.notifier import IpoTelegramNotifier, KST
from app.services.ipo.reminders import run_ipo_subscription_reminders


def _make_market_data(ipo_id="test-ipo-1", start=None, end=None, name="알파로보틱스"):
    cur = datetime.now(KST).date()
    start_str = start or (cur - timedelta(days=1)).isoformat()
    end_str = end or (cur + timedelta(days=2)).isoformat()
    return {
        "ipos": [
            {
                "ipo_id": ipo_id,
                "company_name": name,
                "name": name,
                "subscription_start": start_str,
                "subscription_end": end_str,
                "lead_managers": ["한국투자증권", "미래에셋증권"],
            }
        ]
    }


class IpoSubscriptionActionLinkIntegrationTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.tmp_dir = tempfile.TemporaryDirectory(prefix="wealth-sub-v2-")
        self.addCleanup(self.tmp_dir.cleanup)
        self.action_file = Path(self.tmp_dir.name) / "action_v2_state.json"
        self.public_origin = "https://wealth.example.com"

        # Isolate user directories so repository data/users/ is never touched
        self._tg_users = Path(self.tmp_dir.name) / "users"
        def _get_user_dir(u=None):
            p = self._tg_users / (u or "alice").strip()
            p.mkdir(parents=True, exist_ok=True)
            return p

        self.user_dir_patches = [
            patch("app.services.user_manager.get_user_data_dir", side_effect=_get_user_dir),
            patch("app.services.settings.get_user_data_dir", side_effect=_get_user_dir),
        ]
        for p in self.user_dir_patches:
            p.start()
            self.addCleanup(p.stop)

        self.env_patch = patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "mock-token",
                "TELEGRAM_CHAT_ID": "123456",
                "TELEGRAM_WEBHOOK_SECRET": "test-secret",
                "TELEGRAM_ALLOWED_USER_ID": "111",
                "TELEGRAM_ALLOWED_CHAT_ID": "222",
                "TELEGRAM_WEALTH_USERNAME": "alice",
                "DASHBOARD_SECRET_KEY": "test-secret-key-32-chars-long!!!!",
            },
            clear=False,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        self.settings_patch = patch(
            "app.services.system_settings.get_effective_system_settings",
            return_value={
                "public_base_url": self.public_origin,
                "telegram_webhook_owner": "alice",
            },
        )
        self.settings_patch.start()
        self.addCleanup(self.settings_patch.stop)

        self.action_v2_settings_patch = patch(
            "app.services.action_v2.get_effective_system_settings",
            return_value={
                "public_base_url": self.public_origin,
                "telegram_webhook_owner": "alice",
            },
        )
        self.action_v2_settings_patch.start()
        self.addCleanup(self.action_v2_settings_patch.stop)

        self.action_path_patch = patch(
            "app.services.action_v2.get_action_v2_file_path",
            return_value=self.action_file,
        )
        self.action_path_patch.start()
        self.addCleanup(self.action_path_patch.stop)

        self.action_v1_file = Path(self.tmp_dir.name) / "action_state.json"
        self.action_v1_patch = patch(
            "app.services.ipo.actions.ACTION_FILE",
            self.action_v1_file,
        )
        self.action_v1_patch.start()
        self.addCleanup(self.action_v1_patch.stop)

        self.market_store = _make_market_data()
        self.state_path = Path(self.tmp_dir.name) / "state.json"
        self.notifier = IpoTelegramNotifier(
            bot_token="mock-token",
            chat_id="123456",
            username="alice",
            state_path=self.state_path,
        )
        self.notifier.send_message = MagicMock(return_value=True)
        self.client = TestClient(app)

    def _login_session(self, username="alice", role="user"):
        token = _serializer.dumps({"user": username, "role": role})
        self.client.cookies.set(COOKIE_NAME, token)
        p = patch(
            "app.services.user_manager.get_user_by_name",
            return_value={"username": username, "id": f"id-{username}", "role": role},
        )
        p.start()
        self.addCleanup(p.stop)

    def test_progressive_completion_scenario(self):
        """09:00 (Dad, Mom, Child missing -> 3 web buttons) -> Dad Web Action applied -> 12:00 (Mom, Child -> 2 web buttons) -> Mom and Child applied -> 15:00 (all applied, no reminder)"""
        today = datetime.now(KST).date()
        apps = {
            "revision": 1,
            "family_members": ["아빠", "엄마", "자녀"],
            "applications": {
                "test-ipo-1": {
                    "target_owners": ["아빠", "엄마", "자녀"],
                    "applied_owners": [],
                }
            },
        }

        def fake_update(user, ipo_id, applied, rev):
            apps["applications"][ipo_id]["applied_owners"] = list(applied)
            apps["revision"] = rev + 1
            return {"revision": apps["revision"]}

        # 1. 09:00 Slot: all 3 missing
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.store.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.applications.get_user_applications", return_value=apps):
            res_0900 = run_ipo_subscription_reminders(
                username="alice",
                reminder_slot="0900",
                today=today,
                notifier=self.notifier,
                market_store=self.market_store,
                applications=apps,
            )
        self.assertEqual(res_0900["notifications_sent_count"], 1)
        self.assertEqual(res_0900["all_applied_count"], 0)

        call_args = self.notifier.send_message.call_args
        msg_0900 = call_args[0][0]
        markup_0900 = call_args[1]["reply_markup"]

        self.assertIn("아직 신청하지 않음:</b> 아빠, 엄마, 자녀", msg_0900)
        keyboard = markup_0900["inline_keyboard"]
        # Row 0: 3 legacy callback buttons
        # Row 1: Dad Web Action
        # Row 2: Mom Web Action
        # Row 3: Child Web Action
        self.assertEqual(len(keyboard), 4)
        self.assertEqual(len(keyboard[0]), 3)
        self.assertEqual(keyboard[0][0]["text"], "아빠 청약 완료")
        self.assertEqual(keyboard[0][1]["text"], "엄마 청약 완료")
        self.assertEqual(keyboard[0][2]["text"], "자녀 청약 완료")

        self.assertEqual(keyboard[1][0]["text"], "아빠 Wealth에서 확인")
        self.assertEqual(keyboard[2][0]["text"], "엄마 Wealth에서 확인")
        self.assertEqual(keyboard[3][0]["text"], "자녀 Wealth에서 확인")

        token_dad = keyboard[1][0]["url"].split("/a/")[1]
        token_mom = keyboard[2][0]["url"].split("/a/")[1]
        token_child = keyboard[3][0]["url"].split("/a/")[1]

        # 2. Alice logs in and executes action for Dad via Web Action POST
        self._login_session("alice")
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
            resp_dad = self.client.post(
                f"/a/{token_dad}/execute",
                headers={"Origin": self.public_origin},
            )
            self.assertEqual(resp_dad.status_code, 200)

        applied = apps["applications"]["test-ipo-1"]["applied_owners"]
        self.assertIn("아빠", applied)
        self.assertNotIn("엄마", applied)
        self.assertNotIn("자녀", applied)

        # 3. 12:00 Slot: Mom and Child missing
        self.notifier.send_message.reset_mock()
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.store.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.applications.get_user_applications", return_value=apps):
            res_1200 = run_ipo_subscription_reminders(
                username="alice",
                reminder_slot="1200",
                today=today,
                notifier=self.notifier,
                market_store=self.market_store,
                applications=apps,
            )
        self.assertEqual(res_1200["notifications_sent_count"], 1)
        self.assertEqual(res_1200["all_applied_count"], 0)

        msg_1200 = self.notifier.send_message.call_args[0][0]
        markup_1200 = self.notifier.send_message.call_args[1]["reply_markup"]
        self.assertIn("아직 신청하지 않음:</b> 엄마, 자녀", msg_1200)
        self.assertNotIn("아빠", msg_1200.split("아직 신청하지 않음")[1])

        keyboard_1200 = markup_1200["inline_keyboard"]
        # Row 0: 2 callbacks (Mom, Child)
        # Row 1: Mom Web Action
        # Row 2: Child Web Action
        # Dad Web button must NOT exist
        self.assertEqual(len(keyboard_1200), 3)
        self.assertEqual(len(keyboard_1200[0]), 2)
        self.assertEqual(keyboard_1200[0][0]["text"], "엄마 청약 완료")
        self.assertEqual(keyboard_1200[0][1]["text"], "자녀 청약 완료")
        self.assertEqual(keyboard_1200[1][0]["text"], "엄마 Wealth에서 확인")
        self.assertEqual(keyboard_1200[2][0]["text"], "자녀 Wealth에서 확인")
        all_1200_texts = [btn["text"] for row in keyboard_1200 for btn in row]
        self.assertFalse(any("아빠" in t for t in all_1200_texts))

        token_mom_1200 = keyboard_1200[1][0]["url"].split("/a/")[1]
        token_child_1200 = keyboard_1200[2][0]["url"].split("/a/")[1]

        # 4. Execute action for Mom and Child via Web Action POST (Web-only completion)
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
            resp_mom = self.client.post(f"/a/{token_mom_1200}/execute", headers={"Origin": self.public_origin})
            self.assertEqual(resp_mom.status_code, 200)
            resp_child = self.client.post(f"/a/{token_child_1200}/execute", headers={"Origin": self.public_origin})
            self.assertEqual(resp_child.status_code, 200)

        applied_all = apps["applications"]["test-ipo-1"]["applied_owners"]
        self.assertIn("아빠", applied_all)
        self.assertIn("엄마", applied_all)
        self.assertIn("자녀", applied_all)

        # 5. 15:00 Slot: all applied, no reminder should be sent!
        self.notifier.send_message.reset_mock()
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.store.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.applications.get_user_applications", return_value=apps):
            res_1500 = run_ipo_subscription_reminders(
                username="alice",
                reminder_slot="1500",
                today=today,
                notifier=self.notifier,
                market_store=self.market_store,
                applications=apps,
            )
        self.assertEqual(res_1500["notifications_sent_count"], 0)
        self.assertEqual(res_1500["all_applied_count"], 1)
        self.notifier.send_message.assert_not_called()

    def test_three_owner_url_binding_proof(self):
        """missing = ['아빠', '엄마', '자녀'] -> 3 distinct opaque URLs, correct owner metadata, landing & POST execution."""
        today = datetime.now(KST).date()
        apps = {
            "revision": 1,
            "family_members": ["아빠", "엄마", "자녀"],
            "applications": {
                "test-ipo-1": {
                    "target_owners": ["아빠", "엄마", "자녀"],
                    "applied_owners": [],
                }
            },
        }
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            run_ipo_subscription_reminders(
                username="alice",
                reminder_slot="0900",
                today=today,
                notifier=self.notifier,
                market_store=self.market_store,
                applications=apps,
            )

        markup = self.notifier.send_message.call_args[1]["reply_markup"]
        keyboard = markup["inline_keyboard"]
        self.assertEqual(len(keyboard), 4)

        url_dad = keyboard[1][0]["url"]
        url_mom = keyboard[2][0]["url"]
        url_child = keyboard[3][0]["url"]

        # 1. All 3 URLs are distinct
        self.assertEqual(len({url_dad, url_mom, url_child}), 3)

        # 2. URLs are completely opaque: no owner, username, or ipo_id plaintext
        for u in (url_dad, url_mom, url_child):
            for forbidden in ("alice", "아빠", "엄마", "자녀", "test-ipo-1", "알파로보틱스", "owner", "username"):
                self.assertNotIn(forbidden, u)

        token_dad = url_dad.split("/a/")[1]
        token_mom = url_mom.split("/a/")[1]
        token_child = url_child.split("/a/")[1]

        # 3. Metadata bound to correct owner
        meta_dad = get_web_action_metadata(token_dad)
        meta_mom = get_web_action_metadata(token_mom)
        meta_child = get_web_action_metadata(token_child)
        self.assertEqual(meta_dad["metadata"]["owner"], "아빠")
        self.assertEqual(meta_mom["metadata"]["owner"], "엄마")
        self.assertEqual(meta_child["metadata"]["owner"], "자녀")

        # 4. GET landing renders exact owner after login
        self._login_session("alice")
        with patch("app.services.ipo.store.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.applications.get_user_applications", return_value=apps):
            resp_dad = self.client.get(f"/a/{token_dad}")
            self.assertEqual(resp_dad.status_code, 200)
            self.assertIn("아빠", resp_dad.text)
            self.assertNotIn("엄마", resp_dad.text)
            self.assertNotIn("자녀", resp_dad.text)

            resp_mom = self.client.get(f"/a/{token_mom}")
            self.assertEqual(resp_mom.status_code, 200)
            self.assertIn("엄마", resp_mom.text)
            self.assertNotIn("아빠", resp_mom.text)
            self.assertNotIn("자녀", resp_mom.text)

            resp_child = self.client.get(f"/a/{token_child}")
            self.assertEqual(resp_child.status_code, 200)
            self.assertIn("자녀", resp_child.text)
            self.assertNotIn("아빠", resp_child.text)
            self.assertNotIn("엄마", resp_child.text)

        # 5. POST only marks that specific owner applied
        def fake_update(user, ipo_id, applied, rev):
            apps["applications"][ipo_id]["applied_owners"] = list(applied)
            apps["revision"] = rev + 1
            return {"revision": apps["revision"]}

        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps), \
             patch("app.services.ipo.actions.update_user_application", side_effect=fake_update):
            resp_post_dad = self.client.post(f"/a/{token_dad}/execute", headers={"Origin": self.public_origin})
            self.assertEqual(resp_post_dad.status_code, 200)
            # Only Dad should be in applied_owners
            self.assertEqual(apps["applications"]["test-ipo-1"]["applied_owners"], ["아빠"])

    def test_partial_action_creation_failure_resilience(self):
        """When creating action fails for one owner (e.g. Mom), Dad and Child web actions still succeed and legacy callbacks remain."""
        today = datetime.now(KST).date()
        apps = {
            "revision": 1,
            "family_members": ["아빠", "엄마", "자녀"],
            "applications": {
                "test-ipo-1": {
                    "target_owners": ["아빠", "엄마", "자녀"],
                    "applied_owners": [],
                }
            },
        }

        real_create_action = create_web_action

        def create_action_stub(**kwargs):
            meta = kwargs.get("metadata", {})
            if meta.get("owner") == "엄마":
                raise RuntimeError("Temporary DB lock for Mom")
            return real_create_action(**kwargs)

        with patch("app.services.action_v2.create_web_action", side_effect=create_action_stub), \
             patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            res = run_ipo_subscription_reminders(
                username="alice",
                reminder_slot="0900",
                today=today,
                notifier=self.notifier,
                market_store=self.market_store,
                applications=apps,
            )

        self.assertEqual(res["notifications_sent_count"], 1)
        markup = self.notifier.send_message.call_args[1]["reply_markup"]
        keyboard = markup["inline_keyboard"]

        # Row 0: all 3 legacy callbacks intact
        self.assertEqual(len(keyboard[0]), 3)
        self.assertEqual(keyboard[0][0]["text"], "아빠 청약 완료")
        self.assertEqual(keyboard[0][1]["text"], "엄마 청약 완료")
        self.assertEqual(keyboard[0][2]["text"], "자녀 청약 완료")

        # Rows 1 and 2: Dad and Child web actions (Mom skipped due to partial failure)
        self.assertEqual(len(keyboard), 3)
        self.assertEqual(keyboard[1][0]["text"], "아빠 Wealth에서 확인")
        self.assertEqual(keyboard[2][0]["text"], "자녀 Wealth에서 확인")
        web_texts = [keyboard[1][0]["text"], keyboard[2][0]["text"]]
        self.assertNotIn("엄마 Wealth에서 확인", web_texts)

    def test_missing_public_base_url_fallback(self):
        """If public_base_url is missing, web action is skipped gracefully without breaking reminder."""
        today = datetime.now(KST).date()
        apps = {
            "revision": 1,
            "family_members": ["아빠"],
            "applications": {
                "test-ipo-1": {
                    "target_owners": ["아빠"],
                    "applied_owners": [],
                }
            },
        }

        with patch("app.services.system_settings.get_effective_system_settings", return_value={"public_base_url": None, "telegram_webhook_owner": "alice"}), \
             patch("app.services.action_v2.get_effective_system_settings", return_value={"public_base_url": None, "telegram_webhook_owner": "alice"}), \
             patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            res = run_ipo_subscription_reminders(
                username="alice",
                reminder_slot="0900",
                today=today,
                notifier=self.notifier,
                market_store=self.market_store,
                applications=apps,
            )
        self.assertEqual(res["notifications_sent_count"], 1)
        markup = self.notifier.send_message.call_args[1]["reply_markup"]
        # Only row 0 (callbacks) present, no web action row
        self.assertEqual(len(markup["inline_keyboard"]), 1)
        self.assertEqual(markup["inline_keyboard"][0][0]["text"], "아빠 청약 완료")

    def test_stale_link_when_already_applied_externally(self):
        """If owner was marked applied externally, GET renders '청약 완료 상태' and POST returns already_applied."""
        today = datetime.now(KST).date()
        apps = {
            "revision": 1,
            "family_members": ["아빠"],
            "applications": {
                "test-ipo-1": {
                    "target_owners": ["아빠"],
                    "applied_owners": [],
                }
            },
        }
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            run_ipo_subscription_reminders(
                username="alice",
                reminder_slot="0900",
                today=today,
                notifier=self.notifier,
                market_store=self.market_store,
                applications=apps,
            )
        token = self.notifier.send_message.call_args[1]["reply_markup"]["inline_keyboard"][1][0]["url"].split("/a/")[1]

        # External application marks '아빠' applied
        apps["applications"]["test-ipo-1"]["applied_owners"] = ["아빠"]

        # User opens the link
        self._login_session("alice")
        with patch("app.services.ipo.store.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.applications.get_user_applications", return_value=apps):
            resp = self.client.get(f"/a/{token}")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("청약 완료 상태", resp.text)
            self.assertNotIn('<form method="post"', resp.text)

        # POST execute returns 200 already_applied
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            resp_post = self.client.post(
                f"/a/{token}/execute",
                headers={"Origin": self.public_origin},
            )
            self.assertEqual(resp_post.status_code, 200)
            self.assertIn("이미 처리 완료", resp_post.text)

    def test_cross_user_isolation(self):
        """Token generated for alice cannot be opened or executed by bob."""
        today = datetime.now(KST).date()
        apps = {
            "revision": 1,
            "family_members": ["아빠"],
            "applications": {
                "test-ipo-1": {
                    "target_owners": ["아빠"],
                    "applied_owners": [],
                }
            },
        }
        with patch("app.services.ipo.actions.read_market_store_read_only", return_value=self.market_store), \
             patch("app.services.ipo.actions.get_user_applications", return_value=apps):
            run_ipo_subscription_reminders(
                username="alice",
                reminder_slot="0900",
                today=today,
                notifier=self.notifier,
                market_store=self.market_store,
                applications=apps,
            )
        token = self.notifier.send_message.call_args[1]["reply_markup"]["inline_keyboard"][1][0]["url"].split("/a/")[1]

        # Bob logs in and tries to access Alice's token
        self._login_session("bob")
        resp_get = self.client.get(f"/a/{token}")
        self.assertEqual(resp_get.status_code, 403)
        self.assertIn("접근 권한 없음", resp_get.text)

        resp_post = self.client.post(
            f"/a/{token}/execute",
            headers={"Origin": self.public_origin},
        )
        self.assertEqual(resp_post.status_code, 403)
