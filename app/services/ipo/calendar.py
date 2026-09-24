from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from app.services.dividend_records import read_dividend_records
from app.services.ledger import read_ledger
from app.services.pnl_records import read_pnl_records_readonly

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date_str(date_str: str) -> None:
    if not isinstance(date_str, str) or not DATE_PATTERN.match(date_str):
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD.")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"Invalid calendar date: {date_str}") from exc


def _owner_matches(record_owner: Any, filter_owner: str) -> bool:
    if not filter_owner or filter_owner == "모두":
        return True
    rec_owner = str(record_owner or "모두").strip()
    return rec_owner == filter_owner or rec_owner == "모두"


def build_moneylog_calendar_events(
    username: str | None,
    from_date: str,
    to_date: str,
    owner: str = "모두",
) -> list[dict[str, Any]]:
    validate_date_str(from_date)
    validate_date_str(to_date)
    if from_date > to_date:
        raise ValueError(f"from date ({from_date}) cannot be after to date ({to_date})")

    events: list[dict[str, Any]] = []

    # 1. Realized PnL records
    pnl_records = read_pnl_records_readonly(username)
    for rec in pnl_records:
        rec_date = str(rec.get("date") or "")[:10]
        if not (from_date <= rec_date <= to_date):
            continue
        if not _owner_matches(rec.get("owner"), owner):
            continue

        raw_asset_type = str(rec.get("asset_type") or "").lower()
        if raw_asset_type == "real_estate":
            subtype = "real_estate"
        elif raw_asset_type == "ipo" or rec.get("is_ipo"):
            subtype = "ipo"
        else:
            subtype = "stock"

        name = str(rec.get("name") or rec.get("code") or "종목").strip()
        title = name if ("매도" in name or "실현손익" in name) else f"{name} 매도"
        pnl_val = rec.get("pnl_krw")
        amount_krw = float(pnl_val) if pnl_val is not None else None

        events.append({
            "id": f"realized:{rec.get('id')}",
            "date": rec_date,
            "type": "realized_pnl",
            "subtype": subtype,
            "owner": str(rec.get("owner") or "모두").strip(),
            "title": title,
            "amount_krw": amount_krw,
            "source_id": str(rec.get("id")),
            "meta": {
                "code": rec.get("code"),
                "currency": rec.get("currency", "KRW"),
                "broker": rec.get("broker", ""),
                "account_name": rec.get("account_name", ""),
                "memo": rec.get("memo", ""),
            },
        })

    # 2. Dividend & Interest records
    div_records = read_dividend_records(username)
    for rec in div_records:
        rec_date = str(rec.get("date") or "")[:10]
        if not (from_date <= rec_date <= to_date):
            continue
        if not _owner_matches(rec.get("owner"), owner):
            continue

        code = str(rec.get("code") or "").upper()
        name = str(rec.get("name") or "").strip()
        income_type = str(rec.get("income_type") or "").strip()
        is_interest = (
            income_type == "account_interest"
            or (not income_type and (code.startswith("INTEREST") or ("이자" in name and "화이자" not in name)))
        )

        if is_interest:
            event_type = "interest"
            subtype = "interest"
            title = name or "이자"
        else:
            event_type = "dividend"
            subtype = "dividend"
            title = name if name.endswith("배당") else f"{name} 배당"

        amount_krw = float(rec.get("amount_krw", 0.0))

        events.append({
            "id": f"{event_type}:{rec.get('id')}",
            "date": rec_date,
            "type": event_type,
            "subtype": subtype,
            "owner": str(rec.get("owner") or "모두").strip(),
            "title": title,
            "amount_krw": amount_krw,
            "source_id": str(rec.get("id")),
            "meta": {
                "code": rec.get("code"),
                "currency": rec.get("currency", "KRW"),
                "broker": rec.get("broker", ""),
                "account_name": rec.get("account_name", ""),
                "memo": rec.get("memo", ""),
            },
        })

    # 3. Household Ledger transactions
    ledger_data = read_ledger(username)
    txs = ledger_data.get("transactions", [])
    for tx in txs:
        tx_date = str(tx.get("date") or "")[:10]
        if not (from_date <= tx_date <= to_date):
            continue
        if not _owner_matches(tx.get("owner"), owner):
            continue

        tx_type = str(tx.get("type") or "").lower()
        if tx_type == "income":
            event_type = "ledger_income"
            amount_krw = float(tx.get("amount") or 0.0)
            title = str(tx.get("merchant") or tx.get("category") or tx.get("memo") or "수입").strip()
        elif tx_type == "expense":
            event_type = "ledger_expense"
            amount_krw = -abs(float(tx.get("amount") or 0.0))
            title = str(tx.get("merchant") or tx.get("category") or tx.get("memo") or "지출").strip()
        else:
            continue

        events.append({
            "id": f"ledger:{tx.get('id')}",
            "date": tx_date,
            "type": event_type,
            "subtype": str(tx.get("category") or ("수입" if event_type == "ledger_income" else "지출")).strip(),
            "owner": str(tx.get("owner") or "모두").strip(),
            "title": title,
            "amount_krw": amount_krw,
            "source_id": str(tx.get("id")),
            "meta": {
                "category": tx.get("category"),
                "merchant": tx.get("merchant"),
                "pay_method": tx.get("pay_method"),
                "memo": tx.get("memo", ""),
            },
        })

    # 4. IPO calendar events (fail-closed, never swallows IpoStorageError)
    from app.services.ipo.store import get_ipo_calendar_events
    ipo_events = get_ipo_calendar_events(username, from_date, to_date, owner)
    events.extend(ipo_events)

    events.sort(key=lambda ev: (ev.get("date") or "", ev.get("type") or "", ev.get("id") or ""))
    return events
