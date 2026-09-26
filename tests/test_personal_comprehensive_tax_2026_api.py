from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.main as main
from app.main import app


class PersonalComprehensiveTax2026ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user = patch(
            "app.services.user_manager.get_user_by_name",
            return_value={"username": "alice", "id": "user-alice", "role": "user"},
        )
        self.user.start()
        self.addCleanup(self.user.stop)
        self.client.cookies.set(
            main.COOKIE_NAME,
            main._serializer.dumps({"user": "alice"}),
        )

    def test_authenticated_request_is_stateless_and_no_store(self):
        response = self.client.post(
            "/api/dividends/financial-income-personal-comprehensive-tax",
            json={
                "tax_base_before_financial_income_krw": 14_000_000,
                "financial_income_gross_krw": 36_000_000,
                "assumed_financial_income_included_in_tax_base_krw": 36_000_000,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        body = response.json()
        self.assertEqual(body["tax_base_after_krw"], 50_000_000)
        self.assertTrue(body["data_quality"]["stateless"])

    def test_rejects_unknown_fields_and_invalid_body(self):
        for payload in (
            {"username": "bob"},
            {"tax_base_before_financial_income_krw": 1},
            [],
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/dividends/financial-income-personal-comprehensive-tax",
                    json=payload,
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "PERSONAL_COMPREHENSIVE_TAX_REQUEST_INVALID",
                )
                self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_unsafe_amount_maps_to_stable_400(self):
        response = self.client.post(
            "/api/dividends/financial-income-personal-comprehensive-tax",
            json={
                "tax_base_before_financial_income_krw": -1,
                "financial_income_gross_krw": 1,
                "assumed_financial_income_included_in_tax_base_krw": 0,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "PERSONAL_COMPREHENSIVE_TAX_BASE_INVALID",
        )

    def test_unauthenticated_request_is_401(self):
        self.client.cookies.clear()
        response = self.client.post(
            "/api/dividends/financial-income-personal-comprehensive-tax",
            json={
                "tax_base_before_financial_income_krw": 0,
                "financial_income_gross_krw": 0,
                "assumed_financial_income_included_in_tax_base_krw": 0,
            },
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
