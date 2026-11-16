from __future__ import annotations

import unittest
from pathlib import Path
from html.parser import HTMLParser


ROOT = Path(__file__).resolve().parents[1]


class FinancialIncomeWhatIfStaticTests(unittest.TestCase):
    def test_index_loads_what_if_assets_after_core_wealth_script(self):
        from urllib.parse import parse_qs, urlsplit

        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        class AssetParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.versions, self.scripts, self.stylesheets = [], [], []
                self.revisions = []

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if tag == 'meta' and attributes.get('name') == 'application-version':
                    self.versions.append(attributes.get('content'))
                if tag == 'meta' and attributes.get('name') == 'application-assets-revision':
                    self.revisions.append(attributes.get('content'))
                if tag == 'script' and attributes.get('src'):
                    self.scripts.append(attributes['src'])
                if tag == 'link' and attributes.get('rel') == 'stylesheet':
                    self.stylesheets.append(attributes.get('href'))

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
        loaded = {}
        for name in ('wealth-layout.js', 'wealth.js', 'wealth-financial-income-what-if.js',
                     'wealth-financial-income-what-if.css'):
            path = '/static/' + name
            urls = assets.stylesheets if name.endswith('.css') else assets.scripts
            matches = [url for url in urls if url and urlsplit(url).path == path]
            self.assertEqual(len(matches), 1, name)
            url = matches[0]
            revisions = parse_qs(urlsplit(url).query, keep_blank_values=True).get('v', [])
            self.assertEqual(len(revisions), 1, url)
            self.assertRegex(revisions[0], r'^[0-9]+(?:\.[0-9]+)+(?:[-A-Za-z0-9._]*)$')
            self.assertTrue((ROOT / 'app' / 'static' / name).is_file(), name)
            loaded[name] = url
        self.assertLess(assets.scripts.index(loaded['wealth.js']),
                        assets.scripts.index(loaded['wealth-financial-income-what-if.js']))

    def test_ui_is_stateless_and_only_targets_estimated_dividend_mode(self):
        js = (ROOT / "app" / "static" / "wealth-financial-income-what-if.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("/api/dividends/financial-income-what-if", js)
        self.assertIn("financialIncomeWhatIfPanel", js)
        self.assertIn("data-div-mode", (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8"))
        self.assertIn("estimatedModeActive", js)
        self.assertNotIn("localStorage", js)
        self.assertNotIn("sessionStorage", js)

    def test_ui_distinguishes_exact_threshold_from_exceeding_it(self):
        js = (ROOT / "app" / "static" / "wealth-financial-income-what-if.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("scenarioState.exceeded === true", js)
        self.assertIn("scenarioState.at_or_above === true", js)
        self.assertIn("2천만원 도달 · 초과 아님", js)
        self.assertIn("2천만원 초과", js)

    def test_completion_and_observers_have_scoped_ownership(self):
        js = (ROOT / 'app/static/wealth-financial-income-what-if.js').read_text(encoding='utf-8')
        self.assertIn('if (revision === simulationRevision && owner === currentOwnerValue()) button.disabled = false;', js)
        self.assertIn('owner !== visibilityOwner', js)
        self.assertNotIn('.observe(document.body', js)
        self.assertIn("attributeFilter: ['class']", js)
        self.assertIn("window.addEventListener('wealth:view', syncVisibility)", js)

    def test_watch_threshold_state_is_server_driven(self):
        js = (ROOT / "app" / "static" / "wealth-financial-income-what-if.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("watchState.at_or_above === true", js)
        self.assertNotIn("10_000_000", js)


if __name__ == "__main__":
    unittest.main()
