from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from app.services.tax_benefit import get_total_tax_benefits


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"


class OverdraftNetWorthTests(unittest.TestCase):
    def calculate_debt(self, banks: list[dict], loans: list[dict]) -> dict:
        if not shutil.which("node"):
            self.skipTest("node runtime is not available")
        script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function calculateDashboardDebt');
const end = source.indexOf('\nfunction renderSummary', start);
if (start < 0 || end < 0) throw new Error('debt helper not found');
const sandbox = {};
vm.runInNewContext(source.slice(start, end) + '\nthis.calculate = calculateDashboardDebt;', sandbox);
const input = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(sandbox.calculate(input.banks, input.loans)));
"""
        result = subprocess.run(
            ["node", "-e", script, str(WEALTH_JS), json.dumps({"banks": banks, "loans": loans})],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def assert_debt(self, banks: list[dict], loans: list[dict], expected: float) -> None:
        result = self.calculate_debt(banks, loans)
        self.assertEqual(result["totalPureDebt"] + result["totalMinusBankDebt"], expected)

    def test_positive_bank_is_not_a_liability(self) -> None:
        self.assert_debt([{"id": "bank", "owner": "A", "balance": 100}], [], 0)

    def test_unlinked_negative_bank_is_counted_once(self) -> None:
        self.assert_debt([{"id": "bank", "owner": "A", "balance": -100}], [], 100)

    def test_independent_loan_is_counted_once(self) -> None:
        self.assert_debt([], [{"id": "loan", "owner": "A", "loan_type": "credit", "current_balance": 100}], 100)

    def test_linked_negative_overdraft_is_counted_once(self) -> None:
        banks = [{"id": "bank", "owner": "A", "balance": -100}]
        loans = [{"id": "loan", "owner": "A", "loan_type": "minus", "current_balance": 100,
                  "overdraft_bank_account_id": "bank"}]
        result = self.calculate_debt(banks, loans)
        actual_debt = result["totalPureDebt"] + result["totalMinusBankDebt"]
        self.assertEqual(actual_debt, 100)
        self.assertEqual(500 - actual_debt, 400)

    def test_link_does_not_hide_negative_bank_when_loan_balance_is_zero(self) -> None:
        banks = [{"id": "bank", "owner": "A", "balance": -100}]
        loans = [{"id": "loan", "owner": "A", "loan_type": "minus", "current_balance": 0,
                  "overdraft_bank_account_id": "bank"}]
        self.assert_debt(banks, loans, 100)

    def test_zero_linked_overdraft_has_no_phantom_liability(self) -> None:
        banks = [{"id": "bank", "owner": "A", "balance": 0}]
        loans = [{"id": "loan", "owner": "A", "loan_type": "minus", "current_balance": 0,
                  "overdraft_bank_account_id": "bank"}]
        self.assert_debt(banks, loans, 0)

    def test_positive_linked_bank_remains_outside_debt_deduplication(self) -> None:
        banks = [{"id": "bank", "owner": "A", "balance": 50}]
        loans = [{"id": "loan", "owner": "A", "loan_type": "minus", "current_balance": 100,
                  "overdraft_bank_account_id": "bank"}]
        result = self.calculate_debt(banks, loans)
        self.assertEqual(result, {"totalPureDebt": 100, "totalMinusBankDebt": 0})

    def test_multiple_linked_overdrafts_are_each_counted_once(self) -> None:
        banks = [
            {"id": "bank-a", "owner": "A", "balance": -100},
            {"id": "bank-b", "owner": "A", "balance": -200},
        ]
        loans = [
            {"id": "loan-a", "owner": "A", "loan_type": "minus", "current_balance": 100,
             "overdraft_bank_account_id": "bank-a"},
            {"id": "loan-b", "owner": "A", "loan_type": "minus", "current_balance": 200,
             "overdraft_bank_account_id": "bank-b"},
        ]
        self.assert_debt(banks, loans, 300)

    def test_cross_owner_reference_does_not_suppress_negative_bank(self) -> None:
        banks = [{"id": "bank", "owner": "A", "balance": -100}]
        loans = [{"id": "loan", "owner": "B", "loan_type": "minus", "current_balance": 100,
                  "overdraft_bank_account_id": "bank"}]
        self.assert_debt(banks, loans, 200)


class PensionIrpCeilingTests(unittest.TestCase):
    @staticmethod
    def account(account_id: str, owner: str, account_type: str, deposit: float, **extra) -> dict:
        return {
            "id": account_id,
            "owner": owner,
            "account_type": account_type,
            "annual_deposit": deposit,
            "income_level": "low",
            **extra,
        }

    def total_eligible(self, pension: float, irp: float) -> int:
        result = get_total_tax_benefits({
            "accounts": [
                self.account("pension", "A", "pension_savings", pension),
                self.account("irp", "A", "irp", irp),
            ],
            "insurance_accounts": [],
        })
        return result["pension_irp"]["total_deduction"]

    def test_statutory_current_year_ceiling_scenarios(self) -> None:
        scenarios = (
            (4_000_000, 0, 4_000_000),
            (7_000_000, 0, 6_000_000),
            (6_000_000, 3_000_000, 9_000_000),
            (6_000_000, 9_000_000, 9_000_000),
            (2_000_000, 9_000_000, 9_000_000),
            (0, 9_000_000, 9_000_000),
            (10_000_000, 10_000_000, 9_000_000),
        )
        for pension, irp, expected in scenarios:
            with self.subTest(pension=pension, irp=irp):
                self.assertEqual(self.total_eligible(pension, irp), expected)

    def test_pension_priority_is_independent_of_account_order(self) -> None:
        result = get_total_tax_benefits({
            "accounts": [
                self.account("irp", "A", "irp", 9_000_000),
                self.account("pension", "A", "pension_savings", 6_000_000),
            ],
            "insurance_accounts": [],
        })
        by_type = {item["account_type"]: item["benefit"]["base_deduction_target"]
                   for item in result["pension_irp"]["items"]}
        self.assertEqual(by_type, {"irp": 3_000_000, "pension_savings": 6_000_000})

    def test_two_taxpayers_each_receive_their_own_combined_ceiling(self) -> None:
        accounts = []
        for owner in ("A", "B"):
            accounts.extend([
                self.account(f"pension-{owner}", owner, "pension_savings", 6_000_000),
                self.account(f"irp-{owner}", owner, "irp", 9_000_000),
            ])
        result = get_total_tax_benefits({"accounts": accounts, "insurance_accounts": []})
        self.assertEqual(result["pension_irp"]["total_deduction"], 18_000_000)
        self.assertEqual(
            get_total_tax_benefits({"accounts": accounts, "insurance_accounts": []}, owner="A")
            ["pension_irp"]["total_deduction"],
            9_000_000,
        )

    def test_non_deductible_accounts_do_not_consume_or_receive_credit_limit(self) -> None:
        accounts = [
            self.account("non", "A", "pension_savings_non_deductible", 10_000_000),
            self.account("irp", "A", "irp", 9_000_000),
        ]
        result = get_total_tax_benefits({"accounts": accounts, "insurance_accounts": []})
        self.assertEqual(result["pension_irp"]["total_deduction"], 9_000_000)
        self.assertEqual(result["pension_irp"]["items"][0]["benefit"]["base_deduction_target"], 0)

    def test_yearly_history_is_capped_per_owner_and_year(self) -> None:
        yearly = [{"year": "2025", "deposit": 9_000_000, "is_deductible": True}]
        accounts = [
            self.account("pension", "A", "pension_savings", 0, yearly_contributions=yearly),
            self.account("irp", "A", "irp", 0, yearly_contributions=yearly),
        ]
        result = get_total_tax_benefits({"accounts": accounts, "insurance_accounts": []})
        eligible = sum(
            item["benefit"]["yearly_contributions"][0]["deduction_target"]
            for item in result["pension_irp"]["items"]
        )
        self.assertEqual(eligible, 9_000_000)

    def test_legacy_irp_name_is_not_misclassified_as_pension_savings(self) -> None:
        account = self.account("legacy", "A", "general", 9_000_000)
        account["account_name"] = "개인형퇴직연금 IRP"
        result = get_total_tax_benefits({"accounts": [account], "insurance_accounts": []})
        self.assertEqual(result["pension_irp"]["items"][0]["account_type"], "irp")
        self.assertEqual(result["pension_irp"]["total_deduction"], 9_000_000)


if __name__ == "__main__":
    unittest.main()
