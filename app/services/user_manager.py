from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
USERS_DIR = DATA_DIR / "users"
USERS_FILE = DATA_DIR / "users.json"

PBKDF2_ITERATIONS = 100_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """비밀번호를 PBKDF2-HMAC-SHA256으로 해싱하여 (salt, hash)를 반환합니다."""
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return salt, key.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """비밀번호 일치 여부를 안전하게 검증합니다."""
    _, key_hex = hash_password(password, salt)
    return secrets.compare_digest(key_hex, expected_hash)


def get_user_data_dir(username: str | None = None) -> Path:
    """특정 사용자의 격리된 데이터 디렉터리 경로를 반환하고, 없으면 생성합니다."""
    safe_username = (username or "sagesaint").strip()
    user_dir = USERS_DIR / safe_username
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def load_users_db() -> dict[str, Any]:
    """users.json 파일을 로드합니다."""
    if not USERS_FILE.exists():
        return {"users": []}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("users.json 로드 실패: %s", e)
        return {"users": []}


def save_users_db(data: dict[str, Any]) -> None:
    """users.json 파일에 저장합니다."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = USERS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(USERS_FILE)


def init_users_and_migration() -> None:
    """
    1. users.json이 없으면 초기 admin 계정과 sagesaint 계정을 자동 생성합니다.
    2. 기존 data/ 루트의 포트폴리오/자산기록/배당/손익 파일들을 data/users/sagesaint/로 안전 마이그레이션합니다.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USERS_DIR.mkdir(parents=True, exist_ok=True)

    db = load_users_db()
    users: list[dict[str, Any]] = db.get("users", [])
    usernames = {u["username"] for u in users}
    changed = False

    # 1. 초기 admin 계정 확인 및 생성 (admin / admin, 최초 비밀번호 변경 필수)
    if "admin" not in usernames:
        salt, p_hash = hash_password("admin")
        users.append({
            "username": "admin",
            "salt": salt,
            "password_hash": p_hash,
            "role": "admin",
            "must_change_password": True,
            "created_at": datetime.now().isoformat(),
        })
        usernames.add("admin")
        changed = True
        logger.info("초기 admin 계정이 생성되었습니다 (초기 비번: admin, 변경 필수).")

    # 2. sagesaint 계정 확인 및 등록 (.env의 비밀번호 우선)
    env_user = os.environ.get("DASHBOARD_USERNAME", "sagesaint").strip() or "sagesaint"
    env_pass = os.environ.get("DASHBOARD_PASSWORD", "admin").strip() or "admin"

    if env_user not in usernames:
        salt, p_hash = hash_password(env_pass)
        users.append({
            "username": env_user,
            "salt": salt,
            "password_hash": p_hash,
            "role": "user",  # sagesaint는 일반 유저 등급
            "must_change_password": False,
            "created_at": datetime.now().isoformat(),
        })
        usernames.add(env_user)
        changed = True
        logger.info("%s 계정이 일반 유저로 등록되었습니다.", env_user)

    # 3. 오직 admin 계정만 admin 역할을 유지하도록 정규화
    for u in users:
        if u.get("username") != "admin" and u.get("role") == "admin":
            u["role"] = "user"
            changed = True
            logger.info("비관리자 계정 '%s'의 역할을 'user'로 조정했습니다.", u.get("username"))

    if changed:
        save_users_db({"users": users})

    # 3. 기존 sagesaint 데이터 안전 마이그레이션
    target_dir = get_user_data_dir(env_user)
    files_to_migrate = [
        "portfolio.json",
        "asset_records.json",
        "dividend_records.json",
        "realized_pnl_records.json",
        "period_rates.json",
        "kb_token_cache.json",
        "nhplug_token_cache.json",
    ]

    for fname in files_to_migrate:
        src = DATA_DIR / fname
        dst = target_dir / fname
        # 대상 폴더에 파일이 없고 원본 파일이 루트 data에 존재하면 복사
        if src.exists() and not dst.exists():
            try:
                shutil.copy2(src, dst)
                logger.info("마이그레이션 완료: %s -> %s", src.name, dst)
            except Exception as e:
                logger.error("마이그레이션 실패 (%s): %s", fname, e)


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    """아이디와 비밀번호를 검증하여 일치하면 사용자 딕셔너리를 반환합니다."""
    db = load_users_db()
    for u in db.get("users", []):
        if u["username"] == username:
            if verify_password(password, u.get("salt", ""), u.get("password_hash", "")):
                return u
    return None


def get_user_by_name(username: str) -> dict[str, Any] | None:
    """사용자명으로 사용자 정보를 조회합니다."""
    db = load_users_db()
    for u in db.get("users", []):
        if u["username"] == username:
            return u
    return None


def list_users() -> list[dict[str, Any]]:
    """모든 사용자 목록을 반환합니다 (비밀번호 정보 제외)."""
    db = load_users_db()
    results = []
    for u in db.get("users", []):
        results.append({
            "username": u["username"],
            "role": u.get("role", "user"),
            "must_change_password": bool(u.get("must_change_password", False)),
            "created_at": u.get("created_at", ""),
        })
    return results


def create_new_user(username: str, initial_password_4digit: str, role: str = "user") -> None:
    """신규 사용자를 생성합니다. (초기 4자리 비밀번호, must_change_password=True)"""
    username = username.strip()
    initial_password_4digit = str(initial_password_4digit).strip()

    if not username:
        raise ValueError("사용자 아이디를 입력하세요.")
    if len(username) < 2 or len(username) > 30:
        raise ValueError("아이디는 2자 이상 30자 이하여야 합니다.")
    if len(initial_password_4digit) != 4:
        raise ValueError("초기 비밀번호는 정확히 4자리여야 합니다.")

    db = load_users_db()
    users: list[dict[str, Any]] = db.get("users", [])
    if any(u["username"].lower() == username.lower() for u in users):
        raise ValueError(f"이미 존재하는 아이디입니다: {username}")

    salt, p_hash = hash_password(initial_password_4digit)
    users.append({
        "username": username,
        "salt": salt,
        "password_hash": p_hash,
        "role": role,
        "must_change_password": True,
        "created_at": datetime.now().isoformat(),
    })
    save_users_db({"users": users})

    # 사용자 격리 데이터 디렉터리 및 기본 템플릿 생성
    user_dir = get_user_data_dir(username)
    init_empty_portfolio(user_dir, overwrite=True)
    logger.info("신규 사용자 생성 완료: %s (초기 비번 4자리, 변경 필수)", username)


def init_empty_portfolio(user_dir: Path, overwrite: bool = False) -> None:
    """새 사용자를 위한 빈 포트폴리오 템플릿 생성"""
    port_file = user_dir / "portfolio.json"
    if overwrite or not port_file.exists():
        empty_port = {
            "accounts": [],
            "holdings": [],
            "family_members": ["모두", "나"],
            "updated_at": datetime.now().isoformat(),
        }
        with open(port_file, "w", encoding="utf-8") as f:
            json.dump(empty_port, f, ensure_ascii=False, indent=2)

    rec_file = user_dir / "asset_records.json"
    if overwrite or not rec_file.exists():
        with open(rec_file, "w", encoding="utf-8") as f:
            json.dump({"records": [], "updated_at": None}, f, ensure_ascii=False, indent=2)

    div_file = user_dir / "dividend_records.json"
    if overwrite or not div_file.exists():
        with open(div_file, "w", encoding="utf-8") as f:
            json.dump({"estimated": [], "actual": []}, f, ensure_ascii=False, indent=2)

    pnl_file = user_dir / "realized_pnl_records.json"
    if overwrite or not pnl_file.exists():
        with open(pnl_file, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)


def change_user_password(username: str, old_password: str, new_password: str) -> None:
    """사용자 본인의 비밀번호를 변경합니다."""
    new_password = new_password.strip()
    if len(new_password) < 4:
        raise ValueError("비밀번호는 최소 4자 이상이어야 합니다.")

    db = load_users_db()
    users: list[dict[str, Any]] = db.get("users", [])
    found = False

    for u in users:
        if u["username"] == username:
            found = True
            if not verify_password(old_password, u.get("salt", ""), u.get("password_hash", "")):
                raise ValueError("현재 비밀번호가 일치하지 않습니다.")
            salt, p_hash = hash_password(new_password)
            u["salt"] = salt
            u["password_hash"] = p_hash
            u["must_change_password"] = False
            u["updated_at"] = datetime.now().isoformat()
            break

    if not found:
        raise ValueError("사용자를 찾을 수 없습니다.")

    save_users_db({"users": users})
    logger.info("비밀번호 변경 완료: %s", username)


def force_set_user_password(username: str, new_password: str) -> None:
    """must_change_password 상태에서 새 비밀번호를 설정합니다 (이전 비번 검증 생략 가능)."""
    new_password = new_password.strip()
    if len(new_password) < 4:
        raise ValueError("비밀번호는 최소 4자 이상이어야 합니다.")

    db = load_users_db()
    users: list[dict[str, Any]] = db.get("users", [])
    found = False

    for u in users:
        if u["username"] == username:
            found = True
            salt, p_hash = hash_password(new_password)
            u["salt"] = salt
            u["password_hash"] = p_hash
            u["must_change_password"] = False
            u["updated_at"] = datetime.now().isoformat()
            break

    if not found:
        raise ValueError("사용자를 찾을 수 없습니다.")

    save_users_db({"users": users})
    logger.info("초기 비밀번호 강제 변경 완료: %s", username)


def admin_reset_password_to_4digit(target_username: str, new_4digit_password: str) -> None:
    """관리자가 특정 사용자의 비밀번호를 초기 4자리로 재설정하고 must_change_password=True로 바꿉니다."""
    new_4digit_password = str(new_4digit_password).strip()
    if len(new_4digit_password) != 4:
        raise ValueError("초기화 비밀번호는 정확히 4자리여야 합니다.")

    db = load_users_db()
    users: list[dict[str, Any]] = db.get("users", [])
    found = False

    for u in users:
        if u["username"] == target_username:
            found = True
            salt, p_hash = hash_password(new_4digit_password)
            u["salt"] = salt
            u["password_hash"] = p_hash
            u["must_change_password"] = True
            u["updated_at"] = datetime.now().isoformat()
            break

    if not found:
        raise ValueError(f"사용자를 찾을 수 없습니다: {target_username}")

    save_users_db({"users": users})
    logger.info("관리자가 사용자 %s의 비밀번호를 4자리로 초기화했습니다.", target_username)


def delete_user_account(target_username: str) -> None:
    """사용자를 삭제하고 격리된 데이터 폴더도 함께 정리합니다. (admin 계정은 삭제 불가)"""
    if target_username == "admin":
        raise ValueError("기본 admin 계정은 삭제할 수 없습니다.")

    db = load_users_db()
    users: list[dict[str, Any]] = db.get("users", [])
    initial_len = len(users)
    users = [u for u in users if u["username"] != target_username]

    if len(users) == initial_len:
        raise ValueError(f"사용자를 찾을 수 없습니다: {target_username}")

    save_users_db({"users": users})

    # 해당 사용자 전용 데이터 디렉터리 정리
    user_dir = USERS_DIR / target_username
    if user_dir.exists():
        shutil.rmtree(user_dir, ignore_errors=True)

    logger.info("사용자 계정 및 데이터 폴더 삭제 완료: %s", target_username)
