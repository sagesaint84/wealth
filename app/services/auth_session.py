"""Session signing, cookie handling, and HTTP access control."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from fastapi import Request, Response


def create_auth_session(runtime: ModuleType) -> dict[str, object]:
    # Resolve application bindings when called, including the shared serializer.
    def _resolve_session_secret() -> str:
        """Resolve the session signing secret - fail closed in all environments.

        Priority:
        1. DASHBOARD_SECRET_KEY environment variable (all environments).
        2. WEALTH_TEST_SIGNING_SECRET (test environment only, explicit opt-in).
        3. Raise RuntimeError - no built-in fallback exists.
        """
        explicit = runtime.os.getenv("DASHBOARD_SECRET_KEY", "").strip()
        if explicit: return explicit
        if runtime.TESTING:
            test_value = runtime.os.getenv("WEALTH_TEST_SIGNING_SECRET", "").strip()
            if test_value: return test_value
        from app.services.system_secrets import resolve_application_secret
        return resolve_application_secret()

    SECRET_KEY = _resolve_session_secret()
    SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14일 동안 로그인 유지
    COOKIE_NAME = "dashboard_session_v2"
    _serializer = runtime.URLSafeTimedSerializer(SECRET_KEY)
    PUBLIC_PATHS = {
        "/login",
        "/change-password-init",
        "/sw.js",
        "/manifest.json",
        "/favicon.ico",
        "/api/integrations/telegram/webhook",
        "/api/integrations/kakao/oauth/callback",
        "/api/kftc/openbanking/oauth/callback",
    }

    def _require_authenticated_username(request: Request) -> str:
        """인증 미들웨어를 우회해 호출되더라도 기본 사용자로 대체하지 않는다."""
        username = getattr(request.state, "username", None)
        if not username:
            raise runtime.HTTPException(status_code=401, detail="로그인이 필요합니다.")
        return str(username)

    def get_current_username(request: Request) -> str:
        return runtime._require_authenticated_username(request)

    def get_current_role(request: Request) -> str:
        return getattr(request.state, "role", None) or "user"

    def _new_session_token(user: dict) -> str:
        from app.services.update_permissions import session_stamp, valid_identity
        if not valid_identity(user):
            return runtime._serializer.dumps({"user": user["username"]})
        return runtime._serializer.dumps({"user": user["username"], "uid": user.get("id"),
                                  "auth_stamp": session_stamp(user, runtime.SECRET_KEY), "sid": runtime.secrets.token_urlsafe(24)})

    def _updater_session_current(request: Request, user: dict) -> bool:
        from app.services.update_permissions import session_stamp, valid_identity
        try:
            claims = runtime._serializer.loads(request.cookies.get(runtime.COOKIE_NAME, ''), max_age=runtime.SESSION_MAX_AGE)
            return (valid_identity(user) and isinstance(claims.get('sid'), str)
                    and runtime.re.fullmatch(r'[A-Za-z0-9_-]{32}', claims['sid']) is not None
                    and claims.get('uid') == user['id']
                    and runtime.secrets.compare_digest(str(claims.get('auth_stamp', '')), session_stamp(user, runtime.SECRET_KEY)))
        except (runtime.BadSignature, runtime.SignatureExpired, ValueError, TypeError):
            return False

    def _refresh_auth_cookie(response: Response, username: str) -> None:
        from app.services.user_manager import get_user_by_name
        user = get_user_by_name(username)
        response.set_cookie(runtime.COOKIE_NAME, runtime._new_session_token(user), httponly=True,
                            secure=not runtime.TESTING, samesite='lax', max_age=runtime.SESSION_MAX_AGE)

    def _get_authenticated_user(request: Request) -> dict[str, Any] | None:
        token = request.cookies.get(runtime.COOKIE_NAME)
        if not token or not runtime._serializer:
            return None
        try:
            data = runtime._serializer.loads(token, max_age=runtime.SESSION_MAX_AGE)
            uname = data.get("user")
            if uname:
                from app.services.user_manager import get_user_by_name
                user = get_user_by_name(uname)
                # New sessions expire when this identity is recreated or credentials reset.
                # Legacy sessions retain existing financial access; updater requires re-login.
                if user and ('uid' in data or 'auth_stamp' in data) and not runtime._updater_session_current(request, user):
                    return None
                return user
        except (runtime.BadSignature, runtime.SignatureExpired, Exception):
            pass
        return None

    async def require_login(request: Request, call_next):
        path = request.url.path
        # Immutable authorization identity is resolved from the current persisted
        # user record below; it is never accepted from the signed cookie.
        request.state.user_id = None

        if path in runtime.PUBLIC_PATHS or path.startswith("/static/"):
            return await call_next(request)

        user = runtime._get_authenticated_user(request)
        if not user:
            if path.startswith("/a/"):
                return runtime.RedirectResponse(f"/login?return_to={runtime.quote(path, safe='')}")
            if path.startswith("/api/"):
                return runtime.JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401,
                                    headers={"Cache-Control":"no-store"} if path.startswith("/api/settings/toss-wts/session/") else None)
            return runtime.RedirectResponse("/login")

        request.state.username = user["username"]
        request.state.user_id = user.get("id")
        request.state.role = user.get("role", "user")
        request.state.must_change_password = bool(user.get("must_change_password", False))

        # 초기 비밀번호 상태(must_change_password)일 때: 대시보드 진입을 원천 차단하고 비밀번호 변경 화면으로 리다이렉트
        if request.state.must_change_password:
            if path.startswith("/api/"):
                allowed_api = {"/api/auth/me", "/api/auth/force-change-password"}
                if path not in allowed_api:
                    return runtime.JSONResponse({"detail": "비밀번호 변경이 필요합니다."}, status_code=403,
                                        headers={"Cache-Control":"no-store"} if path.startswith("/api/settings/toss-wts/session/") else None)
            else:
                if path not in ("/change-password-init", "/logout"):
                    return runtime.RedirectResponse("/change-password-init")

        return await call_next(request)

    def _require_system_settings_admin(request: Request) -> None:
        if runtime.get_current_role(request) != "admin":
            raise runtime.HTTPException(status_code=403, detail={"code": "ADMIN_REQUIRED"})

    return {
        "_resolve_session_secret": _resolve_session_secret,
        "_require_authenticated_username": _require_authenticated_username,
        "get_current_username": get_current_username,
        "get_current_role": get_current_role,
        "_new_session_token": _new_session_token,
        "_updater_session_current": _updater_session_current,
        "_refresh_auth_cookie": _refresh_auth_cookie,
        "_get_authenticated_user": _get_authenticated_user,
        "require_login": require_login,
        "_require_system_settings_admin": _require_system_settings_admin,
        "SECRET_KEY": SECRET_KEY,
        "SESSION_MAX_AGE": SESSION_MAX_AGE,
        "COOKIE_NAME": COOKIE_NAME,
        "_serializer": _serializer,
        "PUBLIC_PATHS": PUBLIC_PATHS,
    }
