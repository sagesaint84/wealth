"""Native Chrome link activation against synthetic IPO data and intercepted HTML."""
import base64
import json
from pathlib import Path
import subprocess
import urllib.request

import pytest

from tests.test_account_reorder_runtime import chrome_preview, wait_for


URL = 'https://metalogos.ai/160ipo/stock/B_SYNTHETIC'
TEXT = '160 원문 · 매력지수 86 · 수요예측기관 2,269 · 확약기관 636 · 유통가능 23.33%'
FRAMES = '(async()=>{for(let i=0;i<4;i++)await new Promise(requestAnimationFrame);return true;})()'
SETUP = r'''(async()=>{
window.__ipo={ipo_id:'synthetic-ms',company_name:'엠에스바이오',
subscription_start:'2026-10-12',subscription_end:'2026-10-13',filter_group:'CURRENT',
presentation_sort_date:'2026-10-12',lead_managers:['KB증권'],
score:{score:null,is_calculating:true,coverage:60,core_missing:['tradable_share_ratio']},
sources:{metalogos160:{url:'https://metalogos.ai/160ipo/stock/B_SYNTHETIC',
attractiveness_score:86,demand_participant_count_reference:2269,
lockup_participant_count_reference:636,tradable_share_ratio_reference:23.33}}};
window.fetchJson=async()=>({ipos:[__ipo]});
WealthIpoState.setMarketIpos([__ipo]);WealthIpoState.setFilterGroup('ALL');
WealthIpoState.setHistoryYear(2026);WealthIpoState.setHistoryMonth(10);
WealthIpoState.setMonthExplicitlySelected(true);WealthIpoState.renderIpoList();
document.getElementById('ipoRefreshBtn').dispatchEvent(new Event('click',{bubbles:true}));
for(let i=0;i<6;i++)await new Promise(requestAnimationFrame);
document.querySelector('.ipo-card-detail-toggle').click();
for(let i=0;i<4;i++)await new Promise(requestAnimationFrame);
document.querySelector('.ipo-metalogos-reference a').scrollIntoView({block:'center'});
window.__events=[];
for(const type of ['pointerdown','click'])document.addEventListener(type,e=>{
  if(type==='pointerdown')window.__pressed=e.target;
  __events.push({type,target:e.target.tagName,prevented:e.defaultPrevented});
});return true;})()'''


class Browser:
    """Pause new pages before loading; fulfill Metalogos requests locally.

    This observes standard target=_blank navigation, never calling window.open
    or reading a public detail page. All waits consume CDP responses/events.
    """
    def __init__(self, connection):
        self.connection = connection
        self.responses = {}
        self.sessions = {}
        self.requests = []
        self.sequence = 0

    def call(self, method, params=None, session=None):
        self.sequence += 1
        ident = self.sequence
        message = {'id':ident, 'method':method, 'params':params or {}}
        if session:
            message['sessionId'] = session
        self.connection.send(json.dumps(message))
        while ident not in self.responses:
            self.consume(json.loads(self.connection.recv()))
        result = self.responses.pop(ident)
        assert 'error' not in result, result
        return result.get('result', {})

    def consume(self, message):
        if 'id' in message:
            self.responses[message['id']] = message
        elif message.get('method') == 'Target.attachedToTarget':
            params = message['params']
            session = params['sessionId']
            self.sessions[params['targetInfo']['targetId']] = session
            self.call('Fetch.enable', {'patterns':[
                {'urlPattern':'https://metalogos.ai/*'},
                {'urlPattern':'https://www.metalogos.ai/*'}]}, session)
            self.call('Runtime.runIfWaitingForDebugger', session=session)
        elif message.get('method') == 'Fetch.requestPaused':
            params = message['params']
            self.requests.append(params['request']['url'])
            html = '<html><body>synthetic Metalogos page<script>window.__synthetic=true</script></body></html>'
            self.call('Fetch.fulfillRequest', {'requestId':params['requestId'],
                'responseCode':200, 'responseHeaders':[{'name':'Content-Type','value':'text/html'}],
                'body':base64.b64encode(html.encode()).decode()}, message['sessionId'])

    def close(self):
        self.connection.close()


@pytest.fixture
def reference_browser(monkeypatch, request):
    profile = []
    native = subprocess.Popen

    def launch(args, **kwargs):
        for arg in args:
            if str(arg).startswith('--user-data-dir='):
                profile.append(str(arg).split('=',1)[1])
        # Even a broken interception must not contact external services.
        args = [*args, '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1']
        return native(args, **kwargs)

    monkeypatch.setattr(subprocess, 'Popen', launch)
    preview = request.getfixturevalue('chrome_preview')
    port = (Path(profile[0]) / 'DevToolsActivePort').read_text().splitlines()[0]
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=5) as response:
        url = json.load(response)['webSocketDebuggerUrl']
    websocket = pytest.importorskip('websocket')
    browser = Browser(websocket.create_connection(url, timeout=30))
    try:
        yield *preview, browser
    finally:
        browser.close()


@pytest.mark.parametrize('width', [1280,390])
def test_reference_line_and_native_external_link(reference_browser, width):
    call, evaluate, port, browser = reference_browser
    call('Emulation.setDeviceMetricsOverride', {'width':width,'height':900,'deviceScaleFactor':1,'mobile':False})
    call('Page.navigate', {'url':f'http://127.0.0.1:{port}/#ipo'})
    wait_for(evaluate, "document.readyState==='complete' && !!window.WealthIpoState")
    evaluate(SETUP)
    geometry = evaluate(r'''(()=>{
      const a=document.querySelector('.ipo-metalogos-reference a'), row=a.parentElement,
      r=a.getBoundingClientRect(), rr=row.getBoundingClientRect(), card=a.closest('.ipo-card').getBoundingClientRect();
      const range=document.createRange();range.selectNodeContents(row.lastElementChild);
      return {x:r.x+r.width/2,y:r.y+r.height/2,href:a.href,target:a.target,rel:a.rel,
      pointer:getComputedStyle(a).pointerEvents,hit:document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)===a,
      text:row.textContent,whiteSpace:getComputedStyle(row).whiteSpace,
      metricRects:[...range.getClientRects()].map(r=>({y:r.y,height:r.height})),linkY:r.y,
      left:rr.left,right:rr.right,cardRight:card.right,overflow:getComputedStyle(row).overflowX,
      rowWidth:row.clientWidth,textWidth:row.scrollWidth,pageWidth:document.documentElement.scrollWidth};})()''')
    assert geometry['text'] == TEXT
    assert geometry['href'] == URL
    assert geometry['target'] == '_blank'
    assert set(geometry['rel'].split()) == {'noopener','noreferrer'}
    assert geometry['hit'] is True
    assert geometry['pointer'] != 'none'
    assert geometry['whiteSpace'] == 'nowrap'
    assert all(abs(rect['y']-geometry['linkY']) < 1 for rect in geometry['metricRects'])
    assert geometry['right'] <= width
    assert geometry['right'] <= geometry['cardRight']
    assert geometry['overflow'] == 'auto'
    assert geometry['pageWidth'] <= width
    if width == 1280:
        assert geometry['textWidth'] <= geometry['rowWidth'], 'normal desktop card must show all values on one line'
    before = {target['targetId'] for target in browser.call('Target.getTargets')['targetInfos']}
    browser.call('Target.setAutoAttach', {'autoAttach':True,'waitForDebuggerOnStart':True,'flatten':True})
    call('Input.dispatchMouseEvent', {'type':'mousePressed','x':geometry['x'],'y':geometry['y'],'button':'left','clickCount':1})
    evaluate(FRAMES)
    assert evaluate('__pressed.isConnected'), 'observer replaced the anchor before native click completed'
    call('Input.dispatchMouseEvent', {'type':'mouseReleased','x':geometry['x'],'y':geometry['y'],'button':'left','clickCount':1})
    targets = browser.call('Target.getTargets')['targetInfos']
    popup = next((target for target in targets if target['targetId'] not in before and target['type']=='page'), None)
    assert popup is not None, evaluate('__events')
    session = browser.sessions[popup['targetId']]
    # Runtime returns after loading the intercepted document; poll controlled frames.
    for _ in range(20):
        loaded = browser.call('Runtime.evaluate', {'expression':
            '(async()=>{await new Promise(requestAnimationFrame);return {ready:!!window.__synthetic,url:location.href,opener:window.opener===null}})()',
            'awaitPromise':True,'returnByValue':True}, session)['result'].get('value')
        if loaded and loaded['ready']:
            break
    assert loaded == {'ready':True,'url':URL,'opener':True}
    assert URL in browser.requests
    events = evaluate('__events.filter(e=>e.target==="A")')
    assert [event['type'] for event in events] == ['pointerdown','click']
    assert all(not event['prevented'] for event in events)
    # Keep the popup until fixture teardown: a favicon interception can still
    # be queued, so closing the target here races its attached CDP session.
    call('Page.bringToFront')
    # Compact/expanded toggle remains usable and never exposes reference overflow.
    assert evaluate("(()=>{const c=document.querySelector('.ipo-card'),b=c.querySelector('.ipo-card-detail-toggle');b.click();const compact=!c.classList.contains('ipo-card-expanded');b.click();return compact&&c.classList.contains('ipo-card-expanded');})()")
