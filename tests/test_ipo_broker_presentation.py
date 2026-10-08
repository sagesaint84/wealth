"""IPO display identities reuse the account registry without widening its contract."""
from copy import deepcopy
from datetime import date
import json
from unittest.mock import patch

import pytest

from app.services import broker_registry, portfolio
from app.services.ipo import presentation
from app.services.ipo.account_resolution import resolve_ipo_account_candidates


@pytest.mark.parametrize('broker_id,variants', [
    ('samsung', ['삼성증권', '삼성증권(주)', '삼성증권 주식회사']),
    ('mirae', ['미래에셋증권', '미래에셋증권(주)', '미래에셋증권 주식회사']),
    ('daishin', ['대신증권', '대신증권(주)', '대신증권 주식회사']),
    ('shinhan', ['신한투자증권', '신한금융투자', '신한투자증권(주)']),
    ('bnk', ['(주)비엔케이투자증권', 'BNK투자증권']),
    ('eugene', ['유진증권', '유진투자증권', '유진투자증권(주)']),
])
def test_known_manager_variants_share_registry_portfolio_and_application_identity(broker_id, variants):
    with patch.object(presentation, 'normalize_broker', wraps=broker_registry.normalize_broker) as normalize, \
         patch.object(presentation, 'get_display_name', wraps=broker_registry.get_display_name) as display:
        filters = presentation.derive_lead_manager_filters(variants)
    assert filters == [{'key': broker_id, 'broker_id': broker_id,
                        'display_name': broker_registry.get_display_name(broker_id)}]
    assert [call.args[0] for call in normalize.call_args_list] == variants
    assert all(call.args == (broker_id,) for call in display.call_args_list)
    accounts = [{'id': 'synthetic-account', 'broker': variants[0], 'name': 'fixture'}]
    for raw in variants:
        assert broker_registry.normalize_broker(raw) == broker_id
        assert portfolio.canonical_broker_account_identity(raw) == broker_id
        result = resolve_ipo_account_candidates(raw, accounts)
        assert result.broker_id == filters[0]['broker_id']
        assert result.auto_selected_account_id == 'synthetic-account'
        assert result.resolution_status == 'AUTO_SELECTED'


@pytest.mark.parametrize('raw,name', [
    ('주식회사 상상인증권', '상상인증권'),
    ('케이프투자증권주식회사', '케이프투자증권'),
    ('㈜ 예시증권(주)', '예시증권'),
    ('예시증권㈜', '예시증권'),
    ('예시증권 주식회사', '예시증권'),
    ('  예시   증권 (주)  ', '예시 증권'),
    ('모간스탠리인터내셔날증권회사 서울지점', '모간스탠리인터내셔날증권'),
    ('골드만삭스증권 서울지점', '골드만삭스증권'),
    ('예시증권 리미티드 서울지점', '예시증권'),
    ('삼성증권우', '삼성증권우'),
    ('서울지점증권', '서울지점증권'),
    ('raw:eugene', 'raw:eugene'),
])
def test_unknown_legal_forms_are_ipo_only_and_financial_resolution_stays_closed(raw, name):
    assert broker_registry.normalize_broker(raw) is None
    assert presentation.derive_lead_manager_filters([raw]) == [
        {'key': f'raw:{name}', 'display_name': name, 'broker_id': None}]
    assert presentation._unknown_manager_name(name) == name
    result = resolve_ipo_account_candidates(raw, [{'id': 'synthetic', 'broker': raw}])
    assert result.broker_id is None
    assert result.candidates == ()
    assert result.resolution_status == 'BROKER_UNKNOWN'


def test_explicit_eugene_alias_merges_without_changing_unknown_namespace():
    assert presentation.derive_lead_manager_filters(['유진증권', '유진투자증권(주)', '유진투자증권']) == [
        {'key': 'eugene', 'display_name': '유진투자증권', 'broker_id': 'eugene'},
    ]
    assert broker_registry.get_display_name('eugene') == '유진투자증권'
    assert broker_registry.normalize_broker('유진증권우') is None
    assert presentation.derive_lead_manager_filters(None) == []
    assert presentation.derive_lead_manager_filters(['', '  ', None, 42, '(주)']) == []


def test_presentation_preserves_raw_bytes_and_does_not_mutate_market_or_read_storage():
    market = {'schema_version': 1, 'ipos': [{
        'ipo_id': 'synthetic', 'company_name': 'fixture',
        'lead_managers': [' 삼성증권(주) ', '미래에셋증권 주식회사', '골드만삭스증권 서울지점'],
        'subscription_start': '2026-10-12', 'subscription_end': '2026-10-13',
        'sources': {'fixture': {'raw_issuer': 'untouched'}},
    }]}
    before = deepcopy(market)
    raw_bytes = json.dumps(market['ipos'][0]['lead_managers'], ensure_ascii=False).encode('utf-8')
    with patch.object(presentation, '_read_portfolio_for_presentation', return_value={}), \
         patch.object(presentation, 'read_pnl_records_readonly', return_value=[]):
        output = presentation.present_market_store('synthetic-user', market, date(2026, 10, 8))
    assert market == before
    item = output['ipos'][0]
    assert json.dumps(item['lead_managers'], ensure_ascii=False).encode('utf-8') == raw_bytes
    assert [entry['key'] for entry in item['lead_manager_filters']] == ['samsung', 'mirae', 'raw:골드만삭스증권']
    assert item['sources'] == before['ipos'][0]['sources']
    assert 'lead_manager_filters' not in market['ipos'][0]
    item['lead_managers'].append('output mutation')
    item['lead_manager_filters'][0]['display_name'] = 'output mutation'
    assert market == before
