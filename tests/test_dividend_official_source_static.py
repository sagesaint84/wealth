from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DividendOfficialSourceStaticTests(unittest.TestCase):
    def test_index_loads_source_ui_after_core_wealth_js(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        core = '/static/wealth.js?v=1.3.0'
        source = '/static/wealth-dividend-source.js?v=1.3.0'
        self.assertIn(core, html)
        self.assertIn(source, html)
        self.assertLess(html.index(core), html.index(source))

    def test_source_ui_mentions_official_and_fallback_states(self):
        js = (ROOT / "app" / "static" / "wealth-dividend-source.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("OpenDART", js)
        self.assertIn("KIND", js)
        self.assertIn("missing_api_key", js)
        self.assertIn("confirmed_amount", js)
        self.assertIn("naver", js)
        self.assertIn("yahoo_history", js)

    def test_web_finance_wrapper_preserves_legacy_on_official_failure(self):
        source = (ROOT / "app" / "services" / "web_finance.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_legacy_get_web_dividend_summary", source)
        self.assertIn("official_enrichment_failed", source)
        self.assertIn("legacy_forecast_preserved", source)


if __name__ == "__main__":
    unittest.main()
