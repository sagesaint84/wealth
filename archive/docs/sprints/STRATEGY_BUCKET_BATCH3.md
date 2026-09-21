# Strategy Bucket UI/UX Batch 3

## Audit

### Files inspected

- `app/services/planning.py`
- `app/main.py` planning routes
- `app/static/wealth-planning-model.js`
- `app/static/wealth-planning.js`
- `app/static/wealth-layout.css`
- `app/static/wealth.js` portfolio-view event projection
- `tests/planning-model.test.cjs`
- `tests/test_planning_regression.py`
- existing Batch 1 and Batch 2 contract tests

### Current architecture and persistence

Strategy Bucket data already persists per authenticated Wealth user under `portfolio.settings.wealth_planning`. Each bucket has `id`, `name`, `purpose`, and `target`; the same planning object stores account defaults and holding-specific overrides. The existing `GET /api/planning` and `POST /api/planning/buckets` routes read and atomically update this data with revision conflict protection.

The backend already validates individual targets from 0% through 100%, rejects duplicate IDs/names, and rejects a combined target above 100%. No parallel persistence mechanism was introduced.

Target allocation scope is **GLOBAL within the authenticated user's planning settings**. It is not separately keyed by owner or account. Current allocation scope follows the existing owner-filtered portfolio view.

### Existing valuation denominator and cash treatment

The Current Allocation denominator remains the existing `bucketTotals()` result:

- market value of holdings belonging to the selected view's accounts;
- KRW cash for those accounts;
- USD cash converted with the view's existing USD/KRW rate;
- unassigned/unknown account or holding mappings accumulated under the existing empty bucket key.

The existing fail-closed behavior for missing USD FX is unchanged. Holding overrides still take precedence over account defaults, and the same security may remain assigned differently in different accounts.

`미분류` is current, real portfolio value without an effective bucket assignment. `미배정` is only the unused part of the persisted target percentage. They remain distinct.

## Implementation

### Files modified

- `app/static/wealth-planning-model.js`
- `app/static/wealth-planning.js`
- `app/static/wealth-layout.css`
- `tests/planning-model.test.cjs`
- `tests/test_planning_regression.py`
- `tests/test_strategy_bucket_batch3.py`
- `docs/STRATEGY_BUCKET_BATCH3.md`

`wealth-planning.js` and `wealth-layout.css` already contained uncommitted Batch 2 and Batch 1 work respectively. Those hunks were preserved.

### Preset and custom bucket UX

The compact existing editor now offers these optional presets: 코어, 성장, 배당·인컴, 섹터, 테마, 전술, 방어·안전자산, 현금·대기자금. A preset adds an ordinary unsaved bucket draft through the same existing form and API contract. Existing names are shown with a selected state; selecting an identical name reports that the bucket already exists. Existing and custom buckets are neither renamed nor migrated. Custom creation remains available through `+ 사용자 정의 버킷`.

### Target allocation and validation

The existing target input remains editable per active bucket with 0.1% steps and a 0–100% range. Draft totals are shown immediately:

- below 100%: the explicit `미배정` remainder is shown;
- exactly 100%: valid complete state;
- above 100% or invalid individual input: a numerical text error is shown and save is blocked;
- values are never normalized or rescaled.

Only persisted targets drive the summary donut. When every target is zero, the UI shows a neutral not-configured state rather than fabricating an allocation.

### Target and Current donuts

The summary contains comparable Target and Current donut panels. Both use bucket order from the persisted planning state and a stable ID-based muted color mapping. Every segment also appears in a textual legend, so color is not the sole carrier of meaning.

Target always represents 100% when configured by adding `미배정` for the exact remainder. Current uses the unchanged `bucketTotals()` denominator and includes `미분류`; all-current-unclassified therefore renders as `미분류 100%`. The Current legend also shows monetary value.

The pre-existing compact bucket cards remain below the comparison to preserve purpose, amount, current percentage, target percentage, and difference information. No rebalancing, recommended trade, or order action was added.

### Responsive behavior

Target and Current appear side by side on desktop. At 760 px and below they stack vertically, with smaller donuts and readable legends. Preset buttons wrap and the existing editor inputs remain touch-accessible.

## Safety

- Financial valuation logic changed: **NO**
- Financial calculation logic changed: **NO**
- Database schema changed: **NO**
- Migration added: **NO**
- Trading logic changed: **NO**
- Existing assignments changed automatically: **NO**
- Batch 1 navigation regressed: **NO**
- Batch 2 Home dashboard regressed: **NO**

## Tests

- Pre-change full baseline: `Ran 669 tests in 13.452s` — `OK`.
- Focused Python backend planning: `Ran 15 tests in 0.749s` — `OK`.
- Focused Python Batch 3 plus Batch 1/2 regression: `Ran 21 tests in 0.021s` — `OK`.
- Focused Node planning model: 14 tests, 14 passed, 0 failed.
- Post-change full suite: `Ran 678 tests in 14.765s` — `OK`.
- JavaScript syntax: PASS.
- Python compileall: PASS.
- `git diff --check`: PASS.

Coverage includes persisted boundary and remainder target values, target remainder, current denominator preservation, cash/FX behavior, `미분류`, owner-filtered Current allocation, global targets, stable color mapping contract, preset availability, duplicate-name handling, responsive layout, and Batch 1/2 presentation contracts.
