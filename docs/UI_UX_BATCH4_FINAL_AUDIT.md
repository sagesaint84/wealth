# UI/UX Batch 4 Final Audit

## Independent Findings

The prior CSS-regression report is confirmed. The current DOM renders Net Worth History as compact record cards, but the stylesheet had retained legacy table rules while losing the card, scrolling, and chart-overflow rules introduced for Batch 2. The Strategy Bucket comparison retained only its basic grid and donut dimensions; its donut mask, legend, empty-state, preset, validation, and section-card styles were absent. The debt secondary row also colored only the amount, not its label.

The prior tax-logic report is confirmed. Batch 4 introduced `calcSingleAccountCumulativeTaxSaved(account)`, which applied the pension-savings and IRP limits independently to every account. It did not participate in the existing owner/year allocation performed by `calculateOwnerYearPensionTaxBenefits(accounts)`.

Read-only repository evidence cannot prove the exact shell command that removed the uncommitted CSS, but the resulting stylesheet/DOM mismatch and the missing prior-batch selectors are independently reproducible from the current tree.

## CSS Regression Root Cause

The current stylesheet had a partial prior-batch state: the Batch 2/3 DOM and JavaScript were present while their detailed presentation selectors were absent. This is consistent with restoration of an older tracked stylesheet over uncommitted Batch 2/3 CSS. Batch 4 header, tab, adaptive chart-width, preset-name, and Quick Access removal work remained present and was preserved.

## CSS Rules Restored

- Net Worth History plot horizontal overflow, compact details container, record list scrolling, record card/header/date/value/note/action styling, and the `980px` stacked-layout list height.
- Strategy Bucket comparison section cards, donut center mask and typography, legends, empty states, preset controls, active states, and validation status.
- Debt label and amount now share the restrained amber treatment.
- Obsolete Net Worth History table rules were removed because the current DOM renders compact cards rather than a seven-column table.

## Tax-Calculation Root Cause

The removed account-only helper independently allowed up to KRW 6,000,000 for each pension-savings account and KRW 9,000,000 for each IRP account. For one low-income-rate owner with KRW 6,000,000 pension savings and KRW 9,000,000 IRP, that path displayed KRW 2,475,000 in aggregate account savings. The authoritative owner-level calculation allocates only KRW 6,000,000 to pension savings and KRW 3,000,000 to IRP, producing KRW 1,485,000.

## Old Incorrect Tax Path

`renderAccounts()` called `calcSingleAccountCumulativeTaxSaved(account)`. That helper applied a separate account-type ceiling to each account and therefore could not reconcile multiple accounts, shared owner limits, or owner/year grouping.

## Authoritative Tax Path

`app/services/tax_benefit.py::_allocate_pension_irp_eligible()` is the authoritative domain allocation. Per taxpayer scope, it processes pension savings before IRP, preserves input order within each category, applies the KRW 6,000,000 pension-savings ceiling, and then applies the shared KRW 9,000,000 combined ceiling. The existing frontend owner/year calculation already mirrored that allocation for aggregate totals.

## Account Allocation Approach

The frontend aggregate allocation now records each allocated contribution and its tax saving in `byAccount` while it performs the existing owner/year allocation. Account cards read this allocated value. This is account-level allocation of existing authoritative owner-level tax benefit, not a new tax formula.

The invariant is:

`sum(account displayed tax savings for an owner/year) == authoritative owner/year tax saving`

Non-deductible pension/IRP contributions receive no ordinary eligible contribution and display the existing non-deductible indicator without a misleading tax-saving amount. Existing ISA-transfer handling remains unchanged and is attributed to its source account in the allocation metadata.

## Test Audit and Tests Added

The original Batch 4 per-account test covered only a below-limit pension/IRP example and asserted the independently calculated values. It was strengthened to exceed the combined ceiling and now verifies exact reconciliation to the owner total and absence of the stale helper.

Behavioral coverage now includes pension-only, IRP-only, below/above combined limits, multiple pension accounts, multiple IRP accounts, deductible plus non-deductible accounts, different owners, multiple years, income-rate variation, ISA parity, account allocation order, and Python/JavaScript backend parity. Batch 2 and Batch 3 tests now also require the detailed CSS subsystems rather than only their outer grids.

## Validation Results

- Pre-repair full Python baseline: `Ran 686 tests in 14.734s` — `OK`.
- Focused UI/tax/layout/navigation suite after repair: `Ran 66 tests in 2.882s` — `OK`.
- Final full Python suite: `Ran 687 tests in 14.498s` — `OK`.
- Node planning-model suite: 14 passed, 0 failed, 0 skipped.
- `node --check app/static/wealth.js`: PASS.
- `python -m compileall -q app tests`: PASS.
- `git diff --check`: PASS (line-ending warnings only; no whitespace errors).

## Preserved Batch 4 Behavior

- Strategy Bucket presets remain: 코어, 성장, 배당, 섹터, 테마, 전술, 방어, 현금.
- Home Quick Access remains removed.
- Net Worth History keeps adaptive width: sparse data does not force a scrollbar, while dense data may scroll.
- Standardized major-page headers and secondary navigation icons/order remain unchanged.

## Unchanged Areas

No portfolio, securities valuation, expected-return, FX, realized P/L, dividend, broker, Strategy Bucket persistence/scope/denominator, trading, database, migration, or API contract logic was changed.
