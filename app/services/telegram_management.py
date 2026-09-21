"""Safe, user-triggered Telegram Bot API management operations."""
from __future__ import annotations
import json,re
from urllib import parse,request
from app.services.telegram_config import TelegramConfig

API_BASE="https://api.telegram.org"
TEST_MESSAGE="✅ Wealth Telegram 연결 테스트가 성공했습니다."
SECRET_TOKEN=re.compile(r"^[A-Za-z0-9_-]{1,256}$")
class TelegramManagementError(RuntimeError): pass
def _safe_text(value:object,config:TelegramConfig)->str|None:
 text=str(value or '')[:500]
 for secret in (config.bot_token,config.webhook_secret):
  if secret:text=text.replace(secret,'[redacted]')
 return text or None

def _call(config:TelegramConfig,method:str,payload:dict|None=None,*,opener=request.urlopen)->object:
 if not config.bot_token: raise TelegramManagementError("TELEGRAM_NOT_CONFIGURED")
 url=f"{API_BASE}/bot{config.bot_token}/{method}"; data=parse.urlencode(payload or {},doseq=True).encode("utf-8")
 try:
  with opener(request.Request(url,data=data,method="POST"),timeout=10) as response: body=json.loads(response.read().decode("utf-8"))
 except Exception as exc: raise TelegramManagementError("TELEGRAM_API_UNAVAILABLE") from exc
 if not isinstance(body,dict) or body.get("ok") is not True: raise TelegramManagementError("TELEGRAM_BOT_AUTH_FAILED" if body.get("error_code")==401 else "TELEGRAM_OPERATION_FAILED")
 return body.get("result")

def check_bot(config:TelegramConfig,*,opener=request.urlopen)->dict:
 if not config.enabled or not config.bot_token: raise TelegramManagementError("TELEGRAM_NOT_CONFIGURED")
 result=_call(config,"getMe",opener=opener)
 if not isinstance(result,dict): raise TelegramManagementError("TELEGRAM_OPERATION_FAILED")
 return {k:result.get(k) for k in ("id","username","first_name","can_join_groups","can_read_all_group_messages","supports_inline_queries")}

def send_telegram_message(config:TelegramConfig,text:str,*,opener=request.urlopen)->dict:
 if not config.outbound_configured: raise TelegramManagementError("TELEGRAM_NOT_CONFIGURED")
 result=_call(config,"sendMessage",{"chat_id":config.chat_id,"text":text},opener=opener)
 return {"ok":True,"message":"Telegram 메시지를 전송했습니다.","result":result}

def send_test_message(config:TelegramConfig,*,opener=request.urlopen)->dict:
 if not config.outbound_configured: raise TelegramManagementError("TELEGRAM_NOT_CONFIGURED")
 _call(config,"sendMessage",{"chat_id":config.chat_id,"text":TEST_MESSAGE},opener=opener);return {"ok":True,"message":"Telegram 테스트 메시지를 전송했습니다."}

def webhook_info(config:TelegramConfig,expected_url:str|None,*,opener=request.urlopen)->dict:
 result=_call(config,"getWebhookInfo",opener=opener)
 if not isinstance(result,dict): raise TelegramManagementError("TELEGRAM_OPERATION_FAILED")
 actual=str(result.get("url") or "")
 return {"configured":bool(actual),"expected_url":expected_url,"actual_url":actual or None,"matches_expected":bool(actual and expected_url and actual==expected_url),"pending_update_count":int(result.get("pending_update_count") or 0),"last_error_date":result.get("last_error_date"),"last_error_message":_safe_text(result.get("last_error_message"),config),"max_connections":result.get("max_connections"),"allowed_updates":result.get("allowed_updates"),"ip_address":result.get("ip_address")}

def connect_webhook(config:TelegramConfig,url:str,*,opener=request.urlopen)->None:
 if not config.interactive_configured or not config.bot_token: raise TelegramManagementError("TELEGRAM_WEBHOOK_CONFIG_INCOMPLETE")
 if not config.webhook_secret or not SECRET_TOKEN.fullmatch(config.webhook_secret): raise TelegramManagementError("TELEGRAM_WEBHOOK_SECRET_INVALID")
 _call(config,"setWebhook",{"url":url,"secret_token":config.webhook_secret,"allowed_updates":json.dumps(["message","callback_query"]),"drop_pending_updates":"false"},opener=opener)

def disconnect_webhook(config:TelegramConfig,*,opener=request.urlopen)->None:
 _call(config,"deleteWebhook",{"drop_pending_updates":"false"},opener=opener)
