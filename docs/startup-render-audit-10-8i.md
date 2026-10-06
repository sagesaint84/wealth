# Wealth startup and dividend first-frame audit

Date: 2026-10-06 (Asia/Seoul).
Verified branch: `maintenance10-8i-startup-render-pipeline-audit`.
Verified starting HEAD: `fd4b0715d26d21b8d5dd401b00cd177b056d2f91`.
The initial working tree was clean. No branch switch, pull, rebase, reset,
provider implementation change, push, or PR creation was performed.

## ROOT CAUSE

The body MutationObserver schedules income renders while the chart host is
unowned. Both unified sources previously published their cache key only after
the request completed, so overlapping renders issued the same GET repeatedly.
The legacy actual renderer also wrote its SVG while the unified script was
unavailable. Startup awaited unrelated income reads serially and loaded estimated
dividends even when actual mode was selected. The account summary, owner importer,
and IPO display helpers independently read data already being loaded elsewhere.
The observer also failed to recognize `wealth-unified-empty` as owned, repeatedly
rendering its own empty state after a successful empty response.

## FIX

- Unified PNL and dividend sources use pending Promise maps keyed by owner and,
  for PNL, trade type. Success populates the cache, failure removes the pending
  entry, and stale owners cannot publish into the current owner's cache or chart.
  The observer recognizes both the unified chart shell and unified empty state
  as owned, preventing the empty-state render loop.
- The actual legacy renderer retains summary/detail rendering, but leaves a
  neutral loading message in the chart host until unified owns the chart.
  Estimated mode retains its separate legacy chart.
- Actual startup and actual-mode owner changes skip estimated reads. The first
  estimated selection loads data; later selections reuse it. Owner changes clear
  that selection's estimated data, and stale responses are ignored.
- The shared API reader normalizes endpoint/query keys, shares pending reads,
  and reuses all-time income responses between overview and unified during
  startup. Completed income-response reuse ends when startup settles, so later
  raw-fetch broker imports/clears cannot leave overview reading an old shared
  response. Keyed in-flight sharing remains active after startup. Mutations
  invalidate cached responses; price refresh and automatic planning snapshot
  writes are exempt because they do not mutate realized income or IPO records.
  Explicit `cache: 'no-store'` reads bypass completed-response reuse.
- Overview PNL/dividend reads run concurrently with independent error handling.
  Startup market, actual-dividend, PNL, and overview work runs concurrently after
  the existing refresh -> dashboard -> snapshot ordering. Refresh remains awaited;
  a failed refresh still suppresses the automatic snapshot.
- The account summary waits for the existing unfiltered dashboard and reacts to
  `wealth:portfolio`. Its securities rows are contract-equivalent: `/api/accounts`
  calls `get_dashboard()` and, for `group=All&owner=모두`, returns the same accounts.
  Its banking data also comes from that unfiltered dashboard.
- Owner options use the shared family-members reader. IPO schedule, compact
  metadata, and event-month startup synchronization share `/api/ipo/market`.
  Subsequent schedule/event synchronizations retain fresh reads, and manual
  refresh retains POST, duplicate-refresh protection, and failure retention.

No debounce delays, production timeouts, overflow changes, owner-filter contract
changes, or provider parallelism were introduced.

## REQUEST COUNTS BEFORE/AFTER

The supplied **production** baseline counts by pathname are below. After counts
are from **local Chrome synthetic preview**, not a new production measurement;
they must not be interpreted as measured production latency improvements.

| Endpoint | Supplied production before | Settled local slow-script actual reload after |
| --- | ---: | ---: |
| `/api/realized-pnl` | 12 | 3: current-year once, all-time twice in separate phases |
| `/api/actual-dividends` | 9 | 2 all-time reads in separate phases |
| `/api/dashboard` | 3 | 1 |
| `/api/accounts` | 2 | 0 |
| `/api/family-members` | 2 | 1 |
| `/api/ipo/market` | 2 | 1 |
| `/api/dividends` | startup read | 0 before estimated selection |

These final counts were rechecked after startup settled on both initial entry
and a fresh-document reload, with 650 ms script delay and the preview's rejected
price-refresh POST. In that deliberately slow-script/fast-startup case, unified
arrives after completed income-response reuse has ended and performs one fresh
read. These are sequential bootstrap/unified phases, not simultaneous misses.
Earlier ordinary-script previews observed 2 PNL/1 actual-dividend reads. Production
refresh lasts longer than this synthetic rejected POST, so production after
counts require a real measurement rather than extrapolation.

The preview's explicit actual startup test invokes and awaits a second
`loadAssetDataForUser()` after automatic startup; doubled noncached counts in
that test are deliberate second loads, not concurrent duplicate startup reads.
PNL year-scoped and all-time reads are distinct contracts. The existing
`wealth-income-period-broker-filter.js` actual-dividend loader reads all-time
data and applies period/broker filtering locally; it remains unchanged.
Exact normalized keys are recorded by the Chrome fixture.
Twelve concurrent identical PNL renders issue **1** network call; twelve concurrent
identical dividend renders issue **1** network call. First estimated selection
issues **1** estimated read and renders its SVG; subsequent selection adds **0**.

The supplied production refresh-prices 1914 ms, estimated-dividends 2739 ms, and
unified-script 603-987 ms timings have not been remeasured against production.

## FIRST-FRAME CHECK

Chrome samples every animation frame from document creation on direct `#dividend`
entry and a true fresh-document reload. The fixture delays unified script delivery
by 650 ms and actual-dividend responses by 200 ms. At 320x568, 390x844, 1024x768,
and 1440x900, no sampled actual-mode frame exposes a legacy actual SVG. A neutral
state is allowed before the eventual unified chart. Reload checks require a new
`performance.timeOrigin`, so the previous document cannot satisfy readiness.

## REGRESSION

Coverage includes period modes, chart geometry/pan state across tab switches,
estimated first load/reselection, exact normalized request keys, pending failure
retry, normalized query order, mutation invalidation, broker filtering, PNL trade
types, and stale A -> B -> C source responses. Existing owner/ledger protections
remain covered. No backend API or owner filtering implementation was changed.
Chrome also verifies that empty PNL/dividend hosts remain stable across unrelated
body mutations, with no new dividend renders scheduled by the observer.

## TESTS

Final validation: **2746 passed, 3 skipped, 4 warnings, 669 subtests passed**
in 283.11 seconds, exit code 0, using the project Python 3.14 environment.
All 18 Chrome route/first-frame tests passed in that full run, including the
empty-state observer check. All 7 changed JavaScript files passed `node --check`;
`git diff --check` passed. Commands:

```powershell
$env:PYTHONPATH="$pwd;$pwd\tests"
$env:TEMP="$env:LOCALAPPDATA\Temp"
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
.\.venv\Scripts\python.exe -c "import os,tempfile,pytest; tempfile.tempdir=os.environ['TEMP']; raise SystemExit(pytest.main(['-q']))"
git diff --name-only -- '*.js' | ForEach-Object { node --check $_ }
git diff --check
```

The import path resolves existing `regression_support` imports. All three temp
variables and Python's cached temp directory are set to Local AppData to avoid
the configured ESTsoft temporary directory's intermittent Chrome profile locking.
CDP polling tolerates only the specific navigation-destroyed
context response; other errors still fail tests. Earlier validation found two
source-string assertions expecting direct `fetch`; they were updated to assert
the shared reader while retaining their contract checks.

Windows Python runtimes also reported intermittent native access violations
during file reads and preview/subprocess threads, occasionally leaving scripts
uninitialized in earlier runs.
Chrome was independently rerun under bundled Python 3.12 (18 passed), and an
isolated temporary Python 3.12 environment with the repository requirements,
pytest, websocket-client, and Windows `tzdata` was prepared for full-suite
validation. The Chrome fixture preloads immutable static asset bytes before
HTTP serving; reloads still request those bytes and the slow-script delay remains
unchanged. This avoids filesystem reads in preview worker threads. This does
not alter the repository's environment or dependencies.
The Python 3.12 exploration also exposed three existing security-test mocks that
depend on Python 3.14's `Path.exists()` implementation (3.12 calls mocked
`Path.stat()`). No unrelated security code or tests were changed; final full-suite
validation uses the project's Python 3.14 environment.

## CURSOR ROOT CAUSE

- App-owned: **NOT PROVEN**.
- Element: no cursor-shaped element was identified. The sampled screen-center
  chain was `DIV.wealth-content -> DIV.wealth-workspace ->
  DIV#userAssetDashboardWrapper -> MAIN.shell -> BODY.wealth-layout -> HTML`.
  Each had computed `position: static`, `z-index: auto`, `pointer-events: auto`.
- Creator: not identified because the reported black artifact did not reproduce
  in the local headless preview.
- Cleanup path: no orphan cursor DOM or corresponding cleanup path was found.
- Reproduction: investigated during full reload, dividend/other income tab
  switches, period changes, and estimated/actual transitions in Chrome. Source
  searches covered cursor suppression, custom cursor DOM, mouse/pointer helpers,
  drag ghosts, coachmarks, SVG icons, pseudo-elements, positioned overlays, DOM
  append paths, and MutationObserver/ResizeObserver code. Chart dragging changes
  native CSS cursor/pointer capture; it does not create a cursor icon DOM node.

A separately captured and visually inspected 1440x900 direct-dividend screenshot
also showed no duplicate black cursor. Its center hit was
`DIV.panel-head.dividend-head` (no id), `position: static`, `z-index: auto`,
`pointer-events: auto`. The screenshot is a local temporary diagnostic artifact
at `%LOCALAPPDATA%/Temp/wealth-dividend-cursor-audit.png`.

This does not prove that the user's production artifact is browser/OS-owned.
The exact reported pixel was unavailable; screen center is only a probe. An
artifact visible at a known coordinate with no matching app DOM would justify
**NOT APP-OWNED**, but that observation was not obtained here.

## CURSOR FIX

- Fixed in this commit: **NO**.
- Reason: no reproduced app-owned cause, and no small related fix was proven.
- Evidence: runtime `document.elementFromPoint()` center chain above and static
  source audit. No speculative cursor-removal or overflow rule was added.
- Follow-up: reproduce in the affected visible browser, record the exact pixel,
  screenshot and complete element/pseudo-element stack, compare a clean browser
  profile, then isolate app versus extension/OS/browser ownership. If unrelated,
  make a separate PR rather than widening this startup fix.

## IPO PERFORMANCE

The attached external-source audit is recorded separately from the implemented
display-read dedupe. Production cold-entry/manual-refresh wall times, per-source
start/end/duration/success/retry measurements, Metalogos call counts, cache hit
rates, and the slowest live source are **not measured**. No authenticated
production endpoint/session was provided, and the regression environment blocks
external provider traffic. No fabricated timings or projected numeric speedup
are reported.

Cold entry's `/api/ipo/market` is a read-only persisted-store presentation call;
it does not invoke discovery or Metalogos. Manual refresh invokes providers.

Observed call graph:

```text
loadIpoSchedule / compact metadata / event-month startup
  -> shared GET /api/ipo/market
  -> read_market_store_read_only -> present_market_store

refreshIpoSchedule (frontend refreshInFlight guard)
  -> POST /api/ipo/market/refresh
  -> asyncio.to_thread(orchestrator.refresh_ipo_market)
  -> installed refresh_adapter.refresh_ipo_market
     -> base market-only pipeline: configured KIS schedule, conditional NAVER
        progress lookup; persisted results/scoring
     -> under refresh file lock: discover_and_merge_primary_sources
        -> KIND -> Npay -> NAVER progress -> Metalogos issuer references
        -> company-scoped DART schedule/market reconciliation
     -> refresh_missing_metalogos_references (only missing persisted references)
        -> Metalogos calendar -> sitemap fallback -> sequential details
     -> targeted DART score recovery (maximum 4 candidates)
     -> merged result + presented persisted market
```

KIS is credential-dependent. Base market-only flow explicitly marks KRX as
historical-only and skips base deep DART; the adapter performs scoped DART work.
Provider names here describe discovered call sites and conditions, not a claim
that every provider executed in a live refresh.

Metalogos implementation findings:

- `fetch_company_items()` normalizes/deduplicates issuer names, caps the batch
  at 40 by default, and loops serially. It is a batch Python entry point, not a
  batch HTTP request: each issuer gets a search request, followed by up to 10
  candidate detail requests until an exact relevant issuer matches.
- `fetch_calendar_items()` fetches calendar, optionally sitemap, then serial
  detail pages; its default cap is 60, and missing-reference recovery passes 40.
- `httpx.Client` uses a 15-second timeout and follows redirects. No explicit
  retry/backoff loop or response TTL cache exists in this client. Detail/search
  failures are caught and skipped; a failed calendar/sitemap can fail that source.
- Market references persist in `sources.metalogos160`. Missing-reference recovery
  skips rows already containing a reference. The primary company-reference path
  can still repeat issuer searches across refreshes; persisted references are
  not a general HTTP cache. There is no cross-path HTTP detail-page dedupe.
- Total Metalogos latency can accumulate across sequential issuers/detail pages;
  one slow-call versus many-call contribution requires live timing to quantify.
- The refresh adapter waits for reference work before returning manual refresh.
  Supplemental source failures are recorded separately, but source waits still
  contribute to total wall time. No provider execution behavior was changed.

## IPO DEPENDENCY

- MUST_SERIAL: identifier/issuer discovery before company-specific enrichment;
  search before details; calendar/sitemap before details; canonical merge before
  targeted recovery/scoring/persistence.
- SAFE_PARALLEL candidates: independently fetched public discovery results,
  provided merges remain deterministic and results are staged separately.
- BOUNDED_PARALLEL candidates: independent issuer searches/detail fetches and
  DART issuer work. Provider limits and client/session isolation are unverified;
  do not fan out using the current shared mutable store/client unchecked.
- CACHEABLE candidates: normalized issuer search results and detail references,
  with source timestamp/version and manual bypass. No validated TTL is selected.
- DEDUPABLE: normalized company/source/URL within a refresh and overlapping
  primary/fallback reference scans; frontend display reads are fixed here.
- DEFERABLE: Metalogos reference annotations (Wealth Score explicitly excludes
  these); persisted core cards already render without them.
- UNKNOWN: rate limits, session/thread safety, appropriate TTL, live retry costs,
  provider policy, and connection-pool constraints.

## IPO RECOMMENDATION

For a separate measured provider PR, capture redacted per-source/issuer/URL-key
spans for cold entry, tab return, month reselection, owner change, manual refresh,
and two rapid refresh clicks. Preserve frontend/backend refresh guards and file
locking. Compare total refresh time with summed spans, including failures.
Consider returning core schedule results before independent reference enrichment,
isolated workers with a small measured concurrency bound, per-refresh URL dedupe,
and versioned reference caching. Preserve canonical source precedence, deterministic
merges, partial-result behavior, retry limits, and atomic persistence. Numeric
wall-clock savings require measurements and are currently unknown.

Files audited: `app/main.py`, `app/services/ipo/orchestrator.py`,
`refresh_adapter.py`, `source_discovery.py`, `metalogos_client.py`,
`metalogos_reference_refresh.py`, and the IPO frontend files. Provider files are
unchanged in this commit.

## FILES / COMMIT / WORKTREE STATUS

Implementation files:

- `app/static/wealth.js`
- `app/static/wealth-timeseries-unified.js`
- `app/static/wealth-account-section-summary.js`
- `app/static/wealth-accountinfo-owner-options.js`
- `app/static/wealth-ipo.js`
- `app/static/wealth-ipo-compact-view.js`
- `app/static/wealth-ipo-event-months.js`

Regression files:

- `tests/test_dividend_income_route_chrome.py`
- `tests/test_startup_source_dedupe.py`
- `tests/test_initial_asset_load.py`
- `tests/test_owner_filter_loads.py`
- `tests/test_account_section_summary_10_6b_frontend.py`
- `tests/test_accountinfo_owner_options_frontend.py`
- `tests/test_ipo_future_compact_view_frontend.py`
- `tests/test_ipo_market_refresh.py`

This audit document is the remaining changed file. The final
response supplies its full SHA, final test totals, and post-commit worktree
status. No push or PR is part of this task.
