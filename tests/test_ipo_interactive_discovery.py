from __future__ import annotations

from collections import Counter
from contextlib import nullcontext
import copy
import logging
import threading
from unittest.mock import Mock, patch

import httpx
import pytest

from app.services.ipo import metalogos_client as mc, refresh_adapter, source_discovery
from app.services.ipo.metalogos_reference_refresh import refresh_missing_metalogos_references
from app.logging_security import install_credential_log_redaction


def stock_html(name, *, price=True):
    return f'<h1>{name} 공모주 핵심 요약</h1><div>청약일: 2026.10.07 ~ 10.08</div>' + (
        '<div>공모가: 23,500원</div>' if price else ''
    ) + '<div>매력지수 61</div>'


def public_client(handler):
    real_client = httpx.Client
    return patch.object(mc.httpx, 'Client', side_effect=lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs))


def test_shared_irrelevant_search_card_is_read_once_and_never_attached_to_other_issuers():
    calls = Counter()
    shared = 'https://metalogos.ai/160ipo/stock/B202607142'
    shell = f'<a href="{shared}">진코스텍 상세 보기</a>'
    # The old ?query= approach sees the same card for multiple distinct names.
    for name in ('엘리스그룹', '멜콘'):
        assert mc.parse_metalogos_search_stock_urls(shell) == [shared]

    def handler(request):
        calls[str(request.url)] += 1
        if request.url.path.endswith('/calendar'):
            text = '<div>client-rendered calendar</div>'
        elif request.url.path.endswith('/stock'):
            text = shell
        elif request.url.path.endswith('.xml'):
            text = f'<urlset><url><loc>{shared}</loc></url></urlset>'
        else:
            text = stock_html('진코스텍')
        return httpx.Response(200, text=text)

    with patch.object(mc, 'require_external_network'), public_client(handler):
        rows = mc.MetalogosIpoClient().fetch_company_items(
            company_names=['엘리스그룹', '멜콘', '(주)진코스텍', '진코스텍'],
            target_date_str='2026-10-06',
        )
    assert [row['company_name'] for row in rows] == ['진코스텍']
    assert calls[shared] == 1
    assert sum(calls.values()) == 4
    assert all('?query=' not in url for url in calls)
    assert 'features' not in rows[0]


def test_detail_concurrency_is_bounded_and_results_preserve_discovery_order():
    barrier = threading.Barrier(4)
    lock = threading.Lock()
    active = peak = 0
    calls = Counter()

    def handler(request):
        nonlocal active, peak
        with lock:
            calls[request.url.path] += 1
        if request.url.path.endswith('/calendar'):
            return httpx.Response(200, text=''.join(
                f'<a href="/160ipo/stock/B2026100{i}1">회사{i}</a>' for i in range(1, 9)))
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait(timeout=5)
        with lock:
            active -= 1
        number = request.url.path[-2]
        return httpx.Response(200, text=stock_html(f'회사{number}'))

    with patch.object(mc, 'require_external_network'), public_client(handler):
        rows = mc.MetalogosIpoClient().fetch_company_items(
            company_names=[f'회사{i}' for i in range(1, 9)], target_date_str='2026-10-06')
    assert peak == 4
    assert [row['company_name'] for row in rows] == [f'회사{i}' for i in range(1, 9)]
    assert sum(calls.values()) == 9


def test_sitemap_ignores_subpages_and_regeneration_dates_do_not_prioritize_old_issuers():
    xml = '''<urlset>
    <url><loc>https://metalogos.ai/160ipo/stock/B202201011</loc><lastmod>2026-10-06</lastmod></url>
    <url><loc>https://metalogos.ai/160ipo/stock/B202607142</loc><lastmod>2026-09-30</lastmod></url>
    <url><loc>https://metalogos.ai/160ipo/stock/B202607142/similar-stocks</loc></url>
    <url><loc>https://evil.example/160ipo/stock/B202610061</loc></url>
    <url><loc>http://metalogos.ai/160ipo/stock/B202610061</loc></url>
    </urlset>'''
    assert mc.parse_metalogos_sitemap_stock_urls(xml) == [
        'https://metalogos.ai/160ipo/stock/B202607142',
        'https://metalogos.ai/160ipo/stock/B202201011',
    ]


@pytest.mark.parametrize('band', ['희망공모가 90,500원', '희망 공모가 90,500원',
                                 '공모가: 70,400원 ~ 90,500원', '희망공모가 70,400 ~ 90,500원'])
def test_missing_price_is_not_fabricated_from_band_or_attractiveness(band):
    row = mc.parse_metalogos_stock_html(
        stock_html('엘리스그룹', price=False) + f'<div>{band}</div>',
        source_url='https://metalogos.ai/160ipo/stock/ALICE')
    assert 'final_offer_price' not in row
    assert 'features' not in row
    assert row['sources']['metalogos160']['attractiveness_score'] == 61


def test_untrusted_redirect_is_not_fetched():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        if request.url.path.endswith('/calendar'):
            return httpx.Response(200, text='<a href="/160ipo/stock/ALICE">엘리스그룹</a>')
        return httpx.Response(302, headers={'location': 'https://evil.example/160ipo/stock/ALICE'})
    with patch.object(mc, 'require_external_network'), public_client(handler):
        assert mc.MetalogosIpoClient().fetch_company_items(
            company_names=['엘리스그룹'], target_date_str='2026-10-06') == []
    assert len(calls) == 2
    assert all('evil.example' not in url for url in calls)


@pytest.mark.parametrize('rows', [[], [{
    'company_name': '엘리스그룹', 'final_offer_price': 1, 'features': {'pricing_discipline': 99},
    'sources': {'metalogos160': {'attractiveness_score': 61}},
}]])
def test_reference_fallback_reuses_even_empty_discovery_without_network(rows):
    market = {'ipos': [{'company_name': '엘리스그룹', 'subscription_start': '2026-10-07',
                        'final_offer_price': None, 'offer_band_high': 90500, 'sources': {}}]}
    client = Mock()
    with patch('app.services.ipo.metalogos_reference_refresh.read_market_store', return_value=market), \
         patch('app.services.ipo.metalogos_reference_refresh.write_market_store'):
        result = refresh_missing_metalogos_references(
            target_date_str='2026-10-06', client=client, prefetched_rows=rows)
    client.fetch_calendar_items.assert_not_called()
    assert result['matched'] == len(rows)
    assert market['ipos'][0]['final_offer_price'] is None
    assert 'features' not in market['ipos'][0]


def test_refresh_reuses_discovery_and_reports_monotonic_stages_with_max_four_dart():
    rows = [{'company_name': '엘리스그룹', 'sources': {'metalogos160': {'attractiveness_score': 61}}}]
    elapsed = iter([0, .01, .03, .04, .05, .06, .08])
    supplement = {'statuses': {}, 'metalogos_rows': rows, 'timings': {
        'kind_discovery_ms': 2, 'npay_discovery_ms': 3, 'naver_discovery_ms': 4,
        'metalogos_discovery_ms': 5}}
    with patch.object(refresh_adapter, '_BASE_REFRESH_MARKET', return_value={'status': 'ok'}), \
         patch.object(refresh_adapter._base, '_refresh_file_lock', return_value=nullcontext()), \
         patch.object(refresh_adapter, 'discover_and_merge_primary_sources', return_value=supplement), \
         patch.object(refresh_adapter, 'refresh_missing_metalogos_references', return_value={'status': 'ok'}) as ref, \
         patch.object(refresh_adapter, '_targeted_dart_enrichment', return_value={}) as dart, \
         patch.object(refresh_adapter, 'perf_counter', side_effect=lambda: next(elapsed)):
        result = refresh_adapter.refresh_ipo_market(target_date_str='2026-10-06')
    assert ref.call_args.kwargs['prefetched_rows'] is rows
    assert dart.call_args.kwargs['max_candidates'] == 4
    assert dart.call_args.kwargs['score_recovery_only'] is True
    assert result['timings']['base_refresh_ms'] == 10
    assert result['timings']['metalogos_reference_ms'] == 10
    assert result['timings']['targeted_dart_ms'] == 10
    assert result['timings']['total_ms'] == 80
    assert 'metalogos_rows' not in result


def test_interactive_refresh_has_one_external_discovery_even_when_alice_stays_unmatched():
    state = {'ipos': [
        {'company_name': '진코스텍', 'subscription_start': '2026-10-07', 'sources': {}},
        {'company_name': '엘리스그룹', 'subscription_start': '2026-10-07', 'sources': {},
         'offer_band_low': 70400, 'offer_band_high': 90500, 'final_offer_price': None},
    ]}
    calls = Counter()
    shared = 'https://metalogos.ai/160ipo/stock/B202607142'
    def handler(request):
        calls[str(request.url)] += 1
        if request.url.path.endswith('/calendar'):
            text = 'client-rendered'
        elif request.url.path.endswith('/stock'):
            text = f'<a href="{shared}">진코스텍</a>'
        elif request.url.path.endswith('.xml'):
            text = f'<urlset><url><loc>{shared}</loc></url></urlset>'
        else:
            text = stock_html('진코스텍')
        return httpx.Response(200, text=text)
    kind, npay, naver, dart = (Mock() for _ in range(4))
    kind.fetch_pubofr_schedule_items.return_value = []
    npay.fetch_upcoming_ipos.return_value = []
    naver.fetch_ipo_discovery_items.return_value = []
    dart.is_configured.return_value = False
    def write(market):
        state.clear()
        state.update(copy.deepcopy(market))
    with patch.object(mc, 'require_external_network'), public_client(handler), \
         patch.object(refresh_adapter, '_BASE_REFRESH_MARKET', return_value={'status': 'ok'}), \
         patch.object(refresh_adapter._base, '_refresh_file_lock', return_value=nullcontext()), \
         patch.object(refresh_adapter, '_targeted_dart_enrichment', return_value={}), \
         patch.object(source_discovery, 'KindClient', return_value=kind), \
         patch.object(source_discovery, 'NpayIpoClient', return_value=npay), \
         patch.object(source_discovery, 'NaverIpoDiscoveryClient', return_value=naver), \
         patch.object(source_discovery, 'DartClient', return_value=dart), \
         patch.object(source_discovery, 'read_market_store', side_effect=lambda: copy.deepcopy(state)), \
         patch.object(source_discovery, 'write_market_store', side_effect=write), \
         patch('app.services.ipo.metalogos_reference_refresh.read_market_store', side_effect=lambda: copy.deepcopy(state)), \
         patch('app.services.ipo.metalogos_reference_refresh.write_market_store', side_effect=write):
        result = refresh_adapter.refresh_ipo_market(target_date_str='2026-10-06')
    assert sum(calls.values()) == 4
    assert calls[shared] == 1
    assert 'unmatched=1' in result['sources']['metalogos160_reference_fallback']
    assert state['ipos'][0]['sources']['metalogos160']['attractiveness_score'] == 61
    assert state['ipos'][1]['final_offer_price'] is None
    assert state['ipos'][1]['sources'] == {}
    assert 'features' not in state['ipos'][1]


def test_independent_provider_reads_overlap_but_merge_and_write_stay_on_calling_thread():
    barrier = threading.Barrier(3)
    calling_thread = threading.get_ident()
    def read():
        barrier.wait(timeout=5)
        return [{'company_name': '엘리스그룹', 'subscription_start': '2026-10-07'}]
    kind, npay, naver, metalogos, dart = (Mock() for _ in range(5))
    kind.fetch_pubofr_schedule_items.side_effect = lambda **kw: read()
    npay.fetch_upcoming_ipos.side_effect = lambda **kw: read()
    naver.fetch_ipo_discovery_items.side_effect = read
    metalogos.fetch_company_items.return_value = [{'company_name': '다른회사', 'stock_code': '123456'}]
    dart.is_configured.return_value = False
    seen = []
    original = source_discovery._apply_observation
    def merge(*args, **kwargs):
        assert threading.get_ident() == calling_thread
        seen.append(kwargs['source_name'])
        return original(*args, **kwargs)
    with patch.object(source_discovery, 'read_market_store', return_value={'ipos': []}), \
         patch.object(source_discovery, 'write_market_store') as write, \
         patch.object(source_discovery, '_apply_observation', side_effect=merge):
        result = source_discovery.discover_and_merge_primary_sources(
            username=None, target_date_str='2026-10-06', kind_client=kind, npay_client=npay,
            naver_client=naver, metalogos_client=metalogos, dart_client=dart)
    assert seen == ['kind', 'npay', 'naver']
    assert result['metalogos_rows'] == []  # wrong issuer rejected at merge boundary too
    write.assert_called_once()


def test_reference_stock_code_conflict_cannot_attach_to_another_named_candidate():
    market = {'ipos': [
        {'ipo_id': 'alice', 'company_name': '엘리스그룹', 'stock_code': '123456', 'sources': {}},
        {'ipo_id': 'jinco', 'company_name': '진코스텍', 'sources': {}},
    ]}
    source_discovery._apply_observation(market, {
        'company_name': '진코스텍', 'stock_code': '123456',
        'sources': {'metalogos160': {'attractiveness_score': 61}},
    }, source_name='metalogos160')
    assert market['ipos'][0]['company_name'] == '엘리스그룹'
    assert market['ipos'][0]['sources'] == {}
    assert market['ipos'][1]['sources']['metalogos160']['attractiveness_score'] == 61
    assert not market['ipos'][1].get('stock_code')


def test_httpx_credentials_are_absent_from_emitted_logs_and_exception_chains(caplog):
    install_credential_log_redaction()
    secret = 'SENSITIVE-DART-TEST-KEY'
    url = f'https://opendart.fss.or.kr/api/list.json?corp_code=123&crtfc_key={secret}'
    with caplog.at_level(logging.INFO):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))) as client:
            response = client.get(url)
            assert response.request.url.params['crtfc_key'] == secret
        try:
            raise RuntimeError(url + '&client_secret=OTHER-SECRET')
        except RuntimeError:
            logging.getLogger('wealth.test').exception('DART request failed: %s', url)
    assert secret not in caplog.text
    assert 'OTHER-SECRET' not in caplog.text
    assert 'crtfc_key=[REDACTED]' in caplog.text
    assert 'corp_code=123' in caplog.text
    assert '200 OK' in caplog.text
