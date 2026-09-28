from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.services import dividend_intelligence_async as async_bridge


class DividendIntelligenceAsyncRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        async_bridge._BACKGROUND_TASKS.clear()

    async def asyncTearDown(self) -> None:
        async_bridge._BACKGROUND_TASKS.clear()

    @patch("app.services.dividend_intelligence_async._enabled", return_value=True)
    @patch(
        "app.services.tax.family_financial_income.get_family_financial_income_risk_for_user",
        new_callable=AsyncMock,
    )
    @patch("app.services.dividend_intelligence.dispatch_family_financial_income_alerts")
    async def test_directly_created_task_is_retained_until_dispatch_finishes(
        self, dispatch, get_risk, _enabled
    ) -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def delayed_risk(username: str, *, as_of: str):
            entered.set()
            await release.wait()
            return {"year": 2026, "members": []}

        get_risk.side_effect = delayed_risk
        dispatch.return_value = {"status": "no_new_events", "sent_count": 0}

        task = asyncio.create_task(
            async_bridge.dispatch_scheduled_family_financial_income_alerts(
                "tester", as_of="2026-09-28"
            )
        )
        await entered.wait()
        self.assertIn(task, async_bridge._BACKGROUND_TASKS)

        release.set()
        result = await task

        self.assertEqual(result["status"], "no_new_events")
        self.assertNotIn(task, async_bridge._BACKGROUND_TASKS)


if __name__ == "__main__":
    unittest.main()
