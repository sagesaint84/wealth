from __future__ import annotations
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from app.main import app
import app.main as main
from app.services.tax import FamilyFinancialIncomeAllocationError

class FamilyFinancialIncomeAllocationApiTests(unittest.TestCase):
    def setUp(self):
        self.client=TestClient(app); self.user=patch("app.services.user_manager.get_user_by_name",return_value={"username":"alice","id":"user-alice","role":"user"}); self.user.start(); self.addCleanup(self.user.stop); self.client.cookies.set(main.COOKIE_NAME,main._serializer.dumps({"user":"alice"}))
    def test_authenticated_scope_and_no_store(self):
        with patch("app.services.tax.get_family_financial_income_allocation_simulation_for_user",new=AsyncMock(return_value={"members":[]})) as service: response=self.client.post("/api/dividends/financial-income-family-allocation-simulation",json={"allocations":[]})
        self.assertEqual(response.status_code,200); self.assertEqual(response.headers.get("cache-control"),"no-store"); service.assert_awaited_once_with("alice",allocations=[])
    def test_invalid_shape_and_service_error_and_401(self):
        for payload in ({},{"allocations":[],"username":"bob"},{"allocations":{}}):
            self.assertEqual(self.client.post("/api/dividends/financial-income-family-allocation-simulation",json=payload).status_code,400)
        with patch("app.services.tax.get_family_financial_income_allocation_simulation_for_user",new=AsyncMock(side_effect=FamilyFinancialIncomeAllocationError("FAMILY_ALLOCATION_OWNER_INVALID"))): response=self.client.post("/api/dividends/financial-income-family-allocation-simulation",json={"allocations":[]})
        self.assertEqual(response.json()["detail"]["code"],"FAMILY_ALLOCATION_OWNER_INVALID"); self.client.cookies.clear(); self.assertEqual(self.client.post("/api/dividends/financial-income-family-allocation-simulation",json={"allocations":[]}).status_code,401)
