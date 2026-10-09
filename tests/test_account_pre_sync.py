"""Synthetic account pre-sync/close boundary and scheduler regressions."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from regression_support import IsolatedDataTestCase, empty_portfolio, authenticated_request, import_main_without_loading_real_env
from app.services.automation import account_pre_sync as pre
from app.services.automation.daily_close import run_daily_close_for_user
from app.services.automation.dispatcher import resolve_due_jobs, run_due_automation
from app.services.broker_holdings_sync import BrokerHoldingsResult, ProviderHoldingScope, ALL_MARKETS
from app.services.settings import default_settings
from app.services.kb_openapi import KBOpenAPI, KBOpenAPIError
from app.services.toss_openapi import TossOpenAPI, TossOpenAPIError
from app.services.nhplug_openapi import NhPlugOpenAPI, NhPlugOpenAPIError
from app.services.kis_openapi import KISOpenAPI, KISOpenAPIError
from app.services.kiwoom_openapi import KiwoomOpenAPI, KiwoomOpenAPIError

START = datetime(2026, 10, 9, 20, 50, tzinfo=pre.KST)
CLOSE = START + timedelta(minutes=10)


def run(coro):
    return asyncio.run(coro)


class AccountPreSyncTests(IsolatedDataTestCase):
    def setUp(self):
        super().setUp()
        self.main = import_main_without_loading_real_env()
        self.user = "synthetic_presync"
        self.enterContext(patch.dict("os.environ", {"WEALTH_DATA_DIR": str(self.fixture_root)}))
        self.enterContext(patch("app.services.automation.account_pre_sync.get_user_by_name", return_value={"username": self.user}))
        self.enterContext(patch("app.services.automation.daily_close.get_user_by_name", return_value={"username": self.user}))
        self.enterContext(patch.object(self.main, "is_test_mode", return_value=False))
        self.clients = {}
        specs = [
            ("kb", "KBOpenAPI", "kb_primary", []),
            ("toss", "TossOpenAPI", "7", [{"accountSeq": 7, "accountNo": "0000000007"}]),
            ("nh", "NhPlugOpenAPI", "00000000001", [{"acct_no": "00000000001", "acct_type": "01"}]),
            ("kis", "KISOpenAPI", "1234567801", [{"account_number": "1234567801", "account_name": "KIS"}]),
            ("kiwoom", "KiwoomOpenAPI", "1234567890", [{"account_number": "1234567890", "account_name": "Kiwoom"}]),
        ]
        for provider, name, key, accounts in specs:
            client = MagicMock(configured=True, last_accounts=accounts, account_cash={key: {"KRW": 0}})
            client._parse_account_no.return_value = ("12345678", "01")
            client._account_name.return_value = "Synthetic NH"
            client.refresh_prices = AsyncMock(return_value=({}, []))
            client.get_buying_power = AsyncMock(return_value={"KRW": 0})
            client.scope_key = key
            client.sync_holdings = AsyncMock(return_value=self.records(client))
            self.clients[provider] = client
            self.enterContext(patch.object(self.main, name, return_value=client))
        self.main.write_portfolio(empty_portfolio(), username=self.user)
        self.stock = self.enterContext(patch.object(self.main, "auto_save_all_owner_snapshots", wraps=self.main.auto_save_all_owner_snapshots))
        self.net = self.enterContext(patch.object(self.main, "save_all_owner_net_worth_snapshots", wraps=self.main.save_all_owner_net_worth_snapshots))
        self.price = self.enterContext(patch.object(self.main, "refresh_prices_for_user", new_callable=AsyncMock, return_value={"fx_rate": 1400}))
        self.enterContext(patch("app.services.web_finance.get_web_dividend_summary", new_callable=AsyncMock, return_value={"unavailable": True}))
        self.notify = self.enterContext(patch("app.services.automation.daily_close.send_daily_close_notifications", return_value={
            "telegram_sent": True, "status": "sent", "error": None, "dispatch_status": "sent",
            "notifications_sent_count": 3, "provider_results": {p: {"sent": True} for p in ("telegram", "discord", "kakao")}}))

    @staticmethod
    def records(client, nonempty=False):
        rows = [{"code": "005930", "name": "synthetic", "quantity": 2, "avg_price": 100,
                 "current_price": 120, "currency": "KRW", "market": "KR",
                 "account_key": client.scope_key, "account_number": client.scope_key}] if nonempty else []
        return BrokerHoldingsResult.authoritative_result(rows, [ProviderHoldingScope(client.scope_key, ALL_MARKETS)], cash_valid=True)

    def presync(self, at=START):
        return run(pre.run_account_pre_sync_for_user(self.user, now=at, clock=lambda: at))

    def close_without_accounts(self, at=CLOSE):
        # Guard every canonical account entry as well as all five provider fetches.
        guards = []
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name in ("sync_all_accounts_for_user", "sync_kb_for_user", "sync_toss_for_user",
                         "sync_namoo_for_user", "sync_kis_for_user", "sync_kiwoom_for_user"):
                guards.append(stack.enter_context(patch.object(self.main, name, new_callable=AsyncMock,
                                                              side_effect=AssertionError("close account API forbidden"))))
            for client in self.clients.values():
                client.sync_holdings.reset_mock()
                client.sync_holdings.side_effect = AssertionError("close provider fetch forbidden")
                client.get_buying_power.reset_mock()
                client.get_buying_power.side_effect = AssertionError("close cash fetch forbidden")
            result = run(run_daily_close_for_user(self.user, now=at))
        for guard in guards:
            guard.assert_not_awaited()
        for client in self.clients.values():
            client.sync_holdings.assert_not_awaited()
            client.get_buying_power.assert_not_awaited()
        self.assertTrue(result["ok"])
        self.stock.assert_called_once()
        self.net.assert_called_once()
        self.price.assert_awaited_once()
        self.notify.assert_called_once()
        return result

    def test_success_persists_and_close_has_zero_account_calls_and_one_snapshot(self):
        for client in self.clients.values():
            client.sync_holdings.return_value = self.records(client, True)
        result = self.presync()
        self.assertTrue(result["ok"])
        for client in self.clients.values():
            client.sync_holdings.assert_awaited_once()
        self.stock.assert_not_called()
        self.net.assert_not_called()
        self.price.assert_not_awaited()
        self.notify.assert_not_called()
        canonical = self.main.read_portfolio(username=self.user)
        self.assertEqual(len(canonical["holdings"]), 5)
        persisted = json.loads(pre.metadata_path(self.user).read_text(encoding="utf-8"))
        self.assertEqual(persisted["username"], self.user)
        self.assertEqual(persisted["status"], "COMPLETED")
        self.assertEqual(set(persisted["providers"]), set(self.clients))
        for item in persisted["providers"].values():
            self.assertEqual(item["status"], "SUCCESS")
            self.assertTrue(item["success"])
            self.assertFalse(item["authoritative_empty"])
            self.assertEqual(datetime.fromisoformat(item["completed_at"]), START)
        self.assertTrue(all(r["fresh"] for r in pre.read_pre_sync_for_close(self.user, now=CLOSE)["brokers"]))
        close = self.close_without_accounts()
        self.assertEqual(close["status"], "success")
        self.assertEqual(close["sync_warning_count"], 0)
        self.assertEqual(self.main.read_portfolio(username=self.user)["holdings"], canonical["holdings"])
        self.assertGreater(close["total_assets"], 0)
        self.assertEqual(close["notifications_sent_count"], 3)

    def test_authoritative_empty_is_fresh_and_not_an_error(self):
        self.presync()
        rows = pre.read_pre_sync_for_close(self.user, now=CLOSE)["brokers"]
        self.assertTrue(all(r["authoritative_empty"] and r["usable_for_close"] for r in rows))
        result = self.close_without_accounts()
        self.assertEqual(result["sync_warning_count"], 0)
        self.assertEqual([r["status"] for r in result["steps"]["account_sync"]["result"]["brokers"]], ["CONFIRMED_EMPTY"] * 5)

    def test_stale_success_preserves_canonical_data_and_never_refetches(self):
        for client in self.clients.values():
            client.sync_holdings.return_value = self.records(client, True)
        self.presync(START - timedelta(minutes=6))
        before = deepcopy(self.main.read_portfolio(username=self.user))
        result = self.close_without_accounts()
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["sync_warning_count"], 5)
        self.assertTrue(all(r["status"] == "PRE_SYNC_STALE" and not r["fresh"] for r in result["steps"]["account_sync"]["result"]["brokers"]))
        self.assertEqual(before["holdings"], self.main.read_portfolio(username=self.user)["holdings"])

    def test_missing_metadata_does_not_call_accounts(self):
        result = self.close_without_accounts()
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["sync_warning_count"], 5)
        self.assertTrue(all(r["status"] == "PRE_SYNC_MISSING" for r in result["steps"]["account_sync"]["result"]["brokers"]))

    def test_failed_transient_preserves_old_holdings_and_is_not_empty(self):
        for client in self.clients.values():
            client.sync_holdings.return_value = self.records(client, True)
        self.presync(START - timedelta(days=1))
        before = deepcopy(self.main.read_portfolio(username=self.user))
        for client in self.clients.values():
            client.sync_holdings.reset_mock()
            client.sync_holdings.side_effect = httpx.ConnectError("SECRET_TOKEN 123456789012")
        result = self.presync()
        for client in self.clients.values():
            self.assertEqual(client.sync_holdings.await_count, 2)
        self.assertEqual(before, self.main.read_portfolio(username=self.user))
        for item in result["providers"].values():
            self.assertEqual(item["status"], "API_ERROR")
            self.assertEqual(item["error_category"], "TRANSIENT_ERROR")
            self.assertFalse(item["authoritative_empty"])
        self.assertNotIn("SECRET_TOKEN", pre.metadata_path(self.user).read_text(encoding="utf-8"))
        self.assertNotIn("123456789012", str(result))
        close = self.close_without_accounts()
        self.assertEqual(close["sync_warning_count"], 5)

    def test_completion_clock_controls_freshness_across_utc_and_midnight(self):
        values = iter([START] + [START, START + timedelta(minutes=3)] * 5 + [START + timedelta(minutes=3)])
        run(pre.run_account_pre_sync_for_user(self.user, clock=lambda: next(values)))
        utc = (START + timedelta(minutes=18)).astimezone(timezone.utc)
        self.assertTrue(all(r["fresh"] for r in pre.read_pre_sync_for_close(self.user, now=utc)["brokers"]))
        self.assertFalse(any(r["fresh"] for r in pre.read_pre_sync_for_close(self.user, now=utc + timedelta(microseconds=1))["brokers"]))
        self.presync(START.replace(hour=23, minute=55))
        self.assertTrue(all(r["fresh"] for r in pre.read_pre_sync_for_close(self.user, now=START.replace(hour=23, minute=55) + timedelta(minutes=10))["brokers"]))
        with self.assertRaises(ValueError):
            pre.read_pre_sync_for_close(self.user, now=CLOSE.replace(tzinfo=None))

    def test_corrupt_running_wrong_user_and_future_metadata_fail_closed(self):
        self.presync()
        path = pre.metadata_path(self.user)
        original = json.loads(path.read_text(encoding="utf-8"))
        cases = ["{invalid", json.dumps({**original, "username": "another_user"}),
                 json.dumps({**original, "status": "RUNNING"})]
        for content in cases:
            path.write_text(content, encoding="utf-8")
            rows = pre.read_pre_sync_for_close(self.user, now=CLOSE)["brokers"]
            self.assertTrue(all(not r["usable_for_close"] and not r["authoritative_empty"] for r in rows))
        path.write_text(json.dumps(original), encoding="utf-8")
        self.assertTrue(all(not r["usable_for_close"] for r in pre.read_pre_sync_for_close(self.user, now=START - timedelta(seconds=1))["brokers"]))

    def test_metadata_persistence_failure_prevents_account_fetch(self):
        with patch.object(pre, "atomic_write_private_json", side_effect=OSError("SECRET")):
            with self.assertRaises(OSError):
                self.presync()
        for client in self.clients.values():
            client.sync_holdings.assert_not_awaited()

    def test_manual_endpoint_still_calls_each_provider_once(self):
        result = run(self.main.sync_all_accounts(authenticated_request(self.user)))
        self.assertEqual(result["synced"], 5)
        for client in self.clients.values():
            client.sync_holdings.assert_awaited_once()
        self.assertFalse(pre.metadata_path(self.user).exists())
        self.stock.assert_not_called()
        self.net.assert_not_called()

    def test_all_five_retry_transient_fetch_only_then_persist_once_each(self):
        for client in self.clients.values():
            client.sync_holdings.side_effect = [httpx.ReadTimeout("SECRET_TOKEN"), self.records(client)]
        with patch.object(self.main, "write_portfolio", wraps=self.main.write_portfolio) as save:
            result = self.presync()
        self.assertEqual(save.call_count, 5)
        for client in self.clients.values():
            self.assertEqual(client.sync_holdings.await_count, 2)
        for item in result["providers"].values():
            self.assertTrue(item["retry_attempted"])
            self.assertTrue(item["retry_recovered"])
        self.stock.assert_not_called()
        self.net.assert_not_called()
        self.assertEqual(self.close_without_accounts()["sync_warning_count"], 0)

    def test_http_allowlist_retries_all_providers_and_auth_parse_never_retry(self):
        provider_classes = {"kb": KBOpenAPI, "toss": TossOpenAPI, "nh": NhPlugOpenAPI,
                            "kis": KISOpenAPI, "kiwoom": KiwoomOpenAPI}
        for provider, cls in provider_classes.items():
            client = self.clients[provider]
            for code in (429, 500, 502, 503, 504, 400, 401, 403, 501):
                with self.subTest(provider=provider, http=code):
                    for c in self.clients.values():
                        c.configured = c is client
                    response = httpx.Response(code, request=httpx.Request("GET", "https://synthetic.invalid/account"), json={"secret": "SECRET_TOKEN"})
                    try:
                        cls._raise_for_response(response)
                    except Exception as error:
                        transient = code in (429, 500, 502, 503, 504)
                        client.sync_holdings.reset_mock()
                        client.sync_holdings.side_effect = [error, self.records(client)] if transient else [error]
                    with patch.object(self.main, "write_portfolio", wraps=self.main.write_portfolio) as save:
                        result = self.presync()
                    item = result["providers"][provider]
                    self.assertEqual(client.sync_holdings.await_count, 2 if transient else 1)
                    self.assertEqual(save.call_count, 1 if transient else 0)
                    self.assertEqual(item["status"], "CONFIRMED_EMPTY" if transient else "API_ERROR")
                    self.assertEqual(item["retry_attempted"], transient)
                    self.assertNotIn("SECRET_TOKEN", str(result))
                    if code in (401, 403):
                        self.assertEqual(item["error_category"], "CONFIG_ERROR")

    def test_parse_scope_config_and_persistence_never_retry_or_erase_old_data(self):
        errors = {"kb": KBOpenAPIError, "toss": TossOpenAPIError, "nh": NhPlugOpenAPIError,
                  "kis": KISOpenAPIError, "kiwoom": KiwoomOpenAPIError}
        for provider, client in self.clients.items():
            for kind in ("parse", "scope", "config", "persistence"):
                with self.subTest(provider=provider, kind=kind):
                    for c in self.clients.values():
                        c.configured = c is client
                    client.sync_holdings.reset_mock()
                    client.sync_holdings.side_effect = None
                    client.sync_holdings.return_value = self.records(client)
                    before = deepcopy(self.main.read_portfolio(username=self.user))
                    if kind == "parse":
                        client.sync_holdings.side_effect = errors[provider]("응답 형식이 올바르지 않습니다 SECRET_TOKEN")
                    elif kind == "scope":
                        client.sync_holdings.return_value = []
                    elif kind == "config":
                        client.configured = False
                    with patch.object(self.main, "write_portfolio", side_effect=OSError("SECRET_TOKEN")) as save:
                        result = self.presync()
                    item = result["providers"][provider]
                    expected = {"parse": "PARSE_ERROR", "scope": "SCOPE_UNVERIFIED",
                                "config": "CONFIG_REQUIRED", "persistence": "PERSISTENCE_ERROR"}[kind]
                    self.assertEqual(item["status"], expected)
                    self.assertFalse(item["authoritative_empty"])
                    self.assertFalse(item["retry_attempted"])
                    self.assertEqual(client.sync_holdings.await_count, 0 if kind == "config" else 1)
                    self.assertEqual(save.call_count, 1 if kind == "persistence" else 0)
                    self.assertEqual(before, self.main.read_portfolio(username=self.user))
                    self.assertNotIn("SECRET_TOKEN", str(result))

    def test_toss_cash_transient_read_is_retried_without_repeating_holdings_save(self):
        client = self.clients["toss"]
        error = TossOpenAPIError("SECRET_TOKEN")
        error.status_code = 503
        client.get_buying_power.side_effect = [error, {"KRW": 100}]
        with patch.object(self.main, "write_portfolio", wraps=self.main.write_portfolio) as save:
            result = self.presync()
        self.assertEqual(save.call_count, 5)
        self.assertEqual(client.get_buying_power.await_count, 2)
        client.sync_holdings.assert_awaited_once()
        self.assertTrue(result["providers"]["toss"]["retry_recovered"])

    def test_in_progress_metadata_is_published_before_canonical_sync(self):
        async def inspect_running():
            rows = pre.read_pre_sync_for_close(self.user, now=CLOSE)["brokers"]
            self.assertTrue(all(r["status"] == "PRE_SYNC_RUNNING" for r in rows))
            self.assertTrue(all(not r["usable_for_close"] for r in rows))
            return self.records(self.clients["kb"])
        self.clients["kb"].sync_holdings.side_effect = inspect_running
        self.assertTrue(self.presync()["ok"])

    def test_later_provider_completion_does_not_refresh_earlier_provider_timestamp(self):
        times = iter([START] + [START, START] + [START + timedelta(minutes=10)] * 9)
        run(pre.run_account_pre_sync_for_user(self.user, clock=lambda: next(times)))
        rows = pre.read_pre_sync_for_close(self.user, now=START + timedelta(minutes=20))["brokers"]
        self.assertEqual(rows[0]["status"], "PRE_SYNC_STALE")
        self.assertTrue(all(r["fresh"] for r in rows[1:]))

    def test_partial_toss_cash_keeps_old_balance_and_warns_without_refetch(self):
        client = self.clients["toss"]
        client.get_buying_power.return_value = {"KRW": 100}
        self.presync(START - timedelta(minutes=1))
        before = self.main.read_portfolio(username=self.user)
        error = TossOpenAPIError("SECRET_TOKEN")
        error.status_code = 503
        client.get_buying_power.side_effect = error
        self.presync()
        after = self.main.read_portfolio(username=self.user)
        self.assertEqual(before["settings"]["cash_balances"], after["settings"]["cash_balances"])
        result = self.close_without_accounts()
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["sync_warning_count"], 1)
        self.assertIn("⚠️ 토스증권: PARTIAL_SUCCESS", result["summary"])
        self.assertNotIn("SECRET_TOKEN", str(result))

    def test_metadata_save_failure_after_canonical_write_invalidates_run(self):
        writer = pre.atomic_write_private_json
        calls = 0
        def fail_one_save(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("SECRET_TOKEN")
            return writer(*args, **kwargs)
        with patch.object(pre, "atomic_write_private_json", side_effect=fail_one_save):
            result = self.presync()
        self.assertFalse(result["ok"])
        self.clients["kb"].sync_holdings.assert_awaited_once()
        for provider, client in self.clients.items():
            if provider != "kb":
                client.sync_holdings.assert_not_awaited()
        persisted = json.loads(pre.metadata_path(self.user).read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "FAILED")
        self.assertEqual(persisted["error_category"], "PERSISTENCE_ERROR")
        self.assertNotIn("SECRET_TOKEN", str(persisted))
        self.stock.assert_not_called()
        self.net.assert_not_called()
        self.assertEqual(self.close_without_accounts()["sync_warning_count"], 5)

    def test_running_presync_rejects_concurrent_run_without_duplicate_reads(self):
        async def during_fetch():
            competing = await pre.run_account_pre_sync_for_user(self.user, clock=lambda: START)
            self.assertFalse(competing["ok"])
            self.assertEqual(competing["error"], "ACCOUNT_PRE_SYNC_ALREADY_RUNNING")
            return self.records(self.clients["kb"])
        self.clients["kb"].sync_holdings.side_effect = during_fetch
        self.assertTrue(self.presync()["ok"])
        for client in self.clients.values():
            client.sync_holdings.assert_awaited_once()

    def test_close_utc_midnight_uses_seoul_date_and_zero_account_calls(self):
        at = START.replace(hour=23, minute=55)
        self.presync(at)
        result = self.close_without_accounts((at + timedelta(minutes=10)).astimezone(timezone.utc))
        self.assertEqual(result["date"], "2026-10-10")
        self.assertEqual(result["status"], "success")

    def test_corrupt_success_flags_and_naive_timestamps_are_never_authoritative(self):
        self.presync()
        path = pre.metadata_path(self.user)
        original = json.loads(path.read_text(encoding="utf-8"))
        for key, value in (("status", "API_ERROR"), ("success", "true"),
                           ("authoritative_empty", False), ("completed_at", "2026-10-09T20:50:00"),
                           ("error_category", "SECRET_TOKEN"), ("failure_reason", "SECRET_TOKEN"),
                           ("failure_reason", ["SECRET_TOKEN"])):
            with self.subTest(field=key):
                corrupted = deepcopy(original)
                corrupted["providers"]["kb"][key] = value
                path.write_text(json.dumps(corrupted), encoding="utf-8")
                row = pre.read_pre_sync_for_close(self.user, now=CLOSE)["brokers"][0]
                self.assertEqual(row["status"], "PRE_SYNC_INVALID")
                self.assertFalse(row["usable_for_close"])
                self.assertFalse(row["authoritative_empty"])
                self.assertNotIn("SECRET_TOKEN", str(row))

    def test_stale_configuration_is_not_treated_as_a_current_disabled_connection(self):
        for client in self.clients.values():
            client.configured = False
        self.presync(START - timedelta(days=1))
        result = self.close_without_accounts()
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["sync_warning_count"], 5)
        self.assertTrue(all(r["status"] == "PRE_SYNC_STALE" for r in result["steps"]["account_sync"]["result"]["brokers"]))


class PreSyncSchedulerTests(IsolatedDataTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.fixture_root / "execution.json"
        self.cfg = default_settings()
        self.enterContext(patch("app.services.automation.dispatcher.list_users", return_value=[{"username": "alice"}]))
        self.enterContext(patch("app.services.automation.dispatcher.get_effective_settings", return_value=self.cfg))
        self.enterContext(patch("app.services.automation.dispatcher.resolve_global_automation_owner", return_value="alice"))

    def test_2050_and_2100_are_separate_user_jobs_and_restart_deduplicates(self):
        for at, name in ((START, "account_pre_sync"), (CLOSE, "daily_close")):
            jobs = resolve_due_jobs(now=at.astimezone(timezone.utc), state_path=self.state)
            self.assertEqual([j["job"] for j in jobs], [name])
            self.assertEqual(jobs[0]["scope"], "user")
            self.assertEqual(jobs[0]["username"], "alice")
            self.assertIn(at.strftime("%H%M"), jobs[0]["execution_key"])
        runner = AsyncMock(return_value={"ok": True, "completed_at": START.isoformat(), "providers": {}})
        run(run_due_automation(now=START, state_path=self.state, account_pre_sync_runner=runner))
        run(run_due_automation(now=START, state_path=self.state, account_pre_sync_runner=runner))
        runner.assert_awaited_once()

    def test_configuration_disable_and_midnight_derivation(self):
        self.cfg["automation"]["daily_close"]["time"] = "00:05"
        jobs = resolve_due_jobs(now=START.replace(hour=23, minute=55), state_path=self.state)
        self.assertEqual([j["job"] for j in jobs], ["account_pre_sync"])
        self.cfg["automation"]["daily_close"]["enabled"] = False
        self.assertFalse(resolve_due_jobs(now=START.replace(hour=23, minute=55), state_path=self.state))

    def test_failed_presync_is_never_replayed_at_close_or_catchup(self):
        runner = AsyncMock(side_effect=RuntimeError("SECRET_TOKEN"))
        run(run_due_automation(now=START, state_path=self.state, account_pre_sync_runner=runner))
        runner.assert_awaited_once()
        # Inject the retry descriptor too, independent of reliability backoff/test policy.
        retry = {"key": "user:alice:account_pre_sync:2026-10-09:2050", "scope": "user",
                 "job": "account_pre_sync", "username": "alice", "scheduled_time": "20:50"}
        with patch("app.services.automation.dispatcher.get_retryable_executions", return_value=[retry]):
            for at in (CLOSE, CLOSE + timedelta(minutes=5)):
                jobs = resolve_due_jobs(now=at, state_path=self.state)
                self.assertFalse(any(j["job"] == "account_pre_sync" for j in jobs))
        self.assertNotIn("SECRET_TOKEN", self.state.read_text(encoding="utf-8"))
