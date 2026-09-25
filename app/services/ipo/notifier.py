"""Wealth IPO Telegram Notifier Service.

Supports:
- Subscription tomorrow / today / last day reminders
- Listing tomorrow / today reminders
- Schedule / price change alerts
- Score calculation / significant change alerts (|Δscore| >= 5 or grade change)
- Uncompleted family application reminders on last subscription day
- Deduplication via data/ipo/notification_state.json
- Rate-limiting / backoff on 429
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import threading
import os
from contextlib import contextmanager
from typing import Any
from urllib import parse, request

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
NOTIFICATION_STATE_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "ipo" / "notification_state.json"
_NOTIFIER_LOCK = threading.RLock()
_NOTIFIER_PROCESS_LOCK = threading.Lock()


class IpoNotifierStateError(RuntimeError):
    """Raised when notification_state.json is corrupt or unreadable."""


class IpoNotificationAlreadyRunning(RuntimeError):
    pass


@contextmanager
def notification_state_lock(state_path: Path):
    """Non-blocking lock for every notification-state read/send/write transaction."""
    if not _NOTIFIER_PROCESS_LOCK.acquire(blocking=False):
        raise IpoNotificationAlreadyRunning("IPO_NOTIFICATION_ALREADY_RUNNING")
    handle = None
    try:
        lock_path = state_path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                if lock_path.stat().st_size == 0:
                    handle.write(b"0"); handle.flush()
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise IpoNotificationAlreadyRunning("IPO_NOTIFICATION_ALREADY_RUNNING") from exc
        yield
    finally:
        try:
            if handle is not None:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        if handle is not None:
            handle.close()
        _NOTIFIER_PROCESS_LOCK.release()


class IpoTelegramNotifier:
    """Sends IPO notifications to Telegram with atomic deduplication state tracking."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        state_path: Path | None = None,
        username: str | None = None,
    ):
        if bot_token is None and chat_id is None:
            from app.services.telegram_config import resolve_runtime_telegram_config
            cfg=resolve_runtime_telegram_config(username)
            if cfg: bot_token=cfg.bot_token; chat_id=cfg.chat_id
        self.bot_token = bot_token or ''
        self.chat_id = chat_id or ''
        self.state_path = state_path or NOTIFICATION_STATE_FILE

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def load_state(self) -> dict[str, Any]:
        with _NOTIFIER_LOCK:
            if not self.state_path.exists():
                return {"sent_keys": {}, "last_sent_at": {}, "snapshots": {}}
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise IpoNotifierStateError(f"Notification state at {self.state_path} is not a valid JSON object")
                data.setdefault("sent_keys", {})
                data.setdefault("last_sent_at", {})
                data.setdefault("snapshots", {})
                return data
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise IpoNotifierStateError(f"Notification state at {self.state_path} is corrupt or unreadable") from exc

    def save_state(self, state: dict[str, Any]) -> None:
        with _NOTIFIER_LOCK:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.state_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            tmp_path.replace(self.state_path)

    def send_message(self, text: str, parse_mode: str = "HTML", reply_markup: dict[str, Any] | None = None) -> bool:
        from app.services.notifications.models import NotificationEvent
        from app.services.notifications.telegram import TelegramSender

        sender = TelegramSender(bot_token=self.bot_token, chat_id=self.chat_id)
        metadata = {"reply_markup": reply_markup} if reply_markup is not None else {}
        event = NotificationEvent(
            event_key="ipo_message",
            event_type="ipo_alert",
            body=text,
            parse_mode=parse_mode,
            metadata=metadata,
        )
        # Use urlopen/time from this module if patched in legacy tests
        result = sender.send(event, _urlopen=request.urlopen, _sleep=time.sleep)
        return result.success

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> bool:
        if not self.is_configured() or not callback_query_id:
            return False
        payload = parse.urlencode({"callback_query_id": callback_query_id, "text": text}).encode("utf-8")
        try:
            with request.urlopen(request.Request(f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery", data=payload, method="POST"), timeout=10) as resp:
                return resp.status == 200
        except Exception:
            logger.warning("Telegram callback acknowledgement failed")
            return False

    def check_and_notify_events(
        self, ipos: list[dict[str, Any]], applications: dict[str, Any] | None = None,
        target_date_str: str | None = None, dry_run: bool = False,
    ) -> list[str]:
        with notification_state_lock(self.state_path):
            return self._check_and_notify_events_unlocked(ipos, applications, target_date_str, dry_run)

    def _check_and_notify_events_unlocked(
        self,
        ipos: list[dict[str, Any]],
        applications: dict[str, Any] | None = None,
        target_date_str: str | None = None,
        dry_run: bool = False,
    ) -> list[str]:
        """Check all IPO schedules and state changes, sending notifications if not previously sent."""
        if not target_date_str:
            target_date_str = datetime.now(KST).strftime("%Y-%m-%d")

        today = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        tomorrow = today + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")

        state = self.load_state()
        sent_keys = state.setdefault("sent_keys", {})
        notifications_sent = []

        apps_by_ipo = applications.get("applications", {}) if applications else {}

        for ipo in ipos:
            ipo_id = ipo.get("ipo_id")
            name = ipo.get("company_name", "공모주")
            sub_start = ipo.get("subscription_start")
            sub_end = ipo.get("subscription_end")
            listing = ipo.get("actual_listing_date") or ipo.get("expected_listing_date")
            score_data = ipo.get("score") or {}
            score = score_data.get("score")
            grade = score_data.get("grade")
            lead_managers = ipo.get("lead_managers", [])
            if isinstance(lead_managers, list) and lead_managers:
                managers_str = ", ".join(lead_managers)
            else:
                managers_str = str(ipo.get("lead_manager") or "미정")
            price = f"{int(ipo.get('final_offer_price', 0)):,}원" if ipo.get("final_offer_price") else "미확정"

            def _dispatch_or_preview(k: str, m: str) -> bool:
                if dry_run:
                    notifications_sent.append(k)
                    return True
                if self.send_message(m):
                    sent_keys[k] = datetime.now().isoformat()
                    notifications_sent.append(k)
                    return True
                return False

            # 1. Subscription tomorrow
            if sub_start == tomorrow_str:
                key = f"{ipo_id}:sub_tomorrow:{tomorrow_str}"
                if key not in sent_keys:
                    msg = (
                        f"📅 <b>[공모주 내일 청약 시작] {name}</b>\n"
                        f"• 청약일: {sub_start} ~ {sub_end}\n"
                        f"• 확정공모가: {price}\n"
                        f"• 주관사: {managers_str}\n"
                    )
                    if score is not None:
                        msg += f"• Wealth Score: <b>{score}점 ({grade}등급)</b>\n"
                    _dispatch_or_preview(key, msg)

            # 2. Subscription today (Start day)
            if sub_start == target_date_str:
                key = f"{ipo_id}:sub_start:{target_date_str}"
                if key not in sent_keys:
                    msg = (
                        f"🔔 <b>[공모주 오늘 청약 1일차] {name}</b>\n"
                        f"• 청약일: {sub_start} ~ {sub_end}\n"
                        f"• 확정공모가: {price}\n"
                        f"• 주관사: {managers_str}\n"
                    )
                    if score is not None:
                        msg += f"• Wealth Score: <b>{score}점 ({grade}등급)</b>\n"
                    _dispatch_or_preview(key, msg)

            # 3. Subscription last day
            if sub_end == target_date_str:
                key = f"{ipo_id}:sub_end:{target_date_str}"
                if key not in sent_keys:
                    msg = (
                        f"⏰ <b>[공모주 오늘 청약 마감!] {name}</b>\n"
                        f"• 마감시간 확인 필수 (보통 16:00)\n"
                        f"• 확정공모가: {price}\n"
                        f"• 주관사: {managers_str}\n"
                    )
                    # Check family applications using canonical fields
                    ipo_app = apps_by_ipo.get(ipo_id, {})
                    target_owners = ipo_app.get("target_owners", [])
                    applied_owners = ipo_app.get("applied_owners", [])
                    all_applied = bool(ipo_app.get("all_applied", False))

                    family_status_lines = []
                    for owner in target_owners:
                        if owner in applied_owners:
                            family_status_lines.append(f"✅ {owner}")
                        else:
                            family_status_lines.append(f"⬜ {owner}")

                    # Incomplete family warning only when all_applied is False
                    if not all_applied and target_owners:
                        missing_owners = [o for o in target_owners if o not in applied_owners]
                        msg += f"⚠️ <b>미신청 가족 구성원:</b> {', '.join(missing_owners)}\n"
                        if family_status_lines:
                            msg += f"• 가족 신청 현황: {' '.join(family_status_lines)}\n"
                    elif all_applied and target_owners:
                        msg += f"✅ <b>가족 전원 신청 완료:</b> {', '.join(applied_owners)}\n"

                    _dispatch_or_preview(key, msg)

            # 4. Listing tomorrow
            if listing == tomorrow_str:
                key = f"{ipo_id}:listing_tomorrow:{tomorrow_str}"
                if key not in sent_keys:
                    msg = (
                        f"🚀 <b>[공모주 내일 상장] {name}</b>\n"
                        f"• 상장일: {listing}\n"
                        f"• 공모가: {price}\n"
                        f"• 주관사: {managers_str}\n"
                    )
                    _dispatch_or_preview(key, msg)

            # 5. Listing today
            if listing == target_date_str:
                key = f"{ipo_id}:listing_today:{target_date_str}"
                if key not in sent_keys:
                    msg = (
                        f"🎉 <b>[공모주 오늘 상장!] {name}</b>\n"
                        f"• 상장일: {listing}\n"
                        f"• 공모가: {price}\n"
                        f"• 장 시작 전 호가 확인 및 매도 준비\n"
                    )
                    _dispatch_or_preview(key, msg)

            # 6. Score calculated / significant change (|Δscore| >= 5 or grade change)
            if score is not None:
                last_score_key = f"{ipo_id}:last_score"
                last_score_val = state.get(last_score_key)
                last_grade_key = f"{ipo_id}:last_grade"
                last_grade_val = state.get(last_grade_key)

                is_initial = last_score_val is None
                is_changed = False
                if not is_initial:
                    diff = abs(score - float(last_score_val))
                    grade_changed = (grade != last_grade_val)
                    if diff >= 5.0 or grade_changed:
                        is_changed = True

                if is_initial or is_changed:
                    key = f"{ipo_id}:score_update:{score}_{grade}"
                    if key not in sent_keys:
                        action = "산정 완료" if is_initial else f"변동 ({last_score_val}점 → {score}점)"
                        msg = (
                            f"📊 <b>[공모주 Score {action}] {name}</b>\n"
                            f"• 평가 등급: <b>{grade}등급 ({score}점)</b>\n"
                            f"• 확정공모가: {price}\n"
                            f"• 청약일: {sub_start or '미정'} ~ {sub_end or '미정'}\n"
                        )
                        if _dispatch_or_preview(key, msg):
                            if not dry_run:
                                state[last_score_key] = score
                                state[last_grade_key] = grade

            # 7. Schedule / price change detection
            snapshots = state.setdefault("snapshots", {})
            curr_snap = {
                "subscription_start": sub_start,
                "subscription_end": sub_end,
                "payment_date": ipo.get("payment_date"),
                "expected_listing_date": ipo.get("expected_listing_date"),
                "final_offer_price": ipo.get("final_offer_price"),
            }
            if ipo_id in snapshots:
                prev_snap = snapshots[ipo_id]
                change_labels = {
                    "subscription_start": "청약시작일",
                    "subscription_end": "청약마감일",
                    "payment_date": "납입일",
                    "expected_listing_date": "상장예정일",
                    "final_offer_price": "확정공모가",
                }
                for field_name, label in change_labels.items():
                    old_val = prev_snap.get(field_name)
                    new_val = curr_snap.get(field_name)
                    if old_val is not None and new_val is not None and old_val != new_val:
                        key = f"{ipo_id}:schedule_change:{field_name}:{old_val}:{new_val}"
                        if key not in sent_keys:
                            old_display = f"{int(old_val):,}원" if field_name == "final_offer_price" else str(old_val)
                            new_display = f"{int(new_val):,}원" if field_name == "final_offer_price" else str(new_val)
                            msg = (
                                f"📢 <b>[공모주 {label} 변동 알림] {name}</b>\n"
                                f"• 변동 항목: {label}\n"
                                f"• 기존값: {old_display}\n"
                                f"• 신규값: <b>{new_display}</b>\n"
                            )
                            _dispatch_or_preview(key, msg)
            if not dry_run:
                snapshots[ipo_id] = curr_snap

        if not dry_run:
            self.save_state(state)
        return notifications_sent
