"""Provider-neutral notification dispatcher."""
from __future__ import annotations

import logging
from typing import Sequence

from app.services.notifications.models import NotificationEvent, NotificationSendResult
from app.services.notifications.sender import NotificationSender

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Dispatches notification events to configured transport senders."""

    def __init__(self, senders: Sequence[NotificationSender] | None = None) -> None:
        self._senders = list(senders) if senders is not None else []

    def register_sender(self, sender: NotificationSender) -> None:
        self._senders.append(sender)

    def dispatch(self, event: NotificationEvent) -> list[NotificationSendResult]:
        """Dispatch event to all registered and configured senders."""
        results: list[NotificationSendResult] = []
        for sender in self._senders:
            if sender.is_configured():
                res = sender.send(event)
                results.append(res)
            else:
                results.append(
                    NotificationSendResult(
                        success=False,
                        provider=sender.provider_name,
                        retryable=False,
                        error_code="NOT_CONFIGURED",
                    )
                )
        return results

    @staticmethod
    def send_direct(sender: NotificationSender, event: NotificationEvent) -> NotificationSendResult:
        """Send an event directly to a single sender."""
        return sender.send(event)
