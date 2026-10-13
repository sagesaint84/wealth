"""Optional, user-entered pension analysis. No provider reads or financial totals."""
from __future__ import annotations

import calendar
import math
from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.services.financial_json import financial_rmw, read_financial_json, write_financial_json
from app.services import portfolio

SOURCES = {"agency", "tax_return", "user", "estimate", "unknown"}
MEMBERSHIPS = {"workplace", "regional", "voluntary", "continued", "unknown"}
ROLES = {"employee", "sole_proprietor", "corporate_representative", "unknown"}
INCOMES = {"employment", "business", "mixed", "other", "unknown"}
TAX_SOURCE = "https://t.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7667&mi=2227"
TAX_SOURCE_2026 = "https://www.nts.go.kr/nts/cm/cntnts/cntntsView.do?cntntsId=7675&mi=2232"
TAX_LAW_2026 = "https://law.go.kr/lsLinkCommonInfo.do?chrClsCd=010202&lsJoLnkSeq=1034035335"
TAX_VERIFIED_ON = "2026-10-13"
# NTS official page explicitly labels these attribution years. No extrapolation.
TAX_TABLES = (
    (2017, 2017, (12000000, 46000000, 88000000, 150000000, 500000000), (6, 15, 24, 35, 38, 40)),
    (2018, 2020, (12000000, 46000000, 88000000, 150000000, 300000000, 500000000), (6, 15, 24, 35, 38, 40, 42)),
    (2021, 2022, (12000000, 46000000, 88000000, 150000000, 300000000, 500000000, 1000000000), (6, 15, 24, 35, 38, 40, 42, 45)),
    (2023, 2025, (14000000, 50000000, 88000000, 150000000, 300000000, 500000000, 1000000000), (6, 15, 24, 35, 38, 40, 42, 45)),
    # Separately verified for attribution year 2026; never extend to 2027+.
    (2026, 2026, (14000000, 50000000, 88000000, 150000000, 300000000, 500000000, 1000000000), (6, 15, 24, 35, 38, 40, 42, 45)),
)
ANNUAL_MONEY = ("agency_paid", "personal_paid", "employer_paid", "unpaid", "future_expected", "deductible_amount")
TAX_MONEY = ("gross_salary", "business_revenue", "business_income", "expenses", "taxable_before", "allowed_deduction", "actual_tax_saving")
YEAR_DAYS = 365.2425


class PensionConflict(ValueError):
    pass


def money(value: Any, *, optional: bool = True) -> float | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1e15:
        raise ValueError("금액은 유효한 0 이상 숫자 또는 미확인(null)이어야 합니다.")
    return float(value)


def business_income(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1e15:
        raise ValueError("사업소득금액은 유효한 참고값 또는 미확인이어야 합니다.")
    return float(value)


def integer(value: Any, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError("연도·월·revision 범위가 올바르지 않습니다.")
    return value


def iso_date(value: Any) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("날짜는 실제 YYYY-MM-DD 날짜여야 합니다.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("날짜는 실제 YYYY-MM-DD 날짜여야 합니다.") from exc
    if parsed.isoformat() != value or not 1900 <= parsed.year <= 2200:
        raise ValueError("분석 날짜 범위는 1900~2200년입니다.")
    return parsed


def choice(value: Any, options: set[str], default: str = "unknown") -> str:
    value = default if value is None else value
    if not isinstance(value, str) or value not in options:
        raise ValueError("선택값이 올바르지 않습니다.")
    return value


def boolean(value: Any, default: bool = False) -> bool:
    value = default if value is None else value
    if not isinstance(value, bool):
        raise ValueError("확인 여부는 true/false로 입력하세요.")
    return value


def rows(value: Any) -> list[dict]:
    if not isinstance(value, list) or len(value) > 500 or any(not isinstance(row, dict) for row in value):
        raise ValueError("분석 이력은 최대 500개의 항목 목록이어야 합니다.")
    return value


def annual_rows(value: Any, fields: tuple[str, ...]) -> list[dict]:
    result, years = [], set()
    for row in rows(value):
        year = integer(row.get("year"), 1988, date.today().year)
        if year in years:
            raise ValueError("과세연도/부담액 연도는 중복될 수 없습니다.")
        years.add(year)
        entry = {"year": year, "source": choice(row.get("source"), SOURCES), "verified": boolean(row.get("verified"))}
        entry.update({field: business_income(row.get(field)) if field == "business_income" else money(row.get(field)) for field in fields})
        if fields == ANNUAL_MONEY:
            entry["paid_months"] = None if row.get("paid_months") is None else integer(row["paid_months"], 0, 12)
            entry["payment_date"] = None if not row.get("payment_date") else iso_date(row["payment_date"]).isoformat()
            if entry["payment_date"] and iso_date(entry["payment_date"]).year != year:
                raise ValueError("실제 납부일은 해당 연도 안이어야 합니다.")
        else:
            entry["income_type"] = choice(row.get("income_type"), INCOMES)
            entry["saving_date"] = None if not row.get("saving_date") else iso_date(row["saving_date"]).isoformat()
        result.append(entry)
    return result


def validate_analysis(payload: Any) -> dict:
    if not isinstance(payload, dict) or set(payload) - {"membership_periods", "annual_details", "tax_years", "scenario"}:
        raise ValueError("국민연금 분석 입력 형식이 올바르지 않습니다.")
    periods, occupied = [], set()
    for row in rows(payload.get("membership_periods", [])):
        year = integer(row.get("year"), 1988, date.today().year)
        start = integer(row.get("start_month"), 1, 12)
        end = integer(row.get("end_month"), 1, 12)
        if start > end:
            raise ValueError("가입기간 종료 월은 시작 월보다 빠를 수 없습니다.")
        months = {(year, month) for month in range(start, end + 1)}
        if occupied & months:
            raise ValueError("같은 연도의 가입기간이 겹칩니다.")
        occupied |= months
        kind = choice(row.get("membership_type"), MEMBERSHIPS)
        role = choice(row.get("workplace_role"), ROLES)
        if kind != "workplace" and role != "unknown":
            raise ValueError("사업장 내 지위는 사업장가입자에만 지정할 수 있습니다.")
        periods.append({"year": year, "start_month": start, "end_month": end, "membership_type": kind, "workplace_role": role})
    scenario = payload.get("scenario", {})
    if not isinstance(scenario, dict):
        raise ValueError("수령 가정은 객체여야 합니다.")
    allowed = {"birth_date", "as_of_date", "pension_start", "premium_start", "premium_end", "monthly_pension", "future_monthly_premium",
               "premium_growth", "inflation", "pension_indexed", "pension_value_basis", "output_basis", "annual_date_method",
               "past_history_complete", "assume_agency_as_personal", "include_tax_savings", "future_schedule", "end_age"}
    if set(scenario) - allowed:
        raise ValueError("지원하지 않는 수령 가정입니다.")
    clean = {key: None if not scenario.get(key) else iso_date(scenario[key]).isoformat()
             for key in ("birth_date", "as_of_date", "pension_start", "premium_start", "premium_end")}
    clean.update({key: money(scenario.get(key)) for key in ("monthly_pension", "future_monthly_premium")})
    for key in ("premium_growth", "inflation"):
        value = scenario.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -0.5 <= value <= 0.5):
            raise ValueError("연간 증가율·물가율은 -50%~50% 범위의 숫자입니다.")
        clean[key] = value
    for key in ("past_history_complete", "assume_agency_as_personal", "include_tax_savings", "pension_indexed"):
        clean[key] = boolean(scenario.get(key))
    clean["pension_value_basis"] = choice(scenario.get("pension_value_basis"), {"current_value", "future_nominal", "unknown"})
    clean["output_basis"] = choice(scenario.get("output_basis"), {"real", "nominal"}, "nominal")
    clean["annual_date_method"] = choice(scenario.get("annual_date_method"), {"mid_year", "year_end", "exact_only"}, "exact_only")
    clean["end_age"] = integer(scenario.get("end_age", 90), 65, 110)
    clean["future_schedule"] = None
    if scenario.get("future_schedule") is not None:
        clean["future_schedule"] = []
        dates = set()
        for row in rows(scenario["future_schedule"]):
            day = iso_date(row.get("date")).isoformat()
            if day in dates:
                raise ValueError("미래 납부 일정의 날짜가 중복됩니다.")
            dates.add(day)
            clean["future_schedule"].append({"date": day, "amount": money(row.get("amount"), optional=False)})
    for start_key, end_key in (("birth_date", "as_of_date"), ("premium_start", "premium_end")):
        if clean[start_key] and clean[end_key] and clean[start_key] > clean[end_key]:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
    if clean["as_of_date"]:
        for key in ("pension_start", "premium_start"):
            if clean[key] and clean[key] < clean["as_of_date"]:
                raise ValueError("예상 개시/납부 시작일은 분석 기준일 이후여야 합니다.")
        if clean["future_schedule"] and any(row["date"] < clean["as_of_date"] for row in clean["future_schedule"]):
            raise ValueError("미래 납부 일정은 기준일 이후여야 합니다.")
    return {"membership_periods": periods, "annual_details": annual_rows(payload.get("annual_details", []), ANNUAL_MONEY),
            "tax_years": annual_rows(payload.get("tax_years", []), TAX_MONEY), "scenario": clean}


def tax_saving(row: dict) -> dict:
    confirmed_filing = row.get("source") == "tax_return" and row.get("verified") is True
    input_basis = ("filing_confirmed" if confirmed_filing else "estimate" if row.get("source") == "estimate"
                   else "verified_input" if row.get("verified") and row.get("source") != "unknown" else "unknown")
    result = {"year": row["year"], "allowed_deduction": row.get("allowed_deduction"), "actual_tax_saving": row.get("actual_tax_saving"),
              "source_url": TAX_SOURCE_2026 if row["year"] == 2026 else TAX_SOURCE, "verified_on": TAX_VERIFIED_ON,
              "input_basis": input_basis, "actual_tax_saving_confirmed": confirmed_filing and row.get("actual_tax_saving") is not None,
              "notice": "예상 산출세액 감소분이며 환급액이 아닙니다. 다른 공제·감면·결정세액·지방소득세 미반영."}
    if row["year"] == 2026:
        result["law_url"] = TAX_LAW_2026
    table = next((table for table in TAX_TABLES if table[0] <= row["year"] <= table[1]), None)
    if table is None:
        return {**result, "status": "unsupported_year", "reason": "해당 과세연도의 공식 세율표를 등록·확인하지 않았습니다."}
    if not row.get("verified") or row.get("source") in {"unknown", "estimate"} or row.get("taxable_before") is None or row.get("allowed_deduction") is None:
        return {**result, "status": "unknown", "reason": "공제 전 과세표준과 실제 인정 공제액의 확인이 필요합니다."}
    base = Decimal(str(row["taxable_before"]))
    deduction = min(base, Decimal(str(row["allowed_deduction"])))
    def tax(amount):
        previous, total = Decimal(0), Decimal(0)
        for upper, percent in zip((*table[2], None), table[3]):
            portion = max(Decimal(0), amount - previous) if upper is None else max(Decimal(0), min(amount, Decimal(upper)) - previous)
            total += portion * Decimal(percent) / Decimal(100)
            if upper is None or amount <= upper:
                break
            previous = Decimal(upper)
        return total
    before, after = tax(base), tax(base - deduction)
    def rounded(value):
        return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return {**result, "status": "estimated", "tax_before": rounded(before), "tax_after": rounded(after),
            "estimated_reduction": rounded(before - after), "applied_deduction": rounded(deduction),
            "capped": deduction < Decimal(str(row["allowed_deduction"])), "table_years": [table[0], table[1]]}


def xirr(cashflows: list[dict], *, max_iterations: int = 256) -> dict:
    """ACT/365.2425; unique-sign-change flows only; ambiguous flows fail closed."""
    if not isinstance(cashflows, list) or len(cashflows) > 5000 or any(not isinstance(row, dict) for row in cashflows):
        raise ValueError("IRR 현금흐름은 최대 5000개 항목 목록이어야 합니다.")
    integer(max_iterations, 0, 512)
    combined = {}
    for row in cashflows:
        day = iso_date(row.get("date"))
        amount = row.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or abs(amount) > 1e100:
            raise ValueError("IRR 현금흐름 금액이 유효하지 않습니다.")
        combined[day] = combined.get(day, 0) + amount
    ordered = sorted((day, amount) for day, amount in combined.items() if amount != 0)
    if any(not math.isfinite(amount) for _, amount in ordered):
        raise ValueError("IRR 현금흐름 합계가 유효하지 않습니다.")
    signs = [1 if amount > 0 else -1 for _, amount in ordered]
    changes = sum(a != b for a, b in zip(signs, signs[1:]))
    if changes == 0:
        return {"status": "no_root", "rate": None, "reason": "지출과 수령이 모두 필요합니다. 동일 날짜 합산 후 0인 흐름도 제외합니다."}
    if changes > 1:
        return {"status": "ambiguous", "rate": None, "reason": "부호가 여러 번 변해 복수 해 가능성을 배제하지 못합니다."}
    terms = [((day - ordered[0][0]).days / YEAR_DAYS, 1 if amount > 0 else -1, math.log(abs(amount))) for day, amount in ordered]
    def npv(log_rate):
        exponents = [log_amount - time * log_rate for time, _, log_amount in terms]
        shift = max(exponents)
        values = [sign * math.exp(exponent - shift) for exponent, (_, sign, _) in zip(exponents, terms)]
        return math.fsum(values) / math.fsum(abs(value) for value in values)
    if math.fsum(amount for _, amount in ordered) == 0:
        return {"status": "ok", "rate": 0.0, "iterations": 0}
    low, high = -30.0, 30.0
    fl, fh = npv(low), npv(high)
    if fl * fh > 0:
        return {"status": "out_of_bounds", "rate": None, "reason": "설정한 log(1+r) 범위 [-30,30]에서 해를 찾지 못했습니다."}
    for iteration in range(max_iterations):
        middle = (low + high) / 2
        fm = npv(middle)
        if abs(fm) <= 1e-10 and high - low <= 1e-10:
            return {"status": "ok", "rate": math.expm1(middle), "iterations": iteration + 1}
        if fl * fm <= 0:
            high = middle
        else:
            low, fl = middle, fm
    return {"status": "convergence_failed", "rate": None, "reason": "허용 잔차와 구간 오차에 수렴하지 않았습니다."}


def month_dates(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("종료일은 시작일보다 빠를 수 없습니다.")
    result = []
    for offset in range(1441):
        ordinal = start.year * 12 + start.month - 1 + offset
        year, month = ordinal // 12, ordinal % 12 + 1
        day = date(year, month, min(start.day, calendar.monthrange(year, month)[1]))
        if day > end:
            return result
        result.append(day)
    raise ValueError("월별 분석 기간은 최대 120년입니다.")


def scenario_results(item: dict, analysis: dict) -> dict:
    s = analysis["scenario"]
    required = ("birth_date", "as_of_date", "pension_start", "monthly_pension", "inflation")
    if any(s.get(key) is None for key in required) or s["pension_value_basis"] == "unknown":
        return {"status": "unknown", "reason": "생년월일·기준일·개시일·월 수령액·물가율·금액 기준을 명시하세요.", "scenarios": []}
    birth, as_of, pension_start = (iso_date(s[key]) for key in ("birth_date", "as_of_date", "pension_start"))
    if birth >= as_of or pension_start < as_of:
        return {"status": "unknown", "reason": "생년월일은 기준일 이전, 예상 개시일은 기준일 이후여야 합니다.", "scenarios": []}
    inflation = s["inflation"]
    def basis(amount, day):
        return amount / (1 + inflation) ** ((day - as_of).days / YEAR_DAYS) if s["output_basis"] == "real" else amount
    future = []
    if s["future_schedule"] is not None:
        for payment in s["future_schedule"]:
            day = iso_date(payment["date"])
            if day < as_of:
                raise ValueError("미래 납부 일정은 기준일 이후여야 합니다.")
            future.append({"date": day.isoformat(), "amount": -basis(payment["amount"], day)})
    elif s["future_monthly_premium"] is None:
        return {"status": "unknown", "reason": "미래 월 납부액 또는 명시적 납부 일정을 입력하세요. 0원도 명시적 가정입니다.", "scenarios": []}
    elif s["future_monthly_premium"] > 0:
        if s["premium_start"] is None or s["premium_end"] is None or s["premium_growth"] is None:
            return {"status": "unknown", "reason": "미래 납부 시작·종료일과 증가율이 필요합니다. 연금 개시일을 종료일로 추정하지 않습니다.", "scenarios": []}
        start, end = iso_date(s["premium_start"]), iso_date(s["premium_end"])
        if start < as_of:
            raise ValueError("미래 납부 시작일은 기준일 이후여야 합니다.")
        for index, day in enumerate(month_dates(start, end)):
            amount = s["future_monthly_premium"] * (1 + s["premium_growth"]) ** (index / 12)
            future.append({"date": day.isoformat(), "amount": -basis(amount, day)})
    details = {row["year"]: row for row in analysis["annual_details"]}
    agency = {int(row["year"]): row["deposit"] for row in item.get("yearly_contributions", [])}
    past, reasons, approximated = [], [], False
    if not s["past_history_complete"]:
        reasons.append("과거 기록의 완전성 미확인")
    for year in sorted(set(agency) | set(details)):
        row = details.get(year, {})
        amount = row.get("personal_paid")
        if amount is None or not row.get("verified") or row.get("source") in {None, "unknown", "estimate"}:
            if s["assume_agency_as_personal"] and year in agency:
                amount = agency[year]
            else:
                reasons.append(f"{year}년 실제 본인 부담액 미확인")
                continue
        if row.get("payment_date"):
            day = iso_date(row["payment_date"])
            if row.get("paid_months") != 1:
                approximated = True  # Annual aggregate uses one representative date.
        elif s["annual_date_method"] == "exact_only":
            reasons.append(f"{year}년 납부일 미확인")
            continue
        else:
            day = date(year, 6, 30) if s["annual_date_method"] == "mid_year" else date(year, 12, 31)
            approximated = True
        if day > as_of:
            reasons.append(f"{year}년 근사 납부일이 기준일 이후")
            continue
        past.append({"date": day.isoformat(), "amount": -basis(amount, day)})
    if not agency and not details:
        reasons.append("과거 실제 지출 자료 없음")
    tax_flows, tax_reasons = [], []
    for row in analysis["tax_years"]:
        if row.get("actual_tax_saving") is None or not row.get("verified") or row.get("source") != "tax_return":
            tax_reasons.append(f"{row['year']}년 실제 절세액·확인일 미확인")
            continue
        if row["actual_tax_saving"] == 0:
            continue  # Confirmed zero has no timing effect; unknown is not zero.
        if not row.get("saving_date"):
            tax_reasons.append(f"{row['year']}년 실제 절세액 확인일 미확인")
            continue
        day = iso_date(row["saving_date"])
        if day > as_of:
            tax_reasons.append(f"{row['year']}년 절세액 확인일이 기준일 이후")
            continue
        tax_flows.append({"date": day.isoformat(), "amount": basis(row["actual_tax_saving"], day)})
    if not analysis["tax_years"]:
        tax_reasons.append("신고에서 확인한 실제 절세액 자료 없음")
    scenarios = []
    for age in sorted({75, 80, 85, 90, 95, s["end_age"]}):
        end = date(birth.year + age, birth.month, min(birth.day, calendar.monthrange(birth.year + age, birth.month)[1]))
        if end <= pension_start or end.year > 2200:
            scenarios.append({"age": age, "status": "unknown", "reason": "종료 나이가 예상 개시일 이전입니다."})
            continue
        future_in_horizon = [flow for flow in future if iso_date(flow["date"]) < end]
        payments = []
        initial = s["monthly_pension"]
        if s["pension_value_basis"] == "current_value":
            initial *= (1 + inflation) ** ((pension_start - as_of).days / YEAR_DAYS)
        for index, day in enumerate(month_dates(pension_start, date.fromordinal(end.toordinal() - 1))):
            nominal = initial * ((1 + inflation) ** (index / 12) if s["pension_indexed"] else 1)
            payments.append({"date": day.isoformat(), "amount": basis(nominal, day)})
        flows = past + future_in_horizon + payments
        if any(not math.isfinite(flow["amount"]) for flow in flows):
            raise ValueError("수령 가정의 현금흐름 금액 범위를 확인하세요.")
        cumulative, payback, daily = 0.0, None, {}
        for flow in flows:
            daily.setdefault(flow["date"], []).append(flow["amount"])
        has_cost = any(flow["amount"] < 0 for flow in flows)
        for day, amounts in sorted(daily.items()):
            amount = math.fsum(amounts)
            cumulative += amount
            if has_cost and amount > 0 and cumulative >= 0 and payback is None:
                payback = day
        irr = {"status": "incomplete", "rate": None, "reason": "; ".join(reasons)} if reasons else xirr(flows)
        tax_irr = None
        if s["include_tax_savings"]:
            tax_irr = {"status": "incomplete", "rate": None, "reason": "; ".join(reasons + tax_reasons)} if reasons or tax_reasons else xirr(flows + tax_flows)
        scenarios.append({"age": age, "status": "scenario", "end_date": end.isoformat(),
                          "future_premiums": -math.fsum(flow["amount"] for flow in future_in_horizon),
                          "pension_receipts": math.fsum(flow["amount"] for flow in payments),
                          "future_net_cash_flow": math.fsum(flow["amount"] for flow in future_in_horizon + payments),
                          "net_cash_flow": None if reasons else math.fsum(flow["amount"] for flow in flows),
                          "payback_date": None if reasons else payback, "pre_tax_irr": irr, "tax_benefit_irr": tax_irr,
                          "after_tax_irr": {"status": "unsupported", "rate": None, "reason": "연금 수령 세후 세법/가정은 등록하지 않았습니다."},
                          "cashflows": flows})
    return {"status": "scenario", "basis": s["output_basis"], "annual_dates_approximated": approximated,
            "personal_cost_assumed": s["assume_agency_as_personal"], "history_reasons": reasons, "scenarios": scenarios,
            "notice": "국민연금은 평생 지급되는 구조입니다. 종료 나이는 사망 예측이 아닌 가정입니다. 본인 부담액·날짜·물가 가정에 따른 분석이며 세전 IRR과 절세 반영 IRR은 별개입니다."}


def find_item(data: dict, item_id: str) -> dict:
    item = next((item for item in data.get("insurance_accounts", []) if item.get("id") == item_id), None)
    if item is None:
        raise LookupError("상품을 찾을 수 없습니다.")
    if item.get("insurance_type") != "national_pension":
        raise ValueError("국민연금 상품에서만 사용할 수 있습니다.")
    return item


def read_state(username: str):
    # Avoid read_portfolio's derived snapshot/defaults and write_portfolio's
    # updated_at advancement: this mutation owns only optional metadata.
    path = portfolio._get_portfolio_file(username)
    try:
        return path, read_financial_json(path)
    except FileNotFoundError as exc:
        raise LookupError("상품을 찾을 수 없습니다.") from exc


def stored_analysis(item: dict) -> dict:
    state = item.get("national_pension_analysis", {})
    if not isinstance(state, dict):
        raise ValueError("저장된 국민연금 분석 정보 형식을 확인해 주세요.")
    integer(state.get("revision", 0), 0, 2**53 - 1)
    return state


def view(item_id: str, username: str) -> dict:
    _, data = read_state(username)
    item = find_item(data, item_id)
    state = deepcopy(stored_analysis(item))
    revision = state.pop("revision", 0)
    return {"revision": revision, "analysis": state, "history": deepcopy(item.get("yearly_contributions", [])),
            "total_paid_amount": item.get("total_paid_amount"), "monthly_payout": item.get("monthly_payout"),
            "maturity_date": item.get("maturity_date")}


@financial_rmw('portfolio.json')
def save(item_id: str, payload: Any, revision: int, username: str, *, expected_history: Any) -> dict:
    revision = integer(revision, 0, 2**53 - 2)
    clean = validate_analysis(payload)
    path, data = read_state(username)
    item = find_item(data, item_id)
    current = stored_analysis(item).get("revision", 0)
    if current != revision or expected_history != item.get("yearly_contributions", []):
        raise PensionConflict("분석 정보 또는 납부 이력이 변경되었습니다. 다시 불러와 주세요.")
    item["national_pension_analysis"] = {**clean, "revision": revision + 1}
    write_financial_json(path, data)
    return {"revision": revision + 1, "analysis": deepcopy(clean)}


def calculate(item_id: str, payload: Any, username: str, *, revision: int | None = None, expected_history: Any = None) -> dict:
    clean = validate_analysis(payload)
    _, data = read_state(username)
    item = find_item(data, item_id)
    if revision is not None:
        integer(revision, 0, 2**53 - 1)
        if stored_analysis(item).get("revision", 0) != revision or expected_history != item.get("yearly_contributions", []):
            raise PensionConflict("분석 정보 또는 납부 이력이 변경되었습니다. 다시 불러와 주세요.")
    return {"tax_years": [tax_saving(row) for row in clean["tax_years"]], "returns": scenario_results(item, clean)}
