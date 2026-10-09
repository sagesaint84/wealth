"""Actual savings payments, recorded inside the user's portfolio only.

Withdrawal accounts are historical references: this service never debits them.
"""
from copy import deepcopy
from datetime import date, datetime
import math
import re
import uuid

from app.services.financial_json import financial_rmw
from app.services.portfolio import read_portfolio, write_portfolio

SUPPORTED_TYPES = {"installment", "free", "housing"}


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
    try:
        total = math.fsum(r["amount"] for r in records)
        current = math.fsum([opening, total])
    except OverflowError as exc:
        raise ValueError("납입 이력 합계가 너무 큽니다.") from exc
    if not math.isfinite(current):
        raise ValueError("납입 이력 합계가 올바르지 않습니다.")
    return True, opening, records, total


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
            owner = saving.get("owner") or "모두"
            if bank is None or (owner != "모두" and (bank.get("owner") or "모두") not in {owner, "모두"}):
                raise ValueError("현재 사용자의 상품 소유자 범위에 있는 은행계좌를 선택해 주세요.")
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
