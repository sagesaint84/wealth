# KB Securities Realized P/L Audit

Audit date: 2026-09-14
Repository branch: `codex-refactor-realized-pnl-ipo-import`
Audited HEAD: `6de633e`
Application version: `1.1.4`
Result: **RUNTIME_POC_INCONCLUSIVE**

## Executive Summary

Wealth's KB Securities integration is a domestic, read-only OpenAPI flow using
`SSQM2442` (daily realized P/L detail), followed by the same signed preview,
duplicate classification, explicit import, and destination-mapping safeguards
used by the other broker importers. The implementation preserves KB's
`rlztn_pl` value as provider-authoritative P/L and does not subtract `fee` or
`svrl_tx` again.

Two correctness gaps were confirmed and minimally fixed. Realized-sale
selection now requires the official sell direction code (`trd_dl_ccd == "01"`)
instead of relying only on positive amount fields, and non-finite numeric values
are rejected safely before comparison. Synthetic tests, the cross-broker safety
suite, compilation, and the complete Wealth suite pass.

The implementation is not classified as fully runtime-ready because the single
sanitized live attempt ended in a provider error before a usable row was
returned, and the official material does not define whether `rlztn_pl` is gross
or net, the maximum query window, or the exact business-level row granularity.
The current implementation handles these unknowns conservatively.

## Current Implementation

The current source type is **official KB Securities REST OpenAPI**, not scraping,
file import, or a stub.

- `app/services/kb_openapi.py`: OAuth2 client-credentials authentication,
  server-held account context, SSQM2442 request/response parsing, token retry,
  continuation, and page guard.
- `app/services/kb_feed.py`: conservative realized-sale projection, lossless
  Decimal normalization, canonical rows, hashes, deterministic occurrence
  ordinals, opaque source identity binding, and signed selections/tickets.
- `app/services/kb_realized.py`: duplicate classification and preview logic.
- `app/main.py`: safe status, fetch, preview, import, and mapping orchestration.
- `app/services/user_openapi.py`: server-side resolution of the KB general
  account number and product number; the product number is not hardcoded.

The client never supplies the raw KB account tuple. Status and feed payloads use
masked display data and/or an HMAC-derived opaque source identity.

## Official Contract Mapping

Contract evidence was taken only from the [KB Securities OpenAPI portal](https://openapi.kbsec.com/),
the [official B2C guide](https://openapi.kbsec.com/guide_b2c), the
[official downloadable B2C API specification](https://openapi.kbsec.com/api/kbs/guide/json/b2c),
and the [official KB Securities sample repository](https://github.com/kbsecurities/kb-openapi)
(repository revision inspected: `159480c4fcb19e3a257c6d0484fbe7a5287e4434`).

SSQM2442 is documented as `POST /api/v1/ssqm2442`, with `inq_strt_dt`,
`inq_end_dt`, `md_clsf`, optional `is_cd`, and optional `nxt_key`. Across the
official KB specifications, the shared direction field is defined as
`01: sell, 02: buy`.

| Wealth concept | KB field | Verified meaning | Status |
| --- | --- | --- | --- |
| trade date | `trd_dt` | transaction date | CONFIRMED |
| security code | `shrt_is_cd` | short issue code | CONFIRMED |
| security name | `is_nm` | issue name | CONFIRMED |
| quantity | `dtls_ccls_q` | detailed settled quantity | CONFIRMED |
| sale unit price | `ccls_uprc` | settled unit price | CONFIRMED |
| purchase unit price | `b_uprc` | purchase unit price | CONFIRMED |
| sale amount | `s_amt` | sale amount | CONFIRMED |
| purchase cost | `b_amt` | purchase amount | CONFIRMED |
| provider realized P/L | `rlztn_pl` | realized P/L | CONFIRMED |
| gross realized P/L | none verified | no gross qualifier is documented | ABSENT |
| fee | `fee` | fee | CONFIRMED |
| tax | `svrl_tx` | securities transaction tax | CONFIRMED |
| net realized P/L | none verified | `rlztn_pl` netness is not specified | AMBIGUOUS |
| return percentage | `yld` | yield | CONFIRMED |
| currency | domestic contract | KRW domestic context | DERIVED |
| account | `gnl_ac_no` + `gds_no` context | server-side provider account tuple | CONFIRMED |

No stable, permanent transaction-level identifier is documented in SSQM2442.
Classification: **NO_RELIABLE_ID**. Wealth therefore uses the complete canonical
row hash plus deterministic occurrence ordinal and the opaque source identity.

## Canonical Wealth Semantics

The KB canonical row is domestic KRW data. `rlztn_pl` is retained unchanged as
both `pnl` and `pnl_krw`; `fee` and `svrl_tx` are provenance/breakdown values and
are not deducted again. `fx_rate` is `None`. Missing required financial fields
are rejected rather than converted to zero. Genuine positive, negative, and
zero P/L values retain their signs and numeric meaning through Decimal
canonicalization.

This matches the Wealth principle used by KIS, NH, and Kiwoom: provider truth is
normalized without inventing a second cost-basis calculation. Provider-specific
netness remains provider-specific and is not generalized across brokers.

## Findings

1. **CONFIRMED_BUG — direction was not authoritative in the row filter.** A
   contradictory row marked as an official buy (`02`) could be selected if its
   sale amount happened to be positive. Missing or unknown direction was also
   not independently rejected.
2. **CONFIRMED_MISSING_HANDLING — non-finite filter input.** `NaN` could raise a
   Decimal comparison exception and `Infinity` could pass the positive amount
   check. Projection later rejected non-finite values, but selection itself was
   not total and fail-closed.
3. **UNSUPPORTED_ASSUMPTION — P/L netness.** The official field name confirms
   realized P/L but not gross-versus-net treatment. Wealth correctly preserves
   the value and labels its netness as unverified.
4. **DESIGN_LIMITATION — no provider event ID.** Duplicate protection depends on
   a full canonical-row multiset identity. It is deterministic and preserves
   identical legitimate rows, but a provider-side correction that changes a
   financial field necessarily creates a different identity.
5. **DESIGN_LIMITATION — multi-row persistence.** Records are written using the
   existing broker import convention. A mid-batch storage failure is reported,
   and a retry converges through commit-time duplicate reclassification, but the
   store does not provide a multi-row transactional rollback.

## Fixes Applied

- Required `trd_dl_ccd == "01"` before a KB row can be a realized-sale
  candidate; official buy, missing direction, and unknown direction values now
  fail closed.
- Rejected non-finite sale amount, purchase amount, and quantity in the
  pre-projection classification stage without raising an uncontrolled Decimal
  comparison error.
- Added regression coverage for contradictory direction, missing/unknown
  direction, `NaN`, positive/negative infinity, and missing/blank fee or tax.

No canonical field mapping, provider P/L value, hash algorithm, source
fingerprint, route, UI, database schema, or historical record was changed.

## Unsupported Assumptions

- `rlztn_pl` must not be labelled gross or net until KB documents or runtime
  evidence establishes that meaning.
- SSQM2442 does not prove a stable transaction/event ID.
- The maximum supported query range and history depth are not documented in the
  inspected official material.
- The exact inclusivity of the date boundaries, future-date behavior, and
  holiday behavior are not stated.
- The actual product number must come from configured account context; the sample
  value `01` is not treated as a universal constant.
- Foreign/overseas realized P/L is outside this domestic contract and remains
  unsupported.

## Remaining Unknowns

- Real response row granularity for partial fills, lots, and multiple same-day
  sales.
- Whether every institution/account variant always populates fee, tax, detailed
  quantity, and the short issue code.
- Production rate-limit thresholds and pacing guidance; the portal states that
  limits exist but does not publish a universal numeric contract.
- Real terminal and continuation behavior beyond the official sample's
  whitespace-filled terminal `nxt_key`.
- Stability of the configured account/product scope across all token contexts;
  `source_scope_verified` therefore remains `false`.

## Runtime Verification

The original audit did not perform runtime verification. A subsequent sanitized
PoC attempted exactly one logical, read-only SSQM2442 fetch for the current
month-to-date window through the existing `KBOpenAPI` transport. Configuration
readiness was verified by presence only; no credential or account value was
printed. The provider request failed before a usable response row was returned.
The sanitized failure category was `PROVIDER_ERROR`.

No second call or wider date-range query was attempted. The result is therefore
`RUNTIME_POC_INCONCLUSIVE`, not evidence that the canonical mapping is wrong and
not evidence that the account has no realized activity.

## Runtime PoC

| Check | Result |
| --- | --- |
| `runtime_status` | `RUNTIME_POC_INCONCLUSIVE` |
| `KB_credential_configured` | `YES` |
| `KB_account_configured` | `YES` |
| `runtime_read_only_path_available` | `YES` |
| `SSQM2442_request_success` | `NO` (`PROVIDER_ERROR`) |
| `eligible_sell_row_observed` | `NO` |
| `rlztn_pl_present` | `NOT_OBSERVED` |
| `rlztn_pl_observed_relationship` | `INSUFFICIENT_DATA` |
| `fee_presence` | `NOT_OBSERVED` |
| `tax_presence` | `NOT_OBSERVED` |
| `row_granularity` | `UNKNOWN` |
| `partial_sale_behavior` | `NOT_OBSERVED` |
| `pagination_termination` | `NOT_OBSERVED` |
| `preview_success` | `NOT_TESTABLE` |
| `database_unchanged` | `YES` |

Database invariance covered the user's realized-P/L storage, KB destination
mapping, and portfolio storage using before/after byte hashes. No raw response,
financial value, account identifier, source identity, credential, or token was
written to this report. Normal authentication token caching is separate from
financial storage and was not treated as a financial mutation.

## Test Results

- Baseline before the patch: **598 run, 598 passed, 0 skipped, 0 failed, 0 errors**.
- Corrected focused run: **134 run, 134 passed, 0 skipped, 0 failed, 0 errors**.
- Post-change complete suite: **599 run, 599 passed, 0 skipped, 0 failed, 0 errors**.
- Runtime-PoC baseline: **599 run, 599 passed, 0 skipped, 0 failed, 0 errors**.
- Runtime-PoC KB-focused run: **62 run, 62 passed, 0 skipped, 0 failed, 0 errors**.
- Runtime-PoC post-check complete suite: **599 run, 599 passed, 0 skipped, 0 failed, 0 errors**.
- `python -m compileall -q app tests`: **PASS**.
- `git diff --check`: **PASS** (line-ending conversion warnings only).

The focused set covered KB transport/feed/routes/import, common IPO preferences,
mapping and recovery, signing/security, broker network safety, KIS, NH, Kiwoom,
and monthly date bucketing. The added test method accounts for the baseline-to-
post-suite increase from 598 to 599.

## Known Limitations

- Runtime contract behavior remains unverified.
- The safe projection admits only direction `01` rows with positive sale amount
  and positive detailed quantity. Ambiguous provider rows are excluded rather
  than interpreted.
- Empty or absent required financial values, including fee/tax breakdowns, fail
  closed instead of being fabricated as zero.
- Pagination has a 500-page safety limit per logical request. A non-string,
  missing, null, or repeated continuation key fails the request rather than
  returning partial data.
- Date validation accepts supported calendar formats and requires start not to
  exceed end, but does not impose an invented provider history/window limit.

## Recommended Next Step

Run one sanitized, read-only KB preview POC through the existing safe path to
confirm SSQM2442 row granularity, `rlztn_pl` accounting meaning, required-field
population, and real continuation termination without importing any record.
