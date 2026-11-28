from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter


def create_market_data_routers(runtime: ModuleType) -> tuple[APIRouter, APIRouter]:
    overview_router = APIRouter()
    quotes_router = APIRouter()

    @overview_router.get("/api/market-overview")
    async def market_overview() -> dict:
        try:
            return await runtime.fetch_market_overview()
        except Exception:
            from app.services.market_indicators import unavailable_market_indicators
            return {"markets": [], "exchange_rate": None, "unavailable": True, **unavailable_market_indicators()}

    @quotes_router.get("/api/stock-chart/{code}")
    async def get_stock_chart(code: str, period: str = "1M") -> dict:
        return await runtime.fetch_stock_chart_data(code, period)

    @quotes_router.get("/api/stock-search")
    async def stock_search(q: str = "") -> dict:
        from app.services.stock_master import async_search_stock_by_name
        return await async_search_stock_by_name(q)

    return overview_router, quotes_router
