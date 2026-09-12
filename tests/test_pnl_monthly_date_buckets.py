from __future__ import annotations

import unittest

from app.services import pnl_records
from tests.regression_support import IsolatedDataTestCase


class PnlMonthlyDateBucketTests(IsolatedDataTestCase):
    def test_compact_and_hyphenated_dates_share_the_actual_monthly_bucket(self) -> None:
        records = [
            {
                "id": "synthetic-kiwoom-compact",
                "source": "kiwoom",
                "date": "20260912",
                "asset_type": "stock",
                "code": "SYN-KIWOOM",
                "pnl_krw": 11,
            },
            {
                "id": "synthetic-hyphenated-equivalent",
                "source": "manual",
                "date": "2026-09-12",
                "asset_type": "stock",
                "code": "SYN-MANUAL",
                "pnl_krw": 13,
            },
        ]
        pnl_records.write_pnl_records(records, username="monthly-date-fixture")

        summary = pnl_records.get_pnl_summary(year=2026, username="monthly-date-fixture")
        monthly = {item["month"]: item["total_krw"] for item in summary["monthly_schedule"]}

        self.assertEqual(monthly[9], 24)
        self.assertEqual(monthly[1], 0)

    def test_existing_hyphenated_toss_kis_and_nh_dates_keep_their_months(self) -> None:
        records = [
            {
                "id": "synthetic-toss",
                "source": "toss_wts",
                "date": "2026-07-01",
                "asset_type": "stock",
                "code": "SYN-TOSS",
                "pnl_krw": 7,
            },
            {
                "id": "synthetic-kis",
                "source": "kis",
                "date": "2026-08-01",
                "asset_type": "stock",
                "code": "SYN-KIS",
                "pnl_krw": 8,
            },
            {
                "id": "synthetic-nh",
                "source": "nh",
                "date": "2026-10-01",
                "asset_type": "stock",
                "code": "SYN-NH",
                "pnl_krw": 10,
            },
        ]
        pnl_records.write_pnl_records(records, username="monthly-provider-fixture")

        summary = pnl_records.get_pnl_summary(year=2026, username="monthly-provider-fixture")
        monthly = {item["month"]: item["total_krw"] for item in summary["monthly_schedule"]}

        self.assertEqual(monthly[7], 7)
        self.assertEqual(monthly[8], 8)
        self.assertEqual(monthly[10], 10)


if __name__ == "__main__":
    unittest.main()
