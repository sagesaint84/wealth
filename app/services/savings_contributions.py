"""Actual savings payments, recorded inside the user's portfolio only.

Manual payments only reference withdrawal accounts. Scheduled payments optionally
debit a bank account in the same portfolio commit as their principal/history.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import calendar
import math
import re
import uuid

from app.services.financial_json import financial_rmw
from app.services.portfolio import _get_portfolio_file, read_portfolio, write_portfolio

SUPPORTED_TYPES = {"installment", "free", "housing"}
KST = timezone(timedelta(hours=9))
SAVINGS_AUTO_CONTRIBUTION_TIME = "00:10"


class ContributionConflict(ValueError):
    """An existing payment identity cannot be reused for a different payment."""


def _amount(value, *, opening=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("납입금액은 유한한 숫자여야 합니다.")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("납입금액이 올바르지 않습니다.") from exc
    if not math.isfinite(number) or (number < 0 if opening else number <= 0):
        raise ValueError("납입금액은 양수여야 하며 기초 누적액은 0 이상이어야 합니다.")
    return number


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("납입일은 YYYY-MM-DD 형식이어야 합니다.")
    date.fromisoformat(value)
    return value


def contribution_state(saving):
    """Validate persisted history without normalizing it or writing a file."""
    started = "contribution_opening_amount" in saving or "contributions" in saving
    if not started:
        return False, _amount(saving.get("current_paid_amount") or 0, opening=True), [], 0.0
    if "contribution_opening_amount" not in saving or not isinstance(saving.get("contributions"), list):
        raise ValueError("납입 이력과 기초 누적액 구조가 올바르지 않습니다.")
    opening = _amount(saving["contribution_opening_amount"], opening=True)
    records = saving["contributions"]
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("납입 이력은 객체여야 합니다.")
        ident = record.get("id")
        if not isinstance(ident, str) or not ident.strip() or ident in ids:
            raise ValueError("납입 이력 ID가 없거나 중복되었습니다.")
        ids.add(ident)
        _date(record.get("date"))
        _amount(record.get("amount"))
        if not isinstance(record.get("source"), str) or record["source"] not in {"manual", "auto"}:
            raise ValueError("납입 이력 source가 올바르지 않습니다.")
        for field in ("withdraw_account_id", "withdraw_account_name", "memo", "created_at", "updated_at"):
            if not isinstance(record.get(field), str):
                raise ValueError(f"납입 이력 {field} 필드가 올바르지 않습니다.")
        if "bank_balance_debited" in record and not isinstance(record["bank_balance_debited"], bool):
            raise ValueError("납입 이력 잔액 차감 여부는 boolean이어야 합니다.")
    try:
        total = math.fsum(r["amount"] for r in records)
        current = math.fsum([opening, total])
    except OverflowError as exc:
        raise ValueError("납입 이력 합계가 너무 큽니다.") from exc
    if not math.isfinite(current):
        raise ValueError("납입 이력 합계가 올바르지 않습니다.")
    return True, opening, records, total


def _withdraw_bank(data, saving, bank_id, *, krw=False):
    bank = next((b for b in data.get("bank_accounts", []) if b.get("id") == bank_id), None)
    owner = saving.get("owner") or "모두"
    if bank is None or (owner != "모두" and (bank.get("owner") or "모두") not in {owner, "모두"}):
        raise ValueError("현재 사용자의 상품 소유자 범위에 있는 은행계좌를 선택해 주세요.")
    if krw and (bank.get("currency") or "KRW") != "KRW":
        raise ValueError("자동납입 출금계좌는 KRW 은행계좌여야 합니다.")
    return bank


def _kst_now(now=None):
    now = datetime.now(KST) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone-aware datetime required for savings contributions")
    return now.astimezone(KST)


def _activation(value):
    if not isinstance(value, str):
        raise ValueError("자동납입 활성화 시각이 올바르지 않습니다.")
    try:
        return _kst_now(datetime.fromisoformat(value))
    except (ValueError, TypeError) as exc:
        raise ValueError("자동납입 활성화 시각이 올바르지 않습니다.") from exc


def _auto_config(data, saving):
    if saving.get("saving_type") not in SUPPORTED_TYPES:
        raise ValueError("정기적금, 자유적금, 주택청약만 자동납입을 지원합니다.")
    amount = _amount(saving.get("monthly_amount"))
    day = saving.get("auto_transfer_day")
    if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 31:
        raise ValueError("자동납입 반영일은 1~31의 정수여야 합니다.")
    if not isinstance(saving.get("auto_contribution_debit_balance"), bool):
        raise ValueError("자동납입 잔액 차감 여부를 명시적으로 선택해 주세요.")
    bank_id = saving.get("withdraw_account_id")
    if not isinstance(bank_id, str) or not bank_id.strip():
        raise ValueError("자동납입 출금계좌를 선택해 주세요.")
    bank = _withdraw_bank(data, saving, bank_id, krw=True)
    for field in ("start_date", "end_date"):
        if saving.get(field):
            _date(saving[field])
    return amount, day, bank


def apply_auto_contribution_settings(data, record, payload, previous=None):
    """Explicit opt-in only; the backend owns activation timestamps. No posting."""
    previous = previous or {}
    enabled = payload.get("auto_contribution_enabled", previous.get("auto_contribution_enabled", False))
    if not isinstance(enabled, bool):
        raise ValueError("자동납입 사용 여부는 boolean이어야 합니다.")
    old_enabled = previous.get("auto_contribution_enabled", False)
    if not isinstance(old_enabled, bool):
        raise ValueError("저장된 자동납입 사용 여부가 올바르지 않습니다.")
    debit = payload.get("auto_contribution_debit_balance", previous.get("auto_contribution_debit_balance"))
    if ("auto_contribution_debit_balance" in payload or "auto_contribution_debit_balance" in previous) and not isinstance(debit, bool):
        raise ValueError("자동납입 잔액 차감 여부는 boolean이어야 합니다.")
    if "auto_contribution_enabled" in payload or "auto_contribution_enabled" in previous:
        record["auto_contribution_enabled"] = enabled
    if debit is not None:
        record["auto_contribution_debit_balance"] = debit
    if enabled:
        # Validate the original numeric types before the legacy form conversions.
        raw = {**record, **{k: payload[k] for k in ("monthly_amount", "auto_transfer_day") if k in payload}}
        _auto_config(data, raw)
        if old_enabled:
            _activation(previous.get("auto_contribution_enabled_at"))
            record["auto_contribution_enabled_at"] = previous["auto_contribution_enabled_at"]
        else:
            record["auto_contribution_enabled_at"] = _kst_now().isoformat()
    # Client-provided enabled_at is deliberately ignored; disabling clears it.


@financial_rmw("portfolio.json")
def process_scheduled_savings_contributions(username, *, now=None):
    """Current-month evaluation, with one atomic portfolio write for all postings.

    The entire re-read/dedup/debit/history/total boundary is under the canonical
    portfolio lock. An exception before/during write leaves previous bytes intact.
    Expected eligibility/funds skips are successful jobs, retried the next day.
    """
    if not isinstance(username, str) or not username.strip():
        raise ValueError("자동납입은 사용자 범위에서만 실행할 수 있습니다.")
    current = _kst_now(now)
    result = {"status": "success", "created_count": 0, "created_ids": [],
              "skipped_count": 0, "skipped_reasons": {}}

    def skip(reason):
        result["skipped_count"] += 1
        result["skipped_reasons"][reason] = result["skipped_reasons"].get(reason, 0) + 1

    # Registered users without a portfolio must not bootstrap financial data.
    if not _get_portfolio_file(username).exists():
        return result
    data = read_portfolio(username)
    month = current.strftime("%Y-%m")
    savings = data.get("savings_accounts", [])
    if not isinstance(savings, list) or any(not isinstance(s, dict) for s in savings):
        raise ValueError("예·적금 상품 구조가 올바르지 않습니다.")
    ids = [s.get("id") for s in savings]
    if any(not isinstance(sid, str) or not sid for sid in ids) or len(set(ids)) != len(ids):
        raise ValueError("예·적금 상품 ID가 없거나 중복되었습니다.")
    for saving in savings:
        enabled = saving.get("auto_contribution_enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("저장된 자동납입 사용 여부가 올바르지 않습니다.")
        if not enabled:
            skip("DISABLED")
            continue
        if saving.get("saving_type") not in SUPPORTED_TYPES:
            raise ValueError("정기예금은 자동납입을 지원하지 않습니다.")
        started, opening, records, _ = contribution_state(saving)
        ident = f"auto-saving:{saving['id']}:{month}"
        previous = next((r for r in records if r["id"] == ident), None)
        if previous is not None:
            if previous["source"] != "auto":
                raise ContributionConflict("자동납입 ID에 다른 source의 이력이 저장되어 있습니다.")
            skip("ALREADY_PROCESSED")
            continue
        amount, day, bank = _auto_config(data, saving)
        activated = _activation(saving.get("auto_contribution_enabled_at"))
        due = date(current.year, current.month, min(day, calendar.monthrange(current.year, current.month)[1]))
        if current.date() < due:
            skip("NOT_DUE")
            continue
        if activated.date() > due:
            skip("ENABLED_AFTER_DUE")
            continue
        if saving.get("start_date") and due < date.fromisoformat(saving["start_date"]):
            skip("BEFORE_START")
            continue
        if saving.get("end_date") and due > date.fromisoformat(saving["end_date"]):
            skip("AFTER_END")
            continue
        debit = saving["auto_contribution_debit_balance"]
        balance = bank.get("balance", 0)
        if isinstance(balance, bool) or not isinstance(balance, (int, float)) or not math.isfinite(balance):
            raise ValueError("출금계좌 잔액이 올바르지 않습니다.")
        if debit and balance < amount:
            skip("INSUFFICIENT_FUNDS")
            continue
        stamp = current.isoformat()
        record = {"id": ident, "date": due.isoformat(), "amount": amount, "source": "auto",
                  "withdraw_account_id": bank["id"],
                  "withdraw_account_name": bank.get("account_name") or bank.get("bank_name") or "은행계좌",
                  "memo": f"{month} 자동납입", "created_at": stamp, "updated_at": stamp,
                  "bank_balance_debited": debit}
        if not started:
            saving["contribution_opening_amount"] = opening
            saving["contributions"] = []
        saving["contributions"].append(record)
        _, opening, _, total = contribution_state(saving)
        saving["current_paid_amount"] = math.fsum([opening, total])
        saving["updated_at"] = stamp
        if debit:
            bank["balance"] = balance - amount
            bank["updated_at"] = stamp
        result["created_ids"].append(ident)
    result["created_count"] = len(result["created_ids"])
    if result["created_count"]:
        write_portfolio(data, username)
    return result


def _saving(data, saving_id):
    saving = next((s for s in data.get("savings_accounts", []) if s.get("id") == saving_id), None)
    if saving is None:
        raise LookupError("예·적금 상품을 찾을 수 없습니다.")
    if saving.get("saving_type") not in SUPPORTED_TYPES:
        raise ValueError("정기적금, 자유적금, 주택청약 상품만 납입 이력을 지원합니다.")
    contribution_state(saving)
    return saving


def _payload(data, saving, payload, previous=None):
    if not isinstance(payload, dict):
        raise ValueError("납입 요청은 객체여야 합니다.")
    if payload.get("source", "manual") != "manual":
        raise ValueError("사용자는 수동 납입만 등록할 수 있습니다.")
    effective = {**(previous or {}), **payload}
    result = {"date": _date(effective.get("date")), "amount": _amount(effective.get("amount")), "source": "manual"}
    memo = effective.get("memo", "")
    bank_id = effective.get("withdraw_account_id", "")
    if not isinstance(memo, str) or not isinstance(bank_id, str):
        raise ValueError("메모와 출금계좌 ID는 문자열이어야 합니다.")
    result.update(memo=memo, withdraw_account_id=bank_id, withdraw_account_name="")
    if bank_id:
        bank = next((b for b in data.get("bank_accounts", []) if b.get("id") == bank_id), None)
        # Preserve the old snapshot on date/amount/memo edits after account deletion.
        if bank is None and previous and previous.get("withdraw_account_id") == bank_id:
            result["withdraw_account_name"] = previous["withdraw_account_name"]
        else:
            bank = _withdraw_bank(data, saving, bank_id)
            result["withdraw_account_name"] = (previous["withdraw_account_name"] if previous and previous.get("withdraw_account_id") == bank_id
                                               else bank.get("account_name") or bank.get("bank_name") or "은행계좌")
    return result


def _write(data, saving, username):
    _, opening, _, total = contribution_state(saving)
    saving["current_paid_amount"] = math.fsum([opening, total])
    saving["updated_at"] = datetime.now().astimezone().isoformat()
    write_portfolio(data, username)


@financial_rmw("portfolio.json")
def create_contribution(saving_id, payload, username=None):
    data = read_portfolio(username)
    saving = _saving(data, saving_id)
    if not isinstance(payload, dict):
        raise ValueError("납입 요청은 객체여야 합니다.")
    if "date" not in payload or "amount" not in payload:
        raise ValueError("납입일과 납입금액을 입력해 주세요.")
    ident = payload.get("id", str(uuid.uuid4()))
    if not isinstance(ident, str) or not ident.strip():
        raise ValueError("납입 ID는 비어 있지 않은 문자열이어야 합니다.")
    started, opening, records, _ = contribution_state(saving)
    previous = next((r for r in records if r["id"] == ident), None)
    if previous:
        if previous["source"] != "manual":
            raise ContributionConflict("자동 납입 ID는 사용할 수 없습니다.")
        values = _payload(data, saving, payload, previous)
        if all(previous[k] == v for k, v in values.items() if k != "withdraw_account_name"):
            return deepcopy(previous)
        raise ContributionConflict("동일 납입 ID에 다른 내용이 이미 저장되었습니다.")
    values = _payload(data, saving, payload)
    now = datetime.now().astimezone().isoformat()
    record = {"id": ident, **values, "created_at": now, "updated_at": now}
    if not started:
        saving["contribution_opening_amount"] = opening
        saving["contributions"] = []
    saving["contributions"].append(record)
    _write(data, saving, username)
    return deepcopy(record)


@financial_rmw("portfolio.json")
def update_contribution(saving_id, contribution_id, payload, username=None):
    data = read_portfolio(username)
    saving = _saving(data, saving_id)
    records = contribution_state(saving)[2]
    record = next((r for r in records if r["id"] == contribution_id), None)
    if record is None:
        raise LookupError("납입 이력을 찾을 수 없습니다.")
    if record["source"] != "manual":
        raise ValueError("자동 납입은 사용자 화면에서 수정할 수 없습니다.")
    if isinstance(payload, dict) and "id" in payload and payload["id"] != contribution_id:
        raise ContributionConflict("납입 ID는 변경할 수 없습니다.")
    record.update(_payload(data, saving, payload, record))
    record["updated_at"] = datetime.now().astimezone().isoformat()
    _write(data, saving, username)
    return deepcopy(record)


@financial_rmw("portfolio.json")
def delete_contribution(saving_id, contribution_id, username=None):
    data = read_portfolio(username)
    saving = _saving(data, saving_id)
    records = contribution_state(saving)[2]
    record = next((r for r in records if r["id"] == contribution_id), None)
    if record is None:
        raise LookupError("납입 이력을 찾을 수 없습니다.")
    if record["source"] != "manual":
        raise ValueError("자동 납입은 사용자 화면에서 삭제할 수 없습니다.")
    saving["contributions"] = [r for r in records if r["id"] != contribution_id]
    _write(data, saving, username)
    return True
