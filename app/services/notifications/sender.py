"""Provider-neutral notification sender interface."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.notifications.models import NotificationEvent, NotificationSendResult


@runtime_checkable
class NotificationSender(Protocol):
    """Interface for channel-specific notification senders (Telegram, Discord, Kakao, etc.)."""

    @property
    def provider_name(self) -> str:
        """The canonical name of the provider (e.g. 'telegram', 'discord')."""
        ...

    def is_configured(self) -> bool:
        """Returns True if the sender has the necessary credentials to send notifications."""
        ...

    def send(self, event: NotificationEvent) -> NotificationSendResult:
        """Dispatches the notification event to the underlying provider transport."""
        ...
