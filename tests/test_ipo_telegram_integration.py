"""Endpoint-level Telegram IPO regression coverage; all transport is mocked."""
from __future__ import annotations
import json, os, tempfile, unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.services.ipo import actions
from app.services.ipo.notifier import IpoTelegramNotifier
from app.services.ipo.reminders import run_ipo_subscription_reminders
from app.services.ipo.telegram_interactive import handle_update, interactive_config

ENV={"TELEGRAM_WEBHOOK_SECRET":"test-secret","TELEGRAM_ALLOWED_USER_ID":"111","TELEGRAM_ALLOWED_CHAT_ID":"222","TELEGRAM_WEALTH_USERNAME":"alice"}
def callback(a="opaqueAction_123"):
    return {"callback_query":{"id":"callback-1","from":{"id":111},"message":{"chat":{"id":222}},"data":f"ipoa:{a}"}}

class _IsolatedTelegramTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._tg_tmp = tempfile.TemporaryDirectory(prefix="wealth-tg-iso-")
        self.addCleanup(self._tg_tmp.cleanup)
        self._tg_users = Path(self._tg_tmp.name) / "users"
        def _get_user_dir(u=None):
            p = self._tg_users / (u or "alice").strip()
            p.mkdir(parents=True, exist_ok=True)
            return p
        self._user_dir_patches = [
            patch("app.services.user_manager.get_user_data_dir", side_effect=_get_user_dir),
            patch("app.services.settings.get_user_data_dir", side_effect=_get_user_dir),
        ]
        for p in self._user_dir_patches:
            p.start()
            self.addCleanup(p.stop)

class TelegramEndpointTests(_IsolatedTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.p=patch.dict(os.environ,ENV,clear=False); self.p.start(); self.addCleanup(self.p.stop); self.client=TestClient(app)
        self.portfolio={"revision":7,"applications":{"ipo-1":{"applied_owners":[]}},"account_id":"acct","broker_id":"broker","allocation":{"links":[]},"pnl_records":[{"id":"pnl"}],"MoneyLog":[{"id":"log"}]}
        self.action={"action_id":"opaqueAction_123","username":"alice","ipo_id":"ipo-1","owner":"아빠","action_type":"MARK_IPO_APPLIED","source_channel":"telegram"}
    def post(self, body, secret="test-secret"):
        return self.client.post("/api/integrations/telegram/webhook",json=body,headers={"X-Telegram-Bot-Api-Secret-Token":secret})
    def execute(self, action_id):
        self.assertEqual(action_id,self.action["action_id"]); self.portfolio["applications"]["ipo-1"]["applied_owners"].append("아빠"); self.portfolio["revision"]+=1; self.action["consumed_at"]="2026-09-20T00:00:00+00:00"; return {"status":"applied"}
    def test_callback_endpoint_applies_consumes_and_acknowledges_once(self):
        with patch("app.services.ipo.telegram_interactive.get_action_metadata",return_value=self.action), patch("app.services.ipo.telegram_interactive.execute_action",side_effect=self.execute) as run, patch.object(IpoTelegramNotifier,"answer_callback_query",return_value=True) as ack:
            response=self.post(callback())
        self.assertEqual(response.status_code,200); self.assertEqual(self.portfolio["applications"]["ipo-1"]["applied_owners"],["아빠"]); self.assertIn("consumed_at",self.action); run.assert_called_once_with("opaqueAction_123"); ack.assert_called_once(); self.assertEqual(ack.call_args.args[0],"callback-1"); self.assertTrue(ack.call_args.args[1])
    def test_duplicate_delivery_does_not_bump_revision_twice(self):
        calls=[]
        def run(_):
            calls.append(1)
            if len(calls)==1: return self.execute("opaqueAction_123")
            return {"status":"already_processed"}
        with patch("app.services.ipo.telegram_interactive.get_action_metadata",return_value=self.action), patch("app.services.ipo.telegram_interactive.execute_action",side_effect=run), patch.object(IpoTelegramNotifier,"answer_callback_query",return_value=True) as ack:
            self.assertEqual(self.post(callback()).status_code,200); rev=self.portfolio["revision"]; self.assertEqual(self.post(callback()).status_code,200)
        self.assertEqual(self.portfolio["revision"],rev); self.assertEqual(len(calls),2); self.assertEqual(ack.call_count,2)
    def test_ack_failure_does_not_roll_back_executed_action(self):
        with patch("app.services.ipo.telegram_interactive.get_action_metadata",return_value=self.action), patch("app.services.ipo.telegram_interactive.execute_action",side_effect=self.execute), patch.object(IpoTelegramNotifier,"answer_callback_query",side_effect=OSError("network")):
            with self.assertRaises(OSError): self.post(callback())
        self.assertEqual(self.portfolio["applications"]["ipo-1"]["applied_owners"],["아빠"]); self.assertIn("consumed_at",self.action)
    def test_rejections_never_execute_or_touch_accounting(self):
        cases=[(callback(),"wrong",403),({"callback_query":{"id":"q","from":{"id":9},"message":{"chat":{"id":222}},"data":"ipoa:x"}},"test-secret",403),({"callback_query":{"id":"q","from":{"id":111},"message":{"chat":{"id":9}},"data":"ipoa:x"}},"test-secret",403),({"callback_query":{"from":{"id":111},"message":{"chat":{"id":222}},"data":"ipoa:x"}},"test-secret",403),({"callback_query":{"id":"q","message":{"chat":{"id":222}},"data":"ipoa:x"}},"test-secret",403),({"callback_query":{"id":"q","from":{"id":111},"data":"ipoa:x"}},"test-secret",403),({"callback_query":{"id":"q","from":{"id":111},"message":{},"data":"ipoa:x"}},"test-secret",403),({"callback_query":{"id":"q","from":{"id":111},"message":{"chat":{}},"data":"ipoa:x"}},"test-secret",403),({"callback_query":{"id":"q","from":{"id":111},"message":{"chat":{"id":222}},"data":"bad:x"}},"test-secret",200)]
        before=json.dumps(self.portfolio,sort_keys=True)
        with patch("app.services.ipo.telegram_interactive.execute_action") as run,patch.object(IpoTelegramNotifier,"answer_callback_query") as ack:
            for body,secret,status in cases:self.assertEqual(self.post(body,secret).status_code,status)
        run.assert_not_called(); ack.assert_not_called(); self.assertEqual(json.dumps(self.portfolio,sort_keys=True),before)
    def test_unknown_expired_and_wealth_user_mismatch_are_safe(self):
        before=json.dumps(self.portfolio,sort_keys=True)
        with patch("app.services.ipo.telegram_interactive.get_action_metadata",return_value=None),patch("app.services.ipo.telegram_interactive.execute_action") as run:self.assertEqual(self.post(callback()).status_code,403);run.assert_not_called()
        with patch("app.services.ipo.telegram_interactive.get_action_metadata",return_value=dict(self.action,username="bob")),patch("app.services.ipo.telegram_interactive.execute_action") as run:self.assertEqual(self.post(callback()).status_code,403);run.assert_not_called()
        with patch("app.services.ipo.telegram_interactive.get_action_metadata",return_value=self.action),patch("app.services.ipo.telegram_interactive.execute_action",side_effect=actions.IpoActionError("ACTION_EXPIRED")):self.assertEqual(self.post(callback()).status_code,200)
        self.assertEqual(json.dumps(self.portfolio,sort_keys=True),before)
    def test_missing_and_malformed_config_disables_endpoint(self):
        for key,value in [("TELEGRAM_WEBHOOK_SECRET",""),("TELEGRAM_ALLOWED_USER_ID",""),("TELEGRAM_ALLOWED_CHAT_ID",""),("TELEGRAM_WEALTH_USERNAME",""),("TELEGRAM_ALLOWED_USER_ID","bad"),("TELEGRAM_ALLOWED_CHAT_ID","bad")]:
            with patch.dict(os.environ,{key:value}):self.assertIsNone(interactive_config());self.assertEqual(self.post(callback()).status_code,503)
    def test_stored_webhook_secret_overrides_environment_at_endpoint(self):
        from app.services.telegram_config import TelegramConfig
        cfg=TelegramConfig('alice',True,'token',222,'STORED_SECRET',111,222,'stored','stored')
        body={"message":{"from":{"id":111},"chat":{"id":222},"text":"ignored text"}}
        with patch("app.services.telegram_config.resolve_telegram_config",return_value=cfg):
            self.assertEqual(self.post(body,"STORED_SECRET").status_code,200)
            self.assertEqual(self.post(body,"test-secret").status_code,403)

class TelegramFreeTextTests(_IsolatedTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.p=patch.dict(os.environ,ENV,clear=False);self.p.start();self.addCleanup(self.p.stop)
    def update(self,text,user=111,chat=222):return {"message":{"from":{"id":user},"chat":{"id":chat},"text":text}}
    def test_one_match_is_scoped_to_alice(self):
        apps={"applications":{"a":{"target_owners":["아빠"],"applied_owners":[]}}}; mark=MagicMock(return_value={"status":"applied"})
        with patch("app.services.ipo.telegram_interactive.get_user_applications",return_value=apps),patch("app.services.ipo.telegram_interactive.read_market_store_read_only",return_value={"ipos":[{"ipo_id":"a"}]}),patch("app.services.ipo.telegram_interactive.mark_ipo_owner_applied",mark):self.assertEqual(handle_update(self.update("아빠 청약 완료"),"test-secret"),"applied")
        mark.assert_called_once();self.assertEqual(mark.call_args.args[:3],("alice","a","아빠"))
    def test_ambiguous_zero_already_parser_and_auth_have_no_write(self):
        market={"ipos":[{"ipo_id":"a"},{"ipo_id":"b"}]}; mark=MagicMock()
        scenarios=[({"applications":{"a":{"target_owners":["아빠"],"applied_owners":[]},"b":{"target_owners":["아빠"],"applied_owners":[]}}},"ambiguous"),({"applications":{"a":{"target_owners":["엄마"],"applied_owners":[]}}},"none_pending"),({"applications":{"a":{"target_owners":["아빠"],"applied_owners":["아빠"]}}},"none_pending")]
        for apps,expected in scenarios:
            with patch("app.services.ipo.telegram_interactive.get_user_applications",return_value=apps),patch("app.services.ipo.telegram_interactive.read_market_store_read_only",return_value=market),patch("app.services.ipo.telegram_interactive.mark_ipo_owner_applied",mark):self.assertEqual(handle_update(self.update("아빠 청약 완료"),"test-secret"),expected)
        for text in ("아빠 청약","아빠 완료","청약 완료","아빠 청약 완료해줘","아빠 청약 완료?"):self.assertEqual(handle_update(self.update(text),"test-secret"),"ignored")
        self.assertEqual(handle_update(self.update("아빠 청약 완료",9),"test-secret"),"unauthorized");self.assertEqual(handle_update(self.update("아빠 청약 완료",chat=9),"test-secret"),"unauthorized");mark.assert_not_called()

class TelegramReminderAndMetadataTests(_IsolatedTelegramTestCase):
    def setUp(self):
        super().setUp()
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=patch.dict(os.environ,ENV,clear=False);self.p.start();self.addCleanup(self.p.stop)
        self.notifier=IpoTelegramNotifier(bot_token="x",chat_id="y",state_path=Path(self.tmp.name)/"state.json");self.market={"ipos":[{"ipo_id":"ipo","company_name":"회사","subscription_start":"2026-09-20","subscription_end":"2026-09-21","lead_managers":["증권사"]}]};self.apps={"family_members":["아빠","엄마"],"applications":{"ipo":{"applied_owners":[]}}}
    def test_buttons_are_opaque_bounded_and_scoped(self):
        made=[];self.notifier.send_message=MagicMock(return_value=True)
        def create(username,ipo,owner,source,today):made.append((username,ipo,owner,source));return {"action_id":f"opaque_{len(made)}"}
        with patch("app.services.ipo.actions.create_mark_applied_action",side_effect=create):run_ipo_subscription_reminders(username="alice",reminder_slot="0900",today=date(2026,9,20),notifier=self.notifier,market_store=self.market,applications=self.apps)
        buttons=self.notifier.send_message.call_args.kwargs["reply_markup"]["inline_keyboard"][0];self.assertEqual(len(buttons),2);self.assertEqual([x[0] for x in made],["alice","alice"]);self.assertTrue(all(x[3]=="telegram" for x in made))
        for b in buttons:
            data=b["callback_data"];self.assertTrue(data.startswith("ipoa:"));self.assertGreaterEqual(len(data.encode()),1);self.assertLessEqual(len(data.encode()),64);self.assertTrue(all(x not in data for x in ("아빠","엄마","username","회사","account","broker")))
    def test_plain_compatibility_and_failed_send_has_no_sent_key(self):
        self.notifier.send_message=MagicMock(return_value=True)
        with patch.dict(os.environ,{key:"" for key in ENV}):run_ipo_subscription_reminders(username="alice",reminder_slot="0900",today=date(2026,9,20),notifier=self.notifier,market_store=self.market,applications=self.apps)
        self.assertIsNone(self.notifier.send_message.call_args.kwargs["reply_markup"]);self.notifier=IpoTelegramNotifier(bot_token="x",chat_id="y",state_path=Path(self.tmp.name)/"failed.json");self.notifier.send_message=MagicMock(return_value=False)
        run_ipo_subscription_reminders(username="alice",reminder_slot="1200",today=date(2026,9,20),notifier=self.notifier,market_store=self.market,applications=self.apps);self.assertFalse(self.notifier.state_path.exists())
    def test_metadata_is_read_only_unknown_safe_and_malformed_closed(self):
        path=Path(self.tmp.name)/"actions.json";path.write_text(json.dumps({"actions":{"ok":{"action_id":"ok","username":"alice"}}}),encoding="utf-8");self.assertEqual(actions.get_action_metadata("ok",path=path)["username"],"alice");self.assertIsNone(actions.get_action_metadata("unknown",path=path));path.write_text("{bad",encoding="utf-8")
        with self.assertRaises(actions.IpoActionError):actions.get_action_metadata("ok",path=path)
