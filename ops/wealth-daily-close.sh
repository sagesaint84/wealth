#!/usr/bin/env bash
set -u

CONFIG="${WEALTH_AUTOMATION_ENV:-/root/.config/wealth-automation.env}"

if [ ! -f "$CONFIG" ]; then
    echo "Missing automation config: $CONFIG" >&2
    exit 1
fi

set -a
source "$CONFIG"
set +a

: "${WEALTH_USERNAME:?WEALTH_USERNAME is required}"

WEALTH_CONTAINER="${WEALTH_CONTAINER:-wealth}"
TG_ENV="${TELEGRAM_ENV:-/root/.config/toss-telegram.env}"

LOG="/var/log/wealth-daily-close.log"
LOCK="/var/run/wealth-daily-close.lock"

timestamp() {
    date '+%Y-%m-%d %H:%M:%S %Z'
}

log() {
    echo "[$(timestamp)] $*" >> "$LOG"
}

telegram() {
    [ -f "$TG_ENV" ] || return 0

    set -a
    source "$TG_ENV"
    set +a

    [ -n "${TELEGRAM_BOT_TOKEN:-}" ] || return 0
    [ -n "${TELEGRAM_CHAT_ID:-}" ] || return 0

    curl -fsS -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=$1" \
        >/dev/null 2>&1 || log "WARNING: Telegram notification failed"
}

touch "$LOG"
chmod 600 "$LOG"

exec 9>"$LOCK"
if ! flock -n 9; then
    log "SKIP: another daily-close job is already running"
    exit 0
fi

log "============================================================"
log "Wealth daily close START"

RESULT="$(
docker exec -i -e WEALTH_USERNAME="$WEALTH_USERNAME" "$WEALTH_CONTAINER" python - <<'PY'
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta

from starlette.requests import Request

from app.main import sync_all_accounts, refresh_prices, dashboard
from app.services.planning import read_planning, mutate
from app.services.asset_records import list_asset_records

USERNAME = os.environ["WEALTH_USERNAME"]
KST = timezone(timedelta(hours=9))


def make_request(path: str, method: str = "POST"):
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 0),
        "server": ("127.0.0.1", 4829),
    }
    request = Request(scope)
    request.state.username = USERNAME
    request.state.role = "user"
    return request


def number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def first_number(item, keys):
    for key in keys:
        value = number(item.get(key))
        if value:
            return value
    return 0.0


def won(value):
    return f"{round(number(value)):,}원"


async def run():
    # 1. 모든 설정된 증권사 계좌 동기화
    sync_result = await sync_all_accounts(
        make_request("/api/sync/all")
    )

    # 2. 보유종목 시세 + USD/KRW 환율 갱신
    price_result = await refresh_prices(
        make_request("/api/refresh-prices")
    )

    # 3. 화면과 동일한 dashboard 구성
    # 이 호출 과정에서 당일 '주식기록'이 모두/가족별로 자동 upsert 됨
    data = await dashboard(
        make_request("/api/dashboard", "GET")
    )

    s = data.get("summary") or {}
    banks = data.get("bank_accounts") or []
    savings = data.get("savings_accounts") or []
    insurances = data.get("insurance_accounts") or []
    loans = data.get("loan_accounts") or []
    real_estates = data.get("real_estates") or []

    # ── wealth.js renderSummary()와 동일한 '모두' 기준 계산 ──

    positive_banks = [
        bank for bank in banks
        if number(bank.get("balance")) >= 0
    ]

    total_invest_value = number(s.get("total_value_krw"))

    total_stock_value = number(s.get("total_stock_value_krw"))
    if not total_stock_value:
        total_stock_value = (
            total_invest_value
            - number(s.get("total_cash_krw"))
        )

    total_positive_bank = sum(
        number(bank.get("balance"))
        for bank in positive_banks
    )

    total_saving = sum(
        first_number(
            item,
            (
                "current_value",
                "current_paid_amount",
                "balance",
            ),
        )
        for item in savings
    )

    total_all_cash = (
        number(s.get("total_cash_krw"))
        + total_positive_bank
        + total_saving
    )

    insurance_total = sum(
        first_number(
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

    # wealth.js calculateDashboardDebt() 동일 로직
    total_pure_debt = sum(
        number(loan.get("current_balance"))
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
            and number(loan.get("current_balance")) > 0
        )
    }

    total_minus_bank_debt = 0.0

    for bank in banks:
        balance = number(bank.get("balance"))

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
            current_price = number(item.get("current_price"))
            total_re_invest_equity += current_price

            if property_type == "rental":
                total_landlord_deposit_debt += number(
                    item.get("deposit_amount")
                )
        else:
            total_tenant_deposit += number(
                item.get("deposit_amount")
            )

    total_all_debt = (
        total_pure_debt
        + total_minus_bank_debt
        + total_landlord_deposit_debt
    )

    total_invest_assets = (
        total_re_invest_equity
        + total_stock_value
    )

    total_safe_assets = (
        total_all_cash
        + total_tenant_deposit
        + insurance_total
    )

    net_worth = (
        total_invest_assets
        + total_safe_assets
        - total_all_debt
    )

    total_assets = net_worth + total_all_debt

    # 4. 순자산기록 upsert
    planning = read_planning(USERNAME)
    today = datetime.now(KST).date().isoformat()

    exists = any(
        record.get("date") == today
        and record.get("owner") == "모두"
        for record in planning.get("history", [])
    )

    planning_payload = {
        "revision": planning.get("revision", 0),
        "owner": "모두",
        "assets": total_assets,
        "debt": total_all_debt,
        "net_worth": net_worth,
        "fx_rates": data.get("fx_rates") or {},
        "valuation_at": data.get("updated_at") or "",
        "replace": exists,
    }

    planning_after = mutate(
        USERNAME,
        "snapshot",
        planning_payload,
    )

    net_record = next(
        (
            record
            for record in planning_after.get("history", [])
            if record.get("date") == today
            and record.get("owner") == "모두"
        ),
        None,
    )

    # dashboard()에서 자동 저장한 오늘 주식기록 확인
    stock_record = next(
        (
            record
            for record in reversed(list_asset_records(USERNAME))
            if record.get("date") == today
            and (record.get("owner") or "모두") == "모두"
        ),
        None,
    )

    brokers = sync_result.get("brokers") or []

    broker_lines = []
    warning_count = 0

    good_statuses = {
        "SUCCESS",
        "CONFIRMED_EMPTY",
        "PARTIAL_SUCCESS",
    }

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

        broker_lines.append(
            f"{mark} {name}: {status}"
        )

    day = data.get("day_change") or {}

    stock_profit = number(s.get("profit_krw"))
    stock_return = number(s.get("return_rate"))
    day_profit = number(day.get("change_krw"))
    day_rate = number(day.get("change_rate"))

    sign_stock = "+" if stock_profit > 0 else ""
    sign_day = "+" if day_profit > 0 else ""

    message_lines = [
        f"📊 Wealth 일일 마감 · {today}",
        "",
        f"💎 순자산: {won(net_worth)}",
        f"🏦 총자산: {won(total_assets)}",
        f"💳 총부채: {won(total_all_debt)}",
        "",
        f"📈 주식 평가액: {won(total_stock_value)}",
        f"💰 현금·예금: {won(total_all_cash)}",
        f"🏠 부동산 평가액: {won(total_re_invest_equity)}",
        f"🛡 보험 평가액: {won(insurance_total)}",
        "",
        f"📌 주식 평가손익: {sign_stock}{won(stock_profit)} ({sign_stock}{stock_return:.2f}%)",
        f"🌙 일간 주식변화: {sign_day}{won(day_profit)} ({sign_day}{day_rate:.2f}%)",
        "",
        f"🔄 시세갱신: {price_result.get('message', '완료')}",
        "",
        "계좌 동기화",
        *broker_lines,
        "",
        f"🗓 주식기록: {'저장 확인' if stock_record else '⚠️ 확인 필요'}",
        f"📒 순자산기록: {'저장 확인' if net_record else '⚠️ 확인 필요'}",
    ]

    if warning_count:
        message_lines.extend([
            "",
            f"⚠️ 동기화 경고 {warning_count}건이 있습니다.",
        ])

    result = {
        "ok": True,
        "date": today,
        "net_worth": net_worth,
        "total_assets": total_assets,
        "total_debt": total_all_debt,
        "stock_record_saved": bool(stock_record),
        "net_record_saved": bool(net_record),
        "sync_warning_count": warning_count,
        "message": "\n".join(message_lines),
    }

    print(json.dumps(result, ensure_ascii=False))


asyncio.run(run())
PY
)"
RC=$?

if [ "$RC" -ne 0 ]; then
    log "RESULT: FAILED - docker Wealth daily-close execution failed (exit $RC)"
    log "$RESULT"

    telegram "🚨 Wealth 일일 마감 실패
서버: $(hostname)
시각: $(timestamp)

계좌 동기화/시세갱신/기록 생성 중 오류가 발생했습니다.
로그: /var/log/wealth-daily-close.log"

    exit "$RC"
fi

JSON_RESULT="$(printf '%s\n' "$RESULT" | tail -n 1)"

if ! printf '%s' "$JSON_RESULT" | python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null 2>&1; then
    log "RESULT: FAILED - invalid JSON result"
    log "$RESULT"

    telegram "🚨 Wealth 일일 마감 결과 분석 실패
서버: $(hostname)
시각: $(timestamp)

자동화 실행 결과를 정상적으로 분석하지 못했습니다."

    exit 1
fi

MESSAGE="$(
    printf '%s' "$JSON_RESULT" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["message"])'
)"

SUMMARY="$(
    printf '%s' "$JSON_RESULT" |
    python3 -c '
import json,sys
d=json.load(sys.stdin)
print(
    "RESULT: OK"
    + " net_worth=" + str(d.get("net_worth"))
    + " total_assets=" + str(d.get("total_assets"))
    + " total_debt=" + str(d.get("total_debt"))
    + " stock_record=" + str(d.get("stock_record_saved"))
    + " net_record=" + str(d.get("net_record_saved"))
    + " sync_warnings=" + str(d.get("sync_warning_count"))
)
'
)"

log "$SUMMARY"

telegram "$MESSAGE"

log "Wealth daily close END"
log "============================================================"

exit 0
