"""Synthetic owner switch through the legacy chart and unified observer."""

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_owner_stock_chart_has_one_renderer_and_owner_scoped_source():
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const wealth = fs.readFileSync(process.argv[1], 'utf8');
const unified = fs.readFileSync(process.argv[2], 'utf8');
const part = (text, start, end) => start + text.split(start, 2)[1].split(end, 1)[0];
const code = [
  part(wealth, 'function renderAssetRecords(records) {', '\n// ── 8-1.'),
  part(wealth, 'async function loadAssetRecords(owner) {', '\n// ── 다이얼로그'),
  part(unified, '  function stockSource() {', '\n  function captureNetWorthFromLegacy'),
  part(unified, '  function hostNeedsUnified(hostId) {', '\n  function install()'),
].join('\n');
let records = [
  {owner:'A', date:'2026-10-01', total_value_krw:10, day_profit_krw:1},
  {owner:'B', date:'2026-10-02', total_value_krw:100, day_profit_krw:10},
  {owner:'모두', date:'2026-10-03', total_value_krw:1000, day_profit_krw:100},
];
const writes = [];
let chartHtml = '';
let taxView = false;
let observerCallback;
const chart = {
  get innerHTML() { return chartHtml; },
  set innerHTML(value) { chartHtml = value; writes.push(value); },
  get firstElementChild() {
    return {classList: {contains(name) {
      return name === 'wealth-unified-chart-shell' && chartHtml.includes('wealth-unified-chart-shell');
    }}};
  },
};
const node = {style:{}, classList:{add(){}, remove(){}}, setAttribute(){}};
const panel = {classList:{add(){ taxView = true; }, remove(){ taxView = false; }, contains(){ return taxView; }}};
const elements = {assetChart:chart, recordsPanel:panel, recordPeriodTabs:node};
const selectors = {'#assetChart':chart, '#recordsPanel':panel, '#recordPeriodTabs':node};
const context = {
  window:{}, currentOwner:'A', currentRecordView:'bar', currentRecordPeriod:'ALL',
  allAssetRecords:[], assetRecords:[],
  document:{body:{}, getElementById(id){return elements[id] || null;}, querySelector(){return null;}},
  MutationObserver:class{constructor(callback){observerCallback=callback;} observe(){}},
  $:selector=>selectors[selector] || null,
  api:async()=>({records}),
  buildPreviousRecordMap:()=>new Map(), filterRecordsByPeriod:items=>items,
  number:value=>String(value), money:value=>String(value), html:value=>String(value), signClass:()=>'',
  renderTaxAccountHoldings(){},
  adoptExistingControls(){}, modes:{stock:'MONTH'}, MODE_LABEL:{MONTH:'월간'},
  aggregateState(source, mode){context.lastSource=[...source];context.lastMode=mode;return {mode};},
  renderStateChart(host, aggregated){host.innerHTML='<div class="wealth-unified-chart-shell">'+context.lastSource.map(r=>r.owner).join(',')+'</div>';},
  queue(kind){if(kind==='stock') context.renderStock();},
  dividendMode:()=> 'estimated', netWorthCapturePending:false,
};
vm.createContext(context);
vm.runInContext(code, context);
context.window.WealthUnifiedTimeseries = {renderStock:context.renderStock};
context.installObserver();
(async()=>{
  for(const owner of ['A','B']) {
    context.currentOwner=owner;
    const before=writes.length;
    await context.loadAssetRecords(owner);
    observerCallback();
    assert.deepEqual(context.assetRecords.map(r=>r.owner), [owner]);
    assert.equal(writes.length-before, 1, 'owner switch must paint #assetChart once');
    assert.deepEqual(context.lastSource.map(r=>r.owner), [owner]);
    assert.equal(context.lastMode, 'MONTH');
    assert.match(chart.innerHTML, /wealth-unified-chart-shell/);
  }
  context.currentOwner='모두';
  await context.loadAssetRecords('모두');
  observerCallback();
  assert.deepEqual(context.lastSource.map(r=>r.owner), ['모두']);
  records=records.filter(record=>record.owner!=='모두');
  await context.loadAssetRecords('모두');
  observerCallback();
  assert.deepEqual(context.lastSource.map(r=>r.owner), ['A','B']);
  taxView=true;
  chart.innerHTML='<table class="tax-holdings-table"></table>';
  const before=writes.length;
  context.renderStock();
  observerCallback();
  assert.equal(writes.length, before);
  assert.match(chart.innerHTML, /tax-holdings-table/);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result = subprocess.run(
        ["node", "-e", script, str(ROOT / "app/static/wealth.js"),
         str(ROOT / "app/static/wealth-timeseries-unified.js")],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
