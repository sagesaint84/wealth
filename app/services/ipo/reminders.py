"""Read-only, slot-based IPO subscription reminder runner."""
from __future__ import annotations

import argparse
from datetime import date, datetime
from typing import Any

from app.services.ipo.applications import get_user_applications
from app.services.ipo.notifier import IpoTelegramNotifier, KST, notification_state_lock
from app.services.ipo.store import read_market_store_read_only

REMINDER_SLOTS = {"0900", "1200", "1500"}


def _is_valid_reminder_slot(slot: str) -> bool:
    if not isinstance(slot, str) or len(slot) != 4 or not slot.isdigit():
        return False
    hh = int(slot[:2])
    mm = int(slot[2:])
    return 0 <= hh <= 23 and 0 <= mm <= 59


def run_ipo_subscription_reminders(
    *, username: str | None, reminder_slot: str, today: date | None = None,
    notifier: IpoTelegramNotifier | None = None, market_store: dict[str, Any] | None = None,
    applications: dict[str, Any] | None = None,
    is_last_slot: bool | None = None,
) -> dict[str, Any]:
    """Send at most one grouped reminder per IPO/date/slot; never refreshes market data."""
    if not _is_valid_reminder_slot(reminder_slot):
        raise ValueError("INVALID_REMINDER_SLOT")
    current = today or datetime.now(KST).date()
    date_str = current.isoformat()
    store = market_store if market_store is not None else read_market_store_read_only()
    apps = applications if applications is not None else get_user_applications(username)
    family = list(apps.get("family_members") or [])
    client = notifier or IpoTelegramNotifier(username=username)
    with notification_state_lock(client.state_path):
        return _run_reminders_locked(client, store, apps, current, reminder_slot, username, is_last_slot=is_last_slot)


def _run_reminders_locked(
    client: IpoTelegramNotifier,
    store: dict[str, Any],
    apps: dict[str, Any],
    current: date,
    reminder_slot: str,
    username: str | None,
    is_last_slot: bool | None = None,
) -> dict[str, Any]:
    date_str = current.isoformat()
    family = list(apps.get("family_members") or [])
    state = client.load_state()
    sent_keys = state.setdefault("sent_keys", {})
    sent = 0; eligible = 0; complete = 0
    for ipo in store.get("ipos", []):
        try:
            start = datetime.strptime(str(ipo.get("subscription_start") or "")[:10], "%Y-%m-%d").date()
            end = datetime.strptime(str(ipo.get("subscription_end") or "")[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if end < start or not (start <= current <= end):
            continue
        ipo_id = str(ipo.get("ipo_id") or "").strip()
        if not ipo_id:
            continue
        app = (apps.get("applications") or {}).get(ipo_id, {})
        targets = list(app.get("target_owners") or family)
        applied = set(app.get("applied_owners") or [])
        missing = [owner for owner in targets if owner not in applied]
        if not missing:
            complete += 1
            continue
        eligible += 1
        key = f"{ipo_id}:sub_reminder:{date_str}:{reminder_slot}"
        if key in sent_keys:
            continue
        managers = ", ".join(ipo.get("lead_managers") or []) or "미정"
        message = (
            f"📌 <b>공모주 청약 확인 — {reminder_slot[:2]}:{reminder_slot[2:]}</b>\n"
            f"{ipo.get('company_name') or '공모주'}\n"
            f"• 청약: {start.isoformat()} ~ {end.isoformat()}\n"
            f"• 주관사: {managers}\n"
            f"⚠️ <b>아직 신청하지 않음:</b> {', '.join(missing)}\n"
        )
        should_warn = is_last_slot if is_last_slot is not None else (reminder_slot == "1500")
        if should_warn:
            message += "청약 마감 시간이 가까워지고 있습니다. 증권사별 실제 청약 접수 마감 시간을 확인하세요.\n"
        markup = None
        try:
            from app.services.ipo.telegram_interactive import interactive_config
            if interactive_config() is not None:
                from app.services.ipo.actions import create_mark_applied_action
                buttons=[]
                for owner in missing:
                    action=create_mark_applied_action(username, ipo_id, owner, "telegram", today=current)
                    callback=f"ipoa:{action['action_id']}"
                    if len(callback.encode('utf-8')) <= 64:
                        buttons.append({"text": f"{owner} 청약 완료", "callback_data": callback})
                if buttons: markup={"inline_keyboard":[buttons]}
        except Exception:
            markup = None
        if client.send_message(message, reply_markup=markup):
            sent_keys[key] = datetime.now(KST).isoformat()
            sent += 1
    if sent:
        client.save_state(state)
    return {"status": "ok", "slot": reminder_slot, "eligible_ipos": eligible,
            "notifications_sent_count": sent, "all_applied_count": complete}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--last-slot", action="store_true", default=None)
    args = parser.parse_args()
    print(run_ipo_subscription_reminders(
        username=args.username,
        reminder_slot=args.slot,
        is_last_slot=args.last_slot,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
