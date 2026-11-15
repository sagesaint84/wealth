from __future__ import annotations

import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


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
        # App release metadata and per-file revisions remain separate.
        self.assertEqual(revision, '2.1.3-p0')
        loaded = {}
        for name in ('wealth-layout.js', 'wealth.js', 'wealth-money-input.js'):
            path = '/static/' + name
            matches = [src for src in assets.scripts if urlsplit(src).path == path]
            self.assertEqual(len(matches), 1, name)
            script = matches[0]
            revisions = parse_qs(urlsplit(script).query, keep_blank_values=True).get('v', [])
            self.assertEqual(len(revisions), 1, script)
            self.assertTrue(revisions[0].strip(), script)
            self.assertTrue((ROOT / 'app/static' / name).is_file())
            loaded[name] = script
        self.assertLess(
            assets.scripts.index(loaded['wealth.js']),
            assets.scripts.index(loaded['wealth-money-input.js']),
        )
        for script in loaded.values():
            self.assertEqual(sum(src.split('?', 1)[0] == script.split('?', 1)[0] for src in assets.scripts), 1)
            self.assertTrue((ROOT / 'app/static' / script.split('?', 1)[0].rsplit('/', 1)[1]).is_file())

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
