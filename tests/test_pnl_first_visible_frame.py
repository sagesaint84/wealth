"""Real Chrome regression for the first visible income chart frame."""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
from contextlib import ExitStack, contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.test_realized_pnl_viewport import StaticPreview, _chrome_path


VIEWPORTS = [(320, 568), (390, 844), (1024, 768), (1440, 900)]
RECORDS = [
    {"date": f"{year}-{month:02d}-10", "owner": "모두", "broker": "가상증권",
     "name": "가상종목", "code": "SYN", "pnl_krw": 1000 + month, "amount_krw": 1000}
    for year in range(2022, 2027) for month in range(1, 13)
]


class IncomePreview(StaticPreview):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/realized-pnl":
            owner = parse_qs(urlsplit(self.path).query).get("owner", [""])[0]
            if owner == "synthetic-slow":
                time.sleep(0.2)
                self.send({"records": RECORDS[:1], "monthly": [], "available_years": [2022]})
                return
            if owner == "synthetic-fast":
                self.send({"records": RECORDS[-1:], "monthly": [], "available_years": [2026]})
                return
            self.send({"records": RECORDS, "monthly": [], "available_years": list(range(2022, 2027))})
            return
        if path == "/api/actual-dividends":
            self.send({"records": RECORDS, "interest_records": [], "monthly": [],
                       "available_years": list(range(2022, 2027))})
            return
        super().do_GET()


@contextmanager
def chrome_profile(prefix):
    path = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        yield str(path)
    finally:
        for attempt in range(20):
            try:
                shutil.rmtree(path)
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.2)


@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_pnl_first_visible_frame_matches_settled_chart(width, height):
    websocket = pytest.importorskip("websocket")
    chrome = _chrome_path()
    if chrome is None:
        pytest.skip("Chromium browser unavailable")
    server = ThreadingHTTPServer(("127.0.0.1", 0), IncomePreview)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = None
    try:
        with ExitStack() as cleanup:
            profile = cleanup.enter_context(chrome_profile("wealth-pnl-frame-"))
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(
                [chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
                 "--disable-gpu", "--remote-allow-origins=*", "--remote-debugging-port=0",
                 f"--user-data-dir={profile}", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
            )

            def stop_chrome():
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)

            cleanup.callback(stop_chrome)
            active_port = Path(profile) / "DevToolsActivePort"
            for _ in range(100):
                if active_port.exists():
                    break
                time.sleep(0.1)
            assert active_port.exists()
            port = active_port.read_text().splitlines()[0]
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
              window.__pnlTrace={writes:[],requests:[]};
              const originalFetch=window.fetch;
              window.fetch=function(...args){
                const url=String(args[0]);
                if(url.includes('/api/realized-pnl')) window.__pnlTrace.requests.push(url);
                return originalFetch.apply(this,args);
              };
              const descriptor=Object.getOwnPropertyDescriptor(Element.prototype,'innerHTML');
              Object.defineProperty(Element.prototype,'innerHTML',{
                get:descriptor.get,
                set(value){
                  if(this.id==='pnlBarChartWrap') window.__pnlTrace.writes.push({at:performance.now(),kind:String(value).includes('wealth-unified-chart-shell')?'unified':'legacy'});
                  return descriptor.set.call(this,value);
                }
              });
            """})
            results = []
            for width, height in [(width, height)]:
                call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
                    "screenWidth": width, "screenHeight": height, "deviceScaleFactor": 1,
                    "mobile": width <= 430})
                ready = False
                for attempt in range(2):
                    if attempt:
                        call("Page.reload", {"ignoreCache": True})
                    else:
                        call("Page.navigate", {"url": f"http://127.0.0.1:{server.server_port}/#income"})
                    for _ in range(100):
                        ready = evaluate("document.readyState==='complete' && !!window.WealthUnifiedTimeseries && typeof window.setIncomeTab==='function' && !!document.querySelector('#incomeTabs .income-tab[data-income=\"pnl\"]')")
                        if ready:
                            break
                        time.sleep(0.1)
                    if ready:
                        break
                assert ready, "Synthetic preview did not finish loading"
                time.sleep(0.3)
                row = evaluate("""(async () => {
                  const host=document.getElementById('pnlBarChartWrap');
                  const panel=document.getElementById('realizedPnlPanel');
                  const unified=window.WealthUnifiedTimeseries;
                  unified.modes.pnl=window.WealthTimeseriesPeriodCore.MODES.MONTH;
                  const sample=() => {
                    const viewport=host.querySelector('.wealth-unified-viewport');
                    const content=host.querySelector('.wealth-unified-content');
                    const buckets=host.querySelectorAll('.wealth-unified-flow-bar[data-bucket-index]');
                    const first=viewport?.clientWidth || 0;
                    const contentWidth=content?.getBoundingClientRect().width || 0;
                    const count=buckets.length;
                    const start=count ? Math.floor((viewport.scrollLeft / Math.max(1,contentWidth))*count) : 0;
                    const end=count ? Math.min(count,Math.ceil(((viewport.scrollLeft+first)/Math.max(1,contentWidth))*count)) : 0;
                    return {hidden:panel.classList.contains('wealth-income-hidden'),
                      hostWidth:host.getBoundingClientRect().width, client:first,
                      scrollWidth:viewport?.scrollWidth || 0,scrollLeft:viewport?.scrollLeft || 0,
                      inlineWidth:content?.style.width || '',contentWidth,count,
                      mode:unified.modes.pnl,first:start,last:end};
                  };
                  const hidden=sample();
                  const clickAt=performance.now();
                  document.querySelector('#incomeTabs .income-tab[data-income="pnl"]').click();
                  const frames=[sample()];
                  for(let i=0;i<6;i++){await new Promise(requestAnimationFrame);frames.push(sample());}
                  await new Promise(resolve=>setTimeout(resolve,500));
                  const settled=sample();
                  const initialTrace={writes:[...window.__pnlTrace.writes],
                    requests:[...window.__pnlTrace.requests]};
                  const modes={};
                  for(const key of ['DAY','WEEK','MONTH','YEAR','ALL']){
                    unified.modes.pnl=window.WealthTimeseriesPeriodCore.MODES[key];
                    await unified.renderPnl();
                    await new Promise(requestAnimationFrame);
                    await new Promise(requestAnimationFrame);
                    const before=sample();
                    document.querySelector('#incomeTabs .income-tab[data-income="calendar"]').click();
                    document.querySelector('#incomeTabs .income-tab[data-income="pnl"]').click();
                    await new Promise(requestAnimationFrame);
                    await new Promise(requestAnimationFrame);
                    modes[key]={before,after:sample()};
                  }
                  unified.modes.pnl=window.WealthTimeseriesPeriodCore.MODES.MONTH;
                  await unified.renderPnl();
                  const bars=host.querySelectorAll('.wealth-unified-flow-bar[data-bucket-index]');
                  bars[bars.length-1]?.dispatchEvent(new MouseEvent('click',{bubbles:true}));
                  document.querySelector('#incomeTabs .income-tab[data-income="calendar"]').click();
                  const dividendHost=document.getElementById('dividendBarChartWrap');
                  const dividendViewport=dividendHost.querySelector('.wealth-unified-viewport');
                  const dividendHidden={client:dividendViewport?.clientWidth || 0,
                    inlineWidth:dividendHost.querySelector('.wealth-unified-content')?.style.width || ''};
                  document.querySelector('#incomeTabs .income-tab[data-income="dividend"]').click();
                  const dividendFrames=[];
                  for(let i=0;i<4;i++){
                    await new Promise(requestAnimationFrame);
                    const viewport=dividendHost.querySelector('.wealth-unified-viewport');
                    const content=dividendHost.querySelector('.wealth-unified-content');
                    dividendFrames.push({client:viewport?.clientWidth || 0,
                      width:content?.getBoundingClientRect().width || 0,
                      scrollLeft:viewport?.scrollLeft || 0,
                      scrollWidth:viewport?.scrollWidth || 0});
                  }
                  currentOwner='synthetic-slow';
                  const slow=unified.renderPnl();
                  currentOwner='synthetic-fast';
                  const fast=unified.renderPnl();
                  await Promise.all([slow,fast]);
                  const raceLabel=host.querySelector('svg text[y="280"]')?.textContent || '';
                  return {hidden,clickAt,frames,settled,modes,clickedMonth:selectedPnlMonth,
                    dividendHidden,dividendFrames,raceLabel,initialTrace,trace:window.__pnlTrace};
                })()""")
                results.append({"width": width, **row})
            print("PNL_FIRST_FRAME=" + json.dumps(results, ensure_ascii=False))
            for row in results:
                assert row["hidden"]["hidden"]
                assert row["hidden"]["client"] == 0
                # rAF runs before ResizeObserver/layout/paint. The second rAF observes
                # the first frame that Chrome has actually presented.
                first = row["frames"][2]
                assert not first["hidden"]
                settled = row["settled"]
                assert first["mode"] == settled["mode"]
                assert (first["contentWidth"], first["scrollWidth"], first["scrollLeft"], first["first"], first["last"]) == (
                    settled["contentWidth"], settled["scrollWidth"], settled["scrollLeft"], settled["first"], settled["last"]), row
                for key, pair in row["modes"].items():
                    before, after = pair["before"], pair["after"]
                    assert before["mode"] == after["mode"]
                    assert (before["contentWidth"], before["scrollLeft"], before["first"], before["last"]) == (
                        after["contentWidth"], after["scrollLeft"], after["first"], after["last"]), (row["width"], key, pair)
                assert row["clickedMonth"] == 12, row
                assert not any(write["kind"] == "legacy" and write["at"] >= row["clickAt"]
                               for write in row["initialTrace"]["writes"]), row
                dividend = row["dividendFrames"]
                assert row["dividendHidden"]["client"] == 0, row
                assert dividend[1] == dividend[-1] and dividend[1]["scrollWidth"] > dividend[1]["client"], row
                assert "2026" in row["raceLabel"], row
    finally:
        if connection:
            connection.close()
        server.shutdown()
        server.server_close()
