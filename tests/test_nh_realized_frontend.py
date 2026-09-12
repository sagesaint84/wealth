"""Focused source-level checks for the NH realized-P/L browser workflow.

These tests intentionally do not launch a browser or make provider requests.
"""
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")


class NhRealizedFrontendTests(unittest.TestCase):
    def test_nh_tab_card_and_explicit_controls_exist(self) -> None:
        for marker in (
            "btnTabBrokerNh", "nhRealizedCard", "nhMarketSelect", "nhFromDate",
            "nhToDate", "nhSourceAccount", "btnCheckNhStatus", "btnFetchNhFeed",
            "nhTableBody", "nhSelectAll", "nhDestinationAccount", "btnNhImportSelected",
            "nhImportModalOverlay", "btnNhConfirmCommit",
        ):
            self.assertIn(marker, HTML)

    def test_nh_uses_only_its_backend_routes(self) -> None:
        for route in (
            "/api/nh/status", "/api/nh/realized-feed/fetch",
            "/api/nh/realized-feed/import-preview", "/api/nh/realized-feed/import",
        ):
            self.assertIn(route, JS)
        self.assertIn("const nhRealizedState", JS)
        self.assertIn("const kisRealizedState", JS)
        self.assertIn("switchRealizedBroker('nh')", JS)

    def test_tab_switch_does_not_auto_fetch_nh_status(self) -> None:
        switch_body = re.search(r"else if \(broker === 'nh'\) \{(?P<body>.*?)\n  \} else", JS, re.DOTALL)
        self.assertIsNotNone(switch_body)
        self.assertNotIn("checkNhStatus(", switch_body.group("body"))
        self.assertIn("btnCheckNhStatus", JS)

    def test_shared_display_masking_is_used_by_kis_and_nh(self) -> None:
        self.assertIn("function maskAccountDisplayLabel", JS)
        self.assertGreaterEqual(JS.count("maskAccountDisplayLabel("), 7)
        self.assertIn("kisModalDestAccountDisplay", JS)
        self.assertIn("nhModalDestAccountDisplay", JS)
        self.assertIn("wtsModalDestAccountName", JS)
        self.assertIn("persisted account name", JS)

    def test_display_masking_handles_synthetic_korean_account_labels(self) -> None:
        import shutil
        if not shutil.which("node"):
            self.skipTest("node runtime is not available")
        script = r'''
const fs = require("fs");
const source = fs.readFileSync("app/static/wealth.js", "utf8");
const match = source.match(/function maskAccountDisplayLabel\(value\) \{[\s\S]*?\r?\n\}\r?\n\r?\nconst kisRealizedState/);
if (!match) process.exit(2);
eval(match[0].replace(/\r?\n\r?\nconst kisRealizedState$/, ""));
console.log(JSON.stringify([
  maskAccountDisplayLabel("12345678"),
  maskAccountDisplayLabel("1234567890"),
  maskAccountDisplayLabel("123-45-678901"),
  maskAccountDisplayLabel("NH 계좌 1234-5678-90"),
  maskAccountDisplayLabel("NH 계좌 ****7890 / 87654321"),
  maskAccountDisplayLabel("NH 계좌 ****7890"),
  maskAccountDisplayLabel(maskAccountDisplayLabel("NH 계좌 1234-5678-90")),
  maskAccountDisplayLabel("연도 2026"),
  "NH 계좌 1234-5678-90"
]));
'''
        completed = subprocess.run(
            ["node", "-e", script], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8",
        )
        values = __import__("json").loads(completed.stdout)
        self.assertEqual(values[0], "****5678")
        self.assertEqual(values[1], "******7890")
        self.assertEqual(values[2], "***-**-**8901")
        self.assertNotIn("1234567890", values[3].replace("-", ""))
        self.assertIn("****7890", values[4])
        self.assertNotIn("87654321", values[4])
        self.assertEqual(values[5], "NH 계좌 ****7890")
        self.assertEqual(values[6], values[3])
        self.assertEqual(values[7], "연도 2026")
        self.assertEqual(values[8], "NH 계좌 1234-5678-90")
        for rendered in values[:7]:
            for raw in ("12345678", "1234567890", "12345678901", "87654321"):
                self.assertNotIn(raw, rendered.replace("-", "").replace(" ", ""))

    def test_no_raw_nh_account_number_field_is_rendered(self) -> None:
        nh_section = HTML.split('id="nhRealizedCard"', 1)[1]
        self.assertNotIn("act_no", nh_section)
        self.assertNotIn("account_no", nh_section)
        self.assertIn("source_account_key", JS)  # opaque route scope only

    def test_overseas_columns_do_not_claim_fabricated_krw_or_fx(self) -> None:
        render_body = re.search(r"function renderNhFeedTable\(\) \{(?P<body>.*?)\n\}\nfunction updateNhSelectionUI", JS, re.DOTALL)
        self.assertIsNotNone(render_body)
        self.assertIn("expenses_total", render_body.group("body"))
        self.assertNotIn("pnl_krw", render_body.group("body"))
        self.assertNotIn("fx_rate", render_body.group("body"))

    def test_double_submit_guard_and_preview_gate_exist(self) -> None:
        self.assertIn("nhRealizedState.importing || !nhRealizedState.previewTicket", JS)
        self.assertIn("nhRealizedState.importing = true", JS)
        self.assertIn("if (!accountId)", JS)
        self.assertIn("preview_ticket: nhRealizedState.previewTicket", JS)

    def test_existing_toss_and_kis_hooks_remain(self) -> None:
        for marker in ("btnTabBrokerToss", "btnTabBrokerKis", "tossWtsCard", "kisRealizedCard"):
            self.assertIn(marker, HTML)


if __name__ == "__main__":
    unittest.main()
