from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"


def _function_block(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_krw_preview_uses_money_currency_symbol_only_once() -> None:
    source = WEALTH_JS.read_text(encoding="utf-8")
    helper = _function_block(
        source,
        "function brokerImportPnlPresentation(candidate, value) {",
        "\nfunction brokerImportNameSizeClass",
    )

    assert "`${sign}${money(absolute)}`" in helper
    assert "₩${money(absolute)}" not in helper
    assert "`${sign}$${number(absolute, 2)}`" in helper


def test_long_broker_import_names_receive_compact_size_classes() -> None:
    source = WEALTH_JS.read_text(encoding="utf-8")
    helper = _function_block(
        source,
        "function brokerImportNameSizeClass(name) {",
        "\nfunction renderBrokerImportPreviewDetails",
    )
    assert "compactLength >= 24" in helper
    assert "is-very-long" in helper
    assert "compactLength >= 17" in helper
    assert "is-long" in helper

    preview = _function_block(
        source,
        "function renderBrokerImportPreviewDetails(data, overlayId) {",
        "\n// ── 한국투자증권",
    )
    assert "const itemNameSizeClass = brokerImportNameSizeClass(itemName);" in preview
    assert 'class="broker-import-item-header"' in preview
    assert 'class="broker-import-item-title"' in preview
    assert 'class="broker-import-item-controls"' in preview
    assert 'class="broker-import-item-name ${itemNameSizeClass}"' in preview


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
