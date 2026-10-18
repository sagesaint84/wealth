from __future__ import annotations

import unittest
from pathlib import Path
from html.parser import HTMLParser


ROOT = Path(__file__).resolve().parents[1]


class FinancialIncomeWhatIfStaticTests(unittest.TestCase):
    def test_index_loads_what_if_assets_after_core_wealth_script(self):
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
        css_ref = '/static/wealth-financial-income-what-if.css?v=2.1.0-b2'
        self.assertEqual(len(assets.revisions), 1)
        revision = assets.revisions[0]
        # Core asset revision is independent of the app release version.
        self.assertEqual(revision, '2.1.1-r1')
        core_js = f'/static/wealth.js?v={revision}'
        what_if_js = '/static/wealth-financial-income-what-if.js?v=2.1.0-b2'
        self.assertIn(css_ref, html)
        self.assertIn(core_js, html)
        self.assertIn(what_if_js, html)
        self.assertLess(html.index(core_js), html.index(what_if_js))
        for script in (core_js, what_if_js):
            self.assertEqual(assets.scripts.count(script), 1)
            self.assertEqual(sum(src.split('?', 1)[0] == script.split('?', 1)[0] for src in assets.scripts), 1)
            self.assertTrue((ROOT / 'app/static' / script.split('?', 1)[0].rsplit('/', 1)[1]).is_file())
        self.assertLess(assets.scripts.index(core_js), assets.scripts.index(what_if_js))
        self.assertEqual(assets.stylesheets.count(css_ref), 1)
        self.assertTrue((ROOT / 'app/static/wealth-financial-income-what-if.css').is_file())

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
