"""Synthetic actual Chromium layout checks; no financial server or external data."""
import base64
import json
import pytest
from tests.test_account_reorder_runtime import chrome_preview, wait_for, ReorderPreview

BOOT = r"""
window.__uiErrors=[];window.addEventListener('error',e=>__uiErrors.push(e.message));
window.addEventListener('unhandledrejection',e=>__uiErrors.push(String(e.reason)));
const naturalError=console.error;console.error=function(...args){__uiErrors.push(args.map(String).join(' '));return naturalError.apply(this,args);};
window.__uiExcluded=new Set(['excluded']);window.__uiWrites=[];
const family=['아빠','엄마','자녀'];
const make=(id,name,state,user)=>({ipo_id:id,company_name:name,market:'KOSDAQ',stock_code:'123456',
 subscription_start:'2026-10-19',subscription_end:'2026-10-20',expected_listing_date:'2026-10-29',
 presentation_sort_date:'2026-10-19',presentation_month_keys:['2026-10'],presentation_month_sort_dates:{'2026-10':'2026-10-19'},
 market_state:state,user_state:user,filter_group:'ACTIVE',lead_managers:['가상증권'],final_offer_price:12000,
 updated_at:'2026-10-19T12:00:00+09:00',sources:{metalogos160:{},dart_schedule:{},kind:{},npay:{},naver:{}}});
window.__uiRows=[make('long','가상기업 아주 긴 기업명 및 출처 문자열 레이아웃 검증','SUBSCRIPTION_OPEN','APPLIED'),
 make('listing','가상 상장예정 기업','LISTING_UPCOMING','ALLOCATED_UNSOLD'),
 make('listed','가상 상장완료 기업','LISTED','PARTIALLY_SOLD'),
 make('unknown','가상 일정 확인 기업','DATE_UNKNOWN','NOT_APPLIED'),
 make('excluded','가상 제외 후 일정 변경 기업','UPCOMING','NOT_APPLIED')];
window.__uiApps=Object.fromEntries(__uiRows.map(r=>[r.ipo_id,{target_owners:family,applied_owners:['아빠'],state:'some',all_applied:false}]));
const natural=window.fetch;
window.fetch=function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 const reply=value=>Promise.resolve(new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}}));
 if(path==='/api/ipo/market')return reply({ipos:__uiRows.map(r=>({...r,user_excluded:__uiExcluded.has(r.ipo_id),excluded_schedule_changed:r.ipo_id==='excluded'}))});
 if(path==='/api/ipo/applications')return reply({revision:__uiWrites.length,applications:__uiApps,family_members:family});
 if(path.startsWith('/api/ipo/visibility/') && options.method==='PUT'){
  const id=decodeURIComponent(path.split('/').pop()),body=JSON.parse(options.body);__uiWrites.push({id,...body});
  body.excluded?__uiExcluded.add(id):__uiExcluded.delete(id);return reply({revision:__uiWrites.length});
 }
 if(path.startsWith('/api/ipo/applications/') && options.method==='PUT'){
  const id=decodeURIComponent(path.split('/').pop()),body=JSON.parse(options.body);__uiWrites.push({id,...body});
  __uiApps[id].applied_owners=body.applied_owners;return reply({...__uiApps[id],revision:__uiWrites.length});
 }
 if(path==='/api/moneylog/calendar'){
  const events=[{id:'sub',date:'2026-10-19',type:'ipo_subscription',title:__uiRows[0].company_name+' 청약 첫째날',owner:'모두',meta:{ipo_id:'long',offer_price:12000}},
   {id:'listing',date:'2026-10-19',type:'ipo_listing',title:'가상기업 상장예정',owner:'모두',meta:{ipo_id:'listing',listing_status:'expected'}}];
  for(const [i,type,amount] of [[1,'realized_pnl',5000],[2,'realized_pnl',-3000],[3,'dividend',2000],[4,'ledger_income',4000],[5,'ledger_expense',1000]])
   events.push({id:'event'+i,date:i===2?'2026-10-20':'2026-10-19',type,title:'가상 '+type,owner:'아빠',amount_krw:amount,meta:{}});
  return reply({events:events.filter(e=>!__uiExcluded.has(e.meta.ipo_id))});
 }
 return natural.call(this,url,options);
};
"""


def open_list(call, evaluate, port, width):
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':900,'deviceScaleFactor':1,'mobile':False})
    call('Page.addScriptToEvaluateOnNewDocument', {'source':BOOT})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#ipo'})
    wait_for(evaluate,"!!window.WealthIpoState && !!window.WealthCalendar && typeof window.loadIpoSchedule==='function'")
    evaluate("(async()=>{await loadIpoSchedule();WealthIpoState.setFilterGroup('ALL');WealthIpoState.setHistoryYear(2026);WealthIpoState.setHistoryMonth(10);WealthIpoState.setMonthExplicitlySelected(true);WealthIpoState.renderIpoList();return true;})()")
    wait_for(evaluate,"document.querySelectorAll('#ipoListWrapper .ipo-card').length===4")


def open_calendar(evaluate):
    evaluate("(async()=>{setIncomeTab('calendar');WealthCalendar.setSelectedDate('2026-10-19');await WealthCalendar.loadCalendar();return true;})()")
    wait_for(evaluate,"document.querySelector('#calendarDetailPanel .cal-ipo-exclude')?.getClientRects().length>0")


def screenshot(call, path):
    path.write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})['data']))


@pytest.fixture
def ui_chrome_preview(monkeypatch):
    # Serve the real worker at its actual root URL, rather than suppressing the
    # preview harness's otherwise expected registration-404 console error.
    original = ReorderPreview.do_GET
    def serve(self):
        if self.path == '/sw.js':
            self.send(self.server.assets['sw.js'], 'application/javascript; charset=utf-8')
            return
        return original(self)
    monkeypatch.setattr(ReorderPreview, 'do_GET', serve)
    session = chrome_preview.__wrapped__()
    try:
        yield next(session)
    finally:
        session.close()


@pytest.mark.parametrize('width',[320,390,768,1280])
def test_ipo_calendar_dark_ui_and_actions(ui_chrome_preview, width, tmp_path):
    call,evaluate,port=ui_chrome_preview
    open_list(call,evaluate,port,width)
    assert evaluate("document.documentElement.scrollWidth<=innerWidth"), width
    assert evaluate("parseFloat(getComputedStyle(document.querySelector('.ipo-schedule-notice')).fontSize)<=12"), width
    assert evaluate("parseFloat(getComputedStyle(document.querySelector('.ipo-source-meta')).fontSize)<=11.5"), width
    assert evaluate("[...document.querySelectorAll('.ipo-card-actions .button')].every(b=>{const s=getComputedStyle(b);return parseFloat(s.fontSize)<=12&&b.offsetHeight>=30&&b.offsetHeight<=36})"), width
    assert evaluate("[...document.querySelectorAll('.ipo-card')].every(c=>{const a=c.querySelector('.ipo-card-actions').getBoundingClientRect(),t=c.querySelector('.ipo-card-title-group').getBoundingClientRect();return a.left>=t.right-1||a.top>=t.bottom-1})"), width
    assert evaluate("[...document.querySelectorAll('.ipo-source-meta')].every(n=>n.clientWidth>0&&getComputedStyle(n).textOverflow==='ellipsis')"), width
    screenshot(call,tmp_path/'list.png')
    evaluate("document.querySelector('[data-ipo-id=long] .ipo-card-detail-toggle').click();true")
    assert evaluate("document.querySelector('[data-ipo-id=long] .ipo-card-body').getClientRects().length>0 && document.querySelector('[data-ipo-id=long] .ipo-member-chk').getClientRects().length>0")
    assert evaluate("document.documentElement.scrollWidth<=innerWidth"), width
    screenshot(call,tmp_path/'detail.png')
    evaluate("document.querySelector('#ipoExcludedToggle').click();true")
    assert evaluate("document.querySelectorAll('#ipoListWrapper .ipo-card').length===1 && document.querySelector('#ipoListWrapper').textContent.includes('제외 후 일정 변경')")
    evaluate("document.querySelector('.ipo-visibility-toggle').click();true")
    wait_for(evaluate,"__uiWrites.length===1 && document.querySelectorAll('#ipoListWrapper .ipo-card').length===0")
    assert evaluate("__uiWrites[0].excluded===false && __uiApps.long.applied_owners[0]==='아빠'")
    evaluate("document.querySelector('#ipoExcludedToggle').click();true")
    open_calendar(evaluate)
    assert evaluate("document.documentElement.scrollWidth<=innerWidth"), width
    assert evaluate("[...document.querySelectorAll('#calendarDetailPanel .calendar-event-item')].every(n=>n.scrollWidth<=n.clientWidth+1)"), width
    assert evaluate("parseFloat(getComputedStyle(document.querySelector('.cal-ipo-restore-link')).fontSize)<=12 && getComputedStyle(document.querySelector('.cal-ipo-restore-link')).color===getComputedStyle(document.querySelector('.cal-ipo-exclude')).color"), width
    assert evaluate("[...document.querySelectorAll('.cal-ipo-member-chk')].every(n=>n.getClientRects().length>0)"), width
    assert evaluate("document.querySelector('.cal-day-cell.is-selected') && getComputedStyle(document.querySelector('.cal-day-cell.is-selected')).outlineStyle==='solid'")
    assert evaluate("['tone-ipo-subscription','tone-ipo-listing','tone-profit','tone-loss','tone-dividend','tone-income','tone-expense'].every(c=>document.querySelector('.cal-badge.'+c))"), width
    screenshot(call,tmp_path/'calendar.png')
    evaluate("document.querySelector('.cal-ipo-member-chk[data-member=엄마]').click();true")
    wait_for(evaluate,"__uiWrites.length===2")
    assert evaluate("__uiApps.long.applied_owners.includes('엄마') && __uiApps.long.applied_owners.includes('아빠')")
    evaluate("document.querySelector('.cal-ipo-exclude[data-ipo=long]').click();true")
    wait_for(evaluate,"__uiWrites.length===3 && !document.querySelector('.cal-ipo-exclude[data-ipo=long]')")
    assert evaluate("__uiWrites[2].excluded===true")
    assert evaluate("__uiErrors.length===0"), evaluate("__uiErrors")
    assert not [e for e in evaluate.load_errors if e.get('method')=='Runtime.exceptionThrown'], evaluate.load_errors
