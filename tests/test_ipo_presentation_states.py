from datetime import date
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from app.services.ipo.presentation import (
    _read_portfolio_for_presentation,
    derive_filter_group,
    derive_market_state,
    derive_user_state,
    present_market_store,
)


class IpoPresentationStateTests(unittest.TestCase):
    def ipo(self, **extra):
        return {"ipo_id": "ipo", "subscription_start": "2026-09-10", "subscription_end": "2026-09-11",
                "expected_listing_date": "2026-09-20", **extra}

    def test_market_states_are_kst_date_injectable_and_endpoint_inclusive(self):
        ipo = self.ipo()
        self.assertEqual(derive_market_state(ipo, date(2026, 9, 9)), "UPCOMING")
        self.assertEqual(derive_market_state(ipo, date(2026, 9, 10)), "SUBSCRIPTION_OPEN")
        self.assertEqual(derive_market_state(ipo, date(2026, 9, 11)), "SUBSCRIPTION_OPEN")
        self.assertEqual(derive_market_state(ipo, date(2026, 9, 12)), "LISTING_UPCOMING")
        self.assertEqual(derive_market_state(ipo, date(2026, 9, 20)), "LISTED")

    def test_market_unknown_dates_fail_safe(self):
        self.assertEqual(derive_market_state(self.ipo(subscription_start="bad"), date(2026, 9, 1)), "DATE_UNKNOWN")
        self.assertEqual(derive_market_state(self.ipo(subscription_end="2026-09-01"), date(2026, 9, 1)), "DATE_UNKNOWN")
        self.assertEqual(derive_market_state(self.ipo(expected_listing_date=None), date(2026, 9, 12)), "SUBSCRIPTION_CLOSED")

    def test_user_position_precedence_and_counts(self):
        pnl = [{"id": "a"}, {"id": "b"}]
        app = {"applied_owners": ["본인", "배우자", "자녀"], "applicants": {
            "본인": {"allocation": {"quantity": 5, "links": [{"pnl_record_id": "a", "matched_quantity": 5}]}},
            "배우자": {"allocation": {"quantity": 5, "links": [{"pnl_record_id": "b", "matched_quantity": 2}]}},
            "자녀": {"allocation": {"quantity": 5, "links": []}},
        }}
        state, counts = derive_user_state(app, pnl)
        self.assertEqual(state, "PARTIALLY_SOLD")
        self.assertEqual((counts["fully_sold"], counts["partially_sold"], counts["unsold"]), (1, 1, 1))
        app["applicants"]["자녀"]["allocation"]["links"] = [{"pnl_record_id": "missing", "matched_quantity": 1}]
        self.assertEqual(derive_user_state(app, pnl)[0], "LINK_DATA_MISSING")

    def test_filter_group_keeps_remaining_position_active_and_returns_past_after_unlink_rederive(self):
        self.assertEqual(derive_filter_group("LISTED", "ALLOCATED_UNSOLD"), "ACTIVE")
        self.assertEqual(derive_filter_group("LISTED", "PARTIALLY_SOLD"), "ACTIVE")
        self.assertEqual(derive_filter_group("UPCOMING", "NOT_APPLIED"), "UPCOMING")
        self.assertEqual(derive_filter_group("LISTED", "FULLY_SOLD"), "PAST")
        self.assertEqual(derive_filter_group("DATE_UNKNOWN", "NOT_APPLIED"), "UNKNOWN")

    def test_presentation_is_read_only_and_attaches_authoritative_state(self):
        market = {"ipos": [self.ipo()]}
        data = {"settings": {"ipo": {"applications": {"ipo": {"applied_owners": ["본인"], "applicants": {"본인": {"allocation": {"quantity": 5, "links": []}}}}}}}}
        with patch("app.services.ipo.presentation._read_portfolio_for_presentation", return_value=data), \
             patch("app.services.ipo.presentation.read_pnl_records_readonly", return_value=[]):
            output = present_market_store("test", market, date(2026, 9, 12))
        self.assertNotIn("market_state", market["ipos"][0])
        item = output["ipos"][0]
        self.assertEqual((item["market_state"], item["user_state"], item["filter_group"]), ("LISTING_UPCOMING", "ALLOCATED_UNSOLD", "ACTIVE"))

    def test_frontend_uses_backend_states_for_filtering(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "static" / "wealth-ipo.js").read_text(encoding="utf-8")
        self.assertIn("ipo.filter_group", source)
        self.assertIn("ipo.market_state", source)
        self.assertIn("ipo.user_state", source)
        self.assertIn("전체", source)
        self.assertIn("예정", source)
        self.assertIn("진행", source)
        self.assertIn("과거", source)

    def test_presentation_read_does_not_create_missing_portfolio(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "portfolio.json"
            with patch("app.services.ipo.presentation.portfolio._get_portfolio_file", return_value=missing):
                self.assertEqual(_read_portfolio_for_presentation("missing"), {})
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
