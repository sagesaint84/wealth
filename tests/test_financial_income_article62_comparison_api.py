from __future__ import annotations
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import app.main as main
from app.main import app
from tests.test_financial_income_article62_comparison import payload

class Article62ComparisonApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user = patch("app.services.user_manager.get_user_by_name", return_value={"username":"alice","role":"user"})
        self.user.start(); self.addCleanup(self.user.stop)
        self.client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({"user":"alice"}))
    def test_authenticated_no_store_and_unauthenticated(self):
        response = self.client.post("/api/dividends/financial-income-article62-comparison", json=payload())
        self.assertEqual(response.status_code, 200); self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertIn("dividend_tax_credit_krw", body)
        self.assertIn("dividend_tax_credit_limit_krw", body)
        self.assertIn("article62_tax_after_dividend_credit_before_other_credits_krw", body)
        self.assertTrue(body["data_quality"]["dividend_tax_credit_calculated"])
        self.assertFalse(body["data_quality"]["legal_tax_determination"])
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/api/dividends/financial-income-article62-comparison", json=payload()).status_code, 401)
    def test_unknown_field_rejected(self):
        response = self.client.post("/api/dividends/financial-income-article62-comparison", json={**payload(), "username":"bob"})
        self.assertEqual(response.status_code, 400); self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_renamed_input_fields_are_required_at_the_api_boundary(self):
        accepted = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload(
                other_comprehensive_income_excluding_partnership_dividend_krw=1_000_000,
                online_investment_linked_nonbusiness_loan_interest_14_krw=1_000_000,
            ),
        )
        self.assertEqual(accepted.status_code, 200)
        for old_field in (
            "other_comprehensive_income_krw",
            "nonbusiness_loan_interest_14_krw",
        ):
            with self.subTest(old_field=old_field):
                response = self.client.post(
                    "/api/dividends/financial-income-article62-comparison",
                    json={**payload(), old_field: 0},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_dividend_tax_credit_response_uses_official_comparison_ceiling(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload(
                ordinary_interest_14_krw=10_000_000,
                gross_up_eligible_dividend_krw=15_000_000,
                other_comprehensive_income_excluding_partnership_dividend_krw=13_000_000,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(body["dividend_gross_up_amount_krw"], 500_000)
        self.assertEqual(body["dividend_tax_credit_limit_krw"], 35_000)
        self.assertEqual(body["dividend_tax_credit_krw"], 35_000)
        self.assertEqual(
            body["article62_tax_after_dividend_credit_before_other_credits_krw"],
            4_280_000,
        )
