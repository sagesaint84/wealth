from __future__ import annotations
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import app.main as main
from app.main import app
from tests.test_financial_income_article62_comparison import payload, payload_with_prepaid

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
        self.assertIn("prepaid_financial_income_withholding_tax_total_krw", body)
        self.assertIn("partial_national_income_tax_balance_after_explicit_financial_withholding_krw", body)
        self.assertTrue(body["data_quality"]["dividend_tax_credit_calculated"])
        self.assertFalse(body["data_quality"]["withholding_tax_paid_credit_calculated"])
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

    def test_explicit_prepaid_financial_withholding_is_additive_api_input(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload_with_prepaid(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_income_withholding_tax_krw=4_200_000,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(body["prepaid_financial_income_withholding_tax_total_krw"], 4_200_000)
        self.assertEqual(
            body["partial_national_income_tax_balance_after_explicit_financial_withholding_krw"],
            0,
        )
        self.assertTrue(body["data_quality"]["withholding_tax_paid_credit_calculated"])
        self.assertTrue(body["data_quality"]["local_income_tax_withholding_excluded"])
        self.assertFalse(body["data_quality"]["final_payment_or_refund_calculated"])

    def test_prepaid_financial_withholding_rejects_partial_or_local_tax_inputs(self):
        partial = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload(
                ordinary_interest_14_krw=30_000_000,
                prepaid_interest_income_withholding_tax_krw=4_200_000,
            ),
        )
        self.assertEqual(partial.status_code, 400)
        self.assertEqual(partial.headers.get("cache-control"), "no-store")

        local_tax = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json={
                **payload_with_prepaid(ordinary_interest_14_krw=30_000_000),
                "prepaid_local_income_tax_krw": 420_000,
            },
        )
        self.assertEqual(local_tax.status_code, 400)
        self.assertEqual(local_tax.headers.get("cache-control"), "no-store")

    def test_prepaid_financial_withholding_rejects_below_threshold_readdition(self):
        response = self.client.post(
            "/api/dividends/financial-income-article62-comparison",
            json=payload_with_prepaid(
                ordinary_interest_14_krw=20_000_000,
                prepaid_interest_income_withholding_tax_krw=2_800_000,
            ),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(
            response.json()["detail"]["code"],
            "ARTICLE62_PREPAID_WITHHOLDING_BELOW_THRESHOLD_INVALID",
        )
