from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_admin_users_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/api/admin/users")
    async def admin_list_users(request: Request) -> dict:
        """(Admin 전용) 등록된 모든 사용자 목록 반환"""
        if runtime.get_current_role(request) != "admin":
            raise runtime.HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        from app.services.user_manager import list_users
        return {"users": list_users()}

    @router.post("/api/admin/users")
    async def admin_create_user(request: Request) -> dict:
        """(Admin 전용) 신규 사용자 생성 (초기 4자리 비밀번호, must_change_password=True)"""
        if runtime.get_current_role(request) != "admin":
            raise runtime.HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        body = await request.json()
        uname = str(body.get("username", "")).strip()
        init_pw = str(body.get("initial_password", "")).strip()
        from app.services.user_manager import create_new_user
        try:
            create_new_user(uname, init_pw)
            return {"message": f"사용자 '{uname}'(이)가 생성되었습니다. (초기 비밀번호: {init_pw})"}
        except Exception as e:
            raise runtime.HTTPException(status_code=400, detail=str(e))

    @router.post("/api/admin/users/{target_username}/reset-password")
    async def admin_reset_user_password(target_username: str, request: Request) -> dict:
        """(Admin 전용) 사용자 비밀번호를 4자리로 초기화"""
        if runtime.get_current_role(request) != "admin":
            raise runtime.HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        body = await request.json()
        new_pw_4digit = str(body.get("new_password", "")).strip()
        from app.services.user_manager import admin_reset_password_to_4digit
        try:
            admin_reset_password_to_4digit(target_username, new_pw_4digit)
            return {"message": f"'{target_username}'의 비밀번호가 '{new_pw_4digit}'(으)로 초기화되었습니다."}
        except Exception as e:
            raise runtime.HTTPException(status_code=400, detail=str(e))

    @router.delete("/api/admin/users/{target_username}")
    async def admin_delete_user(target_username: str, request: Request) -> dict:
        """(Admin 전용) 사용자 계정 삭제"""
        if runtime.get_current_role(request) != "admin":
            raise runtime.HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
        from app.services.user_manager import delete_user_account
        try:
            delete_user_account(target_username)
            return {"message": f"사용자 '{target_username}' 계정이 삭제되었습니다."}
        except Exception as e:
            raise runtime.HTTPException(status_code=400, detail=str(e))

    return router
