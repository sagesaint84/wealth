from __future__ import annotations
import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from app.services import settings
from fastapi.testclient import TestClient
from app.main import app
import app.main as main

class SettingsTests(unittest.TestCase):
 def setUp(self): self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/"settings.json"
 def get(self,user="alice"): return settings.get_effective_settings(user,path=self.path)
 def test_absent_defaults_do_not_create_file(self): self.assertEqual(self.get()["automation"]["daily_close"]["time"],"21:00");self.assertFalse(self.path.exists())
 def test_patch_persists_and_deep_merges(self):
  settings.patch_settings("alice",{"automation":{"daily_close":{"time":"20:30"}}},path=self.path);self.assertTrue(self.path.exists());self.assertEqual(self.get()["automation"]["daily_close"]["time"],"20:30");self.assertEqual(self.get()["automation"]["ipo_refresh_morning"]["time"],"07:30")
 def test_times_validate_sort_and_unknowns_fail_closed(self):
  settings.patch_settings("alice",{"automation":{"ipo_reminders":{"times":["15:00","09:00","12:00"]}}},path=self.path);self.assertEqual(self.get()["automation"]["ipo_reminders"]["times"],["09:00","12:00","15:00"])
  for bad in ("9:00","24:00","12:60","0900","abc"):
   with self.assertRaises(settings.SettingsValidationError):settings.patch_settings("alice",{"automation":{"daily_close":{"time":bad}}},path=self.path)
  for bad in ([],["09:00","09:00"],["abc"]):
   with self.assertRaises(settings.SettingsValidationError):settings.patch_settings("alice",{"automation":{"ipo_reminders":{"times":bad}}},path=self.path)
  with self.assertRaises(settings.SettingsValidationError):settings.patch_settings("alice",{"telegram":{"bot_token":"secret"}},path=self.path)
 def test_legacy_automation_gets_listing_reminder_defaults_without_losing_subscription_times(self):
  legacy=settings.default_settings();legacy["automation"].pop("ipo_listing_reminders");legacy["automation"]["ipo_reminders"]["times"]=["10:00"]
  self.path.write_text(json.dumps(legacy),encoding="utf-8")
  effective=self.get();self.assertEqual(effective["automation"]["ipo_reminders"]["times"],["10:00"]);self.assertEqual(effective["automation"]["ipo_listing_reminders"],{"enabled":True,"times":["08:50","14:50"]})
  settings.patch_settings("alice",{"automation":{"ipo_listing_reminders":{"enabled":False,"times":["14:50"]}}},path=self.path)
  self.assertEqual(self.get()["automation"]["ipo_listing_reminders"],{"enabled":False,"times":["14:50"]})
  for bad in ([],["08:50","08:50"],["bad"]):
   with self.assertRaises(settings.SettingsValidationError):settings.patch_settings("alice",{"automation":{"ipo_listing_reminders":{"times":bad}}},path=self.path)
 def test_env_binding_precedence_and_secret_exclusion(self):
  env={"TELEGRAM_WEALTH_USERNAME":"alice","TELEGRAM_CHAT_ID":"-123","TELEGRAM_ALLOWED_USER_ID":"7","TELEGRAM_BOT_TOKEN":"raw-token","TELEGRAM_WEBHOOK_SECRET":"raw-secret"}
  with patch.dict(os.environ,env,clear=False):
   value=self.get();self.assertEqual(value["telegram"]["chat_id"],-123);self.assertTrue(value["telegram"]["bot_token_configured"]);self.assertNotIn("raw-token",json.dumps(value));self.assertIsNone(self.get("bob")["telegram"]["chat_id"])
   settings.patch_settings("alice",{"telegram":{"chat_id":99}},path=self.path);self.assertEqual(self.get()["telegram"]["chat_id"],99)
 def test_corruption_future_and_atomic_failure_preserve(self):
  self.path.write_text("{bad",encoding="utf-8")
  with self.assertRaises(settings.SettingsError):self.get()
  self.path.write_text(json.dumps({"version":999}),encoding="utf-8")
  with self.assertRaises(settings.SettingsError):self.get()
  good=settings.default_settings();settings._save(good,self.path);before=self.path.read_bytes();good["telegram"]["chat_id"]=float("nan")
  with self.assertRaises(ValueError):settings._save(good,self.path)
  self.assertEqual(self.path.read_bytes(),before);self.assertFalse(self.path.with_suffix(".tmp").exists())

class SettingsApiTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.client=TestClient(app)
  self.user=patch("app.services.user_manager.get_user_by_name",return_value={"username":"alice","id":"a","role":"user"});self.user.start();self.addCleanup(self.user.stop)
  self.client.cookies.set(main.COOKIE_NAME,main._serializer.dumps({"user":"alice"}))
  self.dir=patch("app.services.settings.get_user_data_dir",return_value=Path(self.tmp.name));self.dir.start();self.addCleanup(self.dir.stop)
 def test_authenticated_get_patch_and_secret_rejection(self):
  self.assertEqual(self.client.get("/api/settings/automation").status_code,200)
  response=self.client.patch("/api/settings/automation",json={"daily_close":{"time":"20:30"}});self.assertEqual(response.status_code,200);self.assertEqual(response.json()["automation"]["daily_close"]["time"],"20:30")
  self.assertEqual(self.client.patch("/api/settings/notifications",json={"bot_token":"nope"}).status_code,400)
  self.assertFalse((Path(self.tmp.name)/"settings.json").read_text(encoding="utf-8").find("nope")>=0)
 def test_unauthenticated_is_existing_401(self):
  self.client.cookies.clear();self.assertEqual(self.client.get("/api/settings/automation").status_code,401)
 def test_api_byte_isolation_and_raw_secret_absence(self):
  from app.services.settings import _save,default_settings
  from app.services.telegram_secrets import update_telegram_secrets
  settings_path=Path(self.tmp.name)/"settings.json";secret_path=Path(self.tmp.name)/"secrets"/"telegram.json"
  _save(default_settings(),settings_path);update_telegram_secrets("alice",{"bot_token":"SUPER_SECRET_BOT_TOKEN_FINAL_D2","webhook_secret":"SUPER_SECRET_WEBHOOK_SECRET_FINAL_D2"},path=secret_path)
  secret_before=secret_path.read_bytes()
  for url,payload in (("/api/settings/automation",{"daily_close":{"time":"20:31"}}),("/api/settings/notifications",{"enabled":True})):
   response=self.client.patch(url,json=payload);self.assertEqual(response.status_code,200);self.assertEqual(secret_path.read_bytes(),secret_before)
  settings_before=settings_path.read_bytes();response=self.client.patch("/api/settings/telegram/secrets",json={"bot_token":"SUPER_SECRET_BOT_TOKEN_FINAL_D2","webhook_secret":"SUPER_SECRET_WEBHOOK_SECRET_FINAL_D2"});self.assertEqual(response.status_code,200);self.assertEqual(settings_path.read_bytes(),settings_before)
  bodies=[response.text,self.client.get("/api/settings/notifications").text,self.client.get("/api/settings/automation").text,self.client.patch("/api/settings/telegram/secrets",json={"bad":"SUPER_SECRET_BOT_TOKEN_FINAL_D2"}).text]
  self.assertTrue(all("SUPER_SECRET_" not in body for body in bodies))
