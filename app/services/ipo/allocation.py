"""IPO allocation lots and non-mutating links to authoritative P/L records."""
from __future__ import annotations

import json
import math
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any

from app.services import portfolio
from app.services.broker_registry import normalize_broker
from app.services.pnl_records import read_pnl_records_readonly
from app.services.ipo.applications import ApplicationRevisionConflict, InvalidApplicationError


class AllocationConflict(InvalidApplicationError):
    pass


def _quantity(value: object, field: str) -> int:
    if isinstance(value, bool): raise ValueError(f"{field} must be an integer")
    try: number = float(value)
    except (TypeError, ValueError) as exc: raise ValueError(f"{field} must be an integer") from exc
    if not math.isfinite(number) or not number.is_integer() or number < 0: raise ValueError(f"{field} must be a non-negative integer")
    return int(number)


def _code(value: object) -> str:
    return str(value or "").strip().upper().removeprefix("A")


def _account_id(record: dict[str, Any]) -> str:
    return str(record.get("account_id") or record.get("destination_account_id") or "").strip()


def _applications(data: dict[str, Any]) -> dict[str, Any]:
    return ((data.setdefault("settings", {}).setdefault("ipo", {"revision": 0, "applications": {}})).setdefault("applications", {}))


def _all_consumed(apps: dict[str, Any], pnl_id: str) -> int:
    consumed = 0
    for app in apps.values():
        for applicant in (app.get("applicants") or {}).values() if isinstance(app, dict) else []:
            allocation = applicant.get("allocation") if isinstance(applicant, dict) else None
            for link in allocation.get("links", []) if isinstance(allocation, dict) else []:
                if str(link.get("pnl_record_id") or "") == pnl_id:
                    consumed += _quantity(link.get("matched_quantity"), "matched_quantity")
    return consumed


def _load_applicant(data: dict[str, Any], ipo_id: str, owner: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    app = _applications(data).get(ipo_id)
    if not isinstance(app, dict): raise InvalidApplicationError("IPO application must be saved before allocation")
    applicant = (app.get("applicants") or {}).get(owner)
    if not isinstance(applicant, dict) or not applicant.get("account_id") or not applicant.get("broker_id"):
        raise InvalidApplicationError("Applicant account must be connected before allocation")
    return app, applicant, _applications(data)


def set_allocation(username: str | None, ipo_id: str, owner: str, quantity: object, offer_price: object, revision: int) -> dict[str, Any]:
    qty = _quantity(quantity, "allocated_quantity")
    try: price = float(offer_price)
    except (TypeError, ValueError) as exc: raise InvalidApplicationError("IPO_OFFER_PRICE_UNAVAILABLE") from exc
    if not math.isfinite(price) or price <= 0: raise InvalidApplicationError("IPO_OFFER_PRICE_UNAVAILABLE")
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(portfolio.EMPTY_PORTFOLIO)
        ipo = data.setdefault("settings", {}).setdefault("ipo", {"revision": 0, "applications": {}})
        if int(ipo.get("revision", 0)) != revision: raise ApplicationRevisionConflict("Revision conflict")
        _, applicant, _ = _load_applicant(data, ipo_id, owner)
        allocation = applicant.get("allocation") if isinstance(applicant.get("allocation"), dict) else None
        sold = sum(_quantity(link.get("matched_quantity"), "matched_quantity") for link in allocation.get("links", [])) if allocation else 0
        if qty < sold: raise AllocationConflict("ALLOCATION_BELOW_LINKED_QUANTITY")
        if allocation is None:
            allocation = {"id": str(uuid.uuid4()), "links": []}
            applicant["allocation"] = allocation
        allocation.update({"quantity": qty, "offer_price": price, "updated_at": datetime.now().astimezone().isoformat()})
        ipo["revision"] = revision + 1
        path.parent.mkdir(parents=True, exist_ok=True); temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"); temp.replace(path)
        return {"revision": revision + 1, "allocation_id": allocation["id"], "quantity": qty, "offer_price": price}


def _eligible(record: dict[str, Any], applicant: dict[str, Any], stock_code: str, listing_date: str | None) -> bool:
    if _account_id(record) != str(applicant.get("account_id") or ""): return False
    if normalize_broker(record.get("broker")) != str(applicant.get("broker_id") or ""): return False
    if _code(record.get("code")) != _code(stock_code): return False
    if _quantity(record.get("quantity"), "quantity") <= 0: return False
    if listing_date and str(record.get("date") or "") < listing_date: return False
    return True


def link_sale(username: str | None, ipo_id: str, owner: str, pnl_record_id: str, matched_quantity: object, revision: int, stock_code: str, listing_date: str | None) -> dict[str, Any]:
    requested = _quantity(matched_quantity, "matched_quantity")
    if requested <= 0: raise InvalidApplicationError("matched_quantity must be positive")
    with portfolio._LOCK:
        # Keep P/L lookup inside the same lock used by its delete guard: a
        # record cannot disappear between validation and link persistence.
        records = {str(item.get("id") or ""): item for item in read_pnl_records_readonly(username)}
        record = records.get(str(pnl_record_id))
        if not isinstance(record, dict): raise InvalidApplicationError("PNL_RECORD_NOT_FOUND")
        path = portfolio._get_portfolio_file(username); data = json.loads(path.read_text(encoding="utf-8"))
        ipo = data.setdefault("settings", {}).setdefault("ipo", {"revision": 0, "applications": {}})
        if int(ipo.get("revision", 0)) != revision: raise ApplicationRevisionConflict("Revision conflict")
        _, applicant, apps = _load_applicant(data, ipo_id, owner); allocation = applicant.get("allocation")
        if not isinstance(allocation, dict): raise InvalidApplicationError("ALLOCATION_REQUIRED")
        if not _eligible(record, applicant, stock_code, listing_date): raise InvalidApplicationError("IPO_SALE_MATCH_INELIGIBLE")
        links = allocation.setdefault("links", [])
        existing = next((link for link in links if str(link.get("pnl_record_id") or "") == str(pnl_record_id)), None)
        if existing:
            if _quantity(existing.get("matched_quantity"), "matched_quantity") == requested:
                return {"revision": revision, "allocation_id": allocation["id"], "matched_quantity": requested, "status": "IDEMPOTENT"}
            raise AllocationConflict("DUPLICATE_LINK_CONFLICT")
        sold = sum(_quantity(link.get("matched_quantity"), "matched_quantity") for link in links)
        if sold + requested > _quantity(allocation.get("quantity"), "allocated_quantity"): raise AllocationConflict("ALLOCATION_OVERRUN")
        if _all_consumed(apps, str(pnl_record_id)) + requested > _quantity(record.get("quantity"), "quantity"): raise AllocationConflict("PNL_OVERRUN")
        links.append({"pnl_record_id": str(pnl_record_id), "matched_quantity": requested, "linked_at": datetime.now().astimezone().isoformat()})
        ipo["revision"] = revision + 1; temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"); temp.replace(path)
        return {"revision": revision + 1, "allocation_id": allocation["id"], "matched_quantity": requested, "status": "LINKED"}


def unlink_sale(username: str | None, ipo_id: str, owner: str, pnl_record_id: str, revision: int) -> dict[str, Any]:
    """Explicitly remove one allocation-side relationship, never the P/L record."""
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(portfolio.EMPTY_PORTFOLIO)
        ipo = data.setdefault("settings", {}).setdefault("ipo", {"revision": 0, "applications": {}})
        if int(ipo.get("revision", 0)) != revision:
            raise ApplicationRevisionConflict("Revision conflict")
        _, applicant, _ = _load_applicant(data, ipo_id, owner)
        allocation = applicant.get("allocation")
        if not isinstance(allocation, dict):
            raise InvalidApplicationError("ALLOCATION_REQUIRED")
        links = allocation.get("links")
        if not isinstance(links, list):
            raise InvalidApplicationError("LINK_NOT_FOUND")
        target_id = str(pnl_record_id or "").strip()
        target_index = next((index for index, link in enumerate(links)
                             if isinstance(link, dict) and str(link.get("pnl_record_id") or "") == target_id), None)
        if target_index is None:
            raise InvalidApplicationError("LINK_NOT_FOUND")
        removed = links.pop(target_index)
        ipo["revision"] = revision + 1
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)
        return {"revision": revision + 1, "allocation_id": allocation.get("id"),
                "pnl_record_id": target_id, "matched_quantity": _quantity(removed.get("matched_quantity"), "matched_quantity"),
                "status": "UNLINKED"}


def allocation_summary(username: str | None, ipo_id: str, owner: str, stock_code: str, listing_date: str | None) -> dict[str, Any]:
    data = portfolio.read_portfolio(username); _, applicant, apps = _load_applicant(data, ipo_id, owner)
    allocation = applicant.get("allocation")
    if not isinstance(allocation, dict): return {"status": "UNRESOLVED", "allocation": None, "links": []}
    records = {str(item.get("id") or ""): item for item in read_pnl_records_readonly(username)}
    links_out=[]; sold=0; pnl_total=0.0; fee_total=0.0; tax_total=0.0; proceeds_total=0.0; has_dangling=False
    for link in allocation.get("links", []):
        record=records.get(str(link.get("pnl_record_id") or "")); qty=_quantity(link.get("matched_quantity"), "matched_quantity"); sold += qty
        if not isinstance(record, dict):
            has_dangling = True
            links_out.append({"pnl_record_id": link.get("pnl_record_id"), "matched_quantity": qty,
                              "date": None, "missing_pnl_record": True, "pnl_krw": None,
                              "fee": None, "tax": None, "sell_amount": None})
            continue
        ratio=qty / _quantity(record.get("quantity"), "quantity") if _quantity(record.get("quantity"), "quantity") else 0
        pnl_value=float(record.get("pnl_krw") or 0) * ratio if record else 0
        fee_value=float(record.get("fee") or 0) * ratio if record else 0
        tax_value=float(record.get("tax") or 0) * ratio if record else 0
        proceeds_value=float(record.get("sell_amount") or 0) * ratio if record else 0
        pnl_total += pnl_value; fee_total += fee_value; tax_total += tax_value; proceeds_total += proceeds_value
        links_out.append({"pnl_record_id": link.get("pnl_record_id"), "matched_quantity": qty, "date": record.get("date") if record else None, "pnl_krw": round(pnl_value, 0), "fee": round(fee_value, 0), "tax": round(tax_value, 0), "sell_amount": round(proceeds_value, 0)})
    total=_quantity(allocation.get("quantity"), "allocated_quantity"); remaining=total-sold
    status="LINK_DATA_MISSING" if has_dangling else "NO_ALLOCATION" if total == 0 else "FULLY_SOLD" if remaining == 0 else "PARTIALLY_SOLD" if sold else "UNSOLD"
    monetary = None if has_dangling else {"realized_pnl_krw": round(pnl_total, 0), "sell_amount": round(proceeds_total, 0), "fee": round(fee_total, 0), "tax": round(tax_total, 0)}
    return {"status": status, "has_dangling_links": has_dangling, "realized_pnl_complete": not has_dangling,
            "allocation": {"id": allocation.get("id"), "quantity": total, "offer_price": allocation.get("offer_price"),
                           "sold_quantity": sold, "remaining_quantity": remaining, **(monetary or {"realized_pnl_krw": None, "sell_amount": None, "fee": None, "tax": None})}, "links": links_out}


def sale_candidates(username: str | None, ipo_id: str, owner: str, stock_code: str, listing_date: str | None) -> list[dict[str, Any]]:
    """Sanitized, backend-filtered sale candidates; no client-side ledger filtering."""
    data = portfolio.read_portfolio(username); _, applicant, apps = _load_applicant(data, ipo_id, owner)
    result=[]
    for record in read_pnl_records_readonly(username):
        if not _eligible(record, applicant, stock_code, listing_date): continue
        available=_quantity(record.get("quantity"), "quantity")-_all_consumed(apps, str(record.get("id") or ""))
        if available > 0:
            result.append({"pnl_record_id": str(record.get("id")), "date": record.get("date"), "quantity": _quantity(record.get("quantity"), "quantity"), "available_quantity": available, "pnl_krw": record.get("pnl_krw")})
    return sorted(result, key=lambda item: (str(item.get("date") or ""), item["pnl_record_id"]))
