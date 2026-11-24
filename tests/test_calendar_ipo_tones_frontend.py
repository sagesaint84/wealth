from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]
LOADER_JS = ROOT / "app" / "static" / "wealth-family-financial-income-allocation.js"
CALENDAR_JS = ROOT / "app" / "static" / "wealth-calendar.js"
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"
INDEX_HTML = ROOT / "app" / "static" / "index.html"


class CalendarIpoToneFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.loader_js = LOADER_JS.read_text(encoding="utf-8")
        cls.calendar_js = CALENDAR_JS.read_text(encoding="utf-8")
        cls.layout_css = LAYOUT_CSS.read_text(encoding="utf-8")
        cls.index_html = INDEX_HTML.read_text(encoding="utf-8")

    def test_calendar_keeps_distinct_subscription_and_listing_tone_classes(self) -> None:
        self.assertIn("tone-ipo-subscription", self.calendar_js)
        self.assertIn("tone-ipo-listing", self.calendar_js)
        self.assertIn("🎯", self.calendar_js)
        self.assertIn("🚀", self.calendar_js)

    def test_ipo_tones_share_purple_family_but_use_distinct_values(self) -> None:
        self.assertIn("--calendar-subscription-bg: rgba(79, 70, 229, 0.20)", self.layout_css)
        self.assertIn("--calendar-subscription-fg: #A5B4FC", self.layout_css)
        self.assertIn("--calendar-listing-bg: rgba(168, 85, 247, 0.20)", self.layout_css)
        self.assertIn("--calendar-listing-fg: #D8B4FE", self.layout_css)
        self.assertNotIn("--calendar-subscription-fg: #69F0AE", self.layout_css)
        self.assertNotIn("--calendar-subscription-bg: rgba(105, 240, 174", self.layout_css)
        self.assertIn("--calendar-profit-fg: #f87171", self.layout_css)
        self.assertIn("--calendar-loss-fg: #448AFF", self.layout_css)
        self.assertNotEqual("#A5B4FC", "#D8B4FE")

    def test_final_tones_are_in_first_paint_stylesheet(self) -> None:
        self.assertNotIn("wealthCalendarIpoTonesScript", self.loader_js)
        class Assets(HTMLParser):
            def __init__(self):
                super().__init__()
                self.scripts = []
                self.stylesheets = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "script":
                    self.scripts.append(attrs.get("src", "").split("?", 1)[0])
                if tag == "link" and attrs.get("rel") == "stylesheet":
                    self.stylesheets.append(attrs.get("href", "").split("?", 1)[0])

        assets = Assets()
        assets.feed(self.index_html)
        self.assertEqual(assets.stylesheets.count("/static/wealth-layout.css"), 1)
        self.assertEqual(assets.scripts.count("/static/wealth-family-financial-income-allocation.js"), 1)
        self.assertNotIn("/static/wealth-calendar-ipo-tones.js", assets.scripts)
        self.assertIn(".cal-badge.tone-ipo-subscription", self.layout_css)
        self.assertIn(".calendar-legend-item.tone-ipo-subscription", self.layout_css)


if __name__ == "__main__":
    unittest.main()
