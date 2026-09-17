from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TestStockRecordDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
        cls.wealth_js = (ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")
        cls.layout_js = (ROOT / "app" / "static" / "wealth-layout.js").read_text(encoding="utf-8")
        cls.planning_js = (ROOT / "app" / "static" / "wealth-planning.js").read_text(encoding="utf-8")

        # Extract the assetRecordDialog block
        m = re.search(r'<dialog id="assetRecordDialog"[^>]*>(.*?)</dialog>', cls.html, re.DOTALL)
        cls.dialog_html = m.group(1) if m else ""

    def test_stock_dialog_titles_for_add_and_edit(self):
        # 1. Add modal default title in index.html
        self.assertIn('<h2 id="assetRecordDialogTitle">주식기록 추가</h2>', self.dialog_html)

        # 2. Dynamic title switching in wealth.js
        self.assertIn('record ? "주식기록 수정" : "주식기록 추가"', self.wealth_js)
        self.assertNotIn('record ? "자산기록 수정" : "자산기록 추가"', self.wealth_js)

    def test_stock_dialog_contains_exact_11_fields_in_order(self):
        self.assertTrue(self.dialog_html, "assetRecordDialog must exist in index.html")

        # Extract labels from record-form-grid
        grid_m = re.search(r'<div class="form-grid record-form-grid">(.*?)</div>', self.dialog_html, re.DOTALL)
        self.assertIsNotNone(grid_m, "record-form-grid must be present")
        grid_content = grid_m.group(1)

        # Extract label texts
        label_matches = re.findall(r'<label>\s*([^<\n]+)', grid_content)
        labels = [lbl.strip() for lbl in label_matches]

        expected_labels = [
            "날짜",
            "총주식자산",
            "총매입금액",
            "총수익",
            "수익률",
            "일간수익",
            "원화자산",
            "달러자산환산",
            "보유종목수",
            "메모",
            "구성원",
        ]
        self.assertEqual(labels, expected_labels, f"Dialog must contain exact 11 fields in order: {labels}")

    def test_stock_dialog_canonical_field_names(self):
        # Canonical name for 총주식자산 must be total_value_krw
        self.assertIn('name="total_value_krw"', self.dialog_html)
        self.assertIn('name="date"', self.dialog_html)
        self.assertIn('name="total_cost_krw"', self.dialog_html)
        self.assertIn('name="profit_krw"', self.dialog_html)
        self.assertIn('name="return_rate"', self.dialog_html)
        self.assertIn('name="day_profit_krw"', self.dialog_html)
        self.assertIn('name="krw_value_krw"', self.dialog_html)
        self.assertIn('name="usd_value_krw"', self.dialog_html)
        self.assertIn('name="holding_count"', self.dialog_html)
        self.assertIn('name="memo"', self.dialog_html)
        self.assertIn('name="owner"', self.dialog_html)

    def test_removed_fields_not_present_in_stock_modal(self):
        # Verify that 순자산, 총부채, 총자산, 총 투자자산 are not in the dialog HTML
        labels = re.findall(r'<label>\s*([^<\n]+)', self.dialog_html)
        clean_labels = [l.strip() for l in labels]

        self.assertNotIn("순자산", clean_labels)
        self.assertNotIn("총부채", clean_labels)
        self.assertNotIn("총자산", clean_labels)
        self.assertNotIn("총 투자자산", clean_labels)
        self.assertNotIn('name="total_assets_krw"', self.dialog_html)
        self.assertNotIn('name="total_debt_krw"', self.dialog_html)
        self.assertNotIn('name="net_worth_krw"', self.dialog_html)

        # wealth-layout.js must not inject net worth fields into assetRecordForm
        self.assertNotIn("total_assets_krw", self.layout_js)
        self.assertNotIn("total_debt_krw", self.layout_js)

    def test_stock_record_edit_binding_in_wealth_js(self):
        # Check openAssetRecordDialog binds all 11 fields
        self.assertIn("form.date.value = record?.date", self.wealth_js)
        self.assertIn("form.total_value_krw.value = record?.total_value_krw", self.wealth_js)
        self.assertIn("form.total_cost_krw.value = record?.total_cost_krw", self.wealth_js)
        self.assertIn("form.profit_krw.value = record?.profit_krw", self.wealth_js)
        self.assertIn("form.return_rate.value = record?.return_rate", self.wealth_js)
        self.assertIn("form.day_profit_krw.value = record?.day_profit_krw", self.wealth_js)
        self.assertIn("form.krw_value_krw.value = record?.krw_value_krw", self.wealth_js)
        self.assertIn("form.usd_value_krw.value = record?.usd_value_krw", self.wealth_js)
        self.assertIn("form.holding_count.value = record?.holding_count", self.wealth_js)
        self.assertIn("form.memo.value = record?.memo", self.wealth_js)
        self.assertIn("form.owner.value = record?.owner", self.wealth_js)

    def test_save_payload_and_backward_compatibility_maintained(self):
        # Submit handler creates safe fallbacks for legacy consumers using zero-safe checks
        self.assertIn("!isPresent(payload.total_value_krw) && isPresent(payload.total_assets_krw)", self.wealth_js)
        self.assertIn("!isPresent(payload.total_assets_krw) && isPresent(payload.total_value_krw)", self.wealth_js)
        self.assertIn('payload.owner = payload.owner || currentOwner || "모두";', self.wealth_js)

    def test_zero_safe_compatibility_fallback_preserves_zero(self):
        import json
        import shutil
        import subprocess

        # 1. Verify static code patterns in wealth.js
        self.assertIn("const isPresent = v => v !== null && v !== undefined && String(v).trim() !== \"\"", self.wealth_js)
        self.assertIn("record?.total_value_krw ?? record?.total_assets_krw ?? \"\"", self.wealth_js)

        # 2. Dynamic execution of wealth.js fallback logic via node
        node_path = shutil.which("node")
        if node_path:
            node_script = """
            const fs = require('fs');
            const js = fs.readFileSync('app/static/wealth.js', 'utf8');
            const match = js.match(/(const isPresent = [\\s\\S]*?payload\\.owner = payload\\.owner[\\s\\S]*?;)/);
            if (!match) {
                console.error("Snippet not found");
                process.exit(1);
            }
            const fn = new Function('payload', 'currentOwner', match[1] + '\\nreturn payload;');

            // Case 1: total_value_krw is explicitly 0, total_assets_krw is positive -> 0 must be preserved
            const c1 = fn({ total_value_krw: 0, total_assets_krw: 500000 });
            if (c1.total_value_krw !== 0 || c1.total_assets_krw !== 500000) {
                console.error("Case 1 failed: 0 was overwritten", c1);
                process.exit(2);
            }

            // Case 2: total_value_krw is positive, total_assets_krw is explicitly 0 -> 0 must be preserved
            const c2 = fn({ total_value_krw: 500000, total_assets_krw: 0 });
            if (c2.total_value_krw !== 500000 || c2.total_assets_krw !== 0) {
                console.error("Case 2 failed: 0 was overwritten", c2);
                process.exit(3);
            }

            // Case 3: total_value_krw is "0", total_assets_krw missing -> fallback to 0
            const c3 = fn({ total_value_krw: "0" });
            if (c3.total_value_krw !== 0 || c3.total_assets_krw !== 0) {
                console.error("Case 3 failed", c3);
                process.exit(4);
            }

            // Case 4: total_value_krw is empty string, total_assets_krw is 0 -> fallback to 0
            const c4 = fn({ total_value_krw: "", total_assets_krw: 0 });
            if (c4.total_value_krw !== 0 || c4.total_assets_krw !== 0) {
                console.error("Case 4 failed", c4);
                process.exit(5);
            }

            // Case 5: total_value_krw is null, total_assets_krw is 0 -> fallback to 0
            const c5 = fn({ total_value_krw: null, total_assets_krw: 0 });
            if (c5.total_value_krw !== 0 || c5.total_assets_krw !== 0) {
                console.error("Case 5 failed", c5);
                process.exit(6);
            }

            // Case 6: net_worth_krw is explicitly 0 -> preserved, not recalculated
            const c6 = fn({ total_value_krw: 1000, total_debt_krw: 200, net_worth_krw: 0 });
            if (c6.net_worth_krw !== 0) {
                console.error("Case 6 failed: net_worth_krw 0 was overwritten", c6);
                process.exit(7);
            }

            console.log("ALL_ZERO_SAFE_TESTS_PASSED");
            """
            result = subprocess.run(
                [node_path, "-e", node_script],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, f"Node zero-safe test failed: {result.stderr or result.stdout}")
            self.assertIn("ALL_ZERO_SAFE_TESTS_PASSED", result.stdout)

    def test_owner_selector_has_expected_members(self):
        # Options in owner select
        owner_m = re.search(r'<select name="owner">(.*?)</select>', self.dialog_html, re.DOTALL)
        self.assertIsNotNone(owner_m, "owner select must exist in dialog")
        options = re.findall(r'<option value="([^"]+)">', owner_m.group(1))
        self.assertEqual(options, ["모두", "아빠", "엄마", "자녀"])

    def test_net_worth_history_dialog_remains_independent_and_unaffected(self):
        # wealth-planning.js has wealthHistoryEditForm with Net Worth fields intact
        self.assertIn('id="wealthHistoryEditForm"', self.planning_js)
        self.assertIn('name="assets"', self.planning_js)
        self.assertIn('name="debt"', self.planning_js)
        self.assertIn('name="net_worth"', self.planning_js)
        self.assertIn('과거 기록 추가', self.planning_js)
        self.assertIn('기록 수정', self.planning_js)


if __name__ == "__main__":
    unittest.main()
