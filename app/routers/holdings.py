from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.portfolio import normalize_holding, upsert_holdings


class HoldingCreate(BaseModel):
    account_id: str | None = Field(default=None, max_length=100)
    broker: str = Field(min_length=1, max_length=60)
    account_name: str = Field(min_length=1, max_length=80)
    code: str = Field(default="", max_length=20)
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0)
    avg_price: float = Field(ge=0)
    current_price: float = Field(ge=0)
    currency: str = "KRW"
    market: str = ""
    owner: str = "모두"


def create_holdings_routers(
    *,
    get_current_username: Callable[[Request], str],
    financial_user_locks: Callable[..., AbstractContextManager[None]],
    read_portfolio: Callable[..., dict],
    write_portfolio: Callable[..., None],
    get_family_members: Callable[[dict], list],
    get_dashboard: Callable[..., dict],
) -> tuple[APIRouter, APIRouter, APIRouter]:
    holdings_clear_router = APIRouter()
    holdings_collection_router = APIRouter()
    holding_update_router = APIRouter()

    @holdings_clear_router.post("/api/holdings/clear")
    async def clear_holdings_endpoint(request: Request) -> dict:
        """Clear all portfolio holdings."""
        username = get_current_username(request)
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            data["holdings"] = []
            write_portfolio(data, username=username)
            return {"message": "모든 보유종목이 삭제되었습니다."}

    @holdings_collection_router.get("/api/holdings/signals")
    async def get_holding_signals(request: Request, owner: str = "모두") -> JSONResponse:
        from app.services.portfolio import read_portfolio_readonly
        from app.services.holding_signals import holdings_signals
        snapshot = read_portfolio_readonly(get_current_username(request))
        if owner not in set(get_family_members(snapshot)) | {"모두"}:
            raise HTTPException(400, "등록된 가족 구성원을 선택해 주세요.")
        return JSONResponse(await holdings_signals(snapshot, owner), headers={"Cache-Control": "no-store"})

    @holdings_collection_router.post("/api/holdings", status_code=201)
    async def create_holding(payload: HoldingCreate, request: Request) -> dict:
        username = get_current_username(request)
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            from app.services.holding_accounts import resolve_holding_account
            if payload.owner not in set(get_family_members(data)) | {"모두"}:
                raise HTTPException(400, "등록된 가족 구성원을 선택해 주세요.")
            try:
                account = resolve_holding_account(data, payload.model_dump())
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            item = normalize_holding(payload.model_dump(), account["id"], account["broker"], account["name"], "manual")
            upsert_holdings(data, [item])
            write_portfolio(data, username=username)
            return {"message": "보유종목을 저장했습니다.", "dashboard": get_dashboard(username=username)}

    @holdings_collection_router.delete("/api/holdings/{holding_id}")
    async def delete_holding(holding_id: str, request: Request) -> dict:
        username = get_current_username(request)
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            before = len(data["holdings"])
            data["holdings"] = [holding for holding in data["holdings"] if holding["id"] != holding_id]
            if before == len(data["holdings"]):
                raise HTTPException(404, "보유종목을 찾지 못했습니다.")
            # Registered accounts (including empty AccountInfo imports) survive a
            # holding deletion. Account removal has its own explicit endpoint.
            write_portfolio(data, username=username)
            return {"message": "보유종목을 삭제했습니다."}

    @holding_update_router.put("/api/holdings/{holding_id}")
    async def update_holding(holding_id: str, payload: HoldingCreate, request: Request) -> dict:
        username = get_current_username(request)
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            current = next((item for item in data["holdings"] if item["id"] == holding_id), None)
            if current is None:
                raise HTTPException(404, "보유종목을 찾지 못했습니다.")
            from app.services.holding_accounts import resolve_holding_account
            if payload.owner not in set(get_family_members(data)) | {"모두"}:
                raise HTTPException(400, "등록된 가족 구성원을 선택해 주세요.")
            try:
                account = resolve_holding_account(data, payload.model_dump(), current=current)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            item = normalize_holding(payload.model_dump(), account["id"], account["broker"], account["name"], current.get("source", "manual"))
            item["id"] = holding_id
            data["holdings"] = [item if holding["id"] == holding_id else holding for holding in data["holdings"]]
            write_portfolio(data, username=username)
            return {"message": "보유종목을 수정했습니다.", "dashboard": get_dashboard(username=username)}

    return holdings_clear_router, holdings_collection_router, holding_update_router
