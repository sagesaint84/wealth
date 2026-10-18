from __future__ import annotations

import csv
import io
import json
import re
import uuid
import math
from datetime import datetime
from pathlib import Path
from typing import Any
import openpyxl

from app.services.financial_json import (FinancialStorageError, financial_rmw,
    ensure_financial_json, read_financial_json, write_financial_json)
from app.services.historical_fx import get_historical_fx_rate
from app.services.stock_master import resolve_stock_info
from app.services.file_import_identity import (
    FILE_IMPORT_FINGERPRINT_FIELD,
    build_file_import_fingerprint,
    canonical_number,
    canonical_text,
    retain_new_occurrences,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"


class DividendRecordsStorageError(RuntimeError):
    """Existing dividend storage could not be read safely for an import."""


def _record_tax_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Optional user estimates only; never overwrite deposit/source fields."""
    result = {}
    if 'capital_dividend_mode' in payload:
        mode = payload['capital_dividend_mode']
        if mode not in ('AUTO', 'MANUAL_ON', 'MANUAL_OFF'):
            raise ValueError('capital_dividend_mode is invalid')
        result['capital_dividend_mode'] = mode
    for field in ('gross_amount', 'tax', 'fee', 'estimated_tax_rate', 'capital_exempt_amount'):
        if field not in payload:
            continue
        raw = payload[field]
        if raw is None or raw == '':
            result[field] = None
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError(f'{field} is invalid') from None
        if isinstance(raw, bool) or not math.isfinite(value) or value < 0 or (field == 'estimated_tax_rate' and value >= 1):
            raise ValueError(f'{field} is invalid')
        result[field] = value
    return result


def estimate_record_dividend(record: dict[str, Any], official: dict[str, Any] | None = None) -> dict[str, Any]:
    """Personal-management estimate in original currency; no writes or FX fetch."""
    from app.services.tax.investment_tax.rules_2026 import (
        GENERAL_DIVIDEND_WITHHOLDING_RATE, US_TREATY_GENERAL_DIVIDEND_RATE,
    )
    from app.services.dividend_event_identity import build_dividend_event_identity
    def number(value, fallback=0.0):
        try:
            n = float(value)
            return n if not isinstance(value, bool) and math.isfinite(n) and n >= 0 else fallback
        except (ValueError, TypeError):
            return fallback
    currency = str(record.get('currency') or 'KRW').upper()
    net = number(record.get('amount'))
    mode = record.get('capital_dividend_mode') or 'AUTO'
    evidence = official or {}
    capital = evidence.get('capital_dividend_evidence') or {}
    cash = evidence.get('structured_decision_disclosure') or {}
    components = capital.get('payment_components') or {}
    revision = capital.get('correction_relationship') or {}
    identity = build_dividend_event_identity(code=record.get('code'), record_date=cash.get('record_date'),
        source='opendart', source_event_id=cash.get('receipt_no'))
    confirmed = bool(currency == 'KRW' and capital.get('status') == 'available'
        and capital.get('receipt_no') and capital.get('receipt_no') == cash.get('receipt_no')
        and cash.get('confirmed_payment_date') and cash.get('payment_date') == record.get('date')
        and (not record.get('event_identity') or record.get('event_identity') == identity)
        and capital.get('payment_event_status') == 'single_event_scoped'
        and components.get('amount_status') == 'verified'
        and number(components.get('total_cash_dps_krw')) > 0
        and number(components.get('disclosed_capital_reduction_dps_krw')) > 0
        and not any(revision.get(k) for k in ('later_correction_indicated', 'withdrawal_in_search_results', 'selected_metadata_conflict')))
    ratio = min(1.0, number(components.get('disclosed_capital_reduction_dps_krw')) /
        number(components.get('total_cash_dps_krw'), 1)) if confirmed else 0.0
    applied = mode == 'MANUAL_ON' or (mode == 'AUTO' and confirmed)
    rate = number(record.get('estimated_tax_rate'), US_TREATY_GENERAL_DIVIDEND_RATE
        if currency == 'USD' else GENERAL_DIVIDEND_WITHHOLDING_RATE)
    if rate >= 1:
        rate = US_TREATY_GENERAL_DIVIDEND_RATE if currency == 'USD' else GENERAL_DIVIDEND_WITHHOLDING_RATE
    fee = number(record.get('fee'))
    # A manual selection means the entire payment unless an optional partial
    # amount is supplied. Official mixed payments use the disclosed proportion.
    partial = number(record.get('capital_exempt_amount')) if record.get('capital_exempt_amount') is not None else None
    if record.get('gross_amount') is not None:
        gross = number(record['gross_amount'])
        estimated = False
    elif record.get('tax') is not None:
        gross = net + number(record['tax']) + fee
        estimated = False
    elif applied and partial is not None:
        exempt_net = min(net, partial)
        gross = exempt_net + (net - exempt_net + fee) / (1 - rate)
        estimated = True
    else:
        exempt_ratio = (ratio if mode == 'AUTO' else 1.0) if applied else 0.0
        gross = (net + fee) / (1 - rate * (1 - exempt_ratio))
        estimated = True
    tax = number(record['tax']) if record.get('tax') is not None else max(0, gross - net - fee)
    fx = number(record.get('fx_rate')) if currency != 'KRW' else 1
    if currency != 'KRW' and not fx:
        fx = number(record.get('amount_krw')) / net if net else 1
    pending = mode == 'AUTO' and not confirmed and (capital.get('status') == 'unverified'
        or number(components.get('disclosed_capital_reduction_dps_krw')) > 0)
    label = ('감액배당 · 사용자 지정' if mode == 'MANUAL_ON' else
        '감액배당 · 공식 확인' if applied else '감액배당 확인 대기' if pending else '일반 배당')
    return {'capital_dividend_mode': mode, 'capital_official_confirmed': confirmed,
        'capital_applied': applied, 'tax_type_label': label,
        'gross_amount': gross, 'tax': tax, 'estimated': estimated,
        'gross_amount_krw': round(gross * fx), 'estimated_tax_rate': rate,
        'personal_tax_eligibility_confirmed': False}


def _get_user_dir(username: str | None = None) -> Path:
    from app.services.user_manager import get_user_data_dir
    return get_user_data_dir(username)

def _get_dividend_file(username: str | None = None) -> Path:
    return _get_user_dir(username) / "dividend_records.json"


def _ensure_dividend_file(username: str | None = None) -> Path:
    f = _get_dividend_file(username)
    return ensure_financial_json(f, {
        "records": [], "updated_at": datetime.now().astimezone().isoformat(),
    })


def read_dividend_records(username: str | None = None) -> list[dict[str, Any]]:
    f = _ensure_dividend_file(username)
    try:
        return read_financial_json(f).get("records", [])
    except FinancialStorageError as exc:
        raise DividendRecordsStorageError("dividend storage is unreadable") from exc


def _read_dividend_records_for_import(username: str | None = None) -> list[dict[str, Any]]:
    path = _get_dividend_file(username)
    if not path.exists():
        return []
    try:
        data = read_financial_json(path)
    except FinancialStorageError as exc:
        raise DividendRecordsStorageError("dividend storage is unreadable") from exc
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise DividendRecordsStorageError("dividend storage has an invalid structure")
    records = data["records"]
    if not all(isinstance(record, dict) for record in records):
        raise DividendRecordsStorageError("dividend storage has an invalid record structure")
    return records


def read_dividend_records_for_import(username: str | None = None) -> list[dict[str, Any]]:
    """Strict read used by import previews/commits; never treats corruption as empty."""
    return _read_dividend_records_for_import(username)


@financial_rmw('dividend_records.json')
def write_dividend_records(records: list[dict[str, Any]], username: str | None = None) -> None:
    f = _ensure_dividend_file(username)
    payload = {
        "records": records,
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    try:
        write_financial_json(f, payload)
    except FinancialStorageError as exc:
        raise DividendRecordsStorageError("dividend storage is unreadable") from exc


@financial_rmw('dividend_records.json')
def create_dividend_record(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    tax_metadata = _record_tax_metadata(payload)
    if payload.get("source") == "ledger_interest":
        raise ValueError("가계부 연동 기록은 가계부에서 등록해 주세요.")
    records = read_dividend_records(username)
    now_iso = datetime.now().astimezone().isoformat()
    
    currency = str(payload.get("currency", "KRW")).upper()
    amount = float(payload.get("amount", 0.0))
    date_val = str(payload.get("date", datetime.now().strftime("%Y-%m-%d")))
    
    raw_fx = payload.get("fx_rate")
    if currency == "USD":
        if raw_fx is not None and float(raw_fx) > 0:
            fx_rate = float(raw_fx)
        else:
            fx_rate = get_historical_fx_rate(date_val)
    else:
        fx_rate = 1.0

    amount_krw = float(payload.get("amount_krw", 0.0))
    if amount_krw <= 0.0:
        amount_krw = round(amount * fx_rate, 0) if currency == "USD" else round(amount, 0)

    raw_code = str(payload.get("code", "")).strip()
    raw_name = str(payload.get("name", "")).strip()
    code, name, currency = resolve_stock_info(raw_code, raw_name, currency)

    record = {
        "id": str(uuid.uuid4()),
        "date": date_val,
        "code": code,
        "name": name,
        "currency": currency,
        "amount": amount,
        "fx_rate": fx_rate,
        "amount_krw": amount_krw,
        "owner": str(payload.get("owner", "모두")).strip(),
        "broker": str(payload.get("broker", "")).strip(),
        "account_name": str(payload.get("account_name", "")).strip(),
        "memo": str(payload.get("memo", "")).strip(),
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    for field in ("gross_amount", "tax", "fee"):
        if payload.get(field) is not None:
            value = float(payload[field])
            if value < 0:
                raise ValueError(f"{field} must be non-negative")
            record[field] = value

    income_type = payload.get("income_type")
    if income_type is not None:
        income_type = str(income_type).strip()
        if income_type not in {"dividend", "distribution", "account_interest"}:
            raise ValueError("income_type is invalid")
        record["income_type"] = income_type

    for field in ("source", "source_fingerprint", "source_account_scope", "imported_at"):
        value = payload.get(field)
        if value is not None:
            record[field] = str(value).strip()

    for field in ("event_identity", "record_date", "payment_date"):
        value = payload.get(field)
        if value is not None:
            record[field] = str(value).strip()

    for field in ("source_scope_verified", "imported_by_user_action"):
        if field in payload:
            if type(payload[field]) is not bool:
                raise ValueError(f"{field} must be boolean")
            record[field] = payload[field]

    source_meta = payload.get("source_meta")
    if source_meta is not None:
        if not isinstance(source_meta, dict):
            raise ValueError("source_meta must be an object")
        # JSON round-trip is a defensive deep copy and also rejects non-JSON values.
        record["source_meta"] = json.loads(json.dumps(source_meta, ensure_ascii=False, allow_nan=False))

    record.update(tax_metadata)
    records.append(record)
    write_dividend_records(records, username)
    return record


@financial_rmw('dividend_records.json')
def update_dividend_record(record_id: str, payload: dict[str, Any], username: str | None = None) -> dict[str, Any] | None:
    tax_metadata = _record_tax_metadata(payload)
    records = read_dividend_records(username)
    target = None
    for r in records:
        if r.get("id") == record_id:
            target = r
            break
    if not target:
        return None
    if target.get("source") == "ledger_interest" or payload.get("source") == "ledger_interest":
        raise ValueError("가계부 연동 기록은 가계부에서 수정해 주세요.")

    currency = str(payload.get("currency", target.get("currency", "KRW"))).upper()
    amount = float(payload.get("amount", target.get("amount", 0.0)))
    fx_rate = float(payload.get("fx_rate", target.get("fx_rate", 1385.0))) if currency == "USD" else 1.0
    if 'amount_krw' in payload:
        amount_krw = float(payload['amount_krw'])
    elif not any(field in payload for field in ('amount', 'currency', 'fx_rate')):
        amount_krw = target.get('amount_krw', 0.0)
    else:
        amount_krw = round(amount * fx_rate, 0) if currency == 'USD' else round(amount, 0)

    raw_code = str(payload.get("code", target.get("code", ""))).strip()
    raw_name = str(payload.get("name", target.get("name", ""))).strip()
    code, name, currency = resolve_stock_info(raw_code, raw_name, currency)

    target["date"] = str(payload.get("date", target.get("date")))
    target["code"] = code
    target["name"] = name
    target["currency"] = currency
    target["amount"] = amount
    target["fx_rate"] = fx_rate
    target["amount_krw"] = amount_krw
    target["owner"] = str(payload.get("owner", target.get("owner", "모두"))).strip()
    target["broker"] = str(payload.get("broker", target.get("broker", ""))).strip()
    target["account_name"] = str(payload.get("account_name", target.get("account_name", ""))).strip()
    target["memo"] = str(payload.get("memo", target.get("memo", ""))).strip()
    for field in ("event_identity", "record_date", "payment_date"):
        if field in payload:
            value = payload[field]
            target[field] = str(value).strip() if value is not None else ""
    target.update(tax_metadata)
    target["updated_at"] = datetime.now().astimezone().isoformat()

    write_dividend_records(records, username)
    return target


@financial_rmw('dividend_records.json')
def delete_dividend_record(record_id: str, username: str | None = None) -> bool:
    records = read_dividend_records(username)
    if any(r.get("id") == record_id and r.get("source") == "ledger_interest" for r in records):
        raise ValueError("가계부 연동 기록은 가계부에서 삭제해 주세요.")
    initial_len = len(records)
    records = [r for r in records if r.get("id") != record_id]
    if len(records) < initial_len:
        write_dividend_records(records, username)
        return True
    return False


@financial_rmw('dividend_records.json')
def clear_dividend_records(username: str | None = None) -> None:
    write_dividend_records([r for r in read_dividend_records(username) if r.get("source") == "ledger_interest"], username)


def _dividend_income_type(record: dict[str, Any]) -> str:
    explicit = str(record.get("income_type") or "").strip()
    if explicit in {"dividend", "distribution", "account_interest"}:
        return explicit
    code = str(record.get("code") or "").strip().upper()
    name = str(record.get("name") or "").strip()
    if code.startswith("INTEREST") or ("이자" in name and "화이자" not in name):
        return "account_interest"
    return "dividend"


def get_actual_dividend_summary(owner: str = "모두", year: int | str | None = None, username: str | None = None) -> dict[str, Any]:
    records = read_dividend_records(username)

    scoped: list[dict[str, Any]] = []
    for record in records:
        if owner != "모두" and record.get("owner", "모두") != owner:
            continue
        record_date = str(record.get("date", ""))
        if year and str(year) not in {"all", "전체"} and not record_date.startswith(str(year)):
            continue
        scoped.append(record)

    dividend_records = [r for r in scoped if _dividend_income_type(r) != "account_interest"]
    interest_records = [r for r in scoped if _dividend_income_type(r) == "account_interest"]

    available_years = sorted(
        {str(r.get("date", ""))[:4] for r in dividend_records if len(str(r.get("date", ""))) >= 4},
        reverse=True,
    )
    if not available_years:
        available_years = [str(datetime.now().year)]

    total_actual_krw = sum(float(r.get("amount_krw", 0.0)) for r in dividend_records)
    total_interest_krw = sum(float(r.get("amount_krw", 0.0)) for r in interest_records)
    monthly_schedule = {m: {"month": m, "total_krw": 0.0, "items": []} for m in range(1, 13)}

    unique_codes = set()
    for record in dividend_records:
        record_date = str(record.get("date", ""))
        try:
            month = int(record_date.split("-")[1])
        except (IndexError, ValueError):
            month = 1
        if 1 <= month <= 12:
            amount_krw = float(record.get("amount_krw", 0.0))
            monthly_schedule[month]["total_krw"] += amount_krw
            monthly_schedule[month]["items"].append(record)
            if record.get("code"):
                unique_codes.add(record.get("code"))

    monthly_list = []
    for month in range(1, 13):
        item = monthly_schedule[month]
        item["total_krw"] = round(item["total_krw"], 0)
        item["items"].sort(key=lambda x: str(x.get("date", "")), reverse=True)
        monthly_list.append(item)

    yearly_dict: dict[str, dict[str, Any]] = {
        y: {"year": y, "total_krw": 0.0, "items": []} for y in sorted(available_years)
    }
    for record in dividend_records:
        year_text = str(record.get("date", ""))[:4]
        if year_text in yearly_dict:
            yearly_dict[year_text]["total_krw"] += float(record.get("amount_krw", 0.0))
            yearly_dict[year_text]["items"].append(record)

    yearly_list = []
    for year_text in sorted(yearly_dict.keys()):
        item = yearly_dict[year_text]
        item["total_krw"] = round(item["total_krw"], 0)
        item["items"].sort(key=lambda x: str(x.get("date", "")), reverse=True)
        yearly_list.append(item)

    return {
        "year": str(year) if year else str(datetime.now().year),
        "available_years": available_years,
        "total_actual_dividend_krw": round(total_actual_krw, 0),
        "monthly_avg_dividend_krw": round(total_actual_krw / 12, 0),
        "record_count": len(dividend_records),
        "paying_stock_count": len(unique_codes),
        "monthly_schedule": monthly_list,
        "yearly_schedule": yearly_list,
        "records": sorted(dividend_records, key=lambda x: str(x.get("date", "")), reverse=True),
        "total_actual_interest_krw": round(total_interest_krw, 0),
        "interest_record_count": len(interest_records),
        "interest_records": sorted(interest_records, key=lambda x: str(x.get("date", "")), reverse=True),
    }


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _clean_num(val: Any) -> float:
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").replace("₩", "").replace("$", "").replace("원", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _optional_num(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        if name in row and row[name] is not None and str(row[name]).strip() != "":
            return _clean_num(row[name])
    return None


from datetime import date, datetime, timedelta


def _parse_date(val: Any) -> str:
    if val is None or val == "":
        return datetime.now().strftime("%Y-%m-%d")
    if isinstance(val, (datetime, date)):
        return val.strftime("%Y-%m-%d")
    if isinstance(val, (int, float)):
        # 엑셀 시리얼 날짜 지원 (e.g. 46255 -> 2026-08-21, 10000~90000 범위)
        if 10000 <= val <= 90000:
            d = date(1899, 12, 30) + timedelta(days=int(val))
            return d.strftime("%Y-%m-%d")
    s = str(val).strip()
    # 숫자 5자리 시리얼 문자열 (e.g. "46255")
    if s.isdigit() and 10000 <= int(s) <= 90000:
        d = date(1899, 12, 30) + timedelta(days=int(s))
        return d.strftime("%Y-%m-%d")
    # YYYYMMDD 컴팩트 형식
    m_compact = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m_compact:
        return f"{m_compact.group(1)}-{m_compact.group(2)}-{m_compact.group(3)}"
    s = s.replace(".", "-").replace("/", "-")
    m = re.search(r"(\d{4})[-_](\d{1,2})[-_](\d{1,2})", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return datetime.now().strftime("%Y-%m-%d")


def _get_stock_name_to_code_map(username: str | None = None) -> dict[str, tuple[str, str]]:
    """보유종목 DB에서 종목명 -> (종목코드, 통화) 매핑 생성."""
    mapping: dict[str, tuple[str, str]] = {}
    try:
        portfolio_file = _get_user_dir(username) / "portfolio.json"
        if portfolio_file.exists():
            with open(portfolio_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for h in data.get("holdings", []):
                    name = str(h.get("name", "")).strip()
                    code = str(h.get("code", "")).strip()
                    curr = str(h.get("currency", "KRW")).strip().upper()
                    if name and code:
                        mapping[name.lower()] = (code, curr)
                        # 특수문자 제거 버전도 매핑
                        clean_n = re.sub(r"[\(\)\s_\-]", "", name.lower())
                        if clean_n:
                            mapping[clean_n] = (code, curr)
    except Exception:
        pass
    return mapping


def _dividend_file_import_fingerprint(record: dict[str, Any]) -> str | None:
    stored = record.get(FILE_IMPORT_FINGERPRINT_FIELD)
    if isinstance(stored, str) and stored.startswith("file-import:dividend:v1:"):
        return stored
    if record.get("source"):
        return None
    return build_file_import_fingerprint("dividend", {
        "owner": canonical_text(record.get("owner")),
        "broker": canonical_text(record.get("broker")),
        "account_name": canonical_text(record.get("account_name")),
        "date": canonical_text(record.get("date")),
        "code": canonical_text(record.get("code")),
        "name": canonical_text(record.get("name")),
        "currency": canonical_text(record.get("currency")).upper(),
        "amount": canonical_number(record.get("amount")),
        "gross_amount": canonical_number(record.get("gross_amount")),
        "tax": canonical_number(record.get("tax")),
        "fee": canonical_number(record.get("fee")),
        "memo": canonical_text(record.get("memo")),
        "source_reference": canonical_text(record.get("source_reference")),
    })


@financial_rmw('dividend_records.json')
def import_dividend_file_data(content: bytes, filename: str, fx_rate: float = 1385.0, username: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    
    if filename.lower().endswith(".xlsx"):
        wb = None
        for opts in (
            {"read_only": True, "data_only": True},
            {"read_only": True, "data_only": False},
            {"data_only": True},
            {},
        ):
            try:
                wb = openpyxl.load_workbook(io.BytesIO(content), **opts)
                break
            except Exception:
                continue
        if wb is None:
            raise ValueError("엑셀 파일을 열 수 없습니다. 파일 손상 여부를 확인하세요.")
        
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            return []
        
        headers = [_clean_str(h) for h in all_rows[0]]
        for raw in all_rows[1:]:
            if not any(raw):
                continue
            row_dict = {}
            for h, v in zip(headers, raw):
                if h:
                    row_dict[h] = v
            rows.append(row_dict)
    else:
        # CSV
        text = ""
        for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                text = content.decode(enc)
                break
            except Exception:
                continue
        reader = csv.DictReader(io.StringIO(text))
        for r in reader:
            if any(r.values()):
                rows.append({_clean_str(k): v for k, v in r.items() if k})

    existing_records = _read_dividend_records_for_import(username)
    now_iso = datetime.now().astimezone().isoformat()
    imported_records = []

    for r in rows:
        owner = _clean_str(r.get("소유자") or r.get("owner") or "모두")
        broker = _clean_str(r.get("증권사") or r.get("broker") or "")
        account_name = _clean_str(r.get("계좌명") or r.get("account_name") or "")
        
        raw_date = r.get("입금일 (Date)") or r.get("입금일") or r.get("date") or r.get("일자")
        date_str = _parse_date(raw_date)
        
        raw_code = _clean_str(r.get("종목코드") or r.get("code") or r.get("심볼") or "")
        raw_name = _clean_str(r.get("종목명") or r.get("name") or r.get("종목") or "")
        raw_curr = _clean_str(r.get("통화") or r.get("currency") or "").upper()

        if not raw_code and not raw_name:
            continue

        code, name, raw_curr = resolve_stock_info(raw_code, raw_name, raw_curr)

        raw_amt = r.get("실제 배당금 (입금액)") or r.get("실제 배당금") or r.get("배당금") or r.get("amount") or r.get("입금액")
        amount = _clean_num(raw_amt)
        if amount <= 0:
            continue
        gross_amount = _optional_num(r, ("세전배당금", "총배당금", "gross_amount"))
        tax = _optional_num(r, ("세금", "원천징수세", "tax"))
        fee = _optional_num(r, ("수수료", "fee"))

        memo = _clean_str(r.get("메모") or r.get("memo") or "")
        source_reference = _clean_str(
            r.get("거래ID") or r.get("거래번호") or r.get("참조번호")
            or r.get("transaction_id") or r.get("reference_id") or ""
        )
        if broker or account_name:
            extra = f"[{broker} {account_name}]".strip()
            if extra not in memo:
                memo = f"{extra} {memo}".strip()

        fx = get_historical_fx_rate(date_str, fallback=fx_rate) if raw_curr == "USD" else 1.0
        amount_krw = round(amount * fx, 0) if raw_curr == "USD" else round(amount, 0)

        record = {
            "id": str(uuid.uuid4()),
            "date": date_str,
            "code": code,
            "name": name,
            "currency": raw_curr,
            "amount": amount,
            "fx_rate": fx,
            "amount_krw": amount_krw,
            "owner": owner,
            "broker": broker,
            "account_name": account_name,
            "memo": memo,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        for field, value in (("gross_amount", gross_amount), ("tax", tax), ("fee", fee)):
            if value is not None:
                record[field] = value
        if source_reference:
            record["source_reference"] = source_reference
        imported_records.append(record)

    imported_records, _ = retain_new_occurrences(
        imported_records,
        existing_records,
        _dividend_file_import_fingerprint,
    )

    if imported_records:
        existing_records.extend(imported_records)
        write_dividend_records(existing_records, username)

    return imported_records


@financial_rmw('dividend_records.json')
def recalculate_dividend_historical_fx(username: str | None = None) -> int:
    """기존 등록된 모든 배당 내역의 환율을 입금일 기준 과거 환율로 일괄 재계산합니다."""
    records = read_dividend_records(username)
    updated_count = 0
    now_iso = datetime.now().astimezone().isoformat()

    for r in records:
        if r.get("source") == "ledger_interest":
            continue  # Ledger owns the exact KRW amount, including fractional input.
        curr = str(r.get("currency", "KRW")).upper()
        if curr == "USD":
            dt = str(r.get("date", ""))
            amt = float(r.get("amount", 0.0))
            old_fx = float(r.get("fx_rate", 0.0))
            new_fx = get_historical_fx_rate(dt, fallback=old_fx or 1385.0)
            
            r["fx_rate"] = new_fx
            r["amount_krw"] = round(amt * new_fx, 0)
            r["updated_at"] = now_iso
            updated_count += 1
        else:
            r["fx_rate"] = 1.0
            r["amount_krw"] = round(float(r.get("amount", 0.0)), 0)

    if updated_count > 0:
        write_dividend_records(records, username)
    return updated_count
