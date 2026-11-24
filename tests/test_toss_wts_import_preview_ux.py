from __future__ import annotations

from pathlib import Path

from tests.test_broker_realized_ipo_frontend import FEATURE, MODEL, UI, broker_function


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"


def test_toss_wts_realized_destination_dropdown_only_lists_toss_accounts() -> None:
    block = broker_function(FEATURE, "populateWtsAccounts")

    assert ".filter(account => {" in block
    assert "broker.includes('토스') || broker.includes('toss')" in block
    assert "토스증권 계좌를 선택하세요" in block
    assert "accounts.length === 1" not in block
    assert "restoreImportSelection(select, 'toss_wts_realized', accounts)" in block
    assert "accounts.some" in block


def test_broker_import_preview_formats_currency_and_profit_loss_direction() -> None:

    helper = broker_function(FEATURE, "brokerImportPnlPresentation")
    assert "candidate?.currency" in helper
    assert "currency === 'USD'" in helper
    assert "`$" in helper or "$${" in helper
    assert "money(absolute)" in helper
    assert "₩${money(absolute)}" not in helper
    assert "pnl-positive" in helper
    assert "pnl-negative" in helper

    preview = broker_function(FEATURE, "renderBrokerImportPreviewDetails")
    assert "formatters: { brokerImportNameSizeClass, brokerImportPnlPresentation }" in preview
    assert "WealthBrokerImportPreviewScreenController.renderDetails" in preview
    assert "const itemNameSizeClass = brokerImportNameSizeClass(itemName);" in MODEL
    assert 'class="broker-import-item-name ${itemNameSizeClass}"' in UI
    assert "brokerImportPnlPresentation(candidate, choice.provider_realized_pnl" in MODEL
    assert "brokerImportPnlPresentation(candidate, choice.final_wealth_pnl" in MODEL
    assert 'class="broker-import-pnl ${providerPnl.toneClass}"' in UI
    assert 'class="broker-import-pnl ${finalPnl.toneClass}"' in UI


def test_broker_import_preview_has_compact_name_and_red_blue_pnl_styles() -> None:
    css = LAYOUT_CSS.read_text(encoding="utf-8")

    assert ".broker-import-item-name" in css
    assert "font-size: 15px" in css
    assert ".broker-import-pnl.pnl-positive" in css
    assert "var(--red" in css
    assert ".broker-import-pnl.pnl-negative" in css
    assert "var(--blue" in css
