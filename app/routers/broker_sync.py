from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_broker_sync_routers(runtime: ModuleType) -> tuple[APIRouter, APIRouter]:
    broker_router = APIRouter()
    all_accounts_router = APIRouter()

    async def sync_broker(request, sync_for_user) -> dict:
        # Keep the legacy default for direct Python calls without a request.
        username = runtime.get_current_username(request) if request else "sagesaint"
        return await sync_for_user(username=username)

    @broker_router.post("/api/sync/kb")
    async def sync_kb(request: Request = None) -> dict:
        return await sync_broker(request, runtime.sync_kb_for_user)

    @broker_router.post("/api/sync/toss")
    async def sync_toss(request: Request = None) -> dict:
        return await sync_broker(request, runtime.sync_toss_for_user)

    @broker_router.post("/api/sync/namoo")
    async def sync_namoo(request: Request = None) -> dict:
        return await sync_broker(request, runtime.sync_namoo_for_user)

    @broker_router.post("/api/sync/kis")
    async def sync_kis(request: Request = None) -> dict:
        return await sync_broker(request, runtime.sync_kis_for_user)

    @broker_router.post("/api/sync/kiwoom")
    async def sync_kiwoom(request: Request = None) -> dict:
        return await sync_broker(request, runtime.sync_kiwoom_for_user)

    @all_accounts_router.post("/api/sync/all")
    async def sync_all_accounts(request: Request) -> dict:
        username = runtime.get_current_username(request)
        return await runtime.sync_all_accounts_for_user(username=username)

    return broker_router, all_accounts_router
