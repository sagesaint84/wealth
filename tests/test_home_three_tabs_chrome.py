"""Home tabs in native Chromium; invented, in-memory APIs only."""
import json
import pytest
from tests.test_account_reorder_runtime import chrome_preview, wait_for as wait_for_page
from tests.test_static_transport_chrome import transport_server

BOOT = r"""
window.__tabs={errors:[],markets:0,writes:[],views:0,hold:false,fail:false,pending:[]};
addEventListener('error',e=>__tabs.errors.push(e.message));
addEventListener('unhandledrejection',e=>__tabs.errors.push(String(e.reason)));
addEventListener('wealth:view',()=>__tabs.views++);
window.confirm=()=>true;
window.__planning={revision:0,buckets:[],accounts:{},holdings:{},history:[
 {date:'2026-10-01',owner:'모두',assets:1000,debt:100,net_worth:900,source:'manual'},
 {date:'2026-10-02',owner:'모두',assets:1500,debt:100,net_worth:1400,source:'manual'},
 {date:'2026-10-01',owner:'아빠',assets:500,debt:100,net_worth:400,source:'manual'}]};
const nativeFetch=fetch;
window.fetch=function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 const response=value=>new Response(JSON.stringify(value),{status:200,headers:{'Content-Type':'application/json'}});
 if(path==='/api/market-overview'){
   __tabs.markets++;
   const result=()=>__tabs.fail ? Promise.reject(Error('synthetic market failure')) : response({markets:[{label:'SYNTHETIC INDEX',price:123,change:1,change_rate:1,series:[120,121,123]}]});
   if(__tabs.hold)return new Promise((resolve,reject)=>__tabs.pending.push(()=>Promise.resolve().then(result).then(resolve,reject)));
   return Promise.resolve().then(result);
 }
 if(path==='/api/planning')return Promise.resolve(response(__planning));
 if(path.startsWith('/api/planning/snapshot-') && !path.endsWith('snapshot-all')){
   const payload=JSON.parse(options.body);__tabs.writes.push({path,payload});
   const index=__planning.history.findIndex(r=>r.owner===payload.owner&&r.date===payload.date);
   if(path.endsWith('snapshot-delete'))__planning.history.splice(index,1);
   else if(path.endsWith('snapshot-edit'))__planning.history[index]={...__planning.history[index],...payload,date:payload.new_date};
   else __planning.history.push({...payload,source:'manual'});
   __planning.revision++;return Promise.resolve(response(__planning));
 }
 return nativeFetch.apply(this,arguments);
};
"""

CHECK = r"""(()=>{
 const tabs=[...document.querySelectorAll('#homeTabs [role=tab]')];
 const panels=[...document.querySelectorAll('[data-home-panel]')];
 const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);
 return {labels:tabs.map(b=>b.textContent.trim()),selected:tabs.filter(b=>b.getAttribute('aria-selected')==='true').map(b=>b.dataset.homeTab),
 shown:panels.filter(n=>n.getClientRects().length).map(n=>n.dataset.homePanel),
 relations:tabs.every(b=>{const p=document.getElementById(b.getAttribute('aria-controls'));return p.getAttribute('aria-labelledby')===b.id&&p.hidden===(b.getAttribute('aria-selected')!=='true')&&b.tabIndex===(p.hidden?-1:0);}),
 duplicate:ids.filter((id,i)=>ids.indexOf(id)!==i),width:document.documentElement.scrollWidth,
 history:document.querySelectorAll('#wealthHistoryPlot').length,errors:__tabs.errors};
})()"""

def wait_for(evaluate, expression):
    wait_for_page(evaluate, f'Boolean({expression})')


def choose(evaluate, tab):
    before=evaluate('({views:__tabs.views,selected:document.querySelector("#homeTabs [aria-selected=true]").dataset.homeTab})')
    evaluate(f'document.getElementById("homeTab-{tab}").click()')
    wait_for(evaluate, f'document.getElementById("homeTab-{tab}").getAttribute("aria-selected")==="true"')
    assert evaluate("__tabs.views")==before["views"]+(before["selected"]!=tab)


def check(evaluate, tab, width):
    state=evaluate(CHECK)
    assert state['labels']==['자산 포트폴리오','순자산 추이','주요지수'],state
    assert state['selected']==state['shown']==[tab],state
    assert state['relations'] and not state['duplicate'] and not state['errors'],state
    assert state['history']==1 and state['width']<=width+1,state


@pytest.mark.parametrize('width',[320,360,390,768,1280])
def test_home_tabs_keyboard_touch_scope_crud_routes(chrome_preview,width):
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT})
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<500})
    call('Emulation.setTouchEmulationEnabled',{'enabled':width<500})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        wait_for(evaluate,'!!window.WealthUnifiedTimeseries && !!document.querySelector("#wealthHistoryPlot")')
        assert evaluate('document.querySelector("#wealthAssetNetWorth").textContent') == '397,000,000원', evaluate('({text:document.querySelector("#wealthAssetNetWorth").textContent,errors:__tabs.errors,ready:WealthStartup.canRead()})')
        check(evaluate,'portfolio',width)
        document=call('DOM.getDocument')['root']['nodeId']
        for tab,label in [('portfolio','자산 포트폴리오'),('history','순자산 추이'),('markets','주요지수')]:
            node=call('DOM.querySelector',{'nodeId':document,'selector':f'#homeTab-{tab}'})['nodeId']
            ax=call('Accessibility.getPartialAXTree',{'nodeId':node,'fetchRelatives':False})['nodes'][0]
            assert ax['role']['value']=='tab' and ax['name']['value']==label,ax
        assert evaluate('__tabs.markets')==0
        # A real keyboard event activates the next tab, retaining tab focus.
        evaluate('document.getElementById("homeTab-portfolio").focus()')
        call('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowRight'})
        call('Input.dispatchKeyEvent',{'type':'keyUp','key':'ArrowRight'})
        wait_for(evaluate,'document.querySelector("#wealthHistoryPlot svg")')
        check(evaluate,'history',width)
        assert evaluate('document.activeElement.id')=='homeTab-history'
        wait_for(evaluate,'document.querySelector("#wealthHistoryPlot .wealth-unified-viewport")')
        wait_for(evaluate,'(()=>{const p=document.getElementById("wealthHistoryPlot"),s=p.querySelector("svg"),v=p.querySelector(".wealth-unified-viewport");return s && v && Math.abs(v.clientWidth-s.getBoundingClientRect().width)<2 && !!s.querySelector("circle");})()')
        chart=evaluate('(()=>{const p=document.getElementById("wealthHistoryPlot"),s=p.querySelector("svg"),v=p.querySelector(".wealth-unified-viewport");return {width:v.clientWidth,actual:s.getBoundingClientRect().width,text:p.innerHTML};})()')
        assert abs(chart['width']-chart['actual'])<2 and chart['width']>0 and '2026-10-01' in chart['text'],chart
        evaluate('selectOwner("아빠")')
        wait_for(evaluate,'document.querySelector("#wealthHistoryPlot")?.textContent.includes("400원")')
        assert not evaluate('document.querySelector("#wealthHistoryPlot").textContent.includes("1,400원")')
        evaluate('selectOwner("모두")')
        wait_for(evaluate,'document.querySelector("#wealthHistoryPlot")?.textContent.includes("1,400원")')
        # Exercise the existing dialog and delegated CRUD handlers after hiding/reopening.
        choose(evaluate,'portfolio');choose(evaluate,'history')
        evaluate('document.querySelector("[data-history-action=wealthAddHistory]").click()')
        wait_for(evaluate,'document.querySelector("#wealthHistoryEditForm")?.closest("dialog").open')
        evaluate("""(()=>{const f=document.getElementById('wealthHistoryEditForm');f.elements.date.value='2001-01-03';f.elements.assets.value=2200;f.elements.debt.value=200;f.elements.memo.value='SYNTHETIC';f.requestSubmit();})()""")
        wait_for(evaluate,'document.querySelector("[data-history-edit=\\\"2001-01-03\\\"]")')
        evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))')
        evaluate('document.querySelector("[data-history-edit=\\\"2001-01-03\\\"]").click()')
        evaluate("""(()=>{const f=document.getElementById('wealthHistoryEditForm');f.elements.assets.value=3200;f.requestSubmit();})()""")
        wait_for(evaluate,'__tabs.writes.length===2 && !document.querySelector("#wealthHistoryEditForm").closest("dialog").open')
        assert evaluate('__planning.history.find(r=>r.date==="2001-01-03").net_worth')==3000
        evaluate('document.querySelector("[data-history-delete=\\\"2001-01-03\\\"]").click()')
        wait_for(evaluate,'__tabs.writes.length===3 && !document.querySelector("[data-history-delete=\\\"2001-01-03\\\"]")')
        # Touch uses Chromium hit testing on narrow screens.
        if width<500:
            point=evaluate('(()=>{const b=document.getElementById("homeTab-markets");b.scrollIntoView();const r=b.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()')
            call('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[point]})
            call('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
            wait_for(evaluate,'document.getElementById("homeTab-markets").getAttribute("aria-selected")==="true"')
        else:choose(evaluate,'markets')
        wait_for(evaluate,'document.querySelector("#marketGrid").textContent.includes("SYNTHETIC INDEX")')
        check(evaluate,'markets',width)
        assert evaluate('__tabs.markets')==1
        for key,tab in [('Home','portfolio'),('End','markets'),('ArrowLeft','history')]:
            evaluate('document.querySelector("#homeTabs [aria-selected=true]").focus()')
            call('Input.dispatchKeyEvent',{'type':'keyDown','key':key})
            call('Input.dispatchKeyEvent',{'type':'keyUp','key':key})
            wait_for(evaluate,f'document.getElementById("homeTab-{tab}").getAttribute("aria-selected")==="true"')
            check(evaluate,tab,width)
        evaluate('location.hash="assets"')
        wait_for(evaluate,'document.querySelector(".wealth-workspace").dataset.activeView==="assets"')
        evaluate('location.hash="home"')
        wait_for(evaluate,'document.querySelector(".wealth-workspace").dataset.activeView==="home"')
        check(evaluate,'portfolio',width)
        for tab in ['history','markets','portfolio']:
            route='home' if tab=='portfolio' else 'home/'+tab
            previous=evaluate('performance.timeOrigin')
            call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#{route}'})
            wait_for(evaluate,f'location.hash==="#{route}"')
            call('Page.reload')
            wait_for(evaluate,f'performance.timeOrigin!=={previous!r} && !!window.WealthUnifiedTimeseries && !!document.querySelector("#wealthHistoryPlot")')
            wait_for(evaluate,'WealthStartup.canRead()')
            check(evaluate,tab,width)
        choose(evaluate,'history');choose(evaluate,'markets')
        evaluate('history.back()')
        wait_for(evaluate,'document.getElementById("homeTab-history").getAttribute("aria-selected")==="true"')
        evaluate('history.forward()')
        wait_for(evaluate,'document.getElementById("homeTab-markets").getAttribute("aria-selected")==="true"')
        check(evaluate,'markets',width)
        assert not evaluate('__tabs.errors')


def test_market_hidden_late_response_and_failure(chrome_preview):
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        wait_for(evaluate,'!!window.WealthUnifiedTimeseries && WealthStartup.canRead()')
        evaluate('__tabs.hold=true')
        choose(evaluate,'markets')
        wait_for(evaluate,'__tabs.pending.length===1')
        evaluate('void WealthStartup.loadVisible();void WealthStartup.loadVisible()')
        assert evaluate('__tabs.markets')==1
        choose(evaluate,'portfolio')
        before=evaluate('document.getElementById("marketGrid").innerHTML')
        evaluate('__tabs.pending.shift()();__tabs.hold=false')
        wait_for(evaluate,'!startupReadPending.size')
        assert evaluate('document.getElementById("marketGrid").innerHTML')==before
        evaluate('__tabs.fail=true')
        choose(evaluate,'markets')
        wait_for(evaluate,'document.getElementById("marketGrid").textContent.includes("불러오지 못했습니다")')
        evaluate('__tabs.fail=false')
        choose(evaluate,'history');choose(evaluate,'markets')
        wait_for(evaluate,'document.getElementById("marketGrid").textContent.includes("SYNTHETIC INDEX")')
        assert not evaluate('__tabs.errors')


def test_hidden_history_does_not_force_geometry_during_dashboard_render(chrome_preview):
    call,evaluate,_=chrome_preview
    probe=r"""
    const historyRects=Element.prototype.getClientRects;
    Element.prototype.getClientRects=function(){
      if(this.classList.contains('wealth-history') && document.getElementById('wealthHistorySlot')?.hidden)
        throw Error('Hidden history geometry forces synchronous layout');
      return historyRects.apply(this,arguments);
    };
    """
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT+probe})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
        wait_for(evaluate,'window.WealthStartup?.canRead() && !!window.WealthUnifiedTimeseries && !!document.getElementById("wealthHistoryPlot")')
        assert evaluate('document.getElementById("wealthAssetNetWorth").textContent')=='397,000,000원'
        choose(evaluate,'history')
        wait_for(evaluate,'document.querySelector("#wealthHistoryPlot svg")')
        choose(evaluate,'portfolio')
        evaluate('selectOwner("아빠")')
        assert not evaluate('__tabs.errors')


FIRST_PAINT = r"""
window.__firstHome=[];
const capture=()=>({hash:location.hash,shown:[...document.querySelectorAll('[data-home-panel]')].filter(n=>n.getClientRects().length).map(n=>n.dataset.homePanel)});
const sample=()=>{if(__firstHome.length<120)__firstHome.push(capture());if(document.readyState!=='complete')requestAnimationFrame(sample);};
requestAnimationFrame(sample);
new PerformanceObserver(list=>{for(const p of list.getEntries())__firstHome.push({...capture(),paint:p.name});}).observe({type:'paint',buffered:true});
"""


def test_direct_home_tabs_first_paint_at_all_widths(chrome_preview):
    call,evaluate,_=chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT+FIRST_PAINT})
    call('Network.setBypassServiceWorker',{'bypass':True})
    call('Network.setCacheDisabled',{'cacheDisabled':True})
    with transport_server(True) as port:
        for width in [320,360,390,768,1280]:
            call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':width<500})
            for tab in ['portfolio','history','markets']:
                route='home' if tab=='portfolio' else 'home/'+tab
                previous=evaluate('performance.timeOrigin')
                # Query changes force a complete navigation, including the HTML parser.
                call('Page.navigate',{'url':f'http://127.0.0.1:{port}/?tab={tab}&width={width}#{route}'})
                wait_for(evaluate,f'performance.timeOrigin!=={previous!r} && document.readyState==="complete" && !!window.WealthUnifiedTimeseries && WealthStartup.canRead()')
                wait_for(evaluate,'__firstHome.some(r=>r.paint)')
                for frame in evaluate('__firstHome'):
                    assert frame['shown'] in ([],[tab]),frame
                check(evaluate,tab,width)
                if tab=='history':wait_for(evaluate,'document.querySelector("#wealthHistoryPlot .wealth-unified-chart")')
                if tab=='markets':wait_for(evaluate,'__tabs.markets===1')
                else:assert evaluate('__tabs.markets')==0


def test_history_period_pan_zoom_and_hidden_owner_change(chrome_preview):
    call,evaluate,_=chrome_preview
    extra=r"""
__planning.history=Array.from({length:60},(_,i)=>({date:new Date(Date.UTC(2026,7,i+1)).toISOString().slice(0,10),owner:__planning.history[0].owner,assets:2000+i*100,debt:100,net_worth:1900+i*100,source:'manual'})).concat(__planning.history.filter(r=>r.owner!==__planning.history[0].owner));
"""
    call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT+extra})
    with transport_server(True) as port:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home/history'})
        wait_for(evaluate,'document.querySelectorAll("#wealthHistoryPlot circle").length>30 && !!document.querySelector("#wealthHistoryPlot .wealth-unified-viewport")')
        wait_for(evaluate,'document.querySelector("#wealthHistoryPlot .wealth-unified-content").clientWidth>document.querySelector("#wealthHistoryPlot .wealth-unified-viewport").clientWidth')
        before=evaluate('document.querySelector("#wealthHistoryPlot .wealth-unified-content").clientWidth')
        evaluate('document.querySelector("#wealthHistoryPlot .wealth-unified-viewport").dispatchEvent(new WheelEvent("wheel",{deltaY:-100,cancelable:true}))')
        assert evaluate('document.querySelector("#wealthHistoryPlot .wealth-unified-content").clientWidth')>before
        evaluate('document.querySelector("#wealthHistoryPlot .wealth-unified-viewport").scrollLeft=0')
        assert evaluate('document.querySelector("#wealthHistoryPlot .wealth-unified-viewport").scrollLeft')==0
        evaluate('document.querySelector(".wealth-history [data-period=\\\"1M\\\"]").click()')
        wait_for(evaluate,'WealthUnifiedTimeseries.modes.networth==="1M"')
        choose(evaluate,'portfolio')
        evaluate('selectOwner("아빠")')
        choose(evaluate,'history')
        wait_for(evaluate,'document.querySelector("#wealthHistoryPlot").textContent.includes("400원")')
        assert not evaluate('document.querySelector("#wealthHistoryPlot").textContent.includes("7,800원")')
        assert evaluate('WealthUnifiedTimeseries.modes.networth')=='1M'
        assert not evaluate('__tabs.errors')
