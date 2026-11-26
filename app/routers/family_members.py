from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager

from fastapi import APIRouter, HTTPException, Request


def create_family_members_router(
    *,
    get_current_username: Callable[[Request], str],
    financial_user_locks: Callable[..., AbstractContextManager[None]],
    read_portfolio: Callable[..., dict],
    write_portfolio: Callable[..., None],
    get_family_members: Callable[[dict], list],
) -> APIRouter:
    family_members_router = APIRouter()

    @family_members_router.get("/api/family-members")
    async def list_family_members(request: Request) -> dict:
        username = get_current_username(request)
        data = read_portfolio(username=username)
        return {"members": get_family_members(data)}

    @family_members_router.post("/api/family-members")
    async def add_family_member(request: Request) -> dict:
        username = get_current_username(request)
        body = await request.json()
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(400, "이름을 입력해 주세요.")
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            members = get_family_members(data)
            if name in members:
                raise HTTPException(409, "이미 존재하는 이름입니다.")
            members.append(name)
            data.setdefault("settings", {})["family_members"] = members
            write_portfolio(data, username=username)
            return {"members": members, "message": f"'{name}' 구성원을 추가했습니다."}

    @family_members_router.put("/api/family-members/{old_name}")
    async def rename_family_member(old_name: str, request: Request) -> dict:
        username = get_current_username(request)
        body = await request.json()
        new_name = (body.get("name") or "").strip()
        if not new_name:
            raise HTTPException(400, "새 이름을 입력해 주세요.")
        from app.services.family_members import (
            FamilyMemberRenameError,
            IpoApplicantRenameCollision,
            rename_family_member_references,
        )
        try:
            result = rename_family_member_references(username, old_name, new_name)
        except FamilyMemberRenameError as exc:
            code = str(exc)
            if isinstance(exc, IpoApplicantRenameCollision):
                raise HTTPException(409, detail={"code": "IPO_APPLICANT_RENAME_COLLISION", "message": "IPO applicant rename conflicts"}) from exc
            if code == "FAMILY_MEMBER_NOT_FOUND":
                raise HTTPException(404, "구성원을 찾지 못했습니다.") from exc
            if code == "FAMILY_MEMBER_EXISTS":
                raise HTTPException(409, "이미 존재하는 이름입니다.") from exc
            raise HTTPException(400, "가족 구성원 이름을 변경할 수 없습니다.") from exc
        return {"members": result["members"], "ipo_revision": result["ipo_revision"],
                "message": f"'{old_name}' -> '{new_name}'으로 이름을 변경했습니다."}

    @family_members_router.delete("/api/family-members/{member_name}")
    async def delete_family_member(member_name: str, request: Request) -> dict:
        username = get_current_username(request)
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            members = get_family_members(data)
            if member_name not in members:
                raise HTTPException(404, "구성원을 찾지 못했습니다.")
            members = [m for m in members if m != member_name]
            data.setdefault("settings", {})["family_members"] = members
            # Reset owner on accounts that belonged to deleted member
            for acct in data.get("accounts", []):
                if acct.get("owner") == member_name:
                    acct["owner"] = "모두"
            write_portfolio(data, username=username)
            return {"members": members, "message": f"'{member_name}' 구성원을 삭제했습니다."}

    return family_members_router
