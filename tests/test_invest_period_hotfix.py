"""Synthetic canonical summaries and the actual stock summary renderer."""
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from app.services import pnl_records

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app/static'
ROWS = [
    {'date': '2025-10-10', 'owner': '엄마', 'pnl_krw': 20501333},
    {'date': '2026-09-10', 'owner': '엄마', 'pnl_krw': 110},
    {'date': '2026-10-10', 'owner': '엄마', 'pnl_krw': -789783},
    {'date': '2026-11-10', 'owner': '엄마', 'pnl_krw': 220},
]


def canonical(rows, owner='모두', year=None):
    with patch.object(pnl_records, 'read_pnl_records', return_value=rows):
        return pnl_records.get_pnl_summary(owner=owner, year=year)


def render(rows, *, owner='모두', at='2026-09-30T15:30:00Z', intl_failure=False):
    code = r'''
const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8'), input=JSON.parse(process.argv[2]);
const elements={}, RealDate=Date;
class Clock extends RealDate { constructor(...a){super(...(a.length?a:[input.at]));} }
const sandbox={Date:Clock,Intl:input.intlFailure?{...Intl,DateTimeFormat:()=>{throw Error('unavailable')},NumberFormat:Intl.NumberFormat}:Intl,
 currentOwner:input.owner,STOCK_PORTFOLIO_MODE:'sector',rawDashboard:null,pnlData:null,actualDividendData:null,
 rawLoanAccounts:[],rawBankAccounts:[],rawSavingsAccounts:[],rawInsuranceAccounts:[],rawRealEstates:[],
 calculateDashboardDebt:()=>({totalMinusBankDebt:0,totalPureDebt:0}),
 $:selector=>elements[selector]||(elements[selector]={textContent:'',style:{},className:''}),
 CustomEvent:class{constructor(type,init){this.detail=init.detail;}},
 window:{dispatchEvent:e=>{sandbox.summary=e.detail;}}};
vm.createContext(sandbox);
vm.runInContext(source.slice(source.indexOf('function getKstYearMonth'),source.indexOf('function shiftYearMonth')),sandbox);
vm.runInContext(source.slice(source.indexOf('const number ='),source.indexOf('function formatKoreanMoneyFriendly')),sandbox);
vm.runInContext(source.slice(source.indexOf('function finiteRealizedPnlNumber'),source.indexOf('const SECTOR_COLORS')),sandbox);
sandbox.renderSummary({realized_pnl_records:input.rows,realized_pnl_summary:input.canonical});
process.stdout.write(JSON.stringify({summary:sandbox.summary,elements}));
'''
    result = subprocess.run(['node', '-e', code, str(STATIC/'wealth.js'), json.dumps({
        'rows': rows, 'canonical': canonical(rows), 'owner': owner,
        'at': at, 'intlFailure': intl_failure,
    }, ensure_ascii=False)], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True)
    return json.loads(result.stdout)


def test_all_time_year_and_current_month_match_same_year_pnl_page():
    view = render(ROWS)
    assert view['summary']['realizedTrade'] == 19711880  # All years retained.
    assert view['summary']['realizedYear'] == -789453
    assert view['summary']['realizedMonth'] == -789783
    assert canonical(ROWS)['monthly_schedule'][9]['total_krw'] == 19711550
    assert view['summary']['realizedMonth'] == canonical(ROWS, year=2026)['monthly_schedule'][9]['total_krw']
    month = view['elements']['#summaryRealizedPnlMonth']
    assert month['textContent'] == '-₩789,783'
    assert month['className'] == 'loss down'
    assert month['style']['color'] == '#38bdf8'
    assert view['elements']['#pnlMonthLabel']['textContent'] == '10월'


@pytest.mark.parametrize('month,expected', [(9,110), (10,-789783), (11,220)])
def test_previous_current_next_months_do_not_mix(month, expected):
    view = render(ROWS, at=f'2026-{month:02d}-15T00:00:00Z')
    assert view['summary']['realizedMonth'] == expected
    assert view['summary']['realizedMonth'] == canonical(ROWS, year=2026)['monthly_schedule'][month-1]['total_krw']


@pytest.mark.parametrize('owner,expected', [('모두',-789708), ('엄마',-789783), ('아빠',75), ('없는 가족',0)])
def test_owner_scope_matches_canonical_page(owner, expected):
    rows = ROWS + [{'date':'2026-10-20','owner':'아빠','pnl_krw':75}]
    view = render(rows, owner=owner)
    assert view['summary']['realizedMonth'] == expected
    assert expected == canonical(rows, owner=owner, year=2026)['monthly_schedule'][9]['total_krw']
    assert view['summary']['realizedYear'] == canonical(rows, owner=owner, year=2026)['total_pnl_krw']
    assert view['summary']['realizedTrade'] == canonical(rows, owner=owner)['total_pnl_krw']


@pytest.mark.parametrize('marker', [
    {'asset_type':'real_estate'}, {'code':'REAL_ESTATE'}, {'broker':'부동산'},
    {'name':'[부동산] 합성 주택'}, {'re_id':'synthetic'}, {'real_estate_name':'합성 주택'},
])
def test_real_estate_excluded_from_all_three_stock_periods(marker):
    rows = ROWS + [{'date':'2026-10-01','owner':'엄마','pnl_krw':100000000,**marker}]
    view = render(rows)
    assert view['summary']['realizedTrade'] == 19711880
    assert view['summary']['realizedYear'] == -789453
    assert view['summary']['realizedMonth'] == -789783


def test_kst_boundary_and_existing_helper_fallback_use_october():
    assert render(ROWS)['elements']['#pnlMonthLabel']['textContent'] == '10월'
    assert render(ROWS, intl_failure=True)['summary']['realizedMonth'] == -789783


def test_legacy_summary_producers_and_fixed_dates_physically_absent():
    html = (STATIC/'index.html').read_text(encoding='utf-8')
    source = (STATIC/'wealth.js').read_text(encoding='utf-8')
    for identifier in ('netWorthRow','safeAssetRow','subAssetBreakdown','pnlSubBreakdown',
                       'summaryNetWorth','summarySafeAssetVal'):
        assert f'id="{identifier}"' not in html
        assert f'#{identifier}' not in source
    assert '>09월<' not in html
    assert '>26년<' not in html
    assert 'MODE A:' not in source
    summary = html[html.index('<section id="summaryPanel"'):html.index('</section>',html.index('<section id="summaryPanel"'))]
    assert '₩0' not in summary and '+0.00%' not in summary
    for label in ('총 주식자산','원화 주식','달러 주식','주식 기대수익','주식 실현손익','배당금'):
        assert label in summary
    for metric in ('wealthAssetNetWorth','wealthAssetInvest','wealthAssetExpected','wealthAssetRealized','wealthAssetSafe'):
        assert metric in (STATIC/'wealth-layout.js').read_text(encoding='utf-8')


@pytest.mark.parametrize('stored,expected', [(None,'overview'), ('','overview'), ('unknown','overview'),
    ('<img>','overview'), *[(tab,tab) for tab in ('overview','heatmap','records','buckets','tax_accounts','holdings')]])
def test_session_allowlist_before_parsing(stored, expected):
    script = r'''
const fs=require('fs'),vm=require('vm'),root={dataset:{}},saved=[];
const sandbox={document:{documentElement:root},window:{},sessionStorage:{getItem:()=>JSON.parse(process.argv[2]),setItem:(k,v)=>saved.push([k,v])}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const initial=root.dataset.wealthInvestTab;
sandbox.window.WealthInvestTabState.select('unexpected');
process.stdout.write(JSON.stringify({initial,fallback:root.dataset.wealthInvestTab,saved}));
'''
    result = subprocess.run(['node','-e',script,str(STATIC/'wealth-invest-tab-state.js'),json.dumps(stored)],
                            cwd=ROOT,capture_output=True,text=True,check=True)
    value = json.loads(result.stdout)
    assert value == {'initial':expected,'fallback':'overview','saved':[['wealth_invest_tab','overview']]}
