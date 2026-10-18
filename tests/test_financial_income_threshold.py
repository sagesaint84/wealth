"""v2.1.2 registered-income estimates, exclusively synthetic/mock inputs."""
from copy import deepcopy
from unittest.mock import AsyncMock, patch
from pathlib import Path
import asyncio
import subprocess

import pytest

from app.services.dividend_records import estimate_record_dividend, _record_tax_metadata
from app.services.tax.financial_income import build_financial_income_projection
from app.services.tax.what_if import build_financial_income_what_if
from app.services.tax.family_financial_income import build_family_financial_income_risk


def row(gross, *, code='005930', capital=False, high=False, owner='합성 A', **extra):
    net = gross if capital else round(gross * .846)
    return {'id':code, 'code':code, 'owner':owner, 'currency':'KRW', 'date':'2026-04-08',
        'amount':net, 'amount_krw':net, 'gross_amount':gross, 'tax':gross-net,
        'capital_dividend_mode':'MANUAL_ON' if capital else 'MANUAL_OFF',
        'high_dividend_mode':'MANUAL_ON' if high else 'MANUAL_OFF', **extra}


def projection(dividends, interests=(), *, owner='합성 A', forecast=None):
    actual = {'year':'2026', 'records':dividends, 'interest_records':list(interests),
        'record_count':len(dividends), 'interest_record_count':len(interests),
        'total_actual_dividend_krw':sum(r['amount_krw'] for r in dividends),
        'total_actual_interest_krw':sum(r['amount_krw'] for r in interests)}
    return build_financial_income_projection(actual, forecast or {'monthly_schedule':[]},
        owner=owner, as_of='2026-06-01')


def example():
    return [row(12000000), row(8000000, code='316140', capital=True),
        row(10000000, code='000660', high=True)], [row(5000000, code='INTEREST', income_type='account_interest')]


def test_requested_example_uses_gross_exclusions_and_preserves_every_record():
    dividends, interests = example()
    original = deepcopy((dividends, interests))
    p = projection(dividends, interests)
    a = p['actual_financial_income']
    assert a['total_gross_krw'] == 35000000
    assert a['capital_excluded_krw'] == 8000000
    assert a['high_dividend_excluded_krw'] == 10000000
    assert a['included_krw'] == 17000000 and a['remaining_krw'] == 3000000
    assert a['status'] == '기준 이내' and not a['exceeded']
    assert not p['data_quality']['aggregate_cash_floor_applied']
    # The special dividend remains taxed, never treated as tax-free.
    assert a['high_dividend_special_tax']['national_income_tax_krw'] == 1400000
    assert (dividends, interests) == original


def test_disabling_selections_restores_inclusion_and_partial_capital_excludes_only_part():
    d, i = example()
    d[1]['capital_dividend_mode'] = 'MANUAL_OFF'
    assert projection(d, i)['actual_financial_income']['included_krw'] == 25000000
    d[2]['high_dividend_mode'] = 'MANUAL_OFF'
    assert projection(d, i)['actual_financial_income']['included_krw'] == 35000000
    d[1].update(capital_dividend_mode='MANUAL_ON', capital_exempt_amount=3000000)
    assert projection(d, i)['actual_financial_income']['included_krw'] == 32000000


@pytest.mark.parametrize('gross, status, remaining', [(20000000,'기준 이내',0),(20000001,'기준 초과',0)])
def test_exact_threshold_and_one_won_over(gross, status, remaining):
    a = projection([row(gross)])['actual_financial_income']
    assert a['status'] == status and a['remaining_krw'] == remaining
    assert a['exceeded'] == (gross > 20000000)


def test_cash_floor_does_not_reintroduce_excluded_amounts_or_double_exclude_overlap():
    r = row(10000000, capital=True, high=True, capital_exempt_amount=4000000,
        high_dividend_amount=10000000)
    a = projection([r])['actual_financial_income']
    assert a['capital_excluded_krw'] == 4000000
    assert a['high_dividend_excluded_krw'] == 6000000
    assert a['included_krw'] == 0
    assert a['total_gross_krw'] == 10000000


def test_net_estimate_usd_fx_interest_and_explicit_zero():
    r = row(0, currency='USD', amount=85, amount_krw=119000, fx_rate=1400)
    del r['gross_amount']; del r['tax']
    assert projection([r])['actual_financial_income']['total_gross_krw'] == 140000
    # An interest row cannot inherit dividend benefit metadata.
    interest = row(1000, capital=True, high=True, income_type='account_interest')
    assert projection([], [interest])['actual_financial_income']['included_krw'] == 1000
    zero = estimate_record_dividend(row(0, high=True))
    assert zero['gross_amount_krw'] == zero['high_dividend_applied_amount_krw'] == 0


def test_current_company_qualification_never_implies_filing_choice_or_changes_verdict():
    evidence = {'high_dividend_qualification':{'status':'official_qualified','business_year':2025}}
    ordinary = estimate_record_dividend(row(1000), evidence)
    assert ordinary['high_dividend_applied_amount_krw'] == 0
    evidence['high_dividend_qualification']['status'] = 'official_not_qualified'
    assumed = estimate_record_dividend(row(1000, high=True), evidence)
    assert assumed['high_dividend_application_assumption']
    assert assumed['high_dividend_applied_amount_krw'] == 1000
    assert assumed['high_dividend_qualification']['status'] == 'official_not_qualified'
    assert estimate_record_dividend(row(1000, high=True, date='2025-04-08'))['high_dividend_applied_amount_krw'] == 0


def test_what_if_reuses_record_baseline_without_a_second_exclusion():
    d, i = example()
    p = projection(d, i)
    result = build_financial_income_what_if(p)
    assert result['scenario_comprehensive_tax_screening_income_krw'] == 17000000
    assert result['high_dividend_special_tax']['national_income_tax_krw'] == 1400000
    changed = build_financial_income_what_if(p, additional_dividend_gross_krw=20000000,
        high_dividend_scenario={'special_dividend_income_krw':20000000,
            'high_dividend_company_confirmed':True, 'separate_taxation_requested':True})
    assert changed['scenario_comprehensive_tax_screening_income_krw'] == 17000000
    assert changed['high_dividend_special_tax']['special_dividend_income_krw'] == 30000000
    assert changed['high_dividend_special_tax']['national_income_tax_krw'] == 4800000


def test_family_thresholds_remain_personal_and_family_total_is_reference_only():
    a = projection([row(19000000)])
    b = projection([row(19000000, owner='합성 B')], owner='합성 B')
    family = build_family_financial_income_risk([a,b], as_of='2026-06-01')
    assert all(not m['actual_financial_income']['exceeded'] for m in family['members'])
    total = projection([row(19000000), row(19000000, owner='합성 B')], owner='모두')
    assert total['actual_financial_income']['remaining_krw'] is None
    assert total['actual_financial_income']['status'] == '가족 참고 합계'
    assert total['thresholds']['comprehensive_tax']['actual_gross_screening']['exceeded'] is None


def test_official_future_event_and_record_are_not_counted_twice():
    r = row(1000, high=True, date='2026-07-01', event_identity='synthetic:event')
    forecast = {'monthly_schedule':[{'month':7,'total_krw':1000,'items':[
        {'code':'005930','payout_krw':1000,'payment_date':'2026-07-01',
         'event_identity':'synthetic:event','event_identity_confidence':'official'}]}]}
    p = projection([r], forecast=forecast)
    assert p['forecast_basis']['dividend_event_dedup_applied_count'] == 1
    assert p['projected_gross_screening_income_krw'] == 0


def test_optional_high_selection_storage_roundtrip_preserves_money(tmp_path):
    from app.services import dividend_records as service
    with patch.object(service, '_get_user_dir', side_effect=lambda username=None: tmp_path/str(username)), \
         patch.object(service, 'resolve_stock_info', side_effect=lambda c,n,curr:(c,n,curr)):
        saved = service.create_dividend_record(row(10000000), username='alice')
        original = {k:saved[k] for k in ('amount','amount_krw','gross_amount','tax')}
        service.update_dividend_record(saved['id'], {'high_dividend_mode':'MANUAL_ON'}, username='alice')
        reread = service.read_dividend_records('alice')[0]
        assert reread['high_dividend_mode'] == 'MANUAL_ON'
        assert {k:reread[k] for k in original} == original
        assert service.read_dividend_records('bob') == []
    assert _record_tax_metadata({'capital_dividend_mode':'AUTO'}) == {'capital_dividend_mode':'AUTO'}


def test_projection_service_and_what_if_agree_without_writes_or_user_leakage():
    from app.services.tax.financial_income import get_financial_income_projection_for_user
    from app.services.tax.what_if import get_financial_income_what_if_for_user
    d, i = example()
    actual = {'year':'2026', 'records':d, 'interest_records':i,
        'record_count':3, 'interest_record_count':1,
        'total_actual_dividend_krw':sum(r['amount_krw'] for r in d),
        'total_actual_interest_krw':i[0]['amount_krw']}
    async def check():
        with patch('app.services.portfolio.get_dashboard', return_value={'holdings':[], 'accounts':[]}), \
             patch('app.services.web_finance.get_web_dividend_summary', new=AsyncMock(return_value={'monthly_schedule':[]})), \
             patch('app.services.dividend_records.get_actual_dividend_summary', return_value=actual) as reader, \
             patch('app.services.dividend_records.get_record_tax_evidence', new=AsyncMock(return_value={})) as evidence, \
             patch('app.services.dividend_records.write_dividend_records') as writer:
            a = await get_financial_income_projection_for_user('alice', owner='합성 A', as_of='2026-06-01')
            b = await get_financial_income_what_if_for_user('bob', owner='합성 A', as_of='2026-06-01')
            assert a['actual_financial_income'] == b['baseline_projection']['actual_financial_income']
            assert a['actual_financial_income']['included_krw'] == 17000000
            assert [call.kwargs['username'] for call in reader.call_args_list] == ['alice', 'bob']
            assert [call.args[1] for call in evidence.await_args_list] == ['alice', 'bob']
            writer.assert_not_called()
    asyncio.run(check())


def test_registered_summary_rendering_escapes_identity_and_keeps_family_reference_only():
    root = Path(__file__).resolve().parents[1]
    script = r"""
const assert = require('node:assert/strict');
global.window = {addEventListener(){}};
global.document = {readyState:'loading', addEventListener(){}};
eval(require('node:fs').readFileSync(process.argv[1], 'utf8'));
const render = window.WealthFinancialIncomeWhatIf.registeredThresholdHtml;
const summary = {total_gross_krw:35000000,capital_excluded_krw:8000000,
 high_dividend_excluded_krw:10000000,included_krw:17000000,remaining_krw:3000000,
 personal_threshold_applied:true,status:'기준 이내',exceeded:false};
const html = render(summary, '<img src=x onerror=alert(1)>', 2026);
assert(!html.includes('<img'));
assert(html.includes('&lt;img'));
for (const amount of ['35,000,000','8,000,000','10,000,000','17,000,000','3,000,000']) assert(html.includes(amount));
assert(html.includes('기준 이내') && html.includes('등록된 자료 기준 예상'));
const family = render({...summary, personal_threshold_applied:false}, '모두', 2026);
assert(family.includes('가족 참고 합계'));
assert(!family.includes('2천만원 기준까지 남은 금액'));
assert(!family.includes('class="fi-result-card safe"'));
"""
    subprocess.run(['node', '-e', script, str(root/'app/static/wealth-financial-income-what-if.js')],
        check=True, capture_output=True, text=True, encoding='utf-8')
    html = (root/'app/static/index.html').read_text(encoding='utf-8')
    assert '<option value="HIGH_DIVIDEND">고배당 분리과세 적용</option>' in html
    js = (root/'app/static/wealth.js').read_text(encoding='utf-8')
    assert "selected === 'HIGH_DIVIDEND' ? 'MANUAL_OFF' : selected" in js
    assert "high_dividend_mode: selected === 'HIGH_DIVIDEND' ? 'MANUAL_ON' : 'MANUAL_OFF'" in js


@pytest.mark.parametrize('payload', [
    {'high_dividend_mode':'AUTO'}, {'high_dividend_mode':True},
    {'high_dividend_amount':-1}, {'high_dividend_amount':float('nan')},
])
def test_invalid_high_metadata_is_rejected(payload):
    with pytest.raises(ValueError):
        _record_tax_metadata(payload)


@pytest.mark.parametrize('code_fields', [{}, {'code':None}, {'code':''},
    {'code':' '}, {'code':'invalid!'}, {'code':'00593'}, {'code':'ABCDEF'}])
def test_missing_or_invalid_code_skips_only_evidence_not_income(code_fields):
    from app.services.dividend_records import get_record_tax_evidence
    record = row(1100, amount=1000, amount_krw=1000, tax=100,
        capital_dividend_mode='AUTO')
    record.pop('code')
    record.update(code_fields)
    original = deepcopy(record)
    with patch('app.services.dividend_official_sources.get_official_dividend_evidence',
            new=AsyncMock()) as dart, \
         patch('app.services.high_dividend_qualification.enrich_dividend_intelligence_with_high_dividend_qualification',
            new=AsyncMock()) as qualification:
        evidence = asyncio.run(get_record_tax_evidence([record], 'alice'))
        assert evidence == {}
        dart.assert_not_awaited()
        qualification.assert_not_awaited()
    estimate = estimate_record_dividend(record, evidence.get(record.get('code')))
    assert estimate['tax_type_label'] == '일반 배당'
    assert not estimate['capital_official_confirmed']
    assert not estimate['high_dividend_qualification']
    assert estimate['high_dividend_applied_amount_krw'] == 0
    p = projection([record])
    assert p['actual_cash_income_krw'] == 1000
    assert p['actual_gross_screening_income_krw'] == 1100
    assert p['actual_financial_income']['capital_excluded_krw'] == 0
    assert p['actual_financial_income']['high_dividend_excluded_krw'] == 0
    assert record == original


def test_valid_domestic_codes_still_fetch_user_scoped_official_evidence():
    from app.services.dividend_records import get_record_tax_evidence
    records = [row(1100, code=None), row(1100, code=''), row(1100, code='A005930'),
        row(1100, code='005930'), row(1100, code='0005G0'), row(1100, currency='USD')]
    original = deepcopy(records)
    async def enrich(summary, holdings, *, username):
        for instrument in summary['dividend_intelligence']['instruments']:
            instrument['high_dividend_qualification'] = {'status':'source_unavailable', 'synthetic_user':username}
        return summary
    with patch('app.services.dividend_official_sources.get_official_dividend_evidence',
            new=AsyncMock(return_value={'evidence':{}})) as dart, \
         patch('app.services.high_dividend_qualification.enrich_dividend_intelligence_with_high_dividend_qualification',
            new=AsyncMock(side_effect=enrich)) as qualification:
        alice = asyncio.run(get_record_tax_evidence(records, 'alice'))
        bob = asyncio.run(get_record_tax_evidence(records, 'bob'))
    expected = [{'code':'0005G0','currency':'KRW'}, {'code':'005930','currency':'KRW'}]
    assert set(alice) == set(bob) == {'0005G0','005930'}
    assert [c.args[0] for c in dart.await_args_list] == [expected, expected]
    assert [c.kwargs['username'] for c in dart.await_args_list] == ['alice','bob']
    assert [c.kwargs['username'] for c in qualification.await_args_list] == ['alice','bob']
    assert alice['005930']['high_dividend_qualification']['synthetic_user'] == 'alice'
    assert bob['005930']['high_dividend_qualification']['synthetic_user'] == 'bob'
    assert records == original


def test_missing_code_projection_keeps_authenticated_user_and_owner_scope():
    from app.services.tax.financial_income import get_financial_income_projection_for_user
    def actual(*, owner, year, username):
        gross = {('alice','합성 A'):1100, ('alice','합성 B'):2200, ('bob','합성 A'):3300}[(username,owner)]
        record = row(gross, code=None, owner=owner)
        return {'year':year, 'records':[record], 'interest_records':[], 'record_count':1,
            'interest_record_count':0, 'total_actual_dividend_krw':record['amount_krw'],
            'total_actual_interest_krw':0}
    async def check():
        with patch('app.services.portfolio.get_dashboard', return_value={'holdings':[], 'accounts':[]}), \
             patch('app.services.web_finance.get_web_dividend_summary', new=AsyncMock(return_value={'monthly_schedule':[]})), \
             patch('app.services.dividend_records.get_actual_dividend_summary', side_effect=actual) as reader, \
             patch('app.services.dividend_official_sources.get_official_dividend_evidence', new=AsyncMock()) as dart:
            results = [await get_financial_income_projection_for_user(username, owner=owner, as_of='2026-06-01')
                for username,owner in [('alice','합성 A'),('alice','합성 B'),('bob','합성 A')]]
            assert [r['actual_gross_screening_income_krw'] for r in results] == [1100,2200,3300]
            assert [r['owner'] for r in results] == ['합성 A','합성 B','합성 A']
            assert [(c.kwargs['username'],c.kwargs['owner']) for c in reader.call_args_list] == [
                ('alice','합성 A'),('alice','합성 B'),('bob','합성 A')]
            dart.assert_not_awaited()
    asyncio.run(check())
