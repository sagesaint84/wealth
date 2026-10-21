"""The current home must render even before application JavaScript runs.

Synthetic loopback APIs only; the application and financial stores are never opened.
"""
import json
import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_static_transport_chrome import transport_server


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
