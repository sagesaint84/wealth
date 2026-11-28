from __future__ import annotations

import re
from types import ModuleType

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse


LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>로그인 - 내 자산 대시보드</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:#070a14; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Pretendard,sans-serif; }
  .card { background:#0d1326; padding:38px 34px; border-radius:16px; width:330px;
          border:1px solid #263558; box-shadow:0 18px 45px rgba(0,0,0,0.6); }
  .brand-wrap { display:flex; align-items:center; justify-content:center; gap:10px; margin-bottom:20px; }
  .brand-icon { width:38px; height:38px; border-radius:11px; background:linear-gradient(135deg,#9d7bff,#6847e8);
                display:grid; place-items:center; color:white; font-size:20px; font-weight:900; }
  h1 { color:#f3f5ff; font-size:20px; margin:0; text-align:center; font-weight:800; }
  label { display:block; color:#91a0c1; font-size:12px; margin:15px 0 6px; font-weight:600; }
  input { width:100%; box-sizing:border-box; padding:11px 13px; border-radius:9px;
          border:1px solid #263558; background:#080e1e; color:#f3f5ff; font-size:14px; transition:.15s; }
  input:focus { outline:none; border-color:#9d7bff; box-shadow:0 0 0 3px rgba(157,123,255,0.2); }
  button { width:100%; margin-top:24px; padding:12px; border:none; border-radius:9px;
           background:linear-gradient(135deg,#8e70fa,#5d3ad4); color:white; font-size:15px; font-weight:700; cursor:pointer;
           box-shadow:0 6px 18px rgba(93,58,212,0.4); transition:.18s; }
  button:hover { filter:brightness(1.12); transform:translateY(-1px); }
  .error { color:#ff718c; font-size:12.5px; margin-top:15px; text-align:center; background:#2c121e; padding:8px 10px; border-radius:7px; }
</style>
</head>
<body>
  <div class="card">
    <div class="brand-wrap">
      <div class="brand-icon">W</div>
      <h1>자산 대시보드</h1>
    </div>
    <form method="post" action="/login">
      {{return_to_input}}
      <label>아이디</label>
      <input type="text" name="username" autocomplete="username" placeholder="아이디 입력" required autofocus />
      <label>비밀번호</label>
      <input type="password" name="password" autocomplete="current-password" placeholder="비밀번호 입력" required />
      <button type="submit">로그인</button>
    </form>
    {{message}}
  </div>
</body>
</html>"""


FORCE_PASSWORD_PAGE_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>비밀번호 변경 필수 - 시스템 관리자</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:radial-gradient(ellipse at 50% 20%, #15102a 0%, #060913 70%); color:#e0e6f5;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .card { width:100%; max-width:380px; padding:34px 28px; border-radius:16px; box-sizing:border-box;
          background:rgba(14,21,41,0.95); border:1px solid #4a3885;
          box-shadow:0 20px 50px rgba(0,0,0,0.7), 0 0 0 1px rgba(157,123,255,0.2); backdrop-filter:blur(10px); }
  .badge { display:inline-block; font-size:11.5px; font-weight:700; color:#f59e0b; background:rgba(245,158,11,0.15);
           padding:4px 9px; border-radius:6px; margin-bottom:10px; border:1px solid rgba(245,158,11,0.3); }
  h1 { font-size:20px; font-weight:800; margin:0 0 8px; color:#f3f5ff; }
  p.desc { font-size:13px; color:#91a0c1; line-height:1.5; margin:0 0 20px; }
  label { display:block; color:#91a0c1; font-size:12px; margin:14px 0 6px; font-weight:600; }
  input { width:100%; box-sizing:border-box; padding:11px 13px; border-radius:9px;
          border:1px solid #263558; background:#080e1e; color:#f3f5ff; font-size:14px; transition:.15s; }
  input:focus { outline:none; border-color:#9d7bff; box-shadow:0 0 0 3px rgba(157,123,255,0.2); }
  input[readonly] { opacity:0.8; cursor:not-allowed; background:#090f20; border-color:#1c2742; font-weight:700; color:#c4b5fd; }
  button { width:100%; margin-top:22px; padding:12px; border:none; border-radius:9px;
           background:linear-gradient(135deg,#8e70fa,#5d3ad4); color:white; font-size:15px; font-weight:700; cursor:pointer;
           box-shadow:0 6px 18px rgba(93,58,212,0.4); transition:.18s; }
  button:hover { filter:brightness(1.12); transform:translateY(-1px); }
  .error { color:#ff718c; font-size:12.5px; margin-top:14px; text-align:center; background:#2c121e; padding:8px 10px; border-radius:7px; }
</style>
</head>
<body>
  <div class="card">
    <span class="badge">⚠️ 초기 비밀번호 변경 필수</span>
    <h1>새 비밀번호 설정</h1>
    <p class="desc">초기 계정 보호를 위해 <strong>비밀번호를 새로 변경한 후 접속</strong>이 완료됩니다.</p>
    <form method="post" action="/change-password-init">
      <label>접속 아이디</label>
      <input type="text" value="{{username}}" readonly />
      <label>새 비밀번호 (4자 이상)</label>
      <input type="password" name="new_password" placeholder="새 비밀번호 입력" required minlength="4" autofocus />
      <label>새 비밀번호 확인</label>
      <input type="password" name="new_password_confirm" placeholder="새 비밀번호 확인 입력" required minlength="4" />
      <button type="submit">비밀번호 변경 및 로그인 완료</button>
    </form>
    {{message}}
  </div>
</body>
</html>"""


_SAFE_RETURN_TO_RE = re.compile(r"^/a/[A-Za-z0-9_-]{16,64}$")


def _sanitize_return_to(return_to: str | None) -> str | None:
    if not return_to or not isinstance(return_to, str):
        return None
    val = return_to.strip()
    if _SAFE_RETURN_TO_RE.match(val):
        return val
    return None


def create_auth_router(runtime: ModuleType) -> APIRouter:
    router = APIRouter()

    @router.get("/login", include_in_schema=False)
    async def login_page(error: str | None = None, return_to: str | None = None) -> HTMLResponse:
        message = "<p class='error'>아이디 또는 비밀번호가 올바르지 않습니다.</p>" if error else ""
        safe_return_to = runtime._sanitize_return_to(return_to)
        return_to_input = (
            f'<input type="hidden" name="return_to" value="{safe_return_to}" />'
            if safe_return_to
            else ""
        )
        html = (
            runtime.LOGIN_PAGE_HTML
            .replace("{{message}}", message)
            .replace("{{return_to_input}}", return_to_input)
        )
        return runtime.HTMLResponse(html)

    @router.post("/login", include_in_schema=False)
    async def login_submit(
        username: str = Form(...),
        password: str = Form(...),
        return_to: str | None = Form(None),
    ):
        from app.services.user_manager import authenticate_user
        u = authenticate_user(username.strip(), password.strip())
        safe_return_to = runtime._sanitize_return_to(return_to)
        if u:
            token = runtime._new_session_token(u)
            # 초기 비밀번호 변경 필요 계정이면 대시보드가 아닌 비번 변경 전용 페이지로 즉시 리다이렉트
            if u.get("must_change_password", False):
                response = runtime.RedirectResponse("/change-password-init", status_code=303)
            elif safe_return_to:
                response = runtime.RedirectResponse(safe_return_to, status_code=303)
            else:
                response = runtime.RedirectResponse("/dashboard", status_code=303)

            response.set_cookie(
                runtime.COOKIE_NAME,
                token,
                httponly=True,
                secure=not runtime.TESTING,
                samesite="lax",
                max_age=runtime.SESSION_MAX_AGE,
            )
            return response
        err_redirect = "/login?error=1"
        if safe_return_to:
            err_redirect += f"&return_to={runtime.quote(safe_return_to, safe='')}"
        return runtime.RedirectResponse(err_redirect, status_code=303)

    @router.get("/change-password-init", include_in_schema=False)
    async def change_password_init_page(request: Request, error: str | None = None) -> HTMLResponse:
        user = runtime._get_authenticated_user(request)
        if not user:
            return runtime.RedirectResponse("/login")
        if not user.get("must_change_password", False):
            return runtime.RedirectResponse("/dashboard")

        uname = user["username"]
        message_html = f"<p class='error'>{error}</p>" if error else ""
        html = runtime.FORCE_PASSWORD_PAGE_HTML.replace("{{username}}", uname).replace("{{message}}", message_html)
        return runtime.HTMLResponse(html)

    @router.post("/change-password-init", include_in_schema=False)
    async def change_password_init_submit(
        request: Request,
        new_password: str = Form(...),
        new_password_confirm: str = Form(...)
    ):
        user = runtime._get_authenticated_user(request)
        if not user:
            return runtime.RedirectResponse("/login")
        if not user.get('must_change_password', False):
            raise runtime.HTTPException(403, detail={'code': 'PASSWORD_CHANGE_NOT_PENDING'})
        uname = user["username"]

        p1 = new_password.strip()
        p2 = new_password_confirm.strip()
        if len(p1) < 4:
            return runtime.RedirectResponse("/change-password-init?error=" + runtime.quote("새 비밀번호는 최소 4자 이상이어야 합니다."), status_code=303)
        if p1 != p2:
            return runtime.RedirectResponse("/change-password-init?error=" + runtime.quote("새 비밀번호 확인이 일치하지 않습니다."), status_code=303)

        from app.services.user_manager import force_set_user_password
        try:
            force_set_user_password(uname, p1)
        except Exception as e:
            return runtime.RedirectResponse("/change-password-init?error=" + runtime.quote(str(e)), status_code=303)

        # 변경 완료 -> 정식 세션 갱신 후 비로소 대시보드로 이동!
        from app.services.user_manager import get_user_by_name
        token = runtime._new_session_token(get_user_by_name(uname))
        response = runtime.RedirectResponse("/dashboard", status_code=303)
        response.set_cookie(
            runtime.COOKIE_NAME,
            token,
            httponly=True,
            secure=not runtime.TESTING,
            samesite="lax",
            max_age=runtime.SESSION_MAX_AGE,
        )
        return response

    @router.get("/logout", include_in_schema=False)
    async def logout() -> RedirectResponse:
        response = runtime.RedirectResponse("/login")
        response.delete_cookie(runtime.COOKIE_NAME)
        return response

    @router.get("/api/auth/me")
    async def get_my_info(request: Request) -> dict:
        """현재 로그인한 사용자의 프로필 정보 반환"""
        username = runtime.get_current_username(request)
        role = runtime.get_current_role(request)
        must_change = getattr(request.state, "must_change_password", False)
        from app.services.user_manager import get_user_by_name
        from app.services.update_permissions import can_system_update
        allowed = can_system_update(get_user_by_name(username))
        return {
            "username": username,
            "role": role,
            "must_change_password": must_change,
            "can_system_update": allowed,
        }

    @router.post("/api/auth/change-password")
    async def change_password_endpoint(request: Request, response: Response) -> dict:
        """사용자 본인 비밀번호 변경"""
        username = runtime.get_current_username(request)
        body = await request.json()
        old_pw = str(body.get("old_password", "")).strip()
        new_pw = str(body.get("new_password", "")).strip()
        from app.services.user_manager import change_user_password
        try:
            change_user_password(username, old_pw, new_pw)
            runtime._refresh_auth_cookie(response, username)
            return {"message": "비밀번호가 성공적으로 변경되었습니다."}
        except Exception as e:
            raise runtime.HTTPException(status_code=400, detail=str(e))

    @router.post("/api/auth/force-change-password")
    async def force_change_password_endpoint(request: Request, response: Response) -> dict:
        """must_change_password 상태에서 새 비밀번호 설정"""
        username = runtime.get_current_username(request)
        if not getattr(request.state, 'must_change_password', False):
            raise runtime.HTTPException(403, detail={'code': 'PASSWORD_CHANGE_NOT_PENDING'})
        body = await request.json()
        new_pw = str(body.get("new_password", "")).strip()
        from app.services.user_manager import force_set_user_password
        try:
            force_set_user_password(username, new_pw)
            runtime._refresh_auth_cookie(response, username)
            return {"message": "새 비밀번호가 설정되었습니다."}
        except Exception as e:
            raise runtime.HTTPException(status_code=400, detail=str(e))

    return router
