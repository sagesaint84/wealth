"""Optional planning metadata; never changes financial balances or holdings."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
import math
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


def mutate(username, operation, payload):
    # Share the portfolio write lock and read within it (no stale planning copy).
    with portfolio._LOCK:
        path = portfolio._get_portfolio_file(username)
        pf = json.loads(path.read_text(encoding="utf-8")) if path.exists() else deepcopy(portfolio.EMPTY_PORTFOLIO)
        state = deepcopy(pf.get("settings", {}).get("wealth_planning", empty()))
        if payload.get("revision") != state["revision"]:
            raise PlanningConflict("다른 화면에서 기록이 변경되었습니다. 다시 불러온 뒤 저장하세요.")
        if operation == "snapshot":
            owner = str(payload.get("owner") or "").strip()
            if not owner or len(owner) > 100:
                raise ValueError("조회 범위를 확인하세요.")
            assets, debt = finite(payload["assets"], 0), finite(payload["debt"], 0)
            net = finite(payload["net_worth"])
            if not math.isclose(assets - debt, net, rel_tol=0, abs_tol=0.01):
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
            exists = any(r["date"] == record["date"] and r["owner"] == owner for r in state["history"])
            if exists and payload.get("replace") is not True:
                raise PlanningConflict("오늘 같은 조회 범위의 기록이 있습니다. 교체 여부를 확인하세요.")
            state["history"] = [r for r in state["history"] if not (r["date"] == record["date"] and r["owner"] == owner)] + [record]
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
