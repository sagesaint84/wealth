from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEALTH_JS = ROOT / "app" / "static" / "wealth.js"
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"


def _function_block(source: str, start_marker: str, end_marker: str) -> str:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    return source[start:end]


def test_toss_wts_query_table_uses_money_currency_symbol_only_once() -> None:
    source = WEALTH_JS.read_text(encoding="utf-8")
    block = _function_block(
        source,
        "function renderTossWtsFeedTable(rows, basis = 'KRW', status = 'ok') {",
        "\n// ── 토스 WTS 배당·이자 피드",
    )

    assert "₩${money(" not in block
    assert "`${pnlSign}${money(pnl)}`" in block
    assert "`${money(r.buy_amount?.krw ?? 0)}`" in block
    assert "`${money(r.sell_amount?.krw ?? 0)}`" in block
    assert "`${pnlSign}$${number(pnl, 2)}`" in block


def test_broker_import_compacts_samsung_leverage_name_like_other_long_names() -> None:
    source = WEALTH_JS.read_text(encoding="utf-8")
    block = _function_block(
        source,
        "function brokerImportNameSizeClass(name) {",
        "\nfunction renderBrokerImportPreviewDetails",
    )

    assert len("KODEX삼성전자단일종목레버리지") == 17
    assert "compactLength >= 24" in block
    assert "compactLength >= 17" in block
    assert "compactLength >= 18" not in block


def test_securities_tab_uses_shared_workspace_surfaces() -> None:
    css = LAYOUT_CSS.read_text(encoding="utf-8")
    marker = "/* Securities account surfaces: shared workspace theme */"
    assert marker in css
    block = css[css.index(marker):]

    assert ".wealth-layout #catPanelSecurities .broker-group" in block
    assert "background: var(--surface-2);" in block
    assert ".wealth-layout #catPanelSecurities .account-row" in block
    assert "background: var(--surface-1);" in block
    assert "border-color: var(--border-subtle);" in block
    assert "background: var(--surface-hover);" in block
