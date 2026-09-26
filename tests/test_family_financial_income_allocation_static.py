from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FamilyFinancialIncomeAllocationStaticTests(unittest.TestCase):
    def test_assets_stateless_ui_and_route(self):
        index = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        js = (
            ROOT / "app/static/wealth-family-financial-income-allocation.js"
        ).read_text(encoding="utf-8")
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")

        self.assertIn("wealth-family-financial-income-allocation", index)
        self.assertIn(
            "/api/dividends/financial-income-family-allocation-simulation", js
        )
        self.assertIn("legal_tax_notice", js)
        self.assertIn("allocatable_future_financial_income_krw", js)
        self.assertIn("배분 가능 미래소득", js)
        self.assertIn("이미 받은 소득의 귀속", js)
        self.assertIn("data-korean-currency", js)
        self.assertNotIn("localStorage", js)
        self.assertNotIn("sessionStorage", js)
        self.assertIn(
            '@app.post("/api/dividends/financial-income-family-allocation-simulation")',
            main,
        )
        self.assertIn('headers={"Cache-Control": "no-store"}', main)


if __name__ == "__main__":
    unittest.main()
