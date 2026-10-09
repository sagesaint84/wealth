"""Chrome regressions for dividend chart ownership and income tab URLs."""

import json
import threading
import time
import urllib.request
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.chrome_harness import chrome_session, safe_preview_server

from tests.test_pnl_first_visible_frame import IncomePreview, RECORDS
from tests.test_realized_pnl_viewport import StaticPreview, _chrome_path
from tests.ui_preview import STATIC


VIEWPORTS = [(320, 568), (390, 844), (1024, 768), (1440, 900)]
ROUTES = {"calendar": "#income", "pnl": "#pnl", "dividend": "#dividend",
          "ledger": "#ledger", "ipo": "#ipo"}


class DividendPreview(IncomePreview):
    def do_GET(self):
        parsed = urlsplit(self.path)
        assets = self.server.preview_assets
        if parsed.path == '/':
            content = assets['index.html'].replace(
                b'<body>',
                '<body><div style="padding:8px;text-align:center;background:#274c46;color:#fff;font-size:12px">가상 데이터 미리보기 · 실제 계좌와 연결되지 않음 · 저장 불가</div>'.encode(),
            )
            self.send(content, 'text/html; charset=utf-8')
            return
        if (parsed.path in ('/api/actual-dividends', '/api/realized-pnl')
                and parse_qs(parsed.query).get('owner') == ['synthetic-empty']):
            self.send({'records': [], 'interest_records': [], 'monthly': [], 'available_years': []})
            return
        if parsed.path in ("/static/wealth.js", "/static/wealth-timeseries-unified.js"):
            name = parsed.path.rsplit("/", 1)[-1]
            source = assets[name].decode("utf-8")
            marker = ("function renderActualDividends(data) {" if name == "wealth.js"
                      else "async function renderDividend() {")
            counter = "actualCalls" if name == "wealth.js" else "unifiedCalls"
            assert source.count(marker) == 1
            source = source.replace(marker, marker + f"\n    window.__divTrace.{counter}++;", 1)
            self.send(source.encode("utf-8"), "text/javascript; charset=utf-8")
            return
        if parsed.path.startswith('/static/'):
            name = parsed.path.removeprefix('/static/')
            if name in assets:
                kind = ('text/css' if name.endswith('.css') else
                        'text/javascript' if name.endswith('.js') else 'application/octet-stream')
                self.send(assets[name], kind)
                return
        if parsed.path == "/api/actual-dividends":
            owner = parse_qs(parsed.query).get("owner", [""])[0]
            if owner in ("synthetic-slow", "synthetic-fast"):
                if owner == "synthetic-slow":
                    time.sleep(0.2)
                rows = RECORDS[:1] if owner == "synthetic-slow" else RECORDS[-1:]
                self.send({"records": rows, "interest_records": [], "monthly": [],
                           "available_years": [2022 if owner == "synthetic-slow" else 2026]})
                return
        super().do_GET()


class DelayedDividendPreview(DividendPreview):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/static/wealth-timeseries-unified.js":
            time.sleep(0.65)
        if path == "/api/actual-dividends":
            time.sleep(0.2)
        super().do_GET()


class ChromePreviewServer(ThreadingHTTPServer):
    # The complete static bundle arrives in a burst. Windows can refuse core
    # script connections with the stdlib backlog of five, before any app code
    # executes. This changes fixture capacity, not chart assertions or delays.
    request_queue_size = 32


@pytest.fixture
def chrome_preview(request):
    websocket = pytest.importorskip("websocket")
    chrome = _chrome_path()
    if chrome is None:
        pytest.skip("Chromium browser unavailable")
    handler = (DelayedDividendPreview if "dividend_slow_first_frame" in request.node.name
               else DividendPreview if "dividend_visible_chart" in request.node.name or "startup_request" in request.node.name
               else StaticPreview)
    server = safe_preview_server(ChromePreviewServer, handler)
    # Serve immutable fixture bytes on every request/reload. This avoids Windows
    # file reads in HTTP worker threads without changing script delivery delays.
    server.preview_assets = {path.name: path.read_bytes() for path in STATIC.iterdir() if path.is_file()}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = None
    try:
        with ExitStack() as cleanup:
            process, port, profile = cleanup.enter_context(chrome_session(chrome, "wealth-dividend-route-"))
            targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
            target = next(item for item in targets if item.get("type") == "page")
            connection = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=15)
            request_id = 0

            def call(method, params=None):
                nonlocal request_id
                request_id += 1
                connection.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
                while True:
                    response = json.loads(connection.recv())
                    if response.get("id") == request_id:
                        assert "error" not in response, response
                        return response["result"]

            def evaluate(expression):
                result = call("Runtime.evaluate", {"expression": expression,
                    "returnByValue": True, "awaitPromise": True})
                assert "exceptionDetails" not in result, result
                return result["result"].get("value")

            call("Page.enable")
            call("Runtime.enable")
            call("Page.addScriptToEvaluateOnNewDocument", {"source": """
              window.__divTrace={writes:[],requests:[],errors:[],frames:[],actualCalls:0,unifiedCalls:0};
              window.addEventListener('error',event=>window.__divTrace.errors.push(String(event.message)));
              const originalFetch=window.fetch;
              window.fetch=function(...args){
                const url=String(args[0]);
                if(url.includes('/api/')) { const parsed=new URL(url,location.origin); parsed.searchParams.sort(); window.__divTrace.requests.push(parsed.pathname+parsed.search); }
                return originalFetch.apply(this,args);
              };
              function sampleFrame(){
                const host=document.getElementById('dividendBarChartWrap');
                const panel=document.getElementById('dividendPanel');
                if(host && panel && panel.getBoundingClientRect().height>0 && getComputedStyle(panel).visibility!=='hidden')
                  window.__divTrace.frames.push({legacy:!!host.querySelector('svg.record-chart'),unified:!!host.querySelector('.wealth-unified-chart-shell')});
                requestAnimationFrame(sampleFrame);
              }
              requestAnimationFrame(sampleFrame);
              const descriptor=Object.getOwnPropertyDescriptor(Element.prototype,'innerHTML');
              Object.defineProperty(Element.prototype,'innerHTML',{
                get:descriptor.get,
                set(value){
                  if(this.id==='dividendBarChartWrap') window.__divTrace.writes.push({
                    at:performance.now(),
                    visible:!document.getElementById('dividendPanel')?.classList.contains('wealth-income-hidden'),
                    kind:String(value).includes('wealth-unified-chart-shell')?'unified':'legacy'});
                  return descriptor.set.call(this,value);
                }
              });
            """})
            yield call, evaluate, server.server_port
    finally:
        if connection:
            connection.close()
        server.shutdown()
        server.server_close()


def wait_for(evaluate, expression, timeout=20):
    for _ in range(int(timeout * 10)):
        try:
            if evaluate(expression):
                return
        except AssertionError as error:
            if "Inspected target navigated or closed" not in str(error):
                raise
        time.sleep(0.1)
    state = evaluate("({href:location.href,ready:document.readyState,origin:performance.timeOrigin,tab:typeof window.setIncomeTab,layout:!!document.querySelector('#incomeTabs'),root:!!document.getElementById('userAssetDashboardWrapper'),hit:!!window.WealthDonutHitTest,scripts:[...document.scripts].map(s=>s.src.split('/').pop()),errors:window.__divTrace?.errors})")
    pytest.fail(f"Chrome preview did not reach: {expression}; state={state}")


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_dividend_slow_first_frame_has_one_chart_owner(chrome_preview, width, height):
    call, evaluate, port = chrome_preview
    call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
        "screenWidth": width, "screenHeight": height, "deviceScaleFactor": 1,
        "mobile": width <= 430})
    call("Page.navigate", {"url": f"http://127.0.0.1:{port}/#income"})
    ready_expression = "typeof window.setIncomeTab==='function' && !!window.WealthUnifiedTimeseries && !!document.querySelector('#incomeTabs [data-income=\"dividend\"]')"
    try:
        wait_for(evaluate, ready_expression, timeout=8)
    except pytest.fail.Exception:
        call("Page.reload", {"ignoreCache": True})
        wait_for(evaluate, ready_expression)
    result = evaluate("""(async () => {
      const host=document.getElementById('dividendBarChartWrap');
      const panel=document.getElementById('dividendPanel');
      const sample=() => {
        const viewport=host.querySelector('.wealth-unified-viewport');
        const content=host.querySelector('.wealth-unified-content');
        return {visible:!panel.classList.contains('wealth-income-hidden'),
          legacy:!!host.querySelector('svg.record-chart'),
          unified:!!host.querySelector('.wealth-unified-chart-shell'),
          client:viewport?.clientWidth || 0,scroll:viewport?.scrollWidth || 0,
          left:viewport?.scrollLeft || 0,width:content?.getBoundingClientRect().width || 0};
      };
      const visits=[];
      for(let visit=0;visit<2;visit++){
        document.querySelector('#incomeTabs [data-income="calendar"]').click();
        document.querySelector('#incomeTabs [data-income="dividend"]').click();
        const frames=[sample()];
        let visibleFrames=0;
        for(let i=0;i<600 && visibleFrames<90;i++){
          await new Promise(requestAnimationFrame);
          const frame=sample();
          frames.push(frame);
          if(frame.visible) visibleFrames++;
        }
        visits.push(frames);
      }
      return {visits,writes:window.__divTrace.writes,requests:window.__divTrace.requests,
        actualCalls:window.__divTrace.actualCalls,unifiedCalls:window.__divTrace.unifiedCalls};
    })()""")
    print("DIVIDEND_SLOW=" + json.dumps({"width": width,
        "firstVisible": [next((frame for frame in visit if frame["visible"]), None) for visit in result["visits"]],
        "writes": result["writes"], "requestCount": len(result["requests"]),
        "actualCalls": result["actualCalls"], "unifiedCalls": result["unifiedCalls"]}))
    for visit in result["visits"]:
        visible = [frame for frame in visit if frame["visible"]]
        assert visible, result
        assert all(frame["unified"] and not frame["legacy"] for frame in visible), result
        assert visible[0]["width"] == visible[-1]["width"], result
        assert visible[0]["left"] == visible[-1]["left"], result
    assert not any(write["kind"] == "legacy" and write["visible"] for write in result["writes"]), result


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_dividend_visible_chart_is_unified_from_first_paint(chrome_preview, width, height):
    call, evaluate, port = chrome_preview
    call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
        "screenWidth": width, "screenHeight": height, "deviceScaleFactor": 1,
        "mobile": width <= 430})
    call("Page.navigate", {"url": f"http://127.0.0.1:{port}/#income"})
    ready_expression = "typeof window.setIncomeTab==='function' && !!window.WealthUnifiedTimeseries && !!document.querySelector('#dividendBarChartWrap .wealth-unified-chart-shell') && !!actualDividendData"
    try:
        wait_for(evaluate, ready_expression, timeout=8)
    except pytest.fail.Exception:
        call("Page.reload", {"ignoreCache": True})
        wait_for(evaluate, ready_expression)
    result = evaluate("""(async () => {
      const host=document.getElementById('dividendBarChartWrap');
      const panel=document.getElementById('dividendPanel');
      const sample=() => {
        const viewport=host.querySelector('.wealth-unified-viewport');
        const content=host.querySelector('.wealth-unified-content');
        return {tab:document.querySelector('#incomeTabs .income-tab.active')?.dataset.income,
          hidden:panel.classList.contains('wealth-income-hidden'),
          child:host.firstElementChild?.className?.baseVal || host.firstElementChild?.className || '',
          legacy:!!host.querySelector('svg.record-chart'),
          unified:!!host.querySelector('.wealth-unified-chart-shell'),
          client:viewport?.clientWidth || 0,scrollWidth:viewport?.scrollWidth || 0,
          scrollLeft:viewport?.scrollLeft || 0,width:content?.getBoundingClientRect().width || 0};
      };
      const visits=[];
      for(let visit=0;visit<2;visit++){
        document.querySelector('#incomeTabs [data-income="calendar"]').click();
        document.querySelector('#incomeTabs [data-income="dividend"]').click();
        renderActualDividends(actualDividendData);
        const frames=[sample()];
        for(let i=0;i<70;i++){
          await new Promise(requestAnimationFrame);
          frames.push(sample());
        }
        visits.push(frames);
      }
      const actualVisitWrites=[...window.__divTrace.writes];
      const modes={};
      for(const key of ['DAY','WEEK','MONTH','YEAR','ALL']){
        window.WealthUnifiedTimeseries.modes.dividend=window.WealthTimeseriesPeriodCore.MODES[key];
        await window.WealthUnifiedTimeseries.renderDividend();
        const before=sample();
        document.querySelector('#incomeTabs [data-income="calendar"]').click();
        document.querySelector('#incomeTabs [data-income="dividend"]').click();
        await new Promise(requestAnimationFrame);
        await new Promise(requestAnimationFrame);
        modes[key]={before,after:sample(),selected:window.WealthUnifiedTimeseries.modes.dividend};
      }
      document.querySelector('#dividendModeTabs [data-div-mode="estimated"]').click();
      for(let i=0;i<600 && !host.querySelector('svg.record-chart');i++) await new Promise(requestAnimationFrame);
      const estimated=sample();
      document.querySelector('#dividendModeTabs [data-div-mode="actual"]').click();
      const actualFrames=[sample()];
      for(let i=0;i<5;i++){
        await new Promise(requestAnimationFrame);
        actualFrames.push(sample());
      }
      window.WealthUnifiedTimeseries.modes.dividend=window.WealthTimeseriesPeriodCore.MODES.MONTH;
      await window.WealthUnifiedTimeseries.renderDividend();
      currentOwner='synthetic-slow';
      const slow=window.WealthUnifiedTimeseries.renderDividend();
      currentOwner='synthetic-fast';
      const fast=window.WealthUnifiedTimeseries.renderDividend();
      await Promise.all([slow,fast]);
      const raceLabel=host.querySelector('svg text[y="280"]')?.textContent || '';
      return {visits,modes,estimated,actualFrames,actualVisitWrites,writes:window.__divTrace.writes,
        requests:window.__divTrace.requests,
        raceLabel,
        summary:document.getElementById('divTotalAnnual')?.textContent,
        detail:!!document.querySelector('#dividendMonthlyDetail .div-detail-header')};
    })()""")
    print("DIVIDEND_FRAMES=" + json.dumps({"width": width, **result}))
    assert all(frame["unified"] and not frame["legacy"] for visit in result["visits"] for frame in visit), result
    assert not any(write["kind"] == "legacy" and write["visible"] for write in result["actualVisitWrites"]), result
    for visit in result["visits"]:
        assert visit[2]["width"] == visit[-1]["width"], result
        assert visit[2]["scrollLeft"] == visit[-1]["scrollLeft"], result
    for pair in result["modes"].values():
        assert pair["before"]["width"] == pair["after"]["width"], pair
        assert pair["before"]["scrollLeft"] == pair["after"]["scrollLeft"], pair
    assert result["estimated"]["legacy"] and not result["estimated"]["unified"], result
    assert all(frame["unified"] and not frame["legacy"] for frame in result["actualFrames"][1:]), result
    assert result["summary"] and result["detail"], result
    assert "2026" in result["raceLabel"], result


@pytest.mark.parametrize("tab,hash_value", ROUTES.items())
def test_income_tab_hash_survives_reload(chrome_preview, tab, hash_value):
    call, evaluate, port = chrome_preview
    call("Page.navigate", {"url": f"http://127.0.0.1:{port}/#income"})
    try:
        wait_for(evaluate, "typeof window.setIncomeTab==='function' && !!document.querySelector('#incomeTabs [data-income=\"pnl\"]')", timeout=8)
    except pytest.fail.Exception:
        call("Page.reload", {"ignoreCache": True})
        wait_for(evaluate, "typeof window.setIncomeTab==='function' && !!document.querySelector('#incomeTabs [data-income=\"pnl\"]')")
    evaluate("document.querySelector('#incomeTabs [data-income=" + json.dumps(tab) + "]').click()")
    wait_for(evaluate, f"location.hash==='{hash_value}' && document.querySelector('#incomeTabs .income-tab.active')?.dataset.income==='{tab}'")
    result = evaluate("({hash:location.hash,active:document.querySelector('#incomeTabs .income-tab.active')?.dataset.income})")
    print("ROUTE_BEFORE=" + json.dumps({"tab": tab, **result}))
    assert result["hash"] == hash_value
    previous_origin = evaluate("performance.timeOrigin")
    time.sleep(1)
    call("Page.reload", {"ignoreCache": True})
    wait_for(evaluate, f"performance.timeOrigin>{previous_origin} && document.readyState==='complete' && typeof window.setIncomeTab==='function'")
    restored = evaluate("""(() => ({hash:location.hash,
      active:document.querySelector('#incomeTabs .income-tab.active')?.dataset.income,
      panels:Object.fromEntries([['calendar','calendarPanel'],['pnl','realizedPnlPanel'],
        ['dividend','dividendPanel'],['ledger','ledgerSectionPanel'],['ipo','ipoPanel']]
        .map(([name,id])=>[name,!document.getElementById(id).classList.contains('wealth-income-hidden')]))}))()""")
    assert restored["hash"] == hash_value and restored["active"] == tab, restored
    assert restored["panels"] == {name: name == tab for name in ROUTES}, restored
    time.sleep(1)
    call("Page.navigate", {"url": f"http://127.0.0.1:{port}/?direct=1{hash_value}"})
    wait_for(evaluate, f"location.hash==='{hash_value}' && document.readyState==='complete' && typeof window.setIncomeTab==='function'")
    direct = evaluate("""(() => ({active:document.querySelector('#incomeTabs .income-tab.active')?.dataset.income,
      panels:Object.fromEntries([['calendar','calendarPanel'],['pnl','realizedPnlPanel'],
        ['dividend','dividendPanel'],['ledger','ledgerSectionPanel'],['ipo','ipoPanel']]
        .map(([name,id])=>[name,!document.getElementById(id).classList.contains('wealth-income-hidden')]))}))()""")
    assert direct["active"] == tab and direct["panels"] == {name: name == tab for name in ROUTES}, direct


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_dividend_slow_first_frame_direct_reload(chrome_preview, width, height):
    call, evaluate, port = chrome_preview
    call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
        "deviceScaleFactor": 1, "mobile": width <= 430})
    call("Page.navigate", {"url": f"http://127.0.0.1:{port}/#dividend"})
    for visit in range(2):
        wait_for(evaluate, "!!document.querySelector('#dividendBarChartWrap .wealth-unified-chart-shell') && window.__divTrace.frames.length>0")
        result = evaluate("window.__divTrace")
        assert not any(frame['legacy'] for frame in result['frames']), result
        assert not any(urlsplit(key).path == '/api/dividends' for key in result['requests']), result
        print("DIRECT_RELOAD_COUNTS=" + json.dumps({key: result['requests'].count(key) for key in sorted(set(result['requests']))}))
        if visit == 0:
            origin = evaluate("performance.timeOrigin")
            call("Page.reload", {"ignoreCache": True})
            wait_for(evaluate, f"performance.timeOrigin !== {origin}")


def test_startup_request_dedupe_and_estimated_lazy_load(chrome_preview):
    call, evaluate, port = chrome_preview
    call("Page.navigate", {"url": f"http://127.0.0.1:{port}/#dividend"})
    wait_for(evaluate, "!!document.querySelector('#dividendBarChartWrap .wealth-unified-chart-shell') && typeof loadAssetDataForUser==='function'")
    evaluate("loadAssetDataForUser()")
    counts = evaluate("window.__divTrace.requests")
    print("ACTUAL_STARTUP_COUNTS=" + json.dumps({key: counts.count(key) for key in sorted(set(counts))}))
    assert evaluate("window.__divTrace.requests.filter(key=>key.startsWith('/api/dividends?')).length") == 0
    result = evaluate("""(async()=>{
      currentOwner='synthetic-dedupe';
      window.__divTrace.requests=[];
      await Promise.all(Array.from({length:12},()=>window.WealthUnifiedTimeseries.renderPnl()));
      await Promise.all(Array.from({length:12},()=>window.WealthUnifiedTimeseries.renderDividend()));
      return window.__divTrace.requests;
    })()""")
    for endpoint in ['/api/realized-pnl', '/api/actual-dividends']:
        calls = [key for key in result if urlsplit(key).path == endpoint]
        assert len(calls) == 1, result
    evaluate("document.querySelector('#dividendModeTabs [data-div-mode=estimated]').click()")
    wait_for(evaluate, "!!dividendData && !!document.querySelector('#dividendBarChartWrap svg.record-chart')")
    count = evaluate("window.__divTrace.requests.filter(key=>key.startsWith('/api/dividends?')).length")
    assert count == 1
    evaluate("document.querySelector('#dividendModeTabs [data-div-mode=actual]').click(); document.querySelector('#dividendModeTabs [data-div-mode=estimated]').click()")
    assert evaluate("window.__divTrace.requests.filter(key=>key.startsWith('/api/dividends?')).length") == count
    empty = evaluate("""(async()=>{
      document.querySelector('#dividendModeTabs [data-div-mode=actual]').click();
      currentOwner='synthetic-empty';
      await Promise.all([window.WealthUnifiedTimeseries.renderPnl(),window.WealthUnifiedTimeseries.renderDividend()]);
      for(let i=0;i<3;i++) await new Promise(requestAnimationFrame);
      const before=window.__divTrace.unifiedCalls;
      const probe=document.createElement('div');
      document.body.append(probe);
      for(let i=0;i<5;i++) await new Promise(requestAnimationFrame);
      probe.remove();
      for(let i=0;i<5;i++) await new Promise(requestAnimationFrame);
      return {before,after:window.__divTrace.unifiedCalls,
        pnl:!!document.querySelector('#pnlBarChartWrap > .wealth-unified-empty'),
        dividend:!!document.querySelector('#dividendBarChartWrap > .wealth-unified-empty')};
    })()""")
    assert empty['pnl'] and empty['dividend'] and empty['before'] == empty['after'], empty
    cursor = evaluate("""(()=>{
      const node=document.elementFromPoint(innerWidth/2,innerHeight/2);
      const chain=[];
      for(let el=node;el;el=el.parentElement){const css=getComputedStyle(el);chain.push({tag:el.tagName,id:el.id,classes:el.className.baseVal??el.className,position:css.position,zIndex:css.zIndex,pointerEvents:css.pointerEvents});}
      return chain;
    })()""")
    print("CURSOR_CENTER_DOM=" + json.dumps(cursor))
