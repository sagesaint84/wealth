"""Owner filter request counts and stale-response behavior with synthetic data."""

import subprocess
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "app/static/wealth.js"


def _run_owner_script(mode: str) -> subprocess.CompletedProcess[str]:
    source = SOURCE.read_text(encoding="utf-8")
    fragments = (
        ("function selectOwner(owner) {", "\n// ── 핵심 요약"),
        ("function renderWithOwner(data, owner) {", "\n// 다이얼로그"),
        ("async function loadDashboard(recordSnapshots = false) {", "\nasync function loadAssetRecords"),
        ("async function loadAssetRecords(owner) {", "\n// ── 다이얼로그"),
        ("async function loadLedger() {", "\nfunction renderLedger"),
    )
    code = "\n".join(
        start + source.split(start, 1)[1].split(end, 1)[0]
        for start, end in fragments
    )
    script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const mode = process.argv[2];
const requests = [];
const pending = [];
const recordRenders = [];
const ledgerRenders = [];
const data = {accounts: [], holdings: [], summary: {}, fx_rates: {}};
const context = {
  dividendData: null, currentDividendMode: 'actual',
  currentOwner: 'A', rawDashboard: data, dashboard: data,
  currentLedgerYear: 2026, currentLedgerMonth: 10,
  allAssetRecords: [], assetRecords: [], rawLedgerData: null,
  selectedDividendYear: 'all', selectedPnlYear: 'all', currentPnlTradeType: 'all',
  document: {querySelectorAll() { return []; }},
  computeFilteredSummary: () => ({}), computeFilteredClassifications: () => [],
  computeFilteredSectors: () => [], computeFilteredCurrencySummary: () => ({}),
  computeFilteredDayChange: () => ({}), render() {},
  loadDividends() {}, loadActualDividends() {}, loadRealizedPnl() {},
  updateOverviewCardsAllTime() {},
  renderAssetRecords(records) { recordRenders.push(records[0]?.owner); },
  renderLedger(result) { ledgerRenders.push(result.owner); },
  console,
  api(path) {
    requests.push(path);
    if (mode === 'race' && path !== '/api/dashboard') {
      return new Promise(resolve => pending.push({path, resolve}));
    }
    if (path === '/api/dashboard') return Promise.resolve(data);
    if (path === '/api/asset-records') return Promise.resolve({records: []});
    return Promise.resolve({owner: 'B'});
  },
};
vm.createContext(context);
vm.runInContext(process.argv[1], context);
(async () => {
  if (mode === 'counts') {
    context.selectOwner('B');
    await Promise.resolve(); await Promise.resolve();
    assert.equal(requests.filter(path => path === '/api/asset-records').length, 1);
    assert.equal(requests.filter(path => path.startsWith('/api/ledger?')).length, 1);
    assert.equal(requests.filter(path => path.startsWith('/api/dashboard')).length, 0);
  } else if (mode === 'race') {
    context.selectOwner('A'); context.selectOwner('B'); context.selectOwner('C');
    const assetRequests = pending.filter(item => item.path === '/api/asset-records');
    const requestsPerOwner = assetRequests.length / 3;
    for (const [index, owner] of ['C', 'B', 'A'].entries()) {
      const ownerIndex = 2 - index;
      for (const records of assetRequests.slice(ownerIndex * requestsPerOwner, (ownerIndex + 1) * requestsPerOwner)) {
        records.resolve({records: [{owner}]});
      }
      for (const ledger of pending.filter(item => item.path.includes(`owner=${owner}`))) {
        ledger.resolve({owner});
      }
      await Promise.resolve(); await Promise.resolve();
    }
    assert.equal(recordRenders.at(-1), 'C');
    assert.equal(ledgerRenders.at(-1), 'C');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    return subprocess.run(
        ["node", "-e", script, code, mode], capture_output=True, text=True, encoding="utf-8"
    )


def test_owner_change_fetches_each_required_store_once_without_dashboard_refetch():
    result = _run_owner_script("counts")
    assert result.returncode == 0, result.stderr


def test_rapid_owner_changes_do_not_render_stale_asset_or_ledger_responses():
    result = _run_owner_script("race")
    assert result.returncode == 0, result.stderr


def test_income_tab_change_only_loads_ledger_when_selected():
    source = SOURCE.read_text(encoding="utf-8")
    tab_function = "function setIncomeTab(tab, { updateHash = true, loadContent = true } = {}) {" + source.split(
        "function setIncomeTab(tab, { updateHash = true, loadContent = true } = {}) {", 1
    )[1].split("\nwindow.setIncomeTab = setIncomeTab;", 1)[0]
    script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const requests = [];
const context = {
  currentUserProfile: {username: 'synthetic-user'}, currentIncomeTab: 'calendar',
  document: {getElementById() { return null; }, querySelectorAll() { return []; }},
  history: {replaceState() {}}, window: {},
  loadLedger() { requests.push('/api/ledger'); },
};
vm.createContext(context);
vm.runInContext(process.argv[1], context);
context.setIncomeTab('pnl');
assert.deepEqual(requests, []);
context.setIncomeTab('ledger');
assert.deepEqual(requests, ['/api/ledger']);
"""
    result = subprocess.run(
        ["node", "-e", script, tab_function], capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 0, result.stderr
