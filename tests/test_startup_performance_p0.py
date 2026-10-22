"""Synthetic startup scheduling/telemetry regressions. No real app or data imports."""
from pathlib import Path
import json
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'app/static/wealth.js'
BASE = 'bdb03220674943ea833b746add12b85cba8bf5b0'


def fragment(source, start, end):
    return start + source.split(start, 1)[1].split(end, 1)[0]


def startup_code(source, *, modern=True):
    api = fragment(source, 'const startupReadPending = new Map();', 'const fetchJson = api;')
    coordinator = (source.split('// Opt-in synthetic profiling only:', 1)[1].split('const startupReadPending = new Map();', 1)[0]
        if modern else '')
    # The first line after the comment is prose, not executable JavaScript.
    if modern:
        coordinator = coordinator[coordinator.index('globalThis.WealthStartup ='):]
    return coordinator + api + fragment(source, 'async function loadDashboard(recordSnapshots = false) {', '\nasync function loadAssetRecords') + fragment(
        source, 'async function initAuthSession() {', '\nasync function handleForcePasswordSubmit')


HARNESS = r"""
const assert = require('node:assert/strict'), vm = require('node:vm');
function deferred(){let resolve; const promise=new Promise(r=>resolve=r); return {promise,resolve};}
const flush = async()=>{for(let i=0;i<30;i++) await Promise.resolve();};
async function scenario(code, modern, mode='ok', role='user') {
 const calls=[], renders=[], notices=[], phase=[];
 const prices=deferred(), snapshot=deferred(), family=deferred();
 const shown=new Set(['wealthNetWorth','marketGrid','summaryRealizedPnl']);
 const nodes={};
 function node(id){return nodes[id] ||= {style:{setProperty(){}},open:false,
   getClientRects:()=>shown.has(id)?[{}]:[],addEventListener(){},setAttribute(){},showModal(){this.open=true;}};}
 const c={URL,location:{origin:'http://synthetic.invalid'},__WEALTH_SYNTHETIC_PERF__:true,
   performance:{now:()=>phase.length,clearMarks(){},mark:n=>phase.push(n)},
   currentOwner:'SYNTHETIC_PRIVATE_OWNER',currentUserProfile:null,
   selectedDividendYear:'2026',selectedPnlYear:'2026',currentPnlTradeType:'all',currentDividendMode:'actual',
   currentLedgerYear:2026,currentLedgerMonth:10,rawDashboard:null,dashboard:null,
   document:{getElementById:node,querySelector:()=>null},console:{log(){},warn(){},error(){}},
   CustomEvent:class {constructor(type){this.type=type;}},
   toast:message=>notices.push(message),refreshAdminUserList:async()=>{},
   loadFamilyMembers:()=>family.promise,
   renderWithOwner:data=>{renders.push(data);c.WealthStartup?.count('render');},
 };
 c.window={dispatchEvent(){},location:{}};
 c.loadMarkets=()=>c.api('/api/market-overview');
 c.loadAssetRecords=()=>c.api('/api/asset-records');
 c.loadLedger=()=>c.api('/api/ledger?year=2026');
 c.loadDividends=()=>c.api('/api/dividends');
 c.loadActualDividends=()=>c.api('/api/actual-dividends?year=2026');
 c.loadRealizedPnl=()=>c.api('/api/realized-pnl?year=2026');
 c.updateOverviewCardsAllTime=()=>Promise.all([
   c.api('/api/actual-dividends?year=all'),c.api('/api/realized-pnl?year=all')]);
 c.fetch=async(url)=>{
   calls.push(url);
   if(url==='/api/refresh-prices') await prices.promise;
   if(url==='/api/planning/snapshot-all') await snapshot.promise;
   const failed=(mode==='prices-fail' && url==='/api/refresh-prices') || (mode==='snapshot-fail' && url==='/api/planning/snapshot-all');
   return {ok:!failed,status:failed?500:200,json:async()=>url==='/api/auth/me'
     ? {username:role==='admin'?'admin':'synthetic',must_change_password:role==='forced'}
     : url.startsWith('/api/dashboard')?{summary:{total_value_krw:12345}}:{}};
 };
 vm.createContext(c);vm.runInContext(code,c);
 const auth=c.initAuthSession(); await flush();
 if(role!=='user') {
   assert.equal(await auth,true === (role==='admin'));
   assert.deepEqual(calls,['/api/auth/me']);
   assert.equal(renders.length,0);
   assert.equal(c.WealthStartup.canRead(),false);
   if(role==='forced') assert.equal(node('forcePasswordModal').open,true);
   return;
 }
 if(modern){void c.loadAssetDataForUser();await flush();}
 assert.equal(calls.filter(x=>x==='/api/refresh-prices').length,1);
 assert(!calls.some(x=>x.startsWith('/api/dashboard')));
 if(!modern) family.resolve();
 prices.resolve(); await flush();
 assert.equal(renders.length,1,'valid dashboard must render while secondary stores are pending');
 assert(calls.includes(mode==='prices-fail'?'/api/dashboard':'/api/dashboard?record_snapshots=true'));
 if(mode!=='prices-fail') {
   assert(calls.includes('/api/planning/snapshot-all'));
   assert(!calls.includes('/api/market-overview'),'dependent supplementary reads wait for recording');
 }
 snapshot.resolve(); await auth; await flush();
 family.resolve(); await c.loadAssetDataForUser.supplementary; await flush();
 assert.equal(calls.filter(x=>x.startsWith('/api/dashboard')).length,1);
 assert.equal(calls.filter(x=>x==='/api/planning/snapshot-all').length,mode==='prices-fail'?0:1);
 if(modern){
   assert(!calls.includes('/api/actual-dividends?year=2026'));
   assert(!calls.includes('/api/realized-pnl?year=2026'));
   assert(!calls.some(x=>x.startsWith('/api/ledger')));
   const trace=c.WealthStartup.snapshot();
   const text=JSON.stringify(trace);
   assert(!text.includes('SYNTHETIC_PRIVATE_OWNER') && !text.includes('12345') && !text.includes('/api/'));
   assert.equal(trace.counters['dashboard:visible'],1);
   assert.equal(trace.counters['inactive_request'] || 0,0);
   assert.equal(trace.counters['aux_request'],3);
   assert.equal(trace.counters['auth:start'],1);assert.equal(trace.counters['auth:end'],1);
   assert.equal(trace.counters['prices:start'],1);assert.equal(trace.counters['prices:end'],1);
   assert.equal(trace.counters['snapshot:start'] || 0,mode==='prices-fail'?0:1);
   assert.equal(trace.counters['snapshot:end'] || 0,mode==='prices-fail'?0:1);
   for(let i=0;i<200;i++)c.WealthStartup.count('render');
   assert.equal(c.WealthStartup.snapshot().events.length,128);
   // A tab first opened after startup fetches its own details; hidden stores stay untouched.
   shown.clear();shown.add('ledgerSectionPanel');await c.WealthStartup.loadVisible();
   assert(calls.includes('/api/ledger?year=2026'));
 }
 return calls;
}
"""


def run(script, *args):
    # Source fragments in args can also exceed Windows' command-line limit.
    # Restore node -e's argv layout before evaluating the unchanged test script.
    bootstrap = (
        "const stdinPayload=JSON.parse(require('node:fs').readFileSync(0,'utf8'));"
        "process.argv.splice(1,process.argv.length-1,...stdinPayload.args);"
        "eval(stdinPayload.script);"
    )
    result = subprocess.run(['node','-e',bootstrap],input=json.dumps({'script':script,'args':args}),
        capture_output=True,text=True,encoding='utf-8')
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('late_install', [False, True])
def test_income_filter_install_is_lazy_and_active_reads_remain_scoped(late_install):
    source = SOURCE.read_text(encoding='utf-8')
    shared_api = fragment(source, 'const startupReadPending = new Map();', 'const fetchJson = api;')
    core = (ROOT/'app/static/wealth-period-filter-core.js').read_text(encoding='utf-8')
    filters = (ROOT/'app/static/wealth-income-period-broker-filter.js').read_text(encoding='utf-8')
    run(r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const late=process.argv[4]==='True',calls=[],renders=[],nodes={},guardChecks=[],errors=[];
const workspace={dataset:{activeView:'income',incomeTab:late?'dividend':'calendar'}};
const incomePage={hidden:false};
function element(id=''){
 const classes=new Set();
 return {id,style:{},value:'',innerHTML:'',listeners:{},hidden:false,
  classList:{contains:name=>classes.has(name),toggle:(name,on)=>on?classes.add(name):classes.delete(name)},
  setAttribute(){},addEventListener(type,fn){this.listeners[type]=fn;},
  appendChild(child){nodes[child.id]=child;child.parentElement=this;},
  getClientRects(){
   return !incomePage.hidden && !nodes.dividendPanel.hidden
    && !nodes.dividendPanel.classList.contains('wealth-income-hidden')?[{}]:[];
  }};
}
for(const id of ['dividendPanel','dividendYearSelect','pnlYearSelect'])nodes[id]=element(id);
nodes.dividendYearSelect.parentElement=element();nodes.pnlYearSelect.parentElement=element();
const c={URL,location:{origin:'http://synthetic.invalid',hash:late?'#dividend':'#income'},currentOwner:'A',
 currentIncomeTab:late?'dividend':'calendar',
 selectedDividendYear:'2026',selectedDividendMonth:null,currentDividendMode:'actual',
 actualDividendData:null,pnlData:null,console:{error(...args){errors.push(args);}},
 document:{readyState:'complete',body:{},getElementById:id=>nodes[id]||null,
  querySelector:selector=>selector==='.wealth-workspace'?workspace:selector==='[data-wealth-page=income]'?incomePage:null,
  createElement:()=>element(),addEventListener(){}},
 MutationObserver:class {observe(){}},loadActualDividends(){},
 WealthStartup:{visible(id){
  const visible=!!nodes[id]?.getClientRects().length;
  guardChecks.push({hash:c.location.hash,activeView:workspace.dataset.activeView,
   incomeTab:workspace.dataset.incomeTab,incomeHidden:incomePage.hidden,
   panelHidden:nodes.dividendPanel.hidden,panelInactive:nodes.dividendPanel.classList.contains('wealth-income-hidden'),
   currentIncomeTab:c.currentIncomeTab,mode:c.currentDividendMode,owner:c.currentOwner,year:c.selectedDividendYear,
   visible,reason:visible?'active':'hidden-income-page-or-dividend-panel'});
  return visible;
 },count(){},request(){}},
 renderActualDividends:data=>renders.push(data),updateDividendYearOptions:years=>c.years=years,
 // Keep the extracted api()/apiRequest() implementation and observe its actual
 // fetch boundary; a mock named apiRequest would be overwritten by its declaration.
 fetch:(url,options)=>new Promise((resolve,reject)=>calls.push({url,options,
  resolve:data=>resolve({status:200,ok:true,json:async()=>data}),reject}))};
function setDividendVisible(visible){
 c.location.hash=visible?'#dividend':'#income';
 workspace.dataset.incomeTab=visible?'dividend':'calendar';
 c.currentIncomeTab=workspace.dataset.incomeTab;
 nodes.dividendPanel.classList.toggle('wealth-income-hidden',!visible);
}
setDividendVisible(late);
c.window=c;vm.createContext(c);
vm.runInContext(process.argv[1]+process.argv[2]+process.argv[3],c);
const rows=(name,amount=100)=>({records:[
 {date:'2026-04-08',code:'316140',broker:name,amount_krw:amount},
 {date:'2025-04-08',code:'005930',broker:'prior-year',amount_krw:900}],
 interest_records:[{date:'2026-04-09',broker:'interest-broker',amount_krw:20}]});
const clearCache=()=>vm.runInContext('startupIncomeReuse=false;allTimeReadCache.clear();',c);
(async()=>{
 if(late){
  assert.equal(calls.length,1,'late installation initializes only an already visible actual screen');
  calls[0].resolve(rows('late-broker'));
  for(let i=0;i<30;i++)await Promise.resolve();
  assert(nodes.dividendBrokerFilter.innerHTML.includes('late-broker'));
  assert.equal(c.actualDividendData.total_actual_dividend_krw,100);return;
 }
 assert.equal(calls.length,0,'calendar installation must not preload dividend income');
 assert.equal(c.currentIncomeTab,'calendar');assert.equal(c.location.hash,'#income');
 await c.loadActualDividends();assert.equal(calls.length,0,'hidden calls remain deferred');
 assert(guardChecks.some(check=>!check.visible&&check.panelInactive));
 setDividendVisible(true);
 const first=c.loadActualDividends(),joined=c.loadActualDividends();
 assert.equal(calls.length,1,'same active GETs share the existing API pending request; '+JSON.stringify({guardChecks,errors}));
 assert(guardChecks.at(-1).visible&&guardChecks.at(-1).incomeTab==='dividend');
 assert.equal(calls[0].options.credentials,'include','request reaches the real apiRequest fetch boundary');
 calls[0].resolve(rows('active-broker'));await Promise.all([first,joined]);
 assert.equal(c.actualDividendData.total_actual_dividend_krw,100);
 assert.equal(c.actualDividendData.total_actual_interest_krw,20);
 assert(c.years.includes('2025')&&c.years.includes('2026'));
 assert(nodes.dividendBrokerFilter.innerHTML.includes('active-broker'));
 assert(!nodes.dividendBrokerFilter.innerHTML.includes('prior-year'));
 nodes.dividendBrokerFilter.value='active-broker';nodes.dividendBrokerFilter.listeners.change();
 assert.equal(c.actualDividendData.records.length,1);assert.equal(c.actualDividendData.interest_records.length,0);
 clearCache();c.currentOwner='slow';const slow=c.loadActualDividends();
 c.currentOwner='fast';const fast=c.loadActualDividends();
 calls[2].resolve(rows('fast-broker',200));await fast;
 calls[1].resolve(rows('slow-broker',999));await slow;
 assert(calls[1].url.includes('owner=slow')&&calls[2].url.includes('owner=fast'));
 assert.equal(c.actualDividendData.total_actual_dividend_krw,200);
 assert(nodes.dividendBrokerFilter.innerHTML.includes('fast-broker'));
 assert(!nodes.dividendBrokerFilter.innerHTML.includes('slow-broker'));
 clearCache();const yearRequest=c.loadActualDividends();c.selectedDividendYear='2025';
 const beforeYear=renders.length;calls[3].resolve(rows('wrong-year'));await yearRequest;
 assert.equal(renders.length,beforeYear,'a previous-year response cannot redraw the current scope');
 c.selectedDividendYear='2026';clearCache();const leaving=c.loadActualDividends();
 setDividendVisible(false);const beforeLeaving=renders.length;calls[4].resolve(rows('hidden'));await leaving;
 assert.equal(renders.length,beforeLeaving,'leaving the screen ignores the late result');
 setDividendVisible(true);c.currentDividendMode='estimated';await c.loadActualDividends();
 assert.equal(calls.length,5,'estimated mode does not fetch actual detail');
 c.currentDividendMode='actual';clearCache();const empty=c.loadActualDividends();
 calls[5].resolve({records:[],interest_records:[]});await empty;
 assert.equal(c.actualDividendData.record_count,0);assert.equal(c.actualDividendData.total_actual_dividend_krw,0);
 assert(!nodes.dividendBrokerFilter.innerHTML.includes('fast-broker'));
 clearCache();const failed=c.loadActualDividends();calls[6].reject(Error('synthetic unavailable'));await failed;
 assert.equal(c.actualDividendData.record_count,0,'failure must not replace the current view with stale records');
})().catch(error=>{console.error(error);process.exitCode=1;});
""", shared_api, core, filters, str(late_install))


@pytest.mark.parametrize('mode',['ok','prices-fail','snapshot-fail'])
def test_startup_dashboard_and_both_recording_steps_keep_order_without_hidden_details(mode):
    run(HARNESS + "scenario(process.argv[1],true,process.argv[2]).catch(e=>{console.error(e);process.exitCode=1;});",
        startup_code(SOURCE.read_text(encoding='utf-8')),mode)


@pytest.mark.parametrize('role',['admin','forced'])
def test_privileged_or_forced_password_sessions_do_not_start_asset_work(role):
    run(HARNESS + "scenario(process.argv[1],true,'ok',process.argv[2]).catch(e=>{console.error(e);process.exitCode=1;});",
        startup_code(SOURCE.read_text(encoding='utf-8')),role)


def test_same_synthetic_scenario_compares_v212_request_counts_without_claiming_real_latency():
    baseline = subprocess.run(['git','show',BASE+':app/static/wealth.js'],cwd=ROOT,
        capture_output=True,text=True,encoding='utf-8',check=True).stdout
    run(HARNESS + r"""
(async()=>{
 const before=await scenario(process.argv[1],false),after=await scenario(process.argv[2],true);
 assert(before.includes('/api/actual-dividends?year=2026'));
 assert(before.includes('/api/realized-pnl?year=2026'));
 // after includes one deliberately opened ledger tab, still fewer requests overall.
 assert(after.length<before.length);
})().catch(e=>{console.error(e);process.exitCode=1;});
""",startup_code(baseline,modern=False),startup_code(SOURCE.read_text(encoding='utf-8')))


def test_ledger_and_pnl_discard_old_owner_period_and_detached_tab_responses():
    source=SOURCE.read_text(encoding='utf-8')
    code=fragment(source,'let ledgerPendingRead = null;','\nfunction renderLedger')+fragment(
        source,'async function loadRealizedPnl(owner = currentOwner, year = selectedPnlYear, tradeType = currentPnlTradeType) {','\nfunction renderRealizedPnl')
    run(r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
let shown=true;const pending=[],rendered=[];
const c={currentOwner:'A',currentUserProfile:{username:'synthetic'},currentLedgerYear:2026,currentLedgerMonth:10,selectedPnlYear:'2026',currentPnlTradeType:'all',
 WealthStartup:{visible:()=>shown,count(){}},console,
 api:url=>new Promise(resolve=>pending.push({url,resolve})),
 renderLedger:r=>rendered.push(r.tag),renderRealizedPnl:r=>rendered.push(r.tag),updatePnlYearOptions(){}};
vm.createContext(c);vm.runInContext(process.argv[1],c);
(async()=>{
 const a=c.loadLedger();c.currentOwner='B';const b=c.loadLedger();c.currentOwner='A';const newest=c.loadLedger();
 pending[2].resolve({tag:'new A'});await newest;pending[0].resolve({tag:'old A'});pending[1].resolve({tag:'old B'});await Promise.all([a,b]);
 assert.deepEqual(rendered,['new A']);
 const oldMonth=c.loadLedger();c.currentLedgerMonth=11;pending.at(-1).resolve({tag:'old month'});await oldMonth;
 const pnl=c.loadRealizedPnl();shown=false;pending.at(-1).resolve({tag:'hidden'});await pnl;
 assert.deepEqual(rendered,['new A']);
 const count=pending.length;await c.loadLedger();await c.loadRealizedPnl();assert.equal(pending.length,count);
 shown=true;const fresh=c.loadRealizedPnl();pending.at(-1).resolve({tag:'fresh pnl'});await fresh;
 assert.deepEqual(rendered,['new A','fresh pnl']);
})().catch(e=>{console.error(e);process.exitCode=1;});
""",code)


def test_hidden_chart_work_stops_before_reading_sources_or_scheduling_frames():
    source=(ROOT/'app/static/wealth-timeseries-unified.js').read_text(encoding='utf-8')
    code=fragment(source,'  async function renderPnl() {','  function dividendMode() {')+fragment(
        source,'  async function renderDividend() {','  function monthKey(')
    code+=fragment(source,'  function dividendMode() {','  async function dividendSource() {')
    code+=fragment(source,'  function syncDividendPeriodControls(','  function commitDividend(')
    code+=fragment(source,'  function queue(kind) {','  function handlePeriodClick(')
    run(r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
let mode='actual',controlsPresent=true;
const controls={hidden:true},counts={reads:0,frames:0,chartDOM:0};
const forbidden=kind=>{counts[kind]++;throw Error('hidden chart performed '+kind);};
const c={WealthStartup:{visible:()=>false},renderQueued:new Set(),
 document:{getElementById(){forbidden('chartDOM');},querySelector(selector){
  if(selector==='.wealth-unified-periods[data-kind="dividend"]')return controlsPresent?controls:null;
  if(selector==='#dividendModeTabs .heatmap-tab.active')return {dataset:{divMode:mode}};
  throw Error('unexpected hidden chart selector: '+selector);
 }},
 api:()=>forbidden('reads'),fetch:()=>forbidden('reads'),
 pnlSource:()=>forbidden('reads'),dividendSource:()=>forbidden('reads'),prepareDividend:()=>forbidden('reads'),
 commitDividend:()=>forbidden('chartDOM'),renderFlowChart:()=>forbidden('chartDOM'),
 requestAnimationFrame:()=>forbidden('frames'),setTimeout:()=>forbidden('frames')};
vm.createContext(c);vm.runInContext(process.argv[1],c);
(async()=>{
 await c.renderPnl();
 for(const value of ['actual','estimated','actual']){
  mode=value;assert.equal(await c.renderDividend(),false);
  assert.equal(controls.hidden,value!=='actual','only the period-control hidden state may change');
 }
 controlsPresent=false;assert.equal(await c.renderDividend(),false,'no control node must also be safe');
 for(const kind of ['stock','networth','pnl','dividend','ledger'])c.queue(kind);
 assert.equal(counts.reads,0);assert.equal(counts.frames,0);assert.equal(counts.chartDOM,0);
 assert.equal(c.renderQueued.size,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
""",code)


def test_hidden_history_does_not_rebuild_the_legacy_chart_source():
    source=(ROOT/'app/static/wealth-planning.js').read_text(encoding='utf-8')
    code=fragment(source,'  function renderHistory() {','  function renderHistoryDetails(')
    run(r"""
const vm=require('node:vm');
const c={home:{hidden:true},state:{history:[]},summary:{owner:'synthetic'},
 document:{getElementById(){throw Error('hidden history DOM read');}}};
vm.createContext(c);vm.runInContext(process.argv[1],c);c.renderHistory();
""",code)


def test_opt_in_metrics_count_shared_get_and_cache_invalidation_without_payloads():
    code=startup_code(SOURCE.read_text(encoding='utf-8'))
    run(r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const calls=[];
const c={URL,location:{origin:'http://synthetic.invalid'},window:{location:{}},
 __WEALTH_SYNTHETIC_PERF__:true,currentUserProfile:{username:'PRIVATE_USER'},
 document:{getElementById:()=>({getClientRects:()=>[{}]})},
 fetch:(url,options)=>new Promise(resolve=>calls.push({url,options,resolve}))};
vm.createContext(c);vm.runInContext(process.argv[1],c);c.WealthStartup.ready();
const response={ok:true,status:200,json:async()=>({records:[],private:'PRIVATE_FINANCIAL_VALUE'})};
(async()=>{
 const a=c.api('/api/actual-dividends?owner=PRIVATE_OWNER&year=all');
 const b=c.api('/api/actual-dividends?year=all&owner=PRIVATE_OWNER');
 assert.equal(calls.length,1);calls[0].resolve(response);await Promise.all([a,b]);
 await c.api('/api/actual-dividends?owner=PRIVATE_OWNER&year=all');assert.equal(calls.length,1);
 const write=c.api('/api/actual-dividends',{method:'POST'});calls[1].resolve(response);await write;
 const fresh=c.api('/api/actual-dividends?owner=PRIVATE_OWNER&year=all');assert.equal(calls.length,3);
 calls[2].resolve(response);await fresh;
 const trace=c.WealthStartup.snapshot();
 assert.equal(trace.counters['merged_get'],1);assert.equal(trace.counters['cache_hit'],1);
 assert.equal(trace.counters.request,3);assert(!JSON.stringify(trace).includes('PRIVATE_'));
 const disabled={URL,location:c.location,window:{},performance:{now(){throw Error('disabled measurement');}}};
 vm.createContext(disabled);vm.runInContext(process.argv[1],disabled);
 disabled.WealthStartup.count('render');assert.equal(disabled.WealthStartup.snapshot().events.length,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
""",code)


@pytest.mark.parametrize('width',[320,390,1280])
@pytest.mark.parametrize('case',['slow','roundtrip','leave','mode','owner','year','empty','error','hash','hash-error','hash-leave'])
def test_dividend_entry_prepares_once_and_commits_at_visible_width(width, case):
    source=SOURCE.read_text(encoding='utf-8')
    chart=(ROOT/'app/static/wealth-timeseries-unified.js').read_text(encoding='utf-8')
    code=fragment(source,'function setIncomeTab(tab, { updateHash = true, loadContent = true } = {}) {',
        '\nwindow.setIncomeTab = setIncomeTab;')
    code+=fragment(chart,'  async function dividendSource() {','  const dividendPreparations = new Map();')
    code+=fragment(chart,'  const dividendPreparations = new Map();','  function monthKey(')
    # PR #161 owns route resolution in the initial HTML. Exercise that same
    # contract rather than restoring the older layout-local route table.
    html=(ROOT/'app/static/index.html').read_text(encoding='utf-8')
    code+='\n(() => {\n'+fragment(html,'  const views = {','\n    </script>')
    code+='\nconst routeState = window.WealthWorkspaceRoute;\n'
    layout=(ROOT/'app/static/wealth-layout.js').read_text(encoding='utf-8')
    code+=fragment(layout,'  function navigate(focus = false) {',"  window.addEventListener('hashchange'")
    code+=fragment(source,"window.addEventListener('wealth:view', ({ detail }) => {",
        "window.addEventListener('wealth:role'")
    initial=next(line for line in source.splitlines() if line.startswith("setIncomeTab(document.querySelector('.wealth-workspace')"))
    code+='\nthis.restoreInitialIncomeTab=()=>'+initial
    code+="\nthis.renderer={prepareDividend,commitDividend,dividendScopeKey,renderDividend};"
    run(r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
const width=Number(process.argv[2]),kind=process.argv[3];
const directHash=kind.startsWith('hash');
const workspace={dataset:{activeView:'income'},querySelectorAll:()=>[]};
const requests=[],renders=[],listeners=new Map(),nodes={};
let created=0;
const flush=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};
function node(id){
 if(nodes[id])return nodes[id];
 const classes=new Set(['realizedPnlPanel','dividendPanel','ledgerSectionPanel','ipoPanel'].includes(id)?['wealth-income-hidden']:[]);
 return nodes[id]={id,dataset:{},attrs:{},hidden:false,textContent:'',firstElementChild:null,
  classList:{add:k=>classes.add(k),remove:k=>classes.delete(k),contains:k=>classes.has(k),
   toggle:(k,on)=>on?classes.add(k):classes.delete(k)},
  setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];},
  insertAdjacentElement(where,el){nodes[el.id]=el;},remove(){delete nodes[this.id];},
  before(el){nodes[el.id]=el;el.parent=this.parent;},
  append(el){this.head=el;el.parent=this;},prepend(el){this.head=el;el.parent=this;},
  getClientRects(){
   for(let el=this;el;el=el.parent)if(el.hidden||el.classList.contains('wealth-income-hidden'))return [];
   return workspace.dataset.activeView==='income'?[{}]:[];
  },
  querySelector(selector){
   if(selector==='.dividend-head')return this.head?.parent===this?this.head:null;
   return this.firstElementChild?.owned?this.firstElementChild:null;
  },
  closest(){return {querySelector:()=>({})};},
  set innerHTML(value){this.firstElementChild={owned:true,kind:value.includes('role="alert"')?'error':'empty'};}
 };
}
node('dividendPanel');node('dividendBarChartWrap');
node('dividendPanel').parent=node('incomePage');
const originalHead=node('dividend-head');node('dividendPanel').prepend(originalHead);
const importButton=node('importDividendBtn');importButton.parent=originalHead;
const controlsAvailable=()=>originalHead.parent?.id==='dividendPendingControls'
 || !node('dividendPanel').classList.contains('wealth-income-hidden');
let ready=!directHash;
const c={currentIncomeTab:'calendar',currentDividendMode:'actual',currentOwner:'A',selectedDividendYear:'2026',
 layout:workspace,activeView:null,views:{income:['머니 로그','머니 로그','합성 화면']},
 location:{hash:directHash?'#dividend':'#income'},rawDashboard:null,dashboard:null,
 currentUserProfile:{username:'synthetic'},modes:{dividend:'1M'},MODE_LABEL:{'1M':'월간'},
 cache:{dividend:{key:'',dividend:[],interest:[]}},dividendPending:new Map(),dividendRenderGeneration:0,
 details:{dividend:null},finite:Number,console:{error(){}},
 currentOwnerValue:()=>c.currentOwner,dividendMode:()=>c.currentDividendMode,activeBroker:()=> 'all',
 renderInvestmentView(){},
 ensureInjectedControls:()=>({hidden:false}),updateDetail(){},selectBucket(){},
 aggregateFlow:rows=>({mode:'1M',buckets:rows.map(row=>({key:row.tag,values:row}))}),
 document:{getElementById:node,createElement:()=>node('created-'+(++created)),querySelector(selector){
   if(selector==='.wealth-workspace')return workspace;
   if(selector==='#dividendModeTabs .heatmap-tab.active')return {dataset:{divMode:ready?c.currentDividendMode:'actual'}};
   if(selector.includes('wealth-unified-chart-shell'))return node('dividendBarChartWrap').firstElementChild?.kind==='ready'?{}:null;
   return null;
 },querySelectorAll:()=>[]},history:{replaceState(a,b,hash){c.location.hash=hash;}},
 WealthStartup:{canRead:()=>ready,visible:()=>ready&&!node('dividendPanel').classList.contains('wealth-income-hidden'),loadVisible(){},count(){},dashboardRendered(){}},
 CustomEvent:class {constructor(type,options={}){this.type=type;this.detail=options.detail;}},api:url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject})),
 renderFlowChart(host,aggregated){
   assert(!node('dividendPanel').classList.contains('wealth-income-hidden'),'commit must measure the active panel');
   const frame={owned:true,kind:aggregated.buckets.length?'ready':'empty',
     client:width-147,width:(width-147)*3,left:(width-147)*2,tags:aggregated.buckets.map(b=>b.key)};
   host.firstElementChild=frame;renders.push(frame);
 },
};
if(directHash) Object.defineProperty(c,'currentDividendMode',{get(){if(!ready)throw Error('mode read before core initialization');return 'actual';}});
c.window=c;
c.addEventListener=(name,fn)=>{if(!listeners.has(name))listeners.set(name,new Set());listeners.get(name).add(fn);};
c.removeEventListener=(name,fn)=>listeners.get(name)?.delete(fn);
c.emit=(name,detail)=>[...(listeners.get(name)||[])].forEach(fn=>fn({detail}));
c.dispatchEvent=event=>c.emit(event.type,event.detail);
vm.createContext(c);vm.runInContext(process.argv[1],c);
c.WealthUnifiedTimeseries={...c.renderer,refreshVisiblePanZoom(){}};
(async()=>{
 const enter=(opts)=>c.setIncomeTab('dividend',opts);
 if(directHash) {
   node('dividendPanel').classList.remove('wealth-income-hidden');
   const module=c.WealthUnifiedTimeseries;c.WealthUnifiedTimeseries=null;
   const setter=c.setIncomeTab;c.setIncomeTab=undefined;
   c.navigate();assert.equal(workspace.dataset.incomeTab,'dividend','layout records the route before core registration');
   c.setIncomeTab=setter;
   const direct=c.restoreInitialIncomeTab();await flush();
   assert.equal(c.currentIncomeTab,'dividend','route selection must not wait for chart readiness');
   assert.equal(c.location.hash,'#dividend');
   assert(node('dividendPanel').classList.contains('wealth-income-hidden'));
   assert(controlsAvailable(),'direct hash must expose the original controls before assets/chart readiness');
   assert(importButton.getClientRects().length,'import button must have visible ancestors');
   // planning.selectTab() runs during hidden investment-workspace initialization.
   c.emit('wealth:view','invest');await flush();
   assert(importButton.getClientRects().length,'a hidden subview notification must not cancel the actual route');
   assert.equal(c.setIncomeTab.pendingTarget,'dividend');
   assert.equal(requests.length,0);
   if(kind==='hash-leave'){
     c.location.hash='#income';c.navigate();await flush();
     ready=true;c.emit('wealth:assets-ready');c.WealthUnifiedTimeseries=module;c.emit('wealth:unified-ready');
     await direct;assert.equal(c.currentIncomeTab,'calendar');assert.equal(requests.length,0);
     assert.equal(importButton.getClientRects().length,0);return;
   }
   ready=true;c.emit('wealth:assets-ready');await flush();assert.equal(requests.length,0);
   c.WealthUnifiedTimeseries=module;c.emit('wealth:unified-ready');await flush();
   assert.equal(requests.length,1);
   if(kind==='hash-error')requests[0].reject(Error('synthetic unavailable'));
   else requests[0].resolve({records:[{tag:'hash',amount_krw:5}],interest_records:[]});
   await direct;
   assert.equal(c.currentIncomeTab,'dividend');assert.equal(c.location.hash,'#dividend');
   assert(importButton.getClientRects().length,'success or failure must leave the original controls visible');
   assert.equal(originalHead.parent,node('dividendPanel'),'ready hash restores the same controls');
   assert.equal(node('dividendBarChartWrap').dataset.unifiedState,kind==='hash-error'?'error':'ready');
   if(kind!=='hash-error')assert.equal(renders[0].client,width-147);return;
 }
 const first=enter();await flush();
 assert.equal(requests.length,1);
 assert(node('dividendPanel').classList.contains('wealth-income-hidden'),'slow request cannot expose an unowned chart');
 assert(controlsAvailable(),'slow chart preparation must not hide import/add/delete controls');
 let latest=first;
 if(kind==='roundtrip'||kind==='leave'){
   c.setIncomeTab('calendar');
   assert.equal(originalHead.parent,node('dividendPanel'),'leaving restores controls to the inactive panel');
   assert(!nodes.dividendPendingControls,'leaving removes the temporary control container');
   if(kind==='roundtrip'){latest=enter();await flush();assert.equal(requests.length,1);}
 }
 if(kind==='owner')c.currentOwner='B';
 if(kind==='mode'){
   c.currentDividendMode='estimated';c.setIncomeTab('dividend',{updateHash:false});
   assert(controlsAvailable(),'estimated mode activates without waiting for the actual request');
   assert.equal(originalHead.parent,node('dividendPanel'));
 }
 if(kind==='year')c.selectedDividendYear='2027';
 if(kind==='error')requests[0].reject(Error('synthetic unavailable'));
 else requests[0].resolve({records:kind==='empty'?[]:[{tag:'old A',amount_krw:10}],interest_records:[]});
 await flush();
 if(kind==='leave'){
   await first;assert.equal(c.currentIncomeTab,'calendar');assert.equal(renders.length,0);return;
 }
 if(kind==='mode'){
   await first;assert.equal(c.currentDividendMode,'estimated');assert.equal(renders.length,0);
   assert(!node('dividendPanel').classList.contains('wealth-income-hidden'),'late actual response cannot hide estimated mode');return;
 }
 if(kind==='owner'||kind==='year'){
   assert.equal(renders.length,0);assert.equal(requests.length,2);
   if(kind==='owner')assert(requests[1].url.includes('owner=B'));
   requests[1].resolve({records:[{tag:'new scope',amount_krw:20}],interest_records:[]});
 }
 await latest;await flush();
 assert.equal(c.currentIncomeTab,'dividend');
 assert.equal(originalHead.parent,node('dividendPanel'),'commit restores the same controls without cloning');
 const host=node('dividendBarChartWrap'),before=host.firstElementChild;
 assert(before?.owned,'activation must have an actual unified-owned node');
 if(kind==='error')assert.equal(host.dataset.unifiedState,'error');
 else if(kind==='empty')assert.equal(host.dataset.unifiedState,'empty');
 else {assert.equal(before.client,width-147);assert(before.width>0);assert.equal(renders.length,1);}
 if(kind==='owner'||kind==='year')assert.deepEqual(Array.from(before.tags),['new scope']);
 // Repeated queued render requests must reuse the committed frame and geometry.
 await Promise.all([c.renderDividend(),c.renderDividend(),c.renderDividend()]);
 assert.equal(host.firstElementChild,before);
 assert.equal(requests.length,kind==='owner'||kind==='year'?2:1);
 if(kind==='roundtrip')await first;
})().catch(e=>{console.error(e);process.exitCode=1;});
""",code,str(width),case)


def test_dividend_prepared_data_rejects_stale_write_epoch():
    source = SOURCE.read_text(encoding='utf-8')
    chart = (ROOT / 'app/static/wealth-timeseries-unified.js').read_text(encoding='utf-8')
    code = fragment(source, 'const startupReadPending = new Map();', 'const fetchJson = api;')
    code += fragment(chart, '  async function dividendSource() {', '  function monthKey(')
    run(r"""
const assert = require('node:assert/strict'), vm = require('node:vm');
const requests = [], renders = [], controls = {hidden:false};
const host = {dataset:{}, firstElementChild:null,
  closest:()=>({querySelector:()=>({})}), querySelector(){return this.firstElementChild;}};
const response = records => ({ok:true,status:200,json:async()=>({records,interest_records:[]})});
const rows = tag => [{tag,amount_krw:100}];
const c = {URL, location:{origin:'http://127.0.0.1'}, console,
  currentOwner:'A', selectedDividendYear:'2026', mode:'actual', broker:'all',
  modes:{dividend:'1M'}, MODE_LABEL:{'1M':'월간'}, dividendRenderGeneration:0,
  cache:{dividend:{key:'',dividend:[],interest:[]}}, dividendPending:new Map(), details:{},
  currentOwnerValue:()=>c.currentOwner, dividendMode:()=>c.mode, activeBroker:()=>c.broker,
  finite:Number, aggregateFlow:records=>({buckets:records}),
  WealthStartup:{visible:()=>true,count(){},request(){}},
  document:{querySelector:()=>controls,getElementById:id=>id==='dividendBarChartWrap'?host:null},
  ensureInjectedControls:()=>controls, updateDetail(){}, selectBucket(){},
  renderFlowChart(target, aggregated){
    target.firstElementChild={tags:aggregated.buckets.map(row=>row.tag)};
    renders.push(target.firstElementChild);
  },
  fetch(url, options={}) {
    if(options.method==='POST')return Promise.resolve(response([]));
    return new Promise(resolve=>requests.push({url,resolve}));
  },
};
c.window=c;
vm.createContext(c); vm.runInContext(process.argv[1],c);
const write = ()=>c.api('/api/actual-dividends',{method:'POST'});
(async()=>{
  const old = c.prepareDividend();
  assert.equal(c.prepareDividend(),old,'same-epoch preparations share one promise');
  assert.equal(requests.length,1);
  await write();
  const fresh = c.prepareDividend();
  assert.notEqual(fresh,old,'a write must not join the old preparation');
  assert.equal(requests.length,2,'the new epoch needs a fresh GET');
  assert.equal(renders.length,0,'preparation alone does not render');

  // The fresh response wins first; the late old response must neither commit
  // nor replace the new epoch's full-history source cache.
  requests[1].resolve(response(rows('fresh')));
  const preparedFresh = await fresh;
  assert.equal(c.commitDividend(preparedFresh),true);
  const firstFrame=host.firstElementChild;
  requests[0].resolve(response(rows('stale')));
  const preparedOld=await old;
  assert.equal(c.commitDividend(preparedOld),false);
  assert.equal(host.firstElementChild,firstFrame);
  assert.equal(c.cache.dividend.response.records[0].tag,'fresh');
  assert.equal(renders.length,1);
  assert.equal(await c.renderDividend(),true);
  assert.equal(requests.length,2,'unchanged committed scope does not refetch');
  assert.equal(renders.length,1,'unchanged committed scope does not rerender');

  await write();
  const staleRender=c.renderDividend();
  const stalePreparation=c.prepareDividend();
  assert.equal(requests.length,3,'a write invalidates the committed frame and source');
  assert.equal(host.firstElementChild,firstFrame,'no replacement before a fresh response');
  await write();
  const latestRender=c.renderDividend();
  assert.equal(requests.length,4,'an old in-flight source must not satisfy the next epoch');
  requests[2].resolve(response(rows('superseded')));
  assert.equal(await staleRender,false);
  assert.equal(c.commitDividend(await stalePreparation),false);
  assert.equal(renders.length,1);
  requests[3].resolve(response(rows('latest')));
  assert.equal(await latestRender,true);
  assert.deepEqual(Array.from(host.firstElementChild.tags),['latest']);
  assert.equal(renders.length,2);

  const scoped=await c.prepareDividend();
  c.currentOwner='B';assert.equal(c.commitDividend(scoped),false,'owner must match');
  c.currentOwner='A';c.selectedDividendYear='2027';
  assert.equal(c.commitDividend(scoped),false,'year must match');
  c.selectedDividendYear='2026';c.mode='estimated';
  assert.equal(c.commitDividend(scoped),false,'mode must match');
  c.mode='actual';c.broker='other';
  assert.equal(c.commitDividend(scoped),false,'broker must match');
  c.broker='all';
  assert.equal(await c.renderDividend(),true);
  assert.equal(requests.length,4);
  assert.equal(renders.length,2,'scope checks cannot paint stale rows');
})().catch(error=>{console.error(error);process.exitCode=1;});
""", code)


def test_late_ledger_period_wrapper_keeps_hidden_and_stale_guards():
    source = (ROOT / 'app/static/wealth-ledger-period-filter.js').read_text(encoding='utf-8')
    wrapper = fragment(source, 'window.loadLedger = async function', "\n  document.addEventListener('pointerdown'")
    run(r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
(async()=>{
 for(const change of ['hidden','owner','year','month','annual','epoch','none']){
  let active=false,reads=0,renders=0,resolve;
  const c={window:{},globalThis:null,currentOwner:'synthetic',currentLedgerYear:2026,currentLedgerMonth:10,
    annualView:false,startupReadEpoch:0,requestSequence:0,rawLedgerData:null,
    WealthStartup:{visible:()=>active},currentKstYear:()=>2026,
    fetchLedgerMonth:()=>{reads++;return new Promise(r=>resolve=r);},
    renderLedgerPeriodAware:()=>renders++,console};
  c.globalThis=c;vm.createContext(c);vm.runInContext(process.argv[1],c);
  await c.window.loadLedger();assert.equal(reads,0,'hidden late-installed wrapper must not fetch');
  active=true;const pending=c.window.loadLedger();assert.equal(reads,1);
  if(change==='hidden')active=false;
  if(change==='owner')c.currentOwner='another';
  if(change==='year')c.currentLedgerYear=2025;
  if(change==='month')c.currentLedgerMonth=9;
  if(change==='annual')c.annualView=true;
  if(change==='epoch')c.startupReadEpoch++;
  resolve({transactions:[]});await pending;
  assert.equal(renders,change==='none'?1:0,'late ledger response must match active scope');
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""", wrapper)


def test_annual_ledger_stops_next_month_reads_after_scope_or_visibility_change():
    source = (ROOT/'app/static/wealth-ledger-period-filter.js').read_text(encoding='utf-8')
    helper = fragment(source, 'async function loadAnnualLedger(', '\n  function updateLedgerHeaderForAnnual')
    run(r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
(async()=>{
 for(const change of ['hidden','owner','year','annual','epoch','none']){
  let active=true,reads=0;
  const c={currentOwner:'synthetic',currentLedgerYear:2026,annualView:true,startupReadEpoch:0,
   requestSequence:1,WealthStartup:{visible:()=>active},mergeAnnualLedger:rows=>rows,
   fetchLedgerMonth:async()=>{
    reads++;
    if(change==='hidden')active=false;
    if(change==='owner')c.currentOwner='another';
    if(change==='year')c.currentLedgerYear=2025;
    if(change==='annual')c.annualView=false;
    if(change==='epoch')c.startupReadEpoch++;
    return {};
   }};
  vm.createContext(c);vm.runInContext(process.argv[1],c);
  const result=await c.loadAnnualLedger('synthetic',2026,1,0);
  assert.equal(reads,change==='none'?12:1);
  assert.equal(result===null,change!=='none');
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
""", helper)
