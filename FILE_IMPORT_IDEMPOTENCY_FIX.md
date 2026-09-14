# File Import Idempotency Fix

## Problem

The existing realized P/L, dividend, and household-ledger file importers assigned a new UUID to every parsed row and appended every row on every invocation. File name, row content, and existing stored events were not used for duplicate detection. Importing an identical, renamed, reordered, or partially overlapping export could therefore duplicate financial totals.

## Existing Import Semantics

- Realized P/L imports normalize CSV/XLSX rows into stored realized-P/L records and derive KRW display values without using a persistent file-event identity.
- Dividend imports normalize CSV/XLSX rows into actual-dividend records and similarly used only generated record IDs.
- Ledger imports normalize CSV/XLSX rows into income, expense, or transfer transactions; writes already use the ledger's atomic temporary-file replacement, but rows had no repeat-import identity.
- Broker API realized-P/L pipelines use separate signed provider fingerprints. They are intentionally excluded from this file-import reconciliation.

## Duplicate Identity by Domain

All identities use versioned, stable JSON serialization, Unicode NFKC/text normalization, finite decimal normalization, and SHA-256. File name, upload time, generated UUID, and spreadsheet row number are excluded.

### Realized P/L

The identity includes owner, broker/account context, trade date, security code/name, currency, provider P/L, FX P/L adjustment, IPO classification, memo, and optional quantity, purchase amount, sale amount, fee, tax, and source reference. Missing optional values remain distinct from numeric zero.

### Dividend

The identity includes owner, broker/account context, payment date, security code/name, currency, received amount, memo, and optional gross amount, tax, fee, and source reference. This distinguishes equal amounts paid by different securities or on different dates.

### Ledger

The identity includes date, direction/type, amount, category, owner, payment method, merchant, memo, and optional transaction time, post-transaction balance, source institution, counterparty, and source reference. This avoids weak date-plus-amount matching and preserves direction and available transaction detail.

## Fix Applied

Each importer now compares the incoming canonical identity multiset with the existing stored multiset. It inserts only occurrences beyond the count already persisted. The stored fingerprint and occurrence ordinal make the behavior stable across restart, rename, row reordering, overlap, and incremental exports. Legacy records without the new metadata are compared from their stored canonical fields when they belong to the compatible file-import shape.

Dividend and ledger file imports now fail closed when their existing storage is malformed, instead of treating unreadable storage as empty during an import.

## False-Positive Protection

- Identity is domain-specific rather than date-plus-amount.
- Available quantity, amounts, deductions, time, balance, institution, counterparty, and reference fields strengthen identity.
- Provider API realized-P/L records with a provider `source` remain outside file-import deduplication.
- Identical rows within one file are retained as separate occurrence ordinals. Re-importing the same multiset does not add them again; a later file with a larger indistinguishable multiset adds only the increased cardinality.

When a source omits every distinguishing field for genuinely identical events, no deterministic system can map a subset of those events across independent exports perfectly. The multiset policy preserves the maximum observed cardinality and is safer than either collapsing the first file or appending every repeat.

## Existing Duplicate Candidates

No real user storage was scanned and no existing records were changed, merged, or deleted. Historical compatible records participate in future import comparisons where their stored fields provide the required identity. Existing duplicate cleanup remains a separate, user-authorized task.

## Test Results

- Baseline full suite: 614 passed, 0 failed, 0 errors.
- Realized P/L focused: 3 passed, 0 failed, 0 errors.
- Dividend focused: 4 passed, 0 failed, 0 errors.
- Ledger focused: 4 passed, 0 failed, 0 errors.
- Post-change full suite: 625 passed, 0 failed, 0 errors.

Synthetic tests cover CSV/XLSX equivalence, renamed and reordered files, overlap, one-row growth, negative and zero P/L, missing optional values, foreign-currency dividends, same-day similar events, direction/time/balance/institution distinctions, repeated legitimate identical rows, and malformed-storage fail-closed behavior.

## Known Limitations

- Legacy records do not contain source-file reference metadata that was not previously persisted; matching uses only their stored normalized fields.
- Truly identical events without a stable source reference or distinguishing time/balance fields are represented as a multiset, not individually traceable events.
- Cross-source broker-API-versus-file reconciliation is intentionally not performed.
- The existing supported file parsing and public endpoint response shapes are unchanged; a duplicate-only import reports zero inserted records through the existing count.

## Unchanged Areas

No database schema or migration was added. Broker feed/signing pipelines, portfolio calculations, tax benefits, overdraft logic, UI/UX, foreign realized-P/L behavior, dividend automation, and KB runtime behavior were not changed.
