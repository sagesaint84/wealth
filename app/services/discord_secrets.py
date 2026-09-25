"""User-scoped Discord webhook secret storage."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.services.settings import SettingsError, _path as settings_path, settings_lock


class DiscordSecretError(SettingsError):
    pass


def secret_path(username: str) -> Path:
    return settings_path(username).parent / "secrets" / "discord.json"


def _valid_webhook_url(value: str) -> bool:
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except (TypeError, ValueError):
        return False
    if (
        parts.scheme != "https"
        or parts.hostname != "discord.com"
        or port not in (None, 443)
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or not parts.path.startswith("/api/webhooks/")
    ):
        return False
    suffix = parts.path[len("/api/webhooks/"):]
    webhook_id, sep, token = suffix.partition("/")
    return bool(webhook_id and sep and token)


def load_stored_discord_secrets(
    username: str, *, path: Path | None = None
) -> dict[str, str]:
    target = path or secret_path(username)
    if not target.exists():
        return {"webhook_url": ""}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise DiscordSecretError("DISCORD_SECRET_STATE_INVALID") from exc
    if (
        not isinstance(data, dict)
        or set(data) != {"version", "webhook_url"}
        or data.get("version") != 1
        or not isinstance(data.get("webhook_url"), str)
    ):
        raise DiscordSecretError("DISCORD_SECRET_STATE_INVALID")
    return {"webhook_url": data["webhook_url"]}


def _save(data: dict[str, Any], target: Path) -> None:
    tmp = target.with_suffix(".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(target.parent, 0o700)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(50):
            try:
                os.replace(tmp, target)
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(0.01)
        if os.name == "posix":
            os.chmod(target, 0o600)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def update_discord_secrets(
    username: str,
    patch: dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, str]:
    if (
        not isinstance(patch, dict)
        or set(patch) - {"webhook_url", "clear_webhook_url"}
    ):
        raise DiscordSecretError("INVALID_DISCORD_SECRET_PATCH")
    target = path or secret_path(username)
    for attempt in range(100):
        try:
            with settings_lock(target):
                current = load_stored_discord_secrets(username, path=target)
                value = patch.get("webhook_url")
                if value is not None:
                    if not isinstance(value, str) or "\x00" in value:
                        raise DiscordSecretError("INVALID_DISCORD_WEBHOOK_URL")
                    value = value.strip()
                    if value and not _valid_webhook_url(value):
                        raise DiscordSecretError("INVALID_DISCORD_WEBHOOK_URL")
                    if value:
                        current["webhook_url"] = value
                if patch.get("clear_webhook_url") is True:
                    current["webhook_url"] = ""
                _save({"version": 1, **current}, target)
            return current
        except SettingsError as exc:
            if str(exc) != "SETTINGS_ALREADY_RUNNING" or attempt == 99:
                raise
            time.sleep(0.01)
    raise DiscordSecretError("DISCORD_SECRET_SAVE_FAILED")


def discord_secret_status(username: str) -> dict[str, object]:
    stored = load_stored_discord_secrets(username)
    configured = bool(stored["webhook_url"])
    return {
        "webhook_url_configured": configured,
        "webhook_url_source": "stored" if configured else "none",
    }
