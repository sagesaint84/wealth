from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / "app" / "static" / "wealth.js"
CSS_PATH = ROOT / "app" / "static" / "wealth-layout.css"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


js = JS_PATH.read_text(encoding="utf-8")
css = CSS_PATH.read_text(encoding="utf-8")

js = replace_once(
    js,
    "const pnlFormatted = isUsd ? `${pnlSign}$${number(pnl, 2)}` : `${pnlSign}₩${money(pnl)}`;",
    "const pnlFormatted = isUsd ? `${pnlSign}$${number(pnl, 2)}` : `${pnlSign}${money(pnl)}`;",
    "WTS_REALIZED_PNL_KRW_SYMBOL",
)
js = replace_once(
    js,
    "const buyAmt = isUsd ? `$${number(r.buy_amount?.usd ?? 0, 2)}` : `₩${money(r.buy_amount?.krw ?? 0)}`;",
    "const buyAmt = isUsd ? `$${number(r.buy_amount?.usd ?? 0, 2)}` : `${money(r.buy_amount?.krw ?? 0)}`;",
    "WTS_BUY_AMOUNT_KRW_SYMBOL",
)
js = replace_once(
    js,
    "const sellAmt = isUsd ? `$${number(r.sell_amount?.usd ?? 0, 2)}` : `₩${money(r.sell_amount?.krw ?? 0)}`;",
    "const sellAmt = isUsd ? `$${number(r.sell_amount?.usd ?? 0, 2)}` : `${money(r.sell_amount?.krw ?? 0)}`;",
    "WTS_SELL_AMOUNT_KRW_SYMBOL",
)
js = replace_once(
    js,
    "if (compactLength >= 18) return 'is-long';",
    "if (compactLength >= 17) return 'is-long';",
    "BROKER_IMPORT_LONG_NAME_THRESHOLD",
)

surface_css = """

/* Securities account surfaces: shared workspace theme */
.wealth-layout #catPanelSecurities .broker-group {
  background: var(--surface-2);
  border-color: var(--border-subtle);
}
.wealth-layout #catPanelSecurities .broker-head {
  border-bottom-color: var(--border-subtle);
}
.wealth-layout #catPanelSecurities .broker-head span {
  background: var(--surface-1);
  border-color: var(--border-subtle);
}
.wealth-layout #catPanelSecurities .broker-accounts {
  border-left-color: var(--border-subtle);
}
.wealth-layout #catPanelSecurities .account-row {
  background: var(--surface-1);
  border-color: var(--border-subtle);
}
@media (hover: hover) {
  .wealth-layout #catPanelSecurities .account-row:hover {
    background: var(--surface-hover);
    border-color: color-mix(in srgb, var(--workspace-accent) 38%, var(--border-subtle));
  }
}
"""

marker = "/* Securities account surfaces: shared workspace theme */"
if marker not in css:
    css = css.rstrip() + surface_css + "\n"

JS_PATH.write_text(js, encoding="utf-8")
CSS_PATH.write_text(css, encoding="utf-8")

written_js = JS_PATH.read_text(encoding="utf-8")
written_css = CSS_PATH.read_text(encoding="utf-8")

realized_start = written_js.index("function renderTossWtsFeedTable(rows, basis = 'KRW', status = 'ok') {")
realized_end = written_js.index("\n// ── 토스 WTS 배당·이자 피드", realized_start)
realized_block = written_js[realized_start:realized_end]
if "₩${money(" in realized_block:
    raise SystemExit("JS_VERIFY_FAILED: duplicate KRW symbol expression remains in WTS realized table")

for marker_text in (
    "`${pnlSign}${money(pnl)}`",
    "`${money(r.buy_amount?.krw ?? 0)}`",
    "`${money(r.sell_amount?.krw ?? 0)}`",
    "compactLength >= 17",
):
    if marker_text not in written_js:
        raise SystemExit(f"JS_VERIFY_FAILED: {marker_text}")

for marker_text in (
    "/* Securities account surfaces: shared workspace theme */",
    ".wealth-layout #catPanelSecurities .broker-group",
    "background: var(--surface-2);",
    ".wealth-layout #catPanelSecurities .account-row",
    "background: var(--surface-1);",
    "background: var(--surface-hover);",
):
    if marker_text not in written_css:
        raise SystemExit(f"CSS_VERIFY_FAILED: {marker_text}")

print("PR80_WTS_TABLE_AND_SECURITIES_SURFACE_PATCHED")
