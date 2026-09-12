"""Focused source-level checks for the Kiwoom realized-P/L browser workflow.

These tests verify frontend UI wiring, safe defaults, masking, and contract invariants
without launching a browser or performing real provider calls.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")


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
        self.assertIn("switchRealizedBroker('kiwoom')", JS)

    def test_tab_switch_does_not_auto_fetch_kiwoom_status_or_feed(self) -> None:
        switch_body = re.search(
            r"else if \(broker === 'kiwoom'\) \{(?P<body>.*?)\n  \} else",
            JS, re.DOTALL,
        )
        self.assertIsNotNone(switch_body)
        body_text = switch_body.group("body")
        self.assertNotIn("checkKiwoomStatus(", body_text)
        self.assertNotIn("fetchKiwoomRealizedFeed(", body_text)
        self.assertIn("btnCheckKiwoomStatus", JS)
        self.assertIn("btnFetchKiwoomFeed", JS)

    def test_market_selection_options_and_no_auto_fetch(self) -> None:
        kiwoom_section = HTML.split('id="kiwoomRealizedCard"', 1)[1].split('</div>\n          </div>', 1)[0]
        self.assertIn('value="kr"', kiwoom_section)
        self.assertIn('value="us"', kiwoom_section)
        # Verify market select change does not trigger auto-fetch in JS
        self.assertNotIn("kiwoomMarketSelect')?.addEventListener('change', fetchKiwoom", JS)

    def test_shared_display_masking_is_used_by_kiwoom(self) -> None:
        self.assertIn("function maskAccountDisplayLabel", JS)
        self.assertIn("kiwoomModalDestAccountDisplay", JS)
        self.assertIn("maskAccountDisplayLabel(dest.account_name", JS)
        self.assertIn("populateKiwoomDestinationAccounts", JS)

    def test_no_raw_kiwoom_account_number_field_is_rendered(self) -> None:
        kiwoom_section = HTML.split('id="kiwoomRealizedCard"', 1)[1]
        self.assertNotIn("acctNo", kiwoom_section)
        self.assertNotIn("account_no", kiwoom_section)
        self.assertNotIn("appkey", kiwoom_section)
        self.assertNotIn("secretkey", kiwoom_section)
        self.assertIn("source_account_key", JS)  # opaque route scope only

    def test_overseas_columns_do_not_claim_fabricated_krw_or_fx(self) -> None:
        render_body = re.search(
            r"function renderKiwoomFeedTable\(\) \{(?P<body>.*?)\n\}\nfunction updateKiwoomSelectionUI",
            JS, re.DOTALL,
        )
        self.assertIsNotNone(render_body)
        body = render_body.group("body")
        self.assertIn("expenses_total", body)
        self.assertNotIn("pnl_krw", body)
        self.assertNotIn("fx_rate", body)
        self.assertIn("USD", body)

    def test_double_submit_guard_and_preview_gate_exist(self) -> None:
        self.assertIn("kiwoomRealizedState.importing || !kiwoomRealizedState.previewTicket", JS)
        self.assertIn("kiwoomRealizedState.importing = true", JS)
        self.assertIn("preview_ticket: kiwoomRealizedState.previewTicket", JS)

    def test_no_first_use_auto_destination(self) -> None:
        # Default destination select option must be empty placeholder
        self.assertIn('<select id="kiwoomDestinationAccount" class="toss-wts-select" aria-label="귀속할 Wealth 계좌"><option value="">계좌 선택...</option></select>', HTML)
        self.assertIn('select.innerHTML = \'<option value="">귀속 계좌 선택...</option>\';', JS)

    def test_partial_success_mapping_error_ux_messaging(self) -> None:
        # Verify accurate partial-success message acknowledging persisted records without claim of failure
        self.assertIn("partial_success", JS)
        self.assertIn("MAPPING_PERSISTENCE_FAILED", JS)
        self.assertIn("계좌 매핑 저장에 실패했습니다. 재시도 시 손익 중복 없이 매핑을 복구할 수 있습니다", JS)
        self.assertIn("mapping_repaired", JS)

    def test_client_does_not_recompute_canonical_financial_values(self) -> None:
        # Client must send server-issued selection tokens and untouched row objects
        selected_items_fn = re.search(
            r"function kiwoomSelectedItems\(\) \{(?P<body>.*?)\n\}",
            JS, re.DOTALL,
        )
        self.assertIsNotNone(selected_items_fn)
        body = selected_items_fn.group("body")
        self.assertIn("const row = kiwoomRealizedState.rows[idx]", body)
        self.assertIn("{ row, selection_token: token }", body)
        self.assertNotIn("buy_amount =", body)
        self.assertNotIn("sell_amount =", body)
        self.assertNotIn("pnl =", body)

    def test_existing_toss_kis_nh_hooks_remain(self) -> None:
        for marker in (
            "btnTabBrokerToss", "btnTabBrokerKis", "btnTabBrokerNh",
            "tossWtsCard", "kisRealizedCard", "nhRealizedCard",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, HTML)


if __name__ == "__main__":
    unittest.main()
