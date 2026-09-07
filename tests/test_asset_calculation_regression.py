from __future__ import annotations

import unittest
from pathlib import Path

from app.services import portfolio, real_estate, savings
from regression_support import IsolatedDataTestCase, PROJECT_ROOT, empty_portfolio


class AssetCalculationRegressionTests(IsolatedDataTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.data = empty_portfolio(
            settings={
                "fx_rates": {"KRW": 1.0, "USD": 1300.0},
                "cash_balances": {"brokerage": {"KRW": 20, "USD": 0}},
            },
            accounts=[
                {
                    "id": "brokerage",
                    "broker": "가상증권",
                    "name": "가상 일반계좌",
                    "owner": "아빠",
                    "account_type": "general",
                    "family_group": "아빠",
                    "source": "fixture",
                }
            ],
            holdings=[
                {
                    "id": "stock",
                    "account_id": "brokerage",
                    "broker": "가상증권",
                    "account_name": "가상 일반계좌",
                    "code": "SAFE",
                    "name": "가상 주식",
                    "quantity": 2,
                    "avg_price": 40,
                    "current_price": 50,
                    "currency": "KRW",
                    "market": "KRX",
                    "source": "fixture",
                    "sector": "테스트",
                    "owner": "아빠",
                }
            ],
            bank_accounts=[
                {"id": "bank-positive", "owner": "아빠", "balance": 40},
                {"id": "bank-minus", "owner": "엄마", "balance": -10, "interest_rate": 0},
            ],
            savings_accounts=[
                {
                    "id": "saving",
                    "owner": "아빠",
                    "saving_type": "deposit",
                    "target_amount": 30,
                    "current_paid_amount": 30,
                    "interest_rate": 0,
                    "duration_months": 12,
                }
            ],
            insurance_accounts=[
                {
                    "id": "insurance",
                    "owner": "엄마",
                    "insurance_type": "protection",
                    "expected_amount": 25,
                    "total_paid_amount": 12,
                    "monthly_premium": 1,
                }
            ],
            loan_accounts=[
                {
                    "id": "loan",
                    "owner": "아빠",
                    "current_balance": 100,
                    "interest_rate": 0,
                    "repayment_type": "bullet",
                }
            ],
            real_estates=[
                {
                    "id": "home",
                    "property_type": "own",
                    "name": "가상 자가",
                    "owner": "아빠",
                    "ownerships": [{"owner": "아빠", "ratio": 100}],
                    "purchase_price": 400,
                    "current_price": 500,
                    "deposit_amount": 0,
                    "linked_loan_ids": ["loan"],
                },
                {
                    "id": "rental",
                    "property_type": "rental",
                    "name": "가상 임대주택",
                    "owner": "엄마",
                    "ownerships": [{"owner": "엄마", "ratio": 100}],
                    "purchase_price": 250,
                    "current_price": 300,
                    "deposit_amount": 80,
                    "linked_loan_ids": [],
                },
                {
                    "id": "lease",
                    "property_type": "lease",
                    "name": "가상 임차주택",
                    "owner": "자녀",
                    "ownerships": [{"owner": "자녀", "ratio": 100}],
                    "purchase_price": 0,
                    "current_price": 0,
                    "deposit_amount": 50,
                    "linked_loan_ids": [],
                },
            ],
        )
        portfolio.write_portfolio(self.data, username="fixture_user")

    def test_stock_value_and_brokerage_cash_calculation(self) -> None:
        dashboard = portfolio.get_dashboard(username="fixture_user")

        self.assertEqual(dashboard["summary"]["total_stock_value_krw"], 100)
        self.assertEqual(dashboard["summary"]["total_cost_krw"], 80)
        self.assertEqual(dashboard["summary"]["profit_krw"], 20)
        self.assertEqual(dashboard["summary"]["total_cash_krw"], 20)
        self.assertEqual(dashboard["summary"]["total_value_krw"], 120)

    def test_bank_savings_insurance_and_loan_calculation(self) -> None:
        result = savings.get_savings_data(username="fixture_user")
        summary = result["summary"]

        self.assertEqual(summary["total_bank_balance"], 30)
        self.assertEqual(summary["total_positive_bank_balance"], 40)
        self.assertEqual(summary["total_minus_bank_debt"], 10)
        self.assertEqual(summary["total_savings_paid"], 30)
        self.assertEqual(summary["total_insurance_expected"], 25)
        self.assertEqual(summary["total_pure_loan_balance"], 100)
        self.assertEqual(summary["total_loan_balance"], 110)
        self.assertEqual(summary["net_bank_worth"], -40)

    def test_real_estate_tenant_deposit_and_landlord_obligation_calculation(self) -> None:
        result = real_estate.get_real_estate_data(username="fixture_user")
        summary = result["summary"]
        items = {item["id"]: item for item in result["real_estates"]}

        self.assertEqual(summary["total_real_estate_value"], 800)
        self.assertEqual(summary["total_tenant_deposit_asset"], 50)
        self.assertEqual(summary["total_landlord_deposit_debt"], 80)
        self.assertEqual(summary["total_linked_loan_debt"], 100)
        self.assertEqual(summary["total_real_estate_debt"], 180)
        self.assertEqual(summary["net_real_estate_worth"], 670)
        self.assertEqual(items["home"]["net_equity"], 400)
        self.assertEqual(items["rental"]["net_equity"], 220)
        self.assertEqual(items["lease"]["net_equity"], 50)

    def test_current_net_worth_component_formula(self) -> None:
        dashboard = portfolio.get_dashboard(username="fixture_user")
        savings_data = savings.get_savings_data(username="fixture_user")
        real_estate_data = real_estate.get_real_estate_data(username="fixture_user")

        portfolio_summary = dashboard["summary"]
        savings_summary = savings_data["summary"]
        real_estate_summary = real_estate_data["summary"]

        total_invest_assets = (
            real_estate_summary["total_real_estate_value"]
            + portfolio_summary["total_stock_value_krw"]
        )
        total_safe_assets = (
            portfolio_summary["total_cash_krw"]
            + savings_summary["total_positive_bank_balance"]
            + savings_summary["total_savings_paid"]
            + savings_summary["total_insurance_expected"]
            + real_estate_summary["total_tenant_deposit_asset"]
        )
        total_debt = (
            savings_summary["total_pure_loan_balance"]
            + savings_summary["total_minus_bank_debt"]
            + real_estate_summary["total_landlord_deposit_debt"]
        )

        self.assertEqual(total_invest_assets, 900)
        self.assertEqual(total_safe_assets, 165)
        self.assertEqual(total_debt, 190)
        self.assertEqual((total_invest_assets + total_safe_assets) - total_debt, 875)

    def test_frontend_net_worth_formula_contract_is_unchanged(self) -> None:
        source = (PROJECT_ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")

        expected_lines = (
            "const totalAllDebt = totalPureDebt + totalMinusBankDebt + totalLandlordDepositDebt;",
            "const totalInvestAssets = totalREInvestEquity + totalStockVal;",
            "const totalSafeAssets = totalAllCash + totalTenantDepositVal + insuranceTotal;",
            "const netWorth = (totalInvestAssets + totalSafeAssets) - totalAllDebt;",
        )
        for line in expected_lines:
            with self.subTest(line=line):
                self.assertIn(line, source)


if __name__ == "__main__":
    unittest.main()
