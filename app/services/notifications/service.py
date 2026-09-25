"""Common user-scoped notification routing and aggregation service.

This layer owns provider enable switches, sender construction, configuration
failure isolation, and aggregate delivery status. Domain services only need to
build NotificationEvent objects and keep any domain-specific deduplication.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from app.services.notifications.dispatcher import NotificationDispatcher
from app.services.notifications.models import NotificationEvent, NotificationSendResult
from app.services.notifications.sender import NotificationSender

PROVIDER_NAMES: tuple[str, ...] = ("telegram", "discord", "kakao")


def _provider_payload(
    *,
    sent: bool,
    status: str,
    retryable: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "sent": bool(sent),
        "status": status,
        "retryable": bool(retryable),
        "error": error,
    }


def _ordered_provider_names(providers: Sequence[str] | set[str] | None) -> tuple[str, ...]:
    if providers is None:
        return PROVIDER_NAMES
    requested = set(providers)
    return tuple(provider for provider in PROVIDER_NAMES if provider in requested)


@dataclass(frozen=True)
class NotificationDispatchReport:
    """Secret-safe aggregate result for one provider-neutral event."""

    status: str
    notifications_sent_count: int
    provider_results: dict[str, dict[str, Any]]
    results: tuple[NotificationSendResult, ...]
    enabled_providers: frozenset[str]
    requested_providers: frozenset[str]


class UserNotificationService:
    """Resolve and dispatch enabled notification providers for one Wealth user."""

    def __init__(
        self,
        username: str | None,
        *,
        telegram_credentials: tuple[str | None, str | int | None] | None = None,
        telegram_resolver: Callable[[str], Any] | None = None,
        sender_overrides: Mapping[str, NotificationSender] | None = None,
        enabled_overrides: Mapping[str, bool] | None = None,
    ) -> None:
        self.username = username
        self.telegram_credentials = telegram_credentials
        self.telegram_resolver = telegram_resolver
        self.sender_overrides = dict(sender_overrides or {})
        self.enabled_overrides = dict(enabled_overrides or {})

    def _resolve_enabled(self) -> tuple[set[str], bool]:
        """Return enabled providers and whether stored settings were readable."""
        if not self.username:
            enabled = {"telegram"}
            settings_ok = True
        else:
            from app.services.settings import get_effective_settings

            try:
                settings = get_effective_settings(self.username)
            except Exception:
                settings = {}
                settings_ok = False
            else:
                settings_ok = True

            enabled = {
                provider
                for provider in PROVIDER_NAMES
                if settings.get(provider, {}).get("enabled") is True
            }

        for provider, value in self.enabled_overrides.items():
            if provider not in PROVIDER_NAMES:
                continue
            if value is True:
                enabled.add(provider)
            elif value is False:
                enabled.discard(provider)
        return enabled, settings_ok

    def enabled_provider_names(self) -> set[str]:
        enabled, settings_ok = self._resolve_enabled()
        return enabled if settings_ok else set()

    def _build_sender(self, provider: str) -> NotificationSender:
        override = self.sender_overrides.get(provider)
        if override is not None:
            return override

        if provider == "telegram":
            from app.services.notifications.telegram import TelegramSender

            credentials = self.telegram_credentials
            if credentials is None:
                if not self.username:
                    credentials = (None, None)
                else:
                    if self.telegram_resolver is not None:
                        cfg = self.telegram_resolver(self.username)
                    else:
                        from app.services.telegram_config import resolve_telegram_config

                        cfg = resolve_telegram_config(self.username)
                    credentials = (cfg.bot_token, cfg.chat_id)
            bot_token, chat_id = credentials
            return TelegramSender(
                bot_token=bot_token,
                chat_id=chat_id,
                username=self.username,
            )

        if provider == "discord":
            if not self.username:
                raise ValueError("username is required for Discord notifications")
            from app.services.notifications.discord import DiscordSender

            return DiscordSender(username=self.username)

        if provider == "kakao":
            if not self.username:
                raise ValueError("username is required for Kakao notifications")
            from app.services.notifications.kakao import KakaoSender

            return KakaoSender(username=self.username)

        raise ValueError("unsupported notification provider")

    def build_senders(
        self,
        providers: Sequence[str] | set[str] | None = None,
        *,
        respect_enabled: bool = True,
    ) -> tuple[list[NotificationSender], list[NotificationSendResult]]:
        """Build requested senders while isolating constructor/config errors."""
        requested = _ordered_provider_names(providers)
        if respect_enabled:
            enabled, settings_ok = self._resolve_enabled()
            if not settings_ok:
                return [], [
                    NotificationSendResult(
                        success=False,
                        provider=provider,
                        retryable=False,
                        error_code="CONFIGURATION_ERROR",
                    )
                    for provider in requested
                ]
            requested = tuple(provider for provider in requested if provider in enabled)

        senders: list[NotificationSender] = []
        failures: list[NotificationSendResult] = []
        for provider in requested:
            try:
                senders.append(self._build_sender(provider))
            except Exception:
                failures.append(
                    NotificationSendResult(
                        success=False,
                        provider=provider,
                        retryable=False,
                        error_code="CONFIGURATION_ERROR",
                    )
                )
        return senders, failures

    def configured_provider_names(
        self,
        providers: Sequence[str] | set[str] | None = None,
        *,
        respect_enabled: bool = True,
    ) -> set[str]:
        """Return requested providers that are enabled, constructible and configured."""
        senders, _failures = self.build_senders(
            providers,
            respect_enabled=respect_enabled,
        )
        configured: set[str] = set()
        for sender in senders:
            try:
                if sender.is_configured():
                    configured.add(sender.provider_name)
            except Exception:
                # Configuration checks are intentionally secret-safe.
                continue
        return configured

    @staticmethod
    def _result_payload(result: NotificationSendResult) -> dict[str, Any]:
        if result.success:
            return _provider_payload(
                sent=True,
                status="sent",
            )
        if result.error_code == "NOT_CONFIGURED":
            return _provider_payload(
                sent=False,
                status="unconfigured",
            )
        return _provider_payload(
            sent=False,
            status="failed",
            retryable=result.retryable,
            error=result.error_code or "SEND_FAILED",
        )

    def dispatch(
        self,
        event: NotificationEvent,
        *,
        providers: Sequence[str] | set[str] | None = None,
        respect_enabled: bool = True,
        send_options: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> NotificationDispatchReport:
        """Dispatch an event and aggregate a secret-safe provider result."""
        requested_order = _ordered_provider_names(providers)
        requested = set(requested_order)

        if respect_enabled:
            enabled, settings_ok = self._resolve_enabled()
        else:
            enabled, settings_ok = set(requested), True

        provider_results: dict[str, dict[str, Any]] = {}
        if respect_enabled and not settings_ok:
            results = tuple(
                NotificationSendResult(
                    success=False,
                    provider=provider,
                    retryable=False,
                    error_code="CONFIGURATION_ERROR",
                )
                for provider in requested_order
            )
            for result in results:
                provider_results[result.provider] = self._result_payload(result)
            return NotificationDispatchReport(
                status="failed",
                notifications_sent_count=0,
                provider_results=provider_results,
                results=results,
                enabled_providers=frozenset(),
                requested_providers=frozenset(requested),
            )

        active = requested & enabled
        for provider in requested_order:
            if provider not in active:
                provider_results[provider] = _provider_payload(
                    sent=False,
                    status="disabled",
                )

        senders: list[NotificationSender] = []
        construction_results: list[NotificationSendResult] = []
        for provider in requested_order:
            if provider not in active:
                continue
            try:
                senders.append(self._build_sender(provider))
            except Exception:
                construction_results.append(
                    NotificationSendResult(
                        success=False,
                        provider=provider,
                        retryable=False,
                        error_code="CONFIGURATION_ERROR",
                    )
                )

        dispatch_results = NotificationDispatcher(senders).dispatch(
            event,
            send_options=send_options,
        )
        all_results = tuple([*construction_results, *dispatch_results])
        for result in all_results:
            provider_results[result.provider] = self._result_payload(result)

        # Defensive completion for requested active providers.
        for provider in requested_order:
            if provider in active and provider not in provider_results:
                provider_results[provider] = _provider_payload(
                    sent=False,
                    status="failed",
                    error="SEND_FAILED",
                )

        sent_count = sum(
            1
            for provider in active
            if provider_results.get(provider, {}).get("sent") is True
        )
        if not active:
            status = "disabled"
        elif sent_count == len(active):
            status = "sent"
        elif sent_count > 0:
            status = "partial"
        elif all(
            provider_results.get(provider, {}).get("status") == "unconfigured"
            for provider in active
        ):
            status = "unconfigured"
        else:
            status = "failed"

        return NotificationDispatchReport(
            status=status,
            notifications_sent_count=sent_count,
            provider_results=provider_results,
            results=all_results,
            enabled_providers=frozenset(active),
            requested_providers=frozenset(requested),
        )
