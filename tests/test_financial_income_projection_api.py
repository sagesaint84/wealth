from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
import app.main as main
from app.services.tax import FinancialIncomeProjectionError


class FinancialIncomeProjectionApiTests(unittest.TestCase):
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

    def test_stateless_simulation_uses_authenticated_user_and_no_store(self):
        projected = {
            "year": 2026,
            "owner": "아빠",
            "projected_gross_screening_income_krw": 12_345_678,
        }
        with patch(
            "app.services.tax.get_financial_income_projection_for_user",
            new=AsyncMock(return_value=projected),
        ) as service:
            response = self.client.post(
                "/api/dividends/financial-income-simulation",
                json={
                    "owner": "아빠",
                    "expected_remaining_interest_gross_krw": 200_000,
                    "current_month_remaining_dividend_gross_krw": 300_000,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), projected)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        service.assert_awaited_once_with(
            "alice",
            owner="아빠",
            expected_remaining_interest_gross_krw=200_000,
            current_month_remaining_dividend_gross_krw=300_000,
        )

    def test_defaults_are_forwarded_without_persistence_fields(self):
        with patch(
            "app.services.tax.get_financial_income_projection_for_user",
            new=AsyncMock(return_value={"year": 2026, "owner": "모두"}),
        ) as service:
            response = self.client.post(
                "/api/dividends/financial-income-simulation",
                json={},
            )

        self.assertEqual(response.status_code, 200)
        service.assert_awaited_once_with(
            "alice",
            owner="모두",
            expected_remaining_interest_gross_krw=0.0,
            current_month_remaining_dividend_gross_krw=0.0,
        )

    def test_client_cannot_supply_username_or_unknown_fields(self):
        with patch(
            "app.services.tax.get_financial_income_projection_for_user",
            new=AsyncMock(),
        ) as service:
            response = self.client.post(
                "/api/dividends/financial-income-simulation",
                json={"username": "bob"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "FINANCIAL_INCOME_REQUEST_INVALID",
        )
        service.assert_not_awaited()

    def test_blank_or_non_string_owner_is_rejected(self):
        for owner in ("", "   ", 123, None):
            with self.subTest(owner=owner):
                response = self.client.post(
                    "/api/dividends/financial-income-simulation",
                    json={"owner": owner},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "FINANCIAL_INCOME_OWNER_INVALID",
                )

    def test_service_validation_error_maps_to_stable_400_code(self):
        with patch(
            "app.services.tax.get_financial_income_projection_for_user",
            new=AsyncMock(
                side_effect=FinancialIncomeProjectionError(
                    "FINANCIAL_INCOME_EXPECTED_INTEREST_INVALID"
                )
            ),
        ):
            response = self.client.post(
                "/api/dividends/financial-income-simulation",
                json={"expected_remaining_interest_gross_krw": -1},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "FINANCIAL_INCOME_EXPECTED_INTEREST_INVALID",
        )
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_unauthenticated_request_is_existing_401(self):
        self.client.cookies.clear()
        response = self.client.post(
            "/api/dividends/financial-income-simulation",
            json={},
        )
        self.assertEqual(response.status_code, 401)

    def test_non_object_json_is_rejected(self):
        response = self.client.post(
            "/api/dividends/financial-income-simulation",
            json=[],
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "FINANCIAL_INCOME_REQUEST_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
