from __future__ import annotations

import csv
import io
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
import openpyxl

from app.services.historical_fx import get_historical_fx_rate
from app.services.stock_master import resolve_stock_info

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"

def _get_user_dir(username: str | None = None) -> Path:
    from app.services.user_manager import get_user_data_dir
    return get_user_data_dir(username)

def _get_pnl_file(username: str | None = None) -> Path:
    return _get_user_dir(username) / "realized_pnl_records.json"


def _ensure_pnl_file(username: str | None = None) -> Path:
    f = _get_pnl_file(username)
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        initial = {
            "records": [],
            "updated_at": datetime.now().astimezone().isoformat(),
        }
        with open(f, "w", encoding="utf-8") as fp:
            json.dump(initial, fp, ensure_ascii=False, indent=2)
    return f


def read_pnl_records(username: str | None = None) -> list[dict[str, Any]]:
    f = _ensure_pnl_file(username)
    try:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            return data.get("records", [])
    except Exception:
        return []


def write_pnl_records(records: list[dict[str, Any]], username: str | None = None) -> None:
    f = _ensure_pnl_file(username)
    payload = {
        "records": records,
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    with open(f, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def create_pnl_record(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    records = read_pnl_records(username)
    now_iso = datetime.now().astimezone().isoformat()
    
    currency = str(payload.get("currency", "KRW")).upper()
    pnl = float(payload.get("pnl", 0.0))
    date_val = str(payload.get("date", datetime.now().strftime("%Y-%m-%d")))
    fx_pnl_krw = float(payload.get("fx_pnl_krw", 0.0))
    
    raw_fx = payload.get("fx_rate")
    if currency == "USD":
        if raw_fx is not None and float(raw_fx) > 0:
            fx_rate = float(raw_fx)
        else:
            fx_rate = get_historical_fx_rate(date_val)
    else:
        fx_rate = 1.0

    pnl_krw = float(payload.get("pnl_krw", 0.0))
    if pnl_krw == 0.0 and (pnl != 0.0 or fx_pnl_krw != 0.0):
        pnl_krw = round(pnl * fx_rate + fx_pnl_krw, 0) if currency == "USD" else round(pnl, 0)

    is_ipo = bool(payload.get("is_ipo", False))
    asset_type = str(payload.get("asset_type") or "").strip().lower()
    raw_code = str(payload.get("code", "")).strip()
    raw_name = str(payload.get("name", "")).strip()
    raw_broker = str(payload.get("broker", "")).strip()
    raw_memo = str(payload.get("memo", "")).strip()

    re_fields = [
        "purchase_price", "sell_price", "expenses", "address", "real_estate_name",
        "original_property_type", "exclusive_area", "acquisition_date",
        "is_joint_ownership", "ownerships", "re_id"
    ]
    is_explicit_re = (
        asset_type == "real_estate"
        or raw_code == "REAL_ESTATE"
        or raw_broker == "부동산"
        or raw_name.startswith("[부동산]")
        or bool(payload.get("real_estate_name"))
        or bool(payload.get("re_id"))
    )
    if is_explicit_re:
        asset_type = "real_estate"
        code = raw_code or "REAL_ESTATE"
        name = raw_name or "부동산 매매"
        currency = "KRW"
        fx_rate = 1.0
        pnl_krw = pnl
    else:
        asset_type = "ipo" if is_ipo else "stock"
        code, name, currency = resolve_stock_info(raw_code, raw_name, currency)

    record = {
        "id": str(uuid.uuid4()),
        "date": date_val,
        "code": code,
        "name": name,
        "asset_type": asset_type,
        "currency": currency,
        "pnl": pnl,
        "fx_rate": fx_rate,
        "fx_pnl_krw": fx_pnl_krw,
        "pnl_krw": pnl_krw,
        "is_ipo": is_ipo,
        "owner": str(payload.get("owner", "모두")).strip(),
        "broker": str(payload.get("broker", "")).strip(),
        "account_name": str(payload.get("account_name", "")).strip(),
        "memo": str(payload.get("memo", "")).strip(),
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    # 부동산 전용 상세 필드 보존
    re_fields = [
        "purchase_price", "sell_price", "expenses", "address", "real_estate_name",
        "original_property_type", "exclusive_area", "acquisition_date",
        "is_joint_ownership", "ownerships", "re_id"
    ]
    for field in re_fields:
        if field in payload:
            record[field] = payload[field]

    records.append(record)
    write_pnl_records(records, username)
    return record


def update_pnl_record(record_id: str, payload: dict[str, Any], username: str | None = None) -> dict[str, Any] | None:
    records = read_pnl_records(username)
    target = None
    for r in records:
        if r.get("id") == record_id:
            target = r
            break
    if not target:
        return None

    currency = str(payload.get("currency", target.get("currency", "KRW"))).upper()
    pnl = float(payload.get("pnl", target.get("pnl", 0.0)))
    fx_pnl_krw = float(payload.get("fx_pnl_krw", target.get("fx_pnl_krw", 0.0)))
    fx_rate = float(payload.get("fx_rate", target.get("fx_rate", 1385.0))) if currency == "USD" else 1.0
    
    pnl_krw = float(payload.get("pnl_krw", 0.0))
    if pnl_krw == 0.0 and (pnl != 0.0 or fx_pnl_krw != 0.0):
        pnl_krw = round(pnl * fx_rate + fx_pnl_krw, 0) if currency == "USD" else round(pnl, 0)

    raw_code = str(payload.get("code", target.get("code", ""))).strip()
    raw_name = str(payload.get("name", target.get("name", ""))).strip()
    raw_broker = str(payload.get("broker", target.get("broker", ""))).strip()
    asset_type = str(payload.get("asset_type", target.get("asset_type", ""))).strip().lower()

    is_explicit_re = (
        asset_type == "real_estate"
        or raw_code == "REAL_ESTATE"
        or raw_broker == "부동산"
        or raw_name.startswith("[부동산]")
        or bool(payload.get("real_estate_name"))
        or bool(payload.get("re_id"))
        or bool(target.get("real_estate_name"))
        or bool(target.get("re_id"))
    )
    if is_explicit_re:
        asset_type = "real_estate"
        code = raw_code or "REAL_ESTATE"
        name = raw_name or "부동산 매매"
        currency = "KRW"
        fx_rate = 1.0
        pnl_krw = pnl
    else:
        is_ipo = bool(payload.get("is_ipo", target.get("is_ipo", False)))
        asset_type = "ipo" if is_ipo else "stock"
        code, name, currency = resolve_stock_info(raw_code, raw_name, currency)

    target["asset_type"] = asset_type

    target["date"] = str(payload.get("date", target.get("date")))
    target["code"] = code
    target["name"] = name
    target["currency"] = currency
    target["pnl"] = pnl
    target["fx_rate"] = fx_rate
    target["fx_pnl_krw"] = fx_pnl_krw
    target["pnl_krw"] = pnl_krw
    if "is_ipo" in payload:
        target["is_ipo"] = bool(payload.get("is_ipo"))
    target["owner"] = str(payload.get("owner", target.get("owner", "모두"))).strip()
    target["broker"] = str(payload.get("broker", target.get("broker", ""))).strip()
    target["account_name"] = str(payload.get("account_name", target.get("account_name", ""))).strip()
    target["memo"] = str(payload.get("memo", target.get("memo", ""))).strip()
    target["updated_at"] = datetime.now().astimezone().isoformat()

    # 부동산 전용 상세 필드 갱신
    re_fields = [
        "purchase_price", "sell_price", "expenses", "address", "real_estate_name",
        "original_property_type", "exclusive_area", "acquisition_date",
        "is_joint_ownership", "ownerships", "re_id"
    ]
    for field in re_fields:
        if field in payload:
            target[field] = payload[field]

    write_pnl_records(records, username)
    return target


def delete_pnl_record(record_id: str, username: str | None = None) -> bool:
    records = read_pnl_records(username)
    initial_len = len(records)
    records = [r for r in records if r.get("id") != record_id]
    if len(records) < initial_len:
        write_pnl_records(records, username)
        return True
    return False


def is_real_estate_pnl_record(r: dict[str, Any]) -> bool:
    """부동산 매각 실현손익 레코드 여부 판별 (주식/공모주와 명확히 분리)"""
    asset_type = str(r.get("asset_type") or "").strip().lower()
    code = str(r.get("code") or "").strip().upper()
    broker = str(r.get("broker") or "").strip()
    name = str(r.get("name") or "").strip()
    if asset_type == "real_estate" or code == "REAL_ESTATE" or broker == "부동산":
        return True
    if name.startswith("[부동산]") or bool(r.get("real_estate_name")) or bool(r.get("re_id")):
        return True
    return False


def clear_pnl_records(username: str | None = None) -> None:
    """주식/공모주 실현손익만 초기화하고, 부동산 매도 기록은 안전하게 보존합니다."""
    records = read_pnl_records(username)
    preserved = [r for r in records if is_real_estate_pnl_record(r)]
    write_pnl_records(preserved, username)


def get_pnl_summary(owner: str = "모두", year: int | str | None = None, trade_type: str = "all", username: str | None = None) -> dict[str, Any]:
    records = read_pnl_records(username)
    
    # 실현손익 탭 및 요약은 주식/공모주 전용이므로 부동산 실현손익은 완전 제외
    records = [r for r in records if not is_real_estate_pnl_record(r)]

    # 가용 연도 목록 추출
    available_years = sorted(list({str(r.get("date", ""))[:4] for r in records if len(str(r.get("date", ""))) >= 4}), reverse=True)
    if not available_years:
        available_years = [str(datetime.now().year)]

    filtered = []
    for r in records:
        if owner != "모두" and r.get("owner", "모두") != owner:
            continue
        r_date = str(r.get("date", ""))
        if year and str(year) != "all" and str(year) != "전체":
            if not r_date.startswith(str(year)):
                continue
        # 공모주 필터링 (all: 전체, ipo: 공모주만)
        if trade_type == "ipo" and not r.get("is_ipo", False):
            continue
        filtered.append(r)

    total_pnl_krw = sum(float(r.get("pnl_krw", 0.0)) for r in filtered)
    
    win_records = [r for r in filtered if float(r.get("pnl_krw", 0.0)) > 0]
    loss_records = [r for r in filtered if float(r.get("pnl_krw", 0.0)) < 0]
    
    total_win_krw = sum(float(r.get("pnl_krw", 0.0)) for r in win_records)
    total_loss_krw = sum(float(r.get("pnl_krw", 0.0)) for r in loss_records)
    win_rate = (len(win_records) / len(filtered) * 100) if filtered else 0.0

    monthly_schedule = {m: {"month": m, "total_krw": 0.0, "win_krw": 0.0, "loss_krw": 0.0, "items": []} for m in range(1, 13)}
    
    for r in filtered:
        r_date = str(r.get("date", ""))
        try:
            m = int(r_date.split("-")[1])
        except (IndexError, ValueError):
            m = 1
        if 1 <= m <= 12:
            amt_krw = float(r.get("pnl_krw", 0.0))
            monthly_schedule[m]["total_krw"] += amt_krw
            if amt_krw > 0:
                monthly_schedule[m]["win_krw"] += amt_krw
            elif amt_krw < 0:
                monthly_schedule[m]["loss_krw"] += amt_krw
            monthly_schedule[m]["items"].append(r)

    monthly_list = []
    for m in range(1, 13):
        item = monthly_schedule[m]
        item["total_krw"] = round(item["total_krw"], 0)
        item["win_krw"] = round(item["win_krw"], 0)
        item["loss_krw"] = round(item["loss_krw"], 0)
        item["items"].sort(key=lambda x: str(x.get("date", "")), reverse=True)
        monthly_list.append(item)

    # 연도별 집계 (오름차순 2022 -> 2026)
    yearly_dict: dict[str, dict[str, Any]] = {
        y: {"year": y, "total_krw": 0.0, "win_krw": 0.0, "loss_krw": 0.0, "items": []} for y in sorted(available_years)
    }
    for r in filtered:
        y_str = str(r.get("date", ""))[:4]
        if y_str in yearly_dict:
            amt_krw = float(r.get("pnl_krw", 0.0))
            yearly_dict[y_str]["total_krw"] += amt_krw
            if amt_krw > 0:
                yearly_dict[y_str]["win_krw"] += amt_krw
            elif amt_krw < 0:
                yearly_dict[y_str]["loss_krw"] += amt_krw
            yearly_dict[y_str]["items"].append(r)

    yearly_list = []
    for y in sorted(yearly_dict.keys()):
        item = yearly_dict[y]
        item["total_krw"] = round(item["total_krw"], 0)
        item["win_krw"] = round(item["win_krw"], 0)
        item["loss_krw"] = round(item["loss_krw"], 0)
        item["items"].sort(key=lambda x: str(x.get("date", "")), reverse=True)
        yearly_list.append(item)

    filtered_sorted = sorted(filtered, key=lambda x: str(x.get("date", "")), reverse=True)

    return {
        "year": str(year) if year else str(datetime.now().year),
        "trade_type": trade_type,
        "available_years": available_years,
        "total_pnl_krw": round(total_pnl_krw, 0),
        "total_win_krw": round(total_win_krw, 0),
        "win_count": len(win_records),
        "total_loss_krw": round(total_loss_krw, 0),
        "loss_count": len(loss_records),
        "win_rate": round(win_rate, 1),
        "record_count": len(filtered),
        "monthly_schedule": monthly_list,
        "yearly_schedule": yearly_list,
        "records": filtered_sorted,
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
    # 숫자 5자리 시리얼 문자열
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


def import_pnl_file_data(content: bytes, filename: str, fx_rate: float = 1385.0, username: str | None = None) -> list[dict[str, Any]]:
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

    from app.services.stock_master import resolve_stock_info

    existing_records = read_pnl_records(username)
    now_iso = datetime.now().astimezone().isoformat()
    imported_records = []

    for r in rows:
        owner = _clean_str(r.get("소유자") or r.get("owner") or "모두")
        broker = _clean_str(r.get("증권사") or r.get("broker") or "")
        account_name = _clean_str(r.get("계좌명") or r.get("account_name") or "")
        
        raw_date = r.get("매도일 (Date)") or r.get("매도일") or r.get("date") or r.get("일자")
        date_str = _parse_date(raw_date)
        
        raw_code = _clean_str(r.get("종목코드") or r.get("code") or r.get("심볼") or "")
        raw_name = _clean_str(r.get("종목명") or r.get("name") or r.get("종목") or "")
        raw_curr = _clean_str(r.get("통화") or r.get("currency") or "").upper()

        if not raw_code and not raw_name:
            continue

        code, name, raw_curr = resolve_stock_info(raw_code, raw_name, raw_curr)

        raw_pnl = r.get("실현손익") or r.get("실현 손익") or r.get("손익") or r.get("pnl") or r.get("수익금")
        pnl = _clean_num(raw_pnl)

        raw_fx_pnl = r.get("환차손익") or r.get("환차손") or r.get("환차익") or r.get("fx_pnl") or r.get("fx_pnl_krw")
        fx_pnl_krw = _clean_num(raw_fx_pnl)

        raw_ipo = _clean_str(r.get("공모주 여부") or r.get("공모주여부") or r.get("공모주") or r.get("is_ipo") or r.get("ipo") or "").upper()
        is_ipo = raw_ipo in ("Y", "O", "YES", "TRUE", "1", "공모주", "공모")

        memo = _clean_str(r.get("메모") or r.get("memo") or "")
        if broker or account_name:
            extra = f"[{broker} {account_name}]".strip()
            if extra not in memo:
                memo = f"{extra} {memo}".strip()

        fx = get_historical_fx_rate(date_str, fallback=fx_rate) if raw_curr == "USD" else 1.0
        pnl_krw = round(pnl * fx + fx_pnl_krw, 0) if raw_curr == "USD" else round(pnl, 0)

        record = {
            "id": str(uuid.uuid4()),
            "date": date_str,
            "code": code,
            "name": name,
            "currency": raw_curr,
            "pnl": pnl,
            "fx_rate": fx,
            "fx_pnl_krw": fx_pnl_krw,
            "pnl_krw": pnl_krw,
            "is_ipo": is_ipo,
            "owner": owner,
            "broker": broker,
            "account_name": account_name,
            "memo": memo,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        imported_records.append(record)

    if imported_records:
        existing_records.extend(imported_records)
        write_pnl_records(existing_records, username)

    return imported_records


def recalculate_pnl_historical_fx(username: str | None = None) -> int:
    """기존에 저장된 매도 실현손익 중 USD 레코드들의 환율과 원화 손익을 매도일자 기준으로 일괄 재계산합니다."""
    records = read_pnl_records(username)
    updated_count = 0
    for r in records:
        if str(r.get("currency", "KRW")).upper() == "USD":
            d_str = str(r.get("date", ""))
            if d_str:
                new_fx = get_historical_fx_rate(d_str, fallback=float(r.get("fx_rate", 1385.0)))
                pnl = float(r.get("pnl", 0.0))
                fx_pnl = float(r.get("fx_pnl_krw", 0.0))
                r["fx_rate"] = new_fx
                r["pnl_krw"] = round(pnl * new_fx + fx_pnl, 0)
                r["updated_at"] = datetime.now().astimezone().isoformat()
                updated_count += 1
    if updated_count > 0:
        write_pnl_records(records, username)
    return updated_count
