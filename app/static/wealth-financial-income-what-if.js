(() => {
  'use strict';

  const API_PATH = '/api/dividends/financial-income-what-if';
  const DIVIDEND_PRESETS = [1e6, 5e6, 10e6];

  function money(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '확인 불가';
    return `₩${Math.round(Number(value)).toLocaleString('ko-KR')}`;
  }

  function percent(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '확인 불가';
    return `${Number(value).toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
  }

  function currentOwnerValue() {
    try {
      if (typeof currentOwner === 'string' && currentOwner.trim()) return currentOwner;
    } catch (_) {
      // Fall through to the active family tab when the legacy global is unavailable.
    }
    const active = document.querySelector('#dividendFamilyTabs .family-tab.active');
    return active?.dataset?.owner || '모두';
  }

  function estimatedModeActive() {
    const active = document.querySelector('#dividendModeTabs .heatmap-tab.active');
    return active?.dataset?.divMode === 'estimated';
  }

  function numberValue(id) {
    const el = document.getElementById(id);
    if (!el || el.value === '') return 0;
    const value = Number(el.value);
    return Number.isFinite(value) ? value : NaN;
  }

  function boolValue(id) {
    return Boolean(document.getElementById(id)?.checked);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function presetMarkup() {
    return DIVIDEND_PRESETS.map(value => `
      <button type="button" class="fi-dividend-preset" data-dividend-preset="${value}">
        +${Math.round(value / 10_000).toLocaleString('ko-KR')}만
      </button>
    `).join('');
  }

  function panelMarkup() {
    return `
      <section id="financialIncomeWhatIfPanel" class="fi-what-if-panel" aria-label="배당 세금 대시보드">
        <div class="fi-what-if-head">
          <div>
            <span class="fi-what-if-kicker">DIVIDEND TAX DASHBOARD</span>
            <h3>배당 세금 대시보드</h3>
            <p>올해 예상 금융소득과 2천만원 기준까지의 여유를 보고, 배당을 더 받을 때 세전·원천징수 후 현금흐름이 어떻게 달라지는지 빠르게 확인합니다.</p>
          </div>
          <span class="fi-what-if-badge">자산관리용 · 저장 안 함</span>
        </div>

        <form id="financialIncomeWhatIfForm" class="fi-what-if-form">
          <div class="fi-what-if-section fi-dividend-primary">
            <div class="fi-what-if-section-title">
              <strong>배당을 더 받는다면?</strong>
              <small>현재 보유자산의 실제 + 예상 금융소득을 기준으로 비교합니다.</small>
            </div>
            <div class="fi-dividend-input-row">
              <label class="fi-dividend-input">
                <span>추가 배당 가정</span>
                <input id="fiWhatIfExtraDividend" type="number" min="0" step="10000" value="0" inputmode="numeric" data-korean-currency />
                <small>세전 원화 기준 · 실제 자산이나 배당 기록은 변경하지 않습니다.</small>
              </label>
              <div class="fi-dividend-presets" aria-label="추가 배당 빠른 가정">
                ${presetMarkup()}
              </div>
            </div>
            <div class="fi-what-if-grid two">
              <label>
                <span>세후 현금흐름 기준</span>
                <select id="fiWhatIfAfterTaxAssetType">
                  <option value="">계산 안 함</option>
                  <option value="domestic_dividend_stock">일반 국내 배당주</option>
                  <option value="kr_listed_us_etf">국내상장 해외 ETF 분배금</option>
                  <option value="us_direct">미국주식 · 미국 ETF 직투 배당</option>
                </select>
                <small>배당 유형을 명시한 경우에만 기존 verified tax screening을 재사용합니다.</small>
              </label>
              <label>
                <span>투자금액 (선택)</span>
                <input id="fiWhatIfAfterTaxInvestment" type="number" min="0" step="100000" value="0" inputmode="numeric" data-korean-currency />
                <small>입력하면 원천징수 후 배당수익률을 함께 계산합니다.</small>
              </label>
            </div>
          </div>

          <details class="fi-what-if-details fi-secondary-scenarios">
            <summary>이자·매매 등 다른 가정도 추가하기</summary>
            <div class="fi-secondary-scenario-body">
              <div class="fi-what-if-grid two">
                <label>
                  <span>추가 이자 가정</span>
                  <input id="fiWhatIfExtraInterest" type="number" min="0" step="10000" value="0" inputmode="numeric" data-korean-currency />
                  <small>세전 원화 기준</small>
                </label>
                <label>
                  <span>국내상장 해외 ETF 과세기준금액</span>
                  <input id="fiWhatIfKrOverseasEtfTaxableGain" type="number" min="0" step="10000" value="0" data-korean-currency />
                  <small>배당소득 성격의 screening 금액으로 금융소득에 포함</small>
                </label>
              </div>
              <div class="fi-what-if-grid one">
                <label>
                  <span>해외주식 실현차익 가정</span>
                  <input id="fiWhatIfForeignShareGain" type="number" min="0" step="10000" value="0" data-korean-currency />
                  <small>금융소득 2천만원 판정에는 포함하지 않으며 이 입력만으로 양도소득세를 계산하지 않습니다.</small>
                </label>
              </div>
            </div>
          </details>

          <details class="fi-what-if-details fi-advanced-scenarios">
            <summary>고배당 특례 · 개인 vs 가족법인 등 고급 비교</summary>
            <div class="fi-advanced-scenario-body">
              <div class="fi-what-if-section fi-nested-section">
                <label class="fi-what-if-toggle">
                  <input id="fiWhatIfHighDividendEnabled" type="checkbox" />
                  <span>
                    <strong>2026 고배당기업 분리과세 특례 가정</strong>
                    <small>공식 공시 확인과 실제 신고 시 신청 가정을 별도로 입력합니다.</small>
                  </span>
                </label>
                <div id="fiWhatIfHighDividendFields" class="fi-what-if-investment-fields" hidden>
                  <div class="fi-what-if-grid three">
                    <label>
                      <span>특례 배당금액</span>
                      <input id="fiWhatIfHighDividendAmount" type="number" min="0" step="10000" value="0" data-korean-currency />
                      <small>추가 배당 가정 중 특례 대상이라고 가정할 금액</small>
                    </label>
                    <label class="fi-check">
                      <input id="fiWhatIfHighDividendConfirmed" type="checkbox" />
                      <span>공식 공시에서 고배당기업 확인함</span>
                    </label>
                    <label class="fi-check">
                      <input id="fiWhatIfHighDividendRequested" type="checkbox" />
                      <span>신고 시 분리과세 신청 가정</span>
                    </label>
                  </div>
                  <small>앱이 배당수익률로 적격 여부를 추정하지 않습니다. 공식 공시 확인이 전제입니다.</small>
                </div>
              </div>

              <div class="fi-what-if-section fi-nested-section">
                <label class="fi-what-if-toggle">
                  <input id="fiWhatIfInvestmentEnabled" type="checkbox" />
                  <span>
                    <strong>개인 vs 가족법인 투자방법도 비교</strong>
                    <small>국내 배당주 · 국내상장 미국 ETF · 미국직투</small>
                  </span>
                </label>

                <div id="fiWhatIfInvestmentFields" class="fi-what-if-investment-fields" hidden>
                  <label class="fi-check">
                    <input id="fiWhatIfUseQuickTrading" type="checkbox" checked />
                    <span>빠른 매매 가정을 비교 입력의 보조값으로 사용</span>
                  </label>
                  <small>수동 매매차익이 0이거나 ETF 과세대상 매매이익이 빈칸일 때만 위 값을 사용합니다.</small>
                  <div class="fi-what-if-grid three">
                    <label>
                      <span>투자 유형</span>
                      <select id="fiWhatIfAssetType">
                        <option value="domestic_dividend_stock">국내 배당주</option>
                        <option value="kr_listed_us_etf">국내상장 미국 ETF</option>
                        <option value="us_direct">미국주식 · 미국 ETF 직투</option>
                      </select>
                    </label>
                    <label>
                      <span>연간 배당·분배금</span>
                      <input id="fiWhatIfDistribution" type="number" min="0" step="10000" value="0" />
                    </label>
                    <label>
                      <span>연간 실현 매매차익</span>
                      <input id="fiWhatIfRealizedGain" type="number" min="0" step="10000" value="0" />
                    </label>
                  </div>

                  <div id="fiWhatIfEtfTaxGainWrap" class="fi-what-if-grid one" hidden>
                    <label>
                      <span>ETF 과세대상 매매이익</span>
                      <input id="fiWhatIfEtfTaxGain" type="number" min="0" step="10000" placeholder="모르면 비워두기" />
                      <small>비우면 실제 매매차익을 보수적 screening 값으로 사용합니다.</small>
                    </label>
                  </div>

                  <div class="fi-what-if-subhead">가족법인 가정</div>
                  <div class="fi-what-if-grid three">
                    <label>
                      <span>기존 법인 과세소득</span>
                      <input id="fiWhatIfCorporateBase" type="number" min="0" step="100000" value="0" />
                    </label>
                    <label>
                      <span>투자 관련 손금</span>
                      <input id="fiWhatIfCorporateExpense" type="number" min="0" step="10000" value="0" />
                    </label>
                    <label>
                      <span>법인 → 개인 배당 인출</span>
                      <input id="fiWhatIfOwnerDistribution" type="number" min="0" step="10000" value="0" />
                    </label>
                  </div>

                  <details class="fi-what-if-details">
                    <summary>고급 세법 가정</summary>
                    <div class="fi-what-if-grid three">
                      <label class="fi-check">
                        <input id="fiWhatIfDomesticExclusionEligible" type="checkbox" />
                        <span>국내 수입배당 익금불산입 적격</span>
                      </label>
                      <label>
                        <span>국내법인 지분율 (%)</span>
                        <input id="fiWhatIfDomesticOwnership" type="number" min="0" max="100" step="0.1" value="0" />
                      </label>
                      <label>
                        <span>국내법인 보유 개월</span>
                        <input id="fiWhatIfDomesticHoldingMonths" type="number" min="0" step="1" value="0" />
                      </label>
                      <label class="fi-check">
                        <input id="fiWhatIfUsTreatyQualified" type="checkbox" />
                        <span>한미조약 법인 10% 배당세율 적격</span>
                      </label>
                      <label class="fi-check">
                        <input id="fiWhatIfForeignSubsidiaryQualified" type="checkbox" />
                        <span>외국자회사 95% 익금불산입 적격</span>
                      </label>
                      <label>
                        <span>미국법인 지분율 (%)</span>
                        <input id="fiWhatIfForeignOwnership" type="number" min="0" max="100" step="0.1" value="0" />
                      </label>
                    </div>
                  </details>
                </div>
              </div>
            </div>
          </details>

          <div class="fi-what-if-actions">
            <button id="fiWhatIfRun" type="submit" class="button primary">배당 영향 계산</button>
            <span id="fiWhatIfStatus" class="fi-what-if-status" role="status"></span>
          </div>
        </form>

        <div id="financialIncomeWhatIfResult" class="fi-what-if-result" aria-live="polite">
          <div class="fi-what-if-placeholder">예상 배당 기준을 불러오면 현재 상태가 여기에 표시됩니다.</div>
        </div>
      </section>
    `;
  }

  function mountPanel() {
    if (document.getElementById('financialIncomeWhatIfPanel')) return;
    const summary = document.querySelector('#dividendPanel .dividend-summary-cards');
    if (!summary) return;
    summary.insertAdjacentHTML('afterend', panelMarkup());

    document.getElementById('fiWhatIfHighDividendEnabled')?.addEventListener('change', syncHighDividendFields);
    document.getElementById('fiWhatIfInvestmentEnabled')?.addEventListener('change', syncInvestmentFields);
    document.getElementById('fiWhatIfAssetType')?.addEventListener('change', syncInvestmentFields);
    document.getElementById('fiWhatIfAfterTaxAssetType')?.addEventListener('change', () => {
      if (estimatedModeActive()) runSimulation();
    });
    document.getElementById('financialIncomeWhatIfForm')?.addEventListener('submit', event => {
      event.preventDefault();
      runSimulation();
    });
    document.querySelectorAll('[data-dividend-preset]').forEach(button => {
      button.addEventListener('click', () => {
        const input = document.getElementById('fiWhatIfExtraDividend');
        if (!input) return;
        input.value = button.dataset.dividendPreset || '0';
        runSimulation();
      });
    });

    syncHighDividendFields();
    syncInvestmentFields();
    syncVisibility();
    if (estimatedModeActive()) window.setTimeout(() => runSimulation(), 0);
  }

  function syncHighDividendFields() {
    const enabled = boolValue('fiWhatIfHighDividendEnabled');
    const fields = document.getElementById('fiWhatIfHighDividendFields');
    if (fields) fields.hidden = !enabled;
  }

  function syncInvestmentFields() {
    const enabled = boolValue('fiWhatIfInvestmentEnabled');
    const fields = document.getElementById('fiWhatIfInvestmentFields');
    if (fields) fields.hidden = !enabled;
    const etfWrap = document.getElementById('fiWhatIfEtfTaxGainWrap');
    const assetType = document.getElementById('fiWhatIfAssetType')?.value;
    if (etfWrap) etfWrap.hidden = assetType !== 'kr_listed_us_etf';
  }

  function syncVisibility() {
    const panel = document.getElementById('financialIncomeWhatIfPanel');
    if (!panel) return;
    panel.style.display = estimatedModeActive() ? 'block' : 'none';
  }

  function buildHighDividendScenario() {
    if (!boolValue('fiWhatIfHighDividendEnabled')) return null;
    return {
      special_dividend_income_krw: numberValue('fiWhatIfHighDividendAmount'),
      high_dividend_company_confirmed: boolValue('fiWhatIfHighDividendConfirmed'),
      separate_taxation_requested: boolValue('fiWhatIfHighDividendRequested'),
    };
  }

  function buildDashboardCashflowScenario() {
    if (boolValue('fiWhatIfInvestmentEnabled')) return null;
    const assetType = document.getElementById('fiWhatIfAfterTaxAssetType')?.value || '';
    const extraDividend = numberValue('fiWhatIfExtraDividend');
    if (!assetType || !(extraDividend > 0)) return null;
    return {
      asset_type: assetType,
      annual_distribution_krw: extraDividend,
      annual_realized_gain_krw: 0,
      existing_corporate_taxable_income_krw: 0,
      corporate_deductible_expenses_krw: 0,
      corporation_to_owner_distribution_krw: 0,
      domestic_dividend_exclusion_eligible: false,
      domestic_dividend_ownership_pct: 0,
      domestic_dividend_holding_months: 0,
      us_treaty_parent_rate_qualified: false,
      foreign_subsidiary_exclusion_qualified: false,
      foreign_ownership_pct: 0,
    };
  }

  function buildInvestmentScenario() {
    const dashboardScenario = buildDashboardCashflowScenario();
    if (dashboardScenario) return dashboardScenario;
    if (!boolValue('fiWhatIfInvestmentEnabled')) return null;
    const assetType = document.getElementById('fiWhatIfAssetType')?.value || 'domestic_dividend_stock';
    const etfInput = document.getElementById('fiWhatIfEtfTaxGain');
    const useQuickTrading = boolValue('fiWhatIfUseQuickTrading');
    let realizedGain = numberValue('fiWhatIfRealizedGain');
    if (useQuickTrading && assetType === 'us_direct' && realizedGain === 0) {
      realizedGain = numberValue('fiWhatIfForeignShareGain');
    }
    const scenario = {
      asset_type: assetType,
      annual_distribution_krw: numberValue('fiWhatIfDistribution'),
      annual_realized_gain_krw: realizedGain,
      existing_corporate_taxable_income_krw: numberValue('fiWhatIfCorporateBase'),
      corporate_deductible_expenses_krw: numberValue('fiWhatIfCorporateExpense'),
      corporation_to_owner_distribution_krw: numberValue('fiWhatIfOwnerDistribution'),
      domestic_dividend_exclusion_eligible: boolValue('fiWhatIfDomesticExclusionEligible'),
      domestic_dividend_ownership_pct: numberValue('fiWhatIfDomesticOwnership'),
      domestic_dividend_holding_months: numberValue('fiWhatIfDomesticHoldingMonths'),
      us_treaty_parent_rate_qualified: boolValue('fiWhatIfUsTreatyQualified'),
      foreign_subsidiary_exclusion_qualified: boolValue('fiWhatIfForeignSubsidiaryQualified'),
      foreign_ownership_pct: numberValue('fiWhatIfForeignOwnership'),
    };
    if (assetType === 'kr_listed_us_etf' && etfInput) {
      if (etfInput.value !== '') {
        scenario.taxable_etf_gain_krw = numberValue('fiWhatIfEtfTaxGain');
      } else if (useQuickTrading) {
        scenario.taxable_etf_gain_krw = numberValue('fiWhatIfKrOverseasEtfTaxableGain');
      }
    }
    return scenario;
  }

  function buildPayload() {
    const payload = {
      owner: currentOwnerValue(),
      additional_dividend_gross_krw: numberValue('fiWhatIfExtraDividend'),
      additional_interest_gross_krw: numberValue('fiWhatIfExtraInterest'),
      additional_foreign_share_realized_gain_krw: numberValue('fiWhatIfForeignShareGain'),
      additional_kr_listed_overseas_etf_taxable_gain_krw: numberValue('fiWhatIfKrOverseasEtfTaxableGain'),
    };
    const highDividendScenario = buildHighDividendScenario();
    if (highDividendScenario) payload.high_dividend_scenario = highDividendScenario;
    const investmentScenario = buildInvestmentScenario();
    if (investmentScenario) payload.investment_scenario = investmentScenario;
    return payload;
  }

  function validatePayload(payload) {
    const values = [
      payload.additional_dividend_gross_krw,
      payload.additional_interest_gross_krw,
      payload.additional_foreign_share_realized_gain_krw,
      payload.additional_kr_listed_overseas_etf_taxable_gain_krw,
      numberValue('fiWhatIfAfterTaxInvestment'),
    ];
    if (payload.high_dividend_scenario) values.push(payload.high_dividend_scenario.special_dividend_income_krw);
    if (payload.investment_scenario) {
      values.push(
        payload.investment_scenario.annual_distribution_krw,
        payload.investment_scenario.annual_realized_gain_krw,
        payload.investment_scenario.existing_corporate_taxable_income_krw,
        payload.investment_scenario.corporate_deductible_expenses_krw,
        payload.investment_scenario.corporation_to_owner_distribution_krw,
        payload.investment_scenario.domestic_dividend_ownership_pct,
        payload.investment_scenario.domestic_dividend_holding_months,
        payload.investment_scenario.foreign_ownership_pct,
      );
      if ('taxable_etf_gain_krw' in payload.investment_scenario) values.push(payload.investment_scenario.taxable_etf_gain_krw);
    }
    return values.every(value => Number.isFinite(Number(value)) && Number(value) >= 0);
  }

  async function runSimulation() {
    const status = document.getElementById('fiWhatIfStatus');
    const button = document.getElementById('fiWhatIfRun');
    const result = document.getElementById('financialIncomeWhatIfResult');
    if (!status || !button || !result || !estimatedModeActive()) return;

    const payload = buildPayload();
    if (!validatePayload(payload)) {
      status.textContent = '0 이상의 숫자만 입력하세요.';
      status.className = 'fi-what-if-status error';
      return;
    }

    button.disabled = true;
    status.textContent = '계산 중…';
    status.className = 'fi-what-if-status';
    try {
      const response = await fetch(API_PATH, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const code = data?.detail?.code || `HTTP_${response.status}`;
        throw new Error(code);
      }
      renderResult(data);
      status.textContent = '계산 완료';
      status.className = 'fi-what-if-status success';
    } catch (error) {
      result.innerHTML = `<div class="fi-what-if-error">계산하지 못했습니다. <code>${escapeHtml(error?.message || 'UNKNOWN')}</code></div>`;
      status.textContent = '계산 실패';
      status.className = 'fi-what-if-status error';
    } finally {
      button.disabled = false;
    }
  }

  function statusForScenario(scenarioState, watchState) {
    if (scenarioState.exceeded === true) return { className: 'danger', text: '2천만원 초과' };
    if (scenarioState.at_or_above === true) return { className: 'reached', text: '2천만원 도달 · 초과 아님' };
    if (watchState.at_or_above === true) return { className: 'approach', text: '2천만원 접근 구간' };
    if (scenarioState.exceeded === null) return { className: 'unknown', text: '예상치 확인 불가' };
    return { className: 'safe', text: '2천만원 기준 미만' };
  }

  function afterTaxAssetLabel(assetType) {
    if (assetType === 'domestic_dividend_stock') return '일반 국내 배당주';
    if (assetType === 'kr_listed_us_etf') return '국내상장 해외 ETF 분배금';
    if (assetType === 'us_direct') return '미국주식 · 미국 ETF 직투 배당';
    return '선택 안 함';
  }

  function afterTaxBasisNote(assetType) {
    if (assetType === 'domestic_dividend_stock') {
      return '일반 국내 배당 원천징수(국세 14% + 개인지방소득세 1.4%) 기준입니다.';
    }
    if (assetType === 'kr_listed_us_etf') {
      return '국내상장 해외 ETF의 알려진 원천징수 세금만 반영한 screening입니다.';
    }
    if (assetType === 'us_direct') {
      return '미국 일반 조약 원천징수 15%만 반영하며 한국 최종세액·외국납부세액공제는 계산하지 않습니다.';
    }
    return '';
  }

  function renderResult(data) {
    const root = document.getElementById('financialIncomeWhatIfResult');
    if (!root) return;

    const whatIf = data?.what_if || {};
    const threshold = whatIf?.thresholds?.comprehensive_tax || {};
    const baselineState = threshold?.baseline || {};
    const scenarioState = threshold?.scenario || {};
    const watchState = whatIf?.thresholds?.watch?.scenario || {};
    const status = statusForScenario(scenarioState, watchState);
    const baseline = whatIf.baseline_projected_gross_screening_income_krw;
    const projected = whatIf.scenario_projected_gross_screening_income_krw;
    const comprehensiveProjected = whatIf.scenario_comprehensive_tax_screening_income_krw;
    const additionalDividend = Number(whatIf.additional_dividend_gross_krw || 0);
    const totalAddition = Number(whatIf.scenario_addition_gross_krw || 0);
    const otherAddition = Math.max(totalAddition - additionalDividend, 0);
    const baselineRemaining = baselineState.remaining_krw;
    const scenarioRemaining = scenarioState.remaining_krw;

    const baselineRemainingText = baselineRemaining === null || baselineRemaining === undefined
      ? '예상치 확인 불가'
      : (baselineState.at_or_above ? '기준 도달' : money(baselineRemaining));
    const scenarioRemainingText = scenarioRemaining === null || scenarioRemaining === undefined
      ? '미래 배당 예측 데이터가 필요합니다.'
      : (scenarioState.exceeded === true
        ? '2천만원 기준을 초과했습니다.'
        : (scenarioState.at_or_above === true
          ? '2천만원 기준에 정확히 도달했습니다.'
          : `2천만원까지 ${money(scenarioRemaining)} 남음`));

    let html = `
      <div class="fi-result-grid dashboard">
        <div class="fi-result-card">
          <span>올해 예상 금융소득</span>
          <strong>${money(baseline)}</strong>
          <small>현재 실제 + 향후 예상</small>
        </div>
        <div class="fi-result-card ${baselineState.at_or_above ? 'warn' : 'safe'}">
          <span>2천만원까지 여유</span>
          <strong>${baselineRemainingText}</strong>
          <small>현재 예상 기준</small>
        </div>
        <div class="fi-result-card emphasized">
          <span>추가 배당 가정</span>
          <strong>${money(additionalDividend)}</strong>
          <small>${otherAddition > 0 ? `기타 금융소득 가정 ${money(otherAddition)} 별도` : '배당만 빠르게 비교'}</small>
        </div>
        <div class="fi-result-card ${status.className}">
          <span>배당 추가 후 예상 금융소득</span>
          <strong>${money(projected)}</strong>
          <small>${status.text} · ${scenarioRemainingText}</small>
        </div>
      </div>
    `;

    const crossed = threshold?.crossed_by_scenario === true;
    if (scenarioState.exceeded === true) {
      html += `
        <div class="fi-decision-note danger">
          <strong>${crossed ? '추가 배당으로 2천만원 기준을 넘습니다.' : '적용 후 예상 금융소득이 2천만원 기준을 초과합니다.'}</strong>
          <span>이 화면은 자산배분 판단용 screening입니다. 종합소득 최종 신고세액을 확정하는 계산서는 아닙니다.</span>
        </div>
      `;
    } else if (additionalDividend > 0 && scenarioState.at_or_above === true) {
      html += `
        <div class="fi-decision-note reached">
          <strong>추가 배당 후 2천만원 기준에 도달합니다.</strong>
          <span>초과는 아니지만 추가 금융소득이 생기면 기준을 넘을 수 있습니다.</span>
        </div>
      `;
    } else if (additionalDividend > 0 && watchState.at_or_above === true) {
      html += `
        <div class="fi-decision-note approach">
          <strong>2천만원 기준에 가까워지고 있습니다.</strong>
          <span>${scenarioRemainingText}</span>
        </div>
      `;
    } else if (additionalDividend > 0 && scenarioState.exceeded === false) {
      html += `
        <div class="fi-decision-note safe">
          <strong>현재 가정에서는 2천만원 기준 미만입니다.</strong>
          <span>${scenarioRemainingText}</span>
        </div>
      `;
    }

    const comparison = data?.investment_comparison;
    const afterTaxAssetType = document.getElementById('fiWhatIfAfterTaxAssetType')?.value || '';
    const advancedInvestmentEnabled = boolValue('fiWhatIfInvestmentEnabled');
    if (comparison && afterTaxAssetType && !advancedInvestmentEnabled) {
      const individual = comparison.individual || {};
      const taxes = individual.taxes || {};
      const knownTax = Number(taxes.known_tax_total_krw || 0);
      const afterKnownTaxCash = Number(individual.after_known_tax_cash_krw || 0);
      const investmentAmount = numberValue('fiWhatIfAfterTaxInvestment');
      const afterTaxYield = investmentAmount > 0 ? (afterKnownTaxCash / investmentAmount) * 100 : null;
      const comprehensiveWarning = individual.comprehensive_tax_screening === true
        ? ' 금융소득 2천만원 초과 screening 상태이므로 최종 종합소득세는 별도입니다.'
        : '';
      html += `
        <div class="fi-compare-block">
          <div class="fi-compare-title"><strong>추가 배당 세후 현금흐름</strong><span>${afterTaxAssetLabel(afterTaxAssetType)} · screening-only</span></div>
          <div class="fi-result-grid dashboard">
            <div class="fi-result-card"><span>세전 추가 배당</span><strong>${money(additionalDividend)}</strong><small>사용자 가정</small></div>
            <div class="fi-result-card"><span>알려진 원천징수·세금</span><strong>${money(knownTax)}</strong><small>최종 신고세액 아님</small></div>
            <div class="fi-result-card emphasized"><span>원천징수 후 예상 수령액</span><strong>${money(afterKnownTaxCash)}</strong><small>현재 알려진 세금만 차감</small></div>
            <div class="fi-result-card"><span>원천징수 후 배당수익률</span><strong>${afterTaxYield === null ? '투자금액 입력 필요' : percent(afterTaxYield)}</strong><small>원천징수 후 현금 ÷ 투자금액</small></div>
          </div>
          <div class="fi-compare-meta">${afterTaxBasisNote(afterTaxAssetType)}${comprehensiveWarning}</div>
        </div>
      `;
    }

    const tradingImpact = whatIf?.trading_impact;
    if (tradingImpact && (Number(tradingImpact?.foreign_shares?.realized_gain_krw || 0) > 0 || Number(tradingImpact?.kr_listed_overseas_etf?.taxable_gain_krw || 0) > 0)) {
      const foreign = tradingImpact.foreign_shares || {};
      const etf = tradingImpact.kr_listed_overseas_etf || {};
      const foreignTaxText = foreign.capital_gain_tax_calculated === false
        ? '금융소득 판정 미포함 · 양도세 미계산'
        : '금융소득 판정 미포함';
      html += `
        <div class="fi-compare-block">
          <div class="fi-compare-title"><strong>다른 가정의 영향</strong><span>배당 판단과 분리해서 봅니다.</span></div>
          <div class="fi-result-grid comparison">
            <div class="fi-result-card"><span>해외주식 실현차익</span><strong>${money(foreign.realized_gain_krw || 0)}</strong><small>${foreignTaxText}</small></div>
            <div class="fi-result-card"><span>해외 ETF 과세기준금액</span><strong>${money(etf.taxable_gain_krw || 0)}</strong><small>금융소득에 포함</small></div>
            <div class="fi-result-card"><span>ETF 예상 원천징수</span><strong>${money(etf.estimated_withholding_krw || 0)}</strong><small>screening · 최종세액 아님</small></div>
          </div>
        </div>
      `;
    }

    const highDividend = whatIf?.high_dividend_special_tax;
    if (highDividend) {
      const applied = highDividend.special_rule_applied === true;
      html += `
        <div class="fi-compare-block">
          <div class="fi-compare-title"><strong>2026 고배당기업 분리과세 특례</strong><span>${applied ? '특례 적용 가정' : '특례 미적용'} · screening-only</span></div>
          <div class="fi-result-grid comparison">
            <div class="fi-result-card"><span>공식 공시 확인</span><strong>${highDividend.high_dividend_company_confirmed_by_user === true ? '확인함' : '미확인'}</strong><small>앱 자동 적격판정 아님</small></div>
            <div class="fi-result-card"><span>2천만원 판정 제외액</span><strong>${money(highDividend.excluded_from_comprehensive_tax_threshold_krw || 0)}</strong><small>종합과세 판정대상 ${money(comprehensiveProjected)}</small></div>
            <div class="fi-result-card"><span>특례 국세 예상액</span><strong>${money(highDividend.national_income_tax_krw)}</strong><small>지방소득세·최종 신고세액 미포함</small></div>
          </div>
        </div>
      `;
    }

    if (comparison && advancedInvestmentEnabled) {
      const compare = comparison.comparison || {};
      const individual = Number(compare.individual_known_after_tax_value_krw || 0);
      const corporation = Number(compare.family_corporation_known_after_tax_value_krw || 0);
      const difference = Number(compare.family_corporation_minus_individual_krw || 0);
      const winner = difference > 0 ? '가족법인' : (difference < 0 ? '개인' : '동일');
      const diffClass = difference > 0 ? 'gain' : (difference < 0 ? 'loss' : '');
      const ownerLayer = comparison.corporation_to_owner || {};
      html += `
        <div class="fi-compare-block">
          <div class="fi-compare-title"><strong>투자방법 고급 비교</strong><span>필요할 때만 참고 · screening-only</span></div>
          <div class="fi-result-grid comparison">
            <div class="fi-result-card"><span>개인 투자 세후 알려진 금액</span><strong>${money(individual)}</strong></div>
            <div class="fi-result-card"><span>가족법인 세후 알려진 금액</span><strong>${money(corporation)}</strong><small>법인 유보 + 개인 배당 실수령</small></div>
            <div class="fi-result-card ${diffClass}"><span>현재 가정 우세</span><strong>${winner}</strong><small>가족법인 - 개인 ${difference >= 0 ? '+' : ''}${money(difference)}</small></div>
          </div>
          <div class="fi-compare-meta">법인 내부 유보 ${money(ownerLayer.retained_in_corporation_krw || 0)} · 개인 배당 실수령 ${money(ownerLayer.owner_cash_after_withholding_krw || 0)}</div>
        </div>
      `;
    }

    html += `
      <div class="fi-what-if-disclaimer">
        이 화면은 배당·금융소득 자산관리 의사결정용입니다. 세후 표시는 현재 확인 가능한 원천징수·알려진 세금만 반영한 현금흐름 screening이며, 종합소득세 신고서의 모든 공제·기납부세액·가산세 또는 최종 납부·환급세액을 확정하지 않습니다.
      </div>
    `;
    root.innerHTML = html;
  }

  function attachGlobalListeners() {
    document.addEventListener('click', event => {
      const modeTab = event.target.closest?.('#dividendModeTabs .heatmap-tab');
      if (modeTab) {
        window.setTimeout(() => {
          syncVisibility();
          if (estimatedModeActive()) runSimulation();
        }, 0);
        return;
      }
      const ownerTab = event.target.closest?.('.family-tabs .family-tab');
      if (ownerTab && estimatedModeActive()) window.setTimeout(() => runSimulation(), 0);
    });
  }

  function init() {
    mountPanel();
    attachGlobalListeners();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
