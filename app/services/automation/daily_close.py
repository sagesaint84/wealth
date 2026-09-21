"""Wealth Daily Close Automation Service.

Pure business service extracted from the legacy wealth-daily-close host shell.
Performs broker sync, price/FX refresh, dashboard compilation, snapshot
persistence (stock records + net-worth history for all owners), summary
generation, and user-scoped Telegram outbound notifications.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from app.services.telegram_config import TelegramConfig, resolve_telegram_config
from app.services.telegram_management import send_telegram_message, TelegramManagementError
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

    day = data.get("day_change") or {}
    stock_profit = _number(s.get("profit_krw"))
    stock_return = _number(s.get("return_rate"))
    day_profit = _number(day.get("change_krw"))
    day_rate = _number(day.get("change_rate"))

    sign_stock = "+" if stock_profit > 0 else ""
    sign_day = "+" if day_profit > 0 else ""

    stock_record = next(
        (record for record in stock_records if (record.get("owner") or "모두") == "모두"),
        None,
    )
    net_record = next(
        (record for record in net_snapshots if (record.get("owner") or "모두") == "모두"),
        None,
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
        f"🌙 일간 주식변화: {sign_day}{_won(day_profit)} ({sign_day}{day_rate:.2f}%)",
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
    except Exception as exc:
        logger.warning("Daily close Telegram send failed for %s: %s", username, exc)
        return {
            "telegram_sent": False,
            "status": "failed",
            "error": "TELEGRAM_SEND_FAILED",
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
    6. notification: dispatch Telegram message via resolved user config

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
    )
    steps["summary"] = {"status": "success"}

    # 6. notification
    if skip_telegram:
        tg_result = {"telegram_sent": False, "status": "skipped", "error": None}
    else:
        tg_result = send_daily_close_telegram(
            safe_user,
            summary_message,
            transport=telegram_transport,
        )
    steps["notification"] = tg_result

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
        "telegram_sent": tg_result["telegram_sent"],
        "notification_status": tg_result["status"],
        "notification_error": tg_result.get("error"),
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
