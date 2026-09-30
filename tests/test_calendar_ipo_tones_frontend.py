from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TONES_JS = ROOT / "app" / "static" / "wealth-calendar-ipo-tones.js"
LOADER_JS = ROOT / "app" / "static" / "wealth-family-financial-income-allocation.js"
CALENDAR_JS = ROOT / "app" / "static" / "wealth-calendar.js"


class CalendarIpoToneFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tones_js = TONES_JS.read_text(encoding="utf-8")
        cls.loader_js = LOADER_JS.read_text(encoding="utf-8")
        cls.calendar_js = CALENDAR_JS.read_text(encoding="utf-8")

    def test_calendar_keeps_distinct_subscription_and_listing_tone_classes(self) -> None:
        self.assertIn("tone-ipo-subscription", self.calendar_js)
        self.assertIn("tone-ipo-listing", self.calendar_js)
        self.assertIn("🎯", self.calendar_js)
        self.assertIn("🚀", self.calendar_js)

    def test_ipo_tones_share_purple_family_but_use_distinct_values(self) -> None:
        self.assertIn("--calendar-subscription-bg: rgba(79, 70, 229, 0.20)", self.tones_js)
        self.assertIn("--calendar-subscription-fg: #A5B4FC", self.tones_js)
        self.assertIn("--calendar-listing-bg: rgba(168, 85, 247, 0.20)", self.tones_js)
        self.assertIn("--calendar-listing-fg: #D8B4FE", self.tones_js)
        self.assertNotEqual("#A5B4FC", "#D8B4FE")

    def test_loader_registers_calendar_tones_once(self) -> None:
        self.assertIn("wealthCalendarIpoTonesScript", self.loader_js)
        self.assertIn("/static/wealth-calendar-ipo-tones.js?v=10.6f1", self.loader_js)


if __name__ == "__main__":
    unittest.main()
