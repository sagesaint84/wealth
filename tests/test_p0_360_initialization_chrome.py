"""Real Chromium coverage for direct dividend startup at 360 CSS pixels."""

import json
from urllib.parse import urlsplit

import pytest

from tests import test_dividend_income_route_chrome as dividend_preview
from tests.test_dividend_income_route_chrome import chrome_preview, wait_for
from tests.ui_preview import DASHBOARD


@pytest.fixture
def p0_chrome_preview(request, monkeypatch):
    original_factory = dividend_preview.safe_preview_server

    def preview_with_service_worker(server_type, handler, *args, **kwargs):
        # chrome_preview uses ChromePreviewServer with a name-selected handler.
        # Check the actual selection before extending only this server instance.
        assert server_type is dividend_preview.ChromePreviewServer
        expected = (dividend_preview.StaticPreview
                    if request.node.name == 'test_p0_service_worker_real_browser_cache_and_navigation'
                    else dividend_preview.DividendPreview)
        assert handler is expected
        assert dividend_preview.RECORDS

        # The independent SW test's name selects StaticPreview upstream. Keep
        # the same nonempty dividend fixture explicitly for both local tests.
        class ServiceWorkerPreview(dividend_preview.DividendPreview):
            def do_GET(self):
                path = urlsplit(self.path).path
                if path == '/sw.js':
                    # The shared fixture snapshots the real app/static files
                    # before starting its HTTP thread, including sw.js.
                    self.send(self.server.preview_assets['sw.js'],
                              'text/javascript; charset=utf-8')
                    return
                if path == '/dashboard':
                    self.send(self.server.preview_assets['index.html'], 'text/html; charset=utf-8')
                    return
                if path == '/manifest.json':
                    self.send(self.server.preview_assets['manifest.json'],
                              'application/manifest+json; charset=utf-8')
                    return
                super().do_GET()

        return original_factory(server_type, ServiceWorkerPreview, *args, **kwargs)

    # Patch only the factory reference for this function-scoped fixture. Neither
    # the shared server nor its handler class is modified; pytest restores it.
    monkeypatch.setattr(dividend_preview, 'safe_preview_server', preview_with_service_worker)
    return request.getfixturevalue('chrome_preview')


def test_p0_360_dividend_visible_chart_initializes_after_assets_ready(p0_chrome_preview):
    # ChromePreviewServer uses our local extension of DividendPreview; its
    # IncomePreview parent serves 60 nonempty synthetic dividend RECORDS.
    call, evaluate, port = p0_chrome_preview
    call('Emulation.setDeviceMetricsOverride', {
        'width': 360, 'height': 800, 'screenWidth': 360, 'screenHeight': 800,
        'deviceScaleFactor': 1, 'mobile': True,
    })
    call('Page.addScriptToEvaluateOnNewDocument', {'source': r"""
      (() => {
        const trace = window.__p0Initialization = {
          events: [], errors: [], rejections: [], consoleErrors: [],
        };
        const record = (kind, extra = {}) => trace.events.push({kind, ...extra});
        const describe = value => String(value?.stack || value?.message || value);
        window.addEventListener('error', event => {
          if (event.message || event.target?.tagName === 'SCRIPT') {
            trace.errors.push(event.message || `Script failed: ${event.target.src}`);
          }
        }, true);
        window.addEventListener('unhandledrejection', event => {
          trace.rejections.push(describe(event.reason));
        });
        const originalError = console.error;
        console.error = function(...args) {
          trace.consoleErrors.push(args.map(describe).join(' '));
          return originalError.apply(this, args);
        };
        window.addEventListener('wealth:unified-ready', () => record('unified-ready'));
        window.addEventListener('wealth:assets-ready', () => record('assets-ready', {
          canRead: WealthStartup.canRead(), username: currentUserProfile?.username,
          dashboard: rawDashboard,
        }));
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
          const url = new URL(args[0] instanceof Request ? args[0].url : args[0], location.href);
          if (url.origin !== location.origin) {
            throw new Error(`Unexpected non-fixture request: ${url.href}`);
          }
          record('request', {path: url.pathname, query: url.search,
            canRead: window.WealthStartup?.canRead() === true});
          return originalFetch.apply(this, args).then(response => {
            record('response', {path: url.pathname, status: response.status});
            return response;
          });
        };
        // Observe the first real chart write synchronously, including writes
        // before DOMContentLoaded. Do not invoke or replace app initializers.
        const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
        Object.defineProperty(Element.prototype, 'innerHTML', {
          ...descriptor,
          set(value) {
            if (this.id === 'dividendBarChartWrap'
                && String(value).includes('wealth-unified-chart-shell')) {
              record('chart', {canRead: window.WealthStartup?.canRead() === true,
                unified: !!window.WealthUnifiedTimeseries,
                hash: location.hash, tab: currentIncomeTab});
            }
            return descriptor.set.call(this, value);
          },
        });
      })();
    """})
    navigation = call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#dividend'})
    assert not navigation.get('errorText'), navigation

    ready = """(() => {
      const host = document.getElementById('dividendBarChartWrap');
      const viewport = host?.querySelector('.wealth-unified-viewport');
      return document.readyState === 'complete' && !!window.WealthUnifiedTimeseries
        && window.WealthStartup?.canRead() && currentIncomeTab === 'dividend'
        && !setIncomeTab.pendingTarget && startupReadPending.size === 0
        && !loadAssetDataForUser.pending && host?.dataset.unifiedState === 'ready'
        && !!document.getElementById('dividendPanel')?.getClientRects().length
        && !!host.querySelector('.wealth-unified-flow-bar[data-bucket-index]')
        && viewport?.clientWidth > 0;
    })()"""
    try:
        wait_for(evaluate, ready)
    except pytest.fail.Exception as error:
        pytest.fail(f'{error}; initialization={evaluate("window.__p0Initialization")}')

    # Await the actual secondary startup work and the next presented frame,
    # allowing Chromium to deliver any pending unhandledrejection event.
    result = evaluate("""(async () => {
      await loadAssetDataForUser.supplementary;
      await new Promise(requestAnimationFrame);
      await new Promise(requestAnimationFrame);
      const host = document.getElementById('dividendBarChartWrap');
      const viewport = host.querySelector('.wealth-unified-viewport');
      const content = host.querySelector('.wealth-unified-content');
      return {trace: window.__p0Initialization, fixtureErrors: window.__divTrace.errors,
        width: innerWidth, hash: location.hash, tab: currentIncomeTab,
        activeView: document.querySelector('.wealth-workspace').dataset.activeView,
        selected: document.querySelector('#incomeTabs .income-tab.active')?.dataset.income,
        mode: currentDividendMode, state: host.dataset.unifiedState,
        dividendRecords: actualDividendData?.records?.length,
        shells: host.querySelectorAll('.wealth-unified-chart-shell').length,
        bars: host.querySelectorAll('.wealth-unified-flow-bar[data-bucket-index]').length,
        viewportWidth: viewport.clientWidth, contentWidth: content.getBoundingClientRect().width,
        busy: document.getElementById('incomeTabs').hasAttribute('aria-busy'),
        status: !!document.getElementById('incomeChartStatus'),
        pendingControls: !!document.getElementById('dividendPendingControls')};
    })()""")
    trace = result['trace']
    assert trace['errors'] == trace['rejections'] == trace['consoleErrors'] == [], result
    assert result['fixtureErrors'] == [], result
    assert result['width'] == 360, result
    assert result['hash'] == '#dividend', result
    assert result['tab'] == result['selected'] == 'dividend', result
    assert result['activeView'] == 'income' and result['mode'] == 'actual', result
    assert result['dividendRecords'] > 0, result
    assert result['state'] == 'ready' and result['shells'] == 1 and result['bars'] > 0, result
    assert result['contentWidth'] >= result['viewportWidth'] > 0, result
    assert not result['busy'] and not result['status'] and not result['pendingControls'], result

    events = trace['events']

    def first(kind, path=None):
        matches = [index for index, event in enumerate(events)
                   if event['kind'] == kind and (path is None or event.get('path') == path)]
        assert matches, (kind, path, result)
        return matches[0]

    assets = first('assets-ready')
    chart = first('chart')
    assert first('request', '/api/auth/me') < first('response', '/api/auth/me'), result
    assert first('response', '/api/auth/me') < first('request', '/api/refresh-prices'), result
    assert first('response', '/api/refresh-prices') < first('request', '/api/dashboard'), result
    assert first('response', '/api/dashboard') < assets < chart, result
    assert first('unified-ready') < chart, result
    assert events[assets]['canRead'] and events[assets]['username'] == 'DEMO', result
    assert events[assets]['dashboard'] == DASHBOARD, result

    # The shared read-only preview deliberately rejects mutations. Its 403
    # refresh must still reach dashboard/assets readiness via the real fallback;
    # it must not attempt to record production snapshots.
    assert events[first('response', '/api/refresh-prices')]['status'] == 403, result
    assert events[first('response', '/api/dashboard')]['status'] == 200, result
    assert events[first('request', '/api/dashboard')]['query'] == '', result
    assert not any(event.get('path') == '/api/planning/snapshot-all' for event in events), result
    dividend_reads = [index for index, event in enumerate(events)
                      if event['kind'] == 'request' and event.get('path') == '/api/actual-dividends']
    assert dividend_reads and all(assets < index < chart for index in dividend_reads), result
    assert all(events[index]['canRead'] for index in dividend_reads), result
    assert all(event['canRead'] and event['unified'] and event['hash'] == '#dividend'
               and event['tab'] == 'dividend' for event in events if event['kind'] == 'chart'), result


def test_p0_service_worker_real_browser_cache_and_navigation(p0_chrome_preview):
    """Exercise the production SW policy with the existing synthetic APIs."""
    call, evaluate, port = p0_chrome_preview
    origin = f'http://127.0.0.1:{port}'
    cache_name = 'wealth-cache-v2.1.3-p0'
    sw_source = (dividend_preview.STATIC / 'sw.js').read_text(encoding='utf-8')
    assert f'const CACHE_NAME = "{cache_name}";' in sw_source
    call('Network.enable')
    call('Network.setBypassServiceWorker', {'bypass': False})
    call('Network.setCacheDisabled', {'cacheDisabled': False})
    call('Emulation.setDeviceMetricsOverride', {
        'width': 360, 'height': 800, 'screenWidth': 360, 'screenHeight': 800,
        'deviceScaleFactor': 1, 'mobile': True,
    })
    call('Page.addScriptToEvaluateOnNewDocument', {'source': r"""
      (() => {
      window.__p0SwErrors = {errors:[], rejections:[], consoleErrors:[]};
      const describe = value => String(value?.stack || value?.message || value);
      addEventListener('error', event => {
        if (event.message || event.target?.tagName === 'SCRIPT') {
          __p0SwErrors.errors.push(event.message || `Script failed: ${event.target.src}`);
        }
      }, true);
      addEventListener('unhandledrejection', event => {
        __p0SwErrors.rejections.push(describe(event.reason));
      });
      const originalError = console.error;
      console.error = function(...args) {
        __p0SwErrors.consoleErrors.push(args.map(describe).join(' '));
        return originalError.apply(this, args);
      };
      })();
    """})

    common_ready = """document.readyState === 'complete'
      && !!window.WealthUnifiedTimeseries && !!window.WealthIncomePeriodBrokerFilter
      && window.WealthStartup?.canRead() && !loadAssetDataForUser.pending
      && startupReadPending.size === 0"""
    home_ready = """document.querySelector('.wealth-workspace')?.dataset.activeView === 'home'
      && !!document.querySelector('[data-wealth-page=home]')?.getClientRects().length
      && document.getElementById('wealthAssetNetWorth')?.textContent === '397,000,000원'"""
    dividend_ready = """(() => {
      const host = document.getElementById('dividendBarChartWrap');
      return document.querySelector('.wealth-workspace')?.dataset.activeView === 'income'
        && currentIncomeTab === 'dividend' && currentDividendMode === 'actual'
        && !setIncomeTab.pendingTarget && actualDividendData?.records?.length > 0
        && !!document.getElementById('dividendPanel')?.getClientRects().length
        && host?.dataset.unifiedState === 'ready'
        && host.querySelectorAll('.wealth-unified-chart-shell').length === 1
        && !!host.querySelector('.wealth-unified-flow-bar[data-bucket-index]')
        && host.querySelector('.wealth-unified-viewport')?.clientWidth > 0;
    })()"""

    def inspect_page(route, previous_origin=None):
        navigation = (f'performance.timeOrigin !== {previous_origin!r} && '
                      if previous_origin is not None else '')
        ready = home_ready if route == 'home' else dividend_ready
        wait_for(evaluate, navigation + f'location.origin === {json.dumps(origin)}'
                 + f' && location.hash === "#{route}" && ({common_ready}) && ({ready})')
        # Registration comes from the app's load handler. A failed registration
        # must not be repaired by registering a worker from the test itself.
        wait_for(evaluate, """(async () => {
          const registration = await navigator.serviceWorker.getRegistration('/');
          return registration?.active?.state === 'activated'
            && navigator.serviceWorker.controller?.state === 'activated';
        })()""")
        state = evaluate("""(async () => {
          await loadAssetDataForUser.supplementary;
          await navigator.serviceWorker.ready;
          // Exercise an actual API read under SW control without changing data.
          const apiResponse = await fetch('/api/dashboard');
          const apiData = await apiResponse.json();
          await new Promise(requestAnimationFrame);
          await new Promise(requestAnimationFrame);
          const registration = await navigator.serviceWorker.getRegistration('/');
          const names = await caches.keys();
          const entries = [];
          for (const name of names) {
            const cache = await caches.open(name);
            for (const request of await cache.keys()) {
              const url = new URL(request.url);
              entries.push({name, origin:url.origin, path:url.pathname, method:request.method});
            }
          }
          const resources = performance.getEntriesByType('resource').map(entry => ({
            path:new URL(entry.name).pathname, workerStart:entry.workerStart,
          }));
          return {hash:location.hash, width:innerWidth, dashboard:rawDashboard,
            apiStatus:apiResponse.status, apiData, names, entries, resources,
            scope:registration.scope, activeScript:registration.active.scriptURL,
            controlledScript:navigator.serviceWorker.controller.scriptURL,
            errors:window.__p0SwErrors, fixtureErrors:window.__divTrace.errors};
        })()""")
        assert state['width'] == 360 and state['hash'] == f'#{route}', state
        assert state['dashboard'] == state['apiData'] == DASHBOARD, state
        assert state['apiStatus'] == 200, state
        assert state['scope'] == origin + '/', state
        assert state['activeScript'] == state['controlledScript'] == origin + '/sw.js', state
        assert state['names'] == [cache_name], state
        paths = {entry['path'] for entry in state['entries']}
        assert {'/', '/dashboard', '/manifest.json', '/static/icon-192.png',
                '/static/icon-512.png', '/static/apple-touch-icon.png'} <= paths, state
        for entry in state['entries']:
            assert entry['name'] == cache_name and entry['origin'] == origin, state
            assert entry['method'] == 'GET', state
            assert not entry['path'].startswith('/api/'), state
            assert not entry['path'].endswith(('.js', '.css')), state
        errors = state['errors']
        assert errors['errors'] == errors['rejections'] == errors['consoleErrors'] == [], state
        assert state['fixtureErrors'] == [], state
        assert any(entry['path'] == '/api/dashboard' and entry['workerStart'] > 0
                   for entry in state['resources']), state
        return state

    previous = evaluate('performance.timeOrigin')
    navigation = call('Page.navigate', {'url': origin + '/#home'})
    assert not navigation.get('errorText'), navigation
    inspect_page('home', previous)

    previous = evaluate('performance.timeOrigin')
    call('Page.reload', {'ignoreCache': False})
    home_reload = inspect_page('home', previous)
    # Reloaded JS/CSS must actually traverse the active worker; absence from
    # Cache Storage alone would not prove that the SW policy was exercised.
    for extension in ('.js', '.css'):
        assert any(entry['path'].endswith(extension) and entry['workerStart'] > 0
                   for entry in home_reload['resources']), home_reload

    evaluate("location.hash = '#dividend'")
    inspect_page('dividend')
    previous = evaluate('performance.timeOrigin')
    call('Page.reload', {'ignoreCache': False})
    inspect_page('dividend', previous)
