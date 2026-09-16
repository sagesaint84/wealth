# Home Dashboard UI/UX Batch 2

## Scope

This batch changes only the Home dashboard presentation for Asset Portfolio and Net Worth History. It does not change Money Log navigation, Strategy Bucket behavior, financial storage, imports, APIs, or database schema.

## Modified Files

- `app/static/wealth-layout.js`
  - Displays total debt as a secondary net-worth detail with a dedicated debt tone.
  - Shows the existing real-estate and stock expected-return amounts and percentages inside the existing Expected Return card.
  - Changes the display label from `부동산 순에퀴티` to `부동산 순자산`.
  - Shows the existing real-estate return percentage on the right of its allocation row while retaining allocation share in the row detail.
- `app/static/wealth.js`
  - Exposes existing stock and real-estate expected-return values to the Home presentation event.
  - Reuses the real-estate view's existing return-rate rule; no financial formula or stored value was changed.
- `app/static/wealth-planning.js`
  - Places the history chart and record list side by side on desktop.
  - Adds visible markers, record amounts, record dates, and horizontal edge padding to the chart.
  - Replaces the narrow seven-column detail table with compact record cards while retaining every field and edit/delete action.
- `app/static/wealth-layout.css`
  - Adds the restrained amber debt detail treatment.
  - Adds the desktop history grid, compact record-list styling, chart overflow behavior, and stacked responsive breakpoint.
- `tests/test_home_dashboard_batch2.py`
  - Adds focused presentation-contract coverage for the Batch 2 requirements.
- `tests/test_v1015_information_architecture.py`
  - Updates affected Home presentation expectations.
- `tests/test_v1021_ui_ux.py`
  - Updates affected Expected Return presentation expectations.

Some listed tracked files already contained unrelated uncommitted Batch 1 or KB/UI work. Only the narrowly scoped Batch 2 hunks described above were added; those pre-existing hunks were preserved.

## Asset Portfolio

- Net worth remains the primary value.
- Total debt uses muted amber (`#d6a85f`) rather than profit/loss semantic colors.
- Total expected return remains the headline.
- The existing real-estate expected return and return rate are shown separately from the existing stock expected return and return rate.
- The real-estate allocation row now distinguishes allocation share from return percentage.

## Net Worth History

- Desktop uses a two-column chart/list layout at approximately two-thirds/one-third width.
- At widths below 980 px the chart and record list stack vertically.
- Every filtered saved record remains plotted and receives a point marker, amount label, and date label.
- A 92 px plot inset protects first/last points and labels; dense histories use horizontal scrolling without sampling or aggregation.
- Record cards retain date, total assets, total debt, net worth, type, memo, edit, and delete controls. Net worth is the primary value.
- Existing period filtering, owner filtering, record ordering, and add/edit/delete handlers remain intact.

## Financial Logic Review Required

None. Both requested expected-return breakdowns and percentages already existed in the current domain calculations. This batch only projects those values into the Home UI and reuses the existing real-estate return-rate rule.

## Verification

- Baseline full suite: `Ran 662 tests in 14.188s` — `OK`.
- Focused Home/UI suite: `Ran 26 tests in 0.084s` — `OK`.
- Post-change full suite: `Ran 669 tests in 13.452s` — `OK`.
- JavaScript syntax checks: PASS (`wealth.js`, `wealth-layout.js`, `wealth-planning.js`).
- `python -m compileall -q app tests`: PASS.
- `git diff --check`: PASS.

## Unchanged Areas

- Financial calculation formulas and stored financial values
- Owner and period filtering semantics
- Net-worth history records
- Record add/edit/delete behavior
- Broker and file import code
- Money Log navigation behavior in this batch
- Strategy Bucket functionality
- Database schema and migrations

## Remaining Concerns

No financial-logic blocker was found. Browser pixel-level acceptance was not required or performed; responsive behavior is covered by the existing source-contract test strategy and the explicit 980 px stacking rule.
