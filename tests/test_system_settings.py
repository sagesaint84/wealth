import json,os,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from app.services import system_settings as s

class SystemSettingsTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'settings.json'
 def test_absent_read_no_create_and_env_fallback(self):
  with patch.dict(os.environ,{'WEALTH_PUBLIC_BASE_URL':'https://env.example.com/','TELEGRAM_WEALTH_USERNAME':'env-user'},clear=False):
   value=s.get_effective_system_settings(path=self.path);self.assertEqual(value['public_base_url'],'https://env.example.com');self.assertEqual(value['telegram_webhook_owner'],'env-user');self.assertFalse(self.path.exists())
 def test_stored_wins_and_persists(self):
  with patch.dict(os.environ,{'WEALTH_PUBLIC_BASE_URL':'https://env.example.com','TELEGRAM_WEALTH_USERNAME':'env-user'},clear=False):
   value=s.patch_system_settings({'public_base_url':'https://wealth.example.com/','telegram_webhook_owner':'alice'},path=self.path);self.assertEqual(value['public_base_url_source'],'stored');self.assertEqual(value['telegram_webhook_owner'],'alice');self.assertEqual(s.expected_webhook_url(value),'https://wealth.example.com/api/integrations/telegram/webhook')
 def test_url_validation_matrix(self):
  for good in ('https://wealth.example.com','https://wealth.example.com/','https://wealth.example.com:8443'):
   self.assertTrue(s.normalize_public_base_url(good).startswith('https://'))
  for bad in ('http://wealth.example.com','wealth.example.com','ftp://example.com','https://user:pass@example.com','https://example.com?x=1','https://example.com/#x','https://'):
   with self.assertRaises(s.SystemSettingsError):s.normalize_public_base_url(bad)
 def test_corrupt_future_unknown_and_atomic_failure_preserve(self):
  for value in ('{bad',json.dumps({'version':999,'public_base_url':None,'telegram_webhook_owner':None}),json.dumps({'version':1,'public_base_url':None,'telegram_webhook_owner':None,'bad':1})):
   self.path.write_text(value,encoding='utf-8')
   with self.assertRaises(s.SystemSettingsError):s.load_system_settings(path=self.path)
  self.path.unlink()
  s.patch_system_settings({'public_base_url':'https://old.example.com'},path=self.path);before=self.path.read_bytes()
  with patch('app.services.system_settings.os.replace',side_effect=OSError('fail')):
   with self.assertRaises(OSError):s.patch_system_settings({'public_base_url':'https://new.example.com'},path=self.path)
  self.assertEqual(self.path.read_bytes(),before);self.assertFalse(self.path.with_suffix('.tmp').exists())
 def test_owner_stored_env_and_none(self):
  with patch.dict(os.environ,{'TELEGRAM_WEALTH_USERNAME':'legacy'},clear=False):self.assertEqual(s.get_effective_system_settings(path=self.path)['telegram_webhook_owner'],'legacy')
  s.patch_system_settings({'telegram_webhook_owner':'stored'},path=self.path)
  with patch.dict(os.environ,{'TELEGRAM_WEALTH_USERNAME':'legacy'},clear=False):self.assertEqual(s.get_effective_system_settings(path=self.path)['telegram_webhook_owner'],'stored')
  self.path.unlink()
  with patch.dict(os.environ,{'TELEGRAM_WEALTH_USERNAME':''},clear=False):self.assertIsNone(s.get_effective_system_settings(path=self.path)['telegram_webhook_owner'])
 def test_concurrent_unrelated_patches_preserve_both(self):
  s.patch_system_settings({'public_base_url':'https://old.example.com','telegram_webhook_owner':'old'},path=self.path);barrier=threading.Barrier(2);errors=[]
  def run(value):
   try:barrier.wait();s.patch_system_settings(value,path=self.path)
   except Exception as exc:errors.append(exc)
  threads=[threading.Thread(target=run,args=({'public_base_url':'https://new.example.com'},)),threading.Thread(target=run,args=({'telegram_webhook_owner':'new'},))]
  [x.start() for x in threads];[x.join() for x in threads]
  self.assertFalse(errors);value=s.load_system_settings(path=self.path);self.assertEqual(value['public_base_url'],'https://new.example.com');self.assertEqual(value['telegram_webhook_owner'],'new')

 def test_automation_owner_precedence_and_clear(self):
  # 1. Stored > Env
  with patch.dict(os.environ, {'WEALTH_AUTOMATION_OWNER': 'env_user'}, clear=False):
   s.patch_system_settings({'automation_owner': 'admin'}, path=self.path, validate_user=False)
   eff = s.get_effective_system_settings(path=self.path)
   self.assertEqual(eff['automation_owner'], 'admin')
   self.assertEqual(eff['automation_owner_source'], 'stored')

  # 2. Env fallback when stored is None
  with patch.dict(os.environ, {'WEALTH_AUTOMATION_OWNER': 'env_user'}, clear=False):
   s.patch_system_settings({'automation_owner': None}, path=self.path, validate_user=False)
   eff = s.get_effective_system_settings(path=self.path)
   self.assertEqual(eff['automation_owner'], 'env_user')
   self.assertEqual(eff['automation_owner_source'], 'environment')

  # 3. None when both absent
  with patch.dict(os.environ, {'WEALTH_AUTOMATION_OWNER': ''}, clear=False):
   eff = s.get_effective_system_settings(path=self.path)
   self.assertIsNone(eff['automation_owner'])
   self.assertEqual(eff['automation_owner_source'], 'none')

 def test_automation_owner_validation_and_legacy_compatibility(self):
  # Path-like characters rejected
  for bad in ('../evil', '/root', 'a/b', 'a\\b', ' '):
   with self.assertRaises(s.SystemSettingsError):
    s.patch_system_settings({'automation_owner': bad}, path=self.path, validate_user=False)

  # Legacy schema without automation_owner is readable
  legacy_doc = {'version': 1, 'public_base_url': 'https://legacy.example.com', 'telegram_webhook_owner': 'alice'}
  self.path.write_text(json.dumps(legacy_doc), encoding='utf-8')
  loaded = s.load_system_settings(path=self.path)
  self.assertEqual(loaded['version'], 1)
  self.assertIsNone(loaded['automation_owner'])
  self.assertEqual(loaded['telegram_webhook_owner'], 'alice')

 def test_existing_v1_shapes_and_toss_settings_are_compatible(self):
  for document in (
   {'version':1,'public_base_url':None,'telegram_webhook_owner':None},
   {'version':1,'public_base_url':None,'telegram_webhook_owner':None,'automation_owner':'alice'},
  ):
   self.path.write_text(json.dumps(document),encoding='utf-8')
   self.assertIsNone(s.load_system_settings(path=self.path)['toss_wts'])
  allowed='123e4567-e89b-42d3-a456-426614174000'
  s.patch_system_settings({'toss_wts':{
   'enabled':True,'executable':str(Path(self.tmp.name)/'tossctl'),
   'config_dir':str(Path(self.tmp.name)/'config'),'expected_version':'v0.50.3',
   'timeout_seconds':25,'allowed_user_id':allowed}},path=self.path)
  value=s.resolve_toss_wts_settings(path=self.path)
  self.assertTrue(value['enabled'])
  self.assertEqual(value['allowed_user_id'],allowed)
  self.assertTrue(all(source=='stored' for source in value['sources'].values()))

 def test_toss_stored_precedence_legacy_fallback_and_defaults(self):
  env={
   'WEALTH_TOSS_WTS_ENABLED':'1','WEALTH_TOSSCTL_PATH':str(Path(self.tmp.name)/'env-tossctl'),
   'WEALTH_TOSSCTL_CONFIG_DIR':str(Path(self.tmp.name)/'env-config'),
   'WEALTH_TOSSCTL_EXPECTED_VERSION':'v9.9.9','WEALTH_TOSSCTL_TIMEOUT_SECONDS':'31',
   'WEALTH_TOSS_WTS_FEED_ALLOWED_USER_ID':'123e4567-e89b-42d3-a456-426614174001'}
  with patch.dict(os.environ,env,clear=False):
   fallback=s.resolve_toss_wts_settings(path=self.path)
   self.assertTrue(fallback['enabled']);self.assertEqual(fallback['expected_version'],'v9.9.9')
   self.assertEqual(fallback['sources']['enabled'],'environment')
   s.patch_system_settings({'toss_wts':{'enabled':False,'timeout_seconds':7}},path=self.path)
   stored=s.resolve_toss_wts_settings(path=self.path)
   self.assertFalse(stored['enabled']);self.assertEqual(stored['timeout_seconds'],7)
   self.assertEqual(stored['sources']['enabled'],'stored')
  self.path.unlink()
  names=list(env)
  clean=dict(os.environ)
  for name in names:clean.pop(name,None)
  with patch.dict(os.environ,clean,clear=True):
   defaults=s.resolve_toss_wts_settings(path=self.path)
   self.assertFalse(defaults['enabled'])
   self.assertEqual(defaults['executable'],'/opt/toss-wts/tossctl')
   self.assertEqual(defaults['config_dir'],'/opt/toss-wts/config')

 def test_toss_strict_validation(self):
  good={'enabled':False,'executable':str(Path(self.tmp.name)/'tossctl'),'config_dir':str(Path(self.tmp.name)/'config'),'expected_version':'v0.50.3','timeout_seconds':20,'allowed_user_id':None}
  for patch_value in (
   {**good,'enabled':'true'}, {**good,'timeout_seconds':0},
   {**good,'expected_version':'latest'}, {**good,'allowed_user_id':'not-a-user'},
   {**good,'unexpected':True},
  ):
   with self.assertRaises(s.SystemSettingsError):
    s.patch_system_settings({'toss_wts':patch_value},path=self.path)
