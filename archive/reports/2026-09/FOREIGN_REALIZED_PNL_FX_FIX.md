# Foreign Realized P/L FX Correctness Fix

## Root Cause

Broker realized-P/L records can intentionally contain a provider-native `pnl`
while `pnl_krw`, `fx_rate`, and `fx_pnl_krw` are unavailable. The summary used
`pnl_krw` both for monetary totals and win/loss classification, so otherwise
valid foreign trades disappeared from the statistics. Historical recalculation
also assumed nullable FX fields were float-convertible and used the legacy FX
lookup, whose fallback behavior is unsuitable for persisted accounting values.

## NH Contract Trace

The NH overseas path first reads `orr_dt` from `periodPnl`, uses it as the
`periodPnlDetail` request date, and injects that request value as
`_wealth_date_context`. `nh_feed.py` then projects the context as the canonical
date. Publicly accessible official NH material did not establish that this
context is the realized-sale event date required for historical conversion.
It is therefore classified as a query-date context, not as a verified sell
date. NH overseas records remain unconverted.

## Kiwoom Contract

The Kiwoom `ust21530` projection already uses provider `sell_dt` as the
canonical date and `pl_amt` as provider-authoritative USD realized P/L.
`cmsn_tax` remains an informational combined expense and is not subtracted
again. The provider canonical projection, canonical hash, occurrence ordinal,
selection signature, and source fingerprint are unchanged.

## Provider vs Derived P/L Semantics

The native `pnl` is never changed by this fix. A Kiwoom `ust21530` row may gain
a KRW equivalent only when a strict historical observation exists on or before
its sell date. The persisted `source_meta.pnl_krw_semantics` distinguishes
`provider`, `historical_fx_derived`, and `unavailable`. Derived records also
carry the observation date and the cache lookup source. These persistence-only
metadata fields do not participate in provider identity.

## Historical FX Safety

The new strict accounting lookup accepts validated `YYYY-MM-DD` and `YYYYMMDD`
dates, uses an exact cached observation or the latest prior observation, and
returns unavailable when neither exists. It does not perform network I/O, use
the legacy 1385 fallback, or substitute an observation after the target date.
The legacy lookup remains unchanged for unrelated callers.

## Summary Behavior

KRW totals include only records with a valid `pnl_krw`. Win/loss counts use the
provider-native `pnl` sign when present, with a backward-compatible KRW fallback
for older rows that lack native P/L. Top-level, monthly, and yearly results now
expose converted/unconverted counts and `summary_complete`, so an incomplete
KRW total is explicit rather than silently authoritative.

## Frontend Integration

The dashboard and realized-P/L views prefer the backend canonical KRW total and
win-rate metadata. Missing `pnl_krw` values remain unavailable in row display
and are excluded from owner-filtered fallback totals; they are never coerced to
financial zero. Incomplete summaries display a concise unconverted-row count.
Raw records remain available for item rendering, and the existing account and
holding owner filtering is unchanged.

## Fixes Applied

- Added a strict cached historical-FX lookup for accounting conversion.
- Added safe Kiwoom US conversion at persistence and recalculation boundaries.
- Kept NH and providers with authoritative/unknown KRW semantics untouched.
- Made recalculation and record update tolerate nullable FX fields.
- Preserved missing `fx_pnl_krw` rather than manufacturing exchange-rate P/L.
- Separated native-currency win/loss classification from available-KRW totals.

## Tests

Synthetic tests cover exact and compact dates, prior-business-day selection,
no-future/no-fallback behavior, Kiwoom conversion and provenance, NH safe
non-conversion, provider and Toss non-overwrite, nullable FX fields, summary
completeness, native-currency win/loss classification, domestic records, and
manual/file-record compatibility.

## Remaining Limitations

- NH overseas automatic KRW conversion remains disabled until the event-date
  semantics are verified from an official contract or a safe runtime trace.
- A cached market FX observation is an accounting conversion aid, not a tax-law
  realized-gain calculation and not a provider-authoritative KRW P/L value.
- Replacing the existing market-data source with an official accounting FX
  source is outside this targeted fix.
