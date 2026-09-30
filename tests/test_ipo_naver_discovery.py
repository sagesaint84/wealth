from __future__ import annotations

import unittest

from app.services.ipo.naver_discovery import parse_naver_ipo_discovery_json


class IpoNaverDiscoveryTests(unittest.TestCase):
    def test_blank_listing_date_keeps_prelisting_identity(self):
        rows = parse_naver_ipo_discovery_json({
            "subscriptionList": [{
                "ipoCode": "A179880",
                "compName": "멜콘",
                "marketType": "KOSDAQ",
                "gsrClass": "G",
                "ipoStatus": "청약",
                "lcalDate": "",
            }]
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["stock_code"], "179880")
        self.assertEqual(rows[0]["company_name"], "멜콘")
        self.assertEqual(rows[0]["market"], "KOSDAQ")
        self.assertEqual(rows[0]["progress_container"], "subscriptionList")
        self.assertNotIn("expected_listing_date", rows[0])

    def test_valid_listing_date_is_retained_and_invalid_date_is_field_local(self):
        rows = parse_naver_ipo_discovery_json({
            "subscriptionList": [
                {"ipoCode": "A468670", "compName": "브릴스", "lcalDate": "2026-10-01"},
                {"ipoCode": "A123456", "compName": "진코스텍", "lcalDate": "2026-02-30"},
            ]
        })
        by_code = {row["stock_code"]: row for row in rows}
        self.assertEqual(by_code["468670"]["expected_listing_date"], "2026-10-01")
        self.assertNotIn("expected_listing_date", by_code["123456"])

    def test_same_stock_across_progress_lists_is_one_record(self):
        rows = parse_naver_ipo_discovery_json({
            "subscriptionList": [{"ipoCode": "A179880", "compName": "멜콘", "lcalDate": ""}],
            "listingList": [{"ipoCode": "A179880", "compName": "멜콘", "lcalDate": "2026-10-15"}],
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["expected_listing_date"], "2026-10-15")
        self.assertEqual(rows[0]["progress_container"], "listingList")


if __name__ == "__main__":
    unittest.main()
