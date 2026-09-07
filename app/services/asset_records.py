from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
_LOCK = threading.Lock()

def _get_user_dir(username: str | None = None) -> Path:
    from app.services.user_manager import get_user_data_dir
    return get_user_data_dir(username)

def _get_records_file(username: str | None = None) -> Path:
    return _get_user_dir(username) / "asset_records.json"

EMPTY_RECORDS: dict[str, Any] = {"records": [], "updated_at": None}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _ensure_data_file(username: str | None = None) -> Path:
    f = _get_records_file(username)
    f.parent.mkdir(parents=True, exist_ok=True)
    if not f.exists():
        f.write_text(json.dumps(EMPTY_RECORDS, ensure_ascii=False, indent=2), encoding="utf-8")
    return f


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def read_asset_records(username: str | None = None) -> dict[str, Any]:
    with _LOCK:
        f = _ensure_data_file(username)
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                data = {"records": raw, "updated_at": None}
            elif isinstance(raw, dict):
                data = raw
            else:
                data = deepcopy(EMPTY_RECORDS)
        except (json.JSONDecodeError, OSError):
            data = deepcopy(EMPTY_RECORDS)
        data.setdefault("records", [])
        data.setdefault("updated_at", None)
        normalized: list[dict[str, Any]] = []
        for item in data["records"]:
            if not isinstance(item, dict):
                continue
            normalized.append(normalize_record(item, preserve_id=True))
        normalized.sort(key=lambda item: (item.get("date") or "", item.get("created_at") or "", item.get("id") or ""))
        data["records"] = normalized
        return data


def write_asset_records(data: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    with _LOCK:
        f = _ensure_data_file(username)
        data["updated_at"] = now_iso()
        temp_file = f.with_suffix(".json.tmp")
        temp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(f)
        return data


def normalize_record(raw: dict[str, Any], preserve_id: bool = False) -> dict[str, Any]:
    record_id = str(raw.get("id") or uuid.uuid4()) if preserve_id else str(raw.get("id") or uuid.uuid4())
    date = str(raw.get("date") or "").strip()
    return {
        "id": record_id,
        "date": date,
        "owner": str(raw.get("owner") or "모두").strip(),  # 가족 구성원
        "total_value_krw": _coerce_float(raw.get("total_value_krw")),
        "total_cost_krw": _coerce_float(raw.get("total_cost_krw")),
        "profit_krw": _coerce_float(raw.get("profit_krw")),
        "return_rate": _coerce_float(raw.get("return_rate")),
        "day_profit_krw": _coerce_float(raw.get("day_profit_krw")),
        "krw_value_krw": _coerce_float(raw.get("krw_value_krw")),
        "usd_value_krw": _coerce_float(raw.get("usd_value_krw")),
        "holding_count": int(_coerce_float(raw.get("holding_count"))),
        "currency": str(raw.get("currency") or "KRW").upper(),
        "source": str(raw.get("source") or "manual"),
        "memo": str(raw.get("memo") or "").strip(),
        "created_at": str(raw.get("created_at") or now_iso()),
        "updated_at": str(raw.get("updated_at") or now_iso()),
    }


def list_asset_records(username: str | None = None) -> list[dict[str, Any]]:
    return read_asset_records(username)["records"]


def upsert_asset_record(raw: dict[str, Any], by_date: bool = False, username: str | None = None) -> dict[str, Any]:
    data = read_asset_records(username)
    record = normalize_record(raw)
    existing_index = None
    if by_date and record["date"]:
        # 날짜 + owner 복합 키로 매칭 (구성원별 독립 기록)
        owner = record.get("owner") or "모두"
        for index, item in enumerate(data["records"]):
            if item.get("date") == record["date"] and (item.get("owner") or "모두") == owner:
                existing_index = index
                record["id"] = item["id"]
                record["created_at"] = item.get("created_at") or record["created_at"]
                break
    elif record["id"]:
        for index, item in enumerate(data["records"]):
            if item.get("id") == record["id"]:
                existing_index = index
                record["created_at"] = item.get("created_at") or record["created_at"]
                break
    if existing_index is None:
        data["records"].append(record)
    else:
        data["records"][existing_index] = record
    write_asset_records(data, username)
    return record



def delete_asset_record(record_id: str, username: str | None = None) -> bool:
    data = read_asset_records(username)
    before = len(data["records"])
    data["records"] = [item for item in data["records"] if item.get("id") != record_id]
    if len(data["records"]) == before:
        return False
    write_asset_records(data, username)
    return True

