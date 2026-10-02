from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from app.services.ipo.orchestrator import _run_kis_schedule_fetch, run_ipo_daily_pipeline
from app.services.ipo.reminders import _run_reminders_locked
from app.services.ipo.store import get_ipo_calendar_events


IPO = {
    "ipo_id": "jincostech-20261002",
    "company_name": "진코스텍",
    "stock_code": "250030",
    "subscription_start": "2026-10-02",
    "subscription_end": "2026-10-06",
    "expected_listing_date": "2026-10-14",
    "lead_managers": ["하나증권"],
}


class _FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.saved = False

    def load_state(self):
        return {"sent_keys": {}}

    def save_state(self, _state):
        self.saved = True

    def dispatch_message(self, _key, message, _state, reply_markup=None):
        self.messages.append(message)
        return True


def _apps():
    return {
        "family_members": ["아빠", "엄마", "자녀"],
        "applications": {
            IPO["ipo_id"]: {
                "target_owners": ["아빠", "엄마", "자녀"],
                "applied_owners": [],
            }
        },
    }


def test_calendar_projects_only_subscription_first_and_last_day() -> None:
    with patch("app.services.ipo.store.read_market_store", return_value={"ipos": [dict(IPO)]}):
        events = get_ipo_calendar_events(None, "2026-10-01", "2026-10-31")

    subscription_events = [event for event in events if event["type"] == "ipo_subscription"]
    assert [event["date"] for event in subscription_events] == ["2026-10-02", "2026-10-06"]
    assert [event["title"] for event in subscription_events] == [
        "🎯 진코스텍 청약 첫째날",
        "🎯 진코스텍 청약 마지막날",
    ]
    assert [event["meta"]["subscription_phase"] for event in subscription_events] == ["first", "last"]
    assert not any(event["date"] in {"2026-10-03", "2026-10-04", "2026-10-05"} for event in subscription_events)


def test_single_day_subscription_is_projected_once() -> None:
    single = {**IPO, "subscription_start": "2026-10-06", "subscription_end": "2026-10-06"}
    with patch("app.services.ipo.store.read_market_store", return_value={"ipos": [single]}):
        events = get_ipo_calendar_events(None, "2026-10-01", "2026-10-31")

    subscription_events = [event for event in events if event["type"] == "ipo_subscription"]
    assert len(subscription_events) == 1
    assert subscription_events[0]["date"] == "2026-10-06"
    assert subscription_events[0]["title"] == "🎯 진코스텍 청약일"
    assert subscription_events[0]["meta"]["subscription_phase"] == "single"


def test_subscription_reminders_only_run_on_boundary_days_with_phase_wording() -> None:
    middle = _FakeNotifier()
    middle_result = _run_reminders_locked(
        middle, {"ipos": [dict(IPO)]}, _apps(), date(2026, 10, 3), "1500", None, is_last_slot=True,
    )
    assert middle_result["eligible_ipos"] == 0
    assert middle.messages == []

    first = _FakeNotifier()
    first_result = _run_reminders_locked(
        first, {"ipos": [dict(IPO)]}, _apps(), date(2026, 10, 2), "1500", None, is_last_slot=True,
    )
    assert first_result["notifications_sent_count"] == 1
    assert "공모주 청약 첫째날 — 15:00" in first.messages[0]
    assert "청약 마감 시간이 가까워지고 있습니다" not in first.messages[0]

    last = _FakeNotifier()
    last_result = _run_reminders_locked(
        last, {"ipos": [dict(IPO)]}, _apps(), date(2026, 10, 6), "1500", None, is_last_slot=True,
    )
    assert last_result["notifications_sent_count"] == 1
    assert "공모주 청약 마지막날 — 15:00" in last.messages[0]
    assert "청약 마감 시간이 가까워지고 있습니다" in last.messages[0]


def test_kis_subscription_and_listing_schedule_requests_start_concurrently() -> None:
    started: set[str] = set()
    kis = MagicMock()

    async def subscriptions(*_args):
        started.add("subscriptions")
        import asyncio
        await asyncio.sleep(0)
        assert "listings" in started
        return []

    async def listings(*_args):
        started.add("listings")
        import asyncio
        await asyncio.sleep(0)
        assert "subscriptions" in started
        return []

    kis.fetch_ipo_subscription_schedule.side_effect = subscriptions
    kis.fetch_listing_schedule.side_effect = listings

    assert _run_kis_schedule_fetch(kis, "2026-10-01", "2026-10-31") == ([], [])


def test_routine_refresh_never_scans_full_historical_confirmation_sources() -> None:
    kis = MagicMock()
    kis.configured = True

    async def subscriptions(*_args):
        return [dict(IPO)]

    async def listings(*_args):
        return []

    kis.fetch_ipo_subscription_schedule.side_effect = subscriptions
    kis.fetch_listing_schedule.side_effect = listings

    krx = MagicMock()
    naver = MagicMock()
    dart = MagicMock()
    dart.is_configured.return_value = False

    with patch("app.services.ipo.orchestrator.read_market_store", return_value={"schema_version": 1, "ipos": []}), \
         patch("app.services.ipo.orchestrator.write_market_store"):
        result = run_ipo_daily_pipeline(
            kis_client=kis,
            krx_client=krx,
            naver_client=naver,
            dart_client=dart,
            target_date_str="2026-10-02",
            market_only=True,
        )

    assert result["status"] == "ok"
    assert result["sources"]["krx"] == "not_requested (historical_sync_only)"
    assert result["sources"]["naver"] == "not_requested (historical_sync_only)"
    krx.fetch_listed_master.assert_not_called()
    naver.fetch_completed_listings.assert_not_called()
