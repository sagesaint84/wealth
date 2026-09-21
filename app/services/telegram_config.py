from __future__ import annotations
import os
from dataclasses import dataclass, field
from app.services.settings import get_effective_settings
from app.services.telegram_secrets import load_stored_telegram_secrets
@dataclass(frozen=True)
class TelegramConfig:
 username:str; enabled:bool; bot_token:str|None=field(default=None,repr=False); chat_id:int|None=None; webhook_secret:str|None=field(default=None,repr=False); allowed_user_id:int|None=None; allowed_chat_id:int|None=None; bot_token_source:str='none'; webhook_secret_source:str='none'
 @property
 def outbound_configured(self): return self.enabled and bool(self.bot_token) and self.chat_id is not None
 @property
 def interactive_configured(self): return self.enabled and bool(self.webhook_secret) and self.allowed_user_id is not None and self.allowed_chat_id is not None
def resolve_telegram_config(username:str)->TelegramConfig:
 settings=get_effective_settings(username); t=settings['telegram']; bound=os.getenv('TELEGRAM_WEALTH_USERNAME','').strip()==username; stored=load_stored_telegram_secrets(username)
 def sec(key,env):
  if stored[key]: return stored[key],'stored'
  value=os.getenv(env,'').strip() if bound else ''
  return (value or None),('environment' if value else 'none')
 bot,bs=sec('bot_token','TELEGRAM_BOT_TOKEN'); web,ws=sec('webhook_secret','TELEGRAM_WEBHOOK_SECRET')
 return TelegramConfig(username,t['enabled'] or (bound and any((bot,web,t['chat_id'],t['allowed_user_id'],t['allowed_chat_id']))),bot,t['chat_id'],web,t['allowed_user_id'],t['allowed_chat_id'],bs,ws)

def resolve_runtime_telegram_config(username: str | None = None) -> TelegramConfig | None:
 """Compatibility bridge: only the explicitly env-bound user may be implicit."""
 target = username or os.getenv('TELEGRAM_WEALTH_USERNAME', '').strip()
 return resolve_telegram_config(target) if target else None

def telegram_webhook_target_username() -> str | None:
 from app.services.system_settings import get_effective_system_settings
 return get_effective_system_settings().get('telegram_webhook_owner')

def telegram_secret_status(username:str)->dict[str,object]:
 cfg=resolve_telegram_config(username)
 return {"bot_token_configured":bool(cfg.bot_token),"bot_token_source":cfg.bot_token_source,"webhook_secret_configured":bool(cfg.webhook_secret),"webhook_secret_source":cfg.webhook_secret_source}
