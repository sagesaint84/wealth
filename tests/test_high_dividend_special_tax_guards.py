from __future__ import annotations

import math
import unittest

from app.services.tax import (
    HighDividendSpecialTaxError,
    calculate_high_dividend_separate_tax_2026,
)


class HighDividendSpecialTaxGuardsTest(unittest.TestCase):
    def test_confirmation_required_when_special_treatment_requested(self):
        with self.assertRaisesRegex(
            HighDividendSpecialTaxError,
            "HIGH_DIVIDEND_COMPANY_CONFIRMATION_REQUIRED",
        ):
            calculate_high_dividend_separate_tax_2026(
                30_000_000,
                high_dividend_company_confirmed=False,
                separate_taxation_requested=True,
            )

    def test_negative_income_rejected(self):
        with self.assertRaisesRegex(
            HighDividendSpecialTaxError,
            "HIGH_DIVIDEND_SPECIAL_INCOME_INVALID",
        ):
            calculate_high_dividend_separate_tax_2026(-1)

    def test_nonfinite_income_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    HighDividendSpecialTaxError,
                    "HIGH_DIVIDEND_SPECIAL_INCOME_INVALID",
                ):
                    calculate_high_dividend_separate_tax_2026(value)

    def test_boolean_income_rejected(self):
        with self.assertRaisesRegex(
            HighDividendSpecialTaxError,
            "HIGH_DIVIDEND_SPECIAL_INCOME_INVALID",
        ):
            calculate_high_dividend_separate_tax_2026(True)

    def test_confirmation_must_be_boolean(self):
        with self.assertRaisesRegex(
            HighDividendSpecialTaxError,
            "HIGH_DIVIDEND_COMPANY_CONFIRMATION_INVALID",
        ):
            calculate_high_dividend_separate_tax_2026(
                10_000_000,
                high_dividend_company_confirmed="yes",
            )

    def test_request_flag_must_be_boolean(self):
        with self.assertRaisesRegex(
            HighDividendSpecialTaxError,
            "HIGH_DIVIDEND_SEPARATE_TAX_REQUEST_INVALID",
        ):
            calculate_high_dividend_separate_tax_2026(
                10_000_000,
                separate_taxation_requested=1,
            )

    def test_unsupported_year_fails_closed(self):
        with self.assertRaisesRegex(
            HighDividendSpecialTaxError,
            "HIGH_DIVIDEND_RULE_YEAR_UNSUPPORTED",
        ):
            calculate_high_dividend_separate_tax_2026(10_000_000, tax_year=2027)

    def test_invalid_year_rejected(self):
        for value in (True, "bad"):
            with self.subTest(value=value):
                with self.assertRaises(HighDividendSpecialTaxError):
                    calculate_high_dividend_separate_tax_2026(
                        10_000_000,
                        tax_year=value,
                    )


if __name__ == "__main__":
    unittest.main()
