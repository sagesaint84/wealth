from __future__ import annotations

from pathlib import Path

from tests.test_broker_realized_ipo_frontend import FEATURE, MODEL, UI, broker_function


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"


def test_krw_preview_uses_money_currency_symbol_only_once() -> None:
    helper = broker_function(FEATURE, "brokerImportPnlPresentation")

    assert "`${sign}${money(absolute)}`" in helper
    assert "₩${money(absolute)}" not in helper
    assert "`${sign}$${number(absolute, 2)}`" in helper


def test_long_broker_import_names_receive_compact_size_classes() -> None:
    helper = broker_function(FEATURE, "brokerImportNameSizeClass")
    assert "compactLength >= 24" in helper
    assert "is-very-long" in helper
    assert "compactLength >= 17" in helper
    assert "is-long" in helper

    preview = broker_function(FEATURE, "renderBrokerImportPreviewDetails")
    assert "formatters: { brokerImportNameSizeClass, brokerImportPnlPresentation }" in preview
    assert "WealthBrokerImportPreviewScreenController.renderDetails" in preview
    assert "const itemNameSizeClass = brokerImportNameSizeClass(itemName);" in MODEL
    assert 'class="broker-import-item-header"' in UI
    assert 'class="broker-import-item-title"' in UI
    assert 'class="broker-import-item-controls"' in UI
    assert 'class="broker-import-item-name ${itemNameSizeClass}"' in UI


def test_broker_import_header_keeps_type_controls_on_the_right() -> None:
    css = LAYOUT_CSS.read_text(encoding="utf-8")
    assert ".broker-import-item-header" in css
    assert "grid-template-columns: minmax(0, 1fr) auto" in css
    assert ".broker-import-item-title" in css
    assert "min-width: 0" in css
    assert ".broker-import-item-controls" in css
    assert "justify-self: end" in css
    assert "white-space: nowrap" in css
    assert ".broker-import-item-name.is-long" in css
    assert "font-size: 13px" in css
    assert ".broker-import-item-name.is-very-long" in css
    assert "font-size: 12px" in css
