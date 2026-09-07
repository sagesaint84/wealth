from __future__ import annotations

import asyncio
import unittest

from app.services import portfolio
from regression_support import (
    IsolatedDataTestCase,
    authenticated_request,
    empty_portfolio,
    import_main_without_loading_real_env,
)


main = import_main_without_loading_real_env()


def account(account_id: str, name: str, owner: str, account_type: str | None = None) -> dict:
    item = {
        "id": account_id,
        "broker": "가상증권",
        "name": name,
        "owner": owner,
        "family_group": owner,
        "source": "fixture",
    }
    if account_type is not None:
        item["account_type"] = account_type
    return item


def holding(
    holding_id: str,
    account_id: str,
    code: str = "SAFE",
    quantity: float = 1,
    avg_price: float = 80,
    current_price: float = 100,
    currency: str = "KRW",
    owner: str = "모두",
) -> dict:
    return {
        "id": holding_id,
        "account_id": account_id,
        "broker": "가상증권",
        "account_name": account_id,
        "code": code,
        "name": f"가상종목-{code}",
        "quantity": quantity,
        "avg_price": avg_price,
        "current_price": current_price,
        "currency": currency,
        "market": "KRX" if currency == "KRW" else "NAS",
        "source": "fixture",
        "sector": "테스트",
        "owner": owner,
    }


class PortfolioAccountRegressionTests(IsolatedDataTestCase):
    def test_same_symbol_in_multiple_accounts_is_aggregated_without_losing_account_relation(self) -> None:
        data = empty_portfolio(
            accounts=[
                account("acc-general", "일반계좌", "아빠", "general"),
                account("acc-isa", "중개형 ISA", "엄마", "isa"),
            ],
            holdings=[
                holding("holding-a", "acc-general", quantity=2, current_price=100),
                holding("holding-b", "acc-isa", quantity=3, current_price=200),
            ],
        )

        dashboard = portfolio.get_dashboard(data=data, username="fixture_user")
        accounts = {item["id"]: item for item in dashboard["accounts"]}
        holdings = {item["id"]: item for item in dashboard["holdings"]}

        self.assertEqual(dashboard["summary"]["total_stock_value_krw"], 800)
        self.assertEqual(dashboard["summary"]["holding_count"], 2)
        self.assertEqual(accounts["acc-general"]["stock_value_krw"], 200)
        self.assertEqual(accounts["acc-isa"]["stock_value_krw"], 600)
        self.assertEqual(accounts["acc-general"]["holding_count"], 1)
        self.assertEqual(accounts["acc-isa"]["holding_count"], 1)
        self.assertEqual(holdings["holding-a"]["account_id"], "acc-general")
        self.assertEqual(holdings["holding-b"]["account_id"], "acc-isa")

    def test_same_account_and_symbol_upsert_replaces_instead_of_merging(self) -> None:
        original = holding("stable-id", "acc-general", quantity=2)
        replacement = holding("new-id", "acc-general", quantity=5, current_price=120)
        data = empty_portfolio(
            accounts=[account("acc-general", "일반계좌", "아빠", "general")],
            holdings=[original],
        )

        count = portfolio.upsert_holdings(data, [replacement])

        self.assertEqual(count, 1)
        self.assertEqual(len(data["holdings"]), 1)
        self.assertEqual(data["holdings"][0]["id"], "stable-id")
        self.assertEqual(data["holdings"][0]["quantity"], 5)
        self.assertEqual(data["holdings"][0]["current_price"], 120)
        self.assertEqual(data["holdings"][0]["account_id"], "acc-general")

    def test_explicit_account_types_are_preserved(self) -> None:
        expected = {
            "general": "general",
            "isa": "isa",
            "pension": "pension_savings",
            "irp": "irp",
        }
        data = empty_portfolio(
            accounts=[
                account("general", "이름에는 ISA가 있지만 일반계좌", "아빠", "general"),
                account("isa", "중개형 ISA", "아빠", "isa"),
                account("pension", "연금저축", "엄마", "pension_savings"),
                account("irp", "개인형 IRP", "엄마", "irp"),
            ]
        )

        dashboard = portfolio.get_dashboard(data=data, username="fixture_user")
        actual = {item["id"]: item["account_type"] for item in dashboard["accounts"]}

        self.assertEqual(actual, expected)

    def test_legacy_account_name_fallback_for_general_pension_and_irp(self) -> None:
        data = empty_portfolio(
            accounts=[
                account("general", "가상 위탁계좌", "아빠"),
                account("pension", "가상 연금저축", "엄마"),
                account("irp", "가상 개인형퇴직연금 IRP", "엄마"),
            ]
        )

        dashboard = portfolio.get_dashboard(data=data, username="fixture_user")
        actual = {item["id"]: item["account_type"] for item in dashboard["accounts"]}

        self.assertEqual(
            actual,
            {"general": "general", "pension": "pension_savings", "irp": "irp"},
        )

    def test_legacy_isa_name_falls_back_to_isa(self) -> None:
        data = empty_portfolio(accounts=[account("legacy-isa", "가상 중개형 ISA", "아빠")])

        dashboard = portfolio.get_dashboard(data=data, username="fixture_user")

        self.assertEqual(dashboard["accounts"][0]["account_type"], "isa")

    def test_brokerage_cash_is_attributed_to_its_own_account(self) -> None:
        data = empty_portfolio(
            settings={
                "fx_rates": {"KRW": 1.0, "USD": 1300.0},
                "cash_balances": {
                    "acc-a": {"KRW": 1000, "USD": 0},
                    "acc-b": {"KRW": 200, "USD": 2},
                },
            },
            accounts=[
                account("acc-a", "아빠 일반계좌", "아빠", "general"),
                account("acc-b", "엄마 ISA", "엄마", "isa"),
            ],
        )

        dashboard = portfolio.get_dashboard(data=data, username="fixture_user")
        accounts = {item["id"]: item for item in dashboard["accounts"]}

        self.assertEqual(accounts["acc-a"]["cash_total_krw"], 1000)
        self.assertEqual(accounts["acc-b"]["cash_total_krw"], 2800)
        self.assertEqual(accounts["acc-b"]["cash_usd"], 2)
        self.assertEqual(dashboard["summary"]["total_cash_krw"], 3800)

    def test_accounts_api_filters_accounts_for_each_owner_and_all_means_no_filter(self) -> None:
        data = empty_portfolio(
            accounts=[
                account("all", "공용계좌", "모두", "general"),
                account("father", "아빠계좌", "아빠", "general"),
                account("mother", "엄마계좌", "엄마", "isa"),
                account("child", "자녀계좌", "자녀", "general"),
                account("joint", "공동명의계좌", "공동명의", "general"),
            ]
        )
        portfolio.write_portfolio(data, username="fixture_user")
        request = authenticated_request("fixture_user")

        expected = {
            "아빠": ["father"],
            "엄마": ["mother"],
            "자녀": ["child"],
            "공동명의": ["joint"],
        }
        for owner, account_ids in expected.items():
            with self.subTest(owner=owner):
                result = asyncio.run(main.get_accounts(request, owner=owner))
                self.assertEqual([item["id"] for item in result["accounts"]], account_ids)

        all_result = asyncio.run(main.get_accounts(request, owner="모두"))
        self.assertEqual(
            {item["id"] for item in all_result["accounts"]},
            {"all", "father", "mother", "child", "joint"},
        )

    def test_accounts_api_filters_holdings_with_owner_account_scope(self) -> None:
        data = empty_portfolio(
            accounts=[
                account("father", "아빠계좌", "아빠", "general"),
                account("mother", "엄마계좌", "엄마", "general"),
                account("joint", "공동명의계좌", "공동명의", "general"),
            ],
            holdings=[
                holding("father-stock", "father", owner="엄마"),
                holding("mother-stock", "mother", owner="엄마"),
                holding("joint-stock", "joint", owner="공동명의"),
            ],
        )
        portfolio.write_portfolio(data, username="fixture_user")

        result = asyncio.run(
            main.get_accounts(authenticated_request("fixture_user"), owner="아빠")
        )

        self.assertEqual([item["id"] for item in result["holdings"]], ["father-stock"])

        joint_result = asyncio.run(
            main.get_accounts(authenticated_request("fixture_user"), owner="공동명의")
        )
        self.assertEqual([item["id"] for item in joint_result["holdings"]], ["joint-stock"])

        all_result = asyncio.run(
            main.get_accounts(authenticated_request("fixture_user"), owner="모두")
        )
        self.assertEqual(
            {item["id"] for item in all_result["holdings"]},
            {"father-stock", "mother-stock", "joint-stock"},
        )


if __name__ == "__main__":
    unittest.main()
