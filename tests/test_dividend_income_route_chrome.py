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


@pytest.mark.parametrize('width', [320, 390, 1280])
def test_v211_dividend_visible_chart_cards_and_optional_record_fields(chrome_preview, width):
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width':width, 'height':900, 'deviceScaleFactor':1, 'mobile':width < 500})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#dividend'})
    wait_for(evaluate, "!!window.WealthUnifiedTimeseries && !!document.getElementById('divTotalAnnual')")
    result = evaluate("""(() => {
      currentOwner='모두'; selectedDividendYear='2026'; selectedDividendMonth=10;
      const rows=[{id:'v211-a',code:'316140',name:'합성 우리금융',owner:'모두',date:'2026-04-08',currency:'KRW',amount:212800,amount_krw:212800,fx_rate:1,
        capital_dividend_mode:'MANUAL_ON',tax_estimate:{gross_amount_krw:212800,estimated:true,tax_type_label:'감액배당 · 사용자 지정'}},
        {id:'v211-b',code:'005930',date:'2026-10-01',amount:846,amount_krw:846,tax_estimate:{gross_amount_krw:1000,estimated:true}}];
      actualDividendData={records:rows,interest_records:[{date:'2026-10-01',amount_krw:999999}],available_years:['2026'],monthly_schedule:[]};
      renderActualDividends(actualDividendData);
      return {month:document.getElementById('divTotalAnnual').textContent,gross:document.getElementById('divYield').textContent,
        annual:document.getElementById('divMonthlyAvg').textContent,count:document.getElementById('divTotalHoldings').textContent,
        estimate:document.getElementById('divYieldSub').textContent,sub:document.getElementById('divMonthlyAvgSub').textContent};
    })()""")
    assert '846' in result['month']
    assert '213,800' in result['gross'] and '213,646' in result['annual']
    assert '1건' in result['count'] and result['estimate'] == '일부 예상값 포함'
    assert '12개월' not in result['sub']
    evaluate("selectedDividendMonth=4;renderActualDividends(actualDividendData)")
    assert evaluate("document.getElementById('dividendMonthlyDetail').textContent.includes('감액배당 · 사용자 지정')")
    evaluate("openDividendRecordDialog({...actualDividendData.records[0],gross_amount:212800,tax:0})")
    wait_for(evaluate, "document.getElementById('dividendRecordDialog').open")
    assert evaluate("document.querySelector('#dividendRecordForm [name=tax]').value") == '0'
    assert evaluate("document.querySelector('#dividendRecordForm [name=gross_amount]').value") == '212800'
    assert evaluate("document.querySelector('#dividendRecordForm [name=capital_dividend_mode]').value") == 'MANUAL_ON'
    assert not evaluate("document.documentElement.scrollWidth > innerWidth")


@pytest.mark.parametrize('width', [320, 1280])
def test_v211_dividend_visible_chart_shared_tooltip_pointer_keyboard_and_drag(chrome_preview, width):
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width':width, 'height':900, 'deviceScaleFactor':1, 'mobile':width < 500})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#dividend'})
    wait_for(evaluate, "!!window.WealthUnifiedTimeseries")
    # Module registration precedes async route preparation. A synthetic tooltip
    # must not race the real chart's initial render, which closes old tooltips.
    wait_for(evaluate, "WealthStartup.canRead() && currentIncomeTab==='dividend' && !setIncomeTab.pendingTarget && startupReadPending.size===0 && !!document.querySelector('#dividendBarChartWrap .wealth-unified-chart-shell') && !!document.getElementById('dividendPanel').getClientRects().length")
    evaluate("""(() => {
      const host=document.createElement('div');host.id='v211TooltipHost';
      host.style.cssText='position:fixed;inset:80px 10px auto;z-index:99999;height:180px;background:white';
      host.innerHTML='<svg viewBox="0 0 300 180" style="width:100%;height:180px"><rect data-bucket-index="0" tabindex="0" x="10" y="20" width="100" height="100"/><rect data-bucket-index="1" tabindex="0" x="160" y="20" width="100" height="100"/></svg>';
      document.body.appendChild(host);
      WealthUnifiedTimeseries.installAmountTooltip(host,[{key:'2026-04',a:2900000,b:20000},{key:'2026-05',a:-12345,b:0}],
        row=>[['배당 또는 손익',row.a],['이자',row.b]]);
    })()""")
    center = evaluate("(() => {const r=document.querySelector('#v211TooltipHost rect').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
    if width < 500:
        call('Input.dispatchTouchEvent', {'type':'touchStart', 'touchPoints':[center]})
        call('Input.dispatchTouchEvent', {'type':'touchEnd', 'touchPoints':[]})
    else:
        call('Input.dispatchMouseEvent', {'type':'mouseMoved', **center})
    wait_for(evaluate, "!!document.getElementById('wealthChartAmountTooltip') && !document.getElementById('wealthChartAmountTooltip').hidden")
    assert evaluate("document.getElementById('wealthChartAmountTooltip').textContent.includes('2,900,000원')")
    assert evaluate("document.getElementById('wealthChartAmountTooltip').textContent.includes('이자 20,000원')")
    evaluate("document.querySelectorAll('#v211TooltipHost rect')[1].focus()")
    assert evaluate("document.getElementById('wealthChartAmountTooltip').textContent.includes('-12,345원')")
    assert evaluate("(() => {const r=document.getElementById('wealthChartAmountTooltip').getBoundingClientRect();return r.left>=0 && r.right<=innerWidth && r.bottom<=innerHeight})()")
    evaluate("document.querySelectorAll('#v211TooltipHost rect')[1].dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
    assert evaluate("document.getElementById('wealthChartAmountTooltip').hidden")

    # A drag must not select/show the initial bar on release.
    call('Input.dispatchMouseEvent', {'type':'mousePressed', **center, 'button':'left', 'clickCount':1})
    call('Input.dispatchMouseEvent', {'type':'mouseMoved', 'x':center['x']+30, 'y':center['y'], 'buttons':1})
    call('Input.dispatchMouseEvent', {'type':'mouseReleased', 'x':center['x']+30, 'y':center['y'], 'button':'left', 'clickCount':1})
    assert evaluate("document.getElementById('wealthChartAmountTooltip').hidden")

def test_v211_dividend_visible_chart_latest_stock_record_zero_and_empty(chrome_preview):
    call, evaluate, port = chrome_preview
    # Document/module readiness precedes async auth/dashboard/asset reads. Observe
    # their actual completion without changing application results or timings.
    call('Page.addScriptToEvaluateOnNewDocument', {'source': """
      window.__v211StockStartup={auth:'pending',assetReads:0,assetCompletions:0};
      document.addEventListener('DOMContentLoaded', () => {
        const originalAuth=initAuthSession, originalAssets=loadAssetRecords;
        initAuthSession=async function(...args) {
          try {
            const result=await originalAuth.apply(this,args);
            __v211StockStartup.auth=result ? 'complete' : 'failed';
            return result;
          } catch(error) {__v211StockStartup.auth='failed';throw error;}
        };
        loadAssetRecords=async function(...args) {
          ++__v211StockStartup.assetReads;
          try {return await originalAssets.apply(this,args);}
          finally {--__v211StockStartup.assetReads;++__v211StockStartup.assetCompletions;}
        };
      }, {once:true,capture:true});
    """})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#dividend'})

    def state():
        return evaluate("""(() => {
          const host=document.getElementById('assetChart'), latest=host?.querySelector('.wealth-unified-latest');
          return {ready:document.readyState,startup:window.__v211StockStartup,
            owner:typeof currentOwner==='undefined'?null:currentOwner,
            view:typeof currentRecordView==='undefined'?null:currentRecordView,
            mode:window.WealthUnifiedTimeseries?.modes.stock,
            taxView:document.getElementById('recordsPanel')?.classList.contains('is-tax-view'),
            connected:!!host?.isConnected,latestConnected:!!latest?.isConnected,
            latest:latest?.textContent ?? null,empty:!!host?.querySelector('.wealth-unified-empty'),
            text:host?.textContent,source:typeof assetRecords==='undefined'?null:assetRecords,
            errors:window.__divTrace?.errors};
        })()""")

    def wait_state(expression, phase):
        try:
            wait_for(evaluate, expression)
        except pytest.fail.Exception as error:
            pytest.fail(f'{phase}: {error}; stock render state={state()}')

    wait_state("""document.readyState==='complete' && !!window.WealthUnifiedTimeseries
      && !!document.getElementById('assetChart') && __v211StockStartup.auth==='complete'
      && __v211StockStartup.assetCompletions>0 && __v211StockStartup.assetReads===0""", 'startup')

    def inject(owner, rows):
        # Use the production renderer to synchronize both assetRecords and its
        # window mirror; period synchronization can legitimately read either.
        evaluate(f"currentOwner={json.dumps(owner)};currentRecordView='combo';"
                 f"allAssetRecords={json.dumps(rows)};renderAssetRecords(allAssetRecords);"
                 "WealthUnifiedTimeseries.renderStock()")

    def assert_latest(owner, date, amount, mode):
        expected = f'최신 주식자산 {amount:,}원 · {date} 기준'
        wait_state(f"""(() => {{
          const host=document.getElementById('assetChart'), latest=host?.querySelector('.wealth-unified-latest');
          return !!(host?.isConnected && latest?.isConnected && latest.textContent==={json.dumps(expected)}
            && currentOwner==={json.dumps(owner)} && currentRecordView==='combo'
            && !document.getElementById('recordsPanel').classList.contains('is-tax-view')
            && WealthUnifiedTimeseries.modes.stock==={json.dumps(mode)}
            && assetRecords.some(r=>r.owner==={json.dumps(owner)} && r.date==={json.dumps(date)} && r.total_value_krw==={amount}));
        }})()""", f'{owner}/{mode}/{date}/{amount}')
        current = state()
        assert current['latest'] == expected and current['latestConnected'], current
        assert current['owner'] == owner and current['mode'] == mode, current

    owner = '합성 주식 A'
    rows = [{'owner':owner,'date':'2026-10-16','total_value_krw':123456,'day_profit_krw':-100},
            {'owner':owner,'date':'2026-10-17','total_value_krw':0,'day_profit_krw':-123456}]
    evaluate("WealthUnifiedTimeseries.modes.stock='1D'")
    inject(owner, rows)
    assert_latest(owner, '2026-10-17', 0, '1D')
    for mode in ['1D', '1W', '1M', '1Y', 'ALL']:
        evaluate(f"WealthUnifiedTimeseries.modes.stock={json.dumps(mode)};WealthUnifiedTimeseries.renderStock()")
        assert_latest(owner, '2026-10-17', 0, mode)
    inject(owner, rows[:1])
    assert_latest(owner, '2026-10-16', 123456, 'ALL')
    inject(owner, [{'owner':owner,'date':'2026-10-18','total_value_krw':-100,'day_profit_krw':-100}])
    assert_latest(owner, '2026-10-18', -100, 'ALL')
    next_owner = '합성 주식 B'
    inject(next_owner, [{'owner':next_owner,'date':'2026-10-19','total_value_krw':987654,'day_profit_krw':100}])
    assert_latest(next_owner, '2026-10-19', 987654, 'ALL')
    empty_owner = '합성 주식 C'
    inject(empty_owner, [])
    wait_state(f"""currentOwner==={json.dumps(empty_owner)} && assetRecords.length===0
      && !!document.querySelector('#assetChart .wealth-unified-empty')
      && !document.querySelector('#assetChart .wealth-unified-latest')""", 'empty owner')
    final = state()
    assert final['empty'] and final['latest'] is None, final
    assert '기록' in final['text'] and '987,654' not in final['text'], final



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


class V211StatePreview(DividendPreview):
    def do_GET(self):
        if urlsplit(self.path).path == '/':
            self.send('''<!doctype html><html><body>
              <button class="family-tab" id="syntheticOwner">소유자 변경</button>
              <section id="recordsPanel"><div id="recordPeriodTabs"><button data-period="ALL">전체</button></div><div id="assetChart"></div></section>
              <section class="wealth-history"><div class="wealth-periods"><button type="button" data-period="1D">일간</button><button type="button" data-period="1W">주간</button><button type="button" data-period="1M">월간</button><button type="button" data-period="1Y">연간</button><button type="button" data-period="ALL">전체</button></div>
              <div id="wealthHistoryPlot"><svg><g class="wealth-history-point" data-history-date="2026-10-16"><circle cx="80" cy="80" r="4"><title>순자산 100,000원</title></circle></g>
              <g class="wealth-history-point" data-history-date="2026-10-17"><circle cx="80" cy="80" r="4"><title>순자산 0원</title></circle></g></svg></div></section>
              <script>let currentOwner='합성 A';let assetRecords=[{date:'2026-10-17',total_value_krw:123456,day_profit_krw:-100}];</script>
              <script src="/static/wealth-timeseries-period-core.js"></script>
              <script src="/static/wealth-timeseries-visible-range.js"></script>
              <script src="/static/wealth-timeseries-unified.js"></script>
              </body></html>'''.encode(), 'text/html; charset=utf-8')
            return
        super().do_GET()


def test_v211_state_networth_latest_zero_owner_change_and_empty(chrome_preview):
    call, evaluate, port = chrome_preview
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/'})
    wait_for(evaluate, "!!document.querySelector('#wealthHistoryPlot .wealth-unified-latest')")
    assert evaluate("document.querySelector('#wealthHistoryPlot .wealth-unified-latest').textContent.includes('최신 순자산 0원 · 2026-10-17 기준')")
    for mode in ['1D', '1W', '1M', '1Y', 'ALL']:
        evaluate(f"WealthUnifiedTimeseries.modes.networth={json.dumps(mode)};WealthUnifiedTimeseries.renderNetWorth()")
        assert evaluate("document.querySelector('#wealthHistoryPlot .wealth-unified-latest').textContent.includes('순자산 0원')")
    # A new saved snapshot redraws the legacy SVG before the unified adapter
    # captures it. It must render once, rather than repeatedly clearing its cache.
    evaluate("""document.getElementById('wealthHistoryPlot').innerHTML='<svg><g class="wealth-history-point" data-history-date="2026-10-18"><circle cx="80" cy="80" r="4"><title>순자산 200,000원</title></circle></g></svg>';
      WealthUnifiedTimeseries.renderNetWorth();""")
    wait_for(evaluate, "document.querySelector('#wealthHistoryPlot .wealth-unified-latest')?.textContent.includes('최신 순자산 200,000원 · 2026-10-18 기준')")
    evaluate("""currentOwner='합성 B';document.getElementById('syntheticOwner').click();
      document.getElementById('wealthHistoryPlot').innerHTML='<svg><g class="wealth-history-point" data-history-date="2026-10-18"><circle cx="80" cy="80" r="4"><title>순자산 461,000,000원</title></circle></g></svg>';
      WealthUnifiedTimeseries.renderNetWorth();""")
    wait_for(evaluate, "document.querySelector('#wealthHistoryPlot .wealth-unified-latest')?.textContent.includes('461,000,000원')")
    evaluate("currentOwner='합성 C';document.getElementById('syntheticOwner').click();document.getElementById('wealthHistoryPlot').replaceChildren();WealthUnifiedTimeseries.renderNetWorth()")
    wait_for(evaluate, "document.getElementById('wealthHistoryPlot').textContent.includes('기록 없음')")
    assert not evaluate("!!document.querySelector('#wealthHistoryPlot .wealth-unified-latest')")


@pytest.fixture
def chrome_preview(request):
    websocket = pytest.importorskip("websocket")
    chrome = _chrome_path()
    if chrome is None:
        pytest.skip("Chromium browser unavailable")
    handler = (V211StatePreview if 'v211_state' in request.node.name else DividendBenefitPreview if 'b2_benefit' in request.node.name else DelayedDividendPreview if "dividend_slow_first_frame" in request.node.name
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


@pytest.mark.parametrize('width,height', [(320, 568), (390, 844), (1280, 900)])
def test_dividend_mode_dashboard_visibility_and_tax_restore(chrome_preview, width, height):
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
         'screenWidth': width, 'screenHeight': height, 'deviceScaleFactor': 1,
         'mobile': width <= 430})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#dividend'})
    ready = "document.readyState==='complete' && !!window.WealthFinancialIncomeWhatIf && !!document.getElementById('financialIncomeWhatIfPanel')"
    wait_for(evaluate, ready)

    def state():
        return evaluate("""(() => {
          const panel=document.getElementById('financialIncomeWhatIfPanel');
          return {mode:currentDividendMode,
            tab:document.querySelector('#dividendModeTabs .active')?.dataset.divMode,
            hidden:panel.hidden,display:getComputedStyle(panel).display,
            inDividend:!!panel.closest('#dividendPanel'),
            count:document.querySelectorAll('#financialIncomeWhatIfPanel').length,
            overflow:document.documentElement.scrollWidth>innerWidth,
            importVisible:!!document.getElementById('importDividendBtn')?.getClientRects().length};
        })()""")

    def assert_actual():
        wait_for(evaluate, "document.getElementById('financialIncomeWhatIfPanel').hidden")
        value = state()
        assert value['mode'] == value['tab'] == 'actual', value
        assert value['hidden'] and value['display'] == 'none', value
        assert value['inDividend'] and value['count'] == 1, value
        assert value['importVisible'] and not value['overflow'], value

    assert_actual()
    for _ in range(3):
        evaluate("document.querySelector('#dividendModeTabs [data-div-mode=estimated]').click()")
        wait_for(evaluate, "!document.getElementById('financialIncomeWhatIfPanel').hidden")
        value = state()
        assert value['mode'] == value['tab'] == 'estimated', value
        assert value['inDividend'] and value['count'] == 1 and not value['overflow'], value
        evaluate("document.querySelector('#dividendModeTabs [data-div-mode=actual]').click()")
        assert_actual()
    evaluate("location.hash='#assets'")
    wait_for(evaluate, "!document.querySelector('[data-wealth-page=assets]').hidden")
    evaluate("document.querySelector('.account-cat-tab[data-cat=tax]').click()")
    wait_for(evaluate, "!!document.getElementById('financialIncomeWhatIfPanel').closest('#taxWorkspaceBody') && !document.getElementById('financialIncomeWhatIfPanel').hidden")
    preserved = evaluate("""(() => {
      const workspace=document.getElementById('taxWorkspaceBody');
      const picker=document.getElementById('financialIncomeWhatIfPanel');
      const risk=document.getElementById('familyFinancialIncomeRiskPanel');
      const allocation=document.getElementById('familyFinancialIncomeAllocationPanel');
      const input=document.getElementById('fiWhatIfExtraDividend'); input.value='123456';
      const originalDashboard=rawDashboard, originalInsurance=rawInsuranceAccounts, owner=currentOwner;
      let result;
      try {
        rawDashboard={accounts:[
          {id:'synthetic-irr',name:'합성 IRP',account_type:'irp',owner:'모두'},
          {id:'synthetic-pension',name:'합성 연금저축',account_type:'pension_savings',owner:'모두'}]};
        rawInsuranceAccounts=[{id:'synthetic-national',product_name:'합성 국민연금',insurance_type:'national_pension',owner:'모두'}];
        currentOwner='모두'; renderAssetTaxInformation(); renderAssetTaxInformation();
        WealthTaxWorkspace.ensure(); WealthTaxWorkspace.ensure();
        const information=document.getElementById('assetTaxInformation');
        result={workspaceSame:workspace===document.getElementById('taxWorkspaceBody'),
          pickerSame:picker===document.getElementById('financialIncomeWhatIfPanel'),
          draft:input.value, riskSame:!!risk&&risk===document.getElementById('familyFinancialIncomeRiskPanel'),
          allocationSame:!!allocation&&allocation===document.getElementById('familyFinancialIncomeAllocationPanel'),
          workspaceCount:document.querySelectorAll('#taxWorkspaceBody').length,
          panelCount:document.querySelectorAll('#catPanelTax').length,
          informationCount:document.querySelectorAll('#assetTaxInformation').length,
          cards:[...information.querySelectorAll('.np-tax-card h3')].map(node=>node.textContent)};
      } finally {rawDashboard=originalDashboard;rawInsuranceAccounts=originalInsurance;currentOwner=owner;renderAssetTaxInformation();}
      return result;
    })()""")
    assert preserved['workspaceSame'] and preserved['pickerSame'], preserved
    assert preserved['riskSame'] and preserved['allocationSame'], preserved
    assert preserved['draft'] == '123456', preserved
    assert preserved['workspaceCount'] == preserved['panelCount'] == preserved['informationCount'] == 1, preserved
    assert set(preserved['cards']) == {'합성 국민연금', '합성 IRP', '합성 연금저축'}, preserved
    assert evaluate("currentDividendMode==='actual' && document.querySelector('#dividendModeTabs .active').dataset.divMode==='actual'")
    evaluate("location.hash='#dividend'")
    wait_for(evaluate, "!document.querySelector('[data-wealth-page=income]').hidden")
    assert_actual()
    previous = evaluate('performance.timeOrigin')
    call('Page.reload', {'ignoreCache': False})
    wait_for(evaluate, f'performance.timeOrigin>{previous} && ({ready})')
    assert_actual()
    call('Emulation.setDeviceMetricsOverride', {'width': 1280, 'height': 900,
         'screenWidth': 1280, 'screenHeight': 900, 'deviceScaleFactor': 1, 'mobile': False})
    assert_actual()


@pytest.mark.parametrize('width,height', [(320, 568), (390, 844), (1280, 900)])
def test_what_if_stale_requests_cannot_change_result_status_or_button(chrome_preview, width, height):
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height,
         'screenWidth': width, 'screenHeight': height, 'deviceScaleFactor': 1,
         'mobile': width <= 430})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#dividend'})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthFinancialIncomeWhatIf")
    result = evaluate("""(async () => {
      const frame=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      const click=mode=>document.querySelector('#dividendModeTabs [data-div-mode='+mode+']').click();
      click('estimated'); await frame();
      const originalFetch=window.fetch, originalOwner=currentOwner;
      const pending=[];
      window.fetch=(url, options)=>{
        if(String(url)!=='/api/dividends/financial-income-what-if') return originalFetch(url, options);
        return new Promise(resolve=>pending.push({resolve, payload:JSON.parse(options.body)}));
      };
      const snapshot=()=>({html:document.getElementById('financialIncomeWhatIfResult').innerHTML,
        status:document.getElementById('fiWhatIfStatus').textContent,
        disabled:document.getElementById('fiWhatIfRun').disabled});
      const start=()=>{
        const task=WealthFinancialIncomeWhatIf.runSimulation();
        const request=pending.at(-1);
        return {task,request};
      };
      const finish=async(job, amount)=>{
        job.request.resolve(new Response(JSON.stringify({what_if:{
          baseline_projected_gross_screening_income_krw:amount}}),{
          status:200,headers:{'Content-Type':'application/json'}}));
        await job.task; await frame();
      };
      const checks=[];
      const unchanged=(before)=>JSON.stringify(before)===JSON.stringify(snapshot());
      try {
        // A completing while B is pending must not enable B's button.
        const a=start(), b=start(), before=snapshot();
        await finish(a,111);
        checks.push({name:'old completion while B pending',pass:unchanged(before)&&snapshot().disabled});
        await finish(b,222);
        checks.push({name:'B completion',pass:!snapshot().disabled&&snapshot().status==='계산 완료'});
        // Reverse response order: B first, then A.
        const lateA=start(), earlyB=start();
        await finish(earlyB,333); const completed=snapshot();
        await finish(lateA,444);
        checks.push({name:'late A after B',pass:unchanged(completed)});
        const modeA=start(); click('actual'); await frame(); const actual=snapshot();
        await finish(modeA,555);
        checks.push({name:'actual mode invalidation',pass:unchanged(actual)&&document.getElementById('financialIncomeWhatIfPanel').hidden});
        click('estimated'); await frame();
        const ownerA=start(); currentOwner='synthetic-new-owner';
        WealthFinancialIncomeWhatIf.syncVisibility(); const ownerB=start();
        const ownerPending=snapshot(); await finish(ownerA,666);
        checks.push({name:'Owner invalidation',pass:unchanged(ownerPending)&&snapshot().disabled&&ownerB.request.payload.owner==='synthetic-new-owner'});
        await finish(ownerB,777);
        const taxA=start(); location.hash='#assets'; await frame();
        document.querySelector('.account-cat-tab[data-cat=tax]').click(); await frame();
        checks.push({name:'tax context',pass:!!document.getElementById('financialIncomeWhatIfPanel').closest('#taxWorkspaceBody')});
        const workspace=document.getElementById('taxWorkspaceBody'), panel=document.getElementById('financialIncomeWhatIfPanel');
        renderAssetTaxInformation();
        checks.push({name:'tax render preserves workspace and request',pass:workspace===document.getElementById('taxWorkspaceBody')&&panel===document.getElementById('financialIncomeWhatIfPanel')&&document.querySelectorAll('#taxWorkspaceBody').length===1&&document.querySelectorAll('#catPanelTax').length===1});
        location.hash='#dividend'; await frame(); const returned=start(), returning=snapshot();
        await finish(taxA,888);
        checks.push({name:'tax visit invalidates old request',pass:unchanged(returning)&&snapshot().disabled});
        await finish(returned,999);
        checks.push({name:'single panel after return',pass:document.querySelectorAll('#financialIncomeWhatIfPanel').length===1&&!!document.getElementById('financialIncomeWhatIfPanel').closest('#dividendPanel')});
        const unrelated=document.createElement('div'); document.body.append(unrelated);
        unrelated.className='synthetic-unrelated'; unrelated.hidden=true;
        await frame(); unrelated.remove();
        checks.push({name:'unrelated DOM preserves state',pass:!snapshot().disabled&&snapshot().status==='계산 완료'});
        return checks;
      } finally { window.fetch=originalFetch; currentOwner=originalOwner; }
    })()""")
    assert result and all(check['pass'] for check in result), result


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
    # P0 initializes the calendar without fetching/rendering an inactive dividend
    # tab. Establish that baseline before entering through the user's click path.
    wait_for(evaluate, "document.readyState==='complete' && typeof window.setIncomeTab==='function' && !!window.WealthUnifiedTimeseries && !!window.WealthStartup?.canRead() && !!document.querySelector('#incomeTabs [data-income=\"dividend\"]')")
    initial = evaluate("""(() => ({
      hash:location.hash, tab:currentIncomeTab,
      selected:document.querySelector('#incomeTabs .income-tab.active')?.dataset.income,
      calendarVisible:!!document.getElementById('calendarPanel').getClientRects().length,
      dividendHidden:document.getElementById('dividendPanel').classList.contains('wealth-income-hidden'),
      dividendChart:!!document.querySelector('#dividendBarChartWrap .wealth-unified-chart-shell'),
      requests:window.__divTrace.requests
    }))()""")
    assert initial['hash'] == '#income' and initial['tab'] == initial['selected'] == 'calendar', initial
    assert initial['calendarVisible'] and initial['dividendHidden'] and not initial['dividendChart'], initial
    assert not any(urlsplit(key).path in {'/api/actual-dividends', '/api/dividends'}
                   for key in initial['requests']), initial
    # Observe existing full-history responses, without issuing another request
    # or replacing their data. The chart uses both dividend and interest rows.
    evaluate("""(() => {
      const originalApi=window.api;
      window.__v213DividendSource={originalApi,byOwner:new Map()};
      window.api=async function(url,...args){
        const response=await originalApi.call(this,url,...args);
        const parsed=new URL(url,location.origin);
        if(parsed.pathname==='/api/actual-dividends' && parsed.searchParams.get('year')==='all'){
          window.__v213DividendSource.byOwner.set(parsed.searchParams.get('owner'),response);
        }
        return response;
      };
    })()""")
    evaluate("document.querySelector('#incomeTabs [data-income=dividend]').click()")
    # This is setup for the geometry/mode/race checks below, not the slow first
    # visible-frame test, which independently observes the complete entry sequence.
    wait_for(evaluate, "location.hash==='#dividend' && currentIncomeTab==='dividend' && document.querySelector('#incomeTabs .income-tab.active')?.dataset.income==='dividend' && !!document.getElementById('dividendPanel').getClientRects().length && !!document.querySelector('#dividendBarChartWrap .wealth-unified-chart-shell') && !!actualDividendData && !window.setIncomeTab.pendingTarget")
    result = evaluate("""(async () => {
      const host=document.getElementById('dividendBarChartWrap');
      const panel=document.getElementById('dividendPanel');
      const sample=() => {
        const viewport=host.querySelector('.wealth-unified-viewport');
        const content=host.querySelector('.wealth-unified-content');
        const controls=document.querySelector('.wealth-unified-periods[data-kind="dividend"]');
        return {tab:document.querySelector('#incomeTabs .income-tab.active')?.dataset.income,
          controls:{exists:!!controls,hidden:controls?.hidden,
            display:controls?getComputedStyle(controls).display:null,visible:!!controls?.getClientRects().length},
          hidden:panel.classList.contains('wealth-income-hidden'),
          visible:!!panel.getClientRects().length && !!document.querySelector('.wealth-workspace')?.getClientRects().length
            && !panel.closest('[data-wealth-page]')?.hidden && getComputedStyle(panel).visibility!=='hidden',
          actualMode:currentDividendMode,owner:String(currentOwner || '모두'),year:String(selectedDividendYear),
          mode:window.WealthUnifiedTimeseries.modes.dividend,
          renderedMode:window.WealthUnifiedTimeseries.getDetailMode('dividend'),
          expectedRenderedMode:expectedRenderedMode(window.WealthUnifiedTimeseries.modes.dividend),
          scope:window.WealthUnifiedTimeseries.dividendScopeKey(),
          dataRange:JSON.stringify(chartSourceRows()?.map(row=>[row.id || '',row.date,row.amount_krw,row.broker || '']) || null),
          unifiedCount:host.querySelectorAll('.wealth-unified-chart-shell').length,
          child:host.firstElementChild?.className?.baseVal || host.firstElementChild?.className || '',
          legacy:!!host.querySelector('svg.record-chart'),
          unified:!!host.querySelector('.wealth-unified-chart-shell'),
          client:viewport?.clientWidth || 0,scrollWidth:viewport?.scrollWidth || 0,
          scrollLeft:viewport?.scrollLeft || 0,width:content?.getBoundingClientRect().width || 0};
      };
      const chartSourceRows=() => {
        const owner=String(currentOwner || '모두');
        const source=window.__v213DividendSource.byOwner.get(owner);
        if(!source) return null;
        const broker=document.getElementById('dividendBrokerFilter')?.value || 'all';
        return [...(source.records || []),...(source.interest_records || [])].filter(record=>{
          const label=String(record?.broker || '').trim();
          return broker==='all' || (broker==='__unassigned__'?!label:label===broker);
        });
      };
      const expectedRenderedMode=mode => {
        const rows=chartSourceRows();
        return rows===null?null:window.WealthTimeseriesPeriodCore.effectiveMode(rows,mode,'date');
      };
      const waitActualReady=async (mode, phase, frames) => {
        const started=performance.now();
        const scope=window.WealthUnifiedTimeseries.dividendScopeKey();
        for(let i=0;i<600 && performance.now()-started<10000;i++){
          const frame=sample();
          frame.mode=window.WealthUnifiedTimeseries.modes.dividend;
          frame.renderedMode=window.WealthUnifiedTimeseries.getDetailMode('dividend');
          frame.expectedRenderedMode=expectedRenderedMode(mode);
          frame.owner=String(currentOwner || '모두');
          frame.year=String(selectedDividendYear);
          frame.scope=window.WealthUnifiedTimeseries.dividendScopeKey();
          frames.push(frame);
          if(frame.visible && frame.legacy) throw new Error(phase+': visible legacy chart '+JSON.stringify(frame));
          if(frame.tab==='dividend' && currentIncomeTab==='dividend' && !frame.hidden && frame.visible
              && currentDividendMode==='actual' && frame.unified && !frame.legacy
              && host.querySelectorAll('.wealth-unified-chart-shell').length===1
              && frame.client>0 && frame.width>0 && frame.mode===mode
              && frame.controls.exists && !frame.controls.hidden && frame.controls.display!=='none' && frame.controls.visible
              && frame.expectedRenderedMode!==null && frame.renderedMode===frame.expectedRenderedMode
              && frame.scope===scope
              && !window.setIncomeTab.pendingTarget) return frame;
          await new Promise(requestAnimationFrame);
        }
        throw new Error(phase+': actual chart readiness timed out '+JSON.stringify(frames.at(-1)));
      };
      const observeActual=async (mode,phase,count) => {
        const frames=[];
        await waitActualReady(mode,phase,frames);
        for(let i=0;i<count;i++){
          await new Promise(requestAnimationFrame);
          frames.push(sample());
        }
        return frames;
      };
      const visits=[];
      for(let visit=0;visit<2;visit++){
        document.querySelector('#incomeTabs [data-income="calendar"]').click();
        document.querySelector('#incomeTabs [data-income="dividend"]').click();
        renderActualDividends(actualDividendData);
        visits.push(await observeActual(window.WealthUnifiedTimeseries.modes.dividend,'visit '+visit,70));
      }
      const actualVisitWrites=[...window.__divTrace.writes];
      const modes={};
      for(const key of ['DAY','WEEK','MONTH','YEAR','ALL']){
        const frames=[];
        await waitActualReady(window.WealthUnifiedTimeseries.modes.dividend,key+' previous entry',frames);
        const mode=window.WealthTimeseriesPeriodCore.MODES[key];
        window.WealthUnifiedTimeseries.modes.dividend=mode;
        await window.WealthUnifiedTimeseries.renderDividend();
        const before=await waitActualReady(mode,key+' before',frames);
        document.querySelector('#incomeTabs [data-income="calendar"]').click();
        document.querySelector('#incomeTabs [data-income="dividend"]').click();
        const after=await waitActualReady(mode,key+' return',frames);
        modes[key]={before,after,frames,expected:mode,selected:window.WealthUnifiedTimeseries.modes.dividend};
      }
      const actualModeWrites=[...window.__divTrace.writes];
      document.querySelector('#dividendModeTabs [data-div-mode="estimated"]').click();
      for(let i=0;i<600 && !host.querySelector('svg.record-chart');i++) await new Promise(requestAnimationFrame);
      const estimated=sample();
      const actualReturnWriteStart=window.__divTrace.writes.length;
      document.querySelector('#dividendModeTabs [data-div-mode="actual"]').click();
      const actualFrames=await observeActual(window.WealthUnifiedTimeseries.modes.dividend,'actual mode return',5);
      window.WealthUnifiedTimeseries.modes.dividend=window.WealthTimeseriesPeriodCore.MODES.MONTH;
      await window.WealthUnifiedTimeseries.renderDividend();
      currentOwner='synthetic-slow';
      const slow=window.WealthUnifiedTimeseries.renderDividend();
      currentOwner='synthetic-fast';
      const fast=window.WealthUnifiedTimeseries.renderDividend();
      await Promise.all([slow,fast]);
      const actualReturnWrites=window.__divTrace.writes.slice(actualReturnWriteStart);
      const raceLabel=host.querySelector('svg text[y="280"]')?.textContent || '';
      window.api=window.__v213DividendSource.originalApi;
      return {visits,modes,estimated,actualFrames,actualVisitWrites,actualModeWrites,actualReturnWrites,writes:window.__divTrace.writes,
        requests:window.__divTrace.requests,
        raceLabel,
        summary:document.getElementById('divTotalAnnual')?.textContent,
        detail:!!document.querySelector('#dividendMonthlyDetail .div-detail-header')};
    })()""")
    print("DIVIDEND_FRAMES=" + json.dumps({"width": width, **result}))
    def assert_visible_actual_stability(frames):
        displayed = [(index, frame) for index, frame in enumerate(frames)
                     if frame['visible'] and not frame['hidden'] and frame['actualMode'] == 'actual']
        assert displayed, frames
        first_index, first = displayed[0]
        assert first['dataRange'] != 'null', frames
        for frame in frames[first_index:]:
            # Once displayed, a chart must not disappear again or expose an old
            # renderer/scope. Hidden preparation frames before this point remain
            # in the trace but are not valid geometry measurements.
            assert frame['visible'] and not frame['hidden'] and frame['actualMode'] == 'actual', frames
            assert frame['tab'] == 'dividend' and frame['unified'] and not frame['legacy'], frames
            assert frame['unifiedCount'] == 1, frames
            assert frame['controls']['exists'] and not frame['controls']['hidden'], frames
            assert frame['controls']['display'] != 'none' and frame['controls']['visible'], frames
            assert frame['client'] > 0 and frame['width'] > 0, frames
            assert frame['width'] == first['width'], frames
            assert frame['scrollLeft'] == first['scrollLeft'], frames
            for field in ('owner', 'year', 'scope', 'dataRange', 'mode', 'renderedMode'):
                assert frame[field] == first[field], frames
            assert frame['renderedMode'] == frame['expectedRenderedMode'], frames
            if frame['mode'] != 'ALL':
                assert frame['renderedMode'] == frame['mode'], frames
        return first

    assert len(result['visits']) == 2, result
    assert not any(write["kind"] == "legacy" and write["visible"] for write in result["actualVisitWrites"]), result
    for visit in result["visits"]:
        assert_visible_actual_stability(visit)
    for pair in result["modes"].values():
        assert pair['selected'] == pair['expected'], pair
        for frame in (pair['before'], pair['after']):
            assert frame['visible'] and not frame['hidden'] and frame['tab'] == 'dividend', pair
            assert frame['unified'] and not frame['legacy'] and frame['client'] > 0 and frame['width'] > 0, pair
            assert frame['controls']['exists'] and not frame['controls']['hidden'], pair
            assert frame['controls']['display'] != 'none' and frame['controls']['visible'], pair
            assert frame['mode'] == pair['expected'], pair
            assert frame['renderedMode'] == frame['expectedRenderedMode'], pair
            if pair['expected'] != 'ALL':
                assert frame['renderedMode'] == pair['expected'], pair
        assert pair['before']['renderedMode'] == pair['after']['renderedMode'], pair
        assert pair['before']['owner'] == pair['after']['owner'], pair
        assert pair['before']['year'] == pair['after']['year'], pair
        assert pair['before']['scope'] == pair['after']['scope'], pair
        assert not any(frame['visible'] and frame['legacy'] for frame in pair['frames']), pair
        assert pair["before"]["width"] == pair["after"]["width"], pair
        assert pair["before"]["scrollLeft"] == pair["after"]["scrollLeft"], pair
    assert not any(write['kind'] == 'legacy' and write['visible'] for write in result['actualModeWrites']), result
    assert result["estimated"]["legacy"] and not result["estimated"]["unified"], result
    assert result['estimated']['controls']['exists'] and result['estimated']['controls']['hidden'], result
    assert result['estimated']['controls']['display'] == 'none' and not result['estimated']['controls']['visible'], result
    assert_visible_actual_stability(result['actualFrames'])
    assert not any(write['kind'] == 'legacy' and write['visible'] for write in result['actualReturnWrites']), result
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
    wait_for(evaluate, "!loadAssetDataForUser.pending && !window.setIncomeTab.pendingTarget && currentIncomeTab==='dividend' && !!actualDividendData && !!document.getElementById('dividendPanel').getClientRects().length")
    counts = evaluate("window.__divTrace.requests")
    print("ACTUAL_STARTUP_COUNTS=" + json.dumps({key: counts.count(key) for key in sorted(set(counts))}))
    assert evaluate("window.__divTrace.requests.filter(key=>key.startsWith('/api/dividends?')).length") == 0
    result = evaluate("""(async()=>{
      const trace=window.__divTrace, gates=new Map(), originalFetch=window.fetch, requestEvents=[];
      const originalLoadActual=window.loadActualDividends,handoffs=[];
      window.loadActualDividends=function(owner,year,prepared){
        if(prepared?.response){
          handoffs.push({owner,year,accepted:preparedActualDividendResponse(prepared,owner,year)===prepared.response,
            staleEpochRejected:preparedActualDividendResponse({...prepared,readEpoch:prepared.readEpoch-1},owner,year)===null,
            otherOwnerRejected:preparedActualDividendResponse(prepared,owner+'-other',year)===null,
            otherYearRejected:preparedActualDividendResponse(prepared,owner,year==='all'?'1900':'all')===null,
            otherScopeRejected:preparedActualDividendResponse({...prepared,scope:prepared.scope+'-old'},owner,year)===null});
        }
        return originalLoadActual.call(this,owner,year,prepared);
      };
      const matching=(start,path,owner)=>trace.requests.slice(start).filter(key=>{
        const url=new URL(key,location.origin);
        return url.pathname===path && (owner===undefined || url.searchParams.get('owner')===owner);
      });
      const until=async(predicate,phase)=>{
        const start=performance.now();
        for(let i=0;i<600 && performance.now()-start<10000;i++){
          if(predicate())return;
          await new Promise(requestAnimationFrame);
        }
        throw new Error(phase+' timed out '+JSON.stringify({hash:location.hash,tab:currentIncomeTab,
          owner:currentOwner,pending:window.setIncomeTab.pendingTarget,requests:trace.requests}));
      };
      const ready=kind=>currentIncomeTab===kind && location.hash==='#'+kind
        && document.querySelector('.wealth-workspace').dataset.activeView==='income'
        && document.querySelector('.wealth-workspace').dataset.incomeTab===kind
        && document.querySelector('#incomeTabs .income-tab.active')?.dataset.income===kind
        && !!document.getElementById(kind==='pnl'?'realizedPnlPanel':'dividendPanel').getClientRects().length
        && !window.setIncomeTab.pendingTarget
        && window.WealthUnifiedTimeseries.getDetailMode(kind)!==null
        && !!document.querySelector('#'+(kind==='pnl'?'pnlBarChartWrap':'dividendBarChartWrap')+' .wealth-unified-chart-shell');
      window.fetch=function(...args){
        const url=new URL(String(args[0]),location.origin);
        const gate=gates.get(url.pathname+'|'+url.searchParams.get('owner'));
        const event=url.pathname==='/api/actual-dividends'?{
          order:requestEvents.length+1,url:url.pathname+url.search,start:performance.now(),
          stack:new Error('actual dividend GET caller').stack,
          tab:currentIncomeTab,owner:currentOwner,year:selectedDividendYear,mode:currentDividendMode,
          broker:document.getElementById('dividendBrokerFilter')?.value || 'all',
          scope:window.WealthUnifiedTimeseries.dividendScopeKey(),
          previousSameUrl:requestEvents.filter(item=>item.url===url.pathname+url.search).map(item=>({
            order:item.order,networkEnd:item.networkEnd || null,delivered:item.delivered || null})),
          sharedPendingAtStart:startupReadPending.has(url.pathname+url.search),
          gateReleased:gate?gate.released:null}:null;
        if(event)requestEvents.push(event);
        const response=originalFetch.apply(this,args);
        if(gate)gate.started++;
        return response.then(async value=>{
          if(event)event.networkEnd=performance.now();
          if(gate)await gate.pending;
          if(event)event.delivered=performance.now();
          return value;
        },error=>{if(event)event.failed=performance.now();throw error;});
      };
      const checks=[];
      try{
        const idleStart=trace.requests.length;
        await Promise.all(Array.from({length:12},()=>window.WealthUnifiedTimeseries.renderPnl()));
        const inactivePnl=matching(idleStart,'/api/realized-pnl').length;
        for(const [kind,owner,path] of [
            ['pnl','synthetic-dedupe-pnl','/api/realized-pnl'],
            ['dividend','synthetic-dedupe-dividend','/api/actual-dividends']]){
          if(kind==='dividend'){
            // Complete hidden-panel preparation under the previous scope first.
            // Then a fresh owner plus a real re-entry click tests overlapping
            // active render calls, rather than calls correctly skipped while hidden.
            document.querySelector('#incomeTabs [data-income=dividend]').click();
            await until(()=>ready('dividend'),'dividend activation before fresh scope');
            await until(()=>!startupReadPending.size,'previous scope GET completion');
          }
          const start=trace.requests.length;
          const gate={started:0,released:false};gate.pending=new Promise(resolve=>{
            gate.release=()=>{gate.released=true;resolve();};
          });
          gates.set(path+'|'+owner,gate);
          currentOwner=owner;
          selectedPnlYear='all';selectedDividendYear='all';
          document.getElementById('pnlYearSelect').value='all';
          document.getElementById('dividendYearSelect').value='all';
          document.querySelector('#incomeTabs [data-income='+kind+']').click();
          await until(()=>gate.started>0,kind+' activation request');
          // Response delivery is gated, so the batch must join an unfinished
          // request, not merely reuse a previously rendered/cached chart.
          let completed=0;
          const render=kind==='pnl'?'renderPnl':'renderDividend';
          const batch=Array.from({length:12},()=>window.WealthUnifiedTimeseries[render]().then(()=>completed++));
          const inactiveStart=trace.requests.length;
          const inactiveRender=kind==='pnl'?'renderDividend':'renderPnl';
          await Promise.all(Array.from({length:12},()=>window.WealthUnifiedTimeseries[inactiveRender]()));
          const inactivePath=kind==='pnl'?'/api/actual-dividends':'/api/realized-pnl';
          const overlap={requests:matching(start,path,owner).length,started:gate.started,completed,
            inactive:matching(inactiveStart,inactivePath,owner).length};
          gate.release();await Promise.all(batch);
          await until(()=>ready(kind),kind+' active chart');
          // Include automatic navigation loads in the final same-scope count.
          await until(()=>!startupReadPending.size,kind+' pending GET completion');
          checks.push({kind,owner,overlap,total:matching(start,path,owner).length,
            urls:matching(start,path,owner),scope:window.WealthUnifiedTimeseries.dividendScopeKey(),
            activeOwner:currentOwner,tab:currentIncomeTab});
          gates.delete(path+'|'+owner);
        }
        return {inactivePnl,checks,requests:[...trace.requests],requestEvents,handoffs};
      }finally{
        for(const gate of gates.values())gate.release();
        window.fetch=originalFetch;
        window.loadActualDividends=originalLoadActual;
      }
    })()""")
    print('ACTIVE_DEDUPE=' + json.dumps(result))
    assert result['handoffs'], result
    for handoff in result['handoffs']:
        assert all(handoff[key] for key in ('accepted', 'staleEpochRejected', 'otherOwnerRejected',
                                            'otherYearRejected', 'otherScopeRejected')), handoff
    assert result['inactivePnl'] == 0, result
    assert len(result['checks']) == 2, result
    for check in result['checks']:
        assert check['overlap']['requests'] == check['overlap']['started'] == 1, check
        assert check['overlap']['completed'] == 0 and check['overlap']['inactive'] == 0, check
        assert check['total'] == 1, check
        assert check['activeOwner'] == check['owner'] and check['tab'] == check['kind'], check
        assert all(parse_qs(urlsplit(url).query).get('year') == ['all'] for url in check['urls']), check
    estimated = evaluate("""(async()=>{
      const originalFetch=window.fetch,events=[],actions=[];
      const owner=currentOwner;
      let stage='first-entry';
      const cacheState=()=>({present:!!dividendData,dataOwner:dividendDataOwner,
        ownerMatches:dividendDataOwner===currentOwner,cacheEpoch:dividendDataEpoch,epoch:startupReadEpoch});
      const calls=scope=>window.__divTrace.requests.filter(key=>{
        const url=new URL(key,location.origin);
        return url.pathname==='/api/dividends' && url.searchParams.get('owner')===scope;
      });
      const until=async(scope)=>{
        const started=performance.now();
        for(let i=0;i<600 && performance.now()-started<10000;i++){
          const key='/api/dividends?owner='+encodeURIComponent(scope);
          if(currentIncomeTab==='dividend' && currentDividendMode==='estimated'
              && currentOwner===scope && dividendData && dividendDataOwner===scope
              && dividendDataEpoch===startupReadEpoch && !startupReadPending.has(key)
              && document.getElementById('dividendPanel').getClientRects().length
              && document.querySelector('#dividendBarChartWrap svg.record-chart')
              && !document.querySelector('#dividendBarChartWrap .wealth-unified-chart-shell'))return;
          await new Promise(requestAnimationFrame);
        }
        throw new Error('estimated readiness timed out '+JSON.stringify({stage,owner:currentOwner,cache:cacheState(),events}));
      };
      window.fetch=function(...args){
        const url=new URL(String(args[0]),location.origin);
        if(url.pathname!=='/api/dividends')return originalFetch.apply(this,args);
        const event={url:url.pathname+url.search,owner:url.searchParams.get('owner'),stage,
          started:performance.now(),tab:currentIncomeTab,mode:currentDividendMode,currentOwner,
          cache:cacheState(),stack:new Error('estimated dividend GET caller').stack,
          previous:events.map(item=>({url:item.url,started:item.started,completed:item.completed || null}))};
        events.push(event);
        return originalFetch.apply(this,args).then(response=>{
          event.completed=performance.now();return response;
        },error=>{event.failed=performance.now();throw error;});
      };
      try{
        actions.push({stage,owner,cache:cacheState(),mutation:false,refresh:false});
        document.querySelector('#dividendModeTabs [data-div-mode=estimated]').click();
        await until(owner);
        const first=[...calls(owner)],firstCache=cacheState();
        stage='same-owner-reentry';
        actions.push({stage,owner:currentOwner,cache:cacheState(),mutation:false,refresh:false});
        document.querySelector('#dividendModeTabs [data-div-mode=actual]').click();
        document.querySelector('#dividendModeTabs [data-div-mode=estimated]').click();
        await until(owner);
        const reentry=[...calls(owner)],reentryCache=cacheState();
        stage='owner-change';
        const otherOwner='synthetic-estimated-other';
        actions.push({stage,owner:otherOwner,mutation:false,refresh:false});
        selectOwner(otherOwner);
        const ownerChangeStarted=cacheState();
        await until(otherOwner);
        return {owner,otherOwner,first,reentry,firstCache,reentryCache,ownerChangeStarted,
          otherCalls:calls(otherOwner),otherCache:cacheState(),events,actions};
      }finally{window.fetch=originalFetch;}
    })()""")
    print('ESTIMATED_REQUESTS=' + json.dumps(estimated))
    assert len(estimated['first']) == 1, estimated
    assert estimated['reentry'] == estimated['first'], estimated
    for state in (estimated['firstCache'], estimated['reentryCache']):
        assert state['present'] and state['ownerMatches'] and state['dataOwner'] == estimated['owner'], estimated
        assert state['cacheEpoch'] == state['epoch'], estimated
    assert estimated['firstCache']['epoch'] == estimated['reentryCache']['epoch'], estimated
    assert not estimated['ownerChangeStarted']['present'], estimated
    assert len(estimated['otherCalls']) == 1, estimated
    assert estimated['otherCache']['dataOwner'] == estimated['otherOwner'], estimated
    assert estimated['otherCache']['ownerMatches'], estimated
    empty = evaluate("""(async()=>{
      currentOwner='synthetic-empty';
      const checks=[];
      for(const kind of ['pnl','dividend']){
        if(kind==='dividend'){
          document.querySelector('#incomeTabs [data-income=dividend]').click();
          document.querySelector('#dividendModeTabs [data-div-mode=actual]').click();
        }
        else document.querySelector('#incomeTabs [data-income=pnl]').click();
        const panel=document.getElementById(kind==='pnl'?'realizedPnlPanel':'dividendPanel');
        const host=document.getElementById(kind==='pnl'?'pnlBarChartWrap':'dividendBarChartWrap');
        const start=performance.now();let prepared=false;
        for(let i=0;i<600 && performance.now()-start<10000;i++){
          if(currentIncomeTab===kind && location.hash==='#'+kind && panel.getClientRects().length
              && !window.setIncomeTab.pendingTarget && host.querySelector(':scope > .wealth-unified-empty')
              && window.WealthUnifiedTimeseries.getDetailMode(kind)!==null){prepared=true;break;}
          await new Promise(requestAnimationFrame);
        }
        if(!prepared)throw new Error(kind+' empty active chart timed out');
        for(let i=0;i<3;i++) await new Promise(requestAnimationFrame);
        const before=window.__divTrace.unifiedCalls;
        const probe=document.createElement('div');document.body.append(probe);
        for(let i=0;i<5;i++) await new Promise(requestAnimationFrame);
        probe.remove();
        for(let i=0;i<5;i++) await new Promise(requestAnimationFrame);
        checks.push({kind,before,after:window.__divTrace.unifiedCalls,
          empty:!!host.querySelector(':scope > .wealth-unified-empty'),owner:currentOwner});
      }
      return checks;
    })()""")
    assert [check['kind'] for check in empty] == ['pnl', 'dividend'], empty
    for check in empty:
        assert check['empty'] and check['before'] == check['after'], check
        assert check['owner'] == 'synthetic-empty', check
    cursor = evaluate("""(()=>{
      const node=document.elementFromPoint(innerWidth/2,innerHeight/2);
      const chain=[];
      for(let el=node;el;el=el.parentElement){const css=getComputedStyle(el);chain.push({tag:el.tagName,id:el.id,classes:el.className.baseVal??el.className,position:css.position,zIndex:css.zIndex,pointerEvents:css.pointerEvents});}
      return chain;
    })()""")
    print("CURSOR_CENTER_DOM=" + json.dumps(cursor))


class DividendBenefitPreview(StaticPreview):
    def model(self, owner='아빠', year=2026, selections=None):
        from datetime import date
        from tests.test_financial_income_what_if import DividendBenefitPreviewTests
        from app.services.tax.what_if import build_dividend_benefit_preview
        summary = DividendBenefitPreviewTests().fixture()
        if owner == '엄마':
            summary['monthly_schedule'] = []
        if getattr(self.server, 'benefit_missing_amount', False):
            summary['capital_dividend_evidence'] = {}
        result = build_dividend_benefit_preview(summary, owner=owner, tax_year=year,
            selections=selections, as_of=date(2026, 10, 17))
        return {**result, 'context_key': f'synthetic-user:{owner}:{year}', 'owners': ['아빠', '엄마']}

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            self.server.benefit_missing_amount = parse_qs(urlsplit(self.path).query).get('missing') == ['1']
            self.send(("""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
              <link rel="stylesheet" href="/static/wealth-financial-income-what-if.css"></head>
              <body><section id="dividendPanel"><div id="dividendModeTabs"><button data-div-mode="estimated" class="heatmap-tab active">예상</button></div>
              <div class="dividend-summary-cards"></div></section>
              <script>var currentOwner='아빠',currentDividendMode='actual';window.renderDividends=function(){};</script>
              <script src="/static/wealth-dividend-source.js"></script>
              <script src="/static/wealth-financial-income-what-if.js"></script></body></html>""").encode(), 'text/html; charset=utf-8')
            return
        if path.startswith('/static/'):
            name = path.rsplit('/', 1)[-1]
            if name in self.server.preview_assets:
                self.send(self.server.preview_assets[name], 'text/css' if name.endswith('.css') else 'text/javascript')
                return
        super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path == '/api/dividends/tax-benefit-preview':
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.benefit_requests = getattr(self.server, 'benefit_requests', []) + [body]
            self.send(self.model(body['owner'], body['tax_year'], body['selections']))
            return
        super().do_POST()


@pytest.mark.parametrize('width,theme', [(320, 'purple'), (390, 'white'), (1280, 'oled')])
def test_b2_benefit_modes_mobile_xss_and_scope(chrome_preview, width, theme):
    from datetime import date
    from tests.test_financial_income_what_if import DividendBenefitPreviewTests
    from app.services.tax.what_if import build_dividend_benefit_preview
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 900,
        'deviceScaleFactor': 1, 'mobile': width < 500})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/'})
    def wait(expression):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if evaluate(expression):
                return
            time.sleep(.05)
        raise AssertionError(expression)
    wait("!!window.WealthFinancialIncomeWhatIf && !!document.getElementById('dividendBenefitPreview')")
    model = build_dividend_benefit_preview(DividendBenefitPreviewTests().fixture(), owner='아빠',
        tax_year=2026, as_of=date(2026, 10, 17))
    model.update(context_key='synthetic-user:아빠:2026', owners=['아빠', '엄마'])
    evaluate(f"document.documentElement.dataset.theme={json.dumps(theme)};currentDividendMode='estimated';WealthFinancialIncomeWhatIf.syncVisibility();window.renderDividends({{dividend_tax_benefits:{json.dumps(model)}}})")
    wait("document.querySelectorAll('.fi-benefit-card').length===1")
    assert evaluate("document.querySelector('[data-benefit-kind=high_dividend][type=checkbox]').checked")
    assert not evaluate("document.querySelector('[data-benefit-kind=capital][type=checkbox]').checked")
    assert evaluate("document.querySelector('.fi-benefits').textContent.includes('기본 세후 카드와 별도 계산 · 자동 합산 없음')")
    assert evaluate("document.querySelectorAll('.fi-benefit-card img, .fi-benefit-card script').length") == 0
    assert evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert evaluate("[...document.querySelectorAll('.fi-benefits a')].every(a=>a.protocol==='https:')")
    evaluate("document.querySelector('[data-benefit-kind=capital][type=checkbox]').click()")
    wait("document.querySelector('.fi-benefits').textContent.includes('사용자 가정 적용')")
    assert evaluate("document.querySelector('.fi-benefits').textContent.includes('₩62')")
    assert evaluate("document.querySelector('.fi-benefits').textContent.includes('세금 적용 요건 미확인')")
    evaluate("document.querySelector('[data-benefit-kind=high_dividend][type=checkbox]').click()")
    wait("document.querySelector('[data-benefit-kind=high_dividend][type=checkbox]').checked===false && document.querySelector('.fi-benefits').getAttribute('aria-busy')===null")
    evaluate("document.querySelector('[data-benefit-kind=capital][type=checkbox]').click()")
    wait("document.querySelector('[data-benefit-kind=capital][type=checkbox]').checked===false && document.querySelector('.fi-benefits').getAttribute('aria-busy')===null")
    evaluate("document.querySelector('[data-benefit-auto][data-benefit-kind=high_dividend]').click()")
    wait("document.querySelector('[data-benefit-kind=high_dividend][type=checkbox]').checked && document.querySelector('.fi-benefits').getAttribute('aria-busy')===null")
    evaluate("const year=document.getElementById('fiBenefitYear');year.value='2025';year.dispatchEvent(new Event('change',{bubbles:true}))")
    wait("document.getElementById('fiBenefitYear')?.value==='2025' && !document.querySelector('.fi-benefit-card')")
    evaluate("const year2=document.getElementById('fiBenefitYear');year2.value='2026';year2.dispatchEvent(new Event('change',{bubbles:true}))")
    wait("document.querySelectorAll('.fi-benefit-card').length===1 && document.querySelector('.fi-benefits').getAttribute('aria-busy')===null")
    assert not evaluate("document.querySelector('[data-benefit-kind=capital][type=checkbox]').checked")
    evaluate("const owner=document.getElementById('fiBenefitOwner');owner.value='엄마';owner.dispatchEvent(new Event('change',{bubbles:true}))")
    wait("document.getElementById('fiBenefitOwner')?.value==='엄마' && !document.querySelector('.fi-benefit-card')")
    assert not evaluate("document.getElementById('dividendBenefitPreview').textContent.includes('<img')")


def test_b2_benefit_missing_amount_failure_draft_and_stale_user_response(chrome_preview):
    from datetime import date
    from tests.test_financial_income_what_if import DividendBenefitPreviewTests
    from app.services.tax.what_if import build_dividend_benefit_preview
    call, evaluate, port = chrome_preview
    call('Emulation.setDeviceMetricsOverride', {'width': 320, 'height': 800,
        'deviceScaleFactor': 1, 'mobile': True})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/?missing=1'})
    def wait(expression):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if evaluate(expression): return
            time.sleep(.05)
        raise AssertionError(expression)
    wait("!!window.WealthFinancialIncomeWhatIf && !!document.getElementById('dividendBenefitPreview')")
    summary = DividendBenefitPreviewTests().fixture(); summary['capital_dividend_evidence'] = {}
    model = build_dividend_benefit_preview(summary, owner='아빠', tax_year=2026, as_of=date(2026, 10, 17))
    model.update(context_key='synthetic-user:아빠:2026', owners=['아빠', '엄마'])
    evaluate(f"currentDividendMode='estimated';WealthFinancialIncomeWhatIf.syncVisibility();window.renderDividends({{dividend_tax_benefits:{json.dumps(model)}}})")
    evaluate("document.querySelector('[data-benefit-kind=capital][type=checkbox]').click()")
    wait("!!document.querySelector('[data-benefit-amount][data-benefit-kind=capital]')")
    assert evaluate("document.querySelector('[data-benefit-amount][data-benefit-kind=capital]').value") == ''
    evaluate("const amount=document.querySelector('[data-benefit-amount][data-benefit-kind=capital]');amount.value='400';amount.dispatchEvent(new Event('change',{bubbles:true}))")
    wait("document.querySelector('.fi-benefits').textContent.includes('₩62') && !document.querySelector('.fi-benefits').hasAttribute('aria-busy')")
    evaluate("window.__benefitFetch=fetch;window.fetch=(...args)=>String(args[0]).includes('tax-benefit-preview')?Promise.resolve(new Response('{}',{status:503})):__benefitFetch(...args)")
    evaluate("const amount2=document.querySelector('[data-benefit-amount][data-benefit-kind=capital]');amount2.value='350';amount2.dispatchEvent(new Event('change',{bubbles:true}))")
    wait("document.getElementById('fiBenefitStatus').textContent.includes('계산 실패')")
    assert evaluate("document.querySelector('[data-benefit-amount][data-benefit-kind=capital]').value") == '350'
    evaluate("window.fetch=async(...args)=>{const response=await __benefitFetch(...args);if(String(args[0]).includes('tax-benefit-preview'))await new Promise(r=>setTimeout(r,300));return response}")
    evaluate("document.querySelector('[data-benefit-auto][data-benefit-kind=capital]').click()")
    other = {**model, 'owner': '엄마', 'events': [], 'context_key': 'different-user:엄마:2026'}
    evaluate(f"window.renderDividends({{dividend_tax_benefits:{json.dumps(other)}}})")
    evaluate("new Promise(r=>setTimeout(r,600))")
    assert evaluate("document.getElementById('fiBenefitOwner').value") == '엄마'
    assert evaluate("document.querySelectorAll('.fi-benefit-card').length") == 0
    assert not evaluate("document.documentElement.scrollWidth>innerWidth")
