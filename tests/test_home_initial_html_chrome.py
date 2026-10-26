"""The current home must render even before application JavaScript runs.

Synthetic loopback APIs only; the application and financial stores are never opened.
"""
import json
from html.parser import HTMLParser
from pathlib import Path
import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_static_transport_chrome import transport_server


def test_income_panel_start_tags_are_hidden_before_inline_route_selection():
    html = (Path(__file__).resolve().parents[1] / 'app/static/index.html').read_text(encoding='utf-8')
    panels = {
        'calendarPanel': 'calendar', 'realizedPnlPanel': 'pnl',
        'dividendPanel': 'dividend', 'ledgerSectionPanel': 'ledger', 'ipoPanel': 'ipo',
    }

    class PanelParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.panels = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get('id') in panels:
                self.panels.append(attrs['id'])
                assert tag == 'section'
                assert 'wealth-income-hidden' in attrs.get('class', '').split()
                # Selection must run before any panel content can be painted.
                start = self.get_starttag_text()
                selector = f"<script>WealthWorkspaceRoute.select(document.currentScript.parentElement, '{panels[attrs['id']]}');</script>"
                assert html.count(start) == 1
                assert start + selector in html

    parser = PanelParser()
    parser.feed(html)
    parser.close()
    assert sorted(parser.panels) == sorted(panels)


def test_home_initial_html_and_reload_preserve_current_workspace(chrome_preview):
    call, evaluate, _ = chrome_preview
    with transport_server(True) as port:
        call('Network.setBypassServiceWorker', {'bypass': True})
        call('Network.setCacheDisabled', {'cacheDisabled': True})
        for width in (320, 360, 390, 768, 1280):
            call('Emulation.setDeviceMetricsOverride', {
                'width': width, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
            call('Emulation.setScriptExecutionDisabled', {'value': True})
            previous = evaluate('performance.timeOrigin')
            call('Page.navigate', {'url': f'http://127.0.0.1:{port}/?width={width}#home'})
            wait_for(evaluate, f'performance.timeOrigin!=={previous!r} && document.readyState==="complete"')
            initial = evaluate(r'''(()=>{
              const visible = id => document.getElementById(id)?.getClientRects().length > 0;
              const ids = [...document.querySelectorAll('[id]')].map(e=>e.id);
              return {current:visible('wealthAssetNetWorth'),old:visible('summaryPanel'),
                title:document.getElementById('wealthPageTitle').textContent,
                nav:!!document.querySelector('.wealth-nav [aria-current="page"]'),
                css:[...document.querySelectorAll('link[rel=stylesheet]')].every(e=>!!e.sheet),
                duplicates:ids.filter((id,i)=>ids.indexOf(id)!==i),
                parent:document.getElementById('marketPanel').parentElement.id,
                width:document.documentElement.scrollWidth};
            })()''')
            assert initial['current'] and not initial['old'] and initial['nav'] and initial['css'], initial
            assert initial['title'] == '가족의 자산을 한눈에'
            assert initial['parent'] == 'wealthMarketSlot' and not initial['duplicates']
            assert initial['width'] <= width + 1
            assert evaluate('document.querySelectorAll("[data-legacy-summary],#wealthNetWorth,#wealthNetWorthDetails").length') == 0
            call('Emulation.setScriptExecutionDisabled', {'value': False})
            previous = evaluate('performance.timeOrigin')
            call('Page.reload')
            wait_for(evaluate, f'''performance.timeOrigin!=={previous!r} &&
              document.querySelector('#wealthAssetNetWorth')?.textContent==='397,000,000원' &&
              !!window.WealthUnifiedTimeseries''')
            assert evaluate('document.querySelectorAll(".wealth-workspace").length') == 1
            assert evaluate('document.querySelectorAll("#wealthAssetNetWorth").length') == 1
            for view in ('invest', 'assets', 'income', 'settings', 'home'):
                evaluate(f'location.hash={json.dumps(view)}')
                wait_for(evaluate, f'document.querySelector(".wealth-workspace").dataset.activeView==={json.dumps(view)}')
                assert evaluate(f'document.querySelector("[data-wealth-page={view}]").hidden') is False
            assert evaluate('document.querySelector("#wealthAssetNetWorth").textContent') == '397,000,000원'


@pytest.mark.parametrize('username,forced', [('SYNTHETIC', False), ('admin', False), ('SYNTHETIC', True)])
def test_initial_workspace_respects_authenticated_role_and_password_gate(chrome_preview, username, forced):
    call, evaluate, _ = chrome_preview
    me = json.dumps({'username': username, 'role': 'admin' if username == 'admin' else 'user',
                     'must_change_password': forced})
    call('Page.addScriptToEvaluateOnNewDocument', {'source': f'''
      window.__roleRequests=[];
      const naturalFetch=window.fetch;
      window.fetch=function(url,options){{
        __roleRequests.push(new URL(String(url),location.href).pathname);
        if(String(url)==='/api/auth/me')return Promise.resolve(new Response(JSON.stringify({me}),{{status:200}}));
        return naturalFetch.apply(this,arguments);
      }};
    '''})
    with transport_server(True) as port:
        call('Network.setBypassServiceWorker', {'bypass': True})
        call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#home'})
        if forced:
            wait_for(evaluate, 'document.querySelector("#forcePasswordModal")?.open===true')
            assert evaluate('getComputedStyle(document.getElementById("userAssetDashboardWrapper")).display') == 'none'
        elif username == 'admin':
            wait_for(evaluate, 'document.querySelector("#topbarUsername")?.textContent.includes("시스템 관리자")')
            assert evaluate('getComputedStyle(document.getElementById("userAssetDashboardWrapper")).display') == 'none'
            assert evaluate('getComputedStyle(document.getElementById("adminMainPanel")).display') != 'none'
            assert evaluate('document.getElementById("topbarFamilyBtn").closest(".topbar-actions")!==null')
        else:
            wait_for(evaluate, 'document.querySelector("#wealthAssetNetWorth")?.textContent==="397,000,000원"')
            assert evaluate('document.querySelector(".wealth-settings-actions #topbarFamilyBtn")!==null')
        if forced or username == 'admin':
            assert '/api/refresh-prices' not in evaluate('__roleRequests')
            assert '/api/dashboard' not in evaluate('__roleRequests')


# rAF samples precede compositor submission. Paint entries retain the browser's
# navigation-relative clock; no wall-clock or other capture channels are merged.
ROUTE_FRAMES = r"""
window.__routeFrames={frames:[],paints:[],errors:[],stop:false};
addEventListener('error',e=>__routeFrames.errors.push(e.message));
addEventListener('unhandledrejection',e=>__routeFrames.errors.push(String(e.reason)));
const snapshot=()=>({t:performance.now(),hash:location.hash,
 pages:[...document.querySelectorAll('[data-wealth-page]')].filter(n=>n.getClientRects().length).map(n=>n.dataset.wealthPage),
 nav:[...document.querySelectorAll('.wealth-nav [aria-current="page"]')].map(n=>n.dataset.wealthView),
 title:document.getElementById('wealthPageTitle')?.textContent,documentTitle:document.title,
 panels:['calendarPanel','realizedPnlPanel','dividendPanel','ledgerSectionPanel','ipoPanel'].filter(id=>document.getElementById(id)?.getClientRects().length),
 tab:document.querySelector('#incomeTabs [aria-selected="true"]')?.dataset.income,
 ledger:document.getElementById('ledgerTrendContainer')?.closest('.ledger-sub-panel')?.querySelector('h3')?.textContent,
 theme:document.documentElement.dataset.theme||'purple',width:document.documentElement.scrollWidth});
let previous='';const sample=()=>{const row=snapshot(),key=JSON.stringify({...row,t:0});if(key!==previous){__routeFrames.frames.push(row);previous=key;}if(!__routeFrames.stop)requestAnimationFrame(sample);};requestAnimationFrame(sample);
new PerformanceObserver(list=>{for(const entry of list.getEntries())__routeFrames.paints.push({name:entry.name,start:entry.startTime,...snapshot()});}).observe({type:'paint',buffered:true});
"""
ROUTE_LABELS={'home':'가족의 자산을 한눈에','invest':'주식 현황','assets':'자산과 계좌 관리','income':'머니 로그','settings':'설정'}
INCOME_PANELS={'calendar':'calendarPanel','pnl':'realizedPnlPanel','dividend':'dividendPanel','ledger':'ledgerSectionPanel','ipo':'ipoPanel'}
ROUTES=('home','invest','assets','income','ledger','pnl','dividend','ipo','calendar','settings','unknown','__proto__','constructor')


def route_expectation(route):
    key='income' if route in INCOME_PANELS else route if route in ROUTE_LABELS else 'home'
    return key,route if route in INCOME_PANELS else 'calendar'


def assert_route_frames(evaluate,route,width,theme='purple'):
    key,tab=route_expectation(route)
    trace=evaluate('__routeFrames')
    assert trace['paints'] and not trace['errors'],trace
    visible=[row for row in trace['frames'] if row['pages']]
    assert visible,trace
    for row in visible:
        assert row['pages']==[key] and row['nav']==[key],row
        assert row['title']==ROUTE_LABELS[key],row
        assert row['theme']==theme,row
        assert row['width']<=width+1, (row, evaluate('([...document.querySelectorAll("body *")].filter(n=>n.getBoundingClientRect().right>innerWidth+1&&n.getClientRects().length).map(n=>({tag:n.tagName,id:n.id,cls:n.className,right:n.getBoundingClientRect().right,text:n.textContent.slice(0,60)})).slice(0,15))'))
        if key=='income':
            # The selected panel may not yet be parsed; no other panel may paint.
            if row['panels']:assert row['panels']==[INCOME_PANELS[tab]],row
            if row.get('tab'):assert row['tab']==tab,row
        if row.get('ledger'):assert row['ledger']=='월간 현금흐름 추이',row
    for row in trace['paints']:
        if row['pages']:
            assert row['pages']==[key] and row['nav']==[key] and row['title']==ROUTE_LABELS[key],row
    if key=='income':assert trace['frames'][-1]['panels']==[INCOME_PANELS[tab]],trace
    assert evaluate('document.querySelectorAll(".wealth-workspace").length')==1
    assert evaluate('(()=>{const ids=[...document.querySelectorAll("[id]")].map(n=>n.id);return ids.length===new Set(ids).size;})()')
    return trace


def record_route(call,evaluate,port,route,width,theme='purple',reload=False):
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False})
    previous=evaluate('performance.timeOrigin')
    if reload:call('Page.reload',{'ignoreCache':False})
    else:call('Page.navigate',{'url':f'http://127.0.0.1:{port}/?route={route}&width={width}&theme={theme}#{route}'})
    wait_for(evaluate,f"performance.timeOrigin!=={previous!r} && document.readyState==='complete' && !!window.WealthUnifiedTimeseries")
    # A direct actual-dividend entry intentionally hides the data panel until
    # its asynchronous first chart commit. Four frames after DOM completion is
    # not that contract. Continue capturing ALL first frames until commit; do
    # not shorten the trace or permit another panel to paint while waiting.
    key, tab = route_expectation(route)
    if key == 'income':
        panel = INCOME_PANELS[tab]
        wait_for(evaluate, f"!!document.getElementById('{panel}')?.getClientRects().length && !document.getElementById('incomeTabs')?.hasAttribute('aria-busy')")
    evaluate('(async()=>{for(let n=0;n<4;n++)await new Promise(requestAnimationFrame);__routeFrames.stop=true;})()')
    return assert_route_frames(evaluate,route,width,theme)


def test_oled_sw_dividend_pending_commit_is_not_dom_complete(chrome_preview):
    """Deterministically reproduce the old four-frame completion race."""
    from tests.test_ledger_single_renderer_chrome import BOOT as LEDGER_BOOT
    call,evaluate,_=chrome_preview
    gate=r"""
    localStorage.setItem('app_theme','oled');
    window.__frameGate={open:false,releases:[]};
    const frameFetch=fetch;
    window.fetch=function(url,options){
      const pending=frameFetch.apply(this,arguments);
      if(new URL(String(url),location.href).pathname!=='/api/actual-dividends')return pending;
      return pending.then(response=>__frameGate.open?response:new Promise(resolve=>__frameGate.releases.push(()=>resolve(response))));
    };
    """
    call('Page.addScriptToEvaluateOnNewDocument',{'source':ROUTE_FRAMES+LEDGER_BOOT+gate})
    call('Emulation.setDeviceMetricsOverride',{'width':390,'height':900,'deviceScaleFactor':1,'mobile':False})
    call('Network.setBypassServiceWorker',{'bypass':False})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        wait_for(evaluate,'document.readyState==="complete" && !!window.WealthUnifiedTimeseries')
        evaluate("navigator.serviceWorker.register('/sw.js').then(()=>navigator.serviceWorker.ready)")
        wait_for(evaluate,'!!navigator.serviceWorker.controller')
        for reload in [False,True]:
            previous=evaluate('performance.timeOrigin')
            if reload:call('Page.reload',{'ignoreCache':False})
            else:call('Page.navigate',{'url':f'http://127.0.0.1:{port}/?theme=oled#dividend'})
            wait_for(evaluate,f'performance.timeOrigin!=={previous!r} && document.readyState==="complete" && !!window.WealthUnifiedTimeseries && __frameGate.releases.length>0')
            evaluate('(async()=>{for(let n=0;n<4;n++)await new Promise(requestAnimationFrame);return true;})()')
            assert evaluate("document.getElementById('incomeTabs').getAttribute('aria-busy')")=='true'
            assert not evaluate("!!document.getElementById('dividendPanel').getClientRects().length")
            evaluate('__frameGate.open=true;__frameGate.releases.splice(0).forEach(release=>release())')
            wait_for(evaluate,"!!document.getElementById('dividendPanel').getClientRects().length && !document.getElementById('incomeTabs').hasAttribute('aria-busy')")
            evaluate('(async()=>{for(let n=0;n<4;n++)await new Promise(requestAnimationFrame);__routeFrames.stop=true;})()')
            assert_route_frames(evaluate,'dividend',390,'oled')


def test_initial_route_first_frames_all_widths_and_normal_reload(chrome_preview):
    from tests.test_ledger_single_renderer_chrome import BOOT as LEDGER_BOOT
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':ROUTE_FRAMES+LEDGER_BOOT})
    call('Network.setBypassServiceWorker',{'bypass':True})
    call('Network.setCacheDisabled',{'cacheDisabled':True})
    with transport_server(True) as port:
        for width in (320,360,390,768,1280):
            for route in ROUTES:
                record_route(call,evaluate,port,route,width)
                # Same URL and profile, ordinary reload with HTTP cache enabled.
                call('Network.setCacheDisabled',{'cacheDisabled':False})
                record_route(call,evaluate,port,route,width,reload=True)
                call('Network.setCacheDisabled',{'cacheDisabled':True})


def test_initial_route_themes_service_worker_and_history(chrome_preview):
    from tests.test_ledger_single_renderer_chrome import BOOT as LEDGER_BOOT
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':ROUTE_FRAMES+LEDGER_BOOT+";try{localStorage.setItem('app_theme',new URL(location.href).searchParams.get('theme')||'purple');}catch(e){}"})
    call('Network.setCacheDisabled',{'cacheDisabled':False})
    call('Network.setBypassServiceWorker',{'bypass':False})
    with transport_server(True) as port:
        for theme in ('purple','white','oled'):
            for route in ROUTES[:10]:
                record_route(call,evaluate,port,route,390,theme)
                evaluate("navigator.serviceWorker.register('/sw.js').then(()=>navigator.serviceWorker.ready)")
                wait_for(evaluate,'!!navigator.serviceWorker.controller')
                record_route(call,evaluate,port,route,390,theme,reload=True)
                assert evaluate('!!navigator.serviceWorker.controller')
        # Hash navigation remains handled by the existing single hashchange listener.
        for route in ('invest','ledger','settings'):
            evaluate(f'location.hash={json.dumps(route)}')
            wait_for(evaluate,f"document.querySelector('.wealth-workspace').dataset.activeView==={json.dumps(route_expectation(route)[0])}")
        evaluate('history.back()')
        wait_for(evaluate,"location.hash==='#ledger' && document.querySelector('.wealth-workspace').dataset.incomeTab==='ledger'")
        assert evaluate("document.querySelector('[data-wealth-page=home]').hidden")
        evaluate('history.forward()')
        wait_for(evaluate,"location.hash==='#settings' && document.querySelector('.wealth-workspace').dataset.activeView==='settings'")
        # Data/period changes may legitimately change the chart title after bootstrap.
        evaluate("location.hash='ledger'")
        wait_for(evaluate,"document.querySelector('.wealth-workspace').dataset.incomeTab==='ledger'")
        evaluate("WealthUnifiedTimeseries.modes.ledger=WealthTimeseriesPeriodCore.MODES.YEAR;WealthUnifiedTimeseries.renderLedger(rawLedgerData)")
        wait_for(evaluate,"document.getElementById('ledgerTrendContainer').closest('.ledger-sub-panel').querySelector('h3').textContent==='연간 현금흐름 추이'")


@pytest.mark.parametrize('username,forced',[('SYNTHETIC',False),('admin',False),('SYNTHETIC',True)])
def test_initial_non_home_routes_keep_auth_gates(chrome_preview,username,forced):
    call,evaluate,_=chrome_preview
    me=json.dumps({'username':username,'role':'admin' if username=='admin' else 'user','must_change_password':forced})
    call('Page.addScriptToEvaluateOnNewDocument',{'source':f"window.__roleRequests=[];const native=window.fetch;window.fetch=function(url,...args){{__roleRequests.push(new URL(String(url),location.href).pathname);if(String(url)==='/api/auth/me')return Promise.resolve(new Response(JSON.stringify({me}),{{status:200}}));return native.call(this,url,...args);}};"})
    with transport_server(True) as port:
        for route in ('assets','ledger','settings'):
            call('Page.navigate',{'url':f'http://127.0.0.1:{port}/?auth-route={route}#{route}'})
            wait_for(evaluate,"document.readyState==='complete' && typeof currentUserProfile!=='undefined' && !!currentUserProfile")
            if forced:
                wait_for(evaluate,'document.querySelector("#forcePasswordModal")?.open===true')
            elif username=='admin':
                wait_for(evaluate,'document.querySelector("#topbarUsername")?.textContent.includes("시스템 관리자")')
            else:
                wait_for(evaluate,'document.querySelector("#topbarUsername")?.textContent.includes("SYNTHETIC")')
            if forced or username=='admin':
                assert evaluate('getComputedStyle(document.getElementById("userAssetDashboardWrapper")).display')=='none'
                assert '/api/refresh-prices' not in evaluate('__roleRequests')
                assert '/api/dashboard' not in evaluate('__roleRequests')
