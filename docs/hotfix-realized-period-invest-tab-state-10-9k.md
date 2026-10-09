# Realized period / investment reload hotfix — 10-9k

Base: `7724f146db24d6261a633fa0bbf27bd59555ff4d`.
Branch: `hotfix10-9k-realized-period-invest-tab-state`.
Commit title: `fix: correct realized period and investment tab state`.

## ROOT_CAUSE_REALIZED_SCOPE / PORTFOLIO_DATA_PATH / PNL_PAGE_DATA_PATH

`app/main.py` dashboard enrichment includes `read_pnl_records(username)` and
`get_pnl_summary(owner="모두", username=username)` without a year. Its total is
correctly all-time. The backend's all-time monthly schedule groups by month
number, so October includes every year's October.

`wealth.js::renderSummary` previously took that month-number bucket as the
current month for the all-owner view. The detailed page instead requests
`/api/realized-pnl?owner=...&year=2026&trade_type=...`; `get_pnl_summary` filters
the year before building monthly buckets. This explains WHY_VALUES_DIVERGED.
No backend summary, record storage, conversion or import code was changed.

## CURRENT_MONTH_CONTRACT / ALL_TIME_CONTRACT / KST_PERIOD_CONTRACT

The canonical all-time display total still uses
`buildRealizedPnlDisplaySummary`. The existing raw-row period loop is now used
for both all-owner and individual-owner views, after stock-only/owner filters:

- Total: all years and months.
- Year: current Asia/Seoul year.
- Month: current Asia/Seoul year **and** month.

The existing `getKstYearMonth()` is reused. Its Intl failure fallback now uses
UTC fields after a nine-hour offset, rather than the browser's local timezone.
UTC `2026-09-30T15:30:00Z` selects KST October. No second timezone helper exists.

## CROSS_YEAR_REGRESSION / CURRENT_MONTH_VS_PNL_PAGE_EQUALITY

All figures below are invented test fixtures; no production record was read.

| Synthetic record | KRW |
| --- | ---: |
| 2025-10 | 20,501,333 |
| 2026-09 | 110 |
| 2026-10 | -789,783 |
| 2026-11 | 220 |

Expected current month: **-789,783**. Current year: **-789,453**.
All-time total: **19,711,880**, including September/November fixtures.
The legacy all-time October bucket is **19,711,550** and remains all-time;
the portfolio no longer uses it as current October. Cross-year contamination=0.

`test_all_time_year_and_current_month_match_same_year_pnl_page` calls the real
backend summary with a patched synthetic reader and executes the actual
frontend renderer. Exact base fails with `19711550 != -789783`; branch passes.
Previous/current/next-month and owner tests also compare the portfolio against
the same-year canonical backend monthly bucket.

SIGN_COLOR_REGRESSION: negative text is `-₩789,783`, with `loss down` and the
existing loss color; no positive sign/gain class. Native Chrome checks purple,
white and OLED at 1280/390. OWNER_REGRESSION includes all, mother, father and
missing-owner views. REAL_ESTATE_EXCLUSION_REGRESSION covers all six existing
markers: asset_type, REAL_ESTATE code, broker, name prefix, re_id and
real_estate_name. Unconverted KRW handling remains unchanged.

## ROOT_CAUSE_PERIOD_FLASH / INITIAL_LABEL_CONTRACT / HARDCODED_DATE_PRODUCER

The parser produced fixed `26년`/`09월` for the four PnL/dividend summary labels
before wealth.js could replace them. PnL/dividend month-nav text and the initial
year option also had static dates. These target producers now contain `—`.
`initializeSummaryPeriodLabels()` uses the existing KST helper synchronously
before any API request, including month-nav controls, picker values and current
year options. The summary labels and target controls have fixed `09월` producer
count=0 and fixed specific-year producer count=0.

Calendar/ledger period controls outside this task were not redesigned.
DIVIDEND_ANALOG_AUDIT: the portfolio dividend period code already filters full
year and year-month date prefixes from owner-filtered actual records; it does
not use an all-time month-number bucket. No matching cross-year defect was
found in that path. Its aggregation formula was preserved; it now shares the
same KST current-period selection.

## ROOT_CAUSE_INVEST_TAB_RESET / INVEST_TAB_PERSISTENCE_CONTRACT

Planning initialization unconditionally selected overview. STORAGE_MECHANISM:
the six allowlisted subtabs now use `sessionStorage['wealth_invest_tab']`: reload survives within
the same tab/session, without imposing a saved preference on a fresh browser
session. INVALID_STATE_FALLBACK: invalid/empty/missing/unexpected values fall back to overview. Storage
access failures are caught so navigation remains usable. Values are never
inserted into HTML/selectors before validation.

`wealth-invest-tab-state.js` runs synchronously in the document head, before
panel parsing. It resolves the session route into a root data attribute. CSS
applies that selected route to the existing investment panel IDs from their
first creation. This is normal subtab visibility, not a loading mask or delayed
legacy replacement. Once all DOM/listeners exist, planning uses the same state
to restore classes, inner record view and aria-pressed, and dispatches the
existing `wealth:view` event with `detail='invest'`. Outer #invest remains separate.

TAX_ACCOUNT_RESTORE_CONTRACT: records uses recordsPanel+combo; tax_accounts uses
recordsPanel+tax_accounts. `currentRecordView`, inner active button and heading
agree after restore. Owner switching/render/planning refresh paths are retained.

INVEST_PANEL_VISIBILITY_CONTRACT / INVEST_RELOAD_FIRST_VISIBLE_STATE /
RELOAD TEST RESULTS:

| Reload selection | First visible panel | Inner view | Wrong overview frames | Legacy asset frames |
| --- | --- | --- | ---: | ---: |
| overview | summaryPanel | — | 0 | 0 |
| heatmap | assetHeatmapPanel | — | 0 | 0 |
| records | recordsPanel | combo | 0 | 0 |
| buckets | bucketPanel | — | 0 | 0 |
| tax_accounts | recordsPanel | tax_accounts | 0 | 0 |
| holdings | holdingsPanel | — | 0 | 0 |
| invalid / missing | summaryPanel | — | 0 | 0 |

All rows were checked at both 1280 and 390. Inactive panels have
`wealth-invest-hidden`; exactly one top-nav button is pressed; no horizontal
document overflow. New-document IDs ensure reload probes inspect the new
document, not the old page before navigation starts.

## ROOT_CAUSE_LEGACY_ASSET_FLASH / STOCK_PORTFOLIO_NORMAL_PATH

The initial summaryPanel was asset-mode HTML. Layout moved it to INVEST before
wealth.js converted it to stock mode. Source inventory confirms
`STOCK_PORTFOLIO_MODE` is a fixed `const 'sector'`, with no assignment/change
path. HOME's separate `homeAssetPortfolioPanel` already owns the asset summary.
The former asset-mode summary branch was unreachable in normal production.

## LEGACY_ASSET_DOM_INVENTORY / REMOVED_LEGACY_PRODUCERS

| Removed producer | Reason / removed wiring |
| --- | --- |
| netWorthRow / summaryNetWorth / summaryTotalDebtCaption | Asset-only summary row, used only by unreachable MODE A |
| safeAssetRow / summarySafeAssetVal / subSafeAssetBreakdown and children | Asset-only safe-assets summary, used only by MODE A |
| subAssetBreakdown / subRealEstateVal / subStockVal | Combined property+stock breakdown, always hidden in fixed stock mode |
| pnlSubBreakdown | Combined trade+dividend breakdown, only written by MODE A |
| wealth.js summary MODE A and all-time updater's asset-mode branch | No normal runtime caller; physical JS removal |
| Dead white-theme selectors for removed IDs | No remaining DOM owner |
| Initial asset-mode labels, false zero amounts, fixed period labels | Stock-only labels and neutral data placeholders from parsing |

HOME_ASSET_PORTFOLIO_PRESERVATION: homeAssetPortfolioPanel and
wealthAssetNetWorth/Invest/Expected/Realized/Safe remain. Their wealth:summary
projection and all combined asset calculations remain. Sector chart rendering,
the fixed stock mode constant, day/record metrics and active stock summary IDs
remain because they have normal callers and are outside legacy MODE A cleanup.
The unrelated hidden historical HOME grid was not expanded into this cleanup.

LEGACY_NORMAL_CREATION_COUNT=0 and LEGACY_VISIBLE_FIRST_FRAME_COUNT=0 for the
removed investment rows/breakdowns. The new Chrome probe installs its observer
and RAF sampler before document parsing, holds financial API responses, and
asserts every nonempty initial/reload frame shows only the selected panel.
FALSE_ZERO_FLASH_CONTRACT: the stock summary's initial monetary values and
rates are `—` until real dashboard/summary data arrives, with stock-only labels
present immediately. No obsolete DOM is generated then removed; no observer,
timeout, RAF hiding or body-loading opacity mechanism was added.

## TEST / SAFETY / CHANGED_FILES

Focused: **207 passed, 44 subtests** across four nonoverlapping groups: 75 core
(including 18 native Chrome cases), 97 related regressions + 29 subtests,
16 navigation/layout/version + 15 subtests, and 19 cache/load-order contracts.
Node syntax checks passed for all three changed JavaScript files; py_compile
passed for all nine changed Python test/support files. `git diff --check` passed.
Final full pytest with `PYTHONPATH=tests`: **3084 passed, 3 skipped, 758 passed
subtests**, four existing collection/deprecation warnings, exit 0 in 565.02s.

The earlier completed full run returned 3078 passed, 6 failed, 3 skipped and
758 passed subtests. Five failures referenced the previous static asset version;
their exact version expectations were updated without changing any load-order,
calendar-tone, modal geometry or financial assertions. The remaining failure was
`test_income_bucket_drilldown.py::test_native_daily_zoom_label_alignment[pnl]`
(content width 0, overlay width 9867.15625). Alternating exact-base/hotfix
isolated runs yielded base 2/2 passes and hotfix 2/2 passes. This did not reproduce
the failure or establish that it occurs on base; no baseline-failure claim is made.
The chart implementation and geometry assertions were not modified.
The final full rerun also passed that exact test.

All pytest commands run in an explicit temporary source copy, excluding real
data/ and .env, with synthetic fixtures and guarded provider/network calls.
`PYTHONPATH=tests` is restored in finally. Actual data/.env/credential access=0;
production API calls=0. No record migration, FX/formula/import/feed changes,
account sync/scheduler/settings/security changes, or schema/path changes.
The parked atomicity commit is not an ancestor, and no cherry-pick/rebase/merge
was performed. Git identity/completion results are in the final chat report.

Changed files (deleted files: none):

```text
app/static/index.html
app/static/wealth-invest-tab-state.js
app/static/wealth-layout.css
app/static/wealth-overrides.css
app/static/wealth-planning.js
app/static/wealth.js
docs/hotfix-realized-period-invest-tab-state-10-9k.md
tests/test_invest_period_hotfix.py
tests/test_invest_reload_chrome.py
tests/test_release_version.py
tests/ui_preview.py
tests/test_calendar_ipo_tones_frontend.py
tests/test_dividend_official_source_static.py
tests/test_financial_income_what_if_static.py
tests/test_money_input_ux.py
tests/test_toss_wts_import_modal_scroll.py
```
