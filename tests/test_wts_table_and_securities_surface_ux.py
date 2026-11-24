from __future__ import annotations

from pathlib import Path

from tests.test_broker_realized_ipo_frontend import FEATURE, UI, broker_function


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"


def test_toss_wts_query_table_uses_money_currency_symbol_only_once() -> None:
    wrapper = broker_function(FEATURE, "renderTossWtsFeedTable")
    assert "tossWtsScreenController.renderFeedTable(rows, basis, status)" in wrapper
    assert "currency: basis, toss: true" in FEATURE
    block = broker_function(FEATURE, "brokerRealizedDisplayRow")
    assert "₩${money(" not in block
    assert "currency === 'USD' ? number(value, 2) : money(value)" in block
    assert "row[field]?.[currency === 'USD' ? 'usd' : 'krw']" in block
    assert "buy: amount(rawAmount('buy_amount')), sell: amount(rawAmount('sell_amount'))" in block
    assert "present(pnl) ? (Number(pnl) > 0 ? '+' : '')" in block
    table = broker_function(UI, "renderRealizedTable")
    assert "html(display.buy), html(display.sell)" in table
    assert "html(display.pnl)" in table


def test_broker_import_compacts_samsung_leverage_name_like_other_long_names() -> None:
    block = broker_function(FEATURE, "brokerImportNameSizeClass")

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
