from __future__ import annotations

import unittest

from app.services.ipo.presentation import derive_presentation_months


class IpoCrossMonthPresentationTests(unittest.TestCase):
    def test_subscription_month_and_listing_month_are_both_visible(self):
        ipo = {
            "company_name": "브릴스",
            "subscription_start": "2026-09-17",
            "subscription_end": "2026-09-18",
            "expected_listing_date": "2026-10-01",
        }
        keys, sort_dates = derive_presentation_months(ipo)
        self.assertEqual(keys, ["2026-09", "2026-10"])
        self.assertEqual(sort_dates["2026-09"], "2026-09-17")
        self.assertEqual(sort_dates["2026-10"], "2026-10-01")

    def test_actual_listing_replaces_expected_listing_month(self):
        ipo = {
            "subscription_start": "2026-09-17",
            "subscription_end": "2026-09-18",
            "expected_listing_date": "2026-10-01",
            "actual_listing_date": "2026-11-02",
        }
        keys, _ = derive_presentation_months(ipo)
        self.assertEqual(keys, ["2026-09", "2026-11"])
        self.assertNotIn("2026-10", keys)

    def test_subscription_range_spanning_month_boundary_projects_both_months(self):
        keys, sort_dates = derive_presentation_months({
            "subscription_start": "2026-10-30",
            "subscription_end": "2026-11-02",
        })
        self.assertEqual(keys, ["2026-10", "2026-11"])
        self.assertEqual(sort_dates["2026-10"], "2026-10-30")
        self.assertEqual(sort_dates["2026-11"], "2026-11-01")


if __name__ == "__main__":
    unittest.main()
