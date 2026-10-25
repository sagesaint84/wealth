"""AccountInfo destinations and empty-account survival, entirely in memory."""
import asyncio
from contextlib import nullcontext
from copy import deepcopy
from unittest.mock import Mock

from app.services import financial_json, portfolio, savings
from tests.regression_support import authenticated_request, import_main_without_loading_real_env


def test_accountinfo_csv_is_create_only_and_bank_store_is_separate(monkeypatch):
    data = deepcopy(portfolio.EMPTY_PORTFOLIO)
    monkeypatch.setattr(financial_json, "financial_user_locks", lambda *a: nullcontext())
    monkeypatch.setattr(portfolio, "read_portfolio", lambda *a, **kw: data)
    monkeypatch.setattr(savings, "read_portfolio", lambda *a, **kw: data)
    writes = Mock()
    monkeypatch.setattr(portfolio, "write_portfolio", writes)
    monkeypatch.setattr(savings, "write_portfolio", writes)
    csv = ("소유자,증권사,계좌명,계좌번호,계좌유형,원화예수금,달러예수금\n"
           "엄마,가상증권,AccountInfo 일반,1111222233,general,0,0\n"
           "아빠,다른가상증권,AccountInfo ISA,2222333344,isa,0,0\n").encode("utf-8-sig")
    first = portfolio.import_account_rows("accountinfo_accounts.csv", csv, username="fixture", allowed_owners={"아빠", "엄마"})
    before = deepcopy(data)
    second = portfolio.import_account_rows("accountinfo_accounts.csv", csv, username="fixture", allowed_owners={"아빠", "엄마"})
    assert first["created"] == 2 and second["duplicates"] == 2 and second["created"] == 0
    assert data == before and data["holdings"] == []
    assert len({a["id"] for a in data["accounts"]}) == 2
    bank = savings.save_bank_account({"bank_name": "합성은행", "account_name": "AccountInfo 입출금",
                                     "account_number": "3333444455", "owner": "엄마", "balance": 0}, username="fixture")
    assert data["accounts"] == before["accounts"]
    assert data["bank_accounts"] == [bank] and bank["id"] not in {a["id"] for a in data["accounts"]}
    read_only = Mock(side_effect=AssertionError("Savings query must not persist"))
    monkeypatch.setattr(savings, "write_portfolio", read_only)
    visible = savings.get_savings_data(username="fixture")
    assert [a["id"] for a in visible["bank_accounts"]] == [bank["id"]]
    assert read_only.call_count == 0


def test_delete_holding_keeps_all_registered_account_ids_and_metadata(monkeypatch):
    main = import_main_without_loading_real_env()
    data = deepcopy(portfolio.EMPTY_PORTFOLIO)
    data["accounts"] = [{"id": "pdf-empty", "name": "AccountInfo 빈계좌", "owner": "엄마", "account_type": "general"},
                        {"id": "last-position", "name": "증권계좌", "owner": "아빠", "account_type": "isa"}]
    data["bank_accounts"] = [{"id": "bank-empty", "owner": "엄마", "balance": 0}]
    data["holdings"] = [{"id": "remove-only-this", "account_id": "last-position", "code": "005930"}]
    data["settings"]["cash_balances"] = {"pdf-empty": {"KRW": 0}, "last-position": {"KRW": 123}}
    before = deepcopy(data)
    persisted = []
    monkeypatch.setattr(main, "financial_user_locks", lambda *a: nullcontext())
    monkeypatch.setattr(main, "read_portfolio", lambda **kw: data)
    monkeypatch.setattr(main, "write_portfolio", lambda snapshot, **kw: persisted.append(deepcopy(snapshot)))
    asyncio.run(main.delete_holding("remove-only-this", authenticated_request()))
    expected = {**before, "holdings": []}
    assert data == expected and persisted == [expected]


def test_dashboard_projection_includes_zero_holding_registered_accounts(tmp_path, monkeypatch):
    data = deepcopy(portfolio.EMPTY_PORTFOLIO)
    data["accounts"] = [{"id": "pdf-empty", "broker": "합성증권", "name": "AccountInfo 빈계좌",
                         "owner": "엄마", "family_group": "엄마", "account_type": "general"}]
    monkeypatch.setattr(portfolio, "_get_user_dir", lambda *a, **kw: tmp_path)
    writes = Mock(side_effect=AssertionError("Dashboard projection must not persist"))
    monkeypatch.setattr(portfolio, "write_portfolio", writes)
    response = portfolio.get_dashboard(data=data, username="fixture")
    assert [a["id"] for a in response["accounts"]] == ["pdf-empty"]
    assert response["accounts"][0]["holding_count"] == 0
    assert response["accounts"][0]["owner"] == "엄마"
    assert response["summary"]["account_count"] == 1
    assert writes.call_count == 0 and list(tmp_path.iterdir()) == []


def test_account_api_filters_are_views_and_do_not_delete_empty_accounts(monkeypatch):
    main = import_main_without_loading_real_env()
    accounts = [{"id": "pdf-mother", "owner": "엄마", "family_group": "엄마", "holding_count": 0},
                {"id": "pdf-father", "owner": "아빠", "family_group": "아빠", "holding_count": 0}]
    full = {"accounts": accounts, "holdings": [], "fx_rates": {"KRW": 1}}
    before = deepcopy(full)
    writes = Mock(side_effect=AssertionError("Account view must not persist"))
    monkeypatch.setattr(main, "get_dashboard", lambda **kw: full)
    monkeypatch.setattr(main, "write_portfolio", writes)
    for owner, group, expected in [("모두", "All", ["pdf-mother", "pdf-father"]),
                                   ("엄마", "All", ["pdf-mother"]), ("아빠", "All", ["pdf-father"]),
                                   ("모두", "엄마", ["pdf-mother"]), ("엄마", "아빠", [])]:
        response = asyncio.run(main.get_accounts(authenticated_request(), group=group, owner=owner))
        assert [a["id"] for a in response["accounts"]] == expected
        assert response["summary"]["account_count"] == len(expected)
    assert full == before and writes.call_count == 0
