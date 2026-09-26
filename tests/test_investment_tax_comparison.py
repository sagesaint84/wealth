from __future__ import annotations

import unittest

from app.services.tax.investment_tax import (
    ASSET_DOMESTIC_DIVIDEND_STOCK,
    ASSET_KR_LISTED_US_ETF,
    ASSET_US_DIRECT,
    compare_investment_tax_2026,
)


class InvestmentTaxComparisonTests(unittest.TestCase):
    def test_kr_listed_us_etf_uses_provided_taxable_gain_basis(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_KR_LISTED_US_ETF,
            annual_distribution_krw=10_000_000,
            annual_realized_gain_krw=20_000_000,
            taxable_etf_gain_krw=5_000_000,
            existing_personal_financial_income_krw=3_000_000,
        )

        individual = result["individual"]
        self.assertEqual(individual["gross_cash_return_krw"], 30_000_000)
        self.assertEqual(individual["financial_income_addition_krw"], 15_000_000)
        self.assertEqual(individual["projected_financial_income_krw"], 18_000_000)
        self.assertFalse(individual["comprehensive_tax_screening"])
        self.assertEqual(
            individual["taxes"]["domestic_dividend_withholding_krw"],
            2_310_000,
        )
        self.assertEqual(individual["after_known_tax_cash_krw"], 27_690_000)
        self.assertEqual(
            individual["data_quality"]["taxable_etf_gain_basis"], "provided"
        )

        corporation = result["family_corporation"]
        self.assertEqual(corporation["taxable_investment_income_krw"], 30_000_000)
        self.assertEqual(
            corporation["taxes"]["incremental_corporate_income_tax_krw"],
            3_000_000,
        )
        self.assertEqual(
            corporation["taxes"]["incremental_corporate_local_income_tax_krw"],
            300_000,
        )
        self.assertEqual(corporation["after_corporate_tax_return_krw"], 26_700_000)

    def test_kr_listed_us_etf_falls_back_to_realized_gain_for_screening(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_KR_LISTED_US_ETF,
            annual_distribution_krw=1_000_000,
            annual_realized_gain_krw=4_000_000,
        )

        individual = result["individual"]
        self.assertEqual(individual["financial_income_addition_krw"], 5_000_000)
        self.assertEqual(
            individual["data_quality"]["taxable_etf_gain_basis"],
            "realized_gain_conservative_fallback",
        )

    def test_personal_financial_income_threshold_is_screened(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_KR_LISTED_US_ETF,
            annual_distribution_krw=6_000_000,
            annual_realized_gain_krw=0,
            taxable_etf_gain_krw=0,
            existing_personal_financial_income_krw=15_000_000,
        )

        self.assertEqual(
            result["individual"]["projected_financial_income_krw"], 21_000_000
        )
        self.assertTrue(result["individual"]["comprehensive_tax_screening"])
        self.assertFalse(
            result["individual"]["data_quality"][
                "comprehensive_income_final_tax_calculated"
            ]
        )

    def test_us_direct_separates_dividend_withholding_and_capital_gain_tax(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_US_DIRECT,
            annual_distribution_krw=10_000_000,
            annual_realized_gain_krw=10_000_000,
        )

        individual = result["individual"]
        self.assertEqual(individual["taxable_foreign_share_gain_krw"], 7_500_000)
        self.assertEqual(
            individual["taxes"]["us_dividend_withholding_krw"], 1_500_000
        )
        self.assertEqual(
            individual["taxes"]["foreign_share_capital_gain_income_tax_krw"],
            1_500_000,
        )
        self.assertEqual(
            individual["taxes"]["foreign_share_capital_gain_local_tax_krw"],
            150_000,
        )
        self.assertEqual(individual["taxes"]["known_tax_total_krw"], 3_150_000)
        self.assertEqual(individual["after_known_tax_cash_krw"], 16_850_000)

        corporation = result["family_corporation"]
        self.assertEqual(
            corporation["taxes"]["estimated_foreign_tax_credit_krw"], 1_000_000
        )
        self.assertEqual(
            corporation["taxes"]["incremental_corporate_income_tax_krw"],
            1_000_000,
        )
        self.assertEqual(
            corporation["taxes"]["incremental_corporate_local_income_tax_krw"],
            200_000,
        )
        self.assertEqual(corporation["taxes"]["known_tax_total_krw"], 2_700_000)
        self.assertEqual(corporation["after_corporate_tax_return_krw"], 17_300_000)

    def test_domestic_dividend_received_exclusion_uses_30_percent_tier(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_DOMESTIC_DIVIDEND_STOCK,
            annual_distribution_krw=100_000_000,
            domestic_dividend_exclusion_eligible=True,
            domestic_dividend_ownership_pct=5,
            domestic_dividend_holding_months=3,
        )

        corporation = result["family_corporation"]
        self.assertEqual(corporation["domestic_received_dividend_exclusion_rate"], 0.3)
        self.assertEqual(corporation["taxable_investment_income_krw"], 70_000_000)
        self.assertEqual(corporation["taxes"]["known_tax_total_krw"], 7_700_000)
        self.assertEqual(corporation["after_corporate_tax_return_krw"], 92_300_000)

    def test_domestic_dividend_exclusion_requires_three_month_holding(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_DOMESTIC_DIVIDEND_STOCK,
            annual_distribution_krw=100_000_000,
            domestic_dividend_exclusion_eligible=True,
            domestic_dividend_ownership_pct=60,
            domestic_dividend_holding_months=2.9,
        )

        corporation = result["family_corporation"]
        self.assertEqual(corporation["domestic_received_dividend_exclusion_rate"], 0.0)
        self.assertEqual(corporation["taxes"]["known_tax_total_krw"], 11_000_000)

    def test_domestic_dividend_exclusion_tiers_include_80_and_100_percent(self):
        eighty = compare_investment_tax_2026(
            asset_type=ASSET_DOMESTIC_DIVIDEND_STOCK,
            annual_distribution_krw=100_000_000,
            domestic_dividend_exclusion_eligible=True,
            domestic_dividend_ownership_pct=20,
            domestic_dividend_holding_months=12,
        )
        hundred = compare_investment_tax_2026(
            asset_type=ASSET_DOMESTIC_DIVIDEND_STOCK,
            annual_distribution_krw=100_000_000,
            domestic_dividend_exclusion_eligible=True,
            domestic_dividend_ownership_pct=50,
            domestic_dividend_holding_months=12,
        )

        self.assertEqual(
            eighty["family_corporation"]["domestic_received_dividend_exclusion_rate"],
            0.8,
        )
        self.assertEqual(
            hundred["family_corporation"]["domestic_received_dividend_exclusion_rate"],
            1.0,
        )

    def test_owner_distribution_shows_second_tax_layer_and_threshold(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_KR_LISTED_US_ETF,
            annual_distribution_krw=10_000_000,
            taxable_etf_gain_krw=0,
            existing_personal_financial_income_krw=16_000_000,
            corporation_to_owner_distribution_krw=5_000_000,
        )

        extraction = result["corporation_to_owner"]
        self.assertEqual(extraction["distributed_gross_krw"], 5_000_000)
        self.assertEqual(extraction["estimated_dividend_withholding_krw"], 770_000)
        self.assertEqual(extraction["owner_cash_after_withholding_krw"], 4_230_000)
        self.assertEqual(extraction["retained_in_corporation_krw"], 3_900_000)
        self.assertEqual(extraction["combined_known_after_tax_value_krw"], 8_130_000)
        self.assertEqual(extraction["owner_projected_financial_income_krw"], 21_000_000)
        self.assertTrue(extraction["comprehensive_tax_screening"])
        self.assertFalse(extraction["final_owner_income_tax_calculated"])

    def test_qualified_foreign_subsidiary_exclusion_requires_explicit_flag_and_ownership(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_US_DIRECT,
            annual_distribution_krw=100_000_000,
            foreign_subsidiary_exclusion_qualified=True,
            foreign_ownership_pct=10,
            us_treaty_parent_rate_qualified=True,
        )

        corporation = result["family_corporation"]
        self.assertEqual(corporation["foreign_subsidiary_dividend_exclusion_rate"], 0.95)
        self.assertEqual(corporation["taxable_investment_income_krw"], 5_000_000)
        self.assertEqual(corporation["us_dividend_withholding_rate"], 0.10)
        self.assertEqual(corporation["taxes"]["estimated_foreign_tax_credit_krw"], 0)
        self.assertFalse(corporation["data_quality"]["foreign_tax_credit_estimated"])

    def test_treaty_parent_rate_is_not_assumed_from_ownership_alone(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_US_DIRECT,
            annual_distribution_krw=10_000_000,
            foreign_ownership_pct=20,
            us_treaty_parent_rate_qualified=False,
        )
        self.assertEqual(
            result["family_corporation"]["us_dividend_withholding_rate"], 0.15
        )

    def test_existing_corporate_income_uses_marginal_bracket_for_incremental_tax(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_KR_LISTED_US_ETF,
            annual_distribution_krw=100_000_000,
            taxable_etf_gain_krw=0,
            existing_corporate_taxable_income_krw=200_000_000,
        )

        corporation = result["family_corporation"]
        self.assertEqual(
            corporation["taxes"]["incremental_corporate_income_tax_krw"],
            20_000_000,
        )
        self.assertEqual(
            corporation["taxes"]["incremental_corporate_local_income_tax_krw"],
            2_000_000,
        )

    def test_corporate_deductible_expense_reduces_taxable_investment_income_and_cash(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_KR_LISTED_US_ETF,
            annual_distribution_krw=20_000_000,
            taxable_etf_gain_krw=0,
            corporate_deductible_expenses_krw=5_000_000,
        )

        corporation = result["family_corporation"]
        self.assertEqual(corporation["taxable_investment_income_krw"], 15_000_000)
        self.assertEqual(corporation["taxes"]["known_tax_total_krw"], 1_650_000)
        self.assertEqual(corporation["after_corporate_tax_return_krw"], 13_350_000)

    def test_comparison_is_explicitly_screening_only(self):
        result = compare_investment_tax_2026(
            asset_type=ASSET_KR_LISTED_US_ETF,
            annual_distribution_krw=1_000_000,
            taxable_etf_gain_krw=0,
        )

        self.assertTrue(result["comparison"]["screening_only"])
        self.assertFalse(result["comparison"]["legal_tax_determination"])
        self.assertIn("official_sources", result["rule_context"])
        self.assertIn("final comprehensive personal income tax", result["rule_context"]["not_calculated"])


if __name__ == "__main__":
    unittest.main()
