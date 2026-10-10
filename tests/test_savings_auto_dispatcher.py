"""Reuse the dispatcher claims/retry/stale recovery for scheduled savings."""
import asyncio
from datetime import timedelta
import json

import pytest

from app.services.automation import dispatcher, execution_state as state
from tests.test_savings_auto_contributions import configure, now, account, bank
from tests.test_savings_contributions import users, bytes_for


@pytest.fixture
def scheduler(users, tmp_path, monkeypatch):
    monkeypatch.setenv('WEALTH_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(dispatcher, 'list_users', lambda: [{'username': 'bob'}, {'username': 'alice'}])
    monkeypatch.setattr(dispatcher, 'resolve_global_automation_owner', lambda **kwargs: None)
    monkeypatch.setattr(dispatcher, 'get_effective_system_settings', lambda: {})
    monkeypatch.setattr(dispatcher, 'get_effective_settings', lambda username: {'automation': {}})
    # Any unrelated service dispatch during the savings minute is a regression.
    def forbidden(*args, **kwargs): raise AssertionError('unrelated provider/job invoked')
    for name in ('run_daily_close_for_user', 'run_account_pre_sync_for_user',
                 'refresh_ipo_market_enriched', 'run_ipo_subscription_reminders',
                 'run_ipo_listing_reminders', 'run_toss_session_maintenance'):
        monkeypatch.setattr(dispatcher, name, forbidden)
    return tmp_path/'automation'/'execution_state.json'


def jobs(result):
    return [j for j in result['jobs'] if j['job'] == 'savings_auto_contribution']


def test_fixed_minute_sorted_users_dryrun_no_financial_write(scheduler, users):
    alice = bytes_for(users)
    bob = bytes_for(users, 'bob')
    result = asyncio.run(dispatcher.run_due_automation(now=now(), dry_run=True, state_path=scheduler))
    rows = jobs(result)
    assert [r['username'] for r in rows] == ['alice', 'bob']
    assert all(r['scheduled_time'] == '00:10' and r['scope'] == 'user' for r in rows)
    for minute in (-1, 1):
        assert jobs(asyncio.run(dispatcher.run_due_automation(now=now()+timedelta(minutes=minute),
                    dry_run=True, state_path=scheduler))) == []
    assert bytes_for(users) == alice and bytes_for(users, 'bob') == bob
    assert not scheduler.exists()


def test_claim_dedup_optin_user_isolation_and_successful_noop(scheduler, users):
    configure()
    bob = bytes_for(users, 'bob')
    first = jobs(asyncio.run(dispatcher.run_due_automation(now=now(), state_path=scheduler)))
    assert [r['status'] for r in first] == ['success', 'success']
    assert [r['details']['created_count'] for r in first] == [1, 0]
    second = jobs(asyncio.run(dispatcher.run_due_automation(now=now(), state_path=scheduler)))
    assert all(r['status'] == 'skipped' and r['reason'] == 'ALREADY_SUCCESS' for r in second)
    assert bank()['balance'] == 900000 and len(account()['contributions']) == 1
    assert bytes_for(users, 'bob') == bob
    records = state.load_execution_state(scheduler)['executions']
    assert all(r['status'] == 'SUCCESS' for r in records.values())


def test_expected_insufficient_success_next_daily_recheck(scheduler):
    configure(monthly_amount=1000001)
    result = jobs(asyncio.run(dispatcher.run_due_automation(now=now(), state_path=scheduler)))[0]
    assert result['status'] == 'success'
    assert result['details']['skipped_reasons']['INSUFFICIENT_FUNDS'] == 1
    result = jobs(asyncio.run(dispatcher.run_due_automation(now=now(day=16), state_path=scheduler)))[0]
    assert result['status'] == 'success' and result['details']['created_count'] == 0
    assert bank()['balance'] == 1000000


def test_real_failure_secret_safe_retry_reuses_existing_state(scheduler, users):
    configure()
    before = bytes_for(users)
    def failing(user, *, now): raise OSError('secret-account-number=123 credential=private')
    result = asyncio.run(dispatcher.run_due_automation(now=now(), state_path=scheduler, savings_auto_runner=failing))
    assert all(r['status'] == 'failed' for r in jobs(result))
    assert 'private' not in json.dumps(result) and '123' not in scheduler.read_text()
    assert bytes_for(users) == before
    result = jobs(asyncio.run(dispatcher.run_due_automation(now=now()+timedelta(minutes=1), state_path=scheduler)))
    assert len(result) == 2 and all(r['status'] == 'success' and r['is_retry'] for r in result)
    assert bank()['balance'] == 900000
    assert all(r['attempt_count'] == 2 for r in state.load_execution_state(scheduler)['executions'].values())


def test_stale_claim_after_financial_commit_does_not_double_post(scheduler):
    configure()
    row = next(r for r in dispatcher.resolve_due_jobs(now(), state_path=scheduler) if r.get('username') == 'alice')
    state.claim_execution(key=row['execution_key'], job_descriptor=row, now=now(), state_path=scheduler)
    from app.services.savings_contributions import process_scheduled_savings_contributions
    process_scheduled_savings_contributions('alice', now=now())
    # Simulates a crash after portfolio replace but before execution-state SUCCESS.
    result = jobs(asyncio.run(dispatcher.run_due_automation(now=now()+timedelta(minutes=16), state_path=scheduler)))
    assert len(result) == 1 and result[0]['status'] == 'success'
    assert result[0]['details']['skipped_reasons']['ALREADY_PROCESSED'] == 1
    assert bank()['balance'] == 900000 and len(account()['contributions']) == 1


def test_previous_month_retry_only_evaluates_current_month(scheduler):
    configure()
    previous = now(month=9, day=30)
    row = next(r for r in dispatcher.resolve_due_jobs(previous, state_path=scheduler) if r.get('username') == 'alice')
    state.claim_execution(key=row['execution_key'], job_descriptor=row, now=previous, state_path=scheduler)
    state.record_execution_failure(key=row['execution_key'], now=previous, error_code='WRITE_FAILURE', state_path=scheduler)
    result = jobs(asyncio.run(dispatcher.run_due_automation(now=now(day=1)+timedelta(minutes=1), state_path=scheduler)))
    assert result == []  # Existing execution-state contract retries only today's claims.
    assert 'contributions' not in account()
    # Even an explicitly supplied old descriptor evaluates today's month only.
    replay = asyncio.run(dispatcher.execute_job(row, now=now()))
    assert replay['status'] == 'success'
    assert [r['id'] for r in account()['contributions']] == ['auto-saving:alice-housing:2026-10']


def test_product_schedule_independent_of_corrupt_unrelated_user_settings(scheduler, monkeypatch):
    def corrupt(username): raise ValueError('settings corrupt')
    monkeypatch.setattr(dispatcher, 'get_effective_settings', corrupt)
    rows = jobs(asyncio.run(dispatcher.run_due_automation(now=now(), dry_run=True, state_path=scheduler)))
    assert [r['username'] for r in rows] == ['alice', 'bob']


def test_status_recent_projection_user_scoped_and_secret_safe(scheduler, monkeypatch):
    from app.services.automation import status
    configure()
    asyncio.run(dispatcher.run_due_automation(now=now(), state_path=scheduler))
    monkeypatch.setattr(status, 'get_effective_system_settings', lambda: {})
    monkeypatch.setattr(status, 'resolve_toss_wts_settings', lambda: {})
    projected = status.build_automation_status('alice', settings={'automation': {}}, now=now(), state_path=scheduler)
    rows = [r for r in projected['recent'] if r['job'] == 'savings_auto_contribution']
    assert len(rows) == 1 and rows[0]['label'] == '예·적금 자동납입 확인'
    assert rows[0]['details'] == {'created_count': 1, 'skipped_count': 3}
    assert 'created_ids' not in rows[0]['details']
    assert 'alice-housing' not in json.dumps(projected, ensure_ascii=False)
