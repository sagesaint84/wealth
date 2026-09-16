# Wealth — Batch 6.1: Secondary Navigation Typography Consistency Hotfix

## 1. Overview
This hotfix resolves the secondary-navigation typography discrepancy where Comprehensive Assets (`#assetCategoryTabs .account-cat-tab`) computed to `13px / 600 / 13px` while Stock Investment and Money Log computed to `14px / 650 / normal` on desktop.

All secondary navigation systems across Wealth now share unified, identical computed typography:
- **Desktop**: `font-size: 14px; font-weight: 650; line-height: normal;`
- **Mobile (<= 760px)**: `font-size: 13px; font-weight: 650; line-height: normal;`

---

## 2. Root Cause & CSS Cascade Audit

1. **Legacy Tab Standardization Rule in `app/static/wealth-overrides.css` (lines 974–989)**:
   - Selector: `.family-tab, .heatmap-tab, .account-cat-tab`
   - Contained:
     ```css
     height: 29px !important;
     min-height: 29px !important;
     padding: 0 9px !important;
     font-size: 11.5px !important;
     font-weight: 600 !important;
     border-radius: 7px !important;
     display: inline-flex !important;
     align-items: center !important;
     justify-content: center !important;
     line-height: 1 !important;
     white-space: nowrap !important;
     box-sizing: border-box !important;
     ```
   - **Impact**: Because of `font-weight: 600 !important;` and `line-height: 1 !important;`, the modern layout styles (`font-weight: 650`, `line-height: normal`) were overridden. `line-height: 1` forced the line height to match font-size (hence `13px`).

2. **Stale Typography in `app/static/wealth-overrides.css` (lines 3189–3199)**:
   - Selector: `.account-cat-tab`
   - Contained:
     ```css
     font-size: 12.5px;
     font-weight: 600;
     ```
   - **Impact**: Stale non-standard values overriding default inheritance before layout specificity.

3. **Stale Mobile Typography in `app/static/wealth-layout.css` (line 70)**:
   - Selector: `@media (max-width: 760px) { .wealth-layout .account-category-tabs .account-cat-tab { ... } }`
   - Contained:
     ```css
     padding: 10px 12px; font-size: 11px; white-space: nowrap;
     ```
   - **Impact**: High-specificity mobile selector `(0, 3, 0)` shrank mobile buttons down to `11px`, violating the minimum `13px` requirement.

---

## 3. Exact Fix Applied

### A. Removed Legacy Conflicting Overrides (`app/static/wealth-overrides.css`)
- **Line 974**: Removed `.account-cat-tab` from `.family-tab, .heatmap-tab, .account-cat-tab` so only `.family-tab, .heatmap-tab` remain in the legacy standardization rule.
- **Line 3189**: Removed stale `font-size: 12.5px;` and `font-weight: 600;` declarations from `.account-cat-tab` so it cleanly inherits the secondary navigation typography without hacky `!important` additions.

### B. Harmonized Layout Typography (`app/static/wealth-layout.css`)
- **Desktop (lines 270, 274, 277–285)**:
  - Explicitly specified `line-height: normal;` on `.wealth-layout .wealth-invest-tabs button` and `.wealth-layout .wealth-section-tabs > button`.
  - Added unified rules:
    ```css
    .wealth-layout :is(.wealth-invest-tabs, .wealth-section-tabs) > button,
    .wealth-layout .wealth-invest-tabs button {
      font-size: 14px;
      font-weight: 650;
      line-height: normal;
    }
    .wealth-layout .account-category-tabs > button {
      font-size: 14px;
      font-weight: 650;
      line-height: normal;
    }
    ```
- **Mobile (lines 70, 407–417)**:
  - Harmonized `.wealth-layout .account-category-tabs .account-cat-tab` at line 70 from `font-size: 11px;` to `font-size: 13px; font-weight: 650; line-height: normal;`.
  - Harmonized mobile query:
    ```css
    @media (max-width: 760px) {
      .wealth-layout :is(.wealth-invest-tabs, .wealth-section-tabs) > button,
      .wealth-layout .wealth-invest-tabs button {
        font-size: 13px;
        font-weight: 650;
        line-height: normal;
      }
      .wealth-layout .account-category-tabs > button {
        font-size: 13px;
        font-weight: 650;
        line-height: normal;
      }
    ```

---

## 4. Final Computed Typography Results

| Navigation Area | Selector / Elements | Desktop (`> 760px`) | Mobile (`<= 760px`) |
| :--- | :--- | :--- | :--- |
| **Stock Investment** | `.wealth-invest-tabs button` | `14px / 650 / normal` | `13px / 650 / normal` |
| **Comprehensive Assets** | `.account-category-tabs > button` (`.account-cat-tab`) | `14px / 650 / normal` | `13px / 650 / normal` |
| **Money Log** | `.wealth-section-tabs > button` (`.income-tab`) | `14px / 650 / normal` | `13px / 650 / normal` |

---

## 5. Verification & Tests Executed

1. **Focused Navigation & Batch 6 Tests**:
   - `python -m unittest tests/test_ui_ux_batch6.py tests/test_section_navigation.py`: **19 tests PASS** (including 4 new regression tests for Batch 6.1).
2. **Full Python Test Suite**:
   - `python -m unittest discover -s tests -p "test_*.py"`: **719 tests PASS** (zero failures, zero errors).
3. **Node Planning Model Tests**:
   - `node tests/planning-model.test.cjs`: **14 tests PASS**.
4. **Bytecode Compilation**:
   - `python -m compileall -q app tests`: **PASS**.
5. **Git Whitespace & Diff Check**:
   - `git diff --check`: **PASS**.
6. **No-workaround check**:
   - Zero one-off `!important` additions made to fix typography.

---

## 6. Functional & Financial Scope Preservation
- Financial calculations: **NO CHANGE**
- Tax calculations: **NO CHANGE**
- DB schema / migrations: **NO CHANGE**
- API routes & contracts: **NO CHANGE**
- Broker integration contracts: **NO CHANGE**
- Uncommitted work from previous batches: **100% PRESERVED**
