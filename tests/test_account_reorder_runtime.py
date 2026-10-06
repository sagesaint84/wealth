"""Actual Chrome DOM/controller tests with controlled arrow controls and PATCH promises."""
from pathlib import Path
from contextlib import ExitStack
from http.server import ThreadingHTTPServer
import json
import base64
import os
import subprocess
import threading
import time
import urllib.request
from urllib.parse import urlsplit

import pytest

from tests.test_dividend_income_route_chrome import wait_for as wait_for_page
from tests.test_pnl_first_visible_frame import chrome_profile
from tests.test_realized_pnl_viewport import _chrome_path
from tests.ui_preview import PreviewHandler, STATIC


def wait_for(evaluate, expression):
    try:
        wait_for_page(evaluate, expression)
    except pytest.fail.Exception as error:
        pytest.fail(f'{error}; browser load errors={evaluate.load_errors}')


class ReorderPreview(PreviewHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        name = 'index.html' if path == '/' else path.removeprefix('/static/')
        if path == '/' or path.startswith('/static/'):
            content = self.server.assets.get(name)
            if content is not None:
                kind = 'text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'text/javascript'
                self.send(content, kind + '; charset=utf-8')
                return
        super().do_GET()


class ReorderServer(ThreadingHTTPServer):
    # Chrome requests the full application's static bundle in a burst. The
    # stdlib default backlog of five can refuse connections on Windows.
    request_queue_size = 32


@pytest.fixture
def chrome_preview():
    websocket = pytest.importorskip('websocket')
    chrome = _chrome_path()
    if not chrome:
        pytest.skip('Chrome required')
    server = ReorderServer(('127.0.0.1', 0), ReorderPreview)
    # Snapshot files before HTTP workers start: deterministic static delivery,
    # avoiding Windows antivirus/file-read failures in native worker threads.
    server.assets = {path.name: path.read_bytes() for path in STATIC.iterdir() if path.is_file()}
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with ExitStack() as cleanup:
            profile = cleanup.enter_context(chrome_profile('wealth-reorder-'))
            process = subprocess.Popen([chrome, '--headless=new', '--no-first-run',
                '--no-default-browser-check', '--disable-gpu', '--remote-allow-origins=*',
                '--remote-debugging-port=0', f'--user-data-dir={profile}', 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            def stop():
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(5)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(5)
            cleanup.callback(stop)
            for _ in range(100):
                try:
                    debug_port = (Path(profile) / 'DevToolsActivePort').read_text().splitlines()[0]
                    break
                except (FileNotFoundError, PermissionError, IndexError):
                    time.sleep(.1)
            else:
                pytest.fail('Chrome debugging port unavailable')
            targets = json.load(urllib.request.urlopen(f'http://127.0.0.1:{debug_port}/json', timeout=5))
            connection = websocket.create_connection(next(t for t in targets if t['type'] == 'page')['webSocketDebuggerUrl'], timeout=15)
            cleanup.callback(connection.close)
            sequence = 0
            load_errors = []
            def call(method, params=None):
                nonlocal sequence
                sequence += 1
                connection.send(json.dumps({'id': sequence, 'method': method, 'params': params or {}}))
                while True:
                    result = json.loads(connection.recv())
                    if result.get('method') in ('Network.loadingFailed', 'Runtime.exceptionThrown'):
                        load_errors.append(result)
                    if result.get('id') == sequence:
                        assert 'error' not in result, result
                        return result['result']
            def evaluate(expression):
                result = call('Runtime.evaluate', {'expression': expression, 'returnByValue': True, 'awaitPromise': True})
                assert 'exceptionDetails' not in result, result
                return result['result'].get('value')
            evaluate.load_errors = load_errors
            call('Page.enable'); call('Runtime.enable'); call('Network.enable')
            yield call, evaluate, server.server_port
    finally:
        server.shutdown(); server.server_close()


BOOT = r"""
window.__reloadReady=true;
window.__order = {patches:[], pending:[], errors:[], fail:false};
const natural={version:1,
  securities:{institutions:['kb','toss'],accounts:{kb:['A1','A2','A3','A4'],toss:['B1']},labels:{kb:'KB증권',toss:'토스증권'},aliases:{'KB증권':'kb','토스증권':'toss'}},
  banking:{institutions:['국민은행','신한은행'],labels:{'국민은행':'국민은행','신한은행':'신한은행'},aliases:{},
    bank_accounts:{'국민은행':['b1','b2'],'신한은행':['b3']},savings_accounts:{'국민은행':['s1','s2'],'신한은행':['s3']},loan_accounts:{'국민은행':['l1','l2'],'신한은행':['l3']}}};
__order.saved=structuredClone(natural);
const nativeFetch=window.fetch;
window.fetch=function(url,opts){
  if(String(url)!=='/api/account-display-order') return nativeFetch.apply(this,arguments);
  if(!opts || opts.method!=='PATCH') return Promise.resolve({ok:true,json:async()=>structuredClone(__order.saved)});
  const operation=JSON.parse(opts.body);__order.patches.push(operation);
  return new Promise(resolve=>__order.pending.push(()=>{
    if(__order.fail){__order.fail=false;resolve({ok:false});return;}
    const section=__order.saved[operation.scope];
    const full=operation.level==='institutions'?section.institutions:section[operation.kind || 'accounts'][operation.institution];
    const visible=new Set(operation.order);let index=0;
    const merged=full.map(id=>visible.has(id)?operation.order[index++]:id);
    if(operation.level==='institutions')section.institutions=merged;
    else section[operation.kind || 'accounts'][operation.institution]=merged;
    resolve({ok:true,json:async()=>structuredClone(__order.saved)});
  }));
};
"""

HELPERS = r"""
const check=(yes,message)=>{if(!yes)throw Error(message);};
const equals=(a,b,message)=>check(JSON.stringify(a)===JSON.stringify(b),message+': '+JSON.stringify(a));
const account=(id,broker='KB증권')=>({id,broker,name:id,owner:'아빠',account_no:'123456789012',account_type:'irp',annual_deposit:0,cash_krw:10});
const bank=(id,name='국민은행')=>({id,bank_name:name,account_name:id,account_number:'123456789012',owner:'아빠',balance:10,limit_amount:['b1','b2'].includes(id)?100:0});
const saving=(id,name='국민은행')=>({id,bank_name:name,product_name:id,owner:'아빠',saving_type:'deposit',interest_rate:1,duration_months:12,calc:{}});
const loan=(id,name='국민은행')=>({id,bank_name:name,product_name:id,owner:'아빠',loan_type:'credit',current_balance:10,interest_rate:1});
window.toast=(text,error)=>__order.errors.push({text,error});
function draw(ids=['A1','A2','A3','A4']) {
  renderAccounts([...ids.map(id=>account(id)),account('B1','토스증권')]);
  renderSavings([saving('s1'),saving('s2'),saving('s3','신한은행')],
    [bank('b1'),bank('b2'),bank('b3','신한은행')],[loan('l1'),loan('l2'),loan('l3','신한은행')],'모두');
  document.getElementById('accountsPanel').scrollIntoView();
}
function groups(scope='securities',root=null){return [...document.querySelectorAll(root || (scope==='securities'?'#accountList > .broker-group':'#banksListWrap > .bank-institution-group'))];}
const row=id=>document.querySelector(`[data-order-id="${id}"]`);
const controls=node=>node.querySelector('.account-order-controls');
const arrow=(node,direction)=>controls(node).querySelector(`[data-order-direction="${direction}"]`);
const ids=parent=>[...parent.children].filter(n=>n.dataset.orderId && n.dataset.orderDerived!=='true').map(n=>n.dataset.orderId);
const unlock=()=>document.getElementById('accountOrderLock').click();
async function resolveSave(){check(__order.pending.length===1,'one pending save');__order.pending.shift()();for(let i=0;i<8;i++)await Promise.resolve();}
draw();
"""

SCENARIOS = {
    'locked_institutions': r"""
      check(document.getElementById('accountOrderLock').getAttribute('aria-pressed')==='false','initial locked');
      check(controls(groups()[0]).hidden,'locked hidden');
      arrow(groups()[0],1).click();check(!__order.patches.length,'locked no PATCH');
      unlock();check(!controls(groups()[0]).hidden,'unlocked visible');
      check(arrow(groups()[0],-1).disabled && arrow(groups()[1],1).disabled,'institution bounds');
      arrow(groups()[0],1).click();
      equals(__order.patches[0],{scope:'securities',level:'institutions',order:['toss','kb']},'broker down');
      equals(groups().map(n=>n.dataset.orderKey),['kb','toss'],'no optimistic order');
      await resolveSave();arrow(groups()[1],-1).click();await resolveSave();
      equals(groups().map(n=>n.dataset.orderKey),['kb','toss'],'broker up');
      unlock();check(controls(groups()[0]).hidden,'relocked');
      check([...document.querySelectorAll('.account-order-controls')].every(n=>n.hidden),'all controls locked');
      arrow(groups()[0],1).click();check(__order.patches.length===2,'relocked no PATCH');
    """,
    'children_owner_rerender': r"""
      draw(['A1','A3']);unlock();
      check(arrow(row('A1'),-1).disabled && arrow(row('A3'),1).disabled,'child bounds');
      check(arrow(row('B1'),-1).disabled && arrow(row('B1'),1).disabled,'single no crossing');
      arrow(row('A3'),-1).click();
      equals(__order.patches[0],{scope:'securities',level:'accounts',kind:'accounts',institution:'kb',order:['A3','A1']},'visible subset');
      await resolveSave();equals(__order.saved.securities.accounts.kb,['A3','A2','A1','A4'],'hidden preserved');
      arrow(row('A3'),1).click();await resolveSave();
      equals(ids(row('A1').parentElement),['A1','A3'],'one position down');
      draw();equals(ids(row('A1').parentElement),['A1','A2','A3','A4'],'rerender');
      draw(['A1','A3','NEW']);equals(ids(row('A1').parentElement),['A1','A3','NEW'],'new appended');
      renderAccounts([account('A1'),account('NEW','kb증권')]);check(groups().length===1,'alias grouped');
    """,
    'banking': r"""
      switchAccountCategory('banking');unlock();
      check(!document.querySelector('[data-order-derived="true"] .account-order-controls'),'derived no controls');
      for(const [first,last,kind] of [['b1','b2','bank_accounts'],['s1','s2','savings_accounts'],['l1','l2','loan_accounts']]){
        check(arrow(row(first),-1).disabled && arrow(row(last),1).disabled,'bank child bounds');
        arrow(row(first),1).click();
        equals(__order.patches.at(-1),{scope:'banking',level:'accounts',kind,institution:'국민은행',order:[last,first]},kind+' down');
        await resolveSave();
        if(kind==='bank_accounts')equals([...document.querySelectorAll('#loansGrid [data-order-derived="true"]')].map(n=>n.dataset.orderId),['b2','b1'],'derived follows source');
        arrow(row(first),-1).click();await resolveSave();equals(ids(row(first).parentElement),[first,last],kind+' up');
      }
      arrow(groups('banking')[0],1).click();await resolveSave();
      equals(__order.patches.at(-1),{scope:'banking',level:'institutions',order:['신한은행','국민은행']},'bank down');
      for(const root of ['banksListWrap','savingsGrid','loansGrid'])equals([...document.querySelectorAll('#'+root+' > section')].map(n=>n.dataset.orderKey),['신한은행','국민은행'],'common order');
      arrow(groups('banking')[1],-1).click();await resolveSave();
      equals(groups('banking').map(n=>n.dataset.orderKey),['국민은행','신한은행'],'bank up');
      for(const category of ['insurance','real_estate']){
        switchAccountCategory(category);check(document.getElementById('accountOrderLock').hidden,'unsupported lock');
        check([...document.querySelectorAll('.account-order-controls')].every(n=>n.hidden),'unsupported controls');
      }
    """,
    'failure_sequencing': r"""
      unlock();__order.fail=true;arrow(row('A1'),1).click();
      check([...document.querySelectorAll('.account-order-controls button')].every(n=>n.disabled),'saving disabled');
      arrow(row('A2'),1).click();check(__order.patches.length===1,'second blocked');
      await resolveSave();equals(ids(row('A1').parentElement),['A1','A2','A3','A4'],'failure restored');
      check(__order.errors.some(e=>e.error && e.text.includes('저장에 실패')),'toast');
      arrow(row('A1'),1).click();await resolveSave();
      check(document.activeElement===arrow(row('A1'),1),'focus restored');
      arrow(row('A1'),1).click();await resolveSave();equals(ids(row('A1').parentElement),['A2','A3','A1','A4'],'sequential moves');
    """,
    'themes_mobile': r"""
      unlock();
      for(const theme of ['purple','oled','white']){
        document.documentElement.dataset.theme=theme;
        for(const button of controls(row('A1')).children){
          const r=button.getBoundingClientRect();check(r.width>=36 && r.height>=36,'touch target');
          check(r.left>=0 && r.right<=innerWidth,'fits viewport');
          check(button.type==='button' && button.title && button.getAttribute('aria-label'),'accessible button');
        }
      }
      check(document.documentElement.scrollWidth<=innerWidth,'no horizontal overflow');
      const e=new Event('touchmove',{bubbles:true,cancelable:true});controls(row('A1')).dispatchEvent(e);
      check(!e.defaultPrevented,'normal scroll unaffected');
      check(!document.body.textContent.includes('123456789012'),'number masked');
    """,
}


@pytest.mark.parametrize('scenario', SCENARIOS)
def test_reorder_chrome_runtime(chrome_preview, scenario):
    call, evaluate, port = chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument', {'source': BOOT})
    call('Emulation.setDeviceMetricsOverride', {'width': 390 if scenario == 'themes_mobile' else 1440,
        'height': 900, 'deviceScaleFactor': 1, 'mobile': scenario == 'themes_mobile'})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#assets'})
    wait_for(evaluate, "document.readyState==='complete' && typeof renderSavings==='function' && !document.getElementById('accountOrderLock').disabled")
    result = evaluate('(async()=>{' + HELPERS + SCENARIOS[scenario] + ';return true;})()')
    assert result is True


def test_reorder_is_wired_only_to_supported_renderers_and_has_no_storage_or_observer():
    root = Path(__file__).resolve().parents[1] / 'app/static'
    module = (root / 'wealth-account-reorder.js').read_text(encoding='utf-8')
    index = (root / 'index.html').read_text(encoding='utf-8')
    wealth = (root / 'wealth.js').read_text(encoding='utf-8')
    assert index.index('/static/wealth-account-reorder.js') < index.index('/static/wealth.js')
    assert 'localStorage' not in module and 'MutationObserver' not in module
    assert "rendered('securities')" in wealth and "rendered('banking')" in wealth
    assert 'draggable=' not in module
    for forbidden in ['pointerdown', 'pointermove', 'pointerup', 'touchmove', 'preventDefault', 'setPointerCapture', 'setTimeout', 'requestAnimationFrame', 'ArrowUp', 'ArrowDown']:
        assert forbidden not in module
    css = (root / 'wealth-account-reorder.css').read_text()
    for forbidden in ['touch-action', 'grabbing', 'cursor:grab', 'account-order-dragged', 'account-order-target', 'account-order-pressed']:
        assert forbidden not in css


def test_reload_locks_and_keeps_saved_order(chrome_preview):
    call, evaluate, port = chrome_preview
    persisted = BOOT + "__order.saved.securities.institutions=['toss','kb'];"
    call('Page.addScriptToEvaluateOnNewDocument', {'source': persisted})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#assets'})
    wait_for(evaluate, "document.readyState==='complete' && typeof renderSavings==='function' && !document.getElementById('accountOrderLock').disabled")
    evaluate('(()=>{' + HELPERS + "unlock();return true;})()")
    evaluate('window.__reloadReady=false')
    call('Page.reload')
    wait_for(evaluate, "window.__reloadReady && document.readyState==='complete' && typeof renderSavings==='function' && !document.getElementById('accountOrderLock').disabled")
    assert evaluate('(()=>{' + HELPERS + "check(controls(groups()[0]).hidden,'reload locked');equals(groups().map(n=>n.dataset.orderKey),['toss','kb'],'saved order');return true;})()")


def test_banking_mobile_layout_and_visual_artifact(chrome_preview, tmp_path):
    call, evaluate, port = chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument', {'source': BOOT})
    call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#assets'})
    wait_for(evaluate, "document.readyState==='complete' && typeof renderSavings==='function' && !document.getElementById('accountOrderLock').disabled")
    evaluate('(()=>{' + HELPERS + "switchAccountCategory('banking');document.getElementById('accountOrderLock').click();document.getElementById('bankSectionFree').scrollIntoView({block:'start',behavior:'instant'});return true;})()")
    assert evaluate("[...document.querySelectorAll('#banksListWrap .account-order-controls button')].every(n=>{const r=n.getBoundingClientRect();return r.width>=36 && r.height>=36 && r.left>=0 && r.right<=innerWidth;})")
    assert evaluate("document.documentElement.scrollWidth<=innerWidth")
    target = tmp_path / 'banking-390.png'
    target.write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format': 'png'})['data']))
    print(f'Visual artifact: {target}')
