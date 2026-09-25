"""Kakao Talk 'send to me' notification transport."""
from __future__ import annotations

import html
import json
import logging
import re
import time
from typing import Any
from urllib import error, parse, request
from urllib.parse import urlsplit

from app.services.kakao_oauth import (
    KakaoOAuthError,
    get_valid_access_token,
    refresh_kakao_tokens,
    resolve_kakao_app_config,
)
from app.services.kakao_tokens import load_kakao_tokens
from app.services.notifications.models import NotificationEvent, NotificationSendResult

logger = logging.getLogger(__name__)

SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
_MAX_TEXT_LENGTH = 200
_MAX_RETRY_DELAY_SECONDS = 10.0
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


def _telegram_html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<\s*br\s*/?\s*>", "\n", value)
    text = _HTML_TAG_RE.sub("", text)
    return html.unescape(text)


def _same_origin(url: str, base: str) -> bool:
    try:
        u = urlsplit(url)
        b = urlsplit(base)
        return (
            u.scheme == b.scheme == "https"
            and u.hostname == b.hostname
            and u.port == b.port
            and not u.username
            and not u.password
            and not u.fragment
        )
    except ValueError:
        return False


class KakaoSender:
    """Send NotificationEvent to the authenticated user's Kakao 'self' chat."""

    def __init__(
        self,
        *,
        username: str,
        timeout: float = 10.0,
        max_attempts: int = 3,
    ) -> None:
        self.username = username
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)

    @property
    def provider_name(self) -> str:
        return "kakao"

    def is_configured(self) -> bool:
        try:
            app = resolve_kakao_app_config(self.username)
            tokens = load_kakao_tokens(self.username)
            return bool(
                app.app_configured
                and app.public_base_url
                and (tokens.access_token or tokens.refresh_token)
            )
        except Exception:
            return False

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

    def _template(self, event: NotificationEvent) -> tuple[dict[str, Any] | None, str | None]:
        app = resolve_kakao_app_config(self.username)
        if not app.public_base_url:
            return None, "PUBLIC_BASE_URL_REQUIRED"
        raw_text = (
            event.metadata.get("kakao_body")
            if event.metadata and isinstance(event.metadata.get("kakao_body"), str)
            else event.body
        )
        text = _telegram_html_to_text(raw_text).strip()
        if not text:
            return None, "MESSAGE_EMPTY"
        if len(text) > _MAX_TEXT_LENGTH:
            return None, "MESSAGE_TOO_LONG"
        target = app.public_base_url
        if event.action_url:
            if not _same_origin(event.action_url, app.public_base_url):
                return None, "ACTION_URL_NOT_ALLOWED"
            target = event.action_url
        template: dict[str, Any] = {
            "object_type": "text",
            "text": text,
            "link": {
                "web_url": target,
                "mobile_web_url": target,
            },
        }
        if event.action_url:
            label = _telegram_html_to_text(
                event.action_label or "Wealth 열기"
            ).strip()
            if label:
                template["button_title"] = label[:8]
        return template, None

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
                provider="kakao",
                retryable=False,
                error_code="NOT_CONFIGURED",
            )
        template, template_error = self._template(event)
        if template_error:
            return NotificationSendResult(
                success=False,
                provider="kakao",
                retryable=False,
                error_code=template_error,
            )
        opener = _urlopen or request.urlopen
        sleep_func = _sleep or time.sleep

        try:
            token = get_valid_access_token(self.username, opener=opener)
        except KakaoOAuthError as exc:
            return NotificationSendResult(
                success=False,
                provider="kakao",
                retryable=str(exc) in {"KAKAO_OAUTH_UNAVAILABLE"},
                error_code=str(exc),
            )
        except Exception:
            return NotificationSendResult(
                success=False,
                provider="kakao",
                retryable=False,
                error_code="KAKAO_TOKEN_UNAVAILABLE",
            )

        refreshed_after_401 = False
        for attempt in range(self.max_attempts):
            form = parse.urlencode(
                {
                    "template_object": json.dumps(
                        template, ensure_ascii=False, separators=(",", ":")
                    )
                }
            ).encode("utf-8")
            req = request.Request(
                SEND_URL,
                data=form,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                    "User-Agent": "Wealth-Kakao/1.0",
                },
                method="POST",
            )
            try:
                with opener(req, timeout=self.timeout) as response:
                    status = int(getattr(response, "status", 0) or 0)
                    raw = response.read()
                if 200 <= status < 300:
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        return NotificationSendResult(
                            success=False,
                            provider="kakao",
                            retryable=False,
                            error_code="INVALID_RESPONSE",
                        )
                    if isinstance(payload, dict) and payload.get("result_code") == 0:
                        return NotificationSendResult(success=True, provider="kakao")
                    return NotificationSendResult(
                        success=False,
                        provider="kakao",
                        retryable=False,
                        error_code="SEND_FAILED",
                    )
                if status == 429 or status >= 500:
                    if attempt < self.max_attempts - 1:
                        sleep_func(self._retry_delay(attempt, getattr(response, "headers", None)))
                        continue
                    return NotificationSendResult(
                        success=False,
                        provider="kakao",
                        retryable=True,
                        error_code="SEND_FAILED",
                    )
                return NotificationSendResult(
                    success=False,
                    provider="kakao",
                    retryable=False,
                    error_code=f"HTTP_{status}" if status else "SEND_FAILED",
                )
            except error.HTTPError as exc:
                status = int(exc.code)
                if status == 401 and not refreshed_after_401:
                    refreshed_after_401 = True
                    try:
                        token = refresh_kakao_tokens(
                            self.username, opener=opener
                        ).access_token
                    except KakaoOAuthError as refresh_exc:
                        return NotificationSendResult(
                            success=False,
                            provider="kakao",
                            retryable=str(refresh_exc) == "KAKAO_OAUTH_UNAVAILABLE",
                            error_code=str(refresh_exc),
                        )
                    if not token:
                        return NotificationSendResult(
                            success=False,
                            provider="kakao",
                            retryable=False,
                            error_code="KAKAO_ACCESS_TOKEN_MISSING",
                        )
                    continue
                if status == 429 or status >= 500:
                    logger.warning("Kakao send failed (attempt %d)", attempt + 1)
                    if attempt < self.max_attempts - 1:
                        sleep_func(self._retry_delay(attempt, getattr(exc, "headers", None)))
                        continue
                    return NotificationSendResult(
                        success=False,
                        provider="kakao",
                        retryable=True,
                        error_code="SEND_FAILED",
                    )
                logger.warning("Kakao send failed (attempt %d)", attempt + 1)
                return NotificationSendResult(
                    success=False,
                    provider="kakao",
                    retryable=False,
                    error_code=f"HTTP_{status}",
                )
            except Exception:
                # Do not log exception objects: they may include Bearer tokens.
                logger.warning("Kakao send failed (attempt %d)", attempt + 1)
                if attempt < self.max_attempts - 1:
                    sleep_func(self._retry_delay(attempt))
                    continue
                return NotificationSendResult(
                    success=False,
                    provider="kakao",
                    retryable=True,
                    error_code="SEND_FAILED",
                )

        return NotificationSendResult(
            success=False,
            provider="kakao",
            retryable=True,
            error_code="SEND_FAILED",
        )
