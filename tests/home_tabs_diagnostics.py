"""One-shot synthetic render diagnostics; never a replacement performance gate.

Run: PYTHONPATH=.;tests python -m tests.home_tabs_diagnostics
Only temporary static copies are instrumented. App source, old measurements,
financial stores and environment files are never rewritten by this tool.
"""
from pathlib import Path
import gzip
import json
import shutil
import subprocess
import tempfile
from unittest.mock import patch
from tests.test_account_reorder_runtime import chrome_preview
from tests.test_home_three_tabs_chrome import BOOT, wait_for
from tests import test_static_transport_chrome as transport

ROOT=Path(__file__).resolve().parents[1]
BASE='940a42053297059dcbafdc837458876269958086'
ASSETS=['index.html','wealth-layout.js','wealth-layout.css','wealth-planning.js']
DIAG=r"""
window.__homeDiag={phase:'startup',counts:{},events:[],api:[],pending:0};
__homeDiag.note=function(kind,details={}){
 this.counts[kind]=(this.counts[kind]||0)+1;
 if(this.events.length<500)this.events.push({kind,phase:this.phase,t:performance.now(),...details});
};
__homeDiag.invoke=function(kind,work,details={}){
 const start=performance.now();try{return work();}finally{this.note(kind,{...details,ms:performance.now()-start});}
};
const diagFetch=fetch;
window.fetch=function(url,options={}){
 const path=new URL(String(url),location.href).pathname;
 if(!path.startsWith('/api/'))return diagFetch.apply(this,arguments);
 __homeDiag.api.push({path,method:options.method||'GET',phase:__homeDiag.phase});
 __homeDiag.pending++;
 return Promise.resolve(diagFetch.apply(this,arguments)).finally(()=>__homeDiag.pending--);
};
addEventListener('wealth:view',e=>__homeDiag.note('view',{detail:e.detail}));
"""


def replace_once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)


def instrument(directory):
    path=directory/'wealth-planning.js'
    source=path.read_text(encoding='utf-8')
    source=replace_once(source,'  function renderHistory() {',"""  function renderHistory() {
    return __homeDiag.invoke('history-call',()=>renderHistoryImpl(),{visible:!!historyPanel.getClientRects().length});
  }
  function renderHistoryImpl() {""")
    source=replace_once(source,'    plot.innerHTML = ',"    __homeDiag.note('history-svg-write',{width:plot.clientWidth});\n    plot.innerHTML = ")
    path.write_text(source,encoding='utf-8')
    path=directory/'wealth-timeseries-unified.js'
    source=path.read_text(encoding='utf-8')
    source=replace_once(source,'  function renderStateChart(host, aggregated, options = {}) {',"""  function renderStateChart(host, aggregated, options = {}) {
    return __homeDiag.invoke('unified-'+options.kind,()=>renderStateChartImpl(host,aggregated,options),{visible:!!host?.getClientRects().length});
  }
  function renderStateChartImpl(host, aggregated, options = {}) {""")
    path.write_text(source,encoding='utf-8')


def settle(evaluate):
    evaluate('new Promise(async resolve=>{for(let i=0;i<8;i++)await new Promise(requestAnimationFrame);resolve(true);})')
    wait_for(evaluate,'__homeDiag.pending===0')


def snapshot(call,evaluate):
    row=evaluate("""({phase:__homeDiag.phase,counts:{...__homeDiag.counts},api:__homeDiag.api.slice(),
      ids:[...document.querySelectorAll('[id]')].length,
      historySvg:document.querySelectorAll('#wealthHistoryPlot svg').length,
      hiddenHistory:!document.querySelector('#wealthHistoryPlot').getClientRects().length,
      tabButtons:document.querySelectorAll('#homeTabs [role=tab]').length,errors:__tabs.errors.slice()})""")
    row['metrics']={m['name']:m['value'] for m in call('Performance.getMetrics')['metrics'] if m['name'] in ['ScriptDuration','LayoutDuration','RecalcStyleDuration','Nodes','JSEventListeners']}
    return row


def inspect(directory,variant):
    fixture=chrome_preview.__wrapped__()
    call,evaluate,_=next(fixture)
    try:
        call('Page.addScriptToEvaluateOnNewDocument',{'source':BOOT+DIAG})
        call('Emulation.setDeviceMetricsOverride',{'width':360,'height':900,'deviceScaleFactor':1,'mobile':True})
        call('Performance.enable')
        call('Network.setBypassServiceWorker',{'bypass':True})
        call('Network.setCacheDisabled',{'cacheDisabled':True})
        with patch.object(transport,'STATIC',directory):
            with transport.transport_server(True) as port:
                call('Page.navigate',{'url':f'http://127.0.0.1:{port}/#home'})
                wait_for(evaluate,'document.readyState==="complete" && WealthStartup.canRead() && !!window.WealthUnifiedTimeseries && !!document.querySelector("#wealthHistoryPlot")')
                settle(evaluate)
                rows=[snapshot(call,evaluate)]
                if variant=='candidate':
                    for phase,tab in [('history-first','history'),('portfolio-return','portfolio'),('history-second','history'),('markets-first','markets'),('portfolio-second','portfolio'),('markets-second','markets')]:
                        evaluate(f'__homeDiag.phase={json.dumps(phase)};document.getElementById("homeTab-{tab}").click()')
                        wait_for(evaluate,f'document.getElementById("homeTab-{tab}").getAttribute("aria-selected")==="true"')
                        settle(evaluate)
                        rows.append(snapshot(call,evaluate))
                return {'variant':variant,'snapshots':rows,'events':evaluate('__homeDiag.events')}
    finally:
        try:next(fixture)
        except StopIteration:pass


def main():
    sizes=[]
    with tempfile.TemporaryDirectory(prefix='wealth-home-tabs-diagnostics-') as temporary:
        roots={}
        for variant in ['main','candidate']:
            directory=Path(temporary)/variant
            shutil.copytree(transport.STATIC,directory)
            roots[variant]=directory
            if variant=='main':
                for asset in ASSETS:
                    data=subprocess.check_output(['git','show',f'{BASE}:app/static/{asset}'],cwd=ROOT)
                    (directory/asset).write_bytes(data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        for asset in ASSETS:
            data={v:(p/asset).read_bytes() for v,p in roots.items()}
            sizes.append({'asset':asset,**{v:{'raw_bytes':len(b),'gzip5_bytes':len(gzip.compress(b,compresslevel=5,mtime=0))} for v,b in data.items()}})
        observations=[]
        for variant,directory in roots.items():
            instrument(directory)
            observations.append(inspect(directory,variant))
    print(json.dumps({'purpose':'diagnostic only; single fresh Chromium per variant; 360px mobile; CPU/network unthrottled; invented nonempty history; instrumented temporary copies; not comparable to prior timed gate and never replaces it','baseline':BASE,'candidate_parent':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'sizes':sizes,'observations':observations},indent=2))


if __name__=='__main__':main()
