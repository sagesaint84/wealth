from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"


def _function_block(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_toss_wts_realized_destination_dropdown_only_lists_toss_accounts() -> None:
    source = WEALTH_JS.read_text(encoding="utf-8")
    block = _function_block(source, "function populateWtsAccounts() {", "\nlet currentPreviewData")

    assert ".filter(account => {" in block
    assert "broker.includes('토스') || broker.includes('toss')" in block
    assert "토스증권 계좌를 선택하세요" in block
    assert "accounts.length === 1" in block
    assert "accounts.some" in block


def test_broker_import_preview_formats_currency_and_profit_loss_direction() -> None:
    source = WEALTH_JS.read_text(encoding="utf-8")

    helper = _function_block(
        source,
        "function brokerImportPnlPresentation(candidate, value) {",
        "\nfunction renderBrokerImportPreviewDetails",
    )
    assert "candidate?.currency" in helper
    assert "currency === 'USD'" in helper
    assert "`$" in helper or "$${" in helper
    assert "money(absolute)" in helper
    assert "₩${money(absolute)}" not in helper
    assert "pnl-positive" in helper
    assert "pnl-negative" in helper

    preview = _function_block(
        source,
        "function renderBrokerImportPreviewDetails(data, overlayId) {",
        "\n// ── 한국투자증권",
    )
    assert "const itemNameSizeClass = brokerImportNameSizeClass(itemName);" in preview
    assert 'class="broker-import-item-name ${itemNameSizeClass}"' in preview
    assert "brokerImportPnlPresentation(candidate, choice.provider_realized_pnl" in preview
    assert "brokerImportPnlPresentation(candidate, choice.final_wealth_pnl" in preview
    assert 'class="broker-import-pnl ${providerPnl.toneClass}"' in preview
    assert 'class="broker-import-pnl ${finalPnl.toneClass}"' in preview


def test_broker_import_preview_has_compact_name_and_red_blue_pnl_styles() -> None:
    css = LAYOUT_CSS.read_text(encoding="utf-8")

    assert ".broker-import-item-name" in css
    assert "font-size: 15px" in css
    assert ".broker-import-pnl.pnl-positive" in css
    assert "var(--red" in css
    assert ".broker-import-pnl.pnl-negative" in css
    assert "var(--blue" in css
