from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "app" / "static" / "wealth.js").read_text(encoding="utf-8")
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")


class BrokerRealizedIpoFrontendTests(unittest.TestCase):
    def test_all_broker_import_bars_have_per_row_options(self) -> None:
        for marker in ("wtsImportOptions", "kisImportOptions", "nhImportOptions", "kiwoomImportOptions"):
            with self.subTest(marker=marker):
                self.assertIn(f'id="{marker}"', HTML)

    def test_common_controls_default_to_general_and_offer_ipo_fee(self) -> None:
        self.assertIn("stock_type: 'general'", JS)
        self.assertIn("ipo_subscription_fee_krw: 2000", JS)
        self.assertIn(">일반주식</option>", JS)
        self.assertIn(">공모주</option>", JS)
        self.assertIn("공모청약비", JS)
        self.assertIn('type="number" min="0" step="1"', JS)

    def test_each_provider_sends_common_metadata_without_rebuilding_row(self) -> None:
        for state_name in (
            "tossWtsState", "kisRealizedState", "nhRealizedState", "kiwoomRealizedState",
        ):
            with self.subTest(state=state_name):
                self.assertIn(f"brokerImportSelectedItem({state_name},", JS)
        builder = re.search(
            r"function brokerImportSelectedItem\(state, index\) \{(?P<body>.*?)\n\}",
            JS, re.DOTALL,
        )
        self.assertIsNotNone(builder)
        body = builder.group("body")
        self.assertIn("row,", body)
        self.assertIn("selection_token: token", body)
        self.assertIn("wealth_import", body)
        self.assertNotIn("row.pnl =", body)

    def test_preview_displays_server_authoritative_adjustment(self) -> None:
        preview = re.search(
            r"function renderBrokerImportPreviewDetails\(data, overlayId\) \{(?P<body>.*?)\n\}",
            JS, re.DOTALL,
        )
        self.assertIsNotNone(preview)
        body = preview.group("body")
        for marker in (
            "stock_type", "ipo_subscription_fee_krw", "provider_realized_pnl",
            "final_wealth_pnl", "choice.memo",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, body)

    def test_preference_change_invalidates_preview_ticket(self) -> None:
        options = re.search(
            r"function renderBrokerImportOptions\(state, containerId, brokerKey\) \{(?P<body>.*?)\n\}",
            JS, re.DOTALL,
        )
        self.assertIsNotNone(options)
        self.assertGreaterEqual(options.group("body").count("state.previewTicket = null"), 2)

    def test_all_provider_preview_and_import_routes_use_common_layer(self) -> None:
        route_functions = (
            "toss_wts_realized_feed_import_preview", "toss_wts_realized_feed_import",
            "kis_realized_feed_import_preview", "kis_realized_feed_import",
            "nh_realized_feed_import_preview", "nh_realized_feed_import",
            "kiwoom_realized_feed_import_preview", "kiwoom_realized_feed_import",
        )
        for index, name in enumerate(route_functions):
            start = MAIN.index(f"async def {name}(")
            next_start = MAIN.find("\nasync def ", start + 1)
            body = MAIN[start:next_start if next_start >= 0 else len(MAIN)]
            with self.subTest(route=name):
                if name.endswith("import_preview"):
                    self.assertIn("_apply_broker_import_preferences", body)
                    self.assertIn("_broker_import_items_hash", body)
                else:
                    self.assertIn("_broker_import_items_hash", body)
                    self.assertIn("_apply_broker_import_preferences", body)

    def test_modal_second_chance_controls_and_behavior(self) -> None:
        self.assertIn("class=\"modal-broker-stock-type", JS)
        self.assertIn("class=\"modal-broker-ipo-fee", JS)
        self.assertIn("class=\"modal-broker-effect\"", JS)
        self.assertIn("function getBrokerContextByOverlayId(overlayId)", JS)
        self.assertIn("function scheduleBrokerPreviewRefresh(overlayId)", JS)
        self.assertIn("function setModalRecalculating(overlayId, isRecalculating)", JS)
        self.assertIn("commitBtn.textContent = '재계산 중...';", JS)

        # Focus & cursor restoration after second-chance re-render
        self.assertIn("document.activeElement", JS)
        self.assertIn("setSelectionRange", JS)

    def test_commit_button_disabled_when_preview_ticket_null_for_all_brokers(self) -> None:
        # Toss
        wts_update = re.search(r"function updateWtsCommitButton\(\) \{(?P<body>.*?)\n\}", JS, re.DOTALL)
        self.assertIsNotNone(wts_update)
        self.assertIn("tossWtsState.previewTicket", wts_update.group("body"))

        # KIS
        kis_update = re.search(r"function updateKisCommitButton\(\) \{(?P<body>.*?)\n\}", JS, re.DOTALL)
        self.assertIsNotNone(kis_update)
        self.assertIn("!kisRealizedState.previewTicket", kis_update.group("body"))

        # NH
        nh_update = re.search(r"function updateNhCommitButton\(\) \{(?P<body>.*?)\n\}", JS, re.DOTALL)
        self.assertIsNotNone(nh_update)
        self.assertIn("!nhRealizedState.previewTicket", nh_update.group("body"))

        # Kiwoom
        kiwoom_update = re.search(r"function updateKiwoomCommitButton\(\) \{(?P<body>.*?)\n\}", JS, re.DOTALL)
        self.assertIsNotNone(kiwoom_update)
        self.assertIn("!kiwoomRealizedState.previewTicket", kiwoom_update.group("body"))

    def test_modal_close_clears_preview_ticket_for_all_brokers(self) -> None:
        for fn_name, state_name in (
            ("closeWtsImportModal", "tossWtsState"),
            ("closeKisImportModal", "kisRealizedState"),
            ("closeNhImportModal", "nhRealizedState"),
            ("closeKiwoomImportModal", "kiwoomRealizedState"),
        ):
            pattern = rf"function {fn_name}\(\) \{{(?P<body>.*?)\n\}}"
            match = re.search(pattern, JS, re.DOTALL)
            self.assertIsNotNone(match, f"Missing {fn_name}")
            self.assertIn(f"{state_name}.previewTicket = null", match.group("body"))


if __name__ == "__main__":
    unittest.main()
