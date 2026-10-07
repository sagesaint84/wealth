"""Synthetic filings only: interactive recovery must not borrow reference metrics."""
from contextlib import nullcontext
from copy import deepcopy
from io import BytesIO
from unittest.mock import MagicMock
from zipfile import ZipFile

import pytest

from app.services.ipo import refresh_adapter as adapter
from app.services.ipo.dart_parser import DartSemanticParser
from app.services.ipo.score import calculate_wealth_ipo_score


DOCUMENT = '''<html><body><h2>상장 직후 유통가능 주식</h2>
<table><tr><th>구분</th><th>주식수</th><th>비율</th></tr>
<tr><td>상장 직후 유통가능</td><td>2,333,000</td><td>23.33%</td></tr>
</table></body></html>'''


def company():
    values = {'lockup_commitment_ratio':28, 'institutional_competition_ratio':1000,
              'high_bid_ratio':95, 'pricing_discipline':100,
              'relative_valuation':0.8, 'revenue_cagr':20,
              'operating_margin':15, 'net_debt_to_assets':10}
    row = {'ipo_id':'synthetic-ms', 'company_name':'엠에스바이오', 'corp_code':'12345678',
           'subscription_start':'2026-10-12', 'features':{
               key:{'status':'ok', 'value':value, 'source_date':'20261006'}
               for key,value in values.items()},
           'sources':{'metalogos160':{'attractiveness_score':86,
               'tradable_share_ratio_reference':23.33,
               'demand_participant_count_reference':2269,
               'lockup_participant_count_reference':636}}}
    row['score'] = calculate_wealth_ipo_score(row, [row])
    return row


def dart_client():
    dart = MagicMock()
    dart.is_configured.return_value = True
    dart.get_equity_registration_statements.return_value = {}
    # Deliberately return out-of-window filings too, testing the selector itself.
    dart.get_filing_list.return_value = {'list':[
        {'rcept_no':f'{day}000001', 'rcept_dt':day,
         'report_nm':'[기재정정]증권신고서(지분증권)'}
        for day in ['20261006','20261008','20261010','20261012','20261015']]}
    archive = BytesIO()
    with ZipFile(archive, 'w') as zipped:
        zipped.writestr('document.xml', DOCUMENT)
    dart.download_document_zip.return_value = archive.getvalue()
    return dart


def run_interactive(monkeypatch, rows, dart, target='2026-10-07'):
    market = {'schema_version':1, 'ipos':rows}
    monkeypatch.setattr(adapter, 'DartClient', lambda **kwargs:dart)
    monkeypatch.setattr(adapter, 'read_market_store', lambda:market)
    writes = []
    monkeypatch.setattr(adapter, 'write_market_store', lambda value:writes.append(deepcopy(value)))
    monkeypatch.setattr(adapter, '_BASE_REFRESH_MARKET', lambda **kwargs:{'status':'ok'})
    monkeypatch.setattr(adapter._base, '_refresh_file_lock', nullcontext)
    monkeypatch.setattr(adapter, 'discover_and_merge_primary_sources', lambda **kwargs:{})
    monkeypatch.setattr(adapter, 'refresh_missing_metalogos_references', lambda **kwargs:{'status':'ok'})
    return adapter.refresh_ipo_market(username='synthetic-user', target_date_str=target), writes


def test_real_parser_extracts_canonical_tradable_ratio_with_filing_provenance():
    feature = DartSemanticParser().parse_document(
        doc_text=DOCUMENT, rcept_no='20261006000001', source_date='20261006')['tradable_share_ratio']
    assert feature['status'] == 'ok'
    assert feature['value'] == 23.33
    assert feature['source_date'] == '20261006'
    assert feature['rcept_no'] == '20261006000001'


@pytest.mark.parametrize(('target','filing_day','query_end'), [
    ('2026-10-07','20261006','20261007'),
    ('2026-10-15','20261010','20261011'),
])
def test_interactive_recovers_pre_subscription_score_with_both_cutoffs(monkeypatch, target, filing_day, query_end):
    row = company()
    assert row['score']['score'] is None
    assert row['score']['coverage'] == 60
    assert row['score']['core_missing'] == ['tradable_share_ratio']
    dart = dart_client()
    result, writes = run_interactive(monkeypatch, [row], dart, target)
    assert result['targeted_dart']['enriched'] == 1
    assert len(writes) == 1
    dart.download_document_zip.assert_called_once_with(f'{filing_day}000001')
    assert dart.get_filing_list.call_args.kwargs['end_de'] == query_end
    assert dart.get_equity_registration_statements.call_args.kwargs['end_de'] == query_end
    assert row['features']['tradable_share_ratio']['value'] == 23.33
    assert row['features']['tradable_share_ratio']['source_date'] == filing_day
    assert row['sources']['dart']['selection_as_of'] == f'{query_end[:4]}-{query_end[4:6]}-{query_end[6:]}'
    assert row['score']['coverage'] == 75
    assert row['score']['core_missing'] == []
    assert row['score']['is_calculating'] is False
    assert row['score']['score_as_of'] == '2026-10-11T23:59:59+09:00'
    assert row['score']['score'] != 86
    old_score = deepcopy(row['score'])
    row['sources']['metalogos160']['attractiveness_score'] = 1
    row['sources']['metalogos160']['tradable_share_ratio_reference'] = 99
    assert calculate_wealth_ipo_score(row, [row]) == old_score


@pytest.mark.parametrize('unavailable', ['key','network','future_only'])
def test_reference_never_substitutes_for_unavailable_canonical_data(monkeypatch, unavailable):
    row = company()
    original_features = deepcopy(row['features'])
    dart = dart_client()
    if unavailable == 'key':
        dart.is_configured.return_value = False
    elif unavailable == 'network':
        dart.get_filing_list.side_effect = RuntimeError('synthetic network unavailable')
    else:
        dart.get_filing_list.return_value['list'] = dart.get_filing_list.return_value['list'][1:]
    run_interactive(monkeypatch, [row], dart)
    assert row['features'] == original_features
    assert row['score']['score'] is None
    assert row['score']['coverage'] == 60
    assert row['score']['core_missing'] == ['tradable_share_ratio']
    dart.download_document_zip.assert_not_called()


def test_interactive_documents_remain_capped_at_four(monkeypatch):
    rows = [company() for _ in range(8)]
    for index, row in enumerate(rows):
        row.update(ipo_id=f'synthetic-{index}', company_name=f'합성기업{index}', corp_code=f'{index:08d}')
    dart = dart_client()
    result, _ = run_interactive(monkeypatch, rows, dart)
    assert result['targeted_dart']['candidates'] == 4
    assert dart.get_filing_list.call_count == 4
    assert dart.download_document_zip.call_count == 4
    assert sum(row['score']['score'] is not None for row in rows) == 4
    assert 'tradable_share_ratio' not in rows[-1]['features']


def test_one_week_horizon_is_inclusive_and_full_mode_remains_broader():
    rows = [company(), company()]
    rows[0]['subscription_start'] = '2026-10-14'
    rows[1]['subscription_start'] = '2026-10-15'
    selected = adapter._interactive_score_recovery_candidates(rows, target_date_str='2026-10-07')
    assert selected == [rows[0]]
    start, end = adapter._month_window('2026-10-07')
    assert all(adapter._is_target_candidate(row, start, end) for row in rows)
