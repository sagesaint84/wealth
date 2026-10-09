"""Actual payments with synthetic user portfolios; no transfer execution."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading

import pytest

from app.services import portfolio, savings, savings_contributions as history
from regression_support import empty_portfolio, import_main_without_loading_real_env


@pytest.fixture
def users(tmp_path, monkeypatch):
    def directory(username=None):
        path = tmp_path / (username or 'alice')
        path.mkdir(exist_ok=True)
        return path
    monkeypatch.setattr('app.services.user_manager.get_user_data_dir', directory)
    monkeypatch.setattr('app.services.ledger.get_user_data_dir', directory)
    for user in ('alice', 'bob'):
        portfolio.write_portfolio(empty_portfolio(
            bank_accounts=[{'id':user+'-bank', 'owner':'아빠', 'account_name':'생활비', 'balance':1000000},
                           {'id':user+'-mom', 'owner':'엄마', 'account_name':'급여', 'balance':2000000},
                           {'id':user+'-all', 'owner':'모두', 'account_name':'공용', 'balance':3000000}],
            savings_accounts=[{'id':user+'-'+kind, 'saving_type':kind, 'owner':'아빠', 'product_name':kind,
                'current_paid_amount':8000000, 'monthly_amount':100000, 'target_amount':8000000,
                'interest_rate':3, 'duration_months':12, 'start_date':'2020-01-04',
                'auto_transfer_day':4, 'withdraw_account_id':user+'-bank'}
                for kind in ('installment', 'free', 'housing', 'deposit')]), user)
    return directory


def payment(**changes):
    return dict({'id':'payment-1', 'date':'2026-10-04', 'amount':100000, 'source':'manual',
                 'withdraw_account_id':'alice-bank', 'memo':'실제 납입'}, **changes)


def account(kind='housing', user='alice'):
    return next(s for s in portfolio.read_portfolio(user)['savings_accounts'] if s['id']==user+'-'+kind)


def bytes_for(users, user='alice'):
    return (users(user)/'portfolio.json').read_bytes()


@pytest.mark.parametrize('kind', ['installment','free','housing'])
def test_legacy_reads_no_migration_or_auto_then_crud_actual_total(users, kind):
    before = bytes_for(users)
    banks = deepcopy(portfolio.read_portfolio('alice')['bank_accounts'])
    for _ in range(3):
        data = savings.get_savings_data('alice')
        row = next(s for s in data['savings_accounts'] if s['id']=='alice-'+kind)
        assert row['current_value']==8000000 and row['contributions']==[]
        assert not row['contribution_history_started']
    assert bytes_for(users)==before
    first = history.create_contribution('alice-'+kind, payment(), 'alice')
    assert first['source']=='manual' and first['withdraw_account_name']=='생활비'
    assert account(kind)['contribution_opening_amount']==8000000
    assert account(kind)['current_paid_amount']==8100000
    view = next(s for s in savings.get_savings_data('alice')['savings_accounts'] if s['id']=='alice-'+kind)
    assert view['current_value']==8100000 and view['contribution_history_total']==100000
    history.create_contribution('alice-'+kind, payment(id='payment-2', date='2026-11-04'), 'alice')
    assert account(kind)['current_paid_amount']==8200000
    history.update_contribution('alice-'+kind, 'payment-2', {'amount':150000, 'memo':'수정'}, 'alice')
    assert account(kind)['current_paid_amount']==8250000
    assert sum(r['amount'] for r in account(kind)['contributions'])==250000
    history.delete_contribution('alice-'+kind, 'payment-2', 'alice')
    assert account(kind)['current_paid_amount']==8100000
    history.delete_contribution('alice-'+kind, 'payment-1', 'alice')
    assert account(kind)['contribution_opening_amount']==8000000
    assert account(kind)['contributions']==[] and account(kind)['current_paid_amount']==8000000
    assert portfolio.read_portfolio('alice')['bank_accounts']==banks


def test_product_edit_preserves_history_and_ignores_arbitrary_total(users):
    history.create_contribution('alice-housing', payment(), 'alice')
    original = account()
    payload = {k:v for k,v in original.items() if k not in {'contributions','contribution_opening_amount'}}
    result = savings.save_saving_account({**payload, 'product_name':'청약 상품 수정','interest_rate':4,
        'memo':'상품 메모', 'current_paid_amount':99999999}, 'alice')
    assert result['contributions']==original['contributions']
    assert result['contribution_opening_amount']==8000000 and result['current_paid_amount']==8100000
    assert result['product_name']=='청약 상품 수정' and result['interest_rate']==4 and result['memo']=='상품 메모'
    with pytest.raises(ValueError): savings.save_saving_account({**payload,'contributions':[]}, 'alice')
    with pytest.raises(ValueError): savings.save_saving_account({**payload,'saving_type':'deposit'}, 'alice')
    legacy = account('free')
    assert savings.save_saving_account({**legacy, 'current_paid_amount':42}, 'alice')['current_paid_amount']==42


@pytest.mark.parametrize('patch', [
    {'date':'2026-02-30'}, {'date':'2026-2-04'}, {'date':'2026-10-04x'}, {'date':'2026-10-04T00:00:00'},
    {'date':None}, {'date':20261004}, {'amount':0}, {'amount':-1}, {'amount':float('nan')},
    {'amount':float('inf')}, {'amount':-float('inf')}, {'amount':True}, {'amount':'100'},
    {'memo':None}, {'memo':{}}, {'withdraw_account_id':'bob-bank'}, {'withdraw_account_id':'alice-mom'},
    {'withdraw_account_id':'missing'}, {'withdraw_account_id':None}, {'source':'auto'}, {'source':'other'},
    {'id':''}, {'id':123},
])
def test_invalid_payment_no_write(users, patch):
    before = bytes_for(users)
    with pytest.raises(ValueError): history.create_contribution('alice-housing', payment(**patch), 'alice')
    assert bytes_for(users)==before


def test_deposit_and_unknown_or_other_user_saving_rejected(users):
    before = bytes_for(users)
    with pytest.raises(ValueError): history.create_contribution('alice-deposit', payment(), 'alice')
    for ident in ('missing','bob-housing'):
        with pytest.raises(LookupError): history.create_contribution(ident, payment(), 'alice')
    assert bytes_for(users)==before


def test_twelve_concurrent_retries_increase_once_conflicting_id_rejected(users):
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _:history.create_contribution('alice-housing',payment(),'alice'), range(12)))
    assert len({r['id'] for r in results})==1
    assert len(account()['contributions'])==1 and account()['current_paid_amount']==8100000
    before = bytes_for(users)
    with pytest.raises(history.ContributionConflict):
        history.create_contribution('alice-housing',payment(amount=150000),'alice')
    assert bytes_for(users)==before


def test_two_writers_and_concurrent_product_edit_preserve_both_updates(users):
    barrier = threading.Barrier(2)
    def add(ident, amount):
        barrier.wait()
        history.create_contribution('alice-housing',payment(id=ident,amount=amount),'alice')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(add,'A',100000),pool.submit(add,'B',200000)]
        for future in futures: future.result(timeout=15)
    assert len(account()['contributions'])==2 and account()['current_paid_amount']==8300000
    product = {k:v for k,v in account().items() if k not in {'contributions','contribution_opening_amount'}}
    barrier = threading.Barrier(2)
    def edit():
        barrier.wait()
        savings.save_saving_account({**product,'memo':'並行 상품 수정','interest_rate':5},'alice')
    def third():
        barrier.wait()
        history.create_contribution('alice-housing',payment(id='C',amount=300000),'alice')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(edit),pool.submit(third)]
        for future in futures: future.result(timeout=15)
    assert len(account()['contributions'])==3 and account()['current_paid_amount']==8600000
    assert account()['memo']=='並行 상품 수정' and account()['interest_rate']==5


def test_snapshot_survives_bank_rename_delete_and_history_edit(users):
    history.create_contribution('alice-housing',payment(),'alice')
    data = portfolio.read_portfolio('alice')
    data['bank_accounts'][0]['account_name']='이름 변경'
    portfolio.write_portfolio(data,'alice')
    assert account()['contributions'][0]['withdraw_account_name']=='생활비'
    savings.delete_bank_account('alice-bank','alice')
    assert account()['current_paid_amount']==8100000
    view = next(s for s in savings.get_savings_data('alice')['savings_accounts'] if s['id']=='alice-housing')
    assert view['contributions'][0]['withdraw_account_name']=='생활비'
    history.update_contribution('alice-housing','payment-1',{'date':'2026-10-05','memo':'메모만'},'alice')
    assert account()['contributions'][0]['withdraw_account_name']=='생활비'


def test_two_user_isolation_and_account_delete_is_local(users):
    bob_before = bytes_for(users,'bob')
    history.create_contribution('alice-housing',payment(),'alice')
    assert bytes_for(users,'bob')==bob_before
    history.create_contribution('bob-housing',payment(withdraw_account_id='bob-bank'),'bob')
    assert account(user='bob')['current_paid_amount']==8100000
    savings.delete_saving_account('alice-housing','alice')
    assert account('free')['current_paid_amount']==8000000
    assert account(user='bob')['current_paid_amount']==8100000


def test_auto_records_reserved_readable_but_not_user_mutable(users):
    history.create_contribution('alice-housing',payment(),'alice')
    data = portfolio.read_portfolio('alice')
    data['savings_accounts'][2]['contributions'][0]['source']='auto'
    portfolio.write_portfolio(data,'alice')
    before = bytes_for(users)
    assert savings.get_savings_data('alice')['savings_accounts'][2]['contributions'][0]['source']=='auto'
    with pytest.raises(ValueError): history.update_contribution('alice-housing','payment-1',{'amount':2},'alice')
    with pytest.raises(ValueError): history.delete_contribution('alice-housing','payment-1','alice')
    with pytest.raises(ValueError): history.create_contribution('alice-housing',payment(),'alice')
    assert bytes_for(users)==before


@pytest.mark.parametrize('corruption', ['list','entry','duplicate','date','amount','source','snapshot','opening'])
def test_malformed_canonical_history_fails_closed_without_normalization(users, corruption):
    history.create_contribution('alice-housing',payment(),'alice')
    data = portfolio.read_portfolio('alice'); row=data['savings_accounts'][2]
    if corruption=='list': row['contributions']={}
    elif corruption=='entry': row['contributions']=[None]
    elif corruption=='duplicate': row['contributions'].append(deepcopy(row['contributions'][0]))
    elif corruption=='opening': del row['contribution_opening_amount']
    else: row['contributions'][0][{'date':'date','amount':'amount','source':'source','snapshot':'withdraw_account_name'}[corruption]] = {'date':'bad','amount':-1,'source':'bad','snapshot':None}[corruption]
    portfolio.write_portfolio(data,'alice')
    before = bytes_for(users)
    with pytest.raises(ValueError): savings.get_savings_data('alice')
    with pytest.raises(ValueError): history.create_contribution('alice-housing',payment(id='second'),'alice')
    assert bytes_for(users)==before


def test_atomic_write_failure_preserves_bytes(users, monkeypatch):
    from app.services import secure_files
    before = bytes_for(users)
    monkeypatch.setattr(secure_files.os,'replace',lambda *args:(_ for _ in ()).throw(OSError('replace failure')))
    with pytest.raises(OSError): history.create_contribution('alice-housing',payment(),'alice')
    assert bytes_for(users)==before and not list(users('alice').glob('*.tmp'))


def test_interest_projection_and_cash_totals_use_actual_principal(users):
    expected = savings.calculate_interest('installment',100000,3,12)
    history.create_contribution('alice-installment',payment(),'alice')
    history.create_contribution('alice-housing',payment(),'alice')
    data = savings.get_savings_data('alice')
    assert data['savings_accounts'][0]['calc']==expected
    assert data['savings_accounts'][2]['calc']==savings.calculate_interest('housing',100000,3,12,current_paid_amount=8100000)
    assert data['summary']['total_savings_paid']==32200000
    assert data['summary']['total_cash_and_savings']==38200000


def test_zero_history_backed_housing_principal_does_not_fall_back_to_monthly_amount(users):
    data = portfolio.read_portfolio('alice')
    data['savings_accounts'][2]['current_paid_amount']=0
    portfolio.write_portfolio(data,'alice')
    history.create_contribution('alice-housing',payment(),'alice')
    history.delete_contribution('alice-housing','payment-1','alice')
    row=savings.get_savings_data('alice')['savings_accounts'][2]
    assert row['current_value']==row['current_paid_amount']==0
    assert row['calc']['total_principal']==0 and row['calc']['pre_tax_interest']==0


def test_authenticated_api_validation_conflict_and_two_user_scope(users, monkeypatch):
    from fastapi.testclient import TestClient
    main = import_main_without_loading_real_env()
    monkeypatch.setattr('app.services.user_manager.get_user_by_name',lambda name:{'username':'alice','role':'user'})
    token = main._serializer.dumps({'user':'alice','role':'user'})
    with TestClient(main.app,cookies={main.COOKIE_NAME:token}) as client:
        path='/api/savings-accounts/alice-housing/contributions'
        assert client.post('/api/savings-accounts/bob-housing/contributions',json=payment()).status_code==404
        assert client.post(path,json=payment(withdraw_account_id='bob-bank')).status_code==400
        assert client.post(path,json=payment(source='auto')).status_code==400
        assert client.post(path,json=payment()).status_code==200
        assert client.post(path,json=payment()).status_code==200
        assert client.post(path,json=payment(amount=150000)).status_code==409
        assert client.put(path+'/payment-1',json={'amount':150000}).status_code==200
        assert client.delete(path+'/payment-1').status_code==200
    assert account()['current_paid_amount']==8000000
