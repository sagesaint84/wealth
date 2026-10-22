"""Bootstrap request ordering with synthetic responses and no user data."""

import subprocess
from pathlib import Path


def test_initial_dashboard_renders_without_waiting_for_asset_records():
    source = (Path(__file__).resolve().parents[1] / "app/static/wealth.js").read_text(encoding="utf-8")
    dashboard_fn = source.split("async function loadDashboard(recordSnapshots = false) {", 1)[1].split("\nasync function loadAssetRecords", 1)[0]
    bootstrap_fn = source.split("async function loadAssetDataForUser() {", 1)[1].split("\nasync function handleForcePasswordSubmit", 1)[0]
    script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const source = process.argv[1];
const requests = [];
let releaseRecords;
const recordsPending = new Promise(resolve => { releaseRecords = resolve; });
let rendered = false;
let estimatedLoads = 0;
let familyReleased;
const familyPending = new Promise(resolve => { familyReleased = resolve; });
const context = {
  currentDividendMode: 'actual',
  currentOwner: '모두', selectedDividendYear: 'all', selectedPnlYear: 'all',
  currentPnlTradeType: 'all', rawDashboard: null, dashboard: null,
  allAssetRecords: [], window: {dispatchEvent() {}}, CustomEvent: class {},
  toast(error) { throw Error(error); },
  api(path) {
    requests.push(path);
    if (path === '/api/dashboard?record_snapshots=true') return Promise.resolve({summary: {}});
    if (path === '/api/asset-records') return recordsPending;
    return Promise.resolve({});
  },
  renderWithOwner() { rendered = true; void context.loadAssetRecords('모두'); },
  loadFamilyMembers() { return familyPending; },
  loadMarkets: async () => {}, loadDividends: async () => { estimatedLoads++; },
  loadActualDividends: async () => {}, loadRealizedPnl: async () => {},
  updateOverviewCardsAllTime: async () => {},
  finishStartupIncomeReads() {},
};
vm.createContext(context);
vm.runInContext(source, context);
(async () => {
  const loading = context.loadAssetDataForUser();
  await Promise.resolve();
  assert(requests.includes('/api/refresh-prices'), 'refresh must start before family response');
  for (let i = 0; i < 8; i++) await Promise.resolve();
  assert(rendered, 'dashboard must render before asset records respond');
  familyReleased();
  assert.equal(requests.filter(path => path === '/api/asset-records').length, 1);
  releaseRecords({records: []});
  await loading;
  assert.equal(estimatedLoads, 0);
  assert(requests.indexOf('/api/refresh-prices') < requests.indexOf('/api/planning/snapshot-all'));
  assert.equal(requests.filter(path => path === '/api/asset-records').length, 1);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    functions = (
        "async function loadDashboard(recordSnapshots = false) {" + dashboard_fn
        + "\nasync function loadAssetRecords(owner) {\n"
        + "  const allRes = await api('/api/asset-records'); allAssetRecords = allRes.records || [];\n}\n"
        + "async function loadAssetDataForUser() {" + bootstrap_fn
    )
    result = subprocess.run(["node", "-e", script, functions], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_hidden_invest_heatmap_does_not_render_during_home_bootstrap():
    source = (Path(__file__).resolve().parents[1] / "app/static/wealth.js").read_text(encoding="utf-8")
    heatmap_fn = "function renderHeatmaps(data) {" + source.split("function renderHeatmaps(data) {", 1)[1].split("\nfunction ", 1)[0]
    script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
let writes = 0;
const page = {hidden: true};
const container = {closest() { return page; }, set innerHTML(value) { writes++; }};
const context = {$() { return container; }};
vm.createContext(context);
vm.runInContext(process.argv[1], context);
context.renderHeatmaps({holdings: []});
assert.equal(writes, 0);
page.hidden = false;
context.renderHeatmaps({holdings: []});
assert.equal(writes, 1);
"""
    result = subprocess.run(["node", "-e", script, heatmap_fn], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_price_refresh_success_and_failure_preserve_snapshot_order():
    source = (Path(__file__).resolve().parents[1] / 'app/static/wealth.js').read_text(encoding='utf-8')
    code='async function loadAssetDataForUser() {'+source.split('async function loadAssetDataForUser() {',1)[1].split('\nasync function handleForcePasswordSubmit',1)[0]
    script=r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
(async()=>{for(const fail of [false,true]){
 const events=[];const c={currentOwner:'모두',currentDividendMode:'actual',selectedDividendYear:'all',selectedPnlYear:'all',currentPnlTradeType:'all',
  api:async p=>{events.push(p);if(fail&&p==='/api/refresh-prices')throw Error('synthetic refresh failure');return{};},
  loadFamilyMembers:async()=>{events.push('family');},loadDashboard:async flag=>{events.push(flag?'dashboard-with-snapshot':'dashboard-without-snapshot');},
  toast:()=>events.push('warning'),window:{dispatchEvent:event=>events.push(event.type==='wealth:planning-refresh'?'planning-refresh':event.type)},CustomEvent:class{constructor(type){this.type=type;}},
  loadMarkets:async()=>events.push('markets'),loadActualDividends:async()=>events.push('dividends'),loadRealizedPnl:async()=>events.push('pnl'),updateOverviewCardsAllTime:async()=>events.push('overview'),finishStartupIncomeReads:()=>events.push('finished')};
 vm.createContext(c);vm.runInContext(process.argv[1],c);await c.loadAssetDataForUser();await c.loadAssetDataForUser.supplementary;
 const snaps=events.filter(x=>x==='/api/planning/snapshot-all');assert.equal(snaps.length,fail?0:1);
 assert(events.indexOf('/api/refresh-prices')<events.indexOf(fail?'dashboard-without-snapshot':'dashboard-with-snapshot'));
 if(!fail)assert(events.indexOf('dashboard-with-snapshot')<events.indexOf('/api/planning/snapshot-all'));
 assert.equal(events.filter(x=>x==='wealth:assets-ready').length,1);
 assert(events.indexOf(fail?'dashboard-without-snapshot':'/api/planning/snapshot-all')<events.indexOf('wealth:assets-ready'));
 assert.equal(events.filter(x=>x==='planning-refresh').length,fail?0:1);assert.equal(events.at(-1),'finished');
}})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result=subprocess.run(['node','-e',script,code],capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0,result.stderr
