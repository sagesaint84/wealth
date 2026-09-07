from copy import deepcopy
from datetime import datetime
from typing import Any
import uuid

from app.services.portfolio import read_portfolio, write_portfolio


def save_real_estate(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    """부동산(자가/임대/임차) 항목을 생성하거나 수정합니다."""
    data = read_portfolio(username)
    real_estates = data.setdefault("real_estates", [])
    loans = data.setdefault("loan_accounts", [])

    re_id = payload.get("id") or f"re-{uuid.uuid4().hex[:12]}"
    existing_index = next((i for i, r in enumerate(real_estates) if r.get("id") == re_id), None)

    prop_type = (payload.get("property_type") or "own").strip().lower()
    if prop_type not in ("own", "rental", "lease"):
        prop_type = "own"

    # 연결 대출 ID 목록 정돈
    raw_loan_ids = payload.get("linked_loan_ids") or []
    if isinstance(raw_loan_ids, str):
        raw_loan_ids = [s.strip() for s in raw_loan_ids.split(",") if s.strip()]
    linked_loan_ids = list({str(lid).strip() for lid in raw_loan_ids if str(lid).strip()})

    # 공동명의 지분율 처리
    raw_ownerships = payload.get("ownerships") or []
    ownerships = []
    if isinstance(raw_ownerships, list):
        for item in raw_ownerships:
            m_owner = (item.get("owner") or "").strip()
            try:
                m_ratio = max(0.0, min(100.0, float(item.get("ratio") or 0.0)))
            except (ValueError, TypeError):
                m_ratio = 0.0
            if m_owner and m_ratio > 0:
                ownerships.append({"owner": m_owner, "ratio": m_ratio})

    is_joint = bool(payload.get("is_joint_ownership")) and len(ownerships) > 0
    if is_joint:
        owner_display = " · ".join([f"{o['owner']} {int(o['ratio']) if o['ratio'].is_integer() else o['ratio']}%" for o in ownerships])
    else:
        single_owner = (payload.get("owner") or "모두").strip()
        ownerships = [{"owner": single_owner, "ratio": 100.0}]
        owner_display = single_owner

    record = {
        "id": re_id,
        "property_type": prop_type,  # own: 자가, rental: 임대준주택, lease: 임차(전월세거주)
        "name": (payload.get("name") or "").strip() or "부동산 자산",
        "dong_ho": (payload.get("dong_ho") or "").strip(),
        "address": (payload.get("address") or "").strip(),
        "owner": owner_display,
        "is_joint_ownership": is_joint,
        "ownerships": ownerships,
        "purchase_price": max(0.0, float(payload.get("purchase_price") or 0.0)),
        "current_price": max(0.0, float(payload.get("current_price") or 0.0)),
        "deposit_amount": max(0.0, float(payload.get("deposit_amount") or 0.0)),
        "monthly_rent": max(0.0, float(payload.get("monthly_rent") or 0.0)),
        "contract_date": (payload.get("contract_date") or "").strip(),
        "expiry_date": (payload.get("expiry_date") or "").strip(),
        "exclusive_area": max(0.0, float(payload.get("exclusive_area") or 0.0)),
        "linked_loan_ids": linked_loan_ids,
        "kb_complex_no": (payload.get("kb_complex_no") or "").strip(),
        "kb_matched_type": (payload.get("kb_matched_type") or "").strip(),
        "memo": (payload.get("memo") or "").strip(),
        "updated_at": datetime.now().astimezone().isoformat(),
    }

    # 만약 현재 시세가 0이고 매수가가 있다면 시세를 매수가로 기본 설정
    if record["current_price"] <= 0.0 and record["purchase_price"] > 0.0:
        record["current_price"] = record["purchase_price"]

    if existing_index is not None:
        real_estates[existing_index] = record
    else:
        record["created_at"] = record["updated_at"]
        real_estates.append(record)

    # 연결된 대출 계좌의 linked_property_id 양방향 업데이트
    for loan in loans:
        lid = loan.get("id")
        if lid in linked_loan_ids:
            loan["linked_property_id"] = re_id
        elif loan.get("linked_property_id") == re_id and lid not in linked_loan_ids:
            loan["linked_property_id"] = ""

    write_portfolio(data, username)
    return record


def delete_real_estate(re_id: str, username: str | None = None) -> bool:
    """부동산 항목을 삭제하고 대출과의 연결을 해제합니다."""
    data = read_portfolio(username)
    real_estates = data.get("real_estates", [])
    before = len(real_estates)
    data["real_estates"] = [r for r in real_estates if r.get("id") != re_id]
    if len(data["real_estates"]) == before:
        return False

    # 연결되어 있던 대출 계좌의 linked_property_id 해제
    for loan in data.get("loan_accounts", []):
        if loan.get("linked_property_id") == re_id:
            loan["linked_property_id"] = ""

    write_portfolio(data, username)
    return True


def get_real_estate_data(username: str | None = None) -> dict[str, Any]:
    """부동산 목록 및 통계(자가/임대/임차, 손익, 대출 연동)를 계산합니다."""
    data = read_portfolio(username)
    real_estates = data.get("real_estates", [])
    loans = data.get("loan_accounts", [])

    today_dt = datetime.now().astimezone().date()

    # 대출 매핑 사전
    loan_map = {l.get("id"): l for l in loans if l.get("id")}

    enriched_list = []
    total_re_asset_val = 0.0      # 자가 + 임대준 주택 시세(자산)
    total_re_purchase_val = 0.0   # 자가 + 임대 매수가
    total_tenant_deposit = 0.0    # 임차 전세보증금 (내 자산)
    total_landlord_deposit = 0.0  # 임대 전세보증금 (돌려줄 부채)
    total_linked_loan_debt = 0.0  # 부동산에 연결된 대출 부채 합계

    for re_item in real_estates:
        item = deepcopy(re_item)
        p_type = item.get("property_type") or "own"
        purch = float(item.get("purchase_price") or 0.0)
        curr = float(item.get("current_price") or 0.0)
        dep = float(item.get("deposit_amount") or 0.0)

        # 소유권 지분율 정규화
        if not item.get("ownerships"):
            item["ownerships"] = [{"owner": item.get("owner") or "모두", "ratio": 100.0}]

        # 1. 평가손익 및 수익률 (자가 또는 임대 주택인 경우)
        profit_loss = 0.0
        return_rate = 0.0
        if p_type in ("own", "rental") and purch > 0:
            profit_loss = curr - purch
            return_rate = round((profit_loss / purch) * 100, 2)
        item["profit_loss"] = round(profit_loss)
        item["return_rate"] = return_rate

        # 2. 만기일 D-Day
        exp_date_str = item.get("expiry_date") or ""
        d_day = None
        if exp_date_str:
            try:
                exp_dt = datetime.strptime(exp_date_str[:10], "%Y-%m-%d").date()
                d_day = (exp_dt - today_dt).days
            except ValueError:
                pass
        item["d_day"] = d_day

        # 3. 연결 대출 정보 취합
        linked_ids = item.get("linked_loan_ids") or []
        connected_loans = []
        loan_balance_sum = 0.0
        loan_monthly_interest_sum = 0.0

        for lid in linked_ids:
            if lid in loan_map:
                l_obj = loan_map[lid]
                c_bal = float(l_obj.get("current_balance") or 0.0)
                r_rate = float(l_obj.get("interest_rate") or 0.0)
                m_int = float(l_obj.get("monthly_interest") or (c_bal * (r_rate / 100) / 12))
                connected_loans.append({
                    "id": lid,
                    "bank_name": l_obj.get("bank_name") or "",
                    "product_name": l_obj.get("product_name") or "",
                    "loan_type": l_obj.get("loan_type") or "mortgage",
                    "current_balance": round(c_bal),
                    "interest_rate": r_rate,
                    "monthly_interest": round(m_int),
                })
                loan_balance_sum += c_bal
                loan_monthly_interest_sum += m_int

        item["connected_loans"] = connected_loans
        item["linked_loan_balance"] = round(loan_balance_sum)
        item["linked_loan_monthly_interest"] = round(loan_monthly_interest_sum)

        # 4. 부동산 순자산(순에퀴티) 계산
        if p_type == "own":
            net_equity = curr - loan_balance_sum
            total_re_asset_val += curr
            total_re_purchase_val += purch
            total_linked_loan_debt += loan_balance_sum
        elif p_type == "rental":
            net_equity = curr - (dep + loan_balance_sum)
            total_re_asset_val += curr
            total_re_purchase_val += purch
            total_landlord_deposit += dep
            total_linked_loan_debt += loan_balance_sum
        else:  # lease (임차)
            net_equity = dep - loan_balance_sum
            total_tenant_deposit += dep
            total_linked_loan_debt += loan_balance_sum

        item["net_equity"] = round(net_equity)
        enriched_list.append(item)

    total_real_estate_debt = total_landlord_deposit + total_linked_loan_debt
    total_unrealized_profit = (total_re_asset_val - total_re_purchase_val) if total_re_purchase_val > 0 else 0.0
    total_unrealized_rate = round((total_unrealized_profit / total_re_purchase_val) * 100, 2) if total_re_purchase_val > 0 else 0.0

    # 5. 매도 완료된 부동산 실현손익 내역 취합
    import re
    from app.services.pnl_records import read_pnl_records
    all_pnl = read_pnl_records(username)
    sold_list = []
    total_sold_pnl = 0.0
    total_sold_purchase = 0.0
    total_sold_sell = 0.0

    # 등록된 부동산 명칭 목록 추출 (지능형 매칭용)
    registered_re_names = [str(item.get("name") or "").strip() for item in enriched_list if item.get("name")]
    re_keyword_pat = re.compile(r"부동산|아파트|오피스텔|빌라|주택|단지|상가|토지|건물|원룸|분양권|재개발", re.IGNORECASE)

    for r in all_pnl:
        asset_type = str(r.get("asset_type") or "").lower()
        code = str(r.get("code") or "").upper()
        name = str(r.get("name") or "")
        broker = str(r.get("broker") or "")
        memo_str = str(r.get("memo") or "")

        is_re = (
            asset_type == "real_estate"
            or code == "REAL_ESTATE"
            or broker == "부동산"
            or "[부동산]" in name
            or "부동산" in name
            or (name and any(rn in name for rn in registered_re_names if len(rn) >= 2))
            or bool(re_keyword_pat.search(name))
            or (bool(re_keyword_pat.search(memo_str)) and asset_type != "stock")
        )
        if is_re:
            sold_item = deepcopy(r)
            sold_item["asset_type"] = "real_estate"
            purch = float(sold_item.get("purchase_price") or 0.0)
            sell = float(sold_item.get("sell_price") or 0.0)
            exp = float(sold_item.get("expenses") or 0.0)
            pnl_krw = float(sold_item.get("pnl_krw") or sold_item.get("pnl") or 0.0)

            # 메모에서 누락된 매수가, 매도가, 필요경비 파싱 (하위 호환)
            if purch <= 0.0 and memo_str:
                m_p = re.search(r"매수가\s*[₩\$]?([\d,]+)", memo_str)
                if m_p:
                    purch = float(m_p.group(1).replace(",", ""))
            if sell <= 0.0 and memo_str:
                m_s = re.search(r"매도가\s*[₩\$]?([\d,]+)", memo_str)
                if m_s:
                    sell = float(m_s.group(1).replace(",", ""))
            if exp <= 0.0 and memo_str:
                m_e = re.search(r"필요경비\s*[₩\$]?([\d,]+)", memo_str)
                if m_e:
                    exp = float(m_e.group(1).replace(",", ""))

            if sell <= 0.0 and purch > 0.0 and pnl_krw != 0.0:
                sell = purch + pnl_krw + exp

            return_rate = round((pnl_krw / purch * 100), 2) if purch > 0 else 0.0
            clean_name = sold_item.get("real_estate_name") or name.replace("[부동산]", "").strip() or "부동산"

            sold_item["clean_name"] = clean_name
            sold_item["purchase_price"] = round(purch)
            sold_item["sell_price"] = round(sell)
            sold_item["expenses"] = round(exp)
            sold_item["pnl_krw"] = round(pnl_krw)
            sold_item["return_rate"] = return_rate

            sold_list.append(sold_item)
            total_sold_pnl += pnl_krw
            total_sold_purchase += purch
            total_sold_sell += sell

    sold_list.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
    total_sold_rate = round((total_sold_pnl / total_sold_purchase) * 100, 2) if total_sold_purchase > 0 else 0.0

    return {
        "real_estates": enriched_list,
        "sold_real_estates": sold_list,
        "summary": {
            "total_count": len(enriched_list),
            "own_count": sum(1 for r in enriched_list if r.get("property_type") == "own"),
            "rental_count": sum(1 for r in enriched_list if r.get("property_type") == "rental"),
            "lease_count": sum(1 for r in enriched_list if r.get("property_type") == "lease"),
            "total_real_estate_value": round(total_re_asset_val),
            "total_purchase_value": round(total_re_purchase_val),
            "total_unrealized_profit": round(total_unrealized_profit),
            "total_unrealized_return_rate": total_unrealized_rate,
            "total_tenant_deposit_asset": round(total_tenant_deposit),
            "total_landlord_deposit_debt": round(total_landlord_deposit),
            "total_linked_loan_debt": round(total_linked_loan_debt),
            "total_real_estate_debt": round(total_real_estate_debt),
            "net_real_estate_worth": round((total_re_asset_val + total_tenant_deposit) - total_real_estate_debt),
            "sold_count": len(sold_list),
            "total_sold_pnl": round(total_sold_pnl),
            "total_sold_purchase": round(total_sold_purchase),
            "total_sold_sell": round(total_sold_sell),
            "total_sold_rate": total_sold_rate,
        },
    }
