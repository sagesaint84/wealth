"""Cold-route native Chrome coverage with controlled, synthetic IPO responses."""
import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_workflow_ux_chrome import click, no_overflow


BOOT = r'''(() => {
  const nativeFetch = window.fetch;
  window.__ipoCalls = [];
  const day = new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Seoul'}).format(new Date());
  const row = {ipo_id:'startup-fixture',company_name:'Startup synthetic IPO',
    subscription_start:day,subscription_end:day,presentation_sort_date:day,
    filter_group:'ACTIVE',lead_managers:['유진증권'],
    lead_manager_filters:[{key:'eugene',broker_id:'eugene',display_name:'유진투자증권'}]};
  const applications = new Promise(resolve => window.__releaseIpoApplications = () =>
    resolve({ok:true,json:async()=>({revision:1,applications:{},family_members:['아빠']})}));
  window.fetch = function(url, options) {
    const path = new URL(String(url), location.href).pathname;
    if (!['/api/ipo/applications','/api/ipo/market','/api/ipo/market/refresh'].includes(path))
      return nativeFetch.apply(this, arguments);
    __ipoCalls.push({path,method:options?.method || 'GET'});
    if (path === '/api/ipo/applications') return applications;
    return Promise.resolve({ok:true,json:async()=>path.endsWith('/refresh')
      ? {market:{ipos:[{...row,company_name:'Refreshed synthetic IPO'}]}} : {ipos:[row]}});
  };
})();'''

FRAMES = '(async()=>{for(let i=0;i<4;i++)await new Promise(requestAnimationFrame);})()'


def navigate(call, evaluate, port, route, width):
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':900,
         'deviceScaleFactor':1,'mobile':width == 390})
    call('Page.addScriptToEvaluateOnNewDocument', {'source':BOOT})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#{route}'})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthIpoState")


def assert_loaded(evaluate):
    wait_for(evaluate, "document.querySelector('.ipo-card')?.dataset.ipoId==='startup-fixture'")
    evaluate(FRAMES)
    assert evaluate('__ipoCalls') == [
        {'path':'/api/ipo/applications','method':'GET'},
        {'path':'/api/ipo/market','method':'GET'},
    ]
    text = evaluate("document.getElementById('ipoListWrapper').textContent")
    assert 'Startup synthetic IPO' in text
    assert '공모주 일정을 불러오는 중입니다...' not in text
    assert '등록된 공모주 일정이 없습니다.' not in text
    assert evaluate("WealthIpoState.getCanonicalMarketIpos()[0].lead_managers") == ['유진증권']


@pytest.mark.parametrize('width', [1280,390])
def test_direct_ipo_cold_start_and_reload_load_once_without_refresh_post(chrome_preview, width):
    call,evaluate,port = chrome_preview
    navigate(call,evaluate,port,'ipo',width)
    # No tab click: module-ready already started the applications read.
    assert evaluate('__ipoCalls') == [{'path':'/api/ipo/applications','method':'GET'}]
    assert evaluate("document.querySelector('.wealth-workspace').dataset.activeView") == 'income'
    assert evaluate("document.getElementById('ipoPanel').classList.contains('wealth-income-hidden')") is False
    # A simultaneous tab selection and callers share the complete GET cycle.
    evaluate('__firstLoad=loadIpoSchedule();true')
    click(call,evaluate,'#incomeTabs [data-income=ipo]')
    evaluate('__secondLoad=loadIpoSchedule();true')
    assert evaluate('__firstLoad===__secondLoad') is True
    evaluate('__releaseIpoApplications()')
    assert_loaded(evaluate)
    no_overflow(evaluate,width)

    call('Page.reload', {'ignoreCache':True})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthIpoState && __ipoCalls.length===1")
    evaluate('__releaseIpoApplications()')
    assert_loaded(evaluate)
    no_overflow(evaluate,width)
    # Refresh POST retains its explicit button-only behavior.
    click(call,evaluate,'#ipoRefreshBtn')
    wait_for(evaluate, "document.getElementById('ipoListWrapper').textContent.includes('Refreshed synthetic IPO')")
    assert evaluate("__ipoCalls.filter(c=>c.path==='/api/ipo/market/refresh')") == [
        {'path':'/api/ipo/market/refresh','method':'POST'}]


@pytest.mark.parametrize('route', ['income','calendar','pnl','dividend','ledger'])
def test_other_cold_routes_do_not_load_ipo_until_normal_tab_click(chrome_preview, route):
    call,evaluate,port = chrome_preview
    navigate(call,evaluate,port,route,1280)
    evaluate(FRAMES)
    # Calendar already reads applications for its own IPO events. Preserve that
    # pre-existing read; no IPO module market read or additional app read occurs.
    expected = [{'path':'/api/ipo/applications','method':'GET'}] if route in ('income','calendar') else []
    assert evaluate('__ipoCalls') == expected
    evaluate('__releaseIpoApplications()')
    evaluate(FRAMES)
    evaluate('__ipoCalls=[]')
    click(call,evaluate,'#incomeTabs [data-income=ipo]')
    evaluate('__releaseIpoApplications()')
    assert_loaded(evaluate)


def test_failed_load_releases_pending_cycle_for_retry(chrome_preview):
    call,evaluate,port = chrome_preview
    navigate(call,evaluate,port,'pnl',1280)
    evaluate(r'''window.__originalIpoFetch=window.fetch;
      window.fetch=(url,...args)=>String(url)==='/api/ipo/applications'
        ? Promise.reject(new Error('synthetic load failure')) : __originalIpoFetch(url,...args);''')
    evaluate('(async()=>{await loadIpoSchedule();})()')
    assert evaluate("document.getElementById('ipoListWrapper').textContent.includes('오류가 발생했습니다')")
    evaluate('window.fetch=__originalIpoFetch;loadIpoSchedule();__releaseIpoApplications()')
    assert_loaded(evaluate)
