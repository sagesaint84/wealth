# Wealth UI/UX Batch 6: Responsive Secondary Navigation + Net Worth Chart No-Scroll Polish

## 1. Overview & Objectives

Batch 6 focuses on two targeted responsive visual refinements in the Wealth personal/family asset-management workspace:
1. **Secondary Navigation Typography Scale**:
   - Increase desktop font size from `13px` to `14px` across all three secondary navigation bars (Stock Investment, Comprehensive Assets, Money Log) for optimal desktop legibility and visual parity with primary navigation controls.
   - Maintain `13px` typography scale on mobile viewports (`<= 760px`) to prevent control overcrowding and preserve high touch density.
   - Retain existing horizontal touch scrolling, non-wrapping behavior, control heights (`min-height: 38px`), padding, active state indicators, and icons.
2. **Net Worth History Chart No-Scroll Polish**:
   - Completely eliminate horizontal scrolling and scrollbar jitter from the Home Net Worth History chart across desktop, tablet, and mobile.
   - Derive the SVG coordinate space directly from the container width (`width = containerWidth`) rather than inflating SVG dimensions with record count multipliers (`records.length * minSpacing`).
   - Eliminate fixed inline pixel width on the SVG element (`style="width:100%;height:250px;display:block"`), setting container `#wealthHistoryPlot` to `overflow: hidden;` and chart to `width: 100%; max-width: 100%`.
   - Implement adaptive label density with horizontal collision avoidance (`minSpacing = 64px` threshold): first and last records always display date and won amount labels; intermediate records display labels only when sufficient clearance exists.
   - Plotted financial data points (100% of circles, polyline vertices, delta bars, and hover tooltip `<title>` elements) remain completely rendered without dropping or sampling data.

---

## 2. Root Cause Analysis

### Secondary Navigation Typography
Previously, secondary navigation buttons were styled at `font-size: 13px;` across all viewports. On larger desktop monitors, `13px` appeared slightly undersized in comparison to primary navigation links (`14px`) and surrounding section headings. Increasing desktop typography to `14px` while preserving `13px` under the existing mobile breakpoint (`@media (max-width: 760px)`) establishes a balanced typographic hierarchy without sacrificing mobile compact layout or touch-scroll efficiency.

### Net Worth History Chart Horizontal Overflow
In `app/static/wealth-planning.js`, chart width was previously calculated as:
```javascript
const width = Math.max(containerWidth, records.length * minSpacing, 420);
```
accompanied by an SVG style injection:
```javascript
style="width:${width}px;min-width:100%"
```
and stylesheet rules:
```css
#wealthHistoryPlot { min-width: 0; overflow-x: auto; padding: 0 2px 4px; }
.wealth-history-chart { display: block; height: 250px; max-width: none; }
```
When record count exceeded ~6 records, `records.length * 72px` quickly surpassed container width, forcing `#wealthHistoryPlot` to render a horizontal scrollbar. On mobile screens (e.g. 360px), even `420px` forced horizontal overflow regardless of record count.

---

## 3. Implementation Details

### 3.1 Stylesheet Polish (`app/static/wealth-layout.css`)

1. **Secondary Navigation Typography (Desktop 14px)**:
   - Updated `.wealth-layout .wealth-invest-tabs button` to `font-size: 14px;`.
   - Updated `.wealth-layout .wealth-section-tabs > button` to `font-size: 14px;`.
   - Updated shared unifying rule:
     ```css
     .wealth-layout :is(.wealth-invest-tabs, .wealth-section-tabs) > button,
     .wealth-layout .wealth-invest-tabs button {
       font-size: 14px;
       font-weight: 650;
     }
     ```
2. **Secondary Navigation Typography (Mobile 13px Override)**:
   - Added rule inside `@media (max-width: 760px)`:
     ```css
     .wealth-layout :is(.wealth-invest-tabs, .wealth-section-tabs) > button,
     .wealth-layout .wealth-invest-tabs button {
       font-size: 13px;
     }
     ```
3. **Net Worth History Chart Overflow Elimination**:
   - Updated `#wealthHistoryPlot` from `overflow-x: auto;` to `overflow: hidden;`.
   - Updated `.wealth-history-chart` from `max-width: none;` to `width: 100%; max-width: 100%; height: 250px;`.

### 3.2 Dynamic Chart Rendering (`app/static/wealth-planning.js`)

1. **Responsive Container Sizing**:
   ```javascript
   const containerWidth = plot.clientWidth || 800;
   const width = containerWidth;
   ```
2. **Adaptive Delta Bar Sizing**:
   ```javascript
   const barWidth = Math.max(3, Math.min(24, (right - left) / Math.max(records.length * 2, 1)));
   ```
3. **Adaptive Label Density with Collision Avoidance**:
   ```javascript
   const showLabels = new Array(records.length).fill(false);
   if (records.length === 1) {
     showLabels[0] = true;
   } else if (records.length > 1) {
     showLabels[0] = true;
     showLabels[records.length - 1] = true;
     const minSpacing = 64;
     let lastX = points[0][0];
     const lastIdx = records.length - 1;
     const endX = points[lastIdx][0];
     for (let i = 1; i < lastIdx; i++) {
       if (points[i][0] - lastX >= minSpacing && endX - points[i][0] >= minSpacing) {
         showLabels[i] = true;
         lastX = points[i][0];
       }
     }
   }
   ```
4. **Data Point Preservation & Conditional Presentation**:
   - `<circle>`, `<title>` tooltip, delta bars, and `<polyline>` points are rendered for 100% of records.
   - Text elements (`<text>` for won amount and date) render conditionally when `showLabels[i]` is true.
   - SVG element output:
     ```javascript
     <svg class="wealth-history-chart" viewBox="0 0 ${width} 250" style="width:100%;height:250px;display:block" role="img" aria-label="날짜별 순자산과 전 기록 대비 변화 추이">
     ```

---

## 4. Verification & Testing

### 4.1 Focused Test Suite (`tests/test_ui_ux_batch6.py`)
Created comprehensive automated tests verifying:
- Secondary navigation desktop font size (`14px`) across all selectors.
- Mobile font size override (`13px`) under `@media (max-width: 760px)`.
- Touch scrolling, white-space wrapping, button height, and tab icons preserved.
- Chart SVG width strictly derived from container width without record count inflation.
- SVG styling uses `width: 100%` and eliminates fixed inline pixel width.
- Elimination of `overflow-x: auto;` in `#wealthHistoryPlot`.
- Preservation of all financial data points (circles, tooltips, polyline, delta bars).
- Adaptive label density with collision avoidance.

### 4.2 Updated Regression Tests
- `tests/test_home_dashboard_batch2.py`: Updated assertions to reflect Batch 6 no-scroll contract (`const width = containerWidth;` and `overflow:hidden`).
- `tests/test_ui_ux_batch4.py`: Updated assertions to verify responsive width without record count multiplier.

### 4.3 Validation Matrix

| Check | Result | Details |
|---|---|---|
| Python Test Suite | **PASS** | 715 tests run, 0 failures, 0 errors |
| Node Planning Model | **PASS** | 14 tests run, 0 failures |
| JavaScript Syntax Check | **PASS** | `node --check` clean across all static JS |
| Python Compileall | **PASS** | `python -m compileall -q app tests` clean |
| Git Diff Check | **PASS** | `git diff --check` clean, zero whitespace errors |

---

## 5. Non-Regression Invariants Preserved
- No modifications to financial calculations, database schemas, tax engines, FX rates, or trading APIs.
- Existing uncommitted work preserved intact across all working tree files.
- Zero destructive git operations executed.
