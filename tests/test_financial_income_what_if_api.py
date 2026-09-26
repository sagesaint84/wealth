from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
import app.main as main
from app.services.tax import FinancialIncomeWhatIfError


class FinancialIncomeWhatIfApiTests(unittest.TestCase):
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

    def test_what_if_uses_authenticated_user_and_no_store(self):
        payload = {
            "owner": "아빠",
            "what_if": {"scenario_projected_gross_screening_income_krw": 21_000_000},
            "investment_comparison": None,
        }
        scenario = {
            "asset_type": "us_direct",
            "annual_distribution_krw": 3_000_000,
            "annual_realized_gain_krw": 5_000_000,
        }
        with patch(
            "app.services.tax.get_financial_income_what_if_for_user",
            new=AsyncMock(return_value=payload),
        ) as service:
            response = self.client.post(
                "/api/dividends/financial-income-what-if",
                json={
                    "owner": "아빠",
                    "additional_dividend_gross_krw": 1_000_000,
                    "additional_interest_gross_krw": 500_000,
                    "investment_scenario": scenario,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        service.assert_awaited_once_with(
            "alice",
            owner="아빠",
            expected_remaining_interest_gross_krw=0.0,
            current_month_remaining_dividend_gross_krw=0.0,
            additional_dividend_gross_krw=1_000_000,
            additional_interest_gross_krw=500_000,
            investment_scenario=scenario,
        )

    def test_defaults_are_stateless(self):
        with patch(
            "app.services.tax.get_financial_income_what_if_for_user",
            new=AsyncMock(return_value={"owner": "모두"}),
        ) as service:
            response = self.client.post(
                "/api/dividends/financial-income-what-if",
                json={},
            )

        self.assertEqual(response.status_code, 200)
        service.assert_awaited_once_with(
            "alice",
            owner="모두",
            expected_remaining_interest_gross_krw=0.0,
            current_month_remaining_dividend_gross_krw=0.0,
            additional_dividend_gross_krw=0.0,
            additional_interest_gross_krw=0.0,
            investment_scenario=None,
        )

    def test_username_and_unknown_top_level_fields_are_rejected(self):
        for body in ({"username": "bob"}, {"save": True}):
            with self.subTest(body=body):
                response = self.client.post(
                    "/api/dividends/financial-income-what-if", json=body
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID",
                )

    def test_unknown_investment_fields_are_rejected(self):
        response = self.client.post(
            "/api/dividends/financial-income-what-if",
            json={
                "investment_scenario": {
                    "asset_type": "us_direct",
                    "existing_personal_financial_income_krw": 1,
                }
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID",
        )

    def test_blank_owner_is_rejected(self):
        response = self.client.post(
            "/api/dividends/financial-income-what-if",
            json={"owner": "   "},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "FINANCIAL_INCOME_OWNER_INVALID",
        )

    def test_service_error_maps_to_stable_400(self):
        with patch(
            "app.services.tax.get_financial_income_what_if_for_user",
            new=AsyncMock(
                side_effect=FinancialIncomeWhatIfError(
                    "FINANCIAL_INCOME_WHAT_IF_DIVIDEND_INVALID"
                )
            ),
        ):
            response = self.client.post(
                "/api/dividends/financial-income-what-if",
                json={"additional_dividend_gross_krw": -1},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "FINANCIAL_INCOME_WHAT_IF_DIVIDEND_INVALID",
        )
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_non_object_json_and_investment_scenario_are_rejected(self):
        for body in ([], {"investment_scenario": []}):
            with self.subTest(body=body):
                response = self.client.post(
                    "/api/dividends/financial-income-what-if", json=body
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID",
                )

    def test_unauthenticated_request_is_existing_401(self):
        self.client.cookies.clear()
        response = self.client.post(
            "/api/dividends/financial-income-what-if", json={}
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
