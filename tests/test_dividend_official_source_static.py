from __future__ import annotations

from pathlib import Path
from html.parser import HTMLParser
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DividendOfficialSourceStaticTests(unittest.TestCase):
    def test_index_loads_source_ui_after_core_wealth_js(self):
        from urllib.parse import urlsplit

        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        class AssetParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.versions, self.scripts = [], []
                self.revisions = []

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if tag == 'meta' and attributes.get('name') == 'application-version':
                    self.versions.append(attributes.get('content'))
                if tag == 'meta' and attributes.get('name') == 'application-assets-revision':
                    self.revisions.append(attributes.get('content'))
                if tag == 'script' and attributes.get('src'):
                    self.scripts.append(attributes['src'])

        assets = AssetParser()
        assets.feed(html)
        self.assertEqual(len(assets.versions), 1)
        version = assets.versions[0]
        self.assertIsInstance(version, str)
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        self.assertEqual(len(assets.revisions), 1)
        revision = assets.revisions[0]
        self.assertIsInstance(revision, str)
        self.assertRegex(revision, r'^[0-9]+(?:\.[0-9]+)+(?:[-A-Za-z0-9._]*)$')
        scripts = [urlsplit(src).path for src in assets.scripts]
        layout = '/static/wealth-layout.js'
        core = '/static/wealth.js'
        source = '/static/wealth-dividend-source.js'
        for script in (layout, core, source):
            self.assertEqual(scripts.count(script), 1, script)
            self.assertTrue((ROOT / 'app' / 'static' / script.removeprefix('/static/')).is_file(), script)
        self.assertLess(scripts.index(core), scripts.index(source))

    def test_source_ui_mentions_official_and_fallback_states(self):
        js = (ROOT / "app" / "static" / "wealth-dividend-source.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("OpenDART", js)
        self.assertIn("KIND", js)
        self.assertIn("missing_api_key", js)
        self.assertIn("confirmed_amount", js)
        self.assertIn("opendart_confirmed_disclosure", js)
        self.assertIn("confirmed_numeric_override", js)
        self.assertIn("지급예정일", js)
        self.assertIn("naver", js)
        self.assertIn("yahoo_history", js)

    def test_web_finance_wrapper_preserves_legacy_on_official_failure(self):
        source = (ROOT / "app" / "services" / "web_finance.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("_legacy_get_web_dividend_summary", source)
        self.assertIn("official_enrichment_failed", source)
        self.assertIn("legacy_forecast_preserved", source)


    def test_kind_etf_official_overlay_is_wired(self):
        web = (ROOT / "app" / "services" / "web_finance.py").read_text(encoding="utf-8")
        official = (ROOT / "app" / "services" / "dividend_official_sources.py").read_text(
            encoding="utf-8"
        )
        ui = (ROOT / "app" / "static" / "wealth-dividend-source.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('"is_etf": is_etf', web)
        self.assertIn('"is_etf": bool(d_info.get("is_etf"))', web)
        self.assertIn("enrich_dividend_summary_with_kind_etf_distributions", official)
        self.assertIn("kind_etf_confirmed_overlay", ui)
        self.assertIn("kind_etf_numeric_override_count", ui)



if __name__ == "__main__":
    unittest.main()
