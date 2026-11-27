from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
STATIC = ROOT / "app" / "static"
APP = (STATIC / "wealth.js").read_text(encoding="utf-8")
FEATURE = (STATIC / "wealth-broker-import-feature-controller.js").read_text(encoding="utf-8")
UI = (STATIC / "wealth-broker-ui.js").read_text(encoding="utf-8")
FEED = (STATIC / "wealth-broker-realized-feed-controller.js").read_text(encoding="utf-8")
SCREEN = (STATIC / "wealth-broker-realized-screen-controller.js").read_text(encoding="utf-8")
PREVIEW_SCREEN = (STATIC / "wealth-broker-import-preview-screen-controller.js").read_text(encoding="utf-8")
MODEL = (STATIC / "wealth-broker-import-preview-model.js").read_text(encoding="utf-8")
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
BROKER_ROUTES = (ROOT / "app" / "routers" / "broker_realized.py").read_text(encoding="utf-8")


def python_route(source: str, name: str) -> str:
    return next(
        ast.get_source_segment(source, node)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )



def broker_function(source: str, name: str) -> str:
    """Read a named classic-script implementation without depending on its next neighbor."""
    start = re.search(rf"^(?P<indent>[ \t]*)(?:async )?function {re.escape(name)}\(", source, re.M)
    if start is None:
        raise AssertionError(f"Missing broker function {name}")
    end = re.search(rf"^{start['indent']}\}}[ \t]*$", source[start.end():], re.M)
    if end is None:
        raise AssertionError(f"Missing end of broker function {name}")
    return source[start.start():start.end() + end.end()]


def mapped_config(provider: str) -> str:
    return FEATURE.split(f"const {provider}MappedImport = createMappedImport({{", 1)[1].split("\n    });", 1)[0]


def assert_mapped_import(test, provider, title):
    config = mapped_config(provider)
    for marker in (
        f"state: {provider}RealizedState", f"selectedItems: {provider}SelectedItems",
        f"previewUrl: '/api/{provider}/realized-feed/import-preview'",
        f"commitUrl: '/api/{provider}/realized-feed/import'",
        f"destinationId: '{provider}DestinationAccount'",
        f"duplicateToggleId: '{provider}IncludePossibleDuplicates'",
        f"commitButtonId: 'btn{title}ConfirmCommit'", f"overlayId: '{provider}ImportModalOverlay'",
        "resolveMarket: () => 'kr'" if provider == "kb" else f"resolveMarket: () => {provider}RealizedState.market",
    ):
        test.assertIn(marker, config)
    for action, target in ((f"open{title}ImportPreview", "openPreview"), (f"commit{title}Import", "commit"),
                           (f"close{title}ImportModal", "closeModal"), (f"update{title}CommitButton", "updateCommitButton")):
        test.assertIn(f"{provider}MappedImport.{target}()", broker_function(FEATURE, action))

    factory = broker_function(FEATURE, "createMappedImport")
    preview = broker_function(factory, "openPreview")
    commit = broker_function(factory, "commit")
    payload = broker_function(factory, "importPayload")
    test.assertIn("if (!accountId)", preview)
    test.assertIn("if (!items.length) return", preview)
    test.assertIn("post(previewUrl, importPayload(items, accountId))", preview)
    test.assertLess(preview.index("if (!accountId)"), preview.index("previewOpenApiImport"))
    test.assertIn("if (state.importing || !state.previewTicket) return", commit)
    test.assertLess(commit.index("state.importing = true"), commit.index("commitOpenApiImport"))
    test.assertIn("state.preview?.destination_account?.id || destinationAccountId()", commit)
    test.assertIn("...importPayload(selectedItems(), accountId)", commit)
    test.assertIn("preview_ticket: state.previewTicket", commit)
    test.assertIn("include_possible_duplicates: includeDuplicates()", commit)
    test.assertIn("!!document.getElementById(duplicateToggleId)?.checked", broker_function(factory, "includeDuplicates"))
    for marker in ("selected_items: items", "account_id: accountId", "market: resolveMarket()", "source_account_key: state.sourceAccountKey"):
        test.assertIn(marker, payload)

    post = broker_function(factory, "post")
    for marker in ("method: 'POST'", "'Content-Type': 'application/json'", "JSON.stringify(payload)"):
        test.assertIn(marker, post)

    preview_feed = broker_function(FEED, "previewOpenApiImport")
    test.assertIn("state.previewTicket = data.preview_ticket", preview_feed)
    test.assertIn("state.previewTicket = null", preview_feed)
    commit_feed = broker_function(FEED, "commitOpenApiImport")
    success = ("if (!res.ok) throw data", "closeModal();", "renderFeedTable();",
               "updateSelectionUI();", "showResult(data);", "refreshResults();")
    offsets = [commit_feed.index(marker) for marker in success]
    test.assertEqual(offsets, sorted(offsets))
    test.assertIn("showMessage(errorText(error, errorFallback), 'error')", commit_feed)
    test.assertIn("state.importing = false", commit_feed)

    route = python_route(BROKER_ROUTES, f"{provider}_realized_feed_import")
    test.assertIn('body.get("account_id")', route)
    test.assertIn(f"_{provider}_destination(username,", route)
    destination = MAIN.split(f"def _{provider}_destination(", 1)[1].split("\ndef ", 1)[0]
    test.assertIn("_require_realized_destination(", destination)
    required = MAIN.split("def _require_realized_destination(", 1)[1].split("\ndef ", 1)[0]
    test.assertIn("if not isinstance(account_id, str) or not account_id.strip()", required)
    test.assertIn(f"verify_{provider}_import_preview_ticket(", route)
    test.assertIn("_broker_import_items_hash", route)
    test.assertIn('bool(body.get("include_possible_duplicates", False))', route.replace('",False)', '", False)'))

    button = broker_function(factory, "updateCommitButton")
    test.assertIn("include ? (counts.possible_duplicate || 0) : 0", button)
    test.assertIn("renderBrokerImportCommitButton(commitButtonId, eligible, state.previewTicket, state.importing)", button)
    test.assertIn("eligible === 0 || !previewTicket || importing", broker_function(UI, "renderBrokerImportCommitButton"))
    close = broker_function(factory, "closeModal")
    test.assertLess(close.index("setModalVisible(overlayId, false)"), close.index("clearImportPreview(state)"))
    for field in ("preview", "previewTicket"):
        test.assertIn(f"state.{field} = null", broker_function(FEED, "clearImportPreview"))


def assert_explicit_broker_tab(test, provider, title):
    screen = FEATURE.split(f"key: '{provider}'", 1)[1].split("},", 1)[0]
    for marker in (f"tabId: 'btnTabBroker{title}'", f"checkId: 'btnCheck{title}Status'",
                   f"onCheck: check{title}Status", f"fetchId: 'btnFetch{title}Feed'", f"onFetch: fetch{title}RealizedFeed"):
        test.assertIn(marker, screen)
    test.assertIn("brokerImports.initializeScreens()", APP)
    test.assertIn("Object.assign(window, brokerImports.actions)", APP)
    test.assertIn("brokerUI.showBrokerScreen(realizedBrokerScreens, broker)", broker_function(FEATURE, "switchRealizedBroker"))
    init = broker_function(UI, "initializeBrokerScreens")
    test.assertIn("() => onSwitch(screen.key)", init)
    test.assertIn("'click', screen.onCheck", init)
    test.assertIn("'click', screen.onFetch", init)
    switch = broker_function(UI, "showBrokerScreen")
    test.assertNotRegex(switch, r"\b(?:onCheck|onFetch|fetch)\s*\(")


class BrokerRealizedIpoFrontendTests(unittest.TestCase):
    def test_all_broker_import_bars_have_per_row_options(self) -> None:
        for marker in ("kisTableBody", "nhTableBody", "kiwoomTableBody", "kbTableBody"):
            with self.subTest(marker=marker):
                self.assertIn(f'id="{marker}"', HTML)
        self.assertIn("'wts-import-type-cell'", broker_function(UI, "renderRealizedTable"))
        self.assertIn("brokerUI.renderFeedImportOptions(body", broker_function(FEATURE, "syncBrokerRowImportOptions"))
        self.assertNotIn('id="wtsImportOptions"', HTML)

    def test_common_controls_default_to_general_and_offer_ipo_fee(self) -> None:
        self.assertIn("stock_type: 'general'", FEATURE)
        self.assertIn("ipo_subscription_fee_krw: 2000", FEATURE)
        for label in (">일반주식</option>", ">공모주</option>", "공모청약비", 'type="number" min="0" step="1"'):
            self.assertIn(label, UI)

    def test_each_provider_sends_common_metadata_without_rebuilding_row(self) -> None:
        self.assertIn("brokerImportSelectedItem(tossWtsState, idx)", broker_function(FEATURE, "openWtsImportPreview"))
        for prefix, state in (("kis", "kisRealizedState"), ("nh", "nhRealizedState"),
                              ("kiwoom", "kiwoomRealizedState"), ("kb", "kbRealizedState")):
            with self.subTest(state=state):
                body = broker_function(FEATURE, prefix + "SelectedItems")
                self.assertIn(f"selectedImportItems({state}, brokerImportSelectedItem)", body)
        selection = broker_function(FEED, "selectedImportItems")
        self.assertIn(".sort((a, b) => a - b)", selection)
        self.assertIn(".map(index => buildItem(state, index))", selection)
        self.assertIn(".filter(Boolean)", selection)
        body = broker_function(FEATURE, "brokerImportSelectedItem")
        for marker in ("state.rows?.[index]", "state.selectionTokens?.[index]", "if (!row || !token) return null",
                       "row,", "selection_token: token", "wealth_import"):
            self.assertIn(marker, body)
        self.assertNotIn("row.pnl =", body)

    def test_preview_displays_server_authoritative_adjustment(self) -> None:
        preview = broker_function(FEATURE, "renderBrokerImportPreviewDetails")
        self.assertIn("WealthBrokerImportPreviewScreenController.renderDetails", preview)
        self.assertIn("WealthBrokerImportPreviewModel.prepareRow", PREVIEW_SCREEN)
        model = broker_function(MODEL, "prepareRow")
        for marker in ("stock_type", "ipo_subscription_fee_krw", "provider_realized_pnl", "final_wealth_pnl", "choice.memo"):
            self.assertIn(marker, model)

    def test_preference_change_invalidates_preview_ticket(self) -> None:
        for owner in ("syncBrokerRowImportOptions", "renderBrokerImportPreviewDetails"):
            self.assertGreaterEqual(broker_function(FEATURE, owner).count("state.previewTicket = null"), 2)
        self.assertIn("commitBtn.disabled = true", broker_function(FEATURE, "setModalRecalculating"))

    def test_all_provider_preview_and_import_routes_use_common_layer(self) -> None:
        route_functions = (
            "toss_wts_realized_feed_import_preview", "toss_wts_realized_feed_import",
            "kis_realized_feed_import_preview", "kis_realized_feed_import",
            "nh_realized_feed_import_preview", "nh_realized_feed_import",
            "kiwoom_realized_feed_import_preview", "kiwoom_realized_feed_import",
        )
        for name in route_functions:
            source = MAIN if name.startswith("toss_wts_") else BROKER_ROUTES
            body = python_route(source, name)
            with self.subTest(route=name):
                if name.endswith("import_preview"):
                    self.assertIn("_apply_broker_import_preferences", body)
                    self.assertIn("_broker_import_items_hash", body)
                else:
                    self.assertIn("_broker_import_items_hash", body)
                    self.assertIn("_apply_broker_import_preferences", body)

    def test_modal_second_chance_controls_and_behavior(self) -> None:
        self.assertIn("class=\"modal-broker-stock-type", UI)
        self.assertIn("class=\"modal-broker-ipo-fee", UI)
        self.assertIn("class=\"modal-broker-effect\"", UI)
        self.assertIn("function getBrokerContextByOverlayId(overlayId)", FEATURE)
        self.assertIn("function scheduleBrokerPreviewRefresh(overlayId)", FEATURE)
        self.assertIn("function setModalRecalculating(overlayId, isRecalculating)", FEATURE)
        self.assertIn("commitBtn.textContent = '재계산 중...';", FEATURE)

        # Focus & cursor restoration after second-chance re-render
        self.assertIn("document.activeElement", PREVIEW_SCREEN)
        self.assertIn("setSelectionRange", PREVIEW_SCREEN)

    def test_commit_button_disabled_when_preview_ticket_null_for_all_brokers(self) -> None:
        self.assertIn("tossWtsState.previewTicket", broker_function(FEATURE, "updateWtsCommitButton"))
        self.assertIn("!kisRealizedState.previewTicket", broker_function(FEATURE, "updateKisCommitButton"))
        for provider, title in (("nh", "Nh"), ("kiwoom", "Kiwoom"), ("kb", "Kb")):
            assert_mapped_import(self, provider, title)

    def test_modal_close_clears_preview_ticket_for_all_brokers(self) -> None:
        for title, state in (("Wts", "tossWtsState"), ("Kis", "kisRealizedState")):
            self.assertIn(f"{state}.previewTicket = null", broker_function(FEATURE, f"close{title}ImportModal"))
        for provider, title in (("nh", "Nh"), ("kiwoom", "Kiwoom"), ("kb", "Kb")):
            assert_mapped_import(self, provider, title)

if __name__ == "__main__":
    unittest.main()
