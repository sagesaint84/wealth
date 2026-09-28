from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "app" / "static" / "wealth-dividend-source.js"
SOURCE_PATH = ROOT / "app" / "services" / "dividend_official_sources.py"


class PortfolioDividendAfterTaxFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = JS_PATH.read_text(encoding="utf-8")
        cls.source = SOURCE_PATH.read_text(encoding="utf-8")

    def test_forecast_panel_uses_backend_derived_contract(self):
        self.assertIn("portfolio_after_tax", self.js)
        self.assertIn("portfolioAfterTaxDividendPanel", self.js)
        self.assertIn("원천징수·알려진 세금", self.js)
        self.assertIn("after_known_tax_yield_on_market_value_pct", self.js)
        self.assertIn("after_tax_dividend_coverage_pct", self.js)

    def test_partial_coverage_does_not_render_full_portfolio_after_tax_yield(self):
        self.assertIn("calculation_status === 'complete'", self.js)
        self.assertIn("전체 계산 보류", self.js)
        self.assertIn("커버리지가 100%가 아니므로", self.js)
        self.assertIn("unsupported_gross_dividend_krw", self.js)

    def test_cost_basis_copy_matches_backend_contract(self):
        self.assertIn("평균매입가×수량", self.js)
        self.assertIn("현재환율", self.js)
        self.assertIn("현금·예수금은 제외", self.js)

    def test_actual_mode_hides_forecast_only_panel(self):
        self.assertIn("estimatedModeActive", self.js)
        self.assertIn("#dividendModeTabs [data-div-mode]", self.js)
        self.assertIn("panel.hidden = !estimatedModeActive()", self.js)

    def test_frontend_does_not_reimplement_tax_rates(self):
        self.assertNotIn("* 0.154", self.js)
        self.assertNotIn("*0.154", self.js)
        self.assertNotIn("* 0.15", self.js)
        self.assertNotIn("*0.15", self.js)

    def test_final_official_summary_attaches_derived_view_fail_open(self):
        self.assertIn("build_portfolio_after_tax_dividend_summary", self.source)
        self.assertIn('summary["portfolio_after_tax"]', self.source)
        self.assertIn('"portfolio_after_tax_calculation_failed"', self.source)
        kind_pos = self.source.index(
            "enrich_dividend_summary_with_kind_etf_distributions"
        )
        attach_pos = self.source.rindex(
            "_attach_portfolio_after_tax(summary, holdings)"
        )
        self.assertGreater(attach_pos, kind_pos)


if __name__ == "__main__":
    unittest.main()
