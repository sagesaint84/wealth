# Money Log Navigation — Batch 1

## Scope

This batch changes navigation and presentation only. It does not change financial calculations, persistence, API contracts, or data models.

## Modified Files

- `app/static/wealth-layout.js`: renamed primary navigation, created the consolidated Money Log page, moved the existing three financial panels into it, and retained legacy hash compatibility.
- `app/static/wealth.js`: extended the existing presentation-only income tab switcher to include the existing household-ledger panel.
- `app/static/wealth-layout.css`: kept all five mobile navigation destinations visible and made the secondary tab row horizontally scrollable when required.
- `tests/test_money_log_navigation.py`: added the Batch 1 navigation, compatibility, panel-preservation, and responsive contracts.
- `tests/test_section_navigation.py`, `tests/test_v1015_information_architecture.py`, `tests/test_v1021_ui_ux.py`: updated existing presentation contracts for the new labels and three-tab structure.

## Navigation Changes

The visible primary navigation is now:

1. 홈
2. 주식 투자
3. 종합 자산
4. 머니 로그
5. 설정

The former top-level `손익·배당` and `가계부` destinations are represented by one `머니 로그` destination. The home-page quick links use the same consolidated wording.

## Money Log Structure

Money Log has three directly accessible secondary tabs:

- 실현손익
- 배당·이자
- 가계부

The implementation moves the original `realizedPnlPanel`, `dividendPanel`, and `ledgerSectionPanel` DOM nodes. It does not clone or replace their records, filters, renderers, import controls, or add/edit/delete handlers.

## Compatibility

- `#income` opens Money Log on 실현손익.
- The existing `#ledger` deep link remains supported and opens Money Log on 가계부.
- `#pnl` and `#dividend` are accepted as direct Money Log tab links.
- Existing panel IDs and owner/family filter IDs remain unchanged.

## Responsive Behavior

Desktop keeps the three Money Log tabs on one row. On narrow screens, all tabs remain immediately available; the tab strip can scroll horizontally rather than hiding items in a menu. The mobile primary navigation retains five directly accessible destinations, including 설정.

## Verification

- Baseline: `Ran 656 tests in 15.103s` — `OK`.
- Focused navigation/layout tests: `Ran 24 tests in 0.124s` — `OK`.
- Full suite after the final change: `Ran 662 tests in 16.196s` — `OK`.
- `node --check app/static/wealth-layout.js` — PASS.
- `node --check app/static/wealth.js` — PASS.
- `.venv\\Scripts\\python.exe -m compileall -q app tests` — PASS.
- `git diff --check` — PASS (pre-existing line-ending warnings only).

## Explicitly Unchanged

- Portfolio valuation and asset-allocation calculations
- Realized P/L and foreign-FX semantics
- Dividend and interest calculations/imports
- Household-ledger transaction persistence and categorization
- Owner/family filtering semantics
- Broker integrations and import pipelines
- Database schema and migrations

## Remaining Concerns

The behavior is covered by the repository's established static frontend contracts and full regression suite. No separate interactive browser acceptance was requested or performed in this batch.
