from pathlib import Path
import re
import subprocess
import unittest


class UnifiedTimeseriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.js = (root / "app/static/wealth-timeseries-unified.js").read_text(encoding="utf-8")
        cls.loader = (root / "app/static/wealth-planning-model.js").read_text(encoding="utf-8")

    def test_all_five_requested_chart_hosts_are_supported(self):
        for marker in (
            "assetChart",
            "wealthHistoryPlot",
            "pnlBarChartWrap",
            "dividendBarChartWrap",
            "ledgerTrendContainer",
        ):
            self.assertIn(marker, self.js)

    def test_all_five_period_buttons_share_one_mode_set(self):
        self.assertIn("MODES.DAY, MODES.WEEK, MODES.MONTH, MODES.YEAR, MODES.ALL", self.js)
        for label in ("'일간'", "'주간'", "'월간'", "'연간'", "'전체'"):
            self.assertIn(label, self.js)

    def test_stock_uses_period_close_and_price_change_profit(self):
        self.assertIn("valueField: 'total_value_krw'", self.js)
        self.assertIn("changeField: 'day_profit_krw'", self.js)
        self.assertIn("가격변동", self.js)

    def test_net_worth_uses_bucket_close_to_close_change(self):
        self.assertIn("valueField: 'net_worth'", self.js)
        self.assertIn("순자산 변화", self.js)

    def test_realized_pnl_dividend_interest_and_ledger_are_flow_buckets(self):
        self.assertIn("fields: ['pnl_value']", self.js)
        prepare = 'function prepareDividend(' + self.js.split(
            'function prepareDividend(', 1)[1].split('\n  function syncDividendPeriodControls(', 1)[0]
        self.assertRegex(prepare, r'const\s+source\s*=\s*await\s+dividendSource\s*\(\s*\)')
        self.assertRegex(prepare,
            r'aggregateFlow\s*\(\s*rows\s*,\s*modes\.dividend\s*,\s*\{\s*fields\s*:\s*\['
            r'''\s*['"]dividend_value['"]\s*,\s*['"]interest_value['"]\s*\]\s*\}\s*\)''')
        rows = re.search(r'const\s+rows\s*=\s*\[(?P<body>.*?)\]\s*;', prepare, re.S)
        self.assertIsNotNone(rows, 'aggregate input rows missing from prepareDividend')
        mappings = {}
        for kind, value_field, zero_field in (
            ('dividend', 'dividend_value', 'interest_value'),
            ('interest', 'interest_value', 'dividend_value'),
        ):
            mapping = re.search(
                rf'source\.{kind}\.map\(\s*record\s*=>\s*\(\{{(?P<body>.*?)\}}\)\s*\)', rows.group('body'), re.S)
            self.assertIsNotNone(mapping, f'{kind} source mapping missing from prepareDividend')
            mappings[kind] = mapping.start()
            body = mapping.group('body')
            self.assertRegex(body, rf'''\bincome_kind\s*:\s*['"]{kind}['"]''')
            self.assertRegex(body, rf'\b{value_field}\s*:\s*finite\s*\(\s*record\s*\?\.\s*amount_krw\s*\)')
            self.assertRegex(body, rf'\b{zero_field}\s*:\s*0\b')
        self.assertLess(mappings['dividend'], mappings['interest'])
        self.assertIn("fields: ['income_value', 'expense_value']", self.js)
        self.assertIn("year=all&trade_type=", self.js)
        self.assertIn("/api/actual-dividends?owner=", self.js)

    def test_ledger_daily_and_weekly_views_use_transaction_records(self):
        self.assertIn("modes.ledger === MODES.DAY || modes.ledger === MODES.WEEK", self.js)
        self.assertIn("cache.ledgerTransactions", self.js)
        self.assertIn("record?.type === 'income' || record?.type === 'expense'", self.js)

    def test_common_charts_have_fixed_amount_axis_scroll_and_panzoom(self):
        for marker in (
            "wealth-unified-axis",
            "overflow-x: auto",
            "addEventListener('wheel'",
            "event.touches.length !== 2",
            "startScrollLeft - (event.clientX - startX)",
            "compactWon",
        ):
            self.assertIn(marker, self.js)

    def test_scale_one_means_all_loaded_buckets_fit_viewport(self):
        self.assertIn("viewport.clientWidth) * state.scale", self.js)
        self.assertNotIn("state.bucketCount * bucketSlot", self.js)

    def test_year_markers_render_under_nonannual_period_labels(self):
        self.assertIn("if (mode === MODES.YEAR) return ''", self.js)
        self.assertIn("`${bucket.year}년`", self.js)
        self.assertIn("y=\"280\"", self.js)

    def test_monthly_pnl_and_dividend_drilldowns_remain_available(self):
        self.assertIn("renderPnlMonthlyDetail(null, value)", self.js)
        self.assertIn("renderActualDividendDetail(null, value)", self.js)

    def test_estimated_dividend_keeps_legacy_chart_without_misleading_period_controls(self):
        controls_code = 'function syncDividendPeriodControls(' + self.js.split(
            'function syncDividendPeriodControls(', 1)[1].split('\n  function monthKey(', 1)[0]
        click_code = 'function handleExternalClick(event) {' + self.js.split(
            'function handleExternalClick(event) {', 1)[1].split('\n  function hostNeedsUnified', 1)[0]
        script = r"""
const assert=require('node:assert/strict'),vm=require('node:vm');
let mode='actual',visible=true,reads=0;
const controls={hidden:true};
const host={dataset:{},firstElementChild:null,
 closest:()=>({querySelector:()=>({})}),querySelector(){return this.firstElementChild?.unified?{}:null;}};
const c={document:{querySelector:()=>controls,getElementById:id=>id==='dividendBarChartWrap'?host:null},
 dividendMode:()=>mode,WealthStartup:{visible:()=>visible},
 dividendScopeKey:()=>mode,currentOwnerValue:()=> 'synthetic',
 committedDividend:null,dividendRenderGeneration:0,cache:{dividend:{key:'synthetic'}},details:{},
 modes:{dividend:'1M'},MODE_LABEL:{'1M':'월간'},ensureInjectedControls:()=>controls,
 prepareDividend:async()=>{reads++;return {scope:mode,readEpoch:0,aggregated:{buckets:[{}]}};},
 updateDetail(){},selectBucket(){},renderFlowChart(){host.firstElementChild={unified:true};},
 clearDetail(){},queue(){},setTimeout:fn=>fn()};
vm.createContext(c);vm.runInContext(process.argv[1]+process.argv[2],c);
const click=()=>c.handleExternalClick({target:{closest:selector=>selector.includes('dividendModeTabs')?{}:null}});
(async()=>{
 await c.renderDividend();assert.equal(controls.hidden,false);assert(host.firstElementChild.unified);
 assert.equal(reads,1);
 mode='estimated';click();assert.equal(controls.hidden,true,'mode click hides controls immediately');
 const legacy={legacy:true};host.firstElementChild=legacy;
 await c.renderDividend();assert.equal(reads,1,'estimated mode must not read actual data');
 assert.equal(host.firstElementChild,legacy,'estimated legacy chart must remain untouched');
 visible=false;controls.hidden=false;await c.renderDividend();assert.equal(controls.hidden,true);
 assert.equal(reads,1,'inactive estimated rendering must not fetch');
 visible=true;mode='actual';click();assert.equal(controls.hidden,false,'actual click restores controls');
 await c.renderDividend();assert.equal(controls.hidden,false);assert(host.firstElementChild.unified);
 assert.equal(reads,2);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result = subprocess.run(['node', '-e', script, controls_code, click_code],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('.wealth-unified-periods[data-kind="dividend"][hidden] { display: none !important; }', self.js)

    def test_mutation_observer_does_not_rerender_its_own_owned_chart(self):
        self.assertIn("function hostNeedsUnified(hostId)", self.js)
        self.assertIn("wealth-unified-chart-shell", self.js)
        self.assertIn("!document.getElementById('recordsPanel')?.classList.contains('is-tax-view') && hostNeedsUnified('assetChart')", self.js)

    def test_tax_holdings_are_not_replaced_by_stock_record_chart(self):
        render_stock = "function renderStock() {" + self.js.split("function renderStock() {", 1)[1].split("\n  function captureNetWorthFromLegacy", 1)[0]
        script = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
let taxView = true;
let charts = 0;
const host = {innerHTML: '<table class="tax-holdings-table"></table>'};
const context = {
  document: {getElementById(id) {
    if (id === 'recordsPanel') return {classList: {contains() { return taxView; }}};
    return id === 'assetChart' ? host : {};
  }},
  adoptExistingControls() {}, stockSource() { return []; },
  aggregateState() { return {mode: 'ALL'}; },
  renderStateChart() { charts++; },
  modes: {stock: 'ALL'}, MODE_LABEL: {ALL: '전체'},
};
vm.createContext(context);
vm.runInContext(process.argv[1], context);
context.renderStock();
assert.equal(charts, 0);
assert.match(host.innerHTML, /tax-holdings-table/);
taxView = false;
context.renderStock();
assert.equal(charts, 1);
"""
        result = subprocess.run(["node", "-e", script, render_stock], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ledger_can_continue_loading_older_history_at_zoom_boundary(self):
        self.assertIn("onNeedOlder: extendLedgerHistory", self.js)
        self.assertIn("shiftMonthKey(earliest, -1)", self.js)

    def test_loader_orders_period_core_visible_range_label_layout_and_unified_adapter(self):
        self.assertIn("/static/wealth-timeseries-period-core.js?v=10.6k1", self.loader)
        self.assertIn("/static/wealth-timeseries-visible-range.js?v=10.6k4", self.loader)
        self.assertIn("/static/wealth-timeseries-label-layout.js?v=10.6k4", self.loader)
        self.assertIn("/static/wealth-timeseries-unified.js?v=2.1.3-p0", self.loader)
        self.assertIn("visibleRange.addEventListener('load', loadLabelLayout", self.loader)
        self.assertIn("script.addEventListener('load', loadUnified", self.loader)
        self.assertIn("periodCore.addEventListener('load', loadUnifiedTimeseries", self.loader)


if __name__ == "__main__":
    unittest.main()
