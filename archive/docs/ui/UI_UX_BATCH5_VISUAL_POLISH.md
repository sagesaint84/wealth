# Wealth — Batch 5: Visual Hierarchy & Consistency Polish

## 1. Overview
Wealth UI/UX Batch 5 implements three focused visual polish improvements without touching any financial, portfolio valuation, tax logic, or backend contracts:
1. **Net Worth History Record-Card Hierarchy**: Elevates primary financial information (Date, Net Worth, Total Assets, Total Debt) and establishes distinct semantic colors (`#6ea6ec` for assets, `#d6a85f` for liabilities), while de-emphasizing secondary metadata (`구분`, `메모`).
2. **Secondary Navigation Typography Consistency**: Unifies typography scale across Stock Investment, Comprehensive Assets, and Money Log at 13px (+1px from 12px) using a shared selector rule without reducing control heights or touch targets.
3. **Strategy Bucket Card Color Connection**: Visually connects lower strategy bucket cards with target/current donuts and legend entries by binding `--bucket-color` dynamically via `bucketColor(id)` with a restrained left border accent, subtle background tint, and title tint, preserving neutral gray (`#697386`) for `미분류`.

---

## 2. Files Modified

| File | Change Summary |
|---|---|
| `app/static/wealth-planning.js` | Added semantic markup classes (`wealth-history-record-amounts`, `record-asset`, `record-debt`, `record-source`, `record-memo`) in `renderHistoryDetails`; bound `--bucket-color` dynamic property via `bucketColor(b.id)` in `renderBucketSummary`. |
| `app/static/wealth-layout.css` | Added styling for record-card amounts separation, asset soft blue (`#6ea6ec`), liability restrained amber (`#d6a85f`), and metadata de-emphasis; standardized secondary tab typography to 13px with shared `:is(.wealth-invest-tabs, .wealth-section-tabs) > button` rule; added restrained `--bucket-color` border and tint styles for `.wealth-bucket-cards article`. |
| `tests/test_ui_ux_batch5.py` | Added comprehensive automated tests for Batch 5 visual hierarchy, secondary navigation scale, and bucket card color binding. |

---

## 3. Detailed Changes by Requirement

### 3.1 Task 1: Net Worth History Record Card Information Hierarchy
- **Problem Addressed**: Previously, `구분` and `메모` inherited unconstrained body text sizes and dominated the card visually, while `총자산` and `총부채` were rendered in small 10px text that could merge together.
- **Visual Priority Established**:
  1. Date (`<time>`): Visible 11.5px, semi-bold (600), muted.
  2. Net Worth (`<strong>`): Primary monetary amount, 14px, bold (700), tabular figures.
  3. Total Assets & Liabilities (`.wealth-history-record-amounts`):
     - Prominent 12.5px, bold (600), tabular numbers.
     - `display: flex; justify-content: space-between; gap: 6px 14px;` providing guaranteed horizontal separation so they never merge into one sentence.
     - **Total Assets**: Soft positive blue (`#6ea6ec`, matching Wealth `--kpi-color` tone-net).
     - **Total Liabilities**: Restrained amber (`#d6a85f`, matching Home Net Worth debt semantic).
  4. Record Type & Memo (`.wealth-history-record-note`):
     - De-emphasized to 11.5px with `color: var(--muted)`.
     - Multi-line flex layout (`flex-direction: column; gap: 2px`) preventing `구분 · ...` and `메모 · ...` from colliding.
  5. Action Buttons (`수정`/`삭제`): Preserved in `.wealth-history-record-actions` as tiny secondary and danger text buttons.

### 3.2 Task 2: Secondary Navigation Typography Consistency
- **Problem Addressed**: Secondary tabs across Stock Investment, Comprehensive Assets, and Money Log had slight typographic disparities and 12px text felt slightly small.
- **Enhancement**:
  - Increased typography scale by +1px from 12px to 13px (`font-size: 13px; font-weight: 650;`).
  - Added shared CSS selector rule:
    ```css
    .wealth-layout :is(.wealth-invest-tabs, .wealth-section-tabs) > button,
    .wealth-layout .wealth-invest-tabs button {
      font-size: 13px;
      font-weight: 650;
    }
    ```
  - Standardized `.wealth-invest-tabs button` with `min-height: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 6px;` matching `.wealth-section-tabs > button`.
  - Preserved all touch targets, 9px 13px padding, horizontal scrolling on narrow screens, active state styling, account count badges (`증권 (18)`, etc.), and semantic icons/emojis across all 3 sections.

### 3.3 Task 3: Strategy Bucket Card Color Connection
- **Problem Addressed**: Lower strategy bucket cards appeared visually uniform and lacked immediate visual connection to the donut charts and legend.
- **Enhancement**:
  - In `app/static/wealth-planning.js`, bound `style="--bucket-color:${bucketColor(b.id)}"` to each `<article>` in the bucket card list.
  - Reused the exact stable color mapping from `bucketColor(id)`.
  - In `app/static/wealth-layout.css`:
    ```css
    .wealth-bucket-cards article {
      border: 1px solid color-mix(in srgb, var(--bucket-color, var(--line)) 30%, var(--line));
      border-left: 4px solid var(--bucket-color, var(--line));
      border-radius: 12px;
      padding: 16px;
      min-width: 0;
      background: color-mix(in srgb, var(--bucket-color, transparent) 4%, var(--panel));
    }
    .wealth-bucket-cards h4 {
      margin: 0 0 10px;
      color: color-mix(in srgb, var(--bucket-color, var(--text)) 75%, var(--text));
    }
    ```
  - **Restrained Dark UI**: Subtle left accent bar (4px) and very low opacity (4%) background tint over `--panel`, avoiding saturated or noisy cards.
  - **Neutral `미분류`**: For `__unclassified__`, `bucketColor` returns neutral gray `#697386`, keeping it visually distinct as an unassigned holding/cash category.

---

## 4. Responsive Behavior
- **Desktop (>= 980px)**:
  - Net Worth History displays side-by-side: adaptive chart on the left, compact records list on the right.
  - Secondary navigation displays spacious horizontal tabs with clear active indicators.
  - Strategy Bucket comparison displays 2 columns (Target / Current) with auto-fit grid cards below.
- **Narrow / Mobile (<= 760px)**:
  - Net Worth History automatically stacks chart above records.
  - Secondary navigation allows fluid horizontal scrolling (`overflow-x: auto; scrollbar-width: thin;`) with all tabs directly accessible (no dropdown conversion).
  - Strategy Bucket cards maintain responsive auto-fit grid (`minmax(200px, 1fr)`) without horizontal overflow.

---

## 5. Verification & Test Results
- **Batch 5 Focused Tests**: `tests/test_ui_ux_batch5.py` (7 / 7 PASS).
- **Batch 1-4 Regression Tests**:
  - `tests/test_money_log_navigation.py` (Batch 1): PASS
  - `tests/test_home_dashboard_batch2.py` (Batch 2): PASS
  - `tests/test_strategy_bucket_batch3.py` (Batch 3): PASS
  - `tests/test_ui_ux_batch4.py` (Batch 4): PASS
  - `tests/test_section_navigation.py`: PASS
- **Node Planning Model Tests**: `tests/planning-model.test.cjs` (14 / 14 PASS).
- **Static Syntax & Type Checks**:
  - `node --check app/static/wealth.js app/static/wealth-layout.js app/static/wealth-planning.js app/static/wealth-planning-model.js` (PASS)
  - `python -m compileall app tests` (PASS)
  - `git diff --check` (PASS, 0 whitespace errors)
- **Full Python Suite**: All tests pass (694 passed).

---

## 6. Invariant & Safety Confirmation
- **Financial Calculations Changed**: NO
- **Tax Logic Changed**: NO
- **Portfolio Valuation Changed**: NO
- **DB Schema / Migrations**: NO
- **API Contracts Changed**: NO
- **Destructive Git Commands Used**: NO (`git checkout`, `git restore`, `git reset`, `git stash`, `git clean` never run)
- **Uncommitted User Changes Preserved**: YES
- **Application Version**: Retained at `v1.1.4` (no bump)
