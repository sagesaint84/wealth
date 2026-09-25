"""Telegram notification transport sender."""
from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib import parse, request

from app.services.notifications.models import NotificationEvent, NotificationSendResult
from app.services.notifications.sender import NotificationSender

logger = logging.getLogger(__name__)


class TelegramSender:
    """Sends notifications to Telegram Bot API using HTTP POST."""

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | int | None = None,
        username: str | None = None,
        timeout: float = 10.0,
        max_attempts: int = 3,
    ) -> None:
        if bot_token is None and chat_id is None:
            from app.services.telegram_config import resolve_runtime_telegram_config
            cfg = resolve_runtime_telegram_config(username)
            if cfg:
                bot_token = cfg.bot_token
                chat_id = cfg.chat_id
        self._bot_token = bot_token or ""
        self._chat_id = str(chat_id).strip() if chat_id is not None and str(chat_id).strip() else ""
        self.username = username
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)

    @property
    def provider_name(self) -> str:
        return "telegram"

    def is_configured(self) -> bool:
        return bool(self._bot_token and self._chat_id)

    def send(
        self,
        event: NotificationEvent,
        *,
        _urlopen: Any = None,
        _sleep: Any = None,
    ) -> NotificationSendResult:
        """Send a notification event via Telegram Bot API sendMessage."""
        if not self.is_configured():
            logger.info("Telegram not configured. Message skipped: %s", event.body[:50])
            return NotificationSendResult(
                success=False,
                provider="telegram",
                retryable=False,
                error_code="NOT_CONFIGURED",
            )

        reply_markup = event.metadata.get("reply_markup") if event.metadata else None
        parse_mode = event.parse_mode or "HTML"
        text = event.body

        payload: dict[str, Any] = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False, separators=(",", ":"))

        data = parse.urlencode(payload).encode("utf-8")
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        req = request.Request(url, data=data, method="POST")

        urlopen_func = _urlopen or request.urlopen
        sleep_func = _sleep or time.sleep

        for attempt in range(self.max_attempts):
            try:
                with urlopen_func(req, timeout=self.timeout) as resp:
                    if getattr(resp, "status", None) == 200 or getattr(resp, "status_code", None) == 200:
                        return NotificationSendResult(
                            success=True,
                            provider="telegram",
                        )
            except Exception:
                # Never log raw exception containing URL with bot_token
                logger.warning("Telegram send failed (attempt %d)", attempt + 1)
                if attempt < self.max_attempts - 1:
                    sleep_func(1.0 * (attempt + 1))

        return NotificationSendResult(
            success=False,
            provider="telegram",
            retryable=False,
            error_code="SEND_FAILED",
        )
