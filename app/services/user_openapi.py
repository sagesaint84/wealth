from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
USERS_DIR = DATA_DIR / "users"


def _get_user_openapi_file(username: str) -> Path:
    user_dir = USERS_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / "openapi_config.json"


def get_user_openapi_config(username: str) -> dict[str, dict[str, str]]:
    """사용자의 OpenAPI 설정을 조회합니다.
    
    sagesaint 계정의 경우 개별 파일이 없으면 기존 .env 값을 fallback으로 지원합니다.
    """
    file_path = _get_user_openapi_file(username)
    if file_path.exists():
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
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
        }
        return env_config

    return {
        "toss": {"app_key": "", "app_secret": ""},
        "kb": {"app_key": "", "app_secret": ""},
        "nh": {"app_key": "", "app_secret": ""},
        "kis": {"app_key": "", "app_secret": "", "account_no": ""},
        "kiwoom": {"app_key": "", "app_secret": "", "account_no": ""},
    }


def delete_user_broker_openapi(username: str, broker: str) -> dict[str, Any]:
    """특정 증권사의 OpenAPI 키, 시크릿 및 캐시 토큰을 완전히 삭제합니다."""
    current = get_user_openapi_config(username)
    if broker in current:
        if broker in ("kis", "kiwoom"):
            current[broker] = {"app_key": "", "app_secret": "", "account_no": ""}
        else:
            current[broker] = {"app_key": "", "app_secret": ""}

    file_path = _get_user_openapi_file(username)
    file_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")

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


def save_user_openapi_config(username: str, update_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """사용자의 OpenAPI 설정을 저장합니다. 마스킹된 값(****)이나 빈 시크릿은 기존 값을 보존합니다."""
    current = get_user_openapi_config(username)

    for broker in ("toss", "kb", "nh", "kis", "kiwoom"):
        if broker in update_data:
            b_data = update_data[broker]
            current.setdefault(broker, {})

            # 1) 명시적 삭제 플래그가 있는 경우
            if b_data.get("delete") is True:
                delete_user_broker_openapi(username, broker)
                if broker in ("kis", "kiwoom"):
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

    file_path = _get_user_openapi_file(username)
    file_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("사용자 %s의 OpenAPI 설정 저장 완료", username)
    return current


def get_masked_user_openapi_config(username: str) -> dict[str, dict[str, Any]]:
    """UI 표시용 마스킹된 OpenAPI 설정 반환"""
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

    return masked
