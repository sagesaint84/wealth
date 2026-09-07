"""
절세 혜택 및 세액·소득공제 시뮬레이션 서비스
- 1. 노란우산공제 (소기업·소상공인 공제부금 소득공제)
- 2. 개인연금 (연금저축) & IRP 세액공제
- 3. ISA 만기 해지 후 연금계좌 전환 시 추가 세액공제
"""
from typing import Any
import math


# 노란우산공제 사업소득 구간별 법정 소득공제 한도
YELLOW_UMBRELLA_LIMITS = {
    "under_40m": 5_000_000,      # 사업소득 4,000만원 이하 (근로 총급여 7,000만원 이하) -> 500만원
    "40m_to_100m": 3_000_000,    # 사업소득 4,000만 ~ 1억원 이하 -> 300만원
    "over_100m": 2_000_000,      # 사업소득 1억원 초과 -> 200만원
}

# 기본 한계세율 (지방소득세 10% 포함)
DEFAULT_MARGINAL_RATES = {
    "under_40m": 16.5,     # 1,400만 ~ 5,000만원 구간 (15% + 1.5%)
    "40m_to_100m": 26.4,   # 5,000만 ~ 8,800만원 구간 (24% + 2.4%)
    "over_100m": 38.5,     # 8,800만 ~ 1.5억원 구간 (35% + 3.5%)
}


def calculate_yellow_umbrella_benefit(
    monthly_premium: float,
    annual_contribution: float | None = None,
    income_bracket: str = "40m_to_100m",
    custom_marginal_rate: float | None = None,
    yearly_contributions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    노란우산공제 연간 소득공제 대상 금액 및 예상 절세 세액(환급액)을 계산합니다.
    연도별 납입 이력(yearly_contributions)이 있는 경우 과거 연도별 절세액 및 누적 절세액을 함께 산출합니다.
    """
    bracket = income_bracket if income_bracket in YELLOW_UMBRELLA_LIMITS else "40m_to_100m"
    max_limit = YELLOW_UMBRELLA_LIMITS[bracket]

    annual_paid = float(annual_contribution) if annual_contribution is not None and annual_contribution > 0 else float(monthly_premium or 0) * 12.0
    deduction_amount = min(annual_paid, max_limit)

    rate = float(custom_marginal_rate) if custom_marginal_rate is not None and custom_marginal_rate > 0 else DEFAULT_MARGINAL_RATES.get(bracket, 26.4)
    tax_saved = math.floor(deduction_amount * (rate / 100.0))

    yearly_results = []
    cumulative_tax_saved = 0
    cumulative_deposit = 0

    if yearly_contributions:
        for yc in yearly_contributions:
            y_year = str(yc.get("year") or "").strip()
            y_dep = float(yc.get("deposit") or 0.0)
            y_deductible = yc.get("is_deductible") not in (False, "false", "0", 0)
            y_ded_target = min(y_dep, max_limit) if y_deductible else 0.0
            y_tax_saved = math.floor(y_ded_target * (rate / 100.0)) if y_deductible else 0.0

            yearly_results.append({
                "year": y_year,
                "deposit": round(y_dep),
                "is_deductible": bool(y_deductible),
                "deduction_target": round(y_ded_target),
                "tax_saved": round(y_tax_saved),
            })
            cumulative_deposit += y_dep
            cumulative_tax_saved += y_tax_saved
    else:
        cumulative_tax_saved = tax_saved
        cumulative_deposit = annual_paid

    return {
        "income_bracket": bracket,
        "max_limit": max_limit,
        "annual_paid": round(annual_paid),
        "deduction_amount": round(deduction_amount),
        "marginal_tax_rate": round(rate, 1),
        "tax_saved": round(tax_saved),
        "yearly_contributions": yearly_results,
        "cumulative_tax_saved": round(cumulative_tax_saved),
        "cumulative_deposit": round(cumulative_deposit),
    }


def calculate_pension_irp_benefit(
    annual_deposit: float,
    account_type: str = "pension_savings",  # "pension_savings" | "irp" | "pension_savings_non_deductible" | "irp_non_deductible"
    income_level: str = "low",               # "low" (<=5500만원: 16.5%) | "high" (>5500만원: 13.2%)
    isa_transfer_amount: float = 0.0,
    tax_deductible: bool = True,
    yearly_contributions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    개인연금(연금저축) 및 IRP의 세액공제 혜택과 ISA 만기 연금 전환 추가 공제액을 정밀 계산합니다.
    - 세액공제 신청 계좌: 연금저축 600만원 / IRP 900만원 한도
    - 세액공제 제외(미신청) 계좌: 기본 세액공제 대상액 0원 (인출 시 원금 비과세)
    - 연도별 납입 이력(yearly_contributions)이 있는 경우 각 연도별 절세액 및 누적 절세액을 산출합니다.
    """
    is_non_deductible = (
        not tax_deductible
        or account_type in ("pension_savings_non_deductible", "irp_non_deductible")
    )
    rate = 16.5 if income_level == "low" else 13.2

    dep = max(0.0, float(annual_deposit or 0.0))
    isa_tr = max(0.0, float(isa_transfer_amount or 0.0))
    base_limit = 0 if is_non_deductible else (6_000_000.0 if account_type == "pension_savings" else 9_000_000.0)

    if is_non_deductible:
        base_deduction_target = 0.0
    elif account_type in ("pension_savings",):
        base_deduction_target = min(dep, 6_000_000.0)
    elif account_type in ("irp",):
        base_deduction_target = min(dep, 9_000_000.0)
    else:
        base_deduction_target = 0.0

    isa_deduction_target = min(isa_tr * 0.10, 3_000_000.0)
    total_deduction_target = base_deduction_target + isa_deduction_target

    base_tax_refund = math.floor(base_deduction_target * (rate / 100.0))
    isa_tax_refund = math.floor(isa_deduction_target * (rate / 100.0))
    total_tax_refund = base_tax_refund + isa_tax_refund

    yearly_results = []
    cumulative_tax_saved = 0
    cumulative_deposit = 0

    if yearly_contributions:
        for yc in yearly_contributions:
            y_year = str(yc.get("year") or "").strip()
            y_dep = float(yc.get("deposit") or 0.0)
            y_deductible = yc.get("is_deductible") not in (False, "false", "0", 0)
            y_income_level = str(yc.get("income_level") or income_level or "low").strip()
            y_rate = 16.5 if y_income_level == "low" else 13.2
            y_limit = base_limit if y_deductible else 0.0
            y_ded_target = min(y_dep, y_limit) if y_deductible else 0.0
            y_tax_saved = math.floor(y_ded_target * (y_rate / 100.0)) if y_deductible else 0.0

            yearly_results.append({
                "year": y_year,
                "deposit": round(y_dep),
                "is_deductible": bool(y_deductible),
                "income_level": y_income_level,
                "rate": y_rate,
                "deduction_target": round(y_ded_target),
                "tax_saved": round(y_tax_saved),
            })
            cumulative_deposit += y_dep
            cumulative_tax_saved += y_tax_saved
    else:
        cumulative_tax_saved = total_tax_refund
        cumulative_deposit = dep

    return {
        "account_type": account_type,
        "tax_deductible": not is_non_deductible,
        "income_level": income_level,
        "credit_rate": rate,
        "annual_deposit": round(dep),
        "annual_max_deposit_limit": 18_000_000,
        "base_limit": round(base_limit),
        "base_deduction_target": round(base_deduction_target),
        "base_tax_refund": round(base_tax_refund),
        "isa_transfer_amount": round(isa_tr),
        "isa_deduction_target": round(isa_deduction_target),
        "isa_tax_refund": round(isa_tax_refund),
        "total_deduction_target": round(total_deduction_target),
        "total_tax_refund": round(total_tax_refund),
        "yearly_contributions": yearly_results,
        "cumulative_tax_saved": round(cumulative_tax_saved),
        "cumulative_deposit": round(cumulative_deposit),
    }


def get_total_tax_benefits(portfolio_data: dict[str, Any], owner: str | None = None) -> dict[str, Any]:
    """
    포트폴리오 내 모든 절세 상품(노란우산공제, 연금저축, IRP, ISA 전환)의
    연간 총 절세 환급 예상액을 종합 집계합니다.
    """
    insurances = portfolio_data.get("insurance_accounts", [])
    accounts = portfolio_data.get("accounts", [])

    if owner and owner != "모두":
        insurances = [i for i in insurances if (i.get("owner") or "모두") == owner]
        accounts = [a for a in accounts if (a.get("owner") or "모두") == owner]

    yellow_items = []
    total_yellow_deduction = 0
    total_yellow_tax_saved = 0

    for ins in insurances:
        ins_type = ins.get("insurance_type")
        prod_name = (ins.get("product_name") or "").lower()
        if ins_type == "yellow_umbrella" or "노란우산" in prod_name:
            monthly = float(ins.get("monthly_premium") or 0.0)
            bracket = ins.get("income_bracket") or "40m_to_100m"
            custom_rate = float(ins.get("marginal_tax_rate") or 0.0) if ins.get("marginal_tax_rate") else None
            b = calculate_yellow_umbrella_benefit(
                monthly, None, bracket, custom_rate, yearly_contributions=ins.get("yearly_contributions")
            )
            yellow_items.append({
                "id": ins.get("id"),
                "product_name": ins.get("product_name"),
                "owner": ins.get("owner", "모두"),
                "benefit": b,
            })
            total_yellow_deduction += b["deduction_amount"]
            total_yellow_tax_saved += b["tax_saved"]

    pension_items = []
    total_pension_deduction = 0
    total_pension_tax_refund = 0
    total_isa_transfer_amount = 0
    total_isa_tax_refund = 0

    for acc in accounts:
        acc_type = acc.get("account_type") or "general"
        acc_name = (acc.get("account_name") or acc.get("name") or "").lower()

        if acc_type == "general":
            if "연금" in acc_name or "pension" in acc_name:
                acc_type = "pension_savings"
            elif "irp" in acc_name or "개인형퇴직" in acc_name:
                acc_type = "irp"
            elif "isa" in acc_name:
                acc_type = "isa"

        is_tax_deductible = acc.get("tax_deductible", True)
        if acc.get("tax_deductible") is None or "tax_deductible" not in acc:
            if "공제x" in acc_name or "세액공제x" in acc_name or "비공제" in acc_name or "미공제" in acc_name or "공제제외" in acc_name or "공제 안" in acc_name or "공제안" in acc_name:
                is_tax_deductible = False

        if acc_type in ("pension_savings", "irp", "pension_savings_non_deductible", "irp_non_deductible"):
            deposit = float(acc.get("annual_deposit") or 0.0)
            income_lvl = acc.get("income_level") or "low"
            isa_tr = float(acc.get("isa_transfer_amount") or 0.0)

            b = calculate_pension_irp_benefit(
                deposit, acc_type, income_lvl, isa_tr, tax_deductible=is_tax_deductible, yearly_contributions=acc.get("yearly_contributions")
            )
            pension_items.append({
                "id": acc.get("id"),
                "account_name": acc.get("name") or acc.get("account_name"),
                "broker": acc.get("broker"),
                "owner": acc.get("owner", "모두"),
                "account_type": acc_type,
                "tax_deductible": is_tax_deductible,
                "benefit": b,
            })
            total_pension_deduction += b["base_deduction_target"]
            total_pension_tax_refund += b["base_tax_refund"]
            total_isa_transfer_amount += b["isa_transfer_amount"]
            total_isa_tax_refund += b["isa_tax_refund"]

    grand_total_refund = total_yellow_tax_saved + total_pension_tax_refund + total_isa_tax_refund
    grand_total_cumulative = sum(i["benefit"].get("cumulative_tax_saved", 0) for i in yellow_items) + sum(i["benefit"].get("cumulative_tax_saved", 0) for i in pension_items)

    return {
        "owner": owner or "모두",
        "grand_total_tax_benefit": grand_total_refund,
        "grand_total_cumulative_tax_benefit": grand_total_cumulative,
        "yellow_umbrella": {
            "items": yellow_items,
            "total_deduction": total_yellow_deduction,
            "total_tax_saved": total_yellow_tax_saved,
        },
        "pension_irp": {
            "items": pension_items,
            "total_deduction": total_pension_deduction,
            "total_tax_refund": total_pension_tax_refund,
            "total_isa_transfer_amount": total_isa_transfer_amount,
            "total_isa_tax_refund": total_isa_tax_refund,
        },
    }
