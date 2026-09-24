from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.dividend_records import get_actual_dividend_summary, write_dividend_records


class DividendIncomeSummaryTests(unittest.TestCase):
    def test_interest_is_stored_but_excluded_from_dividend_totals(self):
        with tempfile.TemporaryDirectory() as temp, patch(
            "app.services.dividend_records._get_user_dir",
            side_effect=lambda username=None: Path(temp) / (username or "sagesaint"),
        ):
            write_dividend_records(
                [
                    {
                        "id": "div-1", "date": "2026-09-01", "code": "005930", "name": "테스트주식",
                        "currency": "KRW", "amount": 1000, "amount_krw": 1000, "owner": "아빠",
                        "income_type": "dividend",
                    },
                    {
                        "id": "dist-1", "date": "2026-09-02", "code": "069500", "name": "테스트ETF",
                        "currency": "KRW", "amount": 500, "amount_krw": 500, "owner": "아빠",
                        "income_type": "distribution",
                    },
                    {
                        "id": "int-1", "date": "2026-09-03", "code": "INTEREST_CASH", "name": "토스증권 예탁금 이자",
                        "currency": "KRW", "amount": 200, "amount_krw": 200, "owner": "아빠",
                        "income_type": "account_interest",
                    },
                ],
                username="alice",
            )
            result = get_actual_dividend_summary(owner="아빠", year="2026", username="alice")

        self.assertEqual(result["total_actual_dividend_krw"], 1500)
        self.assertEqual(result["record_count"], 2)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["total_actual_interest_krw"], 200)
        self.assertEqual(result["interest_record_count"], 1)
        self.assertEqual(len(result["interest_records"]), 1)


if __name__ == "__main__":
    unittest.main()
