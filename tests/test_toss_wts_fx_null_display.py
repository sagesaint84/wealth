from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"


class TossWtsFxNullDisplayTests(unittest.TestCase):
    def run_helper(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node runtime is not available")
        script = r'''
const fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
const match = source.match(/function formatOptionalTossWtsFxDisplay\(record, value, formatter\) \{\r?\n  return record\?\.source === 'toss_wts' && value == null \? '—' : formatter\(value\);\r?\n\}/);
if (!match) process.exit(2);
eval(match[0]);
const before = {source: 'toss_wts', fx_rate: null, fx_pnl_krw: null};
const snapshot = JSON.stringify(before);
if (formatOptionalTossWtsFxDisplay(before, before.fx_rate, value => `rate:${value}`) !== '—') process.exit(3);
if (formatOptionalTossWtsFxDisplay(before, before.fx_pnl_krw, value => `pnl:${value}`) !== '—') process.exit(4);
if (formatOptionalTossWtsFxDisplay({source: 'toss_wts'}, 0, value => `zero:${value}`) !== 'zero:0') process.exit(5);
if (formatOptionalTossWtsFxDisplay({source: 'toss_wts'}, 12, value => `number:${value}`) !== 'number:12') process.exit(6);
if (formatOptionalTossWtsFxDisplay({source: 'manual', broker: '토스증권'}, null, value => `legacy:${value}`) !== 'legacy:null') process.exit(7);
if (JSON.stringify(before) !== snapshot) process.exit(8);
'''
        result = subprocess.run(["node", "-e", script, str(WEALTH_JS)], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_aware_null_display_and_numeric_preservation(self):
        self.run_helper()

    def test_realized_detail_uses_local_source_aware_branches(self):
        source = WEALTH_JS.read_text(encoding="utf-8")
        self.assertIn("const wtsFxPnlUnavailable = item.source === 'toss_wts' && item.fx_pnl_krw == null;", source)
        self.assertIn("const fxRateDisplay = formatOptionalTossWtsFxDisplay(item, item.fx_rate", source)
        self.assertIn("const fxPnlDisplay = formatOptionalTossWtsFxDisplay(item, item.fx_pnl_krw", source)
        self.assertNotIn("broker === '토스증권'", source[source.index("function formatOptionalTossWtsFxDisplay"):source.index("function formatOptionalTossWtsFxDisplay") + 1200])

    def test_format_optional_toss_wts_fx_display_static_contract(self):
        source = WEALTH_JS.read_text(encoding="utf-8")
        self.assertIn("function formatOptionalTossWtsFxDisplay(record, value, formatter) {", source)
        self.assertIn("return record?.source === 'toss_wts' && value == null ? '—' : formatter(value);", source)


if __name__ == "__main__":
    unittest.main()
