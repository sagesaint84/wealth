(() => {
  'use strict';

  const API_PATH = '/api/dividends/financial-income-what-if';
  const DIVIDEND_PRESETS = [1e6, 5e6, 10e6];
  let visibilityContext = '';
  let simulationRevision = 0;
  let visibilityOwner = '';

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
    try {
      if (typeof currentDividendMode === 'string') return currentDividendMode === 'estimated';
    } catch (_) { /* Core initialization has not completed yet. */ }
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
      <section id="financialIncomeWhatIfPanel" class="fi-what-if-panel" aria-label="배당 세금 대시보드" hidden>
        <div class="fi-what-if-head">
          <div>
            <span class="fi-what-if-kicker">DIVIDEND TAX DASHBOARD</span>
            <h3>배당 세금 대시보드</h3>
            <p>올해 예상 금융소득과 2천만원 기준까지의 여유를 보고, 배당을 더 받을 때 세전·원천징수 후 현금흐름이 어떻게 달라지는지 빠르게 확인합니다.</p>
          </div>
          <span class="fi-what-if-badge">자산관리용 · 저장 안 함</span>
        </div>

        <section id="dividendBenefitPreview" class="fi-benefits" aria-label="배당 이벤트 예상 혜택"></section>
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
      runSimulation();
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
    const taxBody = document.getElementById('taxWorkspaceBody');
    const accounts = document.getElementById('accountsPanel');
    const taxActive = Boolean(taxBody && accounts?.getClientRects().length &&
      window.WealthTaxWorkspace?.isActive?.());
    const summary = document.querySelector('#dividendPanel .dividend-summary-cards');
    if (taxActive && panel.parentElement !== taxBody) taxBody.appendChild(panel);
    else if (!taxActive && summary && panel.parentElement !== summary.parentElement) {
      summary.insertAdjacentElement('afterend', panel);
    }
    const context = taxActive ? 'tax' : (estimatedModeActive() ? 'estimated' : 'actual');
    const owner = currentOwnerValue();
    if (context !== visibilityContext || owner !== visibilityOwner) {
      visibilityContext = context;
      visibilityOwner = owner;
      simulationRevision++;
      const button = document.getElementById('fiWhatIfRun');
      const status = document.getElementById('fiWhatIfStatus');
      if (button) button.disabled = false;
      if (status) { status.textContent = ''; status.className = 'fi-what-if-status'; }
    }
    const visible = context !== 'actual';
    panel.hidden = !visible;
    panel.style.display = visible ? 'block' : 'none';
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
    const year = Number(document.getElementById('fiBenefitYear')?.value || new Date().getFullYear());
    const today = new Date().toLocaleDateString('en-CA', {timeZone:'Asia/Seoul'});
    if (year !== Number(today.slice(0, 4))) payload.as_of = `${year}-12-31`;
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
    syncVisibility();
    if (!status || !button || !result || visibilityContext === 'actual'
        || globalThis.WealthStartup?.visible('financialIncomeWhatIfPanel') === false) return;
    const revision = ++simulationRevision;
    const owner = currentOwnerValue();

    const payload = buildPayload();
    if (!validatePayload(payload)) {
      button.disabled = false;
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
      syncVisibility();
      if (revision !== simulationRevision || owner !== currentOwnerValue() || globalThis.WealthStartup?.visible('financialIncomeWhatIfPanel') === false) return;
      if (!response.ok) {
        const code = data?.detail?.code || `HTTP_${response.status}`;
        throw new Error(code);
      }
      renderResult(data);
      status.textContent = '계산 완료';
      status.className = 'fi-what-if-status success';
    } catch (error) {
      syncVisibility();
      if (revision !== simulationRevision || owner !== currentOwnerValue() || globalThis.WealthStartup?.visible('financialIncomeWhatIfPanel') === false) return;
      result.innerHTML = `<div class="fi-what-if-error">계산하지 못했습니다. <code>${escapeHtml(error?.message || 'UNKNOWN')}</code></div>`;
      status.textContent = '계산 실패';
      status.className = 'fi-what-if-status error';
    } finally {
      syncVisibility();
      if (revision === simulationRevision && owner === currentOwnerValue()) button.disabled = false;
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

  function registeredThresholdHtml(summary, owner, year) {
    if (!summary) return '';
    const personal = summary.personal_threshold_applied === true;
    const status = personal ? summary.status : '가족 참고 합계 · 개인별 기준은 구성원별 확인';
    const metrics = [['전체 세전 금융소득', summary.total_gross_krw],
      ['감액배당 비과세 제외금액', summary.capital_excluded_krw],
      ['고배당 분리과세 제외금액', summary.high_dividend_excluded_krw],
      ['종합과세 기준 포함액', summary.included_krw],
      ...(personal ? [['2천만원 기준까지 남은 금액', summary.remaining_krw]] : [])];
    return `<section aria-label="등록된 실제 금융소득 기준 집계"><strong>${escapeHtml(owner)} · ${escapeHtml(year)}년 실제 등록 기록</strong>
      <div class="fi-result-grid dashboard">${metrics.map(([label, amount]) => `<div class="fi-result-card"><span>${escapeHtml(label)}</span><strong>${money(amount)}</strong></div>`).join('')}
      <div class="fi-result-card ${personal ? (summary.exceeded ? 'warn' : 'safe') : ''}"><strong>${escapeHtml(status)}</strong></div></div>
      <small>등록된 자료 기준 예상 · 실제 입금·원천징수 기록은 변경하지 않습니다.${summary.high_dividend_special_tax?.special_rule_applied ? ` 고배당 신고 가정 국세 ${money(summary.high_dividend_special_tax.national_income_tax_krw)} (지방세 별도)` : ''}</small></section>`;
  }

  function renderResult(data) {
    const root = document.getElementById('financialIncomeWhatIfResult');
    if (!root) return;

    const actualHtml = registeredThresholdHtml(data?.baseline_projection?.actual_financial_income, data?.owner, data?.baseline_projection?.year);
    if (data?.baseline_projection?.owner === '모두') {
      root.innerHTML = actualHtml + '<p>가족 합계에는 개인별 2천만원 기준을 적용하지 않습니다. 소유자를 선택해 확인하세요.</p>';
      return;
    }
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

    let html = actualHtml + `
      <div class="fi-result-grid dashboard">
        <div class="fi-result-card">
          <span>연말 예상 기준 포함액</span>
          <strong>${money(baseline)}</strong>
          <small>현재 실제 + 향후 예상</small>
        </div>
        <div class="fi-result-card ${baselineState.exceeded ? 'warn' : 'safe'}">
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
          <span>추가 가정 후 기준 포함액</span>
          <strong>${money(comprehensiveProjected)}</strong>
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

  // Session-memory only. The server supplies an authenticated-user/owner/year
  // context key; official status is never read from the selection map.
  const benefitChoices = new Map();
  let benefitModel = null;
  let benefitRevision = 0;

  function benefitLink(value) {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && ['dart.fss.or.kr', 'opendart.fss.or.kr', 'kind.krx.co.kr'].includes(url.hostname)
        && !url.username ? url.href : null;
    } catch (_) { return null; }
  }

  function renderBenefits(model) {
    const root = document.getElementById('dividendBenefitPreview');
    if (!root || !model) { if (root) root.replaceChildren(); return; }
    root.removeAttribute('aria-busy');
    const cards = (model.events || []).map((event, index) => {
      const controls = ['capital', 'high_dividend'].map(kind => {
        const view = event[kind];
        const id = `fiBenefit-${index}-${kind}`;
        const link = benefitLink(view.source_url);
        const officialStatus = { official_qualified: '공식 고배당기업 해당', official_not_qualified: '공식 고배당기업 미해당',
          not_assessed: '세금 적용 요건 미확인', not_confirmed: '공식 근거 미확인',
          source_unavailable: '공식 근거 조회 불가', eligibility_confirmed: '적용 근거 확인' }[view.official_status] || '공식 근거 미확인';
        return `<fieldset class="fi-benefit-choice"><legend>${kind === 'capital' ? '감액배당 예상 효과' : '고배당기업 분리과세'}</legend>
          <span>${escapeHtml(view.official_eligible ? '공식 근거·적용 범위 확인' : '적용 요건 미확인')} · ${escapeHtml(officialStatus)}</span>
          <div><label for="${id}"><input id="${id}" type="checkbox" data-benefit-index="${index}" data-benefit-kind="${kind}" ${view.applied || view.needs_amount ? 'checked' : ''} ${model.supported_year ? '' : 'disabled'}> 예상 혜택 적용</label>
          <button type="button" data-benefit-auto="${index}" data-benefit-kind="${kind}" ${model.supported_year ? '' : 'disabled'}>자동</button></div>
          <small>${view.mode === 'AUTO' ? 'AUTO' : view.mode === 'MANUAL_OFF' ? '사용자 제외' : view.assumed ? '사용자 가정 적용' : '사용자 적용'} · 대상 ${money(view.applied_amount_krw)}${view.overlap_removed ? ' · 감액배당 중복분 제외' : ''}</small>
          ${view.mode === 'MANUAL_ON' ? `<label for="${id}-amount">혜택 대상 금액(원)<input id="${id}-amount" data-benefit-amount="${index}" data-benefit-kind="${kind}" type="number" min="0" max="${escapeHtml(event.gross_amount_krw)}" step="1" inputmode="numeric" value="${view.selected_amount_krw === null ? '' : escapeHtml(view.selected_amount_krw)}" placeholder="대상 금액 직접 입력" required></label>` : ''}
          ${view.needs_amount ? '<strong role="status">대상 금액을 입력해야 계산할 수 있습니다.</strong>' : ''}
          ${link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">공식 공시 원문 ↗</a>` : ''}
        </fieldset>`;
      }).join('');
      return `<article class="fi-benefit-card"><strong>${escapeHtml(event.name)} (${escapeHtml(event.code)})</strong>
        <div>${escapeHtml(event.payment_date || '지급일 미확인')} · 세전 예상 ${money(event.gross_amount_krw)}</div>${controls}
        <div>감액배당 예상 원천징수 부담 차이 ${money(event.estimated_capital_withholding_difference_krw)}</div></article>`;
    }).join('');
    root.innerHTML = `<div class="fi-benefit-head"><strong>이벤트별 예상 세금 혜택</strong><span>기본 세후 카드와 별도 계산 · 자동 합산 없음 · 화면 세션 내 선택 · 실제 기록 변경 없음</span></div>
      <div class="fi-benefit-scope"><label>소유자 <select id="fiBenefitOwner"><option value="모두">소유자 선택</option>${(model.owners || []).map(owner => `<option value="${escapeHtml(owner)}" ${owner === model.owner ? 'selected' : ''}>${escapeHtml(owner)}</option>`).join('')}</select></label>
      <label>과세연도 <select id="fiBenefitYear">${[2025, 2026, 2027].map(year => `<option ${year === model.tax_year ? 'selected' : ''}>${year}</option>`).join('')}</select></label></div>
      <p>${model.requires_owner ? '소유자를 선택하면 해당 소유자의 배당 이벤트를 확인합니다.' : !model.supported_year ? '현재 계산기는 2026년만 지원합니다. 다른 연도에 혜택을 자동 적용하지 않습니다.' : '근거 부족 시 일반 배당으로 계산합니다. 직접 적용하면 사용자 가정으로 구분합니다.'}</p>
      <div class="fi-benefit-grid">${cards || (model.requires_owner ? '' : '<p>해당 연도의 계산 가능한 배당 이벤트가 없습니다.</p>')}</div>
      ${model.events?.length ? `<p>선택 이벤트 일반배당 과세 검토액 ${money(model.general_taxable_dividend_krw)} · 감액배당 예상 부담 차이 ${money(model.estimated_capital_withholding_difference_krw)} · 고배당기업 국세 ${money(model.high_dividend_national_tax_krw)} · 일반 원천징수 국세 대비 차이 ${money(model.high_dividend_national_difference_vs_withholding_krw)}${model.needs_amount ? ' (입력 전 부분 계산)' : ''}</p>
      <small>고배당기업은 신고 시 분리과세 신청이 필요합니다. 국세만 단순 비교하며 지방세·종합과세와의 유불리를 확정하지 않습니다. 실제 원천징수·입금 기록은 바꾸지 않습니다.</small>` : ''}
      <div id="fiBenefitStatus" role="status" aria-live="polite"></div>`;
  }

  async function requestBenefits(owner, year, choices = null) {
    const revision = ++benefitRevision;
    const root = document.getElementById('dividendBenefitPreview');
    if (!root || globalThis.WealthStartup?.visible('dividendBenefitPreview') === false) return;
    // Remove the old owner's figures while a different scope is loading.
    root.setAttribute('aria-busy', 'true');
    const differentScope = owner !== benefitModel?.owner || year !== benefitModel?.tax_year;
    if (differentScope) root.replaceChildren(Object.assign(document.createElement('p'), { textContent: '예상 혜택 계산 중…' }));
    try {
      const response = await fetch('/api/dividends/tax-benefit-preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
        body: JSON.stringify({ owner, tax_year: year, selections: choices || {},
          ...(choices ? { context_key: benefitModel?.context_key } : {}) }),
      });
      if (!response.ok) throw new Error('계산 요청을 확인할 수 없습니다. 다시 선택해 주세요.');
      const result = await response.json();
      if (revision !== benefitRevision) return;
      benefitModel = result;
      if (choices === null && benefitChoices.has(result.context_key)) {
        const scoped = currentBenefitChoices(result);
        if (scoped) return requestBenefits(owner, year, scoped);
      }
      renderBenefits(result);
    } catch (error) {
      if (revision !== benefitRevision) return;
      if (differentScope) {
        benefitModel = { ...benefitModel, owner, tax_year: year, events: [], requires_owner: owner === '모두' };
        renderBenefits(benefitModel);
      }
      const status = document.getElementById('fiBenefitStatus');
      if (status) status.textContent = '계산 실패: 선택 초안은 유지했습니다. 다시 선택하거나 자동으로 복원해 주세요.';
    } finally {
      if (revision === benefitRevision) root.removeAttribute('aria-busy');
    }
  }

  function currentBenefitChoices(model) {
    const keys = new Set((model.events || []).map(event => event.key));
    const scoped = Object.fromEntries(Object.entries(benefitChoices.get(model.context_key) || {})
      .filter(([key]) => keys.has(key)));
    benefitChoices.set(model.context_key, scoped);
    return Object.keys(scoped).length ? scoped : null;
  }

  function receiveBenefits(model) {
    ++benefitRevision;
    benefitModel = model;
    renderBenefits(model);
    if (model && benefitChoices.has(model.context_key)) {
      const scoped = currentBenefitChoices(model);
      if (scoped) requestBenefits(model.owner, model.tax_year, scoped);
    }
  }

  document.addEventListener('change', event => {
    if (event.target.id === 'fiBenefitOwner' || event.target.id === 'fiBenefitYear') {
      const owner = document.getElementById('fiBenefitOwner')?.value || '모두';
      const year = Number(document.getElementById('fiBenefitYear')?.value || 2026);
      requestBenefits(owner, year);
      return;
    }
    const target = event.target.closest?.('[data-benefit-index], [data-benefit-amount]');
    if (!target || !benefitModel) return;
    const index = Number(target.dataset.benefitIndex ?? target.dataset.benefitAmount);
    const eventModel = benefitModel.events[index];
    if (!eventModel) return;
    const kind = target.dataset.benefitKind;
    const choices = structuredClone(benefitChoices.get(benefitModel.context_key) || {});
    const choice = (choices[eventModel.key] ||= {});
    choice[kind] = target.dataset.benefitAmount !== undefined
      ? { mode: 'MANUAL_ON', ...(target.value === '' ? {} : { amount_krw: Number(target.value) }) }
      : { mode: target.checked ? 'MANUAL_ON' : 'MANUAL_OFF' };
    benefitChoices.set(benefitModel.context_key, choices);
    requestBenefits(benefitModel.owner, benefitModel.tax_year, choices);
  });
  document.addEventListener('click', event => {
    const target = event.target.closest?.('[data-benefit-auto]');
    if (!target || !benefitModel) return;
    const row = benefitModel.events[Number(target.dataset.benefitAuto)];
    const choices = structuredClone(benefitChoices.get(benefitModel.context_key) || {});
    (choices[row.key] ||= {})[target.dataset.benefitKind] = { mode: 'AUTO' };
    benefitChoices.set(benefitModel.context_key, choices);
    requestBenefits(benefitModel.owner, benefitModel.tax_year, choices);
  });
  document.addEventListener('change', event => {if (event.target.id === 'fiBenefitYear') runSimulation();});
  window.addEventListener('wealth:dividend-benefits', event => receiveBenefits(event.detail));

  function attachGlobalListeners() {
    document.addEventListener('click', event => {
      const modeTab = event.target.closest?.('#dividendModeTabs .heatmap-tab');
      if (modeTab) {
        syncVisibility();
        window.setTimeout(() => {
          syncVisibility();
          if (estimatedModeActive()) runSimulation();
        }, 0);
        return;
      }
      const ownerTab = event.target.closest?.('.family-tabs .family-tab');
      if (ownerTab) {
        syncVisibility();
        if (estimatedModeActive()) window.setTimeout(() => runSimulation(), 0);
      }
    });
  }

  function init() {
    mountPanel();
    attachGlobalListeners();
    receiveBenefits(window.WealthDividendBenefitData || null);
    // Observe only mode/category selection, never panel moves or result markup.
    const observer = new MutationObserver(syncVisibility);
    const modeTabs = document.getElementById('dividendModeTabs');
    const categoryTabs = document.querySelector('.account-cat-tab')?.parentElement;
    for (const tabs of [modeTabs, categoryTabs]) {
      if (tabs) observer.observe(tabs, {subtree: true, attributes: true, attributeFilter: ['class']});
    }
    window.addEventListener('wealth:view', syncVisibility);
    const loadEstimated = () => { syncVisibility(); if (visibilityContext === 'estimated') void runSimulation(); };
    window.addEventListener('wealth:assets-ready', loadEstimated);
    window.addEventListener('wealth:view', loadEstimated);
  }

  window.WealthFinancialIncomeWhatIf = { syncVisibility, runSimulation, registeredThresholdHtml };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
