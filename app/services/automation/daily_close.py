"""Wealth Daily Close Automation Service.

Pure business service extracted from the legacy wealth-daily-close host shell.
Performs broker sync, price/FX refresh, dashboard compilation, snapshot
persistence (stock records + net-worth history for all owners), summary
generation, and user-scoped multi-channel outbound notifications.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from app.services.telegram_config import TelegramConfig, resolve_telegram_config
from app.services.telegram_management import send_telegram_message, TelegramManagementError
from app.services.notifications.models import NotificationEvent, NotificationSendResult
from app.services.notifications.service import UserNotificationService
from app.services.user_manager import get_user_by_name

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _first_number(item: dict[str, Any], keys: tuple[str, ...]) -> float:
    for key in keys:
        value = _number(item.get(key))
        if value:
            return value
    return 0.0


def _won(value: Any) -> str:
    return f"{round(_number(value)):,}원"


def build_daily_close_summary(
    data: dict[str, Any],
    sync_result: dict[str, Any],
    price_result: dict[str, Any],
    stock_records: list[dict[str, Any]],
    net_snapshots: list[dict[str, Any]],
    today: str,
    previous_stock_record: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Pure function generating canonical daily close summary text and metrics.

    Preserves formatting, emojis, number semantics, and broker status markers
    from legacy wealth-daily-close.sh.
    """
    s = data.get("summary") or {}
    banks = data.get("bank_accounts") or []
    savings = data.get("savings_accounts") or []
    insurances = data.get("insurance_accounts") or []
    loans = data.get("loan_accounts") or []
    real_estates = data.get("real_estates") or []

    # ── '모두' 기준 자산/부채 계산 ──
    positive_banks = [
        bank for bank in banks
        if _number(bank.get("balance")) >= 0
    ]

    total_invest_value = _number(s.get("total_value_krw"))
    total_stock_value = _number(s.get("total_stock_value_krw"))
    if not total_stock_value:
        total_stock_value = total_invest_value - _number(s.get("total_cash_krw"))

    total_positive_bank = sum(
        _number(bank.get("balance"))
        for bank in positive_banks
    )

    total_saving = sum(
        _first_number(
            item,
            ("current_value", "current_paid_amount", "balance"),
        )
        for item in savings
    )

    total_all_cash = (
        _number(s.get("total_cash_krw"))
        + total_positive_bank
        + total_saving
    )

    insurance_total = sum(
        _first_number(
            item,
            (
                "expected_amount",
                "converted_total_asset",
                "total_paid_amount",
                "expected_refund_amount",
                "accumulated_paid_amount",
            ),
        )
        for item in insurances
    )

    total_pure_debt = sum(
        _number(loan.get("current_balance"))
        for loan in loans
    )

    represented_overdraft_banks = {
        (
            str(loan.get("owner") or "모두"),
            str(loan.get("overdraft_bank_account_id") or "").strip(),
        )
        for loan in loans
        if (
            str(loan.get("loan_type") or "") == "minus"
            and str(loan.get("overdraft_bank_account_id") or "").strip()
            and _number(loan.get("current_balance")) > 0
        )
    }

    total_minus_bank_debt = 0.0
    for bank in banks:
        balance = _number(bank.get("balance"))
        if balance >= 0:
            continue
        relationship_key = (
            str(bank.get("owner") or "모두"),
            str(bank.get("id") or "").strip(),
        )
        if relationship_key not in represented_overdraft_banks:
            total_minus_bank_debt += abs(balance)

    total_tenant_deposit = 0.0
    total_landlord_deposit_debt = 0.0
    total_re_invest_equity = 0.0

    for item in real_estates:
        property_type = item.get("property_type") or "own"
        if property_type != "lease":
            current_price = _number(item.get("current_price"))
            total_re_invest_equity += current_price
            if property_type == "rental":
                total_landlord_deposit_debt += _number(item.get("deposit_amount"))
        else:
            total_tenant_deposit += _number(item.get("deposit_amount"))

    total_all_debt = (
        total_pure_debt
        + total_minus_bank_debt
        + total_landlord_deposit_debt
    )

    total_invest_assets = total_re_invest_equity + total_stock_value
    total_safe_assets = total_all_cash + total_tenant_deposit + insurance_total
    net_worth = total_invest_assets + total_safe_assets - total_all_debt
    total_assets = net_worth + total_all_debt

    # 브로커 동기화 라인 구성
    brokers = sync_result.get("brokers") or []
    broker_lines: list[str] = []
    warning_count = 0

    good_statuses = {"SUCCESS", "CONFIRMED_EMPTY", "PARTIAL_SUCCESS"}
    for broker in brokers:
        status = broker.get("status") or "UNKNOWN"
        name = broker.get("broker") or "증권사"

        if status in good_statuses:
            mark = "✅"
        elif status == "CONFIG_REQUIRED":
            mark = "➖"
        else:
            mark = "⚠️"
            warning_count += 1

        broker_lines.append(f"{mark} {name}: {status}")

    stock_profit = _number(s.get("profit_krw"))
    stock_return = _number(s.get("return_rate"))

    sign_stock = "+" if stock_profit > 0 else ""

    stock_record = next(
        (
            record for record in stock_records
            if (record.get("owner") or "모두") == "모두" and record.get("date") == today
        ),
        None,
    )
    net_record = next(
        (record for record in net_snapshots if (record.get("owner") or "모두") == "모두"),
        None,
    )

    # These are deliberately separate from dashboard day_change.  The latter
    # is a dashboard comparison field, while the canonical stock record owns
    # price-only P/L and the stock-valuation record-to-record comparison.
    canonical_day_profit = _number(stock_record.get("day_profit_krw")) if stock_record else None
    record_change = None
    record_change_rate = None
    if stock_record and previous_stock_record:
        previous_value = _number(previous_stock_record.get("total_value_krw"))
        if previous_value > 0:
            record_change = _number(stock_record.get("total_value_krw")) - previous_value
            record_change_rate = record_change / previous_value * 100

    def _signed(value: float) -> str:
        return "+" if value > 0 else ""

    price_profit_line = (
        f"🌙 당일 가격변동 손익: {_signed(canonical_day_profit)}{_won(canonical_day_profit)}"
        if canonical_day_profit is not None
        else "🌙 당일 가격변동 손익: 주식기록 없음"
    )
    record_change_line = (
        f"📊 전 기록 대비 평가액: {_signed(record_change)}{_won(record_change)} ({_signed(record_change_rate)}{record_change_rate:.2f}%)"
        if record_change is not None and record_change_rate is not None
        else "📊 전 기록 대비 평가액: 이전 기록 없음"
    )

    message_lines = [
        f"📊 Wealth 일일 마감 · {today}",
        "",
        f"💎 순자산: {_won(net_worth)}",
        f"🏦 총자산: {_won(total_assets)}",
        f"💳 총부채: {_won(total_all_debt)}",
        "",
        f"📈 주식 평가액: {_won(total_stock_value)}",
        f"💰 현금·예금: {_won(total_all_cash)}",
        f"🏠 부동산 평가액: {_won(total_re_invest_equity)}",
        f"🛡 보험 평가액: {_won(insurance_total)}",
        "",
        f"📌 주식 평가손익: {sign_stock}{_won(stock_profit)} ({sign_stock}{stock_return:.2f}%)",
        price_profit_line,
        record_change_line,
        "",
        f"🔄 시세갱신: {price_result.get('message', '완료')}",
        "",
        "계좌 동기화",
        *broker_lines,
        "",
        f"🗓 주식기록: {'저장 확인' if stock_record else '⚠️ 확인 필요'} · {len(stock_records)}개 범위",
        f"📒 순자산기록: {'저장 확인' if net_record else '⚠️ 확인 필요'} · {len(net_snapshots)}개 범위",
    ]

    if warning_count:
        message_lines.extend([
            "",
            f"⚠️ 동기화 경고 {warning_count}건이 있습니다.",
        ])

    message = "\n".join(message_lines)
    metrics = {
        "net_worth": net_worth,
        "total_assets": total_assets,
        "total_debt": total_all_debt,
        "stock_record_saved": bool(stock_record),
        "net_record_saved": bool(net_record),
        "stock_record_count": len(stock_records),
        "net_record_count": len(net_snapshots),
        "sync_warning_count": warning_count,
        "canonical_day_profit_krw": canonical_day_profit,
        "record_change_krw": record_change,
        "record_change_rate": record_change_rate,
    }
    return message, metrics


def send_daily_close_telegram(
    username: str,
    message: str,
    *,
    config: TelegramConfig | None = None,
    transport: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Send daily close summary via user's resolved Telegram configuration.

    Non-fatal: network errors or missing configuration never raise, and
    credentials are never leaked.
    """
    cfg = config or resolve_telegram_config(username)
    if not cfg.enabled:
        return {
            "telegram_sent": False,
            "status": "disabled",
            "error": None,
        }
    if not cfg.outbound_configured:
        return {
            "telegram_sent": False,
            "status": "unconfigured",
            "error": None,
        }

    try:
        if transport is not None:
            transport(cfg, message)
        else:
            send_telegram_message(cfg, message)
        return {
            "telegram_sent": True,
            "status": "sent",
            "error": None,
        }
    except Exception:
        logger.warning("Daily close Telegram send failed for %s", username)
        return {
            "telegram_sent": False,
            "status": "failed",
            "error": "TELEGRAM_SEND_FAILED",
        }



def _compact_daily_close_kakao(message: str) -> str:
    """Build a useful <=200 character Kakao summary from the full close message."""
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    selected: list[str] = []
    for line in lines:
        candidate = "\n".join([*selected, line])
        if len(candidate) <= 200:
            selected.append(line)
            continue
        break
    compact = "\n".join(selected).strip()
    if compact:
        return compact
    raw = message.strip()
    return raw if len(raw) <= 200 else raw[:199].rstrip() + "…"


class _InjectedTelegramSender:
    """Telegram sender adapter for the legacy daily-close transport test hook."""

    provider_name = "telegram"

    def __init__(
        self,
        config: TelegramConfig,
        transport: Callable[..., Any],
    ) -> None:
        self._config = config
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self._config.outbound_configured)

    def send(self, event: NotificationEvent, **_kwargs: Any) -> NotificationSendResult:
        try:
            self._transport(self._config, event.body)
            return NotificationSendResult(success=True, provider="telegram")
        except Exception:
            # Never log exception objects because custom transports may include
            # credential-bearing URLs in their error text.
            logger.warning(
                "Daily close Telegram send failed for %s",
                self._config.username,
            )
            return NotificationSendResult(
                success=False,
                provider="telegram",
                retryable=True,
                error_code="TELEGRAM_SEND_FAILED",
            )


def _daily_close_provider_payload(
    *,
    sent: bool,
    status: str,
    retryable: bool = False,
    error: str | None = None,
) -> dict[str, Any]:
    """Compatibility payload used only by skip/fallback paths."""
    return {
        "sent": bool(sent),
        "status": status,
        "retryable": bool(retryable),
        "error": error,
    }


class _UnavailableTelegramSender:
    """Convert Telegram resolver failures into a stable configuration error."""

    provider_name = "telegram"

    def is_configured(self) -> bool:
        raise RuntimeError("telegram configuration unavailable")

    def send(self, event: NotificationEvent, **_kwargs: Any) -> NotificationSendResult:
        return NotificationSendResult(
            success=False,
            provider="telegram",
            retryable=False,
            error_code="CONFIGURATION_ERROR",
        )


def send_daily_close_notifications(
    username: str,
    message: str,
    *,
    today: str,
    telegram_transport: Callable[..., Any] | None = None,
    skip: bool = False,
) -> dict[str, Any]:
    """Dispatch daily-close summary through the common notification service."""
    providers = ("telegram", "discord", "kakao")
    if skip:
        skipped = {
            provider: _daily_close_provider_payload(
                sent=False,
                status="skipped",
            )
            for provider in providers
        }
        return {
            "telegram_sent": False,
            "status": "skipped",
            "error": None,
            "dispatch_status": "skipped",
            "notifications_sent_count": 0,
            "provider_results": skipped,
        }

    telegram_config: TelegramConfig | None
    telegram_config_failed = False
    try:
        telegram_config = resolve_telegram_config(username)
    except Exception:
        logger.warning("Daily close Telegram configuration unavailable for user")
        telegram_config = None
        telegram_config_failed = True

    sender_overrides: dict[str, Any] = {}
    enabled_overrides: dict[str, bool] = {}
    if telegram_config_failed:
        sender_overrides["telegram"] = _UnavailableTelegramSender()
    elif telegram_transport is not None and telegram_config is not None:
        sender_overrides["telegram"] = _InjectedTelegramSender(
            telegram_config,
            telegram_transport,
        )
        # Preserve the historical injected-transport contract used by tests and
        # custom callers. Production automatic delivery follows stored UI switches.
        enabled_overrides["telegram"] = bool(telegram_config.enabled)

    credentials = (
        (telegram_config.bot_token, telegram_config.chat_id)
        if telegram_config is not None
        else (None, None)
    )
    service = UserNotificationService(
        username,
        telegram_credentials=credentials,
        sender_overrides=sender_overrides,
        enabled_overrides=enabled_overrides,
    )

    event = NotificationEvent(
        event_key=f"daily_close:{username}:{today}",
        event_type="daily_close_summary",
        body=message,
        username=username,
        title=f"Wealth 일일 마감 · {today}",
        metadata={"kakao_body": _compact_daily_close_kakao(message)},
    )
    report = service.dispatch(event)

    telegram_result = report.provider_results.get(
        "telegram",
        _daily_close_provider_payload(
            sent=False,
            status="failed",
            error="SEND_FAILED",
        ),
    )
    legacy_error: str | None
    if telegram_result["status"] != "failed":
        legacy_error = None
    elif telegram_result.get("error") == "CONFIGURATION_ERROR":
        legacy_error = "TELEGRAM_CONFIG_ERROR"
    else:
        legacy_error = "TELEGRAM_SEND_FAILED"

    return {
        "telegram_sent": telegram_result["sent"],
        # Legacy fields intentionally continue to describe the Telegram leg.
        "status": telegram_result["status"],
        "error": legacy_error,
        "dispatch_status": report.status,
        "notifications_sent_count": report.notifications_sent_count,
        "provider_results": report.provider_results,
    }


async def run_daily_close_for_user(
    username: str,
    *,
    now: datetime | None = None,
    telegram_transport: Callable[..., Any] | None = None,
    skip_telegram: bool = False,
) -> dict[str, Any]:
    """Execute end-to-end Wealth daily close processing for a specific user.

    Steps:
    1. account_sync: sync all configured broker accounts
    2. price_refresh: refresh market prices and USD/KRW FX rates
    3. dashboard: compile full portfolio and asset dashboard
    4. snapshot: persist stock records and net-worth snapshots for all owners
    5. summary: generate formatted human-readable summary
    6. notification: dispatch to enabled Telegram / Discord / Kakao providers

    Returns machine-readable result dictionary with status and metrics.
    """
    safe_user = (username or "").strip()
    if not safe_user:
        raise ValueError("username is required")

    user = get_user_by_name(safe_user)
    if not user:
        raise ValueError(f"사용자를 찾을 수 없습니다: {safe_user}")

    if now is not None:
        current_dt = now if now.tzinfo else now.replace(tzinfo=KST)
    else:
        current_dt = datetime.now(KST)
    today = current_dt.date().isoformat()

    steps: dict[str, Any] = {}

    # 1. account_sync
    from app.main import sync_all_accounts_for_user
    try:
        sync_result = await sync_all_accounts_for_user(safe_user)
        steps["account_sync"] = {"status": "success", "result": sync_result}
    except Exception as exc:
        logger.exception("Daily close account sync failed for %s", safe_user)
        steps["account_sync"] = {"status": "failed", "error": str(exc)}
        return {
            "ok": False,
            "status": "failed",
            "failed_step": "account_sync",
            "username": safe_user,
            "date": today,
            "steps": steps,
            "error": f"account_sync failed: {str(exc)}",
            "telegram_sent": False,
            "notification_status": "skipped",
        }

    # 2. price_refresh
    from app.main import refresh_prices_for_user
    try:
        price_result = await refresh_prices_for_user(safe_user)
        steps["price_refresh"] = {"status": "success", "result": price_result}
    except Exception as exc:
        logger.exception("Daily close price refresh failed for %s", safe_user)
        steps["price_refresh"] = {"status": "failed", "error": str(exc)}
        return {
            "ok": False,
            "status": "failed",
            "failed_step": "price_refresh",
            "username": safe_user,
            "date": today,
            "steps": steps,
            "error": f"price_refresh failed: {str(exc)}",
            "telegram_sent": False,
            "notification_status": "skipped",
        }

    # 3. dashboard
    from app.main import get_full_dashboard_for_user
    try:
        data = get_full_dashboard_for_user(username=safe_user, record_snapshots=False)
        steps["dashboard"] = {"status": "success"}
    except Exception as exc:
        logger.exception("Daily close dashboard compilation failed for %s", safe_user)
        steps["dashboard"] = {"status": "failed", "error": str(exc)}
        return {
            "ok": False,
            "status": "failed",
            "failed_step": "dashboard",
            "username": safe_user,
            "date": today,
            "steps": steps,
            "error": f"dashboard compilation failed: {str(exc)}",
            "telegram_sent": False,
            "notification_status": "skipped",
        }

    # 4. snapshot
    from app.main import auto_save_all_owner_snapshots, save_all_owner_net_worth_snapshots
    from app.services.asset_records import list_asset_records
    try:
        previous_stock_record = max(
            (
                record for record in list_asset_records(username=safe_user)
                if (record.get("owner") or "모두") == "모두"
                and str(record.get("date") or "") < today
            ),
            key=lambda record: (str(record.get("date") or ""), str(record.get("created_at") or "")),
            default=None,
        )
    except Exception:
        previous_stock_record = None
    try:
        stock_records = auto_save_all_owner_snapshots(
            data,
            username=safe_user,
            source="scheduled",
            memo="21시 자동 기록",
            as_of=current_dt,
        )
        planning_after, net_snapshots = save_all_owner_net_worth_snapshots(
            data,
            safe_user,
            source="scheduled",
            as_of=current_dt,
        )
        steps["snapshot"] = {
            "status": "success",
            "stock_record_count": len(stock_records),
            "net_record_count": len(net_snapshots),
        }
    except Exception as exc:
        logger.exception("Daily close snapshot persistence failed for %s", safe_user)
        steps["snapshot"] = {"status": "failed", "error": str(exc)}
        return {
            "ok": False,
            "status": "failed",
            "failed_step": "snapshot",
            "username": safe_user,
            "date": today,
            "steps": steps,
            "error": f"snapshot persistence failed: {str(exc)}",
            "telegram_sent": False,
            "notification_status": "skipped",
        }

    # 5. summary
    summary_message, metrics = build_daily_close_summary(
        data=data,
        sync_result=sync_result,
        price_result=price_result,
        stock_records=stock_records,
        net_snapshots=net_snapshots,
        today=today,
        previous_stock_record=previous_stock_record,
    )
    steps["summary"] = {"status": "success"}

    # 6. notification
    # skip_telegram is retained as the legacy public escape hatch; in the
    # multi-channel implementation it skips all outbound notifications so
    # existing no-notify test/maintenance calls remain side-effect free.
    try:
        notification_result = send_daily_close_notifications(
            safe_user,
            summary_message,
            today=today,
            telegram_transport=telegram_transport,
            skip=skip_telegram,
        )
    except Exception:
        # Notification plumbing is deliberately non-fatal to the completed
        # financial snapshot. Never log exception text because a provider may
        # embed credentials in it.
        logger.warning("Daily close notification dispatch failed for %s", safe_user)
        failed_providers = {
            provider: _daily_close_provider_payload(
                sent=False,
                status="failed",
                error="SEND_FAILED",
            )
            for provider in ("telegram", "discord", "kakao")
        }
        notification_result = {
            "telegram_sent": False,
            "status": "failed",
            "error": "TELEGRAM_SEND_FAILED",
            "dispatch_status": "failed",
            "notifications_sent_count": 0,
            "provider_results": failed_providers,
        }
    steps["notification"] = notification_result

    return {
        "ok": True,
        "status": "success",
        "username": safe_user,
        "date": today,
        "steps": steps,
        "net_worth": metrics["net_worth"],
        "total_assets": metrics["total_assets"],
        "total_debt": metrics["total_debt"],
        "stock_record_saved": metrics["stock_record_saved"],
        "net_record_saved": metrics["net_record_saved"],
        "stock_record_count": metrics["stock_record_count"],
        "net_record_count": metrics["net_record_count"],
        "sync_warning_count": metrics["sync_warning_count"],
        "summary": summary_message,
        "message": summary_message,
        "telegram_sent": notification_result["telegram_sent"],
        "notification_status": notification_result["status"],
        "notification_error": notification_result.get("error"),
        "notification_dispatch_status": notification_result["dispatch_status"],
        "notifications_sent_count": notification_result["notifications_sent_count"],
        "notification_provider_results": notification_result["provider_results"],
    }


async def run_daily_close(
    username: str,
    *,
    now: datetime | None = None,
    telegram_transport: Callable[..., Any] | None = None,
    skip_telegram: bool = False,
) -> dict[str, Any]:
    """Public entry point alias for run_daily_close_for_user."""
    return await run_daily_close_for_user(
        username=username,
        now=now,
        telegram_transport=telegram_transport,
        skip_telegram=skip_telegram,
    )
