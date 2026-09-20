"""Telegram-only authentication and IPO action dispatch helpers."""
from __future__ import annotations
import hmac, os, re
from datetime import datetime
from typing import Any
from app.services.ipo.actions import execute_action, get_action_metadata, mark_ipo_owner_applied
from app.services.ipo.applications import get_user_applications
from app.services.ipo.store import read_market_store_read_only
from app.services.ipo.notifier import IpoTelegramNotifier

def interactive_config() -> tuple[str, int, int, str] | None:
    secret=os.environ.get('TELEGRAM_WEBHOOK_SECRET','')
    username=os.environ.get('TELEGRAM_WEALTH_USERNAME','').strip()
    try: user=int(os.environ.get('TELEGRAM_ALLOWED_USER_ID','')); chat=int(os.environ.get('TELEGRAM_ALLOWED_CHAT_ID',''))
    except ValueError: return None
    return (secret,user,chat,username) if secret and user and chat and username else None

def authorized(secret: str | None, sender: object, chat: object) -> bool:
    cfg=interactive_config()
    return bool(cfg and isinstance(secret,str) and hmac.compare_digest(secret,cfg[0]) and sender==cfg[1] and chat==cfg[2])

def handle_update(update: dict[str,Any], secret: str | None) -> str:
    if not isinstance(update,dict): return 'unauthorized'
    q=update.get('callback_query')
    msg=q if isinstance(q,dict) else update.get('message')
    if not isinstance(msg,dict): return 'ignored'
    sender=(msg.get('from') or {}).get('id'); chat=((msg.get('message') or msg).get('chat') or {}).get('id')
    if not authorized(secret,sender,chat): return 'unauthorized'
    if isinstance(q,dict):
        if not isinstance(q.get('id'), str) or not q['id']:
            return 'unauthorized'
        data=str(q.get('data') or '')
        if not re.fullmatch(r'ipoa:[A-Za-z0-9_-]{1,59}',data): return 'ignored'
        action=get_action_metadata(data[5:])
        if not action or action.get('username') != interactive_config()[3]: return 'unauthorized'
        try: result=execute_action(data[5:])
        except Exception as exc: outcome=str(exc)
        else: outcome='already_applied' if result.get('status') in ('already_applied','already_processed') else 'applied'
        messages={'applied':'✅ 청약 완료로 기록했습니다.','already_applied':'✅ 이미 청약 완료 상태입니다.','ACTION_EXPIRED':'이 청약 완료 버튼은 만료되었습니다.','ACTION_ALREADY_CONSUMED':'이 버튼은 이미 처리되었습니다.'}
        IpoTelegramNotifier().answer_callback_query(str(q.get('id') or ''), messages.get(outcome,'현재 상태에서는 이 요청을 처리할 수 없습니다.'))
        return outcome
    text=str(msg.get('text') or '').strip(); match=re.fullmatch(r'(.+?)\s+청약\s*완료',text)
    if not match: return 'ignored'
    owner=match.group(1).strip(); today=datetime.now().astimezone().date(); candidates=[]
    username=interactive_config()[3]
    apps=get_user_applications(username)
    for ipo in read_market_store_read_only().get('ipos',[]):
        app=(apps.get('applications') or {}).get(ipo.get('ipo_id'),{}); targets=app.get('target_owners') or apps.get('family_members') or []
        if owner in targets and owner not in (app.get('applied_owners') or []): candidates.append(ipo.get('ipo_id'))
    if len(candidates)!=1: return 'ambiguous' if candidates else 'none_pending'
    try: return mark_ipo_owner_applied(username,candidates[0],owner,today=today)['status']
    except Exception as exc: return str(exc)
