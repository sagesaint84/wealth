from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "app" / "static" / "index.html"
MONEY_JS = ROOT / "app" / "static" / "wealth-money-input.js"


class MoneyInputUxStaticTests(unittest.TestCase):
    def test_index_loads_money_input_module_after_core_wealth_js(self):
        html = INDEX.read_text(encoding="utf-8")

        class AssetParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.versions = []
                self.revisions = []
                self.scripts = []

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
        # Core and the changed import loader have independent cache revisions.
        # Parse actual tags so comments cannot satisfy order.
        self.assertEqual(len(assets.revisions), 1)
        revision = assets.revisions[0]
        # Workspace changed; the unchanged core keeps its own cache revision.
        self.assertEqual(revision, '2.1.2-home1')
        self.assertEqual(assets.scripts.count(f'/static/wealth-layout.js?v={revision}'), 1)
        core = '/static/wealth.js?v=2.1.2-r1'
        money = '/static/wealth-money-input.js?v=2.0.3-ai1'
        self.assertIn(core, html)
        self.assertIn(money, html)
        self.assertLess(html.index(core), html.index(money))
        self.assertEqual(assets.scripts.count(core), 1)
        self.assertEqual(assets.scripts.count(money), 1)
        self.assertLess(assets.scripts.index(core), assets.scripts.index(money))
        self.assertTrue((ROOT / 'app/static/wealth.js').is_file())
        self.assertTrue(MONEY_JS.is_file())

    def test_money_module_preserves_native_number_inputs(self):
        js = MONEY_JS.read_text(encoding="utf-8")
        self.assertIn('input[type="number"]', js)
        self.assertNotIn("input.type = 'text'", js)
        self.assertNotIn('input.type = "text"', js)
        self.assertNotIn("input.value =", js)

    def test_money_module_handles_existing_and_dynamic_krw_fields(self):
        js = MONEY_JS.read_text(encoding="utf-8")
        self.assertIn("data-korean-currency", js)
        self.assertIn("MutationObserver", js)
        for field_id in (
            "divFormAmount",
            "pnlFormAmount",
            "fiWhatIfExtraDividend",
            "fiWhatIfExtraInterest",
            "fiWhatIfCorporateBase",
            "fiWhatIfCorporateExpense",
            "fiWhatIfOwnerDistribution",
        ):
            self.assertIn(field_id, js)

    def test_money_module_excludes_non_currency_numeric_fields(self):
        js = MONEY_JS.read_text(encoding="utf-8")
        for token in (
            "fx[_-]?rate",
            "interest[_-]?rate",
            "ownership",
            "quantity",
            "year",
            "month",
            "duration",
            "day",
        ):
            self.assertIn(token, js)

    def test_money_module_exposes_comma_and_korean_formatters(self):
        js = MONEY_JS.read_text(encoding="utf-8")
        self.assertIn("function formatKrwDigits", js)
        self.assertIn("function formatKoreanAmount", js)
        self.assertIn("krw-money-preview-numeric", js)
        self.assertIn("krw-money-preview-friendly", js)


if __name__ == "__main__":
    unittest.main()
