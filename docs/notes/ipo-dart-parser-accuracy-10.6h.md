# IPO DART parser accuracy hotfix (10.6h)

This hotfix is intentionally parser-only. It does not relax Wealth IPO scoring thresholds.

## Confirmed Melcon filing values

- Institutional competition ratio: `1,136.84 : 1` (rightmost total column)
- Lockup commitment ratio: `(44,996,000 + 89,848,000 + 138,080,000 + 475,465,000) / 2,074,742,000 = 36.07%`
- High-bid ratio: `(36,252,000 + 2,026,760,000) / (2,074,742,000 - 9,388,000) = 99.89%`
- Relative valuation: final offer price `12,300` / peer-derived evaluation price `14,173` = `0.8678`; with peer PER `26.18`, implied issuer PER is `22.72`

## Parser behavior

- Use the rightmost total from multi-column institutional competition tables.
- Ignore partial lockup tables that lack an explicit total investor group; prefer the complete total table.
- Read share quantities from multi-row price-distribution tables without trusting a misaligned header index.
- Count both exact band-high and above-band-high rows.
- Prefer the last explicit tradable-share disclosure when amended filing content repeats older values.
- Derive the same relative-valuation ratio from final offer price / peer-derived evaluation price when the issuer PER itself is not printed.

The base parser remains the fallback for all unaffected extraction methods.
