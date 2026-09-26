from __future__ import annotations

import unittest

from app.services.tax.investment_tax import (
    ASSET_KR_LISTED_US_ETF,
    InvestmentTaxComparisonError,
    compare_investment_tax_2026,
)


class InvestmentTaxComparisonGuardTests(unittest.TestCase):
    def assertCode(self, expected: str, **kwargs):
        with self.assertRaises(InvestmentTaxComparisonError) as ctx:
            compare_investment_tax_2026(**kwargs)
        self.assertEqual(str(ctx.exception), expected)

    def test_unsupported_year_fails_closed(self):
        self.assertCode(
            "INVESTMENT_TAX_RULE_YEAR_UNSUPPORTED",
            asset_type=ASSET_KR_LISTED_US_ETF,
            year=2027,
        )

    def test_unknown_asset_type_is_rejected(self):
        self.assertCode(
            "INVESTMENT_TAX_ASSET_TYPE_INVALID",
            asset_type="crypto",
        )

    def test_negative_money_inputs_are_rejected(self):
        fields = [
            ("annual_distribution_krw", "INVESTMENT_TAX_DISTRIBUTION_INVALID"),
            ("annual_realized_gain_krw", "INVESTMENT_TAX_REALIZED_GAIN_INVALID"),
            ("taxable_etf_gain_krw", "INVESTMENT_TAX_ETF_GAIN_INVALID"),
            (
                "existing_personal_financial_income_krw",
                "INVESTMENT_TAX_PERSONAL_FINANCIAL_INCOME_INVALID",
            ),
            (
                "existing_corporate_taxable_income_krw",
                "INVESTMENT_TAX_CORPORATE_INCOME_INVALID",
            ),
            ("corporate_deductible_expenses_krw", "INVESTMENT_TAX_CORPORATE_EXPENSE_INVALID"),
            (
                "corporation_to_owner_distribution_krw",
                "INVESTMENT_TAX_OWNER_DISTRIBUTION_INVALID",
            ),
        ]
        for field, code in fields:
            with self.subTest(field=field):
                self.assertCode(
                    code,
                    asset_type=ASSET_KR_LISTED_US_ETF,
                    **{field: -1},
                )

    def test_nonfinite_money_is_rejected(self):
        for value in (float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertCode(
                    "INVESTMENT_TAX_DISTRIBUTION_INVALID",
                    asset_type=ASSET_KR_LISTED_US_ETF,
                    annual_distribution_krw=value,
                )

    def test_ownership_percentages_must_be_between_zero_and_one_hundred(self):
        self.assertCode(
            "INVESTMENT_TAX_DOMESTIC_OWNERSHIP_INVALID",
            asset_type=ASSET_KR_LISTED_US_ETF,
            domestic_dividend_ownership_pct=100.1,
        )
        self.assertCode(
            "INVESTMENT_TAX_FOREIGN_OWNERSHIP_INVALID",
            asset_type=ASSET_KR_LISTED_US_ETF,
            foreign_ownership_pct=101,
        )

    def test_boolean_qualification_flags_do_not_accept_numbers(self):
        self.assertCode(
            "INVESTMENT_TAX_DOMESTIC_DIVIDEND_ELIGIBILITY_INVALID",
            asset_type=ASSET_KR_LISTED_US_ETF,
            domestic_dividend_exclusion_eligible=1,
        )
        self.assertCode(
            "INVESTMENT_TAX_US_TREATY_QUALIFICATION_INVALID",
            asset_type=ASSET_KR_LISTED_US_ETF,
            us_treaty_parent_rate_qualified="yes",
        )
        self.assertCode(
            "INVESTMENT_TAX_FOREIGN_SUBSIDIARY_QUALIFICATION_INVALID",
            asset_type=ASSET_KR_LISTED_US_ETF,
            foreign_subsidiary_exclusion_qualified=None,
        )

    def test_owner_distribution_cannot_exceed_current_after_tax_return(self):
        self.assertCode(
            "INVESTMENT_TAX_OWNER_DISTRIBUTION_EXCEEDS_RETURN",
            asset_type=ASSET_KR_LISTED_US_ETF,
            annual_distribution_krw=10_000_000,
            taxable_etf_gain_krw=0,
            corporation_to_owner_distribution_krw=9_000_000,
        )


if __name__ == "__main__":
    unittest.main()
