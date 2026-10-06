# Alice IPO discovery and provenance follow-up

## ROOT CAUSE

Verified branch `hotfix10-8k-ipo-refresh-matalogos-timeout`, starting HEAD `05a51feb0925f066acdac7bd109cebf197d7c85e`, and a clean working tree before editing. No branch switching, pull, rebase or reset.

The previous implementation capped a prefix ordered by Metalogos ID age. That is not IPO schedule age: Alice's October 2026 subscription belongs to `B202605261`. Neither an increased historical prefix nor per-issuer `?query=` scraping is required.

Public frontend inspection established the actual calendar contract: the frontend's HTTP client uses `https://api.metalogos.site`, its `IPO_SCHEDULE` route is `/schedule/external`, and it requests `startDate`/`endDate`. The response is `data.ipoStocks`; each row supplies `name` and the detail identifier in `code`. One September–November request returned 34 current-window rows, including Alice.

The previous parser also omitted field-level final-price provenance. Derived-feature date selection compared mixed ISO and compact DART encodings lexically, which could hide a later final-price observation behind the compact band date.

## DISCOVERY FIX

One unauthenticated public [schedule-index request](https://api.metalogos.site/schedule/external?startDate=2026-09-01&endDate=2026-11-30) covers the existing three-month candidate window. Build an exact normalized issuer-name index from every returned row, irrespective of detail ID age. Intersect this index with Wealth candidates, construct trusted official stock-detail URLs, deduplicate those URLs, and fetch only the matched details with at most four workers.

The API host is separately allowed for discovery; it is not added to the detail/UI link allowlist. Detail pages remain restricted to HTTPS `metalogos.ai`/`www.metalogos.ai` stock roots, including redirect checks. Malformed contracts, path-like identifiers and ambiguous name mappings fail closed. Structured index prices/scores are not promoted: factual canonical/reference values come from exact parsed detail pages.

Interactive discovery and reference fallback share the same parsed rows, including an empty result. Standalone reference refresh also resolves its candidate names through the index. No current interactive lookup uses calendar HTML, stock-list HTML or sitemap scanning. Candidate detail work is bounded by matched current issuers and four concurrent reads, rather than an arbitrary historical prefix.

## ALICE MATCH RESULT

Live public lookup resolved **엘리스그룹 / 0158S0 → [B202605261](https://metalogos.ai/160ipo/stock/B202605261)**. The parsed page supplies subscription 2026-10-07–08, final offer price **90,500**, attractiveness **79**, demand participants **2,367**, lockup participants **355**, and tradable share reference **20.81%**.

The realistic fixture preserves this detail contract and the actual calendar row. Its regression inserts 60 newer unrelated IDs ahead of Alice and still resolves Alice with one index read plus one detail read. The reference attaches, and the missing canonical final price fills with explicit provenance when source priority permits.

Production market data was not written by the live probe. In the acceptance fixture, the provided before-state coverage 67 and missing pricing discipline become coverage **75**, no core missing fields, pricing discipline **100**, and a recalculated **Wealth score 55.4** for that fixture's Wealth features. This is not a measured production Wealth score, and it is not the Metalogos attractiveness 79.

## METALOGOS REQUEST COUNTS

| Case | Index reads | Matched detail reads | Total | Extra reference discovery |
| --- | ---: | ---: | ---: | ---: |
| Live Alice only | 1 | 1 | **2** | 0 |
| Live Alice + JincoSTech + Melcon | 1 | 3 | **4** | 0 |
| Synthetic Alice behind 60 newer IDs + one absent issuer | 1 | 1 | **2** | 0 |
| Synthetic shared unrelated JincoSTech card, unmatched Alice | 1 | 1 | **2** | 0 |
| Synthetic eight matched candidates | 1 | 8 | **9** | 0 |

All these index-based cases use zero company-search, calendar-HTML, stock-list-HTML and sitemap requests. Eight-candidate concurrency regression reaches exactly four active detail requests and preserves deterministic result order. The same-refresh interactive regression proves no second external discovery even when a candidate remains unmatched.

The prior live three-company implementation used 43 requests (3 shared HTML/sitemap reads and 40 details), found only JincoSTech, and missed Alice. The new live three-company lookup uses **4 requests** and finds all three.

## INTERACTIVE TIMING

Live indexed Metalogos-stage timings on 2026-10-06:

- Alice only: **1,746.035 ms**, 2 requests.
- Alice + JincoSTech + Melcon: **2,581.433 ms**, 4 requests.
- Prior three-company capped-prefix stage: **12,616.932 ms**, 43 requests; original sequential stage was 27,716.833 ms / 48 requests.

These are actual local public HTTP stage measurements, not a production POST refresh duration. End-to-end proxy-safe latency still needs deployment verification. Existing monotonic returned timings remain: base refresh, KIND/Npay/NAVER discovery, Metalogos discovery/reference, DART schedule, targeted DART and total. No proxy timeout increases, new arbitrary timeouts, sleeps, Service Worker changes or broad interactive DART recovery.

## IDENTITY SAFETY

Attachment requires an exact normalized company name and, whenever both sides have a stock code, an exact normalized stock code. This check protects the source merge boundary and reference fallback. Known conflicting same-name stock codes reject the entire canonical/reference attachment. Details must match their own index entry; an unrelated detail card cannot attach simply because another candidate appears in the response. Existing conflicts when only one side knows a stock code retain the prior identity handling.

## POINT-IN-TIME PROVENANCE

Canonical parsed final prices carry `sources.final_offer_price`: source `metalogos_160_public_page`, detail URL, value, `source_date`, full KST `observed_at`, and confidence. The date records actual observation, not the ID's date, subscription date or requested refresh date.

A final price with missing/unusable provenance is not promoted. Higher-priority retained canonical prices keep their existing field provenance. Reobserving the same Metalogos page/value preserves its first observation; a changed price receives its new observation date and cannot be backdated.

Derived features normalize compact DART and ISO input dates before selecting the latest date. An observed final price on/before Alice's 2026-10-06 cutoff can validate pricing discipline, provided band provenance and other scoring rules allow it. A first observation on 2026-10-07 leaves pricing discipline unobserved, coverage 67 and score calculating/null for the acceptance fixture. Cached `ok` derived features cannot bypass the canonical Metalogos price date. Regressions cover before/on/after cutoff, mixed date encodings and cached derived data.

## SCORE SEMANTICS

Reference-only attractiveness, demand/lockup participant counts and tradable-share references never populate Wealth features. Source merge explicitly excludes incoming Metalogos features/score fields. Canonical final price comes only from the parsed price label and carries provenance; hoped-for prices, ranges and band high never substitute for final price.

Pricing discipline remains the Wealth formula based on canonical final price and band high. The market snapshot's scores are recalculated after discovery even if DART is unavailable. Changing attractiveness 79 to 1 leaves the calculated Wealth score unchanged in the acceptance test.

Canonical source priority, deterministic merge/write order, provider read concurrency, file locking and interactive DART recovery max four remain intact.

## UI EXACT TEXT

The Alice reference renders:

[160 원문](https://metalogos.ai/160ipo/stock/B202605261) 매력지수 79 수요예측기관 2,367 확약기관 355 유통가능 20.81%

The link is first, with ordinary single spaces between fields and no visible middle-dot separators. Both removed labels remain absent. Values are dynamic. The existing supplemental/not-used-in-Wealth-score tooltip and trusted URL validation remain. The Node runtime regression asserts the concatenated visible text exactly, link node order, formatting, invalid URL rejection and repeated rendering.

## SECRET LOGGING

Previous credential-query redaction is unchanged. The relevant/full regressions retain tests asserting no credential values appear in actual httpx INFO records or exception chains, while useful status and non-secret query parameters remain. The public schedule request uses no credentials.

## TESTS

- Targeted IPO/backend/frontend/source-priority/point-in-time selection: **580 passed**, 20 subtests, one existing deprecation warning (35.13 seconds).
- Focused acceptance/provenance/fallback/score/UI recheck: **35 passed** (1.47 seconds).
- Full pytest: **2,774 passed, 3 skipped, 669 subtests passed**, four existing collection/deprecation warnings (295.40 seconds).
- `node --check app/static/wealth-ipo-compact-view.js`: passed.
- `git diff --check`: passed.

The first full run had one existing dividend-startup Chrome timeout: the unified chart script was absent from the loaded-script list, with no JavaScript errors. That test passed in isolation (2.68 seconds), and the complete rerun passed. No startup production code, timeout or browser test was altered for this follow-up.

Used project Python with repository/tests on `PYTHONPATH` and temporary storage pinned to LocalAppData. Validation logs and live benchmark data remain outside the repository: `C:/Users/USER/AppData/Local/Temp/wealth-alice-full-pytest-recheck.log`, `wealth-alice-ipo-pytest.log`, `wealth-alice-chrome-recheck.log`, and `wealth-alice-index-benchmark.json`.

## FILES

- `app/services/ipo/metalogos_client.py`
- `app/services/ipo/metalogos_reference_refresh.py`
- `app/services/ipo/source_discovery.py`
- `app/services/ipo/features.py`
- `app/services/ipo/score.py`
- `app/static/wealth-ipo-compact-view.js`
- `tests/fixtures/metalogos_alice_schedule.json`
- `tests/fixtures/metalogos_alice_stock.html`
- `tests/test_ipo_alice_metalogos_acceptance.py`
- `tests/test_ipo_interactive_discovery.py`
- `tests/test_ipo_reference_ui_runtime.py`
- `docs/ipo-alice-index-followup-10-8k.md`

## COMMIT

One additional local commit after passing validation. Its full SHA is supplied in the final response. No push or PR.

## WORKTREE STATUS

All task files are included in the one additional local commit. The final response confirms the post-commit clean-state check and full SHA. Branch remains `hotfix10-8k-ipo-refresh-matalogos-timeout`.
