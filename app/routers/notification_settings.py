from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request


def create_notification_settings_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/api/settings/notifications")
    async def get_notification_settings(request: Request) -> dict:
        from app.services.settings import get_effective_settings
        from app.services.telegram_config import telegram_secret_status
        username=runtime.get_current_username(request); result=get_effective_settings(username); result["telegram"].update(telegram_secret_status(username))
        return {"version": result["version"], "telegram": result["telegram"], "discord": result["discord"], "kakao": result["kakao"]}

    @router.patch("/api/settings/notifications")
    async def patch_notification_settings(request: Request) -> dict:
        from app.services.settings import patch_settings, SettingsValidationError
        body = await request.json()
        if not isinstance(body, dict):
            raise runtime.HTTPException(400, detail={"code": "INVALID_PATCH"})
        provider_keys = {"telegram", "discord", "kakao"}
        if set(body) & provider_keys:
            if set(body) - provider_keys:
                raise runtime.HTTPException(400, detail={"code": "INVALID_PATCH"})
            patch = {key: body[key] for key in provider_keys if key in body}
        else:
            # Backward-compatible direct Telegram payload.
            patch = {"telegram": body}
        username = runtime.get_current_username(request)
        try: result=patch_settings(username, patch)
        except (SettingsValidationError, ValueError, AttributeError) as exc: raise runtime.HTTPException(400, detail={"code":str(exc)}) from exc
        from app.services.telegram_config import telegram_secret_status
        result["telegram"].update(telegram_secret_status(username))
        return {"version":result["version"],"telegram":result["telegram"],"discord":result["discord"],"kakao":result["kakao"]}

    @router.get("/api/settings/notifications/history")
    async def get_notification_history_api(request: Request, limit: int = 20) -> dict:
        from app.services.notifications.history import (
            NotificationHistoryError,
            list_notification_history,
        )
        username = runtime.get_current_username(request)
        try:
            return list_notification_history(username, limit=limit)
        except ValueError as exc:
            raise runtime.HTTPException(400, detail={"code": str(exc)}) from exc
        except NotificationHistoryError as exc:
            raise runtime.HTTPException(
                500, detail={"code": "NOTIFICATION_HISTORY_UNAVAILABLE"}
            ) from exc

    @router.delete("/api/settings/notifications/history")
    async def clear_notification_history_api(request: Request) -> dict:
        from app.services.notifications.history import (
            NotificationHistoryError,
            clear_notification_history,
        )
        username = runtime.get_current_username(request)
        try:
            deleted = clear_notification_history(username)
        except NotificationHistoryError as exc:
            raise runtime.HTTPException(
                500, detail={"code": "NOTIFICATION_HISTORY_UNAVAILABLE"}
            ) from exc
        return {"ok": True, "deleted_count": deleted}

    @router.patch("/api/settings/telegram/secrets")
    async def patch_telegram_secrets(request: Request) -> dict:
        from app.services.telegram_secrets import update_telegram_secrets, TelegramSecretError
        from app.services.telegram_config import resolve_telegram_config
        username=runtime.get_current_username(request)
        try: update_telegram_secrets(username, await request.json())
        except (TelegramSecretError, ValueError, AttributeError) as exc: raise runtime.HTTPException(400,detail={"code":str(exc)}) from exc
        cfg=resolve_telegram_config(username)
        return {"bot_token_configured":bool(cfg.bot_token),"bot_token_source":cfg.bot_token_source,"webhook_secret_configured":bool(cfg.webhook_secret),"webhook_secret_source":cfg.webhook_secret_source}

    @router.get("/api/settings/discord")
    async def get_discord_settings(request: Request) -> dict:
        from app.services.discord_secrets import discord_secret_status
        return discord_secret_status(runtime.get_current_username(request))

    @router.patch("/api/settings/discord/secrets")
    async def patch_discord_secrets(request: Request) -> dict:
        from app.services.discord_secrets import (
            DiscordSecretError,
            discord_secret_status,
            update_discord_secrets,
        )
        username = runtime.get_current_username(request)
        try:
            update_discord_secrets(username, await request.json())
        except (DiscordSecretError, ValueError, AttributeError) as exc:
            raise runtime.HTTPException(400, detail={"code": str(exc)}) from exc
        return discord_secret_status(username)

    @router.post("/api/settings/discord/test")
    async def discord_test_message_api(request: Request) -> dict:
        from app.services.notifications.discord import DiscordSender
        from app.services.notifications.history import record_single_provider_history
        from app.services.notifications.models import NotificationEvent
        username = runtime.get_current_username(request)
        event = NotificationEvent(
            event_key="integration_test:discord",
            event_type="integration_test",
            body="✅ Wealth Discord 연결 테스트가 성공했습니다.",
            username=username,
        )
        result = await runtime.asyncio.to_thread(
            DiscordSender(username=username).send,
            event,
        )
        try:
            record_single_provider_history(
                username,
                event,
                provider="discord",
                success=result.success,
                retryable=result.retryable,
                error=result.error_code,
            )
        except Exception:
            pass
        if not result.success:
            raise runtime.HTTPException(
                status_code=502 if result.retryable else 409,
                detail={"code": result.error_code or "DISCORD_SEND_FAILED"},
            )
        return {"ok": True, "message": "Discord 테스트 메시지를 전송했습니다."}

    @router.get("/api/settings/automation")
    async def get_automation_settings(request: Request) -> dict:
        from app.services.settings import get_effective_settings
        result=get_effective_settings(runtime.get_current_username(request)); return {"version":result["version"],"automation":result["automation"]}

    @router.patch("/api/settings/automation")
    async def patch_automation_settings(request: Request) -> dict:
        from app.services.settings import patch_settings, SettingsValidationError
        body = await request.json()
        try: result=patch_settings(runtime.get_current_username(request), {"automation": body.get("automation", body)})
        except (SettingsValidationError, ValueError, AttributeError) as exc: raise runtime.HTTPException(400, detail={"code":str(exc)}) from exc
        return {"version":result["version"],"automation":result["automation"]}

    @router.get("/api/settings/system")
    async def get_system_settings_api(request: Request) -> dict:
        username=runtime.get_current_username(request)
        from app.services.system_settings import get_effective_system_settings
        # Generic system settings are visible to ordinary users.  Do not append
        # Toss executable/config/session filesystem metadata here; own-session
        # status is deliberately available only through the explicit endpoint.
        return {**get_effective_system_settings(),"can_manage":runtime.get_current_role(request)=="admin","current_username":username}

    @router.patch("/api/settings/system")
    async def patch_system_settings_api(request: Request) -> dict:
        if runtime.get_current_role(request)!="admin": raise runtime.HTTPException(status_code=403,detail={"code":"ADMIN_REQUIRED"})
        from app.services.system_settings import patch_system_settings, SystemSettingsError
        try:return {**patch_system_settings(await request.json()),"can_manage":True,"current_username":runtime.get_current_username(request)}
        except (SystemSettingsError,ValueError,AttributeError) as exc: raise runtime.HTTPException(status_code=400,detail={"code":str(exc)}) from exc

    return router
