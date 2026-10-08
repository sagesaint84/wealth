"""Synthetic portfolios, native Chrome input, no financial storage or imports."""
import json
import pytest
from app.services.ipo.presentation import derive_lead_manager_filters
from tests.test_account_reorder_runtime import chrome_preview, wait_for

FRAMES = '(async()=>{for(let i=0;i<4;i++)await new Promise(requestAnimationFrame);return true})()'
BOOT = r'''
window.__planning={revision:0,history:[],buckets:[{id:'core',name:'코어',target:50},{id:'growth',name:'성장',target:50}],accounts:{a:'core',b:'growth'},holdings:{h1:'growth',h3:''}};
window.__view={owner:'모두',fxRates:{USD:1300},accounts:[{id:'a',broker:'토스증권',name:'계좌 A',cash_krw:100},{id:'b',broker:'KB증권',name:'계좌 B',cash_krw:200}],holdings:[{id:'h1',account_id:'a',name:'예외종목',market_value_krw:500},{id:'h2',account_id:'a',name:'기본종목',market_value_krw:300},{id:'h3',account_id:'b',name:'미분류종목',market_value_krw:700}]};
window.__requests=[];
const nativeFetch=window.fetch;
window.fetch=async function(url,options){
 if(url==='/api/planning')return {ok:true,json:async()=>structuredClone(__planning)};
 if(String(url).endsWith('/import-preview')){
   __requests.push({url,body:JSON.parse(options.body)});
   return {ok:true,json:async()=>({preview_ticket:'synthetic',counts:{new:1,possible_duplicate:1},destination_account:{broker:'토스증권',account_name:'계좌 A',owner:'아빠'},rows:[]})};
 }
 return nativeFetch.apply(this,arguments);
};
'''

def start(preview, width, route):
    call, evaluate, port = preview
    call('Page.addScriptToEvaluateOnNewDocument', {'source':BOOT})
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':900,'deviceScaleFactor':1,'mobile':width==390})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#{route}'})
    wait_for(evaluate, "document.readyState==='complete'&&!!window.WealthIpoState&&!!document.getElementById('wealthBucketSummary')")
    evaluate(FRAMES)
    return call, evaluate

def click(call, evaluate, selector):
    evaluate(f"document.querySelector({selector!r}).scrollIntoView({{block:'center',behavior:'instant'}})")
    evaluate(FRAMES)
    point=evaluate(f'''(()=>{{const e=document.querySelector({selector!r}),r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,hit=document.elementFromPoint(x,y);return {{x,y,hit:e.contains(hit),target:hit?.outerHTML?.slice(0,160)}}}})()''')
    assert point.pop('hit'), point
    point.pop('target')
    for kind in ('mousePressed','mouseReleased'):
        call('Input.dispatchMouseEvent', {'type':kind,**point,'button':'left','clickCount':1})
    evaluate(FRAMES)

def no_overflow(evaluate, width):
    assert evaluate('document.documentElement.scrollWidth') <= width

def attach_broker_metadata(evaluate, variable):
    """Use the real presentation helper for synthetic browser response fixtures."""
    rows = evaluate(variable)
    for row in rows:
        row['lead_manager_filters'] = derive_lead_manager_filters(row.get('lead_managers'))
    evaluate(f'{variable}={json.dumps(rows, ensure_ascii=False)};WealthIpoState.setMarketIpos({variable});WealthIpoState.renderIpoList()')

@pytest.mark.parametrize('width',[1280,390])
def test_ipo_manager_month_status_and_snapshot(chrome_preview,width):
    call,evaluate=start(chrome_preview,width,'ipo')
    evaluate(r'''(()=>{
      const row=(id,managers,month,status)=>({ipo_id:id,company_name:id,lead_managers:managers,filter_group:status,presentation_sort_date:`2026-${month}-12`,subscription_start:`2026-${month}-12`,score:{score:61.9,coverage:75,core_missing:[]}});
      __ipos=[row('mira',['미래에셋증권'],'10','UPCOMING'),row('multi',['미래에셋증권','삼성증권'],'10','ACTIVE'),row('samsung',['삼성증권'],'10','PAST'),row('next',['미래에셋증권'],'11','UPCOMING'),row('past',['미래에셋증권'],'10','PAST'),row('unknown',[],'10','UPCOMING'),row('near-name',['미래에셋증권우'],'10','UPCOMING')];
      WealthIpoState.setMarketIpos(__ipos);WealthIpoState.setFilterGroup('ALL');WealthIpoState.setHistoryYear(2026);WealthIpoState.setHistoryMonth(10);WealthIpoState.setMonthExplicitlySelected(true);WealthIpoState.renderIpoList();
      window.__chooseBroker=name=>{const s=document.getElementById('ipoBrokerFilter');s.value=[...s.options].find(o=>o.textContent===name).value;s.dispatchEvent(new Event('change',{bubbles:true}))};
      window.__cards=()=>[...document.querySelectorAll('.ipo-card')].map(c=>c.dataset.ipoId).sort();
    })()''')
    attach_broker_metadata(evaluate, '__ipos')
    evaluate("__chooseBroker('미래에셋증권')")
    assert evaluate('__cards()') == ['mira','multi','past']
    assert evaluate("document.querySelector('[data-filter-group=ALL]').textContent") == '전체 4'
    for status, expected in [('UPCOMING',['mira']),('ACTIVE',['multi']),('PAST',['past']),('ALL',['mira','multi','past'])]:
        click(call,evaluate,f'[data-filter-group="{status}"]')
        assert evaluate('__cards()') == expected
    click(call,evaluate,'#ipoNextMonthBtn')
    assert evaluate('__cards()') == ['next']
    assert evaluate("document.getElementById('ipoBrokerFilter').value") == 'mirae'
    click(call,evaluate,'#ipoPrevMonthBtn')
    click(call,evaluate,'[data-filter-group="UPCOMING"]')
    click(call,evaluate,'#ipoNextMonthBtn')
    assert evaluate('__cards()') == ['next']
    assert evaluate("document.getElementById('ipoBrokerFilter').value") == 'mirae'
    click(call,evaluate,'#ipoPrevMonthBtn')
    click(call,evaluate,'[data-filter-group="ALL"]')
    evaluate("__chooseBroker('삼성증권')")
    assert evaluate('__cards()') == ['multi','samsung']
    # Accepted canonical replacement updates options and still combines filters.
    evaluate("WealthIpoState.setMarketIpos(__ipos.filter(i=>i.ipo_id==='multi'));WealthIpoState.renderIpoList()")
    assert evaluate('__cards()') == ['multi']
    assert evaluate("document.querySelector('.ipo-score-diagnostic')===null")
    no_overflow(evaluate,width)

@pytest.mark.parametrize('width',[1280,390])
def test_bucket_palette_filter_owner_and_totals(chrome_preview,width):
    call,evaluate=start(chrome_preview,width,'invest')
    wait_for(evaluate,"!!document.querySelector('[data-bucket-filter=core]')")
    click(call,evaluate,'[data-invest="buckets"]')
    evaluate("window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:__view}))")
    assert evaluate("document.querySelector('.wealth-bucket-contents [role=status]').textContent") == '5건 · 합계 1,800원'
    for theme in ['purple','white','oled']:
        evaluate(f"document.documentElement.dataset.theme='{theme}'")
        assert evaluate("getComputedStyle(document.querySelector('[data-bucket-filter=core]')).getPropertyValue('--bucket-color').trim()") == '#A78BFA'
        no_overflow(evaluate,width)
    click(call,evaluate,'[data-bucket-filter="core"]')
    assert evaluate("document.querySelector('[data-bucket-filter=core]').getAttribute('aria-pressed')") == 'true'
    assert evaluate("document.querySelector('.wealth-bucket-contents [role=status]').textContent") == '2건 · 합계 400원'
    click(call,evaluate,'[data-bucket-filter="core"]')
    assert evaluate("document.querySelectorAll('.wealth-bucket-constituent').length") == 5
    click(call,evaluate,'[data-bucket-filter="growth"]')
    assert evaluate("[...document.querySelectorAll('.wealth-bucket-constituent')].every(r=>r.dataset.bucketId==='growth')")
    click(call,evaluate,'[data-bucket-filter="__unclassified__"]')
    assert evaluate("document.querySelector('.wealth-bucket-contents [role=status]').textContent") == '1건 · 합계 700원'
    # Keyboard activation uses native button semantics.
    evaluate("document.querySelector('[data-bucket-filter=core]').focus()")
    call('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'text':'\r'})
    call('Input.dispatchKeyEvent',{'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    assert evaluate("document.querySelector('[data-bucket-filter=core]').getAttribute('aria-pressed')") == 'true'
    evaluate("window.dispatchEvent(new CustomEvent('wealth:portfolio',{detail:{...__view,owner:'엄마',accounts:[__view.accounts[1]]}}))")
    assert evaluate("document.querySelector('.wealth-bucket-contents [role=status]').textContent") == '2건 · 합계 900원'
    assert evaluate("document.querySelectorAll('[data-bucket-filter][aria-pressed=true]').length") == 0
    assert evaluate("document.querySelector('.wealth-bucket-contents').textContent.includes('계좌 A')") is False
    assert evaluate('__requests.length') == 0
    no_overflow(evaluate,width)

@pytest.mark.parametrize('width',[1280,390])
def test_wts_controls_type_preferences_and_preview_contract(chrome_preview,width):
    call,evaluate=start(chrome_preview,width,'pnl')
    evaluate(r'''(()=>{
      dashboard.accounts=[{id:'a',broker:'토스증권',name:'계좌 A',owner:'아빠'}];
      const row={date:'2026-10-07',name:'가상종목',symbol:'DEMO',market_type:'US',quantity:2,buy_amount:{krw:100},sell_amount:{krw:200},profit_loss:{krw:100},profit_rate:100};
      tossWtsState.rows=[row,{...row,date:'2026-10-06'}];tossWtsState.selectionTokens=['one','two'];tossWtsState.selectedIndices.clear();tossWtsState.importedIndices.clear();tossWtsState.importPreferences.clear();
      populateWtsAccounts();document.getElementById('wtsDestinationAccount').value='a';renderTossWtsFeedTable(tossWtsState.rows);updateWtsSelectionUI();
    })()''')
    for ids in [['tossWtsFromDate','tossWtsToDate','tossWtsBasisSelect','wtsDestinationAccount','btnFetchTossWtsFeed','btnWtsImportSelected'],['tossWtsIncomeFromDate','tossWtsIncomeToDate','wtsIncomeDestinationAccount','btnFetchTossWtsIncome','btnWtsIncomeImportSelected']]:
        assert evaluate(f"(()=>{{const es={ids!r}.map(id=>document.getElementById(id));return es.every(e=>e.closest('.toss-wts-controls')===es[0].closest('.toss-wts-controls'))&&es.every((e,i)=>!i||!!(es[i-1].compareDocumentPosition(e)&Node.DOCUMENT_POSITION_FOLLOWING))}})()")
    assert evaluate("[...document.querySelectorAll('#tossWtsTable th')].slice(1,5).map(e=>e.textContent)") == ['거래일자','시장','유형','종목명 (코드)']
    evaluate("const type=document.querySelector('#tossWtsTableBody select');type.value='ipo';type.dispatchEvent(new Event('change',{bubbles:true}));renderTossWtsFeedTable(tossWtsState.rows)")
    assert evaluate("document.querySelector('#tossWtsTableBody select').value") == 'ipo'
    click(call,evaluate,'.wts-row-cb[data-index="0"]')
    assert evaluate("document.getElementById('btnWtsImportSelected').disabled") is False
    no_overflow(evaluate,width)
    click(call,evaluate,'#btnWtsImportSelected')
    wait_for(evaluate,"document.getElementById('wtsImportModalOverlay').style.display==='flex'")
    payload=evaluate('__requests.at(-1).body')
    assert payload['account_id']=='a'
    assert payload['selected_items'][0]['selection_token']=='one'
    assert payload['selected_items'][0]['wealth_import']=={'stock_type':'ipo','ipo_subscription_fee_krw':2000}
    assert evaluate("document.getElementById('wtsIncludePossibleDuplicates').checked") is False
    click(call,evaluate,'#btnWtsModalClose')
    evaluate("location.hash='dividend'")
    evaluate(FRAMES)
    evaluate(r'''(()=>{
      tossWtsIncomeState.rows=[{date:'2026-10-07',name:'가상이자',income_type:'account_interest',market_type:'KR',currency:'KRW',gross_amount:100,tax_amount:10,net_amount:90}];
      tossWtsIncomeState.selectionTokens=['income-one'];tossWtsIncomeState.selectedIndices.clear();tossWtsIncomeState.importedIndices.clear();
      populateTossWtsIncomeAccounts();document.getElementById('wtsIncomeDestinationAccount').value='a';renderTossWtsIncomeTable();updateTossWtsIncomeSelectionUI();
    })()''')
    click(call,evaluate,'#tossWtsIncomeTableBody input[type=checkbox]')
    assert evaluate("document.getElementById('btnWtsIncomeImportSelected').disabled") is False
    no_overflow(evaluate,width)
    click(call,evaluate,'#btnWtsIncomeImportSelected')
    wait_for(evaluate,"document.getElementById('wtsIncomeImportModalOverlay').style.display==='flex'")
    payload=evaluate('__requests.at(-1).body')
    assert payload['account_id']=='a'
    assert payload['selected_items'][0]['row']['income_type']=='account_interest'
    assert payload['selected_items'][0]['selection_token']=='income-one'
    assert evaluate("document.getElementById('wtsIncomeIncludePossibleDuplicates').checked") is False
    no_overflow(evaluate,width)
