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
    ": `${sign}₩${money(absolute)}`;",
    ": `${sign}${money(absolute)}`;",
    "KRW_CURRENCY_SYMBOL",
)

render_marker = "function renderBrokerImportPreviewDetails(data, overlayId) {"
name_helper = """function brokerImportNameSizeClass(name) {
  const compactLength = Array.from(String(name || '').replace(/\\s+/g, '')).length;
  if (compactLength >= 24) return 'is-very-long';
  if (compactLength >= 18) return 'is-long';
  return '';
}

"""

if "function brokerImportNameSizeClass(name) {" not in js:
    js = replace_once(js, render_marker, name_helper + render_marker, "NAME_SIZE_HELPER")

old_values = """    const itemName = candidate.name || candidate.prdt_name || candidate.code || `선택 항목 ${item.index + 1}`;
    const itemDate = candidate.date || '';
    const providerPnl = brokerImportPnlPresentation(candidate, choice.provider_realized_pnl ?? candidate.pnl ?? 0);
"""
new_values = """    const itemName = candidate.name || candidate.prdt_name || candidate.code || `선택 항목 ${item.index + 1}`;
    const itemNameSizeClass = brokerImportNameSizeClass(itemName);
    const itemDate = candidate.date || '';
    const providerPnl = brokerImportPnlPresentation(candidate, choice.provider_realized_pnl ?? candidate.pnl ?? 0);
"""
js = replace_once(js, old_values, new_values, "ITEM_NAME_SIZE_CLASS")

old_header = """      `<div style=\"display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;\">` +
        `<div>` +
          `<strong class=\"broker-import-item-name\">${html(itemName)}</strong>` +
          `${itemDate ? `<span class=\"muted\" style=\"font-size:12px;margin-left:6px;\">(${html(itemDate)})</span>` : ''}` +
        `</div>` +
        `<div style=\"display:flex;align-items:center;gap:8px;flex-wrap:wrap;\">` +
"""
new_header = """      `<div class=\"broker-import-item-header\">` +
        `<div class=\"broker-import-item-title\">` +
          `<strong class=\"broker-import-item-name ${itemNameSizeClass}\">${html(itemName)}</strong>` +
          `${itemDate ? `<span class=\"muted\" style=\"font-size:12px;margin-left:6px;\">(${html(itemDate)})</span>` : ''}` +
        `</div>` +
        `<div class=\"broker-import-item-controls\">` +
"""
js = replace_once(js, old_header, new_header, "BROKER_PREVIEW_HEADER")

old_css = """/* Broker realized import preview readability */
.broker-import-item-name {
  font-size: 15px !important;
  line-height: 1.35;
  font-weight: 700;
}
.broker-import-pnl {
  font-variant-numeric: tabular-nums;
}
.broker-import-pnl.pnl-positive {
  color: var(--red, #ff718c) !important;
}
.broker-import-pnl.pnl-negative {
  color: var(--blue, #54a8ff) !important;
}
"""
new_css = """/* Broker realized import preview readability */
.broker-import-item-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px 16px;
  align-items: start;
}
.broker-import-item-title {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.broker-import-item-controls {
  justify-self: end;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  white-space: nowrap;
}
.broker-import-item-name {
  min-width: 0;
  font-size: 15px !important;
  line-height: 1.35;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.broker-import-item-name.is-long {
  font-size: 13px !important;
}
.broker-import-item-name.is-very-long {
  font-size: 12px !important;
}
.broker-import-pnl {
  font-variant-numeric: tabular-nums;
}
.broker-import-pnl.pnl-positive {
  color: var(--red, #ff718c) !important;
}
.broker-import-pnl.pnl-negative {
  color: var(--blue, #54a8ff) !important;
}
"""
css = replace_once(css, old_css, new_css, "BROKER_PREVIEW_CSS")

JS_PATH.write_text(js, encoding="utf-8")
CSS_PATH.write_text(css, encoding="utf-8")

written_js = JS_PATH.read_text(encoding="utf-8")
written_css = CSS_PATH.read_text(encoding="utf-8")

for marker in (
    "`${sign}${money(absolute)}`",
    "function brokerImportNameSizeClass(name) {",
    "compactLength >= 24",
    "compactLength >= 18",
    'class="broker-import-item-header"',
    'class="broker-import-item-title"',
    'class="broker-import-item-controls"',
    'class="broker-import-item-name ${itemNameSizeClass}"',
):
    if marker not in written_js:
        raise SystemExit(f"JS_VERIFY_FAILED: {marker}")

if "₩${money(absolute)}" in written_js:
    raise SystemExit("JS_VERIFY_FAILED: duplicate KRW symbol expression remains")

for marker in (
    "grid-template-columns: minmax(0, 1fr) auto",
    ".broker-import-item-name.is-long",
    "font-size: 13px",
    ".broker-import-item-name.is-very-long",
    "font-size: 12px",
    "justify-self: end",
    "white-space: nowrap",
):
    if marker not in written_css:
        raise SystemExit(f"CSS_VERIFY_FAILED: {marker}")

print("PR79_BROKER_IMPORT_PREVIEW_LAYOUT_PATCHED")
