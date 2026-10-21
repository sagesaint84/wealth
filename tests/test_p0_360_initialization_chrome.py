"""Real Chromium coverage for direct dividend startup at 360 CSS pixels."""

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
        assert handler is dividend_preview.DividendPreview
        assert dividend_preview.RECORDS

        class ServiceWorkerPreview(handler):
            def do_GET(self):
                if urlsplit(self.path).path == '/sw.js':
                    # The shared fixture snapshots the real app/static files
                    # before starting its HTTP thread, including sw.js.
                    self.send(self.server.preview_assets['sw.js'],
                              'text/javascript; charset=utf-8')
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
