"""User-scoped Telegram secrets; never return raw values from API helpers."""
from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any
from app.services.settings import _path as settings_path, settings_lock, SettingsError
class TelegramSecretError(SettingsError): pass
def secret_path(username:str)->Path: return settings_path(username).parent/'secrets'/'telegram.json'
def load_stored_telegram_secrets(username:str, *, path:Path|None=None)->dict[str,str]:
 p=path or secret_path(username)
 if not p.exists(): return {'bot_token':'','webhook_secret':''}
 try: data=json.loads(p.read_text(encoding='utf-8'))
 except Exception as exc: raise TelegramSecretError('TELEGRAM_SECRET_STATE_INVALID') from exc
 if not isinstance(data,dict) or set(data)!={'version','bot_token','webhook_secret'} or data['version']!=1 or any(not isinstance(data[k],str) for k in ('bot_token','webhook_secret')): raise TelegramSecretError('TELEGRAM_SECRET_STATE_INVALID')
 return {k:data[k] for k in ('bot_token','webhook_secret')}
def _save(data:dict,path:Path)->None:
 tmp=path.with_suffix('.tmp')
 try:
  path.parent.mkdir(parents=True,exist_ok=True)
  if os.name=='posix': os.chmod(path.parent,0o700)
  with open(tmp,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
  for attempt in range(50):
   try:
    os.replace(tmp,path); break
   except PermissionError:
    if attempt == 49: raise
    time.sleep(.01)
  if os.name=='posix': os.chmod(path,0o600)
 except Exception: tmp.unlink(missing_ok=True);raise
def update_telegram_secrets(username:str, patch:dict[str,Any], *, path:Path|None=None)->dict[str,str]:
 if not isinstance(patch,dict) or set(patch)-{'bot_token','webhook_secret','clear_bot_token','clear_webhook_secret'}: raise TelegramSecretError('INVALID_TELEGRAM_SECRET_PATCH')
 p=path or secret_path(username)
 for attempt in range(100):
  try:
   with settings_lock(p):
    current=load_stored_telegram_secrets(username,path=p)
    for key in ('bot_token','webhook_secret'):
     value=patch.get(key)
     if value is not None:
      if not isinstance(value,str) or '\x00' in value: raise TelegramSecretError('INVALID_TELEGRAM_SECRET')
      if value.strip() and not set(value.strip()) <= {'*','•'}: current[key]=value.strip()
    if patch.get('clear_bot_token') is True: current['bot_token']=''
    if patch.get('clear_webhook_secret') is True: current['webhook_secret']=''
    _save({'version':1,**current},p); break
  except SettingsError as exc:
   if str(exc) != 'SETTINGS_ALREADY_RUNNING' or attempt == 99: raise
   time.sleep(.01)
 return current
