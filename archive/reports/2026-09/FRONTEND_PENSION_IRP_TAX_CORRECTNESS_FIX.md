# Frontend Pension / IRP Tax Correctness Fix

## Root Cause

The frontend calculated cumulative pension-savings and IRP tax benefits one account at a time. Each pension-savings account could therefore consume its own KRW 6,000,000 ceiling and each IRP account its own KRW 9,000,000 ceiling before the displayed values were summed. That allowed the UI to show an eligible base equivalent to KRW 15,000,000, or more when several accounts existed, for one taxpayer and tax year.

## Backend Rule

The existing backend in `app/services/tax_benefit.py` is authoritative for this display calculation. For every owner/taxpayer and tax year it:

- aggregates deductible pension-savings contributions and caps them at KRW 6,000,000;
- gives deductible IRP contributions only the remainder of the combined KRW 9,000,000 ceiling;
- keeps different owners and different tax years independent;
- excludes accounts and yearly entries marked non-deductible from the ordinary contribution ceiling; and
- applies the existing income-dependent credit rate after allocating the eligible contribution.

## Frontend Previous Behavior

`calcAccountCumulativeTaxSaved()` applied an account-type ceiling independently to each account. The tax-account holdings view and the insurance/savings view then summed those independently capped results. The account list and individual-account cards also presented account-local amounts as if the statutory benefit were attributable to that account alone.

## Owner/Year Grouping

The frontend now builds contribution entries and groups them by normalized owner and explicit tax year. Missing owners retain the repository's legacy `"모두"` scope. Accounts without yearly history use their current `annual_deposit` as a current-year compatibility fallback; array position is never treated as a year.

## Pension 6M / Combined 9M Rule

Within each owner/year group, pension savings is allocated first up to KRW 6,000,000. IRP then receives only the remaining portion of the KRW 9,000,000 combined ceiling. Tax savings are calculated with the existing account/year income-level rate after allocation. Negative and non-finite contribution inputs have no eligible accounting effect.

## Multi-Account Semantics

Multiple pension-savings and IRP accounts compete for the same owner/year ceilings. Category totals retain meaningful attribution: pension savings receives up to KRW 6,000,000 and IRP receives the remainder of the combined ceiling. Different owners each receive independent ceilings.

## Individual Account Display

No arbitrary statutory allocation is presented as belonging to one account. When an individual pension or IRP account is selected, the displayed cumulative benefit is the combined amount for that account's owner and is explicitly labelled as owner-combined. The same clarification is used in account and savings cards.

## ISA Behavior

Standalone ISA display labels and rules are unchanged. The existing pension-account ISA transfer deduction treatment remains separate from the ordinary pension/IRP KRW 9,000,000 base and follows the backend behavior. As before, cumulative history with explicit yearly entries does not manufacture an ISA transfer amount for those historical years.

## Tests

Synthetic Node-backed frontend tests cover:

- all required single-owner ceiling combinations;
- multiple pension and multiple IRP accounts;
- independent owners and tax years;
- non-deductible accounts and contribution entries;
- the legacy missing-owner `"모두"` fallback;
- year-specific income rates;
- owner-combined individual-account display semantics;
- frontend/backend parity for current and yearly calculations;
- unchanged standalone ISA display behavior; and
- preservation of the pre-existing KB UI contract markers.

The canonical full suite, Python compilation, JavaScript syntax, and whitespace checks are recorded in the task report.

## Limitations

- `"모두"` remains a legacy fallback scope, not a newly inferred taxpayer identity.
- When an old account has no yearly contribution history, `annual_deposit` can only be treated as the current-year contribution; historical tax-year attribution cannot be reconstructed.
- If accounts for the same owner/year contain inconsistent income-level values, the frontend preserves the backend's existing per-entry rate and allocation-order semantics rather than inventing a household tax-rate rule.

## Unchanged Areas

This change does not modify backend tax rules, ISA product display, portfolio calculations, overdraft logic, foreign realized P/L, file-import idempotency, broker integrations, KB/CODEF work, dividends, database schemas, migrations, styling, or application versioning.
