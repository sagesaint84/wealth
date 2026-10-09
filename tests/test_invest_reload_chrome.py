"""Native Chrome reload/first-frame checks; synthetic APIs, no app/data import."""
import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for

TABS = ['overview','heatmap','records','buckets','tax_accounts','holdings']
PANEL = {'overview':'summaryPanel','heatmap':'assetHeatmapPanel','records':'recordsPanel',
         'buckets':'bucketPanel','tax_accounts':'recordsPanel','holdings':'holdingsPanel'}
BOOT = r'''
const NativeDate=Date;
Date=class extends NativeDate {constructor(...args){super(...(args.length?args:['2027-09-30T15:30:00Z']));} static now(){return new NativeDate('2027-09-30T15:30:00Z').getTime();}};
window.__trace={documentId:Math.random(),legacyCreated:0,frames:[],errors:[],held:[]};
window.addEventListener('error',e=>__trace.errors.push(e.message));
const nativeFetch=window.fetch;
window.fetch=function(url,...args){
 if(['/api/dashboard','/api/realized-pnl','/api/actual-dividends'].some(p=>String(url).startsWith(p))){
  __trace.held.push(String(url));return new Promise(()=>{});
 }
 return nativeFetch.call(this,url,...args);
};
const legacy=['netWorthRow','safeAssetRow','subAssetBreakdown','pnlSubBreakdown'];
new MutationObserver(records=>{for(const record of records)for(const node of record.addedNodes){
 if(node.nodeType!==1)continue;
 __trace.legacyCreated+=legacy.filter(id=>node.id===id).length;
 for(const id of legacy)__trace.legacyCreated+=node.querySelectorAll('#'+id).length;
}}).observe(document,{childList:true,subtree:true});
const visible=e=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
function sample(){
 const panels=['summaryPanel','assetHeatmapPanel','recordsPanel','bucketPanel','holdingsPanel'];
 const shown=panels.filter(id=>visible(document.getElementById(id)));
 const labels=['pnlYearLabel','pnlMonthLabel','divYearLabel','divMonthLabel'].map(id=>document.getElementById(id)?.textContent||'');
 if(shown.length)__trace.frames.push({shown,labels});
 requestAnimationFrame(sample);
}
requestAnimationFrame(sample);
'''


def start(preview, width):
    call, evaluate, port = preview
    call('Page.addScriptToEvaluateOnNewDocument', {'source':BOOT})
    call('Emulation.setTimezoneOverride', {'timezoneId':'America/Los_Angeles'})
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':900,'deviceScaleFactor':1,'mobile':width==390})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#invest'})
    wait_for(evaluate, "document.readyState==='complete'&&!!document.querySelector('.wealth-invest-tabs')")
    return call, evaluate


def frames(evaluate):
    evaluate('(async()=>{for(let i=0;i<5;i++)await new Promise(requestAnimationFrame);return true;})()')


@pytest.mark.parametrize('width',[1280,390])
@pytest.mark.parametrize('tab',TABS+['invalid','missing'])
def test_invest_reload_first_visible_panel_and_no_legacy_flash(chrome_preview,width,tab):
    call, evaluate = start(chrome_preview,width)
    if tab in TABS:
        evaluate(f"document.querySelector('[data-invest={tab}]').click()")
        assert evaluate("sessionStorage.getItem('wealth_invest_tab')") == tab
    elif tab == 'invalid':
        evaluate("sessionStorage.setItem('wealth_invest_tab','<unexpected>')")
    else:
        evaluate("sessionStorage.removeItem('wealth_invest_tab')")
    previous_document = evaluate('__trace.documentId')
    call('Page.reload', {'ignoreCache':True})
    expected = tab if tab in TABS else 'overview'
    wait_for(evaluate, f"window.__trace?.documentId!=={previous_document}&&document.readyState==='complete'&&document.documentElement.dataset.wealthInvestTab==='{expected}'&&document.querySelector('[data-invest={expected}]')?.getAttribute('aria-pressed')==='true'")
    frames(evaluate)
    trace = evaluate('__trace')
    assert trace['legacyCreated'] == 0
    assert trace['frames'], trace
    assert all(row['shown']==[PANEL[expected]] for row in trace['frames']), trace['frames']
    assert all(not any(label in ('09월','26년') for label in row['labels']) for row in trace['frames'])
    assert evaluate("['pnlYearLabel','pnlMonthLabel','divYearLabel','divMonthLabel'].map(id=>document.getElementById(id).textContent)") == ['27년','10월','27년','10월']
    assert evaluate("['pnlCurrentMonthText','dividendCurrentMonthText'].map(id=>document.getElementById(id).textContent)") == ['2027년 10월']*2
    assert evaluate("['pnlYearSelect','dividendYearSelect'].map(id=>document.getElementById(id).value)") == ['2027']*2
    assert evaluate("document.querySelectorAll('.wealth-invest-tabs button[aria-pressed=true]').length") == 1
    assert evaluate("document.documentElement.scrollWidth") <= width
    for name, panel in PANEL.items():
        if panel == PANEL[expected]:
            assert not evaluate(f"document.getElementById('{panel}').classList.contains('wealth-invest-hidden')")
        else:
            assert evaluate(f"document.getElementById('{panel}').classList.contains('wealth-invest-hidden')")
    if expected in ('records','tax_accounts'):
        view = 'tax_accounts' if expected=='tax_accounts' else 'combo'
        assert evaluate('currentRecordView') == view
        assert evaluate("document.querySelector('#recordViewTabs .active').dataset.view") == view
        assert evaluate("document.getElementById('recordsHeadingText').textContent") == ('절세계좌' if view=='tax_accounts' else '주식기록')
    assert evaluate("['totalValue','summaryKrwStockVal','summaryUsdStockValKrw','totalProfit','summaryRealizedPnl','summaryActualDividend'].map(id=>document.getElementById(id).textContent)") == ['—']*6
    assert evaluate("document.querySelectorAll('#summaryPanel #netWorthRow,#summaryPanel #safeAssetRow,#summaryPanel #subAssetBreakdown').length") == 0
    assert evaluate("['wealthAssetNetWorth','wealthAssetInvest','wealthAssetExpected','wealthAssetRealized','wealthAssetSafe'].every(id=>!!document.getElementById(id))")
    assert not trace['errors'], trace['errors']


@pytest.mark.parametrize('width',[1280,390])
def test_negative_current_month_loss_color_in_all_themes(chrome_preview,width):
    _,evaluate=start(chrome_preview,width)
    evaluate(r'''(()=>{
      const rows=[{date:'2026-10-01',owner:'모두',pnl_krw:20501333},{date:'2027-10-01',owner:'모두',pnl_krw:-789783}];
      renderSummary({realized_pnl_records:rows,realized_pnl_summary:{total_pnl_krw:19711550,monthly_schedule:[{month:10,total_krw:19711550}]}});
    })()''')
    for theme in ('purple','white','oled'):
        evaluate(f"document.documentElement.dataset.theme='{theme}'")
        frames(evaluate)
        assert evaluate("document.getElementById('summaryRealizedPnlMonth').textContent") == '-₩789,783'
        assert evaluate("document.getElementById('summaryRealizedPnlMonth').classList.contains('loss')")
        assert not evaluate("document.getElementById('summaryRealizedPnlMonth').classList.contains('gain')")
        color = evaluate("getComputedStyle(document.getElementById('summaryRealizedPnlMonth')).color")
        assert color != 'rgb(244, 63, 94)', color
