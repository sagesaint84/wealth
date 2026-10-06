"""Exact filtered bucket detail behavior in the real application DOM."""
from pathlib import Path
import subprocess

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for


SETUP = r"""
const check=(yes,message)=>{if(!yes)throw Error(message);};
const eq=(a,b,message)=>check(JSON.stringify(a)===JSON.stringify(b),message+JSON.stringify(a));
const u=WealthUnifiedTimeseries, modes=WealthTimeseriesPeriodCore.MODES;
window.__chartErrors=[];console.error=(...args)=>__chartErrors.push(args.map(v=>String(v)).join(' '));
currentOwner='감사';selectedPnlYear='2026';selectedDividendYear='2026';selectedPnlMonth=10;selectedDividendMonth=10;
const record=(id,date,value,extra={})=>({id,date,owner:'감사',broker:'가상증권',name:id,code:id,currency:'KRW',pnl:value,pnl_krw:value,amount:value,amount_krw:value,...extra});
window.__pnl=[record('P2025','2025-10-05',100),record('P2026','2026-10-05',200),record('P9','2026-09-05',90),record('P9Broker','2026-09-06',9,{broker:'다른증권'}),record('P11','2026-11-05',110),record('P7a','2026-10-07',30,{is_ipo:true}),record('P7b','2026-10-07',40),record('P8','2026-10-08',80),record('OTHER','2026-10-07',999,{broker:'다른증권',owner:'다른사람'})];
window.__div=[record('D2025','2025-10-05',100),record('D2026','2026-10-05',200),record('D9','2026-09-05',90),record('D9Broker','2026-09-06',9,{broker:'다른증권'}),record('D11','2026-11-05',110),record('D7a','2026-10-07',30),record('D7b','2026-10-07',40),record('D8','2026-10-08',80),record('OTHER-D','2026-10-07',999,{broker:'다른증권',owner:'다른사람'})];
window.__interest=[record('I7','2026-10-07',50,{income_type:'account_interest'}),record('I8','2026-10-08',60,{income_type:'account_interest'})];
window.__incomeCalls=[];const nativeApi=api;
api=async function(path,...args){
 __incomeCalls.push(path);const params=new URL(path,location.origin).searchParams;
 const owner=params.get('owner');
 const filtered=rows=>rows.filter(r=>owner==='모두'||r.owner===owner);
 if(path.startsWith('/api/realized-pnl?'))return {records:filtered(__pnl).filter(r=>(params.get('year')==='all'||r.date.startsWith(params.get('year')+'-'))&&(params.get('trade_type')!=='ipo'||r.is_ipo)),available_years:[2025,2026]};
 if(path.startsWith('/api/actual-dividends?'))return {records:filtered(__div),interest_records:filtered(__interest),available_years:[2025,2026]};
 return nativeApi(path,...args);
};
for(const id of ['pnlBrokerFilter','dividendBrokerFilter'])document.getElementById(id).innerHTML='<option value="all">전체</option><option value="가상증권">가상증권</option><option value="다른증권">다른증권</option>';
document.querySelectorAll('#pnlTradeTypeTabs [data-trade-type]').forEach(n=>n.classList.toggle('active',n.dataset.tradeType==='all'));
document.querySelectorAll('#dividendModeTabs [data-div-mode]').forEach(n=>n.classList.toggle('active',n.dataset.divMode==='actual'));
const host=kind=>document.getElementById(kind==='pnl'?'pnlBarChartWrap':'dividendBarChartWrap');
const detail=kind=>document.getElementById(kind==='pnl'?'pnlMonthlyDetail':'dividendMonthlyDetail');
const target=(kind,key)=>host(kind).querySelector(`.wealth-unified-bucket-target[data-bucket-key="${key}"]`);
const select=(kind,key)=>target(kind,key).dispatchEvent(new MouseEvent('click',{bubbles:true}));
const names=kind=>[...detail(kind).querySelectorAll('.td-stock-name')].map(n=>n.textContent).sort();
const render=async(kind,mode)=>{u.modes[kind]=mode;await (kind==='pnl'?u.renderPnl():u.renderDividend());};
await loadRealizedPnl(currentOwner,selectedPnlYear,currentPnlTradeType);await window.loadActualDividends(currentOwner,selectedDividendYear);
syncPnlMonthNavUI();syncDividendMonthNavUI();
await render('pnl',modes.MONTH);await render('dividend',modes.MONTH);
check(target('pnl','2025-10'), 'target missing: '+JSON.stringify(__chartErrors)+' '+host('pnl').innerHTML.slice(0,300));
"""

SCENARIOS = {
    'legacy_no_selection_and_isolation': r"""
      for(const kind of ['pnl','dividend'])check(u.getDetail(kind)===null,'no bucket returns null');
      const before=[selectedPnlYear,selectedPnlMonth,selectedDividendYear,selectedDividendMonth];
      const ui=['pnlMonthPicker','dividendMonthPicker','pnlYearSelect','dividendYearSelect'].map(id=>document.getElementById(id).value);
      const calls=__incomeCalls.length;
      select('pnl','2025-10');select('dividend','2025-10');
      eq(names('pnl'),['P2025'],'old-year PnL');eq(names('dividend'),['D2025'],'old-year dividend');
      eq([selectedPnlYear,selectedPnlMonth,selectedDividendYear,selectedDividendMonth],before,'legacy variables isolated');
      eq(['pnlMonthPicker','dividendMonthPicker','pnlYearSelect','dividendYearSelect'].map(id=>document.getElementById(id).value),ui,'legacy UI isolated');
      check(__incomeCalls.length===calls,'chart detail has no refetch');
      check(document.getElementById('clearPnlMonthBtn').textContent.includes('선택 해제'),'dismiss label');
      document.getElementById('clearPnlMonthBtn').click();document.getElementById('clearDivMonthBtn').click();
      for(const kind of ['pnl','dividend']){check(u.getDetail(kind)===null,'dismiss null');check(!host(kind).querySelector('.is-selected'),'dismiss marker');}
      eq(names('pnl'),['P2026','P7a','P7b','P8'],'legacy PnL month restored');
      eq(names('dividend'),['D2026','D7a','D7b','D8','I7','I8'],'legacy dividend month restored');
      eq([selectedPnlYear,selectedPnlMonth,selectedDividendYear,selectedDividendMonth],before,'dismiss leaves legacy state');
    """,
    'legacy_navigation_pnl': r"""
      select('pnl','2025-10');document.getElementById('pnlNextMonthBtn').click();
      eq([selectedPnlYear,selectedPnlMonth],['2026',11],'next starts from original legacy state');
      eq(names('pnl'),['P11'],'next legacy month');check(u.getDetail('pnl')===null,'next clears');
      document.getElementById('pnlPrevMonthBtn').click();eq(names('pnl'),['P2026','P7a','P7b','P8'],'previous works');
      const picker=document.getElementById('pnlMonthPicker');select('pnl','2025-10');picker.value='2026-11';picker.dispatchEvent(new Event('change',{bubbles:true}));
      eq(names('pnl'),['P11'],'picker works');check(u.getDetail('pnl')===null&&!host('pnl').querySelector('.is-selected'),'picker clears');
      document.getElementById('pnlTodayMonthBtn').click();const now=getKstYearMonth();
      eq([selectedPnlYear,selectedPnlMonth],[String(now.year),now.month],'today legacy semantics');
    """,
    'legacy_navigation_dividend': r"""
      select('dividend','2025-10');document.getElementById('dividendNextMonthBtn').click();
      eq([selectedDividendYear,selectedDividendMonth],['2026',11],'dividend next original state');
      eq(names('dividend'),['D11'],'next legacy month');check(u.getDetail('dividend')===null,'next clears');
      document.getElementById('dividendPrevMonthBtn').click();eq(names('dividend'),['D2026','D7a','D7b','D8','I7','I8'],'previous works');
      const picker=document.getElementById('dividendMonthPicker');select('dividend','2025-10');picker.value='2026-11';picker.dispatchEvent(new Event('change',{bubbles:true}));
      eq(names('dividend'),['D11'],'dividend picker works');check(u.getDetail('dividend')===null&&!host('dividend').querySelector('.is-selected'),'picker clears');
      document.getElementById('dividendTodayMonthBtn').click();const now=getKstYearMonth();
      eq([selectedDividendYear,selectedDividendMonth],[String(now.year),now.month],'today legacy semantics');
    """,
    'legacy_year_picker_and_actions': r"""
      const frames=async()=>{for(let i=0;i<4;i++)await new Promise(requestAnimationFrame);};
      for(const [kind,prefix] of [['pnl','pnl'],['dividend','dividend']]){
        select(kind,'2026-10');const year=document.getElementById(prefix+'YearSelect');year.value='2025';year.dispatchEvent(new Event('change',{bubbles:true}));await frames();
        check(u.getDetail(kind)===null&&!host(kind).querySelector('.is-selected'),'year clears selection');
        eq(names(kind),[kind==='pnl'?'P2025':'D2025'],'requested year rendered');
        const picker=document.getElementById(prefix+'MonthPicker');select(kind,'2026-10');picker.value='2026-11';picker.dispatchEvent(new Event('change',{bubbles:true}));await frames();
        check(u.getDetail(kind)===null,'cross-year picker clears');eq(names(kind),[kind==='pnl'?'P11':'D11'],'cross-year picker loads');
      }
      window.openPnlRecordDialog=record=>window.__edited=record;window.openDividendRecordDialog=record=>window.__edited=record;
      detail('pnl').querySelector('.edit-pnl-btn').click();check(__edited.id==='P11','legacy edit lookup');
      detail('dividend').querySelector('.edit-actual-div-btn').click();check(__edited.id==='D11','legacy dividend edit');
      window.confirm=text=>{window.__confirmation=text;return false;};
      detail('pnl').querySelector('.delete-pnl-btn').click();check(__confirmation.includes('P11'),'legacy delete lookup');
      detail('dividend').querySelector('.delete-actual-div-btn').click();check(__confirmation.includes('D11'),'legacy dividend delete lookup');
      select('pnl','2025-10');detail('pnl').querySelector('.delete-pnl-btn').click();check(__confirmation.includes('P2025'),'active delete lookup');
      select('dividend','2025-10');detail('dividend').querySelector('.delete-actual-div-btn').click();check(__confirmation.includes('D2025'),'active dividend delete lookup');
    """,
    'legacy_all_sort_and_bars': r"""
      const frames=async()=>{for(let i=0;i<4;i++)await new Promise(requestAnimationFrame);};
      for(const [kind,recordPrefix,clearId,barClass] of [['pnl','P','clearPnlMonthBtn','pnl-bar-group'],['dividend','D','clearDivMonthBtn','dividend-bar-group']]){
        select(kind,'2026-10');const sort=detail(kind).querySelector(kind==='pnl'?'[data-pnl-sort="name"]':'[data-div-sort="name"]');
        sort.click();const first=[...detail(kind).querySelectorAll('.td-stock-name')].map(n=>n.textContent);detail(kind).querySelector(kind==='pnl'?'[data-pnl-sort="name"]':'[data-div-sort="name"]').click();
        const second=[...detail(kind).querySelectorAll('.td-stock-name')].map(n=>n.textContent);
        eq(second,[...first].reverse(),'sort order changes');check(u.getDetail(kind).key==='2026-10','sort keeps bucket');
        document.getElementById(clearId).click();check(u.getDetail(kind)===null,'dismiss');
        document.getElementById(clearId).click();check(names(kind).includes(recordPrefix+'11')&&names(kind).includes(recordPrefix+'9'),'legacy all-year view');
        select(kind,'2025-10');const bar=document.createElement('button');bar.className=barClass;bar.dataset.month='11';document.body.append(bar);bar.click();bar.remove();
        check(u.getDetail(kind)===null,'legacy month bar clears');eq(names(kind),[recordPrefix+'11'],'legacy month bar detail');
        select(kind,'2026-10');const annual=document.createElement('button');annual.className=barClass;annual.dataset.year='2025';document.body.append(annual);annual.click();annual.remove();await frames();
        check(u.getDetail(kind)===null,'legacy year bar clears');eq(names(kind),[recordPrefix+'2025'],'legacy year bar detail');
      }
    """,
    'legacy_year_intent_and_renderer_arguments': r"""
      renderPnlMonthlyDetail(11);eq(names('pnl'),['P11'],'explicit legacy PnL argument honored');
      renderActualDividendDetail(11);eq(names('dividend'),['D11'],'explicit legacy dividend argument honored');
      for(const [kind,prefix] of [['pnl','pnl'],['dividend','dividend']]){
        for(const interaction of ['pointerdown','keydown'])for(const month of [10,null]){
          if(kind==='pnl')window.setSelectedPnlPeriod(2026,month);else window.setSelectedDividendPeriod(2026,month);
          select(kind,'2025-10');const year=document.getElementById(prefix+'YearSelect');
          year.dispatchEvent(interaction==='pointerdown'?new PointerEvent('pointerdown',{bubbles:true}):new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
          check(u.getDetail(kind)===null&&!host(kind).querySelector('.is-selected'),'same-year intent clears');
          check(kind==='pnl'?selectedPnlMonth===null:selectedDividendMonth===null,'existing annual intent preserved');
          check(!names(kind).includes(kind==='pnl'?'P2025':'D2025'),'same-year detail stays in legacy year');
        }
      }
    """,
    'pnl_exact_month': r"""
      select('pnl','2025-10');eq(names('pnl'),['P2025'],'exact year');
      check(detail('pnl').textContent.includes('2025년 10월'),'heading year authoritative');
      check(detail('pnl').textContent.includes('+₩100'),'month sum');
      check(target('pnl','2025-10').classList.contains('is-selected'),'selected');
      check(target('pnl','2025-10').getAttribute('aria-pressed')==='true','selected announced');
      check(detail('pnl').querySelector('.edit-pnl-btn[data-id="P2025"]'),'existing management retained');
      window.openPnlRecordDialog=record=>window.__edited=record;
      detail('pnl').querySelector('.edit-pnl-btn').click();check(__edited.id==='P2025','edit lookup exact old-year record');
      await u.renderPnl();eq(names('pnl'),['P2025'],'rerender preserves selection');
      document.getElementById('clearPnlMonthBtn').click();check(names('pnl').includes('P2026'),'all restored');
      check(!host('pnl').querySelector('.is-selected'),'clear selection');check(u.modes.pnl===modes.MONTH,'period unchanged');
    """,
    'pnl_day_empty_sort': r"""
      await render('pnl',modes.DAY);select('pnl','2026-10-07');
      eq(names('pnl'),['P7a','P7b'],'exact day');check(detail('pnl').textContent.includes('+₩70'),'day sum');
      check(detail('pnl').textContent.includes('2026년 10월 7일'),'day heading');
      detail('pnl').querySelector('[data-pnl-sort="name"]').click();eq(names('pnl'),['P7a','P7b'],'sort preserves selection');
      select('pnl','2026-10-06');eq(names('pnl'),[],'empty no fake records');
      check(detail('pnl').querySelector('#clearPnlMonthBtn'),'empty selection clear control');
    """,
    'dividend_exact_month': r"""
      select('dividend','2025-10');eq(names('dividend'),['D2025'],'exact year');
      check(detail('dividend').textContent.includes('2025년 10월'),'exact heading');
      window.openDividendRecordDialog=record=>window.__edited=record;
      detail('dividend').querySelector('.edit-actual-div-btn').click();check(__edited.id==='D2025','dividend edit exact-year lookup');
      select('dividend','2026-10');eq(names('dividend'),['D2026','D7a','D7b','D8','I7','I8'],'month combined');
      document.getElementById('clearDivMonthBtn').click();check(names('dividend').includes('D2026')&&!names('dividend').includes('D2025'),'legacy period restored');
      check(u.modes.dividend===modes.MONTH,'mode retained');
    """,
    'dividend_day_interest': r"""
      await render('dividend',modes.DAY);select('dividend','2026-10-07');
      eq(names('dividend'),['D7a','D7b','I7'],'same day combined');
      check(detail('dividend').textContent.includes('배당 2건 · 이자 1건 · 합계 ₩120'),'counts and sum');
      const rows=[...detail('dividend').querySelectorAll('tbody tr')];
      check(rows.filter(r=>r.textContent.includes('이자')).length===1,'interest badge');
      const interest=rows.find(r=>r.textContent.includes('I7'));
      check(!interest.querySelector('button') && interest.textContent.includes('읽기 전용'),'interest action safety');
      const bars=[...host('dividend').querySelectorAll('.wealth-unified-flow-bar[data-bucket-key="2026-10-07"]')];
      for(const bar of bars){bar.dispatchEvent(new MouseEvent('click',{bubbles:true}));eq(names('dividend'),['D7a','D7b','I7'],'either series same detail');}
      check(__interest[0].income_type==='account_interest','type unchanged');
    """,
    'filters': r"""
      await render('pnl',modes.DAY);select('pnl','2026-10-07');
      renderRealizedPnl({records:__pnl.filter(r=>r.owner===currentOwner),monthly_schedule:[],available_years:[2025,2026]});
      const broker=document.getElementById('pnlBrokerFilter');broker.value='다른증권';broker.dispatchEvent(new Event('change',{bubbles:true}));
      await u.renderPnl();eq(names('pnl'),[],'broker excludes');check(!host('pnl').querySelector('.is-selected'),'broker clears');
      broker.value='all';currentOwner='모두';await u.renderPnl();select('pnl','2026-10-07');check(names('pnl').includes('OTHER'),'all owner');
      currentOwner='감사';await u.renderPnl();check(!host('pnl').querySelector('.is-selected'),'owner clears');
      document.querySelectorAll('#pnlTradeTypeTabs [data-trade-type]').forEach(n=>n.classList.toggle('active',n.dataset.tradeType==='ipo'));
      await u.renderPnl();select('pnl','2026-10-07');eq(names('pnl'),['P7a'],'trade filter');
      await render('dividend',modes.DAY);select('dividend','2026-10-07');
      await window.loadActualDividends(currentOwner,2026);
      const db=document.getElementById('dividendBrokerFilter');db.value='다른증권';db.dispatchEvent(new Event('change',{bubbles:true}));
      await u.renderDividend();eq(names('dividend'),[],'income broker excludes');check(!host('dividend').querySelector('.is-selected'),'income broker clears');
    """,
    'period_all_and_mode': r"""
      select('pnl','2025-10');
      for(const kind of ['pnl','dividend'])for(const mode of [modes.WEEK,modes.YEAR]){
        await render(kind,mode);check(!host(kind).querySelector('.is-clickable,[role="button"],.is-selected'),'unsupported no controls');
      }
      currentOwner='all-fixture';__pnl=[record('OLD','2023-10-05',1,{owner:currentOwner}),record('NEW','2026-10-05',2,{owner:currentOwner})];
      await render('pnl',modes.ALL);check(u.getDetailMode('pnl')===modes.MONTH,'ALL resolves month');
      select('pnl','2023-10');eq(names('pnl'),['OLD'],'ALL month exact');
      currentOwner='week-fixture';__pnl=[record('OLD','2025-10-05',1,{owner:currentOwner}),record('NEW','2026-10-05',2,{owner:currentOwner})];
      await render('pnl',modes.ALL);check(u.getDetailMode('pnl')===modes.WEEK,'ALL resolves week');
      check(!host('pnl').querySelector('[role="button"],.is-clickable'),'ALL week not clickable');
      document.querySelectorAll('#dividendModeTabs [data-div-mode]').forEach(n=>n.classList.toggle('active',n.dataset.divMode==='estimated'));
      await u.renderDividend();check(u.getDetail('dividend')===null,'estimated selection invalidated');
    """,
    'keyboard_pan': r"""
      await render('pnl',modes.DAY);const n=target('pnl','2026-10-07');n.focus();check(document.activeElement===n,'focusable');
      for(const key of ['Enter',' ']){n.dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true,cancelable:true}));eq(names('pnl'),['P7a','P7b'],'keyboard activates');}
      const vp=host('pnl').querySelector('.wealth-unified-viewport');const text=detail('pnl').textContent;
      vp.scrollLeft=0;vp.dispatchEvent(new Event('scroll'));check(detail('pnl').textContent===text,'scroll stable');
      const other=target('pnl','2026-10-08');
      other.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,pointerId:4,pointerType:'touch',clientX:100,clientY:100}));
      other.dispatchEvent(new PointerEvent('pointermove',{bubbles:true,pointerId:4,pointerType:'touch',clientX:150,clientY:100}));
      other.dispatchEvent(new MouseEvent('click',{bubbles:true,detail:1}));
      check(detail('pnl').textContent===text,'pan does not select');
      check(Number(n.getAttribute('width'))>0 && Number(n.getAttribute('height'))>200,'slot-sized target');
    """,
    'visible_range_stock_labels': r"""
      const frames=async()=>{for(let i=0;i<4;i++)await new Promise(requestAnimationFrame);};
      currentOwner='scale-fixture';
      __pnl=Array.from({length:60},(_,i)=>record('S'+i,`2026-${i<31?'08':'09'}-${String(i<31?i+1:i-30).padStart(2,'0')}`,i===0?1000000:10,{owner:currentOwner}));
      await render('pnl',modes.DAY);await frames();
      const vp=host('pnl').querySelector('.wealth-unified-viewport');
      const axis=host('pnl').querySelector('.wealth-unified-axis');const right=axis.textContent;
      target('pnl','2026-09-29').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
      const selected=detail('pnl').textContent;vp.scrollLeft=0;vp.dispatchEvent(new Event('scroll'));await frames();
      check(axis.textContent!==right,'viewport Y range recomputed');check(detail('pnl').textContent===selected,'scale update preserves detail');
      check([...host('pnl').querySelectorAll('svg text')].some(n=>n.style.visibility==='hidden'),'daily labels thinned');
      assetRecords=__pnl.map((r,i)=>({...r,total_value_krw:100000+i*1000,day_profit_krw:10}));
      u.renderStock();await frames();
      check(document.querySelector('#assetChart .wealth-unified-axis-right'),'stock right axis retained');
      const shell=document.querySelector('#assetChart .wealth-unified-chart-shell');
      check(shell.querySelector('.wealth-unified-axis').textContent!==shell.querySelector('.wealth-unified-axis-right').textContent,'stock asset/change scales separate');
    """,
}


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_income_bucket_runtime(chrome_preview, scenario):
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#pnl'})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthUnifiedTimeseries && !!window.WealthTimeseriesVisibleRange")
    assert evaluate('(async()=>{' + SETUP + SCENARIOS[scenario] + ';return true;})()')
    assert evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_native_mobile_bucket_tap_and_pan(chrome_preview):
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
    call('Emulation.setTouchEmulationEnabled', {'enabled': True, 'maxTouchPoints': 1})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#pnl'})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthUnifiedTimeseries && !!window.WealthTimeseriesVisibleRange")
    evaluate('(async()=>{' + SETUP + "await render('pnl',modes.DAY);return true;})()")
    def position(key):
        return evaluate("(()=>{const n=document.querySelector('#pnlBarChartWrap .wealth-unified-bucket-target[data-bucket-key=\"" + key + "\"]');n.scrollIntoView({block:'center',inline:'center',behavior:'instant'});const r=n.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()")
    def touch(kind, point=None):
        call('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [] if point is None else [point]})
    point = position('2026-10-07')
    call('Input.dispatchMouseEvent', {'type': 'mousePressed', **point, 'button': 'left', 'clickCount': 1})
    call('Input.dispatchMouseEvent', {'type': 'mouseReleased', **point, 'button': 'left', 'clickCount': 1})
    wait_for(evaluate, "WealthUnifiedTimeseries.getDetail('pnl').key==='2026-10-07'")
    evaluate("WealthUnifiedTimeseries.clearDetail('pnl')")
    touch('touchStart', point); touch('touchEnd')
    wait_for(evaluate, "WealthUnifiedTimeseries.getDetail('pnl').key==='2026-10-07'")
    assert evaluate("[...document.querySelectorAll('#pnlMonthlyDetail .td-stock-name')].map(n=>n.textContent).sort()") == ['P7a', 'P7b']
    point = position('2026-10-01')
    before = evaluate("document.querySelector('#pnlBarChartWrap .wealth-unified-viewport').scrollLeft")
    touch('touchStart', point)
    touch('touchMove', dict(x=point['x'] + 30, y=point['y']))
    touch('touchMove', dict(x=point['x'] + 60, y=point['y']))
    touch('touchEnd')
    assert evaluate("WealthUnifiedTimeseries.getDetail('pnl').key") == '2026-10-07'
    assert evaluate("document.querySelector('#pnlBarChartWrap .wealth-unified-viewport').scrollLeft") < before


def test_bucket_membership_and_ledger_writer():
    root = Path(__file__).resolve().parents[1]
    module = (root / 'app/static/wealth-timeseries-unified.js').read_text(encoding='utf-8')
    helper = module.split('  function bucketContains(', 1)[1].split('  function bucketHeading', 1)[0]
    script = "const assert=require('node:assert/strict');const core=require('./app/static/wealth-timeseries-period-core.js');const {MODES}=core;const supportsDetail=mode=>mode===MODES.DAY||mode===MODES.MONTH;function bucketContains(" + helper + r"""
assert(bucketContains('2025-10-05','2025-10',MODES.MONTH));
assert(!bucketContains('2026-10-05','2025-10',MODES.MONTH));
assert(bucketContains('2026-10-07T00:00:00+09:00','2026-10-07',MODES.DAY));
assert(!bucketContains('2026-10-08','2026-10-07',MODES.DAY));
assert(!bucketContains('2026-02-30','2026-02',MODES.MONTH));
assert(!bucketContains('bad','2026-10',MODES.MONTH));
assert(!bucketContains('2026-10-07','2026-10-07',MODES.WEEK));
"""
    subprocess.run(['node', '-e', script], cwd=root, check=True)
    for path in (root / 'app/static').glob('*.js'):
        assert 'MONTH CASHFLOW TREND' not in path.read_text(encoding='utf-8'), path
