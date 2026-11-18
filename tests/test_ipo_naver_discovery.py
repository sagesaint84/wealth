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

    def test_complementary_dates_and_listing_metadata_are_order_independent(self):
        subscription = {"ipoCode": "A179880", "compName": "(주) 멜콘",
                        "poStartDate": "2026-10-01", "poEndDate": "2026-10-02", "lcalDate": "bad"}
        listing = {"ipoCode": "179880", "compName": "멜콘", "lcalDate": "2026-10-15"}
        forward = parse_naver_ipo_discovery_json({"subscriptionList": [subscription], "listingList": [listing]})
        reverse = parse_naver_ipo_discovery_json({"listingList": [listing], "subscriptionList": [subscription]})
        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward), 1)
        row = forward[0]
        self.assertEqual(row["subscription_start"], "2026-10-01")
        self.assertEqual(row["subscription_end"], "2026-10-02")
        self.assertEqual(row["expected_listing_date"], "2026-10-15")
        self.assertEqual(row["progress_container"], "listingList")
        source = row["sources"]["npay"]
        self.assertEqual(source["container"], "listingList")
        self.assertEqual(source["field_paths"]["subscription_start"], "poStartDate")
        self.assertEqual(source["field_containers"]["subscription_start"], "subscriptionList")
        self.assertEqual(source["field_containers"]["expected_listing_date"], "listingList")

    def test_conflicting_dates_and_names_are_not_merged(self):
        base = {"ipoCode": "A179880", "compName": "멜콘", "poStartDate": "2026-10-01",
                "poEndDate": "2026-10-02", "lcalDate": "2026-10-15"}
        for change in ({"poStartDate": "2026-11-01"}, {"poEndDate": "2026-10-03"},
                       {"lcalDate": "2026-11-15"}, {"compName": "다른회사"}):
            with self.subTest(change=change):
                rows = parse_naver_ipo_discovery_json({"subscriptionList": [base],
                                                       "listingList": [{**base, **change}]})
                self.assertEqual(len(rows), 2)

    def test_ambiguous_missing_date_does_not_choose_an_offering(self):
        incomplete = {"ipoCode": "A179880", "compName": "멜콘", "lcalDate": ""}
        first = {**incomplete, "lcalDate": "2026-10-15"}
        second = {**incomplete, "lcalDate": "2026-11-15"}
        forward = parse_naver_ipo_discovery_json({"subscriptionList": [incomplete], "listingList": [first, second]})
        reverse = parse_naver_ipo_discovery_json({"listingList": [second, first], "subscriptionList": [incomplete]})
        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward), 3)
        self.assertEqual(sum("expected_listing_date" not in row for row in forward), 1)


if __name__ == "__main__":
    unittest.main()
