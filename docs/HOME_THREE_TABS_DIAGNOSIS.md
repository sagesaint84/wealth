# Home three-tab performance diagnosis — 2026-10-25

FUNCTIONAL_GATE=PASS (targeted home behavior)
PERFORMANCE_GATE=FAIL/HOLD
MERGE_GATE=HOLD
DEPLOY_GATE=HOLD
FIRST_DISPLAY_ROOT_CAUSE=UNCONFIRMED

Draft PR: https://github.com/sagesaint84/wealth/pull/177

## Method and evidence boundaries

The two failed 360px timing comparisons remain immutable in `home-three-tabs-performance-first.json` and `home-three-tabs-performance.json`. No new gate comparison was run in this follow-up. Their criteria were not relaxed and their failure status was not replaced.

`tests/home_tabs_diagnostics.py` ran one fresh Chromium process per variant against temporary static copies: baseline `940a420`, candidate `c30d09a`, synthetic loopback responses, invented nonempty history, 360px mobile emulation, CPU/network unthrottled. Only the copies were instrumented. Source wrappers count history calls/SVG writes/unified chart renders and route events; API instrumentation records paths/methods/phases without bodies. Eight animation frames separate phases. This is a bounded mechanism diagnostic, **not statistically comparable to the throttled timing gate**, and cannot establish speed improvement.

The diagnostic baseline contains synthetic history, while the original timing harness uses empty planning history. Diagnostic API totals also differ because the nonempty unified chart path may consult existing source APIs. Compare individual mechanisms, not totals between those two different fixtures.

Raw diagnostic: `home-three-tabs-diagnostics.json`. Temporary copies and Chromium profiles are automatically removed. No financial store or environment file was opened by the diagnostic tool.

## Render and request counts

| Phase | New wealth:view events | New history SVG writes | New unified net-worth renders | New market API reads |
|---|---:|---:|---:|---:|
| Candidate initial portfolio | 2 inherited startup notifications | 0 | 0 | 0 |
| First history entry | 1 | 2 | 1 | 0 |
| Portfolio return | 1 | 0 | 0 | 0 |
| Second history entry, unchanged data | 1 | 2 | 1 | 0 |
| First markets entry | 1 | 0 | 0 | 1 |
| Portfolio return | 1 | 0 | 0 | 0 |
| Second markets entry | 1 | 0 | 0 | 1 |

Baseline startup: the same 2 notifications (home navigation and inherited planning `invest` notification), 3 legacy history SVG writes, 1 unified history render, 1 market read. The new tabs did not add another startup route notification. Each tested tab transition adds exactly one event.

### Confirmed: history source is rebuilt on unchanged re-entry

`wealth-planning.js` schedules `renderHistory()` on `wealth:view` with detail home. It writes its existing SVG using actual plot width. `wealth-timeseries-unified.js` detects that source, and `ensureNetWorthSource()` clicks the ALL period control internally to capture the complete saved history, which invokes the existing period handler and writes the legacy SVG again. Two animation frames later it captures points and writes the unified chart.

This explains the observed **2 legacy SVG writes + 1 unified chart render on each history entry**, including a second visit without data changes. Existing saved-source capture already used this bridge in main. Tab re-entry exposes repeated source reconstruction. It is a concrete chart-entry DOM/JS workload candidate; it is **not a confirmed cause of the initial portfolio timing failure**, because initial portfolio generated zero history SVGs/unified history charts and the timed fixture had no history records.

A future optimization would need to distinguish source-data invalidation (owner/revision/CRUD/period) from visibility/width changes and preserve full-history capture, responsive geometry and pan/zoom. No speculative optimization or weakened chart assertion is included here.

### Inactive initialization

On candidate portfolio startup, history function entry was observed 3 times, but all had hidden geometry and returned with **zero plot writes**. Calls on portfolio/market transitions also returned without writes. The history article/dialog and investment bucket DOM are still constructed once by the existing planning module; the planning state read remains part of its shared initialization. They are not wholly lazy, but this mechanism predates the tabs.

No startup market read occurs on the portfolio tab. No hidden history chart render was observed. The shared document-body MutationObserver and legacy event subscribers still run; their aggregate traversal/style-read cost is a candidate for later profiling, not an identified regression source.

### Requests and event ownership

Each market entry caused one market-overview fetch; portfolio/history entries caused none. Existing in-flight sharing and hidden late-response behavior pass the home Chromium tests. Re-fetch on a separate market re-entry is existing revalidation behavior, not a concurrent duplicate request.

An independent CDP DOMDebugger inspection of connected nodes found exactly:

- homeTabs: one click and one keydown listener;
- history article: one delegated click listener;
- history period strip: one click listener.

Raw browser Nodes/JSEventListeners counters include detached nodes/objects until garbage collection. Neither their growth across old benchmark navigations nor this small diagnostic proves a listener leak. Connected-node counts and one-event-per-transition assertions provide the applicable evidence.

## Existing mobile JS/Layout evidence (no resampling)

The following are medians computed from the **already saved** 360px samples; Chrome reports seconds, converted here to milliseconds:

| Recorded comparison | Metric | main | candidate |
|---|---|---:|---:|
| First | ScriptDuration | 497.18 | 724.83 |
| First | LayoutDuration | 46.39 | 41.51 |
| First | RecalcStyleDuration | 107.68 | 131.24 |
| Second | ScriptDuration | 439.57 | 575.28 |
| Second | LayoutDuration | 56.53 | 52.37 |
| Second | RecalcStyleDuration | 131.31 | 155.70 |

Whole-page JS and style costs are higher in both saved sample medians. Whole-page LayoutDuration is lower, so these data do **not** support an overall LayoutDuration increase as the sole explanation. Metrics cover complete page startup, not just new tab code; individual call stacks were not captured during those historical slow samples. Their causal attribution remains UNCONFIRMED.

The diagnostic's single unthrottled runs show fewer initial SVGs/listeners/nodes in the candidate, but are not a replacement speed benchmark. No improvement claim follows from them. A causal explanation of the +287.8ms and +679.7ms first-asset medians still requires attributable traces under the original conditions, retained as additional evidence rather than overwriting the failed records.

## Added payload and DOM/CSS cost

Measured from exact CRLF static source before instrumentation; gzip level 5 is illustrative for HTML and corresponds to the existing JS/CSS compression setting:

| Asset | Extra raw bytes vs main | Extra gzip5 bytes |
|---|---:|---:|
| index.html | 2119 | 398 |
| wealth-layout.js | 858 | 238 |
| wealth-layout.css | 414 | 81 |
| wealth-planning.js | 59 | -1 |
| JS/CSS total | 1331 | 318 |

The extra source is small, but small size alone does not prove zero runtime cost. The synthetic transport serves HTML separately without the JS/CSS gzip middleware, so the HTML gzip column is not a claim about wire transfer. The new static DOM is 3 tab buttons, their strip and 1 history slot; existing financial panels are reused. `syncHome()` queries the three panels/buttons and writes selection attributes/classes on navigation. Its geometry invalidation combined with existing global observers is a plausible style-cost candidate, but has not been causally tied to the slow samples. No extra script file, renderer, financial API pipeline or chart library is shipped.

## CI findings and contract repair

At label HEAD `c30d09a9a0959baca3b2ef0ff2692ea0314f4a2b`, GitHub IPO run `40195353166` failed: **51 passed, 1 failed**, `test_layout_stylesheet_uses_current_hotfix_cache_version`. Job `121174895838` logs confirm that the shared test expected the old `2.1.3-ui-icons-rate1` CSS revision, while the changed asset correctly uses `2.1.3-home-tabs1`.

The exact-value contract in `tests/test_toss_wts_import_modal_scroll.py` is updated to the new CSS revision. A repository-wide revision search also found the old layout JS revision in `tests/test_money_input_ux.py`; it is updated while leaving the unchanged core JS revision alone. No test is removed or relaxed, and no application Toss/IPO code changes.

Local repair verification: `PYTHONPATH=.;tests python -m pytest tests/test_toss_wts_import_modal_scroll.py tests/test_calendar_ipo_tones_frontend.py tests/test_money_input_ux.py tests/test_release_version.py -q`: **15 passed** (1.97s). The earlier failed CI result is preserved; successor CI must be checked at its exact HEAD.

## Protection and release state

Only explicitly listed implementation, tests and useful diagnostic/report files are staged. Test caches, temporary copies, screenshots, logs containing personal data, `.env`, data stores and credentials are excluded. The main checkout stays at `940a420`; the protected v212 worktree is untouched. Historical timing JSONs are unchanged from `c5487ff`. No force push, Draft release, main merge or Oracle operation was performed.

The first-display root cause is **UNCONFIRMED**, with a confirmed history re-entry rebuild mechanism and whole-page JS/style overhead candidates documented above. **PERFORMANCE_GATE=FAIL/HOLD remains in force even if successor CI passes.**
