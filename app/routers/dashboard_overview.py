from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_dashboard_overview_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/api/dashboard")
    async def dashboard(request: Request, record_snapshots: bool = False) -> dict:
        username = runtime.get_current_username(request)
        return runtime.get_full_dashboard_for_user(username=username, record_snapshots=record_snapshots)

    @router.get("/api/dividends")
    async def get_dividends(request: Request, owner: str = "모두") -> dict:
        """Return dividend summary and 12-month schedule for holdings."""
        username = runtime.get_current_username(request)
        return await runtime._get_dividend_overview(username, owner)

    return router
