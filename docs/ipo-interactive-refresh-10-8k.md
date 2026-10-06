# IPO interactive refresh and Metalogos lookup audit

## ROOT CAUSE

Verified starting branch `hotfix10-8k-ipo-refresh-matalogos-timeout` and HEAD `c580a722bc233ec1bf90df60995aee5eaf6d673e`; the starting working tree was clean.

Public probes on 2026-10-06 confirmed that `/160ipo/stock?query=엘리스그룹` and `?query=멜콘` expose the same JincoSTech card, `B202607142`. This route serves the shared stock list, rather than issuer-filtered results. Its parsed detail issuer is **진코스텍**, not Alice or Melcon. The starting client already checked parsed names, but repeated the same irrelevant detail read for every company.

The reference fallback independently scanned calendar/sitemap after company lookup. The calendar has no static detail links. The production sitemap contains stock subpages (`similar-stocks`, `margin-amount`, `competition-rate`) and regeneration timestamps that put historical issuers ahead of recent ones; it also omits current JincoSTech. These facts explain both wasted work and incomplete discovery. KIND, Npay and NAVER external reads also ran serially.

Application URL sanitization did not affect httpx's INFO request records, which include the actual OpenDART credential query.

## FIX

- Replace per-company search with one shared calendar/current-stock-list/sitemap discovery. Accept only trusted official HTTPS stock root pages; exclude subpages. Prefer dated issuer IDs over sitemap regeneration dates when selecting the bounded newest-first fallback.
- Fetch at most 40 deduplicated details, in batches with at most four workers. Stop after a batch if every requested issuer has matched. Build an exact normalized issuer index, preserve requested order, and reject other issuers. Only official HTTPS redirects are followed; off-site redirects are rejected before fetching.
- Pass the parsed rows, including an empty result, to reference fallback in the same interactive or full refresh. No second external discovery occurs. Standalone reference refresh retains its discovery capability.
- Reconcile Metalogos by exact issuer name rather than redirecting a reference to a different issuer through a conflicting stock code.
- Overlap only the three independent KIND/Npay/NAVER reads. Apply observations in the existing KIND → Npay → NAVER → Metalogos → DART order. Retain existing file locks and sequential writes.
- Add monotonic `timings`: `base_refresh_ms`, `kind_discovery_ms`, `npay_discovery_ms`, `naver_discovery_ms`, `metalogos_discovery_ms`, `metalogos_reference_ms`, `dart_schedule_ms`, `targeted_dart_ms`, `total_ms`.
- Keep the interactive point-in-time score-recovery cap at four; no broad historical score recovery, proxy configuration changes, sleeps or new timeout workarounds.
- Redact credential query values at logging-record creation, including formatted HTTP URLs and exception chains. Preserve HTTP method, non-secret query parameters, status and normal log levels.

## METALOGOS REQUEST COUNTS BEFORE/AFTER

Live public-provider comparison used **Alice, JincoSTech and Melcon**, target date 2026-10-06, starting client loaded from the verified Git HEAD. It exercised company discovery plus the old reference fallback, versus the new shared discovery with row reuse. It did not invoke the production market refresh or write market data.

| Read | Before | After |
| --- | ---: | ---: |
| Company search URLs | 3 | 0 |
| Shared stock-list URL | 0 | 1 |
| Calendar | 1 | 1 |
| Sitemap | 1 | 1 |
| Detail reads | 43 | 40 |
| Total | **48** | **43** |
| JincoSTech detail `B202607142` | **3** | **1** |
| Additional reference discovery | Calendar + sitemap + 40 details | **0** |

A deterministic interactive-refresh regression with shared irrelevant cards makes **four requests total**: calendar, stock list, sitemap and one deduplicated detail. The fallback issues zero requests even when Alice remains unmatched. The old company loop grew with the number of candidates; the new discovery has a fixed detail cap and bounded concurrency.

## INTERACTIVE REFRESH TIMING BEFORE/AFTER

The supplied production baseline is HTTP **504**, with continued backend work; no numerical end-to-end duration was supplied. A local live **Metalogos discovery/reference-stage** comparison measured **27,716.833 ms → 12,616.932 ms**, approximately 54.5% less elapsed time. This includes genuine public HTTP reads, and is not an end-to-end production refresh measurement. KIND/Npay/NAVER now overlap; exact overall latency depends on those providers, KIS/base refresh and bounded DART recovery.

The new returned stage diagnostics make that remaining production latency measurable. Proxy-safe end-to-end completion must be verified after deployment; this local-only task does not establish that production result. Public-provider latency and missing provider pages remain external limitations.

## ALICE RESULT

Neither the old nor new bounded public discovery returned an exact **엘리스그룹** page. JincoSTech's 23,500 offer price and 61 attractiveness index were not attached to Alice. This proves no exact match was found by this discovery; it does not prove Metalogos has no Alice page anywhere.

The supplied production Alice baseline therefore remains the expected result in the no-new-canonical-data case: subscription 2026-10-07, band 70,400–90,500, null final offer price, null pricing discipline, calculating/null score, coverage 67, core missing pricing discipline, null Metalogos reference. A regression preserves Alice's missing price while accepting the exact JincoSTech reference. Production Alice was not refreshed from this workspace.

## SCORE SEMANTICS CHECK

Canonical priority remains **DART/KIND + NAVER/Npay > Metalogos160 > KIS fallback**. Existing priority and point-in-time tests remain in the suite. Metalogos reference values do not become feature inputs. Reference fallback copies only `sources.metalogos160` metadata. Pricing discipline remains derived by the existing feature path from canonical final offer price and band high. The parser rejects hoped-for prices and price ranges as final offer prices; no band-high substitution was introduced. The max-four recovery and cutoff selection code remain unchanged.

## UI CHECK

The visible reference now begins with the trusted **160 원문** link, followed by metrics: `160 원문 · 매력지수 61 · 수요예측기관 2,006 · 확약기관 90 · 유통가능 58.44%`. Removed `160 보조자료` and `Wealth Score 미반영`. The existing supplemental/not-used-in-score tooltip remains. A Node runtime regression checks actual node order, formatted metrics, tooltip, trusted URL rejection and repeated rendering.

## SECRET LOGGING CHECK

An actual httpx request against a mock transport retains its credential in the outgoing request, while emitted INFO records redact it. Tests also check exception-chain redaction and retain `corp_code=123` and `200 OK`. No synthetic credential value is present in the captured logs. Redaction is installed at application startup and when the DART client is imported independently; existing log configuration and levels remain intact.

## REGRESSION

New tests cover shared irrelevant search cards, exact normalized matching, duplicate detail suppression, fixed four-worker overlap, deterministic result order, sitemap subpages and old regeneration dates, off-site redirects, missing final prices, empty/non-empty result reuse, one discovery in an actual interactive pipeline, conflicting stock codes, deterministic merge/write threading, monotonic stage diagnostics, max-four DART invocation, secret logging and link-first frontend rendering. Existing source-priority, point-in-time, score, lock, route and frontend tests are retained.

## TESTS

- Relevant IPO/frontend/Chrome selection: **622 passed, 3 skipped, 48 subtests passed** (39.08 seconds). The subsequent full run also covers the final stock-code-conflict regression.
- Full pytest: **2,762 passed, 3 skipped, 669 subtests passed**, four existing collection/deprecation warnings (304.85 seconds).
- `node --check app/static/wealth-ipo-compact-view.js`: passed.
- `git diff --check`: passed.

Used the project Python environment, `PYTHONPATH` including the repository and tests, and pinned Windows temporary storage to LocalAppData. Full-suite output is outside the repository at `C:/Users/USER/AppData/Local/Temp/wealth-ipo-full-pytest.log`; benchmark output is `C:/Users/USER/AppData/Local/Temp/wealth-ipo-matalogos-benchmark.json`.

## FILES

- `app/logging_security.py`
- `app/main.py`
- `app/services/ipo/dart_client.py`
- `app/services/ipo/metalogos_client.py`
- `app/services/ipo/metalogos_reference_refresh.py`
- `app/services/ipo/refresh_adapter.py`
- `app/services/ipo/source_discovery.py`
- `app/static/wealth-ipo-compact-view.js`
- `tests/test_ipo_interactive_discovery.py`
- `tests/test_ipo_reference_ui_runtime.py`
- `tests/test_ipo_fast_refresh_and_krx_auth.py`
- `tests/test_ipo_future_compact_view_frontend.py`
- `docs/ipo-interactive-refresh-10-8k.md`

## COMMIT

One local commit after passing validation. The full SHA is supplied in the final response; no push or PR.

## WORKTREE STATUS

All task files are included in the one local commit. The final response confirms the post-commit clean-state check and full SHA. No branch switching, pull, rebase or reset.
