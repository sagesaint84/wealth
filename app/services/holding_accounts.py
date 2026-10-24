"""Registered securities-account identity for manual holding forms.

Only an explicit holding save calls this helper. Market analysis never does.
Bank/insurance stores are deliberately not holding destinations.
"""
from uuid import uuid4

HOLDING_ACCOUNT_TYPES = frozenset({"general", "isa", "pension_savings", "pension", "irp"})


def supports_holdings(account):
    return (account.get("account_type") or "general") in HOLDING_ACCOUNT_TYPES


def resolve_holding_account(data, payload, current=None):
    """Resolve within the authenticated user's portfolio; never rename an account."""
    accounts = data.setdefault("accounts", [])
    account_id = payload.get("account_id")
    broker = str(payload.get("broker") or "").strip()
    name = str(payload.get("account_name") or "").strip()
    owner = str(payload.get("owner") or "모두").strip()
    if not broker or not name:
        raise ValueError("증권사와 계좌 이름은 필수입니다.")
    if account_id:
        matches = [a for a in accounts if a.get("id") == account_id]
        if len(matches) != 1:
            raise ValueError("등록된 계좌 ID를 확인해 주세요.")
        account = matches[0]
        if not supports_holdings(account):
            raise ValueError("주식 보유를 지원하는 증권계좌를 선택해 주세요.")
        if (broker, name, owner) != (account.get("broker"), account.get("name"), account.get("owner") or "모두"):
            raise ValueError("선택한 계좌 정보가 변경됐습니다. 계좌를 다시 선택해 주세요.")
        return account
    # Legacy edit clients omit account_id. Preserve the existing ID only for
    # the exact unchanged identity; broker/name alone must not redirect an edit.
    if current:
        linked = next((a for a in accounts if a.get("id") == current.get("account_id")), None)
        if linked and supports_holdings(linked) and (broker, name, owner) == (
                linked.get("broker"), linked.get("name"), linked.get("owner") or "모두"):
            return linked
    matches = [a for a in accounts if supports_holdings(a) and (
        a.get("broker"), a.get("name"), a.get("owner") or "모두") == (broker, name, owner)]
    if len(matches) > 1:
        raise ValueError("같은 이름의 계좌가 여러 개입니다. 등록 계좌를 ID로 선택해 주세요.")
    if matches:
        return matches[0]
    account = {"id": str(uuid4()), "broker": broker, "name": name, "owner": owner,
               "family_group": owner if owner != "모두" else "All",
               "account_type": "general", "source": "manual"}
    accounts.append(account)
    return account
