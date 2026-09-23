from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class RecordChangeFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wealth_js = (ROOT / "app/static/wealth.js").read_text(encoding="utf-8")
        cls.planning_js = (ROOT / "app/static/wealth-planning.js").read_text(encoding="utf-8")

    def test_stock_card_separates_record_change_from_price_profit(self):
        self.assertIn("const previousByRecord = buildPreviousRecordMap(rawList);", self.wealth_js)
        self.assertIn("Number(item.total_value_krw || 0) - Number(previous.total_value_krw || 0)", self.wealth_js)
        self.assertIn('class="record-row-head"', self.wealth_js)
        self.assertIn('class="record-row-change"', self.wealth_js)
        self.assertIn('class="record-row-day-profit"', self.wealth_js)
        self.assertIn('class="record-row-meta"', self.wealth_js)
        self.assertIn('class="record-row-actions"', self.wealth_js)
        self.assertIn("전 기록 대비", self.wealth_js)
        self.assertIn("가격변동 손익", self.wealth_js)
        self.assertIn("item.memo || item.source", self.wealth_js)
        self.assertNotIn('signClass(item.day_profit_krw || 0)', self.wealth_js)

    def test_net_worth_card_uses_all_owner_records(self):
        self.assertIn("renderHistoryDetails(details, records, allRecords)", self.planning_js)
        self.assertIn("buildHistoryPreviousRecordMap(allRecords)", self.planning_js)
        self.assertIn("직전 기록 없음", self.planning_js)
        self.assertIn("wealth-history-record-change", self.planning_js)

    def test_previous_maps_keep_values_independent_of_filtered_view_and_owner(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node runtime is not available")
        script = r"""
const fs = require('fs');
const vm = require('vm');

function loadFunction(path, name) {
  const source = fs.readFileSync(path, 'utf8');
  const start = source.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`${name} not found`);
  const brace = source.indexOf('{', start);
  let depth = 0;
  for (let i = brace; i < source.length; i++) {
    if (source[i] === '{') depth++;
    if (source[i] === '}' && --depth === 0) {
      const context = {};
      vm.runInNewContext(`${source.slice(start, i + 1)}; this.fn = ${name};`, context);
      return context.fn;
    }
  }
  throw new Error(`${name} is incomplete`);
}

const stockPrevious = loadFunction('app/static/wealth.js', 'buildPreviousRecordMap');
const historyPrevious = loadFunction('app/static/wealth-planning.js', 'buildHistoryPreviousRecordMap');

const stocks = [
  {date:'2026-09-18', owner:'모두', total_value_krw:1469402230, day_profit_krw:10},
  {date:'2026-09-19', owner:'모두', total_value_krw:1475009990, day_profit_krw:20},
  {date:'2026-09-20', owner:'모두', total_value_krw:1475009990, day_profit_krw:30},
  {date:'2026-09-21', owner:'모두', total_value_krw:1504009644, day_profit_krw:999},
  {date:'2026-09-22', owner:'모두', total_value_krw:1508504799, day_profit_krw:0},
];
const stockMap = stockPrevious(stocks);
const changes = stocks.map((r) => {
  const previous = stockMap.get(r);
  return previous ? r.total_value_krw - previous.total_value_krw : null;
});
if (JSON.stringify(changes) !== JSON.stringify([null, 5607760, 0, 28999654, 4495155])) throw new Error(JSON.stringify(changes));
if (stocks[4].day_profit_krw !== 0 || changes[4] === 0) throw new Error('record change must be independent of zero day profit');
if (stocks[3].day_profit_krw === 0 || changes[2] !== 0) throw new Error('zero record change must be independent of day profit');

const history = [
  {date:'2026-09-01', owner:'아빠', net_worth:100},
  {date:'2026-09-15', owner:'아빠', net_worth:110},
  {date:'2026-09-18', owner:'엄마', net_worth:999},
  {date:'2026-09-20', owner:'아빠', net_worth:130},
  {date:'2026-09-21', owner:'아빠', net_worth:150},
];
const historyMap = historyPrevious(history);
if (history[3].net_worth - historyMap.get(history[3]).net_worth !== 20) throw new Error('filtered first record lost its predecessor');
if (historyMap.get(history[2]) !== null) throw new Error('owners must not be compared');
if (historyMap.get(history[0]) !== null) throw new Error('first owner record must have no predecessor');
console.log('RECORD_CHANGE_FRONTEND_OK');
"""
        result = subprocess.run([node, "-e", script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("RECORD_CHANGE_FRONTEND_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
