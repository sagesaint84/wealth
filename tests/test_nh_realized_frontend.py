"""Focused source-level checks for the NH realized-P/L browser workflow.

These tests intentionally do not launch a browser or make provider requests.
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from tests.test_broker_realized_ipo_frontend import (
    FEATURE as JS, SCREEN, UI, assert_explicit_broker_tab, assert_mapped_import, broker_function,
)

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")


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
        assert_explicit_broker_tab(self, "nh", "Nh")

    def test_tab_switch_does_not_auto_fetch_nh_status(self) -> None:
        assert_explicit_broker_tab(self, "nh", "Nh")

    def test_shared_display_masking_is_used_by_kis_and_nh(self) -> None:
        self.assertIn("function maskAccountDisplayLabel", JS)
        self.assertIn("maskAccountDisplayLabel(dest.account_name", broker_function(JS, "renderKisPreviewModal"))
        self.assertIn("brokerUI.brokerPreviewDestinationText(dest, maskAccountDisplayLabel)", SCREEN)
        self.assertIn("maskAccountDisplayLabel(destination.account_name", broker_function(UI, "brokerPreviewDestinationText"))
        self.assertIn("maskAccountDisplayLabel(account.account_name", broker_function(UI, "populateBrokerDestinationAccountSelect"))
        self.assertIn('id="nhModalDestAccountDisplay"', HTML)
        self.assertIn("wtsModalDestAccountName", JS)
        self.assertIn("persisted account name", JS)

    def test_display_masking_handles_synthetic_korean_account_labels(self) -> None:
        import shutil
        if not shutil.which("node"):
            self.skipTest("node runtime is not available")
        script = r'''
const fs = require("fs");
const vm = require("node:vm");
const sandbox = {document: {}};
sandbox.window = sandbox;
sandbox.WealthBrokerRealizedScreenController = {create: () => ({})};
vm.createContext(sandbox);
for (const asset of ["wealth-broker-realized-feed-controller.js", "wealth-broker-import-feature-controller.js"]) {
  vm.runInContext(fs.readFileSync("app/static/" + asset, "utf8"), sandbox);
}
const { maskAccountDisplayLabel } = sandbox.WealthBrokerImportFeatureController.create({
  window: sandbox, document: sandbox.document, brokerUI: {},
}).actions;
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
        nh_section = HTML.split('id="nhRealizedCard"', 1)[1].split('id="kiwoomRealizedCard"', 1)[0]
        self.assertNotIn("act_no", nh_section)
        self.assertNotIn("account_no", nh_section)
        self.assertIn("source_account_key", JS)  # opaque route scope only

    def test_overseas_columns_do_not_claim_fabricated_krw_or_fx(self) -> None:
        self.assertIn("nhScreenController.renderFeedTable()", broker_function(JS, "renderNhFeedTable"))
        self.assertIn("brokerRealizedDisplayRow", broker_function(SCREEN, "renderFeedTable"))
        display = broker_function(JS, "brokerRealizedDisplayRow")
        self.assertIn("present(row.expenses_total)", display)
        self.assertIn("currency === 'USD'", display)
        self.assertNotIn("row.pnl_krw", display)
        self.assertRegex(display, r"if \(kis && market === 'us'\) \{\s+if \(present\(row.profit_loss_krw\)\)")
        self.assertNotIn("kis: true", JS.split("const nhScreenController", 1)[1].split("\n    });", 1)[0])

    def test_double_submit_guard_and_preview_gate_exist(self) -> None:
        assert_mapped_import(self, "nh", "Nh")

    def test_existing_toss_and_kis_hooks_remain(self) -> None:
        for marker in ("btnTabBrokerToss", "btnTabBrokerKis", "tossWtsCard", "kisRealizedCard"):
            self.assertIn(marker, HTML)


if __name__ == "__main__":
    unittest.main()
