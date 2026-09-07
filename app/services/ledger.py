"""Smart Family Household Ledger (가계부) Service.

Manages income, expense, transfer transactions, recurring payments, and monthly statistics.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from copy import deepcopy
from datetime import datetime, date
from pathlib import Path
from typing import Any

from app.services.user_manager import get_user_data_dir

DEFAULT_CATEGORIES = {
    "expense": [
        "식비/외식",
        "주거/통신",
        "교통/차량",
        "쇼핑/생활용품",
        "교육/학습",
        "의료/건강",
        "문화/여가",
        "경조사/선물",
        "금융/보험/이자",
        "기타지출",
    ],
    "income": [
        "급여/상여",
        "사업소득",
        "배당/금융수익",
        "용돈/이전소득",
        "부수입/기타수입",
    ],
    "transfer": [
        "계좌이체/저축",
        "투자이체",
        "카드대금결제",
    ],
}

BALANCE_DELTA_VERSION = 2
OVERDRAFT_BALANCE_DELTA_VERSION = 3


class LegacyBalanceDeltaError(ValueError):
    """Raised when a legacy transaction balance delta cannot be reversed safely."""


class BalanceConflictError(ValueError):
    """Raised when a balance change cannot be applied completely and safely."""


class PersistenceConsistencyError(RuntimeError):
    """Raised when a cross-file rollback cannot restore the previous state."""


def get_ledger_path(username: str | None = None) -> Path:
    user_dir = get_user_data_dir(username)
    return user_dir / "ledger.json"


def default_ledger_data() -> dict[str, Any]:
    return {
        "version": "1.0",
        "categories": DEFAULT_CATEGORIES,
        "transactions": [],
        "recurring": [],
        "cards": [],
        "budgets": {},
    }


def read_ledger(username: str | None = None) -> dict[str, Any]:
    path = get_ledger_path(username)
    if not os.path.exists(path):
        data = default_ledger_data()
        write_ledger(data, username=username)
        return data
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("version", "1.0")
        data.setdefault("categories", DEFAULT_CATEGORIES)
        data.setdefault("transactions", [])
        data.setdefault("recurring", [])
        data.setdefault("cards", [])
        data.setdefault("budgets", {})
        return data
    except Exception:
        data = default_ledger_data()
        write_ledger(data, username=username)
        return data


def write_ledger(data: dict[str, Any], username: str | None = None) -> None:
    path = get_ledger_path(username)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def get_ledger_summary(
    username: str | None = None,
    year: int | None = None,
    month: int | None = None,
    owner: str = "모두",
) -> dict[str, Any]:
    process_recurring_deductions(username=username)
    data = read_ledger(username=username)
    now = datetime.now()
    target_year = year or now.year
    target_month = month or now.month

    target_prefix = f"{target_year:04d}-{target_month:02d}"

    txs = data.get("transactions", [])
    # 소유자 필터
    if owner and owner != "모두":
        txs = [t for t in txs if t.get("owner") == owner or t.get("owner") == "모두"]

    # 당월 거래 필터링
    month_txs = [t for t in txs if str(t.get("date", "")).startswith(target_prefix)]

    total_income = 0.0
    total_expense = 0.0
    total_transfer = 0.0

    category_expense_map: dict[str, float] = {}
    category_income_map: dict[str, float] = {}

    for t in month_txs:
        amt = float(t.get("amount") or 0.0)
        t_type = t.get("type", "expense")
        cat = t.get("category") or "기타지출"

        if t_type == "income":
            total_income += amt
            category_income_map[cat] = category_income_map.get(cat, 0.0) + amt
        elif t_type == "expense":
            total_expense += amt
            category_expense_map[cat] = category_expense_map.get(cat, 0.0) + amt
        elif t_type == "transfer":
            total_transfer += amt

    net_savings = total_income - total_expense
    savings_rate = (net_savings / total_income * 100.0) if total_income > 0 else 0.0

    # 고정지출 집계
    recurring_list = data.get("recurring", [])
    if owner and owner != "모두":
        recurring_list = [r for r in recurring_list if r.get("owner") == owner or r.get("owner") == "모두"]
    recurring_expense_total = sum(
        float(r.get("amount") or 0.0)
        for r in recurring_list
        if r.get("active", True) and r.get("type", "expense") == "expense"
    )

    # 최근 6개월 추이 계산
    trend_months = []
    curr_y, curr_m = target_year, target_month
    for i in range(5, -1, -1):
        m_val = curr_m - i
        y_val = curr_y
        while m_val <= 0:
            m_val += 12
            y_val -= 1
        prefix = f"{y_val:04d}-{m_val:02d}"
        label = f"{m_val}월"

        m_inc = sum(float(t.get("amount") or 0.0) for t in txs if str(t.get("date", "")).startswith(prefix) and t.get("type") == "income")
        m_exp = sum(float(t.get("amount") or 0.0) for t in txs if str(t.get("date", "")).startswith(prefix) and t.get("type") == "expense")

        trend_months.append({
            "year": y_val,
            "month": m_val,
            "label": label,
            "income": m_inc,
            "expense": m_exp,
            "savings": m_inc - m_exp,
        })

    # 정렬: 날짜 내림차순
    month_txs_sorted = sorted(month_txs, key=lambda x: str(x.get("date", "")), reverse=True)
    cards_summary = get_cards(username=username, owner=owner)

    return {
        "year": target_year,
        "month": target_month,
        "owner": owner,
        "total_income": total_income,
        "total_expense": total_expense,
        "total_transfer": total_transfer,
        "net_savings": net_savings,
        "savings_rate": round(savings_rate, 1),
        "recurring_expense_total": recurring_expense_total,
        "category_expenses": [
            {"category": k, "amount": v, "percent": round(v / total_expense * 100.0, 1) if total_expense > 0 else 0.0}
            for k, v in sorted(category_expense_map.items(), key=lambda x: x[1], reverse=True)
        ],
        "category_incomes": [
            {"category": k, "amount": v}
            for k, v in sorted(category_income_map.items(), key=lambda x: x[1], reverse=True)
        ],
        "monthly_trend": trend_months,
        "transactions": month_txs_sorted,
        "recurring": recurring_list,
        "cards": cards_summary,
        "categories": data.get("categories", DEFAULT_CATEGORIES),
    }


def _validate_overdraft_pair(
    portfolio_data: dict[str, Any],
    bank_account_id: str,
    expected_loan_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    bank = next(
        (item for item in portfolio_data.get("bank_accounts", []) if item.get("id") == bank_account_id),
        None,
    )
    if bank is None:
        if expected_loan_id:
            raise BalanceConflictError("v3 거래가 참조하는 은행계좌를 찾을 수 없습니다.")
        return None

    linked_loans = [
        item
        for item in portfolio_data.get("loan_accounts", [])
        if str(item.get("overdraft_bank_account_id") or "").strip() == bank_account_id
    ]
    if expected_loan_id:
        loan = next((item for item in linked_loans if item.get("id") == expected_loan_id), None)
        if loan is None:
            raise BalanceConflictError("v3 거래 당시의 마이너스통장 관계를 확인할 수 없습니다.")
    elif not linked_loans:
        return None
    else:
        loan = linked_loans[0]

    if len(linked_loans) != 1:
        raise BalanceConflictError("한 은행계좌에 여러 자동연동 마이너스통장이 연결되어 있습니다.")
    if str(loan.get("loan_type") or "") != "minus":
        raise BalanceConflictError("v3 거래가 참조하는 대출이 마이너스통장 유형이 아닙니다.")
    if str(bank.get("currency") or "KRW").upper() != "KRW":
        raise BalanceConflictError("자동 상계는 KRW 은행계좌만 지원합니다.")
    if str(bank.get("owner") or "모두") != str(loan.get("owner") or "모두"):
        raise BalanceConflictError("마이너스통장과 연결 은행계좌의 소유자가 일치하지 않습니다.")

    bank_balance = float(bank.get("balance") or 0.0)
    loan_balance = float(loan.get("current_balance") or 0.0)
    limit_amount = float(loan.get("limit_amount") or 0.0)
    if not all(math.isfinite(value) for value in (bank_balance, loan_balance, limit_amount)):
        raise BalanceConflictError("자동 상계 잔액과 한도는 유한한 숫자여야 합니다.")
    if bank_balance < 0:
        raise BalanceConflictError("음수 잔고 legacy 계좌에는 자동 상계를 적용할 수 없습니다.")
    if loan_balance < 0 or limit_amount < 0 or loan_balance > limit_amount:
        raise BalanceConflictError("마이너스통장 잔액 또는 한도 데이터가 유효하지 않습니다.")
    return bank, loan


def _apply_overdraft_net_delta(
    bank: dict[str, Any],
    loan: dict[str, Any],
    delta: float,
) -> dict[str, Any]:
    current_bank = float(bank.get("balance") or 0.0)
    current_loan = float(loan.get("current_balance") or 0.0)
    limit_amount = float(loan.get("limit_amount") or 0.0)
    new_net_position = current_bank - current_loan + delta
    if not math.isfinite(new_net_position):
        raise BalanceConflictError("자동 상계 금액이 유효하지 않습니다.")
    new_bank = max(0.0, new_net_position)
    new_loan = max(0.0, -new_net_position)
    if new_loan > limit_amount + 1e-6:
        raise BalanceConflictError("마이너스통장 한도를 초과하여 거래 전체를 처리할 수 없습니다.")

    bank_delta = new_bank - current_bank
    loan_delta = new_loan - current_loan
    now = datetime.now().astimezone().isoformat()
    bank["balance"] = new_bank
    bank["updated_at"] = now
    loan["current_balance"] = new_loan
    loan["updated_at"] = now
    return {
        "applied_delta": delta,
        "balance_delta_version": OVERDRAFT_BALANCE_DELTA_VERSION,
        "balance_effect": {
            "bank_account_id": bank.get("id"),
            "overdraft_loan_id": loan.get("id"),
            "net_delta": delta,
            "bank_delta": bank_delta,
            "loan_delta": loan_delta,
        },
        "changed": abs(bank_delta) >= 1e-6 or abs(loan_delta) >= 1e-6,
    }


def _apply_balance_delta_to_portfolio(
    portfolio_data: dict[str, Any],
    acc_id: str | None,
    delta: float,
    *,
    allow_overdraft: bool = True,
    expected_overdraft_loan_id: str | None = None,
) -> dict[str, Any]:
    result = {
        "applied_delta": 0.0,
        "balance_delta_version": BALANCE_DELTA_VERSION,
        "changed": False,
    }
    if not acc_id:
        return result

    if expected_overdraft_loan_id:
        pair = _validate_overdraft_pair(
            portfolio_data,
            acc_id,
            expected_loan_id=expected_overdraft_loan_id,
        )
        if abs(delta) < 1e-6:
            return result
        if pair is None:
            raise BalanceConflictError("v3 거래 당시의 마이너스통장 관계를 확인할 수 없습니다.")
        return _apply_overdraft_net_delta(pair[0], pair[1], delta)

    if abs(delta) < 1e-6:
        return result

    bank = next(
        (item for item in portfolio_data.get("bank_accounts", []) if item.get("id") == acc_id),
        None,
    )
    if bank is not None:
        if allow_overdraft:
            pair = _validate_overdraft_pair(
                portfolio_data,
                acc_id,
            )
            if pair is not None:
                return _apply_overdraft_net_delta(pair[0], pair[1], delta)
        current = float(bank.get("balance") or 0.0)
        new_balance = max(0.0, current + delta)
        bank["balance"] = new_balance
        bank["updated_at"] = datetime.now().astimezone().isoformat()
        result["applied_delta"] = new_balance - current
        result["changed"] = abs(result["applied_delta"]) >= 1e-6
        return result

    for saving in portfolio_data.get("savings_accounts", []):
        if saving.get("id") == acc_id:
            current = float(saving.get("balance") or 0.0)
            new_balance = max(0.0, current + delta)
            saving["balance"] = new_balance
            saving["updated_at"] = datetime.now().astimezone().isoformat()
            result["applied_delta"] = new_balance - current
            result["changed"] = abs(result["applied_delta"]) >= 1e-6
            return result

    for account in portfolio_data.get("accounts", []):
        if account.get("id") == acc_id:
            settings = portfolio_data.setdefault("settings", {})
            cash_balances = settings.setdefault("cash_balances", {})
            account_cash = cash_balances.setdefault(acc_id, {})
            if not isinstance(account_cash, dict):
                account_cash = {}
                cash_balances[acc_id] = account_cash
            current = float(
                account_cash.get("KRW")
                if account_cash.get("KRW") is not None
                else account_cash.get("krw", account.get("cash", 0.0))
                or 0.0
            )
            new_balance = max(0.0, current + delta)
            account["cash"] = new_balance
            account_cash["KRW"] = new_balance
            result["applied_delta"] = new_balance - current
            result["changed"] = abs(result["applied_delta"]) >= 1e-6
            return result
    return result


def _apply_account_balance_delta(
    acc_id: str | None,
    delta: float,
    username: str | None = None,
) -> float:
    """Adjust one linked account immediately; retained for v2-compatible callers."""
    from app.services.portfolio import read_portfolio, write_portfolio

    portfolio_data = read_portfolio(username)
    result = _apply_balance_delta_to_portfolio(portfolio_data, acc_id, delta)
    if result["changed"]:
        write_portfolio(portfolio_data, username)
    return float(result["applied_delta"])


def _commit_ledger_and_portfolio(
    ledger_data: dict[str, Any],
    username: str | None,
    *,
    portfolio_before: dict[str, Any] | None = None,
    portfolio_after: dict[str, Any] | None = None,
) -> None:
    """Persist a coordinated change and restore portfolio data if ledger save fails."""
    if portfolio_after is None:
        write_ledger(ledger_data, username=username)
        return

    from app.services.portfolio import write_portfolio

    write_portfolio(portfolio_after, username)
    try:
        write_ledger(ledger_data, username=username)
    except Exception as ledger_error:
        try:
            if portfolio_before is not None:
                write_portfolio(portfolio_before, username)
        except Exception as rollback_error:
            raise PersistenceConsistencyError(
                "ledger 저장 실패 후 portfolio 원복에도 실패했습니다. 수동 확인이 필요합니다."
            ) from rollback_error
        raise ledger_error


def _set_balance_metadata(transaction: dict[str, Any], result: dict[str, Any]) -> None:
    transaction["applied_delta"] = float(result.get("applied_delta") or 0.0)
    transaction["balance_delta_version"] = int(
        result.get("balance_delta_version") or BALANCE_DELTA_VERSION
    )
    effect = result.get("balance_effect")
    if isinstance(effect, dict):
        transaction["balance_effect"] = effect
    else:
        transaction.pop("balance_effect", None)


def _get_v3_balance_effect(transaction: dict[str, Any]) -> dict[str, Any]:
    effect = transaction.get("balance_effect")
    if not isinstance(effect, dict):
        raise BalanceConflictError("v3 거래의 잔액 반영 정보를 확인할 수 없습니다.")
    bank_account_id = str(effect.get("bank_account_id") or "").strip()
    loan_id = str(effect.get("overdraft_loan_id") or "").strip()
    if not bank_account_id or not loan_id:
        raise BalanceConflictError("v3 거래의 계좌 관계 정보가 불완전합니다.")
    if str(transaction.get("account_id") or "").strip() != bank_account_id:
        raise BalanceConflictError("v3 거래의 연결 계좌 정보가 변경되어 안전하게 처리할 수 없습니다.")
    try:
        net_delta = float(effect["net_delta"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BalanceConflictError("v3 거래의 순잔액 반영값을 확인할 수 없습니다.") from exc
    if not math.isfinite(net_delta):
        raise BalanceConflictError("v3 거래의 순잔액 반영값이 유효하지 않습니다.")
    return {
        "bank_account_id": bank_account_id,
        "overdraft_loan_id": loan_id,
        "net_delta": net_delta,
    }


def _get_reversible_applied_delta(transaction: dict[str, Any]) -> float:
    """Return a verified delta, refusing ambiguous legacy balance changes."""
    account_id = str(transaction.get("account_id") or "").strip()
    if not account_id:
        return 0.0
    if "applied_delta" not in transaction:
        raise LegacyBalanceDeltaError(
            "이 거래는 과거 잔액 반영값을 확인할 수 없어 안전하게 수정하거나 삭제할 수 없습니다."
        )
    try:
        applied_delta = float(transaction.get("applied_delta") or 0.0)
    except (TypeError, ValueError) as exc:
        raise LegacyBalanceDeltaError(
            "이 거래는 과거 잔액 반영값을 확인할 수 없어 안전하게 수정하거나 삭제할 수 없습니다."
        ) from exc
    if abs(applied_delta) < 1e-6:
        return 0.0
    if transaction.get("balance_delta_version") != BALANCE_DELTA_VERSION:
        raise LegacyBalanceDeltaError(
            "이 거래는 구버전 잔액 반영값을 사용하므로 계좌 잔액 확인 후 처리해야 합니다."
        )
    return applied_delta


# ---------------------------------------------------------------------------
# Credit / Debit Cards Management & Billing Settlement
# ---------------------------------------------------------------------------

def get_cards(username: str | None = None, owner: str = "모두") -> list[dict[str, Any]]:
    data = read_ledger(username=username)
    cards = data.get("cards", [])
    if owner and owner != "모두":
        cards = [c for c in cards if c.get("owner") == owner or c.get("owner") == "모두"]

    txs = data.get("transactions", [])
    result = []
    for c in cards:
        cid = c.get("id")
        unpaid_txs = [
            t for t in txs
            if t.get("card_id") == cid and t.get("type") == "expense" and not t.get("is_settled", False)
        ]
        unpaid_amount = sum(float(t.get("amount") or 0.0) for t in unpaid_txs)
        c_copy = dict(c)
        c_copy["unpaid_amount"] = unpaid_amount
        c_copy["unpaid_count"] = len(unpaid_txs)
        result.append(c_copy)
    return result


def create_card(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    data = read_ledger(username=username)
    cid = payload.get("id") or str(uuid.uuid4())
    card = {
        "id": cid,
        "card_company": str(payload.get("card_company") or "신용카드").strip(),
        "card_name": str(payload.get("card_name") or "신용카드").strip(),
        "card_type": str(payload.get("card_type") or "credit").strip(),
        "owner": str(payload.get("owner") or "모두").strip(),
        "payment_day": max(1, min(31, int(payload.get("payment_day") or 14))),
        "linked_account_id": str(payload.get("linked_account_id") or "").strip(),
        "linked_account_name": str(payload.get("linked_account_name") or "").strip(),
        "statement_period": str(payload.get("statement_period") or "").strip(),
        "memo": str(payload.get("memo") or "").strip(),
        "created_at": datetime.now().isoformat(),
    }
    data.setdefault("cards", []).append(card)
    write_ledger(data, username=username)
    card["unpaid_amount"] = 0.0
    card["unpaid_count"] = 0
    return card


def update_card(card_id: str, payload: dict[str, Any], username: str | None = None) -> dict[str, Any] | None:
    data = read_ledger(username=username)
    for idx, c in enumerate(data.get("cards", [])):
        if c.get("id") == card_id:
            for k in ["card_company", "card_name", "card_type", "owner", "linked_account_id", "linked_account_name", "statement_period", "memo"]:
                if k in payload:
                    c[k] = str(payload[k]).strip() if payload[k] is not None else ""
            if "payment_day" in payload:
                c["payment_day"] = max(1, min(31, int(payload["payment_day"] or 14)))
            c["updated_at"] = datetime.now().isoformat()
            data["cards"][idx] = c
            write_ledger(data, username=username)
            return c
    return None


def delete_card(card_id: str, username: str | None = None) -> bool:
    data = read_ledger(username=username)
    before = len(data.get("cards", []))
    data["cards"] = [c for c in data.get("cards", []) if c.get("id") != card_id]
    if before != len(data["cards"]):
        write_ledger(data, username=username)
        return True
    return False


def settle_card_payment(card_id: str, payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    data = read_ledger(username=username)
    target_card = next((c for c in data.get("cards", []) if c.get("id") == card_id), None)
    if not target_card:
        raise ValueError("신용카드를 찾을 수 없습니다.")

    acc_id = str(payload.get("account_id") or target_card.get("linked_account_id") or "").strip()
    acc_name = str(payload.get("account_name") or target_card.get("linked_account_name") or "").strip()
    pay_date = str(payload.get("date") or date.today().isoformat())

    unpaid_txs = [
        t for t in data.get("transactions", [])
        if t.get("card_id") == card_id and t.get("type") == "expense" and not t.get("is_settled", False)
    ]
    auto_sum = sum(float(t.get("amount") or 0.0) for t in unpaid_txs)
    amount_to_pay = float(payload.get("amount") or auto_sum)

    if amount_to_pay <= 0:
        raise ValueError("결제할 카드 청구 금액이 없습니다 (0원).")

    # 1. 은행 계좌에서 카드 대금 출금 차감 (저장은 ledger와 함께 조정)
    balance_result: dict[str, Any] = {
        "applied_delta": 0.0,
        "balance_delta_version": BALANCE_DELTA_VERSION,
        "changed": False,
    }
    portfolio_before = None
    portfolio_after = None
    if acc_id:
        from app.services.portfolio import read_portfolio

        portfolio_after = read_portfolio(username)
        portfolio_before = deepcopy(portfolio_after)
        balance_result = _apply_balance_delta_to_portfolio(
            portfolio_after,
            acc_id,
            -amount_to_pay,
        )

    # 2. 가계부에 카드대금결제 거래 생성
    settle_tx_id = str(uuid.uuid4())
    settle_tx = {
        "id": settle_tx_id,
        "date": pay_date,
        "type": "transfer",
        "category": "카드대금결제",
        "amount": amount_to_pay,
        "owner": target_card.get("owner", "모두"),
        "pay_method": f"계좌출금 ({acc_name})" if acc_name else "계좌출금",
        "account_id": acc_id,
        "account_name": acc_name,
        "merchant": f"[{target_card.get('card_name', '신용카드')}] 카드대금 결제",
        "memo": f"{len(unpaid_txs)}건 카드 이용대금 결제 완료",
        "is_recurring": False,
        "created_at": datetime.now().isoformat(),
    }
    _set_balance_metadata(settle_tx, balance_result)
    data.setdefault("transactions", []).append(settle_tx)

    # 3. 해당 카드 미결제 거래들을 정산 완료(settled) 처리하여 카드 누적액 리셋!
    now_iso = datetime.now().isoformat()
    for t in unpaid_txs:
        t["is_settled"] = True
        t["settled_at"] = now_iso
        t["settled_tx_id"] = settle_tx_id

    _commit_ledger_and_portfolio(
        data,
        username,
        portfolio_before=portfolio_before if balance_result["changed"] else None,
        portfolio_after=portfolio_after if balance_result["changed"] else None,
    )
    return {
        "message": f"[{target_card.get('card_name')}] 카드대금 ₩{int(amount_to_pay):,}원이 결제 처리되었습니다.",
        "settled_amount": amount_to_pay,
        "settled_count": len(unpaid_txs),
        "transaction": settle_tx,
    }


def add_transaction(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    data = read_ledger(username=username)
    tx_id = payload.get("id") or str(uuid.uuid4())
    tx_type = str(payload.get("type") or "expense")
    amount = max(0.0, float(payload.get("amount") or 0.0))
    linked_acc_id = str(payload.get("account_id") or "").strip()
    linked_acc_name = str(payload.get("account_name") or "").strip()
    card_id = str(payload.get("card_id") or "").strip()
    card_name = str(payload.get("card_name") or "").strip()
    is_card = bool(card_id or payload.get("is_card_payment", False))

    # Calculate delta for account balance
    # 신용카드 지출인 경우 즉시 은행 계좌를 차감하지 않고 카드에 누적
    balance_result: dict[str, Any] = {
        "applied_delta": 0.0,
        "balance_delta_version": BALANCE_DELTA_VERSION,
        "changed": False,
    }
    portfolio_before = None
    portfolio_after = None
    apply_to_account = bool(payload.get("apply_to_account", False) or linked_acc_id)
    if apply_to_account and linked_acc_id and amount > 0 and not is_card:
        from app.services.portfolio import read_portfolio

        requested_delta = amount if tx_type == "income" else -amount
        portfolio_after = read_portfolio(username)
        portfolio_before = deepcopy(portfolio_after)
        balance_result = _apply_balance_delta_to_portfolio(
            portfolio_after,
            linked_acc_id,
            requested_delta,
        )

    tx = {
        "id": tx_id,
        "date": str(payload.get("date") or date.today().isoformat()),
        "type": tx_type,
        "amount": amount,
        "category": str(payload.get("category") or "식비/외식"),
        "owner": str(payload.get("owner") or "모두"),
        "pay_method": str(payload.get("pay_method") or (card_name if is_card else "신용/체크카드")),
        "card_id": card_id,
        "card_name": card_name,
        "is_card_payment": is_card,
        "is_settled": False if is_card else True,
        "account_id": linked_acc_id,
        "account_name": linked_acc_name,
        "merchant": str(payload.get("merchant") or payload.get("description") or "").strip(),
        "memo": str(payload.get("memo") or "").strip(),
        "is_recurring": bool(payload.get("is_recurring", False)),
        "created_at": datetime.now().isoformat(),
    }
    _set_balance_metadata(tx, balance_result)
    data["transactions"].append(tx)
    _commit_ledger_and_portfolio(
        data,
        username,
        portfolio_before=portfolio_before if balance_result["changed"] else None,
        portfolio_after=portfolio_after if balance_result["changed"] else None,
    )
    return tx


def update_transaction(tx_id: str, payload: dict[str, Any], username: str | None = None) -> dict[str, Any] | None:
    data = read_ledger(username=username)
    for idx, tx in enumerate(data.get("transactions", [])):
        if tx.get("id") == tx_id:
            old_version = tx.get("balance_delta_version")
            old_v3_effect = None
            old_delta = 0.0
            if old_version == OVERDRAFT_BALANCE_DELTA_VERSION:
                old_v3_effect = _get_v3_balance_effect(tx)
                old_delta = old_v3_effect["net_delta"]
            else:
                old_delta = _get_reversible_applied_delta(tx)
            old_acc_id = str(tx.get("account_id") or "").strip()

            updated_tx = deepcopy(tx)
            for k in ["date", "type", "category", "owner", "pay_method", "card_id", "card_name", "is_card_payment", "is_settled", "account_id", "account_name", "merchant", "memo", "is_recurring"]:
                if k in payload:
                    if k in ["is_recurring", "is_card_payment", "is_settled"]:
                        updated_tx[k] = bool(payload[k])
                    else:
                        updated_tx[k] = str(payload[k]).strip() if payload[k] is not None else ""
            if "amount" in payload:
                updated_tx["amount"] = max(0.0, float(payload["amount"]))

            new_acc_id = str(updated_tx.get("account_id") or "").strip()
            new_amount = float(updated_tx.get("amount") or 0.0)
            new_type = str(updated_tx.get("type") or "expense")
            is_card = bool(updated_tx.get("card_id") or updated_tx.get("is_card_payment", False))
            apply_to_account = bool(payload.get("apply_to_account", False) or new_acc_id)

            portfolio_before = None
            portfolio_after = None
            needs_old_balance = bool(
                old_acc_id and (old_v3_effect is not None or abs(old_delta) > 1e-6)
            )
            needs_new_balance = bool(
                apply_to_account and new_acc_id and new_amount > 0 and not is_card
            )
            if needs_old_balance or needs_new_balance:
                from app.services.portfolio import read_portfolio

                portfolio_after = read_portfolio(username)
                portfolio_before = deepcopy(portfolio_after)

            # Same-pair edits are one net adjustment. Validating an intermediate
            # reversal can reject a valid edit when later spending used the income.
            same_pair_edit = bool(old_v3_effect is not None and needs_new_balance
                                  and new_acc_id == old_acc_id)
            combined_result = None
            if same_pair_edit:
                pair = _validate_overdraft_pair(
                    portfolio_after, old_acc_id,
                    expected_loan_id=old_v3_effect["overdraft_loan_id"],
                )
                requested_delta = new_amount if new_type == "income" else -new_amount
                combined_result = _apply_overdraft_net_delta(
                    pair[0], pair[1], requested_delta - old_delta,
                )
                combined_result["applied_delta"] = requested_delta
                combined_result["balance_effect"]["net_delta"] = requested_delta
                # Component audit values describe the actual edit, not a replay
                # of the historical transaction. Only net_delta is reversible.
                combined_result["balance_effect"]["audit_operation"] = "update"

            if needs_old_balance and portfolio_after is not None and not same_pair_edit:
                if old_v3_effect is not None:
                    _apply_balance_delta_to_portfolio(
                        portfolio_after,
                        old_v3_effect["bank_account_id"],
                        -old_v3_effect["net_delta"],
                        expected_overdraft_loan_id=old_v3_effect["overdraft_loan_id"],
                    )
                else:
                    _apply_balance_delta_to_portfolio(
                        portfolio_after,
                        old_acc_id,
                        -old_delta,
                        allow_overdraft=False,
                    )

            new_result: dict[str, Any] = {
                "applied_delta": 0.0,
                "balance_delta_version": BALANCE_DELTA_VERSION,
                "changed": False,
            }
            if combined_result is not None:
                new_result = combined_result
            elif apply_to_account and new_acc_id and new_amount > 0 and not is_card:
                requested_delta = new_amount if new_type == "income" else -new_amount
                if portfolio_after is None:
                    raise RuntimeError("계좌 잔액 변경 상태를 준비하지 못했습니다.")
                new_result = _apply_balance_delta_to_portfolio(
                    portfolio_after,
                    new_acc_id,
                    requested_delta,
                    allow_overdraft=old_version == OVERDRAFT_BALANCE_DELTA_VERSION,
                )

            _set_balance_metadata(updated_tx, new_result)
            updated_tx["updated_at"] = datetime.now().isoformat()
            data["transactions"][idx] = updated_tx
            _commit_ledger_and_portfolio(
                data,
                username,
                portfolio_before=portfolio_before,
                portfolio_after=portfolio_after,
            )
            return updated_tx
    return None


def delete_transaction(tx_id: str, username: str | None = None) -> bool:
    data = read_ledger(username=username)
    before = len(data.get("transactions", []))
    target_tx = next((t for t in data.get("transactions", []) if t.get("id") == tx_id), None)

    portfolio_before = None
    portfolio_after = None
    # Rollback account balance delta if existed, using net position for v3.
    if target_tx:
        old_version = target_tx.get("balance_delta_version")
        old_v3_effect = None
        if old_version == OVERDRAFT_BALANCE_DELTA_VERSION:
            old_v3_effect = _get_v3_balance_effect(target_tx)
            old_delta = old_v3_effect["net_delta"]
        else:
            old_delta = _get_reversible_applied_delta(target_tx)
        old_acc_id = str(target_tx.get("account_id") or "").strip()
        if old_acc_id and (old_v3_effect is not None or abs(old_delta) > 1e-6):
            from app.services.portfolio import read_portfolio

            portfolio_after = read_portfolio(username)
            portfolio_before = deepcopy(portfolio_after)
            if old_v3_effect is not None:
                _apply_balance_delta_to_portfolio(
                    portfolio_after,
                    old_v3_effect["bank_account_id"],
                    -old_v3_effect["net_delta"],
                    expected_overdraft_loan_id=old_v3_effect["overdraft_loan_id"],
                )
            else:
                _apply_balance_delta_to_portfolio(
                    portfolio_after,
                    old_acc_id,
                    -old_delta,
                    allow_overdraft=False,
                )

    data["transactions"] = [t for t in data.get("transactions", []) if t.get("id") != tx_id]
    after = len(data["transactions"])
    if before != after:
        _commit_ledger_and_portfolio(
            data,
            username,
            portfolio_before=portfolio_before,
            portfolio_after=portfolio_after,
        )
        return True
    return False


def add_recurring(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    data = read_ledger(username=username)
    rec_id = payload.get("id") or str(uuid.uuid4())
    rec = {
        "id": rec_id,
        "name": str(payload.get("name") or "고정지출").strip(),
        "type": str(payload.get("type") or "expense"),
        "amount": max(0.0, float(payload.get("amount") or 0.0)),
        "day_of_month": max(1, min(31, int(payload.get("day_of_month") or 1))),
        "category": str(payload.get("category") or "주거/통신"),
        "owner": str(payload.get("owner") or "모두"),
        "pay_method": str(payload.get("pay_method") or "자동이체"),
        "linked_account_id": str(payload.get("linked_account_id") or "").strip(),
        "linked_account_name": str(payload.get("linked_account_name") or "").strip(),
        "auto_deduct": bool(payload.get("auto_deduct", True)),
        "last_deducted_date": str(payload.get("last_deducted_date") or "").strip(),
        "memo": str(payload.get("memo") or "").strip(),
        "active": bool(payload.get("active", True)),
    }
    data["recurring"].append(rec)
    # 등록 즉시 오늘 이전 이체일인 경우 자동 출금 처리 시도
    process_recurring_deductions(username=username, pending_data=data)
    return rec


def edit_recurring(rec_id: str, payload: dict[str, Any], username: str | None = None) -> dict[str, Any] | None:
    data = read_ledger(username=username)
    for idx, r in enumerate(data.get("recurring", [])):
        if r.get("id") == rec_id:
            r["name"] = str(payload.get("name") or r.get("name")).strip()
            r["amount"] = max(0.0, float(payload.get("amount") if "amount" in payload else r.get("amount", 0)))
            r["day_of_month"] = max(1, min(31, int(payload.get("day_of_month") if "day_of_month" in payload else r.get("day_of_month", 1))))
            r["category"] = str(payload.get("category") or r.get("category"))
            r["owner"] = str(payload.get("owner") or r.get("owner"))
            r["pay_method"] = str(payload.get("pay_method") or r.get("pay_method"))
            if "linked_account_id" in payload:
                r["linked_account_id"] = str(payload.get("linked_account_id") or "").strip()
            if "linked_account_name" in payload:
                r["linked_account_name"] = str(payload.get("linked_account_name") or "").strip()
            if "auto_deduct" in payload:
                r["auto_deduct"] = bool(payload.get("auto_deduct"))
            if "memo" in payload:
                r["memo"] = str(payload.get("memo") or "").strip()
            if "active" in payload:
                r["active"] = bool(payload.get("active"))
            
            data["recurring"][idx] = r
            process_recurring_deductions(username=username, pending_data=data)
            return r
    return None


def delete_recurring(rec_id: str, username: str | None = None) -> bool:
    data = read_ledger(username=username)
    before = len(data.get("recurring", []))
    data["recurring"] = [r for r in data.get("recurring", []) if r.get("id") != rec_id]
    after = len(data["recurring"])
    if before != after:
        write_ledger(data, username=username)
        return True
    return False


def process_recurring_deductions(
    username: str | None = None, *, pending_data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """당월 지정일에 도래한 자동이체 고정지출을 연동 통장에서 자동 출금하고 가계부에 기록합니다."""
    import calendar
    data = pending_data if pending_data is not None else read_ledger(username=username)
    today = date.today()
    cur_year = today.year
    cur_month = today.month
    cur_prefix = f"{cur_year:04d}-{cur_month:02d}"
    _, max_day = calendar.monthrange(cur_year, cur_month)

    processed = []
    has_changes = False
    portfolio_before = None
    portfolio_after = None
    portfolio_changed = False

    for rec in data.get("recurring", []):
        if not rec.get("active", True):
            continue
        if not rec.get("auto_deduct", False):
            continue
        linked_acc_id = str(rec.get("linked_account_id") or "").strip()
        if not linked_acc_id:
            continue
        amount = float(rec.get("amount") or 0.0)
        if amount <= 0:
            continue

        target_day = max(1, min(max_day, int(rec.get("day_of_month") or 1)))
        due_date = date(cur_year, cur_month, target_day)

        # 오늘 날짜가 지정일 이상이고, 당월 아직 출금되지 않은 경우
        if today >= due_date:
            last_deducted = str(rec.get("last_deducted_date") or "")
            if not last_deducted.startswith(cur_prefix):
                # 1. 연동 계좌 잔액 차감 (모든 due 항목 검증 후 한 번에 저장)
                if portfolio_after is None:
                    from app.services.portfolio import read_portfolio

                    portfolio_after = read_portfolio(username)
                    portfolio_before = deepcopy(portfolio_after)
                balance_result = _apply_balance_delta_to_portfolio(
                    portfolio_after,
                    linked_acc_id,
                    -amount,
                )
                portfolio_changed = portfolio_changed or bool(balance_result["changed"])
                balance_deducted = abs(float(balance_result["applied_delta"])) > 1e-6

                # 2. 가계부 지출 내역 1건 생성
                tx_date_str = due_date.isoformat()
                acc_name = str(rec.get("linked_account_name") or "연동 통장").strip()
                rec_name = str(rec.get("name") or "정기 고정지출").strip()

                tx = {
                    "id": str(uuid.uuid4()),
                    "date": tx_date_str,
                    "type": str(rec.get("type") or "expense"),
                    "amount": amount,
                    "category": str(rec.get("category") or "주거/통신"),
                    "owner": str(rec.get("owner") or "모두"),
                    "pay_method": str(rec.get("pay_method") or "자동이체"),
                    "account_id": linked_acc_id,
                    "account_name": acc_name,
                    "merchant": rec_name,
                    "memo": f"[정기 자동이체] {rec_name}",
                    "is_recurring": True,
                    "recurring_id": rec.get("id"),
                    "created_at": datetime.now().isoformat(),
                }
                _set_balance_metadata(tx, balance_result)
                data.setdefault("transactions", []).append(tx)
                rec["last_deducted_date"] = tx_date_str
                processed.append({
                    "recurring_id": rec.get("id"),
                    "name": rec_name,
                    "amount": amount,
                    "account_name": acc_name,
                    "deducted_date": tx_date_str,
                    "balance_deducted": balance_deducted,
                })
                has_changes = True

    if has_changes or pending_data is not None:
        _commit_ledger_and_portfolio(
            data,
            username,
            portfolio_before=portfolio_before if portfolio_changed else None,
            portfolio_after=portfolio_after if portfolio_changed else None,
        )

    return processed


def import_ledger_from_file_bytes(
    file_bytes: bytes,
    filename: str,
    default_owner: str = "모두",
    username: str | None = None,
) -> int:
    """Parse Excel (.xlsx, .xls) or CSV files and append to transactions."""
    import io
    import csv
    import openpyxl

    rows: list[list[Any]] = []
    fname = filename.lower()

    if fname.endswith(".csv"):
        # UTF-8 or CP949 decoding
        decoded_text = ""
        for encoding in ["utf-8-sig", "utf-8", "cp949", "euc-kr"]:
            try:
                decoded_text = file_bytes.decode(encoding)
                break
            except Exception:
                continue
        if not decoded_text:
            raise ValueError("CSV 파일 인코딩을 해석할 수 없습니다.")
        reader = csv.reader(io.StringIO(decoded_text))
        rows = [list(r) for r in reader if any(r)]
    else:
        # Excel
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        ws = wb.active
        for row in ws.iter_rows(values_only=True):
            if any(row):
                rows.append(list(row))

    if not rows:
        raise ValueError("파일에 읽을 수 있는 데이터가 없습니다.")

    # 헤더 행 탐색 (최상위 5행 이내에서 일자, 가맹점/내용, 금액 매핑 검색)
    header_row_idx = -1
    col_map = {
        "date": -1,
        "merchant": -1,
        "amount": -1,
        "type": -1,
        "category": -1,
        "owner": -1,
        "pay_method": -1,
        "memo": -1,
    }

    for idx, r in enumerate(rows[:6]):
        str_row = [str(c or "").strip() for c in r]
        date_idx = next((i for i, c in enumerate(str_row) if any(k in c for k in ["일자", "거래일", "날짜", "date", "승인일"])), -1)
        amt_idx = next((i for i, c in enumerate(str_row) if any(k in c for k in ["금액", "amount", "이용금액", "승인금액", "출금액", "입금액"])), -1)
        merch_idx = next((i for i, c in enumerate(str_row) if any(k in c for k in ["가맹점", "내용", "적요", "상호", "merchant", "description", "거래내역"])), -1)

        if date_idx != -1 and (amt_idx != -1 or merch_idx != -1):
            header_row_idx = idx
            col_map["date"] = date_idx
            col_map["amount"] = amt_idx
            col_map["merchant"] = merch_idx
            col_map["type"] = next((i for i, c in enumerate(str_row) if any(k in c for k in ["구분", "type", "거래구분"])), -1)
            col_map["category"] = next((i for i, c in enumerate(str_row) if any(k in c for k in ["카테고리", "분류", "업종", "category"])), -1)
            col_map["owner"] = next((i for i, c in enumerate(str_row) if any(k in c for k in ["소유자", "이름", "작성자", "owner"])), -1)
            col_map["pay_method"] = next((i for i, c in enumerate(str_row) if any(k in c for k in ["결제", "카드", "수단", "출금처", "통장"])), -1)
            col_map["memo"] = next((i for i, c in enumerate(str_row) if any(k in c for k in ["메모", "비고", "memo", "note"])), -1)
            break

    if header_row_idx == -1:
        # 헤더가 없는 경우 위치 기반 폴백: [0:일자, 1:가맹점, 2:금액...]
        header_row_idx = 0
        col_map["date"] = 0
        col_map["merchant"] = 1
        col_map["amount"] = 2

    data_rows = rows[header_row_idx + 1 :]
    imported_count = 0
    tx_list_to_add = []

    for r in data_rows:
        if not r or all(c is None or str(c).strip() == "" for c in r):
            continue

        # 1. 일자 파싱
        raw_date = str(r[col_map["date"]] if col_map["date"] < len(r) and col_map["date"] != -1 else "").strip()
        if not raw_date:
            continue
        # 날짜 포맷 정리 (YYYYMMDD, YYYY.MM.DD, YYYY/MM/DD -> YYYY-MM-DD)
        clean_date = raw_date.replace(".", "-").replace("/", "-").replace(" ", "")
        if isinstance(r[col_map["date"]], (datetime, date)):
            clean_date = r[col_map["date"]].strftime("%Y-%m-%d")
        elif len(clean_date) == 8 and clean_date.isdigit():
            clean_date = f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:]}"
        elif len(clean_date) >= 10:
            clean_date = clean_date[:10]

        # 2. 내용/가맹점
        merchant = ""
        if col_map["merchant"] != -1 and col_map["merchant"] < len(r):
            merchant = str(r[col_map["merchant"]] or "").strip()

        # 3. 금액 파싱
        raw_amount = ""
        if col_map["amount"] != -1 and col_map["amount"] < len(r):
            raw_amount = str(r[col_map["amount"]] or "").replace(",", "").replace("₩", "").replace("원", "").replace(" ", "").strip()
        try:
            amount = abs(float(raw_amount)) if raw_amount else 0.0
        except ValueError:
            amount = 0.0

        if amount <= 0:
            continue

        # 4. 구분 및 카테고리
        raw_type = str(r[col_map["type"]] if col_map["type"] != -1 and col_map["type"] < len(r) else "").strip()
        is_income = "수입" in raw_type or "입금" in raw_type or "급여" in merchant or "배당" in merchant
        is_transfer = "이체" in raw_type or "저축" in raw_type or "환전" in raw_type
        tx_type = "income" if is_income else ("transfer" if is_transfer else "expense")

        category = ""
        if col_map["category"] != -1 and col_map["category"] < len(r):
            category = str(r[col_map["category"]] or "").strip()
        if not category:
            category = "급여/상여" if is_income else ("계좌이체/저축" if is_transfer else "식비/외식")

        # 5. 소유자
        owner = default_owner
        if col_map["owner"] != -1 and col_map["owner"] < len(r):
            val_owner = str(r[col_map["owner"]] or "").strip()
            if val_owner in ["아빠", "엄마", "자녀", "모두"]:
                owner = val_owner

        # 6. 결제수단 및 메모
        pay_method = "신용/체크카드"
        if col_map["pay_method"] != -1 and col_map["pay_method"] < len(r):
            pay_method = str(r[col_map["pay_method"]] or "").strip() or "신용/체크카드"

        memo = ""
        if col_map["memo"] != -1 and col_map["memo"] < len(r):
            memo = str(r[col_map["memo"]] or "").strip()

        tx = {
            "id": str(uuid.uuid4()),
            "date": clean_date,
            "type": tx_type,
            "amount": amount,
            "category": category,
            "owner": owner,
            "pay_method": pay_method,
            "account_id": "",
            "account_name": "",
            "applied_delta": 0.0,
            "balance_delta_version": BALANCE_DELTA_VERSION,
            "merchant": merchant or "카드이용",
            "memo": memo,
            "is_recurring": False,
            "created_at": datetime.now().isoformat(),
        }
        tx_list_to_add.append(tx)
        imported_count += 1

    if tx_list_to_add:
        ledger_data = read_ledger(username=username)
        ledger_data["transactions"].extend(tx_list_to_add)
        write_ledger(ledger_data, username=username)

    return imported_count
