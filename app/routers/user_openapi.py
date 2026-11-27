from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_user_openapi_routers(runtime: ModuleType) -> tuple[APIRouter, APIRouter]:
    read_router = APIRouter()
    management_router = APIRouter()

    @read_router.get("/api/user/openapi-config")
    async def get_user_openapi_keys(request: Request) -> dict:
        """현재 로그인한 사용자의 마스킹된 OpenAPI 키 정보 반환"""
        username = runtime.get_current_username(request)
        from app.services.user_openapi import get_masked_user_openapi_config
        return get_masked_user_openapi_config(username)

    @management_router.post("/api/user/openapi-config")
    async def save_user_openapi_keys(request: Request) -> dict:
        """현재 로그인한 사용자의 OpenAPI 키 설정 저장"""
        username = runtime.get_current_username(request)
        payload = await request.json()
        from app.services.user_openapi import save_user_openapi_config
        try:
            save_user_openapi_config(username, payload)
        except ValueError as e:
            raise runtime.HTTPException(status_code=400, detail=str(e))
        return {"message": "증권사 OpenAPI 설정이 안전하게 저장되었습니다."}

    @management_router.post("/api/user/openapi-config/dart/test")
    async def test_user_dart_openapi(request: Request) -> dict:
        """현재 로그인한 사용자의 OpenDART API 키 유효성 확인"""
        username = runtime.get_current_username(request)
        if not username or username == "admin":
            raise runtime.HTTPException(status_code=403, detail="Forbidden")
        from app.services.ipo.dart_client import (
            DartAuthError,
            DartClient,
            DartRateLimitError,
            DartSourceError,
        )
        client = DartClient(username=username)
        if not client.is_configured():
            return {
                "configured": False,
                "valid": False,
                "error_code": "NOT_CONFIGURED",
                "message": "DART API 인증키가 설정되지 않았습니다.",
            }
        try:
            client.verify_credentials()
            return {
                "configured": True,
                "valid": True,
                "source": client.credential_source,
                "message": "OpenDART 연결이 정상적으로 확인되었습니다.",
            }
        except DartAuthError:
            return {"configured": True, "valid": False, "error_code": "AUTH_ERROR", "message": "인증키가 올바르지 않습니다."}
        except DartRateLimitError:
            return {"configured": True, "valid": False, "error_code": "RATE_LIMIT", "message": "일일 요청 한도를 초과했습니다."}
        except DartSourceError:
            return {"configured": True, "valid": False, "error_code": "NETWORK_ERROR", "message": "DART 시스템 오류 또는 점검 중입니다."}
        except Exception:
            return {"configured": True, "valid": False, "error_code": "NETWORK_ERROR", "message": "네트워크 통신 오류가 발생했습니다."}

    @management_router.delete("/api/user/openapi-config/{broker}")
    async def delete_user_openapi_broker(broker: str, request: Request) -> dict:
        """현재 로그인한 사용자의 특정 증권사 또는 OpenDART 설정 및 토큰 삭제"""
        username = runtime.get_current_username(request)
        if broker not in ("toss", "kb", "nh", "kis", "kiwoom", "dart"):
            raise runtime.HTTPException(status_code=400, detail="유효하지 않은 증권사 또는 API 대상입니다.")
        from app.services.user_openapi import delete_user_broker_openapi
        delete_user_broker_openapi(username, broker)
        broker_names = {
            "toss": "토스증권",
            "kb": "KB증권",
            "nh": "나무증권",
            "kis": "한국투자증권",
            "kiwoom": "키움증권",
            "dart": "OpenDART",
        }
        bname = broker_names.get(broker, broker)
        return {"message": f"{bname} 설정이 삭제되었습니다."}

    return read_router, management_router
