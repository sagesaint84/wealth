from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_demo_reset_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.post("/api/demo")
    async def load_demo(request: Request) -> dict:
        username = runtime.get_current_username(request)
        runtime.seed_demo(username=username)
        return {"message": "예시 데이터를 불러왔습니다."}

    @router.post("/api/clear")
    async def clear_all(request: Request) -> dict:
        username = runtime.get_current_username(request)
        with runtime.financial_user_locks(username, 'portfolio.json'):
            data = runtime.read_portfolio(username=username)
            data["holdings"] = []
            data["accounts"] = []
            runtime.write_portfolio(data, username=username)
            return {"message": "저장된 보유내역을 모두 지웠습니다."}

    return router
