"""Synthetic preferences, coordinated interest actions, rollback and lock evidence."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import json
import threading

import pytest

from app.services import ledger, portfolio, dividend_records as dividends
from app.services import financial_json as storage
from app.services import ledger_interest, transaction_preferences as preferences
from regression_support import empty_portfolio, import_main_without_loading_real_env


@pytest.fixture
def users(tmp_path, monkeypatch):
    def directory(username=None):
        path = tmp_path / (username or 'alice')
        path.mkdir(exist_ok=True)
        return path
    monkeypatch.setattr('app.services.user_manager.get_user_data_dir', directory)
    monkeypatch.setattr(ledger, 'get_user_data_dir', directory)
    for user in ('alice', 'bob'):
        portfolio.write_portfolio(empty_portfolio(bank_accounts=[
            {'id': user+'-dad', 'owner': '아빠', 'currency': 'KRW', 'balance': 1000000, 'account_name': '생활비'},
            {'id': user+'-mom', 'owner': '엄마', 'currency': 'KRW', 'balance': 2000000, 'account_name': '급여'}],
            accounts=[{'id': user+'-toss', 'owner': '아빠', 'broker': '토스증권', 'account_name': '투자'},
                      {'id': user+'-kis', 'owner': '아빠', 'broker': '한국투자증권'}]), user)
        ledger.write_ledger({**ledger.default_ledger_data(), 'cards': [
            {'id': user+'-card', 'owner': '아빠', 'card_name': '신용카드'}]}, user)
        dividends.write_dividend_records([], user)
    return directory


def payload(**changes):
    return dict({'id':'interest-1', 'type':'income', 'category':'배당/금융수익', 'amount':10000,
                 'date':'2026-10-10', 'owner':'아빠', 'account_id':'alice-dad',
                 'merchant':'은행 이자', 'memo':'synthetic', 'mirror_to_dividend_interest':True}, **changes)


def balance(user='alice'):
    return portfolio.read_portfolio(user)['bank_accounts'][0]['balance']


def mirrors(user='alice'):
    return [r for r in dividends.read_dividend_records(user) if r.get('source') == 'ledger_interest']


def bytes_state(directory, user='alice'):
    return {name: (directory(user)/name).read_bytes() for name in
            ('ledger.json', 'portfolio.json', 'dividend_records.json')}


def test_create_retry_update_unlink_relink_delete_single_credit(users):
    tx = ledger.add_transaction(payload(), 'alice')
    assert balance() == 1010000
    assert ledger.add_transaction(payload(), 'alice') == tx
    assert balance() == 1010000 and len(ledger.read_ledger('alice')['transactions']) == 1
    record = mirrors()[0]
    assert record['id'] == tx['linked_interest_record_id']
    assert record['source_fingerprint'] == 'ledger-interest:interest-1'
    assert record['source_meta'] == {'ledger_transaction_id':'interest-1', 'bank_account_id':'alice-dad'}
    assert (record['income_type'],record['amount'],record['currency'],record['amount_krw']) == ('account_interest',10000,'KRW',10000)
    for _ in range(2):
        ledger.update_transaction(tx['id'], {'amount':15000, 'date':'2026-10-11', 'memo':'수정'}, 'alice')
        assert balance() == 1015000 and len(mirrors()) == 1
        assert (mirrors()[0]['amount'], mirrors()[0]['date'], mirrors()[0]['memo']) == (15000,'2026-10-11','수정')
    summary = dividends.get_actual_dividend_summary(username='alice')
    assert summary['total_actual_interest_krw'] == 15000 and summary['interest_record_count'] == 1
    ledger.update_transaction(tx['id'], {'mirror_to_dividend_interest':False}, 'alice')
    assert balance() == 1015000 and mirrors() == []
    assert len(ledger.read_ledger('alice')['transactions']) == 1
    ledger.update_transaction(tx['id'], {'mirror_to_dividend_interest':True}, 'alice')
    assert balance() == 1015000 and len(mirrors()) == 1
    ledger.delete_transaction(tx['id'], 'alice')
    assert balance() == 1000000 and mirrors() == []
    assert ledger.read_ledger('alice')['transactions'] == []


def test_account_owner_change_and_non_income_removes_mirror(users):
    ledger.add_transaction(payload(), 'alice')
    ledger.update_transaction('interest-1', {'owner':'엄마','account_id':'alice-mom'}, 'alice')
    banks = portfolio.read_portfolio('alice')['bank_accounts']
    assert [b['balance'] for b in banks] == [1000000,2010000]
    assert mirrors()[0]['owner'] == '엄마' and mirrors()[0]['account_name'] == '급여'
    ledger.update_transaction('interest-1', {'type':'expense'}, 'alice')
    assert mirrors() == [] and not ledger.read_ledger('alice')['transactions'][0]['mirror_to_dividend_interest']


@pytest.mark.parametrize('changes', [
    {'account_id':''}, {'account_id':'alice-kis'}, {'account_id':'missing'}, {'account_id':'bob-dad'},
    {'owner':'엄마'}, {'owner':'unknown'}, {'category':'급여/상여'}, {'amount':float('nan')},
    {'amount':float('inf')}, {'card_id':'alice-card'}, {'mirror_to_dividend_interest':'true'},
])
def test_invalid_link_never_changes_any_file(users, changes):
    before = bytes_state(users)
    with pytest.raises(ValueError): ledger.add_transaction(payload(**changes), 'alice')
    assert bytes_state(users) == before and mirrors('bob') == []


@pytest.mark.parametrize('operation', ['create', 'update', 'unlink', 'delete'])
@pytest.mark.parametrize('participant', ['ledger', 'portfolio', 'dividend'])
def test_each_participant_failure_restores_exact_preoperation_bytes(users, monkeypatch, operation, participant):
    if operation != 'create': ledger.add_transaction(payload(), 'alice')
    before = bytes_state(users)
    module, name = {'ledger':(ledger,'write_ledger'), 'portfolio':(portfolio,'write_portfolio'),
                    'dividend':(dividends,'write_dividend_records')}[participant]
    original = getattr(module, name)
    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise OSError('synthetic participant failure')
    monkeypatch.setattr(module, name, fail_after_write)
    with pytest.raises(OSError):
        if operation == 'create': ledger.add_transaction(payload(), 'alice')
        elif operation == 'update': ledger.update_transaction('interest-1', {'amount':15000}, 'alice')
        elif operation == 'unlink': ledger.update_transaction('interest-1', {'amount':12000,'mirror_to_dividend_interest':False}, 'alice')
        else: ledger.delete_transaction('interest-1', 'alice')
    assert bytes_state(users) == before
    assert not list(users('alice').glob('*.tmp'))


def test_missing_participants_failure_restores_absence(users, monkeypatch):
    users('alice').joinpath('ledger.json').unlink()
    users('alice').joinpath('dividend_records.json').unlink()
    before = (users('alice')/'portfolio.json').read_bytes()
    monkeypatch.setattr(dividends, 'write_dividend_records', lambda *a, **k: (_ for _ in ()).throw(OSError('fail')))
    with pytest.raises(OSError): ledger.add_transaction(payload(), 'alice')
    assert not (users('alice')/'ledger.json').exists()
    assert not (users('alice')/'dividend_records.json').exists()
    assert (users('alice')/'portfolio.json').read_bytes() == before


@pytest.mark.parametrize('name', ['ledger.json','portfolio.json','dividend_records.json'])
def test_corrupt_participant_fails_closed(users, name):
    (users('alice')/name).write_bytes(b'{broken')
    before = bytes_state(users)
    with pytest.raises(storage.FinancialStorageError): ledger.add_transaction(payload(), 'alice')
    assert bytes_state(users) == before


def test_ordinary_path_excludes_dividend_lock_and_concurrent_writers_do_not_deadlock(users, monkeypatch):
    calls = []
    original = ledger_interest.financial_user_locks
    @contextmanager
    def tracked(username, *names):
        calls.append(names)
        with original(username, *names): yield
    monkeypatch.setattr(ledger_interest, 'financial_user_locks', tracked)
    ledger.add_transaction({'id':'plain','type':'income','amount':1}, 'alice')
    assert calls == [('ledger.json','portfolio.json')]
    barrier = threading.Barrier(3)
    def linked():
        barrier.wait()
        for i in range(10): ledger.add_transaction(payload(id=f'interest-{i}'), 'alice')
    def ordinary():
        barrier.wait()
        for i in range(10): ledger.add_transaction({'id':f'plain-{i}','type':'income','amount':100,'account_id':'alice-dad'}, 'alice')
    def imported():
        barrier.wait()
        for i in range(10): dividends.create_dividend_record({'amount':3,'name':'synthetic','income_type':'account_interest'}, 'alice')
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(f) for f in (linked, ordinary, imported)]
        for f in futures: f.result(timeout=30)
    assert balance() == 1101000
    assert len(ledger.read_ledger('alice')['transactions']) == 21
    assert len(mirrors()) == 10 and len(dividends.read_dividend_records('alice')) == 20
    assert len({r['source_fingerprint'] for r in mirrors()}) == 10
    assert bytes_state(users, 'bob')


def test_linked_record_direct_mutation_blocked_and_clear_preserves_mirror(users):
    ledger.add_transaction(payload(), 'alice')
    ident = mirrors()[0]['id']
    with pytest.raises(ValueError): dividends.update_dividend_record(ident, {'amount':999}, 'alice')
    with pytest.raises(ValueError): dividends.delete_dividend_record(ident, 'alice')
    with pytest.raises(ValueError): dividends.create_dividend_record({'source':'ledger_interest','amount':1}, 'alice')
    manual = dividends.create_dividend_record({'amount':2, 'name':'manual'}, 'alice')
    assert dividends.delete_dividend_record(manual['id'], 'alice')
    dividends.clear_dividend_records('alice')
    assert len(mirrors()) == 1 and balance() == 1010000


def test_concurrent_same_transaction_retry_has_one_balance_credit_and_one_mirror(users):
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: ledger.add_transaction(payload(), 'alice'), range(12)))
    assert len({t['id'] for t in results}) == 1
    assert balance() == 1010000 and len(mirrors()) == 1
    assert len(ledger.read_ledger('alice')['transactions']) == 1


@pytest.mark.parametrize('provider', ['kis','nh','kb','kiwoom'])
def test_authoritative_provider_mapping_precedence_and_conflict_remain(users, monkeypatch, provider):
    main = import_main_without_loading_real_env()
    from fastapi import HTTPException
    from app.services.broker_account_resolution import validate_realized_destination
    accounts = [{'id':'saved','broker':provider},{'id':'other','broker':provider}]
    destination, resolution = validate_realized_destination(provider, accounts, 'saved', mapped_destination_account_id='saved')
    assert destination['id'] == 'saved' and resolution.reason == 'existing_mapping'
    with pytest.raises(ValueError, match='DESTINATION_MAPPING_CONFLICT'):
        validate_realized_destination(provider, accounts, 'other', mapped_destination_account_id='saved')
    monkeypatch.setattr(main, f'_read_{provider}_mapping', lambda username: {'source':'saved'})
    assert getattr(main,f'_assert_{provider}_mapping_compatible')('alice','source','saved')
    with pytest.raises(HTTPException) as error:
        getattr(main,f'_write_{provider}_mapping')('alice','source','other')
    assert error.value.status_code == 409 and error.value.detail['code'] == 'DESTINATION_MAPPING_CONFLICT'


def test_two_users_link_independently_and_bank_card_preferences_do_not_cross(users):
    before = bytes_state(users,'bob')
    ledger.add_transaction(payload(), 'alice')
    assert bytes_state(users,'bob') == before
    ledger.add_transaction(payload(account_id='bob-dad'), 'bob')
    assert balance('bob') == 1010000 and len(mirrors('bob')) == 1
    assert mirrors('alice')[0]['source_meta']['bank_account_id'] == 'alice-dad'
    assert mirrors('bob')[0]['source_meta']['bank_account_id'] == 'bob-dad'


def test_unlink_category_change_keeps_ledger_balance_only(users):
    ledger.add_transaction(payload(), 'alice')
    ledger.update_transaction('interest-1', {'category':'급여/상여','mirror_to_dividend_interest':False}, 'alice')
    assert balance() == 1010000 and mirrors() == []
    assert ledger.read_ledger('alice')['transactions'][0]['category'] == '급여/상여'


def test_fx_bulk_recalculation_does_not_round_or_mutate_ledger_interest(users, monkeypatch):
    ledger.add_transaction(payload(amount=10000.5), 'alice')
    before = deepcopy(mirrors()[0])
    dividends.create_dividend_record({'currency':'USD','amount':1,'fx_rate':1300,'name':'synthetic'}, 'alice')
    monkeypatch.setattr(dividends, 'get_historical_fx_rate', lambda *a, **k: 1400)
    dividends.recalculate_dividend_historical_fx('alice')
    assert mirrors()[0] == before and balance() == 1010000.5


def test_owner_defaults_roundtrip_clear_no_financial_effect_and_old_read_no_rewrite(users):
    before = bytes_state(users)
    assert preferences.get_transaction_defaults('alice') == {}
    assert bytes_state(users) == before
    pref = {'income_account_id':'alice-dad','expense_payment_method':'credit_card','expense_card_id':'alice-card',
            'expense_account_id':'alice-dad','transfer_account_id':'alice-dad'}
    preferences.set_transaction_defaults('아빠', pref, 'alice')
    preferences.set_transaction_defaults('엄마', {'income_account_id':'alice-mom','expense_payment_method':'bank_account',
        'expense_account_id':'alice-mom'}, 'alice')
    assert preferences.get_transaction_defaults('alice')['아빠'] == pref
    assert preferences.get_transaction_defaults('alice')['엄마']['expense_account_id'] == 'alice-mom'
    assert preferences.get_transaction_defaults('bob') == {}
    after = bytes_state(users)
    assert before['portfolio.json'] == after['portfolio.json'] and before['dividend_records.json'] == after['dividend_records.json']
    preferences.set_transaction_defaults('아빠', {}, 'alice')
    assert '아빠' not in preferences.get_transaction_defaults('alice')


@pytest.mark.parametrize('owner,pref', [('unknown',{}), ('엄마',{'income_account_id':'alice-dad'}),
    ('아빠',{'income_account_id':'bob-dad'}), ('아빠',{'expense_card_id':'bob-card'}),
    ('아빠',{'expense_payment_method':'bitcoin'}), ('아빠',{'income_account_id':'deleted'})])
def test_invalid_defaults_rejected(users, owner, pref):
    before = bytes_state(users)
    with pytest.raises(ValueError): preferences.set_transaction_defaults(owner, pref, 'alice')
    assert bytes_state(users) == before


@pytest.mark.parametrize('workflow', ['toss_wts_realized','toss_wts_income'])
def test_import_defaults_roundtrip_clear_stale_and_ownership(users, workflow):
    before = bytes_state(users)
    assert preferences.set_import_default(workflow,'alice-toss','아빠','alice')[workflow] == 'alice-toss'
    assert preferences.get_import_defaults('bob') == {}
    for ident, owner in [('bob-toss','아빠'),('alice-kis','아빠'),('alice-toss','엄마'),('deleted','모두')]:
        with pytest.raises(ValueError): preferences.set_import_default(workflow,ident,owner,'alice')
    data = portfolio.read_portfolio('alice')
    data['accounts'] = []
    portfolio.write_portfolio(data, 'alice')
    assert preferences.get_import_defaults('alice')[workflow] == 'alice-toss'  # UI must validate against current options.
    assert preferences.set_import_default(workflow,'','모두','alice') == {}
    after = bytes_state(users)
    assert before['ledger.json'] == after['ledger.json'] and before['dividend_records.json'] == after['dividend_records.json']


def test_preference_api_uses_authenticated_username_and_linked_record_api_errors(users, monkeypatch):
    main = import_main_without_loading_real_env()
    from fastapi.testclient import TestClient
    monkeypatch.setattr('app.services.user_manager.get_user_by_name', lambda name: {'username':'alice','role':'user'})
    token = main._serializer.dumps({'user':'alice','role':'user'})
    with TestClient(main.app, cookies={main.COOKIE_NAME:token}) as client:
        response = client.put('/api/ledger/preferences/transaction-defaults',json={'owner':'아빠','defaults':{'income_account_id':'bob-dad'}})
        assert response.status_code == 400
        response = client.put('/api/ledger/preferences/transaction-defaults',json={'owner':'아빠','defaults':{'income_account_id':'alice-dad'}})
        assert response.status_code == 200
        assert client.get('/api/ledger/preferences').json()['transaction_defaults']['아빠']['income_account_id'] == 'alice-dad'
        assert client.post('/api/ledger/transactions',json=payload(account_id='bob-dad')).status_code == 400
        response = client.post('/api/ledger/transactions',json=payload())
        assert response.status_code == 200
        ident = response.json()['transaction']['linked_interest_record_id']
        assert client.put(f'/api/actual-dividends/{ident}',json={'amount':99}).status_code == 400
        assert client.delete(f'/api/actual-dividends/{ident}').status_code == 400
