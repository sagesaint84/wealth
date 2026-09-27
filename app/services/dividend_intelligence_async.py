"""Async bridge for Phase 10.5D scheduled financial-income alerts.

Daily-close snapshot persistence is synchronous, while the existing B-1 family
risk builder is asynchronous.  This bridge keeps the storage path non-fatal and
ensures threshold alerts are calculated only from B-1's *individual* member
results.  The family reference total is never thresholded.
"""
from __future__ import annotations

from typing import Any


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
    """Build B-1 member risk and dispatch opt-in threshold alerts safely."""
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


__all__ = ["dispatch_scheduled_family_financial_income_alerts"]
