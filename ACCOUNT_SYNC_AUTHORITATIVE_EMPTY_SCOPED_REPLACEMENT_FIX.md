# Broker Holdings Authoritative-Empty and Scoped Replacement Safety Fix

## Previous Failure Mode

Broker adapters returned plain holding lists. Missing containers, malformed rows,
and rows discarded during normalization could therefore become indistinguishable
from a provider-confirmed empty portfolio. The sync routes then used source-wide
replacement, so an ambiguous empty result could delete valid holdings owned by
the same provider source.

The implementation baseline for this milestone was 719 discovered and executed
tests with no skips, failures, or errors. The increase from the earlier 706-test
checkpoint is the pre-existing, untracked `tests/test_ui_ux_batch6.py` file (13
UI regression tests); it is unrelated to this fix and was preserved.

## Canonical Safety Invariant

Existing holdings are removable only when all of the following are true:

1. the adapter returned an authoritative holdings result;
2. every returned row passed strict identifier and finite-quantity validation;
3. every provider account scope resolves unambiguously to one Wealth account;
4. the market scope is explicit; and
5. every normalized row belongs to the exact provider/account/market scope being
   replaced.

Missing, null, malformed, status-only, partial, or account-ambiguous responses
cannot authorize a portfolio mutation.

## Provider State Model

`BrokerHoldingsResult` keeps rows separate from deletion authority. Its state
model includes `CONFIRMED_NONEMPTY`, `AUTHORITATIVE_EMPTY`, `PAYLOAD_MISSING`,
`STATUS_ONLY`, `MALFORMED`, `ACCOUNT_SCOPE_UNVERIFIED`,
`MARKET_SCOPE_PARTIAL`, `PROVIDER_ERROR`, `AUTH_ERROR`, and `UNKNOWN_EMPTY`.

Only `CONFIRMED_NONEMPTY` and `AUTHORITATIVE_EMPTY`, accompanied by at least one
explicit provider scope, are authoritative. A legacy/plain list is deliberately
non-authoritative at the persistence boundary.

## Broker-Specific Behavior

### KB Securities

- The existing status-only/missing-body fail-closed behavior remains intact.
- Domestic and overseas containers must both be structurally valid.
- Required symbol and finite quantity fields are validated before zero-quantity
  filtering.
- Unprocessed continuation metadata fails closed.
- A successful result carries separate domestic and overseas scopes for the
  verified `kb_primary` account identity.

### Toss Securities

- An empty account list is scope-unverified rather than zero holdings.
- Every account requires a valid `accountSeq`; every holding requires symbol,
  finite quantity, market country, and currency.
- Unprocessed account or holdings pagination fails closed.
- Successful traversal carries an all-markets scope for every traversed account.
- Existing non-empty synchronization behavior is preserved.

### NH Investment / Namuh

- `Output_0` and `Output_1` are explicitly validated; missing, null, or wrong-type
  `Output_1` is not converted to an empty list.
- Repeated continuation keys fail closed instead of returning partial pages.
- Required symbols and provider quantity fields are validated before filtering.
- Domestic and each completed overseas market request carry distinct scopes.

### Korea Investment Securities (KIS)

- Domestic and overseas required symbol/quantity fields are strict and finite.
- The existing all-or-nothing domestic plus overseas request sequence remains.
- The authoritative result carries distinct domestic and US scopes for the
  configured account.

### Kiwoom Securities

- Domestic symbol and remaining quantity are strict and finite.
- The authoritative scope is limited to the configured account's domestic/KRW
  holdings.
- Overseas/non-KRW holdings remain outside the replacement scope.

## Replacement Scope

`replace_holdings_in_scopes` replaces only rows matching all of:

- provider provenance (`source`);
- resolved Wealth account ID; and
- verified market scope (`DOMESTIC`, `OVERSEAS`, a specific market, or an
  explicitly complete `ALL` scope).

Manual/file-imported and other-provider holdings are never selected by this
replacement. Another account at the same broker and another market in the same
account are preserved. Account matching uses exact provider identity first;
masked-suffix or display-name fallbacks are accepted only when unique. Ambiguous
matches fail closed.

## Cash Independence

Holdings and cash validity are represented separately. For an authoritative
holdings result, existing broker-specific cash behavior is retained. If holdings
are invalid or their account scope is unverified, the route returns before any
portfolio write: holdings and cash are preserved, and the response explicitly
reports `cash_valid` separately from `cash_updated=false`. This conservative
policy avoids a partial write whose account attribution cannot be proven.

## Messaging Semantics

- `SUCCESS` means an authoritative non-empty holdings synchronization completed.
- `CONFIRMED_EMPTY` means the provider authoritatively confirmed no holdings in
  the exact resolved scope.
- `SCOPE_UNVERIFIED` reports that the provider result could not safely authorize
  replacement and that existing holdings were preserved.
- Existing provider exceptions continue through the established safe error
  contract rather than being described as a successful zero result.
- `/api/sync/all` recognizes `CONFIRMED_EMPTY` as a completed authoritative sync.

## Test Matrix

Synthetic tests cover all five provider sources and verify:

- scoped authoritative non-empty replacement and repeated-sync idempotency;
- authoritative empty removal only for the exact account/market;
- preservation of other accounts, overseas scopes, manual rows, and other
  provider rows;
- rejection before mutation when a normalized row falls outside its scope;
- missing/null/status-only/malformed/account-unverified results preserving data;
- missing identifiers and malformed/non-finite quantities failing closed;
- incomplete or repeated pagination failing closed;
- ambiguous multi-account matching producing no write;
- holdings-invalid plus cash-valid metadata not being reported as a full success;
- one broker failure leaving other broker routes independent.

Focused result: 36 tests executed, 0 skipped, 0 failures, 0 errors.
The unchanged NH realized-P/L pagination contract was additionally rechecked:
10 tests executed, 0 skipped, 0 failures, 0 errors. Full regression result:
733 tests discovered and executed, 0 skipped, 0 failures, 0 errors.

## Limitations

- The change intentionally prefers preservation over deletion when legacy account
  metadata cannot establish a unique scope. Such stale holdings may require a
  later explicit account-reconciliation workflow; they are not silently removed.
- Cash is conservatively preserved when holdings/account authority is invalid,
  even if an adapter has already established that a cash payload was structurally
  valid. A future narrowly scoped cash-only transaction could relax this without
  weakening holdings safety.
- No live provider call was used; provider compatibility is covered by existing
  adapter contracts and deterministic synthetic responses.

## Unchanged Areas

- No portfolio valuation or accounting formula changed.
- No realized P/L, dividend, FX, tax, importer, trading, or order behavior changed.
- No database schema or migration was added.
- No UI or frontend behavior changed.
- No real financial data was written.
- Existing KB/OpenAPI, dividend, CODEF, audit, and UI working-tree changes were
  preserved.
