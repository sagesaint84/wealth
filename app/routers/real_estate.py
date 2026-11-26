from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request


def create_real_estate_router(
    *,
    get_current_username: Callable[[Request], str],
    financial_user_locks: Callable[..., AbstractContextManager[None]],
    read_portfolio: Callable[[str], dict],
    now: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/real-estates")
    async def list_real_estates(request: Request) -> dict:
        username = get_current_username(request)
        from app.services.real_estate import get_real_estate_data
        return get_real_estate_data(username=username)

    @router.post("/api/real-estates")
    async def create_or_update_real_estate(request: Request) -> dict:
        username = get_current_username(request)
        body = await request.json()
        from app.services.real_estate import save_real_estate
        item = save_real_estate(body, username=username)
        return {"message": "부동산 자산이 저장되었습니다.", "real_estate": item}

    @router.delete("/api/real-estates/{re_id}")
    async def remove_real_estate(request: Request, re_id: str) -> dict:
        username = get_current_username(request)
        from app.services.real_estate import delete_real_estate
        ok = delete_real_estate(re_id, username=username)
        if not ok:
            raise HTTPException(404, "해당 부동산 항목을 찾을 수 없습니다.")
        return {"message": "부동산 자산이 삭제되었습니다."}


    @router.post("/api/real-estates/{re_id}/sell")
    async def sell_real_estate_and_record_pnl(request: Request, re_id: str) -> dict:
        """부동산 매각을 처리하고 실현손익(양도차익)을 기록합니다. 직접 매도(re_id='direct'/'new')도 지원."""
        username = get_current_username(request)
        body = await request.json()
        from app.services.portfolio import read_portfolio
        from app.services.pnl_records import create_pnl_record
        from app.services.real_estate import delete_real_estate

        with financial_user_locks(username, 'portfolio.json', 'realized_pnl_records.json'):
            pf = read_portfolio(username)
            re_list = pf.get("real_estates", [])
            target = next((r for r in re_list if r.get("id") == re_id), None)

            is_direct = re_id in ("direct", "new") or not target
            if not target and not is_direct:
                raise HTTPException(404, "해당 부동산 항목을 찾을 수 없습니다.")

            sell_price = float(body.get("sell_price") or 0.0)
            expenses = float(body.get("expenses") or 0.0)
            sell_date = str(body.get("sell_date") or now().strftime("%Y-%m-%d")).strip()
            purchase_price = float(body.get("purchase_price") or (target.get("purchase_price") if target else 0.0) or 0.0)
            pnl_krw = round(sell_price - purchase_price - expenses)

            re_name = str(body.get("name") or (target.get("name") if target else "부동산") or "부동산").strip()
            pnl_title = f"[부동산] {re_name}"
            owner = str(body.get("owner") or (target.get("owner") if target else "모두") or "모두").strip()
            memo = str(body.get("memo") or f"매도가 ₩{sell_price:,.0f}, 매수가 ₩{purchase_price:,.0f}, 필요경비 ₩{expenses:,.0f}").strip()

            address = str(target.get("address", "") if target else body.get("address", "")).strip()
            original_property_type = str(target.get("property_type", "own") if target else body.get("property_type", "own")).strip()
            exclusive_area = float(target.get("exclusive_area") or body.get("exclusive_area") or 0.0) if target else float(body.get("exclusive_area") or 0.0)
            acquisition_date = str(target.get("contract_date", "") if target else body.get("acquisition_date", "")).strip()
            is_joint = bool(target.get("is_joint_ownership", False) if target else body.get("is_joint_ownership", False))
            ownerships = target.get("ownerships", []) if target else body.get("ownerships", [])

            pnl_payload = {
                "date": sell_date,
                "code": "REAL_ESTATE",
                "name": pnl_title,
                "asset_type": "real_estate",
                "currency": "KRW",
                "pnl": pnl_krw,
                "pnl_krw": pnl_krw,
                "owner": owner,
                "memo": memo,
                "re_id": re_id if not is_direct else "",
                "real_estate_name": re_name,
                "purchase_price": purchase_price,
                "sell_price": sell_price,
                "expenses": expenses,
                "address": address,
                "original_property_type": original_property_type,
                "exclusive_area": exclusive_area,
                "acquisition_date": acquisition_date,
                "is_joint_ownership": is_joint,
                "ownerships": ownerships,
            }
            pnl_rec = create_pnl_record(pnl_payload, username=username)

            removed = False
            if target and body.get("remove_from_assets", True):
                delete_real_estate(re_id, username=username)
                removed = True

            return {
                "message": f"[{re_name}] 매각 실현손익(₩{pnl_krw:,.0f})이 성공적으로 기록되었습니다.",
                "pnl_krw": pnl_krw,
                "pnl_record": pnl_rec,
                "removed_from_assets": removed,
            }


    @router.get("/api/real-estates/kb-price")
    async def get_kb_price_api(
        request: Request,
        name: str = "",
        area: float = 0.0,
        complex_no: str = ""
    ) -> dict:
        get_current_username(request)
        import re
        from app.services.kb_land import search_kb_complex, get_kb_market_prices

        c_no = complex_no.strip()
        complex_info = None
        complexes = []

        if not c_no and name:
            clean_name = re.sub(r'\s*\d+[-~_동호].*$', '', name).strip()
            complexes = search_kb_complex(clean_name or name)
            if complexes:
                c_no = complexes[0]["complex_no"]
                complex_info = complexes[0]

        if not c_no:
            return {"ok": False, "message": f"'{name}' 단지를 KB부동산에서 찾을 수 없습니다. 아파트명을 확인해 주세요.", "complexes": []}

        price_data = get_kb_market_prices(c_no, target_area=area if area > 0 else None)
        if "error" in price_data:
            return {"ok": False, "message": price_data["error"], "complexes": complexes}

        return {
            "ok": True,
            "complex_no": c_no,
            "complex_info": complex_info,
            "complexes": complexes,
            "matched": price_data.get("matched"),
            "types": price_data.get("types", []),
        }


    @router.post("/api/real-estates/{re_id}/refresh-kb-price")
    async def refresh_kb_price_api(request: Request, re_id: str) -> dict:
        username = get_current_username(request)
        with financial_user_locks(username, 'portfolio.json'):
            data = read_portfolio(username)
            real_estates = data.get("real_estates", [])
            item = next((r for r in real_estates if r.get("id") == re_id), None)
            if not item:
                raise HTTPException(404, "부동산 항목을 찾을 수 없습니다.")

            import re
            from datetime import datetime
            from app.services.kb_land import search_kb_complex, get_kb_market_prices
            from app.services.portfolio import write_portfolio

            c_no = (item.get("kb_complex_no") or "").strip()
            if not c_no:
                clean_name = re.sub(r'\s*\d+[-~_동호].*$', '', item.get("name") or "").strip()
                complexes = search_kb_complex(clean_name or item.get("name") or "")
                if complexes:
                    c_no = complexes[0]["complex_no"]
                    item["kb_complex_no"] = c_no

            if not c_no:
                raise HTTPException(404, f"'{item.get('name')}' 단지를 KB부동산에서 찾지 못했습니다.")

            excl_area = float(item.get("exclusive_area") or 0.0)
            price_data = get_kb_market_prices(c_no, target_area=excl_area if excl_area > 0 else None)
            if "error" in price_data or not price_data.get("matched"):
                raise HTTPException(400, price_data.get("error") or "KB시세 정보를 찾을 수 없습니다.")

            matched = price_data["matched"]
            new_price = matched.get("deal_avg") or matched.get("deal_high") or matched.get("deal_low") or 0
            if new_price > 0:
                item["current_price"] = float(new_price)
                item["kb_complex_no"] = c_no
                item["kb_matched_type"] = matched.get("type_display")
                item["updated_at"] = datetime.now().astimezone().isoformat()
                write_portfolio(data, username)
                return {
                    "message": f"KB시세가 갱신되었습니다. (₩{new_price:,.0f})",
                    "new_price": new_price,
                    "matched_type": matched.get("type_display"),
                    "real_estate": item
                }
            else:
                raise HTTPException(400, "조회된 KB시세 금액이 0원입니다.")

    return router
