from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest

from app.services.ipo import metalogos_client as mc, source_discovery
from app.services.ipo.features import compute_derived_features
from app.services.ipo.metalogos_reference_refresh import refresh_missing_metalogos_references
from app.services.ipo.score import calculate_wealth_ipo_score


FIXTURES = Path(__file__).parent / 'fixtures'
ALICE_URL = 'https://metalogos.ai/160ipo/stock/B202605261'
ALICE_HTML = (FIXTURES / 'metalogos_alice_stock.html').read_text(encoding='utf-8')
ALICE_INDEX = json.loads((FIXTURES / 'metalogos_alice_schedule.json').read_text(encoding='utf-8'))


def alice():
    values = {'institutional_competition_ratio': 1000, 'lockup_commitment_ratio': 15,
              'tradable_share_ratio': 24, 'high_bid_ratio': 95, 'relative_valuation': 1,
              'revenue_cagr': 10, 'operating_margin': 10, 'net_debt_to_assets': 0}
    return {'ipo_id': 'alice', 'company_name': '엘리스그룹', 'stock_code': '0158S0',
            'subscription_start': '2026-10-07', 'subscription_end': '2026-10-08',
            'offer_band_low': 70400, 'offer_band_high': 90500, 'final_offer_price': None,
            'features': {key: {'value': value, 'status': 'ok', 'source_date': '20261006'}
                         for key, value in values.items()},
            'sources': {'offer_band_high': {'source': 'dart_document', 'source_date': '20261006'}}}


def parsed(day='2026-10-06'):
    return mc.parse_metalogos_stock_html(ALICE_HTML, source_url=ALICE_URL,
                                        observed_at=f'{day}T21:00:00+09:00')


def test_schedule_index_finds_alice_beyond_newest_40_and_fetches_only_matched_detail():
    payload = copy.deepcopy(ALICE_INDEX)
    # Simulate many newer IDs ahead of Alice: none is a Wealth candidate.
    payload['data']['ipoStocks'][:0] = [
        {'name': f'다른회사{i}', 'code': f'B202610{i:03d}'} for i in range(60)]
    calls = Counter()
    def handler(request):
        calls[str(request.url)] += 1
        if request.url.host == 'api.metalogos.site':
            assert request.url.path == '/schedule/external'
            assert dict(request.url.params) == {'startDate': '2026-09-01', 'endDate': '2026-11-30'}
            return httpx.Response(200, json=payload)
        assert str(request.url) == ALICE_URL
        return httpx.Response(200, text=ALICE_HTML)
    real_client = httpx.Client
    with patch.object(mc, 'require_external_network'), patch.object(mc.httpx, 'Client',
         side_effect=lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)):
        rows = mc.MetalogosIpoClient().fetch_company_items(
            company_names=['엘리스그룹', '없는회사'], target_date_str='2026-10-06')
    assert len(rows) == 1
    assert rows[0]['stock_code'] == '0158S0'
    assert rows[0]['sources']['metalogos160']['url'] == ALICE_URL
    assert rows[0]['final_offer_price'] == 90500
    assert sum(calls.values()) == 2
    assert calls[ALICE_URL] == 1
    assert all('sitemap' not in url and '?query=' not in url for url in calls)


@pytest.mark.parametrize('day,coverage,missing', [('2026-10-05', 75, False),
                                                ('2026-10-06', 75, False),
                                                ('2026-10-07', 67, True)])
def test_alice_price_provenance_and_score_cutoff(day, coverage, missing):
    target = alice()
    baseline = calculate_wealth_ipo_score(target, [])
    assert baseline['coverage'] == 67
    assert baseline['core_missing'] == ['pricing_discipline']
    market = {'ipos': [target]}
    features_before = copy.deepcopy(target['features'])
    source_discovery._apply_observation(market, parsed(day), source_name='metalogos160')
    assert target['final_offer_price'] == 90500
    price_source = target['sources']['final_offer_price']
    assert price_source['source'] == 'metalogos_160_public_page'
    assert price_source['source_date'] == day
    assert price_source['observed_at'] == f'{day}T21:00:00+09:00'
    assert price_source['url'] == ALICE_URL
    reference = target['sources']['metalogos160']
    assert reference['attractiveness_score'] == 79
    assert reference['demand_participant_count_reference'] == 2367
    assert reference['lockup_participant_count_reference'] == 355
    assert reference['tradable_share_ratio_reference'] == 20.81
    assert target['features'] == features_before
    derived = compute_derived_features(target)['pricing_discipline']
    assert derived['value'] == 100  # from canonical 90500 / 90500, not reference 79
    assert derived['source_date'] == max(day, '2026-10-06')
    result = calculate_wealth_ipo_score(target, [])
    assert result['coverage'] == coverage
    assert ('pricing_discipline' in result['core_missing']) is missing
    assert (result['score'] is None) is missing
    assert result['score'] != 79
    target['sources']['metalogos160']['attractiveness_score'] = 1
    assert calculate_wealth_ipo_score(target, []) == result


def test_late_price_cannot_be_hidden_by_cached_ok_derived_feature():
    target = alice()
    target['features']['pricing_discipline'] = {'value': 100, 'status': 'ok', 'source_date': '20261006'}
    source_discovery._apply_observation({'ipos': [target]}, parsed('2026-10-07'), source_name='metalogos160')
    assert 'pricing_discipline' in calculate_wealth_ipo_score(target, [])['core_missing']


@pytest.mark.parametrize('code', ['999999', '0158S1'])
def test_known_stock_code_conflict_rejects_canonical_and_reference(code):
    target = alice()
    row = parsed()
    row['stock_code'] = code
    before = copy.deepcopy(target)
    source_discovery._apply_observation({'ipos': [target]}, row, source_name='metalogos160')
    assert target == before
    with patch('app.services.ipo.metalogos_reference_refresh.read_market_store', return_value={'ipos': [target]}), \
         patch('app.services.ipo.metalogos_reference_refresh.write_market_store') as write:
        result = refresh_missing_metalogos_references(target_date_str='2026-10-06', prefetched_rows=[row])
    assert result['matched'] == 0
    write.assert_not_called()
    assert target == before


def test_source_priority_preserves_official_price_and_its_field_provenance():
    target = alice()
    target['final_offer_price'] = 90000
    official = {'source': 'dart_document', 'source_date': '20261005', 'value': 90000}
    target['sources'].update({'dart_schedule': {'source_date': '20261005'}, 'final_offer_price': official})
    source_discovery._apply_observation({'ipos': [target]}, parsed(), source_name='metalogos160')
    assert target['final_offer_price'] == 90000
    assert target['sources']['final_offer_price'] == official
    assert target['sources']['metalogos160']['attractiveness_score'] == 79


def test_same_price_keeps_first_observation_but_changed_price_cannot_be_backdated():
    target = alice()
    market = {'ipos': [target]}
    source_discovery._apply_observation(market, parsed('2026-10-06'), source_name='metalogos160')
    source_discovery._apply_observation(market, parsed('2026-10-07'), source_name='metalogos160')
    assert target['sources']['final_offer_price']['source_date'] == '2026-10-06'
    row = parsed('2026-10-07')
    row['final_offer_price'] = 91000
    row['sources']['final_offer_price']['value'] = 91000
    source_discovery._apply_observation(market, row, source_name='metalogos160')
    assert target['sources']['final_offer_price']['source_date'] == '2026-10-07'
    assert 'pricing_discipline' in calculate_wealth_ipo_score(target, [])['core_missing']


def test_missing_provenance_or_missing_page_price_never_uses_band_high():
    target = alice()
    row = parsed()
    row['sources'].pop('final_offer_price')
    source_discovery._apply_observation({'ipos': [target]}, row, source_name='metalogos160')
    assert target['final_offer_price'] is None
    no_price = mc.parse_metalogos_stock_html(ALICE_HTML.replace('<div>공모가: 90,500원</div>', ''),
                                            source_url=ALICE_URL)
    assert 'final_offer_price' not in no_price
    assert 'final_offer_price' not in no_price['sources']


def test_discovery_recalculates_alice_score_without_dart_and_reuses_reference_rows():
    target = alice()
    target['score'] = calculate_wealth_ipo_score(target, [])
    kind, npay, naver, metalogos, dart = (Mock() for _ in range(5))
    kind.fetch_pubofr_schedule_items.return_value = []
    npay.fetch_upcoming_ipos.return_value = []
    naver.fetch_ipo_discovery_items.return_value = []
    metalogos.fetch_company_items.return_value = [parsed()]
    dart.is_configured.return_value = False
    with patch.object(source_discovery, 'read_market_store', return_value={'ipos': [target]}), \
         patch.object(source_discovery, 'write_market_store') as write:
        result = source_discovery.discover_and_merge_primary_sources(
            username=None, target_date_str='2026-10-06', kind_client=kind, npay_client=npay,
            naver_client=naver, metalogos_client=metalogos, dart_client=dart)
    saved = write.call_args.args[0]['ipos'][0]
    assert saved['score']['coverage'] == 75
    assert saved['score']['core_missing'] == []
    assert saved['score']['score'] == calculate_wealth_ipo_score(saved, [saved])['score']
    assert saved['score']['score'] != 79
    assert result['metalogos_rows'][0]['sources']['metalogos160']['url'] == ALICE_URL
    with patch('app.services.ipo.metalogos_reference_refresh.read_market_store', return_value={'ipos': [saved]}):
        fallback = refresh_missing_metalogos_references(target_date_str='2026-10-06',
                      client=metalogos, prefetched_rows=result['metalogos_rows'])
    assert fallback['status'] == 'not_needed'
    metalogos.fetch_calendar_items.assert_not_called()


def test_schedule_contract_and_ambiguous_names_fail_closed():
    with pytest.raises(mc.MetalogosIpoClientError):
        mc.parse_metalogos_schedule_index({'data': {}})
    payload = {'data': {'ipoStocks': [
        {'name': '엘리스그룹', 'code': 'B202605261'},
        {'name': '엘리스그룹', 'code': 'OTHER'},
        {'name': '공격자', 'code': '../evil'},
    ]}}
    assert mc.parse_metalogos_schedule_index(payload) == {}
