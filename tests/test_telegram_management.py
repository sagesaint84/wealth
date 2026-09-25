import io,json,tempfile,unittest
from pathlib import Path
from urllib.parse import parse_qs
from unittest.mock import patch
from app.services.telegram_config import TelegramConfig
from app.services import telegram_management as m
from fastapi.testclient import TestClient
from app.main import app,_serializer,COOKIE_NAME

class Response:
 def __init__(self,value):self.value=value
 def __enter__(self):return self
 def __exit__(self,*_):return False
 def read(self):return json.dumps(self.value).encode()

class TelegramManagementTests(unittest.TestCase):
 def cfg(self,**changes):
  values=dict(username='alice',enabled=True,bot_token='SUPER_TOKEN',chat_id=222,webhook_secret='Safe_secret-1',allowed_user_id=111,allowed_chat_id=222,bot_token_source='stored',webhook_secret_source='stored');values.update(changes);return TelegramConfig(**values)
 def opener(self,result,calls):
  def run(req,timeout=0):calls.append((req.full_url,parse_qs(req.data.decode()),timeout));return Response({'ok':True,'result':result})
  return run
 def test_get_me_safe_normalized(self):
  calls=[];result=m.check_bot(self.cfg(),opener=self.opener({'id':7,'username':'wealth_bot','first_name':'Wealth','extra':'hidden'},calls));self.assertEqual(result['username'],'wealth_bot');self.assertNotIn('extra',result);self.assertIn('/getMe',calls[0][0]);self.assertNotIn('SUPER_TOKEN',json.dumps(result))
 def test_test_message_contract(self):
  calls=[];result=m.send_test_message(self.cfg(),opener=self.opener({'message_id':1},calls));self.assertTrue(result['ok']);self.assertEqual(calls[0][1]['chat_id'],['222']);self.assertEqual(calls[0][1]['text'],[m.TEST_MESSAGE])
 def test_webhook_info_normalization(self):
  calls=[];expected='https://wealth.example.com/api/integrations/telegram/webhook';value=m.webhook_info(self.cfg(),expected,opener=self.opener({'url':expected,'pending_update_count':3,'last_error_message':'SUPER_TOKEN Safe_secret-1'},calls));self.assertTrue(value['matches_expected']);self.assertEqual(value['pending_update_count'],3);self.assertNotIn('SUPER_TOKEN',json.dumps(value));self.assertNotIn('Safe_secret-1',json.dumps(value))
 def test_connect_and_disconnect_payloads(self):
  calls=[];url='https://wealth.example.com/api/integrations/telegram/webhook';m.connect_webhook(self.cfg(),url,opener=self.opener(True,calls));payload=calls[0][1];self.assertEqual(payload['url'],[url]);self.assertEqual(payload['secret_token'],['Safe_secret-1']);self.assertEqual(json.loads(payload['allowed_updates'][0]),['message','callback_query']);self.assertEqual(payload['drop_pending_updates'],['false'])
  m.disconnect_webhook(self.cfg(),opener=self.opener(True,calls));self.assertEqual(calls[1][1]['drop_pending_updates'],['false'])
 def test_secret_token_constraints(self):
  for bad in ('space bad','x'*257,'한글'):
   with self.assertRaisesRegex(m.TelegramManagementError,'TELEGRAM_WEBHOOK_SECRET_INVALID'):m.connect_webhook(self.cfg(webhook_secret=bad),'https://wealth.example.com/x',opener=self.opener(True,[]))
 def test_api_failures_are_normalized_without_secret(self):
  def explode(*_args,**_kwargs):raise OSError('https://api.telegram.org/botSUPER_TOKEN/getMe')
  with self.assertRaises(m.TelegramManagementError) as ctx:m.check_bot(self.cfg(),opener=explode)
  self.assertEqual(str(ctx.exception),'TELEGRAM_API_UNAVAILABLE');self.assertNotIn('SUPER_TOKEN',str(ctx.exception))
  with self.assertRaisesRegex(m.TelegramManagementError,'TELEGRAM_BOT_AUTH_FAILED'):m.check_bot(self.cfg(),opener=lambda *_a,**_k:Response({'ok':False,'error_code':401,'description':'Unauthorized'}))
  class BadResponse(Response):
   def read(self):return b'{bad'
  with self.assertRaisesRegex(m.TelegramManagementError,'TELEGRAM_API_UNAVAILABLE'):m.check_bot(self.cfg(),opener=lambda *_a,**_k:BadResponse({}))
 def test_stored_owner_drives_no_env_webhook_target(self):
  with patch('app.services.system_settings.get_effective_system_settings',return_value={'telegram_webhook_owner':'alice'}),patch.dict('os.environ',{'TELEGRAM_WEALTH_USERNAME':''},clear=False):
   from app.services.telegram_config import telegram_webhook_target_username
   self.assertEqual(telegram_webhook_target_username(),'alice')
  from app.services.ipo.telegram_interactive import interactive_config
  with patch('app.services.system_settings.get_effective_system_settings',return_value={'telegram_webhook_owner':'alice'}),patch('app.services.telegram_config.resolve_telegram_config',return_value=self.cfg()):self.assertEqual(interactive_config()[3],'alice')

class TelegramManagementApiTests(unittest.TestCase):
 def setUp(self):
  self._tmp=tempfile.TemporaryDirectory(prefix='wealth-tg-mgmt-');self.addCleanup(self._tmp.cleanup)
  self._users=Path(self._tmp.name)/'users'
  def _get_user_dir(u=None):
   p=self._users/(u or 'alice').strip();p.mkdir(parents=True,exist_ok=True);return p
  p=patch('app.services.user_manager.get_user_data_dir',side_effect=_get_user_dir)
  p.start();self.addCleanup(p.stop)
 def client(self,role='admin'):
  client=TestClient(app);client.cookies.set(COOKIE_NAME,_serializer.dumps({'user':'alice'}));user=patch('app.services.user_manager.get_user_by_name',return_value={'username':'alice','id':'1','role':role});user.start();self.addCleanup(user.stop);return client
 def test_system_patch_is_admin_only(self):
  with patch('app.services.system_settings.patch_system_settings',return_value={'version':1,'public_base_url':'https://wealth.example.com','public_base_url_source':'stored','telegram_webhook_owner':'alice','telegram_webhook_owner_source':'stored'}):
   self.assertEqual(self.client('user').patch('/api/settings/system',json={'public_base_url':'https://wealth.example.com'}).status_code,403)
   self.assertEqual(self.client().patch('/api/settings/system',json={'public_base_url':'https://wealth.example.com'}).status_code,200)
 def test_test_message_uses_authenticated_user_config(self):
  with patch('app.services.telegram_config.resolve_telegram_config',return_value=TelegramManagementTests().cfg()),patch('app.services.telegram_management.send_test_message',return_value={'ok':True,'message':'sent'}) as send,patch('app.services.notifications.history.record_single_provider_history') as record:
   response=self.client('user').post('/api/settings/telegram/test');self.assertEqual(response.status_code,200);send.assert_called_once();self.assertEqual(send.call_args.args[0].username,'alice');record.assert_called_once();self.assertEqual(record.call_args.args[0],'alice');self.assertEqual(record.call_args.kwargs['provider'],'telegram');self.assertTrue(record.call_args.kwargs['success'])
 def test_connect_requires_admin_and_matching_owner(self):
  system={'telegram_webhook_owner':'bob','public_base_url':'https://wealth.example.com'}
  with patch('app.services.system_settings.get_effective_system_settings',return_value=system):
   self.assertEqual(self.client('user').post('/api/settings/telegram/webhook/connect').status_code,403)
   self.assertEqual(self.client().post('/api/settings/telegram/webhook/connect').status_code,409)
 def test_status_connect_disconnect_safe_api_contract(self):
  config=TelegramManagementTests().cfg();system={'telegram_webhook_owner':'alice','public_base_url':'https://wealth.example.com'};hook={'configured':True,'expected_url':'https://wealth.example.com/api/integrations/telegram/webhook','actual_url':'https://wealth.example.com/api/integrations/telegram/webhook','matches_expected':True,'pending_update_count':0,'last_error_date':None,'last_error_message':None,'max_connections':40,'allowed_updates':['message'],'ip_address':None}
  with patch('app.services.telegram_config.resolve_telegram_config',return_value=config),patch('app.services.system_settings.get_effective_system_settings',return_value=system),patch('app.services.telegram_management.check_bot',return_value={'id':1,'username':'wealth_bot'}),patch('app.services.telegram_management.webhook_info',return_value=hook),patch('app.services.telegram_management.connect_webhook') as connect,patch('app.services.telegram_management.disconnect_webhook') as disconnect:
   client=self.client();status=client.get('/api/settings/telegram/status');self.assertEqual(status.status_code,200);self.assertNotIn('SUPER_TOKEN',status.text);self.assertNotIn('Safe_secret-1',status.text)
   self.assertEqual(client.post('/api/settings/telegram/webhook/connect').status_code,200);connect.assert_called_once()
   self.assertEqual(client.post('/api/settings/telegram/webhook/disconnect').status_code,200);disconnect.assert_called_once()
