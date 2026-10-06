"""Exercise real unified source functions with controlled overlapping responses."""
from pathlib import Path
import subprocess


def test_unified_pending_keys_retry_stale_owners_and_broker_filters():
    source = (Path(__file__).resolve().parents[1] / 'app/static/wealth-timeseries-unified.js').read_text(encoding='utf-8')
    functions = 'const pnlPending = new Map(); const dividendPending = new Map();\n'
    for start, end in [('async function pnlSource() {', 'async function renderPnl() {'),
                       ('async function dividendSource() {', 'async function renderDividend() {')]:
        functions += start + source.split(start, 1)[1].split(end, 1)[0] + '\n'
    script = r"""
const assert=require('node:assert/strict'), vm=require('node:vm');
let owner='A', trade='all', broker='all';
const calls=[];
const cache={pnl:{key:'',raw:[]},dividend:{key:'',dividend:[],interest:[]}};
const context={cache,currentOwnerValue:()=>owner,activePnlTradeType:()=>trade,
 activeBroker:()=>broker,api:url=>new Promise((resolve,reject)=>calls.push({url,resolve,reject}))};
vm.createContext(context); vm.runInContext(process.argv[1],context);
const rows=[{broker:'X',pnl_krw:1,amount_krw:1},{broker:'Y',pnl_krw:2,amount_krw:2}];
(async()=>{
 for(const [kind,fn] of [['pnl',context.pnlSource],['dividend',context.dividendSource]]){
  cache[kind].key=''; calls.length=0; owner='A'; broker='all';
  const requests=Array.from({length:12},()=>fn());
  assert.equal(calls.length,1);
  calls[0].resolve({records:rows,interest_records:rows}); await Promise.all(requests);
  broker='X'; const filtered=await fn();
  assert.equal((kind==='pnl'?filtered:filtered.dividend).length,1);
  assert.equal(calls.length,1); broker='all';
  owner='retry'; const failed=fn(); calls.at(-1).reject(Error('synthetic failure'));
  await assert.rejects(failed); const retry=fn();
  assert.equal(calls.length,3); calls.at(-1).resolve({records:rows}); await retry;
  calls.length=0; const pending=[];
  for(const name of ['A','B','C']){owner=name;pending.push(fn());}
  for(const name of ['C','B','A']){
   const call=calls.find(item=>item.url.includes('owner='+name));
   call.resolve({records:[{broker:name}],interest_records:[]});
   await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  }
  await Promise.all(pending); assert.equal(cache[kind].key,kind==='pnl'?'C|all':'C');
 }
 owner='C'; trade='stock'; const stock=context.pnlSource();
 assert(calls.at(-1).url.includes('trade_type=stock'));
 calls.at(-1).resolve({records:rows}); await stock;
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script, functions], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_shared_api_normalizes_queries_reuses_income_and_retries_failure():
    source = (Path(__file__).resolve().parents[1] / 'app/static/wealth.js').read_text(encoding='utf-8')
    functions = 'const startupReadPending = new Map();' + source.split('const startupReadPending = new Map();', 1)[1].split('const fetchJson = api;', 1)[0]
    script = r"""
const assert=require('node:assert/strict'), vm=require('node:vm');
const calls=[];
const context={URL,location:{origin:'http://localhost'},window:{location:{}},
 fetch:(url,options)=>new Promise((resolve,reject)=>calls.push({url,options,resolve,reject}))};
vm.createContext(context); vm.runInContext(process.argv[1],context);
const response={ok:true,status:200,json:async()=>({records:[]})};
(async()=>{
 const one=context.api('/api/actual-dividends?owner=A&year=all');
 const two=context.api('/api/actual-dividends?year=all&owner=A');
 assert.equal(calls.length,1);calls[0].resolve(response);await Promise.all([one,two]);
 await context.api('/api/actual-dividends?owner=A&year=all');assert.equal(calls.length,1);
 const family1=context.api('/api/family-members'),family2=context.api('/api/family-members');
 assert.equal(calls.length,2);calls[1].reject(Error('synthetic'));
 await Promise.all([assert.rejects(family1),assert.rejects(family2)]);
 const retry=context.api('/api/family-members');assert.equal(calls.length,3);
 calls[2].resolve(response);await retry;
 const write=context.api('/api/actual-dividends',{method:'POST'});calls[3].resolve(response);await write;
 const fresh=context.api('/api/actual-dividends?owner=A&year=all');
 assert.equal(calls.length,5);calls[4].resolve(response);await fresh;
 context.finishStartupIncomeReads();
 const afterStartup=context.api('/api/actual-dividends?owner=A&year=all');
 assert.equal(calls.length,6);calls[5].resolve(response);await afterStartup;
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(['node', '-e', script, functions], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_observer_recognizes_unified_empty_state_as_owned():
    source = (Path(__file__).resolve().parents[1] / 'app/static/wealth-timeseries-unified.js').read_text(encoding='utf-8')
    function = 'function hostNeedsUnified(hostId) {' + source.split('function hostNeedsUnified(hostId) {', 1)[1].split('function refreshVisiblePanZoom', 1)[0]
    script = r"""
const assert=require('node:assert/strict'), vm=require('node:vm');
const hosts={};
for(const name of ['wealth-unified-chart-shell','wealth-unified-empty','legacy']){
 hosts[name]={firstElementChild:{classList:{contains:value=>value===name}}};
}
const context={document:{getElementById:id=>hosts[id]}};
vm.createContext(context);vm.runInContext(process.argv[1],context);
assert.equal(context.hostNeedsUnified('wealth-unified-chart-shell'),false);
assert.equal(context.hostNeedsUnified('wealth-unified-empty'),false);
assert.equal(context.hostNeedsUnified('legacy'),true);
assert.equal(context.hostNeedsUnified('missing'),false);
"""
    result = subprocess.run(['node', '-e', script, function], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
