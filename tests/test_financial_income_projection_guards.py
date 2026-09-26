from __future__ import annotations

import unittest

from app.services.tax.financial_income import (
    FinancialIncomeProjectionError,
    build_financial_income_projection,
)


def _empty_schedule() -> list[dict]:
    return [
        {"month": month, "total_krw": 0, "items": []}
        for month in range(1, 13)
    ]


class FinancialIncomeProjectionGuardTests(unittest.TestCase):
    def test_unsupported_rule_year_fails_closed(self):
        with self.assertRaisesRegex(
            FinancialIncomeProjectionError,
            "FINANCIAL_INCOME_RULE_YEAR_UNSUPPORTED",
        ):
            build_financial_income_projection(
                {
                    "year": "2027",
                    "total_actual_dividend_krw": 0,
                    "total_actual_interest_krw": 0,
                },
                {"monthly_schedule": _empty_schedule()},
                as_of="2027-01-01",
            )

    def test_zero_gross_amount_does_not_override_positive_cash_receipt(self):
        result = build_financial_income_projection(
            {
                "year": "2026",
                "total_actual_dividend_krw": 1000,
                "total_actual_interest_krw": 0,
                "record_count": 1,
                "interest_record_count": 0,
                "records": [
                    {
                        "currency": "KRW",
                        "amount": 1000,
                        "amount_krw": 1000,
                        "gross_amount": 0,
                    }
                ],
                "interest_records": [],
            },
            {"monthly_schedule": _empty_schedule()},
            as_of="2026-09-26",
        )

        self.assertEqual(result["actual_gross_screening_income_krw"], 1000)
        self.assertFalse(result["data_quality"]["actual_gross_basis_complete"])
        self.assertEqual(result["data_quality"]["actual_cash_fallback_record_count"], 1)


if __name__ == "__main__":
    unittest.main()
