"""Scheduled savings accounting in synthetic per-user portfolios only."""
import calendar
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import threading

import pytest

from app.services import portfolio, savings, savings_contributions as history
from tests.test_savings_contributions import users, account, bytes_for, payment

KST = history.KST


def now(year=2026, month=10, day=15):
    return datetime(year, month, day, 0, 10, tzinfo=KST)


def configure(*, user='alice', kind='housing', **changes):
    data = portfolio.read_portfolio(user)
    row = next(s for s in data['savings_accounts'] if s['id'] == user+'-'+kind)
    row.update(auto_contribution_enabled=True, auto_contribution_enabled_at='2020-01-01T00:00:00+09:00',
               auto_contribution_debit_balance=True, auto_transfer_day=15)
    row.update(changes)
    portfolio.write_portfolio(data, user)
    return row


def bank(user='alice'):
    return portfolio.read_portfolio(user)['bank_accounts'][0]


def product_payload(row, **changes):
    return {**{k: v for k, v in row.items() if k not in {'contributions', 'contribution_opening_amount'}}, **changes}


@pytest.mark.parametrize('debit', [True, False])
@pytest.mark.parametrize('kind', ['installment', 'free', 'housing'])
def test_first_posting_accounting_and_identity(users, debit, kind):
    configure(kind=kind, auto_contribution_debit_balance=debit)
    before = portfolio.read_portfolio('alice')
    result = history.process_scheduled_savings_contributions('alice', now=now())
    saving = account(kind)
    assert result['status'] == 'success' and result['created_count'] == 1
    assert saving['contribution_opening_amount'] == 8000000
    assert saving['current_paid_amount'] == 8100000
    row = saving['contributions'][0]
    assert row['id'] == f'auto-saving:alice-{kind}:2026-10'
    assert row['source'] == 'auto' and row['date'] == '2026-10-15'
    assert row['amount'] == 100000 and row['withdraw_account_name'] == '생활비'
    assert row['bank_balance_debited'] is debit
    assert bank()['balance'] == 1000000 - (100000 if debit else 0)
    assert portfolio.read_portfolio('alice').get('loan_accounts') == before.get('loan_accounts')
    after = portfolio.read_portfolio('alice')
    net_worth = lambda data: sum(b['balance'] for b in data['bank_accounts']) + sum(s['current_paid_amount'] for s in data['savings_accounts'])
    assert net_worth(after) - net_worth(before) == (0 if debit else 100000)
    view = next(s for s in savings.get_savings_data('alice')['savings_accounts'] if s['id'] == saving['id'])
    assert view['current_value'] == 8100000
    before_retry = bytes_for(users)
    for _ in range(3):
        retry = history.process_scheduled_savings_contributions('alice', now=now(day=20))
        assert retry['created_count'] == 0 and retry['skipped_reasons']['ALREADY_PROCESSED'] == 1
    assert bytes_for(users) == before_retry
    for operation in (
        lambda: history.create_contribution(saving['id'], payment(id=row['id']), 'alice'),
        lambda: history.update_contribution(saving['id'], row['id'], {'amount': 1}, 'alice'),
        lambda: history.delete_contribution(saving['id'], row['id'], 'alice'),
    ):
        with pytest.raises(ValueError): operation()
    assert bytes_for(users) == before_retry


@pytest.mark.parametrize('year,month', [(2026, 2), (2028, 2), (2026, 4), (2026, 10)])
@pytest.mark.parametrize('day', [1, 15, 28, 29, 30, 31])
@pytest.mark.parametrize('offset', [-1, 0, 1])
def test_due_calendar_matrix_current_month_only(users, year, month, day, offset):
    configure(auto_transfer_day=day)
    due = datetime(year, month, min(day, calendar.monthrange(year, month)[1]), 0, 10, tzinfo=KST)
    when = due + timedelta(days=offset)
    before = bytes_for(users)
    result = history.process_scheduled_savings_contributions('alice', now=when)
    actual_due = min(day, calendar.monthrange(when.year, when.month)[1])
    eligible = when.day >= actual_due
    assert result['created_count'] == int(eligible)
    if eligible:
        rows = account()['contributions']
        assert len(rows) == 1
        assert rows[0]['id'] == f"auto-saving:alice-housing:{when:%Y-%m}"
        assert rows[0]['date'] == f'{when.year:04}-{when.month:02}-{actual_due:02}'
    else:
        assert bytes_for(users) == before


@pytest.mark.parametrize('enabled_day,run_day,created', [(10, 15, 1), (15, 15, 1), (16, 20, 0)])
def test_activation_date_no_current_month_catchup(users, enabled_day, run_day, created):
    configure(auto_contribution_enabled_at=now(day=enabled_day).isoformat())
    result = history.process_scheduled_savings_contributions('alice', now=now(day=run_day))
    assert result['created_count'] == created
    if not created:
        assert result['skipped_reasons']['ENABLED_AFTER_DUE'] == 1
        assert history.process_scheduled_savings_contributions('alice', now=now(month=11))['created_count'] == 1
        assert len(account()['contributions']) == 1


@pytest.mark.parametrize('field,value,created', [
    ('start_date', '2026-10-16', 0), ('start_date', '2026-10-15', 1),
    ('end_date', '2026-10-14', 0), ('end_date', '2026-10-15', 1), ('end_date', '', 1),
])
def test_start_end_inclusive(users, field, value, created):
    configure(**{field: value})
    assert history.process_scheduled_savings_contributions('alice', now=now())['created_count'] == created


def test_legacy_disabled_reads_and_processing_never_write(users):
    before = bytes_for(users)
    for _ in range(3):
        savings.get_savings_data('alice')
        result = history.process_scheduled_savings_contributions('alice', now=now())
        assert result['created_count'] == 0
    assert bytes_for(users) == before
    assert 'auto_contribution_enabled_at' not in account()
    with pytest.raises(ValueError): history.process_scheduled_savings_contributions('alice', now=datetime(2026, 10, 15))
    assert bytes_for(users) == before
    utc = now().astimezone(timezone.utc)
    configure()
    assert history.process_scheduled_savings_contributions('alice', now=utc)['created_count'] == 1


def test_enable_preserve_disable_reenable_backend_time(users, monkeypatch):
    real_now = history._kst_now
    clock = [now(day=10)]
    monkeypatch.setattr(history, '_kst_now', lambda value=None: real_now(clock[0] if value is None else value))
    row = savings.save_saving_account(product_payload(account(), auto_contribution_enabled=True,
        auto_contribution_debit_balance=False, auto_transfer_day=15,
        auto_contribution_enabled_at='1900-01-01T00:00:00+09:00'), 'alice')
    assert row['auto_contribution_enabled_at'] == clock[0].isoformat()
    assert not row['auto_contribution_debit_balance']
    assert 'contributions' not in row and bank()['balance'] == 1000000
    clock[0] = now(day=12)
    row = savings.save_saving_account(product_payload(row, memo='수정', auto_contribution_debit_balance=True), 'alice')
    assert row['auto_contribution_enabled_at'] == now(day=10).isoformat()
    row = savings.save_saving_account(product_payload(row, auto_contribution_enabled=False), 'alice')
    assert 'auto_contribution_enabled_at' not in row
    clock[0] = now(day=16)
    row = savings.save_saving_account(product_payload(row, auto_contribution_enabled=True), 'alice')
    assert row['auto_contribution_enabled_at'] == clock[0].isoformat()
    assert history.process_scheduled_savings_contributions('alice', now=now(day=20))['created_count'] == 0


@pytest.mark.parametrize('changes', [
    {'saving_type': 'deposit'}, {'monthly_amount': 0}, {'monthly_amount': -1},
    {'monthly_amount': True}, {'monthly_amount': '100000'}, {'monthly_amount': float('nan')},
    {'monthly_amount': float('inf')}, {'monthly_amount': float('-inf')},
    {'auto_transfer_day': 0}, {'auto_transfer_day': 32}, {'auto_transfer_day': True},
    {'auto_transfer_day': 15.5}, {'auto_transfer_day': '15'},
    {'withdraw_account_id': ''}, {'withdraw_account_id': 'missing'},
    {'withdraw_account_id': 'bob-bank'}, {'withdraw_account_id': 'alice-mom'},
    {'auto_contribution_enabled': 1}, {'auto_contribution_debit_balance': 0},
    {'auto_contribution_debit_balance': None},
])
def test_optin_invalid_configuration_rejected_without_write(users, changes):
    before = bytes_for(users)
    payload = product_payload(account(), auto_contribution_enabled=True, auto_contribution_debit_balance=True)
    with pytest.raises((ValueError, TypeError, OverflowError)):
        savings.save_saving_account({**payload, **changes}, 'alice')
    assert bytes_for(users) == before


def test_currency_validation_both_modes_and_owner_all(users):
    data = portfolio.read_portfolio('alice')
    data['bank_accounts'][0]['currency'] = 'USD'
    portfolio.write_portfolio(data, 'alice')
    for debit in (True, False):
        with pytest.raises(ValueError):
            savings.save_saving_account(product_payload(account(), auto_contribution_enabled=True,
                auto_contribution_debit_balance=debit), 'alice')
    configure(owner='모두', withdraw_account_id='alice-mom')
    assert history.process_scheduled_savings_contributions('alice', now=now())['created_count'] == 1


def test_insufficient_funds_retry_no_overdraft_no_other_financial_file(users):
    configure(monthly_amount=1000001)
    before = bytes_for(users)
    result = history.process_scheduled_savings_contributions('alice', now=now())
    assert result['status'] == 'success' and result['skipped_reasons']['INSUFFICIENT_FUNDS'] == 1
    assert bytes_for(users) == before
    data = portfolio.read_portfolio('alice')
    data['bank_accounts'][0]['balance'] = 2000000
    portfolio.write_portfolio(data, 'alice')
    assert history.process_scheduled_savings_contributions('alice', now=now(day=20))['created_count'] == 1
    assert bank()['balance'] == 999999
    assert not (users('alice')/'ledger.json').exists()
    assert not (users('alice')/'dividend_records.json').exists()


def test_record_authority_after_settings_change_snapshot_and_bank_delete(users):
    configure()
    history.process_scheduled_savings_contributions('alice', now=now())
    original = deepcopy(account()['contributions'])
    configure(monthly_amount=200000, auto_contribution_debit_balance=False,
              withdraw_account_id='alice-all')
    before = bytes_for(users)
    assert history.process_scheduled_savings_contributions('alice', now=now(day=20))['created_count'] == 0
    assert bytes_for(users) == before and account()['contributions'] == original
    for debit in (True, False):
        configure(auto_contribution_debit_balance=debit, withdraw_account_id='alice-bank')
        with pytest.raises(ValueError): savings.delete_bank_account('alice-bank', 'alice')
    configure(auto_contribution_enabled=False)
    assert savings.delete_bank_account('alice-bank', 'alice')
    assert account()['contributions'] == original and account()['current_paid_amount'] == 8100000


def test_bank_rename_new_month_and_manual_same_date_not_deduplicated(users):
    configure()
    history.create_contribution('alice-housing', payment(date='2026-10-15'), 'alice')
    history.process_scheduled_savings_contributions('alice', now=now())
    savings.save_bank_account({**bank(), 'account_name': '새 표시명'}, 'alice')
    history.process_scheduled_savings_contributions('alice', now=now(month=11))
    rows = account()['contributions']
    assert len(rows) == 3 and [r['withdraw_account_name'] for r in rows] == ['생활비', '생활비', '새 표시명']
    assert bank()['balance'] == 800000 and account()['current_paid_amount'] == 8300000


@pytest.mark.parametrize('failure', ['manual_collision', 'duplicate', 'bad_debit', 'bad_source'])
def test_corrupt_existing_identity_fail_closed(users, failure):
    configure()
    history.create_contribution('alice-housing', payment(id='auto-saving:alice-housing:2026-10'), 'alice')
    data = portfolio.read_portfolio('alice')
    row = next(s for s in data['savings_accounts'] if s['id'] == 'alice-housing')
    if failure == 'duplicate': row['contributions'].append(deepcopy(row['contributions'][0]))
    if failure == 'bad_debit': row['contributions'][0]['bank_balance_debited'] = 'true'
    if failure == 'bad_source': row['contributions'][0]['source'] = 'unknown'
    portfolio.write_portfolio(data, 'alice')
    before = bytes_for(users)
    with pytest.raises(ValueError): history.process_scheduled_savings_contributions('alice', now=now())
    assert bytes_for(users) == before


@pytest.mark.parametrize('target', ['write', 'replace'])
def test_failed_commit_preserves_bytes_and_no_temp_or_partial_event(users, monkeypatch, target):
    configure()
    before = bytes_for(users)
    def fail(*args, **kwargs): raise OSError('injected')
    if target == 'write': monkeypatch.setattr(history, 'write_portfolio', fail)
    else: monkeypatch.setattr('app.services.financial_json.os.replace', fail)
    with pytest.raises(OSError): history.process_scheduled_savings_contributions('alice', now=now())
    assert bytes_for(users) == before
    assert not list(users('alice').glob('*.tmp'))


def test_twelve_concurrent_processors_exactly_one_event_and_two_user_isolation(users):
    configure()
    bob_before = bytes_for(users, 'bob')
    barrier = threading.Barrier(12)
    def run(_):
        barrier.wait(timeout=10)
        return history.process_scheduled_savings_contributions('alice', now=now())
    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(run, range(12)))
    assert sum(r['created_count'] for r in results) == 1
    assert bank()['balance'] == 900000 and len(account()['contributions']) == 1
    assert bytes_for(users, 'bob') == bob_before
    configure(user='bob')
    history.process_scheduled_savings_contributions('bob', now=now())
    assert account(user='bob')['current_paid_amount'] == 8100000
    assert bank('bob')['balance'] == 900000


def test_concurrent_manual_and_product_edit_preserve_all_changes(users):
    configure()
    payload = product_payload(account(), memo='동시 상품 수정', interest_rate=4)
    other_bank = portfolio.read_portfolio('alice')['bank_accounts'][1]
    barrier = threading.Barrier(4)
    operations = [lambda: history.process_scheduled_savings_contributions('alice', now=now()),
                  lambda: history.create_contribution('alice-housing', payment(amount=200000), 'alice'),
                  lambda: savings.save_saving_account(payload, 'alice'),
                  lambda: savings.save_bank_account({**other_bank, 'account_name': '동시 통장 수정'}, 'alice')]
    def run(operation):
        barrier.wait(timeout=10)
        return operation()
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(run, operations))
    saving = account()
    assert len(saving['contributions']) == 2 and saving['current_paid_amount'] == 8300000
    assert saving['memo'] == '동시 상품 수정' and saving['interest_rate'] == 4
    assert bank()['balance'] == 900000
    assert portfolio.read_portfolio('alice')['bank_accounts'][1]['account_name'] == '동시 통장 수정'


def test_multiple_products_share_cash_and_bad_second_product_never_partially_commits(users):
    configure(kind='housing')
    configure(kind='installment')
    configure(kind='free', auto_transfer_day=0)
    before = bytes_for(users)
    with pytest.raises(ValueError): history.process_scheduled_savings_contributions('alice', now=now())
    assert bytes_for(users) == before
    configure(kind='free', auto_contribution_enabled=False)
    result = history.process_scheduled_savings_contributions('alice', now=now())
    assert result['created_count'] == 2 and bank()['balance'] == 800000
    assert account('housing')['current_paid_amount'] == account('installment')['current_paid_amount'] == 8100000


def test_debit_off_does_not_require_available_cash_or_create_loan(users):
    configure(auto_contribution_debit_balance=False)
    data = portfolio.read_portfolio('alice')
    data['bank_accounts'][0]['balance'] = 0
    data['loan_accounts'] = [{'id': 'existing-loan', 'balance': 123456}]
    portfolio.write_portfolio(data, 'alice')
    before_banks = deepcopy(data['bank_accounts'])
    before_loans = deepcopy(data['loan_accounts'])
    result = history.process_scheduled_savings_contributions('alice', now=now())
    assert result['created_count'] == 1
    after = portfolio.read_portfolio('alice')
    assert after['bank_accounts'] == before_banks and after['loan_accounts'] == before_loans
    assert account()['current_paid_amount'] == 8100000


def test_missing_user_portfolio_no_bootstrap(users):
    path = users('registered-empty')/'portfolio.json'
    assert history.process_scheduled_savings_contributions('registered-empty', now=now())['created_count'] == 0
    assert not path.exists()
    with pytest.raises(ValueError): history.process_scheduled_savings_contributions(None, now=now())
