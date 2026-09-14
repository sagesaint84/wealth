from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"


class ForeignRealizedPnlFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not shutil.which("node"):
            raise unittest.SkipTest("node runtime is not available")
        cls.source = WEALTH_JS.read_text(encoding="utf-8")

    def run_summary_helper(self, summary: dict, records: list[dict], prefer_canonical: bool = True) -> dict:
        script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function finiteRealizedPnlNumber');
const end = source.indexOf('\nfunction renderSummary', start);
if (start < 0 || end < 0) throw new Error('realized P/L display helpers not found');
const sandbox = {};
vm.runInNewContext(source.slice(start, end) + '\nthis.build = buildRealizedPnlDisplaySummary;', sandbox);
const input = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(sandbox.build(input.summary, input.records, input.preferCanonical)));
"""
        result = subprocess.run(
            [
                "node", "-e", script, str(WEALTH_JS),
                json.dumps({"summary": summary, "records": records, "preferCanonical": prefer_canonical}),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return json.loads(result.stdout)

    def test_missing_krw_is_unconverted_not_financial_zero(self) -> None:
        view = self.run_summary_helper(
            {},
            [{"pnl": 10, "pnl_krw": None}, {"pnl": -2, "pnl_krw": 500}],
            False,
        )
        self.assertEqual(view["totalPnlKrw"], 500)
        self.assertEqual(view["convertedRecordCount"], 1)
        self.assertEqual(view["unconvertedRecordCount"], 1)
        self.assertFalse(view["summaryComplete"])

    def test_backend_canonical_total_and_native_win_rate_are_preserved(self) -> None:
        view = self.run_summary_helper(
            {
                "total_pnl_krw": 777,
                "converted_record_count": 1,
                "unconverted_record_count": 2,
                "record_count": 3,
                "win_rate": 66.7,
                "summary_complete": False,
            },
            [{"pnl": 99, "pnl_krw": 9999}],
        )
        self.assertTrue(view["canonicalUsed"])
        self.assertEqual(view["totalPnlKrw"], 777)
        self.assertEqual(view["winRate"], 66.7)
        self.assertEqual(view["unconvertedRecordCount"], 2)
        self.assertEqual(view["completenessNote"], "미환산 해외 실현손익 2건 포함")

    def test_complete_summary_retains_the_existing_unannotated_ui(self) -> None:
        view = self.run_summary_helper(
            {
                "total_pnl_krw": 100,
                "converted_record_count": 1,
                "unconverted_record_count": 0,
                "record_count": 1,
                "win_rate": 100,
                "summary_complete": True,
            },
            [],
        )
        self.assertTrue(view["summaryComplete"])
        self.assertEqual(view["completenessNote"], "")

    def test_renderers_use_backend_summary_and_do_not_zero_fill_raw_pnl(self) -> None:
        render_start = self.source.index("function renderSummary")
        render_end = self.source.index("\nfunction ", render_start + 20)
        render_body = self.source[render_start:render_end]
        overview_start = self.source.index("async function updateOverviewCardsAllTime")
        overview_end = self.source.index("\nasync function ", overview_start + 20)
        overview_body = self.source[overview_start:overview_end]
        self.assertIn("buildRealizedPnlDisplaySummary(curRealized, pnlRecords", render_body)
        self.assertNotIn("Number(r.pnl_krw || 0)", render_body)
        self.assertIn("buildRealizedPnlDisplaySummary(pnlRes, [], true)", overview_body)
        self.assertIn("pnlView.completenessNote", overview_body)
        monthly_start = self.source.index("function renderPnlMonthlyDetail")
        monthly_end = self.source.index("\nfunction calcPnlReProfit", monthly_start)
        monthly_body = self.source[monthly_start:monthly_end]
        self.assertNotIn("Number(cur.pnl_krw || 0)", monthly_body)
        self.assertNotIn("money(item.pnl_krw)", monthly_body)
        self.assertIn("formatOptionalRealizedPnlValue(item.pnl_krw", monthly_body)

    def test_render_with_owner_still_filters_accounts_and_holdings_before_render(self) -> None:
        script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function renderWithOwner');
const end = source.indexOf('\n// 다이얼로그', start);
if (start < 0 || end < 0) throw new Error('renderWithOwner not found');
const sandbox = {
  rawDashboard: null,
  dashboard: null,
  currentOwner: '모두',
  computeFilteredSummary: () => ({}),
  computeFilteredClassifications: () => [],
  computeFilteredSectors: () => [],
  computeFilteredCurrencySummary: () => ({}),
  computeFilteredDayChange: () => ({}),
  loadAssetRecords: () => {},
  loadLedger: () => {},
  render: data => { sandbox.result = data; },
};
vm.runInNewContext(source.slice(start, end) + '\nthis.run = renderWithOwner;', sandbox);
const data = {
  accounts: [{id: 'a', owner: 'A'}, {id: 'b', owner: 'B'}],
  holdings: [{id: 'ha', account_id: 'a'}, {id: 'hb', account_id: 'b'}],
};
sandbox.run(data, 'A');
process.stdout.write(JSON.stringify({
  accounts: sandbox.result.accounts.map(item => item.id),
  holdings: sandbox.result.holdings.map(item => item.id),
}));
"""
        result = subprocess.run(
            ["node", "-e", script, str(WEALTH_JS)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), {"accounts": ["a"], "holdings": ["ha"]})

    def test_preexisting_kb_ui_contract_markers_remain_present(self) -> None:
        self.assertIn("const kbRealizedState = {", self.source)
        self.assertIn("function renderKbFeedTable()", self.source)
        self.assertIn("function initKbRealizedUI()", self.source)
        self.assertIn("initKbRealizedUI();", self.source)


if __name__ == "__main__":
    unittest.main()
