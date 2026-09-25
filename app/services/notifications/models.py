"""Provider-neutral notification foundation models."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class NotificationEvent:
    """Provider-neutral notification event representation.

    Fields are frozen. `metadata` is defensively copied on initialization so that
    caller-side mutations to the original dict do not affect the event; the internal
    dict itself remains a standard Python dict for ease of serialization and test inspection.
    """

    event_key: str
    event_type: str
    body: str
    username: str | None = None
    title: str | None = None
    parse_mode: str | None = None
    action_url: str | None = None
    action_label: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_key or not isinstance(self.event_key, str):
            raise ValueError("event_key must be a non-empty string")
        if not self.event_type or not isinstance(self.event_type, str):
            raise ValueError("event_type must be a non-empty string")
        if not isinstance(self.body, str):
            raise ValueError("body must be a string")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")
        # Defensive copy isolates instance from external mutations to caller's dict
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class NotificationSendResult:
    """Explicit result of dispatching a notification through a transport sender."""

    success: bool
    provider: str
    retryable: bool = False
    provider_message_id: str | None = None
    error_code: str | None = None
