"""System-wide OpenDART credential storage, separate from user broker keys."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.services.secure_files import atomic_write_private_json


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DART_SECRET_FILE = ROOT_DIR / "data" / "system" / "secrets" / "dart.json"


class DartSecretError(RuntimeError):
    pass


def dart_secret_path() -> Path:
    configured_root = os.getenv("WEALTH_DATA_DIR", "").strip()
    if configured_root:
        return Path(configured_root) / "system" / "secrets" / "dart.json"
    return DEFAULT_DART_SECRET_FILE


def load_stored_dart_api_key(*, path: Path | None = None) -> str:
    target = path or dart_secret_path()
    if not target.exists():
        return ""
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DartSecretError("DART_SECRET_STATE_INVALID") from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "api_key"}
        or value.get("version") != 1
        or not isinstance(value.get("api_key"), str)
        or not value["api_key"].strip()
    ):
        raise DartSecretError("DART_SECRET_STATE_INVALID")
    return value["api_key"].strip()


def resolve_dart_api_key(*, path: Path | None = None) -> tuple[str, str]:
    """Resolve stored credential before the legacy environment fallback."""
    stored = load_stored_dart_api_key(path=path)
    if stored:
        return stored, "stored"
    environment = os.getenv("DART_API_KEY", "").strip()
    if environment:
        return environment, "environment"
    return "", "unconfigured"


def get_dart_credential_status(*, path: Path | None = None) -> dict[str, Any]:
    _key, source = resolve_dart_api_key(path=path)
    return {"configured": source != "unconfigured", "source": source}


def save_dart_api_key(value: Any, *, path: Path | None = None) -> None:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise DartSecretError("INVALID_DART_API_KEY")
    target = path or dart_secret_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(target.parent, 0o700)
    atomic_write_private_json(target, {"version": 1, "api_key": value.strip()})


def delete_stored_dart_api_key(*, path: Path | None = None) -> None:
    target = path or dart_secret_path()
    try:
        target.unlink()
    except FileNotFoundError:
        pass
