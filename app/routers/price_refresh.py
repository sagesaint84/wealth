from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_price_refresh_routers(runtime: ModuleType) -> tuple[APIRouter, APIRouter]:
    fx_router = APIRouter()
    prices_router = APIRouter()

    @fx_router.post("/api/fx/refresh")
    async def refresh_fx_rate(request: Request) -> dict:
        username = runtime.get_current_username(request)
        return await runtime.refresh_fx_for_user(username=username)

    @prices_router.post("/api/refresh-prices")
    async def refresh_prices(request: Request) -> dict:
        username = runtime.get_current_username(request)
        return await runtime.refresh_prices_for_user(username=username)

    return fx_router, prices_router
