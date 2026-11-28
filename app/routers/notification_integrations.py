from __future__ import annotations

from collections.abc import Callable
from types import ModuleType

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse


def create_notification_integrations_router(
    runtime: ModuleType,
) -> tuple[APIRouter, dict[str, Callable[..., HTTPException | HTMLResponse]]]:
    router = APIRouter()

    def _kakao_management_http_error(exc: Exception) -> HTTPException:
        code = str(exc)
        if code in {"KAKAO_OAUTH_UNAVAILABLE", "KAKAO_API_UNAVAILABLE"}:
            status = 502
        elif code in {"KAKAO_OAUTH_STATE_INVALID", "KAKAO_AUTHORIZATION_CODE_INVALID"}:
            status = 400
        else:
            status = 409
        return runtime.HTTPException(status_code=status, detail={"code": code})

    @router.get("/api/settings/kakao")
    async def kakao_settings_status_api(request: Request) -> dict:
        """Return secret-free Kakao self-message configuration for current user."""
        username = runtime.get_current_username(request)
        from app.services.kakao_oauth import safe_kakao_status
        try:
            return safe_kakao_status(username)
        except Exception:
            raise runtime.HTTPException(
                status_code=500, detail={"code": "KAKAO_STATUS_UNAVAILABLE"}
            )

    @router.patch("/api/settings/kakao/secrets")
    async def patch_kakao_app_secrets_api(request: Request) -> dict:
        from app.services.kakao_app_secrets import (
            KakaoAppSecretError,
            kakao_app_secret_status,
            load_stored_kakao_app_secrets,
            update_kakao_app_secrets,
        )
        from app.services.kakao_tokens import (
            KakaoTokenError,
            clear_kakao_tokens,
        )
        username = runtime.get_current_username(request)
        try:
            before = load_stored_kakao_app_secrets(username)
            after = update_kakao_app_secrets(username, await request.json())
            if before["rest_api_key"] != after["rest_api_key"]:
                clear_kakao_tokens(username)
        except (KakaoAppSecretError, KakaoTokenError, ValueError, AttributeError) as exc:
            raise runtime.HTTPException(400, detail={"code": str(exc)}) from exc
        return kakao_app_secret_status(username)

    @router.get("/api/settings/kakao/oauth/start")
    async def kakao_oauth_start_api(request: Request) -> RedirectResponse:
        """Start Kakao Login for the current Wealth user."""
        username = runtime.get_current_username(request)
        from app.services.kakao_oauth import build_authorize_url, KakaoOAuthError
        try:
            url = build_authorize_url(username)
        except KakaoOAuthError as exc:
            raise runtime._kakao_management_http_error(exc) from exc
        return runtime.RedirectResponse(url=url, status_code=302)

    def _kakao_oauth_callback_page(ok: bool, code: str | None = None) -> HTMLResponse:
        """Small popup completion page; never includes OAuth tokens or secrets."""
        from app.services.system_settings import get_effective_system_settings
        origin = get_effective_system_settings().get("public_base_url") or ""
        payload = runtime.json.dumps(
            {
                "type": "wealth:kakao-oauth",
                "ok": bool(ok),
                "code": code if not ok else None,
            },
            ensure_ascii=False,
        )
        target = runtime.json.dumps(origin)
        title = "카카오 연결 완료" if ok else "카카오 연결 실패"
        message = (
            "카카오톡 나에게 보내기 연결이 완료되었습니다."
            if ok
            else "카카오 연결을 완료하지 못했습니다. Wealth 설정에서 다시 시도해 주세요."
        )
        script = ""
        if origin:
            script = (
                "<script>"
                f"if(window.opener){{window.opener.postMessage({payload},{target});}}"
                "setTimeout(function(){window.close();},300);"
                "</script>"
            )
        body = (
            "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<title>{runtime.html.escape(title)}</title></head>"
            "<body style='font-family:sans-serif;padding:24px'>"
            f"<h2>{runtime.html.escape(title)}</h2><p>{runtime.html.escape(message)}</p>"
            f"{script}</body></html>"
        )
        return runtime.HTMLResponse(
            body,
            status_code=200 if ok else 400,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @router.get("/api/integrations/kakao/oauth/callback")
    async def kakao_oauth_callback_api(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> HTMLResponse:
        """Public Kakao OAuth callback bound to a signed Wealth user state."""
        from app.services.kakao_oauth import (
            KakaoOAuthError,
            consume_oauth_state,
            exchange_authorization_code,
        )
        if error:
            return runtime._kakao_oauth_callback_page(False, "KAKAO_OAUTH_REJECTED")
        try:
            username = consume_oauth_state(state or "")
            exchange_authorization_code(username, code or "")
        except KakaoOAuthError as exc:
            return runtime._kakao_oauth_callback_page(False, str(exc))
        return runtime._kakao_oauth_callback_page(True)

    @router.post("/api/settings/kakao/test")
    async def kakao_test_message_api(request: Request) -> dict:
        """Send one user-triggered test message to the current user's Kakao chat."""
        from app.services.notifications.history import record_single_provider_history
        from app.services.notifications.kakao import KakaoSender
        from app.services.notifications.models import NotificationEvent
        username = runtime.get_current_username(request)
        sender = KakaoSender(username=username)
        event = NotificationEvent(
            event_key="integration_test:kakao",
            event_type="integration_test",
            body="✅ Wealth 카카오톡 나에게 보내기 연결 테스트가 성공했습니다.",
            username=username,
        )
        result = await runtime.asyncio.to_thread(sender.send, event)
        try:
            record_single_provider_history(
                username,
                event,
                provider="kakao",
                success=result.success,
                retryable=result.retryable,
                error=result.error_code,
            )
        except Exception:
            pass
        if not result.success:
            status = 502 if result.retryable else 409
            raise runtime.HTTPException(
                status_code=status,
                detail={"code": result.error_code or "KAKAO_SEND_FAILED"},
            )
        return {"ok": True, "message": "카카오톡 테스트 메시지를 전송했습니다."}

    @router.post("/api/settings/kakao/disconnect")
    async def kakao_disconnect_api(request: Request) -> dict:
        """Forget the current user's local Kakao OAuth tokens."""
        from app.services.kakao_tokens import clear_kakao_tokens, KakaoTokenError
        username = runtime.get_current_username(request)
        try:
            clear_kakao_tokens(username)
        except KakaoTokenError as exc:
            raise runtime._kakao_management_http_error(exc) from exc
        return {"ok": True, "message": "Wealth의 카카오 연결 정보를 삭제했습니다."}

    def _telegram_management_http_error(exc: Exception) -> HTTPException:
        code=str(exc)
        status=502 if code in {"TELEGRAM_API_UNAVAILABLE","TELEGRAM_BOT_AUTH_FAILED","TELEGRAM_OPERATION_FAILED"} else 409
        return runtime.HTTPException(status_code=status,detail={"code":code})

    @router.post("/api/settings/telegram/test")
    async def telegram_test_message_api(request: Request) -> dict:
        from app.services.notifications.history import record_single_provider_history
        from app.services.notifications.models import NotificationEvent
        from app.services.telegram_config import resolve_telegram_config
        from app.services.telegram_management import send_test_message,TelegramManagementError
        username = runtime.get_current_username(request)
        event = NotificationEvent(
            event_key="integration_test:telegram",
            event_type="integration_test",
            body="Wealth Telegram 연결 테스트",
            username=username,
        )
        try:
            result = send_test_message(resolve_telegram_config(username))
        except TelegramManagementError as exc:
            try:
                record_single_provider_history(
                    username,
                    event,
                    provider="telegram",
                    success=False,
                    retryable=str(exc) == "TELEGRAM_API_UNAVAILABLE",
                    error=str(exc),
                )
            except Exception:
                pass
            raise runtime._telegram_management_http_error(exc) from exc
        try:
            record_single_provider_history(
                username,
                event,
                provider="telegram",
                success=True,
            )
        except Exception:
            pass
        return result

    @router.get("/api/settings/telegram/status")
    async def telegram_management_status_api(request: Request) -> dict:
        username=runtime.get_current_username(request)
        from app.services.telegram_config import resolve_telegram_config
        from app.services.system_settings import get_effective_system_settings,expected_webhook_url
        from app.services.telegram_management import check_bot,webhook_info,TelegramManagementError
        system=get_effective_system_settings();cfg=resolve_telegram_config(username);expected=expected_webhook_url(system)
        try:bot=check_bot(cfg);hook=webhook_info(cfg,expected)
        except TelegramManagementError as exc: raise runtime._telegram_management_http_error(exc) from exc
        return {"bot":bot,"webhook":hook,"configuration":{"enabled":cfg.enabled,"outbound_configured":cfg.outbound_configured,"interactive_configured":cfg.interactive_configured,"public_base_url_configured":bool(expected),"webhook_owner":system.get("telegram_webhook_owner"),"is_current_owner":system.get("telegram_webhook_owner")==username}}

    @router.post("/api/settings/telegram/webhook/connect")
    async def telegram_webhook_connect_api(request: Request) -> dict:
        if runtime.get_current_role(request)!="admin": raise runtime.HTTPException(status_code=403,detail={"code":"ADMIN_REQUIRED"})
        username=runtime.get_current_username(request)
        from app.services.telegram_config import resolve_telegram_config
        from app.services.system_settings import get_effective_system_settings,expected_webhook_url
        from app.services.telegram_management import connect_webhook,TelegramManagementError
        system=get_effective_system_settings();url=expected_webhook_url(system)
        if system.get("telegram_webhook_owner")!=username: raise runtime.HTTPException(status_code=409,detail={"code":"WEBHOOK_OWNER_MISMATCH"})
        if not url: raise runtime.HTTPException(status_code=409,detail={"code":"PUBLIC_BASE_URL_REQUIRED"})
        try:connect_webhook(resolve_telegram_config(username),url)
        except TelegramManagementError as exc: raise runtime._telegram_management_http_error(exc) from exc
        return {"ok":True,"message":"Telegram webhook을 연결했습니다."}

    @router.post("/api/settings/telegram/webhook/disconnect")
    async def telegram_webhook_disconnect_api(request: Request) -> dict:
        if runtime.get_current_role(request)!="admin": raise runtime.HTTPException(status_code=403,detail={"code":"ADMIN_REQUIRED"})
        username=runtime.get_current_username(request)
        from app.services.telegram_config import resolve_telegram_config
        from app.services.system_settings import get_effective_system_settings
        from app.services.telegram_management import disconnect_webhook,TelegramManagementError
        if get_effective_system_settings().get("telegram_webhook_owner")!=username: raise runtime.HTTPException(status_code=409,detail={"code":"WEBHOOK_OWNER_MISMATCH"})
        try:disconnect_webhook(resolve_telegram_config(username))
        except TelegramManagementError as exc: raise runtime._telegram_management_http_error(exc) from exc
        return {"ok":True,"message":"Telegram webhook 연결을 해제했습니다."}

    return router, {
        "_kakao_management_http_error": _kakao_management_http_error,
        "_kakao_oauth_callback_page": _kakao_oauth_callback_page,
        "_telegram_management_http_error": _telegram_management_http_error,
    }


def create_telegram_webhook_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.post("/api/integrations/telegram/webhook")
    async def telegram_ipo_webhook(request: Request) -> dict:
        """Provider-authenticated Telegram IPO action ingress."""
        from app.services.ipo.telegram_interactive import handle_update, interactive_config
        if interactive_config() is None:
            raise runtime.HTTPException(status_code=503, detail={"code": "TELEGRAM_INTERACTIVE_DISABLED"})
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        try:
            update = await request.json()
        except Exception as exc:
            raise runtime.HTTPException(status_code=400, detail={"code": "INVALID_TELEGRAM_UPDATE"}) from exc
        result = handle_update(update, secret)
        if result == "unauthorized":
            raise runtime.HTTPException(status_code=403, detail={"code": "TELEGRAM_UNAUTHORIZED"})
        return {"status": result}

    return router
