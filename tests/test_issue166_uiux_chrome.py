"""Issue 166 acceptance in native Chromium; all data and writes are synthetic."""
import base64
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests import test_account_reorder_runtime as harness
from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.test_settings_surface_chrome import BOOT as SETTINGS_BOOT
from tests.test_workflow_ux_chrome import attach_broker_metadata, click, no_overflow


BOOT = SETTINGS_BOOT + r"""
(() => {
  const native = window.fetch;
  window.__issue166 = {errors:[], writes:[], duplicates:[], removedUiSeen:[], calls:{}, ipoRenders:0, chartRenders:0, historySourceWrites:0,
    planning:{revision:0,buckets:[],accounts:{},holdings:{},history:
    [['2026-06-08',380000000],['2026-07-08',385000000],['2026-08-08',382000000],['2026-09-08',397000000]]
      .map(([date,net_worth])=>({date,net_worth,assets:net_worth+120000000,debt:120000000,owner:'모두',source:'manual'}))}};
  const singletonSelectors=['#assetCategoryTabs','.wealth-history','#wealthHistoryPlot','#wealthHistoryDetails',
    '#wealthHistoryEditForm','#ipoPanel','#ipoListWrapper','#ipoBrokerFilter','.ipo-filter-toolbar',
    '.ipo-list-tools','#settingsSurface','#openapiKrxSection','#openapiKrxLoginId','#openapiKrxPassword',
    '#openapiDartSection','#wealthHistoryPlot .wealth-unified-chart-shell','#wealthHistoryPlot .wealth-unified-latest'];
  const removedSelector='#wealthHistorySummary,.wealth-history-summary';
  new MutationObserver(records=>{
    for(const selector of singletonSelectors){
      const count=document.querySelectorAll(selector).length;
      if(count>1)__issue166.duplicates.push({selector,count});
    }
    for(const record of records)for(const node of record.addedNodes){
      if(node.nodeType===1&&(node.matches(removedSelector)||node.querySelector(removedSelector)))
        __issue166.removedUiSeen.push(node.id||node.className);
    }
  }).observe(document,{subtree:true,childList:true});
  window.addEventListener('wealth:ipo-market-rendered',()=>__issue166.ipoRenders++);
  const markup=Object.getOwnPropertyDescriptor(Element.prototype,'innerHTML');
  Object.defineProperty(Element.prototype,'innerHTML',{...markup,set(value){
    if(this.id==='wealthHistoryPlot'&&String(value).includes('wealth-unified-chart-shell'))__issue166.chartRenders++;
    if(this.id==='wealthHistoryPlot'&&String(value).includes('wealth-history-chart'))__issue166.historySourceWrites++;
    markup.set.call(this,value);
  }});
  const originalError = console.error;
  console.error = function(...args) {__issue166.errors.push(args.map(String).join(' '));return originalError.apply(this,args);};
  window.fetch = async function(url, options={}) {
    const address=new URL(String(url),location.href);
    if(address.origin!==location.origin)throw Error('External request forbidden');
    if(address.pathname.startsWith('/api/planning')) {
      const state=__issue166.planning;
      if(options.method==='POST') {
        const body=JSON.parse(options.body);__issue166.writes.push(address.pathname);
        if(address.pathname.endsWith('/snapshot-delete'))state.history=state.history.filter(r=>r.date!==body.date||r.owner!==body.owner);
        if(address.pathname.endsWith('/snapshot-manual')||address.pathname.endsWith('/snapshot-edit')) {
          state.history=state.history.filter(r=>r.date!==body.date||r.owner!==body.owner);
          state.history.push({...body,date:body.new_date||body.date,source:'manual'});
        }
        state.revision++;
      }
      return {ok:true,status:200,json:async()=>structuredClone(state)};
    }
    // The shared settings fixture models deletion but not re-registration.
    // Reflect a successful synthetic save so the real controller can reload
    // configured state after the repeated delete -> save lifecycle.
    if(address.pathname==='/api/user/krx-marketplace-config'&&options.method==='POST'){
      const body=JSON.parse(options.body);
      Object.assign(krx,{configured:true,login_id_configured:true,password_configured:true});
      if(body.login_id)krx.login_id='synt****';
    }
    return native.apply(this,arguments);
  };
})();
"""


@pytest.fixture
def issue166_preview(request, monkeypatch):
    factory = harness.safe_preview_server

    class Preview(harness.ReorderPreview):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/sw.js', '/manifest.json', '/dashboard'):
                name = 'index.html' if path == '/dashboard' else path[1:]
                mime = {'sw.js':'text/javascript', 'manifest.json':'application/manifest+json',
                        'index.html':'text/html'}[name]
                self.send(self.server.assets[name], mime + '; charset=utf-8')
                return
            super().do_GET()

    monkeypatch.setattr(harness, 'safe_preview_server',
                        lambda server_type, handler: factory(server_type, Preview))
    return request.getfixturevalue('chrome_preview')


def capture(call, evaluate, width, route):
    directory = os.environ.get('WEALTH_ISSUE166_EVIDENCE')
    if directory and width in (360, 1280):
        selector = {'assets':'#assetCategoryTabs','home':'.wealth-history',
                    'ipo':'#ipoPanel','settings':'#openapiKrxSection'}[route]
        evaluate(f"document.querySelector({json.dumps(selector)}).scrollIntoView({{block:'start',behavior:'instant'}})")
        evaluate('(async()=>{await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame)})()')
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        (path / f'after-{width}-{route}.png').write_bytes(base64.b64decode(
            call('Page.captureScreenshot', {'format':'png','captureBeyondViewport':False})['data']))


def seed_ipo(evaluate):
    evaluate(r"""(() => {
      const row=(id,date,extra={})=>({ipo_id:id,company_name:id,subscription_start:date,
        presentation_sort_date:date,filter_group:'UPCOMING',lead_managers:['삼성증권'],...extra});
      window.__issueIpos=[row('tie-b','2026-10-05'),row('tie-a','2026-10-05'),
        row('fallback','2026-10-07',{subscription_start:null,expected_listing_date:'2026-10-07'}),
        row('actual','2026-10-08',{subscription_start:null,actual_listing_date:'2026-10-08'}),
        row('late','2026-10-20',{lead_managers:['미래에셋증권']}),row('unknown',''),
        row('past-old','2026-08-03',{filter_group:'PAST'}),row('past-new','2026-09-03',{filter_group:'PAST'}),
        row('past-unknown','',{filter_group:'PAST'}),row('excluded','2026-10-02',{user_excluded:true}),
        row('next','2026-11-01')];
      WealthIpoState.setMarketIpos(__issueIpos);WealthIpoState.setFilterGroup('ALL');
      WealthIpoState.setHistoryYear(2026);WealthIpoState.setHistoryMonth(10);
      WealthIpoState.setMonthExplicitlySelected(true);WealthIpoState.renderIpoList();
    })()""")
    attach_broker_metadata(evaluate, '__issueIpos')


def assert_single_components(evaluate, *, chart=False, ipo=False):
    selectors = ['#assetCategoryTabs', '.wealth-history', '#wealthHistoryStatus',
                 '#wealthHistoryPlot', '#wealthHistoryDetails', '#wealthHistoryEditForm',
                 '#ipoPanel', '#ipoListWrapper', '#settingsSurface', '#openapiKrxSection',
                 '#openapiKrxLoginId', '#openapiKrxPassword', '#openapiDartSection']
    if chart:
        selectors += ['#wealthHistoryPlot .wealth-unified-chart-shell',
                      '#wealthHistoryPlot .wealth-unified-latest', '#wealthHistoryPlot svg',
                      '.wealth-history .wealth-periods']
    if ipo:
        selectors += ['#ipoBrokerFilter', '.ipo-filter-toolbar', '.ipo-list-tools', '.ipo-sort-notice']
    counts = evaluate(f"Object.fromEntries({json.dumps(selectors)}.map(s=>[s,document.querySelectorAll(s).length]))")
    assert counts == dict.fromkeys(selectors, 1), counts
    assert evaluate("document.querySelectorAll('#wealthHistorySummary,.wealth-history-summary').length") == 0
    assert evaluate('__issue166.duplicates') == []
    assert evaluate('__issue166.removedUiSeen') == []


def assert_one_call(evaluate, name, expected):
    assert evaluate(f'__issue166.calls[{json.dumps(name)}]') == expected


@pytest.mark.parametrize('width', [360, 390, 768, 1280])
def test_issue166_mobile_tabs_history_ipo_and_krx(issue166_preview, width):
    call, evaluate, port = issue166_preview
    call('Page.addScriptToEvaluateOnNewDocument', {'source':BOOT})
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':1000,
        'deviceScaleFactor':1,'mobile':width<500})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#assets'})
    wait_for(evaluate, "document.readyState==='complete'&&window.WealthStartup?.canRead()&&!!window.WealthUnifiedTimeseries&&!!window.WealthSettings&&!!window.WealthIpoState")
    evaluate("""(()=>{for(const name of ['switchAccountCategory','saveKrxMarketplaceConfig',
      'testKrxMarketplaceConfig','deleteKrxMarketplaceConfig']){
        const original=window[name];__issue166.calls[name]=0;
        window[name]=function(...args){__issue166.calls[name]++;return original.apply(this,args);};
      }})()""")
    assert_single_components(evaluate)
    capture(call, evaluate, width, 'assets')
    tabs = evaluate("""(() => {const host=document.getElementById('assetCategoryTabs');
      const rows=[...host.children].map(n=>n.getBoundingClientRect().top);
      return {rows,scroll:host.scrollWidth,client:host.clientWidth,rect:host.getBoundingClientRect().toJSON(),labels:[...host.children].map(n=>n.textContent.trim())};})()""")
    assert max(tabs['rows']) - min(tabs['rows']) < 1, tabs
    assert tabs['scroll'] <= tabs['client'] + 1, tabs
    assert tabs['labels'] == ['📈 증권', '🏦 은행', '🛡️ 연금·보험', '🏠 부동산', '🧾 세금']
    assert evaluate("[...document.querySelectorAll('#assetCategoryTabs button')].every(n=>getComputedStyle(n).flexGrow==='1')")
    for category in ('tax','banking','insurance','real_estate','securities'):
        before = evaluate('__issue166.calls.switchAccountCategory')
        click(call, evaluate, f'#assetCategoryTabs [data-cat={category}]')
        assert_one_call(evaluate, 'switchAccountCategory', before + 1)
        assert evaluate(f"document.querySelector('#assetCategoryTabs [data-cat={category}]').getAttribute('aria-selected')") == 'true'
        assert evaluate('WealthAssetCategoryState.current()') == category
        no_overflow(evaluate, width)
    evaluate("document.querySelector('#assetCategoryTabs [data-cat=securities]').focus()")
    for event_type in ('keyDown', 'keyUp'):
        call('Input.dispatchKeyEvent', {'type':event_type,'key':'Tab','code':'Tab','windowsVirtualKeyCode':9})
    assert evaluate('document.activeElement.dataset.cat') == 'banking'
    call('Input.dispatchKeyEvent', {'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13,'text':'\r'})
    call('Input.dispatchKeyEvent', {'type':'keyUp','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
    wait_for(evaluate, "WealthAssetCategoryState.current()==='banking'")
    evaluate("document.getElementById('assetCategoryTabs').scrollLeft=0;document.querySelector('#assetCategoryTabs [data-cat=tax]').click()")
    wait_for(evaluate, "(()=>{const h=document.getElementById('assetCategoryTabs').getBoundingClientRect(),r=document.querySelector('#assetCategoryTabs [data-cat=tax]').getBoundingClientRect();return r.left>=h.left&&r.right<=h.right})()")
    assert evaluate("[...document.querySelectorAll('#assetCategoryTabs button')].map(n=>n.textContent.trim())") == tabs['labels']
    assert not any('(' in label or ')' in label for label in tabs['labels'])

    evaluate("location.hash='#home'")
    headline = '#wealthHistoryPlot .wealth-unified-latest'
    wait_for(evaluate, f"document.querySelector('{headline}')?.textContent==='최신 순자산 397,000,000원 · 2026-09-08 기준'")
    assert evaluate("document.querySelectorAll('#wealthHistorySummary,.wealth-history-summary').length") == 0
    assert evaluate("document.getElementById('wealthHistoryStatus').textContent") == ''
    assert_single_components(evaluate, chart=True)
    for period in ('1D','1W','1M','1Y','ALL'):
        before = evaluate('__issue166.chartRenders')
        click(call, evaluate, f'.wealth-history [data-period="{period}"]')
        wait_for(evaluate, f"document.querySelector('{headline}')?.textContent.includes('397,000,000원')")
        assert evaluate("document.querySelectorAll('#wealthHistoryPlot svg').length") == 1
        assert evaluate('__issue166.chartRenders') == before + 1
    click(call, evaluate, '.wealth-history [data-period="1D"]')
    capture(call, evaluate, width, 'home')
    click(call, evaluate, '[data-history-action=wealthAddHistory]')
    wait_for(evaluate, "document.getElementById('wealthHistoryEditForm').closest('dialog').open")
    evaluate("""(()=>{const f=document.getElementById('wealthHistoryEditForm');f.elements.date.value='2026-10-22';f.elements.assets.value='123456';f.elements.debt.value='0';f.requestSubmit();})()""")
    wait_for(evaluate, f"document.querySelector('{headline}')?.textContent==='최신 순자산 123,456원 · 2026-10-22 기준'")
    click(call, evaluate, '[data-history-edit="2026-10-22"]')
    evaluate("const f=document.getElementById('wealthHistoryEditForm');f.elements.assets.value='0';f.requestSubmit()")
    wait_for(evaluate, f"document.querySelector('{headline}')?.textContent==='최신 순자산 0원 · 2026-10-22 기준'")
    click(call, evaluate, '[data-history-delete="2026-10-22"]')
    wait_for(evaluate, f"document.querySelector('{headline}')?.textContent.includes('397,000,000원')")
    assert evaluate('__issue166.writes') == ['/api/planning/snapshot-manual',
        '/api/planning/snapshot-edit', '/api/planning/snapshot-delete']
    evaluate("selectOwner('엄마')")
    wait_for(evaluate, "document.getElementById('wealthHistoryStatus').textContent.includes('아직 기록이 없습니다.')")
    assert not evaluate(f"!!document.querySelector('{headline}')")
    evaluate("selectOwner('모두')")
    wait_for(evaluate, f"document.querySelector('{headline}')?.textContent.includes('397,000,000원')")
    evaluate("location.hash='#assets'")
    wait_for(evaluate, "document.querySelector('[data-wealth-page=assets]').hidden===false")
    assert evaluate("document.querySelector('#assetCategoryTabs [aria-selected=true]').dataset.cat") == 'tax'

    evaluate("location.hash='#ipo'")
    wait_for(evaluate, "currentIncomeTab==='ipo'&&!!document.getElementById('ipoListWrapper')?.getClientRects().length")
    evaluate('loadIpoSchedule()')
    seed_ipo(evaluate)
    assert_single_components(evaluate, ipo=True)
    cards = "[...document.querySelectorAll('.ipo-card')].map(n=>n.dataset.ipoId)"
    assert evaluate(cards) == ['tie-a','tie-b','fallback','actual','late','past-unknown','unknown']
    assert evaluate("document.querySelector('.ipo-sort-notice').textContent.includes('청약 시작일 기준')")
    capture(call, evaluate, width, 'ipo')
    before = evaluate('__issue166.ipoRenders')
    evaluate("document.getElementById('ipoBrokerFilter').value='samsung';document.getElementById('ipoBrokerFilter').dispatchEvent(new Event('change',{bubbles:true}))")
    assert evaluate('__issue166.ipoRenders') == before + 1
    assert evaluate("document.activeElement.id") == 'ipoBrokerFilter'
    assert 'late' not in evaluate(cards)
    click(call, evaluate, '[data-filter-group=PAST]')
    assert evaluate(cards) == ['past-new','past-old','past-unknown']
    assert evaluate("document.querySelector('.ipo-sort-notice').textContent.includes('최신순')")
    click(call, evaluate, '#ipoExcludedToggle')
    assert evaluate(cards) == ['excluded']
    assert evaluate("document.querySelector('.ipo-sort-notice').textContent.includes('오래된순')")
    click(call, evaluate, '#ipoExcludedToggle')
    click(call, evaluate, '[data-filter-group=ALL]')
    click(call, evaluate, '#ipoNextMonthBtn')
    assert evaluate(cards) == ['next','past-unknown','unknown']
    assert_single_components(evaluate, ipo=True)
    no_overflow(evaluate, width)

    evaluate("location.hash='#settings'")
    wait_for(evaluate, "document.querySelector('[data-wealth-page=settings]').hidden===false")
    click(call, evaluate, '[data-settings-tab=api]')
    wait_for(evaluate, "document.getElementById('openapiKrxPassword').placeholder==='******** (변경 시에만 입력)'")
    capture(call, evaluate, width, 'settings')
    assert evaluate("document.getElementById('openapiKrxPassword').type") == 'password'
    assert evaluate("document.getElementById('openapiKrxPassword').value") == ''
    assert evaluate("['openapiKrxLoginId','openapiKrxPassword'].every(id=>document.querySelector('label[for='+id+']')?.control===document.getElementById(id))")
    evaluate("document.getElementById('openapiKrxLoginId').value='synthetic-uiux-login';document.getElementById('openapiKrxPassword').value='synthetic-uiux-secret'")
    click(call, evaluate, '#openapiKrxSection [onclick="saveKrxMarketplaceConfig()"]')
    wait_for(evaluate, "document.getElementById('openapiKrxPassword').value===''")
    click(call, evaluate, '#openapiKrxSection [onclick="testKrxMarketplaceConfig()"]')
    wait_for(evaluate, "__settingsProbe.requests.some(r=>r.path.endsWith('/krx-marketplace-config/test'))")
    click(call, evaluate, '#openapiKrxDeleteBtn')
    wait_for(evaluate, "document.getElementById('openapiKrxBadge').textContent==='미설정'")
    assert not evaluate("document.getElementById('settingsSurface').textContent.includes('synthetic-uiux-secret')")
    for name in ('saveKrxMarketplaceConfig', 'testKrxMarketplaceConfig', 'deleteKrxMarketplaceConfig'):
        assert_one_call(evaluate, name, 1)
    assert evaluate("__settingsProbe.requests.filter(r=>r.path==='/api/user/krx-marketplace-config'&&r.method==='POST').length") == 1
    assert evaluate("__settingsProbe.requests.filter(r=>r.path==='/api/user/krx-marketplace-config/test'&&r.method==='POST').length") == 1
    assert evaluate("__settingsProbe.requests.filter(r=>r.path==='/api/user/krx-marketplace-config'&&r.method==='DELETE').length") == 1

    # Re-enter existing surfaces repeatedly. New DOM or rebound handlers must
    # not accumulate across route changes, period changes or list replacements.
    for _ in range(3):
        evaluate("location.hash='#assets'")
        wait_for(evaluate, "document.querySelector('[data-wealth-page=assets]').hidden===false")
        before = evaluate('__issue166.calls.switchAccountCategory')
        click(call, evaluate, '#assetCategoryTabs [data-cat=banking]')
        assert_one_call(evaluate, 'switchAccountCategory', before + 1)
        assert_single_components(evaluate)
        no_overflow(evaluate, width)
        source_before = evaluate('__issue166.historySourceWrites')
        chart_before = evaluate('__issue166.chartRenders')
        evaluate("location.hash='#home'")
        # Await the new saved-record SVG handoff and its chart, rather than
        # accepting the headline left in the hidden home from the last visit.
        wait_for(evaluate, f"__issue166.historySourceWrites>{source_before}&&__issue166.chartRenders>{chart_before}&&document.querySelector('{headline}')?.textContent.includes('397,000,000원')&&!!document.querySelector('[data-wealth-page=home]')?.getClientRects().length")
        assert_single_components(evaluate, chart=True)
        assert evaluate("document.getElementById('wealthHistoryStatus').textContent") == ''
        no_overflow(evaluate, width)
        evaluate("location.hash='#ipo'")
        wait_for(evaluate, "currentIncomeTab==='ipo'&&!!document.getElementById('ipoListWrapper')?.getClientRects().length")
        evaluate('loadIpoSchedule()')
        seed_ipo(evaluate)
        before = evaluate('__issue166.ipoRenders')
        click(call, evaluate, '[data-filter-group=PAST]')
        assert evaluate('__issue166.ipoRenders') == before + 1
        assert evaluate(cards) == ['past-new','past-old','past-unknown']
        assert_single_components(evaluate, ipo=True)
        no_overflow(evaluate, width)
        evaluate("location.hash='#settings'")
        wait_for(evaluate, "document.querySelector('[data-wealth-page=settings]').hidden===false")
        click(call, evaluate, '[data-settings-tab=api]')
        wait_for(evaluate, "!document.getElementById('settingsApiFields').disabled")
        assert_single_components(evaluate, ipo=True)
        no_overflow(evaluate, width)
    evaluate("document.getElementById('openapiKrxLoginId').value='synthetic-uiux-login';document.getElementById('openapiKrxPassword').value='synthetic-uiux-secret'")
    click(call, evaluate, '#openapiKrxSection [onclick="saveKrxMarketplaceConfig()"]')
    wait_for(evaluate, "document.getElementById('openapiKrxPassword').value===''")
    click(call, evaluate, '#openapiKrxSection [onclick="testKrxMarketplaceConfig()"]')
    click(call, evaluate, '#openapiKrxDeleteBtn')
    wait_for(evaluate, "document.getElementById('openapiKrxBadge').textContent==='미설정'")
    for name in ('saveKrxMarketplaceConfig', 'testKrxMarketplaceConfig', 'deleteKrxMarketplaceConfig'):
        assert_one_call(evaluate, name, 2)
    for path, method in (('/api/user/krx-marketplace-config','POST'),
                         ('/api/user/krx-marketplace-config/test','POST'),
                         ('/api/user/krx-marketplace-config','DELETE')):
        assert evaluate(f"__settingsProbe.requests.filter(r=>r.path==={json.dumps(path)}&&r.method==={json.dumps(method)}).length") == 2
    assert evaluate('__settingsProbe.forms') == 1
    assert evaluate('__settingsProbe.legacy') == 0
    assert evaluate('__settingsProbe.moves') == 0
    assert_single_components(evaluate, ipo=True)
    assert not evaluate("document.getElementById('settingsSurface').textContent.includes('synthetic-uiux-secret')")
    no_overflow(evaluate, width)
    assert evaluate('__settingsProbe.errors') == []
    assert evaluate('__issue166.errors') == []
