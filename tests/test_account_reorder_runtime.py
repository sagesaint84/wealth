"""Actual Chrome DOM/controller tests with controlled long-press and PATCH promises."""
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
window.__order = {patches:[], pending:[], errors:[], timers:new Map(), fail:false};
const nativeTimeout=window.setTimeout, nativeClear=window.clearTimeout;
let nextTimer=-1;
window.setTimeout=function(fn,delay,...args){
  if(delay===450){const id=nextTimer--; __order.timers.set(id,()=>fn(...args));return id;}
  return nativeTimeout(fn,delay,...args);
};
window.clearTimeout=function(id){__order.timers.delete(id);return nativeClear(id);};
window.__press=()=>{const tasks=[...__order.timers.values()];__order.timers.clear();tasks.forEach(fn=>fn());};
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
// Only synthetic pointer events need capture stubs. Native gesture test keeps native methods.
if(!window.__nativeGesture){Element.prototype.setPointerCapture=function(){};Element.prototype.hasPointerCapture=()=>false;}
function draw(ids=['A1','A2','A3','A4']) {
  renderAccounts([...ids.map(id=>account(id)),account('B1','토스증권')]);
  renderSavings([saving('s1'),saving('s2'),saving('s3','신한은행')],
    [bank('b1'),bank('b2'),bank('b3','신한은행')],[loan('l1'),loan('l2'),loan('l3','신한은행')],'모두');
  document.getElementById('accountsPanel').scrollIntoView();
}
function groups(scope='securities',root=null){return [...document.querySelectorAll(root || (scope==='securities'?'#accountList > .broker-group':'#banksListWrap > .bank-institution-group'))];}
const row=id=>document.querySelector(`[data-order-id="${id}"]`);
const handle=node=>node.querySelector('.account-order-handle');
const ids=parent=>[...parent.children].filter(n=>n.dataset.orderId && n.dataset.orderDerived!=='true').map(n=>n.dataset.orderId);
function pointer(type,target,x,y,kind='mouse') {const event=new PointerEvent(type,{bubbles:true,cancelable:true,pointerId:123,pointerType:kind,isPrimary:true,button:0,clientX:x,clientY:y});target.dispatchEvent(event);return event;}
function start(node,kind='mouse') {const h=handle(node),r=h.getBoundingClientRect();pointer('pointerdown',h,r.x+r.width/2,r.y+r.height/2,kind);return h;}
function dragTo(node,target,kind='mouse',release=true) {
  const h=start(node,kind); if(kind==='touch')__press();
  const r=target.getBoundingClientRect();pointer('pointermove',h,r.x+10,r.bottom-2,kind);
  if(release)pointer('pointerup',h,r.x+10,r.bottom-2,kind);return h;
}
async function resolveSave(){check(__order.pending.length===1,'one pending save');__order.pending.shift()();for(let i=0;i<8;i++)await Promise.resolve();}
draw();
"""

SCENARIOS = {
    'lock_desktop': r"""
      check(!document.getElementById('accountOrderLock').disabled,'order loaded');
      check(document.getElementById('accountOrderLock').getAttribute('aria-pressed')==='false','initial locked');
      dragTo(groups()[0],groups()[1]);check(__order.patches.length===0,'locked no PATCH');
      document.getElementById('accountOrderLock').click();
      check(!handle(groups()[0]).hidden,'unlocked handle');
      dragTo(groups()[0],groups()[1]);
      equals(__order.patches[0],{scope:'securities',level:'institutions',order:['toss','kb']},'group PATCH');
      await resolveSave();equals(groups().map(n=>n.dataset.orderKey),['toss','kb'],'group visual order');
      document.getElementById('accountOrderLock').click();
      check(handle(groups()[0]).hidden,'locked handles hidden');
      dragTo(groups()[0],groups()[1]);check(__order.patches.length===1,'relocked no PATCH');
    """,
    'children_owner_rerender': r"""
      draw(['A1','A3']);document.getElementById('accountOrderLock').click();
      dragTo(row('A1'),row('A3'));
      equals(__order.patches[0],{scope:'securities',level:'accounts',kind:'accounts',institution:'kb',order:['A3','A1']},'partial child PATCH');
      await resolveSave();equals(__order.saved.securities.accounts.kb,['A3','A2','A1','A4'],'hidden positions');
      draw();equals(ids(row('A1').parentElement),['A3','A2','A1','A4'],'rerender persisted');
      draw(['A1','A3','NEW']);equals(ids(row('A1').parentElement),['A3','A1','NEW'],'new appended no stale DOM');
      const before=__order.patches.length;dragTo(row('A1'),row('B1'));
      check(__order.patches.length===before,'cross broker drop blocked');
      renderAccounts([account('A1'),account('NEW','kb증권')]);
      check(groups().length===1,'known broker alias does not create duplicate group');
      equals(ids(row('A1').parentElement),['A1','NEW'],'new alias account appended');
    """,
    'banking': r"""
      switchAccountCategory('banking');document.getElementById('accountOrderLock').click();
      const derived=document.querySelector('[data-order-derived="true"]');
      check(!derived.querySelector('.account-order-handle'),'derived non-draggable');
      for(const [first,last,kind] of [['b1','b2','bank_accounts'],['s1','s2','savings_accounts'],['l1','l2','loan_accounts']]){
        dragTo(row(first),row(last));
        const operation=__order.patches.at(-1);equals(operation,{scope:'banking',level:'accounts',kind,institution:'국민은행',order:[last,first]},kind+' PATCH');
        await resolveSave();equals(ids(row(first).parentElement),[last,first],kind+' visual order');
        if(kind==='bank_accounts')equals([...document.querySelectorAll('#loansGrid [data-order-derived="true"]')].map(n=>n.dataset.orderId),['b2','b1'],'derived follows underlying bank order');
      }
      dragTo(groups('banking')[0],groups('banking')[1]);await resolveSave();
      equals(__order.patches.at(-1),{scope:'banking',level:'institutions',order:['신한은행','국민은행']},'shared institution PATCH');
      for(const root of ['banksListWrap','savingsGrid','loansGrid'])equals([...document.querySelectorAll('#'+root+' > section')].map(n=>n.dataset.orderKey),['신한은행','국민은행'],'common order '+root);
      switchAccountCategory('insurance');check(document.getElementById('accountOrderLock').hidden,'insurance disabled');
      switchAccountCategory('real_estate');check(document.getElementById('accountOrderLock').hidden,'property disabled');
    """,
    'touch_cancel_lock_controls': r"""
      document.getElementById('accountOrderLock').click();
      let h=start(row('A1'),'touch'),r=h.getBoundingClientRect();
      pointer('pointerup',h,r.x,r.y,'touch');__press();check(__order.patches.length===0,'quick tap');
      h=start(row('A1'),'touch');r=h.getBoundingClientRect();
      const move=pointer('pointermove',h,r.x,r.y+20,'touch');check(!move.defaultPrevented,'ordinary scroll not prevented');
      __press();check(!document.querySelector('.account-order-dragged'),'movement cancels timer');
      h=start(row('A1'),'touch');__press();check(row('A1').classList.contains('account-order-dragged'),'long press activated');
      pointer('pointercancel',h,0,0,'touch');check(!document.querySelector('.account-order-dragged'),'pointercancel cleanup');
      h=dragTo(row('A1'),row('A4'),'mouse',false);document.getElementById('accountOrderLock').click();
      pointer('pointerup',h,0,0);check(__order.patches.length===0,'lock cancels drag');
      document.getElementById('accountOrderLock').click();
      for(const selector of ['[data-account-edit-id]','[data-account-del-id]','[data-toggle-tax-account-id]']){
        const control=row('A1').querySelector(selector);check(control,'normal control exists');
        pointer('pointerdown',control,0,0);pointer('pointermove',control,0,50);pointer('pointerup',control,0,50);
        check(!document.querySelector('.account-order-dragged'),'normal control cannot drag');
      }
      check(__order.patches.length===0,'normal controls no reorder PATCH');
    """,
    'failure_sequencing': r"""
      document.getElementById('accountOrderLock').click();
      __order.fail=true;dragTo(row('A1'),row('A4'));
      dragTo(row('A2'),row('A4'));check(__order.patches.length===1,'overlapping drop disabled');
      await resolveSave();equals(ids(row('A1').parentElement),['A1','A2','A3','A4'],'failure restored');
      check(__order.errors.some(e=>e.error && e.text.includes('저장에 실패')),'failure toast');
      dragTo(row('A1'),row('A4'));await resolveSave();
      dragTo(row('A2'),row('A4'));await resolveSave();
      equals(ids(row('A1').parentElement),['A3','A4','A2','A1'],'serialized saves');
    """,
    'themes_mobile': r"""
      document.getElementById('accountOrderLock').click();
      for(const theme of ['purple','oled','white']) {
        document.documentElement.dataset.theme=theme;
        const h=handle(row('A1')),r=h.getBoundingClientRect();
        check(r.width>=30 && r.height>=30,'usable handle '+theme);
        check(r.left>=0 && r.right<=innerWidth,'handle fits viewport '+theme);
        check(getComputedStyle(h).touchAction==='pan-y','scroll-capable touch action');
      }
      check(!document.body.textContent.includes('123456789012'),'full account number not exposed');
    """,
    'keyboard_autoscroll': r"""
      document.getElementById('accountOrderLock').click();
      handle(row('A1')).dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}));
      await resolveSave();equals(ids(row('A1').parentElement),['A2','A1','A3','A4'],'keyboard same broker order');
      draw(Array.from({length:30},(_,i)=>'A'+(i+1)));
      const scroll=document.getElementById('accountList');scroll.style.maxHeight='220px';scroll.style.overflowY='auto';scroll.scrollTop=0;
      const queued=new Map();let counter=0;const raf=window.requestAnimationFrame,caf=window.cancelAnimationFrame;
      window.requestAnimationFrame=fn=>{queued.set(++counter,fn);return counter;};window.cancelAnimationFrame=id=>queued.delete(id);
      const h=start(row('A1')),box=scroll.getBoundingClientRect();
      pointer('pointermove',h,box.x+20,box.bottom-5);
      check(queued.size>0,'autoscroll tick scheduled');
      const tasks=[...queued.values()];queued.clear();tasks.forEach(fn=>fn());
      check(scroll.scrollTop>0,'container scrolls near edge');
      pointer('pointercancel',h,0,0);check(!document.querySelector('.account-order-dragged'),'autoscroll cleaned');
      window.requestAnimationFrame=raf;window.cancelAnimationFrame=caf;
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
    assert 'touch-action:none' not in (root / 'wealth-account-reorder.css').read_text()


def test_native_touch_long_press_preserves_swipe_and_allows_drag(chrome_preview):
    call, evaluate, port = chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument', {'source': BOOT + "\nwindow.__nativeGesture=true;window.__nativeTrace=[];for(const name of ['pointerdown','pointercancel','pointerup'])document.addEventListener(name,e=>__nativeTrace.push([name,e.target.className,e.clientX,e.clientY]));"})
    call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
    call('Emulation.setTouchEmulationEnabled', {'enabled': True, 'maxTouchPoints': 1})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#assets'})
    wait_for(evaluate, "document.readyState==='complete' && typeof renderSavings==='function' && !document.getElementById('accountOrderLock').disabled")
    evaluate('(()=>{' + HELPERS + "draw(['A1','A3']);document.getElementById('accountOrderLock').click();return true;})()")
    def point(selector, bottom=False):
        return evaluate(f"(()=>{{const node=document.querySelector({json.dumps(selector)});{'node.scrollIntoView({block: \"center\",behavior:\"instant\"});' if not bottom else ''}const r=node.getBoundingClientRect();return {{x:r.x+10,y:r.{'bottom-4' if bottom else 'y+15'}}};}})()")
    def touch(kind, position=None):
        call('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': [] if position is None else [position]})
    start = point('[data-order-id="A1"] .account-order-handle')
    touch('touchStart', start); touch('touchEnd')
    evaluate('__press()')
    assert evaluate('__order.patches.length') == 0
    # Run the long press before the swipe, so swipe momentum cannot move the
    # target between querying its position and dispatching the next gesture.
    start = point('[data-order-id="A1"] .account-order-handle')
    touch('touchStart', start)
    evaluate('__press()')
    assert evaluate("!!document.querySelector('.account-order-dragged')"), evaluate("({trace:__nativeTrace,timers:__order.timers.size,locked:document.getElementById('accountOrderLock').getAttribute('aria-pressed'),scrollY,rect:document.querySelector('[data-order-id=\"A1\"] .account-order-handle').getBoundingClientRect().toJSON()})")
    target = point('[data-order-id="A3"]', bottom=True)
    touch('touchMove', target)
    assert evaluate("!!document.querySelector('.account-order-dragged')"), 'native touch must not turn active drag into scrolling'
    touch('touchEnd')
    assert evaluate('__order.patches.length') == 1
    assert evaluate('__order.patches[0].order') == ['A3', 'A1']
    evaluate("(async()=>{__order.pending.shift()();for(let i=0;i<8;i++)await Promise.resolve();})()")
    start = point('[data-order-id="A1"] .account-order-handle')
    touch('touchStart', start)
    touch('touchMove', dict(x=start['x'], y=start['y'] + 50)); touch('touchEnd')
    evaluate('__press()')
    assert evaluate('__order.patches.length') == 1
    assert evaluate("!document.querySelector('.account-order-dragged')")


def test_banking_mobile_layout_and_visual_artifact(chrome_preview, tmp_path):
    call, evaluate, port = chrome_preview
    call('Page.addScriptToEvaluateOnNewDocument', {'source': BOOT})
    call('Emulation.setDeviceMetricsOverride', {'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True})
    call('Page.navigate', {'url': f'http://127.0.0.1:{port}/#assets'})
    wait_for(evaluate, "document.readyState==='complete' && typeof renderSavings==='function' && !document.getElementById('accountOrderLock').disabled")
    evaluate('(()=>{' + HELPERS + "switchAccountCategory('banking');document.getElementById('accountOrderLock').click();document.getElementById('bankSectionFree').scrollIntoView({block:'start',behavior:'instant'});return true;})()")
    assert evaluate("[...document.querySelectorAll('#banksListWrap .account-order-handle')].every(n=>{const r=n.getBoundingClientRect();return r.width>=30 && r.height>=30 && r.left>=0 && r.right<=innerWidth;})")
    target = tmp_path / 'banking-390.png'
    target.write_bytes(base64.b64decode(call('Page.captureScreenshot', {'format': 'png'})['data']))
    print(f'Visual artifact: {target}')
