# Ledger single renderer audit

## ROOT_CAUSE

Production load path on base `72adc40784a77080bdd945314cc42d424b8ad246`:

1. FastAPI `app/main.py` serves `STATIC_DIR / "index.html"` from `/` and `/dashboard`, and mounts `/static`. That `app/static/index.html` loads classic scripts at the end of the body, including `wealth.js`, then `wealth-planning-model.js`, then `wealth-planning.js`.
2. The browser-only portion of `wealth-planning-model.js` dynamically appends panzoom and legacy ledger history, then period-core. The ordered scripts use `async = false`.
3. The period-core `load` event starts visible-range; its `load` or `error` starts label-layout; label-layout `load` or `error` starts unified. Period-core is required by unified. Visible-range/label-layout are optional helpers in that loader.
4. Unified registers `window.WealthUnifiedTimeseries` and synchronously dispatches `wealth:unified-ready` at the end of module evaluation. Installation either runs immediately or waits for DOMContentLoaded; chart queues run in RAF. The event means API registration, not first chart paint.

The application can run and enter ledger before this dynamic chain finishes. Unified is attempted on every production startup but historically acts as an enhancement: core ledger summaries, categories and transactions work with it unavailable. The blocked-module fallback therefore remains necessary. No saved ledger-specific unavailable-module Chrome test was found; this change preserves the audited blocked-script behavior with an explicit regression test.

Originally `wealth.js` wrote legacy `.ledger-trend-chart` for each ledger response. Unified's body MutationObserver noticed `hostNeedsUnified('ledgerTrendContainer')`, queued ledger, and replaced that DOM on the next RAF. Legacy history expansion also called the legacy producer. Static HTML produced the six-month eyebrow; visible-range removed it after unified installation.

The same pre-parser probe on the base reproduced 2 legacy host writes, 1 visible RAF sample and 2 legacy-to-unified replacements at 1280. The corrected flow reports zero for all three.

## ARCHITECTURE

`renderLedger(data)` stores the in-memory data and preserves header/month/owner, summary, category and transaction rendering. It requests `renderLedgerChart()`, which waits for the explicit loader promise. A sequence guard coalesces pending requests to the latest ledger data.

Ready: direct `WealthUnifiedTimeseries.renderLedger(rawLedgerData)` handoff. The renderer seeds monthly cache and refreshes selected-month transaction cache; owner/data-version/render-generation guards reject stale asynchronous chart/history responses. Empty data clears obsolete cache and uses the unified empty state. API failure retains the last authoritative chart.

Failed: `renderLedgerTrendFallback(trend)` is guarded by `WealthLedgerChartModule.state === 'failed'`. Failure is settled by period-core or unified script error, by period-core loading without its required export, or by unified script loading without a registered renderLedger API. An absent API, delayed script, or elapsed time never triggers fallback. Optional helper errors continue toward unified as before.

History: `WealthLedgerTimeseriesHistory.expandHistory()` delegates directly to existing `WealthUnifiedTimeseries.extendLedgerHistory()`. The unified wheel boundary also extends its cache and renders directly. Only explicit module failure uses legacy history fetching/merging/rendering. Ledger period header helpers update legacy chart titles only in fallback mode.

## REMOVED_SHADOW

- `wealth.js`: normal legacy trend call removed; legacy implementation explicitly renamed and failure-guarded.
- `wealth-ledger-timeseries-history.js`: normal expansion uses unified; fallback has owner checks.
- `wealth-timeseries-unified.js`: ledger observer replacement branch and startup/family legacy-repair queues removed. Other chart observer branches preserved.
- `index.html`: six-month eyebrow producer deleted.
- `wealth-timeseries-visible-range.js`: ledger-only eyebrow removal helper and call deleted. Eyebrow creation and removal are both zero.

No persistence/API schema or financial calculation changes. No stock/networth/PnL/dividend renderer cleanup, WTS, IPO, KFTC or broker registry changes. The shared legend condition adds a legend only for ledger; other chart kinds retain their behavior. No files deleted.

## FRAME_TEST / FALLBACK_TEST

Native installed Chrome via CDP, headless, isolated temporary profiles, 1280x900 and 390x900. `Page.addScriptToEvaluateOnNewDocument` installs host-write hooks, DOM mutation counting and continuous visible RAF sampling before document parsing. Synthetic ledger responses and a local static-only preview avoid production data access.

Normal and delayed runs verify cold ledger, previous/next month, month picker, native family selection, API reload, annual filter, DAY/WEEK/MONTH/YEAR/ALL, axis labels, legend, overflow, native wheel zoom, scrolling, direct history expansion, native wheel expansion at the widest boundary, stale owner responses, missing monthly_trend/no transactions, and API errors.

The existing period set has no QUARTER. ALL auto-resolves its bucket interval; its title follows that existing resolved-period contract.

At each normal/delayed checkpoint, including history expansion:

| Width | Legacy writes | Legacy DOM observations | Visible legacy RAF samples | Legacy-to-unified replacements | Six-month eyebrow |
| --- | --- | --- | --- | --- | --- |
| 1280 | 0 | 0 | 0 | 0 | 0 |
| 390 | 0 | 0 | 0 | 0 | 0 |

Actual unified and period-core script blocking are separately tested at both widths. Legacy fallback visibly renders, expands from 6 to 12 months, keeps synthetic summaries/categories/transactions working, has no JS exceptions, no unified replacements and no six-month eyebrow. A held unified script plus month/reload changes proves that loading stays pending with no chart shadow or fallback before release.

Desktop/mobile PNG captures were inspected for title, axes, legend and overflow. They are stored with test logs in the isolated temporary source workspace.

## TEST

- Focused static/controller/Chrome workflow tests: 68 passed.
- Ledger native Chrome load/refresh/history/error/fallback scenarios: 8 passed.
- All 6 changed JavaScript files pass `node --check`.
- All 3 changed/new Python test files pass `py_compile`.
- `git diff --check` passes.
- Final full pytest: **2,987 passed, 2 failed, 3 skipped, 4 warnings, 670 subtests passed** in 502.87s. The two existing Chrome probes failed before application execution: `test_income_tab_hash_survives_reload[ipo-#ipo]` reached `chrome-error://chromewebdata/`, and `test_native_daily_pointer_accuracy[True-pnl]` found no DevTools page target (`StopIteration`). Re-running those exact two nodes sequentially: **2 passed** in 8.22s. This is a passing targeted retry, not a claim that the full invocation exited successfully. Ledger Chrome tests passed in the full invocation as well.
- Isolation setup: an earlier complete run failed on excluded `.env.example` and first creation of a synthetic default market file by an existing mocked IPO test. Restoring the public template and initializing synthetic temporary storage made the respective test files pass (5 and 3 tests); those fixture failures did not recur in the final full invocation. No IPO source/test changes were made.
- Category renderer, transaction/CRUD tail, and wealth renderer source preceding the ledger module were compared against the base and are identical after newline normalization.

Evidence workspace: `C:/Users/Public/Documents/ESTsoft/CreatorTemp/wealth-ledger-synthetic-mra9cpe6`. Logs: `ledger-final.log`, `focused-final.log`, `full-pytest-clean.log`, `chrome-retry.log`; captures: `ledger-artifacts/ledger-1280.png` and `ledger-artifacts/ledger-390.png`. Negative-control base probe: `C:/Users/Public/Documents/ESTsoft/CreatorTemp/wealth-ledger-base-synthetic-5p49r8kj/base-shadow-probe.log`.

Tests run from a temporary copy of source plus the public `.env.example`, excluding actual `.env` and repository `data/`. PYTHONPATH includes that copy's `tests` directory for existing `regression_support` imports. All financial fixtures/storage are synthetic or temporary; no push, PR or merge is performed.

## CHANGED_FILES

- app/static/index.html
- app/static/wealth.js
- app/static/wealth-planning-model.js
- app/static/wealth-timeseries-unified.js
- app/static/wealth-timeseries-visible-range.js
- app/static/wealth-ledger-timeseries-history.js
- app/static/wealth-ledger-period-filter.js
- tests/test_ledger_single_renderer_chrome.py (new)
- tests/test_ledger_timeseries_history.py
- tests/test_timeseries_visible_range.py
- docs/ledger-single-renderer-audit.md (new)

Deleted files: none. Branch: `maintenance10-9f-ledger-single-renderer`. Base: `72adc40784a77080bdd945314cc42d424b8ad246`. Local commit title: `refactor: remove ledger shadow renderer`. Commit SHA, count above base and final git status are supplied in the final chat report after committing.
