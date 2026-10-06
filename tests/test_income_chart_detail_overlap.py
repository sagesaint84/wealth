"""Chrome geometry regression for unified income charts and detail headings."""

import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests.test_realized_pnl_viewport import StaticPreview, _chrome_path


VIEWPORTS = [(320, 568), (360, 800), (390, 844), (430, 932), (768, 1024), (1024, 768)]
MODES = ("DAY", "WEEK", "MONTH", "YEAR", "ALL")
RECORDS = [
    {"date": "2025-12-30", "owner": "모두", "broker": "가상증권", "name": "가상종목", "code": "SYN", "pnl_krw": 12345, "amount_krw": 3456},
    {"date": "2026-10-01", "owner": "모두", "broker": "가상증권", "name": "가상종목", "code": "SYN", "pnl_krw": 23456, "amount_krw": 4567},
]


class IncomePreview(StaticPreview):
    empty_chart = False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/realized-pnl":
            self.send({"records": [] if type(self).empty_chart else RECORDS, "monthly": [], "available_years": [2025, 2026]})
            return
        if path == "/api/actual-dividends":
            self.send({"records": [] if type(self).empty_chart else RECORDS, "interest_records": [], "monthly": [], "available_years": [2025, 2026]})
            return
        super().do_GET()


def test_income_chart_labels_do_not_overlap_detail_headers():
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
            profile = cleanup.enter_context(tempfile.TemporaryDirectory(prefix="wealth-income-overlap-"))
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
            assert active_port.exists(), "Chrome DevTools port did not start"
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

            call("Page.enable")
            call("Runtime.enable")
            call("Page.navigate", {"url": f"http://127.0.0.1:{server.server_port}/#pnl"})
            for _ in range(100):
                ready = call("Runtime.evaluate", {"expression": "document.readyState === 'complete' && !!window.WealthUnifiedTimeseries && typeof renderPnlMonthlyDetail === 'function'", "returnByValue": True})
                if ready.get("result", {}).get("value"):
                    break
                time.sleep(0.1)
            assert ready.get("result", {}).get("value"), "Synthetic unified charts did not load"
            measurements = []
            for width, height in VIEWPORTS:
                call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
                    "screenWidth": width, "screenHeight": height, "deviceScaleFactor": 1,
                    "mobile": width <= 430})
                for mode in MODES:
                    for has_detail in (False, True):
                        expression = """(async () => {
                          const modeKey = %s;
                          const mode = window.WealthTimeseriesPeriodCore.MODES[modeKey];
                          const records = %s;
                          pnlData = {records: %s};
                          actualDividendData = {records: %s};
                          selectedPnlYear = 2026;
                          selectedDividendYear = 2026;
                          renderPnlMonthlyDetail(10);
                          renderActualDividendDetail(10);
                          const unified = window.WealthUnifiedTimeseries;
                          unified.modes.pnl = mode;
                          unified.modes.dividend = mode;
                          const rect = el => {
                            if (!el) return null;
                            const r=el.getBoundingClientRect();
                            return {top:Math.round(r.top*10)/10,bottom:Math.round(r.bottom*10)/10,
                              left:Math.round(r.left*10)/10,right:Math.round(r.right*10)/10};
                          };
                          const chart = (hostId, detailId) => {
                            const host=document.getElementById(hostId);
                            const shell=host.querySelector('.wealth-unified-chart-shell');
                            const viewport=host.querySelector('.wealth-unified-viewport');
                            const content=host.querySelector('.wealth-unified-content');
                            const svg=host.querySelector('svg.wealth-unified-chart');
                            const labels=[...svg.querySelectorAll('text[y="262"],text[y="280"]')]
                              .filter(label=>label.textContent.trim());
                            const labelEdge = label => {
                              const point=svg.createSVGPoint();
                              point.x=Number(label.getAttribute('x'));
                              point.y=Number(label.getAttribute('y'));
                              const baseline=point.matrixTransform(label.getScreenCTM()).y;
                              const fontSize=parseFloat(label.getAttribute('font-size')) || 10;
                              const canvas=document.createElement('canvas');
                              const ctx=canvas.getContext('2d');
                              ctx.font=getComputedStyle(label).font;
                              const descent=ctx.measureText(label.textContent).actualBoundingBoxDescent || fontSize*0.25;
                              return baseline + descent*(svg.getBoundingClientRect().height/292);
                            };
                            const detail=document.getElementById(detailId);
                            return {host:rect(host),shell:rect(shell),viewport:rect(viewport),
                              content:rect(content),svg:rect(svg),detail:rect(detail),
                              header:rect(detail.querySelector('.div-detail-header')),
                              labelBottom:Math.max(...labels.map(labelEdge)),
                              labels:labels.length};
                          };
                          window.setIncomeTab?.('pnl', {updateHash:false,loadContent:false});
                          await unified.renderPnl();
                          const pnlChart=chart('pnlBarChartWrap','pnlMonthlyDetail');
                          window.setIncomeTab?.('dividend', {updateHash:false,loadContent:false});
                          await unified.renderDividend();
                          const dividendChart=chart('dividendBarChartWrap','dividendMonthlyDetail');
                          window.setIncomeTab?.('pnl', {updateHash:false,loadContent:false});
                          const wrapper=document.getElementById('tossWtsTableWrap');
                          const switcher=document.querySelector('#realizedPnlPanel .broker-feed-switcher');
                          return {width:innerWidth,doc:document.documentElement.scrollWidth,
                            body:document.body.scrollWidth,
                            wrapperClient:wrapper.clientWidth,wrapperScroll:wrapper.scrollWidth,
                            switcherClient:switcher.clientWidth,switcherScroll:switcher.scrollWidth,
                            pnl:pnlChart,dividend:dividendChart};
                        })()""" % (json.dumps(mode), json.dumps(RECORDS), "records" if has_detail else "[]", "records" if has_detail else "[]")
                        result = call("Runtime.evaluate", {"expression": expression,
                            "returnByValue": True, "awaitPromise": True})
                        assert "exceptionDetails" not in result, result
                        measurements.append({"requested": width, "mode": mode, "data": has_detail,
                                             **result["result"]["value"]})
            print("OVERLAP_SUMMARY=" + json.dumps([
                {"width": width, "pnl": row["pnl"], "dividend": row["dividend"],
                 "doc": row["doc"], "wrapper": [row["wrapperClient"], row["wrapperScroll"]]}
                for width in (320, 360, 390, 430, 768, 1024)
                for row in [next(item for item in measurements
                    if item["requested"] == width and item["mode"] == "MONTH" and item["data"])]
            ], ensure_ascii=False))
            for row in measurements:
                assert row["doc"] <= row["requested"] and row["body"] <= row["requested"], row
                assert row["switcherScroll"] <= row["switcherClient"], row
                assert row["wrapperClient"] <= row["requested"], row
                if row["requested"] <= 768:
                    assert row["wrapperScroll"] > row["wrapperClient"], row
                for kind in ("pnl", "dividend"):
                    chart = row[kind]
                    assert chart["labels"] > 0, row
                    visual_bottom = max(chart["svg"]["bottom"], chart["labelBottom"], chart["viewport"]["bottom"])
                    assert visual_bottom <= chart["header"]["top"], row
            IncomePreview.empty_chart = True
            for width, height in VIEWPORTS:
                call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
                    "screenWidth": width, "screenHeight": height, "deviceScaleFactor": 1,
                    "mobile": width <= 430})
                expression = """(async () => {
                  currentOwner = 'synthetic-empty';
                  pnlData = {records: []}; actualDividendData = {records: []};
                  renderPnlMonthlyDetail(10); renderActualDividendDetail(10);
                  const unified = window.WealthUnifiedTimeseries;
                  await unified.renderPnl(); await unified.renderDividend();
                  const result = {};
                  for (const [kind, hostId, detailId] of [
                    ['pnl', 'pnlBarChartWrap', 'pnlMonthlyDetail'],
                    ['dividend', 'dividendBarChartWrap', 'dividendMonthlyDetail']]) {
                    const host = document.getElementById(hostId);
                    const empty = host.querySelector('.wealth-unified-empty');
                    const detail = document.getElementById(detailId);
                    result[kind] = {empty: !!empty,
                      hostBottom: host.getBoundingClientRect().bottom,
                      detailTop: detail.querySelector('.div-detail-header').getBoundingClientRect().top};
                  }
                  return result;
                })()"""
                result = call("Runtime.evaluate", {"expression": expression,
                    "returnByValue": True, "awaitPromise": True})
                assert "exceptionDetails" not in result, result
                for chart in result["result"]["value"].values():
                    assert chart["empty"] and chart["hostBottom"] <= chart["detailTop"], (width, chart)
    finally:
        IncomePreview.empty_chart = False
        if connection:
            connection.close()
        server.shutdown()
        server.server_close()
