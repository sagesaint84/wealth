"""Exercise the restored tax holdings renderer with invented accounts."""

from pathlib import Path
import subprocess


def test_tax_holdings_all_account_filter_and_sort():
    source_path = Path(__file__).resolve().parents[1] / "app/static/wealth.js"
    script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const renderer = 'function renderTaxAccountHoldings(owner = currentOwner) {' +
  source.split('function renderTaxAccountHoldings(owner = currentOwner) {')[1].split('\n// ── 9.')[0];
const chart = {innerHTML: ''};
const list = {innerHTML: ''};
const panel = {classList: {add() {}}};
const elements = {'#assetChart': chart, '#assetRecordList': list, '#recordsPanel': panel};
const accounts = [
  {id:'isa', name:'ISA', account_type:'isa', owner:'모두', broker:'Demo'},
  {id:'irp', name:'IRP', account_type:'irp', owner:'모두', broker:'Demo'},
  {id:'pension', name:'Pension', account_type:'pension_savings', owner:'모두', broker:'Demo'},
];
const holdings = [
  {id:'h1', account_id:'isa', name:'Alpha', code:'AAA', quantity:2, current_price:100, avg_price:80, market_value_krw:200, cost_value_krw:160},
  {id:'h2', account_id:'irp', name:'Beta', code:'BBB', quantity:1, current_price:300, avg_price:200, market_value_krw:300, cost_value_krw:200},
  {id:'h3', account_id:'pension', name:'Gamma', code:'CCC', quantity:1, current_price:50, avg_price:40, market_value_krw:50, cost_value_krw:40},
];
const context = {
  $: selector => elements[selector] || null,
  document: {querySelector() { return null; }},
  dashboard: {accounts, holdings, fx_rates:{USD:1400}}, rawDashboard: null,
  currentOwner:'모두', currentTaxAccountFilter:'all',
  taxHoldingSortField:'market_value_krw', taxHoldingSortOrder:'desc',
  isTaxAdvantagedAccount: a => ['isa','irp','pension_savings'].includes(a.account_type),
  getTaxCategory: a => a.account_type,
  isAccountTaxDeductible: () => true,
  calculateOwnerYearPensionTaxBenefits: () => ({cumulative:{taxSaved:0, irpTaxSaved:0, pensionTaxSaved:0}}),
  calcAccountCumulativeTaxSaved: () => 0,
  number: (n, digits) => Number(n || 0).toFixed(digits),
  html: value => String(value || ''),
  signClass: () => '',
};
vm.createContext(context);
vm.runInContext(renderer, context);
const codes = () => [...chart.innerHTML.matchAll(/<tr data-code="([A-Z]+)"/g)].map(match => match[1]);
context.renderTaxAccountHoldings('모두');
assert.deepEqual(codes(), ['BBB','AAA','CCC']);
assert.match(chart.innerHTML, /class="tax-holdings-table"/);
assert.match(chart.innerHTML, /평가금액/);
assert.match(chart.innerHTML, /평가손익/);
assert.match(chart.innerHTML, /수익률/);
context.currentTaxAccountFilter = 'acc_isa';
context.renderTaxAccountHoldings('모두');
assert.deepEqual(codes(), ['AAA']);
context.currentTaxAccountFilter = 'acc_irp';
context.renderTaxAccountHoldings('모두');
assert.deepEqual(codes(), ['BBB']);
context.currentTaxAccountFilter = 'acc_pension';
context.renderTaxAccountHoldings('모두');
assert.deepEqual(codes(), ['CCC']);
context.currentTaxAccountFilter = 'all';
context.taxHoldingSortOrder = 'asc';
context.renderTaxAccountHoldings('모두');
assert.deepEqual(codes(), ['CCC','AAA','BBB']);
"""
    result = subprocess.run(["node", "-e", script, str(source_path)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
