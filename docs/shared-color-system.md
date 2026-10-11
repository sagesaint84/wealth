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

## First consumer: strategy buckets

`wealth-planning.js` retains semantic legacy/preset/hash fallbacks, account/holding assignment and cash-bucket rules. Confirmed picker colors preview on cards, legends, charts and assignment badges; only the existing explicit bucket Save persists planning metadata. Backend strict HEX validation remains in `planning.mutate`.

Future consumers should pass their own semantic fallback and label, use returned HEX for accents/series/dots, and own their existing save flow. Calendar, portfolio and chart-wide migrations are outside this change. Do not use custom colors for primary body text or introduce alpha into stored values.
