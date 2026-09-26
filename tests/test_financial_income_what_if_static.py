from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FinancialIncomeWhatIfStaticTests(unittest.TestCase):
    def test_index_loads_what_if_assets_after_core_wealth_script(self):
        html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        css_ref = '/static/wealth-financial-income-what-if.css?v=1.3.0'
        core_js = '/static/wealth.js?v=1.3.0'
        what_if_js = '/static/wealth-financial-income-what-if.js?v=1.3.0'
        self.assertIn(css_ref, html)
        self.assertIn(core_js, html)
        self.assertIn(what_if_js, html)
        self.assertLess(html.index(core_js), html.index(what_if_js))

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

    def test_watch_threshold_state_is_server_driven(self):
        js = (ROOT / "app" / "static" / "wealth-financial-income-what-if.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("watchState.at_or_above === true", js)
        self.assertNotIn("10_000_000", js)


if __name__ == "__main__":
    unittest.main()
