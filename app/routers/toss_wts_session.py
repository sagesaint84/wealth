from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse


def create_toss_wts_session_router(runtime: ModuleType) -> APIRouter:
    # Use live app bindings for authentication and existing caller patches.
    router = APIRouter()

    # User settings
    @router.get("/api/settings/toss-wts")
    async def get_toss_wts_settings_api(request: Request) -> dict:
        username = runtime.get_current_username(request)
        from app.services.settings import get_effective_settings
        from app.services.system_settings import resolve_toss_wts_settings
        system = resolve_toss_wts_settings()
        allowed = set(system.get("allowed_users") or [])
        return {"toss_wts": {"enabled": system["enabled"], "allowed": not allowed or username in allowed, "expected_version": system["expected_version"], "session_check_enabled": get_effective_settings(username).get("toss_wts", {}).get("session_check_enabled", False)}, "can_manage_global": runtime.get_current_role(request)=="admin"}

    @router.patch("/api/settings/toss-wts")
    async def patch_toss_wts_settings_api(request: Request) -> dict:
        username = runtime.get_current_username(request)
        from app.services.settings import patch_settings, SettingsError
        try: body=await request.json()
        except Exception: body=None
        if not isinstance(body, dict) or set(body) != {"session_check_enabled"} or type(body["session_check_enabled"]) is not bool:
            raise runtime.HTTPException(status_code=400,detail={"code":"TOSS_WTS_SESSION_CHECK_ENABLED_INVALID"})
        try:
            updated = patch_settings(username, {"toss_wts": body})
            return {"toss_wts": {"session_check_enabled": updated["toss_wts"]["session_check_enabled"]}}
        except (SettingsError, ValueError, AttributeError) as exc: raise runtime.HTTPException(status_code=400,detail={"code":str(exc)}) from exc

    # Session status and extension
    @router.post("/api/settings/toss-wts/status")
    async def toss_wts_session_status_api(request: Request) -> dict:
        """Return the current user's Toss WTS session status.

    Any authenticated user can check their own session.
    Username is always derived from the session — never from request body.
    """
        username = runtime.get_current_username(request)
        if not runtime._toss_wts_user_allowed(username):
            raise runtime.HTTPException(status_code=403, detail={"code": "TOSS_WTS_NOT_ALLOWED"})
        from app.services.toss_wts_session import get_toss_session_status
        from app.services.system_settings import resolve_toss_wts_settings
        return get_toss_session_status(username=username, settings=resolve_toss_wts_settings())

    @router.post("/api/settings/toss-wts/session/extend")
    async def toss_wts_session_extend_api(request: Request) -> JSONResponse:
        """Start only the logged-in user's extension; no client command/config fields."""
        headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
        try:
            username = runtime.get_current_username(request)
        except runtime.HTTPException as exc:
            exc.headers = {**(exc.headers or {}), **headers}
            raise
        if not runtime._toss_wts_user_allowed(username):
            raise runtime.HTTPException(status_code=403, detail={"code": "TOSS_WTS_NOT_ALLOWED"}, headers=headers)
        from app.services.toss_wts_session import start_toss_session_extension
        result = await runtime.asyncio.to_thread(start_toss_session_extension, username)
        if result.get("action") == "deferred":
            raise runtime.HTTPException(status_code=409, detail={"code": result["error_code"]}, headers=headers)
        return runtime.JSONResponse(result, headers=headers)


    @router.get("/api/settings/toss-wts/session/extension")
    async def toss_wts_session_extension_status_api(request: Request) -> JSONResponse:
        """Reconnect to the user's persisted result; does not resubmit extension."""
        headers = {"Cache-Control": "no-store", "Pragma": "no-cache"}
        try:
            username = runtime.get_current_username(request)
        except runtime.HTTPException as exc:
            exc.headers = {**(exc.headers or {}), **headers}
            raise
        if not runtime._toss_wts_user_allowed(username):
            raise runtime.HTTPException(status_code=403, detail={"code": "TOSS_WTS_NOT_ALLOWED"}, headers=headers)
        from app.services.toss_wts_session import get_toss_session_extension
        result = await runtime.asyncio.to_thread(get_toss_session_extension, username)
        return runtime.JSONResponse(result, headers=headers)


    # Login attempts and QR
    @router.post("/api/settings/toss-wts/login/start")
    async def toss_wts_login_start_api(request: Request) -> dict:
        """Start a per-user background tossctl auth login attempt.

    Any authenticated user can start their own Toss login.
    Username is always derived from the authenticated session — the request
    body MUST NOT contain a username field that would be trusted.

    Request body (optional JSON):
        reauthenticate: bool  — if true, bypasses TOSS_SESSION_ALREADY_VALID check.
                                UI must show explicit confirmation before sending true.
    """
        username = runtime.get_current_username(request)
        if not runtime._toss_wts_user_allowed(username):
            raise runtime.HTTPException(status_code=403, detail={"code": "TOSS_WTS_NOT_ALLOWED"})
        from app.services.toss_wts_login import (
            start_toss_login, TossLoginLockError, TossLoginFlagUnverifiedError,
            TossLoginError, TossSessionAlreadyValidError,
        )
        from app.services.system_settings import resolve_toss_wts_settings
        settings = resolve_toss_wts_settings()
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict) or "reauthenticate" in body and type(body["reauthenticate"]) is not bool:
            raise runtime.HTTPException(status_code=400, detail={"code":"TOSS_REAUTHENTICATE_INVALID"})
        reauthenticate = body.get("reauthenticate", False)
        try:
            attempt_id = await runtime.asyncio.to_thread(
                start_toss_login, settings, username=username, reauthenticate=reauthenticate
            )
            return {"attempt_id": attempt_id, "status": "pending"}
        except TossLoginFlagUnverifiedError as exc:
            raise runtime.HTTPException(status_code=501, detail={"code":"AUTH_LOGIN_FLAG_UNVERIFIED"}) from exc
        except TossSessionAlreadyValidError:
            raise runtime.HTTPException(status_code=409, detail={"code":"TOSS_SESSION_ALREADY_VALID"})
        except TossLoginLockError:
            raise runtime.HTTPException(status_code=409, detail={"code":"TOSS_AUTH_OPERATION_BUSY"})
        except TossLoginError:
            raise runtime.HTTPException(status_code=500, detail={"code":"AUTH_LOGIN_FAILED"})

    @router.get("/api/settings/toss-wts/login/{attempt_id}")
    async def toss_wts_login_status_api(request: Request, attempt_id: str) -> JSONResponse:
        """Poll the status of the current user's login attempt.

    Only the owner of the attempt can poll it.  Any other user receives 404.
    """
        username = runtime.get_current_username(request)
        from app.services.toss_wts_login import get_login_attempt, TossLoginNotFoundError
        try:
            data = await runtime.asyncio.to_thread(
                get_login_attempt, attempt_id, requesting_username=username
            )
            return runtime.JSONResponse(data, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
        except TossLoginNotFoundError:
            raise runtime.HTTPException(status_code=404, detail={"code":"ATTEMPT_NOT_FOUND"}, headers={"Cache-Control": "no-store"})

    @router.get("/api/settings/toss-wts/login/{attempt_id}/qr")
    async def toss_wts_login_qr_api(request: Request, attempt_id: str) -> Response:
        """Serve the QR PNG image for the current user's pending login attempt.

    Only the owner can fetch their QR.  Served with Cache-Control: no-store.
    Never served from static assets directory.
    """
        username = runtime.get_current_username(request)
        from app.services.toss_wts_login import get_login_qr
        options = {"requesting_username": username}
        if request.query_params.get("revision") is not None:
            options["expected_revision"] = request.query_params["revision"]
        data = await runtime.asyncio.to_thread(get_login_qr, attempt_id, **options)
        if data is None:
            raise runtime.HTTPException(status_code=404, detail={"code":"QR_NOT_AVAILABLE"})
        return runtime.Response(
            content=data,
            media_type="image/png",
            headers={"Cache-Control":"no-store","Pragma":"no-cache"},
        )

    @router.post("/api/settings/toss-wts/login/{attempt_id}/cancel")
    async def toss_wts_login_cancel_api(request: Request, attempt_id: str) -> dict:
        """Cancel the current user's pending login attempt.

    Only the owner can cancel their attempt.  Any other user receives 404.
    """
        username = runtime.get_current_username(request)
        from app.services.toss_wts_login import cancel_login_attempt, TossLoginNotFoundError
        try:
            return await runtime.asyncio.to_thread(
                cancel_login_attempt, attempt_id, requesting_username=username
            )
        except TossLoginNotFoundError:
            raise runtime.HTTPException(status_code=404, detail={"code":"ATTEMPT_NOT_FOUND"})

    return router
