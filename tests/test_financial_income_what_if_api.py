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

    def test_missing_investment_asset_type_is_rejected_before_service(self):
        with patch(
            "app.services.tax.get_financial_income_what_if_for_user",
            new=AsyncMock(),
        ) as service:
            response = self.client.post(
                "/api/dividends/financial-income-what-if",
                json={"investment_scenario": {}},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"]["code"],
            "FINANCIAL_INCOME_WHAT_IF_REQUEST_INVALID",
        )
        service.assert_not_awaited()

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





class DividendBenefitApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.user = patch('app.services.user_manager.get_user_by_name', return_value={
            'username': 'alice', 'id': 'user-alice', 'role': 'user'})
        self.user.start(); self.addCleanup(self.user.stop)
        self.client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({'user': 'alice'}))
        from tests.test_financial_income_what_if import DividendBenefitPreviewTests
        self.summary = DividendBenefitPreviewTests().fixture()
        self.full = {'accounts': [{'id': 'a', 'owner': '아빠'}, {'id': 'b', 'owner': '엄마'}],
            'holdings': [{'code': '005930', 'currency': 'KRW', 'quantity': 10, 'account_id': 'a'},
                {'code': '035420', 'currency': 'KRW', 'quantity': 10, 'account_id': 'b'}]}

    def post(self, body):
        from copy import deepcopy
        if body.get('selections') and 'context_key' not in body:
            body = {**body, 'context_key': main._dividend_benefit_context(
                self.summary, self.full, username='alice', owner=body.get('owner', '모두'),
                tax_year=body.get('tax_year', 2026))['context_key']}
        with (patch.object(main, 'get_dashboard', return_value=deepcopy(self.full)) as dashboard,
              patch.object(main, 'get_web_dividend_summary', new=AsyncMock(return_value=deepcopy(self.summary))) as source,
              patch('app.services.dividend_records.write_dividend_records') as writer,
              patch('app.services.pnl_records.write_pnl_records') as pnl_writer):
            response = self.client.post('/api/dividends/tax-benefit-preview', json=body)
        writer.assert_not_called(); pnl_writer.assert_not_called()
        for call in dashboard.call_args_list:
            self.assertEqual(call.kwargs['username'], 'alice')
        for call in source.call_args_list:
            self.assertEqual(call.kwargs['username'], 'alice')
        return response

    def test_authenticated_scope_auto_manual_and_no_store(self):
        result = self.post({'owner': '아빠', 'tax_year': 2026})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers['cache-control'], 'no-store')
        data = result.json(); key = data['events'][0]['key']
        self.assertTrue(data['events'][0]['high_dividend']['applied'])
        result = self.post({'owner': '아빠', 'tax_year': 2026,
            'selections': {key: {'capital': {'mode': 'MANUAL_ON'}, 'high_dividend': {'mode': 'MANUAL_OFF'}}}})
        self.assertEqual(result.json()['capital_applied_amount_krw'], 400)
        self.assertEqual(result.json()['high_dividend_applied_amount_krw'], 0)
        self.assertEqual(self.post({'owner': '아빠', 'tax_year': 2026}).json()['capital_applied_amount_krw'], 0)

    def test_owner_year_and_user_context_separate_and_unknown_owner_rejected(self):
        dad = self.post({'owner': '아빠', 'tax_year': 2026}).json()
        mom = self.post({'owner': '엄마', 'tax_year': 2026}).json()
        other_year = self.post({'owner': '아빠', 'tax_year': 2025}).json()
        self.assertNotEqual(dad['context_key'], mom['context_key'])
        self.assertNotEqual(dad['context_key'], other_year['context_key'])
        self.assertEqual(mom['events'], [])
        key = dad['events'][0]['key']
        self.assertEqual(self.post({'owner': '엄마', 'tax_year': 2026, 'selections': {key: {}}}).status_code, 400)
        self.assertEqual(self.post({'owner': '외부사용자', 'tax_year': 2026}).status_code, 400)
        a = main._dividend_benefit_context(self.summary, self.full, username='alice', owner='아빠', tax_year=2026)
        b = main._dividend_benefit_context(self.summary, self.full, username='bob', owner='아빠', tax_year=2026)
        self.assertNotEqual(a['context_key'], b['context_key'])
        self.assertEqual(self.post({'owner': '아빠', 'tax_year': 2026, 'context_key': b['context_key'],
            'selections': {key: {'capital': {'mode': 'MANUAL_ON'}}}}).status_code, 400)

    def test_client_cannot_submit_events_official_status_username_or_invalid_schema(self):
        for body in [{'username': 'bob'}, {'events': []}, {'official_eligible': True},
                {'tax_year': True}, {'owner': []}, {'selections': []}]:
            with self.subTest(body=body):
                self.assertEqual(self.post(body).status_code, 400)
        self.assertEqual(TestClient(app).post('/api/dividends/tax-benefit-preview', json={}).status_code, 401)

    def test_get_preserves_forecast_numbers_and_adds_separate_readonly_preview(self):
        from copy import deepcopy
        with (patch.object(main, 'get_dashboard', return_value=deepcopy(self.full)),
              patch.object(main, 'get_web_dividend_summary', new=AsyncMock(return_value=deepcopy(self.summary)))):
            response = self.client.get('/api/dividends', params={'owner': '아빠'})
        self.assertEqual(response.status_code, 200)
        data = response.json(); data.pop('dividend_tax_benefits')
        self.assertEqual(data, self.summary)


if __name__ == "__main__":
    unittest.main()
