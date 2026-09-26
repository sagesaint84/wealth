from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FamilyFinancialIncomeRiskStaticTests(unittest.TestCase):
    def test_index_loads_family_risk_assets(self):
        text = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
        self.assertIn("wealth-family-financial-income-risk.css", text)
        self.assertIn("wealth-family-financial-income-risk.js", text)

    def test_ui_is_family_reference_only_and_individual_thresholds(self):
        text = (
            ROOT / "app/static/wealth-family-financial-income-risk.js"
        ).read_text(encoding="utf-8")
        self.assertIn("/api/dividends/financial-income-family-risk", text)
        self.assertIn("가족 합계에는 2천만원 종합과세 기준을 적용하지 않습니다", text)
        self.assertIn("2천만원 도달 · 초과 아님", text)
        self.assertIn("1천만원 watch", text)
        self.assertNotIn("localStorage", text)
        self.assertNotIn("sessionStorage", text)

    def test_main_exposes_authenticated_family_risk_route(self):
        text = (ROOT / "app/main.py").read_text(encoding="utf-8")
        self.assertIn(
            '@app.get("/api/dividends/financial-income-family-risk")', text
        )
        self.assertIn("get_current_username(request)", text)
        self.assertIn("get_family_financial_income_risk_for_user", text)
        self.assertIn('headers={"Cache-Control": "no-store"}', text)


if __name__ == "__main__":
    unittest.main()
