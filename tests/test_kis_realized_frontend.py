from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")
LAYOUT_CSS = (ROOT / "app" / "static" / "wealth-layout.css").read_text(encoding="utf-8")


class KisRealizedFrontendTests(unittest.TestCase):
    def test_kis_uses_shared_control_selection_and_preview_structure(self) -> None:
        for marker in (
            "kisSourceAccount", "kisMarketSelect", "kisFromDate", "kisToDate",
            "btnFetchKisFeed", "kisSelectAll", "kisDestinationAccount",
            "kisImportOptions", "kisImportModalOverlay", "kisModalCountNew",
            "kisModalCountAlready", "kisModalCountDup", "kisModalCountInvalid",
            "btnKisConfirmCommit",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, HTML)
        self.assertIn("brokerImportSelectedItem(kisRealizedState, idx)", JS)
        self.assertIn("renderBrokerImportOptions(kisRealizedState", JS)
        self.assertIn("renderBrokerImportPreviewDetails(data, 'kisImportModalOverlay')", JS)

    def test_kis_tab_status_fetch_and_import_are_explicit(self) -> None:
        switch = re.search(r"if \(broker === 'kis'\) \{(?P<body>.*?)\n  \} else if \(broker === 'nh'\)", JS, re.DOTALL)
        self.assertIsNotNone(switch)
        self.assertNotIn("checkKisStatus(", switch.group("body"))
        self.assertNotIn("fetchKisRealizedFeed(", switch.group("body"))
        self.assertIn("btnCheckKisStatus')?.addEventListener('click', checkKisStatus", JS)
        self.assertIn("btnFetchKisFeed')?.addEventListener('click', fetchKisRealizedFeed", JS)
        self.assertIn("btnKisImportSelected')?.addEventListener('click', openKisImportPreview", JS)
        self.assertIn("btnKisConfirmCommit')?.addEventListener('click', commitKisImport", JS)

    def test_kis_table_matches_common_ten_column_shape_and_preserves_missing_values(self) -> None:
        section = HTML.split('id="kisRealizedCard"', 1)[1].split('id="nhRealizedCard"', 1)[0]
        self.assertIn('colspan="10"', section)
        self.assertIn("시장 / 통화", section)
        render = re.search(r"function renderKisFeedTable\(rows, market, state\) \{(?P<body>.*?)\n\}", JS, re.DOTALL)
        self.assertIsNotNone(render)
        body = render.group("body")
        self.assertIn("sellRaw == null", body)
        self.assertIn("buyRaw == null", body)
        self.assertIn("'—'", body)

    def test_kis_preview_uses_common_status_language_and_ipo_details(self) -> None:
        section = HTML.split('id="kisImportModalOverlay"', 1)[1].split('id="kisNotice"', 1)[0]
        for label in ("신규 등록 가능", "이미 가져옴", "중복 의심", "유효하지 않음"):
            self.assertIn(label, section)
        self.assertIn("brokerPreviewStatusLabel(it.status)", JS)
        self.assertIn("공모수수료 2천원 차감", (ROOT / "app" / "services" / "broker_realized_import.py").read_text(encoding="utf-8"))
        self.assertIn("provider_realized_pnl", JS)
        self.assertIn("final_wealth_pnl", JS)

    def test_kis_error_is_not_converted_to_successful_empty_response(self) -> None:
        fetch = re.search(r"async function fetchKisRealizedFeed\(\) \{(?P<body>.*?)\n\}", JS, re.DOTALL)
        self.assertIsNotNone(fetch)
        self.assertIn("if (!res.ok)", fetch.group("body"))
        self.assertIn("showKisMessage", fetch.group("body"))

    def test_kis_double_submit_and_partial_success_guards_match_new_flow(self) -> None:
        self.assertIn("kisRealizedState.importing || !kisRealizedState.previewTicket", JS)
        self.assertIn("kisRealizedState.importing = true", JS)
        self.assertIn("partial_success", JS)
        self.assertIn("mapping_repaired", JS)

    def test_shared_layout_remains_responsive(self) -> None:
        self.assertIn(".toss-wts-controls", LAYOUT_CSS)
        self.assertIn("flex-wrap: wrap", LAYOUT_CSS)
        self.assertIn("@media (max-width: 760px)", LAYOUT_CSS)
        self.assertIn("overflow-x: auto", LAYOUT_CSS)


if __name__ == "__main__":
    unittest.main()
