from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from app.services.secure_files import atomic_write_private_json

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
USERS_DIR = DATA_DIR / "users"


def _get_user_openapi_file(username: str) -> Path:
    user_dir = USERS_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "openapi_config.json"


def _write_openapi_config(file_path: Path, value: dict[str, Any]) -> None:
    """Atomically persist credential-bearing config with restrictive POSIX mode."""
    atomic_write_private_json(file_path, value, indent=2)


def get_stored_user_dart_api_key(username: str) -> str:
    """Return only this user's persisted DART key, never an environment fallback.

    The broad OpenAPI reader has legacy broker bootstrap behavior for the
    original owner.  DART resolution must not treat that compatibility path as
    a user-owned credential, otherwise the resolver's precedence becomes
    ambiguous.
    """
    file_path = _get_user_openapi_file(username)
    if not file_path.exists():
        return ""
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(value, dict):
        return ""
    dart = value.get("dart")
    if not isinstance(dart, dict):
        return ""
    api_key = dart.get("api_key")
    return api_key.strip() if isinstance(api_key, str) else ""


def get_user_dart_credential_status(username: str) -> dict[str, Any]:
    """Return safe credential availability metadata without the key itself."""
    if get_stored_user_dart_api_key(username):
        return {"configured": True, "source": "user"}
    if os.getenv("DART_API_KEY", "").strip():
        return {"configured": True, "source": "environment"}
    return {"configured": False, "source": "unconfigured"}


def get_user_openapi_config(username: str) -> dict[str, dict[str, str]]:
    """사용자의 OpenAPI 설정을 조회합니다.
    
    sagesaint 계정의 경우 개별 파일이 없으면 기존 .env 값을 fallback으로 지원합니다.
    """
    file_path = _get_user_openapi_file(username)
    if file_path.exists():
        try:
            cfg = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(cfg, dict):
                cfg.setdefault("dart", {"api_key": ""})
                return cfg
        except Exception as e:
            logger.warning("사용자 %s의 openapi_config.json 파싱 실패: %s", username, e)

    # fallback: sagesaint 계정일 때만 .env 기본값을 읽어와 부트스트랩
    if username == "sagesaint":
        env_config = {
            "toss": {
                "app_key": os.getenv("TOSSINVEST_CLIENT_ID", "").strip(),
                "app_secret": os.getenv("TOSSINVEST_CLIENT_SECRET", "").strip(),
            },
            "kb": {
                "app_key": os.getenv("KB_OPENAPI_APP_KEY", "").strip(),
                "app_secret": os.getenv("KB_OPENAPI_APP_SECRET", "").strip(),
                "gnl_ac_no": os.getenv("KB_OPENAPI_ACCOUNT_NO", "").strip(),
                "gds_no": os.getenv("KB_OPENAPI_PRODUCT_NO", "").strip(),
            },
            "nh": {
                "app_key": os.getenv("NHPLUG_APP_KEY", "").strip(),
                "app_secret": os.getenv("NHPLUG_APP_SECRET", "").strip(),
            },
            "kis": {
                "app_key": os.getenv("KIS_APP_KEY", "").strip(),
                "app_secret": os.getenv("KIS_APP_SECRET", "").strip(),
                "account_no": os.getenv("KIS_ACCOUNT_NO", "").strip(),
            },
            "kiwoom": {
                "app_key": os.getenv("KIWOOM_APP_KEY", "").strip(),
                "app_secret": os.getenv("KIWOOM_APP_SECRET", "").strip(),
                "account_no": os.getenv("KIWOOM_ACCOUNT_NO", "").strip(),
            },
            "dart": {"api_key": ""},
        }
        return env_config

    return {
        "toss": {"app_key": "", "app_secret": ""},
        "kb": {"app_key": "", "app_secret": "", "gnl_ac_no": "", "gds_no": ""},
        "nh": {"app_key": "", "app_secret": ""},
        "kis": {"app_key": "", "app_secret": "", "account_no": ""},
        "kiwoom": {"app_key": "", "app_secret": "", "account_no": ""},
        "dart": {"api_key": ""},
    }


def delete_user_broker_openapi(username: str, broker: str) -> dict[str, Any]:
    """특정 증권사의 OpenAPI 키, 시크릿 및 캐시 토큰을 완전히 삭제합니다."""
    current = get_user_openapi_config(username)
    if broker in current:
        if broker == "kb":
            current[broker] = {"app_key": "", "app_secret": "", "gnl_ac_no": "", "gds_no": ""}
        elif broker in ("kis", "kiwoom"):
            current[broker] = {"app_key": "", "app_secret": "", "account_no": ""}
        elif broker == "dart":
            current[broker] = {"api_key": ""}
        else:
            current[broker] = {"app_key": "", "app_secret": ""}

    file_path = _get_user_openapi_file(username)
    _write_openapi_config(file_path, current)

    # 토큰 캐시 파일도 함께 삭제하여 깨끗하게 초기화
    user_dir = USERS_DIR / username
    cache_map = {
        "toss": "toss_token_cache.json",
        "kb": "kb_token_cache.json",
        "nh": "nhplug_token_cache.json",
        "kis": "kis_token_cache.json",
        "kiwoom": "kiwoom_token_cache.json",
    }
    c_filename = cache_map.get(broker)
    if c_filename:
        c_file = user_dir / c_filename
        if c_file.exists():
            try:
                c_file.unlink()
            except OSError:
                pass

    logger.info("사용자 %s의 %s OpenAPI 설정 및 토큰 캐시 삭제 완료", username, broker)
    return current


# WEALTH_DERIVED_ACCOUNT_CONTEXT_PENDING_LIVE_VALIDATION:
# KB Securities customer-facing account numbers are 11 digits (e.g. OOO-91-OOOOOO).
# Internal OpenAPI structures use a 9-digit gnl_ac_no and 2-digit gds_no.
# The structures are compatible with:
#   11-digit account: AAA BB CCCCCC
#   gnl_ac_no = AAA + CCCCCC (9 digits: account11[:3] + account11[5:])
#   gds_no    = BB (2 digits: account11[3:5])
# This derivation is a Wealth account-format policy supported by current
# KB customer-facing account-format evidence and the OpenAPI sample shape.
# It remains pending live SSQM2442 validation.


def _validate_and_derive_kb_account(val: str) -> tuple[str, str, str]:
    """Validate 11-digit KB account number and derive (account11, gnl_ac_no, gds_no).

    Accepts exactly 11 ASCII digits after trimming whitespace and removing hyphens.
    Preserves leading zeroes as strings.
    """
    cleaned = str(val or "").strip()
    if not cleaned:
        return "", "", ""
    # Strip hyphens
    no_dashes = cleaned.replace("-", "")
    if not (no_dashes.isdigit() and len(no_dashes) == 11):
        raise ValueError("KB증권 계좌번호 11자리를 확인하세요.")
    account11 = no_dashes
    gnl_ac_no = account11[:3] + account11[5:]
    gds_no = account11[3:5]
    return account11, gnl_ac_no, gds_no


def save_user_openapi_config(username: str, update_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """사용자의 OpenAPI 설정을 저장합니다. 마스킹된 값(****)이나 빈 시크릿은 기존 값을 보존합니다."""
    if not isinstance(update_data, dict):
        raise ValueError("OpenAPI 설정 형식이 올바르지 않습니다.")
    current = get_user_openapi_config(username)

    for broker in ("toss", "kb", "nh", "kis", "kiwoom"):
        if broker in update_data:
            b_data = update_data[broker]
            current.setdefault(broker, {})

            # 1) 명시적 삭제 플래그가 있는 경우
            if b_data.get("delete") is True:
                delete_user_broker_openapi(username, broker)
                if broker == "kb":
                    current[broker] = {"app_key": "", "app_secret": "", "gnl_ac_no": "", "gds_no": ""}
                elif broker in ("kis", "kiwoom"):
                    current[broker] = {"app_key": "", "app_secret": "", "account_no": ""}
                else:
                    current[broker] = {"app_key": "", "app_secret": ""}
                continue

            # 2) app_key 처리
            new_key = str(b_data.get("app_key", "")).strip()
            if new_key and not new_key.endswith("****"):
                current[broker]["app_key"] = new_key
            elif new_key == "":
                current[broker]["app_key"] = ""

            # 3) app_secret 처리: 새 값이 들어왔을 때만 변경 (비어있거나 '********'이면 기존값 보존)
            new_sec = str(b_data.get("app_secret", "")).strip()
            if new_sec and not new_sec.startswith("****") and new_sec != "********":
                current[broker]["app_secret"] = new_sec
            elif new_key == "" and new_sec == "":
                current[broker]["app_secret"] = ""

            # 4) account_no 처리 (kis, kiwoom 등)
            if "account_no" in b_data:
                new_acc = str(b_data.get("account_no", "")).strip()
                if new_acc and not new_acc.endswith("****"):
                    current[broker]["account_no"] = new_acc
                elif new_acc == "":
                    current[broker]["account_no"] = ""

            # KB SSQM2442 account context is server-side configuration.
            # Accepts 11-digit account number (via account_no or gnl_ac_no) and derives gnl_ac_no and gds_no.
            if broker == "kb":
                input_acct = None
                if "account_no" in b_data:
                    input_acct = str(b_data.get("account_no", "")).strip()
                elif "gnl_ac_no" in b_data:
                    input_acct = str(b_data.get("gnl_ac_no", "")).strip()

                if input_acct is not None:
                    if input_acct and "*" not in input_acct:
                        account11, gnl_ac_no, gds_no = _validate_and_derive_kb_account(input_acct)
                        current[broker]["account11"] = account11
                        current[broker]["gnl_ac_no"] = gnl_ac_no
                        current[broker]["gds_no"] = gds_no
                    elif input_acct == "":
                        current[broker]["account11"] = ""
                        current[broker]["gnl_ac_no"] = ""
                        current[broker]["gds_no"] = ""

    # DART 설정 처리 (시장 데이터 API)
    if "dart" in update_data:
        d_data = update_data["dart"]
        if not isinstance(d_data, dict):
            raise ValueError("OpenDART 설정 형식이 올바르지 않습니다.")
        current.setdefault("dart", {})
        if d_data.get("delete") is True:
            current["dart"] = {"api_key": ""}
        elif "api_key" in d_data:
            raw_dart_key = d_data["api_key"]
            if not isinstance(raw_dart_key, str):
                raise ValueError("OpenDART API Key 형식이 올바르지 않습니다.")
            new_dart_key = raw_dart_key.strip()
            if new_dart_key and not new_dart_key.startswith("****") and not new_dart_key.endswith("****"):
                current["dart"]["api_key"] = new_dart_key

    file_path = _get_user_openapi_file(username)
    _write_openapi_config(file_path, current)
    logger.info("사용자 %s의 OpenAPI 설정 저장 완료", username)
    return current


def get_masked_user_openapi_config(username: str) -> dict[str, dict[str, Any]]:
    """UI 표시용 마스킹된 OpenAPI 설정 반환"""
    from app.services.kb_openapi import mask_kb_account

    cfg = get_user_openapi_config(username)
    masked: dict[str, dict[str, Any]] = {}

    for broker in ("toss", "kb", "nh", "kis", "kiwoom"):
        b_cfg = cfg.get(broker, {})
        key = b_cfg.get("app_key", "")
        sec = b_cfg.get("app_secret", "")
        acc = b_cfg.get("account_no", "")

        masked_key = ""
        if key:
            prefix = key[:4] if len(key) >= 4 else key
            masked_key = f"{prefix}****"

        masked_sec = "********" if sec else ""

        masked_acc = ""
        if acc:
            masked_acc = f"{acc[:4]}****" if len(acc) >= 4 else acc

        masked[broker] = {
            "app_key": masked_key,
            "has_app_key": bool(key),
            "app_secret": masked_sec,
            "has_app_secret": bool(sec),
            "account_no": masked_acc,
            "has_account_no": bool(acc),
            "configured": bool(key and sec),
        }
        if broker == "kb":
            kb_acct = b_cfg.get("gnl_ac_no", "")
            kb_prod = b_cfg.get("gds_no", "")
            account11 = b_cfg.get("account11", "")
            masked[broker]["has_provider_account"] = bool(kb_acct)
            masked[broker]["has_product_number"] = bool(kb_prod)
            masked[broker]["account_no"] = mask_kb_account(account11 or kb_acct, kb_prod) if (account11 or kb_acct) else ""
            masked[broker]["has_account_no"] = bool(kb_acct or account11)
            masked[broker]["realized_configured"] = bool(
                key and sec and kb_acct and kb_prod
            )

    dart_status = get_user_dart_credential_status(username)
    masked["dart"] = {
        # Do not expose a key prefix: it is unnecessary for replacement UI.
        "api_key": "********" if dart_status["configured"] else "",
        "has_api_key": dart_status["source"] == "user",
        "configured": dart_status["configured"],
        "source": dart_status["source"],
    }

    return masked
