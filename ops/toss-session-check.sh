#!/usr/bin/env bash

CONFIG="${WEALTH_AUTOMATION_ENV:-/root/.config/wealth-automation.env}"

if [ ! -f "$CONFIG" ]; then
    echo "Missing automation config: $CONFIG" >&2
    exit 1
fi

set -a
source "$CONFIG"
set +a

TOSSCTL="${TOSSCTL_PATH:?TOSSCTL_PATH is required}"
CONFIG_DIR="${TOSS_CONFIG_DIR:?TOSS_CONFIG_DIR is required}"
TG_ENV="${TELEGRAM_ENV:-/root/.config/toss-telegram.env}"

LOG="/var/log/toss-auth-extend.log"
THRESHOLD_HOURS="${TOSS_EXTEND_THRESHOLD_HOURS:-48}"

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

log "============================================================"
log "Toss WTS session check START"

STATUS="$("$TOSSCTL" --config-dir "$CONFIG_DIR" --output json auth status 2>&1)"
STATUS_RC=$?

if [ "$STATUS_RC" -ne 0 ]; then
    log "RESULT: FAILED - auth status command failed (exit $STATUS_RC)"
    telegram "🚨 Wealth Toss WTS 세션 확인 실패
서버: $(hostname)
시각: $(timestamp)
auth status 실행 자체가 실패했습니다.
수동 확인이 필요합니다."
    exit "$STATUS_RC"
fi

PARSED="$(printf '%s' "$STATUS" | python3 -c '
import json, sys
from datetime import datetime, timezone

try:
    d = json.load(sys.stdin)
    valid = bool(d.get("valid"))
    active = bool(d.get("active"))
    expiry = d.get("server_expires_at")

    if not expiry:
        print("ERROR|missing server_expires_at")
        raise SystemExit

    exp = datetime.fromisoformat(expiry)
    now = datetime.now(timezone.utc)
    seconds = (exp.astimezone(timezone.utc) - now).total_seconds()
    hours = seconds / 3600

    print(f"OK|{int(active)}|{int(valid)}|{hours:.2f}|{expiry}")
except Exception as e:
    print(f"ERROR|{e}")
')"

case "$PARSED" in
    OK\|*)
        ;;
    *)
        log "RESULT: FAILED - could not parse auth status"
        telegram "🚨 Wealth Toss WTS 상태 분석 실패
서버: $(hostname)
시각: $(timestamp)
세션 상태 JSON을 정상적으로 분석하지 못했습니다."
        exit 1
        ;;
esac

IFS='|' read -r _ ACTIVE VALID HOURS_LEFT SERVER_EXPIRY <<< "$PARSED"

log "Session active=$ACTIVE valid=$VALID hours_left=$HOURS_LEFT server_expiry=$SERVER_EXPIRY"

if [ "$ACTIVE" != "1" ] || [ "$VALID" != "1" ]; then
    log "RESULT: FAILED - session is inactive or invalid"
    log "ACTION REQUIRED: QR re-login may be required"

    telegram "🚨 Wealth Toss WTS 세션 오류
서버: $(hostname)
시각: $(timestamp)
현재 세션이 유효하지 않습니다.
QR 재로그인이 필요할 수 있습니다."

    exit 1
fi

WITHIN_THRESHOLD="$(python3 -c "print(1 if float('$HOURS_LEFT') <= $THRESHOLD_HOURS else 0)")"

if [ "$WITHIN_THRESHOLD" != "1" ]; then
    log "RESULT: OK - approximately ${HOURS_LEFT}h remaining; extension not required"
    log "Toss WTS session check END"
    exit 0
fi

telegram "⚠️ Wealth Toss WTS 세션 만료 임박
남은 시간: 약 ${HOURS_LEFT}시간
만료 예정: ${SERVER_EXPIRY}

지금 세션 연장을 시도합니다.
토스 앱에 승인 요청이 오면 승인해주세요."

log "Session is within ${THRESHOLD_HOURS}h of expiry; starting auth extend"

OUTPUT="$("$TOSSCTL" --config-dir "$CONFIG_DIR" auth extend --if-expiring "${THRESHOLD_HOURS}h" --timeout 2m 2>&1)"
RC=$?

printf '%s\n' "$OUTPUT" >> "$LOG"

if [ "$RC" -ne 0 ]; then
    log "RESULT: FAILED - auth extend failed (exit $RC)"
    log "ACTION REQUIRED: manual extension or QR login required"

    telegram "🚨 Wealth Toss WTS 세션 연장 실패
서버: $(hostname)
시각: $(timestamp)
종료 코드: $RC

토스 앱 승인을 놓쳤거나 세션이 이미 무효일 수 있습니다.
수동 연장 또는 QR 재로그인을 확인해주세요."

    exit "$RC"
fi

VERIFY="$("$TOSSCTL" --config-dir "$CONFIG_DIR" --output json auth status 2>/dev/null)"

VERIFY_RESULT="$(printf '%s' "$VERIFY" | python3 -c '
import json, sys
try:
    d=json.load(sys.stdin)
    print("1" if d.get("valid") and d.get("active") else "0")
    print(d.get("server_expires_at") or "")
except Exception:
    print("0")
    print("")
')"

VERIFY_VALID="$(printf '%s\n' "$VERIFY_RESULT" | sed -n '1p')"
NEW_EXPIRY="$(printf '%s\n' "$VERIFY_RESULT" | sed -n '2p')"

if [ "$VERIFY_VALID" = "1" ]; then
    log "RESULT: OK - session extension succeeded; new expiry=$NEW_EXPIRY"

    telegram "✅ Wealth Toss WTS 세션 연장 성공
서버: $(hostname)
완료 시각: $(timestamp)
새 서버 만료 예정: ${NEW_EXPIRY}"

    log "Toss WTS session check END"
    exit 0
fi

log "RESULT: FAILED - extension command returned success but live validation failed"

telegram "🚨 Wealth Toss WTS 연장 후 검증 실패
서버: $(hostname)
시각: $(timestamp)

연장 명령은 완료됐지만 세션 Live Check가 유효하지 않습니다.
수동 확인이 필요합니다."

exit 1
