from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"
BASE_CSS = ROOT / "app" / "static" / "wealth.css"


def test_workspace_radial_background_is_anchored_to_viewport() -> None:
    base_css = BASE_CSS.read_text(encoding="utf-8")
    layout_css = LAYOUT_CSS.read_text(encoding="utf-8")

    # The shared body background is intentionally radial/gradient based.
    assert "body{margin:0;background:radial-gradient" in base_css

    marker = "/* Workspace background consistency across long tabs */"
    assert marker in layout_css
    block = layout_css[layout_css.index(marker):]

    assert "body.wealth-layout" in block
    assert "background-attachment: fixed;" in block

    # Keep this fix on the outer workspace background only.  Securities and
    # realized P&L must not receive special panel/wrapper background colors.
    assert "#accountsPanel" not in block
    assert "#catPanelSecurities" not in block
    assert "#realizedPnlPanel" not in block
    assert ".pnl-panel" not in block
