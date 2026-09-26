from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "app" / "static" / "index.html"
MONEY_JS = ROOT / "app" / "static" / "wealth-money-input.js"


class MoneyInputUxStaticTests(unittest.TestCase):
    def test_index_loads_money_input_module_after_core_wealth_js(self):
        html = INDEX.read_text(encoding="utf-8")
        core = '/static/wealth.js?v=1.3.0'
        money = '/static/wealth-money-input.js?v=1.3.0'
        self.assertIn(core, html)
        self.assertIn(money, html)
        self.assertLess(html.index(core), html.index(money))

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
