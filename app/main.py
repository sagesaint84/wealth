from __future__ import annotations

import asyncio
import html
import json
import os
import re
import secrets
import sys
import time
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from app.static_transport import CompressedStaticFiles as StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field

from app.services.kb_openapi import KBOpenAPI, KBOpenAPIError, KBTransientAPIError
from app.services.kb_feed import (
    build_kb_realized_feed, compute_kb_items_hash,
    sign_kb_import_preview_ticket, verify_kb_import_preview_ticket,
)
from app.services.kb_realized import preview_kb_realized_selection
from app.services.nhplug_openapi import NhPlugOpenAPI, NhPlugOpenAPIError, NhPlugRateLimitError
from app.services.toss_openapi import TossOpenAPI, TossOpenAPIError
from app.services.kis_openapi import KISOpenAPI, KISOpenAPIError
from app.services.kiwoom_openapi import KiwoomOpenAPI, KiwoomOpenAPIError
from app.services.broker_holdings_sync import (
    BrokerHoldingsResult,
    HoldingsResultState,
    replace_holdings_in_scopes,
    resolve_scopes,
)
from app.services.broker_account_resolution import (
    resolve_realized_destination_candidates,
    validate_realized_destination,
)
from app.services.network_policy import is_test_mode
from app.services.web_finance import (
    get_web_market_overview,
    fetch_fx_rate_usd_krw,
    refresh_all_holdings_prices,
    fetch_stock_chart_data,
    get_web_dividend_summary,
)
fetch_market_overview = get_web_market_overview
from app.services.financial_json import FinancialStorageError, financial_user_locks
from app.services.portfolio import (
    clear_portfolio, get_dashboard, import_rows, normalize_holding,
    read_portfolio, seed_demo, upsert_holdings, write_portfolio, to_number, migrate_add_family_group,
    import_account_rows, normalize_broker_account_no, canonical_broker_account_identity
)
from app.services.asset_records import (
    build_stock_record_from_holdings,
    delete_asset_record,
    list_asset_records,
    merge_price_session_obs,
    normalize_session_date,
    upsert_asset_record,
)
from app.services.dividend_records import (
    create_dividend_record, delete_dividend_record, get_actual_dividend_summary,
    read_dividend_records, read_dividend_records_for_import,
    update_dividend_record, import_dividend_file_data,
    clear_dividend_records, recalculate_dividend_historical_fx, DividendRecordsStorageError
)
from app.services.pnl_records import (
    create_pnl_record, delete_pnl_record, get_pnl_summary,
    read_pnl_records, read_pnl_records_readonly, update_pnl_record, import_pnl_file_data,
    clear_pnl_records, recalculate_pnl_historical_fx, PnlRecordsStorageError,
    PnlRecordLinkedToIpoError, PnlRecordsLinkedToIpoError,
)
from app.services.pnl_broker_clear import clear_pnl_records_for_broker
from app.services.historical_fx import get_historical_fx_rate, sync_historical_fx
from app.services.stock_master import sync_stock_master_online
from app.services.toss_wts_adapter import TossWtsAdapter, TossWtsAdapterError
from app.services.toss_wts_feed_auth import check_wts_feed_static_authorization
from app.services.toss_wts_feed_runtime import (
    check_wts_feed_runtime_confirmation,
    check_wts_feed_runtime_confirmation_for_username,
    confirm_wts_feed_runtime_session,
    confirm_wts_feed_runtime_session_for_username,
    get_current_runtime_generation_id,
    get_current_runtime_generation_id_for_username,
)
from app.services.toss_wts_feed import (
    build_realized_feed_response,
    compute_items_hash,
    sign_import_preview_ticket,
    validate_realized_feed_request,
    verify_import_preview_ticket,
)
from app.services.toss_wts_realized import preview_toss_wts_realized_selection


def _toss_wts_user_allowed(username: str) -> bool:
    """Global Toss feature gate plus optional admin username allowlist."""
    from app.services.system_settings import resolve_toss_wts_settings
    settings = resolve_toss_wts_settings()
    allowed = set(settings.get("allowed_users") or [])
    return bool(settings.get("enabled")) and (not allowed or username in allowed)
from app.services.kis_feed import (
    build_kis_realized_feed_response,
    compute_kis_items_hash,
    sign_kis_import_preview_ticket,
    validate_kis_feed_request,
    verify_kis_import_preview_ticket,
)
from app.services.kis_realized import preview_kis_realized_selection
from app.services.nh_feed import (
    build_nh_realized_feed, compute_nh_items_hash,
    sign_nh_import_preview_ticket, verify_nh_import_preview_ticket,
)
from app.services.nh_realized import preview_nh_realized_selection
from app.services.nhplug_openapi import compute_nh_account_key, mask_nh_account
from app.services.kiwoom_feed import (
    build_kiwoom_realized_feed, compute_kiwoom_items_hash,
    sign_kiwoom_import_preview_ticket, verify_kiwoom_import_preview_ticket,
)
from app.services.kiwoom_realized import preview_kiwoom_realized_selection
from app.services.broker_realized_import import (
    BrokerRealizedImportError,
    apply_wealth_import_preferences,
    compute_wealth_import_items_hash,
    has_wealth_import_preferences,
)
import logging
from app.logging_security import install_credential_log_redaction

install_credential_log_redaction()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "app" / "static"
WEALTH_ENV = os.getenv("WEALTH_ENV", "production").strip().lower()
TESTING = WEALTH_ENV == "test"
_NH_IMPORT_LOCK = threading.RLock()
_KIS_IMPORT_LOCK = threading.RLock()
_KIWOOM_IMPORT_LOCK = threading.RLock()
_KB_IMPORT_LOCK = threading.RLock()
_TOSS_WTS_INCOME_IMPORT_LOCK = threading.RLock()


def _broker_import_items_hash(provider_hash: str, selected_items: list[dict[str, Any]]) -> str:
    if not has_wealth_import_preferences(selected_items):
        return provider_hash
    try:
        return compute_wealth_import_items_hash(provider_hash, selected_items)
    except BrokerRealizedImportError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": str(exc), "message": "Broker import accounting selection is invalid"},
        ) from exc


def _apply_broker_import_preferences(
    result: dict[str, Any], selected_items: list[dict[str, Any]],
) -> dict[str, Any]:
    if not has_wealth_import_preferences(selected_items):
        return result
    try:
        return apply_wealth_import_preferences(result, selected_items)
    except BrokerRealizedImportError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": str(exc), "message": "Broker import accounting selection is invalid"},
        ) from exc


def load_env_file() -> None:
    if os.getenv("WEALTH_DISABLE_ENV_FILE", "").strip().lower() in {"1", "true", "yes"}:
        return
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
APP_VERSION = "2.1.20"
app = FastAPI(title="내 자산 대시보드", docs_url=None, redoc_url=None, version=APP_VERSION)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

from app.services.account_sync_retry import (
    AccountSyncPersistenceError, fetch_account_holdings, get_failure_diagnostic, read_account_with_retry,
)


from app.services.broker_portfolio_sync import create_broker_portfolio_sync

globals().update(create_broker_portfolio_sync(sys.modules[__name__]))


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

def _resolve_session_secret() -> str:
    """Resolve the session signing secret - fail closed in all environments.

    Priority:
    1. DASHBOARD_SECRET_KEY environment variable (all environments).
    2. WEALTH_TEST_SIGNING_SECRET (test environment only, explicit opt-in).
    3. Raise RuntimeError - no built-in fallback exists.
    """
    explicit = os.getenv("DASHBOARD_SECRET_KEY", "").strip()
    if explicit: return explicit
    if TESTING:
        test_value = os.getenv("WEALTH_TEST_SIGNING_SECRET", "").strip()
        if test_value: return test_value
    from app.services.system_secrets import resolve_application_secret
    return resolve_application_secret()


SECRET_KEY = _resolve_session_secret()
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # 14일 동안 로그인 유지
COOKIE_NAME = "dashboard_session_v2"

_serializer = URLSafeTimedSerializer(SECRET_KEY)
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
    "webhookurl",
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
            "webhookurl",
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


def _new_session_token(user: dict) -> str:
    from app.services.update_permissions import session_stamp, valid_identity
    if not valid_identity(user):
        return _serializer.dumps({"user": user["username"]})
    return _serializer.dumps({"user": user["username"], "uid": user.get("id"),
                              "auth_stamp": session_stamp(user, SECRET_KEY), "sid": secrets.token_urlsafe(24)})


def _updater_session_current(request: Request, user: dict) -> bool:
    from app.services.update_permissions import session_stamp, valid_identity
    try:
        claims = _serializer.loads(request.cookies.get(COOKIE_NAME, ''), max_age=SESSION_MAX_AGE)
        return (valid_identity(user) and isinstance(claims.get('sid'), str)
                and re.fullmatch(r'[A-Za-z0-9_-]{32}', claims['sid']) is not None
                and claims.get('uid') == user['id']
                and secrets.compare_digest(str(claims.get('auth_stamp', '')), session_stamp(user, SECRET_KEY)))
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return False


def _refresh_auth_cookie(response: Response, username: str) -> None:
    from app.services.user_manager import get_user_by_name
    user = get_user_by_name(username)
    response.set_cookie(COOKIE_NAME, _new_session_token(user), httponly=True,
                        secure=not TESTING, samesite='lax', max_age=SESSION_MAX_AGE)


def _get_authenticated_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token or not _serializer:
        return None
    try:
        data = _serializer.loads(token, max_age=SESSION_MAX_AGE)
        uname = data.get("user")
        if uname:
            from app.services.user_manager import get_user_by_name
            user = get_user_by_name(uname)
            # New sessions expire when this identity is recreated or credentials reset.
            # Legacy sessions retain existing financial access; updater requires re-login.
            if user and ('uid' in data or 'auth_stamp' in data) and not _updater_session_current(request, user):
                return None
            return user
    except (BadSignature, SignatureExpired, Exception):
        pass
    return None


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
        if path.startswith("/a/"):
            return RedirectResponse(f"/login?return_to={quote(path, safe='')}")
        if path.startswith("/api/"):
            return JSONResponse({"detail": "로그인이 필요합니다."}, status_code=401,
                                headers={"Cache-Control":"no-store"} if path.startswith("/api/settings/toss-wts/session/") else None)
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
                return JSONResponse({"detail": "비밀번호 변경이 필요합니다."}, status_code=403,
                                    headers={"Cache-Control":"no-store"} if path.startswith("/api/settings/toss-wts/session/") else None)
        else:
            if path not in ("/change-password-init", "/logout"):
                return RedirectResponse("/change-password-init")

    return await call_next(request)


from app.routers.auth import (
    FORCE_PASSWORD_PAGE_HTML,
    LOGIN_PAGE_HTML,
    _sanitize_return_to,
    create_auth_router,
)

auth_router = create_auth_router(sys.modules[__name__])
app.include_router(auth_router)
globals().update({route.name: route.endpoint for route in auth_router.routes})


from app.routers.user_openapi import create_user_openapi_routers

user_openapi_read_router, user_openapi_management_router = create_user_openapi_routers(sys.modules[__name__])
app.include_router(user_openapi_read_router)
globals().update({route.name: route.endpoint for route in user_openapi_read_router.routes})

from app.routers.notification_settings import create_notification_settings_router

notification_settings_router = create_notification_settings_router(sys.modules[__name__])
app.include_router(notification_settings_router)
globals().update({route.name: route.endpoint for route in notification_settings_router.routes})

def _require_system_settings_admin(request: Request) -> None:
    if get_current_role(request) != "admin":
        raise HTTPException(status_code=403, detail={"code": "ADMIN_REQUIRED"})

from app.routers.toss_wts_session import create_toss_wts_session_router

toss_wts_session_router = create_toss_wts_session_router(sys.modules[__name__])
app.include_router(toss_wts_session_router)
globals().update({route.name: route.endpoint for route in toss_wts_session_router.routes})




from app.routers.notification_integrations import create_notification_integrations_router

notification_integrations_router, notification_integration_helpers = create_notification_integrations_router(
    sys.modules[__name__]
)
app.include_router(notification_integrations_router)
globals().update(notification_integration_helpers)
globals().update({route.name: route.endpoint for route in notification_integrations_router.routes})


# ---------------------------------------------------------------------------
# KFTC Open Banking Phase 1 API (Per-User Scope)
# ---------------------------------------------------------------------------

from app.routers.kftc_openbanking import create_kftc_openbanking_router

kftc_openbanking_router = create_kftc_openbanking_router(sys.modules[__name__])
app.include_router(kftc_openbanking_router)
globals().update({route.name: route.endpoint for route in kftc_openbanking_router.routes})


from app.routers.krx_credentials import create_krx_credentials_router

krx_credentials_router = create_krx_credentials_router(sys.modules[__name__])
app.include_router(krx_credentials_router)
globals().update({route.name: route.endpoint for route in krx_credentials_router.routes})


app.include_router(user_openapi_management_router)
globals().update({route.name: route.endpoint for route in user_openapi_management_router.routes})




from app.routers.admin_users import create_admin_users_router

admin_users_router = create_admin_users_router(sys.modules[__name__])
app.include_router(admin_users_router)
globals().update({route.name: route.endpoint for route in admin_users_router.routes})


# ---------------------------------------------------------------------------
# 기존 기능
# ---------------------------------------------------------------------------


from app.routers.holdings import HoldingCreate, create_holdings_routers


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> HTMLResponse:
    return HTMLResponse(status_code=204)


from app.services.dashboard_composition import create_dashboard_composition

globals().update(create_dashboard_composition(sys.modules[__name__]))


from app.routers.accounts import create_accounts_routers

# Resolve these dependencies at request time to preserve existing Python callers and patches.
portfolio_route_dependencies = {
    "get_current_username": lambda request: get_current_username(request),
    "financial_user_locks": lambda *args: financial_user_locks(*args),
    "read_portfolio": lambda **kwargs: read_portfolio(**kwargs),
    "write_portfolio": lambda data, **kwargs: write_portfolio(data, **kwargs),
    "get_family_members": lambda data: get_family_members(data),
}
display_order_router, account_collection_router, account_changes_router = create_accounts_routers(
    **portfolio_route_dependencies,
    get_dashboard=lambda **kwargs: get_dashboard(**kwargs),
)

app.include_router(display_order_router)


from app.routers.dashboard_overview import create_dashboard_overview_router
from app.services.dividend_overview import create_dividend_overview

globals().update(create_dividend_overview(sys.modules[__name__]))
dashboard_overview_router = create_dashboard_overview_router(sys.modules[__name__])
app.include_router(dashboard_overview_router)
globals().update({route.name: route.endpoint for route in dashboard_overview_router.routes})


from app.routers.financial_income import create_financial_income_router

financial_income_router = create_financial_income_router(sys.modules[__name__])
app.include_router(financial_income_router)
globals().update({route.name: route.endpoint for route in financial_income_router.routes})


from app.routers.actual_dividends import create_actual_dividends_router

# Keep the existing shared evidence cache and resolve app dependencies at call time.
actual_dividends_router = create_actual_dividends_router(
    get_current_username=lambda request: get_current_username(request),
    get_dashboard=lambda **kwargs: get_dashboard(**kwargs),
    get_root_dir=lambda: ROOT_DIR,
    log_exception=lambda message: logger.exception(message),
    get_actual_dividend_summary=lambda *args, **kwargs: get_actual_dividend_summary(*args, **kwargs),
    _actual_dividend_evidence=lambda records, username: _actual_dividend_evidence(records, username),
    create_dividend_record=lambda *args, **kwargs: create_dividend_record(*args, **kwargs),
    update_dividend_record=lambda *args, **kwargs: update_dividend_record(*args, **kwargs),
    delete_dividend_record=lambda *args, **kwargs: delete_dividend_record(*args, **kwargs),
    import_dividend_file_data=lambda *args, **kwargs: import_dividend_file_data(*args, **kwargs),
    clear_dividend_records=lambda *args, **kwargs: clear_dividend_records(*args, **kwargs),
    sync_historical_fx=lambda *args, **kwargs: sync_historical_fx(*args, **kwargs),
    recalculate_dividend_historical_fx=lambda *args, **kwargs: recalculate_dividend_historical_fx(*args, **kwargs),
    get_historical_fx_rate=lambda *args, **kwargs: get_historical_fx_rate(*args, **kwargs),
    now=lambda: datetime.now(),
)
app.include_router(actual_dividends_router)
globals().update({route.name: route.endpoint for route in actual_dividends_router.routes})


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


@app.get("/api/sample/accounts")
async def download_sample_accounts():
    p = ROOT_DIR / "data" / "샘플_증권계좌.xlsx"
    if not p.exists():
        p = ROOT_DIR / "샘플_증권계좌.xlsx"
    if not p.exists():
        raise HTTPException(status_code=404, detail="샘플_증권계좌.xlsx 파일을 찾을 수 없습니다.")
    return FileResponse(path=str(p), filename="샘플_증권계좌.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------------------
# MoneyLog Unified Calendar API
# ---------------------------------------------------------------------------

@app.get("/api/moneylog/calendar")
async def get_moneylog_calendar(
    request: Request,
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    owner: str = "모두",
) -> dict:
    """Return unified calendar events for realized PnL, dividends, interest, ledger, and IPOs."""
    username = get_current_username(request)
    try:
        from app.services.ipo.calendar import build_moneylog_calendar_events
        events = build_moneylog_calendar_events(username, from_date, to_date, owner)
        return {
            "from": from_date,
            "to": to_date,
            "owner": owner,
            "events": events,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# IPO Subsystem API
# ---------------------------------------------------------------------------

from app.routers.ipo_market import create_ipo_market_router

ipo_market_router = create_ipo_market_router(
    get_current_username=lambda request: get_current_username(request),
    log_exception=lambda message: logger.exception(message),
)
app.include_router(ipo_market_router)
globals().update({route.name: route.endpoint for route in ipo_market_router.routes})


@app.post("/api/integrations/telegram/webhook")
async def telegram_ipo_webhook(request: Request) -> dict:
    """Provider-authenticated Telegram IPO action ingress."""
    from app.services.ipo.telegram_interactive import handle_update, interactive_config
    if interactive_config() is None:
        raise HTTPException(status_code=503, detail={"code": "TELEGRAM_INTERACTIVE_DISABLED"})
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    try:
        update = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_TELEGRAM_UPDATE"}) from exc
    result = handle_update(update, secret)
    if result == "unauthorized":
        raise HTTPException(status_code=403, detail={"code": "TELEGRAM_UNAUTHORIZED"})
    return {"status": result}


from app.routers.ipo_applications import (
    _ipo_listing_date,
    _ipo_market_record,
    _ipo_source_broker_ids,
    _ipo_source_brokers,
    _validate_ipo_source_broker,
    create_ipo_applications_router,
)

ipo_applications_router = create_ipo_applications_router(
    get_current_username=lambda request: get_current_username(request),
)
app.include_router(ipo_applications_router)
globals().update({route.name: route.endpoint for route in ipo_applications_router.routes})


# ---------------------------------------------------------------------------
# Realized PnL API
# ---------------------------------------------------------------------------

from app.routers.realized_pnl import create_realized_pnl_routers

realized_pnl_router, realized_pnl_import_router = create_realized_pnl_routers(
    get_current_username=lambda request: get_current_username(request),
    get_dashboard=lambda **kwargs: get_dashboard(**kwargs),
    get_root_dir=lambda: ROOT_DIR,
    log_exception=lambda message: logger.exception(message),
    get_pnl_summary=lambda *args, **kwargs: get_pnl_summary(*args, **kwargs),
    create_pnl_record=lambda *args, **kwargs: create_pnl_record(*args, **kwargs),
    update_pnl_record=lambda *args, **kwargs: update_pnl_record(*args, **kwargs),
    delete_pnl_record=lambda *args, **kwargs: delete_pnl_record(*args, **kwargs),
    clear_pnl_records=lambda *args, **kwargs: clear_pnl_records(*args, **kwargs),
    clear_pnl_records_for_broker=lambda *args, **kwargs: clear_pnl_records_for_broker(*args, **kwargs),
    import_pnl_file_data=lambda *args, **kwargs: import_pnl_file_data(*args, **kwargs),
    recalculate_pnl_historical_fx=lambda *args, **kwargs: recalculate_pnl_historical_fx(*args, **kwargs),
)
app.include_router(realized_pnl_router)


holdings_clear_router, holdings_collection_router, holding_update_router = create_holdings_routers(
    **portfolio_route_dependencies,
    get_dashboard=lambda **kwargs: get_dashboard(**kwargs),
)

app.include_router(holdings_clear_router)


app.include_router(realized_pnl_import_router)
globals().update({
    route.name: route.endpoint
    for router in (realized_pnl_router, realized_pnl_import_router)
    for route in router.routes
})


@app.get("/api/status")
async def status() -> dict:
    return {
        "kb_configured": KBOpenAPI().configured,
        "toss_configured": TossOpenAPI().configured,
        "namoo_configured": NhPlugOpenAPI().configured,
        "storage": "local",
    }


from app.routers.toss_wts_feed import create_toss_wts_feed_router

toss_wts_feed_router = create_toss_wts_feed_router(sys.modules[__name__])
app.include_router(toss_wts_feed_router)
globals().update({route.name: route.endpoint for route in toss_wts_feed_router.routes})


from app.routers.broker_realized import create_broker_realized_routers
from app.services.broker_realized_destination import create_broker_realized_destination

globals().update(create_broker_realized_destination(sys.modules[__name__]))

kis_realized_router, nh_realized_router, kb_realized_router, kiwoom_realized_router = (
    create_broker_realized_routers(sys.modules[__name__])
)
app.include_router(kis_realized_router)
globals().update({route.name: route.endpoint for route in kis_realized_router.routes})
app.include_router(nh_realized_router)
globals().update({route.name: route.endpoint for route in nh_realized_router.routes})
app.include_router(kb_realized_router)
globals().update({route.name: route.endpoint for route in kb_realized_router.routes})
app.include_router(kiwoom_realized_router)
globals().update({route.name: route.endpoint for route in kiwoom_realized_router.routes})


# ---------------------------------------------------------------------------
# Family accounts API
# ---------------------------------------------------------------------------

app.include_router(account_collection_router)


# Register the asset routers in the original savings and real-estate route order.
from app.routers.real_estate import create_real_estate_router
from app.routers.savings_pension import create_savings_pension_router

savings_pension_router = create_savings_pension_router(
    get_current_username=lambda request: get_current_username(request),
)
app.include_router(savings_pension_router)

real_estate_router = create_real_estate_router(
    get_current_username=lambda request: get_current_username(request),
    financial_user_locks=lambda *args: financial_user_locks(*args),
    read_portfolio=lambda username: read_portfolio(username),
    now=lambda: datetime.now(),
)
app.include_router(real_estate_router)

# Keep the original Python endpoint names available to existing callers.
globals().update({route.name: route.endpoint
                  for router in (savings_pension_router, real_estate_router)
                  for route in router.routes})


# Family members CRUD API
# ---------------------------------------------------------------------------

from app.routers.family_members import create_family_members_router

family_members_router = create_family_members_router(**portfolio_route_dependencies)

app.include_router(family_members_router)


from app.routers.market_data import create_market_data_routers

market_overview_router, market_quotes_router = create_market_data_routers(sys.modules[__name__])
app.include_router(market_overview_router)
globals().update({route.name: route.endpoint for route in market_overview_router.routes})


app.include_router(holdings_collection_router)


app.include_router(account_changes_router)


app.include_router(holding_update_router)

# Keep the original Python endpoint names for direct callers.
globals().update({
    route.name: route.endpoint
    for router in (
        display_order_router, account_collection_router, account_changes_router,
        holdings_clear_router, holdings_collection_router, holding_update_router, family_members_router,
    )
    for route in router.routes
})


from app.routers.data_transfer import create_data_transfer_router

data_transfer_router = create_data_transfer_router(sys.modules[__name__])
app.include_router(data_transfer_router)
globals().update({route.name: route.endpoint for route in data_transfer_router.routes})

from app.routers.demo_reset import create_demo_reset_router

demo_reset_router = create_demo_reset_router(sys.modules[__name__])
app.include_router(demo_reset_router)
globals().update({route.name: route.endpoint for route in demo_reset_router.routes})


from app.routers.planning import create_planning_routers

planning_read_router, planning_write_router = create_planning_routers(sys.modules[__name__])
app.include_router(planning_read_router)
globals().update({route.name: route.endpoint for route in planning_read_router.routes})


from app.routers.color_preferences import create_color_preferences_router

color_preferences_router = create_color_preferences_router(sys.modules[__name__])
app.include_router(color_preferences_router)
globals().update({route.name: route.endpoint for route in color_preferences_router.routes})


app.include_router(planning_write_router)
globals().update({route.name: route.endpoint for route in planning_write_router.routes})


from app.routers.asset_records import create_asset_records_router

asset_records_router = create_asset_records_router(sys.modules[__name__])
app.include_router(asset_records_router)
globals().update({route.name: route.endpoint for route in asset_records_router.routes})


from app.routers.broker_sync import create_broker_sync_routers

broker_sync_router, all_accounts_sync_router = create_broker_sync_routers(sys.modules[__name__])
app.include_router(broker_sync_router)
globals().update({route.name: route.endpoint for route in broker_sync_router.routes})



from app.routers.price_refresh import create_price_refresh_routers
from app.services.portfolio_price_refresh import create_portfolio_price_refresh

refresh_prices_for_user, refresh_fx_for_user = create_portfolio_price_refresh(sys.modules[__name__])

fx_refresh_router, prices_refresh_router = create_price_refresh_routers(sys.modules[__name__])
app.include_router(fx_refresh_router)
globals().update({route.name: route.endpoint for route in fx_refresh_router.routes})


app.include_router(prices_refresh_router)
globals().update({route.name: route.endpoint for route in prices_refresh_router.routes})

app.include_router(market_quotes_router)
globals().update({route.name: route.endpoint for route in market_quotes_router.routes})


app.include_router(all_accounts_sync_router)
globals().update({route.name: route.endpoint for route in all_accounts_sync_router.routes})



# Attach the ledger routes in their original position in the app.
from app.routers.ledger import create_ledger_router

ledger_router = create_ledger_router(
    get_current_username=lambda request: get_current_username(request),
    get_root_dir=lambda: ROOT_DIR,
)
app.include_router(ledger_router)

# Preserve Python callers of app.main's original endpoint functions.
globals().update({route.name: route.endpoint for route in ledger_router.routes})


from app.routers.ipo_web_actions import (
    ACTION_LANDING_HTML,
    _render_action_card,
    _validate_same_origin_request,
    create_ipo_web_actions_router,
)

ipo_web_actions_router = create_ipo_web_actions_router(sys.modules[__name__])
app.include_router(ipo_web_actions_router)
globals().update({route.name: route.endpoint for route in ipo_web_actions_router.routes})


# Web boundary only; the Docker executor is installed separately on Oracle.
from app.system_update import register_update_routes
register_update_routes(app, app_version=APP_VERSION, secret=SECRET_KEY,
                       username=get_current_username, origin=_validate_same_origin_request,
                       session_current=_updater_session_current)
