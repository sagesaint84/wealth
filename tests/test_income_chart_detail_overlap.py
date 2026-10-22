"""Chrome geometry regression for unified income charts and detail headings."""

import json
import re
import sys
import threading
import time
import urllib.request
from contextlib import ExitStack
from collections import deque
from urllib.parse import urlsplit

import pytest

from tests.chrome_harness import chrome_session, safe_preview_server

from tests.test_realized_pnl_viewport import StaticPreview, StaticPreviewServer, _chrome_path


VIEWPORTS = [(320, 568), (360, 800), (390, 844), (430, 932), (768, 1024), (1024, 768), (1280, 900)]
MODES = ("DAY", "WEEK", "MONTH", "YEAR", "ALL")
RECORDS = [
    {"date": "2025-12-30", "owner": "모두", "broker": "가상증권", "name": "가상종목", "code": "SYN", "pnl_krw": 12345, "amount_krw": 3456},
    {"date": "2026-10-01", "owner": "모두", "broker": "가상증권", "name": "가상종목", "code": "SYN", "pnl_krw": 23456, "amount_krw": 4567},
]


class IncomePreview(StaticPreview):
    empty_chart = False

    def send_response(self, code, message=None):
        if getattr(self, "_auth_transport_id", None) is not None:
            self._auth_transport_status = code
        return super().send_response(code, message)

    def do_GET(self):
        path = urlsplit(self.path).path
        record = getattr(self.server, "record_transport", None)
        if path == "/api/auth/me" and record is not None:
            self._auth_transport_id = record("AUTH_HANDLER_START", path=path)
            self._auth_transport_status = "UNAVAILABLE"
            try:
                return super().do_GET()
            except BaseException as error:
                record("AUTH_HANDLER_EXCEPTION", path=path,
                       handlerId=self._auth_transport_id, errorType=type(error).__name__)
                raise
            finally:
                record("AUTH_HANDLER_END", path=path, handlerId=self._auth_transport_id,
                       status=self._auth_transport_status)
        if path == "/api/realized-pnl":
            self.send({"records": [] if type(self).empty_chart else RECORDS, "monthly": [], "available_years": [2025, 2026]})
            return
        if path == "/api/actual-dividends":
            self.send({"records": [] if type(self).empty_chart else RECORDS, "interest_records": [], "monthly": [], "available_years": [2025, 2026]})
            return
        super().do_GET()



def income_preview_server():
    # The stdlib backlog of five rejects a static connection burst on Windows
    # before HTTP handlers run. Use the same capacity as the other UI previews.
    return safe_preview_server(StaticPreviewServer, IncomePreview)


def test_income_preview_accepts_static_connection_burst():
    import socket
    from concurrent.futures import ThreadPoolExecutor
    server = income_preview_server()
    clients = []
    try:
        # Fill the actual pending queue before accepting. No sleep or retry:
        # changing the factory back to the default backlog must fail here.
        with ThreadPoolExecutor(max_workers=24) as pool:
            def connect(_):
                try:
                    return socket.create_connection(server.server_address, timeout=3)
                except OSError as error:
                    return error
            results = list(pool.map(connect, range(24)))
        clients = [result for result in results if isinstance(result, socket.socket)]
        assert len(clients) == 24, [type(result).__name__ for result in results]
        server.socket.settimeout(3)
        for _ in clients:
            connection, _ = server.get_request()
            connection.close()
    finally:
        for client in clients:
            client.close()
        server.server_close()

def test_income_chart_labels_do_not_overlap_detail_headers():
    websocket = pytest.importorskip("websocket")
    chrome = _chrome_path()
    if chrome is None:
        pytest.skip("Chromium browser unavailable")
    server = income_preview_server()
    transport_events = deque(maxlen=96)
    transport_lock = threading.Lock()
    transport_sequence = 0

    def record_transport(event, **values):
        nonlocal transport_sequence
        # Collection times share Python's monotonic clock, never CDP timestamps.
        with transport_lock:
            transport_sequence += 1
            transport_events.append({"sequence": transport_sequence,
                "collectedAt": time.monotonic(), "event": event, **values})
            return transport_sequence

    server.record_transport = record_transport
    original_handle_error = server.handle_error

    def observe_handler_error(request, client_address):
        error_type = sys.exc_info()[0]
        record_transport("SERVER_HANDLER_EXCEPTION",
                         errorType=error_type.__name__ if error_type else "UNAVAILABLE")
        return original_handle_error(request, client_address)

    server.handle_error = observe_handler_error

    def serve_with_diagnostics():
        record_transport("SERVER_THREAD_START")
        try:
            return server.serve_forever()
        except BaseException as error:
            record_transport("SERVER_THREAD_EXCEPTION", errorType=type(error).__name__)
            raise
        finally:
            record_transport("SERVER_THREAD_EXIT")

    thread = threading.Thread(target=serve_with_diagnostics, daemon=True)

    def server_state():
        # Inspect the existing listener only; no connection/probe is made.
        listener = getattr(server, "socket", None)
        try:
            listener_open = listener is not None and listener.fileno() >= 0
        except OSError:
            listener_open = "UNAVAILABLE"
        return {"collectedAt": time.monotonic(), "binding": list(server.server_address),
                "requestQueueSize": server.request_queue_size, "threadAlive": thread.is_alive(),
                "listenerExists": listener is not None, "listenerOpen": listener_open}

    thread.start()
    connection = None
    try:
        with ExitStack() as cleanup:
            process, port, profile = cleanup.enter_context(chrome_session(chrome, "wealth-income-overlap-"))
            targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5))
            target = next(item for item in targets if item.get("type") == "page")
            connection = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=15)
            request_id = 0
            boot_events = {"network": {}, "errors": [], "lifecycle": [], "context": [], "dropped": 0}

            def safe_text(value):
                # Only synthetic browser errors; strip URL queries/fragments too.
                return re.sub(r"https?://[^\s)]+", lambda match: urlsplit(match.group()).path,
                              str(value))[:3000]

            def observe_boot_event(message):
                method = message.get("method", "")
                params = message.get("params", {})
                if method == "Network.requestWillBeSent":
                    path = urlsplit(params.get("request", {}).get("url", "")).path
                    if not (path.startswith("/static/") or path.startswith("/api/")):
                        return
                    requests = boot_events["network"]
                    if len(requests) >= 300:
                        del requests[next(iter(requests))]
                        boot_events["dropped"] += 1
                    requests[params["requestId"]] = {"path": path, "loaderId": params.get("loaderId"),
                        "frameId": params.get("frameId"), "status": "UNAVAILABLE"}
                    if path == "/api/auth/me":
                        record_transport("CDP_AUTH_REQUEST", requestId=params["requestId"],
                                         path=path, server=server_state())
                elif method in ("Network.responseReceived", "Network.loadingFailed"):
                    item = boot_events["network"].get(params.get("requestId"))
                    if item is not None:
                        if method == "Network.responseReceived":
                            item["status"] = params.get("response", {}).get("status", "UNAVAILABLE")
                        else:
                            item["loadingFailed"] = safe_text(params.get("errorText", "UNAVAILABLE"))
                            item["canceled"] = params.get("canceled", False)
                        if item["path"] == "/api/auth/me":
                            record_transport("CDP_AUTH_RESPONSE" if method == "Network.responseReceived"
                                             else "CDP_AUTH_FAILED", requestId=params.get("requestId"),
                                             path=item["path"], status=item["status"],
                                             errorType=item.get("loadingFailed", "NONE"), server=server_state())
                elif method == "Runtime.exceptionThrown":
                    detail = params.get("exceptionDetails", {})
                    boot_events["errors"].append({"type": method, "contextId": detail.get("executionContextId"),
                        "text": safe_text(detail.get("exception", {}).get("description", detail.get("text", "UNAVAILABLE")))})
                elif method == "Log.entryAdded" and params.get("entry", {}).get("level") in ("error", "warning"):
                    entry = params["entry"]
                    boot_events["errors"].append({"type": method, "source": entry.get("source"),
                        "level": entry.get("level"), "text": safe_text(entry.get("text", ""))})
                elif method in ("Page.domContentEventFired", "Page.loadEventFired"):
                    boot_events["lifecycle"].append({"type": method, "timestamp": params.get("timestamp")})
                elif method in ("Runtime.executionContextDestroyed", "Runtime.executionContextsCleared"):
                    boot_events["context"].append({"type": method, "contextId": params.get("executionContextId", "UNAVAILABLE")})
                for key in ("errors", "lifecycle", "context"):
                    del boot_events[key][:-40]

            def call(method, params=None):
                nonlocal request_id
                request_id += 1
                connection.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
                while True:
                    response = json.loads(connection.recv())
                    if response.get("id") == request_id:
                        assert "error" not in response, response
                        return response["result"]
                    observe_boot_event(response)

            def print_evaluation_failure(result):
                if "exceptionDetails" not in result:
                    return
                details = result["exceptionDetails"]
                description = details.get("exception", {}).get("description")
                print("V213_OVERLAP_EXCEPTION=" + (
                    description or json.dumps(details, ensure_ascii=False)), flush=True)
                diagnostic = call("Runtime.evaluate", {
                    "expression": "JSON.stringify(window.__v213OverlapReadyDiagnostic ?? 'UNAVAILABLE')",
                    "returnByValue": True,
                })
                serialized = diagnostic.get("result", {}).get("value")
                print("V213_OVERLAP_READY_DIAG=" + (
                    serialized if isinstance(serialized, str) else json.dumps(
                        {"diagnostic": "UNAVAILABLE", "cdp": diagnostic}, ensure_ascii=False)), flush=True)
                trace = call("Runtime.evaluate", {
                    "expression": "JSON.stringify(window.__v213RouteTrace ? {events:window.__v213RouteTrace.events, dropped:window.__v213RouteTrace.dropped, summary:window.__v213RouteTrace.summary} : 'UNAVAILABLE')",
                    "returnByValue": True,
                })
                print("V213_ROUTE_EVENT_TRACE=" + trace.get("result", {}).get(
                    "value", '"UNAVAILABLE"'), flush=True)

            call("Page.enable")
            call("Runtime.enable")
            call("Network.enable")
            call("Log.enable")
            call("Page.addScriptToEvaluateOnNewDocument", {"source": r"""
              (() => {
                const limit = 1000;
                const read = getter => {try {return getter() ?? 'UNAVAILABLE';} catch {return 'UNAVAILABLE';}};
                const trace = window.__v213RouteTrace = {
                  events:[], dropped:0, context:null,
                  summary:{dividendClicks:0,toDividend:0,toPnl:0,
                    unexpectedHashTransition:false,activeTabHashMismatch:false},
                };
                trace.record = (type, extra = {}) => {
                  // Diagnostics must never interrupt the observed application.
                  try {
                    const hash = location.hash;
                    const tab = read(() => currentIncomeTab);
                    const event = {time:performance.now(),type,
                      targetIncomeTab:extra.targetIncomeTab ?? trace.context?.kind ?? 'UNAVAILABLE',
                      hashBefore:hash,hashAfter:hash,currentIncomeTab:tab,
                      activeIncomeButton:read(() => document.querySelector('#incomeTabs .income-tab.active')?.dataset.income),
                      selectionToken:read(() => window.setIncomeTab?.pendingIncomeTabSelection),
                      pendingTarget:read(() => window.setIncomeTab?.pendingTarget),
                      context:trace.context ? {...trace.context} : 'UNAVAILABLE',
                      viewport:{width:innerWidth,height:innerHeight},...extra};
                    if (type === 'CLICK_CAPTURE' && event.targetIncomeTab === 'dividend') trace.summary.dividendClicks++;
                    const completedHistory = type === 'HISTORY_REPLACE_AFTER' || type === 'HISTORY_PUSH_AFTER';
                    if (((completedHistory && event.outcome === 'RETURNED') || type === 'HASHCHANGE')
                        && event.hashBefore !== event.hashAfter) {
                      if (event.hashAfter === '#dividend') trace.summary.toDividend++;
                      if (event.hashAfter === '#pnl') trace.summary.toPnl++;
                      if (trace.context && event.hashAfter !== '#' + trace.context.kind)
                        trace.summary.unexpectedHashTransition = true;
                    }
                    if (['CLICK_BUBBLE','HISTORY_REPLACE_AFTER','HISTORY_PUSH_AFTER',
                         'HASHCHANGE','POPSTATE','ACTIVATE_READY','ACTIVATE_TIMEOUT'].includes(type)
                        && ['pnl','dividend'].includes(tab) && hash !== '#' + tab)
                      trace.summary.activeTabHashMismatch = true;
                    trace.events.push(event);
                    if (trace.events.length > limit) {trace.events.shift(); trace.dropped++;}
                  } catch { /* Observation failure must not change app behavior. */ }
                };
                for (const [method, prefix] of [['replaceState','HISTORY_REPLACE'],['pushState','HISTORY_PUSH']]) {
                  const original = history[method];
                  history[method] = function (...args) {
                    const before = location.hash;
                    trace.record(prefix + '_BEFORE', {hashBefore:before,hashAfter:before,
                      stack:read(() => new Error().stack)});
                    let outcome = 'THREW';
                    try {
                      const result = Reflect.apply(original, this, args);
                      outcome = 'RETURNED';
                      return result;
                    } finally {
                      trace.record(prefix + '_AFTER', {hashBefore:before,hashAfter:location.hash,outcome});
                    }
                  };
                }
                const observeClick = type => event => {
                  const target = event.target?.closest?.('#incomeTabs [data-income]');
                  if (!target) return;
                  trace.record(type, {targetIncomeTab:target.dataset.income,
                    target:{tag:target.tagName,id:target.id,connected:target.isConnected,disabled:!!target.disabled},
                    eventPhase:event.eventPhase,bubbles:event.bubbles,defaultPrevented:event.defaultPrevented,
                    isTrusted:event.isTrusted});
                };
                document.addEventListener('click', observeClick('CLICK_CAPTURE'), true);
                document.addEventListener('click', observeClick('CLICK_BUBBLE'), false);
                window.addEventListener('hashchange', event => trace.record('HASHCHANGE', {
                  hashBefore:read(() => new URL(event.oldURL).hash),hashAfter:read(() => new URL(event.newURL).hash)}));
                window.addEventListener('popstate', () => trace.record('POPSTATE', {hashBefore:'UNAVAILABLE'}));
              })();
            """})
            def start_viewport_document(width, phase):
                transport_started = time.monotonic()
                transport_before = server_state()
                previous_loader = call("Page.getFrameTree")["frameTree"]["frame"]["loaderId"]
                boot_events["network"].clear()
                for key in ("errors", "lifecycle", "context"):
                    boot_events[key].clear()
                boot_events["dropped"] = 0
                # A different query creates a document navigation, not a hash-only
                # route change. No app cache or History API behavior is mocked.
                navigation = call("Page.navigate", {
                    "url": f"http://127.0.0.1:{server.server_port}/?overlap_case={phase}-{width}#pnl",
                })
                assert not navigation.get("errorText"), navigation
                loader = navigation.get("loaderId")
                assert loader and loader != previous_loader, navigation
                loaded = False
                ready = None
                current_loader = "UNAVAILABLE"
                evaluate_errors = []
                for _ in range(100):
                    current_loader = call("Page.getFrameTree")["frameTree"]["frame"]["loaderId"]
                    if current_loader != loader:
                        time.sleep(0.1)
                        continue
                    ready = call("Runtime.evaluate", {"expression": "document.readyState === 'complete' && !!window.WealthUnifiedTimeseries && typeof renderPnlMonthlyDetail === 'function' && window.WealthStartup?.canRead() && !loadAssetDataForUser.pending", "returnByValue": True})
                    if "exceptionDetails" in ready:
                        detail = ready["exceptionDetails"]
                        evaluate_errors.append(safe_text(detail.get("exception", {}).get("description", detail.get("text", "UNAVAILABLE"))))
                        del evaluate_errors[:-20]
                    loaded = bool(ready.get("result", {}).get("value"))
                    if loaded:
                        break
                    time.sleep(0.1)
                failed_conditions = "UNAVAILABLE"
                if not loaded:
                    snapshot = call("Runtime.evaluate", {"expression": """JSON.stringify((() => {
                      const read = fn => {try {return fn() ?? 'UNAVAILABLE';} catch (error) {return 'UNAVAILABLE';}};
                      return {
                        hash:location.hash,origin:location.origin,readyState:document.readyState,
                        conditions:{documentComplete:document.readyState === 'complete',
                          unified:!!window.WealthUnifiedTimeseries,
                          pnlDetailFunction:typeof renderPnlMonthlyDetail === 'function',
                          startupCanRead:read(() => window.WealthStartup?.canRead()),
                          assetLoadNotPending:read(() => !loadAssetDataForUser.pending)},
                        modules:{actualDetail:typeof renderActualDividendDetail === 'function',
                          periodCore:!!window.WealthTimeseriesPeriodCore,startup:!!window.WealthStartup},
                        assetLoadPending:read(() => !!loadAssetDataForUser.pending),
                        owner:read(() => currentOwner),tab:read(() => currentIncomeTab),
                        workspace:read(() => document.querySelector('.wealth-workspace')?.dataset.activeView),
                        incomeTab:read(() => document.querySelector('.wealth-workspace')?.dataset.incomeTab),
                        pnlVisible:read(() => window.WealthStartup?.visible('pnlBarChartWrap')),
                        dividendVisible:read(() => window.WealthStartup?.visible('dividendBarChartWrap')),
                        startupState:read(() => window.WealthStartup?.snapshot()),
                        pendingReads:read(() => startupReadPending.size),
                        globalInitializationErrors:'See bounded Runtime/Log events; unreported errors UNAVAILABLE'
                      };
                    })())""", "returnByValue": True})
                    raw = snapshot.get("result", {}).get("value")
                    application = json.loads(raw) if isinstance(raw, str) else "UNAVAILABLE"
                    if isinstance(application, dict):
                        failed_conditions = application["conditions"]
                    frame = call("Page.getFrameTree")["frameTree"]["frame"]
                    diagnostic = {"document": {"width": width, "height": dict(VIEWPORTS)[width],
                        "phase": phase, "expectedHash": "#pnl", "server": f"127.0.0.1:{server.server_port}",
                        "previousLoaderId": previous_loader, "expectedLoaderId": loader,
                        "lastPolledLoaderId": current_loader, "currentLoaderId": frame.get("loaderId"),
                        "frameId": frame.get("id"), "newDocument": frame.get("loaderId") != previous_loader,
                        "loaderMatches": frame.get("loaderId") == loader, "navigation": navigation,
                        "reload": "NOT_USED", "lifecycle": boot_events["lifecycle"]},
                        "application": application, "network": list(boot_events["network"].values()),
                        "chrome": {"errors": boot_events["errors"], "contextEvents": boot_events["context"],
                            "evaluateErrors": evaluate_errors, "lastReadyResult": ready,
                            "snapshotException": safe_text(snapshot.get("exceptionDetails", "NONE"))},
                        "data": {"emptyFixture": IncomePreview.empty_chart, "syntheticOnly": True,
                            "fixtureConsumedByDocument": "UNAVAILABLE; HTTP status does not prove response consumption"},
                        "droppedNetworkEvents": boot_events["dropped"]}
                    print("V213_DOCUMENT_BOOT_DIAG=" + json.dumps(diagnostic, ensure_ascii=False), flush=True)
                    with transport_lock:
                        recent_transport = list(transport_events)
                    # Preserve document-window events plus earlier server errors.
                    selected = [event for event in recent_transport
                                if event["collectedAt"] >= transport_started
                                or event["event"].endswith("EXCEPTION")][-40:]
                    app = application if isinstance(application, dict) else {}
                    auth_diagnostic = {
                        "clock": "Python time.monotonic; CDP times are collection, not emission times",
                        "document": {"width": width, "phase": phase,
                            "readyState": app.get("readyState", "UNAVAILABLE"),
                            "hash": app.get("hash", "UNAVAILABLE"), "path": "/",
                            "startupCanRead": app.get("conditions", {}).get("startupCanRead", "UNAVAILABLE"),
                            "conditions": failed_conditions},
                        "serverBefore": transport_before, "serverAfter": server_state(),
                        "events": selected, "eventBufferLimit": 96,
                        "serverAuthStartsInWindow": sum(event["event"] == "AUTH_HANDLER_START"
                                                        for event in selected),
                        "correlation": "CDP events share requestId; server handler start/end share handlerId. "
                            "Exact server-to-CDP identity UNAVAILABLE (no request/header modification). "
                            "Compare document window and counts; collection order is not emission order.",
                        "jsErrors": [{"type": event.get("type"),
                                      "text": event.get("text", "")[:300]}
                                     for event in boot_events["errors"][-8:]],
                        "evaluateErrors": [error[:300] for error in evaluate_errors[-4:]],
                    }
                    # Fixed event/field bounds plus a hard serialized byte budget.
                    while len(json.dumps(auth_diagnostic, ensure_ascii=False).encode("utf-8")) > 24000:
                        auth_diagnostic["events"].pop(0)
                        auth_diagnostic["eventsTruncated"] = True
                    print("V213_AUTH_TRANSPORT_DIAG=" + json.dumps(auth_diagnostic, ensure_ascii=False), flush=True)
                assert loaded, ("Synthetic unified charts did not load", width, phase, failed_conditions)
                frame = call("Page.getFrameTree")["frameTree"]["frame"]
                assert frame["loaderId"] == loader, (width, phase, frame)

            route_summaries = []

            def capture_route_summary(width, phase):
                result = call("Runtime.evaluate", {
                    "expression": "JSON.stringify(window.__v213RouteTrace?.summary ?? 'UNAVAILABLE')",
                    "returnByValue": True,
                })
                route_summaries.append({"width": width, "phase": phase,
                    "summary": json.loads(result.get("result", {}).get("value", '"UNAVAILABLE"'))})
            # Share the real navigation/readiness contract between populated and
            # empty charts; module availability alone does not mean a tab rendered.
            chart_setup = """
              const unified = window.WealthUnifiedTimeseries;
              let recordReadyDiagnostic = () => {};
              const state = kind => {
                const host = document.getElementById(kind === 'pnl' ? 'pnlBarChartWrap' : 'dividendBarChartWrap');
                const workspace = document.querySelector('.wealth-workspace');
                return {hash:location.hash, tab:currentIncomeTab, owner:currentOwner,
                  workspace:workspace?.dataset.activeView, incomeTab:workspace?.dataset.incomeTab,
                  mode:currentDividendMode, pending:window.setIncomeTab.pendingTarget,
                  visible:!!host?.getClientRects().length,
                  svg:!!host?.querySelector('svg.wealth-unified-chart'),
                  empty:!!host?.querySelector('.wealth-unified-empty'),
                  detailMode:unified.getDetailMode(kind)};
              };
              const waitUntil = async (predicate, label, kind) => {
                const started = performance.now();
                const deadline = started + 10000;
                while (true) {
                  const ready = predicate();
                  recordReadyDiagnostic(label, performance.now() - started, ready);
                  if (ready) break;
                  if (performance.now() >= deadline) {
                    window.__v213RouteTrace?.record('ACTIVATE_TIMEOUT', {guard:label,
                      elapsedMs:performance.now() - started});
                    throw new Error(label + ': ' + JSON.stringify(state(kind)));
                  }
                  await new Promise(requestAnimationFrame);
                }
              };
              const activate = async (kind, mode, empty = false) => {
                unified.modes[kind] = mode;
                const owner = currentOwner;
                const expectedMode = WealthTimeseriesPeriodCore.effectiveMode(empty ? [] : records, mode, 'date');
                if (window.__v213RouteTrace) {
                  window.__v213RouteTrace.context = {kind,mode,
                    requestedMode:Object.keys(WealthTimeseriesPeriodCore.MODES)
                      .find(key => WealthTimeseriesPeriodCore.MODES[key] === mode) ?? 'UNAVAILABLE',
                    phase:empty ? 'empty' : 'records',has_detail:overlapDiagnosticContext.has_detail};
                  window.__v213RouteTrace.record('ACTIVATE_BEGIN');
                }
                const panelId = kind === 'pnl' ? 'realizedPnlPanel' : 'dividendPanel';
                const hostId = kind === 'pnl' ? 'pnlBarChartWrap' : 'dividendBarChartWrap';
                let renderAwaitCompleted = false;
                let previousSvg = null;
                recordReadyDiagnostic = (guard, elapsedMs, guardResult) => {
                  const s = state(kind);
                  const host = document.getElementById(hostId);
                  const panel = document.getElementById(panelId);
                  const viewport = host?.querySelector('.wealth-unified-viewport');
                  const svg = host?.querySelector('svg.wealth-unified-chart');
                  const emptyNode = host?.querySelector('.wealth-unified-empty');
                  const activeButton = document.querySelector('#incomeTabs .income-tab.active');
                  const svgWidth = svg?.getBoundingClientRect().width ?? null;
                  const viewportWidth = viewport?.clientWidth ?? null;
                  const startupVisible = WealthStartup.visible(hostId);
                  const booleans = {
                    ownerMatches:s.owner === owner, hashMatches:s.hash === '#' + kind,
                    tabMatches:s.tab === kind, workspaceMatches:s.workspace === 'income',
                    incomeTabMatches:s.incomeTab === kind, noPendingTab:!s.pending,
                    activeButtonMatches:activeButton?.dataset.income === kind,
                    panelVisible:!!panel?.getClientRects().length,
                    startupVisible:!!startupVisible,
                    actualMode:kind !== 'dividend' || s.mode === 'actual',
                    selectedModeMatches:unified.modes[kind] === mode,
                    effectiveModeMatches:unified.getDetailMode(kind) === expectedMode,
                    noPendingReads:startupReadPending.size === 0,
                    emptyExists:!!emptyNode, svgAbsent:!svg, svgExists:!!svg,
                    svgPositiveWidth:!!svg && svgWidth > 0,
                    viewportPositiveWidth:!!viewport && viewportWidth > 0,
                  };
                  booleans.routeReady = ['ownerMatches','hashMatches','tabMatches','workspaceMatches',
                    'incomeTabMatches','noPendingTab','activeButtonMatches','panelVisible',
                    'startupVisible','actualMode'].every(key => booleans[key]);
                  booleans.dataDomReady = empty ? booleans.emptyExists && booleans.svgAbsent
                    : booleans.svgExists && booleans.svgPositiveWidth && booleans.viewportPositiveWidth;
                  booleans.chartReady = booleans.routeReady && booleans.selectedModeMatches
                    && booleans.effectiveModeMatches && booleans.noPendingReads && booleans.dataDomReady;
                  const source = empty ? [] : records;
                  const fields = kind === 'pnl' ? ['pnl_value'] : ['dividend_value','interest_value'];
                  const rows = source.map(row => ({...row, pnl_value:Number(row.pnl_krw),
                    dividend_value:Number(row.amount_krw), interest_value:0}));
                  const expectedBuckets = WealthTimeseriesPeriodCore.aggregateFlow(rows, mode, {fields}).buckets;
                  const expectedKeys = expectedBuckets.map(bucket => bucket.key);
                  const actualKeys = [...new Set([...host.querySelectorAll('.wealth-unified-flow-bar')]
                    .map(node => node.dataset.bucketKey))];
                  window.__v213OverlapReadyDiagnostic = {
                    context:{width:innerWidth,height:innerHeight,kind,
                      requestedMode:Object.keys(WealthTimeseriesPeriodCore.MODES)
                        .find(key => WealthTimeseriesPeriodCore.MODES[key] === mode) ?? 'UNAVAILABLE',
                      has_detail:overlapDiagnosticContext.has_detail,
                      phase:empty ? 'empty' : 'records',guard,elapsedMs,guardResult},
                    route:{expectedHash:'#' + kind,actualHash:s.hash,tab:s.tab,
                      workspace:s.workspace ?? 'UNAVAILABLE',incomeTab:s.incomeTab ?? 'UNAVAILABLE',
                      activeButton:activeButton?.dataset.income ?? 'UNAVAILABLE',panelId,pending:s.pending ?? null},
                    owner:{expected:owner,actual:s.owner,matches:booleans.ownerMatches},
                    period:{expectedMode:mode,actualMode:unified.modes[kind],
                      expectedEffectiveMode:expectedMode,detailMode:s.detailMode,dividendMode:s.mode},
                    startup:{pendingCount:startupReadPending.size,visible:startupVisible,
                      renderAwaitCompleted,internalRenderGeneration:'UNAVAILABLE',
                      unifiedState:host.dataset.unifiedState ?? 'UNAVAILABLE'},
                    dom:{svg:!!svg,svgWidth,viewport:!!viewport,viewportWidth,
                      empty:!!emptyNode,header:!!document.querySelector(
                        '#' + (kind === 'pnl' ? 'pnlMonthlyDetail' : 'dividendMonthlyDetail') + ' .div-detail-header'),
                      belongsToPanel:!!panel?.contains(host),hostConnected:host.isConnected,
                      svgChangedSincePreviousCheck:previousSvg === null ? 'UNAVAILABLE' : previousSvg !== svg},
                    data:{recordIds:source.map(row => row.id ?? 'UNAVAILABLE'),
                      sourceDates:source.map(row => row.date),expectedBucketKeys:expectedKeys,actualBucketKeys:actualKeys,
                      bucketKeysMatch:JSON.stringify(expectedKeys) === JSON.stringify(actualKeys),
                      fullValueAndSourceProvenanceMatch:'UNAVAILABLE',
                      pnlYear:selectedPnlYear,dividendYear:selectedDividendYear,
                      broker:document.getElementById(kind === 'pnl' ? 'pnlBrokerFilter' : 'dividendBrokerFilter')?.value ?? 'UNAVAILABLE',
                      dividendScope:kind === 'dividend' ? unified.dividendScopeKey() : 'UNAVAILABLE'},
                    conditions:booleans,
                  };
                  previousSvg = svg;
                };
                const routeReady = () => {
                  const s = state(kind);
                  return s.owner === owner && s.hash === '#' + kind && s.tab === kind && s.workspace === 'income'
                    && s.incomeTab === kind && !s.pending
                    && document.querySelector('#incomeTabs .income-tab.active')?.dataset.income === kind
                    && !!document.getElementById(panelId).getClientRects().length
                    && WealthStartup.visible(hostId)
                    && (kind !== 'dividend' || s.mode === 'actual');
                };
                if (!routeReady())
                  document.querySelector('#incomeTabs [data-income="' + kind + '"]').click();
                await waitUntil(routeReady, kind + ' active route', kind);
                // Navigation can schedule its renderer; wait for outstanding reads
                // before explicitly rendering the selected aggregation mode.
                await waitUntil(() => startupReadPending.size === 0, kind + ' reads', kind);
                await (kind === 'pnl' ? unified.renderPnl() : unified.renderDividend());
                renderAwaitCompleted = true;
                await waitUntil(() => {
                  const host = document.getElementById(hostId);
                  const svg = host.querySelector('svg.wealth-unified-chart');
                  const viewport = host.querySelector('.wealth-unified-viewport');
                  return routeReady() && unified.modes[kind] === mode
                    && unified.getDetailMode(kind) === expectedMode && startupReadPending.size === 0
                    && (empty ? !!host.querySelector('.wealth-unified-empty') && !svg
                      : !!svg && svg.getBoundingClientRect().width > 0 && viewport?.clientWidth > 0);
                }, kind + (empty ? ' empty state' : ' SVG'), kind);
                window.__v213RouteTrace?.record('ACTIVATE_READY');
              };
            """
            measurements = []
            for width, height in VIEWPORTS:
                call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height,
                    "screenWidth": width, "screenHeight": height, "deviceScaleFactor": 1,
                    "mobile": width <= 430})
                start_viewport_document(width, "records")
                for mode in MODES:
                    for has_detail in (False, True):
                        expression = """(async () => {
                          %s
                          const modeKey = %s;
                          const mode = window.WealthTimeseriesPeriodCore.MODES[modeKey];
                          const records = %s;
                          const overlapDiagnosticContext = {has_detail: %s};
                          selectedPnlYear = '2026';
                          selectedDividendYear = '2026';
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
                            if (!shell || !viewport || !content || !svg)
                              throw new Error('Missing active chart DOM ' + hostId + ': '
                                + JSON.stringify(state(hostId === 'pnlBarChartWrap' ? 'pnl' : 'dividend')));
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
                          await activate('pnl', mode);
                          pnlData = {records: %s};
                          renderPnlMonthlyDetail(10);
                          const pnlChart=chart('pnlBarChartWrap','pnlMonthlyDetail');
                          await activate('dividend', mode);
                          actualDividendData = {records: %s};
                          renderActualDividendDetail(10);
                          const dividendChart=chart('dividendBarChartWrap','dividendMonthlyDetail');
                          await activate('pnl', mode);
                          const wrapper=document.getElementById('tossWtsTableWrap');
                          const switcher=document.querySelector('#realizedPnlPanel .broker-feed-switcher');
                          return {width:innerWidth,doc:document.documentElement.scrollWidth,
                            body:document.body.scrollWidth,
                            wrapperClient:wrapper.clientWidth,wrapperScroll:wrapper.scrollWidth,
                            switcherClient:switcher.clientWidth,switcherScroll:switcher.scrollWidth,
                            pnl:pnlChart,dividend:dividendChart};
                        })()""" % (chart_setup, json.dumps(mode), json.dumps(RECORDS), json.dumps(has_detail), "records" if has_detail else "[]", "records" if has_detail else "[]")
                        result = call("Runtime.evaluate", {"expression": expression,
                            "returnByValue": True, "awaitPromise": True})
                        print_evaluation_failure(result)
                        assert "exceptionDetails" not in result, result
                        measurements.append({"requested": width, "mode": mode, "data": has_detail,
                                             **result["result"]["value"]})
                capture_route_summary(width, "records")
            print("OVERLAP_SUMMARY=" + json.dumps([
                {"width": width, "pnl": row["pnl"], "dividend": row["dividend"],
                 "doc": row["doc"], "wrapper": [row["wrapperClient"], row["wrapperScroll"]]}
                for width in (320, 360, 390, 430, 768, 1024, 1280)
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
                start_viewport_document(width, "empty")
                expression = """(async () => {
                  %s
                  const overlapDiagnosticContext = {has_detail:false};
                  currentOwner = 'synthetic-empty-' + innerWidth;
                  selectedPnlYear = '2026'; selectedDividendYear = '2026';
                  const result = {};
                  for (const [kind, hostId, detailId] of [
                    ['pnl', 'pnlBarChartWrap', 'pnlMonthlyDetail'],
                    ['dividend', 'dividendBarChartWrap', 'dividendMonthlyDetail']]) {
                    await activate(kind, window.WealthTimeseriesPeriodCore.MODES.MONTH, true);
                    if (kind === 'pnl') {
                      pnlData = {records: []}; renderPnlMonthlyDetail(10);
                    } else {
                      actualDividendData = {records: []}; renderActualDividendDetail(10);
                    }
                    const host = document.getElementById(hostId);
                    const empty = host.querySelector('.wealth-unified-empty');
                    const detail = document.getElementById(detailId);
                    result[kind] = {empty: !!empty,
                      hostBottom: host.getBoundingClientRect().bottom,
                      detailTop: detail.querySelector('.div-detail-header').getBoundingClientRect().top};
                  }
                  return result;
                })()""" % chart_setup
                result = call("Runtime.evaluate", {"expression": expression,
                    "returnByValue": True, "awaitPromise": True})
                print_evaluation_failure(result)
                assert "exceptionDetails" not in result, result
                for chart in result["result"]["value"].values():
                    assert chart["empty"] and chart["hostBottom"] <= chart["detailTop"], (width, chart)
                capture_route_summary(width, "empty")
            print("V213_ROUTE_TRACE_SUMMARY=" + json.dumps(
                {"documents": route_summaries}, ensure_ascii=False), flush=True)
    finally:
        IncomePreview.empty_chart = False
        if connection:
            connection.close()
        server.shutdown()
        server.server_close()
