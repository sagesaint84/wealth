"""Real Chrome viewport check using the read-only synthetic UI preview."""

import json
import os
import shutil
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

from tests.ui_preview import PreviewHandler, STATIC


VIEWPORTS = [(320, 568), (360, 800), (390, 844), (430, 932),
             (768, 1024), (1024, 768), (1440, 900), (2560, 1440)]


def _chrome_path():
    for name in ("chrome", "chromium", "chromium-browser", "msedge"):
        path = shutil.which(name)
        if path:
            return path
    for path in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if Path(path).exists():
            return path
    return None


class StaticPreview(PreviewHandler):
    """Use the existing synthetic API responses and serve only repo static assets."""

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/static/"):
            name = path.removeprefix("/static/")
            target = STATIC / name
            if name == target.name and target.is_file():
                kind = "text/css" if name.endswith(".css") else "text/javascript" if name.endswith(".js") else "application/octet-stream"
                self.send(target.read_bytes(), kind)
                return
        super().do_GET()


def test_realized_pnl_page_stays_within_eight_viewports():
    websocket = pytest.importorskip("websocket")
    chrome = _chrome_path()
    if chrome is None:
        pytest.skip("Chromium browser unavailable")
    server = ThreadingHTTPServer(("127.0.0.1", 0), StaticPreview)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    process = None
    connection = None
    try:
        with ExitStack() as cleanup:
            profile = cleanup.enter_context(tempfile.TemporaryDirectory(prefix="wealth-viewport-"))
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
                ready = call("Runtime.evaluate", {"expression": "document.readyState === 'complete' && !!document.querySelector('.wealth-workspace')", "returnByValue": True})
                if ready.get("result", {}).get("value"):
                    break
                time.sleep(0.1)
            assert ready.get("result", {}).get("value"), "Synthetic preview did not load"
            measurements = []
            for width, height in VIEWPORTS:
                call("Emulation.setDeviceMetricsOverride", {
                    "width": width, "height": height, "deviceScaleFactor": 1,
                    "screenWidth": width, "screenHeight": height,
                    "mobile": width <= 430,
                })
                measured = call("Runtime.evaluate", {"returnByValue": True, "expression": """(() => {
                  window.setIncomeTab?.('pnl', {updateHash:false, loadContent:false});
                  const panel = document.getElementById('realizedPnlPanel');
                  const wrapper = document.getElementById('tossWtsTableWrap');
                  const table = document.getElementById('tossWtsTable');
                  const switcher = panel.querySelector('.broker-feed-switcher');
                  const metrics = el => el && ({left:Math.round(el.getBoundingClientRect().left),
                    right:Math.round(el.getBoundingClientRect().right),
                    client:el.clientWidth, scroll:el.scrollWidth});
                  const widest = [...document.querySelectorAll('*')]
                    .filter(el => el.getClientRects().length && el.getBoundingClientRect().right > innerWidth + 1)
                    .sort((a,b)=>b.getBoundingClientRect().right-a.getBoundingClientRect().right)
                    .slice(0,5).map(el=>({tag:el.tagName,id:el.id,className:String(el.className).slice(0,80),right:Math.round(el.getBoundingClientRect().right)}));
                  return {viewport:innerWidth, visual:Math.round(visualViewport.width), doc:document.documentElement.scrollWidth,
                    body:document.body.scrollWidth, panel:metrics(panel), wrapper:metrics(wrapper),
                    table:metrics(table), switcher:metrics(switcher),
                    panelDisplay:getComputedStyle(panel).display, widest};
                })()"""})["result"]["value"]
                measurements.append(measured)
            print("WIDTH_METRICS=" + json.dumps([
                {"requested": width, "inner": row["viewport"], "visual": row["visual"],
                 "doc": row["doc"], "body": row["body"], "panel": row["panel"],
                 "wrapper": row["wrapper"], "table": row["table"], "switcher": row["switcher"],
                 "widest": row["widest"]}
                for (width, _), row in zip(VIEWPORTS, measurements)
            ], ensure_ascii=False))
            assert all(row["panelDisplay"] != "none" for row in measurements), measurements
            assert all(row["doc"] <= width and row["body"] <= width
                       for row, (width, _) in zip(measurements, VIEWPORTS)), measurements
            assert all(row["switcher"]["scroll"] <= row["switcher"]["client"] for row in measurements)
            assert measurements[0]["table"]["scroll"] > measurements[0]["wrapper"]["client"]
            assert all(row["wrapper"]["scroll"] <= row["wrapper"]["client"]
                       for row, (width, _) in zip(measurements, VIEWPORTS) if width >= 1024)
    finally:
        if connection:
            connection.close()
        server.shutdown()
        server.server_close()
