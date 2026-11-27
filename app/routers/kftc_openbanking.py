from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Request, Response


def create_kftc_openbanking_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/api/user/kftc-openbanking-config")
    async def get_user_kftc_config_api(request: Request) -> dict:
        """Return current user's safe KFTC Open Banking configuration metadata (never reveals secret)."""
        username = runtime.get_current_username(request)
        from app.services.kftc_openbanking_config import get_user_kftc_status_metadata
        return get_user_kftc_status_metadata(username)

    @router.patch("/api/user/kftc-openbanking-config")
    async def patch_user_kftc_config_api(request: Request) -> dict:
        """Update current user's KFTC Open Banking configuration and credentials."""
        username = runtime.get_current_username(request)
        from app.services.kftc_openbanking_config import patch_user_kftc_config, KftcConfigError
        try:
            body = await request.json()
        except Exception:
            body = None
        if not isinstance(body, dict):
            raise runtime.HTTPException(status_code=400, detail={"code": "KFTC_CONFIG_PATCH_INVALID"})
        try:
            return patch_user_kftc_config(username, body)
        except (KftcConfigError, ValueError, AttributeError) as exc:
            raise runtime.HTTPException(status_code=400, detail={"code": str(exc)}) from exc

    @router.get("/api/kftc/openbanking/status")
    async def get_kftc_user_status_api(request: Request) -> dict:
        """Return current user's KFTC connection and token status (never reveals tokens)."""
        username = runtime.get_current_username(request)
        from app.services.kftc_openbanking_service import get_user_kftc_status
        return get_user_kftc_status(username)

    @router.post("/api/kftc/openbanking/oauth/start")
    async def start_kftc_oauth_api(request: Request) -> dict:
        """Start OAuth 2.0 flow: generate 32-char state bound to user/session and return authorize_url."""
        username = runtime.get_current_username(request)
        from app.services.kftc_openbanking_service import start_oauth_flow, compute_session_fingerprint, KftcServiceError
        session_cookie = request.cookies.get(runtime.COOKIE_NAME)
        session_id = compute_session_fingerprint(session_cookie)

        # Scope is strictly server-controlled ('login inquiry'); ignore any client-supplied scope body
        try:
            result = start_oauth_flow(username, session_id=session_id)
            # Never send secret or tokens to frontend; only authorize_url
            return {"authorize_url": result["authorize_url"]}
        except KftcServiceError as exc:
            status_code = 403 if exc.code in {"KFTC_NOT_ALLOWED", "KFTC_SCOPE_FORBIDDEN"} else 400
            raise runtime.HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    @router.get("/api/kftc/openbanking/oauth/callback")
    async def kftc_oauth_callback_api(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
    ):
        """Handle OAuth callback from KFTC, validate state, exchange code, redirect safely."""
        # Ensure user has a valid authenticated session
        user = runtime._get_authenticated_user(request)
        if not user:
            return runtime.RedirectResponse("/login?error=kftc_session_expired", status_code=303)

        username = user["username"]
        from app.services.kftc_openbanking_service import handle_oauth_callback, compute_session_fingerprint, KftcServiceError
        session_cookie = request.cookies.get(runtime.COOKIE_NAME)
        session_id = compute_session_fingerprint(session_cookie)

        try:
            await handle_oauth_callback(
                username,
                session_id=session_id,
                code=code,
                state=state,
                error=error,
                error_description=error_description,
            )
            return runtime.RedirectResponse("/?kftc_connected=1", status_code=303)
        except KftcServiceError as exc:
            runtime.logger.warning("KFTC callback error for user %s: %s (%s)", username, exc.code, exc)
            return runtime.RedirectResponse(f"/?kftc_error={exc.code}", status_code=303)
        except Exception as exc:
            runtime.logger.error("Unexpected error in KFTC callback for user %s: %s", username, exc)
            return runtime.RedirectResponse("/?kftc_error=INTERNAL_ERROR", status_code=303)

    @router.post("/api/kftc/openbanking/token/refresh")
    async def refresh_kftc_token_api(request: Request) -> dict:
        """Manually or proactively refresh user's access token using stored refresh token."""
        username = runtime.get_current_username(request)
        from app.services.kftc_openbanking_service import refresh_user_token, KftcServiceError
        try:
            return await refresh_user_token(username)
        except KftcServiceError as exc:
            status_code = 403 if exc.code == "KFTC_NOT_ALLOWED" else 400
            raise runtime.HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    @router.delete("/api/kftc/openbanking/disconnect")
    async def disconnect_kftc_api(request: Request) -> dict:
        """Disconnect local KFTC connection and erase tokens/mapping without affecting Wealth assets."""
        username = runtime.get_current_username(request)
        from app.services.kftc_openbanking_service import disconnect_kftc
        disconnect_kftc(username)
        return {"ok": True, "message": "KFTC 오픈뱅킹 연동을 안전하게 해제했습니다."}

    @router.get("/api/kftc/openbanking/accounts")
    async def get_kftc_accounts_api(request: Request, refresh: bool = False) -> dict:
        """Return user's registered bank accounts from KFTC with masked numbers and safe IDs."""
        username = runtime.get_current_username(request)
        from app.services.kftc_openbanking_service import (
            refresh_and_sync_accounts,
            load_user_kftc_accounts,
            KftcServiceError,
        )
        from app.services.kftc_openbanking_storage import load_user_token_status

        status = load_user_token_status(username)
        if not status.get("connected"):
            raise runtime.HTTPException(status_code=400, detail={"code": "NOT_CONNECTED", "message": "KFTC 오픈뱅킹이 연결되어 있지 않습니다."})

        try:
            if refresh or not load_user_kftc_accounts(username):
                accounts = await refresh_and_sync_accounts(username)
            else:
                accounts = load_user_kftc_accounts(username)
            return {"accounts": accounts, "count": len(accounts)}
        except KftcServiceError as exc:
            status_code = 403 if exc.code == "KFTC_NOT_ALLOWED" else 400
            raise runtime.HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    @router.post("/api/kftc/openbanking/accounts/{provider_account_id}/balance/preview")
    async def preview_kftc_account_balance_api(
        provider_account_id: str,
        request: Request,
        response: Response,
    ) -> dict:
        """Read-only balance inquiry preview for a registered KFTC account.

    Strictly read-only: does not modify bank_accounts, portfolio, ledger, or balance records.
    """
        response.headers["Cache-Control"] = "no-store"
        username = runtime.get_current_username(request)
        from app.services.kftc_openbanking_service import (
            KftcServiceError,
            preview_account_balance,
        )

        try:
            return await preview_account_balance(username, provider_account_id)
        except KftcServiceError as exc:
            if exc.code == "KFTC_NOT_ALLOWED":
                status_code = 403
            elif exc.code in {"ACCOUNT_NOT_FOUND", "INVALID_FINTECH_USE_NUM"}:
                status_code = 404
            else:
                status_code = 400
            raise runtime.HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)}) from exc

    return router
