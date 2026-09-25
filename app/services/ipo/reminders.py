"""Read-only, slot-based IPO subscription reminder runner."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)

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
        callback_buttons = []
        try:
            from app.services.ipo.telegram_interactive import interactive_config
            if interactive_config() is not None:
                from app.services.ipo.actions import create_mark_applied_action
                for owner in missing:
                    action = create_mark_applied_action(username, ipo_id, owner, "telegram", today=current)
                    callback = f"ipoa:{action['action_id']}"
                    if len(callback.encode("utf-8")) <= 64:
                        callback_buttons.append({"text": f"{owner} 청약 완료", "callback_data": callback})
        except Exception:
            callback_buttons = []

        web_action_rows = []
        if username:
            from app.services.action_v2 import (
                ACTION_TYPE_MARK_IPO_APPLIED,
                build_action_url,
                create_web_action,
            )
            for owner in missing:
                try:
                    web_action = create_web_action(
                        action_type=ACTION_TYPE_MARK_IPO_APPLIED,
                        username=username,
                        source_channel="telegram",
                        metadata={"ipo_id": ipo_id, "owner": owner},
                        today=current,
                    )
                    action_url = build_action_url(web_action["raw_token"])
                    web_action_rows.append([{"text": f"{owner} Wealth에서 확인", "url": action_url}])
                except Exception as exc:
                    logger.warning("IPO web action link unavailable: %s", type(exc).__name__)

        keyboard = []
        if callback_buttons:
            keyboard.append(callback_buttons)
        if web_action_rows:
            keyboard.extend(web_action_rows)
        if keyboard:
            markup = {"inline_keyboard": keyboard}
        if client.dispatch_message(
            key,
            message,
            state,
            reply_markup=markup,
        ):
            sent += 1
    if sent:
        client.save_state(state)
    return {"status": "ok", "slot": reminder_slot, "eligible_ipos": eligible,
            "notifications_sent_count": sent, "all_applied_count": complete}


def run_ipo_listing_reminders(
    *, username: str | None, reminder_slot: str, today: date | None = None,
    notifier: IpoTelegramNotifier | None = None,
    market_store: dict[str, Any] | None = None,
    applications: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send user-scoped, non-advisory reminders for IPOs listing today."""
    if not _is_valid_reminder_slot(reminder_slot):
        raise ValueError("INVALID_LISTING_REMINDER_SLOT")
    current = today or datetime.now(KST).date()
    store = market_store if market_store is not None else read_market_store_read_only()
    apps = applications if applications is not None else get_user_applications(username)
    client = notifier or IpoTelegramNotifier(username=username)
    with notification_state_lock(client.state_path):
        return _run_listing_reminders_locked(client, store, apps, current, reminder_slot, username)


def _run_listing_reminders_locked(
    client: IpoTelegramNotifier,
    store: dict[str, Any],
    apps: dict[str, Any],
    current: date,
    reminder_slot: str,
    username: str | None,
) -> dict[str, Any]:
    from app.services.ipo.allocation import allocation_summary
    from app.services.broker_registry import get_display_name

    date_str = current.isoformat()
    state = client.load_state()
    sent_keys = state.setdefault("sent_keys", {})
    sent = 0
    eligible = 0
    fully_sold_count = 0
    no_allocation_count = 0
    unresolved_count = 0
    actionable_owner_count = 0

    user_apps = apps.get("applications", {}) if isinstance(apps, dict) else {}

    for ipo in store.get("ipos", []):
        ipo_id = str(ipo.get("ipo_id") or "").strip()
        if not ipo_id:
            continue
        listing_raw = str(
            ipo.get("actual_listing_date") or ipo.get("expected_listing_date") or ""
        )[:10]
        try:
            listing_date = datetime.strptime(listing_raw, "%Y-%m-%d").date()
        except ValueError:
            continue
        if listing_date != current:
            continue
        eligible += 1
        key = f"{ipo_id}:listing_reminder:{date_str}:{reminder_slot}"
        if key in sent_keys:
            continue

        app_record = user_apps.get(ipo_id, {})
        applied_owners = list(app_record.get("applied_owners") or [])
        applicants = app_record.get("applicants", {}) or {}
        stock_code = str(ipo.get("stock_code") or "").strip()

        # If user has no applied owners for this IPO, do not send reminder
        if not applied_owners:
            continue

        owner_lines: list[str] = []
        action_buttons: list[dict[str, str]] = []
        has_actionable_owners = False

        for owner in applied_owners:
            applicant = applicants.get(owner)
            broker_display = None
            if isinstance(applicant, dict) and applicant.get("broker_id"):
                broker_display = get_display_name(applicant["broker_id"]) or applicant["broker_id"]

            if not isinstance(applicant, dict) or not applicant.get("account_id") or not applicant.get("broker_id"):
                # UNRESOLVED_ACCOUNT
                owner_header = f"{owner} / {broker_display}" if broker_display else owner
                owner_lines.append(f"{owner_header}\n청약 계좌 연결 필요")
                has_actionable_owners = True
                unresolved_count += 1
                actionable_owner_count += 1
                # Status check action button
                if username:
                    try:
                        from app.services.action_v2 import ACTION_TYPE_OPEN_IPO_SALE_FLOW, build_action_url, create_web_action
                        web_action = create_web_action(
                            action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
                            username=username,
                            source_channel="telegram",
                            metadata={"ipo_id": ipo_id, "owner": owner},
                            today=current,
                        )
                        action_buttons.append({"text": f"{owner} 상태 확인", "url": build_action_url(web_action["raw_token"])})
                    except Exception as exc:
                        logger.warning("IPO listing web action unavailable: %s", type(exc).__name__)
                continue

            try:
                summary = allocation_summary(username, ipo_id, owner, stock_code, listing_raw)
            except Exception as exc:
                logger.warning("IPO allocation summary unavailable: %s", type(exc).__name__)
                summary = {"status": "UNRESOLVED"}

            status = summary.get("status")
            alloc_info = summary.get("allocation") or {}
            qty = alloc_info.get("quantity", 0)
            sold = alloc_info.get("sold_quantity", 0)
            remaining = alloc_info.get("remaining_quantity", 0)

            owner_header = f"{owner} / {broker_display}" if broker_display else owner

            if status == "NO_ALLOCATION":
                no_allocation_count += 1
                continue
            elif status == "FULLY_SOLD":
                fully_sold_count += 1
                continue
            elif status == "UNSOLD":
                owner_lines.append(f"{owner_header}\n배정 {qty}주 · 매도 0주 · 잔여 {remaining}주")
                has_actionable_owners = True
                actionable_owner_count += 1
                if username:
                    try:
                        from app.services.action_v2 import ACTION_TYPE_OPEN_IPO_SALE_FLOW, build_action_url, create_web_action
                        web_action = create_web_action(
                            action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
                            username=username,
                            source_channel="telegram",
                            metadata={"ipo_id": ipo_id, "owner": owner},
                            today=current,
                        )
                        action_buttons.append({"text": f"{owner} 매도 기록", "url": build_action_url(web_action["raw_token"])})
                    except Exception as exc:
                        logger.warning("IPO listing web action unavailable: %s", type(exc).__name__)
            elif status == "PARTIALLY_SOLD":
                owner_lines.append(f"{owner_header}\n배정 {qty}주 · 매도 {sold}주 · 잔여 {remaining}주")
                has_actionable_owners = True
                actionable_owner_count += 1
                if username:
                    try:
                        from app.services.action_v2 import ACTION_TYPE_OPEN_IPO_SALE_FLOW, build_action_url, create_web_action
                        web_action = create_web_action(
                            action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
                            username=username,
                            source_channel="telegram",
                            metadata={"ipo_id": ipo_id, "owner": owner},
                            today=current,
                        )
                        action_buttons.append({"text": f"{owner} 매도 기록", "url": build_action_url(web_action["raw_token"])})
                    except Exception as exc:
                        logger.warning("IPO listing web action unavailable: %s", type(exc).__name__)
            elif status == "LINK_DATA_MISSING":
                owner_lines.append(f"{owner_header}\n매도 연결 데이터 확인 필요")
                has_actionable_owners = True
                actionable_owner_count += 1
                if username:
                    try:
                        from app.services.action_v2 import ACTION_TYPE_OPEN_IPO_SALE_FLOW, build_action_url, create_web_action
                        web_action = create_web_action(
                            action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
                            username=username,
                            source_channel="telegram",
                            metadata={"ipo_id": ipo_id, "owner": owner},
                            today=current,
                        )
                        action_buttons.append({"text": f"{owner} 상태 확인", "url": build_action_url(web_action["raw_token"])})
                    except Exception as exc:
                        logger.warning("IPO listing web action unavailable: %s", type(exc).__name__)
            else:  # UNRESOLVED
                owner_lines.append(f"{owner_header}\n배정수량 미기록")
                has_actionable_owners = True
                unresolved_count += 1
                actionable_owner_count += 1
                if username:
                    try:
                        from app.services.action_v2 import ACTION_TYPE_OPEN_IPO_SALE_FLOW, build_action_url, create_web_action
                        web_action = create_web_action(
                            action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
                            username=username,
                            source_channel="telegram",
                            metadata={"ipo_id": ipo_id, "owner": owner},
                            today=current,
                        )
                        action_buttons.append({"text": f"{owner} 상태 확인", "url": build_action_url(web_action["raw_token"])})
                    except Exception as exc:
                        logger.warning("IPO listing web action unavailable: %s", type(exc).__name__)

        # If all applied owners are FULLY_SOLD or NO_ALLOCATION, suppress message
        if not has_actionable_owners or not owner_lines:
            continue

        price = ipo.get("final_offer_price")
        price_text = f"{int(price):,}원" if isinstance(price, (int, float)) else "미정"
        managers = ", ".join(ipo.get("lead_managers") or []) or "미정"
        if reminder_slot == "0850":
            title = "🚀 <b>공모주 오늘 상장</b>"
            guidance = "장 시작 전 호가와 주문 상태를 확인하세요."
        elif reminder_slot == "1450":
            title = "📈 <b>공모주 상장일 오후 확인</b>"
            guidance = "장 마감 전 보유 및 주문 상태를 확인하세요."
        else:
            title = "📌 <b>공모주 오늘 상장 확인</b>"
            guidance = "상장 일정과 현재 주문·보유 상태를 확인하세요."

        details_block = "\n\n".join(owner_lines)
        message = (
            f"{title}\n{ipo.get('company_name') or '공모주'}\n"
            f"• 상장일: {listing_date.isoformat()}\n"
            f"• 공모가: {price_text}\n"
            f"• 주관사: {managers}\n\n"
            f"{details_block}\n\n"
            f"{guidance}\n"
        )

        reply_markup = None
        if action_buttons:
            reply_markup = {"inline_keyboard": [[btn] for btn in action_buttons]}

        if client.dispatch_message(
            key,
            message,
            state,
            reply_markup=reply_markup,
        ):
            sent += 1

    if sent:
        client.save_state(state)
    return {
        "status": "ok",
        "slot": reminder_slot,
        "eligible_ipos": eligible,
        "notifications_sent_count": sent,
        "fully_sold_count": fully_sold_count,
        "no_allocation_count": no_allocation_count,
        "unresolved_count": unresolved_count,
        "actionable_owner_count": actionable_owner_count,
    }


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
