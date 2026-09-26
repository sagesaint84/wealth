from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
import app.main as main
from app.services.tax import FamilyFinancialIncomeRiskError


class FamilyFinancialIncomeRiskApiTests(unittest.TestCase):
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

    def test_family_risk_uses_authenticated_user_and_no_store(self):
        payload = {
            "configured_members": ["아빠", "엄마"],
            "members": [],
            "family_reference": {"reference_only": True},
        }
        with patch(
            "app.services.tax.get_family_financial_income_risk_for_user",
            new=AsyncMock(return_value=payload),
        ) as service:
            response = self.client.get(
                "/api/dividends/financial-income-family-risk"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        service.assert_awaited_once_with("alice")

    def test_service_error_maps_to_stable_400(self):
        with patch(
            "app.services.tax.get_family_financial_income_risk_for_user",
            new=AsyncMock(
                side_effect=FamilyFinancialIncomeRiskError(
                    "FAMILY_FINANCIAL_INCOME_PORTFOLIO_INVALID"
                )
            ),
        ):
            response = self.client.get(
                "/api/dividends/financial-income-family-risk"
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "FAMILY_FINANCIAL_INCOME_PORTFOLIO_INVALID",
        )
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_unauthenticated_request_is_existing_401(self):
        self.client.cookies.clear()
        response = self.client.get(
            "/api/dividends/financial-income-family-risk"
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
