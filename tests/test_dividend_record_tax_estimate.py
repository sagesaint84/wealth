"""Synthetic record-only regressions; no real files, credentials or network."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from app.services import dividend_records as service


def record(**values):
    return dict({'id': 'synthetic-woori', 'code': '316140', 'name': '우리금융지주',
        'owner': '합성 소유자', 'date': '2026-04-08', 'currency': 'KRW',
        'amount': 212800, 'amount_krw': 212800, 'fx_rate': 1}, **values)


def official(capital='100', total='100'):
    return {'structured_decision_disclosure': {'receipt_no': '20260301000001',
        'confirmed_payment_date': True, 'payment_date': '2026-04-08', 'record_date': '2025-12-31'},
        'capital_dividend_evidence': {'status': 'available', 'receipt_no': '20260301000001',
            'payment_event_status': 'single_event_scoped', 'correction_relationship': {'status': 'not_resolved'},
            'payment_components': {'amount_status': 'verified', 'total_cash_dps_krw': total,
                'disclosed_capital_reduction_dps_krw': capital}}}


def test_general_net_is_automatically_grossed_up_without_modification():
    r = record()
    before = deepcopy(r)
    result = service.estimate_record_dividend(r)
    assert result['gross_amount'] == pytest.approx(212800 / .846)
    assert result['tax'] == pytest.approx(result['gross_amount'] - 212800)
    assert result['estimated'] and not result['capital_applied']
    assert r == before


def test_official_composition_auto_and_user_overrides_are_distinct():
    evidence = official()
    auto = service.estimate_record_dividend(record(), evidence)
    assert auto['capital_official_confirmed'] and auto['capital_applied']
    assert auto['gross_amount'] == 212800 and auto['tax'] == 0
    assert not auto['personal_tax_eligibility_confirmed']
    off = service.estimate_record_dividend(record(capital_dividend_mode='MANUAL_OFF'), evidence)
    assert off['capital_official_confirmed'] and not off['capital_applied']
    assert off['gross_amount'] == pytest.approx(212800 / .846)
    manual = service.estimate_record_dividend(record(capital_dividend_mode='MANUAL_ON'))
    assert manual['gross_amount'] == 212800 and manual['tax'] == 0
    assert manual['tax_type_label'] == '감액배당 · 사용자 지정'
    assert not manual['capital_official_confirmed']


@pytest.mark.parametrize('change', ['date', 'receipt', 'event', 'revision'])
def test_official_mismatch_keeps_ordinary_default(change):
    r, evidence = record(), official()
    if change == 'date':
        r['date'] = '2025-04-08'
    elif change == 'receipt':
        evidence['capital_dividend_evidence']['receipt_no'] = 'other'
    elif change == 'event':
        r['event_identity'] = 'different-event'
    else:
        evidence['capital_dividend_evidence']['correction_relationship']['later_correction_indicated'] = True
    assert not service.estimate_record_dividend(r, evidence)['capital_applied']


def test_partial_capital_is_not_grossed_up_twice():
    result = service.estimate_record_dividend(record(capital_dividend_mode='MANUAL_ON', capital_exempt_amount=100000))
    assert result['gross_amount'] == pytest.approx(100000 + 112800 / .846)
    mixed = service.estimate_record_dividend(record(), official('40', '100'))
    assert mixed['gross_amount'] == pytest.approx(212800 / (1 - .154 * .6))


def test_currency_rate_explicit_gross_tax_zero_and_fx_are_preserved():
    usd = service.estimate_record_dividend(record(currency='USD', amount=85, fx_rate=1400))
    assert usd['gross_amount'] == pytest.approx(100)
    assert usd['gross_amount_krw'] == 140000
    custom = service.estimate_record_dividend(record(estimated_tax_rate=.165))
    assert custom['gross_amount'] == pytest.approx(212800 / .835)
    assert service.estimate_record_dividend(record(gross_amount=300000, tax=123))['tax'] == 123
    assert service.estimate_record_dividend(record(gross_amount=0))['gross_amount'] == 0
    assert service.estimate_record_dividend(record(tax=0))['gross_amount'] == 212800
    assert service.estimate_record_dividend(record(tax=None))['gross_amount'] > 212800


def test_update_preserves_unknown_fields_and_omitted_tax_metadata(tmp_path):
    # Exercise the real atomic storage path, exclusively inside pytest's sandbox.
    with patch.object(service, '_get_user_dir', side_effect=lambda username=None: tmp_path / str(username)), \
         patch.object(service, 'resolve_stock_info', side_effect=lambda c, n, curr: (c, n, curr)):
        created = service.create_dividend_record(record(gross_amount=250000, tax=37200,
            capital_dividend_mode='MANUAL_ON'), username='alice')
        service.update_dividend_record(created['id'], {'memo': 'synthetic edit'}, username='alice')
        saved = service.read_dividend_records('alice')[0]
        assert saved['gross_amount'] == 250000 and saved['tax'] == 37200
        assert saved['capital_dividend_mode'] == 'MANUAL_ON'
        assert saved['amount'] == 212800 and saved['id'] == created['id']
        service.update_dividend_record(saved['id'], {'tax': 0, 'capital_dividend_mode': 'MANUAL_OFF'}, username='alice')
        assert service.read_dividend_records('alice')[0]['tax'] == 0
        assert service.read_dividend_records('bob') == []


@pytest.mark.parametrize('metadata', [{'estimated_tax_rate': 1}, {'gross_amount': float('nan')},
    {'tax': -1}, {'capital_dividend_mode': 'official'}, {'capital_exempt_amount': True}])
def test_invalid_optional_values_never_reach_writer(metadata, tmp_path):
    with patch.object(service, '_get_user_dir', return_value=tmp_path), \
         patch.object(service, 'write_dividend_records') as writer:
        with pytest.raises(ValueError):
            service.create_dividend_record(record(**metadata), username='synthetic')
        writer.assert_not_called()


def test_preview_is_authenticated_user_scoped_and_never_saves():
    from fastapi.testclient import TestClient
    from tests.test_request_state_user_id import _import_main_without_loading_real_env
    main = _import_main_without_loading_real_env()
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({'user': 'alice'}))
    with patch('app.services.user_manager.get_user_by_name', return_value={'username':'alice', 'role':'user'}), \
         patch.object(main, '_actual_dividend_evidence', new=AsyncMock(return_value={'316140': official()})) as source, \
         patch.object(service, 'write_dividend_records') as writer:
        result = client.post('/api/actual-dividends/estimate', json=record())
        assert result.status_code == 200
        assert result.headers['cache-control'] == 'no-store'
        assert result.json()['gross_amount'] == 212800
        assert source.await_args.args[1] == 'alice'
        writer.assert_not_called()
    client.cookies.clear()
    assert client.post('/api/actual-dividends/estimate', json=record()).status_code == 401


def test_evidence_cache_does_not_mix_users():
    async def check_cache():
        from tests.test_request_state_user_id import _import_main_without_loading_real_env
        main = _import_main_without_loading_real_env()
        with patch.object(main, '_actual_dividend_evidence_cache', {}), \
             patch('app.services.dividend_official_sources.get_official_dividend_evidence',
                new=AsyncMock(side_effect=[{'evidence':{'316140':{'synthetic':'alice'}}},
                                          {'evidence':{'316140':{'synthetic':'bob'}}}])) as source:
            a = await main._actual_dividend_evidence([record()], 'alice')
            b = await main._actual_dividend_evidence([record()], 'bob')
            again = await main._actual_dividend_evidence([record()], 'alice')
            assert a == again and a != b
            assert source.await_count == 2

    asyncio.run(check_cache())


def test_list_enrichment_respects_owner_year_and_interest_without_writes():
    from fastapi.testclient import TestClient
    from tests.test_request_state_user_id import _import_main_without_loading_real_env
    main = _import_main_without_loading_real_env()
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({'user':'alice'}))
    rows = [record(), record(id='other-owner', owner='합성 B'), record(id='old', date='2025-04-08'),
        record(id='interest', income_type='account_interest')]
    before = deepcopy(rows)
    with patch('app.services.user_manager.get_user_by_name', return_value={'username':'alice', 'role':'user'}), \
         patch.object(service, 'read_dividend_records', return_value=rows) as reader, \
         patch.object(main, '_actual_dividend_evidence', new=AsyncMock(return_value={'316140': official()})), \
         patch.object(service, 'write_dividend_records') as writer:
        response = client.get('/api/actual-dividends', params={'owner':'합성 소유자', 'year':'2026'})
        assert response.status_code == 200
        body = response.json()
        assert [r['id'] for r in body['records']] == ['synthetic-woori']
        assert body['records'][0]['tax_estimate']['gross_amount'] == 212800
        assert len(body['interest_records']) == 1
        assert body['total_actual_dividend_krw'] == 212800
        assert reader.call_args.args == ('alice',)
        writer.assert_not_called()
    assert rows == before
