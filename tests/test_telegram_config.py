import io,logging,os,unittest
from unittest.mock import patch
from app.services.telegram_config import resolve_telegram_config
class C(unittest.TestCase):
 def test_repr_hides_secrets_and_env_binding(self):
  env={'TELEGRAM_WEALTH_USERNAME':'user_a','TELEGRAM_BOT_TOKEN':'SUPER_TOKEN','TELEGRAM_WEBHOOK_SECRET':'SUPER_WEB','TELEGRAM_CHAT_ID':'-9','TELEGRAM_ALLOWED_USER_ID':'1','TELEGRAM_ALLOWED_CHAT_ID':'-2'}
  with patch.dict(os.environ,env,clear=False),patch('app.services.telegram_config.get_effective_settings',return_value={'telegram':{'enabled':False,'chat_id':None,'allowed_user_id':None,'allowed_chat_id':None}}),patch('app.services.telegram_config.load_stored_telegram_secrets',return_value={'bot_token':'','webhook_secret':''}):
   a=resolve_telegram_config('user_a');b=resolve_telegram_config('user_b');self.assertEqual(a.bot_token,'SUPER_TOKEN');self.assertEqual(a.bot_token_source,'environment');self.assertIsNone(b.bot_token);self.assertIsNone(b.chat_id);self.assertNotIn('SUPER_TOKEN',repr(a));self.assertNotIn('SUPER_WEB',str(a))
 def test_stored_wins(self):
  with patch.dict(os.environ,{'TELEGRAM_WEALTH_USERNAME':'a','TELEGRAM_BOT_TOKEN':'ENV','TELEGRAM_WEBHOOK_SECRET':'ENVW'},clear=False),patch('app.services.telegram_config.get_effective_settings',return_value={'telegram':{'enabled':True,'chat_id':1,'allowed_user_id':1,'allowed_chat_id':1}}),patch('app.services.telegram_config.load_stored_telegram_secrets',return_value={'bot_token':'STORED','webhook_secret':'STOREDW'}):
   c=resolve_telegram_config('a');self.assertEqual((c.bot_token,c.webhook_secret,c.bot_token_source,c.webhook_secret_source),('STORED','STOREDW','stored','stored'));self.assertTrue(c.outbound_configured);self.assertTrue(c.interactive_configured)
 def test_clear_falls_back_to_bound_env_or_none(self):
  from app.services.telegram_secrets import update_telegram_secrets
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'telegram.json';update_telegram_secrets('a',{'bot_token':'S','webhook_secret':'W'},path=p);update_telegram_secrets('a',{'clear_bot_token':True,'clear_webhook_secret':True},path=p)
   with patch.dict(os.environ,{'TELEGRAM_WEALTH_USERNAME':'a','TELEGRAM_BOT_TOKEN':'ENV','TELEGRAM_WEBHOOK_SECRET':'ENVW'},clear=False),patch('app.services.telegram_config.get_effective_settings',return_value={'telegram':{'enabled':True,'chat_id':1,'allowed_user_id':1,'allowed_chat_id':1}}),patch('app.services.telegram_config.load_stored_telegram_secrets',return_value={'bot_token':'','webhook_secret':''}):
    c=resolve_telegram_config('a');self.assertEqual((c.bot_token_source,c.webhook_secret_source),('environment','environment'))
   with patch.dict(os.environ,{'TELEGRAM_WEALTH_USERNAME':'a','TELEGRAM_BOT_TOKEN':'','TELEGRAM_WEBHOOK_SECRET':''},clear=False),patch('app.services.telegram_config.get_effective_settings',return_value={'telegram':{'enabled':True,'chat_id':1,'allowed_user_id':1,'allowed_chat_id':1}}),patch('app.services.telegram_config.load_stored_telegram_secrets',return_value={'bot_token':'','webhook_secret':''}):
    c=resolve_telegram_config('a');self.assertEqual((c.bot_token_source,c.webhook_secret_source),('none','none'));self.assertFalse(c.bot_token);self.assertFalse(c.webhook_secret)
 def test_notifier_transport_uses_resolved_stored_token(self):
  from app.services.ipo.notifier import IpoTelegramNotifier
  captured=[]
  class Response:
   status=200
   def __enter__(self):return self
   def __exit__(self,*_):return False
  def open_request(req,timeout=0):captured.append(req.full_url);return Response()
  settings={'telegram':{'enabled':True,'chat_id':123,'allowed_user_id':None,'allowed_chat_id':None}}
  with patch.dict(os.environ,{'TELEGRAM_WEALTH_USERNAME':'a','TELEGRAM_BOT_TOKEN':'ENV_TOKEN'},clear=False),patch('app.services.telegram_config.get_effective_settings',return_value=settings),patch('app.services.telegram_config.load_stored_telegram_secrets',return_value={'bot_token':'STORED_TOKEN','webhook_secret':''}),patch('app.services.ipo.notifier.request.urlopen',side_effect=open_request):
   self.assertTrue(IpoTelegramNotifier(username='a').send_message('safe'))
  self.assertIn('botSTORED_TOKEN',captured[0]);self.assertNotIn('ENV_TOKEN',captured[0])
 def test_env_only_transport_and_log_output_hide_secrets(self):
  from app.services.ipo.notifier import IpoTelegramNotifier
  captured=[];stream=io.StringIO();handler=logging.StreamHandler(stream);root=logging.getLogger();root.addHandler(handler)
  class Response:
   status=200
   def __enter__(self):return self
   def __exit__(self,*_):return False
  settings={'telegram':{'enabled':False,'chat_id':321,'allowed_user_id':None,'allowed_chat_id':None}}
  try:
   with patch.dict(os.environ,{'TELEGRAM_WEALTH_USERNAME':'a','TELEGRAM_BOT_TOKEN':'SUPER_ENV_TOKEN'},clear=False),patch('app.services.telegram_config.get_effective_settings',return_value=settings),patch('app.services.telegram_config.load_stored_telegram_secrets',return_value={'bot_token':'','webhook_secret':''}),patch('app.services.ipo.notifier.request.urlopen',side_effect=lambda req,timeout=0:(captured.append(req.full_url) or Response())):
    config=resolve_telegram_config('a');self.assertEqual(config.bot_token_source,'environment');self.assertTrue(IpoTelegramNotifier(username='a').send_message('safe'))
  finally:root.removeHandler(handler)
  self.assertIn('SUPER_ENV_TOKEN',captured[0]);self.assertNotIn('SUPER_ENV_TOKEN',stream.getvalue())
 def test_transport_exception_log_does_not_leak_token_url(self):
  from app.services.ipo.notifier import IpoTelegramNotifier
  stream=io.StringIO();handler=logging.StreamHandler(stream);logger=logging.getLogger('app.services.ipo.notifier');logger.addHandler(handler)
  try:
   with patch('app.services.ipo.notifier.request.urlopen',side_effect=RuntimeError('https://api.telegram.org/botSUPER_FAILURE_TOKEN/sendMessage')),patch('app.services.ipo.notifier.time.sleep'):
    self.assertFalse(IpoTelegramNotifier(bot_token='SUPER_FAILURE_TOKEN',chat_id='1').send_message('safe'))
  finally:logger.removeHandler(handler)
  self.assertNotIn('SUPER_FAILURE_TOKEN',stream.getvalue())
