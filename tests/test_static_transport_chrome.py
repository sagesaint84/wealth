"""Actual Chromium + ASGI static transport, synthetic APIs only."""
import json
import statistics
import socket
import threading
import time
from contextlib import contextmanager

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from tests.chrome_harness import UNSAFE_PORTS
from tests.test_account_reorder_runtime import chrome_preview, wait_for
from tests.ui_preview import STATIC, DASHBOARD


@contextmanager
def transport_server(compressed=False):
    if compressed:
        from app.static_transport import CompressedStaticFiles
        static = CompressedStaticFiles(directory=STATIC)
    else:
        static = StaticFiles(directory=STATIC)
    async def page(request):
        name = request.path_params.get('name', 'index.html')
        return FileResponse(STATIC / name, headers={'Content-Security-Policy': "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'"})
    async def api(request):
        key = request.url.path
        data = {
            '/api/auth/me': {'username':'SYNTHETIC','role':'user','must_change_password':False},
            '/api/dashboard': DASHBOARD,
            '/api/planning': {'revision':0,'buckets':[],'accounts':{},'holdings':{},'history':[]},
            '/api/family-members': {'members':['아빠','엄마','자녀']},
            '/api/asset-records': {'records':[]}, '/api/market-overview':{'items':[]},
            '/api/actual-dividends': {'records':[], 'monthly':[], 'available_years':[]},
            '/api/realized-pnl': {'records':[], 'monthly':[], 'available_years':[]},
            '/api/ledger/cards': [], '/api/ledger':{'transactions':[], 'total_income':0,'total_expense':0},
            '/api/dividends': {'holdings':[], 'monthly':[]},
        }.get(key,{})
        return JSONResponse(data)
    app = Starlette(routes=[Route('/',page), Route('/dashboard',page),
        Route('/sw.js',lambda request: FileResponse(STATIC/'sw.js',media_type='application/javascript')),
        Route('/manifest.json',lambda request: FileResponse(STATIC/'manifest.json')),
        Mount('/static',static),Route('/api/{path:path}',api,methods=['GET','POST','PUT','DELETE'])])
    listener = socket.socket()
    for _ in range(32):
        listener.bind(('127.0.0.1',0))
        if listener.getsockname()[1] not in UNSAFE_PORTS: break
        listener.close(); listener=socket.socket()
    else: raise RuntimeError('No safe loopback port')
    listener.listen(128)
    port=listener.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',lifespan='off'))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
    thread.start(); deadline=time.monotonic()+10
    try:
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline, 'ASGI preview did not start'
            time.sleep(.01)
        yield port
    finally:
        server.should_exit=True; thread.join(10); listener.close()
        assert not thread.is_alive(), 'ASGI preview did not stop'


PROFILE = r"""
window.__transport={api:[],pending:0,visible:null,received:false,errors:[]};
window.addEventListener('error',e=>__transport.errors.push(e.message));
window.addEventListener('unhandledrejection',e=>__transport.errors.push(String(e.reason)));
const naturalFetch=window.fetch;
window.fetch=function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 if(!path.startsWith('/api/'))return naturalFetch.apply(this,arguments);
 const row={path,method:options.method||'GET',start:performance.now()};__transport.api.push(row);__transport.pending++;
 return naturalFetch.apply(this,arguments).then(response=>{
  if(path==='/api/dashboard')__transport.received=true;
  return response;
 }).finally(()=>{row.end=performance.now();__transport.pending--;});
};
new MutationObserver(()=>{
 const node=document.querySelector('#wealthAssetNetWorth');
 if(__transport.visible===null&&__transport.received&&node&&node.textContent.trim()&&!['—','-'].includes(node.textContent.trim())&&node.getClientRects().length)
  __transport.visible=performance.now();
}).observe(document,{subtree:true,childList:true,characterData:true});
"""


def measure(call,evaluate,port,width):
    call('Emulation.setDeviceMetricsOverride',{'width':width,'height':900,'deviceScaleFactor':1,'mobile':False})
    call('Emulation.setCPUThrottlingRate',{'rate':4 if width<500 else 1})
    call('Network.enable'); call('Performance.enable')
    call('Network.setCacheDisabled',{'cacheDisabled':True})
    call('Network.setBypassServiceWorker',{'bypass':True})
    call('Network.emulateNetworkConditions',{'offline':False,'latency':40 if width<500 else 20,
        'downloadThroughput':250000 if width<500 else 500000,'uploadThroughput':500000})
    if not getattr(evaluate, 'transport_instrumented', False):
        call('Page.addScriptToEvaluateOnNewDocument',{'source':PROFILE})
        evaluate.transport_instrumented=True
    previous_origin=evaluate('performance.timeOrigin')
    start_cpu=time.process_time()
    if evaluate('location.origin') == f'http://127.0.0.1:{port}':
        call('Page.reload',{'ignoreCache':True})
    else:
        call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
    wait_for(evaluate,f"performance.timeOrigin!=={previous_origin!r} && location.origin==='http://127.0.0.1:{port}' && document.readyState==='complete' && __transport.visible!==null && __transport.pending===0 && document.querySelector('#wealthIpoEventMonthsScript')?.dataset.loaded==='true' && !!window.WealthUnifiedTimeseries")
    info=evaluate("({visible:__transport.visible,ready:performance.now(),fcp:performance.getEntriesByType('paint').find(e=>e.name==='first-contentful-paint')?.startTime,summary:document.querySelector('#wealthAssetNetWorth').textContent,errors:__transport.errors,api:__transport.api,resources:performance.getEntriesByType('resource').filter(r=>/\\.(js|css)(\\?|$)/.test(r.name)).map(r=>({path:new URL(r.name).pathname,bytes:r.encodedBodySize,decoded:r.decodedBodySize,duration:r.duration}))})")
    info['python_cpu_ms']=(time.process_time()-start_cpu)*1000
    info['metrics']={item['name']:item['value'] for item in call('Performance.getMetrics')['metrics'] if item['name'] in ['ScriptDuration','LayoutDuration','RecalcStyleDuration','TaskDuration','JSHeapUsedSize','Nodes','JSEventListeners']}
    return info


@pytest.mark.parametrize('width',[1280,390])
def test_static_compression_transfer_and_startup(chrome_preview,width):
    call,evaluate,_=chrome_preview
    samples={}
    for compressed in (False,True):
        with transport_server(compressed) as port:
            samples[compressed]=[measure(call,evaluate,port,width) for _ in range(3)]
    raw=samples[False]; packed=samples[True]
    assert all(r['summary']==raw[0]['summary'] and not r['errors'] for r in raw+packed)
    assert statistics.median(r['visible'] for r in packed)<statistics.median(r['visible'] for r in raw)
    assert statistics.median(r['ready'] for r in packed)<statistics.median(r['ready'] for r in raw)
    raw_bytes=[sum(s['bytes'] for s in r['resources']) for r in raw]
    packed_bytes=[sum(s['bytes'] for s in r['resources']) for r in packed]
    assert min(raw_bytes)>1000000, raw_bytes
    assert max(packed_bytes)<min(raw_bytes)*.6, (raw_bytes,packed_bytes)
    for row in raw+packed:
        paths=[r['path'] for r in row['api']]
        assert paths.index('/api/refresh-prices')<paths.index('/api/dashboard')<paths.index('/api/planning/snapshot-all')
    print('WEALTH_STATIC_TRANSPORT_PERF='+json.dumps({'width':width,'samples':samples},ensure_ascii=False))
