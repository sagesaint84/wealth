from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.services.portfolio import canonical_broker_account_identity, normalize_broker_account_no, to_number


def create_accounts_routers(
    *,
    get_current_username: Callable[[Request], str],
    financial_user_locks: Callable[..., AbstractContextManager[None]],
    read_portfolio: Callable[..., dict],
    write_portfolio: Callable[..., None],
    get_family_members: Callable[[dict], list],
    get_dashboard: Callable[..., dict],
) -> tuple[APIRouter, APIRouter, APIRouter]:
    display_order_router = APIRouter()
    account_collection_router = APIRouter()
    account_changes_router = APIRouter()

    @display_order_router.get("/api/account-display-order")
    async def get_account_display_order_api(request: Request) -> dict:
        from app.services.account_display_order import get_account_display_order
        return get_account_display_order(get_current_username(request))

    @display_order_router.patch("/api/account-display-order")
    async def patch_account_display_order_api(request: Request) -> dict:
        from app.services.account_display_order import patch_account_display_order
        username = get_current_username(request)
        body = await request.body()
        if len(body) > 256_000:
            raise HTTPException(status_code=413, detail="순서 요청이 너무 큽니다.")
        try:
            payload = json.loads(body)
            return patch_account_display_order(username, payload)
        except (ValueError, TypeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="계좌/기관 순서 요청이 올바르지 않습니다.")

    @account_collection_router.get("/api/accounts")
    async def get_accounts(request: Request, group: str = "All", owner: str = "모두") -> dict:
        """Return accounts filtered by family_group and aggregated summary."""
        username = get_current_username(request)
        full = get_dashboard(username=username)
        accounts = full.get("accounts", [])
        filtered = [a for a in accounts
                    if (owner == "모두" or a.get("owner", "모두") == owner)
                    and (group == "All" or a.get("family_group", "All") == group)]
        filtered_account_ids = {a.get("id") for a in filtered}
        filtered_holdings = [
            holding for holding in full.get("holdings", [])
            if holding.get("account_id") in filtered_account_ids
        ]
        total_stock_value = sum(a.get("stock_value_krw", 0) for a in filtered)
        total_cash = sum(a.get("cash_krw", 0) for a in filtered)
        total_value = total_stock_value + total_cash
        profit = sum(a.get("profit_krw", 0) for a in filtered)
        holding_count = sum(a.get("holding_count", 0) for a in filtered)
        return {
            "summary": {
                "total_value_krw": total_value,
                "total_stock_value_krw": total_stock_value,
                "total_cash_krw": total_cash,
                "profit_krw": profit,
                "return_rate": profit / total_stock_value * 100 if total_stock_value else 0,
                "holding_count": holding_count,
                "account_count": len(filtered),
            },
            "accounts": filtered,
            "holdings": filtered_holdings,
            "fx_rates": full.get("fx_rates", {}),
            "currency_summary": full.get("currency_summary", {}),
            "classifications": full.get("classifications", []),
            "updated_at": full.get("updated_at"),
        }

    @account_collection_router.post("/api/accounts")
    async def create_account(request: Request) -> dict:
        """Create a new account entry."""
        import uuid
        username = get_current_username(request)
        body = await request.json()
        broker = (body.get("broker") or "").strip()
        account_name = (body.get("account_name") or body.get("name") or "").strip()
        owner = (body.get("owner") or "모두").strip()
        if not broker or not account_name:
            raise HTTPException(status_code=400, detail="증권사와 계좌 이름은 필수입니다.")
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            if owner not in set(get_family_members(data)):
                raise HTTPException(status_code=400, detail="등록된 가족 구성원만 소유자로 선택할 수 있습니다.")
            account_no = str(body.get("account_no") or "").strip()
            if account_no:
                duplicate = next((account for account in data["accounts"] if canonical_broker_account_identity(account.get("broker")) == canonical_broker_account_identity(broker) and normalize_broker_account_no(account.get("account_no")) == normalize_broker_account_no(account_no)), None)
                if duplicate:
                    code = "ACCOUNT_NUMBER_OWNER_CONFLICT" if str(duplicate.get("owner") or "모두") != owner else "ACCOUNT_ALREADY_EXISTS"
                    raise HTTPException(status_code=409, detail={"code": code, "message": "같은 증권사와 계좌번호의 계좌가 이미 등록되어 있습니다."})
            acc_type = (body.get("account_type") or "general").strip()
            income_lvl = (body.get("income_level") or "low").strip()
            annual_dep = max(0.0, float(body.get("annual_deposit") or 0.0))
            isa_tr = max(0.0, float(body.get("isa_transfer_amount") or 0.0))
            isa_year = str(body.get("isa_transfer_year") or "2026").strip()
            def _parse_bool(val: Any, default: bool = True) -> bool:
                if val is None:
                    return default
                if isinstance(val, bool):
                    return val
                if isinstance(val, (int, float)):
                    return bool(val)
                if isinstance(val, str):
                    s = val.strip().lower()
                    if s in ("false", "0", "no", "off", "non_deductible"):
                        return False
                    if s in ("true", "1", "yes", "on", "deductible"):
                        return True
                return default

            tax_deductible = _parse_bool(body.get("tax_deductible"), True)

            new_account = {
                "id": str(uuid.uuid4()),
                "broker": broker,
                "name": account_name,
                "owner": owner,
                "account_type": acc_type,
                "tax_deductible": tax_deductible,
                "income_level": income_lvl,
                "annual_deposit": annual_dep,
                "isa_transfer_amount": isa_tr,
                "isa_transfer_year": isa_year,
                "family_group": "All",
                "market_value_krw": 0,
                "stock_value_krw": 0,
                "cash_krw": 0,
                "cash_usd": 0,
                "cash_total_krw": 0,
                "profit_krw": 0,
                "holding_count": 0,
                "account_no": account_no,
            }
            cash_krw = float(to_number(body.get("cash_krw", 0.0)))
            cash_usd = float(to_number(body.get("cash_usd", 0.0)))
            if cash_krw > 0 or cash_usd > 0:
                cash_balances = data["settings"].setdefault("cash_balances", {})
                cash_balances[new_account["id"]] = {"KRW": cash_krw, "USD": cash_usd}
                usd_rate = float(data.get("settings", {}).get("usd_krw_rate", 1400.0))
                cash_total_krw = cash_krw + (cash_usd * usd_rate)
                new_account["cash_krw"] = cash_krw
                new_account["cash_usd"] = cash_usd
                new_account["cash_total_krw"] = cash_total_krw
                new_account["market_value_krw"] = cash_total_krw
            if "yearly_contributions" in body:
                new_account["yearly_contributions"] = body.get("yearly_contributions") or []
            data.setdefault("accounts", []).append(new_account)
            write_portfolio(data, username=username)
            return {"message": f"계좌 '{broker} - {account_name}'이(가) 추가되었습니다.", **new_account}

    @account_changes_router.delete("/api/accounts/{account_id}")
    async def delete_account(account_id: str, request: Request) -> dict:
        username = get_current_username(request)
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            if not any(account.get("id") == account_id for account in data["accounts"]):
                raise HTTPException(404, "계좌를 찾지 못했습니다.")
            data["accounts"] = [account for account in data["accounts"] if account.get("id") != account_id]
            data["holdings"] = [holding for holding in data["holdings"] if holding.get("account_id") != account_id]
            if "cash_balances" in data["settings"] and account_id in data["settings"]["cash_balances"]:
                del data["settings"]["cash_balances"][account_id]
            write_portfolio(data, username=username)
            return {"message": "증권사 계좌와 연결된 보유종목을 삭제했습니다."}

    @account_changes_router.put("/api/accounts/{account_id}")
    async def rename_account(account_id: str, payload: dict, request: Request) -> dict:
        username = get_current_username(request)
        name = str(payload.get("name") or payload.get("account_name") or "").strip()
        broker = str(payload.get("broker") or "").strip()
        if not name:
            raise HTTPException(400, "계좌 이름을 입력해 주세요.")
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            account = next((item for item in data["accounts"] if item.get("id") == account_id), None)
            if account is None:
                raise HTTPException(404, "계좌를 찾지 못했습니다.")
            owner_val = str(payload.get("owner") or "").strip()
            effective_broker = broker or str(account.get("broker") or "")
            effective_owner = owner_val or str(account.get("owner") or "모두")
            if "account_no" in payload:
                requested_no = str(payload.get("account_no") or "").strip()
                if requested_no:
                    duplicate = next((item for item in data["accounts"] if item.get("id") != account_id and canonical_broker_account_identity(item.get("broker")) == canonical_broker_account_identity(effective_broker) and normalize_broker_account_no(item.get("account_no")) == normalize_broker_account_no(requested_no)), None)
                    if duplicate:
                        code = "ACCOUNT_NUMBER_OWNER_CONFLICT" if str(duplicate.get("owner") or "모두") != effective_owner else "ACCOUNT_ALREADY_EXISTS"
                        raise HTTPException(409, detail={"code": code, "message": "같은 증권사와 계좌번호의 계좌가 이미 등록되어 있습니다."})
            account["name"] = name
            if broker:
                account["broker"] = broker
            if owner_val:
                account["owner"] = owner_val
            if "account_type" in payload:
                account["account_type"] = str(payload.get("account_type") or "general").strip()
            if "account_no" in payload:
                requested_no = str(payload.get("account_no") or "").strip()
                account["account_no"] = requested_no
            if "tax_deductible" in payload:
                td_val = payload.get("tax_deductible")
                if isinstance(td_val, bool):
                    account["tax_deductible"] = td_val
                elif isinstance(td_val, str):
                    account["tax_deductible"] = td_val.strip().lower() not in ("false", "0", "no", "off", "non_deductible")
                elif isinstance(td_val, (int, float)):
                    account["tax_deductible"] = bool(td_val)
                else:
                    account["tax_deductible"] = bool(td_val)
            if "income_level" in payload:
                account["income_level"] = str(payload.get("income_level") or "low").strip()
            if "annual_deposit" in payload:
                account["annual_deposit"] = max(0.0, float(payload.get("annual_deposit") or 0.0))
            if "isa_transfer_amount" in payload:
                account["isa_transfer_amount"] = max(0.0, float(payload.get("isa_transfer_amount") or 0.0))
            if "isa_transfer_year" in payload:
                account["isa_transfer_year"] = str(payload.get("isa_transfer_year") or "").strip()
            if "yearly_contributions" in payload:
                ycs = payload.get("yearly_contributions") or []
                inc = account.get("income_level") or "low"
                for yc in ycs:
                    if isinstance(yc, dict) and not yc.get("income_level"):
                        yc["income_level"] = inc
                account["yearly_contributions"] = ycs
            elif account.get("account_type") in ("pension_savings", "irp") and float(account.get("annual_deposit") or 0) > 0 and not account.get("yearly_contributions"):
                from datetime import datetime as _dt
                account["yearly_contributions"] = [{
                    "year": str(_dt.now().year),
                    "deposit": float(account.get("annual_deposit") or 0),
                    "is_deductible": account.get("tax_deductible", True),
                    "income_level": account.get("income_level", "low")
                }]

            if "cash_krw" in payload or "cash_usd" in payload:
                cash_balances = data["settings"].setdefault("cash_balances", {})
                existing_cash = cash_balances.get(account_id, {})
                cash_krw = float(to_number(payload["cash_krw"])) if "cash_krw" in payload else float(to_number(existing_cash.get("KRW", existing_cash.get("krw", 0.0))))
                cash_usd = float(to_number(payload["cash_usd"])) if "cash_usd" in payload else float(to_number(existing_cash.get("USD", existing_cash.get("usd", 0.0))))
                cash_balances[account_id] = {"KRW": cash_krw, "USD": cash_usd}

            for holding in data["holdings"]:
                if holding.get("account_id") == account_id:
                    holding["account_name"] = name
                    if broker:
                        holding["broker"] = broker
            write_portfolio(data, username=username)
            return {"message": "증권사 및 계좌 정보를 수정했습니다.", "dashboard": get_dashboard(username=username)}

    @account_changes_router.get("/api/tax-benefits")
    async def get_tax_benefits_endpoint(request: Request, owner: str | None = None) -> dict:
        from app.services.tax_benefit import get_total_tax_benefits
        username = get_current_username(request)
        data = read_portfolio(username=username)
        return get_total_tax_benefits(data, owner=owner)

    @account_changes_router.put("/api/accounts/{account_id}/cash")
    async def update_account_cash(account_id: str, payload: dict, request: Request) -> dict:
        username = get_current_username(request)
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username=username)
            if not any(account.get("id") == account_id for account in data["accounts"]):
                raise HTTPException(404, "계좌를 찾지 못했습니다.")
            cash_krw = float(to_number(payload.get("cash_krw") or payload.get("KRW")))
            cash_usd = float(to_number(payload.get("cash_usd") or payload.get("USD")))
            cash_balances = data["settings"].setdefault("cash_balances", {})
            cash_balances[account_id] = {"KRW": cash_krw, "USD": cash_usd}
            write_portfolio(data, username=username)
            return {"message": "계좌 예수금을 수정했습니다.", "dashboard": get_dashboard(username=username)}

    return display_order_router, account_collection_router, account_changes_router
