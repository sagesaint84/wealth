from __future__ import annotations

import unittest
from pathlib import Path

from tests.test_broker_realized_ipo_frontend import (
    FEATURE as JS, MODEL, assert_explicit_broker_tab, broker_function,
)

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
LAYOUT_CSS = (ROOT / "app" / "static" / "wealth-layout.css").read_text(encoding="utf-8")


class KisRealizedFrontendTests(unittest.TestCase):
    def test_kis_uses_shared_control_selection_and_preview_structure(self) -> None:
        for marker in (
            "kisSourceAccount", "kisMarketSelect", "kisFromDate", "kisToDate",
            "btnFetchKisFeed", "kisSelectAll", "kisDestinationAccount",
            "kisTableBody", "kisImportModalOverlay", "kisModalCountNew",
            "kisModalCountAlready", "kisModalCountDup", "kisModalCountInvalid",
            "btnKisConfirmCommit",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, HTML)
        self.assertIn("selectedImportItems(kisRealizedState, brokerImportSelectedItem)", broker_function(JS, "kisSelectedItems"))
        self.assertIn("syncBrokerRowImportOptions", JS.split("const kisScreenController", 1)[1].split("\n    });", 1)[0])
        self.assertIn("renderBrokerImportPreviewDetails(data, 'kisImportModalOverlay')", JS)

    def test_kis_tab_status_fetch_and_import_are_explicit(self) -> None:
        assert_explicit_broker_tab(self, "kis", "Kis")
        bind = broker_function(JS, "initKisRealizedUI")
        self.assertIn("btnKisImportSelected')?.addEventListener('click', openKisImportPreview", bind)
        self.assertIn("btnKisConfirmCommit')?.addEventListener('click', commitKisImport", bind)

    def test_kis_table_matches_common_ten_column_shape_and_preserves_missing_values(self) -> None:
        section = HTML.split('id="kisRealizedCard"', 1)[1].split('id="nhRealizedCard"', 1)[0]
        self.assertIn('colspan="10"', section)
        self.assertIn("시장 / 통화", section)
        self.assertIn("kisScreenController.renderFeedTable(rows, market", broker_function(JS, "renderKisFeedTable"))
        row = broker_function(JS, "brokerRealizedDisplayRow")
        self.assertIn("present(value) ?", row)
        self.assertIn(": '';", row)
        self.assertIn("buy: amount(rawAmount('buy_amount')), sell: amount(rawAmount('sell_amount'))", row)

    def test_kis_preview_uses_common_status_language_and_ipo_details(self) -> None:
        section = HTML.split('id="kisImportModalOverlay"', 1)[1].split('id="kisNotice"', 1)[0]
        for label in ("신규 등록 가능", "이미 가져옴", "중복 의심", "유효하지 않음"):
            self.assertIn(label, section)
        self.assertIn("brokerPreviewStatusLabel(it.status)", JS)
        self.assertIn("공모수수료 2천원 차감", (ROOT / "app" / "services" / "broker_realized_import.py").read_text(encoding="utf-8"))
        self.assertIn("provider_realized_pnl", MODEL)
        self.assertIn("final_wealth_pnl", MODEL)

    def test_kis_error_is_not_converted_to_successful_empty_response(self) -> None:
        fetch = broker_function(JS, "fetchKisRealizedFeed")
        self.assertIn("if (!res.ok)", fetch)
        self.assertIn("showKisMessage", fetch)
        self.assertLess(fetch.index("if (!res.ok)"), fetch.index("applySuccessfulFeed"))

    def test_kis_double_submit_and_partial_success_guards_match_new_flow(self) -> None:
        self.assertIn("kisRealizedState.importing || !kisRealizedState.previewTicket", JS)
        self.assertIn("kisRealizedState.importing = true", JS)
        self.assertIn("partial_success", JS)
        self.assertIn("mapping_repaired", JS)

    def test_destination_options_use_broker_scoped_candidates(self) -> None:
        self.assertIn("function realizedDestinationAccounts(accounts, provider, candidateIds)", JS)
        self.assertIn("realizedBrokerId(account.broker) === provider", JS)
        self.assertIn("candidate_account_ids", JS)
        self.assertIn("해당 증권사 계좌를 먼저 등록하세요.", JS)
        self.assertIn("realizedDestinationAccounts(accounts, 'kis'", broker_function(JS, "populateKisDestinationAccounts"))
        self.assertIn("realizedDestinationAccounts(accounts, broker, source?.candidate_account_ids)",
                      broker_function(JS, "populateOpenApiDestinationAccounts"))
        for provider, title in (("nh", "Nh"), ("kiwoom", "Kiwoom"), ("kb", "Kb")):
            self.assertIn(f"populateOpenApiDestinationAccounts(select, {provider}RealizedState, '{provider}')",
                          broker_function(JS, f"populate{title}DestinationAccounts"))

    def test_shared_layout_remains_responsive(self) -> None:
        self.assertIn(".toss-wts-controls", LAYOUT_CSS)
        self.assertIn("flex-wrap: wrap", LAYOUT_CSS)
        self.assertIn("@media (max-width: 760px)", LAYOUT_CSS)
        self.assertIn("overflow-x: auto", LAYOUT_CSS)


if __name__ == "__main__":
    unittest.main()
