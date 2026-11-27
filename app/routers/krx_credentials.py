from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_krx_credentials_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/api/user/krx-marketplace-config")
    async def get_user_krx_marketplace_config(request: Request) -> dict:
        username = runtime.get_current_username(request)
        from app.services.user_krx_credentials import krx_credential_status
        return krx_credential_status(username)

    @router.post("/api/user/krx-marketplace-config")
    async def save_user_krx_marketplace_config(request: Request) -> dict:
        username = runtime.get_current_username(request)
        payload = await request.json()
        from app.services.user_krx_credentials import save_user_krx_credentials
        try:
            status = save_user_krx_credentials(username, payload)
        except ValueError as exc:
            raise runtime.HTTPException(status_code=400, detail=str(exc)) from exc
        return {"message": "KRX Data Marketplace 로그인 정보가 사용자 설정에 저장되었습니다.", **status}

    @router.delete("/api/user/krx-marketplace-config")
    async def delete_user_krx_marketplace_config(request: Request) -> dict:
        username = runtime.get_current_username(request)
        from app.services.user_krx_credentials import clear_user_krx_credentials
        clear_user_krx_credentials(username)
        return {"message": "KRX Data Marketplace 로그인 정보가 삭제되었습니다."}

    @router.post("/api/user/krx-marketplace-config/test")
    async def test_user_krx_marketplace_config(request: Request) -> dict:
        username = runtime.get_current_username(request)
        from app.services.ipo.krx_authenticated_client import (
            AuthenticatedKrxHistoricalClient, KrxAuthenticationError,
        )
        if not AuthenticatedKrxHistoricalClient.credentials_configured(username):
            return {"configured": False, "valid": False, "error_code": "NOT_CONFIGURED", "message": "KRX 아이디와 비밀번호가 저장되지 않았습니다."}
        client = AuthenticatedKrxHistoricalClient(username=username)
        try:
            await runtime.asyncio.to_thread(client.verify_credentials)
            return {"configured": True, "valid": True, "message": "KRX Data Marketplace 로그인이 정상적으로 확인되었습니다."}
        except KrxAuthenticationError as exc:
            return {"configured": True, "valid": False, "error_code": "AUTH_ERROR", "message": str(exc)}
        except Exception:
            return {"configured": True, "valid": False, "error_code": "NETWORK_ERROR", "message": "KRX Data Marketplace 연결을 확인할 수 없습니다."}
        finally:
            client.close()

    return router
