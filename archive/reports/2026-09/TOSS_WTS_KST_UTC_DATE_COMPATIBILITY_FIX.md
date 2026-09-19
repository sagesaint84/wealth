# Toss WTS KST/UTC Date Compatibility Fix

## Root Cause

Toss WTS itself and the local session were available. The incompatibility is in `tossctl` v0.50.3: a `YYYY-MM-DD` input is parsed as UTC midnight and compared with the current instant. Between 00:00 and 08:59 Asia/Seoul, Korean today is later than the current UTC calendar date and is rejected as a future date.

Classification:

- Primary: `UPSTREAM_TOSSCTL_TIMEZONE_BUG`
- Wealth-side: `WEALTH_TOSSCTL_COMPATIBILITY_GAP`

## Upstream Behavior

For example, at 2026-09-15 02:00 KST the UTC calendar date is still 2026-09-14. `2026-09-15` parsed as UTC midnight is later than that instant, despite being a valid Korean calendar date.

## Why Session Was Not the Problem

The confirmed audit showed valid local WTS runtime material and successful read-only WTS endpoints. A historical request through 2026-09-14 also returned realized-profit rows. No re-login or credential workflow is required by this fix.

The confirmation endpoint still verifies only local runtime material and its process-local generation. The UI now calls this `WTS 런타임 확인` and reports `런타임 확인 완료`; it no longer implies live provider authentication.

## Requested vs Effective Date

The browser request remains the user's Korean-calendar request. For the affected v0.50.3 contract only, when the requested end date is Korean today and Korean today is ahead of the UTC calendar date, the adapter sends the latest CLI-safe date instead.

The response preserves both:

- `requested.from_date` / `requested.to_date`
- `provider_effective.from_date` / `provider_effective.to_date`
- `date_compatibility.adjusted` and its safe compatibility code

No row is fabricated for the omitted day. If adjustment would make the effective end precede the requested start, the request fails safely with the specific compatibility code.

## Timezone Handling

The compatibility helper derives calendar dates from an aware instant using explicit Asia/Seoul UTC+09:00 and UTC timezones. It does not depend on the server OS timezone, browser timezone, or naive datetimes. Korea has no daylight-saving transition, so the fixed offset is exact and avoids adding an unavailable platform `tzdata` dependency.

## Error Classification

Only a profit-daily non-zero exit containing the known dated Korean future-date rejection is mapped to `TOSSCTL_DATE_TIMEZONE_CONFLICT`. Raw stderr is never propagated. Other non-zero exits remain `NONZERO_EXIT`, preserving the existing safe generic boundary.

## UI Cleanup

When the backend reports a successful adjusted range, the UI displays the effective end date and explains that today's data becomes queryable after 09:00. On HTTP errors and network failures, a loading row is replaced with a truthful empty/error row instead of remaining indefinitely. Unknown 502/503 failures keep the existing generic runtime message.

## Tests

Synthetic tests cover:

- 02:00 KST adjustment from 2026-09-15 to provider-effective 2026-09-14
- 09:01 KST without adjustment
- unchanged historical and earlier safe dates
- specific and generic non-zero exit classification
- requested/effective response metadata
- adjusted-range frontend notice
- loading-row cleanup after HTTP 502
- unchanged successful feed rendering
- runtime-confirmation wording

No live provider call or financial write was performed.

Validation results:

- Focused Toss WTS suite: `countTestCases=177`, `testsRun=177`, `skipped=0`, `failures=0`, `errors=0`.
- Full unittest suite: `countTestCases=706`, `testsRun=706`, `skipped=0`, `failures=0`, `errors=0`.
- `node --check app/static/wealth.js`: PASS.
- `python -m compileall -q app tests`: PASS.
- `git diff --check`: PASS (line-ending notices only; no whitespace errors).

## Limitations

The workaround is intentionally limited to the configured affected v0.50.3 contract. It does not modify `tossctl`, infer omitted realized P/L, or attempt to query Korean today before the upstream validator can accept it.

## Unchanged Areas

Toss account synchronization, holdings/cash, financial mapping, selection tokens, preview/import, duplicate detection, persistence, FX, source attribution, owner mapping, other brokers, database schema, migrations, and application version remain unchanged.
