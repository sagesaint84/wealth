"""Optional planning metadata; never changes financial balances or holdings."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
import json
import math
import re
from app.services import portfolio


class PlanningConflict(ValueError):
    pass


def empty():
    return {"revision": 0, "history": [], "buckets": [], "accounts": {}, "holdings": {}}


def read_planning(username):
    return deepcopy(portfolio.read_portfolio(username).get("settings", {}).get("wealth_planning", empty()))


def finite(value, minimum=None):
    if isinstance(value, bool):
        raise ValueError("금액과 비중은 숫자로 입력하세요.")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError("금액과 비중이 유효하지 않습니다.")
    return result


def history_date(value):
    if not isinstance(value, str):
        raise ValueError("날짜를 YYYY-MM-DD 형식으로 입력하세요.")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value or parsed > datetime.now(timezone(timedelta(hours=9))).date():
        raise ValueError("오늘 또는 과거 날짜만 기록할 수 있습니다.")
    return value


def history_memo(value):
    if not isinstance(value, str) or len(value) > 1000:
        raise ValueError("메모는 1,000자 이내로 입력하세요.")
    return value



def _number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _first_number(item, keys):
    for key in keys:
        value = _number(item.get(key))
        if value:
            return value
    return 0.0


def _owner_items(items, owner):
    rows = list(items or [])
    if owner == "모두":
        return rows
    return [row for row in rows if (row.get("owner") or "모두") == owner]


def _real_estate_share(item, owner):
    if owner == "모두":
        return 1.0
    ownerships = item.get("ownerships") or [
        {"owner": item.get("owner") or "모두", "ratio": 100}
    ]
    matched = next((row for row in ownerships if row.get("owner") == owner), None)
    owner_text = str(item.get("owner") or "")
    if matched is None and owner and owner in owner_text:
        match = re.search(re.escape(owner) + r"\s*([0-9.]+)%", owner_text)
        if match:
            return _number(match.group(1)) / 100.0
        return 0.5
    if matched is not None and _number(matched.get("ratio")) > 0:
        return (_number(matched.get("ratio")) or 100.0) / 100.0
    return 0.0


def build_net_worth_snapshot(data, owner="모두"):
    """Build the current net-worth snapshot using the same asset/debt semantics as the home summary."""
    fx_rates = data.get("fx_rates") or {"KRW": 1.0, "USD": 1385.0}
    usd_krw = _number(fx_rates.get("USD")) or 1385.0

    accounts = _owner_items(data.get("accounts"), owner)
    account_ids = {str(item.get("id")) for item in accounts if item.get("id")}
    all_holdings = list(data.get("holdings") or [])
    if owner == "모두":
        holdings = all_holdings
    else:
        holdings = [
            item for item in all_holdings
            if str(item.get("account_id") or "") in account_ids or item.get("owner") == owner
        ]

    stock_value = 0.0
    for item in holdings:
        market_value = item.get("market_value_krw")
        if market_value is None:
            currency = str(item.get("currency") or "KRW").upper()
            rate = _number(item.get("fx_rate")) or (_number(fx_rates.get(currency)) or (1.0 if currency == "KRW" else usd_krw))
            market_value = _number(item.get("quantity")) * _number(item.get("current_price")) * rate
        stock_value += _number(market_value)

    stock_cash = sum(
        _number(item.get("cash_krw")) + (_number(item.get("cash_usd")) * usd_krw)
        for item in accounts
    )

    banks = _owner_items(data.get("bank_accounts"), owner)
    savings = _owner_items(data.get("savings_accounts"), owner)
    insurances = _owner_items(data.get("insurance_accounts"), owner)
    loans = _owner_items(data.get("loan_accounts"), owner)

    positive_bank = sum(max(0.0, _number(item.get("balance"))) for item in banks)
    savings_total = sum(
        _first_number(item, ("current_value", "current_paid_amount", "balance"))
        for item in savings
    )
    insurance_total = sum(
        _first_number(
            item,
            ("expected_amount", "converted_total_asset", "total_paid_amount", "expected_refund_amount", "accumulated_paid_amount"),
        )
        for item in insurances
    )

    total_pure_debt = sum(_number(item.get("current_balance")) for item in loans)
    represented_overdraft_banks = {
        (str(item.get("owner") or "모두"), str(item.get("overdraft_bank_account_id") or "").strip())
        for item in loans
        if (
            str(item.get("loan_type") or "") == "minus"
            and str(item.get("overdraft_bank_account_id") or "").strip()
            and _number(item.get("current_balance")) > 0
        )
    }
    total_minus_bank_debt = 0.0
    for bank in banks:
        balance = _number(bank.get("balance"))
        if balance >= 0:
            continue
        key = (str(bank.get("owner") or "모두"), str(bank.get("id") or "").strip())
        if key not in represented_overdraft_banks:
            total_minus_bank_debt += abs(balance)

    real_estate_value = 0.0
    tenant_deposit = 0.0
    landlord_deposit_debt = 0.0
    for item in data.get("real_estates") or []:
        share = _real_estate_share(item, owner)
        if share <= 0:
            continue
        property_type = item.get("property_type") or "own"
        if property_type == "lease":
            tenant_deposit += _number(item.get("deposit_amount")) * share
        else:
            real_estate_value += _number(item.get("current_price")) * share
            if property_type == "rental":
                landlord_deposit_debt += _number(item.get("deposit_amount")) * share

    assets = stock_value + stock_cash + positive_bank + savings_total + insurance_total + real_estate_value + tenant_deposit
    debt = total_pure_debt + total_minus_bank_debt + landlord_deposit_debt
    net_worth = assets - debt
    return {
        "owner": owner,
        "assets": assets,
        "debt": debt,
        "net_worth": net_worth,
        "fx_rates": fx_rates,
        "valuation_at": str(data.get("updated_at") or "")[:100],
    }


def upsert_current_snapshots(username, snapshots, source="auto"):
    """Atomically upsert today's current net-worth snapshots for multiple owners."""
    if source not in {"auto", "scheduled", "user_confirmed"}:
        raise ValueError("기록 출처를 확인하세요.")
    rows = list(snapshots or [])
    if not rows:
        return read_planning(username)

    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        pf = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(portfolio.EMPTY_PORTFOLIO)
        state = deepcopy(pf.get("settings", {}).get("wealth_planning", empty()))
        now = datetime.now(timezone(timedelta(hours=9)))
        today = now.date().isoformat()
        replacements = {}

        for raw in rows:
            owner = str(raw.get("owner") or "").strip()
            if not owner or len(owner) > 100:
                raise ValueError("조회 범위를 확인하세요.")
            assets = finite(raw.get("assets"), 0)
            debt = finite(raw.get("debt"), 0)
            net = finite(raw.get("net_worth"))
            if not math.isclose(assets - debt, net, rel_tol=0, abs_tol=0.01):
                raise ValueError("순자산과 자산·부채 합계가 일치하지 않습니다.")
            fx = {str(k): finite(v, 0) for k, v in (raw.get("fx_rates") or {}).items()}
            if any(len(k) != 3 or not k.isascii() or not k.isalpha() or k != k.upper() or v <= 0 for k, v in fx.items()):
                raise ValueError("환율은 대문자 통화 코드와 양수 값으로 기록하세요.")
            replacements[owner] = {
                "date": today,
                "owner": owner,
                "assets": assets,
                "debt": debt,
                "net_worth": net,
                "fx_rates": fx,
                "recorded_at": now.isoformat(),
                "valuation_at": str(raw.get("valuation_at") or "")[:100],
                "source": source,
                "calculation_version": 1,
            }

        owners = set(replacements)
        state["history"] = [
            row for row in state.get("history", [])
            if not (row.get("date") == today and row.get("owner") in owners)
        ] + list(replacements.values())
        state["history"].sort(key=lambda row: (row.get("date", ""), row.get("owner", "")))
        state["revision"] += 1
        pf.setdefault("settings", {})["wealth_planning"] = state
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(pf, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)
        return deepcopy(state)

def mutate(username, operation, payload):
    # Share the portfolio write lock and read within it (no stale planning copy).
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        pf = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(portfolio.EMPTY_PORTFOLIO)
        state = deepcopy(pf.get("settings", {}).get("wealth_planning", empty()))
        if payload.get("revision") != state["revision"]:
            raise PlanningConflict("다른 화면에서 기록이 변경되었습니다. 다시 불러온 뒤 저장하세요.")
        if operation == "snapshot-delete":
            if payload.get("confirm") is not True:
                raise ValueError("기록 삭제를 확인하세요.")
            matches = [r for r in state['history'] if r['date'] == payload.get('date') and r['owner'] == payload.get('owner')]
            if len(matches) != 1:
                raise PlanningConflict("삭제할 기록이 변경되었거나 없습니다. 다시 불러오세요.")
            state['history'].remove(matches[0])
        elif operation in ("snapshot", "snapshot-edit", "snapshot-manual"):
            owner = str(payload.get("owner") or "").strip()
            if not owner or len(owner) > 100:
                raise ValueError("조회 범위를 확인하세요.")
            original = None
            if operation == "snapshot-edit":
                matches = [r for r in state['history'] if r['date'] == payload.get('date') and r['owner'] == owner]
                if len(matches) != 1 or payload.get('confirm') is not True:
                    raise PlanningConflict("수정할 기존 기록과 확인 여부를 확인하세요.")
                original = matches[0]
            manual = operation == 'snapshot-manual' or (original is not None and original.get('source') == 'manual')
            has_breakdown = 'assets' in payload and 'debt' in payload
            # New manual records may include an explicit asset/debt breakdown;
            # legacy net-only records remain supported without inventing values.
            assets, debt = ((finite(payload["assets"], 0), finite(payload["debt"], 0))
                            if has_breakdown else ((None, None) if manual else (finite(payload["assets"], 0), finite(payload["debt"], 0))))
            net = finite(payload["net_worth"])
            if has_breakdown and not math.isclose(assets - debt, net, rel_tol=0, abs_tol=0.01):
                raise ValueError("순자산과 자산·부채 합계가 일치하지 않습니다.")
            fx = {str(k): finite(v, 0) for k, v in payload.get("fx_rates", {}).items()}
            if any(len(k) != 3 or not k.isascii() or not k.isalpha() or k != k.upper() or v <= 0 for k, v in fx.items()):
                raise ValueError("환율은 대문자 통화 코드와 양수 값으로 기록하세요.")
            now = datetime.now(timezone(timedelta(hours=9)))
            record = {"date": now.date().isoformat(), "owner": owner,
                      "assets": assets, "debt": debt, "net_worth": net,
                      "fx_rates": fx, "recorded_at": now.isoformat(),
                      "valuation_at": str(payload.get("valuation_at") or "")[:100],
                      "source": "user_confirmed", "calculation_version": 1}
            if operation == 'snapshot-manual':
                record.update(date=history_date(payload.get('date')), source='manual',
                              memo=history_memo(payload.get('memo', '')), fx_rates={}, valuation_at='')
            if original is not None:
                record = {**original, 'assets': assets, 'debt': debt, 'net_worth': net,
                          'date': history_date(payload.get('new_date', original['date'])),
                          'edited_at': now.isoformat(), 'source': 'manual' if manual else 'user_corrected'}
                if 'memo' in payload:
                    record['memo'] = history_memo(payload['memo'])
            others = [r for r in state['history'] if r is not original]
            if operation != 'snapshot' and any(r['date'] == record['date'] and r['owner'] == owner for r in others):
                raise PlanningConflict("해당 날짜의 기록이 이미 있습니다. 기존 기록을 선택하여 수정하세요.")
            exists = any(r["date"] == record["date"] and r["owner"] == owner for r in state["history"])
            if exists and operation == 'snapshot' and payload.get("replace") is not True:
                raise PlanningConflict("오늘 같은 조회 범위의 기록이 있습니다. 교체 여부를 확인하세요.")
            state["history"] = [r for r in others if not (r["date"] == record["date"] and r["owner"] == owner)] + [record]
            state["history"].sort(key=lambda r: (r["date"], r["owner"]))
        elif operation == "buckets":
            buckets = payload.get("buckets", [])
            if not isinstance(buckets, list) or len(buckets) > 30:
                raise ValueError("버킷은 최대 30개까지 등록할 수 있습니다.")
            clean, ids, names = [], set(), set()
            for item in buckets:
                key, name = str(item.get("id") or ""), str(item.get("name") or "").strip()
                target = finite(item.get("target", 0), 0)
                if not key or len(key) > 100 or key in ids or not name or len(name) > 50 or name in names or target > 100:
                    raise ValueError("버킷 이름·ID·목표 비중을 확인하세요. 중복은 허용하지 않습니다.")
                ids.add(key); names.add(name)
                clean.append({"id": key, "name": name, "purpose": str(item.get("purpose") or "")[:200], "target": target})
            if sum(b["target"] for b in clean) > 100.000001:
                raise ValueError("목표 비중 합계는 100%를 넘을 수 없습니다.")
            for field in ("accounts", "holdings"):
                mapping = payload.get(field, {})
                if not isinstance(mapping, dict):
                    raise ValueError("분류 정보가 유효하지 않습니다.")
                valid = {str(item["id"]) for item in pf.get(field, []) if item.get("id")}
                old = state.get(field, {})
                for key, value in mapping.items():
                    if key not in valid and old.get(key) != value:
                        raise ValueError("분류할 계좌 또는 보유내역이 존재하지 않습니다.")
                    if value and value not in ids:
                        raise ValueError("존재하지 않는 버킷입니다.")
                state[field] = dict(mapping)
            state["buckets"] = clean
        else:
            raise ValueError("지원하지 않는 작업입니다.")
        state["revision"] += 1
        pf.setdefault("settings", {})["wealth_planning"] = state
        # Classification and user-confirmed history are not quote refreshes.
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(pf, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        temp.replace(path)
        return deepcopy(state)
