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
from urllib.parse import quote, urlsplit

import httpx
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
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


def _realized_destination_resolution(
    username: str,
    provider: str,
    *,
    provider_account_identity: object = None,
    mapped_destination_account_id: object = None,
):
    """Resolve a provider source only to same-broker Wealth accounts."""
    accounts = read_portfolio(username=username).get("accounts", [])
    return resolve_realized_destination_candidates(
        provider,
        accounts,
        provider_account_identity=provider_account_identity,
        mapped_destination_account_id=mapped_destination_account_id,
    )


def _realized_destination_payload(resolution: Any) -> dict[str, Any]:
    return {
        "candidate_account_ids": list(resolution.candidate_account_ids),
        "auto_selected_account_id": resolution.auto_selected_account_id,
        "destination_resolution": resolution.reason,
        "mapping_status": resolution.mapping_status,
    }


def _require_realized_destination(
    username: str,
    provider: str,
    account_id: object,
    *,
    provider_account_identity: object = None,
    mapped_destination_account_id: object = None,
) -> dict[str, Any]:
    if not isinstance(account_id, str) or not account_id.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "DESTINATION_INVALID", "message": "Explicit destination account is required"},
        )
    accounts = read_portfolio(username=username).get("accounts", [])
    try:
        account, _ = validate_realized_destination(
            provider,
            accounts,
            account_id,
            provider_account_identity=provider_account_identity,
            mapped_destination_account_id=mapped_destination_account_id,
        )
        return account
    except ValueError as exc:
        code = str(exc)
        if code in {"CROSS_BROKER_MAPPING", "DESTINATION_MAPPING_CONFLICT", "DESTINATION_IDENTITY_CONFLICT"}:
            status = 409
            message = "Source account destination mapping conflicts with this import"
        else:
            status = 400
            message = "Destination account must belong to the same broker"
        raise HTTPException(status_code=status, detail={"code": code, "message": message}) from exc


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
    if isinstance(error, (AccountSyncPersistenceError, FinancialStorageError)):
        return "PERSISTENCE_ERROR"
    text = str(error.detail if isinstance(error, HTTPException) else error)
    if any(marker in text for marker in ("응답 형식", "올바른 JSON", "항목 형식", "연속조회")):
        return "PARSE_ERROR"
    if isinstance(error, (HTTPException, KBOpenAPIError, TossOpenAPIError, NhPlugOpenAPIError, KISOpenAPIError, KiwoomOpenAPIError)):
        return "API_ERROR"
    return "INTERNAL_ERROR"


def _unverified_holdings_response(broker: str, records: object) -> dict:
    state = (
        records.state.value
        if isinstance(records, BrokerHoldingsResult)
        else HoldingsResultState.UNKNOWN_EMPTY.value
    )
    return {
        "broker": broker,
        "status": "SCOPE_UNVERIFIED",
        "message": "잔고 응답의 계좌·시장 범위를 확인할 수 없어 기존 보유종목을 유지했습니다.",
        "count": 0,
        "holdings_valid": False,
        "holdings_state": state,
        "cash_valid": records.cash_valid if isinstance(records, BrokerHoldingsResult) else False,
        "cash_updated": False,
        "data_preserved": True,
    }


def _holdings_success_status(records: BrokerHoldingsResult) -> str:
    return "CONFIRMED_EMPTY" if records.state == HoldingsResultState.AUTHORITATIVE_EMPTY else "SUCCESS"


def _mark_sync_success(data: dict, broker: str) -> None:
    data.setdefault("settings", {}).setdefault("sync_last_success", {})[broker] = datetime.now().astimezone().isoformat(timespec="seconds")

def _save_account_sync(data: dict, username: str) -> None:
    try:
        write_portfolio(data, username=username)
    except Exception as exc:
        raise AccountSyncPersistenceError("ACCOUNT_SYNC_PERSISTENCE_FAILED") from exc


def _load_account_sync(username: str) -> dict:
    try:
        return read_portfolio(username=username)
    except Exception as exc:
        raise AccountSyncPersistenceError("ACCOUNT_SYNC_STORAGE_INVALID") from exc


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


_SAFE_RETURN_TO_RE = re.compile(r"^/a/[A-Za-z0-9_-]{16,64}$")


def _sanitize_return_to(return_to: str | None) -> str | None:
    if not return_to or not isinstance(return_to, str):
        return None
    val = return_to.strip()
    if _SAFE_RETURN_TO_RE.match(val):
        return val
    return None


@app.get("/login", include_in_schema=False)
async def login_page(error: str | None = None, return_to: str | None = None) -> HTMLResponse:
    message = "<p class='error'>아이디 또는 비밀번호가 올바르지 않습니다.</p>" if error else ""
    safe_return_to = _sanitize_return_to(return_to)
    return_to_input = (
        f'<input type="hidden" name="return_to" value="{safe_return_to}" />'
        if safe_return_to
        else ""
    )
    html = (
        LOGIN_PAGE_HTML
        .replace("{{message}}", message)
        .replace("{{return_to_input}}", return_to_input)
    )
    return HTMLResponse(html)


@app.post("/login", include_in_schema=False)
async def login_submit(
    username: str = Form(...),
    password: str = Form(...),
    return_to: str | None = Form(None),
):
    from app.services.user_manager import authenticate_user
    u = authenticate_user(username.strip(), password.strip())
    safe_return_to = _sanitize_return_to(return_to)
    if u:
        token = _new_session_token(u)
        # 초기 비밀번호 변경 필요 계정이면 대시보드가 아닌 비번 변경 전용 페이지로 즉시 리다이렉트
        if u.get("must_change_password", False):
            response = RedirectResponse("/change-password-init", status_code=303)
        elif safe_return_to:
            response = RedirectResponse(safe_return_to, status_code=303)
        else:
            response = RedirectResponse("/dashboard", status_code=303)
        
        response.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            secure=not TESTING,
            samesite="lax",
            max_age=SESSION_MAX_AGE,
        )
        return response
    err_redirect = "/login?error=1"
    if safe_return_to:
        err_redirect += f"&return_to={quote(safe_return_to, safe='')}"
    return RedirectResponse(err_redirect, status_code=303)


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
    if not user.get('must_change_password', False):
        raise HTTPException(403, detail={'code': 'PASSWORD_CHANGE_NOT_PENDING'})
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
    from app.services.user_manager import get_user_by_name
    token = _new_session_token(get_user_by_name(uname))
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=not TESTING,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
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
    from app.services.user_manager import get_user_by_name
    from app.services.update_permissions import can_system_update
    allowed = can_system_update(get_user_by_name(username))
    return {
        "username": username,
        "role": role,
        "must_change_password": must_change,
        "can_system_update": allowed,
    }


@app.post("/api/auth/change-password")
async def change_password_endpoint(request: Request, response: Response) -> dict:
    """사용자 본인 비밀번호 변경"""
    username = get_current_username(request)
    body = await request.json()
    old_pw = str(body.get("old_password", "")).strip()
    new_pw = str(body.get("new_password", "")).strip()
    from app.services.user_manager import change_user_password
    try:
        change_user_password(username, old_pw, new_pw)
        _refresh_auth_cookie(response, username)
        return {"message": "비밀번호가 성공적으로 변경되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/force-change-password")
async def force_change_password_endpoint(request: Request, response: Response) -> dict:
    """must_change_password 상태에서 새 비밀번호 설정"""
    username = get_current_username(request)
    if not getattr(request.state, 'must_change_password', False):
        raise HTTPException(403, detail={'code': 'PASSWORD_CHANGE_NOT_PENDING'})
    body = await request.json()
    new_pw = str(body.get("new_password", "")).strip()
    from app.services.user_manager import force_set_user_password
    try:
        force_set_user_password(username, new_pw)
        _refresh_auth_cookie(response, username)
        return {"message": "새 비밀번호가 설정되었습니다."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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


DEFAULT_FAMILY_MEMBERS = ["아빠", "엄마", "자녀"]

def get_family_members(data: dict) -> list:
    return data.get("settings", {}).get("family_members", list(DEFAULT_FAMILY_MEMBERS))


def _snapshot_target_owners(data: dict) -> list[str]:
    """Return all configured/discovered owners, always including '모두'."""
    candidates = list(get_family_members(data) or DEFAULT_FAMILY_MEMBERS)
    for key in ("accounts", "bank_accounts", "savings_accounts", "insurance_accounts", "loan_accounts"):
        for item in data.get(key, []) or []:
            owner = str(item.get("owner") or "").strip()
            if owner and owner != "모두":
                candidates.append(owner)
    for item in data.get("real_estates", []) or []:
        for ownership in item.get("ownerships") or []:
            owner = str(ownership.get("owner") or "").strip()
            if owner and owner != "모두":
                candidates.append(owner)
        owner = str(item.get("owner") or "").strip()
        if owner and owner != "모두" and owner in DEFAULT_FAMILY_MEMBERS:
            candidates.append(owner)
    return ["모두"] + list(dict.fromkeys(owner for owner in candidates if owner and owner != "모두"))


def auto_save_all_owner_snapshots(
    data: dict[str, Any],
    username: str | None = None,
    source: str = "auto",
    memo: str = "자동 기록",
    as_of: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    '모두' 및 모든 가족 구성원의 당일 주식기록을 동일한 canonical 계산으로 upsert합니다.
    보유종목이 없는 owner도 0원 스냅샷을 남겨 전체 owner의 날짜 축을 일관되게 유지합니다.

    Session de-duplication: for each owner, the most recent prior asset record is
    consulted for its holdings_session provenance map.  Holdings whose market session
    date has not advanced since that prior record contribute 0 to day_profit_krw,
    preventing the same session gain from being booked again on non-trading days.
    """
    if not data:
        return []

    if as_of is not None:
        today = (as_of.astimezone() if as_of.tzinfo else as_of).date().isoformat()
    else:
        today = datetime.now().astimezone().date().isoformat()
    fx_rates = data.get("fx_rates")
    accounts = data.get("accounts", []) or []
    all_holdings = data.get("holdings", []) or []
    saved: list[dict[str, Any]] = []

    # Pre-load existing records once per call for prev_session_map extraction
    try:
        existing_records = list_asset_records(username=username)
    except Exception:
        existing_records = []

    for owner in _snapshot_target_owners(data):
        if owner == "모두":
            owned_holdings = all_holdings
        else:
            owned_accounts = [a for a in accounts if (a.get("owner") or "모두") == owner]
            owned_acc_ids = {a.get("id") for a in owned_accounts if a.get("id")}
            owned_holdings = [
                h for h in all_holdings
                if h.get("account_id") in owned_acc_ids or h.get("owner") == owner
            ]

        # Extract session provenance from the most recent prior record for this owner
        # Default to {} (not None): {} means "baseline exists but empty" → suppress all contributions
        # on first provenance-aware snapshot, preventing fabrication of unverified P/L.
        prev_session_map: dict[str, str] = {}
        try:
            owner_norm = owner or "모두"
            prior_records = [
                r for r in existing_records
                if (r.get("owner") or "모두") == owner_norm
                and r.get("date")
                and r.get("date") < today
            ]
            if prior_records:
                prior_records.sort(key=lambda r: r.get("date") or "")
                latest_prior = prior_records[-1]
                hs = latest_prior.get("holdings_session")
                if isinstance(hs, dict) and hs:
                    prev_session_map = hs  # use the stored provenance map
                # else: prior record exists but has no/empty provenance → keep {} (suppress all)
        except Exception:
            prev_session_map = {}  # on error, suppress all (safe)

        payload = build_stock_record_from_holdings(
            owned_holdings,
            owner=owner,
            today=today,
            source=source,
            memo=memo,
            fx_rates=fx_rates,
            prev_session_map=prev_session_map,
        )
        saved.append(upsert_asset_record(payload, by_date=True, username=username))

    return saved


def save_all_owner_net_worth_snapshots(
    data: dict[str, Any],
    username: str,
    source: str = "auto",
    as_of: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Calculate and atomically save current net-worth snapshots for all owners."""
    from app.services.planning import build_net_worth_snapshot, upsert_current_snapshots

    snapshots = [build_net_worth_snapshot(data, owner) for owner in _snapshot_target_owners(data)]
    state = upsert_current_snapshots(username, snapshots, source=source, as_of=as_of)
    return state, snapshots


def get_full_dashboard_for_user(username: str, record_snapshots: bool = False) -> dict:
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

    if record_snapshots:
        auto_save_all_owner_snapshots(data, username=username, source="auto", memo="접속 자동 기록")
    return data


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


@app.get("/api/dashboard")
async def dashboard(request: Request, record_snapshots: bool = False) -> dict:
    username = get_current_username(request)
    return get_full_dashboard_for_user(username=username, record_snapshots=record_snapshots)


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
    summary = await get_web_dividend_summary(holdings, fx_rate=fx_rate, username=username)
    return {**summary, 'dividend_tax_benefits': _dividend_benefit_context(
        summary, full, username=username, owner=owner, tax_year=datetime.now(ZoneInfo('Asia/Seoul')).year)}


def _dividend_benefit_context(summary, full, *, username, owner, tax_year, selections=None):
    import hashlib
    from app.services.tax.what_if import build_dividend_benefit_preview
    accounts = {a['id']: a.get('owner') for a in full.get('accounts', [])}
    owners = sorted({str(h.get('owner') or accounts.get(h.get('account_id')) or '')
        for h in full.get('holdings', [])} - {'', '모두'})
    invalid_owner = owner != '모두' and owner not in owners
    context = hashlib.sha256(f'{username}\0{owner}\0{tax_year}'.encode()).hexdigest()
    # Refuse mixed/ambiguous quantity scopes without changing the legacy summary.
    import math
    from app.services.dividend_event_identity import normalize_dividend_code
    quantities = {}
    for holding in full.get('holdings', []):
        if str(holding.get('currency') or 'KRW').upper() != 'KRW':
            continue
        if str(holding.get('owner') or accounts.get(holding.get('account_id')) or '') != owner:
            continue
        code = normalize_dividend_code(holding.get('code'))
        quantity = holding.get('quantity')
        if isinstance(quantity, (int, float)) and not isinstance(quantity, bool) and math.isfinite(quantity) and quantity > 0:
            quantities[code] = quantities.get(code, 0) + quantity
    scoped = {**summary, 'monthly_schedule': [{**bucket, 'items': [item for item in bucket.get('items', [])
        if isinstance(item.get('quantity'), (int, float))
        and item.get('quantity') == quantities.get(normalize_dividend_code(item.get('code')))]}
        for bucket in summary.get('monthly_schedule', [])]}
    result = ({'owner': owner, 'tax_year': tax_year, 'events': [], 'requires_owner': True,
        'session_only': True, 'invalid_owner': invalid_owner} if owner == '모두' or invalid_owner else build_dividend_benefit_preview(
            scoped, owner=owner, tax_year=tax_year, selections=selections, as_of=datetime.now(ZoneInfo('Asia/Seoul')).date()))
    return {**result, 'context_key': context, 'owners': owners}


@app.post('/api/dividends/tax-benefit-preview')
async def dividend_tax_benefit_preview(request: Request) -> JSONResponse:
    username = get_current_username(request)
    from app.services.tax.what_if import FinancialIncomeWhatIfError
    try:
        body = await request.json()
        if not isinstance(body, dict) or set(body) - {'owner', 'tax_year', 'selections', 'context_key'}:
            raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_REQUEST_INVALID')
        owner = body.get('owner', '모두')
        year = body.get('tax_year', datetime.now(ZoneInfo('Asia/Seoul')).year)
        if not isinstance(owner, str) or not owner.strip():
            raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_OWNER_INVALID')
        if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100:
            raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_YEAR_INVALID')
        choices = body.get('selections', {})
        if not isinstance(choices, dict) or len(choices) > 500 or (owner == '모두' and choices):
            raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_SELECTION_INVALID')
        full = get_dashboard(username=username)
        # Resolve owner from authenticated holdings; never accept client events,
        # official verdicts, gross amounts, or a client username.
        context = _dividend_benefit_context({}, full, username=username, owner=owner, tax_year=year)
        if context.get('invalid_owner'):
            raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_OWNER_INVALID')
        if choices and body.get('context_key') != context['context_key']:
            raise FinancialIncomeWhatIfError('DIVIDEND_BENEFIT_CONTEXT_CHANGED')
        account_owners = {a['id']: a.get('owner') for a in full.get('accounts', [])}
        holdings = [h for h in full.get('holdings', [])
            if str(h.get('owner') or account_owners.get(h.get('account_id')) or '') == owner]
        summary = await get_web_dividend_summary(holdings,
            fx_rate=full.get('fx_rates', {}).get('USD', 1385.0), username=username) if owner != '모두' else {}
        result = _dividend_benefit_context(summary, full, username=username, owner=owner,
            tax_year=year, selections=body.get('selections'))
    except (FinancialIncomeWhatIfError, ValueError) as exc:
        code = str(exc) if isinstance(exc, FinancialIncomeWhatIfError) else 'DIVIDEND_BENEFIT_REQUEST_INVALID'
        raise HTTPException(status_code=400, detail={'code': code}, headers={'Cache-Control': 'no-store'}) from None
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@app.get("/api/dividends/financial-income-family-risk")
async def financial_income_family_risk(request: Request) -> JSONResponse:
    """Return per-family-member financial-income screening risk."""
    username = get_current_username(request)
    from app.services.tax import (
        FamilyFinancialIncomeRiskError,
        get_family_financial_income_risk_for_user,
    )
    try:
        result = await get_family_financial_income_risk_for_user(username)
    except FamilyFinancialIncomeRiskError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": str(exc)},
            headers={"Cache-Control": "no-store"},
        ) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/dividends/financial-income-family-allocation-simulation")
async def financial_income_family_allocation_simulation(request: Request) -> JSONResponse:
    """Compare a hypothetical family financial-income allocation without writes."""
    username = get_current_username(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "FAMILY_ALLOCATION_REQUEST_INVALID"}, headers={"Cache-Control": "no-store"}) from exc
    if (
        not isinstance(body, dict)
        or set(body) != {"allocations"}
        or not isinstance(body.get("allocations"), list)
    ):
        raise HTTPException(status_code=400, detail={"code": "FAMILY_ALLOCATION_REQUEST_INVALID"}, headers={"Cache-Control": "no-store"})
    from app.services.tax import (
        FamilyFinancialIncomeAllocationError,
        get_family_financial_income_allocation_simulation_for_user,
    )
    try:
        result = await get_family_financial_income_allocation_simulation_for_user(
            username, allocations=body["allocations"]
        )
    except FamilyFinancialIncomeAllocationError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc)}, headers={"Cache-Control": "no-store"}) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/dividends/financial-income-personal-comprehensive-tax")
async def financial_income_personal_comprehensive_tax(request: Request) -> JSONResponse:
    """Compare explicit tax-base scenarios using the 2026 national basic rates."""
    get_current_username(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "PERSONAL_COMPREHENSIVE_TAX_REQUEST_INVALID"},
            headers={"Cache-Control": "no-store"},
        ) from exc

    required_fields = {
        "tax_base_before_financial_income_krw",
        "financial_income_gross_krw",
        "assumed_financial_income_included_in_tax_base_krw",
    }
    if not isinstance(body, dict) or set(body) != required_fields:
        raise HTTPException(
            status_code=400,
            detail={"code": "PERSONAL_COMPREHENSIVE_TAX_REQUEST_INVALID"},
            headers={"Cache-Control": "no-store"},
        )

    from app.services.tax import (
        PersonalComprehensiveTaxError,
        calculate_personal_comprehensive_tax_basic_rate_2026,
    )

    try:
        result = calculate_personal_comprehensive_tax_basic_rate_2026(**body)
    except PersonalComprehensiveTaxError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": str(exc)},
            headers={"Cache-Control": "no-store"},
        ) from exc
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/dividends/financial-income-article62-comparison")
async def financial_income_article62_comparison(request: Request) -> JSONResponse:
    """Return a stateless Article 62 comparison before credits."""
    get_current_username(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "ARTICLE62_REQUEST_INVALID"}, headers={"Cache-Control": "no-store"}) from exc
    from app.services.tax import PersonalComprehensiveTaxError, calculate_financial_income_article62_comparison_2026
    try:
        result = calculate_financial_income_article62_comparison_2026(**body) if isinstance(body, dict) else None
    except PersonalComprehensiveTaxError as exc:
        raise HTTPException(status_code=400, detail={"code": str(exc)}, headers={"Cache-Control": "no-store"}) from exc
    if result is None:
        raise HTTPException(status_code=400, detail={"code": "ARTICLE62_REQUEST_INVALID"}, headers={"Cache-Control": "no-store"})
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/dividends/financial-income-simulation")
async def simulate_financial_income(request: Request) -> JSONResponse:
    """Return a stateless annual financial-income screening projection."""
    username = get_current_username(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "FINANCIAL_INCOME_REQUEST_INVALID"},
            headers={"Cache-Control": "no-store"},
        ) from exc
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail={"code": "FINANCIAL_INCOME_REQUEST_INVALID"},
            headers={"Cache-Control": "no-store"},
        )

    allowed_fields = {
        "owner",
        "expected_remaining_interest_gross_krw",
        "current_month_remaining_dividend_gross_krw",
    }
    if set(body) - allowed_fields:
        raise HTTPException(
            status_code=400,
            detail={"code": "FINANCIAL_INCOME_REQUEST_INVALID"},
            headers={"Cache-Control": "no-store"},
        )

    owner = body.get("owner", "모두")
    if not isinstance(owner, str) or not owner.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "FINANCIAL_INCOME_OWNER_INVALID"},
            headers={"Cache-Control": "no-store"},
        )

    from app.services.tax import (
        FinancialIncomeProjectionError,
        get_financial_income_projection_for_user,
    )

    try:
        result = await get_financial_income_projection_for_user(
            username,
            owner=owner.strip(),
            expected_remaining_interest_gross_krw=body.get(
                "expected_remaining_interest_gross_krw", 0.0
            ),
            current_month_remaining_dividend_gross_krw=body.get(
                "current_month_remaining_dividend_gross_krw", 0.0
            ),
        )
    except FinancialIncomeProjectionError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": str(exc)},
            headers={"Cache-Control": "no-store"},
        ) from exc

    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.post("/api/dividends/financial-income-what-if")
async def simulate_financial_income_what_if(request: Request) -> JSONResponse:
    """Return a stateless financial-income and investment-method What-if."""
    username = get_current_username(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
            headers={"Cache-Control": "no-store"},
        ) from exc
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
            headers={"Cache-Control": "no-store"},
        )

    allowed_fields = {
        "owner",
        "as_of",
        "expected_remaining_interest_gross_krw",
        "current_month_remaining_dividend_gross_krw",
        "additional_dividend_gross_krw",
        "additional_interest_gross_krw",
        "additional_foreign_share_realized_gain_krw",
        "additional_kr_listed_overseas_etf_taxable_gain_krw",
        "high_dividend_scenario",
        "investment_scenario",
    }
    if set(body) - allowed_fields:
        raise HTTPException(
            status_code=400,
            detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
            headers={"Cache-Control": "no-store"},
        )

    owner = body.get("owner", "모두")
    if not isinstance(owner, str) or not owner.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "FINANCIAL_INCOME_OWNER_INVALID"},
            headers={"Cache-Control": "no-store"},
        )

    high_dividend_scenario = body.get("high_dividend_scenario")
    if high_dividend_scenario is not None:
        if not isinstance(high_dividend_scenario, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )
        allowed_high_dividend_fields = {
            "special_dividend_income_krw",
            "high_dividend_company_confirmed",
            "separate_taxation_requested",
        }
        if set(high_dividend_scenario) - allowed_high_dividend_fields:
            raise HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )

    investment_scenario = body.get("investment_scenario")
    if investment_scenario is not None:
        if not isinstance(investment_scenario, dict):
            raise HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )
        allowed_investment_fields = {
            "asset_type",
            "annual_distribution_krw",
            "annual_realized_gain_krw",
            "taxable_etf_gain_krw",
            "existing_corporate_taxable_income_krw",
            "corporate_deductible_expenses_krw",
            "corporation_to_owner_distribution_krw",
            "domestic_dividend_exclusion_eligible",
            "domestic_dividend_ownership_pct",
            "domestic_dividend_holding_months",
            "us_treaty_parent_rate_qualified",
            "foreign_subsidiary_exclusion_qualified",
            "foreign_ownership_pct",
        }
        if set(investment_scenario) - allowed_investment_fields:
            raise HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )
        asset_type = investment_scenario.get("asset_type")
        if not isinstance(asset_type, str) or not asset_type.strip():
            raise HTTPException(
                status_code=400,
                detail={"code": "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID"},
                headers={"Cache-Control": "no-store"},
            )

    from app.services.tax import (
        FinancialIncomeProjectionError,
        FinancialIncomeWhatIfError,
        HighDividendSpecialTaxError,
        InvestmentTaxComparisonError,
        get_financial_income_what_if_for_user,
    )

    try:
        result = await get_financial_income_what_if_for_user(
            username,
            owner=owner.strip(),
            **({"as_of": body["as_of"]} if "as_of" in body else {}),
            expected_remaining_interest_gross_krw=body.get(
                "expected_remaining_interest_gross_krw", 0.0
            ),
            current_month_remaining_dividend_gross_krw=body.get(
                "current_month_remaining_dividend_gross_krw", 0.0
            ),
            additional_dividend_gross_krw=body.get(
                "additional_dividend_gross_krw", 0.0
            ),
            additional_interest_gross_krw=body.get(
                "additional_interest_gross_krw", 0.0
            ),
            investment_scenario=investment_scenario,
            **(
                {
                    "additional_foreign_share_realized_gain_krw": body.get(
                        "additional_foreign_share_realized_gain_krw"
                    )
                }
                if "additional_foreign_share_realized_gain_krw" in body
                else {}
            ),
            **(
                {
                    "additional_kr_listed_overseas_etf_taxable_gain_krw": body.get(
                        "additional_kr_listed_overseas_etf_taxable_gain_krw"
                    )
                }
                if "additional_kr_listed_overseas_etf_taxable_gain_krw" in body
                else {}
            ),
            **(
                {"high_dividend_scenario": high_dividend_scenario}
                if high_dividend_scenario is not None
                else {}
            ),
        )
    except (
        FinancialIncomeProjectionError,
        FinancialIncomeWhatIfError,
        HighDividendSpecialTaxError,
        InvestmentTaxComparisonError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": str(exc)},
            headers={"Cache-Control": "no-store"},
        ) from exc

    return JSONResponse(result, headers={"Cache-Control": "no-store"})


_actual_dividend_evidence_cache = {}


async def _actual_dividend_evidence(records, username):
    """Small user-scoped read cache shared by list and debounced form preview."""
    import time
    from app.services.dividend_records import get_record_tax_evidence
    codes = tuple(sorted({str(r.get('code') or '') for r in records if r.get('currency', 'KRW') == 'KRW'}))
    if not codes:
        return {}
    key = (username, codes)
    cached = _actual_dividend_evidence_cache.get(key)
    if cached and time.monotonic() - cached[0] < 60:
        return cached[1]
    evidence = await get_record_tax_evidence(
        [{'code': code, 'currency': 'KRW'} for code in codes], username)
    if len(_actual_dividend_evidence_cache) >= 128:
        _actual_dividend_evidence_cache.clear()
    _actual_dividend_evidence_cache[key] = (time.monotonic(), evidence)
    return evidence


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


# ---------------------------------------------------------------------------
# KIS Realized Profit Feed API
# ---------------------------------------------------------------------------

def _kis_mapping_file(username: str) -> Path:
    from app.services.user_manager import get_user_data_dir
    return get_user_data_dir(username) / "kis_account_mapping.json"


def _read_kis_mapping(username: str) -> dict[str, str]:
    path = _kis_mapping_file(username)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _assert_kis_mapping_compatible(username: str, source_key: str, destination_id: str) -> bool:
    existing = _read_kis_mapping(username).get(source_key)
    if existing and existing != destination_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "KIS destination mapping conflicts with this import"},
        )
    return existing == destination_id


def _write_kis_mapping(username: str, source_key: str, destination_id: str) -> bool:
    if _assert_kis_mapping_compatible(username, source_key, destination_id):
        return False
    path = _kis_mapping_file(username)
    mapping = _read_kis_mapping(username)
    mapping[source_key] = destination_id
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return True

from app.routers.broker_realized import create_broker_realized_routers

kis_realized_router, nh_realized_router, kb_realized_router, kiwoom_realized_router = (
    create_broker_realized_routers(sys.modules[__name__])
)
app.include_router(kis_realized_router)
globals().update({route.name: route.endpoint for route in kis_realized_router.routes})


# ---------------------------------------------------------------------------
# NH Realized Profit Feed API
# ---------------------------------------------------------------------------

async def _resolve_nh_source_account(client: NhPlugOpenAPI, source_key: str) -> tuple[str, str]:
    """Resolve an opaque client key to a server-side NH account number."""
    for account in await client._accounts():
        act_no = str(account.get("acct_no") or account.get("act_no") or "").strip()
        if act_no and compute_nh_account_key(act_no) == source_key:
            return act_no, mask_nh_account(act_no)
    raise HTTPException(status_code=400, detail={"code": "SCOPE_MISMATCH", "message": "NH source account is unavailable"})


def _nh_mapping_file(username: str) -> Path:
    from app.services.user_manager import get_user_data_dir
    return get_user_data_dir(username) / "nh_account_mapping.json"


def _read_nh_mapping(username: str) -> dict[str, str]:
    path = _nh_mapping_file(username)
    if not path.exists(): return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _assert_nh_mapping_compatible(username: str, source_key: str, destination_id: str) -> bool:
    """Return whether the exact mapping exists; reject a conflicting mapping."""
    existing = _read_nh_mapping(username).get(source_key)
    if existing and existing != destination_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "NH destination mapping conflicts with this import"},
        )
    return existing == destination_id


def _write_nh_mapping(username: str, source_key: str, destination_id: str) -> bool:
    """Persist one non-conflicting mapping atomically; return whether it changed."""
    if _assert_nh_mapping_compatible(username, source_key, destination_id):
        return False
    path = _nh_mapping_file(username)
    mapping = _read_nh_mapping(username)
    mapping[source_key] = destination_id
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return True


def _nh_imported_items_match_destination(
    result: dict[str, Any], current: list[dict[str, Any]], source_key: str, destination_id: str,
) -> bool:
    """Prove every selected item is an existing NH row for this source/destination."""
    items = result.get("items") if isinstance(result, dict) else None
    if not isinstance(items, list) or not items or any(item.get("status") != "ALREADY_IMPORTED" for item in items):
        return False
    records_by_fingerprint = {
        str(record.get("source_fingerprint")): record
        for record in current
        if record.get("source") == "nh" and record.get("source_fingerprint")
    }
    for item in items:
        record = records_by_fingerprint.get(str(item.get("fingerprint") or ""))
        if (
            not record
            or record.get("source") != "nh"
            or str(record.get("source_account_key") or "") != source_key
            or str(record.get("destination_account_id") or "") != destination_id
        ):
            return False
    return True


def _assert_nh_source_records_destination(
    current: list[dict[str, Any]], source_key: str, destination_id: str,
) -> None:
    """Prevent one opaque NH source from silently spanning destinations."""
    conflict = any(
        record.get("source") == "nh"
        and str(record.get("source_account_key") or "") == source_key
        and str(record.get("destination_account_id") or "") != destination_id
        for record in current
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "NH source records belong to a different destination"},
        )


def _read_nh_pnl_records_strict(username: str) -> list[dict[str, Any]]:
    try:
        return read_pnl_records_readonly(username=username)
    except PnlRecordsStorageError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "PNL_STORAGE_INVALID", "message": "Realized P/L storage requires review"},
        ) from exc


app.include_router(nh_realized_router)
globals().update({route.name: route.endpoint for route in nh_realized_router.routes})


def _nh_destination(username: str, account_id: object, source_key: str, act_no: str) -> dict[str, Any]:
    return _require_realized_destination(
        username, "nh", account_id,
        provider_account_identity=act_no,
        mapped_destination_account_id=_read_nh_mapping(username).get(source_key),
    )


# ---------------------------------------------------------------------------
# KB Securities Domestic Realized Profit Feed API
# ---------------------------------------------------------------------------

def _kb_mapping_file(username: str) -> Path:
    from app.services.user_manager import get_user_data_dir
    return get_user_data_dir(username) / "kb_account_mapping.json"


def _read_kb_mapping(username: str) -> dict[str, str]:
    path = _kb_mapping_file(username)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_INVALID", "message": "KB destination mapping requires review"},
        ) from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_INVALID", "message": "KB destination mapping requires review"},
        )
    return value


def _assert_kb_mapping_compatible(username: str, source_key: str, destination_id: str) -> bool:
    existing = _read_kb_mapping(username).get(source_key)
    if existing and existing != destination_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "KB destination mapping conflicts with this import"},
        )
    return existing == destination_id


def _write_kb_mapping(username: str, source_key: str, destination_id: str) -> bool:
    if _assert_kb_mapping_compatible(username, source_key, destination_id):
        return False
    path = _kb_mapping_file(username)
    mapping = _read_kb_mapping(username)
    mapping[source_key] = destination_id
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return True


def _kb_destination(username: str, account_id: object, source_key: str) -> dict[str, Any]:
    return _require_realized_destination(
        username, "kb", account_id,
        mapped_destination_account_id=_read_kb_mapping(username).get(source_key),
    )


def _read_kb_pnl_records_strict(username: str) -> list[dict[str, Any]]:
    try:
        return read_pnl_records_readonly(username=username)
    except PnlRecordsStorageError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "PNL_STORAGE_INVALID", "message": "Realized P/L storage requires review"},
        ) from exc


def _assert_kb_source_records_destination(
    current: list[dict[str, Any]], source_key: str, destination_id: str,
) -> None:
    if any(
        record.get("source") == "kb"
        and str(record.get("source_account_key") or "") == source_key
        and str(record.get("destination_account_id") or "") != destination_id
        for record in current
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "KB source records belong to a different destination"},
        )


def _kb_imported_items_match_destination(
    result: dict[str, Any], current: list[dict[str, Any]], source_key: str, destination_id: str,
) -> bool:
    items = result.get("items") if isinstance(result, dict) else None
    if not isinstance(items, list) or not items or any(item.get("status") != "ALREADY_IMPORTED" for item in items):
        return False
    records_by_fingerprint = {
        str(record.get("source_fingerprint")): record
        for record in current
        if record.get("source") == "kb" and record.get("source_fingerprint")
    }
    for item in items:
        record = records_by_fingerprint.get(str(item.get("fingerprint") or ""))
        if (
            not record
            or str(record.get("source_account_key") or "") != source_key
            or str(record.get("destination_account_id") or "") != destination_id
        ):
            return False
    return True


def _verify_kb_source_context(client: KBOpenAPI, source_key: str) -> tuple[str, str]:
    try:
        current_key, label = client.get_realized_source_account_state()
    except KBOpenAPIError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "KB_NOT_READY", "message": "KB realized account configuration is unavailable"},
        ) from exc
    if not source_key or current_key != source_key:
        raise HTTPException(
            status_code=400,
            detail={"code": "SCOPE_MISMATCH", "message": "KB source account changed"},
        )
    return current_key, label


app.include_router(kb_realized_router)
globals().update({route.name: route.endpoint for route in kb_realized_router.routes})


# ---------------------------------------------------------------------------
# Kiwoom Realized Profit Feed API
# ---------------------------------------------------------------------------

def _kiwoom_mapping_file(username: str) -> Path:
    from app.services.user_manager import get_user_data_dir
    return get_user_data_dir(username) / "kiwoom_account_mapping.json"


def _read_kiwoom_mapping(username: str) -> dict[str, str]:
    path = _kiwoom_mapping_file(username)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_INVALID", "message": "Kiwoom destination mapping requires review"},
        ) from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_INVALID", "message": "Kiwoom destination mapping requires review"},
        )
    return value


def _assert_kiwoom_mapping_compatible(username: str, source_key: str, destination_id: str) -> bool:
    existing = _read_kiwoom_mapping(username).get(source_key)
    if existing and existing != destination_id:
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "Kiwoom destination mapping conflicts with this import"},
        )
    return existing == destination_id


def _write_kiwoom_mapping(username: str, source_key: str, destination_id: str) -> bool:
    if _assert_kiwoom_mapping_compatible(username, source_key, destination_id):
        return False
    path = _kiwoom_mapping_file(username)
    mapping = _read_kiwoom_mapping(username)
    mapping[source_key] = destination_id
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return True


def _kiwoom_destination(username: str, account_id: object, source_key: str, acct_no: str) -> dict[str, Any]:
    return _require_realized_destination(
        username, "kiwoom", account_id,
        provider_account_identity=acct_no,
        mapped_destination_account_id=_read_kiwoom_mapping(username).get(source_key),
    )


def _read_kiwoom_pnl_records_strict(username: str) -> list[dict[str, Any]]:
    try:
        return read_pnl_records_readonly(username=username)
    except PnlRecordsStorageError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "PNL_STORAGE_INVALID", "message": "Realized P/L storage requires review"},
        ) from exc


def _assert_kiwoom_source_records_destination(
    current: list[dict[str, Any]], source_key: str, destination_id: str,
) -> None:
    if any(
        record.get("source") == "kiwoom"
        and str(record.get("source_account_key") or "") == source_key
        and str(record.get("destination_account_id") or "") != destination_id
        for record in current
    ):
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_MAPPING_CONFLICT", "message": "Kiwoom source records belong to a different destination"},
        )


def _kiwoom_imported_items_match_destination(
    result: dict[str, Any], current: list[dict[str, Any]], source_key: str, destination_id: str,
) -> bool:
    items = result.get("items") if isinstance(result, dict) else None
    if not isinstance(items, list) or not items or any(item.get("status") != "ALREADY_IMPORTED" for item in items):
        return False
    records_by_fingerprint = {
        str(record.get("source_fingerprint")): record
        for record in current
        if record.get("source") == "kiwoom" and record.get("source_fingerprint")
    }
    for item in items:
        record = records_by_fingerprint.get(str(item.get("fingerprint") or ""))
        if (
            not record
            or str(record.get("source_account_key") or "") != source_key
            or str(record.get("destination_account_id") or "") != destination_id
        ):
            return False
    return True


async def _verify_kiwoom_source_context(
    client: KiwoomOpenAPI, source_key: str,
) -> tuple[str, str, str]:
    try:
        account_no, current_key, label = await client.get_realized_source_account_context()
    except KiwoomOpenAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "KIWOOM_API_ERROR", "message": "Kiwoom source account unavailable"},
        ) from exc
    if not source_key or current_key != source_key:
        raise HTTPException(
            status_code=400,
            detail={"code": "SCOPE_MISMATCH", "message": "Kiwoom source account changed"},
        )
    return account_no, current_key, label


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


@app.get("/api/market-overview")
async def market_overview() -> dict:
    try:
        return await fetch_market_overview()
    except Exception:
        from app.services.market_indicators import unavailable_market_indicators
        return {"markets": [], "exchange_rate": None, "unavailable": True, **unavailable_market_indicators()}


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


@app.post("/api/import-accounts")
async def import_accounts(request: Request, file: UploadFile = File(...)) -> dict:
    if Path(file.filename or "").suffix.lower() not in {".csv", ".xlsx", ".xlsm"}:
        raise HTTPException(400, "CSV 또는 XLSX 파일만 가져올 수 있습니다.")
    username = get_current_username(request)
    data = read_portfolio(username=username)
    result = import_account_rows(file.filename or "accounts.csv", await file.read(), username=username, allowed_owners=set(get_family_members(data)))
    result["message"] = f"증권계좌 {result['created']}개를 추가했습니다."
    return result



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
    from app.services.backup_restore import MAX_BACKUP_UPLOAD_BYTES, restore_general_data
    from app.services.user_openapi import save_user_openapi_config

    username = get_current_username(request)
    try:
        raw = await file.read(MAX_BACKUP_UPLOAD_BYTES + 1)
        if len(raw) > MAX_BACKUP_UPLOAD_BYTES:
            raise HTTPException(413, "백업 파일 크기 제한을 초과했습니다.")
        bundle = json.loads(raw.decode("utf-8"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"JSON 파싱 실패: {exc}") from exc

    if not isinstance(bundle, dict):
        raise HTTPException(400, "유효한 백업 파일이 아닙니다.")
    if "portfolio" not in bundle and "asset_records" not in bundle and "ledger" not in bundle:
        raise HTTPException(400, "유효한 백업 파일이 아닙니다.")

    expected_sections = {
        "portfolio": dict,
        "asset_records": dict,
        "dividend_records": list,
        "realized_pnl_records": list,
        "ledger": dict,
    }
    for section, expected_type in expected_sections.items():
        value = bundle.get(section)
        if value and (not isinstance(value, expected_type) or (expected_type is list and not all(isinstance(item, dict) for item in value))):
            raise HTTPException(400, "유효한 백업 파일이 아닙니다.")

    msgs = restore_general_data(username, bundle)
    # Current general_data_only exports never carry credentials. Preserve the
    # legacy config restore path only for older backups without that policy.
    if bundle.get("backup_policy") != "general_data_only" and "openapi_config" in bundle and isinstance(bundle["openapi_config"], dict):
        try:
            save_user_openapi_config(username=username, update_data=bundle["openapi_config"])
            msgs.append("OpenAPI설정")
        except Exception as e:
            logger.warning("OpenAPI config restore warning: %s", e)

    return {"message": f"{', '.join(msgs)} 데이터를 복원했습니다."}

@app.post("/api/demo")
async def load_demo(request: Request) -> dict:
    username = get_current_username(request)
    seed_demo(username=username)
    return {"message": "예시 데이터를 불러왔습니다."}


@app.post("/api/clear")
async def clear_all(request: Request) -> dict:
    username = get_current_username(request)
    with financial_user_locks(username, 'portfolio.json'):
        data = read_portfolio(username=username)
        data["holdings"] = []
        data["accounts"] = []
        write_portfolio(data, username=username)
        return {"message": "저장된 보유내역을 모두 지웠습니다."}


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


def _resolve_kb_sync_account(data: dict):
    # 1. 고유 키(kb_primary) 또는 기존 KB 동기화 계좌 찾기
    primary_matches = [a for a in data["accounts"] if a.get("broker") == "KB증권" and a.get("account_key") == "kb_primary"]
    if len(primary_matches) > 1:
        return None, False
    existing = primary_matches[0] if primary_matches else None
    if not existing:
        source_matches = [a for a in data["accounts"] if a.get("broker") == "KB증권" and a.get("source") == "kb_api"]
        if len(source_matches) > 1:
            return None, False
        existing = source_matches[0] if source_matches else None
    if not existing:
        name_matches = [a for a in data["accounts"] if a.get("broker") == "KB증권" and ("KB" in a.get("name", "") or a.get("name") == "KB OpenAPI 동기화 계좌")]
        if len(name_matches) > 1:
            return None, False
        existing = name_matches[0] if name_matches else None

    return existing, True


async def sync_kb_for_user(username: str, *, retry_transient: bool = False) -> dict:
    """Retry only read-only holdings fetches, opted in by account pre-sync.

    All authority checks and persistence remain outside the retry loop. The
    sync-all user lock remains held across both fetches and their short delay.
    """
    client = KBOpenAPI(username=username)
    if not client.configured:
        return {"broker": "KB증권", "status": "CONFIG_REQUIRED", "message": "KB증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True, "warnings": []}
    try:
        records, retry_info = await fetch_account_holdings(client, "KB", retry_transient=retry_transient)
    except Exception as exc:
        diagnostic = get_failure_diagnostic(exc)
        failure = HTTPException(400, diagnostic.get("failure_reason", "KB_FETCH_INTERNAL_ERROR"))
        failure.kb_sync_diagnostic = diagnostic
        raise failure from exc

    def unverified_result() -> dict:
        result = _unverified_holdings_response("KB증권", records)
        if retry_info:
            result.update({**retry_info, "retry_recovered": False})
        return result

    if not isinstance(records, BrokerHoldingsResult) or not records.authoritative:
        return unverified_result()
    # Preserve scope validation before optional quote reads; revalidate the
    # latest account again inside the commit after those asynchronous reads.
    preview = _load_account_sync(username)
    existing, verified = _resolve_kb_sync_account(preview)
    if not verified or resolve_scopes(records.scopes, {"kb_primary": ("preview", "KB")}) is None:
        return unverified_result()
    holdings = [normalize_holding(record, existing["id"] if existing else "",
                                 "KB증권", existing["name"] if existing else "", "kb_api")
                for record in records]
    prices, warnings = await client.refresh_prices(holdings)
    with financial_user_locks(username, 'portfolio.json'):
        data = _load_account_sync(username)

        existing, verified = _resolve_kb_sync_account(data)
        if not verified:
            return unverified_result()

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

        for holding in holdings:
            holding["account_id"] = account_id
            holding["account_name"] = account_name
        scopes = resolve_scopes(records.scopes, {"kb_primary": (account_id, account_name)})
        if scopes is None:
            return unverified_result()
        for holding in holdings:
            price = prices.get(holding["id"])
            if price:
                holding["current_price"] = price
                if holding["avg_price"] == 0:
                    holding["avg_price"] = price
        replace_holdings_in_scopes(data, holdings, source="kb_api", scopes=scopes)
        _mark_sync_success(data, "kb")
        _save_account_sync(data, username)
        status = _holdings_success_status(records)
        message = "KB증권 보유종목이 0개로 확인되었습니다." if not holdings else f"KB증권 보유종목 {len(holdings)}개를 동기화했습니다."
        return {"broker": "KB증권", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": False, "cash_updated": False, "data_preserved": False, "warnings": warnings[:10], **retry_info}


from app.routers.broker_sync import create_broker_sync_routers

broker_sync_router, all_accounts_sync_router = create_broker_sync_routers(sys.modules[__name__])
app.include_router(broker_sync_router)
globals().update({route.name: route.endpoint for route in broker_sync_router.routes})



async def sync_toss_for_user(username: str, *, retry_transient: bool = False) -> dict:
    client = TossOpenAPI(username=username)
    if not client.configured:
        return {"broker": "토스증권", "status": "CONFIG_REQUIRED", "message": "토스증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    try:
        records, retry_info = await fetch_account_holdings(client, "TOSS", retry_transient=retry_transient)
        toss_accounts = client.last_accounts
    except TossOpenAPIError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not isinstance(records, BrokerHoldingsResult) or not records.authoritative:
        return _unverified_holdings_response("토스증권", records)
    def resolve_toss_account(data_accounts, seq, acct_no, default_name):
        seq_str = str(seq) if seq is not None else ""
        suffix = str(acct_no)[-4:] if acct_no else ""
        broker_accounts = [
            a for a in data_accounts
            if canonical_broker_account_identity(a.get("broker"))
            == canonical_broker_account_identity("토스증권")
        ]
        exact = [a for a in broker_accounts if seq_str and a.get("account_key") == seq_str]
        if len(exact) == 1:
            return exact[0], True
        if len(exact) > 1:
            return None, False
        # Toss deliberately stores only the last four digits for API-created
        # accounts.  A manually entered full number can still be reconciled
        # safely when exactly one account shares that suffix; ambiguity is
        # deliberately left unverified rather than guessing an account.
        suffix_matches = [
            a for a in broker_accounts
            if suffix and normalize_broker_account_no(a.get("account_no")).endswith(suffix)
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0], True
        if len(suffix_matches) > 1:
            return None, False
        name_matches = [
            a for a in broker_accounts
            if (suffix and suffix in a.get("name", "")) or a.get("name") == default_name
        ]
        if len(name_matches) == 1:
            return name_matches[0], True
        return None, True

    preview = _load_account_sync(username)
    for account in toss_accounts:
        seq = account.get("accountSeq")
        account_no = str(account.get("accountNo", ""))
        suffix = account_no[-4:] if account_no else ""
        default_name = f"토스증권 계좌 {suffix}" if suffix else (f"토스증권 계좌 {seq}" if seq is not None else "토스증권")
        _, verified = resolve_toss_account(preview["accounts"], seq, account_no, default_name)
        if not verified:
            return _unverified_holdings_response("토스증권", records)
    buying_power = {}
    cash_failures = 0
    for account in toss_accounts:
        seq = account.get("accountSeq")
        if seq is not None:
            try:
                bp, cash_retry = await read_account_with_retry(
                    lambda: client.get_buying_power(int(seq)), "TOSS", retry_transient=retry_transient,
                )
                if cash_retry:
                    retry_info.update(cash_retry)
                buying_power[str(seq)] = bp
            except TossOpenAPIError as exc:
                diagnostic = get_failure_diagnostic(exc)
                retry_info.update({key: diagnostic[key] for key in ("failure_reason", "retryable")
                                   if key in diagnostic})
                if diagnostic.get("retry_attempted"):
                    retry_info.update({key: diagnostic[key] for key in
                                       ("retry_attempted", "retry_recovered", "initial_failure_reason")})
                cash_failures += 1
    with financial_user_locks(username, 'portfolio.json'):
        data = _load_account_sync(username)
        cash = data["settings"].setdefault("toss_cash", {})
        cash_balances = data["settings"].setdefault("cash_balances", {})

        toss_map = {}
        cash_successes = 0
        for account in toss_accounts:
            seq = account.get("accountSeq")
            seq_str = str(seq) if seq is not None else ""
            account_no = str(account.get("accountNo", ""))
            suffix = account_no[-4:] if account_no else ""
            account_name_default = f"토스증권 계좌 {suffix}" if suffix else (f"토스증권 계좌 {seq}" if seq is not None else "토스증권")

            existing, account_scope_verified = resolve_toss_account(data["accounts"], seq, account_no, account_name_default)
            if not account_scope_verified:
                return _unverified_holdings_response("토스증권", records)
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
            if seq_str in buying_power:
                bp = buying_power[seq_str]
                cash[str(seq)] = bp
                cash_balances[account_id] = bp
                cash_successes += 1

        data["settings"]["toss_cash"] = cash
        data["settings"]["cash_balances"] = cash_balances
        holdings = []
        for record in records:
            acct_key = str(record.get("account_key", ""))
            if acct_key in toss_map:
                account_id, account_name = toss_map[acct_key]
            else:
                return _unverified_holdings_response("토스증권", records)
            holdings.append(normalize_holding(record, account_id, "토스증권", account_name, "toss_api"))

        scopes = resolve_scopes(records.scopes, toss_map)
        if scopes is None:
            return _unverified_holdings_response("토스증권", records)
        replace_holdings_in_scopes(data, holdings, source="toss_api", scopes=scopes)
        _mark_sync_success(data, "toss")
        _save_account_sync(data, username)
        status = "PARTIAL_SUCCESS" if cash_failures else _holdings_success_status(records)
        message = "토스증권 보유종목이 0개로 확인되었습니다." if not holdings else f"토스증권 보유종목 {len(holdings)}개를 동기화했습니다."
        message += " 예수금 조회 실패 계좌의 기존 데이터는 유지했습니다." if cash_failures else " 예수금도 동기화했습니다."
        return {"broker": "토스증권", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": not cash_failures, "cash_updated": bool(cash_successes), "data_preserved": bool(cash_failures), **retry_info}



async def sync_namoo_for_user(username: str, *, retry_transient: bool = False) -> dict:
    client = NhPlugOpenAPI(username=username)
    if not client.configured:
        return {"broker": "NH투자증권(나무)", "status": "CONFIG_REQUIRED", "message": "나무증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    try:
        records, retry_info = await fetch_account_holdings(client, "NH", retry_transient=retry_transient)
    except NhPlugOpenAPIError as exc:
        detail = str(exc)
        if isinstance(exc, NhPlugRateLimitError) or "IGW42903" in detail or "거래건수를 초과" in detail:
            detail = "나무증권 API 호출 한도를 초과했습니다(IGW42903). 잠시 후 다시 시도해 주세요. 기존 데이터는 유지했습니다."
        raise HTTPException(429 if isinstance(exc, NhPlugRateLimitError) or "IGW42903" in str(exc) else 400, detail) from exc
    if not isinstance(records, BrokerHoldingsResult) or not records.authoritative:
        return _unverified_holdings_response("NH투자증권(나무)", records)
    with financial_user_locks(username, 'portfolio.json'):
        data = _load_account_sync(username)
        cash_balances = data["settings"].setdefault("cash_balances", {})

        def resolve_namoo_account(data_accounts, acct_no, default_name):
            suffix = str(acct_no)[-4:] if acct_no else ""
            broker_accounts = [
                a for a in data_accounts
                if canonical_broker_account_identity(a.get("broker"))
                == canonical_broker_account_identity("NH투자증권(나무)")
            ]
            exact = [a for a in broker_accounts if normalize_broker_account_no(a.get("account_no")) == normalize_broker_account_no(acct_no)]
            if len(exact) == 1:
                return exact[0], True
            if len(exact) > 1:
                return None, False
            suffix_matches = [a for a in broker_accounts if suffix and a.get("account_key") == suffix]
            if len(suffix_matches) == 1:
                return suffix_matches[0], True
            if len(suffix_matches) > 1:
                return None, False
            name_matches = [
                a for a in broker_accounts
                if (suffix and suffix in a.get("name", "")) or a.get("name") == default_name
            ]
            if len(name_matches) == 1:
                return name_matches[0], True
            return None, True

        account_map = {}  # acct_no -> (account_id, account_name)
        for account in client.last_accounts:
            account_no = str(account.get("acct_no", ""))
            default_name = client._account_name(account)
            suffix = account_no[-4:] if account_no else ""
            if account_no:
                existing, account_scope_verified = resolve_namoo_account(data["accounts"], account_no, default_name)
                if not account_scope_verified:
                    return _unverified_holdings_response("NH투자증권(나무)", records)
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
                return _unverified_holdings_response("NH투자증권(나무)", records)
            holdings.append(normalize_holding(record, account_id, "NH투자증권(나무)", account_name, "nhplug_api"))

        scopes = resolve_scopes(records.scopes, account_map)
        if scopes is None:
            return _unverified_holdings_response("NH투자증권(나무)", records)
        replace_holdings_in_scopes(data, holdings, source="nhplug_api", scopes=scopes)
        data["settings"]["cash_balances"] = cash_balances
        _mark_sync_success(data, "nh")
        _save_account_sync(data, username)
        status = _holdings_success_status(records)
        message = "나무증권 보유종목이 0개로 확인되어 예수금만 동기화했습니다." if not holdings else f"나무증권 보유종목 {len(holdings)}개 및 예수금을 동기화했습니다."
        return {"broker": "NH투자증권(나무)", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": True, "cash_updated": True, "data_preserved": False, **retry_info}



async def sync_kis_for_user(username: str, *, retry_transient: bool = False) -> dict:
    client = KISOpenAPI(username=username)
    if not client.configured:
        return {"broker": "한국투자증권", "status": "CONFIG_REQUIRED", "message": "한국투자증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    if not client._parse_account_no()[0]:
        return {"broker": "한국투자증권", "status": "CONFIG_REQUIRED", "message": "한국투자증권 계좌번호(CANO 8자리 또는 8자리-상품코드 2자리)를 확인해 주세요. 기존 데이터는 유지했습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    try:
        records, retry_info = await fetch_account_holdings(client, "KIS", retry_transient=retry_transient)
    except KISOpenAPIError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not isinstance(records, BrokerHoldingsResult) or not records.authoritative:
        return _unverified_holdings_response("한국투자증권", records)
    with financial_user_locks(username, 'portfolio.json'):
        data = _load_account_sync(username)
        cash_balances = data["settings"].setdefault("cash_balances", {})

        def resolve_kis_account(data_accounts, acct_no, default_name):
            suffix = str(acct_no)[-4:] if acct_no else ""
            broker_accounts = [
                a for a in data_accounts
                if canonical_broker_account_identity(a.get("broker"))
                == canonical_broker_account_identity("한국투자증권")
            ]
            exact = [a for a in broker_accounts if normalize_broker_account_no(a.get("account_no")) == normalize_broker_account_no(acct_no)]
            if len(exact) == 1:
                return exact[0], True
            if len(exact) > 1:
                return None, False
            suffix_matches = [a for a in broker_accounts if suffix and a.get("account_key") == suffix]
            if len(suffix_matches) == 1:
                return suffix_matches[0], True
            if len(suffix_matches) > 1:
                return None, False
            name_matches = [
                a for a in broker_accounts
                if (suffix and suffix in a.get("name", "")) or a.get("name") == default_name
            ]
            if len(name_matches) == 1:
                return name_matches[0], True
            return None, True

        account_map = {}
        for account in client.last_accounts:
            account_no = str(account.get("account_number", ""))
            default_name = account.get("account_name", f"한국투자증권 ({account_no[:4]}****)")
            suffix = account_no[-4:] if account_no else ""
            if account_no:
                existing, account_scope_verified = resolve_kis_account(data["accounts"], account_no, default_name)
                if not account_scope_verified:
                    return _unverified_holdings_response("한국투자증권", records)
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
                return _unverified_holdings_response("한국투자증권", records)
            holdings.append(normalize_holding(record, account_id, "한국투자증권", account_name, "kis_api"))

        scopes = resolve_scopes(records.scopes, account_map)
        if scopes is None:
            return _unverified_holdings_response("한국투자증권", records)
        replace_holdings_in_scopes(data, holdings, source="kis_api", scopes=scopes)
        data["settings"]["cash_balances"] = cash_balances
        _mark_sync_success(data, "kis")
        _save_account_sync(data, username)
        status = _holdings_success_status(records)
        message = "한국투자증권 보유종목이 0개로 확인되어 예수금만 동기화했습니다." if not holdings else f"한국투자증권 보유종목 {len(holdings)}개 및 예수금을 동기화했습니다."
        return {"broker": "한국투자증권", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": True, "cash_updated": True, "data_preserved": False, **retry_info}



async def sync_kiwoom_for_user(username: str, *, retry_transient: bool = False) -> dict:
    client = KiwoomOpenAPI(username=username)
    if not client.configured:
        return {"broker": "키움증권", "status": "CONFIG_REQUIRED", "message": "키움증권 OpenAPI 키가 설정되지 않았습니다.", "count": 0, "holdings_valid": False, "cash_valid": False, "data_preserved": True}
    try:
        records, retry_info = await fetch_account_holdings(client, "KIWOOM", retry_transient=retry_transient)
    except KiwoomOpenAPIError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not isinstance(records, BrokerHoldingsResult) or not records.authoritative:
        return _unverified_holdings_response("키움증권", records)
    with financial_user_locks(username, 'portfolio.json'):
        data = _load_account_sync(username)
        cash_balances = data["settings"].setdefault("cash_balances", {})

        def resolve_kiwoom_account(data_accounts, acct_no, default_name):
            suffix = str(acct_no)[-4:] if acct_no else ""
            broker_accounts = [
                a for a in data_accounts
                if canonical_broker_account_identity(a.get("broker"))
                == canonical_broker_account_identity("키움증권")
            ]
            exact = [a for a in broker_accounts if normalize_broker_account_no(a.get("account_no")) == normalize_broker_account_no(acct_no)]
            if len(exact) == 1:
                return exact[0], True
            if len(exact) > 1:
                return None, False
            suffix_matches = [a for a in broker_accounts if suffix and a.get("account_key") == suffix]
            if len(suffix_matches) == 1:
                return suffix_matches[0], True
            if len(suffix_matches) > 1:
                return None, False
            name_matches = [
                a for a in broker_accounts
                if (suffix and suffix in a.get("name", "")) or a.get("name") == default_name
            ]
            if len(name_matches) == 1:
                return name_matches[0], True
            return None, True

        account_map = {}
        for account in client.last_accounts:
            account_no = str(account.get("account_number", ""))
            default_name = account.get("account_name", f"키움증권 ({account_no[:4]}****)")
            suffix = account_no[-4:] if account_no else ""
            if account_no:
                existing, account_scope_verified = resolve_kiwoom_account(data["accounts"], account_no, default_name)
                if not account_scope_verified:
                    return _unverified_holdings_response("키움증권", records)
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
                return _unverified_holdings_response("키움증권", records)
            holdings.append(normalize_holding(record, account_id, "키움증권", account_name, "kiwoom_api"))

        scopes = resolve_scopes(records.scopes, account_map)
        if scopes is None:
            return _unverified_holdings_response("키움증권", records)
        replace_holdings_in_scopes(data, holdings, source="kiwoom_api", scopes=scopes)
        data["settings"]["cash_balances"] = cash_balances
        _mark_sync_success(data, "kiwoom")
        _save_account_sync(data, username)
        status = _holdings_success_status(records)
        message = "키움증권 국내 보유종목이 0개로 확인되어 KRW 예수금만 동기화했습니다." if not holdings else f"키움증권 국내 보유종목 {len(holdings)}개 및 KRW 예수금을 동기화했습니다."
        return {"broker": "키움증권", "status": status, "message": message, "count": len(holdings), "holdings_valid": True, "holdings_state": records.state.value, "cash_valid": True, "cash_updated": True, "data_preserved": False, **retry_info}



@app.post("/api/fx/refresh")
async def refresh_fx_rate(request: Request) -> dict:
    username = get_current_username(request)
    rate = await fetch_fx_rate_usd_krw()
    with financial_user_locks(username, 'portfolio.json'):
        data = read_portfolio(username=username)
        data["settings"]["fx_rates"]["USD"] = rate
        now_str = datetime.now().astimezone().isoformat(timespec="seconds")
        data["settings"]["fx_info"] = {"source": "실시간 웹 환율", "rate": rate, "updated_at": now_str}
        data["settings"]["fx_updated_at"] = now_str
        write_portfolio(data, username=username)
        return {"message": f"실시간 환율(USD/KRW: {rate:,.1f}원)을 반영했습니다.", "rate": rate}


async def refresh_prices_for_user(username: str) -> dict:
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
            with financial_user_locks(username, 'portfolio.json'):
                data = read_portfolio(username=username)
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

    with financial_user_locks(username, 'portfolio.json'):
        data = read_portfolio(username=username)
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
        session_obs = res.get("session_obs", {})
        if session_obs:
            stored_obs = data["settings"].setdefault("price_session_obs", {})
            merge_price_session_obs(stored_obs, session_obs)

        session_dates = res.get("session_dates", {})
        if session_dates:
            stored_dates = data["settings"].setdefault("price_session_dates", {})
            for code, inc_date in session_dates.items():
                inc_norm = normalize_session_date(inc_date)
                if not inc_norm:
                    continue
                cur_date = normalize_session_date(stored_dates.get(code))
                if cur_date and inc_norm < cur_date:
                    continue
                stored_dates[code] = inc_date
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


@app.post("/api/refresh-prices")
async def refresh_prices(request: Request) -> dict:
    username = get_current_username(request)
    return await refresh_prices_for_user(username=username)

@app.get("/api/stock-chart/{code}")
async def get_stock_chart(code: str, period: str = "1M") -> dict:
    return await fetch_stock_chart_data(code, period)


@app.get("/api/stock-search")
async def stock_search(q: str = "") -> dict:
    from app.services.stock_master import async_search_stock_by_name
    return await async_search_stock_by_name(q)


async def sync_all_accounts_for_user(
    username: str, *, retry_kb_transient: bool = False,
    retry_account_transient: bool = False, provider_observer=None, sync_clock=None,
) -> dict:
    sync_clock = sync_clock or (lambda: datetime.now().astimezone())
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
            ("KB증권", KBOpenAPI(username=username), "sync_kb", sync_kb_for_user),
            ("토스증권", TossOpenAPI(username=username), "sync_toss", sync_toss_for_user),
            ("NH투자증권(나무)", NhPlugOpenAPI(username=username), "sync_namoo", sync_namoo_for_user),
            ("한국투자증권", KISOpenAPI(username=username), "sync_kis", sync_kis_for_user),
            ("키움증권", KiwoomOpenAPI(username=username), "sync_kiwoom", sync_kiwoom_for_user),
        ]
        for label, client, route_name, user_fn in jobs:
            started_at = sync_clock() if provider_observer else None
            if not client.configured:
                broker_results.append({
                    "broker": label, "status": "CONFIG_REQUIRED", "count": 0,
                    "holdings_valid": False, "cash_valid": False, "data_preserved": True,
                    "message": "OpenAPI 연결 정보가 필요합니다. 기존 데이터는 유지했습니다.",
                })
                if provider_observer:
                    provider_observer(broker_results[-1], started_at, sync_clock())
                continue
            try:
                route_attr = globals().get(route_name)
                if route_attr is not None and type(route_attr).__module__.startswith("unittest.mock"):
                    try:
                        broker_results.append(await route_attr(username=username))
                    except TypeError:
                        broker_results.append(await route_attr())
                else:
                    if retry_account_transient or (label == "KB증권" and retry_kb_transient):
                        broker_results.append(await user_fn(username=username, retry_transient=True))
                    else:
                        broker_results.append(await user_fn(username=username))
            except Exception as exc:
                diagnostic = get_failure_diagnostic(exc) or (getattr(exc, "kb_sync_diagnostic", {}) if label == "KB증권" else {})
                status = diagnostic.get("status") or _sync_error_status(exc)
                # KB diagnostics are allowlisted categories, never raw provider bodies/credentials.
                message = (diagnostic.get("failure_reason", "KB_SYNC_FAILED") if diagnostic or label == "KB증권"
                           else "ACCOUNT_SYNC_PERSISTENCE_FAILED" if isinstance(exc, AccountSyncPersistenceError)
                           else _mask_sync_error(exc, client))
                broker_results.append({
                    "broker": label, "status": status, "count": 0,
                    "holdings_valid": False, "cash_valid": False, "data_preserved": True,
                    "message": f"{message} 기존 데이터는 유지했습니다.",
                    **diagnostic,
                })
            if provider_observer:
                provider_observer(broker_results[-1], started_at, sync_clock())
    finally:
        _syncing_users.discard(username)

    successful_statuses = {"SUCCESS", "CONFIRMED_EMPTY", "PARTIAL_SUCCESS"}
    succeeded = [r for r in broker_results if r["status"] in successful_statuses]
    errors = [f"{r['broker']}: {r['message']}" for r in broker_results if r["status"] not in successful_statuses | {"CONFIG_REQUIRED"}]
    lines = [f"{r['broker']} [{r['status']}] {r['message']}" for r in broker_results]
    return {"message": " / ".join(lines), "synced": len(succeeded), "errors": errors, "brokers": broker_results}


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


ACTION_LANDING_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="referrer" content="no-referrer" />
<title>{{page_title}} - Wealth Action</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:radial-gradient(ellipse at 50% 20%, #15102a 0%, #060913 70%); color:#e0e6f5;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .card { width:100%; max-width:440px; padding:32px 28px; border-radius:16px; box-sizing:border-box;
          background:rgba(14,21,41,0.96); border:1px solid #3d2c73;
          box-shadow:0 20px 50px rgba(0,0,0,0.7), 0 0 0 1px rgba(157,123,255,0.2); backdrop-filter:blur(10px); }
  .brand-wrap { display:flex; align-items:center; gap:12px; margin-bottom:20px; }
  .brand-icon { width:36px; height:36px; border-radius:10px; background:linear-gradient(135deg,#9d7bff,#5d3ad4);
                display:flex; align-items:center; justify-content:center; font-weight:800; font-size:18px; color:#fff; }
  h1 { font-size:20px; font-weight:800; margin:0; color:#f3f5ff; }
  .desc { font-size:14px; color:#91a0c1; line-height:1.5; margin:0 0 20px; }
  .info-box { background:#080e1e; border:1px solid #222d48; border-radius:10px; padding:16px; margin-bottom:24px; }
  .info-row { display:flex; justify-content:space-between; margin-bottom:8px; font-size:13.5px; }
  .info-row:last-child { margin-bottom:0; }
  .info-label { color:#7e8ea8; }
  .info-value { color:#f3f5ff; font-weight:600; }
  .status-badge { display:inline-block; padding:3px 8px; border-radius:6px; font-size:12px; font-weight:700; }
  .badge-pending { background:rgba(157,123,255,0.18); color:#c4b5fd; border:1px solid rgba(157,123,255,0.3); }
  .badge-done { background:rgba(34,197,94,0.18); color:#86efac; border:1px solid rgba(34,197,94,0.3); }
  .badge-error { background:rgba(239,68,68,0.18); color:#fca5a5; border:1px solid rgba(239,68,68,0.3); }
  button { width:100%; padding:13px; border:none; border-radius:10px;
           background:linear-gradient(135deg,#8e70fa,#5d3ad4); color:white; font-size:15px; font-weight:700; cursor:pointer;
           box-shadow:0 6px 18px rgba(93,58,212,0.4); transition:.18s; }
  button:hover { filter:brightness(1.12); transform:translateY(-1px); }
  .back-link { display:block; text-align:center; margin-top:16px; font-size:13px; color:#91a0c1; text-decoration:none; }
  .back-link:hover { color:#c4b5fd; }
</style>
</head>
<body>
  <div class="card">
    <div class="brand-wrap">
      <div class="brand-icon">W</div>
      <h1>{{header_title}}</h1>
    </div>
    <p class="desc">{{description}}</p>
    <div class="info-box">
      {{info_rows}}
    </div>
    {{action_content}}
    <a href="/dashboard" class="back-link">대시보드로 돌아가기</a>
  </div>
</body>
</html>"""


def _render_action_card(
    *,
    page_title: str,
    header_title: str,
    description: str,
    info_dict: dict[str, str],
    action_content: str,
    status_code: int = 200,
) -> HTMLResponse:
    info_rows = ""
    for k, v in info_dict.items():
        info_rows += f'<div class="info-row"><span class="info-label">{html.escape(k)}</span><span class="info-value">{html.escape(v)}</span></div>'
    rendered = (
        ACTION_LANDING_HTML
        .replace("{{page_title}}", html.escape(page_title))
        .replace("{{header_title}}", html.escape(header_title))
        .replace("{{description}}", html.escape(description))
        .replace("{{info_rows}}", info_rows)
        .replace("{{action_content}}", action_content)
    )
    return HTMLResponse(
        content=rendered,
        status_code=status_code,
        headers={"Referrer-Policy": "no-referrer"},
    )


def _validate_same_origin_request(request: Request) -> bool:
    """Strict same-origin CSRF validation against configured public_base_url.

    Checks Origin (or Referer as fallback). Both must match configured public_base_url origin.
    Missing Origin AND missing Referer fails closed (returns False).
    """
    from app.services.system_settings import get_effective_system_settings
    settings = get_effective_system_settings()
    base_url = settings.get("public_base_url")
    if not base_url:
        return False

    try:
        base_parts = urlsplit(base_url)
        expected_scheme = base_parts.scheme
        expected_netloc = base_parts.netloc
    except Exception:
        return False

    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    if origin:
        try:
            o_parts = urlsplit(origin)
            return o_parts.scheme == expected_scheme and o_parts.netloc == expected_netloc
        except Exception:
            return False

    if referer:
        try:
            r_parts = urlsplit(referer)
            return r_parts.scheme == expected_scheme and r_parts.netloc == expected_netloc
        except Exception:
            return False

    return False


@app.get("/a/{token}", include_in_schema=False)
async def get_web_action_landing(request: Request, token: str) -> HTMLResponse:
    from app.services.action_v2 import (
        ACTION_TYPE_MARK_IPO_APPLIED,
        ACTION_TYPE_OPEN_IPO_SALE_FLOW,
        get_web_action_metadata,
        is_action_expired,
        validate_action_token,
    )
    from app.services.ipo.applications import get_user_applications
    from app.services.ipo.store import read_market_store_read_only

    try:
        token = validate_action_token(token)
    except Exception:
        return _render_action_card(
            page_title="유효하지 않은 링크",
            header_title="작업 링크 오류",
            description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
            info_dict={"상태": "유효하지 않음"},
            action_content="",
            status_code=404,
        )

    current_user = get_current_username(request)
    action = get_web_action_metadata(token)
    if not action:
        return _render_action_card(
            page_title="유효하지 않은 링크",
            header_title="작업 링크 오류",
            description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
            info_dict={"상태": "유효하지 않음"},
            action_content="",
            status_code=404,
        )

    # Cross-user authorization check: strict username binding
    if action.get("username") != current_user:
        return _render_action_card(
            page_title="접근 제한",
            header_title="접근 권한 없음",
            description="해당 작업에 대한 접근 권한이 없습니다. 올바른 계정으로 로그인해 주세요.",
            info_dict={"요청 계정": current_user},
            action_content="",
            status_code=403,
        )

    action_type = action.get("action_type")
    meta = action.get("metadata", {})
    ipo_id = meta.get("ipo_id")
    owner = meta.get("owner") or "-"

    # Canonical IPO display resolve: authoritative source is read_market_store_read_only()
    ipo_name = "공모주"
    matched_ipo = None
    if ipo_id:
        try:
            market_ipos = read_market_store_read_only().get("ipos", [])
            matched_ipo = next((x for x in market_ipos if x.get("ipo_id") == ipo_id), None)
            if matched_ipo and matched_ipo.get("company_name"):
                ipo_name = matched_ipo["company_name"]
            elif matched_ipo and matched_ipo.get("name"):
                ipo_name = matched_ipo["name"]
        except Exception as exc:
            logger.warning("Failed to resolve canonical IPO company name: %s", type(exc).__name__)

    # Expiration check
    if is_action_expired(action):
        return _render_action_card(
            page_title="만료된 링크",
            header_title="작업 기한 만료",
            description="해당 청약 신청 기한이 이미 만료되었습니다.",
            info_dict={
                "종목명": ipo_name,
                "대상자": owner,
                "상태": "기한 만료",
            },
            action_content="",
            status_code=410,
        )

    # Already consumed check
    if action.get("consumed_at"):
        return _render_action_card(
            page_title="처리 완료된 작업",
            header_title="이미 처리된 작업",
            description="해당 작업은 이미 성공적으로 처리되었습니다.",
            info_dict={
                "종목명": ipo_name,
                "대상자": owner,
                "처리 상태": "완료됨",
            },
            action_content="",
            status_code=200,
        )

    # Check live application state
    apps = get_user_applications(current_user)
    app_record = apps.get("applications", {}).get(ipo_id, {})
    applied_owners = list(app_record.get("applied_owners") or [])
    if action_type == ACTION_TYPE_MARK_IPO_APPLIED and owner in applied_owners:
        return _render_action_card(
            page_title="청약 완료 상태",
            header_title="청약 신청 완료 확인",
            description="해당 대상자는 이미 청약 완료 상태로 등록되어 있습니다.",
            info_dict={
                "종목명": ipo_name,
                "대상자": owner,
                "현재 상태": "청약 완료",
            },
            action_content="",
            status_code=200,
        )

    if action_type == ACTION_TYPE_MARK_IPO_APPLIED:
        action_button = f"""<form method="post" action="/a/{html.escape(token)}/execute">
          <button type="submit">청약 완료 확인 및 상태 변경</button>
        </form>"""
        return _render_action_card(
            page_title="청약 완료 확인",
            header_title="IPO 청약 완료 확인",
            description="아래 정보를 확인하고 청약 완료 처리를 진행해 주세요.",
            info_dict={
                "종목명": ipo_name,
                "신청 대상": owner,
                "현재 상태": "청약 전 (확인 대기)",
            },
            action_content=action_button,
            status_code=200,
        )
    elif action_type == ACTION_TYPE_OPEN_IPO_SALE_FLOW:
        from app.services.ipo.allocation import allocation_summary, sale_candidates
        from app.services.ipo.applications import InvalidApplicationError

        # Metadata contains only opaque authoritative identifiers.  Resolve
        # mutable market facts from the canonical market store on every view.
        stock_code = str((matched_ipo or {}).get("stock_code") or "")
        listing_date = str(
            (matched_ipo or {}).get("actual_listing_date")
            or (matched_ipo or {}).get("expected_listing_date")
            or ""
        )[:10] or None

        # Resolve account mapping before allocation state so that an applied
        # owner with no bound account is distinct from a mapped owner whose
        # allocation quantity has not been recorded yet.
        applicant = (app_record.get("applicants") or {}).get(owner)
        account_resolved = (
            isinstance(applicant, dict)
            and bool(applicant.get("broker_id"))
            and bool(applicant.get("account_id"))
        )
        alloc_status = "UNRESOLVED_ACCOUNT" if not account_resolved else None
        alloc_data = None
        candidates: list[dict] = []
        alloc_error: str | None = None
        if account_resolved:
            try:
                summary = allocation_summary(current_user, ipo_id, owner, stock_code, listing_date)
                alloc_status = summary.get("status")
                alloc_data = summary.get("allocation")
                if alloc_status in ("UNSOLD", "PARTIALLY_SOLD"):
                    candidates = sale_candidates(current_user, ipo_id, owner, stock_code, listing_date)
            except InvalidApplicationError:
                # Canonical application/allocation state is unavailable.  Do
                # not offer a mutation form from an ambiguous state.
                alloc_error = "DATA_UNAVAILABLE"
            except Exception as exc:
                logger.warning(
                    "IPO allocation summary unavailable in GET handler: %s",
                    type(exc).__name__,
                )
                alloc_error = "DATA_UNAVAILABLE"

        def _fmt_qty(n: object) -> str:
            try:
                return f"{int(n):,}주"
            except Exception:
                return "-"

        def _fmt_krw(n: object) -> str:
            try:
                v = int(float(str(n)))
                sign = "+" if v > 0 else ""
                return f"{sign}{v:,}원"
            except Exception:
                return "-"

        if alloc_status == "FULLY_SOLD":
            return _render_action_card(
                page_title="매도 기록 완료",
                header_title="매도 기록 완료",
                description="해당 배정 물량이 전량 매도 처리 완료되었습니다.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "배정수량": _fmt_qty(alloc_data.get("quantity") if alloc_data else None),
                    "상태": "전량 매도 완료",
                },
                action_content="",
                status_code=200,
            )


        if alloc_status == "UNRESOLVED_ACCOUNT":
            return _render_action_card(
                page_title="계좌 연결 필요",
                header_title="청약 계좌 연결 필요",
                description="매도 기록을 연결하려면 먼저 청약 계좌를 연결해 주세요.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "상태": "청약 계좌 연결 필요",
                },
                action_content="",
                status_code=200,
            )

        if alloc_status == "NO_ALLOCATION":
            return _render_action_card(
                page_title="배정 없음",
                header_title="배정 0주",
                description="해당 공모주 청약 결과 배정이 이루어지지 않았습니다.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "배정수량": "0주",
                    "상태": "미배정",
                },
                action_content="",
                status_code=200,
            )

        if alloc_status == "UNRESOLVED":
            return _render_action_card(
                page_title="배정 미기록",
                header_title="배정수량 미기록",
                description="배정수량이 아직 기록되지 않았습니다. Wealth에서 배정수량을 먼저 입력해 주세요.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "상태": "배정수량 미기록",
                },
                action_content="",
                status_code=200,
            )

        if alloc_error:
            return _render_action_card(
                page_title="상태 확인 필요",
                header_title="매도 기록 상태 확인 필요",
                description="현재 배정 및 매도 연결 상태를 안전하게 확인할 수 없습니다. Wealth에서 상태를 확인해 주세요.",
                info_dict={"종목명": ipo_name, "대상자": owner, "상태": "확인 필요"},
                action_content="",
                status_code=409,
            )

        if alloc_status == "LINK_DATA_MISSING":
            return _render_action_card(
                page_title="데이터 확인 필요",
                header_title="매도 연결 데이터 오류",
                description="기존 매도 연결 데이터 확인이 필요합니다. Wealth에서 연결된 실현손익 기록을 확인해 주세요.",
                info_dict={
                    "종목명": ipo_name,
                    "대상자": owner,
                    "배정수량": _fmt_qty(alloc_data.get("quantity") if alloc_data else None),
                    "상태": "LINK_DATA_MISSING",
                },
                action_content="",
                status_code=200,
            )

        # UNSOLD or PARTIALLY_SOLD — show form with candidates
        sold_qty = alloc_data.get("sold_quantity", 0) if alloc_data else 0
        remaining_qty = alloc_data.get("remaining_quantity", 0) if alloc_data else 0
        total_qty = alloc_data.get("quantity", 0) if alloc_data else 0

        if not candidates:
            form_html = (
                "<p style='font-size:13px;color:#91a0c1;text-align:center;margin:0'>"
                "연결 가능한 매도 실현손익 기록이 없습니다.</p>"
            )
        else:
            candidate_options = ""
            for c in candidates:
                pnl_id = html.escape(str(c.get("pnl_record_id", "")))
                date_str = html.escape(str(c.get("date") or "-"))
                avail = c.get("available_quantity", 0)
                pnl_krw = c.get("pnl_krw")
                pnl_label = _fmt_krw(pnl_krw)
                candidate_options += (
                    f'<option value="{pnl_id}" data-avail="{avail}">'
                    f'{date_str} | 가능수량 {avail:,}주 | 실현손익 {pnl_label}'
                    f'</option>\n'
                )
            esc_token = html.escape(token)
            form_html = f"""<form method="post" action="/a/{esc_token}/link-sale" id="lsform"
  style="display:flex;flex-direction:column;gap:12px;margin-top:4px">
  <div>
    <label style="font-size:12px;color:#7e8ea8;display:block;margin-bottom:4px">매도 실현손익 기록 선택</label>
    <select name="pnl_record_id" id="pnl_sel" required
      style="width:100%;padding:10px;border-radius:8px;border:1px solid #3d2c73;
             background:#080e1e;color:#f3f5ff;font-size:13px;box-sizing:border-box">
      <option value="">— 기록 선택 —</option>
      {candidate_options}
    </select>
  </div>
  <div>
    <label style="font-size:12px;color:#7e8ea8;display:block;margin-bottom:4px">
      연결 수량 <span id="avail_hint" style="color:#c4b5fd"></span>
    </label>
    <input name="matched_quantity" id="qty_inp" type="number" min="1" max="{remaining_qty}" required
      placeholder="수량 입력"
      style="width:100%;padding:10px;border-radius:8px;border:1px solid #3d2c73;
             background:#080e1e;color:#f3f5ff;font-size:13px;box-sizing:border-box" />
  </div>
  <button type="submit">매도 기록 연결</button>
</form>
<script>
(function(){{
  var sel=document.getElementById('pnl_sel');
  var inp=document.getElementById('qty_inp');
  var hint=document.getElementById('avail_hint');
  sel.addEventListener('change',function(){{
    var opt=sel.options[sel.selectedIndex];
    var avail=opt.getAttribute('data-avail');
    if(avail){{hint.textContent='(가능 '+parseInt(avail,10).toLocaleString()+'주)';inp.max=avail;inp.value='';}}
    else{{hint.textContent='';inp.max='{remaining_qty}';}}
  }});
}})();
</script>"""

        status_label = "매도 전" if alloc_status == "UNSOLD" else f"일부 매도 ({sold_qty:,}주/{total_qty:,}주)"
        return _render_action_card(
            page_title="매도 기록 연결",
            header_title="IPO 상장일 매도 기록",
            description="아래에서 실현손익 기록을 선택하고 연결 수량을 입력해 주세요.",
            info_dict={
                "종목명": ipo_name,
                "대상자": owner,
                "배정수량": _fmt_qty(total_qty),
                "잔여수량": _fmt_qty(remaining_qty),
                "상태": status_label,
            },
            action_content=form_html,
            status_code=200,
        )
    else:
        return _render_action_card(
            page_title="지원하지 않는 작업",
            header_title="알 수 없는 작업",
            description="지원되지 않는 작업 유형입니다.",
            info_dict={"작업 유형": str(action_type)},
            action_content="",
            status_code=400,
        )


@app.post("/a/{token}/execute", include_in_schema=False)
async def post_web_action_execute(request: Request, token: str) -> HTMLResponse:
    from app.services.action_v2 import execute_web_action, validate_action_token
    from app.services.ipo.actions import IpoActionError

    # 1. CSRF same-origin check
    if not _validate_same_origin_request(request):
        return _render_action_card(
            page_title="접근 제한",
            header_title="요청 검증 실패",
            description="안전하지 않거나 허용되지 않은 출처에서의 요청입니다.",
            info_dict={"오류": "CSRF_FORBIDDEN"},
            action_content="",
            status_code=403,
        )

    # 2. Token format validation
    try:
        token = validate_action_token(token)
    except Exception:
        return _render_action_card(
            page_title="유효하지 않은 링크",
            header_title="작업 링크 오류",
            description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
            info_dict={"상태": "유효하지 않음"},
            action_content="",
            status_code=404,
        )

    current_user = get_current_username(request)
    try:
        result = execute_web_action(token, authenticated_username=current_user)
    except IpoActionError as exc:
        err_msg = str(exc)
        if err_msg == "ACTION_NOT_FOUND":
            return _render_action_card(
                page_title="유효하지 않은 링크",
                header_title="작업 링크 오류",
                description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
                info_dict={"상태": "유효하지 않음"},
                action_content="",
                status_code=404,
            )
        elif err_msg == "FORBIDDEN":
            return _render_action_card(
                page_title="접근 제한",
                header_title="접근 권한 없음",
                description="해당 작업에 대한 접근 권한이 없습니다. 올바른 계정으로 로그인해 주세요.",
                info_dict={"요청 계정": current_user},
                action_content="",
                status_code=403,
            )
        elif err_msg == "ACTION_EXPIRED":
            return _render_action_card(
                page_title="만료된 링크",
                header_title="작업 기한 만료",
                description="해당 청약 신청 기한이 이미 만료되었습니다.",
                info_dict={"상태": "기한 만료"},
                action_content="",
                status_code=410,
            )
        elif err_msg == "ACTION_NOT_EXECUTABLE":
            return _render_action_card(
                page_title="실행 불가",
                header_title="실행할 수 없는 작업",
                description="해당 작업은 현재 웹 액션으로 실행할 수 없습니다.",
                info_dict={"상태": "ACTION_NOT_EXECUTABLE"},
                action_content="",
                status_code=400,
            )
        elif err_msg in (
            "ACTION_ALREADY_RUNNING",
            "ACTION_V2_STATE_INVALID",
            "ACTION_TOKEN_INVALID",
            "SUBSCRIPTION_NOT_ACTIVE",
            "OWNER_NOT_ELIGIBLE",
            "IPO_NOT_FOUND",
        ):
            # Known stable business error codes
            safe_descriptions = {
                "ACTION_ALREADY_RUNNING": "다른 작업이 처리 중입니다. 잠시 후 다시 시도해 주세요.",
                "ACTION_V2_STATE_INVALID": "작업 저장소 상태를 확인할 수 없습니다.",
                "ACTION_TOKEN_INVALID": "유효하지 않은 요청 토큰입니다.",
                "SUBSCRIPTION_NOT_ACTIVE": "청약 진행 기간이 아닙니다.",
                "OWNER_NOT_ELIGIBLE": "해당 청약의 신청 대상자가 아닙니다.",
                "IPO_NOT_FOUND": "대상 공모주 정보를 찾을 수 없습니다.",
            }
            desc = safe_descriptions.get(err_msg, "작업을 처리할 수 없습니다.")
            return _render_action_card(
                page_title="처리 실패",
                header_title="작업 처리 실패",
                description=desc,
                info_dict={"상태": err_msg},
                action_content="",
                status_code=400,
            )
        else:
            logger.warning("Action execution failed with unmapped error: %s", err_msg)
            return _render_action_card(
                page_title="처리 실패",
                header_title="작업 처리 실패",
                description="작업을 처리할 수 없습니다.",
                info_dict={"상태": "ERROR"},
                action_content="",
                status_code=400,
            )

    status = result.get("status")
    owner = result.get("owner", "")
    if status == "already_applied":
        return _render_action_card(
            page_title="청약 완료",
            header_title="이미 처리 완료",
            description=f"{owner} 님의 청약 완료 처리가 이미 반영되어 있습니다.",
            info_dict={"대상자": owner, "처리 결과": "기 반영됨"},
            action_content="",
            status_code=200,
        )
    elif status == "already_processed":
        return _render_action_card(
            page_title="처리 완료",
            header_title="이미 처리 완료",
            description="해당 작업 링크는 이미 처리되었습니다.",
            info_dict={"처리 결과": "이미 처리됨"},
            action_content="",
            status_code=200,
        )
    elif status == "applied":
        notification_status = result.get("notification", {}).get("status")
        confirmation_info = {}
        if notification_status in {"failed", "partial", "unconfigured"}:
            confirmation_info["확인 알림"] = "일부 알림을 보내지 못했습니다. 청약 완료 기록은 저장되었습니다."
        return _render_action_card(
            page_title="청약 완료 완료",
            header_title="청약 완료 처리 성공",
            description=f"축하합니다! {owner} 님의 공모주 청약이 성공적으로 완료 처리되었습니다.",
            info_dict={"대상자": owner, "처리 결과": "청약 완료 등록 성공", **confirmation_info},
            action_content="",
            status_code=200,
        )
    else:
        return _render_action_card(
            page_title="작업 완료",
            header_title="작업 처리 완료",
            description="작업이 성공적으로 처리되었습니다.",
            info_dict={"처리 결과": "완료"},
            action_content="",
            status_code=200,
        )


@app.post("/a/{token}/link-sale", include_in_schema=False)
async def post_web_action_link_sale(request: Request, token: str) -> HTMLResponse:
    """Link a P&L record to an IPO allocation (OPEN_IPO_SALE_FLOW)."""
    from app.services.action_v2 import (
        ACTION_TYPE_OPEN_IPO_SALE_FLOW,
        get_web_action_metadata,
        is_action_expired,
        mark_web_action_consumed_if_current,
        validate_action_token,
    )
    from app.services.ipo.allocation import (
        AllocationConflict,
        allocation_summary,
        link_sale,
    )
    from app.services.ipo.applications import (
        ApplicationRevisionConflict,
        InvalidApplicationError,
        get_user_applications,
    )
    from app.services.ipo.store import read_market_store_read_only

    # 1. CSRF same-origin check
    if not _validate_same_origin_request(request):
        return _render_action_card(
            page_title="접근 제한",
            header_title="요청 검증 실패",
            description="안전하지 않거나 허용되지 않은 출처에서의 요청입니다.",
            info_dict={"오류": "CSRF_FORBIDDEN"},
            action_content="",
            status_code=403,
        )

    # 2. Token format validation
    try:
        token = validate_action_token(token)
    except Exception:
        return _render_action_card(
            page_title="유효하지 않은 링크",
            header_title="작업 링크 오류",
            description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
            info_dict={"상태": "유효하지 않음"},
            action_content="",
            status_code=404,
        )

    current_user = get_current_username(request)
    action = get_web_action_metadata(token)
    if not action:
        return _render_action_card(
            page_title="유효하지 않은 링크",
            header_title="작업 링크 오류",
            description="해당 링크가 존재하지 않거나 유효하지 않습니다.",
            info_dict={"상태": "유효하지 않음"},
            action_content="",
            status_code=404,
        )

    # 3. Cross-user authorization
    if action.get("username") != current_user:
        return _render_action_card(
            page_title="접근 제한",
            header_title="접근 권한 없음",
            description="해당 작업에 대한 접근 권한이 없습니다. 올바른 계정으로 로그인해 주세요.",
            info_dict={"요청 계정": current_user},
            action_content="",
            status_code=403,
        )

    # 4. Action type guard — only OPEN_IPO_SALE_FLOW handled here
    if action.get("action_type") != ACTION_TYPE_OPEN_IPO_SALE_FLOW:
        return _render_action_card(
            page_title="지원하지 않는 작업",
            header_title="알 수 없는 작업",
            description="지원되지 않는 작업 유형입니다.",
            info_dict={"작업 유형": str(action.get("action_type"))},
            action_content="",
            status_code=400,
        )

    # 5. Expiry check
    if is_action_expired(action):
        return _render_action_card(
            page_title="만료된 링크",
            header_title="작업 기한 만료",
            description="해당 상장일 매도 기록 기한이 이미 만료되었습니다.",
            info_dict={"상태": "기한 만료"},
            action_content="",
            status_code=410,
        )

    meta = action.get("metadata", {})
    ipo_id = meta.get("ipo_id") or ""
    owner = meta.get("owner") or ""
    stock_code = ""
    listing_date = None

    # Resolve canonical IPO name for display
    ipo_name = "공모주"
    matched_ipo = None
    try:
        market_ipos = read_market_store_read_only().get("ipos", [])
        matched_ipo = next((x for x in market_ipos if x.get("ipo_id") == ipo_id), None)
        if matched_ipo and matched_ipo.get("company_name"):
            ipo_name = matched_ipo["company_name"]
        elif matched_ipo and matched_ipo.get("name"):
            ipo_name = matched_ipo["name"]
        if isinstance(matched_ipo, dict):
            stock_code = str(matched_ipo.get("stock_code") or "")
            listing_date = str(
                matched_ipo.get("actual_listing_date")
                or matched_ipo.get("expected_listing_date")
                or ""
            )[:10] or None
    except Exception as exc:
        logger.warning("Failed to resolve canonical IPO company name: %s", type(exc).__name__)

    if not isinstance(matched_ipo, dict) or not stock_code or not listing_date:
        return _render_action_card(
            page_title="연결 실패",
            header_title="매도 기록 연결 실패",
            description="상장 종목 정보를 확인할 수 없습니다.",
            info_dict={"종목명": ipo_name, "대상자": owner, "상태": "오류"},
            action_content="",
            status_code=400,
        )

    # Re-resolve current application/account state.  The action was valid at
    # creation time, but a stale link must not bypass current owner/account
    # eligibility.
    current_apps = get_user_applications(current_user)
    current_app = (current_apps.get("applications") or {}).get(ipo_id, {})
    if owner not in list(current_app.get("applied_owners") or []):
        return _render_action_card(
            page_title="연결 실패",
            header_title="매도 기록 연결 불가",
            description="현재 청약 신청 상태를 확인해 주세요.",
            info_dict={"종목명": ipo_name, "상태": "OWNER_NOT_ELIGIBLE"},
            action_content="",
            status_code=400,
        )
    current_applicant = (current_app.get("applicants") or {}).get(owner)
    if (
        not isinstance(current_applicant, dict)
        or not current_applicant.get("broker_id")
        or not current_applicant.get("account_id")
    ):
        return _render_action_card(
            page_title="계좌 연결 필요",
            header_title="청약 계좌 연결 필요",
            description="매도 기록을 연결하려면 먼저 청약 계좌를 연결해 주세요.",
            info_dict={"종목명": ipo_name, "대상자": owner, "상태": "UNRESOLVED_ACCOUNT"},
            action_content="",
            status_code=400,
        )

    # A stale action must never create an additional link.  FULLY_SOLD is
    # derived from allocation links; consume the URL lifecycle only now.
    try:
        pre_status = allocation_summary(current_user, ipo_id, owner, stock_code, listing_date).get("status")
    except InvalidApplicationError:
        pre_status = "UNRESOLVED"
    if pre_status == "FULLY_SOLD":
        try:
            mark_web_action_consumed_if_current(
                token, authenticated_username=current_user,
                action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
            )
        except Exception as exc:
            logger.warning("Failed to consume stale fully-sold action: %s", type(exc).__name__)
        return _render_action_card(
            page_title="매도 기록 완료", header_title="매도 기록 완료",
            description="해당 배정 물량이 전량 매도 처리 완료되었습니다.",
            info_dict={"종목명": ipo_name, "대상자": owner, "상태": "전량 매도 완료"},
            action_content="", status_code=200,
        )
    if pre_status == "LINK_DATA_MISSING":
        return _render_action_card(
            page_title="연결 실패", header_title="매도 연결 데이터 오류",
            description="기존 매도 연결 데이터를 먼저 확인해 주세요.",
            info_dict={"종목명": ipo_name, "대상자": owner, "상태": "IPO_LINK_DATA_MISSING"},
            action_content="", status_code=409,
        )
    if pre_status in {"NO_ALLOCATION", "UNRESOLVED"}:
        return _render_action_card(
            page_title="연결 실패", header_title="매도 기록 연결 불가",
            description="배정수량 기록을 먼저 확인해 주세요.",
            info_dict={"종목명": ipo_name, "대상자": owner, "상태": pre_status},
            action_content="", status_code=400,
        )

    # 6. Parse POST body
    try:
        form = await request.form()
        pnl_record_id = str(form.get("pnl_record_id") or "").strip()
        matched_quantity_raw = str(form.get("matched_quantity") or "").strip()
        if not pnl_record_id:
            raise ValueError("pnl_record_id is required")
        matched_quantity = int(matched_quantity_raw)
        if matched_quantity <= 0:
            raise ValueError("matched_quantity must be positive")
    except (ValueError, TypeError) as exc:
        return _render_action_card(
            page_title="입력 오류",
            header_title="입력값 오류",
            description="입력값을 확인해 주세요.",
            info_dict={"종목명": ipo_name, "대상자": owner, "상태": "입력 오류"},
            action_content="",
            status_code=400,
        )

    # 7. CAS retry loop: read revision → link_sale → retry on conflict (up to 3)
    MAX_RETRIES = 3
    last_error: Exception | None = None
    link_result: dict | None = None
    for attempt in range(MAX_RETRIES):
        try:
            revision = int(get_user_applications(current_user)["revision"])
            link_result = link_sale(
                username=current_user,
                ipo_id=ipo_id,
                owner=owner,
                pnl_record_id=pnl_record_id,
                matched_quantity=matched_quantity,
                revision=revision,
                stock_code=stock_code,
                listing_date=listing_date,
            )
            break
        except ApplicationRevisionConflict:
            last_error = None  # retry
            continue
        except (InvalidApplicationError, AllocationConflict) as exc:
            last_error = exc
            break
        except Exception as exc:
            logger.warning("link_sale unexpected error: %s", type(exc).__name__)
            last_error = exc
            break
    else:
        last_error = RuntimeError("REVISION_CONFLICT_EXHAUSTED")

    if last_error is not None:
        err_str = str(last_error)
        user_messages = {
            "IPO application must be saved before allocation": "신청 정보가 없습니다. Wealth에서 청약 신청 정보를 확인해 주세요.",
            "Applicant account must be connected before allocation": "증권사 계좌 연결이 필요합니다.",
            "ALLOCATION_REQUIRED": "배정수량 기록이 필요합니다.",
            "PNL_RECORD_NOT_FOUND": "선택한 실현손익 기록을 찾을 수 없습니다.",
            "IPO_SALE_MATCH_INELIGIBLE": "선택한 기록이 이 종목·계좌 조건에 맞지 않습니다.",
            "ALLOCATION_BELOW_LINKED_QUANTITY": "배정수량보다 연결 수량이 많습니다.",
            "DUPLICATE_LINK_CONFLICT": "이미 동일한 기록이 연결되어 있습니다.",
            "ALLOCATION_OVERRUN": "연결 수량이 잔여 배정수량을 초과합니다.",
            "PNL_OVERRUN": "해당 실현손익 기록의 수량이 초과됩니다.",
            "REVISION_CONFLICT_EXHAUSTED": "동시 요청 충돌이 반복되었습니다. 잠시 후 다시 시도해 주세요.",
        }
        desc = user_messages.get(err_str, "처리 중 오류가 발생했습니다. Wealth에서 상태를 확인한 뒤 다시 시도해 주세요.")
        return _render_action_card(
            page_title="연결 실패",
            header_title="매도 기록 연결 실패",
            description=desc,
            info_dict={"종목명": ipo_name, "대상자": owner, "상태": "오류"},
            action_content="",
            status_code=400,
        )

    # 8. Check post-link allocation status to decide if action is fully consumed
    new_status = "UNSOLD"
    try:
        new_summary = allocation_summary(current_user, ipo_id, owner, stock_code, listing_date)
        new_status = new_summary.get("status", "UNSOLD")
    except Exception as exc:
        logger.warning("allocation_summary after link_sale failed: %s", type(exc).__name__)

    if new_status == "FULLY_SOLD":
        # Action lifecycle is separate from the allocation/P&L authority.
        try:
            mark_web_action_consumed_if_current(
                token,
                authenticated_username=current_user,
                action_type=ACTION_TYPE_OPEN_IPO_SALE_FLOW,
            )
        except Exception as exc:
            logger.warning("Failed to mark action consumed after FULLY_SOLD: %s", type(exc).__name__)

    # 9. Render success card
    link_status = (link_result or {}).get("status", "LINKED")
    if link_status == "IDEMPOTENT":
        return _render_action_card(
            page_title="이미 연결됨",
            header_title="중복 연결 감지",
            description="동일한 수량과 기록이 이미 연결되어 있습니다.",
            info_dict={
                "종목명": ipo_name,
                "대상자": owner,
                "연결 수량": f"{matched_quantity:,}주",
                "상태": "기 연결됨 (변경 없음)",
            },
            action_content="",
            status_code=200,
        )

    if new_status == "FULLY_SOLD":
        return _render_action_card(
            page_title="매도 기록 완료",
            header_title="전량 매도 기록 완료",
            description="배정 수량 전체가 매도 기록으로 연결되었습니다.",
            info_dict={
                "종목명": ipo_name,
                "대상자": owner,
                "연결 수량": f"{matched_quantity:,}주",
                "상태": "전량 매도 완료",
            },
            action_content="",
            status_code=200,
        )

    # PARTIALLY_SOLD — still has remaining quantity
    return _render_action_card(
        page_title="매도 기록 연결 완료",
        header_title="매도 기록 연결 완료",
        description="매도 기록이 연결되었습니다. 잔여 수량이 남아 있으면 추가 연결이 가능합니다.",
        info_dict={
            "종목명": ipo_name,
            "대상자": owner,
            "연결 수량": f"{matched_quantity:,}주",
            "상태": "일부 연결 완료",
        },
        action_content=f'<a href="/a/{html.escape(token)}" style="display:block;text-align:center;margin-top:8px;font-size:14px;color:#c4b5fd">추가 연결하기 →</a>',
        status_code=200,
    )


# Web boundary only; the Docker executor is installed separately on Oracle.
from app.system_update import register_update_routes
register_update_routes(app, app_version=APP_VERSION, secret=SECRET_KEY,
                       username=get_current_username, origin=_validate_same_origin_request,
                       session_current=_updater_session_current)
