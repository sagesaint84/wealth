from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest

from app.services.tax_benefit import get_total_tax_benefits


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"


class FrontendPensionIrpTaxCorrectnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("node"):
            raise unittest.SkipTest("node runtime is not available")
        cls.source = WEALTH_JS.read_text(encoding="utf-8")

    def run_frontend(self, accounts: list[dict], selected_id: str | None = None) -> dict:
        script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const deductibleStart = source.indexOf('function isAccountTaxDeductible');
const deductibleEnd = source.indexOf('\nfunction isTaxAdvantagedAccount', deductibleStart);
const advantagedStart = deductibleEnd + 1;
const advantagedEnd = source.indexOf('\n// ── 4.', advantagedStart);
const categoryStart = source.indexOf('function getTaxCategory');
const categoryEnd = source.indexOf('\nfunction renderTaxAccountHoldings', categoryStart);
if ([deductibleStart, deductibleEnd, advantagedEnd, categoryStart, categoryEnd].some(i => i < 0)) {
  throw new Error('pension tax helpers not found');
}
const sandbox = {};
vm.runInNewContext(
  source.slice(deductibleStart, deductibleEnd) + '\n' +
  source.slice(advantagedStart, advantagedEnd) + '\n' +
  source.slice(categoryStart, categoryEnd) +
  '\nthis.calculate = calculateOwnerYearPensionTaxBenefits;' +
  '\nthis.accountSaved = calcAccountCumulativeTaxSaved;',
  sandbox
);
const input = JSON.parse(process.argv[2]);
const result = sandbox.calculate(input.accounts);
if (input.selectedId) {
  const selected = input.accounts.find(account => account.id === input.selectedId);
  result.selectedOwnerCumulativeTaxSaved = sandbox.accountSaved(selected, input.accounts);
}
process.stdout.write(JSON.stringify(result));
"""
        result = subprocess.run(
            ["node", "-e", script, str(WEALTH_JS), json.dumps({"accounts": accounts, "selectedId": selected_id})],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(result.stdout)

    @staticmethod
    def account(account_id: str, owner: str | None, account_type: str, deposit: float, **extra) -> dict:
        account = {
            "id": account_id,
            "account_type": account_type,
            "annual_deposit": deposit,
            "income_level": "low",
            **extra,
        }
        if owner is not None:
            account["owner"] = owner
        return account

    def test_single_owner_statutory_ceiling_scenarios(self) -> None:
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
                result = self.run_frontend([
                    self.account("pension", "A", "pension_savings", pension),
                    self.account("irp", "A", "irp", irp),
                ])
                self.assertEqual(result["current"]["eligibleContribution"], expected)

    def test_multiple_accounts_aggregate_before_category_and_combined_caps(self) -> None:
        result = self.run_frontend([
            self.account("pension-1", "A", "pension_savings", 4_000_000),
            self.account("pension-2", "A", "pension_savings", 4_000_000),
            self.account("irp-1", "A", "irp", 2_000_000),
            self.account("irp-2", "A", "irp", 3_000_000),
        ])
        current = result["current"]
        self.assertEqual(current["pensionEligibleContribution"], 6_000_000)
        self.assertEqual(current["irpEligibleContribution"], 3_000_000)
        self.assertEqual(current["eligibleContribution"], 9_000_000)

    def test_limits_are_independent_per_owner(self) -> None:
        accounts = []
        for owner in ("A", "B"):
            accounts.extend([
                self.account(f"pension-{owner}", owner, "pension_savings", 6_000_000),
                self.account(f"irp-{owner}", owner, "irp", 3_000_000),
            ])
        result = self.run_frontend(accounts)
        self.assertEqual(result["current"]["eligibleContribution"], 18_000_000)
        self.assertEqual(result["current"]["byOwner"]["A"]["eligibleContribution"], 9_000_000)
        self.assertEqual(result["current"]["byOwner"]["B"]["eligibleContribution"], 9_000_000)

    def test_limits_are_independent_per_tax_year(self) -> None:
        years = [
            {"year": "2025", "deposit": 6_000_000, "is_deductible": True, "income_level": "low"},
            {"year": "2026", "deposit": 6_000_000, "is_deductible": True, "income_level": "low"},
        ]
        irp_years = [
            {"year": "2025", "deposit": 3_000_000, "is_deductible": True, "income_level": "low"},
            {"year": "2026", "deposit": 3_000_000, "is_deductible": True, "income_level": "low"},
        ]
        result = self.run_frontend([
            self.account("pension", "A", "pension_savings", 6_000_000, yearly_contributions=years),
            self.account("irp", "A", "irp", 3_000_000, yearly_contributions=irp_years),
        ])
        self.assertEqual(result["cumulative"]["eligibleContribution"], 18_000_000)
        for year in ("2025", "2026"):
            self.assertEqual(result["cumulative"]["byOwnerYear"][f"A\x00{year}"]["eligibleContribution"], 9_000_000)

    def test_non_deductible_contributions_do_not_consume_the_ceiling(self) -> None:
        result = self.run_frontend([
            self.account(
                "pension",
                "A",
                "pension_savings_non_deductible",
                10_000_000,
                yearly_contributions=[{"year": "2026", "deposit": 10_000_000, "is_deductible": False}],
            ),
            self.account("irp", "A", "irp", 9_000_000),
        ])
        self.assertEqual(result["current"]["eligibleContribution"], 9_000_000)
        self.assertEqual(result["cumulative"]["eligibleContribution"], 9_000_000)

    def test_missing_owner_uses_the_legacy_all_scope(self) -> None:
        result = self.run_frontend([
            self.account("pension", None, "pension_savings", 6_000_000),
            self.account("irp", "모두", "irp", 9_000_000),
        ])
        self.assertEqual(result["current"]["eligibleContribution"], 9_000_000)
        self.assertEqual(result["current"]["byOwner"]["모두"]["eligibleContribution"], 9_000_000)

    def test_individual_account_value_is_owner_combined_not_arbitrarily_allocated(self) -> None:
        accounts = [
            self.account("pension-1", "A", "pension_savings", 4_000_000),
            self.account("pension-2", "A", "pension_savings", 4_000_000),
            self.account("irp", "A", "irp", 5_000_000),
        ]
        first = self.run_frontend(accounts, "pension-1")
        irp = self.run_frontend(accounts, "irp")
        self.assertEqual(first["selectedOwnerCumulativeTaxSaved"], irp["selectedOwnerCumulativeTaxSaved"])
        self.assertEqual(first["selectedOwnerCumulativeTaxSaved"], 1_485_000)
        self.assertIn("소유자 합산 누적 절세액", self.source)

    def test_year_specific_income_rates_are_applied_after_owner_year_caps(self) -> None:
        result = self.run_frontend([
            self.account("pension", "A", "pension_savings", 0, yearly_contributions=[
                {"year": "2025", "deposit": 6_000_000, "is_deductible": True, "income_level": "high"},
                {"year": "2026", "deposit": 6_000_000, "is_deductible": True, "income_level": "low"},
            ]),
            self.account("irp", "A", "irp", 0, yearly_contributions=[
                {"year": "2025", "deposit": 3_000_000, "is_deductible": True, "income_level": "high"},
                {"year": "2026", "deposit": 3_000_000, "is_deductible": True, "income_level": "low"},
            ]),
        ])
        self.assertEqual(result["cumulative"]["taxSaved"], 1_188_000 + 1_485_000)

    def test_frontend_matches_backend_for_base_caps_rates_and_isa_transfer(self) -> None:
        accounts = [
            self.account("pension", "A", "pension_savings", 6_000_000, isa_transfer_amount=10_000_000),
            self.account("irp", "A", "irp", 9_000_000),
            self.account("pension-b", "B", "pension_savings", 4_000_000, income_level="high"),
        ]
        frontend = self.run_frontend(accounts)
        backend = get_total_tax_benefits({"accounts": accounts, "insurance_accounts": []})
        backend_current_eligible = backend["pension_irp"]["total_deduction"]
        backend_current_saved = (
            backend["pension_irp"]["total_tax_refund"]
            + backend["pension_irp"]["total_isa_tax_refund"]
        )
        self.assertEqual(frontend["current"]["eligibleContribution"], backend_current_eligible)
        self.assertEqual(frontend["current"]["taxSaved"], backend_current_saved)
        self.assertEqual(frontend["cumulative"]["taxSaved"], backend["grand_total_cumulative_tax_benefit"])

    def test_frontend_yearly_history_matches_backend_owner_year_allocation(self) -> None:
        accounts = [
            self.account("pension-a", "A", "pension_savings", 0, yearly_contributions=[
                {"year": "2025", "deposit": 7_000_000, "is_deductible": True, "income_level": "high"},
                {"year": "2026", "deposit": 2_000_000, "is_deductible": True, "income_level": "low"},
            ]),
            self.account("irp-a", "A", "irp", 0, yearly_contributions=[
                {"year": "2025", "deposit": 9_000_000, "is_deductible": True, "income_level": "high"},
                {"year": "2026", "deposit": 9_000_000, "is_deductible": True, "income_level": "low"},
            ]),
            self.account("irp-b", "B", "irp", 0, yearly_contributions=[
                {"year": "2025", "deposit": 9_000_000, "is_deductible": True, "income_level": "low"},
            ]),
        ]
        frontend = self.run_frontend(accounts)
        backend = get_total_tax_benefits({"accounts": accounts, "insurance_accounts": []})
        backend_yearly_eligible = sum(
            yearly["deduction_target"]
            for item in backend["pension_irp"]["items"]
            for yearly in item["benefit"]["yearly_contributions"]
        )
        self.assertEqual(frontend["cumulative"]["eligibleContribution"], backend_yearly_eligible)
        self.assertEqual(frontend["cumulative"]["taxSaved"], backend["grand_total_cumulative_tax_benefit"])

    def test_isa_account_display_contract_is_unchanged(self) -> None:
        result = self.run_frontend([
            self.account("isa", "A", "isa", 99_000_000, isa_transfer_amount=99_000_000),
        ])
        self.assertEqual(result["current"]["eligibleContribution"], 0)
        self.assertEqual(result["current"]["taxSaved"], 0)
        self.assertIn("ISA 혜택: 비과세 200~400만 + 9.9% 분리과세", self.source)

    def test_general_accounts_are_not_reclassified_as_pension_savings(self) -> None:
        result = self.run_frontend([
            self.account("general", "A", "general", 99_000_000, name="일반 증권계좌"),
            self.account("irp", "A", "irp", 9_000_000),
        ])
        self.assertEqual(result["current"]["eligibleContribution"], 9_000_000)

    def test_preexisting_kb_ui_hunks_remain_present(self) -> None:
        self.assertIn("const kbRealizedState = {", self.source)
        self.assertIn("function renderKbFeedTable()", self.source)
        self.assertIn("function initKbRealizedUI()", self.source)
        self.assertIn("initKbRealizedUI();", self.source)

    def test_all_cumulative_display_consumers_use_owner_context(self) -> None:
        self.assertNotIn("taxAccounts.reduce((sum, a) => sum + calcAccountCumulativeTaxSaved", self.source)
        self.assertNotIn("irpAccounts.reduce((sum, a) => sum + calcAccountCumulativeTaxSaved", self.source)
        self.assertNotIn("pensionAccounts.reduce((sum, a) => sum + calcAccountCumulativeTaxSaved", self.source)
        self.assertIn("calcAccountCumulativeTaxSaved(targetAcc, taxAccounts)", self.source)
        self.assertIn("calcAccountCumulativeTaxSaved(acct, taxAccounts)", self.source)


if __name__ == "__main__":
    unittest.main()
