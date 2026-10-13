"""Synthetic annual payments; never load real user or provider data."""
from copy import deepcopy
from datetime import date

import pytest

from app.services import portfolio, savings, user_manager
from app.services.test_safety import assert_write_allowed
from regression_support import empty_portfolio


@pytest.fixture
def users(tmp_path, monkeypatch):
    root = tmp_path / 'users'
    def directory(username=None):
        user = username or 'alice'
        if user not in ('alice', 'bob'):
            raise AssertionError('Unexpected synthetic user')
        path = root / user
        assert_write_allowed(path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def portfolio_file(username=None):
        return directory(username) / 'portfolio.json'

    # Patch the actual resolution boundaries, not only a root that a previous
    # test's replacement resolver might ignore. Canonical RMW locks and real
    # readers/writers continue to operate on the same synthetic file.
    monkeypatch.setenv('WEALTH_ENV', 'test')
    monkeypatch.setattr(user_manager, 'USERS_DIR', root)
    monkeypatch.setattr(user_manager, 'get_user_data_dir', directory)
    monkeypatch.setattr(portfolio, '_get_user_dir', directory)
    monkeypatch.setattr(portfolio, '_get_portfolio_file', portfolio_file)
    monkeypatch.setattr(savings, 'read_portfolio', portfolio.read_portfolio)
    monkeypatch.setattr(savings, 'write_portfolio', portfolio.write_portfolio)
    for user in ('alice', 'bob'):
        portfolio.write_portfolio(empty_portfolio(insurance_accounts=[
            dict(id=user+'-np', insurance_type='national_pension', owner='아빠',
                 product_name='국민연금', total_paid_amount=8000000, monthly_payout=100000,
                 payout_type='monthly_pension', payout_duration_years=20,
                 expected_amount=24000000, converted_total_asset=24000000,
                 maturity_date='2045-01-01', yearly_contributions=[]),
            dict(id=user+'-mom', insurance_type='national_pension', owner='엄마',
                 total_paid_amount=1000000, expected_amount=1000000),
            dict(id=user+'-yu', insurance_type='yellow_umbrella', owner='아빠',
                 product_name='노란우산', monthly_premium=100000, total_paid_amount=1000000,
                 expected_amount=1000000, income_bracket='40m_to_100m',
                 marginal_tax_rate=26.4, yearly_contributions=[dict(year='2013',deposit=50000,is_deductible=False)]),
        ]), user)
        expected = root / user / 'portfolio.json'
        assert portfolio._get_portfolio_file(user) == expected
        assert expected.is_file(), 'Synthetic writer and fixture must use the same portfolio path'
        assert portfolio.read_portfolio(user)['insurance_accounts'][0]['id'] == user+'-np'
    return root


def test_annual_crud_round_trip_preserves_all_financial_fields_and_other_users(users):
    before = portfolio.read_portfolio('alice')
    bob_bytes = (users / 'bob/portfolio.json').read_bytes()
    view_before = savings.get_savings_data('alice')
    records = [dict(year='2013',deposit=120000), dict(year='2015',deposit=0),
               dict(year=str(date.today().year),deposit=10000)]
    original = deepcopy(before['insurance_accounts'][0])
    result = savings.save_national_pension_history('alice-np', records, 'alice', expected_history=[])
    assert result['yearly_contributions'] == records
    assert '2014' not in {row['year'] for row in result['yearly_contributions']}
    assert next(row for row in records if row['year']=='2015')['deposit'] == 0
    assert {key:value for key,value in result.items() if key!='yearly_contributions'} == {
        key:value for key,value in original.items() if key!='yearly_contributions'}
    assert portfolio.read_portfolio('alice')['insurance_accounts'][1:] == before['insurance_accounts'][1:]
    assert (users / 'bob/portfolio.json').read_bytes() == bob_bytes
    view_after = savings.get_savings_data('alice')
    assert view_after['summary'] == view_before['summary']
    assert view_after['insurance_accounts'][2]['tax_benefit'] == view_before['insurance_accounts'][2]['tax_benefit']
    updated = [dict(year='2013',deposit=150000), dict(year='2015',deposit=0)]
    savings.save_national_pension_history('alice-np', updated, 'alice', expected_history=records)
    assert portfolio.read_portfolio('alice')['insurance_accounts'][0]['yearly_contributions'] == updated
    savings.save_national_pension_history('alice-np', [], 'alice', expected_history=updated)
    assert portfolio.read_portfolio('alice')['insurance_accounts'][0]['total_paid_amount'] == 8000000
    assert portfolio.read_portfolio('alice')['insurance_accounts'][0]['yearly_contributions'] == []


@pytest.mark.parametrize('records', [None, {}, [None], [dict(year='2013')],
    [dict(year='2013',deposit=-1)], [dict(year='2013',deposit=float('nan'))],
    [dict(year='2013',deposit=float('inf'))], [dict(year='2013',deposit=True)],
    [dict(year='2013',deposit=0),dict(year=2013,deposit=10)],
    [dict(year='13',deposit=1)], [dict(year='2013.0',deposit=1)],
    [dict(year='1987',deposit=1)], [dict(year=str(date.today().year+1),deposit=1)]])
def test_invalid_history_rejected_without_any_write(users, records):
    before = (users / 'alice/portfolio.json').read_bytes()
    with pytest.raises(ValueError): savings.save_national_pension_history('alice-np', records, 'alice')
    assert (users / 'alice/portfolio.json').read_bytes() == before


def test_user_boundary_yellow_umbrella_and_stale_edits_are_rejected(users):
    before = (users / 'alice/portfolio.json').read_bytes()
    with pytest.raises(LookupError): savings.save_national_pension_history('bob-np', [], 'alice')
    with pytest.raises(ValueError): savings.save_national_pension_history('alice-yu', [], 'alice')
    with pytest.raises(savings.NationalPensionHistoryConflict):
        savings.save_national_pension_history('alice-np', [], 'alice', expected_history=[dict(year='2013',deposit=1)])
    assert (users / 'alice/portfolio.json').read_bytes() == before


def test_regular_product_edit_keeps_history_if_omitted_and_validates_explicit_history(users):
    records = [dict(year='2013',deposit=100)]
    savings.save_national_pension_history('alice-np', records, 'alice')
    item = portfolio.read_portfolio('alice')['insurance_accounts'][0]
    payload = {key:value for key,value in item.items() if key!='yearly_contributions'}
    result = savings.save_insurance_account(dict(payload,memo='상품 메모 변경'), 'alice')
    assert result['yearly_contributions'] == records
    assert result['total_paid_amount'] == item['total_paid_amount']
    with pytest.raises(ValueError):
        savings.save_insurance_account(dict(payload,yearly_contributions=[dict(year='2013',deposit=-1)]), 'alice')


def test_yellow_umbrella_regular_history_storage_contract_is_unchanged(users):
    item = portfolio.read_portfolio('alice')['insurance_accounts'][2]
    result = savings.save_insurance_account(item, 'alice')
    assert result['yearly_contributions'] == item['yearly_contributions']
    assert result['marginal_tax_rate'] == item['marginal_tax_rate']
