from __future__ import annotations

import asyncio
import os
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field

from app.services.kb_openapi import KBOpenAPI, KBOpenAPIError
from app.services.nhplug_openapi import NhPlugOpenAPI, NhPlugOpenAPIError
from app.services.toss_openapi import TossOpenAPI, TossOpenAPIError
from app.services.kis_openapi import KISOpenAPI, KISOpenAPIError
from app.services.kiwoom_openapi import KiwoomOpenAPI, KiwoomOpenAPIError
from app.services.network_policy import is_test_mode
from app.services.web_finance import (
    get_web_market_overview,
    fetch_fx_rate_usd_krw,
    refresh_all_holdings_prices,
    fetch_stock_chart_data,
    get_web_dividend_summary,
)
fetch_market_overview = get_web_market_overview
from app.services.portfolio import (
    clear_portfolio, get_dashboard, get_or_add_account, import_rows, normalize_holding,
    read_portfolio, seed_demo, upsert_holdings, write_portfolio, to_number, migrate_add_family_group
)
from app.services.asset_records import delete_asset_record, list_asset_records, upsert_asset_record
from app.services.dividend_records import (
    create_dividend_record, delete_dividend_record, get_actual_dividend_summary,
    read_dividend_records, update_dividend_record, import_dividend_file_data,
    clear_dividend_records, recalculate_dividend_historical_fx
)
from app.services.pnl_records import (
    create_pnl_record, delete_pnl_record, get_pnl_summary,
    read_pnl_records, update_pnl_record, import_pnl_file_data,
    clear_pnl_records, recalculate_pnl_historical_fx
)
from app.services.historical_fx import get_historical_fx_rate, sync_historical_fx
from app.services.stock_master import sync_stock_master_online
from app.services.toss_wts_adapter import TossWtsAdapter, TossWtsAdapterError
from app.services.toss_wts_feed_auth import check_wts_feed_static_authorization
from app.services.toss_wts_feed_runtime import (
    check_wts_feed_runtime_confirmation,
    confirm_wts_feed_runtime_session,
    get_current_runtime_generation_id,
)
from app.services.toss_wts_feed import (
    build_realized_feed_response,
    compute_items_hash,
    sign_import_preview_ticket,
    validate_realized_feed_request,
    verify_import_preview_ticket,
)
from app.services.toss_wts_realized import preview_toss_wts_realized_selection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "app" / "static"
WEALTH_ENV = os.getenv("WEALTH_ENV", "production").strip().lower()
TESTING = WEALTH_ENV == "test"


def load_env_file() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.exists():
        return
    if not env_path.is_file():
        raise RuntimeError("Configuration error: .env must be a regular file, but a directory was found.")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


if not TESTING:
    load_env_file()
app = FastAPI(title="내 자산 대시보드", docs_url=None, redoc_url=None, version="1.1.1")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_syncing_users: set[str] = set()


def _mask_sync_error(error: Exception, client: object | None = None) -> str:
    """Return a user-facing sync error without credentials or full account numbers."""
    detail = error.detail if isinstance(error, HTTPException) else str(error)
    text = str(detail)
    if client is not None:
        for attr in ("app_key", "app_secret", "account_no"):
            value = str(getattr(client, attr, "") or "")
            if value:
                text = text.replace(value, f"{value[:4]}****" if attr == "account_no" else "********")
    text = re.sub(r"(?<!\d)\d{8,12}(?!\d)", lambda m: f"{m.group(0)[:4]}****", text)
    return text[:300]


def _sync_error_status(error: Exception) -> str:
    text = str(error.detail if isinstance(error, HTTPException) else error)
    if any(marker in text for marker in ("응답 형식", "올바른 JSON", "항목 형식", "연속조회")):
        return "PARSE_ERROR"
    if isinstance(error, (HTTPException, KBOpenAPIError, TossOpenAPIError, NhPlugOpenAPIError, KISOpenAPIError, KiwoomOpenAPIError)):
        return "API_ERROR"
    return "INTERNAL_ERROR"


def _mark_sync_success(data: dict, broker: str) -> None:
    data.setdefault("settings", {}).setdefault("sync_last_success", {})[broker] = datetime.now().astimezone().isoformat(timespec="seconds")

@app.get("/sw.js")
async def service_worker_file():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed": "/"})

@app.get("/manifest.json")
async def manifest_file_root():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")
async def ensure_data_dir():
    if TESTING:
        return
    data_dir = ROOT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    # 1. 멀티유저 초기화 및 sagesaint 데이터 자동 마이그레이션 실행
    from app.services.user_manager import init_users_and_migration
    init_users_and_migration()
    # 2. 계좌 가족 그룹 마이그레이션 실행
    migrate_add_family_group()
    # 3. 5년치 과거 환율 비동기 동기화
    asyncio.create_task(sync_historical_fx())
    # 4. 종목 마스터(국내 ETF/상장사/미국주식) 비동기 동기화
    asyncio.create_task(sync_stock_master_online())


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    """Run the existing startup contract once per application lifespan."""
    await ensure_data_dir()
    yield


app.router.lifespan_context = app_lifespan


# ---------------------------------------------------------------------------
# 로그인 / 멀티유저 인증
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "").strip() or "asset_dashboard_secret_key_default"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14일 동안 로그인 유지
COOKIE_NAME = "dashboard_session_v2"

_serializer = URLSafeTimedSerializer(SECRET_KEY)
PUBLIC_PATHS = {"/login", "/change-password-init", "/sw.js", "/manifest.json", "/favicon.ico"}

_SENSITIVE_EXPORT_KEYS = {
    "accesstoken",
    "apikey",
    "apisecret",
    "appkey",
    "appsecret",
    "authtoken",
    "bearertoken",
    "clientsecret",
    "credential",
    "credentials",
    "password",
    "passwordhash",
    "passwordsalt",
    "privatekey",
    "refreshtoken",
    "salt",
    "secret",
    "secretkey",
    "sessionid",
    "sessionsecret",
    "sessiontoken",
    "token",
    "tokencache",
}


def _normalize_sensitive_key(key: object) -> str:
    return "".join(char.lower() for char in str(key) if char.isalnum())


def _is_sensitive_export_key(key: object) -> bool:
    normalized = _normalize_sensitive_key(key)
    return normalized in _SENSITIVE_EXPORT_KEYS or normalized.endswith(
        (
            "accesstoken",
            "apikey",
            "apisecret",
            "appkey",
            "appsecret",
            "clientsecret",
            "credential",
            "credentials",
            "password",
            "passwordhash",
            "privatekey",
            "refreshtoken",
            "secret",
            "sessionsecret",
            "token",
            "tokencache",
        )
    )


def _sanitize_export_data(value: object) -> object:
    """백업 데이터 어디에도 인증정보가 포함되지 않도록 재귀적으로 제거한다."""
    if isinstance(value, dict):
        return {
            key: _sanitize_export_data(item)
            for key, item in value.items()
            if not _is_sensitive_export_key(key)
        }
    if isinstance(value, list):
        return [_sanitize_export_data(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_export_data(item) for item in value]
    return value


def _require_authenticated_username(request: Request) -> str:
    """인증 미들웨어를 우회해 호출되더라도 기본 사용자로 대체하지 않는다."""
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return str(username)


def get_current_username(request: Request) -> str:
    return _require_authenticated_username(request)


def get_current_role(request: Request) -> str:
    return getattr(request.state, "role", None) or "user"


def _get_authenticated_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token or not _serializer:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
        uname = data.get("user")
        if uname:
            from app.services.user_manager import get_user_by_name
            return get_user_by_name(uname)
    except (BadSignature, SignatureExpired, Exception):
        pass
    return None


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


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    # Immutable authorization identity is resolved from the current persisted
    # user record below; it is never accepted from the signed cookie.
    request.state.user_id = None
    
    if path in PUBLIC_PATHS or path.startswith("/static/"):
        return await call_next(request)
    
    user = _get_authenticated_user(request)
    if not user:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401)
        return RedirectResponse("/login")
    
    request.state.username = user["username"]
    request.state.user_id = user.get("id")
    request.state.role = user.get("role", "user")
    request.state.must_change_password = bool(user.get("must_change_password", False))

    # 초기 비밀번호 상태(must_change_password)일 때: 대시보드 진입을 원천 차단하고 비밀번호 변경 화면으로 리다이렉트
    if request.state.must_change_password:
        if path.startswith("/api/"):
            allowed_api = {"/api/auth/me", "/api/auth/force-change-password"}
            if path not in allowed_api:
                return JSONResponse({"detail": "비밀번호 변경이 필요합니다."}, status_code=403)
        else:
            if path not in ("/change-password-init", "/logout"):
                return RedirectResponse("/change-password-init")

    return await call_next(request)


@app.get("/login", include_in_schema=False)
async def login_page(error: str | None = None) -> HTMLResponse:
    message = "<p class='error'>아이디 또는 비밀번호가 올바르지 않습니다.</p>" if error else ""
    return HTMLResponse(LOGIN_PAGE_HTML.replace("{{message}}", message))


@app.post("/login", include_in_schema=False)
async def login_submit(username: str = Form(...), password: str = Form(...)):
    from app.services.user_manager import authenticate_user
    u = authenticate_user(username.strip(), password.strip())
    if u:
        token = _serializer.dumps({"user": u["username"], "role": u.get("role", "user")})
        # 초기 비밀번호 변경 필요 계정이면 대시보드가 아닌 비번 변경 전용 페이지로 즉시 리다이렉트
        if u.get("must_change_password", False):
            response = RedirectResponse("/change-password-init", status_code=303)
        else:
            response = RedirectResponse("/dashboard", status_code=303)
        
        response.set_cookie(
            COOKIE_NAME, token, httponly=True, samesite="lax", max_age=SESSION_MAX_AGE
        )
        return response
    return RedirectResponse("/login?error=1", status_code=303)


@app.get("/change-password-init", include_in_schema=False)
async def change_password_init_page(request: Request, error: str | None = None) -> HTMLResponse:
    user = _get_authenticated_user(request)
    if not user:
        return RedirectResponse("/login")
    if not user.get("must_change_password", False):
        return RedirectResponse("/dashboard")
    
    uname = user["username"]
    message_html = f"<p class='error'>{error}</p>" if error else ""
    html = FORCE_PASSWORD_PAGE_HTML.replace("{{username}}", uname).replace("{{message}}", message_html)
    return HTMLResponse(html)


@app.post("/change-password-init", include_in_schema=False)
async def change_password_init_submit(
    request: Request,
    new_password: str = Form(...),
    new_password_confirm: str = Form(...)
):
    user = _get_authenticated_user(request)
    if not user:
        return RedirectResponse("/login")
    uname = user["username"]
    
    p1 = new_password.strip()
    p2 = new_password_confirm.strip()
    if len(p1) < 4:
        return RedirectResponse("/change-password-init?error=" + quote("새 비밀번호는 최소 4자 이상이어야 합니다."), status_code=303)
    if p1 != p2:
        return RedirectResponse("/change-password-init?error=" + quote("새 비밀번호 확인이 일치하지 않습니다."), status_code=303)
    
    from app.services.user_manager import force_set_user_password
    try:
        force_set_user_password(uname, p1)
    except Exception as e:
        return RedirectResponse("/change-password-init?error=" + quote(str(e)), status_code=303)
    
    # 변경 완료 -> 정식 세션 갱신 후 비로소 대시보드로 이동!
    token = _serializer.dumps({"user": uname, "role": user.get("role", "user")})
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax", max_age=SESSION_MAX_AGE
    )
    return response


@app.get("/logout", include_in_schema=False)
async def logout() -> RedirectResponse:
    response = RedirectResponse("/login")
    response.delete_cookie(COOKIE_NAME)
    return response


# ---------------------------------------------------------------------------
# 사용자 및 계정 관리 API
# ---------------------------------------------------------------------------

@app.get("/api/auth/me")
async def get_my_info(request: Request) -> dict:
    """현재 로그인한 사용자의 프로필 정보 반환"""
    username = get_current_username(request)
    role = get_current_role(request)
    must_change = getattr(request.state, "must_change_password", False)
    return {
        "username": username,
        "role": role,
        "must_change_password": must_change,
    }


@app.post("/api/auth/change-password")
async def change_password_endpoint(request: Request) -> dict:
    """사용자 본인 비밀번호 변경"""
    username = get_current_username(request)
    body = await request.json()
    old_pw = str(body.get("old_password", "")).strip()
    new_pw = str(body.get("new_password", "")).strip()
    from app.services.user_manager import change_user_password
    try:
        change_user_password(username, old_pw, new_pw)
        return {"message": "비밀번호가 성공적으로 변경되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/force-change-password")
async def force_change_password_endpoint(request: Request) -> dict:
    """must_change_password 상태에서 새 비밀번호 설정"""
    username = get_current_username(request)
    body = await request.json()
    new_pw = str(body.get("new_password", "")).strip()
    from app.services.user_manager import force_set_user_password
    try:
        force_set_user_password(username, new_pw)
        return {"message": "새 비밀번호가 설정되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/user/openapi-config")
async def get_user_openapi_keys(request: Request) -> dict:
    """현재 로그인한 사용자의 마스킹된 OpenAPI 키 정보 반환"""
    username = get_current_username(request)
    from app.services.user_openapi import get_masked_user_openapi_config
    return get_masked_user_openapi_config(username)


@app.post("/api/user/openapi-config")
async def save_user_openapi_keys(request: Request) -> dict:
    """현재 로그인한 사용자의 OpenAPI 키 설정 저장"""
    username = get_current_username(request)
    payload = await request.json()
    from app.services.user_openapi import save_user_openapi_config
    save_user_openapi_config(username, payload)
    return {"message": "증권사 OpenAPI 키가 안전하게 저장되었습니다."}


@app.delete("/api/user/openapi-config/{broker}")
async def delete_user_openapi_broker(broker: str, request: Request) -> dict:
    """현재 로그인한 사용자의 특정 증권사 OpenAPI 설정 및 토큰 삭제"""
    username = get_current_username(request)
    if broker not in ("toss", "kb", "nh"):
        raise HTTPException(status_code=400, detail="유효하지 않은 증권사입니다.")
    from app.services.user_openapi import delete_user_broker_openapi
    delete_user_broker_openapi(username, broker)
    broker_names = {"toss": "토스증권", "kb": "KB증권", "nh": "나무증권"}
    bname = broker_names.get(broker, broker)
    return {"message": f"{bname} OpenAPI 키 및 시크릿이 삭제되었습니다."}




@app.get("/api/admin/users")
async def admin_list_users(request: Request) -> dict:
    """(Admin 전용) 등록된 모든 사용자 목록 반환"""
    if get_current_role(request) != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    from app.services.user_manager import list_users
    return {"users": list_users()}


@app.post("/api/admin/users")
async def admin_create_user(request: Request) -> dict:
    """(Admin 전용) 신규 사용자 생성 (초기 4자리 비밀번호, must_change_password=True)"""
    if get_current_role(request) != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    body = await request.json()
    uname = str(body.get("username", "")).strip()
    init_pw = str(body.get("initial_password", "")).strip()
    from app.services.user_manager import create_new_user
    try:
        create_new_user(uname, init_pw)
        return {"message": f"사용자 '{uname}'(이)가 생성되었습니다. (초기 비밀번호: {init_pw})"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/users/{target_username}/reset-password")
async def admin_reset_user_password(target_username: str, request: Request) -> dict:
    """(Admin 전용) 사용자 비밀번호를 4자리로 초기화"""
    if get_current_role(request) != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    body = await request.json()
    new_pw_4digit = str(body.get("new_password", "")).strip()
    from app.services.user_manager import admin_reset_password_to_4digit
    try:
        admin_reset_password_to_4digit(target_username, new_pw_4digit)
        return {"message": f"'{target_username}'의 비밀번호가 '{new_pw_4digit}'(으)로 초기화되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/admin/users/{target_username}")
async def admin_delete_user(target_username: str, request: Request) -> dict:
    """(Admin 전용) 사용자 계정 삭제"""
    if get_current_role(request) != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    from app.services.user_manager import delete_user_account
    try:
        delete_user_account(target_username)
        return {"message": f"사용자 '{target_username}' 계정이 삭제되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# 기존 기능
# ---------------------------------------------------------------------------


class HoldingCreate(BaseModel):
    broker: str = Field(min_length=1, max_length=60)
    account_name: str = Field(min_length=1, max_length=80)
    code: str = Field(default="", max_length=20)
    name: str = Field(min_length=1, max_length=80)
    quantity: float = Field(gt=0)
    avg_price: float = Field(ge=0)
    current_price: float = Field(ge=0)
    currency: str = "KRW"
    market: str = ""
    owner: str = "모두"


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> HTMLResponse:
    return HTMLResponse(status_code=204)


DEFAULT_FAMILY_MEMBERS = ["아빠", "엄마", "자녀"]

def get_family_members(data: dict) -> list:
    return data.get("settings", {}).get("family_members", list(DEFAULT_FAMILY_MEMBERS))


def auto_save_all_owner_snapshots(data: dict[str, Any], username: str | None = None) -> None:
    """
    대시보드 접속 또는 조회 시 '모두' 및 모든 가족 구성원('아빠', '엄마', '자녀' 등)의
    당일 자산기록(스냅샷)을 실시간 평가액으로 자동 갱신 및 신규 생성합니다.
    """
    if not data or not data.get("summary"):
        return

    today = datetime.now().astimezone().date().isoformat()
    usd_rate = float(data.get("fx_rates", {}).get("USD", 1385.0))
    all_records = list_asset_records(username=username)

    raw_members = get_family_members(data) or list(DEFAULT_FAMILY_MEMBERS)
    account_owners = [
        a.get("owner")
        for a in data.get("accounts", [])
        if a.get("owner") and a.get("owner") != "모두"
    ]
    target_owners = ["모두"] + list(dict.fromkeys(raw_members + account_owners))

    for owner in target_owners:
        if owner == "모두":
            if data["summary"]["holding_count"] or data["summary"]["total_value_krw"]:
                day = data.get("day_change") or {}
                snapshot_all = {
                    "date": today,
                    "total_value_krw": data["summary"]["total_value_krw"],
                    "total_cost_krw": data["summary"]["total_cost_krw"],
                    "profit_krw": data["summary"]["profit_krw"],
                    "return_rate": data["summary"]["return_rate"],
                    "day_profit_krw": day.get("change_krw") or 0,
                    "krw_value_krw": data.get("currency_summary", {}).get("KRW", {}).get("market_value_krw", 0),
                    "usd_value_krw": data.get("currency_summary", {}).get("USD", {}).get("market_value_krw", 0),
                    "holding_count": data["summary"]["holding_count"],
                    "currency": "KRW",
                    "source": "auto",
                    "memo": "자동 기록",
                    "owner": "모두",
                }
                upsert_asset_record(snapshot_all, by_date=True, username=username)
        else:
            owned_accounts = [a for a in data.get("accounts", []) if (a.get("owner") or "모두") == owner]
            owned_acc_ids = {a["id"] for a in owned_accounts}
            owned_holdings = [
                h for h in data.get("holdings", [])
                if h.get("account_id") in owned_acc_ids or h.get("owner") == owner
            ]

            if not owned_accounts and not owned_holdings:
                continue

            stock_value_krw = 0.0
            stock_cost_krw = 0.0
            krw_stock_krw = 0.0
            usd_stock_usd = 0.0
            holding_day_gain = 0.0

            for h in owned_holdings:
                m_val = float(h.get("market_value_krw") or 0.0)
                c_val = float(h.get("cost_value_krw") or 0.0)
                stock_value_krw += m_val
                stock_cost_krw += c_val

                curr = (h.get("currency") or "KRW").upper()
                if curr == "KRW":
                    krw_stock_krw += m_val
                else:
                    usd_stock_usd += float(h.get("market_value") or (m_val / usd_rate))

                r = float(h.get("day_change_rate") or 0.0)
                if r != 0 and (100 + r) > 0:
                    holding_day_gain += m_val * (r / (100 + r))

            cash_krw = sum(float(a.get("cash_krw") or 0.0) for a in owned_accounts)
            cash_usd = sum(float(a.get("cash_usd") or 0.0) for a in owned_accounts)
            cash_total_krw = cash_krw + (cash_usd * usd_rate)

            total_value_krw = stock_value_krw + cash_total_krw
            total_cost_krw = stock_cost_krw + cash_total_krw
            profit_krw = stock_value_krw - stock_cost_krw
            return_rate = (profit_krw / total_cost_krw * 100) if total_cost_krw > 0 else 0.0

            krw_value_krw = krw_stock_krw + cash_krw
            usd_value_krw = (usd_stock_usd + cash_usd) * usd_rate

            past_records = [
                r for r in all_records
                if (r.get("owner") or "모두") == owner
                and r.get("date") and r.get("date") < today
                and float(r.get("total_value_krw") or 0) > 0
            ]
            if past_records:
                past_records.sort(key=lambda x: str(x.get("date")))
                last_rec = past_records[-1]
                prev_val = float(last_rec.get("total_value_krw") or 0)
                day_profit_krw = total_value_krw - prev_val
            else:
                day_profit_krw = holding_day_gain

            snapshot_owner = {
                "date": today,
                "total_value_krw": round(total_value_krw, 2),
                "total_cost_krw": round(total_cost_krw, 2),
                "profit_krw": round(profit_krw, 2),
                "return_rate": round(return_rate, 2),
                "day_profit_krw": round(day_profit_krw, 2),
                "krw_value_krw": round(krw_value_krw, 2),
                "usd_value_krw": round(usd_value_krw, 2),
                "holding_count": len(owned_holdings),
                "currency": "KRW",
                "source": "auto",
                "memo": "자동 기록",
                "owner": owner,
            }
            upsert_asset_record(snapshot_owner, by_date=True, username=username)


@app.get("/api/dashboard")
async def dashboard(request: Request) -> dict:
    username = get_current_username(request)
    if username == "admin":
        return {
            "summary": {"total_value_krw": 0, "total_cost_krw": 0, "profit_krw": 0, "return_rate": 0, "holding_count": 0, "account_count": 0},
            "holdings": [],
            "accounts": [],
            "classifications": [],
            "currency_summary": {},
            "fx_rates": {"KRW": 1.0, "USD": 1385.0},
            "day_change": {"change_krw": 0, "change_rate": 0},
            "updated_at": datetime.now().astimezone().isoformat(),
        }
    data = get_dashboard(username=username)
    from app.services.savings import get_savings_data
    savings_info = get_savings_data(username=username)
    data["bank_accounts"] = savings_info.get("bank_accounts", [])
    data["savings_accounts"] = savings_info.get("savings_accounts", [])
    data["savings_summary"] = savings_info.get("summary", {})
    data["insurance_accounts"] = savings_info.get("insurance_accounts", [])
    data["loan_accounts"] = savings_info.get("loan_accounts", [])

    from app.services.real_estate import get_real_estate_data
    re_info = get_real_estate_data(username=username)
    data["real_estates"] = re_info.get("real_estates", [])
    data["sold_real_estates"] = re_info.get("sold_real_estates", [])
    data["real_estate_summary"] = re_info.get("summary", {})

    from app.services.pnl_records import get_pnl_summary, read_pnl_records
    from app.services.dividend_records import get_actual_dividend_summary, read_dividend_records
    data["realized_pnl_records"] = read_pnl_records(username=username)
    data["realized_pnl_summary"] = get_pnl_summary(owner="모두", username=username)
    data["actual_dividend_records"] = read_dividend_records(username=username)
    data["dividend_summary"] = get_actual_dividend_summary(owner="모두", username=username)

    auto_save_all_owner_snapshots(data, username=username)
    return data


@app.get("/api/dividends")
async def get_dividends(request: Request, owner: str = "모두") -> dict:
    """Return dividend summary and 12-month schedule for holdings."""
    username = get_current_username(request)
    full = get_dashboard(username=username)
    holdings = full.get("holdings", [])
    accounts = full.get("accounts", [])
    if owner != "모두":
        acct_map = {a["id"]: a.get("owner", "모두") for a in accounts}
        holdings = [
            h for h in holdings 
            if (h.get("owner") == owner) or (acct_map.get(h.get("account_id")) == owner)
        ]
    fx_rate = full.get("fx_rates", {}).get("USD", 1385.0)
    summary = await get_web_dividend_summary(holdings, fx_rate=fx_rate)
    return summary


@app.get("/api/actual-dividends")
async def get_actual_dividends(request: Request, owner: str = "모두", year: str | None = None) -> dict:
    """Return actual dividend records and 12-month summary."""
    username = get_current_username(request)
    return get_actual_dividend_summary(owner=owner, year=year, username=username)


@app.post("/api/actual-dividends")
async def add_actual_dividend(request: Request) -> dict:
    """Add a new actual dividend record."""
    username = get_current_username(request)
    body = await request.json()
    record = create_dividend_record(body, username=username)
    return {"message": "배당금이 등록되었습니다.", "record": record}


@app.put("/api/actual-dividends/{record_id}")
async def edit_actual_dividend(record_id: str, request: Request) -> dict:
    """Update an existing actual dividend record."""
    username = get_current_username(request)
    body = await request.json()
    record = update_dividend_record(record_id, body, username=username)
    if not record:
        raise HTTPException(status_code=404, detail="배당 기록을 찾을 수 없습니다.")
    return {"message": "배당금이 수정되었습니다.", "record": record}


@app.delete("/api/actual-dividends/{record_id}")
async def remove_actual_dividend(record_id: str, request: Request) -> dict:
    """Delete an actual dividend record."""
    username = get_current_username(request)
    ok = delete_dividend_record(record_id, username=username)
    if not ok:
        raise HTTPException(status_code=404, detail="배당 기록을 찾을 수 없습니다.")
    return {"message": "배당 기록이 삭제되었습니다."}


@app.post("/api/import-dividends")
async def import_dividends_endpoint(request: Request, file: UploadFile = File(...)) -> dict:
    """Import actual dividend records from Excel or CSV."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="업로드할 파일을 선택하세요.")
    username = get_current_username(request)
    contents = await file.read()
    full = get_dashboard(username=username)
    fx_rate = full.get("fx_rates", {}).get("USD", 1385.0)
    try:
        records = import_dividend_file_data(contents, file.filename, fx_rate=fx_rate, username=username)
        return {
            "message": f"총 {len(records)}건의 배당금 내역을 가져왔습니다.",
            "count": len(records),
            "records": records,
        }
    except Exception as e:
        logger.exception("배당 파일 가져오기 실패")
        raise HTTPException(status_code=400, detail=f"배당 파일 처리 실패: {e}")


@app.post("/api/actual-dividends/clear")
async def clear_actual_dividends_endpoint(request: Request) -> dict:
    """Clear all actual dividend records."""
    username = get_current_username(request)
    clear_dividend_records(username=username)
    return {"message": "모든 실제 배당금 기록이 삭제되었습니다."}


@app.post("/api/actual-dividends/recalculate-fx")
async def recalculate_actual_dividends_fx(request: Request) -> dict:
    """Recalculate USD dividend amounts using historical exchange rates for each deposit date."""
    username = get_current_username(request)
    await sync_historical_fx()
    updated = recalculate_dividend_historical_fx(username=username)
    return {"message": f"총 {updated}건의 해외 배당금 환율이 입금일자 기준으로 재계산되었습니다.", "updated_count": updated}


@app.get("/api/historical-fx")
async def get_historical_fx_endpoint(date: str = "") -> dict:
    """Get historical USD/KRW exchange rate for a given date."""
    today = datetime.now().strftime("%Y-%m-%d")
    target = date.strip() or today
    rate = get_historical_fx_rate(target)
    return {"date": target, "rate": rate, "currency": "USD"}


@app.get("/api/sample/dividends")
async def download_sample_dividends():
    """Download sample Excel file for actual dividend tracking."""
    p = ROOT_DIR / "data" / "샘플_배당.xlsx"
    if not p.exists():
        p = ROOT_DIR / "샘플_배당.xlsx"
    if not p.exists():
        raise HTTPException(status_code=404, detail="샘플_배당.xlsx 파일을 찾을 수 없습니다.")
    return FileResponse(
        path=str(p),
        filename="샘플_배당.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/sample/holdings")
async def download_sample_holdings():
    """Download sample Excel file for portfolio holdings."""
    p = ROOT_DIR / "data" / "샘플_타증권사_보유종목.xlsx"
    if not p.exists():
        p = ROOT_DIR / "샘플_타증권사_보유종목.xlsx"
    if not p.exists():
        raise HTTPException(status_code=404, detail="샘플_타증권사_보유종목.xlsx 파일을 찾을 수 없습니다.")
    return FileResponse(
        path=str(p),
        filename="샘플_타증권사_보유종목.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# Realized PnL API
# ---------------------------------------------------------------------------

@app.get("/api/realized-pnl")
async def get_realized_pnl(request: Request, owner: str = "모두", year: str | None = None, trade_type: str = "all") -> dict:
    """Return realized profit and loss records and summary."""
    username = get_current_username(request)
    return get_pnl_summary(owner=owner, year=year, trade_type=trade_type, username=username)


@app.post("/api/realized-pnl")
async def add_realized_pnl(request: Request) -> dict:
    """Add a new realized PnL record."""
    username = get_current_username(request)
    body = await request.json()
    record = create_pnl_record(body, username=username)
    return {"message": "매도 실현손익이 등록되었습니다.", "record": record}


@app.put("/api/realized-pnl/{record_id}")
async def edit_realized_pnl(record_id: str, request: Request) -> dict:
    """Update an existing realized PnL record."""
    username = get_current_username(request)
    body = await request.json()
    record = update_pnl_record(record_id, body, username=username)
    if not record:
        raise HTTPException(status_code=404, detail="실현손익 기록을 찾을 수 없습니다.")
    return {"message": "매도 실현손익이 수정되었습니다.", "record": record}


@app.delete("/api/realized-pnl/{record_id}")
async def remove_realized_pnl(record_id: str, request: Request) -> dict:
    """Delete a realized PnL record."""
    username = get_current_username(request)
    ok = delete_pnl_record(record_id, username=username)
    if not ok:
        raise HTTPException(status_code=404, detail="실현손익 기록을 찾을 수 없습니다.")
    return {"message": "실현손익 기록이 삭제되었습니다."}


@app.post("/api/realized-pnl/clear")
async def clear_realized_pnl_endpoint(request: Request) -> dict:
    """Clear all realized PnL records."""
    username = get_current_username(request)
    clear_pnl_records(username=username)
    return {"message": "모든 매도 실현손익 기록이 삭제되었습니다."}


@app.post("/api/holdings/clear")
async def clear_holdings_endpoint(request: Request) -> dict:
    """Clear all portfolio holdings."""
    username = get_current_username(request)
    data = read_portfolio(username=username)
    data["holdings"] = []
    write_portfolio(data, username=username)
    return {"message": "모든 보유종목이 삭제되었습니다."}


@app.post("/api/import-realized-pnl")
async def import_realized_pnl_endpoint(request: Request, file: UploadFile = File(...)) -> dict:
    """Import realized PnL records from Excel or CSV."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="업로드할 파일을 선택하세요.")
    username = get_current_username(request)
    contents = await file.read()
    full = get_dashboard(username=username)
    fx_rate = full.get("fx_rates", {}).get("USD", 1385.0)
    try:
        records = import_pnl_file_data(contents, file.filename, fx_rate=fx_rate, username=username)
        return {
            "message": f"총 {len(records)}건의 실현손익 내역을 가져왔습니다.",
            "count": len(records),
            "records": records,
        }
    except Exception as e:
        logger.exception("실현손익 파일 가져오기 실패")
        raise HTTPException(status_code=400, detail=f"실현손익 파일 처리 실패: {e}")


@app.post("/api/realized-pnl/recalculate-fx")
async def recalculate_realized_pnl_fx_endpoint(request: Request) -> dict:
    """Recalculate historical FX rates and KRW amounts for all USD realized PnL records."""
    username = get_current_username(request)
    count = recalculate_pnl_historical_fx(username=username)
    return {
        "message": f"총 {count}건의 달러 실현손익 내역을 매도일자 기준 환율 및 환차손익으로 재계산했습니다.",
        "count": count,
    }


@app.get("/api/sample/realized-pnl")
async def download_sample_pnl():
    """Download sample Excel file for realized profit/loss tracking."""
    p = ROOT_DIR / "data" / "샘플_매도실현손익.xlsx"
    if not p.exists():
        p = ROOT_DIR / "샘플_매도실현손익.xlsx"
    if not p.exists():
        raise HTTPException(status_code=404, detail="샘플_매도실현손익.xlsx 파일을 찾을 수 없습니다.")
    return FileResponse(
        path=str(p),
        filename="샘플_매도실현손익.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/status")
async def status() -> dict:
    return {
        "kb_configured": KBOpenAPI().configured,
        "toss_configured": TossOpenAPI().configured,
        "namoo_configured": NhPlugOpenAPI().configured,
        "storage": "local",
    }


@app.get("/api/toss-wts/status")
async def toss_wts_local_status(request: Request, response: Response = None) -> dict:
    """Local-only WTS readiness state; protected by static allowed-user authorization."""
    get_current_username(request)
    auth_decision = check_wts_feed_static_authorization(getattr(request.state, "user_id", None))
    if not auth_decision.authorized:
        raise HTTPException(
            status_code=403,
            detail={"code": "STATIC_AUTHORIZATION_FAILED"},
            headers={"Cache-Control": "no-store"},
        )
    if response is not None:
        response.headers["Cache-Control"] = "no-store"
    return TossWtsAdapter().get_local_status()


@app.post("/api/toss-wts/feed/confirm")
async def toss_wts_feed_confirm(request: Request) -> JSONResponse:
    """Explicitly confirm current local WTS session generation for the allowed Wealth user."""
    get_current_username(request)
    try:
        decision = confirm_wts_feed_runtime_session(getattr(request.state, "user_id", None))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={"code": "CONFIRMATION_FAILED"},
            headers={"Cache-Control": "no-store"},
        )
    if decision.confirmed and decision.code == "CONFIRMED":
        return JSONResponse(
            status_code=200,
            content={"confirmed": True, "code": "CONFIRMED"},
            headers={"Cache-Control": "no-store"},
        )
    if decision.code == "STATIC_AUTHORIZATION_FAILED":
        raise HTTPException(
            status_code=403,
            detail={"code": "STATIC_AUTHORIZATION_FAILED"},
            headers={"Cache-Control": "no-store"},
        )
    if decision.code == "RUNTIME_MATERIAL_UNAVAILABLE":
        raise HTTPException(
            status_code=503,
            detail={"code": "RUNTIME_MATERIAL_UNAVAILABLE"},
            headers={"Cache-Control": "no-store"},
        )
    raise HTTPException(
        status_code=409,
        detail={"code": decision.code if decision.code else "CONFIRMATION_FAILED"},
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/toss-wts/realized-feed/fetch")
async def toss_wts_realized_feed_fetch(request: Request) -> JSONResponse:
    """Fetch read-only, non-persisted realized P/L feed for the confirmed WTS session."""
    get_current_username(request)
    user_id = getattr(request.state, "user_id", None)
    runtime_decision = check_wts_feed_runtime_confirmation(user_id)
    if not runtime_decision.confirmed:
        if runtime_decision.code == "STATIC_AUTHORIZATION_FAILED":
            raise HTTPException(
                status_code=403,
                detail={"code": "STATIC_AUTHORIZATION_FAILED"},
                headers={"Cache-Control": "no-store"},
            )
        if runtime_decision.code == "RUNTIME_MATERIAL_UNAVAILABLE":
            raise HTTPException(
                status_code=503,
                detail={"code": "RUNTIME_MATERIAL_UNAVAILABLE"},
                headers={"Cache-Control": "no-store"},
            )
        raise HTTPException(
            status_code=409,
            detail={"code": runtime_decision.code},
            headers={"Cache-Control": "no-store"},
        )

    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "Invalid JSON body"},
            headers={"Cache-Control": "no-store"},
        )

    try:
        from_date, to_date, basis = validate_realized_feed_request(
            body.get("from_date"),
            body.get("to_date"),
            body.get("profit_rate_basis"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": str(exc)},
            headers={"Cache-Control": "no-store"},
        )

    try:
        adapter = TossWtsAdapter()
        raw_result = adapter.get_profit_daily(from_date=from_date, to_date=to_date, currency=basis)
        gen_id = get_current_runtime_generation_id(user_id)
        feed_response = build_realized_feed_response(
            from_date,
            to_date,
            basis,
            raw_result,
            user_id=str(user_id) if user_id else None,
            generation_id=gen_id,
        )
        return JSONResponse(
            status_code=200,
            content=feed_response,
            headers={"Cache-Control": "no-store"},
        )
    except TossWtsAdapterError as exc:
        status_code = 502 if exc.code in {"INVALID_JSON", "INVALID_SCHEMA", "UNSUPPORTED_COMMAND"} else 503
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code},
            headers={"Cache-Control": "no-store"},
        )
    except Exception:
        raise HTTPException(
            status_code=500,
            detail={"code": "FEED_FETCH_FAILED"},
            headers={"Cache-Control": "no-store"},
        )


@app.post("/api/toss-wts/realized-feed/import-preview")
async def toss_wts_realized_feed_import_preview(request: Request) -> JSONResponse:
    """Preview duplicate classification for selected WTS rows without persisting."""
    username = get_current_username(request)
    user_id = getattr(request.state, "user_id", None)
    auth_decision = check_wts_feed_static_authorization(user_id)
    if not auth_decision.authorized:
        raise HTTPException(
            status_code=403,
            detail={"code": "STATIC_AUTHORIZATION_FAILED"},
            headers={"Cache-Control": "no-store"},
        )
    runtime_decision = check_wts_feed_runtime_confirmation(user_id)
    if not runtime_decision.confirmed:
        if runtime_decision.code == "RUNTIME_MATERIAL_UNAVAILABLE":
            raise HTTPException(
                status_code=503,
                detail={"code": "RUNTIME_MATERIAL_UNAVAILABLE"},
                headers={"Cache-Control": "no-store"},
            )
        raise HTTPException(
            status_code=409,
            detail={"code": runtime_decision.code},
            headers={"Cache-Control": "no-store"},
        )

    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "Invalid JSON body"},
            headers={"Cache-Control": "no-store"},
        )

    selected_items = body.get("selected_items")
    if not isinstance(selected_items, list) or len(selected_items) == 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "selected_items must be a non-empty list"},
            headers={"Cache-Control": "no-store"},
        )

    account_id = body.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "account_id is required"},
            headers={"Cache-Control": "no-store"},
        )

    portfolio = read_portfolio(username=username)
    accounts = portfolio.get("accounts", [])
    destination_account = next((a for a in accounts if str(a.get("id")) == account_id.strip()), None)
    if not destination_account:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ACCOUNT", "message": "Destination account not found in user portfolio"},
            headers={"Cache-Control": "no-store"},
        )

    gen_id = get_current_runtime_generation_id(user_id)
    existing_records = read_pnl_records(username=username)
    profit_rate_basis = str(body.get("profit_rate_basis") or "KRW").upper()
    if profit_rate_basis not in ("KRW", "USD"):
        profit_rate_basis = "KRW"

    preview_result = preview_toss_wts_realized_selection(
        selected_items=selected_items,
        destination_account=destination_account,
        existing_records=existing_records,
        user_id=str(user_id),
        current_generation_id=gen_id,
        profit_rate_basis=profit_rate_basis,
    )

    items_hash = compute_items_hash(selected_items)
    preview_ticket = sign_import_preview_ticket(
        account_id=str(destination_account["id"]),
        items_hash=items_hash,
        user_id=str(user_id),
        generation_id=gen_id,
    )
    preview_result["preview_ticket"] = preview_ticket

    return JSONResponse(
        status_code=200,
        content=preview_result,
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/toss-wts/realized-feed/import")
async def toss_wts_realized_feed_import(request: Request) -> JSONResponse:
    """Commit eligible selected WTS rows into user's normal realized P/L records.

    Rechecks duplicates at commit time to prevent race conditions.
    """
    username = get_current_username(request)
    user_id = getattr(request.state, "user_id", None)
    auth_decision = check_wts_feed_static_authorization(user_id)
    if not auth_decision.authorized:
        raise HTTPException(
            status_code=403,
            detail={"code": "STATIC_AUTHORIZATION_FAILED"},
            headers={"Cache-Control": "no-store"},
        )
    runtime_decision = check_wts_feed_runtime_confirmation(user_id)
    if not runtime_decision.confirmed:
        if runtime_decision.code == "RUNTIME_MATERIAL_UNAVAILABLE":
            raise HTTPException(
                status_code=503,
                detail={"code": "RUNTIME_MATERIAL_UNAVAILABLE"},
                headers={"Cache-Control": "no-store"},
            )
        raise HTTPException(
            status_code=409,
            detail={"code": runtime_decision.code},
            headers={"Cache-Control": "no-store"},
        )

    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "Invalid JSON body"},
            headers={"Cache-Control": "no-store"},
        )

    selected_items = body.get("selected_items")
    if not isinstance(selected_items, list) or len(selected_items) == 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "selected_items must be a non-empty list"},
            headers={"Cache-Control": "no-store"},
        )

    account_id = body.get("account_id")
    if not isinstance(account_id, str) or not account_id.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "account_id is required"},
            headers={"Cache-Control": "no-store"},
        )

    portfolio = read_portfolio(username=username)
    accounts = portfolio.get("accounts", [])
    destination_account = next((a for a in accounts if str(a.get("id")) == account_id.strip()), None)
    if not destination_account:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_ACCOUNT", "message": "Destination account not found in user portfolio"},
            headers={"Cache-Control": "no-store"},
        )

    gen_id = get_current_runtime_generation_id(user_id)
    items_hash = compute_items_hash(selected_items)

    preview_ticket = body.get("preview_ticket")
    if preview_ticket:
        valid_ticket, ticket_err = verify_import_preview_ticket(
            preview_ticket,
            account_id=str(destination_account["id"]),
            items_hash=items_hash,
            user_id=str(user_id),
            current_generation_id=gen_id,
        )
        if not valid_ticket:
            raise HTTPException(
                status_code=400,
                detail={"code": ticket_err or "PREVIEW_TICKET_INVALID", "message": f"Preview verification failed: {ticket_err}"},
                headers={"Cache-Control": "no-store"},
            )

    include_possible_duplicates = bool(body.get("include_possible_duplicates", False))
    profit_rate_basis = str(body.get("profit_rate_basis") or "KRW").upper()
    if profit_rate_basis not in ("KRW", "USD"):
        profit_rate_basis = "KRW"

    fresh_existing = read_pnl_records(username=username)
    classification = preview_toss_wts_realized_selection(
        selected_items=selected_items,
        destination_account=destination_account,
        existing_records=fresh_existing,
        user_id=str(user_id),
        current_generation_id=gen_id,
        profit_rate_basis=profit_rate_basis,
    )

    imported_count = 0
    already_imported_count = 0
    possible_duplicate_skipped = 0
    invalid_count = 0
    imported_ids: list[str] = []
    now_iso = datetime.now().astimezone().isoformat()

    for item in classification["items"]:
        status = item["status"]
        if status == "ALREADY_IMPORTED":
            already_imported_count += 1
            continue
        if status == "INVALID":
            invalid_count += 1
            continue
        if status == "POSSIBLE_DUPLICATE":
            if not include_possible_duplicates:
                possible_duplicate_skipped += 1
                continue

        candidate = item.get("candidate")
        if not candidate:
            invalid_count += 1
            continue

        candidate_payload = dict(candidate)
        candidate_payload["source"] = "toss_wts"
        candidate_payload["source_fingerprint"] = item["fingerprint"]
        candidate_payload["source_scope_verified"] = False
        candidate_payload["imported_by_user_action"] = True
        candidate_payload["imported_at"] = now_iso

        created = create_pnl_record(candidate_payload, username=username)
        imported_ids.append(created["id"])
        imported_count += 1

    return JSONResponse(
        status_code=200,
        content={
            "selected": len(selected_items),
            "imported": imported_count,
            "already_imported": already_imported_count,
            "possible_duplicate_skipped": possible_duplicate_skipped,
            "invalid": invalid_count,
            "imported_ids": imported_ids,
            "scope_kind": "unverified",
            "scope_verified": False,
            "destination_account": {
                "id": destination_account.get("id"),
                "broker": destination_account.get("broker"),
                "account_name": destination_account.get("account_name") or destination_account.get("name"),
                "owner": destination_account.get("owner"),
            },
        },
        headers={"Cache-Control": "no-store"},
    )


# ---------------------------------------------------------------------------
# Family accounts API
# ---------------------------------------------------------------------------

@app.get("/api/accounts")
async def get_accounts(request: Request, group: str = "All", owner: str = "모두") -> dict:
    """Return accounts filtered by family_group and aggregated summary."""
    username = get_current_username(request)
    full = get_dashboard(username=username)
    accounts = full.get("accounts", [])
    filtered = [a for a in accounts
                if (owner == "모두" or a.get("owner", "모두") == owner)
                and (group == "All" or a.get("family_group", "All") == group)]
    filtered_account_ids = {a.get("id") for a in filtered}
    filtered_holdings = [
        holding for holding in full.get("holdings", [])
        if holding.get("account_id") in filtered_account_ids
    ]
    total_stock_value = sum(a.get("stock_value_krw", 0) for a in filtered)
    total_cash = sum(a.get("cash_krw", 0) for a in filtered)
    total_value = total_stock_value + total_cash
    profit = sum(a.get("profit_krw", 0) for a in filtered)
    holding_count = sum(a.get("holding_count", 0) for a in filtered)
    return {
        "summary": {
            "total_value_krw": total_value,
            "total_stock_value_krw": total_stock_value,
            "total_cash_krw": total_cash,
            "profit_krw": profit,
            "return_rate": profit / total_stock_value * 100 if total_stock_value else 0,
            "holding_count": holding_count,
            "account_count": len(filtered),
        },
        "accounts": filtered,
        "holdings": filtered_holdings,
        "fx_rates": full.get("fx_rates", {}),
        "currency_summary": full.get("currency_summary", {}),
        "classifications": full.get("classifications", []),
        "updated_at": full.get("updated_at"),
    }


@app.post("/api/accounts")
async def create_account(request: Request) -> dict:
    """Create a new account entry."""
    import uuid
    username = get_current_username(request)
    body = await request.json()
    broker = (body.get("broker") or "").strip()
    account_name = (body.get("account_name") or body.get("name") or "").strip()
    owner = (body.get("owner") or "모두").strip()
    if not broker or not account_name:
        raise HTTPException(status_code=400, detail="증권사와 계좌 이름은 필수입니다.")
    data = read_portfolio(username=username)
    acc_type = (body.get("account_type") or "general").strip()
    income_lvl = (body.get("income_level") or "low").strip()
    annual_dep = max(0.0, float(body.get("annual_deposit") or 0.0))
    isa_tr = max(0.0, float(body.get("isa_transfer_amount") or 0.0))
    isa_year = str(body.get("isa_transfer_year") or "2026").strip()
    def _parse_bool(val: Any, default: bool = True) -> bool:
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        if isinstance(val, (int, float)):
            return bool(val)
        if isinstance(val, str):
            s = val.strip().lower()
            if s in ("false", "0", "no", "off", "non_deductible"):
                return False
            if s in ("true", "1", "yes", "on", "deductible"):
                return True
        return default

    tax_deductible = _parse_bool(body.get("tax_deductible"), True)

    new_account = {
        "id": str(uuid.uuid4()),
        "broker": broker,
        "name": account_name,
        "owner": owner,
        "account_type": acc_type,
        "tax_deductible": tax_deductible,
        "income_level": income_lvl,
        "annual_deposit": annual_dep,
        "isa_transfer_amount": isa_tr,
        "isa_transfer_year": isa_year,
        "family_group": "All",
        "market_value_krw": 0,
        "stock_value_krw": 0,
        "cash_krw": 0,
        "cash_usd": 0,
        "cash_total_krw": 0,
        "profit_krw": 0,
        "holding_count": 0,
    }
    cash_krw = float(to_number(body.get("cash_krw", 0.0)))
    cash_usd = float(to_number(body.get("cash_usd", 0.0)))
    if cash_krw > 0 or cash_usd > 0:
        cash_balances = data["settings"].setdefault("cash_balances", {})
        cash_balances[new_account["id"]] = {"KRW": cash_krw, "USD": cash_usd}
        usd_rate = float(data.get("settings", {}).get("usd_krw_rate", 1400.0))
        cash_total_krw = cash_krw + (cash_usd * usd_rate)
        new_account["cash_krw"] = cash_krw
        new_account["cash_usd"] = cash_usd
        new_account["cash_total_krw"] = cash_total_krw
        new_account["market_value_krw"] = cash_total_krw
    if "yearly_contributions" in body:
        new_account["yearly_contributions"] = body.get("yearly_contributions") or []
    data.setdefault("accounts", []).append(new_account)
    write_portfolio(data, username=username)
    return {"message": f"계좌 '{broker} - {account_name}'이(가) 추가되었습니다.", **new_account}


# ---------------------------------------------------------------------------
# Bank accounts & Savings accounts (예·적금 및 일반 은행 계좌) API
# ---------------------------------------------------------------------------

@app.get("/api/savings")
async def get_savings_endpoint(request: Request) -> dict:
    from app.services.savings import get_savings_data
    username = get_current_username(request)
    return get_savings_data(username=username)

@app.post("/api/bank-accounts")
async def save_bank_account_endpoint(request: Request) -> dict:
    from app.services.savings import OverdraftValidationError, save_bank_account
    username = get_current_username(request)
    body = await request.json()
    try:
        record = save_bank_account(body, username=username)
    except OverdraftValidationError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"message": "은행 계좌가 저장되었습니다.", "account": record}

@app.delete("/api/bank-accounts/{acc_id}")
async def delete_bank_account_endpoint(acc_id: str, request: Request) -> dict:
    from app.services.savings import OverdraftValidationError, delete_bank_account
    username = get_current_username(request)
    try:
        success = delete_bank_account(acc_id, username=username)
    except OverdraftValidationError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not success:
        raise HTTPException(404, "계좌를 찾을 수 없습니다.")
    return {"message": "은행 계좌가 삭제되었습니다."}

@app.post("/api/savings-accounts")
async def save_saving_account_endpoint(request: Request) -> dict:
    from app.services.savings import save_saving_account
    username = get_current_username(request)
    body = await request.json()
    record = save_saving_account(body, username=username)
    return {"message": "예·적금 상품이 저장되었습니다.", "saving": record}

@app.delete("/api/savings-accounts/{saving_id}")
async def delete_saving_account_endpoint(saving_id: str, request: Request) -> dict:
    from app.services.savings import delete_saving_account
    username = get_current_username(request)
    success = delete_saving_account(saving_id, username=username)
    if not success:
        raise HTTPException(404, "예·적금 상품을 찾을 수 없습니다.")
    return {"message": "예·적금 상품이 삭제되었습니다."}

@app.post("/api/savings/calculate")
async def calculate_saving_endpoint(request: Request) -> dict:
    from app.services.savings import calculate_interest
    body = await request.json()
    calc = calculate_interest(
        saving_type=body.get("saving_type", "deposit"),
        principal_or_monthly=float(body.get("principal_or_monthly") or 0.0),
        interest_rate=float(body.get("interest_rate") or 0.0),
        duration_months=int(body.get("duration_months") or 12),
        tax_type=body.get("tax_type", "normal"),
    )
    return {"calc": calc}

@app.post("/api/insurance-accounts")
async def save_insurance_account_endpoint(request: Request) -> dict:
    from app.services.savings import save_insurance_account
    username = get_current_username(request)
    body = await request.json()
    record = save_insurance_account(body, username=username)
    return {"message": "보험/연금 상품이 저장되었습니다.", "insurance": record}

@app.delete("/api/insurance-accounts/{ins_id}")
async def delete_insurance_account_endpoint(ins_id: str, request: Request) -> dict:
    from app.services.savings import delete_insurance_account
    username = get_current_username(request)
    success = delete_insurance_account(ins_id, username=username)
    if not success:
        raise HTTPException(404, "보험/연금 상품을 찾을 수 없습니다.")
    return {"message": "보험/연금 상품이 삭제되었습니다."}

@app.post("/api/loan-accounts")
async def save_loan_account_endpoint(request: Request) -> dict:
    from app.services.savings import OverdraftValidationError, save_loan_account
    username = get_current_username(request)
    body = await request.json()
    try:
        record = save_loan_account(body, username=username)
    except OverdraftValidationError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"message": "대출·마이너스통장이 저장되었습니다.", "loan": record}

@app.delete("/api/loan-accounts/{loan_id}")
async def delete_loan_account_endpoint(loan_id: str, request: Request) -> dict:
    from app.services.savings import OverdraftValidationError, delete_loan_account
    username = get_current_username(request)
    try:
        success = delete_loan_account(loan_id, username=username)
    except OverdraftValidationError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not success:
        raise HTTPException(404, "대출·마이너스통장을 찾을 수 없습니다.")
    return {"message": "대출·마이너스통장이 삭제되었습니다."}

@app.post("/api/loans/calculate")
async def calculate_loan_endpoint(request: Request) -> dict:
    from app.services.savings import calculate_loan_interest
    body = await request.json()
    calc = calculate_loan_interest(
        current_balance=float(body.get("current_balance") or 0.0),
        interest_rate=float(body.get("interest_rate") or 0.0),
        repayment_type=body.get("repayment_type", "bullet"),
        remaining_months=int(body.get("remaining_months") or 12),
    )
    return {"calc": calc}


# ---------------------------------------------------------------------------
# Real Estate CRUD API
# ---------------------------------------------------------------------------

@app.get("/api/real-estates")
async def list_real_estates(request: Request) -> dict:
    username = get_current_username(request)
    from app.services.real_estate import get_real_estate_data
    return get_real_estate_data(username=username)

@app.post("/api/real-estates")
async def create_or_update_real_estate(request: Request) -> dict:
    username = get_current_username(request)
    body = await request.json()
    from app.services.real_estate import save_real_estate
    item = save_real_estate(body, username=username)
    return {"message": "부동산 자산이 저장되었습니다.", "real_estate": item}

@app.delete("/api/real-estates/{re_id}")
async def remove_real_estate(request: Request, re_id: str) -> dict:
    username = get_current_username(request)
    from app.services.real_estate import delete_real_estate
    ok = delete_real_estate(re_id, username=username)
    if not ok:
        raise HTTPException(404, "해당 부동산 항목을 찾을 수 없습니다.")
    return {"message": "부동산 자산이 삭제되었습니다."}


@app.post("/api/real-estates/{re_id}/sell")
async def sell_real_estate_and_record_pnl(request: Request, re_id: str) -> dict:
    """부동산 매각을 처리하고 실현손익(양도차익)을 기록합니다. 직접 매도(re_id='direct'/'new')도 지원."""
    username = get_current_username(request)
    body = await request.json()
    from app.services.portfolio import read_portfolio
    from app.services.pnl_records import create_pnl_record
    from app.services.real_estate import delete_real_estate

    pf = read_portfolio(username)
    re_list = pf.get("real_estates", [])
    target = next((r for r in re_list if r.get("id") == re_id), None)
    
    is_direct = re_id in ("direct", "new") or not target
    if not target and not is_direct:
        raise HTTPException(404, "해당 부동산 항목을 찾을 수 없습니다.")

    sell_price = float(body.get("sell_price") or 0.0)
    expenses = float(body.get("expenses") or 0.0)
    sell_date = str(body.get("sell_date") or datetime.now().strftime("%Y-%m-%d")).strip()
    purchase_price = float(body.get("purchase_price") or (target.get("purchase_price") if target else 0.0) or 0.0)
    pnl_krw = round(sell_price - purchase_price - expenses)

    re_name = str(body.get("name") or (target.get("name") if target else "부동산") or "부동산").strip()
    pnl_title = f"[부동산] {re_name}"
    owner = str(body.get("owner") or (target.get("owner") if target else "모두") or "모두").strip()
    memo = str(body.get("memo") or f"매도가 ₩{sell_price:,.0f}, 매수가 ₩{purchase_price:,.0f}, 필요경비 ₩{expenses:,.0f}").strip()

    address = str(target.get("address", "") if target else body.get("address", "")).strip()
    original_property_type = str(target.get("property_type", "own") if target else body.get("property_type", "own")).strip()
    exclusive_area = float(target.get("exclusive_area") or body.get("exclusive_area") or 0.0) if target else float(body.get("exclusive_area") or 0.0)
    acquisition_date = str(target.get("contract_date", "") if target else body.get("acquisition_date", "")).strip()
    is_joint = bool(target.get("is_joint_ownership", False) if target else body.get("is_joint_ownership", False))
    ownerships = target.get("ownerships", []) if target else body.get("ownerships", [])

    pnl_payload = {
        "date": sell_date,
        "code": "REAL_ESTATE",
        "name": pnl_title,
        "asset_type": "real_estate",
        "currency": "KRW",
        "pnl": pnl_krw,
        "pnl_krw": pnl_krw,
        "owner": owner,
        "memo": memo,
        "re_id": re_id if not is_direct else "",
        "real_estate_name": re_name,
        "purchase_price": purchase_price,
        "sell_price": sell_price,
        "expenses": expenses,
        "address": address,
        "original_property_type": original_property_type,
        "exclusive_area": exclusive_area,
        "acquisition_date": acquisition_date,
        "is_joint_ownership": is_joint,
        "ownerships": ownerships,
    }
    pnl_rec = create_pnl_record(pnl_payload, username=username)

    removed = False
    if target and body.get("remove_from_assets", True):
        delete_real_estate(re_id, username=username)
        removed = True

    return {
        "message": f"[{re_name}] 매각 실현손익(₩{pnl_krw:,.0f})이 성공적으로 기록되었습니다.",
        "pnl_krw": pnl_krw,
        "pnl_record": pnl_rec,
        "removed_from_assets": removed,
    }


@app.get("/api/real-estates/kb-price")
async def get_kb_price_api(
    request: Request,
    name: str = "",
    area: float = 0.0,
    complex_no: str = ""
) -> dict:
    get_current_username(request)
    import re
    from app.services.kb_land import search_kb_complex, get_kb_market_prices

    c_no = complex_no.strip()
    complex_info = None
    complexes = []

    if not c_no and name:
        clean_name = re.sub(r'\s*\d+[-~_동호].*$', '', name).strip()
        complexes = search_kb_complex(clean_name or name)
        if complexes:
            c_no = complexes[0]["complex_no"]
            complex_info = complexes[0]

    if not c_no:
        return {"ok": False, "message": f"'{name}' 단지를 KB부동산에서 찾을 수 없습니다. 아파트명을 확인해 주세요.", "complexes": []}

    price_data = get_kb_market_prices(c_no, target_area=area if area > 0 else None)
    if "error" in price_data:
        return {"ok": False, "message": price_data["error"], "complexes": complexes}

    return {
        "ok": True,
        "complex_no": c_no,
        "complex_info": complex_info,
        "complexes": complexes,
        "matched": price_data.get("matched"),
        "types": price_data.get("types", []),
    }


@app.post("/api/real-estates/{re_id}/refresh-kb-price")
async def refresh_kb_price_api(request: Request, re_id: str) -> dict:
    username = get_current_username(request)
    data = read_portfolio(username)
    real_estates = data.get("real_estates", [])
    item = next((r for r in real_estates if r.get("id") == re_id), None)
    if not item:
        raise HTTPException(404, "부동산 항목을 찾을 수 없습니다.")

    import re
    from datetime import datetime
    from app.services.kb_land import search_kb_complex, get_kb_market_prices
    from app.services.portfolio import write_portfolio

    c_no = (item.get("kb_complex_no") or "").strip()
    if not c_no:
        clean_name = re.sub(r'\s*\d+[-~_동호].*$', '', item.get("name") or "").strip()
        complexes = search_kb_complex(clean_name or item.get("name") or "")
        if complexes:
            c_no = complexes[0]["complex_no"]
            item["kb_complex_no"] = c_no

    if not c_no:
        raise HTTPException(404, f"'{item.get('name')}' 단지를 KB부동산에서 찾지 못했습니다.")

    excl_area = float(item.get("exclusive_area") or 0.0)
    price_data = get_kb_market_prices(c_no, target_area=excl_area if excl_area > 0 else None)
    if "error" in price_data or not price_data.get("matched"):
        raise HTTPException(400, price_data.get("error") or "KB시세 정보를 찾을 수 없습니다.")

    matched = price_data["matched"]
    new_price = matched.get("deal_avg") or matched.get("deal_high") or matched.get("deal_low") or 0
    if new_price > 0:
        item["current_price"] = float(new_price)
        item["kb_complex_no"] = c_no
        item["kb_matched_type"] = matched.get("type_display")
        item["updated_at"] = datetime.now().astimezone().isoformat()
        write_portfolio(data, username)
        return {
            "message": f"KB시세가 갱신되었습니다. (₩{new_price:,.0f})",
            "new_price": new_price,
            "matched_type": matched.get("type_display"),
            "real_estate": item
        }
    else:
        raise HTTPException(400, "조회된 KB시세 금액이 0원입니다.")

# Family members CRUD API
# ---------------------------------------------------------------------------

@app.get("/api/family-members")
async def list_family_members(request: Request) -> dict:
    username = get_current_username(request)
    data = read_portfolio(username=username)
    return {"members": get_family_members(data)}

@app.post("/api/family-members")
async def add_family_member(request: Request) -> dict:
    username = get_current_username(request)
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "이름을 입력해 주세요.")
    data = read_portfolio(username=username)
    members = get_family_members(data)
    if name in members:
        raise HTTPException(409, "이미 존재하는 이름입니다.")
    members.append(name)
    data.setdefault("settings", {})["family_members"] = members
    write_portfolio(data, username=username)
    return {"members": members, "message": f"'{name}' 구성원을 추가했습니다."}

@app.put("/api/family-members/{old_name}")
async def rename_family_member(old_name: str, request: Request) -> dict:
    username = get_current_username(request)
    body = await request.json()
    new_name = (body.get("name") or "").strip()
    if not new_name:
        raise HTTPException(400, "새 이름을 입력해 주세요.")
    data = read_portfolio(username=username)
    members = get_family_members(data)
    if old_name not in members:
        raise HTTPException(404, "구성원을 찾지 못했습니다.")
    if new_name in members and new_name != old_name:
        raise HTTPException(409, "이미 존재하는 이름입니다.")
    members = [new_name if m == old_name else m for m in members]
    data.setdefault("settings", {})["family_members"] = members
    # Update all accounts with old_name owner -> new_name
    for acct in data.get("accounts", []):
        if acct.get("owner") == old_name:
            acct["owner"] = new_name
    write_portfolio(data, username=username)
    return {"members": members, "message": f"'{old_name}' -> '{new_name}'으로 이름을 변경했습니다."}

@app.delete("/api/family-members/{member_name}")
async def delete_family_member(member_name: str, request: Request) -> dict:
    username = get_current_username(request)
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


@app.get("/api/market-overview")
async def market_overview() -> dict:
    return await fetch_market_overview()

@app.post("/api/holdings", status_code=201)
async def create_holding(payload: HoldingCreate, request: Request) -> dict:
    username = get_current_username(request)
    data = read_portfolio(username=username)
    account_id = get_or_add_account(data, payload.broker.strip(), payload.account_name.strip(), "manual")
    item = normalize_holding(payload.model_dump(), account_id, payload.broker.strip(), payload.account_name.strip(), "manual")
    # propagate owner to account
    owner_val = getattr(payload, "owner", "모두") or "모두"
    for acct in data.get("accounts", []):
        if acct.get("id") == account_id:
            acct["owner"] = owner_val
            break
    upsert_holdings(data, [item])
    write_portfolio(data, username=username)
    return {"message": "보유종목을 저장했습니다.", "dashboard": get_dashboard(username=username)}


@app.delete("/api/holdings/{holding_id}")
async def delete_holding(holding_id: str, request: Request) -> dict:
    username = get_current_username(request)
    data = read_portfolio(username=username)
    before = len(data["holdings"])
    data["holdings"] = [holding for holding in data["holdings"] if holding["id"] != holding_id]
    if before == len(data["holdings"]):
        raise HTTPException(404, "보유종목을 찾지 못했습니다.")
    used_accounts = {holding["account_id"] for holding in data["holdings"]}
    data["accounts"] = [account for account in data["accounts"] if account["id"] in used_accounts]
    write_portfolio(data, username=username)
    return {"message": "보유종목을 삭제했습니다."}


@app.delete("/api/accounts/{account_id}")
async def delete_account(account_id: str, request: Request) -> dict:
    username = get_current_username(request)
    data = read_portfolio(username=username)
    if not any(account.get("id") == account_id for account in data["accounts"]):
        raise HTTPException(404, "계좌를 찾지 못했습니다.")
    data["accounts"] = [account for account in data["accounts"] if account.get("id") != account_id]
    data["holdings"] = [holding for holding in data["holdings"] if holding.get("account_id") != account_id]
    if "cash_balances" in data["settings"] and account_id in data["settings"]["cash_balances"]:
        del data["settings"]["cash_balances"][account_id]
    write_portfolio(data, username=username)
    return {"message": "증권사 계좌와 연결된 보유종목을 삭제했습니다."}


@app.put("/api/accounts/{account_id}")
async def rename_account(account_id: str, payload: dict, request: Request) -> dict:
    username = get_current_username(request)
    name = str(payload.get("name") or payload.get("account_name") or "").strip()
    broker = str(payload.get("broker") or "").strip()
    if not name:
        raise HTTPException(400, "계좌 이름을 입력해 주세요.")
    data = read_portfolio(username=username)
    account = next((item for item in data["accounts"] if item.get("id") == account_id), None)
    if account is None:
        raise HTTPException(404, "계좌를 찾지 못했습니다.")
    account["name"] = name
    if broker:
        account["broker"] = broker
    owner_val = str(payload.get("owner") or "").strip()
    if owner_val:
        account["owner"] = owner_val
    if "account_type" in payload:
        account["account_type"] = str(payload.get("account_type") or "general").strip()
    if "tax_deductible" in payload:
        td_val = payload.get("tax_deductible")
        if isinstance(td_val, bool):
            account["tax_deductible"] = td_val
        elif isinstance(td_val, str):
            account["tax_deductible"] = td_val.strip().lower() not in ("false", "0", "no", "off", "non_deductible")
        elif isinstance(td_val, (int, float)):
            account["tax_deductible"] = bool(td_val)
        else:
            account["tax_deductible"] = bool(td_val)
    if "income_level" in payload:
        account["income_level"] = str(payload.get("income_level") or "low").strip()
    if "annual_deposit" in payload:
        account["annual_deposit"] = max(0.0, float(payload.get("annual_deposit") or 0.0))
    if "isa_transfer_amount" in payload:
        account["isa_transfer_amount"] = max(0.0, float(payload.get("isa_transfer_amount") or 0.0))
    if "isa_transfer_year" in payload:
        account["isa_transfer_year"] = str(payload.get("isa_transfer_year") or "").strip()
    if "yearly_contributions" in payload:
        ycs = payload.get("yearly_contributions") or []
        inc = account.get("income_level") or "low"
        for yc in ycs:
            if isinstance(yc, dict) and not yc.get("income_level"):
                yc["income_level"] = inc
        account["yearly_contributions"] = ycs
    elif account.get("account_type") in ("pension_savings", "irp") and float(account.get("annual_deposit") or 0) > 0 and not account.get("yearly_contributions"):
        from datetime import datetime as _dt
        account["yearly_contributions"] = [{
            "year": str(_dt.now().year),
            "deposit": float(account.get("annual_deposit") or 0),
            "is_deductible": account.get("tax_deductible", True),
            "income_level": account.get("income_level", "low")
        }]

    if "cash_krw" in payload or "cash_usd" in payload:
        cash_balances = data["settings"].setdefault("cash_balances", {})
        existing_cash = cash_balances.get(account_id, {})
        cash_krw = float(to_number(payload["cash_krw"])) if "cash_krw" in payload else float(to_number(existing_cash.get("KRW", existing_cash.get("krw", 0.0))))
        cash_usd = float(to_number(payload["cash_usd"])) if "cash_usd" in payload else float(to_number(existing_cash.get("USD", existing_cash.get("usd", 0.0))))
        cash_balances[account_id] = {"KRW": cash_krw, "USD": cash_usd}

    for holding in data["holdings"]:
        if holding.get("account_id") == account_id:
            holding["account_name"] = name
            if broker:
                holding["broker"] = broker
    write_portfolio(data, username=username)
    return {"message": "증권사 및 계좌 정보를 수정했습니다.", "dashboard": get_dashboard(username=username)}


@app.get("/api/tax-benefits")
async def get_tax_benefits_endpoint(request: Request, owner: str | None = None) -> dict:
    from app.services.tax_benefit import get_total_tax_benefits
    username = get_current_username(request)
    data = read_portfolio(username=username)
    return get_total_tax_benefits(data, owner=owner)


@app.put("/api/accounts/{account_id}/cash")
async def update_account_cash(account_id: str, payload: dict, request: Request) -> dict:
    username = get_current_username(request)
    data = read_portfolio(username=username)
    if not any(account.get("id") == account_id for account in data["accounts"]):
        raise HTTPException(404, "계좌를 찾지 못했습니다.")
    cash_krw = float(to_number(payload.get("cash_krw") or payload.get("KRW")))
    cash_usd = float(to_number(payload.get("cash_usd") or payload.get("USD")))
    cash_balances = data["settings"].setdefault("cash_balances", {})
    cash_balances[account_id] = {"KRW": cash_krw, "USD": cash_usd}
    write_portfolio(data, username=username)
    return {"message": "계좌 예수금을 수정했습니다.", "dashboard": get_dashboard(username=username)}


@app.put("/api/holdings/{holding_id}")
async def update_holding(holding_id: str, payload: HoldingCreate, request: Request) -> dict:
    username = get_current_username(request)
    data = read_portfolio(username=username)
    current = next((item for item in data["holdings"] if item["id"] == holding_id), None)
    if current is None:
        raise HTTPException(404, "보유종목을 찾지 못했습니다.")
    broker = payload.broker.strip()
    account_name = payload.account_name.strip()
    account_id = get_or_add_account(data, broker, account_name, current.get("source", "manual"))
    item = normalize_holding(payload.model_dump(), account_id, broker, account_name, current.get("source", "manual"))
    item["id"] = holding_id
    data["holdings"] = [item if holding["id"] == holding_id else holding for holding in data["holdings"]]
    write_portfolio(data, username=username)
    return {"message": "보유종목을 수정했습니다.", "dashboard": get_dashboard(username=username)}


@app.post("/api/import")
async def import_portfolio(request: Request, file: UploadFile = File(...), broker: str = "기타 증권사") -> dict:
    if Path(file.filename or "").suffix.lower() not in {".csv", ".xlsx", ".xlsm"}:
        raise HTTPException(400, "CSV 또는 XLSX 파일만 가져올 수 있습니다.")
    username = get_current_username(request)
    try:
        count, warnings = import_rows(file.filename or "portfolio.csv", await file.read(), broker, username=username)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"message": f"{count}개 보유종목을 반영했습니다.", "count": count, "warnings": warnings}



@app.get("/api/export")
async def export_data(request: Request):
    """포트폴리오, 가계부 등 전체 데이터를 JSON 파일로 다운로드"""
    import json
    from app.services.portfolio import read_portfolio
    from app.services.asset_records import read_asset_records
    from app.services.dividend_records import read_dividend_records
    from app.services.pnl_records import read_pnl_records
    from app.services.ledger import read_ledger

    username = _require_authenticated_username(request)
    bundle = _sanitize_export_data({
        "version": "2.2",
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "user": username,
        "backup_policy": "general_data_only",
        "portfolio": read_portfolio(username=username),
        "asset_records": read_asset_records(username=username),
        "dividend_records": read_dividend_records(username=username),
        "realized_pnl_records": read_pnl_records(username=username),
        "ledger": read_ledger(username=username),
    })
    content = json.dumps(bundle, ensure_ascii=False, indent=2)
    from starlette.responses import Response
    today_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"wealth_{username}_{today_str}.json"
    return Response(
        content=content.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/import-backup")
async def import_backup(request: Request, file: UploadFile = File(...)) -> dict:
    """백업 JSON 파일에서 데이터 복원 (포트폴리오, 자산기록, 배당, 손익, 가계부, OpenAPI)"""
    import json
    from app.services.portfolio import write_portfolio
    from app.services.asset_records import write_asset_records
    from app.services.dividend_records import write_dividend_records
    from app.services.pnl_records import write_pnl_records
    from app.services.ledger import write_ledger, DEFAULT_CATEGORIES
    from app.services.user_openapi import save_user_openapi_config

    username = get_current_username(request)
    try:
        raw = await file.read()
        bundle = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(400, f"JSON 파싱 실패: {exc}") from exc

    if "portfolio" not in bundle and "asset_records" not in bundle and "ledger" not in bundle:
        raise HTTPException(400, "유효한 백업 파일이 아닙니다.")

    msgs = []
    if "portfolio" in bundle and bundle["portfolio"]:
        write_portfolio(bundle["portfolio"], username=username, replace_planning=True)
        msgs.append("포트폴리오")
    if "asset_records" in bundle and bundle["asset_records"]:
        write_asset_records(bundle["asset_records"], username=username)
        msgs.append("자산기록")
    if "dividend_records" in bundle and bundle["dividend_records"]:
        write_dividend_records(bundle["dividend_records"], username=username)
        msgs.append("배당내역")
    if "realized_pnl_records" in bundle and bundle["realized_pnl_records"]:
        write_pnl_records(bundle["realized_pnl_records"], username=username)
        msgs.append("매도실현손익")
    if "ledger" in bundle and isinstance(bundle["ledger"], dict):
        ledger_data = bundle["ledger"]
        ledger_data.setdefault("version", "1.0")
        ledger_data.setdefault("categories", DEFAULT_CATEGORIES)
        ledger_data.setdefault("transactions", [])
        ledger_data.setdefault("recurring", [])
        ledger_data.setdefault("cards", [])
        ledger_data.setdefault("budgets", {})
        write_ledger(ledger_data, username=username)
        msgs.append("가계부")
    if "openapi_config" in bundle and isinstance(bundle["openapi_config"], dict):
        try:
            save_user_openapi_config(username=username, update_data=bundle["openapi_config"])
            msgs.append("OpenAPI설정")
        except Exception as e:
            logger.warning("OpenAPI config restore warning: %s", e)

    return {"message": f"{', '.join(msgs)} 데이터를 복원했습니다."}

@app.post("/api/demo")
async def load_demo() -> dict:
    seed_demo()
    return {"message": "예시 데이터를 불러왔습니다."}


@app.post("/api/clear")
async def clear_all(request: Request) -> dict:
    username = get_current_username(request)
    data = read_portfolio(username=username)
    data["holdings"] = []
    data["accounts"] = []
    write_portfolio(data, username=username)
    return {"message": "저장된 보유내역을 모두 지웠습니다."}


@app.get("/api/planning")
async def get_planning(request: Request) -> dict:
    from app.services.planning import read_planning
    return read_planning(_require_authenticated_username(request))


@app.post("/api/planning/{operation}")
async def save_planning(operation: str, request: Request) -> dict:
    from app.services.planning import mutate, PlanningConflict
    username = _require_authenticated_username(request)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "입력 형식이 올바르지 않습니다.")
    try:
        return mutate(username, operation, payload)
    except PlanningConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(400, "입력값을 확인하세요. " + str(exc)) from exc


@app.get("/api/asset-records")
async def get_asset_records(request: Request, owner: str = "") -> dict:
    username = get_current_username(request)
    records = list_asset_records(username=username)
    if owner:
        records = [r for r in records if (r.get("owner") or "모두") == owner]
    return {"records": records}



@app.post("/api/asset-records")
async def create_asset_record(payload: dict, request: Request) -> dict:
    username = get_current_username(request)
    payload["owner"] = payload.get("owner") or "모두"
    record = upsert_asset_record(payload, by_date=bool(payload.get("date")), username=username)
    return {"message": "자산기록을 저장했습니다.", "record": record}


@app.put("/api/asset-records/{record_id}")
async def update_asset_record(record_id: str, payload: dict, request: Request) -> dict:
    username = get_current_username(request)
    payload["id"] = record_id
    if "owner" not in payload or not payload["owner"]:
        payload["owner"] = "모두"
    record = upsert_asset_record(payload, username=username)
    return {"message": "자산기록을 수정했습니다.", "record": record}


@app.delete("/api/asset-records/{record_id}")
async def remove_asset_record(record_id: str, request: Request) -> dict:
    username = get_current_username(request)
    if not delete_asset_record(record_id, username=username):
        raise HTTPException(404, "자산기록을 찾지 못했습니다.")
    return {"message": "자산기록을 삭제했습니다."}


@app.post("/api/asset-records/snapshot")
async def snapshot_asset_record(request: Request) -> dict:
    username = get_current_username(request)
    data = get_dashboard(username=username)
    if not data["summary"]["holding_count"]:
        raise HTTPException(400, "저장할 보유자산이 없습니다.")
    day = data.get("day_change") or {}
    record = upsert_asset_record(
        {
            "date": datetime.now().astimezone().date().isoformat(),
            "total_value_krw": data["summary"]["total_value_krw"],
            "total_cost_krw": data["summary"]["total_cost_krw"],
            "profit_krw": data["summary"]["profit_krw"],
            "return_rate": data["summary"]["return_rate"],
            "day_profit_krw": day.get("change_krw") or 0,
            "krw_value_krw": data.get("currency_summary", {}).get("KRW", {}).get("market_value_krw", 0),
            "usd_value_krw": data.get("currency_summary", {}).get("USD", {}).get("market_value_krw", 0),
            "holding_count": data["summary"]["holding_count"],
            "currency": "KRW",
            "source": "snapshot",
            "memo": "수동 스냅샷",
        },
        by_date=True,
        username=username,
    )
    return {"message": "오늘 자산을 기록했습니다.", "record": record}


@app.post("/api/sync/kb")
async def sync_kb(request: Request = None) -> dict:
    username = get_current_username(request) if request else "sagesaint"
    client = KBOpenAPI(username=username)
    if not client.configured:
        return {"broker": "KB증권", "status": "CONFIG_REQUIRED", "message": "KB증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True, "warnings": []}
    try:
        records = await client.sync_holdings()
    except KBOpenAPIError as exc:
        raise HTTPException(400, str(exc)) from exc
    data = read_portfolio(username=username)

    # 1. 고유 키(kb_primary) 또는 기존 KB 동기화 계좌 찾기
    existing = next((a for a in data["accounts"] if a.get("broker") == "KB증권" and (a.get("account_key") == "kb_primary" or a.get("source") == "kb_api")), None)
    if not existing:
        existing = next((a for a in data["accounts"] if a.get("broker") == "KB증권" and ("KB" in a.get("name", "") or a.get("name") == "KB OpenAPI 동기화 계좌")), None)

    if existing:
        account_id = existing["id"]
        account_name = existing["name"]  # 사용자가 변경한 이름을 100% 보존!
        existing["source"] = "kb_api"
        existing["account_key"] = "kb_primary"
    else:
        # 삭제되었거나 신규일 때 자동 복구 생성
        account_id = str(uuid.uuid4())
        account_name = "KB OpenAPI 동기화 계좌"
        data["accounts"].append({
            "id": account_id,
            "broker": "KB증권",
            "name": account_name,
            "family_group": "All",
            "source": "kb_api",
            "account_key": "kb_primary",
            "owner": "모두",
        })

    holdings = [normalize_holding(record, account_id, "KB증권", account_name, "kb_api") for record in records]
    prices, warnings = await client.refresh_prices(holdings)
    for holding in holdings:
        price = prices.get(holding["id"])
        if price:
            holding["current_price"] = price
            if holding["avg_price"] == 0:
                holding["avg_price"] = price
    upsert_holdings(data, holdings, replace_source="kb_api")
    _mark_sync_success(data, "kb")
    write_portfolio(data, username=username)
    return {"broker": "KB증권", "status": "SUCCESS", "message": f"KB증권 보유종목 {len(holdings)}개를 동기화했습니다.", "count": len(holdings), "holdings_valid": True, "cash_valid": False, "data_preserved": False, "warnings": warnings[:10]}


@app.post("/api/sync/toss")
async def sync_toss(request: Request = None) -> dict:
    username = get_current_username(request) if request else "sagesaint"
    client = TossOpenAPI(username=username)
    if not client.configured:
        return {"broker": "토스증권", "status": "CONFIG_REQUIRED", "message": "토스증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    try:
        records = await client.sync_holdings()
        toss_accounts = client.last_accounts
    except TossOpenAPIError as exc:
        raise HTTPException(400, str(exc)) from exc
    data = read_portfolio(username=username)
    cash = data["settings"].setdefault("toss_cash", {})
    cash_balances = data["settings"].setdefault("cash_balances", {})

    def resolve_toss_account(data_accounts, seq, acct_no, default_name):
        seq_str = str(seq) if seq is not None else ""
        suffix = str(acct_no)[-4:] if acct_no else ""
        # 1) account_key 또는 seq_str 일치
        for a in data_accounts:
            if a.get("broker") == "토스증권" and (
                (seq_str and a.get("account_key") == seq_str) or 
                (suffix and a.get("account_no") == suffix)
            ):
                return a
        # 2) 이름에 suffix나 토스증권이 매칭되는 계좌
        for a in data_accounts:
            if a.get("broker") == "토스증권" and (
                (suffix and suffix in a.get("name", "")) or 
                a.get("name") == default_name or
                (a.get("source") == "toss_api")
            ):
                return a
        return None

    toss_map = {}
    cash_failures = 0
    for account in toss_accounts:
        seq = account.get("accountSeq")
        seq_str = str(seq) if seq is not None else ""
        account_no = str(account.get("accountNo", ""))
        suffix = account_no[-4:] if account_no else ""
        account_name_default = f"토스증권 계좌 {suffix}" if suffix else (f"토스증권 계좌 {seq}" if seq is not None else "토스증권")
        
        existing = resolve_toss_account(data["accounts"], seq, account_no, account_name_default)
        if existing:
            account_id = existing["id"]
            account_name = existing["name"]  # 사용자가 변경한 이름을 100% 보존!
            existing["source"] = "toss_api"
            if seq_str:
                existing["account_key"] = seq_str
            if suffix:
                existing["account_no"] = suffix
        else:
            # 삭제되었거나 신규일 때 자동 복구 생성
            account_id = str(uuid.uuid4())
            account_name = account_name_default
            data["accounts"].append({
                "id": account_id,
                "broker": "토스증권",
                "name": account_name,
                "family_group": "All",
                "source": "toss_api",
                "account_key": seq_str,
                "account_no": suffix,
                "owner": "모두",
            })

        toss_map[seq_str] = (account_id, account_name)
        if seq is not None:
            try:
                bp = await client.get_buying_power(int(seq))
                cash[str(seq)] = bp
                cash_balances[account_id] = bp
            except TossOpenAPIError:
                cash_failures += 1

    data["settings"]["toss_cash"] = cash
    data["settings"]["cash_balances"] = cash_balances
    holdings = []
    for record in records:
        acct_key = str(record.get("account_key", ""))
        if acct_key in toss_map:
            account_id, account_name = toss_map[acct_key]
        else:
            existing = resolve_toss_account(data["accounts"], None, None, record.get("account_name", "토스증권"))
            if existing:
                account_id = existing["id"]
                account_name = existing["name"]
            else:
                account_id = get_or_add_account(data, "토스증권", record["account_name"], "toss_api")
                account_name = record["account_name"]
        holdings.append(normalize_holding(record, account_id, "토스증권", account_name, "toss_api"))

    upsert_holdings(data, holdings, replace_source="toss_api")
    _mark_sync_success(data, "toss")
    write_portfolio(data, username=username)
    status = "PARTIAL_SUCCESS" if cash_failures else "SUCCESS"
    message = f"토스증권 보유종목 {len(holdings)}개를 동기화했습니다."
    message += " 예수금 조회 실패 계좌의 기존 데이터는 유지했습니다." if cash_failures else " 예수금도 동기화했습니다."
    return {"broker": "토스증권", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "cash_valid": not cash_failures, "data_preserved": bool(cash_failures)}


@app.post("/api/sync/namoo")
async def sync_namoo(request: Request = None) -> dict:
    username = get_current_username(request) if request else "sagesaint"
    client = NhPlugOpenAPI(username=username)
    if not client.configured:
        return {"broker": "NH투자증권(나무)", "status": "CONFIG_REQUIRED", "message": "나무증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    try:
        records = await client.sync_holdings()
    except NhPlugOpenAPIError as exc:
        detail = str(exc)
        if "IGW42903" in detail or "거래건수를 초과" in detail:
            detail = "나무증권 API 호출 한도를 초과했습니다(IGW42903). 잠시 후 다시 시도하거나 나무 OpenAPI 포털에서 호출 한도·계정별 제한을 확인해 주세요. 인증키 오류가 아닙니다."
        raise HTTPException(429 if "IGW42903" in str(exc) else 400, detail) from exc
    data = read_portfolio(username=username)
    cash_balances = data["settings"].setdefault("cash_balances", {})

    def resolve_namoo_account(data_accounts, acct_no, default_name):
        suffix = str(acct_no)[-4:] if acct_no else ""
        # 1) account_key 또는 account_no 고유 식별자 우선 일치
        for a in data_accounts:
            if a.get("broker") == "NH투자증권(나무)" and (a.get("account_key") == suffix or a.get("account_no") == str(acct_no)):
                return a
        # 2) 계좌 이름에 suffix(예: 3861)가 포함되어 있거나 기존 기본 이름과 일치하는 계좌
        if suffix:
            for a in data_accounts:
                if a.get("broker") == "NH투자증권(나무)" and (suffix in a.get("name", "") or a.get("name") == default_name):
                    return a
        return None

    account_map = {}  # acct_no -> (account_id, account_name)
    for account in client.last_accounts:
        account_no = str(account.get("acct_no", ""))
        default_name = client._account_name(account)
        suffix = account_no[-4:] if account_no else ""
        if account_no:
            existing = resolve_namoo_account(data["accounts"], account_no, default_name)
            if existing:
                account_id = existing["id"]
                account_name = existing["name"]  # 사용자가 변경한 이름을 100% 보존!
                existing["source"] = "nhplug_api"
                existing["account_key"] = suffix
                existing["account_no"] = account_no
            else:
                # 삭제되었거나 신규일 때 자동 복구 생성
                account_id = str(uuid.uuid4())
                account_name = default_name
                data["accounts"].append({
                    "id": account_id,
                    "broker": "NH투자증권(나무)",
                    "name": account_name,
                    "family_group": "All",
                    "source": "nhplug_api",
                    "account_key": suffix,
                    "account_no": account_no,
                    "owner": "모두",
                })
            account_map[account_no] = (account_id, account_name)
            if account_no in client.account_cash:
                cash_balances[account_id] = client.account_cash[account_no]

    holdings = []
    for record in records:
        acct_key = str(record.get("account_key", ""))
        if acct_key in account_map:
            account_id, account_name = account_map[acct_key]
        else:
            existing = resolve_namoo_account(data["accounts"], acct_key, record.get("account_name", "나무증권 계좌"))
            if existing:
                account_id = existing["id"]
                account_name = existing["name"]
            else:
                account_id = get_or_add_account(data, "NH투자증권(나무)", record.get("account_name", "나무증권 계좌"), "nhplug_api")
                account_name = record.get("account_name", "나무증권 계좌")
        holdings.append(normalize_holding(record, account_id, "NH투자증권(나무)", account_name, "nhplug_api"))

    upsert_holdings(data, holdings, replace_source="nhplug_api")
    data["settings"]["cash_balances"] = cash_balances
    _mark_sync_success(data, "nh")
    write_portfolio(data, username=username)
    return {"broker": "NH투자증권(나무)", "status": "SUCCESS", "message": f"나무증권 보유종목 {len(holdings)}개 및 예수금을 동기화했습니다.", "count": len(holdings), "holdings_valid": True, "cash_valid": True, "data_preserved": False}


@app.post("/api/sync/kis")
async def sync_kis(request: Request = None) -> dict:
    username = get_current_username(request) if request else "sagesaint"
    client = KISOpenAPI(username=username)
    if not client.configured:
        return {"broker": "한국투자증권", "status": "CONFIG_REQUIRED", "message": "한국투자증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    if not client._parse_account_no()[0]:
        return {"broker": "한국투자증권", "status": "CONFIG_REQUIRED", "message": "한국투자증권 계좌번호(CANO 8자리 또는 8자리-상품코드 2자리)를 확인해 주세요. 기존 데이터는 유지했습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    try:
        records = await client.sync_holdings()
    except KISOpenAPIError as exc:
        raise HTTPException(400, str(exc)) from exc
    data = read_portfolio(username=username)
    cash_balances = data["settings"].setdefault("cash_balances", {})

    def resolve_kis_account(data_accounts, acct_no, default_name):
        suffix = str(acct_no)[-4:] if acct_no else ""
        for a in data_accounts:
            if a.get("broker") == "한국투자증권" and (a.get("account_key") == suffix or a.get("account_no") == str(acct_no)):
                return a
        if suffix:
            for a in data_accounts:
                if a.get("broker") == "한국투자증권" and (suffix in a.get("name", "") or a.get("name") == default_name):
                    return a
        return None

    account_map = {}
    for account in client.last_accounts:
        account_no = str(account.get("account_number", ""))
        default_name = account.get("account_name", f"한국투자증권 ({account_no[:4]}****)")
        suffix = account_no[-4:] if account_no else ""
        if account_no:
            existing = resolve_kis_account(data["accounts"], account_no, default_name)
            if existing:
                account_id = existing["id"]
                account_name = existing["name"]  # 사용자 지정 이름 100% 보존
                existing["source"] = "kis_api"
                existing["account_key"] = suffix
                existing["account_no"] = account_no
            else:
                account_id = str(uuid.uuid4())
                account_name = default_name
                data["accounts"].append({
                    "id": account_id,
                    "broker": "한국투자증권",
                    "name": account_name,
                    "family_group": "All",
                    "source": "kis_api",
                    "account_key": suffix,
                    "account_no": account_no,
                    "owner": "모두",
                })
            account_map[account_no] = (account_id, account_name)
            if account_no in client.account_cash:
                cash_balances.setdefault(account_id, {})
                for ccy, amt in client.account_cash[account_no].items():
                    cash_balances[account_id][ccy] = amt

    holdings = []
    for record in records:
        acct_no = str(record.get("account_number", ""))
        if acct_no in account_map:
            account_id, account_name = account_map[acct_no]
        else:
            first_acct = next(iter(account_map.values()), None)
            if first_acct:
                account_id, account_name = first_acct
            else:
                account_id = get_or_add_account(data, "한국투자증권", "한국투자증권 계좌", "kis_api")
                account_name = "한국투자증권 계좌"
        holdings.append(normalize_holding(record, account_id, "한국투자증권", account_name, "kis_api"))

    upsert_holdings(data, holdings, replace_source="kis_api")
    data["settings"]["cash_balances"] = cash_balances
    _mark_sync_success(data, "kis")
    write_portfolio(data, username=username)
    return {"broker": "한국투자증권", "status": "SUCCESS", "message": f"한국투자증권 보유종목 {len(holdings)}개 및 예수금을 동기화했습니다.", "count": len(holdings), "holdings_valid": True, "cash_valid": True, "data_preserved": False}


@app.post("/api/sync/kiwoom")
async def sync_kiwoom(request: Request = None) -> dict:
    username = get_current_username(request) if request else "sagesaint"
    client = KiwoomOpenAPI(username=username)
    if not client.configured:
        return {"broker": "키움증권", "status": "CONFIG_REQUIRED", "message": "키움증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    try:
        records = await client.sync_holdings()
    except KiwoomOpenAPIError as exc:
        raise HTTPException(400, str(exc)) from exc
    data = read_portfolio(username=username)
    cash_balances = data["settings"].setdefault("cash_balances", {})

    def resolve_kiwoom_account(data_accounts, acct_no, default_name):
        suffix = str(acct_no)[-4:] if acct_no else ""
        for a in data_accounts:
            if a.get("broker") == "키움증권" and (a.get("account_key") == suffix or a.get("account_no") == str(acct_no)):
                return a
        if suffix:
            for a in data_accounts:
                if a.get("broker") == "키움증권" and (suffix in a.get("name", "") or a.get("name") == default_name):
                    return a
        return None

    account_map = {}
    for account in client.last_accounts:
        account_no = str(account.get("account_number", ""))
        default_name = account.get("account_name", f"키움증권 ({account_no[:4]}****)")
        suffix = account_no[-4:] if account_no else ""
        if account_no:
            existing = resolve_kiwoom_account(data["accounts"], account_no, default_name)
            if existing:
                account_id = existing["id"]
                account_name = existing["name"]  # 사용자 지정 이름 100% 보존
                existing["source"] = "kiwoom_api"
                existing["account_key"] = suffix
                existing["account_no"] = account_no
            else:
                account_id = str(uuid.uuid4())
                account_name = default_name
                data["accounts"].append({
                    "id": account_id,
                    "broker": "키움증권",
                    "name": account_name,
                    "family_group": "All",
                    "source": "kiwoom_api",
                    "account_key": suffix,
                    "account_no": account_no,
                    "owner": "모두",
                })
            account_map[account_no] = (account_id, account_name)
            if account_no in client.account_cash:
                cash_balances.setdefault(account_id, {})
                for ccy, amt in client.account_cash[account_no].items():
                    cash_balances[account_id][ccy] = amt

    holdings = []
    for record in records:
        acct_no = str(record.get("account_number", ""))
        if acct_no in account_map:
            account_id, account_name = account_map[acct_no]
        else:
            first_acct = next(iter(account_map.values()), None)
            if first_acct:
                account_id, account_name = first_acct
            else:
                account_id = get_or_add_account(data, "키움증권", "키움증권 계좌", "kiwoom_api")
                account_name = "키움증권 계좌"
        holdings.append(normalize_holding(record, account_id, "키움증권", account_name, "kiwoom_api"))

    # v1.0.9 uses Kiwoom's documented domestic API. Preserve any legacy USD
    # holdings until an official overseas adapter is implemented and validated.
    data["holdings"] = [h for h in data["holdings"] if not (h.get("source") == "kiwoom_api" and str(h.get("currency", "KRW")).upper() == "KRW")]
    upsert_holdings(data, holdings)
    data["settings"]["cash_balances"] = cash_balances
    _mark_sync_success(data, "kiwoom")
    write_portfolio(data, username=username)
    return {"broker": "키움증권", "status": "SUCCESS", "message": f"키움증권 국내 보유종목 {len(holdings)}개 및 KRW 예수금을 동기화했습니다.", "count": len(holdings), "holdings_valid": True, "cash_valid": True, "data_preserved": False}


@app.post("/api/fx/refresh")
async def refresh_fx_rate(request: Request) -> dict:
    username = get_current_username(request)
    rate = await fetch_fx_rate_usd_krw()
    data = read_portfolio(username=username)
    data["settings"]["fx_rates"]["USD"] = rate
    now_str = datetime.now().astimezone().isoformat(timespec="seconds")
    data["settings"]["fx_info"] = {"source": "실시간 웹 환율", "rate": rate, "updated_at": now_str}
    data["settings"]["fx_updated_at"] = now_str
    write_portfolio(data, username=username)
    return {"message": f"실시간 환율(USD/KRW: {rate:,.1f}원)을 반영했습니다.", "rate": rate}


@app.post("/api/refresh-prices")
async def refresh_prices(request: Request) -> dict:
    username = get_current_username(request)
    data = read_portfolio(username=username)
    if is_test_mode():
        return {
            "message": "테스트 환경에서는 외부 시세 갱신을 실행하지 않습니다. 기존 데이터를 유지했습니다.",
            "count": 0,
            "fx_rate": data.get("settings", {}).get("fx_rates", {}).get("USD"),
            "warnings": [],
            "status": "TEST_MODE",
            "data_preserved": True,
        }
    now_str = datetime.now().astimezone().isoformat(timespec="seconds")

    # 보유종목이 없는 경우에도 지수 및 환율 정상 갱신
    if not data.get("holdings"):
        fx_rate = await fetch_fx_rate_usd_krw()
        if fx_rate and fx_rate > 0:
            data.setdefault("settings", {})
            data["settings"].setdefault("exchange_rates", {})["USD"] = fx_rate
            data["settings"]["fx_rates"] = {"KRW": 1.0, "USD": fx_rate}
            data["settings"]["fx_info"] = {"source": "실시간 웹 환율", "rate": fx_rate, "updated_at": now_str}
            data["settings"]["fx_updated_at"] = now_str
            write_portfolio(data, username=username)
        return {
            "message": "지수 및 환율을 갱신했습니다.",
            "count": 0,
            "fx_rate": fx_rate,
            "warnings": [],
        }

    # 네이버페이 증권 & 야후 파이낸스 & 웹 실시간 환율 병렬 직접 갱신 (토큰 불필요)
    res = await refresh_all_holdings_prices(data["holdings"])
    prices = res.get("prices", {})
    daily_changes = res.get("daily_changes", {})
    period_rates = res.get("period_rates", {})
    fx_rate = res.get("fx_rate", 1385.0)

    # 포트폴리오 업데이트
    for holding in data["holdings"]:
        hid = holding["id"]
        if hid in prices and prices[hid] > 0:
            holding["current_price"] = prices[hid]
            holding["price_updated_at"] = now_str

    if daily_changes:
        data["settings"].setdefault("daily_price_changes", {}).update(daily_changes)
    if period_rates:
        data["settings"].setdefault("period_rates", {}).update(period_rates)
    if fx_rate and fx_rate > 0:
        data["settings"].setdefault("exchange_rates", {})["USD"] = fx_rate
        data["settings"]["fx_updated_at"] = now_str

    write_portfolio(data, username=username)
    return {
        "message": f"전체 {len(prices)}개 종목 시세 및 환율({fx_rate:,.1f}원)을 갱신했습니다.",
        "count": len(prices),
        "fx_rate": fx_rate,
        "warnings": [],
    }

@app.get("/api/stock-chart/{code}")
async def get_stock_chart(code: str, period: str = "1M") -> dict:
    return await fetch_stock_chart_data(code, period)


@app.get("/api/stock-search")
async def stock_search(q: str = "") -> dict:
    from app.services.stock_master import async_search_stock_by_name
    return await async_search_stock_by_name(q)


@app.post("/api/sync/all")
async def sync_all_accounts(request: Request) -> dict:
    username = get_current_username(request)
    if is_test_mode():
        brokers = [
            {"broker": label, "status": "TEST_MODE", "count": 0,
             "holdings_valid": False, "cash_valid": False, "data_preserved": True,
             "message": "테스트 환경에서는 외부 동기화를 실행하지 않습니다. 기존 데이터를 유지했습니다."}
            for label in ("KB증권", "토스증권", "NH투자증권(나무)", "한국투자증권", "키움증권")
        ]
        return {
            "message": "테스트 환경에서는 계좌 동기화를 실행하지 않습니다. 기존 데이터를 유지했습니다.",
            "synced": 0,
            "errors": [],
            "brokers": brokers,
            "status": "TEST_MODE",
            "data_preserved": True,
        }
    if username in _syncing_users:
        raise HTTPException(409, "이미 계좌 동기화가 진행 중입니다.")
    _syncing_users.add(username)
    broker_results: list[dict] = []
    try:
        jobs = [
            ("KB증권", KBOpenAPI(username=username), sync_kb),
            ("토스증권", TossOpenAPI(username=username), sync_toss),
            ("NH투자증권(나무)", NhPlugOpenAPI(username=username), sync_namoo),
            ("한국투자증권", KISOpenAPI(username=username), sync_kis),
            ("키움증권", KiwoomOpenAPI(username=username), sync_kiwoom),
        ]
        for label, client, endpoint in jobs:
            if not client.configured:
                broker_results.append({
                    "broker": label, "status": "CONFIG_REQUIRED", "count": 0,
                    "holdings_valid": False, "cash_valid": False, "data_preserved": True,
                    "message": "OpenAPI 연결 정보가 필요합니다. 기존 데이터는 유지했습니다.",
                })
                continue
            try:
                broker_results.append(await endpoint(request))
            except Exception as exc:
                status = _sync_error_status(exc)
                broker_results.append({
                    "broker": label, "status": status, "count": 0,
                    "holdings_valid": False, "cash_valid": False, "data_preserved": True,
                    "message": f"{_mask_sync_error(exc, client)} 기존 데이터는 유지했습니다.",
                })
    finally:
        _syncing_users.discard(username)

    succeeded = [r for r in broker_results if r["status"] in {"SUCCESS", "PARTIAL_SUCCESS"}]
    errors = [f"{r['broker']}: {r['message']}" for r in broker_results if r["status"] not in {"SUCCESS", "PARTIAL_SUCCESS", "CONFIG_REQUIRED"}]
    lines = [f"{r['broker']} [{r['status']}] {r['message']}" for r in broker_results]
    return {"message": " / ".join(lines), "synced": len(succeeded), "errors": errors, "brokers": broker_results}


# ---------------------------------------------------------------------------
# Smart Household Ledger (스마트 가족 가계부) API Endpoints
# ---------------------------------------------------------------------------
from app.services.ledger import (
    BalanceConflictError,
    LegacyBalanceDeltaError,
    get_ledger_summary,
    add_transaction,
    update_transaction,
    delete_transaction,
    add_recurring,
    edit_recurring,
    delete_recurring,
    process_recurring_deductions,
    get_cards,
    create_card,
    update_card,
    delete_card,
    settle_card_payment,
    read_ledger,
)


@app.get("/api/ledger")
async def get_ledger(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    owner: str = "모두",
) -> dict:
    """Get ledger summary, category analytics, trend, cards, and transactions for the specified month/owner."""
    username = get_current_username(request)
    try:
        return get_ledger_summary(username=username, year=year, month=month, owner=owner)
    except BalanceConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/ledger/transactions")
async def create_ledger_transaction(request: Request) -> dict:
    """Create a new income/expense/transfer transaction."""
    username = get_current_username(request)
    payload = await request.json()
    if not payload.get("amount"):
        raise HTTPException(400, "금액을 입력해 주세요.")
    try:
        tx = add_transaction(payload, username=username)
    except BalanceConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"message": "내역이 등록되었습니다.", "transaction": tx}


@app.put("/api/ledger/transactions/{tx_id}")
async def edit_ledger_transaction(tx_id: str, request: Request) -> dict:
    """Update an existing transaction."""
    username = get_current_username(request)
    payload = await request.json()
    try:
        tx = update_transaction(tx_id, payload, username=username)
    except (LegacyBalanceDeltaError, BalanceConflictError) as exc:
        raise HTTPException(409, str(exc)) from exc
    if not tx:
        raise HTTPException(404, "수정할 내역을 찾을 수 없습니다.")
    return {"message": "내역이 수정되었습니다.", "transaction": tx}


@app.delete("/api/ledger/transactions/{tx_id}")
async def remove_ledger_transaction(tx_id: str, request: Request) -> dict:
    """Delete a transaction."""
    username = get_current_username(request)
    try:
        success = delete_transaction(tx_id, username=username)
    except (LegacyBalanceDeltaError, BalanceConflictError) as exc:
        raise HTTPException(409, str(exc)) from exc
    if not success:
        raise HTTPException(404, "삭제할 내역을 찾을 수 없습니다.")
    return {"message": "내역이 삭제되었습니다."}


@app.post("/api/ledger/recurring")
async def create_recurring(request: Request) -> dict:
    """Add a recurring monthly expense/income."""
    username = get_current_username(request)
    payload = await request.json()
    if not payload.get("name") or not payload.get("amount"):
        raise HTTPException(400, "고정지출 이름과 금액을 입력해 주세요.")
    try:
        rec = add_recurring(payload, username=username)
    except BalanceConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"message": "고정지출이 등록되었습니다.", "recurring": rec}


@app.delete("/api/ledger/recurring/{rec_id}")
async def remove_recurring(rec_id: str, request: Request) -> dict:
    """Delete a recurring entry."""
    username = get_current_username(request)
    success = delete_recurring(rec_id, username=username)
    if not success:
        raise HTTPException(404, "삭제할 고정지출 항목을 찾을 수 없습니다.")
    return {"message": "고정지출 항목이 삭제되었습니다."}


@app.put("/api/ledger/recurring/{rec_id}")
async def update_recurring_entry(rec_id: str, request: Request) -> dict:
    """Update a recurring entry."""
    username = get_current_username(request)
    payload = await request.json()
    try:
        rec = edit_recurring(rec_id, payload, username=username)
    except BalanceConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    if not rec:
        raise HTTPException(404, "수정할 고정지출 항목을 찾을 수 없습니다.")
    return {"message": "고정지출 항목이 수정되었습니다.", "recurring": rec}


@app.post("/api/ledger/recurring/process")
async def trigger_recurring_deductions(request: Request) -> dict:
    """Trigger processing of recurring bank deductions for current month."""
    username = get_current_username(request)
    try:
        processed = process_recurring_deductions(username=username)
    except BalanceConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    count = len(processed)
    msg = f"당월 자동이체 고정지출 {count}건이 통장에서 정상 출금 처리되었습니다." if count > 0 else "당월 추가로 출금 처리할 자동이체 항목이 없습니다."
    return {"message": msg, "count": count, "processed": processed}


# ---------------------------------------------------------------------------
# Credit / Debit Card Routes
# ---------------------------------------------------------------------------

@app.get("/api/ledger/cards")
async def get_ledger_cards(request: Request, owner: str = "모두") -> list[dict]:
    """Get all cards with unpaid bill amount."""
    username = get_current_username(request)
    return get_cards(username=username, owner=owner)


@app.post("/api/ledger/cards")
async def add_ledger_card(request: Request) -> dict:
    """Register a new credit or debit card."""
    username = get_current_username(request)
    payload = await request.json()
    if not payload.get("card_name"):
        raise HTTPException(400, "카드명을 입력해 주세요.")
    card = create_card(payload, username=username)
    return {"message": "신용카드가 등록되었습니다.", "card": card}


@app.put("/api/ledger/cards/{card_id}")
async def edit_ledger_card(card_id: str, request: Request) -> dict:
    """Update card details."""
    username = get_current_username(request)
    payload = await request.json()
    card = update_card(card_id, payload, username=username)
    if not card:
        raise HTTPException(404, "수정할 카드를 찾을 수 없습니다.")
    return {"message": "카드 정보가 수정되었습니다.", "card": card}


@app.delete("/api/ledger/cards/{card_id}")
async def remove_ledger_card(card_id: str, request: Request) -> dict:
    """Delete a card."""
    username = get_current_username(request)
    ok = delete_card(card_id, username=username)
    if not ok:
        raise HTTPException(404, "삭제할 카드를 찾을 수 없습니다.")
    return {"message": "카드가 삭제되었습니다."}


@app.post("/api/ledger/cards/{card_id}/pay")
async def pay_ledger_card(card_id: str, request: Request) -> dict:
    """Settle unpaid credit card bills via linked bank account."""
    username = get_current_username(request)
    payload = await request.json() if request.headers.get("content-type") == "application/json" else {}
    try:
        res = settle_card_payment(card_id, payload, username=username)
        return res
    except BalanceConflictError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# Ledger Sample Downloads & Excel File Import
# ---------------------------------------------------------------------------
from app.services.ledger import import_ledger_from_file_bytes


@app.get("/api/sample/card-statement")
async def download_sample_card_statement():
    """Download sample Excel file for card transaction statements."""
    p = ROOT_DIR / "data" / "샘플_카드내역.xlsx"
    if not p.exists():
        raise HTTPException(status_code=404, detail="샘플_카드내역.xlsx 파일을 찾을 수 없습니다.")
    return FileResponse(
        path=str(p),
        filename="샘플_카드내역.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/sample/ledger-transactions")
async def download_sample_ledger_transactions():
    """Download sample Excel file for general household transactions."""
    p = ROOT_DIR / "data" / "샘플_거래내역.xlsx"
    if not p.exists():
        raise HTTPException(status_code=404, detail="샘플_거래내역.xlsx 파일을 찾을 수 없습니다.")
    return FileResponse(
        path=str(p),
        filename="샘플_거래내역.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.post("/api/ledger/import-file")
async def upload_ledger_file(
    request: Request,
    file: UploadFile = File(...),
    owner: str = Form("모두"),
) -> dict:
    """Upload Excel (.xlsx, .xls) or CSV file to import transactions."""
    username = get_current_username(request)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "업로드된 파일이 비어 있습니다.")
    try:
        count = import_ledger_from_file_bytes(
            file_bytes=file_bytes,
            filename=file.filename or "import.xlsx",
            default_owner=owner,
            username=username,
        )
        return {"message": f"총 {count}건의 거래 내역을 성공적으로 등록했습니다.", "count": count}
    except Exception as e:
        raise HTTPException(400, f"파일 처리 중 오류가 발생했습니다: {str(e)}")


