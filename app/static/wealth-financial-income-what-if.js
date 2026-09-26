(() => {
  'use strict';

  const API_PATH = '/api/dividends/financial-income-what-if';

  function money(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '확인 불가';
    return `₩${Math.round(Number(value)).toLocaleString('ko-KR')}`;
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

  function panelMarkup() {
    return `
      <section id="financialIncomeWhatIfPanel" class="fi-what-if-panel" aria-label="금융소득 What-if 시뮬레이터">
        <div class="fi-what-if-head">
          <div>
            <span class="fi-what-if-kicker">FINANCIAL INCOME WHAT-IF</span>
            <h3>금융소득 영향 · 개인 vs 가족법인</h3>
            <p>현재 예상 금융소득에 추가 배당·이자를 가정하고, 같은 투자수익을 개인과 가족법인으로 비교합니다.</p>
          </div>
          <span class="fi-what-if-badge">저장 안 함 · 2026 screening</span>
        </div>

        <form id="financialIncomeWhatIfForm" class="fi-what-if-form">
          <div class="fi-what-if-section">
            <div class="fi-what-if-section-title">
              <strong>빠른 금융소득 시나리오</strong>
              <small>현재 보유자산의 실제+예상 금융소득을 기준으로 계산합니다.</small>
            </div>
            <div class="fi-what-if-grid two">
              <label>
                <span>추가 배당 가정</span>
                <input id="fiWhatIfExtraDividend" type="number" min="0" step="10000" value="0" inputmode="numeric" />
                <small>세전 원화 기준</small>
              </label>
              <label>
                <span>추가 이자 가정</span>
                <input id="fiWhatIfExtraInterest" type="number" min="0" step="10000" value="0" inputmode="numeric" />
                <small>세전 원화 기준</small>
              </label>
            </div>
          </div>

          <div class="fi-what-if-section">
            <label class="fi-what-if-toggle">
              <input id="fiWhatIfInvestmentEnabled" type="checkbox" />
              <span>
                <strong>개인 vs 가족법인 투자방법도 비교</strong>
                <small>국내 배당주 · 국내상장 미국 ETF · 미국직투</small>
              </span>
            </label>

            <div id="fiWhatIfInvestmentFields" class="fi-what-if-investment-fields" hidden>
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

          <div class="fi-what-if-actions">
            <button id="fiWhatIfRun" type="submit" class="button primary">계산</button>
            <span id="fiWhatIfStatus" class="fi-what-if-status" role="status"></span>
          </div>
        </form>

        <div id="financialIncomeWhatIfResult" class="fi-what-if-result" aria-live="polite">
          <div class="fi-what-if-placeholder">예상 탭에서 계산하면 결과가 여기에 표시됩니다.</div>
        </div>
      </section>
    `;
  }

  function mountPanel() {
    if (document.getElementById('financialIncomeWhatIfPanel')) return;
    const summary = document.querySelector('#dividendPanel .dividend-summary-cards');
    if (!summary) return;
    summary.insertAdjacentHTML('afterend', panelMarkup());

    document.getElementById('fiWhatIfInvestmentEnabled')?.addEventListener('change', syncInvestmentFields);
    document.getElementById('fiWhatIfAssetType')?.addEventListener('change', syncInvestmentFields);
    document.getElementById('financialIncomeWhatIfForm')?.addEventListener('submit', event => {
      event.preventDefault();
      runSimulation();
    });
    syncInvestmentFields();
    syncVisibility();
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

  function buildInvestmentScenario() {
    if (!boolValue('fiWhatIfInvestmentEnabled')) return null;
    const assetType = document.getElementById('fiWhatIfAssetType')?.value || 'domestic_dividend_stock';
    const etfInput = document.getElementById('fiWhatIfEtfTaxGain');
    const scenario = {
      asset_type: assetType,
      annual_distribution_krw: numberValue('fiWhatIfDistribution'),
      annual_realized_gain_krw: numberValue('fiWhatIfRealizedGain'),
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
    if (assetType === 'kr_listed_us_etf' && etfInput && etfInput.value !== '') {
      scenario.taxable_etf_gain_krw = numberValue('fiWhatIfEtfTaxGain');
    }
    return scenario;
  }

  function validatePayload(payload) {
    const values = [
      payload.additional_dividend_gross_krw,
      payload.additional_interest_gross_krw,
    ];
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
      if ('taxable_etf_gain_krw' in payload.investment_scenario) {
        values.push(payload.investment_scenario.taxable_etf_gain_krw);
      }
    }
    return values.every(value => Number.isFinite(Number(value)) && Number(value) >= 0);
  }

  async function runSimulation() {
    const status = document.getElementById('fiWhatIfStatus');
    const button = document.getElementById('fiWhatIfRun');
    const result = document.getElementById('financialIncomeWhatIfResult');
    if (!status || !button || !result || !estimatedModeActive()) return;

    const payload = {
      owner: currentOwnerValue(),
      additional_dividend_gross_krw: numberValue('fiWhatIfExtraDividend'),
      additional_interest_gross_krw: numberValue('fiWhatIfExtraInterest'),
    };
    const investmentScenario = buildInvestmentScenario();
    if (investmentScenario) payload.investment_scenario = investmentScenario;

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

  function escapeHtml(value) {
    return String(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function renderResult(data) {
    const root = document.getElementById('financialIncomeWhatIfResult');
    if (!root) return;
    const whatIf = data?.what_if || {};
    const threshold = whatIf?.thresholds?.comprehensive_tax || {};
    const scenarioState = threshold?.scenario || {};
    const projected = whatIf.scenario_projected_gross_screening_income_krw;
    const baseline = whatIf.baseline_projected_gross_screening_income_krw;
    const remaining = scenarioState.remaining_krw;

    let statusClass = 'safe';
    let statusText = '2천만원 기준 미만';
    if (scenarioState.exceeded === true) {
      statusClass = 'danger';
      statusText = '2천만원 초과';
    } else if (scenarioState.at_or_above === true) {
      statusClass = 'warn';
      statusText = '2천만원 도달 · 초과 아님';
    } else if (projected !== null && Number(projected) >= 10_000_000) {
      statusClass = 'warn';
      statusText = '주의 구간';
    } else if (scenarioState.exceeded === null) {
      statusClass = 'unknown';
      statusText = '예상치 확인 불가';
    }

    let html = `
      <div class="fi-result-grid">
        <div class="fi-result-card">
          <span>현재 연간 예상</span>
          <strong>${money(baseline)}</strong>
          <small>실제 + 향후 예상 기준</small>
        </div>
        <div class="fi-result-card emphasized">
          <span>What-if 적용 후</span>
          <strong>${money(projected)}</strong>
          <small>추가 가정 ${money(whatIf.scenario_addition_gross_krw || 0)}</small>
        </div>
        <div class="fi-result-card ${statusClass}">
          <span>금융소득 종합과세 screening</span>
          <strong>${statusText}</strong>
          <small>${remaining === null || remaining === undefined ? '미래 배당 예측 데이터가 필요합니다.' : `2천만원까지 ${money(remaining)}`}</small>
        </div>
      </div>
    `;

    const comparison = data?.investment_comparison;
    if (comparison) {
      const compare = comparison.comparison || {};
      const individual = Number(compare.individual_known_after_tax_value_krw || 0);
      const corporation = Number(compare.family_corporation_known_after_tax_value_krw || 0);
      const difference = Number(compare.family_corporation_minus_individual_krw || 0);
      const winner = difference > 0 ? '가족법인' : (difference < 0 ? '개인' : '동일');
      const diffClass = difference > 0 ? 'gain' : (difference < 0 ? 'loss' : '');
      const ownerLayer = comparison.corporation_to_owner || {};
      html += `
        <div class="fi-compare-block">
          <div class="fi-compare-title">
            <strong>투자방법 비교</strong>
            <span>screening-only · 최종 종합소득세/건보료 미포함</span>
          </div>
          <div class="fi-result-grid comparison">
            <div class="fi-result-card">
              <span>개인 투자 세후 알려진 금액</span>
              <strong>${money(individual)}</strong>
            </div>
            <div class="fi-result-card">
              <span>가족법인 세후 알려진 금액</span>
              <strong>${money(corporation)}</strong>
              <small>법인 유보 + 개인 배당 실수령 합계</small>
            </div>
            <div class="fi-result-card ${diffClass}">
              <span>현재 가정 우세</span>
              <strong>${winner}</strong>
              <small>가족법인 - 개인 ${difference >= 0 ? '+' : ''}${money(difference)}</small>
            </div>
          </div>
          <div class="fi-compare-meta">
            법인 내부 유보 ${money(ownerLayer.retained_in_corporation_krw || 0)} · 개인 배당 실수령 ${money(ownerLayer.owner_cash_after_withholding_krw || 0)}
          </div>
        </div>
      `;
    }

    html += `
      <div class="fi-what-if-disclaimer">
        이 결과는 2026년 기준 사전 screening입니다. 금융소득 종합과세 최종세액, 고배당 특례, 건강보험료, 급여·퇴직금 인출, 증여·상속세는 포함하지 않습니다.
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
      if (ownerTab && estimatedModeActive()) {
        window.setTimeout(() => runSimulation(), 0);
      }
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
