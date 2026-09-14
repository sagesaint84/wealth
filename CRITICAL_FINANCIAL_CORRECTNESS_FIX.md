# Critical Financial Correctness Fix

Date: 2026-09-14  
Branch: `codex-refactor-realized-pnl-ipo-import`  
HEAD at start: `6de633e`  
Application version: `1.1.4`

## Overdraft Double Counting

### Root cause

The dashboard independently summed every negative bank balance into
`totalMinusBankDebt` and every explicit loan balance into `totalPureDebt`.
Consequently, a negative bank account explicitly linked to a positive
credit-line liability by `overdraft_bank_account_id` could reduce net worth
twice.

The existing data model establishes a strong relationship only when the loan is
`loan_type == "minus"`, names the bank through
`overdraft_bank_account_id`, and belongs to the same owner. Existing service
validation also treats the relationship as one-to-one.

### Previous behavior

All negative bank balances were counted as liabilities even when an explicitly
linked overdraft loan already represented the same economic debt.

### New invariant

One economic liability reduces net worth exactly once. A linked negative bank
balance is suppressed from the negative-bank component only when a same-owner,
explicitly linked overdraft loan has a positive balance. Unlinked negative bank
balances and independent loans remain liabilities. A zero loan balance cannot
hide a negative bank balance, and a positive linked bank balance remains an
asset.

### Fix

`calculateDashboardDebt` now derives the two existing debt components from the
explicit relationship. The final dashboard formula and visual output contract
remain unchanged.

### Tests

Nine targeted scenarios cover positive and unlinked-negative bank accounts,
independent loans, linked overdrafts, zero and positive linked bank states,
zero-balance linked loans, multiple overdrafts, owner isolation, and a direct
net-worth invariant. The 24 existing overdraft and 5 asset-calculation
regressions also pass.

## Pension / IRP Ceiling

### Root cause

Wealth calculated each account separately and then summed the account-level
results. A pension-savings account could therefore contribute KRW 6,000,000 and
an IRP account another KRW 9,000,000 for the same taxpayer, producing an
incorrect KRW 15,000,000 eligible contribution.

Legacy name fallback also checked the generic pension marker before the more
specific IRP marker, so a name containing both could be classified as pension
savings.

### Statutory rule

Under the current Korean Income Tax Act Article 59-3, pension-savings
contributions are eligible up to KRW 6,000,000 per resident per tax year, and
the combined eligible pension-savings and retirement-pension contribution is
limited to KRW 9,000,000. Source: [Korean Law Information Center, Income Tax Act Article 59-3](https://www.law.go.kr/lsLinkCommonInfo.do?lsJoLnkSeq=1032884269).

These are eligible-contribution ceilings, not tax-credit amounts. Wealth's
existing income-dependent credit rates were intentionally left unchanged.

### Owner/taxpayer scope

The existing service uses the account `owner` field as its taxpayer scope and
supports an explicit owner filter. The new allocator therefore applies both
ceilings independently for each owner and, for contribution history, each owner
and tax year. A household view may aggregate multiple independently capped
owners; it is not globally capped at KRW 9,000,000.

### Fix

- Normalize eligible account candidates without broadening the existing account
  taxonomy.
- Recognize the specific IRP legacy-name marker before the generic pension
  marker.
- Allocate pension savings first up to KRW 6,000,000 and then IRP against the
  remaining combined KRW 9,000,000 ceiling for each owner.
- Apply the same allocation to each owner's yearly contribution history.
- Preserve non-deductible pension/IRP exclusion, ISA additional-credit handling,
  existing rates, and account-level display details.

### Tests

Six targeted tests cover all seven required contribution combinations,
account-order independence, two-owner aggregation, explicit non-deductible
accounts, per-owner/per-year history, and legacy IRP classification.

## Unchanged Areas

- Stored portfolio and realized-P/L data; no data rewrite or migration.
- Database schema and persistence architecture.
- UI layout, controls, labels, and styling.
- Broker integrations and realized-P/L importers: Toss, KIS, NH, Kiwoom, and KB.
- Dividend and CODEF work.
- Portfolio allocation, planning, and strategy-bucket calculations.
- Foreign realized-P/L dashboard behavior.
- Owner-filter findings outside these two calculations.
- CSV/XLSX import idempotency.
- Existing tax-credit rates and unrelated tax rules.

## Verification

- Baseline full suite: 599 run, 599 passed, 0 skipped, 0 failed, 0 errors.
- Overdraft targeted tests: 9 run, 9 passed, 0 skipped, 0 failed, 0 errors.
- Pension/IRP targeted tests: 6 run, 6 passed, 0 skipped, 0 failed, 0 errors.
- Existing overdraft regression: 24 run, 24 passed.
- Existing asset-calculation regression: 5 run, 5 passed.
- `compileall`: PASS.
- `git diff --check`: PASS.
- Post-change full suite: 614 run, 614 passed, 0 skipped, 0 failed, 0 errors.
