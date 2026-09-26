from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
import app.main as main


class FinancialIncomeTradingWhatIfApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        user = patch(
            "app.services.user_manager.get_user_by_name",
            return_value={"username": "alice", "id": "user-alice", "role": "user"},
        )
        user.start()
        self.addCleanup(user.stop)
        self.client.cookies.set(
            main.COOKIE_NAME,
            main._serializer.dumps({"user": "alice"}),
        )

    def test_trading_inputs_are_forwarded_when_supplied(self):
        payload = {"owner": "엄마", "what_if": {}}
        with patch(
            "app.services.tax.get_financial_income_what_if_for_user",
            new=AsyncMock(return_value=payload),
        ) as service:
            response = self.client.post(
                "/api/dividends/financial-income-what-if",
                json={
                    "owner": "엄마",
                    "additional_foreign_share_realized_gain_krw": 4_000_000,
                    "additional_kr_listed_overseas_etf_taxable_gain_krw": 1_200_000,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        kwargs = service.call_args.kwargs
        self.assertEqual(kwargs["additional_foreign_share_realized_gain_krw"], 4_000_000)
        self.assertEqual(
            kwargs["additional_kr_listed_overseas_etf_taxable_gain_krw"], 1_200_000
        )

    def test_unknown_trading_field_is_rejected(self):
        response = self.client.post(
            "/api/dividends/financial-income-what-if",
            json={"additional_foreign_share_tax_krw": 1},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID",
        )

    def test_legacy_default_call_contract_is_preserved(self):
        with patch(
            "app.services.tax.get_financial_income_what_if_for_user",
            new=AsyncMock(return_value={"owner": "모두"}),
        ) as service:
            response = self.client.post(
                "/api/dividends/financial-income-what-if",
                json={},
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "additional_foreign_share_realized_gain_krw", service.call_args.kwargs
        )
        self.assertNotIn(
            "additional_kr_listed_overseas_etf_taxable_gain_krw",
            service.call_args.kwargs,
        )


if __name__ == "__main__":
    unittest.main()
