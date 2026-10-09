import copy
import json
import threading

from fastapi.testclient import TestClient
import pytest

from app import main
from app.services import portfolio
from app.services.account_display_order import effective_order, institution_key


@pytest.fixture
def users(tmp_path, monkeypatch):
    monkeypatch.setattr(portfolio, '_get_user_dir', lambda username=None: tmp_path / (username or 'default'))
    monkeypatch.setattr('app.services.user_manager.get_user_by_name',
                        lambda name: {'username': name, 'id': name, 'role': 'user'})
    data = copy.deepcopy(portfolio.EMPTY_PORTFOLIO)
    data['accounts'] = [dict(id=f'A{i}', broker='KB증권', name=f'계좌{i}', owner='아빠' if i % 2 else '엄마', cash_krw=i) for i in range(1, 5)] + [dict(id='B1', broker='토스증권', cash_krw=10)]
    for kind in ('bank_accounts', 'savings_accounts', 'loan_accounts'):
        data[kind] = [dict(id=f'{kind}-{i}', bank_name='국민은행' if i < 3 else '신한은행', balance=-i, limit_amount=100) for i in range(1, 4)]
    data['holdings'] = [{'id': 'holding', 'quantity': 20}]
    for user in ('alice', 'bob'):
        portfolio.write_portfolio(copy.deepcopy(data), user)
    client = TestClient(main.app)
    client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({'user': 'alice'}))
    return client, data


def test_natural_orders_and_user_isolation_and_financial_arrays_unchanged(users):
    client, original = users
    before = portfolio.read_portfolio('alice')
    result = client.get('/api/account-display-order').json()
    kb, toss = institution_key('KB증권', 'securities'), institution_key('토스증권', 'securities')
    assert result['securities']['institutions'] == [kb, toss]
    assert result['securities']['accounts'][kb] == ['A1', 'A2', 'A3', 'A4']
    assert result['securities']['labels'][kb] == 'KB증권'
    assert client.patch('/api/account-display-order', json={'scope': 'securities', 'level': 'institutions', 'order': ['토스증권', 'KB증권']}).status_code == 200
    assert client.get('/api/account-display-order').json()['securities']['institutions'] == [toss, kb]
    for kind in ('accounts', 'holdings', 'bank_accounts', 'savings_accounts', 'loan_accounts'):
        assert portfolio.read_portfolio('alice')[kind] == before[kind]
    client.cookies.set(main.COOKIE_NAME, main._serializer.dumps({'user': 'bob'}))
    assert client.get('/api/account-display-order').json()['securities']['institutions'] == [kb, toss]
    assert 'account_display_order' not in portfolio.read_portfolio('bob')['settings']


def test_owner_subset_positions_preserve_hidden_entries_and_new_deleted_cleanup(users):
    client, _ = users
    operation = dict(scope='securities', level='accounts', institution='KB증권', order=['A3', 'A1'])
    result = client.patch('/api/account-display-order', json=operation)
    assert result.status_code == 200
    kb = institution_key('KB증권', 'securities')
    assert result.json()['securities']['accounts'][kb] == ['A3', 'A2', 'A1', 'A4']
    data = portfolio.read_portfolio('alice')
    data['accounts'].append(dict(id='A5', broker='KB증권'))
    data['accounts'] = [row for row in data['accounts'] if row['id'] != 'A2']
    portfolio.write_portfolio(data, 'alice')
    assert client.get('/api/account-display-order').json()['securities']['accounts'][kb] == ['A3', 'A1', 'A4', 'A5']


@pytest.mark.parametrize('kind', ['bank_accounts', 'savings_accounts', 'loan_accounts'])
def test_banking_kind_order_and_cross_bank_rejection(users, kind):
    client, _ = users
    operation = dict(scope='banking', level='accounts', kind=kind, institution='국민은행',
                     order=[f'{kind}-2', f'{kind}-1'])
    response = client.patch('/api/account-display-order', json=operation)
    assert response.status_code == 200
    assert response.json()['banking'][kind]['국민은행'] == operation['order']
    operation['order'] = [f'{kind}-3']
    assert client.patch('/api/account-display-order', json=operation).status_code == 400


def test_institution_partial_merge_and_banking_shared_order(users):
    client, _ = users
    data = portfolio.read_portfolio('alice')
    data['bank_accounts'].append(dict(id='third', bank_name='우리은행'))
    portfolio.write_portfolio(data, 'alice')
    result = client.patch('/api/account-display-order', json=dict(scope='banking', level='institutions', order=['우리은행', '국민은행']))
    assert result.status_code == 200
    assert result.json()['banking']['institutions'] == ['우리은행', '신한은행', '국민은행']


def test_broker_aliases_and_bank_whitespace_share_identity_preserve_labels(users):
    _, data = users
    data['accounts'].append(dict(id='alias', broker='KB'))
    data['bank_accounts'].append(dict(id='space', bank_name=' 국민은행 '))
    result = effective_order(data)
    kb = institution_key('KB증권', 'securities')
    assert len(result['securities']['institutions']) == 2
    assert result['securities']['accounts'][kb][-1] == 'alias'
    assert result['securities']['labels'][kb] == 'KB증권'
    assert result['securities']['aliases']['KB'] == kb
    assert result['banking']['bank_accounts']['국민은행'][-1] == 'space'


@pytest.mark.parametrize('payload', [
    dict(scope='securities', level='accounts', institution='KB증권', order=['B1']),
    dict(scope='securities', level='accounts', institution='KB증권', order=['unknown']),
    dict(scope='securities', level='accounts', institution='KB증권', order=['A1', 'A1']),
    dict(scope='securities', level='institutions', order=['unknown']),
    dict(scope='securities', level='institutions', order=['KB증권', 'kb']),
    dict(scope='insurance', level='institutions', order=['x']),
    dict(scope='banking', level='accounts', kind='accounts', institution='국민은행', order=['A1']),
    dict(scope='securities', level='accounts', institution='unknown', order=['A1']),
    dict(scope='banking', level='institutions', order=[]),
    dict(scope='banking', level='institutions', order=['국민은행'] * 2001),
    dict(scope='securities', level='institutions', order=[{}]),
    dict(scope=[], level='institutions', order=['x']),
    dict(scope='securities', level='accounts', institution='KB증권', order=['A1'], owner='other'),
    [], None,
])
def test_invalid_operations_rejected_without_any_write(users, payload):
    client, _ = users
    before = portfolio.read_portfolio('alice')
    assert client.patch('/api/account-display-order', json=payload).status_code == 400
    assert portfolio.read_portfolio('alice') == before


def test_authentication_malformed_json_and_body_limit(users):
    client, _ = users
    assert client.patch('/api/account-display-order', content='{').status_code == 400
    assert client.patch('/api/account-display-order', content=' ' * 256001).status_code == 413
    client.cookies.clear()
    assert client.get('/api/account-display-order').status_code == 401
    assert client.patch('/api/account-display-order', json={}).status_code == 401


def test_stale_financial_writer_preserves_order_and_planning(users):
    client, _ = users
    stale = portfolio.read_portfolio('alice')
    latest = copy.deepcopy(stale)
    latest['settings']['wealth_planning'] = {'version': 1, 'saved': 'new'}
    portfolio.write_portfolio(latest, 'alice', replace_planning=True)
    assert client.patch('/api/account-display-order', json=dict(scope='securities', level='accounts', institution='KB증권', order=['A4', 'A1'])).status_code == 200
    saved = portfolio.read_portfolio('alice')['settings']['account_display_order']
    stale['accounts'][0]['cash_krw'] = 123
    portfolio.write_portfolio(stale, 'alice')
    current = portfolio.read_portfolio('alice')
    assert current['settings']['account_display_order'] == saved
    assert current['settings']['wealth_planning'] == {'version': 1, 'saved': 'new'}
    assert current['accounts'][0]['cash_krw'] == 123


def test_order_edit_preserves_financial_timestamp_and_unrelated_raw_metadata(users):
    client, _ = users
    path = portfolio._get_portfolio_file('alice')
    original = json.loads(path.read_text(encoding='utf-8'))
    original['updated_at'] = '2026-01-01T12:00:00+09:00'
    original['settings']['daily_snapshot'] = {}
    original['settings']['wealth_planning'] = {'version': 1, 'saved': 'retain'}
    path.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
    assert client.patch('/api/account-display-order', json=dict(scope='securities', level='accounts', institution='KB증권', order=['A4', 'A1'])).status_code == 200
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['settings'].pop('account_display_order')['version'] == 1
    assert saved == original


@pytest.mark.parametrize('malformed', [None, [], 'bad', {'version': 9}, {'version': True}, {'version': 1, 'securities': []},
    {'version': 1, 'securities': {'institutions': {}, 'accounts': {'kb': [[], 'stale']}}}])
def test_malformed_preference_falls_back_and_never_creates_synthetic_overdraft(users, malformed):
    _, data = users
    data['settings']['account_display_order'] = malformed
    result = effective_order(data)
    kb = institution_key('KB증권', 'securities')
    assert result['securities']['accounts'][kb] == ['A1', 'A2', 'A3', 'A4']
    assert result['banking']['loan_accounts']['국민은행'] == ['loan_accounts-1', 'loan_accounts-2']
    assert not any(identity.startswith('bank_accounts') for ids in result['banking']['loan_accounts'].values() for identity in ids)


def test_ambiguous_duplicate_identity_across_institutions_is_rejected(users):
    from app.services.account_display_order import apply_operation
    _, data = users
    data['accounts'].append(dict(id='A1', broker='토스증권'))
    with pytest.raises(ValueError):
        apply_operation(data, dict(scope='securities', level='accounts', institution='KB증권', order=['A1']))


def test_reorder_transaction_holds_portfolio_lock_through_read_validation_write(users):
    from app.services.account_display_order import patch_account_display_order
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    stale = portfolio.read_portfolio('alice')
    def reorder():
        with portfolio.financial_lock(portfolio._get_portfolio_file("alice")):
            entered.set()
            assert release.wait(5)
            patch_account_display_order('alice', dict(scope='securities', level='accounts', institution='KB증권', order=['A4', 'A1']))
    def financial():
        portfolio.write_portfolio(stale, 'alice')
        finished.set()
    first = threading.Thread(target=reorder); first.start(); assert entered.wait(5)
    second = threading.Thread(target=financial); second.start()
    assert not finished.is_set()
    release.set(); first.join(5); second.join(5)
    assert not first.is_alive() and not second.is_alive()
    kb = institution_key('KB증권', 'securities')
    assert effective_order(portfolio.read_portfolio('alice'))['securities']['accounts'][kb] == ['A4', 'A2', 'A3', 'A1']
