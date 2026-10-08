"""Telegram-only authentication and IPO action dispatch helpers."""
from __future__ import annotations
import hmac, re
from datetime import datetime
from typing import Any
from app.services.ipo.actions import execute_action, get_action_metadata, mark_ipo_owner_applied
from app.services.ipo.applications import get_user_applications
from app.services.ipo.store import read_market_store_read_only
from app.services.ipo.notifier import IpoTelegramNotifier

ACTION_MESSAGES = {
    'applied': '✅ 청약 완료로 기록했습니다.',
    'already_applied': '✅ 이미 청약 완료 상태입니다.',
    'ACTION_NOT_FOUND': '이 청약 완료 버튼을 찾을 수 없습니다. 최신 알림을 확인해 주세요.',
    'ACTION_EXPIRED': '이 청약 완료 버튼은 만료되었습니다.',
    'OWNER_NOT_ELIGIBLE': '이 신청자는 해당 공모주의 청약 대상이 아닙니다.',
    'SUBSCRIPTION_NOT_ACTIVE': '현재는 이 공모주의 청약 기간이 아닙니다.',
    'IPO_ACTION_ALREADY_RUNNING': '청약 완료 처리 중입니다. 잠시 후 다시 확인해 주세요.',
    'ACTION_ALREADY_RUNNING': '청약 완료 처리 중입니다. 잠시 후 다시 확인해 주세요.',
    'ACTION_ALREADY_CONSUMED': '이 버튼은 이미 처리되었습니다.',
}

def _safe_action_error(exc: Exception) -> str:
    code = str(exc)
    return code if code in ACTION_MESSAGES else 'ACTION_FAILED'

def interactive_config() -> tuple[str, int, int, str] | None:
    from app.services.telegram_config import telegram_webhook_target_username
    username=telegram_webhook_target_username()
    if not username: return None
    from app.services.telegram_config import resolve_telegram_config
    cfg=resolve_telegram_config(username)
    return (cfg.webhook_secret,cfg.allowed_user_id,cfg.allowed_chat_id,username) if cfg.interactive_configured else None

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
        result = {}
        try:
            action=get_action_metadata(data[5:])
            if action and action.get('username') != interactive_config()[3]: return 'unauthorized'
            if not action:
                outcome='ACTION_NOT_FOUND'
            else:
                result=execute_action(data[5:])
                outcome='already_applied' if result.get('status') in ('already_applied','already_processed') else 'applied'
        except Exception as exc: outcome=_safe_action_error(exc)
        answer=ACTION_MESSAGES.get(outcome,'현재 상태에서는 이 요청을 처리할 수 없습니다.')
        if outcome == 'applied' and result.get('notification', {}).get('status') in ('failed', 'partial', 'unconfigured'):
            answer += ' 확인 알림 일부를 보내지 못했습니다.'
        IpoTelegramNotifier(username=interactive_config()[3]).answer_callback_query(str(q.get('id') or ''), answer)
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
    try:
        from app.services.ipo.application_confirmation import confirm_applied_transition
        return confirm_applied_transition(username, mark_ipo_owner_applied(username,candidates[0],owner,today=today))['status']
    except Exception as exc: return _safe_action_error(exc)
