"""Synthetic account identities only; never open a user's portfolio."""
import asyncio
from contextlib import nullcontext
from copy import deepcopy
from unittest.mock import Mock

import pytest

from app.services.holding_accounts import resolve_holding_account, supports_holdings
from tests.regression_support import authenticated_request, import_main_without_loading_real_env


def accounts():
    return [{"id": str(i), "broker": "가상증권", "name": "같은 이름", "owner": owner, "account_type": kind}
            for i, (owner, kind) in enumerate([
                ("아빠", "general"), ("엄마", "isa"), ("자녀", "pension_savings"),
                ("엄마", "irp"), ("자녀", "pension"), ("아빠", "bank")])]


def payload(account):
    return {"account_id": account["id"], "broker": account["broker"],
            "account_name": account["name"], "owner": account["owner"]}


@pytest.mark.parametrize("index", range(5))
def test_exact_registered_id_across_owners_and_supported_types(index):
    data = {"accounts": accounts()}
    before = deepcopy(data)
    assert resolve_holding_account(data, payload(data["accounts"][index]))["id"] == str(index)
    assert data == before


def test_bank_unknown_id_metadata_mismatch_do_not_change_accounts():
    data = {"accounts": accounts()}
    before = deepcopy(data)
    for raw in [payload(data["accounts"][5]), {**payload(data["accounts"][0]), "account_id": "foreign"},
                {**payload(data["accounts"][1]), "owner": "아빠"}]:
        with pytest.raises(ValueError):
            resolve_holding_account(data, raw)
    assert data == before
    assert not supports_holdings(data["accounts"][5])


def test_same_name_same_owner_is_ambiguous_without_id_but_legacy_edit_keeps_id():
    data = {"accounts": accounts()}
    raw = payload(data["accounts"][1]); raw.pop("account_id")
    with pytest.raises(ValueError, match="ID"):
        resolve_holding_account(data, raw)
    assert resolve_holding_account(data, raw, current={"account_id": "3"})["id"] == "3"


def test_manual_input_creates_only_a_new_general_account():
    data = {"accounts": accounts(), "bank_accounts": [{"id": "protected-bank"}]}
    before = deepcopy(data)
    new = resolve_holding_account(data, {"broker": "직접증권", "account_name": "직접", "owner": "자녀"})
    assert new["id"] not in {a["id"] for a in before["accounts"]}
    assert new["account_type"] == "general"
    assert data["accounts"][:-1] == before["accounts"]
    assert data["bank_accounts"] == before["bank_accounts"]


@pytest.mark.parametrize("edit", [False, True])
def test_save_routes_link_exact_id_without_changing_account_owner(monkeypatch, edit):
    main = import_main_without_loading_real_env()
    data = {"accounts": accounts(), "holdings": [{"id": "existing", "account_id": "0", "code": "005930"}], "settings": {}}
    before_accounts = deepcopy(data["accounts"])
    writes = Mock()
    monkeypatch.setattr(main, "financial_user_locks", lambda *a: nullcontext())
    monkeypatch.setattr(main, "read_portfolio", lambda **kw: data)
    monkeypatch.setattr(main, "write_portfolio", writes)
    monkeypatch.setattr(main, "get_dashboard", lambda **kw: {})
    raw = {**payload(data["accounts"][3]), "code": "005930", "name": "합성 주식", "quantity": 1,
           "avg_price": 100, "current_price": 100, "currency": "KRW"}
    model = main.HoldingCreate(**raw)
    if edit:
        asyncio.run(main.update_holding("existing", model, authenticated_request()))
        saved = next(h for h in data["holdings"] if h["id"] == "existing")
    else:
        asyncio.run(main.create_holding(model, authenticated_request()))
        saved = next(h for h in data["holdings"] if h.get("code") == "005930")
    assert saved["account_id"] == "3"
    assert (saved["broker"], saved["account_name"]) == ("가상증권", "같은 이름")
    assert data["accounts"] == before_accounts
    assert writes.call_count == 1  # Explicit save only, against mocked storage.
