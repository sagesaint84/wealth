# Shared Color System

`wealth-color-picker.js` exports `window.WealthColorPicker` in the browser and the same model via CommonJS for Node tests. It has no bucket IDs, financial calculations, persistence calls, or surface-specific defaults.

## Model and rendering API

- `normalizeHexColor(value)`: trims an opaque six-digit HEX string, returns uppercase `#RRGGBB`, or `null`. Short HEX, alpha, named colors and invalid values are rejected.
- `isValidHexColor(value)` / compatibility alias `valid(value)`.
- `getFallbackColor(value, fallback)`: returns a valid normalized color, the caller's valid fallback, or the first recommended color. Reads never migrate stored data.
- `getRecommendedPalette()`: a fresh array, safe for independent consumers.
- `hexToHsv(value)` / `hsvToHex(h, s, v)`: opaque color conversion; HSV saturation/value use 0..1.
- `renderColorPreview({value, label, className})`: accessible theme-neutral color dot. Suitable for badges, legends, tables and card accents; text keeps its theme color.
- `getPickerMode(viewportWidth)`: advanced at 768px and above, palette below that breakpoint.
- `create({value, label, onChange})`: returns a control node. `onChange` receives canonical opaque HEX only after a swatch choice or explicit advanced Apply/Enter. Escape/outside click discards an unfinished draft. The node's `dataset.color` holds the last confirmed selection.

## Behavior

Desktop includes recommended swatches, a two-axis saturation/value plane, Hue range, preview and HEX input. Left/right arrows adjust saturation, up/down adjust brightness; Shift increases the step. Swatch arrows traverse the palette. Tab stays in the open panel, Escape restores trigger focus. Resize closes the panel; outer scrolling repositions it without discarding keyboard focus.

Mobile exposes only recommended swatches plus the current custom color, preserving desktop colors without forcing dense controls. The panel is clamped to the viewport and can scroll locally on short screens.

## Current consumers and persistence

`wealth-planning.js` retains semantic legacy/preset/hash fallbacks, account/holding assignment and cash-bucket rules. Bucket editor and target/current legend controls reuse the picker. Inline Save uses the existing planning mutation/revision path; dirty drafts block an inline save and conflict failures restore persisted colors. Cash classification remains fixed independently of editable cash-bucket colors. System-only unclassified/unallocated entries retain their fallbacks.

`wealth-color-preferences.js` owns visualization preference load/resolve/register and PATCH persistence, while editing occurs at calendar legends and asset/stock markers. There is no central settings color list. Overrides live in `portfolio.json.settings.visualization_colors` under `calendar_event_colors`, `asset_category_colors` and `stock_category_colors`; strategy colors remain in `bucket.color`.

Calendar has seven keys: `ipo_subscription`, `ipo_listing`, `profit`, `loss`, `dividend`, `income`, `expense`. Interest is a display alias for `dividend`, not a separate saved key. Calendar grid pills and legend labels use the selected event color; detail body text keeps its theme color. Asset/stock donuts, legends, markers and bars resolve the same category key; color-marker clicks remain separate from row filtering. Draft changes do not PATCH until Save; reset removes the visualization override with `color=null`.

The fixed eight recommended colors are `#FF5A5F`, `#FF9F1C`, `#FFD60A`, `#2ECF73`, `#22C7B8`, `#4D96FF`, `#7C6CFF`, `#FF5FA2`, laid out as two rows of four. Desktop keeps SV/Hue spectrum/HEX; mobile keeps the compact palette. Do not introduce alpha into stored values.
