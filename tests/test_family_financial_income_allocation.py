from __future__ import annotations
import unittest
from unittest.mock import AsyncMock, patch
from app.services.tax.family_financial_income_allocation import FamilyFinancialIncomeAllocationError, build_family_financial_income_allocation_simulation, get_family_financial_income_allocation_simulation_for_user

def member(owner, amount):
    def state(limit):
        return None if amount is None else {"amount_krw": amount, "threshold_krw": limit, "at_or_above": amount >= limit, "exceeded": amount > limit}
    return {"owner": owner, "projected_gross_screening_income_krw": amount, "thresholds": {"watch": {"projected_gross_screening": state(10_000_000)}, "comprehensive_tax": {"projected_gross_screening": state(20_000_000)}}}
def baseline(*rows): return {"year": 2026, "as_of": "2026-09-26", "members": list(rows)}

class FamilyFinancialIncomeAllocationTests(unittest.IsolatedAsyncioTestCase):
    def test_moves_income_recalculates_thresholds_and_preserves_total(self):
        result = build_family_financial_income_allocation_simulation(baseline(member("아빠",25000000),member("엄마",4000000),member("자녀",1000000)), allocations=[{"from_owner":"아빠","to_owner":"엄마","financial_income_gross_krw":5000000},{"from_owner":"아빠","to_owner":"자녀","financial_income_gross_krw":3000000}])
        rows = {row["owner"]:row for row in result["members"]}
        self.assertEqual(rows["아빠"]["after_projected_gross_screening_income_krw"],17000000); self.assertEqual(rows["엄마"]["after_projected_gross_screening_income_krw"],9000000); self.assertEqual(rows["자녀"]["after_projected_gross_screening_income_krw"],4000000)
        self.assertFalse(rows["아빠"]["thresholds"]["comprehensive_tax"]["after"]["at_or_above"]); self.assertEqual(result["family_reference"]["before_projected_gross_screening_income_krw"],30000000); self.assertEqual(result["family_reference"]["after_projected_gross_screening_income_krw"],30000000); self.assertFalse(result["family_reference"]["statutory_threshold_applied"])
    def test_twenty_million_and_invalid_inputs(self):
        result = build_family_financial_income_allocation_simulation(baseline(member("아빠",19000000),member("엄마",1000000)), allocations=[{"from_owner":"엄마","to_owner":"아빠","financial_income_gross_krw":1000000}]); state=result["members"][0]["thresholds"]["comprehensive_tax"]["after"]; self.assertTrue(state["at_or_above"]); self.assertFalse(state["exceeded"])
        base=baseline(member("아빠",1),member("엄마",1))
        for allocations in (None,[{"from_owner":"아빠","to_owner":"엄마","financial_income_gross_krw":-1}],[{"from_owner":"아빠","to_owner":"엄마","financial_income_gross_krw":float("nan")}],[{"from_owner":"아빠","to_owner":"엄마","financial_income_gross_krw":True}],[{"from_owner":"아빠","to_owner":"아빠","financial_income_gross_krw":0}],[{"from_owner":"모두","to_owner":"엄마","financial_income_gross_krw":0}],[{"from_owner":"없는사람","to_owner":"엄마","financial_income_gross_krw":0}]):
            with self.assertRaises(FamilyFinancialIncomeAllocationError): build_family_financial_income_allocation_simulation(base, allocations=allocations)
    def test_excess_and_unavailable_are_not_presented_as_complete(self):
        with self.assertRaisesRegex(FamilyFinancialIncomeAllocationError,"SOURCE_AMOUNT_EXCEEDED"): build_family_financial_income_allocation_simulation(baseline(member("아빠",1),member("엄마",0)),allocations=[{"from_owner":"아빠","to_owner":"엄마","financial_income_gross_krw":2}])
        with self.assertRaisesRegex(FamilyFinancialIncomeAllocationError,"SOURCE_FORECAST_UNAVAILABLE"): build_family_financial_income_allocation_simulation(baseline(member("아빠",None),member("엄마",0)),allocations=[{"from_owner":"아빠","to_owner":"엄마","financial_income_gross_krw":1}])
        result=build_family_financial_income_allocation_simulation(baseline(member("아빠",1),member("엄마",None)),allocations=[]); self.assertIsNone(result["family_reference"]["after_projected_gross_screening_income_krw"]); self.assertIsNone(result["family_reference"]["income_conserved"])
    async def test_user_scope_and_no_persistence(self):
        with patch("app.services.tax.family_financial_income_allocation.get_family_financial_income_risk_for_user",new=AsyncMock(return_value=baseline(member("아빠",1),member("엄마",0)))) as risk: result=await get_family_financial_income_allocation_simulation_for_user("alice",allocations=[])
        risk.assert_awaited_once_with("alice"); self.assertTrue(result["source_context"]["authenticated_user_scoped"]); self.assertFalse(result["source_context"]["persistence_applied"])
