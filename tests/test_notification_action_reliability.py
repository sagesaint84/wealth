"""Synthetic regression coverage for native/web IPO confirmation and KB account read retries."""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.ipo import actions
from app.services.action_v2 import create_web_action, execute_web_action, _load_v2
from app.services.ipo.telegram_interactive import handle_update
from app.services.notifications.models import NotificationSendResult
from app.services.notifications.service import UserNotificationService
from app.services.kb_openapi import KBOpenAPI, KBOpenAPIError, KBTransientAPIError
from app.services.broker_holdings_sync import BrokerHoldingsResult, ProviderHoldingScope, ALL_MARKETS
from regression_support import empty_portfolio, import_main_without_loading_real_env


class Sender:
    def __init__(self, provider, *, fail=False):
        self.provider_name, self.fail, self.events = provider, fail, []

    def is_configured(self):
        return True

    def send(self, event, **kwargs):
        self.events.append(event)
        if self.fail:
            raise RuntimeError("SECRET_TOKEN account=123456789012")
        return NotificationSendResult(success=True, provider=self.provider_name)


class IpoConfirmationTests(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        def user_dir(username=None):
            path = self.root / "users" / (username or "alice")
            path.mkdir(parents=True, exist_ok=True)
            return path
        stack.enter_context(patch("app.services.settings.get_user_data_dir", side_effect=user_dir))
        stack.enter_context(patch("app.services.user_manager.get_user_data_dir", side_effect=user_dir))
        self.path = self.root / "actions.json"
        self.apps_path = self.root / "applications.json"
        self.apps = {"revision": 0, "family_members": ["엄마"],
                     "applications": {"ipo1": {"applied_owners": [], "target_owners": ["엄마"]}}}
        self.market = {"ipos": [{"ipo_id": "ipo1", "company_name": "엘리스그룹",
                                "subscription_start": "2026-01-01", "subscription_end": "2099-12-31"}]}
        self.apps_path.write_text(json.dumps(self.apps), encoding="utf-8")
        stack.enter_context(patch.object(actions, "ACTION_FILE", self.path))
        stack.enter_context(patch.object(actions, "read_market_store_read_only", return_value=self.market))
        stack.enter_context(patch.object(actions, "get_user_applications", return_value=self.apps))
        self.update = stack.enter_context(patch.object(actions, "update_user_application", side_effect=self._update))
        self.telegram, self.discord = Sender("telegram"), Sender("discord")
        service = UserNotificationService("alice", sender_overrides={"telegram": self.telegram, "discord": self.discord},
                                          enabled_overrides={"telegram": True, "discord": True, "kakao": False})
        stack.enter_context(patch("app.services.ipo.application_confirmation.read_market_store_read_only", return_value=self.market))
        self.service_factory = stack.enter_context(patch("app.services.ipo.application_confirmation.UserNotificationService", return_value=service))
        stack.enter_context(patch("app.services.notifications.history.record_notification_history"))
        stack.enter_context(patch("app.services.ipo.telegram_interactive.interactive_config", return_value=("secret", 111, 222, "alice")))
        self.ack = stack.enter_context(patch("app.services.ipo.telegram_interactive.IpoTelegramNotifier"))

    def _update(self, username, ipo_id, applied, revision):
        self.assertEqual(username, "alice")
        self.assertEqual(revision, self.apps["revision"])
        self.apps["applications"][ipo_id]["applied_owners"] = applied
        self.apps["revision"] += 1
        self.apps_path.write_text(json.dumps(self.apps), encoding="utf-8")
        return {"revision": self.apps["revision"]}

    def create(self):
        return actions.create_mark_applied_action("alice", "ipo1", "엄마", "telegram")

    def callback(self, aid):
        return {"callback_query": {"id": "q1", "from": {"id": 111},
                "message": {"chat": {"id": 222}}, "data": "ipoa:" + aid}}

    def test_real_default_path_consumes_after_canonical_mutation(self):
        action = self.create()  # Intentionally no explicit path.
        result = actions.execute_action(action["action_id"])  # Intentionally no explicit path.
        self.assertEqual(result["status"], "applied")
        self.assertEqual(json.loads(self.apps_path.read_text(encoding="utf-8"))["applications"]["ipo1"]["applied_owners"], ["엄마"])
        self.assertTrue(json.loads(self.path.read_text(encoding="utf-8"))["actions"][action["action_id"]]["consumed_at"])
        self.assertEqual(actions.execute_action(action["action_id"])["status"], "already_processed")
        self.update.assert_called_once()

    def test_native_callback_dispatches_enabled_providers_only_once(self):
        aid = self.create()["action_id"]
        self.assertEqual(handle_update(self.callback(aid), "secret"), "applied")
        answer = self.ack.return_value.answer_callback_query.call_args.args[1]
        self.assertIn("✅ 청약 완료로 기록했습니다.", answer)
        self.assertTrue(actions.get_action_metadata(aid)["consumed_at"])
        self.assertEqual(handle_update(self.callback(aid), "secret"), "already_applied")
        # A different native action and a web action for the same owner cannot re-notify.
        actions.execute_action(self.create()["action_id"])
        web = create_web_action(username="alice", action_type="MARK_IPO_APPLIED",
                                metadata={"ipo_id": "ipo1", "owner": "엄마"}, path=self.root / "v2.json")
        self.assertEqual(execute_web_action(web["raw_token"], authenticated_username="alice", path=self.root / "v2.json")["status"], "already_applied")
        for sender in (self.telegram, self.discord):
            self.assertEqual(len(sender.events), 1)
            event = sender.events[0]
            self.assertEqual(event.username, "alice")
            self.assertIn("엘리스그룹", event.body)
            self.assertIn("신청자: 엄마", event.body)
            self.assertTrue(event.event_key.startswith("ipo_application_confirmed:"))
        self.assertEqual(self.telegram.events[0].event_key, self.discord.events[0].event_key)

    def test_web_action_confirmation_and_consumption(self):
        path = self.root / "v2.json"
        web = create_web_action(username="alice", action_type="MARK_IPO_APPLIED",
                                metadata={"ipo_id": "ipo1", "owner": "엄마"}, path=path)
        result = execute_web_action(web["raw_token"], authenticated_username="alice", path=path)
        self.assertEqual(result["notification"]["status"], "sent")
        self.assertTrue(_load_v2(path)["actions"][web["token_digest"]]["consumed_at"])
        execute_web_action(web["raw_token"], authenticated_username="alice", path=path)
        self.assertEqual(len(self.discord.events), 1)

    def test_notification_failure_preserves_application_and_consumption(self):
        self.telegram.fail = self.discord.fail = True
        aid = self.create()["action_id"]
        result = actions.execute_action(aid)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["notification"]["status"], "failed")
        self.assertNotIn("SECRET_TOKEN", str(result))
        self.assertEqual(self.apps["applications"]["ipo1"]["applied_owners"], ["엄마"])
        self.assertTrue(actions.get_action_metadata(aid)["consumed_at"])
        actions.execute_action(aid)
        self.assertEqual(len(self.telegram.events), 1)

    def test_native_failed_confirmation_still_answers_application_success(self):
        self.telegram.fail = self.discord.fail = True
        aid = self.create()["action_id"]
        self.assertEqual(handle_update(self.callback(aid), "secret"), "applied")
        answer = self.ack.return_value.answer_callback_query.call_args.args[1]
        self.assertIn("✅ 청약 완료로 기록했습니다.", answer)
        self.assertIn("확인 알림", answer)
        self.assertNotIn("SECRET_TOKEN", answer)
        self.assertTrue(actions.get_action_metadata(aid)["consumed_at"])
        self.assertEqual(self.apps["applications"]["ipo1"]["applied_owners"], ["엄마"])

    def test_web_failed_confirmation_retains_success_and_does_not_resend(self):
        self.telegram.fail = self.discord.fail = True
        path = self.root / "v2.json"
        web = create_web_action(username="alice", action_type="MARK_IPO_APPLIED",
                                metadata={"ipo_id": "ipo1", "owner": "엄마"}, path=path)
        result = execute_web_action(web["raw_token"], authenticated_username="alice", path=path)
        self.assertEqual(result["status"], "applied")
        self.assertEqual(result["notification"]["status"], "failed")
        self.assertTrue(_load_v2(path)["actions"][web["token_digest"]]["consumed_at"])
        self.assertEqual(execute_web_action(web["raw_token"], authenticated_username="alice", path=path)["status"], "already_processed")
        self.assertEqual(len(self.discord.events), 1)

    def test_persistence_failure_is_not_swallowed_or_notified(self):
        aid = self.create()["action_id"]
        with patch.object(actions, "_save", side_effect=OSError("save failed")):
            with self.assertRaises(OSError):
                actions.execute_action(aid)
        self.assertIsNone(actions.get_action_metadata(aid)["consumed_at"])
        self.assertFalse(self.telegram.events)

    def test_safe_callback_errors_do_not_mutate_or_notify(self):
        aid = self.create()["action_id"]
        for code, text in [("ACTION_EXPIRED", "만료"), ("OWNER_NOT_ELIGIBLE", "대상"),
                           ("SUBSCRIPTION_NOT_ACTIVE", "청약 기간"), ("IPO_ACTION_ALREADY_RUNNING", "처리 중")]:
            with self.subTest(code=code), patch("app.services.ipo.telegram_interactive.execute_action", side_effect=actions.IpoActionError(code)):
                self.assertEqual(handle_update(self.callback(aid), "secret"), code)
                self.assertIn(text, self.ack.return_value.answer_callback_query.call_args.args[1])
        self.assertEqual(handle_update(self.callback("missing"), "secret"), "ACTION_NOT_FOUND")
        with actions.action_state_lock(self.path):
            self.assertEqual(handle_update(self.callback(aid), "secret"), "IPO_ACTION_ALREADY_RUNNING")
        self.assertFalse(self.telegram.events)
        self.update.assert_not_called()
        self.assertIsNone(actions.get_action_metadata(aid)["consumed_at"])

    def test_expired_ineligible_and_corrupt_native_actions_fail_closed(self):
        aid = self.create()["action_id"]
        self.assertEqual(handle_update(self.callback(aid), "wrong secret"), "unauthorized")
        with patch.object(actions, "_is_expired", return_value=True):
            self.assertEqual(handle_update(self.callback(aid), "secret"), "ACTION_EXPIRED")
        self.apps["applications"]["ipo1"]["target_owners"] = ["다른 신청자"]
        self.assertEqual(handle_update(self.callback(aid), "secret"), "OWNER_NOT_ELIGIBLE")
        self.assertIsNone(actions.get_action_metadata(aid)["consumed_at"])
        self.path.write_text("{invalid", encoding="utf-8")
        self.assertEqual(handle_update(self.callback(aid), "secret"), "ACTION_FAILED")
        self.assertFalse(self.telegram.events)
        self.update.assert_not_called()


class KbPreSyncRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.main = import_main_without_loading_real_env()
        stack = self.enterContext(ExitStack())
        self.client = MagicMock(configured=True)
        self.client.refresh_prices = AsyncMock(return_value=({}, []))
        stack.enter_context(patch.object(self.main, "KBOpenAPI", return_value=self.client))
        for name in ("TossOpenAPI", "NhPlugOpenAPI", "KISOpenAPI", "KiwoomOpenAPI"):
            stack.enter_context(patch.object(self.main, name, return_value=MagicMock(configured=False)))
        stack.enter_context(patch.object(self.main, "is_test_mode", return_value=False))
        self.before = empty_portfolio()
        self.read = stack.enter_context(patch.object(self.main, "read_portfolio", side_effect=lambda **kw: deepcopy(self.before)))
        self.write = stack.enter_context(patch.object(self.main, "write_portfolio"))
        self.sleep = stack.enter_context(patch.object(self.main.asyncio, "sleep", new_callable=AsyncMock))

    def records(self, nonempty=False):
        rows = [{"code": "005930", "name": "synthetic", "quantity": 1, "avg_price": 100,
                 "current_price": 100, "currency": "KRW", "market": "KR"}] if nonempty else []
        return BrokerHoldingsResult.authoritative_result(rows, [ProviderHoldingScope("kb_primary", ALL_MARKETS)], cash_valid=False)

    async def sync(self, effects, *, automatic=True):
        self.client.sync_holdings = AsyncMock(side_effect=effects)
        result = await self.main.sync_all_accounts_for_user("fixture", retry_kb_transient=automatic)
        return result, result["brokers"][0]

    async def test_retry_recovers_authoritative_empty_and_success(self):
        for nonempty, status in [(False, "CONFIRMED_EMPTY"), (True, "SUCCESS")]:
            with self.subTest(status=status):
                self.write.reset_mock()
                result, kb = await self.sync([KBTransientAPIError(503), self.records(nonempty)])
                self.assertEqual(kb["status"], status)
                self.assertTrue(kb["retry_attempted"])
                self.assertTrue(kb["retry_recovered"])
                self.assertFalse(result["errors"])
                self.write.assert_called_once()
                self.assertEqual(self.client.sync_holdings.await_count, 2)
                self.assertTrue(all(b["status"] == "CONFIG_REQUIRED" for b in result["brokers"][1:]))

    async def test_second_failure_preserves_data_and_safe_diagnostic(self):
        result, kb = await self.sync([KBTransientAPIError(503), httpx.ConnectError("SECRET_TOKEN 123456789012")])
        self.assertEqual(kb["status"], "API_ERROR")
        self.assertTrue(kb["retry_attempted"])
        self.assertFalse(kb["retry_recovered"])
        self.assertEqual(kb["failure_reason"], "KB_TRANSPORT_ERROR")
        self.assertTrue(kb["data_preserved"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertNotIn("SECRET_TOKEN", str(result))
        self.assertNotIn("123456789012", str(result))
        self.read.assert_not_called()
        self.write.assert_not_called()
        self.sleep.assert_awaited_once_with(0.1)

    async def test_nontransient_parse_validation_and_manual_failures_never_retry(self):
        for error, status, automatic in [(KBOpenAPIError("응답 형식 오류"), "PARSE_ERROR", True),
                                         (KBOpenAPIError("provider validation failure"), "API_ERROR", True),
                                         (KBTransientAPIError(503), "API_ERROR", False)]:
            with self.subTest(error=error, automatic=automatic):
                _, kb = await self.sync([error], automatic=automatic)
                self.assertEqual(kb["status"], status)
                self.client.sync_holdings.assert_awaited_once()
                self.assertNotIn("retry_attempted", kb)
        self.sleep.assert_not_awaited()
        self.write.assert_not_called()

    async def test_transport_configuration_and_malformed_response_are_not_retried(self):
        for error in (httpx.UnsupportedProtocol("unsupported URL SECRET_TOKEN"),
                      httpx.LocalProtocolError("invalid headers SECRET_TOKEN"),
                      httpx.RemoteProtocolError("malformed response SECRET_TOKEN"),
                      ValueError("malformed body SECRET_TOKEN")):
            with self.subTest(error=type(error)):
                _, kb = await self.sync([error])
                self.client.sync_holdings.assert_awaited_once()
                self.assertNotIn("retry_attempted", kb)
                self.assertNotIn("SECRET_TOKEN", str(kb))
        self.sleep.assert_not_awaited()
        self.write.assert_not_called()

    async def test_other_successful_broker_is_not_retried(self):
        toss = AsyncMock(return_value={"broker": "토스증권", "status": "SUCCESS", "message": "synthetic", "count": 1})
        with patch.object(self.main, "TossOpenAPI", return_value=MagicMock(configured=True)), patch.object(self.main, "sync_toss_for_user", toss):
            result, kb = await self.sync([KBTransientAPIError(503), self.records()])
        self.assertEqual(result["brokers"][1]["status"], "SUCCESS")
        toss.assert_awaited_once_with(username="fixture")
        self.assertTrue(kb["retry_recovered"])

    async def test_config_and_unverified_never_retry(self):
        self.client.configured = False
        _, kb = await self.sync([])
        self.assertEqual(kb["status"], "CONFIG_REQUIRED")
        self.client.sync_holdings.assert_not_awaited()
        self.client.configured = True
        _, kb = await self.sync([[]])
        self.assertEqual(kb["status"], "SCOPE_UNVERIFIED")
        self.client.sync_holdings.assert_awaited_once()
        self.write.assert_not_called()

    async def test_persistence_failure_never_retries_holdings(self):
        self.write.side_effect = OSError("SECRET_TOKEN 123456789012")
        _, kb = await self.sync([self.records()])
        self.assertEqual(kb["status"], "PERSISTENCE_ERROR")
        self.client.sync_holdings.assert_awaited_once()
        self.assertEqual(kb["message"], "KB_SYNC_FAILED 기존 데이터는 유지했습니다.")
        self.sleep.assert_not_awaited()

    async def test_presync_then_close_preserve_step_sequence(self):
        from app.services.automation.daily_close import run_daily_close_for_user
        from app.services.automation.account_pre_sync import run_account_pre_sync_for_user
        from tests.test_daily_close import DailyCloseServiceTests
        dashboard = DailyCloseServiceTests._sample_dashboard(self)
        for final, status, warnings in [(self.records(), "CONFIRMED_EMPTY", 0),
                                         (self.records(True), "SUCCESS", 0),
                                         (KBTransientAPIError(503), "API_ERROR", 1)]:
            with self.subTest(status=status), ExitStack() as stack:
                self.write.reset_mock()
                self.client.sync_holdings = AsyncMock(side_effect=[KBTransientAPIError(503), final])
                stack.enter_context(patch("app.services.automation.daily_close.get_user_by_name", return_value={"username": "fixture"}))
                price = stack.enter_context(patch.object(self.main, "refresh_prices_for_user", new_callable=AsyncMock, return_value={"fx_rate": 1400}))
                dash = stack.enter_context(patch.object(self.main, "get_full_dashboard_for_user", return_value=dashboard))
                stock = stack.enter_context(patch.object(self.main, "auto_save_all_owner_snapshots", return_value=[{"owner": "모두", "total_value": 100}]))
                net = stack.enter_context(patch.object(self.main, "save_all_owner_net_worth_snapshots", return_value=({}, [{"owner": "모두", "net_worth": 100}])))
                stack.enter_context(patch("app.services.asset_records.list_asset_records", return_value=[]))
                stack.enter_context(patch("app.services.web_finance.get_web_dividend_summary", new_callable=AsyncMock, return_value={"unavailable": True}))
                notify = stack.enter_context(patch("app.services.automation.daily_close.send_daily_close_notifications", return_value={
                    "telegram_sent": True, "status": "sent", "dispatch_status": "sent", "error": None,
                    "provider_results": {}, "notifications_sent_count": 1}))
                root = stack.enter_context(tempfile.TemporaryDirectory(prefix="wealth-presync-"))
                stack.enter_context(patch.dict("os.environ", {"WEALTH_DATA_DIR": root}))
                stack.enter_context(patch("app.services.automation.account_pre_sync.get_user_by_name", return_value={"username": "fixture"}))
                pre = await run_account_pre_sync_for_user("fixture", clock=lambda: datetime(2026, 10, 8, 20, 50, tzinfo=actions.KST))
                self.assertTrue(pre["ok"])
                stock.assert_not_called()
                net.assert_not_called()
                notify.assert_not_called()
                self.assertEqual(self.client.sync_holdings.await_count, 2)
                self.client.sync_holdings.reset_mock()
                self.client.sync_holdings.side_effect = AssertionError("21:00 account fetch forbidden")
                result = await run_daily_close_for_user("fixture", now=datetime(2026, 10, 8, 21, tzinfo=actions.KST))
                self.client.sync_holdings.assert_not_awaited()
                self.assertTrue(result["ok"])
                self.assertEqual(result["sync_warning_count"], warnings)
                kb = result["steps"]["account_sync"]["result"]["brokers"][0]
                self.assertEqual(kb["status"], status)
                self.assertTrue(kb["retry_attempted"])
                price.assert_awaited_once()
                dash.assert_called_once_with(username="fixture", record_snapshots=False)
                stock.assert_called_once()
                net.assert_called_once()
                notify.assert_called_once()
                self.assertEqual(self.write.call_count, 0 if warnings else 1)

    def test_only_allowlisted_http_failures_are_transient(self):
        for status in (429, 500, 502, 503, 504):
            with self.assertRaises(KBTransientAPIError):
                KBOpenAPI._raise_for_response(httpx.Response(status, json={"secret": "SECRET_TOKEN"}))
        for status in (400, 401, 403, 501):
            with self.assertRaises(KBOpenAPIError) as exc:
                KBOpenAPI._raise_for_response(httpx.Response(status, json={"error": "validation"}))
            self.assertNotIsInstance(exc.exception, KBTransientAPIError)
