from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_price_refresh_routers(runtime: ModuleType) -> tuple[APIRouter, APIRouter]:
    fx_router = APIRouter()
    prices_router = APIRouter()

    @fx_router.post("/api/fx/refresh")
    async def refresh_fx_rate(request: Request) -> dict:
        username = runtime.get_current_username(request)
        rate = await runtime.fetch_fx_rate_usd_krw()
        with runtime.financial_user_locks(username, 'portfolio.json'):
            data = runtime.read_portfolio(username=username)
            data["settings"]["fx_rates"]["USD"] = rate
            now_str = runtime.datetime.now().astimezone().isoformat(timespec="seconds")
            data["settings"]["fx_info"] = {"source": "실시간 웹 환율", "rate": rate, "updated_at": now_str}
            data["settings"]["fx_updated_at"] = now_str
            runtime.write_portfolio(data, username=username)
            return {"message": f"실시간 환율(USD/KRW: {rate:,.1f}원)을 반영했습니다.", "rate": rate}

    @prices_router.post("/api/refresh-prices")
    async def refresh_prices(request: Request) -> dict:
        username = runtime.get_current_username(request)
        return await runtime.refresh_prices_for_user(username=username)

    return fx_router, prices_router
