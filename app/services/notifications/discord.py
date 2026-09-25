"""Discord notification transport sender."""
from __future__ import annotations

import html
import json
import logging
import re
import time
from typing import Any
from urllib import error, request
from urllib.parse import urlsplit

from app.services.discord_secrets import load_stored_discord_secrets
from app.services.notifications.models import NotificationEvent, NotificationSendResult

logger = logging.getLogger(__name__)

_MAX_CONTENT_LENGTH = 2000
_MAX_RETRY_DELAY_SECONDS = 10.0
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


def _is_valid_webhook_url(value: str) -> bool:
    """Accept only Discord HTTPS webhook endpoints; reject generic webhook URLs."""
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
    suffix = parts.path[len("/api/webhooks/") :]
    webhook_id, separator, token_and_suffix = suffix.partition("/")
    return bool(webhook_id and separator and token_and_suffix)


def _telegram_html_to_discord(value: str) -> str:
    """Convert the small Telegram HTML subset used by Wealth to Discord markdown."""
    text = value
    text = re.sub(r"(?is)<\s*br\s*/?\s*>", "\n", text)
    replacements = (
        (r"(?is)<\s*(?:b|strong)\s*>", "**"),
        (r"(?is)<\s*/\s*(?:b|strong)\s*>", "**"),
        (r"(?is)<\s*(?:i|em)\s*>", "*"),
        (r"(?is)<\s*/\s*(?:i|em)\s*>", "*"),
        (r"(?is)<\s*code\s*>", "\x60"),
        (r"(?is)<\s*/\s*code\s*>", "\x60"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    # Strip remaining HTML tags while preserving Discord mention syntax such as <@123>.
    text = _HTML_TAG_RE.sub("", text)
    return html.unescape(text)


def _action_label(value: str | None) -> str:
    label = _telegram_html_to_discord(value or "Wealth에서 확인").strip()
    return label or "Wealth에서 확인"


class DiscordSender:
    """Send provider-neutral notification events through a Discord webhook."""

    def __init__(
        self,
        webhook_url: str | None = None,
        username: str | None = None,
        timeout: float = 10.0,
        max_attempts: int = 3,
    ) -> None:
        if webhook_url is None and username:
            webhook_url = load_stored_discord_secrets(username)["webhook_url"]
        self._webhook_url = (webhook_url or "").strip()
        self.username = username
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)

    @property
    def provider_name(self) -> str:
        return "discord"

    def is_configured(self) -> bool:
        return bool(self._webhook_url)

    @staticmethod
    def _retry_delay(attempt: int, headers: Any = None) -> float:
        delay = min(float(attempt + 1), _MAX_RETRY_DELAY_SECONDS)
        if headers is not None:
            try:
                raw = headers.get("Retry-After")
                if raw is not None:
                    delay = min(max(float(raw), 0.0), _MAX_RETRY_DELAY_SECONDS)
            except (TypeError, ValueError, AttributeError):
                pass
        return delay

    @staticmethod
    def _content(event: NotificationEvent) -> str:
        content = _telegram_html_to_discord(event.body)
        if event.action_url:
            suffix = f"{_action_label(event.action_label)}: {event.action_url}"
            content = f"{content.rstrip()}\n\n{suffix}" if content.strip() else suffix
        return content

    def send(
        self,
        event: NotificationEvent,
        *,
        _urlopen: Any = None,
        _sleep: Any = None,
    ) -> NotificationSendResult:
        if not self.is_configured():
            return NotificationSendResult(
                success=False,
                provider="discord",
                retryable=False,
                error_code="NOT_CONFIGURED",
            )
        if not _is_valid_webhook_url(self._webhook_url):
            return NotificationSendResult(
                success=False,
                provider="discord",
                retryable=False,
                error_code="INVALID_WEBHOOK_URL",
            )

        content = self._content(event)
        if len(content) > _MAX_CONTENT_LENGTH:
            return NotificationSendResult(
                success=False,
                provider="discord",
                retryable=False,
                error_code="MESSAGE_TOO_LONG",
            )

        payload = {
            "content": content,
            "allowed_mentions": {"parse": []},
        }
        req = request.Request(
            self._webhook_url,
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Wealth-Notification/1.0",
            },
            method="POST",
        )
        urlopen_func = _urlopen or request.urlopen
        sleep_func = _sleep or time.sleep

        def retry_or_fail(attempt: int, headers: Any = None) -> NotificationSendResult | None:
            if attempt < self.max_attempts - 1:
                sleep_func(self._retry_delay(attempt, headers))
                return None
            return NotificationSendResult(
                success=False,
                provider="discord",
                retryable=True,
                error_code="SEND_FAILED",
            )

        for attempt in range(self.max_attempts):
            try:
                with urlopen_func(req, timeout=self.timeout) as resp:
                    status = int(getattr(resp, "status", getattr(resp, "status_code", 0)) or 0)
                    if 200 <= status < 300:
                        provider_message_id = None
                        try:
                            read = getattr(resp, "read", None)
                            raw = read() if callable(read) else b""
                            if raw:
                                body = json.loads(raw.decode("utf-8"))
                                if isinstance(body, dict) and body.get("id") is not None:
                                    provider_message_id = str(body["id"])
                        except (UnicodeError, json.JSONDecodeError, AttributeError):
                            pass
                        return NotificationSendResult(
                            success=True,
                            provider="discord",
                            provider_message_id=provider_message_id,
                        )
                    if status == 429 or status >= 500:
                        result = retry_or_fail(attempt, getattr(resp, "headers", None))
                        if result is not None:
                            return result
                        continue
                    return NotificationSendResult(
                        success=False,
                        provider="discord",
                        retryable=False,
                        error_code=f"HTTP_{status}" if status else "SEND_FAILED",
                    )
            except error.HTTPError as exc:
                status = int(exc.code)
                if status == 429 or status >= 500:
                    logger.warning("Discord send failed (attempt %d)", attempt + 1)
                    result = retry_or_fail(attempt, getattr(exc, "headers", None))
                    if result is not None:
                        return result
                    continue
                logger.warning("Discord send failed (attempt %d)", attempt + 1)
                return NotificationSendResult(
                    success=False,
                    provider="discord",
                    retryable=False,
                    error_code=f"HTTP_{status}",
                )
            except Exception:
                # Never log the exception object: it may contain the credential-bearing URL.
                logger.warning("Discord send failed (attempt %d)", attempt + 1)
                result = retry_or_fail(attempt)
                if result is not None:
                    return result

        return NotificationSendResult(
            success=False,
            provider="discord",
            retryable=True,
            error_code="SEND_FAILED",
        )
