"""Confirmation after a canonical applied transition and successful action consumption."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from app.services.notifications.models import NotificationEvent
from app.services.notifications.service import UserNotificationService
from app.services.ipo.store import read_market_store_read_only

logger = logging.getLogger(__name__)


def confirm_applied_transition(username: str | None, result: dict[str, Any]) -> dict[str, Any]:
    """CAS's first-transition result is the domain dedup gate, shared by native/web actions.

    Delivery is best effort after durable action consumption. A delivery failure never
    changes application state or makes a consumed action executable again.
    """
    if result.get("status") != "applied":
        return result
    if not username:
        return {**result, "notification": {"status": "unconfigured", "error": "USER_REQUIRED"}}
    try:
        ipo_id, owner = result["ipo_id"], result["owner"]
        ipo = next((item for item in read_market_store_read_only().get("ipos", [])
                    if item.get("ipo_id") == ipo_id), {})
        identity = json.dumps([username, ipo_id, owner], ensure_ascii=False, separators=(",", ":"))
        event = NotificationEvent(
            event_key="ipo_application_confirmed:" + hashlib.sha256(identity.encode()).hexdigest(),
            event_type="ipo_application_confirmed",
            username=username,
            body=f"✅ 공모주 청약 확인\n{ipo.get('company_name') or ipo_id}\n• 신청자: {owner}\n• 청약 완료로 기록했습니다.",
            metadata={"ipo_id": ipo_id, "owner": owner},
        )
        report = UserNotificationService(username).dispatch(event)
        notification = {"status": report.status,
                        "notifications_sent_count": report.notifications_sent_count,
                        "provider_results": report.provider_results}
    except Exception:
        # Only the outbound boundary is isolated; canonical/action persistence exceptions propagate.
        logger.warning("IPO application confirmation failed")
        notification = {"status": "failed", "error": "CONFIRMATION_FAILED"}
    return {**result, "notification": notification}
