from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from app.services.tax.what_if import (
    FinancialIncomeWhatIfError,
    build_financial_income_what_if,
    get_financial_income_what_if_for_user,
)


class FinancialIncomeWhatIfTests(unittest.IsolatedAsyncioTestCase):
    def test_extra_income_can_cross_comprehensive_threshold(self):
        result = build_financial_income_what_if(
            {
                "known_gross_screening_income_krw": 17_000_000,
                "projected_gross_screening_income_krw": 18_500_000,
            },
            additional_dividend_gross_krw=1_000_000,
            additional_interest_gross_krw=750_000,
        )

        self.assertEqual(result["scenario_addition_gross_krw"], 1_750_000)
        self.assertEqual(
            result["scenario_projected_gross_screening_income_krw"], 20_250_000
        )
        comprehensive = result["thresholds"]["comprehensive_tax"]
        self.assertFalse(comprehensive["baseline"]["exceeded"])
        self.assertTrue(comprehensive["scenario"]["exceeded"])
        self.assertTrue(comprehensive["crossed_by_scenario"])
        self.assertEqual(comprehensive["scenario"]["remaining_krw"], 0)

    def test_exact_twenty_million_is_at_threshold_but_not_exceeded(self):
        result = build_financial_income_what_if(
            {
                "known_gross_screening_income_krw": 19_000_000,
                "projected_gross_screening_income_krw": 19_500_000,
            },
            additional_dividend_gross_krw=500_000,
        )

        scenario = result["thresholds"]["comprehensive_tax"]["scenario"]
        self.assertTrue(scenario["at_or_above"])
        self.assertFalse(scenario["exceeded"])
        self.assertFalse(
            result["thresholds"]["comprehensive_tax"]["crossed_by_scenario"]
        )

    def test_unavailable_projection_stays_unknown(self):
        result = build_financial_income_what_if(
            {
                "known_gross_screening_income_krw": 9_000_000,
                "projected_gross_screening_income_krw": None,
            },
            additional_dividend_gross_krw=5_000_000,
        )

        self.assertIsNone(result["scenario_projected_gross_screening_income_krw"])
        self.assertIsNone(
            result["thresholds"]["comprehensive_tax"]["scenario"]["exceeded"]
        )
        self.assertFalse(result["data_quality"]["scenario_projected_available"])

    def test_negative_extra_income_is_rejected(self):
        with self.assertRaisesRegex(
            FinancialIncomeWhatIfError,
            "FINANCIAL_INCOME_WHAT_IF_DIVIDEND_INVALID",
        ):
            build_financial_income_what_if(
                {
                    "known_gross_screening_income_krw": 0,
                    "projected_gross_screening_income_krw": 0,
                },
                additional_dividend_gross_krw=-1,
            )

    def test_boolean_money_input_is_rejected(self):
        with self.assertRaisesRegex(
            FinancialIncomeWhatIfError,
            "FINANCIAL_INCOME_WHAT_IF_INTEREST_INVALID",
        ):
            build_financial_income_what_if(
                {
                    "known_gross_screening_income_krw": 0,
                    "projected_gross_screening_income_krw": 0,
                },
                additional_interest_gross_krw=True,
            )

    def test_invalid_baseline_is_rejected(self):
        with self.assertRaisesRegex(
            FinancialIncomeWhatIfError,
            "FINANCIAL_INCOME_WHAT_IF_BASELINE_INVALID",
        ):
            build_financial_income_what_if(
                {"projected_gross_screening_income_krw": 1_000_000}
            )

    async def test_investment_comparison_uses_server_scoped_projected_income(self):
        baseline = {
            "known_gross_screening_income_krw": 12_000_000,
            "projected_gross_screening_income_krw": 16_000_000,
        }
        scenario = {
            "asset_type": "us_direct",
            "annual_distribution_krw": 3_000_000,
            "annual_realized_gain_krw": 5_000_000,
            "existing_personal_financial_income_krw": 1,
        }
        comparison = {"comparison": {"screening_only": True}}

        with patch(
            "app.services.tax.what_if.get_financial_income_projection_for_user",
            new=AsyncMock(return_value=baseline),
        ) as projection_mock, patch(
            "app.services.tax.what_if.compare_investment_tax_2026",
            return_value=comparison,
        ) as comparison_mock:
            result = await get_financial_income_what_if_for_user(
                "alice",
                owner="엄마",
                investment_scenario=scenario,
            )

        projection_mock.assert_awaited_once()
        kwargs = comparison_mock.call_args.kwargs
        self.assertEqual(kwargs["existing_personal_financial_income_krw"], 16_000_000)
        self.assertEqual(kwargs["asset_type"], "us_direct")
        context = result["investment_comparison"]["what_if_context"]
        self.assertEqual(
            context["existing_personal_financial_income_source"],
            "projected_gross_screening_income",
        )
        self.assertTrue(context["server_scoped_from_authenticated_user"])

    async def test_investment_comparison_falls_back_to_known_income(self):
        baseline = {
            "known_gross_screening_income_krw": 7_000_000,
            "projected_gross_screening_income_krw": None,
        }
        comparison = {"comparison": {"screening_only": True}}
        with patch(
            "app.services.tax.what_if.get_financial_income_projection_for_user",
            new=AsyncMock(return_value=baseline),
        ), patch(
            "app.services.tax.what_if.compare_investment_tax_2026",
            return_value=comparison,
        ) as comparison_mock:
            result = await get_financial_income_what_if_for_user(
                "alice",
                investment_scenario={
                    "asset_type": "domestic_dividend_stock",
                    "annual_distribution_krw": 1_000_000,
                },
            )

        self.assertEqual(
            comparison_mock.call_args.kwargs["existing_personal_financial_income_krw"],
            7_000_000,
        )
        self.assertEqual(
            result["investment_comparison"]["what_if_context"][
                "existing_personal_financial_income_source"
            ],
            "known_gross_screening_income",
        )

    async def test_invalid_investment_scenario_is_rejected(self):
        baseline = {
            "known_gross_screening_income_krw": 0,
            "projected_gross_screening_income_krw": 0,
        }
        with patch(
            "app.services.tax.what_if.get_financial_income_projection_for_user",
            new=AsyncMock(return_value=baseline),
        ):
            for scenario in ([], {}, {"asset_type": 123}):
                with self.subTest(scenario=scenario):
                    with self.assertRaisesRegex(
                        FinancialIncomeWhatIfError,
                        "FINANCIAL_INCOME_WHAT_IF_INVESTMENT_SCENARIO_INVALID",
                    ):
                        await get_financial_income_what_if_for_user(
                            "alice", investment_scenario=scenario  # type: ignore[arg-type]
                        )





class DividendBenefitPreviewTests(unittest.TestCase):
    def fixture(self):
        from app.services.dividend_event_identity import build_dividend_event_identity
        identity = build_dividend_event_identity(code='005930', record_date='2025-12-31')
        return {'holding_dividends': [{'code': '005930'}], 'monthly_schedule': [{'month': 4, 'items': [{
            'code': '005930', 'name': '<img src=x onerror=alert(1)>', 'currency': 'KRW', 'quantity': 10,
            'payout_krw': 1000, 'record_date': '2025-12-31', 'payment_date': '2026-04-20',
            'receipt_no': '20260301000001', 'event_identity': identity, 'event_identity_confidence': 'official'}]}],
            'dividend_intelligence': {'instruments': [{'code': '005930', 'tax_engine_asset_type': 'domestic_dividend_stock', 'high_dividend_qualification': {
                'status': 'official_qualified', 'source': 'official_valueup_disclosure',
                'receipt_no': '20260301000002', 'receipt_date': '20260302', 'business_year': 2025, 'decision_date': '2026-03-01',
                'correction_review': 'no_correction_indicated', 'source_url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260301000002'}}]},
            'capital_dividend_evidence': {'005930': {'receipt_no': '20260301000001',
                'viewer_url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260301000001',
                'payment_components': {'amount_status': 'verified', 'total_cash_dps_krw': '100',
                    'disclosed_capital_reduction_dps_krw': '40'},
                'reserve_evidence_status': 'disclosed', 'payment_event_status': 'single_event_scoped',
                'correction_relationship': {'status': 'not_resolved'}, 'tax_assessment': {'status': 'not_assessed'}}}}

    def preview(self, summary=None, selections=None, owner='아빠', year=2026):
        from datetime import date
        from app.services.tax.what_if import build_dividend_benefit_preview
        return build_dividend_benefit_preview(summary or self.fixture(), owner=owner, tax_year=year,
            selections=selections, as_of=date(2026, 10, 17))

    def test_auto_uses_matching_official_year_and_never_promotes_component_verification(self):
        result = self.preview()
        event = result['events'][0]
        self.assertFalse(event['capital']['applied'])
        self.assertEqual(event['capital']['official_status'], 'not_assessed')
        self.assertTrue(event['high_dividend']['applied'])
        self.assertEqual(event['high_dividend']['applied_amount_krw'], 600)
        self.assertEqual(result['high_dividend_national_tax_krw'], 84)
        self.assertTrue(result['filing_application_required'])
        self.assertFalse(result['favorable_vs_comprehensive_confirmed'])

    def test_insufficient_or_different_year_company_evidence_keeps_general_tax(self):
        for field, value in [('business_year', 2024), ('status', 'not_confirmed'),
                ('decision_date', '2026-05-01'), ('correction_review', 'not_resolved')]:
            with self.subTest(field=field):
                summary = self.fixture()
                summary['dividend_intelligence']['instruments'][0]['high_dividend_qualification'][field] = value
                result = self.preview(summary)
                self.assertFalse(result['events'][0]['high_dividend']['applied'])
                self.assertEqual(result['high_dividend_applied_amount_krw'], 0)

    def test_manual_on_requires_amount_and_off_and_auto_restore(self):
        summary = self.fixture()
        summary['dividend_intelligence']['instruments'][0]['high_dividend_qualification']['status'] = 'not_confirmed'
        key = self.preview(summary)['events'][0]['key']
        result = self.preview(summary, {key: {'high_dividend': {'mode': 'MANUAL_ON'}}})
        self.assertTrue(result['needs_amount'])
        self.assertEqual(result['high_dividend_applied_amount_krw'], 0)
        result = self.preview(summary, {key: {'high_dividend': {'mode': 'MANUAL_ON', 'amount_krw': 700}}})
        self.assertEqual(result['high_dividend_applied_amount_krw'], 700)
        self.assertTrue(result['events'][0]['high_dividend']['assumed'])
        self.assertEqual(result['events'][0]['high_dividend']['official_status'], 'not_confirmed')
        for mode in ['MANUAL_OFF', 'AUTO']:
            self.assertEqual(self.preview(summary, {key: {'high_dividend': {'mode': mode}}})['high_dividend_applied_amount_krw'], 0)

    def test_capital_manual_effect_and_no_double_subtraction_and_input_immutable(self):
        from copy import deepcopy
        summary = self.fixture(); before = deepcopy(summary)
        key = self.preview(summary)['events'][0]['key']
        result = self.preview(summary, {key: {'capital': {'mode': 'MANUAL_ON'},
            'high_dividend': {'mode': 'MANUAL_ON', 'amount_krw': 1000}}})
        self.assertEqual(result['capital_applied_amount_krw'], 400)
        self.assertEqual(result['high_dividend_applied_amount_krw'], 600)
        self.assertEqual(result['estimated_capital_withholding_difference_krw'], 62)
        self.assertEqual(result['gross_amount_krw'], 1000)
        self.assertEqual(result['general_taxable_dividend_krw'], 0)
        self.assertEqual(summary, before)
        self.assertFalse(result['actual_records_modified'])

    def test_scopes_invalid_amounts_and_forged_official_flags_rejected(self):
        key = self.preview()['events'][0]['key']
        for choices in [{key: {'capital': {'mode': 'MANUAL_ON', 'amount_krw': 1001}}},
                {key: {'capital': {'mode': 'MANUAL_ON', 'amount_krw': float('nan')}}},
                {key: {'capital': {'mode': 'AUTO', 'official_eligible': True}}},
                {'다른사람:2026:event': {}}]:
            with self.subTest(choices=choices), self.assertRaises(FinancialIncomeWhatIfError):
                self.preview(selections=choices)
        with self.assertRaises(FinancialIncomeWhatIfError):
            self.preview(selections={key: {}}, owner='엄마')
        self.assertEqual(self.preview(year=2025)['events'], [])
        self.assertFalse(self.preview(year=2027)['supported_year'])

    def test_ambiguous_events_and_etfs_are_not_double_counted(self):
        from copy import deepcopy
        summary = self.fixture()
        summary['monthly_schedule'][0]['items'] *= 2
        result = self.preview(summary)
        self.assertEqual(result['events'], [])
        self.assertEqual(result['ambiguous_events_excluded'], 1)
        summary = self.fixture(); summary['holding_dividends'][0]['is_etf'] = True
        self.assertEqual(self.preview(summary)['events'], [])

    def test_verified_scoped_capital_eligibility_uses_only_assessed_amount(self):
        summary = self.fixture()
        capital = summary['capital_dividend_evidence']['005930']
        capital['correction_relationship']['status'] = 'resolved'
        capital['tax_assessment'] = {'status': 'eligibility_confirmed', 'tax_year': 2026,
            'event_identity': summary['monthly_schedule'][0]['items'][0]['event_identity'],
            'eligible_amount_krw': 200}
        result = self.preview(summary)
        self.assertEqual(result['capital_applied_amount_krw'], 200)
        self.assertEqual(result['estimated_capital_withholding_difference_krw'], 31)
        capital['tax_assessment']['tax_year'] = 2025
        self.assertFalse(self.preview(summary)['events'][0]['capital']['applied'])


    def test_progressive_high_dividend_comparison_is_not_claimed_as_tax_saving(self):
        summary = self.fixture()
        summary['monthly_schedule'][0]['items'][0].update(quantity=300000, payout_krw=30000000)
        key = self.preview(summary)['events'][0]['key']
        result = self.preview(summary, {key: {'capital': {'mode': 'MANUAL_OFF'},
            'high_dividend': {'mode': 'MANUAL_ON', 'amount_krw': 30000000}}})
        self.assertEqual(result['high_dividend_national_tax_krw'], 4800000)
        self.assertEqual(result['high_dividend_national_difference_vs_withholding_krw'], -600000)
        self.assertFalse(result['favorable_vs_comprehensive_confirmed'])
        self.assertFalse(result['high_dividend_local_tax_included'])


if __name__ == "__main__":
    unittest.main()
