from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from app.services.dividend_confirmed_disclosures import (
    _component_evidence, parse_dividend_decision_document, parse_dividend_payment_components,
)
import json
from app.services import dividend_official_sources as official


DISCLOSURE = """
<html><body><table>
<tr><th>구분</th><th>내용</th></tr>
<tr><td>3. 1주당 배당금 (원)</td><td>보통주식</td><td>1,250</td></tr>
<tr><td>배당기준일</td><td>2026년 09월 30일</td></tr>
<tr><td>배당금지급 예정일자</td><td>2026-11-20</td></tr>
</table></body></html>
"""


class ConfirmedDividendDisclosureParserTests(unittest.TestCase):
    def test_structurally_parses_amount_and_dates(self):
        result = parse_dividend_decision_document(
            DISCLOSURE,
            report_name="현금ㆍ현물배당 결정",
            receipt_no="20260926000123",
            receipt_date="20260926",
            viewer_url="https://dart.fss.or.kr/example",
            as_of=date(2026, 9, 26),
        )
        self.assertTrue(result["structured_verification"])
        self.assertTrue(result["confirmed_amount"])
        self.assertEqual(result["ordinary_cash_dps_krw"], 1250.0)
        self.assertEqual(result["record_date"], "2026-09-30")
        self.assertEqual(result["payment_date"], "2026-11-20")
        self.assertTrue(result["future_payment"])

    def test_missing_payment_date_is_not_invented(self):
        result = parse_dividend_decision_document(
            "<table><tr><td>1주당 배당금(원)</td><td>보통주식</td><td>500</td></tr></table>",
            report_name="현금ㆍ현물배당 결정",
            receipt_no="20260926000124",
            as_of=date(2026, 9, 26),
        )
        self.assertTrue(result["confirmed_amount"])
        self.assertIsNone(result["payment_date"])
        self.assertFalse(result["confirmed_payment_date"])
        self.assertIsNone(result["future_payment"])

    def test_title_match_without_structured_amount_is_not_confirmed(self):
        result = parse_dividend_decision_document(
            "<table><tr><td>배당기준일</td><td>2026-09-30</td></tr></table>",
            report_name="현금ㆍ현물배당 결정",
            receipt_no="20260926000125",
        )
        self.assertFalse(result["confirmed_amount"])
        self.assertFalse(result["structured_verification"])

    def test_non_decision_report_is_rejected(self):
        result = parse_dividend_decision_document(
            DISCLOSURE,
            report_name="사업보고서",
            receipt_no="20260926000126",
        )
        self.assertFalse(result["confirmed_amount"])
        self.assertEqual(result["reason"], "not_dividend_decision_report")


class ConfirmedDividendForecastIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_structured_future_amount_replaces_matching_month_estimate(self):
        summary = {
            "holding_dividends": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 10,
                    "currency": "KRW",
                    "annual_div_per_share": 4000,
                    "annual_payout_orig": 40000,
                    "annual_payout_krw": 40000,
                    "payout_months": [4, 5, 8, 11],
                    "div_yield": 5.0,
                }
            ],
            "monthly_schedule": [
                {"month": m, "total_krw": (10000 if m in {4, 5, 8, 11} else 0), "items": ([{
                    "code": "005930", "name": "삼성전자", "quantity": 10,
                    "currency": "KRW", "payout_krw": 10000, "payout_orig": 10000,
                    "div_yield": 5.0,
                }] if m in {4, 5, 8, 11} else [])}
                for m in range(1, 13)
            ],
            "total_annual_dividend_krw": 40000,
            "monthly_avg_dividend_krw": 3333,
            "portfolio_yield": 5.0,
        }
        evidence = {
            "status": "ok",
            "policy": {},
            "evidence": {
                "005930": {
                    "official_data_available": True,
                    "historical": {},
                    "recent_decision_disclosure": {"receipt_no": "20260926000123"},
                    "structured_decision_disclosure": {
                        "confirmed_amount": True,
                        "structured_verification": True,
                        "ordinary_cash_dps_krw": 1250,
                        "receipt_no": "20260926000123",
                        "record_date": "2026-08-31",
                        "payment_date": "2026-11-20",
                        "future_payment": True,
                    },
                }
            },
        }
        with patch.object(
            official,
            "get_official_dividend_evidence",
            new=AsyncMock(return_value=evidence),
        ):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "005930", "currency": "KRW", "quantity": 10, "current_price": 80000}],
                as_of=date(2026, 9, 26),
            )
        row = result["holding_dividends"][0]
        november = result["monthly_schedule"][10]
        self.assertEqual(november["total_krw"], 12500)
        self.assertEqual(row["annual_payout_krw"], 42500)
        self.assertEqual(row["annual_div_per_share"], 4250)
        self.assertEqual(result["total_annual_dividend_krw"], 42500)
        self.assertEqual(row["forecast_source"]["numeric_source"], "opendart_confirmed_disclosure")
        self.assertTrue(row["forecast_source"]["confirmed_amount"])
        self.assertTrue(row["forecast_source"]["confirmed_numeric_override"])
        item = november["items"][0]
        self.assertEqual(
            item["event_identity"],
            "dividend:v1:005930:record:2026-08-31",
        )
        self.assertEqual(item["event_identity_confidence"], "official")
        self.assertEqual(item["record_date"], "2026-08-31")
        self.assertEqual(item["payment_date"], "2026-11-20")
        self.assertEqual(item["receipt_no"], "20260926000123")
        self.assertEqual(item["forecast_source"], "opendart_confirmed_disclosure")
        self.assertEqual(item["quantity_basis"], "current_holding")
        self.assertFalse(item["entitlement_confirmed"])

    async def test_confirmed_amount_without_payment_date_keeps_numeric_fallback(self):
        summary = {
            "holding_dividends": [{
                "code": "005930", "name": "삼성전자", "quantity": 10,
                "currency": "KRW", "annual_div_per_share": 1500,
                "annual_payout_orig": 15000, "annual_payout_krw": 15000,
                "payout_months": [11],
            }],
            "monthly_schedule": [{"month": m, "total_krw": 0, "items": []} for m in range(1, 13)],
            "total_annual_dividend_krw": 15000,
        }
        evidence = {
            "status": "ok", "policy": {}, "evidence": {"005930": {
                "official_data_available": True,
                "historical": {},
                "structured_decision_disclosure": {
                    "confirmed_amount": True,
                    "structured_verification": True,
                    "ordinary_cash_dps_krw": 1700,
                    "payment_date": None,
                    "future_payment": None,
                },
            }},
        }
        with patch.object(official, "get_official_dividend_evidence", new=AsyncMock(return_value=evidence)):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "005930", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        source = result["holding_dividends"][0]["forecast_source"]
        self.assertTrue(source["confirmed_amount"])
        self.assertFalse(source["confirmed_numeric_override"])
        self.assertEqual(source["numeric_source"], "naver")
        self.assertEqual(result["total_annual_dividend_krw"], 15000)

    async def test_confirmed_event_can_create_forecast_when_legacy_is_zero(self):
        summary = {
            "holding_dividends": [{
                "code": "005930", "name": "삼성전자", "quantity": 10,
                "currency": "KRW", "annual_div_per_share": 0,
                "annual_payout_orig": 0, "annual_payout_krw": 0,
                "payout_months": [],
            }],
            "monthly_schedule": [{"month": m, "total_krw": 0, "items": []} for m in range(1, 13)],
            "total_annual_dividend_krw": 0,
        }
        evidence = {
            "status": "ok", "policy": {}, "evidence": {"005930": {
                "official_data_available": True,
                "historical": {},
                "structured_decision_disclosure": {
                    "confirmed_amount": True,
                    "structured_verification": True,
                    "ordinary_cash_dps_krw": 600,
                    "payment_date": "2026-12-20",
                    "future_payment": True,
                },
            }},
        }
        with patch.object(official, "get_official_dividend_evidence", new=AsyncMock(return_value=evidence)):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "005930", "currency": "KRW", "quantity": 10}],
                as_of=date(2026, 9, 26),
            )
        row = result["holding_dividends"][0]
        self.assertEqual(row["annual_payout_krw"], 6000)
        self.assertEqual(result["monthly_schedule"][11]["total_krw"], 6000)
        self.assertEqual(row["payout_months"], [12])
        self.assertEqual(result["dividend_paying_count"], 1)
        self.assertTrue(row["forecast_source"]["confirmed_numeric_override"])

    def test_latest_correction_filing_wins(self):
        selected = official._latest_dividend_decision([
            {
                "report_nm": "현금ㆍ현물배당 결정",
                "rcept_no": "20260313000100",
                "rcept_dt": "20260313",
            },
            {
                "report_nm": "[정정]현금ㆍ현물배당 결정",
                "rcept_no": "20260420000276",
                "rcept_dt": "20260420",
            },
        ])
        self.assertIsNotNone(selected)
        self.assertEqual(selected["receipt_no"], "20260420000276")
        self.assertFalse(selected["confirmed_amount"])


class PaymentComponentEvidenceTests(unittest.TestCase):
    def document(self, total='5400', regular='3238', capital='2162', kind='보통주식'):
        rows = [f'<tr><td>1주당 배당금(원)</td><td>{kind}</td><td>{total}</td></tr>']
        if regular is not None:
            rows.append(f'<tr><td>{kind} 1주당 일반 이익배당</td><td>{regular}원</td></tr>')
        if capital is not None:
            rows.append(f'<tr><td>{kind} 1주당 감액배당 (자본준비금 감액 재원)</td><td>{capital}원</td></tr>')
        return '<table>' + ''.join(rows) + '</table>'

    def parse(self, markup, **kwargs):
        return parse_dividend_payment_components(markup, report_name=kwargs.pop('report_name', '현금ㆍ현물배당 결정'), **kwargs)

    def test_regular_only_has_no_invented_capital_zero(self):
        value = self.parse(self.document(regular='5400', capital=None))['payment_components']
        self.assertEqual(value['disclosed_regular_dps_krw'], '5400')
        self.assertIsNone(value['disclosed_capital_reduction_dps_krw'])
        self.assertEqual(value['unclassified_dps_krw'], '0')

    def test_full_capital_with_explicit_regular_zero(self):
        value = self.parse(self.document(regular='0', capital='5400'))['payment_components']
        self.assertEqual(value['disclosed_regular_dps_krw'], '0')
        self.assertEqual(value['disclosed_capital_reduction_dps_krw'], '5400')
        self.assertEqual(value['amount_status'], 'verified')

    def test_integer_mixed_public_example(self):
        value = self.parse(self.document())['payment_components']
        self.assertEqual((value['total_cash_dps_krw'], value['disclosed_regular_dps_krw'],
                          value['disclosed_capital_reduction_dps_krw']), ('5400', '3238', '2162'))
        self.assertEqual(value['reconciliation_status'], 'matched')
        self.assertEqual(value['unclassified_dps_krw'], '0')
        self.assertIn('자본준비금', value['reserve_description'])
        self.assertTrue(value['evidence_locations'])

    def test_fractional_mixed_public_example_and_json(self):
        result = self.parse(self.document('1320.00', '880.10', '439.90'))
        value = result['payment_components']
        self.assertEqual((value['total_cash_dps_krw'], value['disclosed_regular_dps_krw'],
                          value['disclosed_capital_reduction_dps_krw']), ('1320', '880.1', '439.9'))
        self.assertEqual(value['reconciliation_status'], 'matched')
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)

    def test_over_total_is_inconsistent(self):
        value = self.parse(self.document('100', '60', '50'))['payment_components']
        self.assertEqual(value['reconciliation_status'], 'inconsistent')
        self.assertIsNone(value['unclassified_dps_krw'])
        self.assertEqual(value['amount_status'], 'unverified')

    def test_missing_regular_stays_unknown_not_subtracted(self):
        value = self.parse(self.document(regular=None))['payment_components']
        self.assertIsNone(value['disclosed_regular_dps_krw'])
        self.assertEqual(value['unclassified_dps_krw'], '3238')
        self.assertEqual(value['amount_status'], 'partial')

    def test_keyword_only_is_insufficient(self):
        markup = self.document(regular=None, capital=None) + '<p>감액배당 여부는 확인 필요</p>'
        value = self.parse(markup)['payment_components']
        self.assertIsNone(value['disclosed_capital_reduction_dps_krw'])
        self.assertEqual(value['amount_status'], 'insufficient_evidence')

    def test_reserve_approval_is_not_payment_decision(self):
        value = self.parse(self.document(), report_name='자본준비금 감액 승인')['payment_components']
        self.assertIsNone(value['total_cash_dps_krw'])
        self.assertEqual(value['amount_status'], 'insufficient_evidence')

    def test_unrelated_report_is_not_a_dividend(self):
        value = self.parse(self.document(), report_name='사업보고서')['payment_components']
        self.assertIsNone(value['total_cash_dps_krw'])

    def test_unknown_payment_date_remains_unknown(self):
        markup = self.document('1320', '880.1', '439.9')
        legacy = parse_dividend_decision_document(markup, report_name='현금배당 결정', receipt_no='20260312000001')
        self.assertIsNone(legacy['payment_date'])
        self.assertFalse(legacy['confirmed_payment_date'])
        self.assertIsNone(legacy['future_payment'])

    def test_mixed_share_classes_are_kept_separate(self):
        markup = self.document() + self.document('200', '150', '50', '종류주식')
        ordinary = self.parse(markup)['payment_components']
        preferred = self.parse(markup, share_class='preferred')['payment_components']
        self.assertEqual(ordinary['total_cash_dps_krw'], '5400')
        self.assertEqual(preferred['total_cash_dps_krw'], '200')
        self.assertEqual(preferred['disclosed_capital_reduction_dps_krw'], '50')
        self.assertEqual(preferred['share_class'], 'preferred')

    def test_unrelated_note_does_not_establish_amount(self):
        markup = self.document(regular=None, capital=None) + '<table><tr><td>타사 예시: 1주당 감액배당 5400원</td></tr></table>'
        value = self.parse(markup)['payment_components']
        self.assertIsNone(value['disclosed_capital_reduction_dps_krw'])

    def test_correction_title_does_not_create_relationship(self):
        result = self.parse(self.document(), report_name='[정정] 현금배당 결정')
        self.assertNotIn('corrects_receipt_no', result)
        self.assertNotIn('supersedes_receipt_no', result['payment_components'])
        self.assertEqual(result['tax_assessment']['status'], 'not_assessed')

    def test_invalid_amounts_never_confirmed(self):
        for invalid in ('-1', 'NaN', 'Infinity', '1,20', '1e3'):
            with self.subTest(amount=invalid):
                value = self.parse(self.document(capital=invalid))['payment_components']
                self.assertEqual(value['amount_status'], 'unverified')
                self.assertEqual(value['reconciliation_status'], 'invalid_amount')
                self.assertIsNone(value['disclosed_capital_reduction_dps_krw'])

    def test_legacy_amount_dates_and_status_are_unchanged(self):
        before = parse_dividend_decision_document(DISCLOSURE, report_name='현금ㆍ현물배당 결정',
            receipt_no='20260926000123', as_of=date(2026, 9, 26))
        self.parse(DISCLOSURE)
        after = parse_dividend_decision_document(DISCLOSURE, report_name='현금ㆍ현물배당 결정',
            receipt_no='20260926000123', as_of=date(2026, 9, 26))
        self.assertEqual(before, after)
        self.assertEqual(after['ordinary_cash_dps_krw'], 1250.0)
        self.assertEqual((after['record_date'], after['payment_date'], after['future_payment']),
                         ('2026-09-30', '2026-11-20', True))
        self.assertTrue(after['confirmed_amount'] and after['structured_verification'])
        self.assertNotIn('payment_components', after)

    def test_no_investor_tax_amount_is_ever_generated(self):
        for markup in (self.document(), self.document('1320', '880.1', '439.9'), self.document('100', '0', '100')):
            with self.subTest(markup=markup):
                self.assertEqual(self.parse(markup)['tax_assessment'], {
                    'status': 'not_assessed', 'excluded_income_amount_krw': None,
                    'withholding_adjustment_krw': None})

    def test_explicit_narrative_and_unknown_reserve(self):
        markup = self.document('1320', None, None) + '<table><tr><td>상기 1주당 배당금 1320원 (이익배당 880.1원 + 감액배당 439.9원)</td></tr></table>'
        value = self.parse(markup)['payment_components']
        self.assertEqual(value['disclosed_capital_reduction_dps_krw'], '439.9')
        self.assertEqual(value['reconciliation_status'], 'matched')
        self.assertIsNone(value['reserve_description'])

    def test_conflicting_disclosed_components_fail_closed(self):
        markup = self.document() + '<table><tr><td>보통주식 1주당 감액배당</td><td>2163원</td></tr></table>'
        value = self.parse(markup)['payment_components']
        self.assertEqual(value['reconciliation_status'], 'inconsistent')
        self.assertIsNone(value['disclosed_capital_reduction_dps_krw'])

    def test_plain_total_does_not_imply_regular_or_capital_amount(self):
        value = self.parse(DISCLOSURE)['payment_components']
        self.assertEqual(value['total_cash_dps_krw'], '1250')
        self.assertIsNone(value['disclosed_regular_dps_krw'])
        self.assertIsNone(value['disclosed_capital_reduction_dps_krw'])

    def test_unscoped_note_and_split_adjustment_are_not_inferred(self):
        markup = self.document(regular=None, capital=None) + '<table><tr><td>준비금 감액 설명: 감액배당 2162원. 주식분할 비율 2:1</td></tr></table>'
        value = self.parse(markup)['payment_components']
        self.assertEqual(value['total_cash_dps_krw'], '5400')
        self.assertIsNone(value['disclosed_capital_reduction_dps_krw'])


class PaymentComponentHotfixTests(unittest.TestCase):
    document = PaymentComponentEvidenceTests.document
    parse = PaymentComponentEvidenceTests.parse

    def assert_unconfirmed(self, markup, total):
        value = self.parse(markup)['payment_components']
        self.assertEqual(value['total_cash_dps_krw'], total)
        self.assertIsNone(value['disclosed_regular_dps_krw'])
        self.assertIsNone(value['disclosed_capital_reduction_dps_krw'])
        self.assertNotEqual(value['amount_status'], 'verified')
        self.assertNotEqual(value['reconciliation_status'], 'matched')

    def test_shared_single_amount_is_not_assigned_twice(self):
        for note in (
            '<tr><td>보통주식 1주당 일반배당/감액배당</td><td>50원</td></tr>',
            '<tr><td>1주당 일반배당/감액배당 50원</td></tr>',
            '<tr><td>1주당 일반배당 및 감액배당 50원</td></tr>',
        ):
            with self.subTest(note=note):
                self.assert_unconfirmed(self.document('100', None, None) + '<table>'+note+'</table>', '100')

    def test_independent_equal_amounts_are_valid(self):
        for markup in (
            self.document('100', '50', '50'),
            # Independent amounts still require an explicit cross-table event link.
            self.document('100', None, None) + '<table><tr><td>상기 1주당 일반배당 50원 + 감액배당 50원 지급 예정</td></tr></table>',
        ):
            with self.subTest(markup=markup):
                value = self.parse(markup)['payment_components']
                self.assertEqual(value['disclosed_regular_dps_krw'], '50')
                self.assertEqual(value['disclosed_capital_reduction_dps_krw'], '50')
                self.assertEqual(value['amount_status'], 'verified')
                self.assertEqual(value['reconciliation_status'], 'matched')
                locations = [row for row in value['evidence_locations'] if row['role'] != 'total']
                for evidence in locations:
                    self.assertNotEqual(evidence['role_span'], evidence['amount_span'])

    def test_negated_payment_does_not_confirm_components(self):
        markup = self.document('5400', None, None) + '<table><tr><td>상기 1주당 일반배당 3238원, 감액배당 2162원은 지급하지 않습니다.</td></tr></table>'
        self.assert_unconfirmed(markup, '5400')

    def test_ambiguous_two_amount_role_connection_is_rejected(self):
        markup = self.document('100', None, None) + '<table><tr><td>1주당 일반배당/감액배당 50원/50원</td></tr></table>'
        self.assert_unconfirmed(markup, '100')

    def test_past_and_other_event_notes_are_not_current_components(self):
        for prefix in ('과거 지급 사례', '지난해 배당', '전년도 배당', '이전 회차', '다른 지급 회차', '다른 분기'):
            with self.subTest(prefix=prefix):
                markup = self.document('5400', None, None) + f'<table><tr><td>{prefix}: 1주당 일반배당 3238원 + 감액배당 2162원</td></tr></table>'
                self.assert_unconfirmed(markup, '5400')

    def test_cancel_unpaid_and_pending_conditions_are_not_positive(self):
        for suffix in ('지급 취소', '미지급', '해당 없음', '승인 대기', '조건부', '승인될 경우 지급', '요건이 충족되지 않음'):
            with self.subTest(suffix=suffix):
                markup = self.document('5400', None, None) + f'<table><tr><td>1주당 일반배당 3238원 + 감액배당 2162원: {suffix}</td></tr></table>'
                self.assert_unconfirmed(markup, '5400')

    def test_negative_scope_does_not_invalidate_other_positive_rows(self):
        markup = self.document() + '<table><tr><td>다른 회차 1주당 일반배당 999원 + 감액배당 888원은 지급하지 않습니다.</td></tr></table>'
        value = self.parse(markup)['payment_components']
        self.assertEqual(value['amount_status'], 'verified')
        self.assertEqual(value['reconciliation_status'], 'matched')
        self.assertEqual(value['disclosed_capital_reduction_dps_krw'], '2162')

    def test_denied_table_heading_is_scoped_to_its_table(self):
        denied = '<table><tr><td>미지급 배당</td></tr><tr><td>1주당 일반배당</td><td>500원</td></tr><tr><td>1주당 감액배당</td><td>500원</td></tr></table>'
        self.assert_unconfirmed(self.document('1000', None, None) + denied, '1000')
        value = self.parse(self.document() + denied)['payment_components']
        self.assertEqual(value['amount_status'], 'verified')
        self.assertEqual(value['disclosed_regular_dps_krw'], '3238')
        historical = '<table><tr><td>과거 배당 비교</td></tr><tr><td>1주당 배당금(원)</td><td>보통주식</td><td>1000</td></tr><tr><td>1주당 일반배당</td><td>500원</td></tr><tr><td>1주당 감액배당</td><td>500원</td></tr></table>'
        current = self.parse(self.document() + historical)['payment_components']
        self.assertEqual(current['total_cash_dps_krw'], '5400')
        self.assertEqual(current['amount_status'], 'verified')

    def test_scheduled_fractional_payout_remains_valid(self):
        markup = self.document('1320', None, None) + '<table><tr><td>상기 1주당 일반배당 880.1원 + 감액배당 439.9원 지급 예정</td></tr></table>'
        value = self.parse(markup)['payment_components']
        self.assertEqual(value['reconciliation_status'], 'matched')
        self.assertEqual(value['disclosed_regular_dps_krw'], '880.1')
        self.assertEqual(value['disclosed_capital_reduction_dps_krw'], '439.9')

    def test_full_capital_and_inconsistent_sum_contracts_remain(self):
        full = self.parse(self.document('100', '0', '100'))['payment_components']
        self.assertEqual(full['amount_status'], 'verified')
        mismatch = self.parse(self.document('100', '60', '50'))['payment_components']
        self.assertEqual(mismatch['reconciliation_status'], 'inconsistent')

    def test_share_class_and_reserve_approval_still_fail_closed(self):
        markup = self.document() + self.document('200', '150', '50', '종류주식')
        self.assertEqual(self.parse(markup)['payment_components']['disclosed_capital_reduction_dps_krw'], '2162')
        approval = self.parse(markup, report_name='자본준비금 감액 승인')['payment_components']
        self.assertIsNone(approval['total_cash_dps_krw'])

    def test_hotfix_preserves_legacy_dict_and_tax_non_assessment(self):
        arguments = dict(report_name='현금배당 결정', receipt_no='20261014000001', as_of=date(2026, 10, 14))
        before = parse_dividend_decision_document(DISCLOSURE, **arguments)
        metadata = self.parse(self.document())
        self.assertEqual(parse_dividend_decision_document(DISCLOSURE, **arguments), before)
        self.assertEqual(metadata['tax_assessment'], {'status':'not_assessed',
            'excluded_income_amount_krw':None, 'withholding_adjustment_krw':None})
        root = Path(__file__).resolve().parents[1]
        for relative in ('app/services/dividend_official_sources.py', 'app/services/tax/financial_income.py',
                         'app/services/dividend_records.py', 'app/services/portfolio_dividend_after_tax.py'):
            self.assertNotIn('parse_dividend_payment_components', (root / relative).read_text(encoding='utf-8'))


class PaymentComponentScopeAndSpanTests(unittest.TestCase):
    document = PaymentComponentEvidenceTests.document
    parse = PaymentComponentEvidenceTests.parse

    def table(self, *rows, event='', record_date=''):
        heading = f'<tr><th>{event}</th></tr>' if event else ''
        day = f'<tr><td>배당기준일</td><td>{record_date}</td></tr>' if record_date else ''
        return '<table>' + heading + day + ''.join(rows) + '</table>'

    def total(self, amount='100'):
        return f'<tr><td>1주당 배당금(원)</td><td>보통주식</td><td>{amount}</td></tr>'

    def component(self, role, amount):
        return f'<tr><td>보통주식 1주당 {role}</td><td>{amount}원</td></tr>'

    def assert_unknown_event(self, markup):
        result = self.parse(markup)
        value = result['payment_components']
        self.assertEqual(value['amount_status'], 'unverified')
        self.assertNotEqual(value['reconciliation_status'], 'matched')
        self.assertIsNone(value['disclosed_regular_dps_krw'])
        self.assertIsNone(value['disclosed_capital_reduction_dps_krw'])
        self.assertEqual(result['tax_assessment'], {'status': 'not_assessed',
            'excluded_income_amount_krw': None, 'withholding_adjustment_krw': None})
        return value

    def test_distinct_rounds_cannot_complete_each_other(self):
        markup = self.table(self.total(), self.component('일반배당', '60'), event='제1차 배당')
        markup += self.table(self.component('감액배당', '40'), event='제2차 배당')
        self.assert_unknown_event(markup)

    def test_distinct_periods_cannot_complete_each_other(self):
        markup = self.table(self.total(), self.component('일반배당', '60'), event='2026년 1분기 배당')
        markup += self.table(self.component('감액배당', '40'), event='2026년 2분기 배당')
        self.assert_unknown_event(markup)

    def test_two_complete_events_with_equal_amounts_remain_distinct(self):
        rows = (self.total(), self.component('일반배당', '60'), self.component('감액배당', '40'))
        self.assert_unknown_event(self.table(*rows, event='제1차 지급') + self.table(*rows, event='제2차 지급'))

    def test_duplicate_tables_of_explicit_same_event_are_not_added(self):
        block = self.table(self.total(), self.component('일반배당', '60'),
                           self.component('감액배당', '40'), event='2026년 제1차 배당')
        value = self.parse(block + block)['payment_components']
        self.assertEqual(value['amount_status'], 'verified')
        self.assertEqual(value['total_cash_dps_krw'], '100')
        self.assertEqual(value['unclassified_dps_krw'], '0')

    def test_same_event_can_span_separately_labelled_tables(self):
        markup = self.table(self.total(), event='2026년 제1차 배당')
        markup += self.table(self.component('일반배당', '60'), self.component('감액배당', '40'),
                             event='2026년 제1차 배당')
        self.assertEqual(self.parse(markup)['payment_components']['amount_status'], 'verified')

    def test_shared_explicit_section_connects_tables(self):
        markup = '<h3>2026년 제1차 배당</h3>' + self.table(self.total())
        markup += self.table(self.component('일반배당', '60'), self.component('감액배당', '40'))
        self.assertEqual(self.parse(markup)['payment_components']['amount_status'], 'verified')

    def test_equal_dates_do_not_establish_cross_table_identity(self):
        markup = self.table(self.total(), record_date='2026-09-30')
        markup += self.table(self.component('일반배당', '60'), self.component('감액배당', '40'),
                             record_date='2026-09-30')
        self.assert_unknown_event(markup)

    def test_unlabelled_cross_table_components_are_ambiguous(self):
        markup = self.table(self.total())
        markup += self.table(self.component('일반배당', '60'), self.component('감액배당', '40'))
        self.assert_unknown_event(markup)

    def test_repeated_unlabelled_complete_tables_are_not_identity_evidence(self):
        self.assert_unknown_event(self.document('100', '60', '40') * 2)

    def test_multiple_rounds_within_one_table_are_not_flattened(self):
        markup = self.table('<tr><th>제1차 배당</th></tr>', self.total(), self.component('일반배당', '60'),
                             '<tr><th>제2차 배당</th></tr>', self.component('감액배당', '40'))
        self.assert_unknown_event(markup)

    def test_equal_event_label_with_conflicting_dates_is_ambiguous(self):
        markup = self.table(self.total(), event='제1차 배당', record_date='2026-06-30')
        markup += self.table(self.component('일반배당', '60'), self.component('감액배당', '40'),
                             event='제1차 배당', record_date='2026-09-30')
        self.assert_unknown_event(markup)

    def test_reference_cannot_override_explicit_other_round(self):
        markup = self.table(self.total(), event='제1차 배당')
        markup += self.table('<tr><td>상기 1주당 일반배당 60원 + 감액배당 40원</td></tr>', event='제2차 배당')
        self.assert_unknown_event(markup)

    def test_explicit_reference_preserves_single_event_partial_amounts(self):
        markup = self.table(self.total()) + self.table('<tr><td>상기 배당의 1주당 감액배당 40원</td></tr>')
        value = self.parse(markup)['payment_components']
        self.assertEqual(value['amount_status'], 'partial')
        self.assertIsNone(value['disclosed_regular_dps_krw'])
        self.assertEqual(value['unclassified_dps_krw'], '60')

    def test_long_row_quotes_include_exact_amount_and_role_spans(self):
        markup = self.table(self.total()) + self.table(
            '<tr><td>' + '공시 설명 ' * 80 + '상기 1주당 일반배당 60원 + 감액배당 40원 지급 예정</td></tr>')
        value = self.parse(markup)['payment_components']
        self.assertEqual(value['amount_status'], 'verified')
        for evidence in value['evidence_locations']:
            if evidence['role'] == 'total':
                continue
            self.assertLessEqual(len(evidence['text']), 320)
            start, end = evidence['amount_span']
            self.assertTrue(0 <= start < end <= len(evidence['text']))
            self.assertEqual(evidence['text'][start:end], {'regular': '60', 'capital': '40'}[evidence['role']])
            start, end = evidence['role_span']
            self.assertEqual(evidence['text'][start:end], {'regular': '일반배당', 'capital': '감액배당'}[evidence['role']])

    def test_equal_numbers_keep_distinct_role_positions(self):
        markup = self.table(self.total()) + self.table(
            '<tr><td>참고번호 50. 상기 1주당 일반배당 50원 + 감액배당 50원</td></tr>')
        locations = [item for item in self.parse(markup)['payment_components']['evidence_locations']
                     if item['role'] != 'total']
        self.assertEqual(len(locations), 2)
        self.assertNotEqual(locations[0]['amount_span'], locations[1]['amount_span'])
        for item in locations:
            start, end = item['amount_span']
            self.assertEqual(item['text'][start:end], '50')
            self.assertGreater(start, item['role_span'][1])

    def test_long_gap_keeps_amount_quote_without_false_role_span(self):
        label = '보통주식 1주당 감액배당 ' + '재원 설명 ' * 80
        markup = self.table(self.total(), f'<tr><td>{label}</td><td>40원</td></tr>')
        item = next(item for item in self.parse(markup)['payment_components']['evidence_locations']
                    if item['role'] == 'capital')
        self.assertLessEqual(len(item['text']), 320)
        self.assertEqual(item['text'][slice(*item['amount_span'])], '40원')
        self.assertNotIn('role_span', item)

    def test_no_position_is_guessed_when_candidate_is_ambiguous(self):
        markup = self.table(self.total(), '<tr><td>1주당 일반배당/감액배당 50원/50원</td></tr>')
        value = self.parse(markup)['payment_components']
        self.assertEqual([item['role'] for item in value['evidence_locations']], ['total'])

    def test_missing_and_explicit_zero_keep_distinct_contracts(self):
        missing = self.parse(self.document('100', None, '100'))['payment_components']
        zero = self.parse(self.document('100', '0', '100'))['payment_components']
        self.assertIsNone(missing['disclosed_regular_dps_krw'])
        self.assertEqual(missing['amount_status'], 'partial')
        self.assertEqual(zero['disclosed_regular_dps_krw'], '0')
        self.assertEqual(zero['amount_status'], 'verified')

    def test_conflicting_total_and_components_never_confirm(self):
        for extra in (self.total('101'), self.component('감액배당', '41')):
            with self.subTest(extra=extra):
                markup = self.document('100', '60', '40').replace('</table>', extra + '</table>')
                value = self.parse(markup)['payment_components']
                self.assertEqual(value['amount_status'], 'unverified')
                self.assertEqual(value['reconciliation_status'], 'inconsistent')

    def test_empty_non_string_and_oversized_inputs_fail_closed(self):
        for value in ('', None, 123, b'<table/>', 'x' * 200_001):
            with self.subTest(value_type=type(value).__name__):
                result = self.parse(value)
                self.assertEqual(result['payment_components']['amount_status'], 'insufficient_evidence')
                self.assertIsNone(result['payment_components']['total_cash_dps_krw'])
                self.assertEqual(result['tax_assessment']['status'], 'not_assessed')

    def test_unsupported_share_class_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported share class'):
            self.parse(self.document(), share_class='all')

    def test_labelled_payment_rounds_are_not_combined(self):
        markup = self.table('<tr><th>지급 회차: 제1차</th></tr>', self.total(),
                             self.component('일반배당', '60'), '<tr><th>지급 회차: 제2차</th></tr>',
                             self.component('감액배당', '40'))
        self.assert_unknown_event(markup)

    def test_caption_identifies_same_event_across_tables(self):
        caption = '<caption>2026년 제1차 배당</caption>'
        markup = self.table(self.total()).replace('<table>', '<table>' + caption)
        markup += self.table(self.component('일반배당', '60'), self.component('감액배당', '40')).replace(
            '<table>', '<table>' + caption)
        self.assertEqual(self.parse(markup)['payment_components']['amount_status'], 'verified')

    def test_conflicting_payment_dates_within_table_fail_closed(self):
        markup = self.document('100', '60', '40').replace('</table>',
            '<tr><td>지급예정일</td><td>2026-10-20</td></tr>'
            '<tr><td>지급예정일</td><td>2026-11-20</td></tr></table>')
        self.assert_unknown_event(markup)

    def test_nested_and_unbalanced_tables_are_not_confirmed(self):
        for markup in (self.document().replace('</table>', ''),
                       '<table><tr><td>' + self.document() + '</td></tr></table>'):
            with self.subTest(markup=markup):
                self.assertEqual(self.parse(markup)['payment_components']['amount_status'], 'unverified')

    def test_unverifiable_positions_are_omitted_without_number_search(self):
        text = '일반배당 50원 감액배당 50원'
        for span in (None, (-1, 2), (0, len(text) + 1), (0, 2)):
            with self.subTest(span=span):
                evidence = _component_evidence(text, index=0, key='regular', raw='50원',
                    role_span=(0, 4), amount_span=span)
                self.assertEqual(evidence['text'], text)
                self.assertNotIn('amount_span', evidence)
                self.assertNotIn('role_span', evidence)

    def test_duplicate_rows_in_same_event_do_not_double_amounts(self):
        markup = self.document('100', '60', '40').replace('</table>',
            self.component('일반배당', '60') + self.component('감액배당', '40') + '</table>')
        value = self.parse(markup)['payment_components']
        self.assertEqual(value['amount_status'], 'verified')
        self.assertEqual(value['disclosed_regular_dps_krw'], '60')
        self.assertEqual(value['disclosed_capital_reduction_dps_krw'], '40')
        self.assertEqual(value['unclassified_dps_krw'], '0')

    def test_currency_tokens_and_entities_keep_exact_quote_spans(self):
        markup = self.table(self.total('1,320.00'),
            '<tr><td>보통주식 1주당 일반배당</td><td>&#8361;880.10원</td></tr>',
            '<tr><td>보통주식 1주당 감액배당</td><td>439.90원</td></tr>')
        result = self.parse(markup)
        value = result['payment_components']
        self.assertEqual(value['amount_status'], 'verified')
        self.assertEqual(value['disclosed_regular_dps_krw'], '880.1')
        tokens = {'total': '1,320.00', 'regular': '₩880.10원', 'capital': '439.90원'}
        for evidence in value['evidence_locations']:
            self.assertEqual(evidence['text'][slice(*evidence['amount_span'])], tokens[evidence['role']])
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)

    def test_section_end_does_not_leak_previous_event_identity(self):
        markup = '<section><h3>제1차 배당</h3>' + self.table(self.total()) + '</section><section>'
        markup += self.table(self.component('일반배당', '60'), self.component('감액배당', '40')) + '</section>'
        self.assert_unknown_event(markup)

    def test_closed_empty_section_does_not_connect_later_tables(self):
        heading = '<section><h3>제1차 배당</h3></section>'
        markup = heading + self.table(self.total()) + heading
        markup += self.table(self.component('일반배당', '60'), self.component('감액배당', '40'))
        self.assert_unknown_event(markup)

    def test_malformed_table_declaration_fails_closed(self):
        markup = self.document().replace('<table>', '<table><![unsupported]>')
        self.assertEqual(self.parse(markup)['payment_components']['amount_status'], 'unverified')


if __name__ == "__main__":
    unittest.main()
