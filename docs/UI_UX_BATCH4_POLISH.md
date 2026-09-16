# Wealth — UI Consistency Polish and Tax-Account Display Fix (Batch 4)

## Scope

Batch 4 addresses UI/UX polish across the Wealth application alongside one critical display correctness issue:
1. Simplify Strategy Bucket default preset names to exact 8 canonical categories.
2. Remove redundant Home Quick Access section while keeping DOM/navigation contracts clean.
3. Remove unnecessary horizontal scrolling from Net Worth History on wide desktop screens.
4. **P0 Financial Display Fix**: Correct per-account cumulative tax-saving display on tax-advantaged securities cards.
5. Standardize major page-header styling and unhide `wealth-eyebrow` on Comprehensive Assets.
6. Standardize secondary tab navigation across Stock Investment, Comprehensive Assets, and Money Log.
7. Add small semantic icons/emojis to Stock Investment and Money Log tabs.

No database migrations, backend data structure alterations, broker integrations, or trading actions were introduced.

---

## Modified Files

### Application Code
- `app/static/wealth-planning.js`:
  - Simplified `BUCKET_PRESETS` to exact 8 canonical names (`코어`, `성장`, `배당`, `섹터`, `테마`, `전술`, `방어`, `현금`). Existing user buckets and custom buckets are neither renamed nor modified.
  - History panel cleanly inserts via `(home.querySelector('#wealthMarketSlot') || home).before(historyPanel)` without depending on the removed Quick Access section.
  - Implemented responsive chart width calculation `Math.max(plot.clientWidth || 800, records.length * 72, 420)` with adaptive horizontal padding `Math.max(48, Math.min(64, Math.round(width * 0.06)))`.
  - Added semantic emojis to Stock Investment secondary tabs (`📊 포트폴리오`, `🗺️ 히트맵`, `🗓️ 주식기록`, `🎯 전략 버킷`, `🧾 절세계좌`, `📋 보유종목`).
- `app/static/wealth-layout.js`:
  - Removed redundant `.wealth-home-secondary` / `.wealth-shortcuts` section ("오늘의 자산 관리" / "QUICK ACCESS") from the Home dashboard.
  - Added semantic emojis to Money Log secondary tabs (`📈 실현손익`, `💰 배당·이자`, `🧾 가계부`).
- `app/static/wealth-layout.css`:
  - Removed CSS rule hiding `.wealth-eyebrow` in the Comprehensive Assets view (`assets`), restoring standard header hierarchy (`YOUR FINANCIAL OVERVIEW`).
  - Standardized `.wealth-section-tabs` across Comprehensive Assets and Money Log with `display: flex; flex-wrap: nowrap; width: 100%; min-height: 38px; padding: 9px 13px; margin: 0 0 18px; border-radius: 12px;` to match Stock Investment tab layout.
  - Maintained responsive breakpoint rules and verified layout contracts for Batches 1, 2, and 3.
- `app/static/wealth.js`:
  - **P0 Fix**: Defined `calcSingleAccountCumulativeTaxSaved(account)` that accurately calculates the individual account's cumulative tax savings based on its annual deposit and income bracket (`16.5%` or `13.2%` up to the eligible account limit).
  - Updated `renderAccounts(items)` to use `calcSingleAccountCumulativeTaxSaved(account)` on deductible account cards instead of the owner-wide aggregate `calcAccountCumulativeTaxSaved(account, accounts)`.
  - Prevented non-deductible accounts from rendering fabricated cumulative tax savings.

### Test Suites
- `tests/test_ui_ux_batch4.py`: New comprehensive test suite validating all 7 Batch 4 requirements, including Node VM execution of tax helper functions for multi-account and non-deductible scenarios.
- `tests/test_v1015_information_architecture.py`: Updated assertions to reflect removal of Home Quick Access, updated `invest` label to `주식 투자`, and updated `부동산 순에퀴티` to `부동산 순자산`.
- `tests/test_v1021_ui_ux.py`: Updated assertions for removal of `.wealth-shortcuts` and `.wealth-home-secondary`.
- `tests/test_home_dashboard_batch2.py`: Updated chart padding assertions to match the Batch 4 responsive chart width.
- `tests/test_strategy_bucket_batch3.py`: Updated chart padding assertions to match the Batch 4 responsive chart width.

---

## Detailed Implementation Notes

### 1. Strategy Bucket Presets
- The default presets available in the editor are now strictly:
  `코어`, `성장`, `배당`, `섹터`, `테마`, `전술`, `방어`, `현금`.
- Deprecated compound names (`배당·인컴`, `방어·안전자산`, `현금·대기자금`) were removed from preset buttons while user-created buckets bearing any name remain completely intact.
- Custom bucket creation (`+ 사용자 정의 버킷`) remains fully functional.

### 2. Redundant Home Quick Access Removal
- The Home page previously contained a secondary section with redundant links to Stock Investment, Assets, and Money Log.
- This section was removed to eliminate clutter and give visual prominence to the Asset Portfolio and Net Worth History panels.
- The Net Worth History panel cleanly attaches before the market slot (`#wealthMarketSlot`) or directly inside the Home container.

### 3. Net Worth History Responsiveness
- Previously, the Net Worth History chart enforced a hardcoded `records.length * 150px` width and `92px` padding, causing unnecessary horizontal scrolling even when wide desktop screens had sufficient space.
- The chart now inspects container width (`plot.clientWidth || 800`) and uses `Math.max(containerWidth, records.length * minSpacing, 420)` with `minSpacing = 72px`.
- Horizontal padding adaptively scales between `48px` and `64px` based on chart width, preventing label clipping while maximizing plotting area.

### 4. Per-Account Cumulative Tax-Saving Display Fix (P0)
- **Problem**: When a taxpayer had multiple deductible accounts (e.g., Pension Savings + IRP), each account's summary card was displaying the taxpayer's *total combined* tax savings rather than the tax savings generated by *that specific account*. Furthermore, non-deductible accounts could misleadingly display tax savings.
- **Solution**:
  - Defined `calcSingleAccountCumulativeTaxSaved(account)`:
    - Verifies `isAccountTaxDeductible(account)`. If false, returns `0`.
    - Computes eligible deposit under the specific account type ceiling (Pension Savings: up to 6,000,000 KRW; IRP: up to 9,000,000 KRW).
    - Multiplies by tax credit rate (`16.5%` for low income, `13.2%` for high income).
  - In `renderAccounts(items)`:
    - Deductible accounts display `calcSingleAccountCumulativeTaxSaved(account)`.
    - Non-deductible accounts do not display `cumSaved` badge and are explicitly badged as `🌿 비공제 계좌`.
  - The aggregate owner-level calculation `calcAccountCumulativeTaxSaved(account, accounts)` and `calculateOwnerYearPensionTaxBenefits` remain unchanged for owner/family-level tax summaries.

### 5. Page Header Hierarchy
- The Comprehensive Assets view had CSS suppressing `.wealth-eyebrow`, causing an inconsistent header presentation compared to Home, Stock Investment, and Money Log.
- The suppression rule was removed. All 4 major sections now render the standardized eyebrow (`YOUR FINANCIAL OVERVIEW`), title (`#wealthPageTitle`), and description (`#wealthPageDescription`).

### 6. Secondary Tab Navigation Standardization
- Stock Investment (`.wealth-invest-tabs`) served as the canonical reference for secondary tab styling.
- Comprehensive Assets (`.account-category-tabs`) and Money Log (`.income-tabs`) were aligned with:
  - `display: flex; flex-wrap: nowrap; width: 100%;`
  - `min-height: 38px; padding: 9px 13px; margin: 0 0 18px;`
  - Horizontal scroll with thin scrollbar on narrow viewports to avoid tab wrapping or layout shifts.

### 7. Semantic Icons/Emojis in Secondary Tabs
- **Stock Investment**:
  - `📊 포트폴리오`
  - `🗺️ 히트맵`
  - `🗓️ 주식기록`
  - `🎯 전략 버킷`
  - `🧾 절세계좌`
  - `📋 보유종목`
- **Money Log**:
  - `📈 실현손익`
  - `💰 배당·이자`
  - `🧾 가계부`
- **Comprehensive Assets** (retained):
  - `📈 증권`
  - `🏦 은행`
  - `🛡️ 보험`
  - `🏠 부동산`

---

## Verification and Quality Invariants

| Check | Result |
| :--- | :--- |
| Full unittest suite | **Ran 686 tests — 100% OK (0 failures, 0 errors, 0 skipped)** |
| Node planning-model tests | **14 tests — 100% PASS** |
| Batch 4 dedicated tests | **8 tests — 100% PASS** |
| JavaScript syntax (`node --check`) | **PASS** (`wealth.js`, `wealth-layout.js`, `wealth-planning.js`, `wealth-planning-model.js`) |
| Python compileall | **PASS** |
| `git diff --check` | **PASS** |
| Production code modifications | Restricted strictly to Batch 4 requirements |
| Pre-existing work preserved | KB OpenAPI, CODEF probe, Dividend audit, Batches 1/2/3 intact |
| Version bumped | No (retained current v1.1.4) |
| Git commit/push executed | No |
