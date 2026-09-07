from __future__ import annotations

import unittest
from datetime import date as real_date
from unittest.mock import patch

from app.services import ledger, pnl_records, portfolio
from regression_support import IsolatedDataTestCase, empty_portfolio


class FixedDate(real_date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 15)


class FinancialRecordsRegressionTests(IsolatedDataTestCase):
    def test_usd_realized_pnl_uses_explicit_exchange_rate_and_fx_pnl(self) -> None:
        with (
            patch.object(
                pnl_records,
                "resolve_stock_info",
                return_value=("SAFE", "가상 해외주식", "USD"),
            ),
            patch.object(pnl_records, "get_historical_fx_rate") as historical_fx,
        ):
            record = pnl_records.create_pnl_record(
                {
                    "date": "2026-09-01",
                    "code": "SAFE",
                    "name": "가상 해외주식",
                    "currency": "USD",
                    "pnl": 10,
                    "fx_rate": 1300,
                    "fx_pnl_krw": 500,
                    "owner": "아빠",
                },
                username="fixture_user",
            )

        self.assertEqual(record["fx_rate"], 1300)
        self.assertEqual(record["pnl_krw"], 13500)
        historical_fx.assert_not_called()

    def test_usd_realized_pnl_uses_mocked_historical_rate_when_rate_is_missing(self) -> None:
        with (
            patch.object(
                pnl_records,
                "resolve_stock_info",
                return_value=("SAFE", "가상 해외주식", "USD"),
            ),
            patch.object(pnl_records, "get_historical_fx_rate", return_value=1250) as historical_fx,
        ):
            record = pnl_records.create_pnl_record(
                {
                    "date": "2026-08-01",
                    "code": "SAFE",
                    "name": "가상 해외주식",
                    "currency": "USD",
                    "pnl": 8,
                    "owner": "엄마",
                },
                username="fixture_user",
            )

        historical_fx.assert_called_once_with("2026-08-01")
        self.assertEqual(record["fx_rate"], 1250)
        self.assertEqual(record["pnl_krw"], 10000)

    def test_transaction_create_update_between_accounts_and_delete_restore_balances(self) -> None:
        data = empty_portfolio(
            bank_accounts=[
                {"id": "bank-a", "name": "가상 A통장", "balance": 1000},
                {"id": "bank-b", "name": "가상 B통장", "balance": 500},
            ]
        )
        portfolio.write_portfolio(data, username="fixture_user")

        transaction = ledger.add_transaction(
            {
                "date": "2026-09-01",
                "type": "expense",
                "amount": 100,
                "account_id": "bank-a",
                "account_name": "가상 A통장",
                "owner": "아빠",
            },
            username="fixture_user",
        )
        after_create = portfolio.read_portfolio("fixture_user")
        self.assertEqual(after_create["bank_accounts"][0]["balance"], 900)
        self.assertEqual(transaction["applied_delta"], -100)

        updated = ledger.update_transaction(
            transaction["id"],
            {
                "amount": 200,
                "account_id": "bank-b",
                "account_name": "가상 B통장",
                "apply_to_account": True,
            },
            username="fixture_user",
        )
        after_update = portfolio.read_portfolio("fixture_user")
        balances = {item["id"]: item["balance"] for item in after_update["bank_accounts"]}
        self.assertIsNotNone(updated)
        self.assertEqual(balances, {"bank-a": 1000, "bank-b": 300})
        self.assertEqual(updated["applied_delta"], -200)

        self.assertTrue(ledger.delete_transaction(transaction["id"], username="fixture_user"))
        after_delete = portfolio.read_portfolio("fixture_user")
        restored = {item["id"]: item["balance"] for item in after_delete["bank_accounts"]}
        self.assertEqual(restored, {"bank-a": 1000, "bank-b": 500})

    def test_credit_card_expense_does_not_change_linked_bank_until_settlement(self) -> None:
        data = empty_portfolio(bank_accounts=[{"id": "bank", "balance": 1000}])
        portfolio.write_portfolio(data, username="fixture_user")

        transaction = ledger.add_transaction(
            {
                "date": "2026-09-01",
                "type": "expense",
                "amount": 300,
                "account_id": "bank",
                "card_id": "card",
                "card_name": "가상카드",
                "owner": "엄마",
            },
            username="fixture_user",
        )

        self.assertEqual(portfolio.read_portfolio("fixture_user")["bank_accounts"][0]["balance"], 1000)
        self.assertEqual(transaction["applied_delta"], 0)
        self.assertFalse(transaction["is_settled"])

    def test_recurring_deduction_runs_once_per_month_and_creates_transaction(self) -> None:
        portfolio.write_portfolio(
            empty_portfolio(bank_accounts=[{"id": "bank", "name": "가상통장", "balance": 1000}]),
            username="fixture_user",
        )
        data = ledger.default_ledger_data()
        data["recurring"] = [
            {
                "id": "recurring",
                "name": "가상 고정지출",
                "type": "expense",
                "amount": 100,
                "day_of_month": 5,
                "category": "주거/통신",
                "owner": "아빠",
                "pay_method": "자동이체",
                "linked_account_id": "bank",
                "linked_account_name": "가상통장",
                "auto_deduct": True,
                "active": True,
                "last_deducted_date": "",
            }
        ]
        ledger.write_ledger(data, username="fixture_user")

        with patch.object(ledger, "date", FixedDate):
            first = ledger.process_recurring_deductions(username="fixture_user")
            second = ledger.process_recurring_deductions(username="fixture_user")

        stored_ledger = ledger.read_ledger(username="fixture_user")
        stored_portfolio = portfolio.read_portfolio(username="fixture_user")
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(stored_portfolio["bank_accounts"][0]["balance"], 900)
        self.assertEqual(len(stored_ledger["transactions"]), 1)
        self.assertEqual(stored_ledger["transactions"][0]["recurring_id"], "recurring")
        self.assertEqual(stored_ledger["recurring"][0]["last_deducted_date"], "2026-09-05")

    def test_overdraft_transaction_update_and_delete_restores_original_balance(self) -> None:
        portfolio.write_portfolio(
            empty_portfolio(bank_accounts=[{"id": "bank", "balance": 100}]),
            username="fixture_user",
        )
        transaction = ledger.add_transaction(
            {
                "type": "expense",
                "amount": 150,
                "account_id": "bank",
                "apply_to_account": True,
            },
            username="fixture_user",
        )
        self.assertEqual(transaction["applied_delta"], -100)
        self.assertEqual(
            portfolio.read_portfolio("fixture_user")["bank_accounts"][0]["balance"],
            0,
        )

        updated = ledger.update_transaction(
            transaction["id"],
            {"amount": 50, "apply_to_account": True},
            username="fixture_user",
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated["applied_delta"], -50)
        self.assertEqual(
            portfolio.read_portfolio("fixture_user")["bank_accounts"][0]["balance"],
            50,
        )

        self.assertTrue(ledger.delete_transaction(transaction["id"], username="fixture_user"))

        restored_balance = portfolio.read_portfolio("fixture_user")["bank_accounts"][0]["balance"]
        self.assertEqual(restored_balance, 100)

    def test_brokerage_transaction_updates_krw_and_preserves_usd_cash(self) -> None:
        portfolio.write_portfolio(
            empty_portfolio(
                settings={
                    "fx_rates": {"KRW": 1.0, "USD": 1300.0},
                    "cash_balances": {"broker": {"KRW": 100, "USD": 2}},
                },
                accounts=[
                    {
                        "id": "broker",
                        "broker": "가상증권",
                        "name": "가상계좌",
                        "owner": "아빠",
                        "account_type": "general",
                    }
                ],
            ),
            username="fixture_user",
        )
        ledger.add_transaction(
            {
                "type": "expense",
                "amount": 20,
                "account_id": "broker",
                "apply_to_account": True,
            },
            username="fixture_user",
        )

        dashboard = portfolio.get_dashboard(username="fixture_user")
        self.assertEqual(dashboard["accounts"][0]["cash_krw"], 80)
        self.assertEqual(dashboard["accounts"][0]["cash_usd"], 2)
        stored_cash = portfolio.read_portfolio("fixture_user")["settings"]["cash_balances"]["broker"]
        self.assertEqual(stored_cash, {"KRW": 80, "USD": 2})

    def test_brokerage_transaction_reads_legacy_lowercase_cash_and_writes_canonical_krw(self) -> None:
        portfolio.write_portfolio(
            empty_portfolio(
                settings={
                    "fx_rates": {"KRW": 1.0, "USD": 1300.0},
                    "cash_balances": {"broker": {"krw": 100, "usd": 2}},
                },
                accounts=[
                    {
                        "id": "broker",
                        "broker": "가상증권",
                        "name": "가상계좌",
                        "owner": "아빠",
                        "account_type": "general",
                    }
                ],
            ),
            username="fixture_user",
        )

        before = portfolio.get_dashboard(username="fixture_user")["accounts"][0]
        self.assertEqual((before["cash_krw"], before["cash_usd"]), (100, 2))

        ledger.add_transaction(
            {
                "type": "expense",
                "amount": 20,
                "account_id": "broker",
                "apply_to_account": True,
            },
            username="fixture_user",
        )

        stored_cash = portfolio.read_portfolio("fixture_user")["settings"]["cash_balances"]["broker"]
        dashboard_cash = portfolio.get_dashboard(username="fixture_user")["accounts"][0]
        self.assertEqual(stored_cash["KRW"], 80)
        self.assertEqual((dashboard_cash["cash_krw"], dashboard_cash["cash_usd"]), (80, 2))

    def test_credit_card_settlement_records_actual_delta_and_delete_restores_balance(self) -> None:
        portfolio.write_portfolio(
            empty_portfolio(bank_accounts=[{"id": "bank", "name": "가상통장", "balance": 1000}]),
            username="fixture_user",
        )
        ledger_data = ledger.default_ledger_data()
        ledger_data["cards"] = [
            {
                "id": "card",
                "card_name": "가상카드",
                "owner": "아빠",
                "linked_account_id": "bank",
                "linked_account_name": "가상통장",
            }
        ]
        ledger.write_ledger(ledger_data, username="fixture_user")
        ledger.add_transaction(
            {"type": "expense", "amount": 300, "card_id": "card", "owner": "아빠"},
            username="fixture_user",
        )

        result = ledger.settle_card_payment("card", {}, username="fixture_user")
        settlement = result["transaction"]
        self.assertEqual(settlement["applied_delta"], -300)
        self.assertEqual(portfolio.read_portfolio("fixture_user")["bank_accounts"][0]["balance"], 700)

        self.assertTrue(ledger.delete_transaction(settlement["id"], username="fixture_user"))
        self.assertEqual(portfolio.read_portfolio("fixture_user")["bank_accounts"][0]["balance"], 1000)


if __name__ == "__main__":
    unittest.main()
