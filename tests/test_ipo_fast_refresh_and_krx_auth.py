from __future__ import annotations

from contextlib import nullcontext
from datetime import date
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.services.ipo import historical_online_sync, orchestrator, refresh_adapter, source_discovery
from app.services.ipo.krx_authenticated_client import AuthenticatedKrxHistoricalClient
from app.services.user_krx_credentials import (
    credential_path, krx_credential_status, load_user_krx_credentials,
    save_user_krx_credentials,
)


class _FakeResponse:
    def __init__(self, *, status_code=200, payload=None, text=''):
        self.status_code = status_code; self._payload = payload; self.text = text
    @property
    def is_error(self): return self.status_code >= 400
    @property
    def is_redirect(self): return 300 <= self.status_code < 400
    def json(self): return self._payload


class _FakeHttpxClient:
    def __init__(self): self.calls = []; self.closed = False
    def get(self, url, **kwargs): self.calls.append(('GET', url)); return _FakeResponse(text='ok')
    def post(self, url, *, data=None, **kwargs):
        self.calls.append(('POST', url))
        if url.endswith('MDCCOMS001D1.cmd'):
            return _FakeResponse(payload={'_error_code':'CD001'}, text='{"_error_code":"CD001"}')
        return _FakeResponse(text='{"output":[{"ISU_SRT_CD":"250030","ISU_ABBRV":"진코스텍","LIST_DD":"2026/10/14","IPO_PRC":"13500","MKT_NM":"코스닥","LEAD_MGR":"하나증권"}]}')
    def close(self): self.closed = True


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("2026-10-02", (date(2026, 9, 1), date(2026, 11, 30))),
        ("2026-11-01", (date(2026, 10, 1), date(2026, 12, 31))),
        ("2026-12-15", (date(2026, 11, 1), date(2027, 1, 31))),
        ("2027-01-10", (date(2026, 12, 1), date(2027, 2, 28))),
        ("2028-02-10", (date(2028, 1, 1), date(2028, 3, 31))),
    ],
)
def test_interactive_window_rolls_with_target_month(target, expected):
    assert source_discovery._month_window(target) == expected
    assert refresh_adapter._month_window(target) == expected


def test_interactive_refresh_runs_bounded_discovery_with_capped_score_recovery():
    base = {'status':'ok','sources':{},'total_ipos':1}
    supplement = {'statuses':{'metalogos160':'sync_ok (matched=1)','dart_schedule':'sync_ok (matched=1, failed=0, ignored=0)'}, 'window_start':'2026-09-01','window_end':'2026-11-30','total_ipos':2}
    reference = {'status':'ok','candidates':1,'matched':1,'unmatched':0}
    targeted = {'status':'ok','mode':'score_recovery','candidates':1,'enriched':1}
    with patch.object(refresh_adapter, '_BASE_REFRESH_MARKET', return_value=base) as base_refresh, \
         patch.object(refresh_adapter, 'discover_and_merge_primary_sources', return_value=supplement) as discover, \
         patch.object(refresh_adapter, 'refresh_missing_metalogos_references', return_value=reference) as metalogos_ref, \
         patch.object(refresh_adapter, '_targeted_dart_enrichment', return_value=targeted) as deep, \
         patch.object(refresh_adapter._base, '_refresh_file_lock', return_value=nullcontext()):
        result = refresh_adapter.refresh_ipo_market(username='alice', target_date_str='2026-10-02')
    base_refresh.assert_called_once_with(username='alice', target_date_str='2026-10-02')
    discover.assert_called_once_with(username='alice', target_date_str='2026-10-02')
    metalogos_ref.assert_called_once_with(target_date_str='2026-10-02', prefetched_rows=[])
    deep.assert_called_once_with(
        username='alice',
        target_date_str='2026-10-02',
        score_recovery_only=True,
        max_candidates=4,
    )
    assert result['targeted_dart'] == targeted
    assert result['sources']['metalogos160_reference_fallback'] == 'ok (matched=1, unmatched=0)'
    assert result['interactive_window_start'] == '2026-09-01'
    assert result['interactive_window_end'] == '2026-11-30'
    assert orchestrator.refresh_ipo_market is refresh_adapter.refresh_ipo_market


def test_interactive_score_recovery_selects_only_due_near_term_calculating_ipos():
    rows = [
        {
            'company_name':'진코스텍',
            'subscription_start':'2026-10-02',
            'score':{'is_calculating':True,'score':None,'core_missing':['lockup_commitment_ratio']},
        },
        {
            'company_name':'멜콘',
            'subscription_start':'2026-10-01',
            'score':{'is_calculating':False,'score':68.1,'core_missing':[]},
        },
        {
            'company_name':'미래청약',
            'subscription_start':'2026-10-07',
            'score':{'is_calculating':True,'score':None,'core_missing':['lockup_commitment_ratio']},
        },
        {
            'company_name':'오래된청약',
            'subscription_start':'2026-09-10',
            'score':{'is_calculating':True,'score':None,'core_missing':['lockup_commitment_ratio']},
        },
        {
            'company_name':'테스트스팩',
            'listing_track':'spac',
            'subscription_start':'2026-10-02',
            'score':{'is_calculating':True,'score':None},
        },
    ]
    selected = refresh_adapter._interactive_score_recovery_candidates(
        rows,
        target_date_str='2026-10-03',
    )
    assert [row['company_name'] for row in selected] == ['진코스텍']


@pytest.mark.parametrize('shares_only', [False, True])
def test_targeted_dart_enrichment_persists_post_offer_shares(shares_only):
    market = {
        'schema_version': 1,
        'ipos': [
            {
                'ipo_id': 'ipo-jincostech',
                'company_name': '진코스텍',
                'corp_code': '01158632',
                'stock_code': '250030',
                'subscription_start': '2026-10-02',
                'final_offer_price': 23500.0,
                'features': {},
                'sources': {},
                'score': {
                    'score': None,
                    'is_calculating': True,
                    'core_missing': [],
                },
            }
        ],
    }

    filing = {
        'rcept_no': '20261001000594',
        'rcept_dt': '20261001',
        'report_nm': '[기재정정]투자설명서',
    }

    doc = """
    <p>
      당사의 상장예정주식수 3,786,533주 중
      58.44%에 해당하는 2,212,851주는
      상장 직후 유통가능 물량에 해당합니다.
    </p>
    """

    dart = MagicMock()
    dart.is_configured.return_value = True
    dart.get_filing_list.return_value = {'list': [filing]}
    dart.get_equity_registration_statements.return_value = {}
    dart.download_document_zip.return_value = b'fake-zip'

    parser = MagicMock()
    parser.parse_document.return_value = {}
    parser.extract_post_offer_shares.return_value = 3786533
    parser.extract_offer_band_from_structured.return_value = None
    parser.extract_offer_band.return_value = None
    parser_patch = (
        patch.object(refresh_adapter, 'DartSemanticParser', return_value=parser)
        if shares_only else nullcontext()
    )

    with parser_patch, \
         patch.object(refresh_adapter, 'DartClient', return_value=dart), \
         patch.object(refresh_adapter, 'read_market_store', return_value=market), \
         patch.object(refresh_adapter, 'write_market_store') as write_market, \
         patch.object(
             refresh_adapter,
             'extract_document_text_from_zip',
             return_value=doc,
         ), \
         patch.object(
             refresh_adapter,
             'select_point_in_time_filing',
             return_value=filing,
         ):
        result = refresh_adapter._targeted_dart_enrichment(
            username='alice',
            target_date_str='2026-10-05',
            score_recovery_only=True,
            max_candidates=1,
        )

    ipo = market['ipos'][0]

    assert result['status'] == 'ok'
    assert result['candidates'] == 1
    assert result['enriched'] == 1
    assert result['skipped'] == 0

    if shares_only:
        parser.parse_document.assert_called_once()

    assert ipo['post_offer_shares'] == 3786533

    source = ipo['sources']['post_offer_shares']
    assert source['source'] == 'dart_document'
    assert source['source_date'] == '20261001'
    assert source['rcept_no'] == '20261001000594'
    assert source['confidence'] == 'high'

    write_market.assert_called_once_with(market)


def test_metalogos_receives_only_three_month_candidate_names():
    market = {'ipos':[
        {'company_name':'9월회사','subscription_start':'2026-09-10'},
        {'company_name':'11월회사','subscription_start':'2026-11-10'},
        {'company_name':'12월회사','subscription_start':'2026-12-01'},
    ]}
    kind = MagicMock(); kind.fetch_pubofr_schedule_items.return_value = []
    npay = MagicMock(); npay.fetch_upcoming_ipos.return_value = []
    naver = MagicMock(); naver.fetch_ipo_discovery_items.return_value = []
    metalogos = MagicMock(); metalogos.fetch_company_items.return_value = []
    dart = MagicMock(); dart.is_configured.return_value = False
    with patch.object(source_discovery, 'read_market_store', return_value=market), patch.object(source_discovery, 'write_market_store'):
        source_discovery.discover_and_merge_primary_sources(username='alice', target_date_str='2026-10-02', kind_client=kind, npay_client=npay, naver_client=naver, metalogos_client=metalogos, dart_client=dart)
    names = metalogos.fetch_company_items.call_args.kwargs['company_names']
    assert names == ['9월회사', '11월회사']


def test_dart_skips_corp_master_when_bounded_candidates_already_have_corp_code():
    market = {'ipos':[{'company_name':'진코스텍','corp_code':'12345678','subscription_start':'2026-10-02'}]}
    dart = MagicMock(); dart.get_filing_list.return_value = {'list':[]}; dart.get_equity_registration_statements.return_value = {}
    source_discovery._apply_dart_schedules(market, dart=dart, target_date_str='2026-10-02', start=date(2026,9,1), end=date(2026,11,30))
    dart.get_corp_code_master.assert_not_called()


def test_krx_credentials_are_user_scoped_and_masked():
    with tempfile.TemporaryDirectory() as tmp, patch('app.services.user_krx_credentials.get_user_data_dir', return_value=Path(tmp) / 'alice'):
        status = save_user_krx_credentials('alice', {'login_id':'mykrxid','password':'super-secret'})
        assert status['configured'] is True
        assert status['login_id'] == 'mykr****'
        assert 'password' not in status
        raw = load_user_krx_credentials('alice')
        assert raw == {'login_id':'mykrxid','password':'super-secret'}
        assert credential_path('alice').parent.name == 'secrets'


def test_online_history_without_user_credentials_fails_before_network():
    with patch.object(AuthenticatedKrxHistoricalClient, 'credentials_configured', return_value=False):
        with pytest.raises(historical_online_sync.HistoricalOnlineSyncError) as exc:
            historical_online_sync.create_online_historical_preview('alice')
    assert exc.value.code == 'KRX_AUTH_REQUIRED'
    assert 'OpenAPI 설정' in str(exc.value)


def test_authenticated_krx_history_uses_user_credentials_and_reuses_session():
    fake = _FakeHttpxClient()
    with patch('app.services.ipo.krx_authenticated_client.load_user_krx_credentials', return_value={'login_id':'test-user','password':'test-password'}), \
         patch('app.services.ipo.krx_authenticated_client.require_external_network', return_value=None), \
         patch('app.services.ipo.krx_authenticated_client.httpx.Client', return_value=fake):
        client = AuthenticatedKrxHistoricalClient(username='alice')
        first = client.fetch_new_listings('2026-01-01','2026-06-30')
        second = client.fetch_new_listings('2026-07-01','2026-10-02')
    assert first[0]['stock_code'] == '250030'
    assert second[0]['actual_listing_date'] == '2026-10-14'
    assert len([u for m,u in fake.calls if m == 'POST' and u.endswith('MDCCOMS001D1.cmd')]) == 1
    assert len([u for m,u in fake.calls if m == 'POST' and u.endswith('getJsonData.cmd')]) == 2


def test_krx_credentials_are_not_wired_through_env_or_compose():
    root = Path(__file__).resolve().parents[1]
    env = (root / '.env.example').read_text(encoding='utf-8')
    compose = (root / 'docker-compose.ghcr.yml').read_text(encoding='utf-8')
    assert 'KRX_ID' not in env and 'KRX_PW' not in env
    assert 'KRX_ID' not in compose and 'KRX_PW' not in compose


def test_openapi_modal_contains_user_krx_settings_controls():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'app/static/index.html').read_text(encoding='utf-8')
    js = (root / 'app/static/wealth.js').read_text(encoding='utf-8')
    for token in ('openapiKrxLoginId','openapiKrxPassword','openapiKrxBadge'):
        assert token in html
    assert '/api/user/krx-marketplace-config' in js
    assert 'WEALTH_KRX_MARKETPLACE_CONFIG_V1' in js
