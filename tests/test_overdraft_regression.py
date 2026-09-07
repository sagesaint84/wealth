from __future__ import annotations

import asyncio
import json
import unittest
from copy import deepcopy
from datetime import date as real_date
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from app.services import ledger, portfolio, savings
from regression_support import IsolatedDataTestCase, empty_portfolio, import_main_without_loading_real_env


class FixedDate(real_date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 15)


class OverdraftRegressionTests(IsolatedDataTestCase):
    username = "fixture_user"

    def setUp(self) -> None:
        super().setUp()
        ledger.write_ledger(ledger.default_ledger_data(), username=self.username)

    def configure_pair(
        self,
        *,
        bank_balance: float = 1_000_000,
        loan_balance: float = 0,
        limit_amount: float = 10_000_000,
        bank_currency: str = "KRW",
        bank_owner: str = "아빠",
        loan_owner: str = "아빠",
    ) -> None:
        portfolio.write_portfolio(
            empty_portfolio(
                bank_accounts=[
                    {
                        "id": "bank",
                        "bank_name": "가상은행",
                        "account_name": "가상 입출금계좌",
                        "balance": bank_balance,
                        "currency": bank_currency,
                        "owner": bank_owner,
                    }
                ],
                loan_accounts=[
                    {
                        "id": "loan",
                        "loan_type": "minus",
                        "bank_name": "가상은행",
                        "product_name": "가상 한도대출",
                        "current_balance": loan_balance,
                        "limit_amount": limit_amount,
                        "owner": loan_owner,
                        "linked_account_id": "interest-bank",
                        "overdraft_bank_account_id": "bank",
                    }
                ],
            ),
            username=self.username,
        )

    def pair_balances(self) -> tuple[float, float]:
        data = portfolio.read_portfolio(self.username)
        return (
            float(data["bank_accounts"][0]["balance"]),
            float(data["loan_accounts"][0]["current_balance"]),
        )

    def test_v2_edit_does_not_opt_into_overdraft(self):
        self.configure_pair(bank_balance=100)
        data = ledger.read_ledger(self.username)
        data["transactions"].append({"id": "old-v2", "account_id": "bank", "amount": 50,
                                     "type": "expense", "applied_delta": -50,
                                     "balance_delta_version": 2})
        ledger.write_ledger(data, self.username)
        tx = ledger.update_transaction("old-v2", {"amount": 200}, self.username)
        self.assertEqual(tx["balance_delta_version"], 2)
        self.assertNotIn("balance_effect", tx)
        self.assertEqual(self.pair_balances(), (0, 0))
        ledger.delete_transaction("old-v2", self.username)
        self.assertEqual(self.pair_balances(), (150, 0))

    def test_income_edit_validates_final_net_not_intermediate_reversal(self):
        self.configure_pair(bank_balance=0, limit_amount=100)
        income = self.add("income", 100)
        self.add("expense", 200)
        changed = ledger.update_transaction(income["id"], {"amount": 110}, self.username)
        self.assertEqual(changed["balance_effect"]["net_delta"], 110)
        self.assertEqual(self.pair_balances(), (0, 90))

    def test_failed_recurring_create_and_edit_leave_definition_unchanged(self):
        self.configure_pair(bank_balance=0, limit_amount=100)
        before = ledger.read_ledger(self.username)
        payload = {"name": "가상 정기지출", "amount": 101, "day_of_month": 1,
                   "linked_account_id": "bank", "auto_deduct": True}
        with patch.object(ledger, "date", FixedDate):
            with self.assertRaises(ledger.BalanceConflictError):
                ledger.add_recurring(payload, self.username)
            self.assertEqual(ledger.read_ledger(self.username), before)
            rec = ledger.add_recurring({**payload, "active": False}, self.username)
            before = ledger.read_ledger(self.username)
            with self.assertRaises(ledger.BalanceConflictError):
                ledger.edit_recurring(rec["id"], {"active": True}, self.username)
            self.assertEqual(ledger.read_ledger(self.username), before)
        self.assertEqual(self.pair_balances(), (0, 0))

    def add(self, tx_type: str, amount: float):
        return ledger.add_transaction(
            {
                "type": tx_type,
                "amount": amount,
                "account_id": "bank",
                "account_name": "가상 입출금계좌",
                "owner": "아빠",
                "apply_to_account": True,
            },
            username=self.username,
        )

    def assert_v3_effect(
        self,
        transaction: dict,
        *,
        net_delta: float,
        bank_delta: float,
        loan_delta: float,
    ) -> None:
        self.assertEqual(
            transaction["balance_delta_version"],
            ledger.OVERDRAFT_BALANCE_DELTA_VERSION,
        )
        self.assertEqual(transaction["applied_delta"], net_delta)
        self.assertEqual(
            transaction["balance_effect"],
            {
                "bank_account_id": "bank",
                "overdraft_loan_id": "loan",
                "net_delta": net_delta,
                "bank_delta": bank_delta,
                "loan_delta": loan_delta,
            },
        )

    def test_expense_uses_bank_then_overdraft_and_records_v3(self) -> None:
        self.configure_pair()
        transaction = self.add("expense", 1_500_000)
        self.assertEqual(self.pair_balances(), (0, 500_000))
        self.assert_v3_effect(
            transaction,
            net_delta=-1_500_000,
            bank_delta=-1_000_000,
            loan_delta=500_000,
        )

    def test_income_repays_overdraft_before_increasing_bank_balance(self) -> None:
        self.configure_pair(bank_balance=0, loan_balance=500_000)
        transaction = self.add("income", 700_000)
        self.assertEqual(self.pair_balances(), (200_000, 0))
        self.assert_v3_effect(
            transaction,
            net_delta=700_000,
            bank_delta=200_000,
            loan_delta=-500_000,
        )

    def test_expense_from_partially_used_overdraft_and_exact_limit(self) -> None:
        self.configure_pair(bank_balance=0, loan_balance=300_000)
        self.add("expense", 200_000)
        self.assertEqual(self.pair_balances(), (0, 500_000))

        self.configure_pair(bank_balance=100, loan_balance=900, limit_amount=1_000)
        self.add("expense", 200)
        self.assertEqual(self.pair_balances(), (0, 1_000))

    def test_one_unit_over_limit_is_409_and_changes_nothing(self) -> None:
        self.configure_pair(bank_balance=100, loan_balance=900, limit_amount=1_000)
        before_portfolio = deepcopy(portfolio.read_portfolio(self.username))
        before_ledger = deepcopy(ledger.read_ledger(self.username))

        main = import_main_without_loading_real_env()
        body = json.dumps(
            {
                "type": "expense",
                "amount": 201,
                "account_id": "bank",
                "apply_to_account": True,
            }
        ).encode("utf-8")
        sent = False

        async def receive():
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/ledger/transactions",
                "raw_path": b"/api/ledger/transactions",
                "query_string": b"",
                "headers": [(b"content-type", b"application/json")],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
            },
            receive,
        )
        request.state.username = self.username
        request.state.role = "user"

        with self.assertRaises(HTTPException) as raised:
            asyncio.run(main.create_ledger_transaction(request))
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(portfolio.read_portfolio(self.username), before_portfolio)
        self.assertEqual(ledger.read_ledger(self.username), before_ledger)

    def test_bank_without_overdraft_keeps_zero_floor_and_v2(self) -> None:
        portfolio.write_portfolio(
            empty_portfolio(bank_accounts=[{"id": "bank", "balance": 100}]),
            username=self.username,
        )
        transaction = self.add("expense", 150)
        self.assertEqual(
            portfolio.read_portfolio(self.username)["bank_accounts"][0]["balance"],
            0,
        )
        self.assertEqual(transaction["applied_delta"], -100)
        self.assertEqual(transaction["balance_delta_version"], ledger.BALANCE_DELTA_VERSION)
        self.assertNotIn("balance_effect", transaction)

    def test_card_settlement_uses_overdraft_but_card_purchase_does_not(self) -> None:
        self.configure_pair(bank_balance=100, loan_balance=0, limit_amount=1_000)
        ledger_data = ledger.default_ledger_data()
        ledger_data["cards"] = [
            {
                "id": "card",
                "card_name": "가상카드",
                "owner": "아빠",
                "linked_account_id": "bank",
                "linked_account_name": "가상 입출금계좌",
            }
        ]
        ledger.write_ledger(ledger_data, username=self.username)
        purchase = ledger.add_transaction(
            {"type": "expense", "amount": 300, "card_id": "card", "owner": "아빠"},
            username=self.username,
        )
        self.assertEqual(self.pair_balances(), (100, 0))
        self.assertEqual(purchase["balance_delta_version"], ledger.BALANCE_DELTA_VERSION)

        settlement = ledger.settle_card_payment("card", {}, username=self.username)["transaction"]
        self.assertEqual(self.pair_balances(), (0, 200))
        self.assert_v3_effect(
            settlement,
            net_delta=-300,
            bank_delta=-100,
            loan_delta=200,
        )

    def test_card_settlement_over_limit_does_not_mark_purchases_settled(self) -> None:
        self.configure_pair(bank_balance=100, loan_balance=900, limit_amount=1_000)
        ledger_data = ledger.default_ledger_data()
        ledger_data["cards"] = [
            {
                "id": "card",
                "card_name": "가상카드",
                "owner": "아빠",
                "linked_account_id": "bank",
                "linked_account_name": "가상 입출금계좌",
            }
        ]
        ledger.write_ledger(ledger_data, username=self.username)
        purchase = ledger.add_transaction(
            {"type": "expense", "amount": 201, "card_id": "card", "owner": "아빠"},
            username=self.username,
        )
        with self.assertRaises(ledger.BalanceConflictError):
            ledger.settle_card_payment("card", {}, username=self.username)

        self.assertEqual(self.pair_balances(), (100, 900))
        stored = ledger.read_ledger(self.username)["transactions"]
        self.assertEqual([item["id"] for item in stored], [purchase["id"]])
        self.assertFalse(stored[0]["is_settled"])

    def test_recurring_deduction_uses_overdraft(self) -> None:
        self.configure_pair(bank_balance=50, loan_balance=0, limit_amount=1_000)
        ledger_data = ledger.default_ledger_data()
        ledger_data["recurring"] = [
            {
                "id": "recurring",
                "name": "가상 고정지출",
                "type": "expense",
                "amount": 200,
                "day_of_month": 5,
                "owner": "아빠",
                "linked_account_id": "bank",
                "linked_account_name": "가상 입출금계좌",
                "auto_deduct": True,
                "active": True,
                "last_deducted_date": "",
            }
        ]
        ledger.write_ledger(ledger_data, username=self.username)
        with patch.object(ledger, "date", FixedDate):
            processed = ledger.process_recurring_deductions(username=self.username)

        self.assertEqual(len(processed), 1)
        self.assertEqual(self.pair_balances(), (0, 150))
        transaction = ledger.read_ledger(self.username)["transactions"][0]
        self.assertEqual(
            transaction["balance_delta_version"],
            ledger.OVERDRAFT_BALANCE_DELTA_VERSION,
        )

    def test_recurring_deduction_over_limit_leaves_all_state_unchanged(self) -> None:
        self.configure_pair(bank_balance=100, loan_balance=900, limit_amount=1_000)
        ledger_data = ledger.default_ledger_data()
        ledger_data["recurring"] = [
            {
                "id": "recurring",
                "name": "가상 고정지출",
                "type": "expense",
                "amount": 201,
                "day_of_month": 5,
                "owner": "아빠",
                "linked_account_id": "bank",
                "auto_deduct": True,
                "active": True,
                "last_deducted_date": "",
            }
        ]
        ledger.write_ledger(ledger_data, username=self.username)
        before_portfolio = deepcopy(portfolio.read_portfolio(self.username))
        before_ledger = deepcopy(ledger.read_ledger(self.username))
        with patch.object(ledger, "date", FixedDate):
            with self.assertRaises(ledger.BalanceConflictError):
                ledger.process_recurring_deductions(username=self.username)
        self.assertEqual(portfolio.read_portfolio(self.username), before_portfolio)
        self.assertEqual(ledger.read_ledger(self.username), before_ledger)

    def test_v3_delete_restores_pair_from_current_net_position(self) -> None:
        self.configure_pair()
        transaction = self.add("expense", 1_500_000)
        self.assertTrue(ledger.delete_transaction(transaction["id"], username=self.username))
        self.assertEqual(self.pair_balances(), (1_000_000, 0))

    def test_v3_update_removes_old_net_delta_then_applies_new_delta(self) -> None:
        self.configure_pair()
        transaction = self.add("expense", 1_500_000)
        updated = ledger.update_transaction(
            transaction["id"],
            {"amount": 1_200_000, "apply_to_account": True},
            username=self.username,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(self.pair_balances(), (0, 200_000))
        self.assertEqual(updated["balance_effect"]["net_delta"], -1_200_000)

        self.assertTrue(ledger.delete_transaction(transaction["id"], username=self.username))
        self.assertEqual(self.pair_balances(), (1_000_000, 0))

    def test_v3_update_over_limit_preserves_original_transaction_and_pair(self) -> None:
        self.configure_pair(bank_balance=100, loan_balance=0, limit_amount=1_000)
        transaction = self.add("expense", 200)
        before_portfolio = deepcopy(portfolio.read_portfolio(self.username))
        before_ledger = deepcopy(ledger.read_ledger(self.username))
        with self.assertRaises(ledger.BalanceConflictError):
            ledger.update_transaction(
                transaction["id"],
                {"amount": 1_201, "apply_to_account": True},
                username=self.username,
            )
        self.assertEqual(portfolio.read_portfolio(self.username), before_portfolio)
        self.assertEqual(ledger.read_ledger(self.username), before_ledger)

    def test_deleting_older_v3_transaction_uses_current_pair_net_position(self) -> None:
        self.configure_pair()
        first = self.add("expense", 1_500_000)
        self.add("income", 700_000)
        self.assertEqual(self.pair_balances(), (200_000, 0))

        # Audit component deltas are deliberately made wrong: net_delta must remain
        # the sole reversal source of truth.
        ledger_data = ledger.read_ledger(self.username)
        stored_first = next(item for item in ledger_data["transactions"] if item["id"] == first["id"])
        stored_first["balance_effect"]["bank_delta"] = -9_999_999
        stored_first["balance_effect"]["loan_delta"] = 9_999_999
        ledger.write_ledger(ledger_data, username=self.username)

        self.assertTrue(ledger.delete_transaction(first["id"], username=self.username))
        self.assertEqual(self.pair_balances(), (1_700_000, 0))

    def test_invalid_overdraft_relations_are_rejected(self) -> None:
        cases = (
            {"bank_currency": "USD", "bank_owner": "아빠", "loan_owner": "아빠", "bank_balance": 0},
            {"bank_currency": "KRW", "bank_owner": "엄마", "loan_owner": "아빠", "bank_balance": 0},
            {"bank_currency": "KRW", "bank_owner": "아빠", "loan_owner": "아빠", "bank_balance": -1},
        )
        for index, case in enumerate(cases):
            with self.subTest(case=index):
                portfolio.write_portfolio(
                    empty_portfolio(
                        bank_accounts=[
                            {
                                "id": "bank",
                                "balance": case["bank_balance"],
                                "currency": case["bank_currency"],
                                "owner": case["bank_owner"],
                            }
                        ]
                    ),
                    username=self.username,
                )
                with self.assertRaises(savings.OverdraftValidationError):
                    savings.save_loan_account(
                        {
                            "id": f"loan-{index}",
                            "loan_type": "minus",
                            "owner": case["loan_owner"],
                            "current_balance": 0,
                            "limit_amount": 1_000,
                            "overdraft_bank_account_id": "bank",
                        },
                        username=self.username,
                    )

    def test_overdraft_requires_minus_type_existing_bank_and_valid_limit(self) -> None:
        portfolio.write_portfolio(
            empty_portfolio(
                bank_accounts=[
                    {"id": "bank", "balance": 0, "currency": "KRW", "owner": "아빠"}
                ]
            ),
            username=self.username,
        )
        invalid_payloads = (
            {
                "loan_type": "credit",
                "owner": "아빠",
                "current_balance": 0,
                "limit_amount": 1_000,
                "overdraft_bank_account_id": "bank",
            },
            {
                "loan_type": "minus",
                "owner": "아빠",
                "current_balance": 0,
                "limit_amount": 1_000,
                "overdraft_bank_account_id": "missing-bank",
            },
            {
                "loan_type": "minus",
                "owner": "아빠",
                "current_balance": 1_001,
                "limit_amount": 1_000,
                "overdraft_bank_account_id": "bank",
            },
            {
                "loan_type": "minus",
                "owner": "아빠",
                "current_balance": -1,
                "limit_amount": 1_000,
                "overdraft_bank_account_id": "bank",
            },
        )
        for index, payload in enumerate(invalid_payloads):
            with self.subTest(case=index), self.assertRaises(savings.OverdraftValidationError):
                savings.save_loan_account(
                    {"id": f"invalid-{index}", **payload},
                    username=self.username,
                )

    def test_duplicate_overdraft_relation_is_rejected(self) -> None:
        self.configure_pair(bank_balance=0, loan_balance=0, limit_amount=1_000)
        with self.assertRaises(savings.OverdraftValidationError):
            savings.save_loan_account(
                {
                    "id": "loan-2",
                    "loan_type": "minus",
                    "owner": "아빠",
                    "current_balance": 0,
                    "limit_amount": 1_000,
                    "overdraft_bank_account_id": "bank",
                },
                username=self.username,
            )

    def test_v3_relation_change_is_blocked_on_transaction_delete(self) -> None:
        self.configure_pair()
        transaction = self.add("expense", 1_500_000)
        changed = portfolio.read_portfolio(self.username)
        changed["loan_accounts"][0].pop("overdraft_bank_account_id")
        portfolio.write_portfolio(changed, username=self.username)
        before = deepcopy(portfolio.read_portfolio(self.username))

        with self.assertRaises(ledger.BalanceConflictError):
            ledger.delete_transaction(transaction["id"], username=self.username)
        self.assertEqual(portfolio.read_portfolio(self.username), before)
        self.assertEqual(len(ledger.read_ledger(self.username)["transactions"]), 1)

    def test_referenced_bank_and_loan_deletion_are_blocked(self) -> None:
        self.configure_pair()
        transaction = self.add("expense", 100)
        self.assertEqual(
            transaction["balance_delta_version"],
            ledger.OVERDRAFT_BALANCE_DELTA_VERSION,
        )
        with self.assertRaises(savings.OverdraftValidationError):
            savings.delete_bank_account("bank", username=self.username)
        with self.assertRaises(savings.OverdraftValidationError):
            savings.delete_loan_account("loan", username=self.username)

    def test_portfolio_save_failure_does_not_create_ledger_transaction(self) -> None:
        self.configure_pair(bank_balance=100, loan_balance=0, limit_amount=1_000)
        before_portfolio = deepcopy(portfolio.read_portfolio(self.username))
        before_ledger = deepcopy(ledger.read_ledger(self.username))
        with patch.object(portfolio, "write_portfolio", side_effect=OSError("fixture portfolio failure")):
            with self.assertRaises(OSError):
                self.add("expense", 200)
        self.assertEqual(portfolio.read_portfolio(self.username), before_portfolio)
        self.assertEqual(ledger.read_ledger(self.username), before_ledger)

    def test_ledger_save_failure_rolls_back_portfolio_change(self) -> None:
        self.configure_pair(bank_balance=100, loan_balance=0, limit_amount=1_000)
        before_portfolio = deepcopy(portfolio.read_portfolio(self.username))
        before_ledger = deepcopy(ledger.read_ledger(self.username))
        with patch.object(ledger, "write_ledger", side_effect=OSError("fixture ledger failure")):
            with self.assertRaises(OSError):
                self.add("expense", 200)
        self.assertEqual(self.pair_balances(), (100, 0))
        self.assertEqual(ledger.read_ledger(self.username), before_ledger)
        restored = portfolio.read_portfolio(self.username)
        self.assertEqual(restored["bank_accounts"], before_portfolio["bank_accounts"])
        self.assertEqual(restored["loan_accounts"], before_portfolio["loan_accounts"])

    def test_ui_exposes_separate_interest_and_overdraft_account_fields(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        html = (project_root / "app" / "static" / "index.html").read_text(encoding="utf-8")
        javascript = (project_root / "app" / "static" / "wealth.js").read_text(encoding="utf-8")
        self.assertIn("이자 출금 통장 (연동)", html)
        self.assertIn("마이너스통장 연결 계좌 (자동 상계)", html)
        self.assertIn('name="overdraft_bank_account_id"', html)
        self.assertIn('overdraft_bank_account_id: fd.get("overdraft_bank_account_id")', javascript)
        self.assertIn('label.style.display = loanType === "minus" ? "" : "none"', javascript)


if __name__ == "__main__":
    unittest.main()
