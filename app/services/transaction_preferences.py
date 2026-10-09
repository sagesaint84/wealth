"""User-scoped transaction and import UI preferences; no balance mutations."""
from copy import deepcopy

from app.services.financial_json import financial_rmw, read_financial_json
from app.services.ledger import read_ledger, write_ledger
from app.services.portfolio import _get_portfolio_file, write_portfolio

OWNERS = {"모두", "아빠", "엄마", "자녀"}
METHODS = {"credit_card", "bank_account", "cash"}
FIELDS = {"income_account_id", "expense_payment_method", "expense_card_id",
          "expense_account_id", "transfer_account_id"}
WORKFLOWS = {"toss_wts_realized", "toss_wts_income"}


def owner_matches(item, owner):
    return owner == "모두" or item.get("owner", "모두") in {owner, "모두"}


def validate_owner(owner):
    if not isinstance(owner, str) or owner not in OWNERS:
        raise ValueError("소유자가 올바르지 않습니다.")


def get_transaction_defaults(username=None):
    data = read_ledger(username)
    preferences = data.get("preferences", {})
    if not isinstance(preferences, dict) or not isinstance(preferences.get("transaction_defaults", {}), dict):
        raise ValueError("가계부 기본값 설정이 올바르지 않습니다.")
    return deepcopy(preferences.get("transaction_defaults", {}))


@financial_rmw('ledger.json', 'portfolio.json')
def set_transaction_defaults(owner, defaults, username=None):
    validate_owner(owner)
    if not isinstance(defaults, dict) or set(defaults) - FIELDS:
        raise ValueError("기본값 필드가 올바르지 않습니다.")
    data = read_ledger(username)
    portfolio = read_financial_json(_get_portfolio_file(username), default={})
    accounts = [item for group in ("bank_accounts", "savings_accounts", "accounts")
                for item in portfolio.get(group, [])]
    for field, value in defaults.items():
        if not isinstance(value, str):
            raise ValueError("기본값은 문자열이어야 합니다.")
        if field == "expense_payment_method":
            if value and value not in METHODS:
                raise ValueError("결제수단이 올바르지 않습니다.")
        elif value:
            candidates = data.get("cards", []) if field == "expense_card_id" else accounts
            if not any(item.get("id") == value and owner_matches(item, owner) for item in candidates):
                raise ValueError("현재 사용자의 소유자 범위에 있는 카드/계좌를 선택해 주세요.")
    get_transaction_defaults(username)  # Validate existing preference containers before changing them.
    scopes = data.setdefault("preferences", {}).setdefault("transaction_defaults", {})
    if defaults:
        scopes[owner] = dict(defaults)
    else:
        scopes.pop(owner, None)
    write_ledger(data, username)
    return deepcopy(scopes)


def get_import_defaults(username=None):
    value = read_financial_json(_get_portfolio_file(username), default={}).get("settings", {}).get("import_destination_defaults", {})
    if not isinstance(value, dict):
        raise ValueError("가져오기 기본값 설정이 올바르지 않습니다.")
    return deepcopy(value)


@financial_rmw('portfolio.json')
def set_import_default(workflow, account_id, owner="모두", username=None):
    if not isinstance(workflow, str) or workflow not in WORKFLOWS or not isinstance(account_id, str):
        raise ValueError("가져오기 기본값이 올바르지 않습니다.")
    validate_owner(owner)
    data = read_financial_json(_get_portfolio_file(username), default={})
    if account_id:
        account = next((a for a in data.get("accounts", []) if a.get("id") == account_id), None)
        broker = str((account or {}).get("broker", "")).lower()
        if not account or not owner_matches(account, owner) or not ("toss" in broker or "토스" in broker):
            raise ValueError("소유자 범위에 있는 토스증권 계좌를 선택해 주세요.")
    get_import_defaults(username)
    defaults = data.setdefault("settings", {}).setdefault("import_destination_defaults", {})
    if account_id:
        defaults[workflow] = account_id
    else:
        defaults.pop(workflow, None)
    write_portfolio(data, username)
    return deepcopy(defaults)
