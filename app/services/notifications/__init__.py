"""Wealth notification subsystem foundation."""
from __future__ import annotations

from app.services.notifications.discord import DiscordSender
from app.services.notifications.dispatcher import NotificationDispatcher
from app.services.notifications.models import NotificationEvent, NotificationSendResult
from app.services.notifications.sender import NotificationSender
from app.services.notifications.telegram import TelegramSender

__all__ = [
    "DiscordSender",
    "NotificationDispatcher",
    "NotificationEvent",
    "NotificationSendResult",
    "NotificationSender",
    "TelegramSender",
]
