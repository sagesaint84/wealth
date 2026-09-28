"""Async bridge for Phase 10.5D scheduled financial-income alerts.

Daily-close snapshot persistence is synchronous, while the existing B-1 family
risk builder is asynchronous.  This bridge keeps the storage path non-fatal and
ensures threshold alerts are calculated only from B-1's *individual* member
results.  The family reference total is never thresholded.
"""
from __future__ import annotations

import asyncio
from typing import Any

_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _enabled(username: str) -> bool:
    try:
        from app.services.settings import get_effective_settings

        settings = get_effective_settings(username, include_automation_status=False)
    except Exception:
        return False
    automation = settings.get("automation")
    config = automation.get("dividend_intelligence_alerts") if isinstance(automation, dict) else None
    return isinstance(config, dict) and config.get("enabled") is True


async def dispatch_scheduled_family_financial_income_alerts(
    username: str,
    *,
    as_of: str,
) -> dict[str, Any]:
    """Build B-1 member risk and dispatch opt-in threshold alerts safely.

    Keep a strong reference to the currently running task as well as tasks
    created through the explicit scheduler.  The daily-close snapshot hook may
    create this coroutine directly with ``loop.create_task``; retaining the
    running task here prevents it from being collected before the B-1 async
    calculation and notification dispatch finish.
    """
    current_task = asyncio.current_task()
    if current_task is not None:
        _BACKGROUND_TASKS.add(current_task)
    try:
        if not username:
            return {"status": "skipped", "reason": "username_unavailable", "sent_count": 0}
        if not _enabled(username):
            return {"status": "disabled", "reason": "not_opted_in", "sent_count": 0}
        try:
            from app.services.dividend_intelligence import dispatch_family_financial_income_alerts
            from app.services.tax.family_financial_income import (
                get_family_financial_income_risk_for_user,
            )

            family_risk = await get_family_financial_income_risk_for_user(
                username,
                as_of=as_of,
            )
            return dispatch_family_financial_income_alerts(username, family_risk)
        except Exception:
            # Alerts must never make the daily-close financial snapshot fail.
            return {
                "status": "unavailable",
                "reason": "family_financial_income_alert_unavailable",
                "sent_count": 0,
            }
    finally:
        if current_task is not None:
            _BACKGROUND_TASKS.discard(current_task)


def schedule_scheduled_family_financial_income_alerts(
    username: str,
    *,
    as_of: str,
) -> bool:
    """Queue the async B-1 alert pass on daily close's running event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    task = loop.create_task(
        dispatch_scheduled_family_financial_income_alerts(username, as_of=as_of)
    )
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return True


__all__ = [
    "dispatch_scheduled_family_financial_income_alerts",
    "schedule_scheduled_family_financial_income_alerts",
]
