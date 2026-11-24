"""Focused source-level checks for the Kiwoom realized-P/L browser workflow.

These tests verify frontend UI wiring, safe defaults, masking, and contract invariants
without launching a browser or performing real provider calls.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tests.test_broker_realized_ipo_frontend import (
    FEATURE as JS, FEED, PREVIEW_SCREEN, SCREEN, UI, assert_explicit_broker_tab, assert_mapped_import, broker_function, mapped_config,
)

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")


class KiwoomRealizedFrontendTests(unittest.TestCase):
    def test_kiwoom_tab_card_and_explicit_controls_exist(self) -> None:
        for marker in (
            "btnTabBrokerKiwoom", "kiwoomRealizedCard", "kiwoomMarketSelect", "kiwoomFromDate",
            "kiwoomToDate", "kiwoomSourceAccount", "btnCheckKiwoomStatus", "btnFetchKiwoomFeed",
            "kiwoomTableBody", "kiwoomSelectAll", "kiwoomDestinationAccount", "btnKiwoomImportSelected",
            "kiwoomImportModalOverlay", "btnKiwoomConfirmCommit", "kiwoomExpenseColumn",
            "kiwoomModalCountNew", "kiwoomModalCountAlready", "kiwoomModalCountDup",
            "kiwoomModalCountInvalid", "kiwoomIncludePossibleDuplicates",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, HTML)

    def test_kiwoom_uses_only_its_backend_routes(self) -> None:
        for route in (
            "/api/kiwoom/status",
            "/api/kiwoom/realized-feed/fetch",
            "/api/kiwoom/realized-feed/import-preview",
            "/api/kiwoom/realized-feed/import",
        ):
            with self.subTest(route=route):
                self.assertIn(route, JS)
        self.assertIn("const kiwoomRealizedState", JS)
        assert_explicit_broker_tab(self, "kiwoom", "Kiwoom")

    def test_tab_switch_does_not_auto_fetch_kiwoom_status_or_feed(self) -> None:
        assert_explicit_broker_tab(self, "kiwoom", "Kiwoom")

    def test_market_selection_options_and_no_auto_fetch(self) -> None:
        kiwoom_section = HTML.split('id="kiwoomRealizedCard"', 1)[1].split('</div>\n          </div>', 1)[0]
        self.assertIn('value="kr"', kiwoom_section)
        self.assertIn('value="us"', kiwoom_section)
        # Verify market select change does not trigger auto-fetch in JS
        self.assertNotIn("kiwoomMarketSelect')?.addEventListener('change', fetchKiwoom", JS)

    def test_shared_display_masking_is_used_by_kiwoom(self) -> None:
        self.assertIn("function maskAccountDisplayLabel", JS)
        self.assertIn('id="kiwoomModalDestAccountDisplay"', HTML)
        self.assertIn("maskAccountDisplayLabel(destination.account_name", broker_function(UI, "brokerPreviewDestinationText"))
        self.assertIn("brokerUI.brokerPreviewDestinationText(dest, maskAccountDisplayLabel)", SCREEN)
        self.assertIn("destinationId: `${prefix}ModalDestAccountDisplay`", PREVIEW_SCREEN)
        self.assertIn("populateOpenApiDestinationAccounts(select, kiwoomRealizedState, 'kiwoom')",
                      broker_function(JS, "populateKiwoomDestinationAccounts"))

    def test_no_raw_kiwoom_account_number_field_is_rendered(self) -> None:
        kiwoom_section = HTML.split('id="kiwoomRealizedCard"', 1)[1].split('id="kbRealizedCard"', 1)[0]
        self.assertNotIn("acctNo", kiwoom_section)
        self.assertNotIn("account_no", kiwoom_section)
        self.assertNotIn("appkey", kiwoom_section)
        self.assertNotIn("secretkey", kiwoom_section)
        self.assertIn("source_account_key", JS)  # opaque route scope only

    def test_overseas_columns_do_not_claim_fabricated_krw_or_fx(self) -> None:
        self.assertIn("kiwoomScreenController.renderFeedTable()", broker_function(JS, "renderKiwoomFeedTable"))
        self.assertIn("brokerRealizedDisplayRow", broker_function(SCREEN, "renderFeedTable"))
        display = broker_function(JS, "brokerRealizedDisplayRow")
        self.assertIn("present(row.expenses_total)", display)
        self.assertIn("currency === 'USD'", display)
        self.assertNotIn("row.pnl_krw", display)
        self.assertRegex(display, r"if \(kis && market === 'us'\) \{\s+if \(present\(row.profit_loss_krw\)\)")
        self.assertNotIn("kis: true", JS.split("const kiwoomScreenController", 1)[1].split("\n    });", 1)[0])

    def test_double_submit_guard_and_preview_gate_exist(self) -> None:
        assert_mapped_import(self, "kiwoom", "Kiwoom")

    def test_no_first_use_auto_destination(self) -> None:
        # Default destination select option must be empty placeholder
        self.assertIn('<select id="kiwoomDestinationAccount" class="toss-wts-select" aria-label="귀속할 Wealth 계좌"><option value="">계좌 선택...</option></select>', HTML)
        populate = broker_function(UI, "populateBrokerDestinationAccountSelect")
        self.assertIn('<option value="">귀속 계좌 선택...</option>', populate)
        self.assertIn("if (current && hasOption(current))", populate)
        self.assertIn("else if (preferred && hasOption(String(preferred)))", populate)
        self.assertNotIn("selectedIndex", populate)
        self.assertNotIn("accounts.length === 1", populate)

    def test_partial_success_mapping_error_ux_messaging(self) -> None:
        # Verify accurate partial-success message acknowledging persisted records without claim of failure
        self.assertIn("partial_success", JS)
        self.assertIn("reportMappingResult: true", mapped_config("kiwoom"))
        result = broker_function(broker_function(JS, "createMappedImport"), "showResult")
        self.assertIn("data.partial_success || data.mapping_warning === 'MAPPING_PERSISTENCE_FAILED'", result)
        self.assertIn("계좌 매핑 저장에 실패했습니다. 재시도 시 손익 중복 없이 매핑을 복구할 수 있습니다", JS)
        self.assertIn("data.mapping_repaired", result)

    def test_client_does_not_recompute_canonical_financial_values(self) -> None:
        selection = broker_function(JS, "kiwoomSelectedItems")
        self.assertIn("selectedImportItems(kiwoomRealizedState, brokerImportSelectedItem)", selection)
        common = broker_function(FEED, "selectedImportItems")
        self.assertIn(".sort((a, b) => a - b)", common)
        self.assertIn(".map(index => buildItem(state, index))", common)
        builder = broker_function(JS, "brokerImportSelectedItem")
        self.assertIn("state.rows?.[index]", builder)
        self.assertIn("row,", builder)
        self.assertIn("selection_token: token", builder)
        for field in ("buy_amount", "sell_amount", "pnl"):
            self.assertNotRegex(selection + common + builder, rf"\b{field}\s*=")

    def test_existing_toss_kis_nh_hooks_remain(self) -> None:
        for marker in (
            "btnTabBrokerToss", "btnTabBrokerKis", "btnTabBrokerNh",
            "tossWtsCard", "kisRealizedCard", "nhRealizedCard",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, HTML)


if __name__ == "__main__":
    unittest.main()
