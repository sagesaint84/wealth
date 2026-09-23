"""Focused source-level checks for the KB Securities realized-P/L browser workflow.

These tests verify frontend UI wiring, safe defaults, masking, domestic-only restriction,
and contract invariants without launching a browser or performing real provider calls.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")


class KbRealizedFrontendTests(unittest.TestCase):
    def test_kb_tab_card_and_explicit_controls_exist(self) -> None:
        for marker in (
            "btnTabBrokerKb", "kbRealizedCard", "kbMarketSelect", "kbFromDate",
            "kbToDate", "kbSourceAccount", "btnCheckKbStatus", "btnFetchKbFeed",
            "kbTableBody", "kbSelectAll", "kbDestinationAccount", "btnKbImportSelected",
            "kbImportModalOverlay", "btnKbConfirmCommit", "kbImportOptions",
            "kbModalCountNew", "kbModalCountAlready", "kbModalCountDup",
            "kbModalCountInvalid", "kbIncludePossibleDuplicates",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, HTML)

    def test_kb_uses_only_its_backend_routes(self) -> None:
        for route in (
            "/api/kb/status",
            "/api/kb/realized-feed/fetch",
            "/api/kb/realized-feed/import-preview",
            "/api/kb/realized-feed/import",
        ):
            with self.subTest(route=route):
                self.assertIn(route, JS)
        self.assertIn("const kbRealizedState", JS)
        self.assertIn("switchRealizedBroker('kb')", JS)

    def test_tab_switch_does_not_auto_fetch_kb_status_or_feed(self) -> None:
        switch_body = re.search(
            r"else if \(broker === 'kb'\) \{(?P<body>.*?)\n  \}",
            JS, re.DOTALL,
        )
        self.assertIsNotNone(switch_body)
        body_text = switch_body.group("body")
        self.assertNotIn("checkKbStatus(", body_text)
        self.assertNotIn("fetchKbRealizedFeed(", body_text)
        self.assertIn("btnCheckKbStatus", JS)
        self.assertIn("btnFetchKbFeed", JS)

    def test_market_selection_domestic_only(self) -> None:
        kb_section = HTML.split('id="kbRealizedCard"', 1)[1].split('</div>\n          </div>', 1)[0]
        self.assertIn('value="kr"', kb_section)
        # Verify domestic is default and selected
        self.assertIn('value="kr" selected', kb_section)
        # Verify overseas is marked disabled / unsupported
        self.assertIn('value="us" disabled', kb_section)
        self.assertIn('해외주식 (지원하지 않음)', kb_section)
        # Verify market select change does not trigger auto-fetch in JS
        self.assertNotIn("kbMarketSelect')?.addEventListener('change', fetchKb", JS)

    def test_shared_display_masking_is_used_by_kb(self) -> None:
        self.assertIn("function maskAccountDisplayLabel", JS)
        self.assertIn("kbModalDestAccountDisplay", JS)
        self.assertIn("maskAccountDisplayLabel(dest.account_name", JS)
        self.assertIn("populateKbDestinationAccounts", JS)

    def test_no_raw_kb_account_number_field_is_rendered(self) -> None:
        # Bound the assertion to the KB card itself.  Later dialogs can
        # legitimately contain a generic Wealth account_no input.
        kb_section = HTML.split('id="kbRealizedCard"', 1)[1].split('<section id="dividendPanel"', 1)[0]
        self.assertNotIn("acctNo", kb_section)
        self.assertNotIn("account_no", kb_section)
        self.assertNotIn("appkey", kb_section)
        self.assertNotIn("secretkey", kb_section)
        self.assertIn("source_account_key", JS)  # opaque route scope only

    def test_double_submit_guard_and_preview_gate_exist(self) -> None:
        self.assertIn("kbRealizedState.importing || !kbRealizedState.previewTicket", JS)
        self.assertIn("kbRealizedState.importing = true", JS)
        self.assertIn("preview_ticket: kbRealizedState.previewTicket", JS)

    def test_no_first_use_auto_destination(self) -> None:
        # Default destination select option must be empty placeholder
        self.assertIn('<select id="kbDestinationAccount" class="toss-wts-select" aria-label="귀속할 Wealth 계좌"><option value="">계좌 선택...</option></select>', HTML)
        self.assertIn('select.innerHTML = \'<option value="">귀속 계좌 선택...</option>\';', JS)

    def test_partial_success_mapping_error_ux_messaging(self) -> None:
        self.assertIn("MAPPING_PERSISTENCE_FAILED", JS)
        self.assertIn("mapping_repaired", JS)

    def test_client_does_not_recompute_canonical_financial_values(self) -> None:
        selected_items_fn = re.search(
            r"function kbSelectedItems\(\) \{(?P<body>.*?)\n\}",
            JS, re.DOTALL,
        )
        self.assertIsNotNone(selected_items_fn)
        body = selected_items_fn.group("body")
        self.assertIn("const row = kbRealizedState.rows[idx]", body)
        self.assertIn("brokerImportSelectedItem(kbRealizedState, idx)", body)
        self.assertNotIn("buy_amount =", body)
        self.assertNotIn("sell_amount =", body)
        self.assertNotIn("pnl =", body)

    def test_kb_overlay_registered_in_modal_second_chance(self) -> None:
        self.assertIn("if (overlayId === 'kbImportModalOverlay')", JS)
        self.assertIn("brokerKey: 'kb'", JS)
        self.assertIn("state: kbRealizedState,", JS)
        self.assertIn("refreshPreview: openKbImportPreview,", JS)
        self.assertIn("commitButtonId: 'btnKbConfirmCommit',", JS)

    def test_kb_commit_button_disabled_when_preview_ticket_null(self) -> None:
        kb_update = re.search(r"function updateKbCommitButton\(\) \{(?P<body>.*?)\n\}", JS, re.DOTALL)
        self.assertIsNotNone(kb_update)
        self.assertIn("!kbRealizedState.previewTicket", kb_update.group("body"))

    def test_kb_modal_close_clears_preview_ticket(self) -> None:
        match = re.search(r"function closeKbImportModal\(\) \{(?P<body>.*?)\n\}", JS, re.DOTALL)
        self.assertIsNotNone(match)
        self.assertIn("kbRealizedState.previewTicket = null", match.group("body"))

    def test_kb_preview_and_import_routes_use_common_layer(self) -> None:
        for name in ("kb_realized_feed_import_preview", "kb_realized_feed_import"):
            start = MAIN.index(f"async def {name}(")
            next_start = MAIN.find("\nasync def ", start + 1)
            body = MAIN[start:next_start if next_start >= 0 else len(MAIN)]
            with self.subTest(route=name):
                self.assertIn("_broker_import_items_hash", body)
                self.assertIn("_apply_broker_import_preferences", body)

    def test_kb_openapi_settings_ui_elements(self) -> None:
        for element_id in ("openapiKbKey", "openapiKbSecret", "openapiKbAccountNo"):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', HTML)
        # Separate product input is absent from normal UI
        self.assertNotIn('id="openapiKbProductNo"', HTML)
        self.assertNotIn("openapiKbProductNo", JS)
        self.assertIn("openapiKbAccountNo", JS)
        self.assertIn("KB증권 계좌번호 (11자리)", HTML)
        self.assertIn("하이픈 없이 11자리 계좌번호를 입력하세요.", HTML)


if __name__ == "__main__":
    unittest.main()
