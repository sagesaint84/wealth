# KB Securities Open API Generic Response Normalization Contract (2026-09)

> **Status**: `AUTHORITATIVE_CONTRACT_DOCUMENT`
> **Topic**: Provider-level vs Endpoint-level response status and generic TR normalization semantics
> **Reference Issue**: Over-generalized `o_clsf` / `clsfP` error code check in `KBOpenAPI._normalize_response()`

---

## 1. Executive Summary

This document formalizes the response envelope and normalization contract for the KB Securities Open API integration in Wealth.

- **Root Issue**: The generic helper `KBOpenAPI._normalize_response()` previously evaluated `o_clsf` / `clsfP` against `{"", "0", "00"}` as if they were global provider error codes.
- **Root Cause Classification**: `O_CLSF_IS_ENDPOINT_BUSINESS_DATA_AND_GLOBAL_CHECK_IS_WRONG`.
- **Contract Reality**:
  - Global provider execution status is authoritative **only** in `dataHeader.processFlag` (`"A"` = success, `"B"` = failure) and `dataHeader.processCode` (`"0011"` = success, `"9999"` = failure).
  - `o_clsf` ("출구분") and `clsfP` ("구분자") are individual TR output packet fields having type `char(2)` and standard protocol value `"SC"` across all 95 KB Open API TR specifications. They are **never** error codes.
- **Resolution**: Removed the erroneous generic `o_clsf` / `clsfP` rejection from `_normalize_response()`. TR payloads (`dataBody`) are returned intact to caller services after verifying provider-level status via the fail-closed `_check_provider_status()`.

---

## 2. Official KB TR Specification Findings

An exhaustive audit of the official KB Securities Open API specification archive (`https://openapi.kbsec.com/api/kbs/guide/json/b2c`, 95 TRs) established the following contract facts:

### 2.1 `o_clsf` Definition
- **Korean Name**: `출구분` (Output Classification)
- **Type**: `char(2)`
- **Presence**: Defined in `outputSpec` across multiple heterogeneous TRs, including:
  - `SZQM0771` (Market Status / Public Information)
  - `SIQM4900` (Stock Balance / Account Information)
  - `SSQM5472`, `SSQN5472` (Order History / Domestic Trading)
  - `SIAM4983` (Account Summary)
  - `SKQM3350`, `SKQO3390` (Derivatives / Option Trading)
  - Appears alongside `o_lngth` (output length) and `o_msg` (output message).
- **Official Sample Value**: `"SC"` across all documented responses.
- **Meaning**: The official documentation does not define "SC" as an error code; it is a packet classification marker.

### 2.2 `clsfP` Definition
- **Korean Name**: `구분자` (Delimiter / Packet Classifier)
- **Type**: `char(2)`
- **Presence**: Defined in `outputSpec` across market/investment information TRs, including:
  - `IVU10140`, `IVU10070`, `IVU10080` (Stock Quotes / Prices)
  - `IVM10050`, `IVSA0070`, `IVA60140`, `IVM30010`, `IVA60190` (Market Indices / Statistics)
  - Appears alongside `lngth`, `msg`, and `RecordSize`.
- **Official Sample Value**: `"SC"` across all documented responses.

### 2.3 Provider Status Fields (`dataHeader`)
- `processCode` and `processFlag` are **NOT** per-TR `outputSpec` fields.
- They exist strictly at the `dataHeader` level:
  - `dataHeader.processFlag`: `"A"` (정상/Success), `"B"` (오류/Failure)
  - `dataHeader.processCode`: `"0011"` (정상/Success), `"9999"` (업무/인증 오류/Failure)
  - `dataHeader.resultCode`: `"200"` (HTTP/Gateway success)

---

## 3. Architecture & Design Policy

### 3.1 Separation of Concerns
1. **Global Provider Status**:
   - Must be verified via `_check_provider_status(data_header)`.
   - Any response with `processFlag != "A"` or `processCode != "0011"` raises `KBOpenAPIError`.
   - Unknown or unexpected process status fails closed.
2. **Generic TR Normalization (`_normalize_response`)**:
   - Checks `dataHeader` with `_check_provider_status()`.
   - Ensures `dataBody` is present if required (`require_data_body=True`) and is a `dict`.
   - Returns `dataBody` without stripping or validating endpoint-specific fields like `o_clsf` or `clsfP`.
3. **Endpoint-Specific Business Parsing**:
   - Specialized parsers (such as `_parse_realized_response` for `SSQM2442`) retain full ownership of interpreting their respective TR payloads (`Record1`, summary fields, etc.).
   - `SSQM2442` dedicated parser remains completely independent and does not rely on `o_clsf`.

---

## 4. Live Verification Evidence

### 4.1 SZQM0771 Read-Only Probe
Executed read-only live probe against KB Open API production gateway:
- **Endpoint**: `POST /api/v1/szqm0771`
- **Request**: Empty payload `dataBody: {}`
- **Response Headers**:
  - `HTTP Status`: `200`
  - `dataHeader.resultCode`: `"200"`
  - `dataHeader.processCode`: `"0011"`
  - `dataHeader.processFlag`: `"A"`
  - `dataHeader.processMessage`: `"정상 조회되었습니다."`
- **Returned `dataBody`**:
  - `o_clsf`: `"SC"`
  - `client.call("/api/v1/szqm0771", {})`: Succeeded cleanly without exception.
  - Correctly returned all 35 data fields.

### 4.2 SSQM2442 Realized P/L Dedicated Parser
- Successfully processes real and synthetic payloads with `0011` / `A`.
- Correctly fails closed on `9999` / `B`.
- No financial data imported or mutated during validation.

---

## 5. Verification Matrix

| Test Scope | Reference Baseline | Post-Fix Result | Status |
|:---|:---|:---|:---|
| KB Realized & Transport Tests | 83 tests | 86 tests (+3) | **PASS** |
| Full Application Test Suite | 769 tests | 772 tests (+3) | **PASS** |
| JavaScript Syntax Check | `node --check` | Clean | **PASS** |
| Planning Model Tests | 14 tests | 14 tests | **PASS** |
| Python Bytecode Compilation | `compileall` | Clean | **PASS** |
| Git Whitespace Check | `git diff --check` | Clean | **PASS** |
