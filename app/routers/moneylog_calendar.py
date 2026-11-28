from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Query, Request


def create_moneylog_calendar_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/api/moneylog/calendar")
    async def get_moneylog_calendar(
        request: Request,
        from_date: str = Query(..., alias="from"),
        to_date: str = Query(..., alias="to"),
        owner: str = "모두",
    ) -> dict:
        """Return unified calendar events for realized PnL, dividends, interest, ledger, and IPOs."""
        username = runtime.get_current_username(request)
        try:
            from app.services.ipo.calendar import build_moneylog_calendar_events
            events = build_moneylog_calendar_events(username, from_date, to_date, owner)
            return {
                "from": from_date,
                "to": to_date,
                "owner": owner,
                "events": events,
            }
        except ValueError as exc:
            raise runtime.HTTPException(status_code=400, detail=str(exc)) from exc

    return router
