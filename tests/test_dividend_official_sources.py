from __future__ import annotations

from datetime import date
from contextlib import nullcontext
from copy import deepcopy
import io
import json
import unittest
from unittest.mock import AsyncMock, patch
import zipfile

import httpx

from app.services import dividend_official_sources as official
from app.services.dividend_confirmed_disclosures import parse_dividend_decision_document


class DividendOfficialSourcesTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_corp_code_zip_maps_listed_stock_codes(self):
        xml = b"""<?xml version='1.0' encoding='UTF-8'?>
<result>
  <list><corp_code>00126380</corp_code><corp_name>Samsung</corp_name><stock_code>005930</stock_code></list>
  <list><corp_code>00000001</corp_code><corp_name>Unlisted</corp_name><stock_code></stock_code></list>
</result>"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("CORPCODE.xml", xml)
        self.assertEqual(
            official._parse_corp_code_zip(buf.getvalue()),
            {"005930": "00126380"},
        )

    def test_extracts_ordinary_share_cash_dps(self):
        rows = [
            {"se": "주당 현금배당금(원)", "stock_knd": "보통주", "thstrm": "1,444"},
            {"se": "주당 현금배당금(원)", "stock_knd": "우선주", "thstrm": "1,445"},
            {"se": "현금배당수익률(%)", "stock_knd": "보통주", "thstrm": "2.3"},
        ]
        self.assertEqual(official._extract_ordinary_cash_dps(rows), 1444.0)

    def test_decision_title_never_confirms_amount(self):
        result = official._latest_dividend_decision(
            [
                {
                    "report_nm": "현금ㆍ현물배당 결정",
                    "rcept_no": "20260319000123",
                    "rcept_dt": "20260319",
                }
            ]
        )
        self.assertIsNotNone(result)
        self.assertFalse(result["confirmed_amount"])
        self.assertIn("20260319000123", result["viewer_url"])

    async def test_missing_api_key_fails_open(self):
        with patch.object(official, "external_network_allowed", return_value=True):
            result = await official.get_official_dividend_evidence(
                [{"code": "005930", "currency": "KRW"}],
                api_key="",
                as_of=date(2026, 9, 26),
            )
        self.assertEqual(result["status"], "missing_api_key")
        self.assertEqual(result["evidence"], {})
        self.assertFalse(result["policy"]["opendart_configured"])

    async def test_network_disabled_fails_open(self):
        with patch.object(official, "external_network_allowed", return_value=False):
            result = await official.get_official_dividend_evidence(
                [{"code": "005930", "currency": "KRW"}],
                api_key="test-key",
                as_of=date(2026, 9, 26),
            )
        self.assertEqual(result["status"], "network_disabled")
        self.assertEqual(result["evidence"], {})

    async def test_official_historical_dps_fills_only_missing_legacy_value(self):
        summary = {
            "holding_dividends": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 10,
                    "currency": "KRW",
                    "annual_div_per_share": 0,
                    "div_yield": 0,
                    "annual_payout_krw": 0,
                    "annual_payout_orig": 0,
                    "payout_months": [4],
                }
            ],
            "monthly_schedule": [],
        }
        holdings = [
            {
                "code": "005930",
                "name": "삼성전자",
                "quantity": 10,
                "currency": "KRW",
                "current_price": 70_000,
            }
        ]
        evidence = {
            "status": "ok",
            "policy": {"opendart_configured": True},
            "evidence": {
                "005930": {
                    "official_data_available": True,
                    "historical": {
                        "ordinary_cash_dps_krw": 1_444,
                        "business_year": 2025,
                    },
                    "recent_decision_disclosure": None,
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
                holdings,
                fx_rate=1_400,
            )
        row = result["holding_dividends"][0]
        self.assertEqual(row["annual_div_per_share"], 1_444)
        self.assertEqual(row["annual_payout_krw"], 14_440)
        self.assertEqual(row["forecast_source"]["numeric_source"], "opendart_historical_fill")
        self.assertFalse(row["forecast_source"]["confirmed_amount"])
        self.assertEqual(result["total_annual_dividend_krw"], 14_440)
        self.assertEqual(result["monthly_schedule"][3]["total_krw"], 14_440)

    async def test_official_history_does_not_override_nonzero_naver_forecast(self):
        summary = {
            "holding_dividends": [
                {
                    "code": "005930",
                    "name": "삼성전자",
                    "quantity": 10,
                    "currency": "KRW",
                    "annual_div_per_share": 1_500,
                    "div_yield": 2.0,
                    "annual_payout_krw": 15_000,
                    "annual_payout_orig": 15_000,
                    "payout_months": [4],
                }
            ],
            "monthly_schedule": [{"month": m, "total_krw": 0, "items": []} for m in range(1, 13)],
            "total_annual_dividend_krw": 15_000,
        }
        evidence = {
            "status": "ok",
            "policy": {},
            "evidence": {
                "005930": {
                    "official_data_available": True,
                    "historical": {
                        "ordinary_cash_dps_krw": 1_444,
                        "business_year": 2025,
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
                [{"code": "005930", "currency": "KRW", "quantity": 10}],
            )
        row = result["holding_dividends"][0]
        self.assertEqual(row["annual_div_per_share"], 1_500)
        self.assertEqual(row["forecast_source"]["numeric_source"], "naver")
        self.assertEqual(
            row["forecast_source"]["official_historical_annual_div_per_share_krw"],
            1_444,
        )

    async def test_us_holding_remains_yahoo_history(self):
        summary = {
            "holding_dividends": [
                {
                    "code": "SCHD",
                    "name": "SCHD",
                    "quantity": 10,
                    "currency": "USD",
                    "annual_div_per_share": 2.5,
                    "payout_months": [3, 6, 9, 12],
                }
            ]
        }
        with patch.object(
            official,
            "get_official_dividend_evidence",
            new=AsyncMock(return_value={"status": "no_domestic_holdings", "policy": {}, "evidence": {}}),
        ):
            result = await official.enrich_dividend_summary_with_official_sources(
                summary,
                [{"code": "SCHD", "currency": "USD", "quantity": 10}],
            )
        self.assertEqual(
            result["holding_dividends"][0]["forecast_source"]["numeric_source"],
            "yahoo_history",
        )


class CapitalDividendOfficialEvidenceTests(unittest.IsolatedAsyncioTestCase):
    day = date(2026, 10, 17)
    receipt = '20261016000001'
    holdings = [{'code': '005930', 'name': '가상회사', 'currency': 'KRW',
                 'quantity': 10, 'current_price': 1000}]

    def document(self, regular='60', capital='40'):
        return ('<table><tr><td>제1차 배당</td></tr>'
            '<tr><td>1주당 배당금(원)</td><td>보통주식</td><td>100</td></tr>'
            '<tr><td>배당기준일</td><td>2026-09-30</td></tr>'
            '<tr><td>지급예정일자</td><td>2026-11-20</td></tr>'
            + (f'<tr><td>보통주식 1주당 일반배당</td><td>{regular}원</td></tr>' if regular is not None else '')
            + (f'<tr><td>보통주식 1주당 감액배당 자본준비금 재원</td><td>{capital}원</td></tr>' if capital is not None else '')
            + '</table>')

    def filing(self, **changes):
        return {'rcept_no': self.receipt, 'rcept_dt': '20261016',
                'report_nm': '현금ㆍ현물배당 결정', 'rm': '', **changes}

    def zip_document(self, text):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('disclosure.xml', text)
        return buffer.getvalue()

    def client(self, *, text=None, rows=None, document_bytes=None, error=None, list_status='000', list_response=None, list_error=None):
        document = self.zip_document(self.document() if text is None else text) if document_bytes is None else document_bytes
        requests = []

        async def respond(request):
            requests.append(request)
            if request.url.path.endswith('/alotMatter.json'):
                return httpx.Response(200, json={'status': '013', 'list': []})
            if request.url.path.endswith('/list.json'):
                if list_error:
                    raise list_error
                if list_response is not None:
                    return list_response
                return httpx.Response(200, json={'status': list_status, 'total_page': 2,
                    'list': [self.filing()] if rows is None else rows})
            if request.url.path.endswith('/document.xml'):
                if error:
                    raise error
                return httpx.Response(200, content=document)
            raise AssertionError(f'Unexpected request path: {request.url.path}')

        return httpx.AsyncClient(transport=httpx.MockTransport(respond)), requests

    async def evidence(self, **options):
        client, requests = self.client(**options)
        async with client, self.source_context():
            result = await official.get_official_dividend_evidence(
                self.holdings, api_key='SYNTHETIC_KEY', as_of=self.day, client=client)
        return result, requests

    def source_context(self):
        # An async context wrapper keeps every test off external APIs.
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def context():
            with (patch.object(official, 'external_network_allowed', return_value=True),
                  patch.object(official, '_load_corp_codes', new=AsyncMock(return_value={'005930': '00000001'}))):
                yield
        return context()

    async def test_same_document_is_reused_and_legacy_fields_are_exact(self):
        result, requests = await self.evidence()
        item = result['evidence']['005930']
        self.assertEqual(sum(r.url.path.endswith('/document.xml') for r in requests), 1)
        self.assertEqual(len(requests), 3)
        query = next(r.url.params for r in requests if r.url.path.endswith('/list.json'))
        self.assertEqual(query['page_count'], '100')
        self.assertEqual(query['bgn_de'], '20251012')
        self.assertEqual(query['end_de'], '20261017')
        self.assertEqual(item['structured_decision_disclosure'], parse_dividend_decision_document(
            self.document(), report_name='현금ㆍ현물배당 결정', receipt_no=self.receipt,
            receipt_date='20261016', viewer_url=official.DART_VIEWER_URL.format(rcept_no=self.receipt), as_of=self.day))
        evidence = item['capital_dividend_evidence']
        self.assertEqual(evidence['receipt_no'], self.receipt)
        self.assertEqual(evidence['receipt_date'], '20261016')
        self.assertEqual(evidence['viewer_url'], official.DART_VIEWER_URL.format(rcept_no=self.receipt))
        self.assertEqual(evidence['as_of_date'], '2026-10-17')
        self.assertEqual(evidence['share_class'], 'ordinary')
        self.assertEqual(evidence['payment_components']['amount_status'], 'verified')
        self.assertEqual(evidence['reserve_evidence_status'], 'disclosed')
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), result)

    async def test_component_parser_exception_preserves_legacy_result(self):
        before, _ = await self.evidence()
        with patch.object(official, 'parse_dividend_payment_components', side_effect=RuntimeError('synthetic')):
            after, requests = await self.evidence()
        self.assertEqual(len(requests), 3)
        self.assertEqual(sum(r.url.path.endswith('/document.xml') for r in requests), 1)
        old, new = before['evidence']['005930'], after['evidence']['005930']
        self.assertEqual(old['structured_decision_disclosure'], new['structured_decision_disclosure'])
        self.assertEqual(new['capital_dividend_evidence']['reason'], 'component_parse_failed')
        self.assertIsNone(new['capital_dividend_evidence']['payment_components'])

    async def test_legacy_parser_failure_preserves_component_evidence(self):
        with patch.object(official, 'parse_dividend_decision_document', side_effect=ValueError('synthetic')):
            result, requests = await self.evidence()
        item = result['evidence']['005930']
        self.assertEqual(item['structured_decision_disclosure']['reason'], 'legacy_parse_failed')
        self.assertFalse(item['structured_decision_disclosure']['confirmed_amount'])
        self.assertFalse(item['structured_decision_disclosure']['confirmed_payment_date'])
        self.assertIsNone(item['structured_decision_disclosure']['ordinary_cash_dps_krw'])
        self.assertEqual(item['capital_dividend_evidence']['payment_components']['amount_status'], 'verified')
        self.assertEqual(len(requests), 3)
        self.assertEqual(sum(r.url.path.endswith('/document.xml') for r in requests), 1)

    async def test_verified_components_cannot_override_forecast_after_legacy_failure(self):
        summary = {'holding_dividends': [{'code': '005930', 'currency': 'KRW',
            'quantity': 10, 'annual_div_per_share': 80, 'annual_payout_orig': 800,
            'annual_payout_krw': 800, 'payout_months': [11], 'div_yield': 8}],
            'monthly_schedule': [{'month': 11, 'total_krw': 800, 'items': []}],
            'total_annual_dividend_krw': 800, 'monthly_avg_dividend_krw': 67, 'portfolio_yield': 8}
        client, requests = self.client()
        async with client, self.source_context():
            with (patch.object(official, 'parse_dividend_decision_document', side_effect=ValueError('synthetic')),
                  patch.object(official, '_attach_high_dividend_qualification', new=AsyncMock()),
                  patch('app.services.dividend_records.write_dividend_records') as dividend_writer,
                  patch('app.services.pnl_records.write_pnl_records') as pnl_writer):
                result = await official.enrich_dividend_summary_with_official_sources(
                    deepcopy(summary), self.holdings, api_key='SYNTHETIC', as_of=self.day, client=client)
        self.assertEqual(result['total_annual_dividend_krw'], 800)
        self.assertEqual(result['holding_dividends'][0]['annual_div_per_share'], 80)
        self.assertEqual(result['monthly_schedule'], summary['monthly_schedule'])
        self.assertEqual(result['capital_dividend_evidence']['005930']['payment_components']['amount_status'], 'verified')
        self.assertFalse(result['holding_dividends'][0]['forecast_source']['confirmed_amount'])
        dividend_writer.assert_not_called()
        pnl_writer.assert_not_called()
        self.assertEqual(len(requests), 3)

    async def test_both_parsers_fail_independently_with_one_download(self):
        with (patch.object(official, 'parse_dividend_decision_document', side_effect=ValueError('synthetic')) as legacy,
              patch.object(official, 'parse_dividend_payment_components', side_effect=ValueError('synthetic')) as capital):
            result, requests = await self.evidence()
        legacy.assert_called_once()
        capital.assert_called_once()
        item = result['evidence']['005930']
        self.assertFalse(item['structured_decision_disclosure']['confirmed_amount'])
        self.assertEqual(item['structured_decision_disclosure']['reason'], 'legacy_parse_failed')
        self.assertEqual(item['capital_dividend_evidence']['reason'], 'component_parse_failed')
        self.assertIsNone(item['capital_dividend_evidence']['payment_components'])
        self.assertEqual(len(requests), 3)

    async def test_zip_failure_is_distinct_and_neither_parser_runs(self):
        with (patch.object(official, 'parse_dividend_decision_document') as legacy,
              patch.object(official, 'parse_dividend_payment_components') as capital):
            result, requests = await self.evidence(document_bytes=b'not a zip')
        legacy.assert_not_called()
        capital.assert_not_called()
        item = result['evidence']['005930']
        self.assertEqual(item['structured_decision_disclosure']['reason'], 'document_extract_failed')
        self.assertEqual(item['capital_dividend_evidence']['reason'], 'document_extract_failed')
        self.assertEqual(len(requests), 3)

    async def test_explicit_api_errors_are_not_absence_and_expose_only_safe_code(self):
        for status in ('010', '011', '012', '020', '100', '800', '900'):
            with self.subTest(status=status):
                response = httpx.Response(200, json={'status': status, 'message': 'PRIVATE_SERVER_MESSAGE'})
                result, requests = await self.evidence(list_response=response)
                item = result['evidence']['005930']
                evidence = item['capital_dividend_evidence']
                self.assertEqual(evidence['reason'], 'source_unavailable')
                self.assertEqual(evidence['api_status'], status)
                self.assertIsNone(item['recent_decision_disclosure'])
                self.assertIsNone(item['structured_decision_disclosure'])
                self.assertEqual(evidence['tax_assessment']['status'], 'not_assessed')
                self.assertEqual(evidence['correction_relationship']['status'], 'not_resolved')
                self.assertNotIn('PRIVATE_SERVER_MESSAGE', json.dumps(result))
                self.assertNotIn('SYNTHETIC_KEY', json.dumps(result))
                self.assertEqual(len(requests), 2)

    async def test_malformed_lookup_is_not_absence(self):
        payloads = ([], {}, {'status': '000'}, {'status': '000', 'list': {}},
            {'status': '000', 'list': [None]}, {'status': 0}, {'status': 'PRIVATE_VALUE'})
        responses = [httpx.Response(200, json=p) for p in payloads]
        responses.append(httpx.Response(200, content=b'not json'))
        for response in responses:
            with self.subTest(payload=response.content):
                result, requests = await self.evidence(list_response=response)
                evidence = result['evidence']['005930']['capital_dividend_evidence']
                self.assertEqual(evidence['reason'], 'invalid_response')
                self.assertNotIn('api_status', evidence)
                self.assertIsNone(evidence['payment_components'])
                self.assertEqual(len(requests), 2)

    async def test_lookup_failures_preserve_periodic_fallback_policy(self):
        periodic = {'available': True, 'ordinary_cash_dps_krw': 80, 'business_year': 2025}
        cases = (({'rows': []}, True, 'decision_not_found'),
            ({'list_status': '010'}, True, 'source_unavailable'),
            ({'list_response': httpx.Response(200, content=b'not json')}, False, 'invalid_response'),
            ({'list_response': httpx.Response(503)}, False, 'source_request_failed'))
        for options, available, reason in cases:
            with self.subTest(reason=reason):
                with patch.object(official, '_fetch_periodic_dividend', new=AsyncMock(return_value=deepcopy(periodic))):
                    result, requests = await self.evidence(**options)
                item = result['evidence']['005930']
                self.assertEqual(item['official_data_available'], available)
                self.assertEqual(item['capital_dividend_evidence']['reason'], reason)
                if available:
                    self.assertEqual(item['historical'], periodic)
                else:
                    self.assertNotIn('historical', item)
                    self.assertEqual(item['reason'], 'opendart_request_failed')
                self.assertEqual(len(requests), 1)

    async def test_lookup_transport_failure_preserves_legacy_fallback(self):
        request = httpx.Request('GET', official.OPENDART_LIST_URL)
        for error in (httpx.ReadTimeout('private', request=request),
                httpx.HTTPStatusError('private', request=request, response=httpx.Response(503))):
            with self.subTest(error=type(error).__name__):
                result, requests = await self.evidence(list_error=error)
                item = result['evidence']['005930']
                self.assertFalse(item['official_data_available'])
                self.assertEqual(item['reason'], 'opendart_request_failed')
                self.assertEqual(item['capital_dividend_evidence']['reason'], 'source_request_failed')
                self.assertEqual(len(requests), 2)
                self.assertNotIn('private', json.dumps(result))

    async def test_absent_key_and_blocked_network_make_no_requests(self):
        for allowed, key, status in ((True, '', 'missing_api_key'), (False, 'SYNTHETIC', 'network_disabled')):
            with self.subTest(status=status):
                client, requests = self.client()
                async with client:
                    with patch.object(official, 'external_network_allowed', return_value=allowed):
                        result = await official.get_official_dividend_evidence(
                            self.holdings, api_key=key, as_of=self.day, client=client)
                self.assertEqual(result['status'], status)
                self.assertEqual(result['evidence'], {})
                self.assertEqual(requests, [])

    async def test_document_failures_remain_unavailable_without_new_requests(self):
        request = httpx.Request('GET', official.OPENDART_DOCUMENT_URL)
        for options in ({'document_bytes': b'not a zip'},
                        {'error': httpx.ReadTimeout('synthetic timeout', request=request)},
                        {'error': httpx.HTTPStatusError('synthetic error', request=request, response=httpx.Response(503))}):
            with self.subTest(options=next(iter(options))):
                result, requests = await self.evidence(**options)
                item = result['evidence']['005930']
                self.assertFalse(item['structured_decision_disclosure']['confirmed_amount'])
                self.assertEqual(item['capital_dividend_evidence']['status'], 'unavailable')
                self.assertEqual(sum(r.url.path.endswith('/document.xml') for r in requests), 1)

    async def test_empty_document_cannot_create_component_evidence(self):
        result, _ = await self.evidence(document_bytes=self.zip_document('   '))
        evidence = result['evidence']['005930']['capital_dividend_evidence']
        self.assertEqual(evidence['status'], 'unavailable')
        self.assertEqual(evidence['tax_assessment']['status'], 'not_assessed')

    async def test_no_selected_disclosure_keeps_tax_unassessed(self):
        for options in ({'rows': []}, {'list_status': '013'}):
            with self.subTest(options=options):
                result, requests = await self.evidence(**options)
                evidence = result['evidence']['005930']['capital_dividend_evidence']
                self.assertEqual(evidence['reason'], 'decision_not_found')
                self.assertIsNone(evidence['payment_components'])
                self.assertEqual(evidence['tax_assessment']['status'], 'not_assessed')
                self.assertFalse(any(r.url.path.endswith('/document.xml') for r in requests))

    async def test_multiple_events_are_not_promoted_by_official_provenance(self):
        markup = self.document() + self.document().replace('제1차', '제2차')
        result, _ = await self.evidence(text=markup)
        evidence = result['evidence']['005930']['capital_dividend_evidence']
        self.assertEqual(evidence['payment_components']['amount_status'], 'unverified')
        self.assertEqual(evidence['payment_event_status'], 'not_resolved')

    async def test_correction_selection_is_unchanged_and_relationship_unresolved(self):
        corrected = self.filing(rcept_no='20261017000002', rcept_dt='20261017', report_nm='[기재정정] 현금배당 결정')
        result, _ = await self.evidence(rows=[self.filing(rm='정'), corrected])
        item = result['evidence']['005930']
        self.assertEqual(item['recent_decision_disclosure'], official._latest_dividend_decision([self.filing(rm='정'), corrected]))
        evidence = item['capital_dividend_evidence']
        self.assertEqual(evidence['receipt_no'], corrected['rcept_no'])
        correction = evidence['correction_relationship']
        self.assertEqual(correction['status'], 'not_resolved')
        self.assertTrue(correction['title_has_correction_marker'])
        self.assertIsNone(correction['original_receipt_no'])
        self.assertIsNone(correction['supersedes_receipt_no'])
        self.assertEqual(correction['search_scope'], '370_days_first_page_100')

    async def test_withdrawal_later_correction_and_conflict_block_components_only(self):
        cases = ([self.filing(rm='철')], [self.filing(rm='정')],
                 [self.filing(), self.filing(report_nm='[기재정정] 현금배당 결정')])
        for rows in cases:
            with self.subTest(rows=rows):
                result, _ = await self.evidence(rows=rows)
                item = result['evidence']['005930']
                self.assertTrue(item['structured_decision_disclosure']['confirmed_amount'])
                evidence = item['capital_dividend_evidence']
                self.assertEqual(evidence['status'], 'unverified')
                self.assertEqual(evidence['payment_components']['amount_status'], 'unverified')
                self.assertIsNone(evidence['payment_components']['disclosed_capital_reduction_dps_krw'])

    async def test_missing_and_explicit_zero_and_quote_spans_survive_connection(self):
        for regular, expected in ((None, None), ('0', '0')):
            with self.subTest(regular=regular):
                result, _ = await self.evidence(text=self.document(regular=regular, capital='100'))
                evidence = result['evidence']['005930']['capital_dividend_evidence']
                self.assertEqual(evidence['payment_components']['disclosed_regular_dps_krw'], expected)
                self.assertEqual(evidence['tax_assessment'], {'status': 'not_assessed',
                    'excluded_income_amount_krw': None, 'withholding_adjustment_krw': None})
                for row in evidence['payment_components']['evidence_locations']:
                    self.assertTrue(0 <= row['amount_span'][0] < row['amount_span'][1] <= len(row['text']))
                    self.assertIn(row['text'][slice(*row['amount_span'])], ('100', '100원', '0원'))

    async def test_future_ui_boundary_is_plain_json_text_with_exact_spans(self):
        markup = self.document().replace('자본준비금 재원', '&lt;script&gt;synthetic()&lt;/script&gt; 자본준비금 재원')
        result, _ = await self.evidence(text=markup)
        evidence = result['evidence']['005930']['capital_dividend_evidence']
        self.assertEqual(evidence['evidence_text_format'], 'plain_text')
        self.assertTrue(evidence['requires_html_escape'])
        self.assertIn('<script>', evidence['payment_components']['reserve_description'])
        from starlette.responses import JSONResponse
        self.assertEqual(JSONResponse(result).headers['content-type'], 'application/json')

    async def test_user_scoped_keys_are_forwarded_without_shared_evidence_cache(self):
        for username in ('synthetic_a', 'synthetic_b'):
            client, requests = self.client()
            async with client, self.source_context():
                with patch.object(official, 'DartClient') as resolver:
                    resolver.return_value.api_key = username + '_KEY'
                    resolver.return_value.credential_source = 'user_config'
                    result = await official.get_official_dividend_evidence(
                        self.holdings, username=username, as_of=self.day, client=client)
                    resolver.assert_called_once_with(username=username)
            self.assertTrue(all(r.url.params['crtfc_key'] == username + '_KEY' for r in requests))
            self.assertNotIn(username + '_KEY', json.dumps(result))

    async def test_financial_and_high_dividend_results_match_pre_b1_same_mock_response(self):
        from app.services import high_dividend_qualification as high
        from app.services.dividend_forecast_snapshots import build_dividend_forecast_snapshot

        async def legacy_fetch(client, key, decision, *, as_of, revision_context=None):
            # Legacy transport contract, without any component parsing. Keep CI
            # independent of local checkpoint objects and shallow Git history.
            response = await client.get(official.OPENDART_DOCUMENT_URL,
                params={'crtfc_key': key, 'rcept_no': decision['receipt_no']}, timeout=10.0)
            response.raise_for_status()
            return parse_dividend_decision_document(
                official.extract_document_text_from_zip(response.content), as_of=as_of,
                **{field: decision[field] for field in ('report_name', 'receipt_no', 'receipt_date', 'viewer_url')})
        summary = {'holding_dividends': [{'code': '005930', 'name': '가상회사', 'currency': 'KRW',
            'quantity': 10, 'annual_div_per_share': 80, 'annual_payout_orig': 800,
            'annual_payout_krw': 800, 'payout_months': [11], 'div_yield': 8}],
            'monthly_schedule': [{'month': month, 'total_krw': 800 if month == 11 else 0,
                'items': [{'code': '005930', 'name': '가상회사', 'quantity': 10, 'currency': 'KRW',
                           'payout_krw': 800, 'payout_orig': 800}] if month == 11 else []}
                for month in range(1, 13)],
            'total_annual_dividend_krw': 800, 'monthly_avg_dividend_krw': 67, 'portfolio_yield': 8}
        outputs = []
        for legacy in (True, False):
            client, _ = self.client()
            async with client:
                with (patch.object(official, '_fetch_structured_decision', new=legacy_fetch) if legacy else nullcontext(),
                      patch.object(official, 'external_network_allowed', return_value=True),
                      patch.object(official, '_load_corp_codes', new=AsyncMock(return_value={'005930': '00000001'})),
                      patch.object(high, 'external_network_allowed', return_value=True),
                      patch.object(high, '_load_corp_code_map', new=AsyncMock(return_value={'005930': '00000001'})),
                      patch.object(high, '_fetch_company_status', new=AsyncMock(return_value={
                          'status': 'official_qualified', 'evidence': {'business_year': '2026'}}))):
                    outputs.append(await official.enrich_dividend_summary_with_official_sources(
                        deepcopy(summary), self.holdings, api_key='SYNTHETIC', as_of=self.day, client=client))
        before, after = outputs
        without_evidence = lambda value: {k: v for k, v in value.items() if k != 'capital_dividend_evidence'}
        self.assertEqual(without_evidence(after), without_evidence(before))
        self.assertEqual(after['total_annual_dividend_krw'], 1000)
        self.assertEqual(after['dividend_intelligence']['high_dividend']['official_qualified_count'], 1)
        self.assertFalse(after['monthly_schedule'][10]['items'][0]['entitlement_confirmed'])
        self.assertIn('capital_dividend_evidence', after)
        with patch('app.services.dividend_forecast_snapshots.uuid.uuid4', return_value='synthetic'):
            snapshots = [build_dividend_forecast_snapshot(value, self.holdings,
                as_of_date=self.day.isoformat(), captured_at='2026-10-17T00:00:00') for value in outputs]
        self.assertEqual(snapshots[0], snapshots[1])
        self.assertNotIn('capital_dividend_evidence', json.dumps(snapshots[1]))


if __name__ == "__main__":
    unittest.main()
