"""Invented pension inputs only. Calculation never writes financial totals."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import asyncio

import pytest

from app.services import national_pension as np, portfolio, savings
from tests.test_national_pension_history import users
from regression_support import import_main_without_loading_real_env
from fastapi import HTTPException


@pytest.fixture
def isolated(users, monkeypatch):
    return users


def input_analysis(**changes):
    base = dict(membership_periods=[], annual_details=[], tax_years=[], scenario={})
    base.update(changes)
    return base


def case_scenario(**changes):
    base = dict(birth_date='1960-01-01', as_of_date='2025-01-01', pension_start='2030-01-01',
                monthly_pension=200, pension_value_basis='future_nominal', output_basis='nominal',
                future_monthly_premium=100, premium_start='2025-01-01', premium_end='2029-12-01',
                premium_growth=0, inflation=0, past_history_complete=True, annual_date_method='exact_only')
    base.update(changes)
    return base


def analysis_result(**changes):
    item = dict(yearly_contributions=[dict(year='2013', deposit=1200)])
    data = input_analysis(annual_details=[dict(year=2013, agency_paid=1200, personal_paid=600, employer_paid=600,
                     source='agency', verified=True, payment_date='2013-06-30')], scenario=case_scenario())
    data.update(changes)
    return np.scenario_results(item, np.validate_analysis(data))


def test_membership_periods_roles_nulls_and_legacy_history_are_separate(isolated):
    history = [dict(year='2013',deposit=1200)]
    savings.save_national_pension_history('alice-np', history, 'alice')
    before = deepcopy(portfolio.read_portfolio('alice')['insurance_accounts'])
    bob_bytes = (isolated/'bob/portfolio.json').read_bytes()
    periods = [dict(year=2024,start_month=1,end_month=4,membership_type='workplace',workplace_role='employee'),
               dict(year=2024,start_month=5,end_month=8,membership_type='workplace',workplace_role='sole_proprietor'),
               dict(year=2024,start_month=9,end_month=10,membership_type='workplace',workplace_role='corporate_representative'),
               dict(year=2024,start_month=11,end_month=12,membership_type='unknown')]
    payload = input_analysis(membership_periods=periods, annual_details=[dict(year=2013,personal_paid=None,employer_paid=0,unpaid=10)])
    saved = np.save('alice-np',payload,0,'alice',expected_history=history)
    assert saved['analysis']['annual_details'][0]['personal_paid'] is None
    assert saved['analysis']['annual_details'][0]['employer_paid'] == 0
    after = portfolio.read_portfolio('alice')['insurance_accounts']
    assert {k:v for k,v in after[0].items() if k!='national_pension_analysis'} == before[0]
    assert after[1:] == before[1:]
    assert (isolated/'bob/portfolio.json').read_bytes() == bob_bytes
    assert np.view('alice-np','alice')['analysis'] == saved['analysis']
    product = deepcopy(after[0]); product.pop('national_pension_analysis'); product['memo']='합성 메모'
    result = savings.save_insurance_account(product,'alice')
    assert result['national_pension_analysis']['revision'] == 1
    assert result['yearly_contributions'] == history


@pytest.mark.parametrize('periods', [
    [dict(year=2024,start_month=5,end_month=4)],
    [dict(year=2024,start_month=0,end_month=12)],
    [dict(year=2024,start_month=1,end_month=4),dict(year=2024,start_month=4,end_month=12)],
    [dict(year=2024,start_month=1,end_month=12,membership_type='regional',workplace_role='employee')],
])
def test_bad_periods_rejected_before_write(isolated, periods):
    before=(isolated/'alice/portfolio.json').read_bytes()
    with pytest.raises(ValueError):np.save('alice-np',input_analysis(membership_periods=periods),0,'alice',expected_history=[])
    assert (isolated/'alice/portfolio.json').read_bytes()==before


def tax_row(**changes):
    row=dict(year=2023,taxable_before=15000000,allowed_deduction=2000000,verified=True,source='tax_return')
    row.update(changes)
    return np.validate_analysis(input_analysis(tax_years=[row]))['tax_years'][0]


def test_progressive_tax_crosses_boundary_does_not_use_top_rate_or_gross_income():
    row=tax_row(gross_salary=999999999,business_revenue=888888888,business_income=55555555,actual_tax_saving=12345)
    result=np.tax_saving(row)
    assert result['tax_before']==990000
    assert result['tax_after']==780000
    assert result['estimated_reduction']==210000
    assert result['estimated_reduction']!=2000000*0.15
    assert result['actual_tax_saving']==12345
    assert np.tax_saving(tax_row(year=2022,taxable_before=13000000,allowed_deduction=1000000))['estimated_reduction']==150000
    assert np.tax_saving(tax_row(year=2023,taxable_before=13000000,allowed_deduction=1000000))['estimated_reduction']==60000
    capped=np.tax_saving(tax_row(taxable_before=100,allowed_deduction=1000))
    assert capped['capped'] and capped['applied_deduction']==100 and capped['estimated_reduction']==6
    assert np.tax_saving(tax_row(allowed_deduction=0))['estimated_reduction']==0
    loss=tax_row(business_income=-1000,taxable_before=None)
    assert loss['business_income']==-1000
    assert np.tax_saving(loss)['status']=='unknown'


@pytest.mark.parametrize('year', range(2017,2026))
def test_each_registered_year_bracket_boundaries_are_continuous(year):
    table=next(table for table in np.TAX_TABLES if table[0]<=year<=table[1])
    for limit, percent in zip(table[2],table[3]):
        value=np.tax_saving(tax_row(year=year,taxable_before=limit,allowed_deduction=1))
        assert value['estimated_reduction']==pytest.approx(percent/100,abs=0.01)
        assert value['source_url']==np.TAX_SOURCE and value['verified_on']==np.TAX_VERIFIED_ON


@pytest.mark.parametrize('changes', [dict(year=2013),dict(year=2026,verified=False),dict(verified=False),
    dict(source='unknown'),dict(source='estimate'),dict(taxable_before=None),dict(allowed_deduction=None)])
def test_unverified_tax_returns_no_fabricated_zero(changes):
    result=np.tax_saving(tax_row(**changes))
    assert result['status'] in {'unknown','unsupported_year'}
    assert 'estimated_reduction' not in result


@pytest.mark.parametrize('base,percent,deduction_constant', [
    (14000000,6,0), (50000000,15,1260000), (88000000,24,5760000),
    (150000000,35,15440000), (300000000,38,19940000),
    (500000000,40,25940000), (1000000000,42,35940000),
    (1100000000,45,65940000),
])
def test_2026_official_brackets_and_both_sides_of_boundaries(base,percent,deduction_constant):
    result=np.tax_saving(tax_row(year=2026,taxable_before=base,allowed_deduction=1))
    assert result['tax_before']==base*percent/100-deduction_constant
    assert result['estimated_reduction']==pytest.approx(percent/100,abs=0.001)
    assert result['tax_after']==pytest.approx(result['tax_before']-percent/100,abs=0.001)
    assert result['table_years']==[2026,2026]
    assert result['source_url']==np.TAX_SOURCE_2026
    assert result['law_url']==np.TAX_LAW_2026
    assert result['verified_on']==np.TAX_VERIFIED_ON
    next_rate={14000000:15,50000000:24,88000000:35,150000000:38,
               300000000:40,500000000:42,1000000000:45}.get(base,45)
    above=np.tax_saving(tax_row(year=2026,taxable_before=base+1,allowed_deduction=1))
    assert above['tax_after']==result['tax_before']
    assert above['estimated_reduction']==pytest.approx(next_rate/100,abs=0.001)


def test_2026_deduction_difference_cap_zero_and_input_confirmation_are_distinct():
    result=np.tax_saving(tax_row(year=2026,actual_tax_saving=12345))
    assert (result['tax_before'],result['tax_after'],result['estimated_reduction'])==(990000,780000,210000)
    assert result['estimated_reduction']!=2000000*0.15
    assert result['input_basis']=='filing_confirmed' and result['actual_tax_saving_confirmed']
    assert result['actual_tax_saving']==12345 and result['status']=='estimated'
    assert '환급액이 아닙니다' in result['notice'] and '지방소득세 미반영' in result['notice']
    capped=np.tax_saving(tax_row(year=2026,taxable_before=100,allowed_deduction=1000))
    assert capped['capped'] and capped['applied_deduction']==100 and capped['estimated_reduction']==6
    assert np.tax_saving(tax_row(year=2026,allowed_deduction=0))['estimated_reduction']==0
    for source,verified,basis in [('estimate',False,'estimate'),('tax_return',False,'unknown'),('unknown',True,'unknown')]:
        unconfirmed=np.tax_saving(tax_row(year=2026,source=source,verified=verified,actual_tax_saving=12345))
        assert unconfirmed['input_basis']==basis and not unconfirmed['actual_tax_saving_confirmed']
        assert unconfirmed['status']=='unknown' and 'estimated_reduction' not in unconfirmed
    checked=np.tax_saving(tax_row(year=2026,source='user',verified=True,actual_tax_saving=12345))
    assert checked['input_basis']=='verified_input' and not checked['actual_tax_saving_confirmed']
    # Future-year rate lookup itself must fail closed, independently of input-year validation.
    unsupported=np.tax_saving({**tax_row(), 'year':2027})
    assert unsupported['status']=='unsupported_year' and 'estimated_reduction' not in unsupported


@pytest.mark.parametrize('receipt', [110,100,80])
def test_xirr_positive_zero_and_negative_actual_dates(receipt):
    result=np.xirr([dict(date='2024-01-01',amount=-100),dict(date='2025-01-01',amount=receipt)])
    assert result['status']=='ok'
    assert result['rate']==pytest.approx((receipt/100)**(np.YEAR_DAYS/366)-1,abs=1e-8)


def test_xirr_no_root_multiple_sign_changes_and_convergence_failure():
    assert np.xirr([dict(date='2024-01-01',amount=100)])['rate'] is None
    assert np.xirr([dict(date='2024-01-01',amount=-100),dict(date='2024-01-01',amount=100)])['rate'] is None
    flows=[dict(date='2023-01-01',amount=-100),dict(date='2024-01-01',amount=230),dict(date='2025-01-01',amount=-132)]
    assert np.xirr(flows)['status']=='ambiguous'
    result=np.xirr(flows[:2],max_iterations=0)
    assert result['status']=='convergence_failed' and result['rate'] is None
    with pytest.raises(ValueError):np.xirr([dict(date='2024-02-30',amount=-100)])
    with pytest.raises(ValueError):np.xirr([dict(date='2024-01-01',amount=float('nan'))])
    extreme=np.xirr([dict(date='2024-01-01',amount=-1e-300),dict(date='2025-01-01',amount=1e100)])
    assert extreme['status']=='out_of_bounds' and extreme['rate'] is None


def test_receipt_ages_future_costs_payback_and_real_nominal_consistency():
    result=analysis_result()
    ages={row['age']:row for row in result['scenarios']}
    assert set(ages)=={75,80,85,90,95}
    assert ages[75]['future_premiums']==6000
    assert ages[75]['pension_receipts']==12000
    assert ages[75]['net_cash_flow']==5400
    assert ages[75]['payback_date']=='2032-09-01'
    assert ages[95]['pension_receipts']>ages[90]['pension_receipts']>ages[75]['pension_receipts']
    real=analysis_result(scenario=case_scenario(pension_value_basis='current_value',output_basis='real',inflation=0.02,pension_indexed=True))
    first_receipt=next(flow for flow in real['scenarios'][0]['cashflows'] if flow['amount']>0)
    assert first_receipt['amount']==pytest.approx(200)
    nominal=analysis_result(scenario=case_scenario(pension_value_basis='current_value',inflation=0.02))
    assert nominal['scenarios'][0]['pension_receipts']>result['scenarios'][0]['pension_receipts']
    schedule=analysis_result(scenario=case_scenario(future_schedule=[dict(date='2026-01-01',amount=1234)]))
    assert schedule['scenarios'][0]['future_premiums']==1234
    assert [day.isoformat() for day in np.month_dates(np.iso_date('2024-01-31'),np.iso_date('2024-03-31'))]==['2024-01-31','2024-02-29','2024-03-31']


def test_unknown_personal_cost_missing_history_and_explicit_assumptions():
    result=analysis_result(annual_details=[])
    assert result['scenarios'][0]['pre_tax_irr']['status']=='incomplete'
    assert result['scenarios'][0]['net_cash_flow'] is None
    assumed=analysis_result(annual_details=[],scenario=case_scenario(assume_agency_as_personal=True,annual_date_method='year_end'))
    assert assumed['personal_cost_assumed'] and assumed['annual_dates_approximated']
    assert assumed['scenarios'][0]['pre_tax_irr']['status']=='ok'
    incomplete=analysis_result(scenario=case_scenario(past_history_complete=False))
    assert incomplete['scenarios'][0]['payback_date'] is None
    assert analysis_result(scenario=case_scenario(future_monthly_premium=None))['status']=='unknown'
    assert analysis_result(scenario=case_scenario(pension_value_basis='unknown'))['status']=='unknown'


def test_tax_irr_stays_separate_and_after_tax_is_explicitly_unsupported():
    result=analysis_result(tax_years=[dict(year=2017,source='tax_return',verified=True,taxable_before=1000,
        allowed_deduction=100,actual_tax_saving=10,saving_date='2018-03-01')],scenario=case_scenario(include_tax_savings=True))
    scenario=result['scenarios'][0]
    assert scenario['pre_tax_irr']['status']=='ok'
    assert scenario['tax_benefit_irr']['status']=='ambiguous'
    assert scenario['after_tax_irr']['status']=='unsupported'
    zero=analysis_result(tax_years=[dict(year=2017,source='tax_return',verified=True,actual_tax_saving=0)],scenario=case_scenario(include_tax_savings=True))
    assert zero['scenarios'][0]['tax_benefit_irr']==zero['scenarios'][0]['pre_tax_irr']


def test_revision_conflict_concurrency_other_user_and_calculation_read_only(isolated):
    def write(_):
        try:return np.save('alice-np',input_analysis(),0,'alice',expected_history=[])['revision']
        except np.PensionConflict:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(write,[1,2]))
    assert sorted(results,key=str)==[1,'conflict']
    before=(isolated/'alice/portfolio.json').read_bytes()
    with pytest.raises(LookupError):np.save('bob-np',input_analysis(),0,'alice',expected_history=[])
    with pytest.raises(ValueError):np.save('alice-yu',input_analysis(),0,'alice',expected_history=[])
    np.calculate('alice-np',input_analysis(),'alice')
    assert (isolated/'alice/portfolio.json').read_bytes()==before
    assert np.save('alice-np',{},1,'alice',expected_history=[])['revision']==2


@pytest.mark.parametrize('payload', [input_analysis(annual_details=[dict(year=2024,personal_paid=-1)]),
    input_analysis(annual_details=[dict(year=2024,personal_paid=float('nan'))]),
    input_analysis(tax_years=[dict(year=2024),dict(year=2024)]),
    input_analysis(scenario=case_scenario(premium_end='2024-01-01')),
    input_analysis(scenario=case_scenario(inflation=2)),
    input_analysis(scenario=case_scenario(pension_start='2024-01-01'))])
def test_invalid_optional_metadata_never_partially_saves(isolated,payload):
    before=(isolated/'alice/portfolio.json').read_bytes()
    with pytest.raises(ValueError):np.save('alice-np',payload,0,'alice',expected_history=[])
    assert (isolated/'alice/portfolio.json').read_bytes()==before


def test_failed_save_preserves_bytes_and_concurrent_product_edit_preserves_metadata(isolated,monkeypatch):
    before=(isolated/'alice/portfolio.json').read_bytes()
    with monkeypatch.context() as context:
        def fail(*args,**kwargs):raise OSError('synthetic write failure')
        context.setattr(np,'write_financial_json',fail)
        with pytest.raises(OSError):np.save('alice-np',input_analysis(),0,'alice',expected_history=[])
    assert (isolated/'alice/portfolio.json').read_bytes()==before
    product=deepcopy(portfolio.read_portfolio('alice')['insurance_accounts'][0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(np.save,'alice-np',input_analysis(),0,'alice',expected_history=[]),
                 pool.submit(savings.save_insurance_account,{**product,'memo':'합성 동시 편집'},'alice')]
        for future in futures:future.result(timeout=10)
    current=portfolio.read_portfolio('alice')['insurance_accounts'][0]
    assert current['national_pension_analysis']['revision']==1
    assert current['memo']=='합성 동시 편집'
    assert current['total_paid_amount']==8000000
    assert current['yearly_contributions']==[]


def test_api_metadata_conflict_validation_delete_and_actor_scope(isolated,monkeypatch):
    main=import_main_without_loading_real_env()
    class SyntheticRequest:
        def __init__(self,body=None,username='alice'):self.body=body;self.username=username
        async def json(self):return self.body
    monkeypatch.setattr(main,'get_current_username',lambda request:request.username)
    original=(isolated/'alice/portfolio.json').read_bytes()
    state=asyncio.run(main.get_national_pension_analysis_endpoint('alice-np',SyntheticRequest()))
    assert state['revision']==0 and state['analysis']=={}
    assert (isolated/'alice/portfolio.json').read_bytes()==original
    payload=dict(analysis=input_analysis(),revision=0,expected_history=[])
    result=asyncio.run(main.save_national_pension_analysis_endpoint('alice-np',SyntheticRequest(payload)))
    assert result['revision']==1
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(main.save_national_pension_analysis_endpoint('alice-np',SyntheticRequest(payload)))
    assert conflict.value.status_code==409
    with pytest.raises(HTTPException) as foreign:
        asyncio.run(main.get_national_pension_analysis_endpoint('alice-np',SyntheticRequest(username='bob')))
    assert foreign.value.status_code==404
    with pytest.raises(HTTPException) as invalid:
        asyncio.run(main.save_national_pension_analysis_endpoint('alice-np',SyntheticRequest(
            dict(payload,revision=1,analysis=input_analysis(annual_details=[dict(year=2024,personal_paid=-1)])))))
    assert invalid.value.status_code==400
    before=(isolated/'alice/portfolio.json').read_bytes()
    result=asyncio.run(main.calculate_national_pension_analysis_endpoint('alice-np',SyntheticRequest(dict(analysis=input_analysis(),revision=1,expected_history=[]))))
    assert result['returns']['status']=='unknown'
    with pytest.raises(HTTPException) as stale_calculation:
        asyncio.run(main.calculate_national_pension_analysis_endpoint('alice-np',SyntheticRequest(dict(analysis=input_analysis(),revision=0,expected_history=[]))))
    assert stale_calculation.value.status_code==409
    assert (isolated/'alice/portfolio.json').read_bytes()==before
    result=asyncio.run(main.reset_national_pension_analysis_endpoint('alice-np',SyntheticRequest(dict(revision=1,expected_history=[]))))
    assert result['revision']==2
    assert portfolio.read_portfolio('alice')['insurance_accounts'][0]['total_paid_amount']==8000000


def test_metadata_only_save_does_not_advance_financial_timestamp_or_snapshots(isolated):
    path=isolated/'alice/portfolio.json'
    data=np.read_financial_json(path)
    data['updated_at']='2020-01-01T00:00:00+09:00'
    data['settings']['daily_snapshot']={}
    np.write_financial_json(path,data)
    before=deepcopy(data)
    np.save('alice-np',input_analysis(),0,'alice',expected_history=[])
    after=np.read_financial_json(path)
    after['insurance_accounts'][0].pop('national_pension_analysis')
    assert after==before
