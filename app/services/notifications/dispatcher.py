"""Provider-neutral notification dispatcher."""
from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence

from app.services.notifications.models import NotificationEvent, NotificationSendResult
from app.services.notifications.sender import NotificationSender

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatches notification events to configured transport senders."""

    def __init__(self, senders: Sequence[NotificationSender] | None = None) -> None:
        self._senders = list(senders) if senders is not None else []

    def register_sender(self, sender: NotificationSender) -> None:
        self._senders.append(sender)

    def dispatch(
        self,
        event: NotificationEvent,
        *,
        send_options: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> list[NotificationSendResult]:
        """Dispatch event to all registered and configured senders.

        send_options is an optional provider-keyed mapping used only for
        transport test hooks / compatibility shims. Ordinary callers can omit
        it and each sender uses its normal network implementation.
        """
        results: list[NotificationSendResult] = []
        options = send_options or {}
        for sender in self._senders:
            try:
                configured = sender.is_configured()
            except Exception:
                logger.warning(
                    "Notification provider configuration check failed: %s",
                    sender.provider_name,
                )
                results.append(
                    NotificationSendResult(
                        success=False,
                        provider=sender.provider_name,
                        retryable=False,
                        error_code="CONFIGURATION_ERROR",
                    )
                )
                continue

            if not configured:
                results.append(
                    NotificationSendResult(
                        success=False,
                        provider=sender.provider_name,
                        retryable=False,
                        error_code="NOT_CONFIGURED",
                    )
                )
                continue

            kwargs = dict(options.get(sender.provider_name, {}))
            try:
                res = sender.send(event, **kwargs)
            except Exception:
                # Do not log the exception object; provider exceptions may
                # contain credential-bearing URLs or access tokens.
                logger.warning(
                    "Notification provider raised unexpectedly: %s",
                    sender.provider_name,
                )
                res = NotificationSendResult(
                    success=False,
                    provider=sender.provider_name,
                    retryable=True,
                    error_code="SEND_FAILED",
                )
            results.append(res)
        return results

    @staticmethod
    def send_direct(sender: NotificationSender, event: NotificationEvent) -> NotificationSendResult:
        """Send an event directly to a single sender."""
        return sender.send(event)
