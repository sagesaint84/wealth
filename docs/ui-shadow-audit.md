# UI shadow / retired renderer audit

Audit starting commit: `e61ff7dad748a754af1e2776de52f677ea6ba6ae`.
Only synthetic storage and loopback Chrome fixtures were used. No production
financial data was inspected. The cleanup is limited to the retired KFTC frontend.

## Classification

| Path / UI | Classification | Evidence and disposition |
| --- | --- | --- |
| `index.html`: `kftcOpenBankingCard`, `openapiKftcSection` | CONFIRMED_SHADOW_UI → SAFE_TO_REMOVE | Parser creates both sections. `wealth-kftc-retirement.js` injects `display:none!important`, removes them, and observes the whole body to remove future instances. Native Chrome confirmed creation and removal. Both producers removed. |
| `wealth.js`: KFTC status/OAuth/accounts/balance/disconnect/config handlers | SAFE_TO_REMOVE | Retirement replaces all seven global handlers with no-ops. Banking/settings callsites therefore perform no KFTC reads in the settled UI. Removed handlers and their no-op callsites; no backend route or data deletion. |
| KFTC callback query notifications | ACTIVE_EXTENSION | `kftc_connected` / `kftc_error` still produce notifications and clean the query URL independently of the retired account UI. Kept notifications and URL cleanup; removed their ineffective status refresh call. |
| `assetChart` | FALLBACK_REQUIRED | `renderAssetRecords()` writes a legacy chart only when `renderStock` is unavailable. Once unified is ready, it calls unified directly. Tax-account presentation intentionally uses the same host and is excluded by unified's tax-view guard. Kept both contracts. |
| `wealthHistoryPlot` | FALLBACK_REQUIRED | Its original renderer is `wealth-planning.js::renderHistory()`, not `wealth.js`. Unified explicitly clicks the legacy ALL control, then reads date/title values from `.wealth-history-point` after two RAFs to populate its source cache. Removing the producer would break the current unified data path. |
| `pnlBarChartWrap` | FALLBACK_REQUIRED | `renderRealizedPnl()` only inserts its old SVG when unified is unavailable. Legacy summary/detail preparation remains active. No legacy host writes were observed after unified initialization in this audit. |
| `dividendBarChartWrap` | ACTIVE_EXTENSION | Actual mode prepares detail data but never inserts the old SVG; before unified readiness it writes neutral loading text. Estimated mode still has a separate, supported legacy chart. Kept both mode contracts. |
| `ledgerTrendContainer` | CONFIRMED_SHADOW_UI | `renderLedgerTrend()` still inserts `.ledger-trend-chart`. Unified's body observer sees an unowned host and queues replacement for the next RAF. History expansion also calls this producer. Removal safety is not established: legacy history/panzoom paths and unavailable-unified behavior remain supported. No chart changes made. |
| `index.html`: `6-MONTH CASHFLOW TREND` | CONFIRMED_SHADOW_UI | Static eyebrow is generated, then `wealth-timeseries-visible-range.js::hideLegacyLedgerEyebrow()` removes it for unified ledger charts. The obsolete JS text writer is already gone. The static fallback markup and defensive remover were retained. |
| SVG X labels → HTML X-axis overlay | ACTIVE_EXTENSION | Label-layout masks unified SVG date/year text and renders HTML labels from the same aggregation, with geometry synchronization and pixel thinning. This is an active layout adapter, not evidence that chart data/renderers can be deleted. |
| Legacy `wealth-timeseries-panzoom.js` / ledger-history extension | FALLBACK_REQUIRED | Selectors target legacy stock/networth SVGs and ledger columns. Ledger history expansion mutates its synthetic in-memory trend and invokes the legacy producer. Unified owns separate panzoom behavior. Kept pending an explicit data/control handoff. |
| Home KPI `small` rows in `wealth-layout.js` | CONFIRMED_SHADOW_UI | The initial template creates rows that `splitMetricRows()` immediately removes/recreates synchronously. Final financial metric IDs and updater contracts are active. A direct-template cleanup is a separate candidate; not mixed into KFTC removal. |
| Per-panel family tabs / `recordViewTabs` | UNCERTAIN | CSS hides generated controls, but owner-state synchronization, view handlers, tax views and fallback contracts still reference them. A lack of visible UI is insufficient deletion proof. |
| Disabled `kisSourceAccount` control | UNCERTAIN | Markup is still generated and hidden by a `:has()` rule; explicit frontend tests preserve this source-account placeholder contract. No WTS/KIS import changes made. |
| Account row enhancement / reorder group merging | ACTIVE_EXTENSION | Layout moves delete controls into an accessible menu; reorder consolidates broker alias groups after moving their rows. Removing an emptied duplicate group does not retire its accounts. |
| Automation status, money previews, IPO sale bridge, calendar tones | ACTIVE_EXTENSION | Observers/styles provide live status, form previews, sale-link tools and schedule states. Their observers are not deletion evidence. |

## Chrome evidence (1280 and 390)

Instrumentation starts before document parsing. It records DOM insertion/removal,
host `innerHTML` writes, viewport visibility and repeated RAF samples. Tested cold
reload, bank/settings tabs, price refresh, stock/PnL/dividend/ledger navigation and
planning history refresh. All API responses are synthetic.

Both widths gave the same relevant counts:

| Observation | Before | After KFTC removal |
| --- | ---: | ---: |
| KFTC section identities created then removed | 2 | 0 |
| Visible KFTC RAF samples | 0 | 0 |
| KFTC API calls | 0 | 0 |
| Legacy stock host writes during startup | 1 | 1 |
| Legacy networth host writes | 6 | 6 |
| Legacy ledger host writes | 4 | 4 |
| Legacy PnL / actual-dividend host writes after unified readiness | 0 / 0 | 0 / 0 |
| Visible legacy ledger RAF samples during tab/render operations | 2 | 2 |
| Visible legacy networth RAF samples during history refresh | 1 | 1 |

The ledger samples were separate transitions, not consecutive legacy frames.
**RAF samples are pre-paint observations.** These results establish renderer
replacement and a transient visible DOM state; they do not prove that Chrome's
compositor painted a legacy frame or that a production flash occurs. Production
latency, provider failures and all extension combinations were not reproduced.
Existing direct-PnL/actual-dividend first-frame tests are also retained and run.

A second native Chrome probe blocked the unified script at both widths. Stock,
PnL and ledger still produced their legacy charts; actual dividends stayed in
the neutral loading state without a legacy SVG. This proves an executable
unavailable-module fallback, not its frequency or necessity in production.
Networth's legacy producer additionally remains necessary to supply unified's
current SVG-based source adapter.

The new KFTC regression blocks its former retirement script, then checks cold
startup, reload, native bank/settings clicks and refresh. No retired DOM may ever
be created, removed or displayed; no retired handler/API read may be required.

## Follow-up boundaries

Before consolidating networth, expose planning's filtered history as an explicit
read-only source instead of scraping legacy SVG titles. Before consolidating
ledger, give its history/annual controls a deterministic unified handoff and test
unavailable-module behavior. Keep stock tax views and estimated dividends
separate. No chart producer should be deleted solely because an observer later
replaces it.

## Validation

- Focused KFTC backend/frontend, native Chrome, account/overdraft and chart
  regressions: 143 passed; 7 subtests passed.
- Unavailable-unified native Chrome probe: 2 passed (1280 / 390).
- Full pytest in guarded temporary storage: 2981 passed, 3 skipped,
  670 subtests passed; exit code 0.
- Both changed production JS files passed `node --check`; all three changed
  Python test files passed `py_compile`; `git diff --check` passed.
- The first focused run failed an existing storage-signature check because the
  copied fixture lacked the empty `data/users/alice` directory. Preparing that
  temporary directory resolved the fixture issue; no backend change was made.
- Windows/Python 3.14 printed access-violation diagnostics during some Chrome
  probes and full-suite collection. Execution continued and pytest exited 0.
  The underlying native diagnostic was not established as harmless or fixed.
