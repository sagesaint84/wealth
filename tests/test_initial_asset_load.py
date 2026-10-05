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
let familyReleased;
const familyPending = new Promise(resolve => { familyReleased = resolve; });
const context = {
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
  loadMarkets: async () => {}, loadDividends: async () => {},
  loadActualDividends: async () => {}, loadRealizedPnl: async () => {},
  updateOverviewCardsAllTime: async () => {},
};
vm.createContext(context);
vm.runInContext(source, context);
(async () => {
  const loading = context.loadAssetDataForUser();
  await Promise.resolve();
  assert(requests.includes('/api/refresh-prices'), 'refresh must start before family response');
  familyReleased();
  for (let i = 0; i < 8; i++) await Promise.resolve();
  assert(rendered, 'dashboard must render before asset records respond');
  assert.equal(requests.filter(path => path === '/api/asset-records').length, 1);
  releaseRecords({records: []});
  await loading;
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
