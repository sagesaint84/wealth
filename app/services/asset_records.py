from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from app.services.test_safety import assert_write_allowed


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
        f = _get_records_file(username)
        assert_write_allowed(f)
        f = _ensure_data_file(username)
        data["updated_at"] = now_iso()
        temp_file = f.with_suffix(".json.tmp")
        temp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_file.replace(f)
        return data


def normalize_record(raw: dict[str, Any], preserve_id: bool = False) -> dict[str, Any]:
    record_id = str(raw.get("id") or uuid.uuid4()) if preserve_id else str(raw.get("id") or uuid.uuid4())
    date = str(raw.get("date") or "").strip()
    record = {
        "id": record_id,
        "date": date,
        "owner": str(raw.get("owner") or "모두").strip(),
        "total_value_krw": _coerce_float(raw.get("total_value_krw")),
        "total_assets_krw": _coerce_float(raw.get("total_assets_krw", raw.get("total_value_krw"))),
        "total_debt_krw": _coerce_float(raw.get("total_debt_krw")),
        "net_worth_krw": _coerce_float(raw.get("net_worth_krw", _coerce_float(raw.get("total_assets_krw", raw.get("total_value_krw"))) - _coerce_float(raw.get("total_debt_krw")))),
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
    # Preserve session provenance if present (pass-through for backward compatibility)
    if raw.get("holdings_session") is not None:
        record["holdings_session"] = raw["holdings_session"]
    return record


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


def normalize_session_date(val: Any) -> str | None:
    """Normalize a session date string to ISO YYYY-MM-DD format."""
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return s


def merge_price_session_obs(
    stored_obs: dict[str, Any],
    incoming_obs: dict[str, Any],
) -> dict[str, Any]:
    """
    Monotonically merge incoming price_session_obs into stored_obs.
    - Newer incoming session (inc_as_of > cur_as_of): updates stored observation.
    - Same-date incoming session (inc_as_of == cur_as_of): updates stored observation.
    - Older incoming session (inc_as_of < cur_as_of): rejects incoming, keeps stored observation.
    - Incomplete/unknown incoming (no valid as_of): rejects incoming, preserves stored observation.
    - If stored observation has no date: accepts incoming observation.
    """
    for code, inc in (incoming_obs or {}).items():
        if not isinstance(inc, dict):
            continue
        inc_as_of = normalize_session_date(inc.get("as_of"))
        if not inc_as_of:
            continue
        cur = stored_obs.get(code)
        if isinstance(cur, dict) and cur.get("as_of"):
            cur_as_of = normalize_session_date(cur.get("as_of"))
            if cur_as_of and inc_as_of < cur_as_of:
                continue
        stored_obs[code] = inc
    return stored_obs


def build_stock_record_from_holdings(
    holdings: list[dict[str, Any]],
    owner: str = "모두",
    today: str | None = None,
    source: str = "auto",
    memo: str = "자동 기록",
    fx_rates: dict[str, float] | None = None,
    prev_session_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    주식기록(asset_records) canonical snapshot 생성 헬퍼.
    예수금/외부 현금흐름을 엄격히 배제하고 순수 보유 주식/ETF 등의 시장 평가액과
    가격 변동 손익만을 기록합니다.

    prev_session_map: instrument_key -> last_recorded_session_date.
      An instrument may contribute to day_profit_krw ONLY when:
      - current trustworthy session/as_of exists
      - prev_session_map is not None
      - instrument_key in prev_session_map
      - previous session is known
      - current session has strictly ADVANCED (current_session > previous_session)
      Otherwise, contribution = 0.

    The returned dict includes 'holdings_session' mapping each instrument_key to
    its session date (persisted_session = max(previous, current)) so the caller
    can persist it without moving backward.
    """
    today_str = today or datetime.now().astimezone().date().isoformat()
    rates = fx_rates or {"KRW": 1.0, "USD": 1385.0}
    stock_value_krw = 0.0
    stock_cost_krw = 0.0
    krw_value_krw = 0.0
    usd_value_krw = 0.0
    day_profit_krw = 0.0
    holding_count = 0
    # Accumulate session provenance for each instrument encountered
    curr_session_map: dict[str, str] = {}

    for h in holdings:
        curr = (h.get("currency") or "KRW").upper()
        fx = 1.0 if curr == "KRW" else float(rates.get(curr, 1385.0))
        m_val = float(h.get("market_value_krw") or (float(h.get("quantity", 0)) * float(h.get("current_price", 0)) * fx))
        c_val = float(h.get("cost_value_krw") or (float(h.get("quantity", 0)) * float(h.get("avg_price", 0)) * fx))

        stock_value_krw += m_val
        stock_cost_krw += c_val
        holding_count += 1

        if curr == "KRW":
            krw_value_krw += m_val
        else:
            usd_value_krw += m_val

        code = str(h.get("code") or "").strip().upper()

        # Build stable instrument key: currency:code (stable across market alias changes)
        instrument_key = f"{curr}:{code}" if code else ""

        # Determine paired observation for stock record:
        # Prioritize separated record-specific observation if present
        if h.get("record_day_change_rate") is not None:
            r = float(h.get("record_day_change_rate"))
            as_of = h.get("record_day_change_as_of") or h.get("day_change_as_of")
        else:
            r = float(h.get("day_change_rate") or 0.0)
            as_of = h.get("day_change_as_of")

        curr_as_of = normalize_session_date(as_of)
        prev_as_of = (
            normalize_session_date(prev_session_map.get(instrument_key))
            if prev_session_map
            else None
        )

        # Monotonic session provenance tracking for this instrument:
        # Rule for known valid dates:
        #   persisted_session = max(previous_session, current_session)
        # If there is no previous session:
        #   establish current known session as baseline.
        # If current session is unknown:
        #   preserve previous known session if applicable.
        if instrument_key:
            if curr_as_of and prev_as_of:
                persisted_session = max(prev_as_of, curr_as_of)
            elif curr_as_of:
                persisted_session = curr_as_of
            elif prev_as_of:
                persisted_session = prev_as_of
            else:
                persisted_session = None

            if persisted_session:
                if instrument_key in curr_session_map:
                    curr_session_map[instrument_key] = max(
                        curr_session_map[instrument_key], persisted_session
                    )
                else:
                    curr_session_map[instrument_key] = persisted_session

        # Strict safe-by-default monotonic P/L contract:
        # An instrument may contribute to day_profit_krw ONLY when ALL are true:
        # 1. current trustworthy session/as_of exists
        # 2. previous provenance map exists
        # 3. the instrument exists in the previous provenance map
        # 4. previous session is known
        # 5. current session has strictly ADVANCED (current_session > previous_session)
        # Otherwise contribution = 0.
        if r != 0 and (100.0 + r) > 0:
            if (
                curr_as_of is not None
                and prev_session_map is not None
                and instrument_key
                and instrument_key in prev_session_map
                and prev_as_of is not None
                and curr_as_of > prev_as_of
            ):
                day_profit_krw += m_val * (r / (100.0 + r))

    profit_krw = stock_value_krw - stock_cost_krw
    return_rate = (profit_krw / stock_cost_krw * 100.0) if stock_cost_krw > 0 else 0.0

    result: dict[str, Any] = {
        "date": today_str,
        "total_value_krw": round(stock_value_krw, 2),
        "total_cost_krw": round(stock_cost_krw, 2),
        "profit_krw": round(profit_krw, 2),
        "return_rate": round(return_rate, 2),
        "day_profit_krw": round(day_profit_krw, 2),
        "krw_value_krw": round(krw_value_krw, 2),
        "usd_value_krw": round(usd_value_krw, 2),
        "holding_count": len(holdings),
        "currency": "KRW",
        "source": source,
        "memo": memo,
        "owner": owner,
    }
    # Only attach holdings_session when we actually have provenance data
    if curr_session_map:
        result["holdings_session"] = curr_session_map
    return result
