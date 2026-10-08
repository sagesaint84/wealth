"""Pre-parser instrumentation in native Chrome, synthetic HTTP and ledger data only."""
import base64
from pathlib import Path

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_workflow_ux_chrome import click, no_overflow, FRAMES


BOOT = r'''(() => {
  window.__ledgerTrace={legacyWrites:0,legacyCreated:0,legacyFrames:0,replacements:0,eyebrows:0,unifiedWrites:0,errors:[]};
  addEventListener('error',e=>{if(e.message)__ledgerTrace.errors.push(e.message)});
  const descriptor=Object.getOwnPropertyDescriptor(Element.prototype,'innerHTML');
  Object.defineProperty(Element.prototype,'innerHTML',{...descriptor,set(value){
    const text=String(value);
    if(text.includes('ledger-trend-chart'))__ledgerTrace.legacyWrites++;
    if(text.includes('6-MONTH CASHFLOW TREND'))__ledgerTrace.eyebrows++;
    if(this.id==='ledgerTrendContainer' && text.includes('wealth-unified-')){
      __ledgerTrace.unifiedWrites++;
      if(this.querySelector('.ledger-trend-chart'))__ledgerTrace.replacements++;
    }
    descriptor.set.call(this,value);
  }});
  new MutationObserver(records=>records.forEach(record=>record.addedNodes.forEach(node=>{
    if(node.nodeType!==1)return;
    __ledgerTrace.legacyCreated+=(node.matches('.ledger-trend-chart')?1:0)+node.querySelectorAll('.ledger-trend-chart').length;
    if(node.matches('.eyebrow') && node.textContent.includes('6-MONTH CASHFLOW TREND'))__ledgerTrace.eyebrows++;
  }))).observe(document,{childList:true,subtree:true});
  const sample=()=>{
    if([...document.querySelectorAll('.ledger-trend-chart')].some(e=>e.getBoundingClientRect().height>0))__ledgerTrace.legacyFrames++;
    requestAnimationFrame(sample);
  };requestAnimationFrame(sample);
  window.__ledgerCalls=[];
  window.__ledgerEmpty=false; window.__ledgerFail=false;
  window.__ledgerFixture=(year,month,owner)=>({year,month,owner,total_income:100000,total_expense:40000,
    net_savings:60000,savings_rate:60,recurring_expense_total:0,
    category_expenses:__ledgerEmpty?[]:[{category:'synthetic',amount:40000,percent:100}],
    transactions:__ledgerEmpty?[]:[{id:'synthetic-income',date:`${year}-${String(month).padStart(2,'0')}-10`,type:'income',amount:100000,category:'synthetic'},
      {id:'synthetic-expense',date:`${year}-${String(month).padStart(2,'0')}-11`,type:'expense',amount:40000,category:'synthetic'}],
    ...(__ledgerEmpty?{}:{monthly_trend:Array.from({length:6},(_,i)=>{
      const d=new Date(Date.UTC(year,month-6+i,1));return {year:d.getUTCFullYear(),month:d.getUTCMonth()+1,label:`${d.getUTCMonth()+1}월`,income:100000+i*1000,expense:40000};
    })})});
  const nativeFetch=window.fetch;
  window.fetch=async function(url,options){
    const parsed=new URL(url,location.href);
    if(parsed.pathname!=='/api/ledger')return nativeFetch.apply(this,arguments);
    __ledgerCalls.push(parsed.search);
    if(__ledgerFail)return {ok:false,status:500,json:async()=>({detail:'synthetic error'})};
    const data=__ledgerFixture(Number(parsed.searchParams.get('year')),Number(parsed.searchParams.get('month')),parsed.searchParams.get('owner'));
    if(data.owner==='synthetic-slow')await new Promise(resolve=>window.__releaseSlow=resolve);
    return {ok:true,json:async()=>data};
  };
})();'''

DELAY = r'''(() => {
  // Hold the actual script before it executes; no timer-based fallback.
  const headAppend=Element.prototype.append;
  Element.prototype.append=function(...nodes){
    if(nodes.some(node=>node?.dataset?.wealthTimeseriesUnified)){
      window.__releaseUnified=()=>headAppend.apply(this,nodes);return;
    }
    return headAppend.apply(this,nodes);
  };
})();'''


def start(preview, width, mode):
    call, evaluate, port = preview
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':900,'deviceScaleFactor':1,'mobile':width==390})
    if mode in ('blocked', 'core-blocked'):
        asset = 'unified' if mode == 'blocked' else 'period-core'
        call('Network.setBlockedURLs', {'urls':[f'*wealth-timeseries-{asset}.js*']})
    call('Page.addScriptToEvaluateOnNewDocument', {'source':BOOT + (DELAY if mode == 'delayed' else '')})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#income'})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthLedgerPeriodFilter")
    click(call, evaluate, '#incomeTabs [data-income="ledger"]')
    wait_for(evaluate, '!!rawLedgerData')
    return call, evaluate


def assert_no_shadow(evaluate):
    trace = evaluate('__ledgerTrace')
    for key in ('legacyWrites','legacyCreated','legacyFrames','replacements','eyebrows'):
        assert trace[key] == 0, trace
    assert not trace['errors'], trace


@pytest.mark.parametrize('width', [1280, 390])
@pytest.mark.parametrize('mode', ['normal', 'delayed', 'blocked', 'core-blocked'])
def test_ledger_renderer_load_contract(chrome_preview, width, mode):
    call, evaluate = start(chrome_preview, width, mode)
    if mode == 'delayed':
        wait_for(evaluate, "typeof __releaseUnified==='function'")
        evaluate(FRAMES)
        assert evaluate('WealthLedgerChartModule.state') == 'loading'
        assert evaluate("document.getElementById('ledgerTrendContainer').children.length") == 0
        assert_no_shadow(evaluate)
        click(call, evaluate, '#ledgerPrevMonthBtn')
        evaluate('loadLedger()')
        assert_no_shadow(evaluate)
        evaluate('__releaseUnified()')
    if mode in ('blocked', 'core-blocked'):
        wait_for(evaluate, "!!document.querySelector('.ledger-trend-chart')")
        assert evaluate('WealthLedgerChartModule.state') == 'failed'
        assert evaluate("document.querySelectorAll('.ledger-cat-row').length") == 1
        assert evaluate("document.getElementById('ledgerTxCountBadge').textContent") == '2건'
        assert evaluate("document.getElementById('ledgerTotalIncomeVal').textContent") == '₩100,000'
        evaluate("WealthLedgerTimeseriesHistory.expandHistory(document.querySelector('.wealth-timeseries-viewport[data-panzoom-kind=ledger]'))")
        assert evaluate('rawLedgerData.monthly_trend.length') == 12
        assert evaluate('__ledgerTrace.replacements') == 0
        assert evaluate('__ledgerTrace.eyebrows') == 0
        assert evaluate('__ledgerTrace.errors') == []
        evaluate(FRAMES)
        assert evaluate('__ledgerTrace.legacyFrames') > 0
        no_overflow(evaluate, width)
        return
    wait_for(evaluate, "!!document.querySelector('#ledgerTrendContainer .wealth-unified-chart')")
    assert_no_shadow(evaluate)
    assert evaluate('__ledgerTrace.unifiedWrites') >= 1
    for selector in ('#ledgerPrevMonthBtn', '#ledgerNextMonthBtn'):
        click(call, evaluate, selector)
        assert_no_shadow(evaluate)
    evaluate("document.getElementById('ledgerMonthPicker').value='2025-02';document.getElementById('ledgerMonthPicker').dispatchEvent(new Event('change',{bubbles:true}))")
    wait_for(evaluate, 'rawLedgerData.year===2025 && rawLedgerData.month===2')
    click(call, evaluate, '.family-tab[data-owner="아빠"]')
    wait_for(evaluate, "rawLedgerData.owner==='아빠'")
    evaluate('loadLedger()')
    evaluate(FRAMES)
    assert_no_shadow(evaluate)
    # Annual filter must not overwrite the unified period title.
    evaluate("document.getElementById('ledgerYearSelect').value='2024';document.getElementById('ledgerYearSelect').dispatchEvent(new Event('change',{bubbles:true}))")
    wait_for(evaluate, 'rawLedgerData.__ledger_annual_view && rawLedgerData.year===2024')
    evaluate(FRAMES)
    assert evaluate("document.querySelector('#ledgerTrendContainer').closest('.ledger-sub-panel').querySelector('h3').textContent") == '월간 현금흐름 추이'
    for mode_value, label in [('1D','일간'),('1W','주간'),('1M','월간'),('1Y','연간'),('ALL','전체')]:
        click(call, evaluate, f'.wealth-unified-ledger-controls [data-unified-period="{mode_value}"]')
        if mode_value == 'ALL':
            # ALL automatically resolves a supported bucket interval for the data span.
            assert evaluate('WealthUnifiedTimeseries.modes.ledger') == 'ALL'
        else:
            wait_for(evaluate, f"document.querySelector('#ledgerTrendContainer').closest('.ledger-sub-panel').querySelector('h3').textContent==='{label} 현금흐름 추이'")
        assert evaluate("document.querySelectorAll('#ledgerTrendContainer .wealth-unified-axis-label').length") >= 5
        assert evaluate("document.querySelectorAll('#ledgerTrendContainer svg text').length") > 0
        assert_no_shadow(evaluate)
        no_overflow(evaluate, width)
        assert evaluate("document.querySelector('#ledgerTrendContainer .wealth-unified-flow-legend').textContent.includes('수입') && document.querySelector('#ledgerTrendContainer .wealth-unified-flow-legend').textContent.includes('지출')")
    click(call, evaluate, '.wealth-unified-ledger-controls [data-unified-period="1M"]')
    before = evaluate("document.querySelectorAll('#ledgerTrendContainer .wealth-unified-flow-bar').length")
    assert evaluate('WealthLedgerTimeseriesHistory.expandHistory()') is True
    after = evaluate("document.querySelectorAll('#ledgerTrendContainer .wealth-unified-flow-bar').length")
    assert after > before
    assert_no_shadow(evaluate)
    # Native wheel exercises the chart's direct history/zoom path.
    evaluate("document.querySelector('#ledgerTrendContainer .wealth-unified-viewport').scrollIntoView({block:'center'})")
    point = evaluate("(()=>{const r=document.querySelector('#ledgerTrendContainer .wealth-unified-viewport').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+50}})()")
    call('Input.dispatchMouseEvent', {'type':'mouseWheel',**point,'deltaY':-240,'deltaX':0})
    evaluate(FRAMES)
    assert evaluate("document.querySelector('#ledgerTrendContainer .wealth-unified-content').getBoundingClientRect().width>document.querySelector('#ledgerTrendContainer .wealth-unified-viewport').clientWidth")
    evaluate("document.querySelector('#ledgerTrendContainer .wealth-unified-viewport').scrollLeft=30")
    evaluate(FRAMES)
    assert_no_shadow(evaluate)
    history_calls = evaluate('__ledgerCalls.length')
    for _ in range(24):
        call('Input.dispatchMouseEvent', {'type':'mouseWheel',**point,'deltaY':1000,'deltaX':0})
        evaluate(FRAMES)
        if evaluate('__ledgerCalls.length') > history_calls:
            break
    assert evaluate('__ledgerCalls.length') > history_calls
    assert evaluate("document.querySelectorAll('#ledgerTrendContainer .wealth-unified-flow-bar').length") > after
    assert_no_shadow(evaluate)
    if mode == 'normal':
        snapshot = Path('ledger-artifacts')
        snapshot.mkdir(exist_ok=True)
        (snapshot / f'ledger-{width}.png').write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format':'png'})['data']))
    click(call, evaluate, '#ledgerNextMonthBtn')
    # Latest owner response wins, including a deliberately stale response.
    evaluate("currentOwner='synthetic-slow';void loadLedger()")
    wait_for(evaluate, "typeof __releaseSlow==='function'")
    evaluate("currentOwner='synthetic-fast';loadLedger()")
    evaluate('__releaseSlow()')
    evaluate(FRAMES)
    assert evaluate('rawLedgerData.owner') == 'synthetic-fast'
    evaluate('__ledgerEmpty=true;loadLedger()')
    wait_for(evaluate, "!!document.querySelector('#ledgerTrendContainer .wealth-unified-empty')")
    evaluate('__ledgerFail=true;loadLedger()')
    assert evaluate("!!document.querySelector('#ledgerTrendContainer .wealth-unified-empty')")
    assert_no_shadow(evaluate)
    no_overflow(evaluate, width)
