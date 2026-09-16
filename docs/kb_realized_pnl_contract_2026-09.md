# KB Securities Open API Realized P/L Contract Revalidation (2026-09)

> **Amendment**: Updated by the Bounded Contract Correction Audit (2026-09-13).
> Corrections are marked `[CORRECTED]`. See Section 8 (Correction Log) for a full diff summary.

## 1. Executive Summary

This document establishes the authoritative contract revalidation for KB Securities Open API realized-P/L support for Wealth v1.1.5.

- **Domestic Realized P/L Status**: **`IMPLEMENTABLE_NOW`** via authoritative transaction **`SSQM2442`** (`SSQM2442_일자별실현손익상세`).
- **Overseas Realized P/L Status**: **`NOT_CURRENTLY_AVAILABLE`** (API contract limitation in `SPQM2207`).
- **Target Result**: **`KB_V115_DOMESTIC_CONTRACT_CORRECTION_PASS`**
- **Recommended Next Step**: **`READY_FOR_KB_V115_DOMESTIC_IMPLEMENTATION`**

All findings are derived strictly from:
1. KB Securities Open API Official Portal (`https://openapi.kbsec.com/`)
2. Official JSON API Specification Archive (`https://openapi.kbsec.com/api/kbs/guide/json/b2c`, 95 TR specifications)
3. Official Excel API Specification Workbook (`https://openapi.kbsec.com/api/kbs/guide/excel/b2c`, 77 sheets)
4. Official GitHub Repository (`kbsecurities/kb-openapi`) including `samples.generated.json`

---

## 2. Official Sources and Endpoints

### 2.1 Base URLs and Protocol
- **API Domain**: `https://developer.kbsec.com:32484`
- **Protocol**: HTTPS / REST (POST)
- **Data Exchange Format**: JSON

### 2.2 Authentication
- **Token Endpoint**: `POST https://developer.kbsec.com:32484/oauth2/token`
- **Grant Type**: `client_credentials`
- **Service Headers**: `Authorization: bearer <access_token>`, `appKey: <appKey>`, `Content-Type: application/json`

---

## 3. Domestic Realized P/L Contract: SSQM2442

### 3.1 Endpoint and Method — VERIFIED

- **API Label**: `SSQM2442 일자별실현손익상세` [CORRECTED from `실현손익현황`]
- **Path**: `POST /api/v1/ssqm2442`
- **Category**: 고객계좌 (Customer Account)
- **Description** (official): 일자별 실현 손익 내역을 상세하게 조회합니다. 매매일, 종목명, 체결 수량·단가, 수수료, 제세금, 실현 손익 및 수익률을 날짜 범위별로 확인할 수 있습니다.

### 3.2 Request Schema

**Official inputSpec fields** (from `samples.generated.json`):

| Field | Korean Name | Type | Required | Notes |
|:---|:---|:---|:---|:---|
| `is_cd` | 종목코드 | String(12) | N | Stock code filter; empty for all |
| `inq_strt_dt` | 조회시작일자 | String(8) | Y | YYYYMMDD |
| `inq_end_dt` | 조회종료일자 | String(8) | Y | YYYYMMDD |
| `md_clsf` | 매체구분 | String(1) | Y | [CORRECTED] Channel: 1=offline, 2=online, 3=branch |
| `nxt_key` | 다음키 | String(24) | N | Continuation key; empty for first page |

**[CORRECTED] `md_clsf` semantics**:
- Previous description incorrectly stated `md_clsf='2'` means "realized P/L mode".
- Official description: `1:오프라인 2:온라인 3:지점` (channel/medium classification, not a trade-type selector).
- API always returns realized P/L for the account; `md_clsf='2'` is the correct value for online API clients.
- Source: `samples.generated.json` inputSpec, confirmed by SSQM2443 inputSpec.

**`gnl_ac_no` / `gds_no` status** [CORRECTED]:
- These appear in the raw JSON sample dataBody but are **NOT in the official inputSpec**.
- Pass them in the request dataBody as shown in the official raw sample.
- `gds_no='01'` is in the sample but is **not officially documented as fixed** — do not hardcode without live verification.

### 3.3 Response Schema

**Summary aggregates (`dataBody` header level)**:

| Field | Korean Name | Type |
|:---|:---|:---|
| `s_q_sum` | 매도수량합계 | String(18) |
| `s_amt_sum` | 매도금액합계 | String(18) |
| `tl_s_fee` | 총매도수수료 | String(12) |
| `tl_s_svrl_tx` | 총매도제세금 | String(12) |
| `tl_s_ec_amt` | 총매도정산금액 | String(15) |
| `b_q_sum` | 매수수량합계 | String(18) |
| `b_amt_sum` | 매수금액합계 | String(18) |
| `tl_b_fee` | 총매수수수료 | String(12) |
| `tl_b_svrl_tx` | 총매수제세금 | String(12) |
| `tl_b_ec_amt` | 총매수정산금액 | String(12) |
| `trd_fee_sum` | 매매수수료합계 | String(18) |
| `svrl_tx_tl_sum` | 제세금총합계 | String(18) |
| `tl_ec_amt` | 총정산금액 | String(18) |
| `nxt_key` | 다음키 | String(24) |
| `grid_cnt1` | 그리드건수1 | String(4) |
| `Record1` | — | Object array(60) |

### 3.4 Record1 Fields — Full Official Schema

| Field | Korean Name | Type | Wealth Mapping | Classification |
|:---|:---|:---|:---|:---|
| `trd_dt` | 매매일자 | String(8) | date (YYYYMMDD) | DIRECT_VERIFIED |
| `stnd_is_cd` | 표준종목코드 | String(12) | standard ISIN code | DIRECT_VERIFIED |
| `shrt_is_cd` | 단축종목코드 | String(12) | stock code (strip leading A) | DIRECT_VERIFIED |
| `is_nm` | 종목명 | String(40) | stock name | DIRECT_VERIFIED |
| `trd_dl_ccd` | 매매거래구분코드 | String(2) | buy/sell type code | DIRECT_VERIFIED |
| `crdt_typ_cd` | 신용유형코드 | String(2) | credit type (00=cash) | DIRECT_VERIFIED |
| `ccls_q` | 체결수량 | String(9) | execution qty (integer precision) | DIRECT_BUT_SEMANTICS_AMBIGUOUS |
| `dtls_ccls_q` | 상세체결수량 | String(23) | authoritative qty (fractional-safe) | DIRECT_VERIFIED |
| `dcml_dl_f` | 소수점거래여부 | String(1) | fractional flag (0/1) | DIRECT_VERIFIED |
| `ccls_uprc` | 체결단가 | String(9) | sell unit price | DIRECT_VERIFIED |
| `b_uprc` | 매수단가 | String(9) | buy unit price (cost basis) | DIRECT_BUT_SEMANTICS_AMBIGUOUS |
| `s_amt` | 매도금액 | String(13) | sell amount | DIRECT_VERIFIED |
| `b_amt` | 매수금액 | String(13) | buy amount | DIRECT_VERIFIED |
| `fee` | 수수료 | String(9) | commission (informational) | DIRECT_VERIFIED |
| `svrl_tx` | 제세금 | String(9) | tax (informational) | DIRECT_VERIFIED |
| `rlztn_pl` | 실현손익 | String(13) | realized pnl (authoritative) | DIRECT_BUT_SEMANTICS_AMBIGUOUS |
| `yld` | 수익율 | String(9) | profit rate (authoritative) | DIRECT_VERIFIED |

**[CORRECTED]**: `ern_r` appears in raw JSON sample but is NOT in official outputSpec. Do not use it.

### 3.5 rlztn_pl Netness — NOT_VERIFIED [CORRECTED]

**[CORRECTED]** — Previous report incorrectly claimed `rlztn_pl` is "net of commission and tax".

**Evidence examined**:
- The only official JSON sample row has `rlztn_pl=0` because it is a BUY row (`trd_dl_ccd='02'`) with no realization event. No sell-realization arithmetic example exists in the published spec.
- Field description is simply `실현손익` — no "net" or "gross" qualifier.
- Sister API `SSQM2443` has both `rlztn_pl` and separate `s_fee`, `b_fee`, `s_svrl_tx` fields at row level. This is structurally consistent with both gross and net interpretations.

**Conclusions**:
- rlztn_pl commission inclusion: **NOT_VERIFIED**
- rlztn_pl tax inclusion: **NOT_VERIFIED**

**Canonical safe policy** (Section 4 policy):
- Use `rlztn_pl` as the authoritative P/L value.
- Retain `fee` and `svrl_tx` as informational breakdowns only.
- Do NOT subtract either from `rlztn_pl`.
- Rationale: If `rlztn_pl` is net, this policy is correct. If `rlztn_pl` is gross, Wealth shows gross P/L — conservative and does not manufacture incorrect accounting entries.
- Mark `pnl_netness = PROVIDER_AUTHORITATIVE_UNVERIFIED` in implementation metadata.
- Verify with live sandbox before release.

**Recommended fee subtraction**: NO
**Recommended tax subtraction**: NO

### 3.6 Authoritative Quantity Field — dtls_ccls_q [CORRECTED]

- `ccls_q` (String(9), decimal=0): Integer precision. May truncate fractional shares.
- `dtls_ccls_q` (String(23)): Extended precision. Designed for fractional trading.
- When `dcml_dl_f='0'`, both carry the same integer value.
- When `dcml_dl_f='1'`, `dtls_ccls_q` is the lossless representation.
- **Authoritative quantity field**: `dtls_ccls_q` (never silently rounds).

### 3.7 Row Granularity — GRANULARITY_NOT_VERIFIED

API name means "per-date realized P/L detail". Each row has `trd_dt` and `trd_dl_ccd`. The official JSON sample row has `trd_dl_ccd='02'` (BUY), suggesting both buy and sell rows may appear (API is not sell-only). Whether one row = one execution lot or one row = one stock per date aggregate is not definitively established by official documentation.

**Classification**: GRANULARITY_NOT_VERIFIED

**Safe assumption**: Treat each row as a discrete record. Use canonical multiset occurrence hashing.

### 3.8 Duplicate Identity

- No provider row ID is exposed in Record1.
- **Stable provider row ID**: NO
- **Recommended identity**: Canonical hash of the full authoritative row tuple:
  `hash(trd_dt, shrt_is_cd, trd_dl_ccd, dtls_ccls_q, ccls_uprc, b_uprc, rlztn_pl)` + occurrence ordinal for identical tuples.
- Provider response order and page index must NOT be used as identity.

### 3.9 Pagination Contract

| Dimension | Classification |
|:---|:---|
| Request field `dataBody.nxt_key` | VERIFIED |
| Response field `dataBody.nxt_key` | VERIFIED |
| All-whitespace 24-char terminal | VERIFIED (present in official JSON sample output) |
| Empty string terminal | NOT_VERIFIED |
| null terminal | NOT_VERIFIED |
| Missing field terminal | NOT_VERIFIED |

**Repeated-key official semantics**: NOT_VERIFIED — not documented.

**Wealth safe implementation policies** (not KB contract facts):
- Treat empty string, all-whitespace, null, and missing `nxt_key` as all terminal.
- If a non-empty non-whitespace `nxt_key` is returned unchanged across consecutive requests, fail closed (do not loop).
- Implement a maximum-page guard (e.g., 500 pages) against malformed responses.
- Never surface partial data as a complete result.

### 3.10 Date-Range and Historical Limits

- Maximum query period: NOT_VERIFIED
- Historical retention depth: NOT_VERIFIED
- Same-day query validity: NOT_VERIFIED
- Start/end inclusivity: NOT_VERIFIED
- Multi-year range support: NOT_VERIFIED

**Policy**: Send user-selected range as-is. Do not invent automatic chunking. Surface errors cleanly.

---

## 4. Account Contract

### 4.1 Account Number Semantics

- `gnl_ac_no` (계좌번호): 9-10 digit customer account number. Present in raw JSON sample dataBody.
- `gds_no` (상품번호): Product number. Value `01` in raw JSON sample. NOT in official inputSpec.

### 4.2 Account Discovery

- **SSQM0005** (`총 잔고 조회`): Returns `ac_no` in Record1 — can enumerate account numbers.
- **SSQM0005 does NOT return `gds_no`**. It returns `gds_typ_cd` (different field).
- No official API enumerates complete `(gnl_ac_no, gds_no)` pairs for SSQM2442.

**Account Discovery Classification**: NOT_AVAILABLE_VERIFIED for full `(gnl_ac_no, gds_no)` discovery.

### 4.3 Multi-Account Scope

- Multi-account scope verified: NO
- `source_scope_verified = false` must remain the design until live verification.
- Opaque identity: `HMAC-SHA256(server_secret, "kb:" + gnl_ac_no + ":" + gds_no)`

### 4.4 gds_no Semantics — [CORRECTED]

- `gds_no='01'` is the raw JSON sample value only. It is NOT formally documented as fixed.
- Do not hardcode. Obtain from actual user account configuration.

---

## 5. Overseas Realized P/L — Unchanged

The overseas decision (`NOT_CURRENTLY_AVAILABLE`) is not reopened by this audit. `SPQM2207` Record2 does not expose per-stock lot rows across historical date ranges. `SPQM2206` is same-day only.

---

## 6. Canonical Field Mapping (Final Corrected)

| Wealth Field | KB Field | Classification |
|:---|:---|:---|
| date | `trd_dt` | DIRECT_VERIFIED |
| stock_code | `shrt_is_cd` (strip A prefix) | DIRECT_VERIFIED |
| stock_name | `is_nm` | DIRECT_VERIFIED |
| quantity | **`dtls_ccls_q`** (authoritative) | DIRECT_VERIFIED |
| buy_unit_price | `b_uprc` | DIRECT_BUT_SEMANTICS_AMBIGUOUS |
| buy_amount | `b_amt` | DIRECT_VERIFIED |
| sell_unit_price | `ccls_uprc` | DIRECT_VERIFIED |
| sell_amount | `s_amt` | DIRECT_VERIFIED |
| commission | `fee` (informational) | DIRECT_VERIFIED |
| tax | `svrl_tx` (informational) | DIRECT_VERIFIED |
| pnl | `rlztn_pl` (authoritative; netness unverified) | DIRECT_BUT_SEMANTICS_AMBIGUOUS |
| profit_rate | **`yld`** (authoritative; ern_r not in official schema) | DIRECT_VERIFIED |
| currency | KRW (implicit for all SSQM2442 rows) | DIRECT_VERIFIED |
| pnl_krw | `rlztn_pl` (domestic = KRW) | DIRECT_VERIFIED |
| fx_rate | None (domestic only) | DIRECT_VERIFIED |

---

## 7. Implementation Readiness

**Domestic SSQM2442**: **READY_FOR_IMPLEMENTATION**

- All required fields are available with safe canonical mappings.
- `rlztn_pl` netness is unverified but safe fail-closed policy exists (do not re-subtract).
- `dtls_ccls_q` is the authoritative quantity field.
- `yld` is the authoritative profit rate field.
- `md_clsf='2'` (online channel) is correct for API clients.
- Pagination is well-defined with conservative terminal detection policy.
- Date range limits are undocumented but do not block implementation.
- `gds_no` uncertainty does not block (pass from user account configuration).
- No stable row ID; canonical full-tuple hash is safe.

---

## 8. Correction Log (Bounded Audit 2026-09-13)

| # | Item | Previous Claim | Corrected Claim |
|:--|:--|:--|:--|
| C1 | `md_clsf` semantics | '2' = realized P/L mode | 매체구분 channel code: 2=online |
| C2 | `gnl_ac_no`/`gds_no` in inputSpec | Documented input fields | NOT in official inputSpec |
| C3 | `rlztn_pl` netness | "net of commission and tax" | NOT_VERIFIED |
| C4 | Profit rate field | `yld / ern_r` (ambiguous) | `yld` is authoritative; `ern_r` undocumented |
| C5 | Authoritative quantity | `ccls_q` | `dtls_ccls_q` (fractional-safe) |
| C6 | Pagination terminal | empty-string listed as verified | only all-whitespace 24-char verified; others defensive |
| C7 | `gds_no='01'` | Mapping fact | Sample value only; not formally fixed |
| C8 | API label | `실현손익현황` | `일자별실현손익상세` |
---

## 9. Live Runtime Validation — 2026-09-16

> **Amendment**: Added by live provider validation session (2026-09-16).
> Supersedes any `PENDING_LIVE_VALIDATION` or `RUNTIME_POC_INCONCLUSIVE` markers in prior sections.

### 9.1 TR Request dataHeader — Live-Validated Requirement

**Official KB sample default** (from `kbsecurities/kb-openapi` → `common.py`):
```python
DEFAULT_TR_DATA_HEADER = {"ipAddr": "", "macAddr": ""}
```
The comment in that file states: "When called from a server/backend, empty values are allowed."

**Live direct API behavior** observed in this environment (direct call to `https://developer.kbsec.com:32484`):

| dataHeader configuration | processCode | processFlag | dataBody |
|:---|:---|:---|:---|
| `ipAddr=""`, `macAddr=""` | `9999` | `B` | `null` |
| No `dataHeader` key at all | N/A (Spring HTTP 500) | N/A | N/A |
| `ipAddr=<local outbound IP>`, `macAddr=""` | `9999` | `B` | `null` |
| `ipAddr=<local outbound IP>`, `macAddr=<local MAC>` | `0011` | `A` | OBJECT |

**Conclusion**: For direct calls to the KB developer portal in this environment, both `ipAddr` AND `macAddr` must be non-empty for TR calls to succeed.

**Important distinction**:
- This document does NOT claim the official KB sample is wrong.
- The official sample may work correctly within the KB test portal proxy, where the proxy fills in real network information before forwarding to the backend.
- For **direct server-to-KB-API calls**, the live evidence shows that populated runtime values are required.
- Wealth now derives both fields at runtime using the same technique as the official KB backend sample (`openapi_test_defaults.py`): UDP socket connect to 8.8.8.8 for local IP, `uuid.getnode()` for MAC.

**Wealth implementation**: `KBOpenAPI._data_header()` — derives both fields at runtime. No hard-coded values.

### 9.2 KB Response Envelope — Two-Layer Status Semantics (Live-Verified)

KB TR responses use a **two-layer status system**:

```json
{
  "dataHeader": {
    "resultCode": "200",       // outer envelope — always "200" on HTTP 200
    "resultMessage": "성공",   // outer — always "성공" on HTTP 200
    "processCode": "0011",     // business-layer code (SUCCESS observed live)
    "processFlag": "A",        // "A" = provider business success (observed live)
    "processMessage": "..."    // human-readable status detail
  },
  "dataBody": { ... }          // present only when processFlag == "A"
}
```

**Live-observed status pairs**:

| Condition | processCode | processFlag | dataBody |
|:---|:---|:---|:---|
| TR call succeeded (SSQM2442, SZQM0771) | `0011` | `A` | OBJECT |
| TR validation failure (blank ipAddr/macAddr) | `9999` | `B` | `null` |

**Critical rule**: `resultCode="200"` alone does **NOT** indicate business success. `processFlag="A"` is the authoritative success indicator.

**Wealth implementation**: `KBOpenAPI._check_provider_status()` — called before any `dataBody` inspection in both `_parse_realized_response()` (SSQM2442 path) and `_normalize_response()` (generic TR path).

### 9.3 SSQM2442 Live Success — Confirmed (2026-09-16)

A live `SSQM2442` call with runtime-derived `dataHeader` returned:

- **HTTP**: `200`
- **resultCode**: `"200"`
- **processCode**: `"0011"`
- **processFlag**: `"A"`
- **dataBody**: OBJECT (all summary fields present)
- **Record1**: PRESENT (2 rows in H1 2025 window)
- **nxt_key**: 24-space whitespace string → terminal (no second page)
- **rlztn_pl**: PRESENT in all rows

**All fields verified present at runtime**:
`trd_dt`, `trd_dl_ccd`, `shrt_is_cd`, `is_nm`, `dtls_ccls_q`, `ccls_uprc`, `b_uprc`, `s_amt`, `b_amt`, `fee`, `svrl_tx`, `rlztn_pl`, `yld`, `dcml_dl_f`, `crdt_typ_cd`, `stnd_is_cd`

### 9.4 Trade Direction — Runtime Verified

| Code | Direction | Evidence |
|:---|:---|:---|
| `trd_dl_ccd = "01"` | Sell (realization event) | RUNTIME_VERIFIED — row with rlztn_pl, sell row filtered by `is_realized_sale_row()` |
| `trd_dl_ccd = "02"` | Buy (cost acquisition) | RUNTIME_VERIFIED — excluded by feed builder as non-realization |

### 9.5 Account Number Derivation — Live Verified

- Derivation: `gnl_ac_no = account11[:3] + account11[5:]` (9 digits), `gds_no = account11[3:5]` (2 digits)
- Status: **`LIVE_VALIDATED`** — SSQM2442 succeeded using derived values.

### 9.6 rlztn_pl Provider→Feed Preservation

- **`PROVIDER_TO_FEED_EQUAL: YES`** — `canonical_kb_number(rlztn_pl)` equals `feed_row["pnl"]`
- **`FEED_PNL_EQUALS_PNL_KRW: YES`** — confirmed for domestic (KRW) rows
- **Net/gross semantics**: Still `PROVIDER_AUTHORITATIVE_UNVERIFIED` — official docs do not define whether `rlztn_pl` is gross or net. Wealth preserves the provider value without re-subtracting `fee` or `svrl_tx`.

### 9.7 Pagination — Runtime Verified

- **`nxt_key` whitespace-only terminal**: **`LIVE_VALIDATED`** — observed 24-space string in successful SSQM2442 response; `is_terminal_nxt_key()` returns `True`.
- No second page request was triggered.

### 9.8 Financial Writes

- All validation probes were **read-only**.
- `FINANCIAL_WRITES = 0`
- No live import was performed.

### 9.9 Updated Status

| Classification | Prior | Current |
|:---|:---|:---|
| `SSQM2442` live execution | `PENDING_LIVE_VALIDATION` | `LIVE_VALIDATED` |
| TR dataHeader contract | `OFFICIAL_SAMPLE_DEFAULT_BLANK` | `RUNTIME_NON_EMPTY_REQUIRED_FOR_DIRECT_CALLS` |
| processCode/processFlag semantics | `UNKNOWN` | `LIVE_VALIDATED (0011/A=success, 9999/B=failure)` |
| Account 9+2 derivation | `PENDING_LIVE_VALIDATION` | `LIVE_VALIDATED` |
| Trade side discriminator | `CONTRACT_ONLY` | `RUNTIME_VERIFIED (01=sell, 02=buy)` |
| rlztn_pl provider→feed | `PENDING_LIVE_VALIDATION` | `LIVE_VALIDATED (equal)` |
| rlztn_pl netness | `NOT_VERIFIED` | `PROVIDER_AUTHORITATIVE_UNVERIFIED (unchanged)` |
| Wealth capability | `KB_IMPLEMENTATION_STATUS_FIX_COMPLETE_PROVIDER_POC_PENDING` | `KB_REALIZED_PNL_READY_WITH_LIMITATIONS` |

**Remaining limitation**: `rlztn_pl` gross/net semantics not officially documented. Wealth preserves provider value authoritatively.
