from __future__ import annotations

import json
import math
import uuid
from copy import deepcopy
from datetime import date, datetime
from typing import Any

from app.services.portfolio import read_portfolio, write_portfolio
from app.services.tax_benefit import calculate_yellow_umbrella_benefit, get_total_tax_benefits


def calculate_interest(
    saving_type: str,
    principal_or_monthly: float,
    interest_rate: float,
    duration_months: int,
    tax_type: str = "normal",
    current_paid_amount: float | None = None,
) -> dict[str, Any]:
    """
    정기예금 및 정기적금의 세전이자, 소득세, 세후이자, 만기지급액을 정밀 계산합니다.
    """
    rate = float(interest_rate or 0.0) / 100.0
    months = max(1, int(duration_months or 12))
    amt = float(principal_or_monthly or 0.0)

    if saving_type == "housing":
        cur_amt = float(current_paid_amount or 0.0) if current_paid_amount is not None and current_paid_amount > 0 else amt
        total_principal = cur_amt
        pre_tax_interest = total_principal * rate
    elif saving_type == "deposit":
        total_principal = amt
        pre_tax_interest = total_principal * rate * (months / 12.0)
    else:
        total_principal = amt * months
        pre_tax_interest = amt * rate * (months * (months + 1) / 24.0)

    if tax_type == "preferential":
        tax_rate = 0.014
    elif tax_type == "tax_free":
        tax_rate = 0.0
    else:
        tax_rate = 0.154

    tax_amount = math.floor(pre_tax_interest * tax_rate)
    after_tax_interest = pre_tax_interest - tax_amount
    maturity_total = total_principal + after_tax_interest

    return {
        "saving_type": saving_type,
        "total_principal": round(total_principal),
        "pre_tax_interest": round(pre_tax_interest),
        "tax_rate_percent": round(tax_rate * 100, 1),
        "tax_amount": round(tax_amount),
        "after_tax_interest": round(after_tax_interest),
        "maturity_total": round(maturity_total),
    }


def calculate_loan_interest(
    current_balance: float,
    interest_rate: float,
    repayment_type: str = "bullet",
    remaining_months: int = 12,
) -> dict[str, Any]:
    """대출의 월 예상 이자 및 상환액을 계산합니다."""
    balance = max(0.0, float(current_balance or 0.0))
    rate = max(0.0, float(interest_rate or 0.0)) / 100.0

    monthly_rate = rate / 12.0
    monthly_interest = round(balance * monthly_rate)

    monthly_principal = 0
    monthly_payment = monthly_interest

    if repayment_type == "amortizing" and remaining_months > 0 and balance > 0 and monthly_rate > 0:
        factor = (1.0 + monthly_rate) ** remaining_months
        monthly_payment = round(balance * (monthly_rate * factor) / (factor - 1.0))
        monthly_principal = max(0, monthly_payment - monthly_interest)
    elif repayment_type == "principal" and remaining_months > 0 and balance > 0:
        monthly_principal = round(balance / remaining_months)
        monthly_payment = monthly_principal + monthly_interest

    return {
        "current_balance": round(balance),
        "interest_rate": round(rate * 100, 2),
        "monthly_interest": monthly_interest,
        "monthly_principal": monthly_principal,
        "monthly_payment": monthly_payment,
        "repayment_type": repayment_type,
    }


def get_savings_data(username: str | None = None) -> dict[str, Any]:
    """사용자의 일반 은행 계좌, 예·적금 및 대출 목록을 조회하고 이자 및 진행률을 계산하여 반환합니다."""
    data = read_portfolio(username)
    bank_accounts = data.get("bank_accounts", [])
    savings_accounts = data.get("savings_accounts", [])

    today_dt = datetime.now().astimezone().date()

    enriched_savings = []
    total_savings_paid = 0.0
    total_savings_maturity = 0.0

    for sa in savings_accounts:
        item = deepcopy(sa)
        s_type = item.get("saving_type") or "deposit"
        rate = float(item.get("interest_rate") or 0.0)
        months = int(item.get("duration_months") or 12)
        tax = item.get("tax_type") or "normal"

        cur_val = float(item.get("current_paid_amount") or 0)
        if s_type == "housing":
            amount = float(item.get("monthly_amount") or 0.0)
            calc = calculate_interest(s_type, amount, rate, months, tax, current_paid_amount=cur_val)
        else:
            amount = float(item.get("target_amount") or 0.0) if s_type == "deposit" else float(item.get("monthly_amount") or 0.0)
            calc = calculate_interest(s_type, amount, rate, months, tax)
        item["calc"] = calc

        end_date_str = item.get("end_date") or ""
        d_day = None
        if end_date_str and s_type != "housing":
            try:
                end_dt = datetime.strptime(end_date_str[:10], "%Y-%m-%d").date()
                d_day = (end_dt - today_dt).days
            except ValueError:
                pass
        item["d_day"] = d_day

        start_date_str = item.get("start_date") or ""
        progress = 0
        if s_type == "housing" or not end_date_str:
            if start_date_str:
                try:
                    st_dt = datetime.strptime(start_date_str[:10], "%Y-%m-%d").date()
                    elapsed_months = max(1, (today_dt.year - st_dt.year) * 12 + today_dt.month - st_dt.month)
                    item["elapsed_months"] = elapsed_months
                except ValueError:
                    pass
            progress = 100
        elif start_date_str and end_date_str:
            try:
                st_dt = datetime.strptime(start_date_str[:10], "%Y-%m-%d").date()
                end_dt = datetime.strptime(end_date_str[:10], "%Y-%m-%d").date()
                total_days = (end_dt - st_dt).days
                elapsed_days = (today_dt - st_dt).days
                if total_days > 0:
                    progress = max(0, min(100, round((elapsed_days / total_days) * 100)))
            except ValueError:
                pass
        item["progress_percent"] = progress

        if cur_val <= 0:
            cur_val = calc["total_principal"] if item.get("saving_type") == "deposit" else 0

        item["current_value"] = cur_val
        total_savings_paid += cur_val
        total_savings_maturity += cur_val if s_type == "housing" else calc["maturity_total"]
        enriched_savings.append(item)

    enriched_banks = []
    total_bank_balance = 0.0
    total_positive_bank_balance = 0.0
    total_minus_bank_debt = 0.0
    minus_account_count = 0
    total_loan_monthly_interest = 0.0
    total_loan_limit = 0.0

    for b in bank_accounts:
        b_item = deepcopy(b)
        bal = float(b_item.get("balance") or 0.0)
        total_bank_balance += bal
        rate = float(b_item.get("interest_rate") or 0.0)
        limit = float(b_item.get("limit_amount") or 0.0)
        mat_date_str = b_item.get("maturity_date") or ""

        d_day = None
        if mat_date_str:
            try:
                mat_dt = datetime.strptime(mat_date_str[:10], "%Y-%m-%d").date()
                d_day = (mat_dt - today_dt).days
            except ValueError:
                pass
        b_item["d_day"] = d_day

        if bal < 0:
            debt = abs(bal)
            b_item["is_minus_account"] = True
            b_item["minus_debt"] = debt
            total_minus_bank_debt += debt
            minus_account_count += 1
            calc = calculate_loan_interest(debt, rate, "bullet", 12)
            b_item["calc"] = calc
            b_item["monthly_interest"] = calc["monthly_interest"]
            total_loan_monthly_interest += calc["monthly_interest"]
            total_loan_limit += limit
        else:
            b_item["is_minus_account"] = False
            b_item["minus_debt"] = 0.0
            b_item["monthly_interest"] = 0.0
            total_positive_bank_balance += bal
        enriched_banks.append(b_item)

    insurance_accounts = data.get("insurance_accounts", [])
    enriched_insurances = []
    total_insurance_monthly = 0.0
    total_insurance_paid = 0.0
    total_insurance_expected = 0.0

    for ins in insurance_accounts:
        item = deepcopy(ins)
        monthly = float(item.get("monthly_premium") or 0.0)
        paid = float(item.get("total_paid_amount") or 0.0)
        payout_type = item.get("payout_type") or "lump_sum"

        if payout_type == "monthly_pension":
            monthly_payout = float(item.get("monthly_payout") or 0.0)
            years = float(item.get("payout_duration_years") or 20.0)
            converted = round(monthly_payout * 12.0 * years)
            item["converted_total_asset"] = converted
            item["expected_amount"] = converted
            expected = float(converted)
        else:
            expected = float(item.get("expected_amount") or 0.0)
            item["converted_total_asset"] = expected

        total_insurance_monthly += monthly
        total_insurance_paid += paid
        total_insurance_expected += expected

        ins_type = item.get("insurance_type") or "protection"
        prod_name = (item.get("product_name") or "").lower()
        if ins_type == "yellow_umbrella" or "노란우산" in prod_name:
            bracket = item.get("income_bracket") or "40m_to_100m"
            custom_rate = float(item.get("marginal_tax_rate") or 0.0) if item.get("marginal_tax_rate") else None
            item["tax_benefit"] = calculate_yellow_umbrella_benefit(monthly, None, bracket, custom_rate)

        enriched_insurances.append(item)

    loan_accounts = data.get("loan_accounts", [])
    enriched_loans = []
    total_loan_balance = 0.0

    for loan in loan_accounts:
        item = deepcopy(loan)
        cur_bal = float(item.get("current_balance") or 0.0)
        rate = float(item.get("interest_rate") or 0.0)
        repay_type = item.get("repayment_type") or "bullet"
        limit = float(item.get("limit_amount") or 0.0)

        mat_date_str = item.get("maturity_date") or ""
        d_day = None
        if mat_date_str:
            try:
                mat_dt = datetime.strptime(mat_date_str[:10], "%Y-%m-%d").date()
                d_day = (mat_dt - today_dt).days
            except ValueError:
                pass
        item["d_day"] = d_day

        calc = calculate_loan_interest(cur_bal, rate, repay_type, 12)
        item["calc"] = calc
        item["monthly_interest"] = calc["monthly_interest"]
        item["monthly_payment"] = calc["monthly_payment"]

        total_loan_balance += cur_bal
        total_loan_monthly_interest += calc["monthly_interest"]
        total_loan_limit += limit
        enriched_loans.append(item)

    total_combined_debt = total_loan_balance + total_minus_bank_debt
    tax_benefits_summary = get_total_tax_benefits(data)

    return {
        "bank_accounts": enriched_banks,
        "savings_accounts": enriched_savings,
        "insurance_accounts": enriched_insurances,
        "loan_accounts": enriched_loans,
        "tax_benefits": tax_benefits_summary,
        "summary": {
            "bank_account_count": len(enriched_banks),
            "savings_account_count": len(enriched_savings),
            "insurance_account_count": len(enriched_insurances),
            "loan_account_count": len(enriched_loans),
            "minus_account_count": minus_account_count,
            "total_bank_balance": round(total_bank_balance),
            "total_positive_bank_balance": round(total_positive_bank_balance),
            "total_minus_bank_debt": round(total_minus_bank_debt),
            "total_savings_paid": round(total_savings_paid),
            "total_savings_maturity": round(total_savings_maturity),
            "total_cash_and_savings": round(total_bank_balance + total_savings_paid),
            "total_loan_balance": round(total_combined_debt),
            "total_pure_loan_balance": round(total_loan_balance),
            "total_loan_monthly_interest": round(total_loan_monthly_interest),
            "total_loan_limit": round(total_loan_limit),
            "net_bank_worth": round((total_bank_balance + total_savings_paid) - total_loan_balance),
            "total_insurance_monthly": round(total_insurance_monthly),
            "total_insurance_paid": round(total_insurance_paid),
            "total_insurance_expected": round(total_insurance_expected),
            "total_tax_benefits": tax_benefits_summary.get("grand_total_tax_benefit", 0),
        },
    }


def save_bank_account(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    """일반 은행 계좌를 생성하거나 수정합니다."""
    data = read_portfolio(username)
    accounts = data.setdefault("bank_accounts", [])

    acc_id = payload.get("id") or f"bank-{uuid.uuid4().hex[:12]}"
    existing_index = next((i for i, a in enumerate(accounts) if a.get("id") == acc_id), None)

    record = {
        "id": acc_id,
        "bank_name": (payload.get("bank_name") or "").strip() or "일반은행",
        "account_name": (payload.get("account_name") or "").strip() or "수시입출금",
        "account_number": (payload.get("account_number") or "").strip(),
        "owner": (payload.get("owner") or "모두").strip(),
        "balance": float(payload.get("balance") or 0.0),
        "limit_amount": max(0.0, float(payload.get("limit_amount") or 0.0)),
        "interest_rate": max(0.0, float(payload.get("interest_rate") or 0.0)),
        "maturity_date": (payload.get("maturity_date") or "").strip(),
        "currency": (payload.get("currency") or "KRW").upper(),
        "memo": (payload.get("memo") or "").strip(),
        "updated_at": datetime.now().astimezone().isoformat(),
    }

    if existing_index is not None:
        accounts[existing_index] = record
    else:
        record["created_at"] = record["updated_at"]
        accounts.append(record)

    write_portfolio(data, username)
    return record


def delete_bank_account(acc_id: str, username: str | None = None) -> bool:
    """일반 은행 계좌를 삭제합니다."""
    data = read_portfolio(username)
    accounts = data.get("bank_accounts", [])
    before = len(accounts)
    data["bank_accounts"] = [a for a in accounts if a.get("id") != acc_id]
    if len(data["bank_accounts"]) == before:
        return False
    write_portfolio(data, username)
    return True


def save_saving_account(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    """예·적금 상품 계좌를 생성하거나 수정합니다."""
    data = read_portfolio(username)
    savings = data.setdefault("savings_accounts", [])

    sid = payload.get("id") or f"saving-{uuid.uuid4().hex[:12]}"
    existing_index = next((i for i, s in enumerate(savings) if s.get("id") == sid), None)

    saving_type = payload.get("saving_type") or "deposit"
    duration = int(payload.get("duration_months") or 12)
    rate = float(payload.get("interest_rate") or 0.0)

    record = {
        "id": sid,
        "saving_type": saving_type,
        "bank_name": (payload.get("bank_name") or "").strip() or "은행",
        "product_name": (payload.get("product_name") or "").strip() or "정기예금/적금",
        "owner": (payload.get("owner") or "모두").strip(),
        "start_date": (payload.get("start_date") or "").strip(),
        "end_date": (payload.get("end_date") or "").strip(),
        "duration_months": duration,
        "interest_rate": rate,
        "tax_type": payload.get("tax_type") or "normal",
        "auto_transfer_day": int(payload.get("auto_transfer_day") or 0),
        "monthly_amount": float(payload.get("monthly_amount") or 0.0),
        "target_amount": float(payload.get("target_amount") or 0.0),
        "current_paid_amount": float(payload.get("current_paid_amount") or 0.0),
        "withdraw_account_id": (payload.get("withdraw_account_id") or "").strip(),
        "deposit_account_id": (payload.get("deposit_account_id") or "").strip(),
        "memo": (payload.get("memo") or "").strip(),
        "updated_at": datetime.now().astimezone().isoformat(),
    }

    if existing_index is not None:
        savings[existing_index] = record
    else:
        record["created_at"] = record["updated_at"]
        savings.append(record)

    write_portfolio(data, username)
    return record


def delete_saving_account(saving_id: str, username: str | None = None) -> bool:
    """예·적금 상품 계좌를 삭제합니다."""
    data = read_portfolio(username)
    savings = data.get("savings_accounts", [])
    before = len(savings)
    data["savings_accounts"] = [s for s in savings if s.get("id") != saving_id]
    if len(data["savings_accounts"]) == before:
        return False
    write_portfolio(data, username)
    return True


def save_insurance_account(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    """보험/연금/공제 계좌를 생성하거나 수정합니다."""
    data = read_portfolio(username)
    insurances = data.setdefault("insurance_accounts", [])

    ins_id = payload.get("id") or f"ins-{uuid.uuid4().hex[:12]}"
    existing_index = next((i for i, ins in enumerate(insurances) if ins.get("id") == ins_id), None)

    payout_type = (payload.get("payout_type") or "lump_sum").strip()
    monthly_payout = max(0.0, float(payload.get("monthly_payout") or 0.0))
    payout_duration_years = max(1.0, float(payload.get("payout_duration_years") or 20.0))

    if payout_type == "monthly_pension":
        converted_total = round(monthly_payout * 12.0 * payout_duration_years)
        expected_amount = float(converted_total)
    else:
        expected_amount = max(0.0, float(payload.get("expected_amount") or 0.0))
        converted_total = expected_amount

    record = {
        "id": ins_id,
        "insurance_type": (payload.get("insurance_type") or "protection").strip(),
        "company_name": (payload.get("company_name") or "").strip() or "보험/기관",
        "product_name": (payload.get("product_name") or "").strip() or "보험/공제 상품",
        "owner": (payload.get("owner") or "모두").strip(),
        "payment_status": (payload.get("payment_status") or "paying").strip(),
        "income_bracket": (payload.get("income_bracket") or "40m_to_100m").strip(),
        "marginal_tax_rate": float(payload.get("marginal_tax_rate") or 0.0) if payload.get("marginal_tax_rate") else None,
        "monthly_premium": max(0.0, float(payload.get("monthly_premium") or 0.0)),
        "total_paid_amount": max(0.0, float(payload.get("total_paid_amount") or 0.0)),
        "expected_amount": expected_amount,
        "payout_type": payout_type,
        "monthly_payout": monthly_payout,
        "payout_duration_years": payout_duration_years,
        "converted_total_asset": converted_total,
        "start_date": (payload.get("start_date") or "").strip(),
        "maturity_date": (payload.get("maturity_date") or "").strip(),
        "memo": (payload.get("memo") or "").strip(),
        "updated_at": datetime.now().astimezone().isoformat(),
    }

    if "yearly_contributions" in payload:
        record["yearly_contributions"] = payload.get("yearly_contributions") or []
    elif existing_index is not None and "yearly_contributions" in insurances[existing_index]:
        record["yearly_contributions"] = insurances[existing_index]["yearly_contributions"]

    if existing_index is not None:
        insurances[existing_index] = record
    else:
        record["created_at"] = record["updated_at"]
        insurances.append(record)

    write_portfolio(data, username)
    return record


def delete_insurance_account(ins_id: str, username: str | None = None) -> bool:
    """보험/연금/공제 계좌를 삭제합니다."""
    data = read_portfolio(username)
    insurances = data.get("insurance_accounts", [])
    before = len(insurances)
    data["insurance_accounts"] = [i for i in insurances if i.get("id") != ins_id]
    if len(data["insurance_accounts"]) == before:
        return False
    write_portfolio(data, username)
    return True


def save_loan_account(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    """대출·마이너스통장 계좌를 생성하거나 수정합니다."""
    data = read_portfolio(username)
    loans = data.setdefault("loan_accounts", [])

    lid = payload.get("id") or f"loan-{uuid.uuid4().hex[:12]}"
    existing_index = next((i for i, l in enumerate(loans) if l.get("id") == lid), None)

    loan_type = (payload.get("loan_type") or "minus").strip()
    balance = max(0.0, float(payload.get("current_balance") or 0.0))
    limit = max(0.0, float(payload.get("limit_amount") or 0.0))
    rate = max(0.0, float(payload.get("interest_rate") or 0.0))
    repay_type = (payload.get("repayment_type") or "bullet").strip()

    record = {
        "id": lid,
        "loan_type": loan_type,
        "bank_name": (payload.get("bank_name") or "").strip() or "은행",
        "product_name": (payload.get("product_name") or "").strip() or "마이너스통장/신용대출",
        "owner": (payload.get("owner") or "모두").strip(),
        "limit_amount": limit,
        "current_balance": balance,
        "interest_rate": rate,
        "repayment_type": repay_type,
        "start_date": (payload.get("start_date") or "").strip(),
        "maturity_date": (payload.get("maturity_date") or "").strip(),
        "linked_account_id": (payload.get("linked_account_id") or "").strip(),
        "linked_property_id": (payload.get("linked_property_id") or "").strip(),
        "memo": (payload.get("memo") or "").strip(),
        "updated_at": datetime.now().astimezone().isoformat(),
    }

    if existing_index is not None:
        loans[existing_index] = record
    else:
        record["created_at"] = record["updated_at"]
        loans.append(record)

    write_portfolio(data, username)
    return record


def delete_loan_account(loan_id: str, username: str | None = None) -> bool:
    """대출·마이너스통장 계좌를 삭제합니다."""
    data = read_portfolio(username)
    loans = data.get("loan_accounts", [])
    before = len(loans)
    data["loan_accounts"] = [l for l in loans if l.get("id") != loan_id]
    if len(data["loan_accounts"]) == before:
        return False
    write_portfolio(data, username)
    return True


