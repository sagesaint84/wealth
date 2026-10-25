# Issue #176 home tabs validation — 2026-10-25

Baseline: `origin/main@940a42053297059dcbafdc837458876269958086` (includes merged PR #165).
Branch: `codex/v213-home-three-tabs`.
Worktree: `C:/Users/USER/.codex/worktrees/v213-home-three-tabs/wealth`.
The primary main checkout was clean before work and remains unchanged. The protected v212 worktree was not edited.

## Implementation and ownership

- `index.html`: existing `homeAssetPortfolioPanel` and `wealthMarketSlot > marketPanel > marketGrid` become tab panels. A single `wealthHistorySlot` receives the existing dynamic history article. Parser-time route selection prevents inactive content painting. Native `hidden` is the only tab visibility mechanism.
- `wealth-layout.js`: one delegated click listener and one keyboard listener on `homeTabs`; the existing hash navigator emits `wealth:view`. URLs: `#home`, `#home/history`, `#home/markets`. Returning via the main Home menu selects the portfolio. Refresh and browser history retain the explicit tab URL.
- `wealth-planning.js`: constructs the same history article once, appends it to its slot, and skips rendering while hidden. On home tab entry its existing `wealth:view` listener renders using actual width, without the old 800px fallback.
- The existing `wealth-timeseries-unified.js` captures the legacy history source, adopts period controls, and provides the final chart, labels and pan/zoom. No second renderer or data cache was added.
- `wealth.js` is unchanged: `WealthStartup.loadVisible()` sees `marketGrid` only on the market tab and calls the existing `loadMarkets()`. Existing in-flight request sharing, visibility and generation guards handle inactive/late responses.
- Financial calculation code, account sync, price refresh, APIs, persistence, Toss, IPO, pension and tax implementation remain unchanged.
- Only changed layout JS/CSS and planning JS get revision `2.1.3-home-tabs1`. APP_VERSION stays 2.1.3; core JS, SW and all other revisions stay unchanged.
- PR #165 operating archive remains byte-for-byte unchanged. README and ROADMAP distinguish this unshipped candidate from operations and keep Fear & Greed integration as future work.

## Functional evidence

`tests/test_home_three_tabs_chrome.py`: 8 passed after final CSS change. Real Chromium at 320/360/390/768/1280px; synthetic loopback APIs and in-memory planning mutations only.

Coverage includes parser-time first paint for all 3 URLs at all 5 widths; exact panel selection; ARIA relationships and roving tabindex; arrow/Home/End keys; touch hit testing at mobile widths; no page-wide horizontal overflow; one DOM ID per element; one route event per tab selection; no initial market request; in-flight market request sharing; late hidden responses; failure and successful re-entry; history real viewport width and labels; owner changes while visible/hidden; manual add/edit/delete; period mode retention; wheel zoom and horizontal chart scroll; page re-entry, reload, back and forward; uncaught errors and rejected promises.

Initial targeted run: 99 passed, 21 subtests passed (initial HTML/route, owner, startup, labels, manual history, planning). A separate initial source/version/layout run: 23 passed, 15 subtests passed. These overlap and must not be summed as unique tests.

Final broader regression run: **247 passed, 5 failed, 51 subtests passed** (307.39s). Four failures were the previous market regression's assumption that entering `#home` immediately loads markets. That test now asserts zero market reads on portfolio, clicks the market tab, and retains all seven-card/rate/link/delayed-source assertions. Those four cases passed on focused rerun.

The fifth failure was `test_initial_route_themes_service_worker_and_history`: on OLED `#dividend` reload, the last sampled frame had no visible income panel. The same unchanged test passed in the earlier 99-test run and in the final focused rerun. Root cause is **UNCONFIRMED**; a passing retry does not erase the original result. No unrelated dividend code or assertion was weakened.

Final focused rerun: **5 passed** (36.83s), covering all four updated market cases and the unchanged theme/SW/history test. The full 252-test selection was not rerun after the test-only market adaptation. Regression gate is **REVIEW_REQUIRED** because the initial-frame failure was intermittent.

Broader command:

```powershell
$env:PYTHONPATH='.;tests'
python -m pytest tests/test_home_three_tabs_chrome.py tests/test_home_initial_html_chrome.py tests/test_home_dashboard_batch2.py tests/test_owner_filter_loads.py tests/test_layout_contract.py tests/test_release_version.py tests/test_startup_performance_p0.py tests/test_startup_source_dedupe.py tests/test_timeseries_label_layout.py tests/test_timeseries_panzoom.py tests/test_timeseries_unified.py tests/test_timeseries_period_core.py tests/test_timeseries_visible_range.py tests/test_manual_history.py tests/test_planning_regression.py tests/test_initial_asset_load.py tests/test_view_initial_work_chrome.py tests/test_service_worker_cache_guard.py tests/test_market_signals_holdings_chrome.py tests/test_toss_wts_source_account_ui.py tests/test_frontend_pension_irp_tax_correctness.py -q
```

Final focused command:

```powershell
python -m pytest tests/test_home_initial_html_chrome.py::test_initial_route_themes_service_worker_and_history tests/test_market_signals_holdings_chrome.py::test_existing_market_cards_daily_units_dates_and_official_links -q
```

The first combined collection attempt without `PYTHONPATH` did not execute tests because `regression_support` was not importable. The documented corrected command ran the tests.
Full pytest: NOT_RUN.

Static DOM audit: three existing-content panels; no duplicate IDs. CSS selectors apply only to home tabs and were checked against the existing section-tab specificity. No copied screen, unused superseded home screen or new market API/event pipeline was introduced. `git diff --check`: PASS.

Synthetic screenshots (outside the repository) were captured at 320 and 1280px for all tabs; 320px history and 1280px portfolio were visually inspected.

## Performance evidence — FAIL / HOLD

Reproducer: `PYTHONPATH=.;tests python -m tests.home_tabs_benchmark` on Windows. Uses a temporary copy of static files only, restores the four baseline assets from Git, matches CRLF line endings, and removes the temporary directory automatically. Synthetic APIs only; gzip; HTTP cache disabled; SW bypass; 3 alternating cold samples per variant and width. Mobile 360px: CPU 4x, latency 40ms, download 250KB/s. Desktop 1280px: CPU 1x, latency 20ms, download 500KB/s.

First comparison is preserved in `home-three-tabs-performance-first.json`. After correcting the final home-tab CSS specificity, the final comparison is `home-three-tabs-performance.json`. No further tuning or selective resampling was used to claim a pass.

| Final median | main | candidate | difference |
|---|---:|---:|---:|
| 360px FCP | 632ms | 664ms | +32ms |
| 360px first asset | 3829.9ms | 4509.6ms | +679.7ms |
| 360px readiness | 4112.1ms | 4833.9ms | +721.8ms |
| 360px API count | 12 | 11 | -1 |
| 1280px FCP | 324ms | 336ms | +12ms |
| 1280px first asset | 1630.7ms | 1628.0ms | -2.7ms |
| 1280px readiness | 1787.2ms | 1777.1ms | -10.1ms |
| 1280px API count | 13 | 12 | -1 |

The first comparison also had slower mobile medians (+287.8ms asset, +177.1ms readiness). Numeric no-regression is not established; the exact code cause is UNCONFIRMED. Samples show substantial runtime variance and browser-level node/listener counters accumulate across navigations, so those counters are not proof of per-page event leakage. Functional tests independently assert one event per transition. No previous release performance exception is inherited. No warm-cache or production performance pass is claimed.

## Gates

| Gate | Result |
|---|---|
| SOURCE_GATE | PASS — fetched origin/main matches supplied SHA; PR #165 included |
| WORKTREE_GATE | PASS — isolated managed worktree/feature branch; main and protected worktree untouched |
| HOME_TAB_STRUCTURE_GATE | PASS — exactly portfolio/history/markets, portfolio default |
| NO_DUPLICATE_UI_GATE | PASS — original panels/renderers/IDs reused |
| HISTORY_CHART_GATE | PASS — visible-width rendering, unified chart/period/pan/zoom/CRUD/owner tests |
| MARKET_LOADING_GATE | PASS — lazy first entry, in-flight sharing, failure/late-response tests |
| MOBILE_CHROMIUM_GATE | PASS — 5 requested widths, initial paint and interaction coverage |
| REGRESSION_GATE | REVIEW_REQUIRED — 247 passed/5 failed; all five focused reruns passed, one initial-frame failure cause unconfirmed; full pytest NOT_RUN |
| PERFORMANCE_GATE | FAIL / HOLD — mobile medians slower in both comparisons |
| CHANGE_SCOPE_GATE | PASS — UI, tests, CI test registration and candidate docs only |
| PR_STATUS | DRAFT_AUTHORIZED — user explicitly authorized Commit/Push/Draft PR with PERFORMANCE_GATE=FAIL/HOLD; current CI must be checked on GitHub |
| DEPLOY_STATUS | NOT_DEPLOYED — no merge, release, Docker publish or Oracle operation |


## Exact-label follow-up — 2026-10-25

The home tab labels and native Chromium accessibility names are exactly **자산 포트폴리오 / 순자산 추이 / 주요지수**. The portfolio panel continues to use `aria-labelledby=homeTab-portfolio`, so its accessible name follows the same visible tab label. README and runtime assertions match.

Validation: `PYTHONPATH=.;tests python -m pytest tests/test_home_three_tabs_chrome.py tests/test_home_dashboard_batch2.py tests/test_release_version.py -q`: **19 passed** (39.29s). Native accessibility-tree names were checked at all five requested widths. This is FUNCTIONAL_GATE=PASS for the targeted home tab behavior, while the earlier intermittent regression remains disclosed separately.

FUNCTIONAL_GATE=PASS
PERFORMANCE_GATE=FAIL/HOLD
MERGE_GATE=HOLD
DEPLOY_GATE=HOLD

Neither historical performance JSON file was modified. No performance threshold was weakened; no new timing sample replaces either failed 360px comparison. No performance fix or root cause is claimed.


## Performance mechanism diagnosis and CI follow-up

See `HOME_THREE_TABS_DIAGNOSIS.md`, the synthetic raw `home-three-tabs-diagnostics.json`, and reproducer `tests/home_tabs_diagnostics.py`. Re-entry causes 2 legacy history SVG writes and 1 unified chart render per history entry, but none on initial portfolio. Market reads occur once per market entry. The first-display cause remains UNCONFIRMED. Historical mobile JS/style medians are higher while LayoutDuration medians are lower. No new gate benchmark was run and neither failed timing record was changed.

IPO CI at label HEAD c30d09a failed on an overlooked old CSS revision contract (51 passed, 1 failed). Exact CSS/JS revision expectations were corrected in two additional tests, with 15 local tests passed. This does not erase the failed CI run; successor CI is tracked at its exact SHA in PR #177. FUNCTIONAL_GATE=PASS (19 home/label tests); REGRESSION_GATE=REVIEW_REQUIRED; PERFORMANCE_GATE=FAIL/HOLD; MERGE_GATE=HOLD; DEPLOY_GATE=HOLD.
