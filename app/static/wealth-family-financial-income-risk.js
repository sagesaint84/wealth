(() => {
  'use strict';

  const API_PATH = '/api/dividends/financial-income-family-risk';
  let loading = false;
  let loadedOnce = false;
  let relayoutQueued = false;
  let whatIfSpoofSnapshot = null;

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function money(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) {
      return '확인 불가';
    }
    return `₩${Math.round(Number(value)).toLocaleString('ko-KR')}`;
  }

  function taxWorkspaceActive() {
    return document.querySelector('.account-cat-tab.active')?.dataset?.cat === 'tax';
  }

  function ensureTaxWorkspace() {
    const realEstatePanel = document.getElementById('catPanelRealEstate');
    const parent = realEstatePanel?.parentElement;
    if (!realEstatePanel || !parent) return null;

    let taxTab = document.querySelector('.account-cat-tab[data-cat="tax"]');
    if (!taxTab) {
      const tabs = Array.from(document.querySelectorAll('.account-cat-tab'));
      const lastTab = tabs[tabs.length - 1];
      if (!lastTab) return null;
      taxTab = document.createElement('button');
      taxTab.type = 'button';
      taxTab.className = 'account-cat-tab';
      taxTab.dataset.cat = 'tax';
      taxTab.textContent = '🧾 세금';
      taxTab.setAttribute('aria-label', '세금 및 금융소득 도구');
      lastTab.insertAdjacentElement('afterend', taxTab);
    }

    let panel = document.getElementById('catPanelTax');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'catPanelTax';
      panel.className = 'cat-panel';
      panel.style.cssText = 'display:none;margin-top:12px;';
      panel.innerHTML = `
        <div style="margin-bottom:14px;padding:12px 14px;border:1px solid rgba(99,102,241,.24);border-radius:10px;background:rgba(15,23,42,.35);">
          <div style="font-size:11px;font-weight:800;letter-spacing:.08em;color:#7dd3fc;">TAX & FINANCIAL INCOME</div>
          <div style="margin-top:3px;font-size:15px;font-weight:800;color:#e2e8f0;">세금 · 금융소득 관리</div>
          <div style="margin-top:4px;font-size:11.5px;line-height:1.55;color:#94a3b8;">매일 입출금되는 머니로그와 분리해 금융소득 기준, 가족별 screening, 가상 배분과 배당 세금 What-if를 한곳에서 확인합니다.</div>
        </div>
        <div id="taxWorkspaceBody"></div>
      `;
      realEstatePanel.insertAdjacentElement('afterend', panel);
    }
    return panel.querySelector('#taxWorkspaceBody');
  }

  function correctDividendCards() {
    return document.getElementById('divTotalAnnual')?.closest('.dividend-summary-cards') || null;
  }

  function relocateDividendForecastPanels() {
    const cards = correctDividendCards();
    if (!cards?.parentElement) return;

    const banner = document.getElementById('dividendForecastSourceBanner');
    if (banner && banner.nextElementSibling !== cards) {
      cards.parentElement.insertBefore(banner, cards);
    }

    const afterTax = document.getElementById('portfolioAfterTaxDividendPanel');
    if (afterTax && cards.nextElementSibling !== afterTax) {
      cards.insertAdjacentElement('afterend', afterTax);
    }
  }

  function relocateTaxTools() {
    const body = ensureTaxWorkspace();
    if (!body) return;
    const risk = document.getElementById('familyFinancialIncomeRiskPanel');
    const allocation = document.getElementById('familyFinancialIncomeAllocationPanel');
    const whatIf = document.getElementById('financialIncomeWhatIfPanel');
    [risk, allocation, whatIf].forEach(panel => {
      if (panel && panel.parentElement !== body) body.appendChild(panel);
    });
  }

  function restoreWhatIfDividendMode() {
    if (!whatIfSpoofSnapshot) return;
    whatIfSpoofSnapshot.forEach(({tab, active}) => tab.classList.toggle('active', active));
    whatIfSpoofSnapshot = null;
  }

  function beginWhatIfEstimatedModeSpoof() {
    if (!taxWorkspaceActive() || whatIfSpoofSnapshot) return;
    const tabs = Array.from(document.querySelectorAll('#dividendModeTabs .heatmap-tab'));
    const estimated = tabs.find(tab => tab.dataset?.divMode === 'estimated');
    if (!estimated || estimated.classList.contains('active')) return;
    whatIfSpoofSnapshot = tabs.map(tab => ({tab, active: tab.classList.contains('active')}));
    tabs.forEach(tab => tab.classList.remove('active'));
    estimated.classList.add('active');
    window.setTimeout(restoreWhatIfDividendMode, 0);
  }

  function refreshWhatIfForTaxWorkspace() {
    if (!taxWorkspaceActive()) return;
    const panel = document.getElementById('financialIncomeWhatIfPanel');
    const form = document.getElementById('financialIncomeWhatIfForm');
    if (!panel || !form) return;
    panel.style.display = 'block';
    beginWhatIfEstimatedModeSpoof();
    form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
  }

  function scheduleRelayout() {
    if (relayoutQueued) return;
    relayoutQueued = true;
    queueMicrotask(() => {
      relayoutQueued = false;
      relocateDividendForecastPanels();
      relocateTaxTools();
      const taxPanel = document.getElementById('catPanelTax');
      if (taxPanel) taxPanel.style.display = taxWorkspaceActive() ? 'block' : 'none';
      if (taxWorkspaceActive()) {
        const whatIf = document.getElementById('financialIncomeWhatIfPanel');
        if (whatIf) whatIf.style.display = 'block';
      }
    });
  }

  function panelMarkup() {
    return `
      <section id="familyFinancialIncomeRiskPanel" class="family-fi-risk-panel" aria-label="가족 금융소득 위험">
        <div class="family-fi-risk-head">
          <div>
            <span class="family-fi-risk-kicker">FAMILY FINANCIAL INCOME RISK</span>
            <h3>가족 금융소득 위험 · 개인별</h3>
            <p>가족 구성원별 예상 금융소득과 1천만원 watch / 2천만원 종합과세 screening 상태를 따로 봅니다.</p>
          </div>
          <div class="family-fi-risk-actions">
            <span class="family-fi-risk-badge">가족 합계는 참고값</span>
            <button id="familyFinancialIncomeRiskRefresh" type="button" class="button secondary compact">↻ 새로고침</button>
          </div>
        </div>
        <div id="familyFinancialIncomeRiskBody">
          <div class="family-fi-risk-placeholder">개인별 금융소득 위험을 불러오는 중입니다.</div>
        </div>
      </section>
    `;
  }

  function thresholdLabel(state, kind) {
    if (!state || state.amount_krw === null || state.amount_krw === undefined) {
      return { text: kind === 'watch' ? '1천만원 확인 불가' : '2천만원 확인 불가', cls: '' };
    }
    if (kind === 'watch') {
      if (state.at_or_above) return { text: '1천만원 watch 도달', cls: 'watch' };
      return { text: `1천만원까지 ${money(state.remaining_krw)}`, cls: '' };
    }
    if (state.exceeded) return { text: '2천만원 초과', cls: 'danger' };
    if (state.at_or_above) return { text: '2천만원 도달 · 초과 아님', cls: 'reached' };
    return { text: `2천만원까지 ${money(state.remaining_krw)}`, cls: '' };
  }

  function memberCard(member) {
    const watch = thresholdLabel(member?.thresholds?.watch, 'watch');
    const comprehensive = thresholdLabel(member?.thresholds?.comprehensive_tax, 'comprehensive');
    const components = member?.components || {};
    const basisText = member?.risk_basis === 'projected'
      ? '연말 예상 기준'
      : '예상 불완전 · 현재 확인된 금액 기준';
    return `
      <article class="family-fi-risk-card">
        <div class="family-fi-risk-card-head">
          <span class="family-fi-risk-owner">${escapeHtml(member?.owner || '구성원')}</span>
          <span class="family-fi-risk-badge">${escapeHtml(basisText)}</span>
        </div>
        <div class="family-fi-risk-amount">${money(member?.risk_amount_krw)}</div>
        <div class="family-fi-risk-states">
          <span class="family-fi-risk-state ${watch.cls}">${escapeHtml(watch.text)}</span>
          <span class="family-fi-risk-state ${comprehensive.cls}">${escapeHtml(comprehensive.text)}</span>
        </div>
        <div class="family-fi-risk-components">
          <span>실제 수령액 ${money(member?.actual_cash_income_krw)}</span>
          <span>현재월 이후 예상 배당 ${money(components.future_months_estimated_dividend_gross_krw)}</span>
          <span>예상 이자 자동 반영 없음 · 입력값 0원 기준</span>
        </div>
      </article>
    `;
  }

  function render(data) {
    const body = document.getElementById('familyFinancialIncomeRiskBody');
    if (!body) return;
    const members = Array.isArray(data?.members) ? data.members : [];
    const reference = data?.family_reference || {};
    const unassigned = data?.unassigned || {};
    const total = reference.projected_gross_screening_income_krw;
    const totalBasis = total === null || total === undefined
      ? '가족 예상 합계 확인 불가'
      : `가족 예상 참고 합계 ${money(total)}`;
    const incomplete = reference.reference_complete === false;

    body.innerHTML = `
      <div class="family-fi-risk-reference">
        <div class="family-fi-risk-reference-head">
          <div>
            <small>REFERENCE TOTAL</small><br />
            <strong>${escapeHtml(totalBasis)}</strong>
          </div>
          <span class="family-fi-risk-badge">개인별 세법 기준</span>
        </div>
        <div class="family-fi-risk-note">가족 합계에는 2천만원 종합과세 기준을 적용하지 않습니다. 각 구성원의 개인별 screening 상태를 확인하세요.</div>
      </div>
      ${members.length
        ? `<div class="family-fi-risk-grid">${members.map(memberCard).join('')}</div>`
        : '<div class="family-fi-risk-placeholder">등록된 가족 구성원이 없습니다.</div>'}
      ${incomplete
        ? `<div class="family-fi-risk-warning">가족 참고 합계가 불완전합니다. 소유자 미분류 보유자산 ${Number(unassigned.holding_count || 0).toLocaleString('ko-KR')}건(소유자 충돌 ${Number(unassigned.ownership_conflict_count || 0).toLocaleString('ko-KR')}건 포함) · 올해 실제 금융소득 기록 ${Number(unassigned.actual_record_count || 0).toLocaleString('ko-KR')}건을 확인하세요.</div>`
        : ''}
      <div class="family-fi-risk-note" style="margin-top:10px;">screening only · 최종 종합소득세/지방소득세를 확정하지 않습니다.</div>
    `;
  }

  function renderError(message) {
    const body = document.getElementById('familyFinancialIncomeRiskBody');
    if (!body) return;
    body.innerHTML = `<div class="family-fi-risk-error">${escapeHtml(message || '가족 금융소득 위험을 불러오지 못했습니다.')}</div>`;
  }

  async function loadRisk({ force = false } = {}) {
    if (loading || (!force && loadedOnce) || !taxWorkspaceActive()) return;
    loading = true;
    const button = document.getElementById('familyFinancialIncomeRiskRefresh');
    if (button) button.disabled = true;
    try {
      const response = await fetch(API_PATH, {
        method: 'GET',
        headers: { Accept: 'application/json' },
        cache: 'no-store',
        credentials: 'same-origin',
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = payload?.detail;
        const text = typeof detail === 'object' ? detail?.message || detail?.code : detail;
        throw new Error(text || `HTTP ${response.status}`);
      }
      render(payload);
      loadedOnce = true;
    } catch (error) {
      renderError(error?.message);
    } finally {
      loading = false;
      if (button) button.disabled = false;
    }
  }

  function syncTaxWorkspace() {
    scheduleRelayout();
    const visible = taxWorkspaceActive();
    const panel = document.getElementById('catPanelTax');
    if (panel) panel.style.display = visible ? 'block' : 'none';
    if (visible) {
      loadRisk();
      window.setTimeout(refreshWhatIfForTaxWorkspace, 0);
    }
  }

  function mount() {
    const workspace = ensureTaxWorkspace();
    if (!workspace) return;
    if (!document.getElementById('familyFinancialIncomeRiskPanel')) {
      workspace.insertAdjacentHTML('beforeend', panelMarkup());
      document.getElementById('familyFinancialIncomeRiskRefresh')?.addEventListener('click', () => {
        loadedOnce = false;
        loadRisk({ force: true });
      });
    }
    relocateTaxTools();
    relocateDividendForecastPanels();
    syncTaxWorkspace();

    const observer = new MutationObserver(scheduleRelayout);
    observer.observe(document.body, {childList: true, subtree: true});
  }

  document.addEventListener('click', event => {
    const accountTab = event.target?.closest?.('.account-cat-tab');
    if (accountTab) {
      window.setTimeout(syncTaxWorkspace, 0);
    }
    if (event.target?.closest?.('#dividendModeTabs .heatmap-tab')) {
      window.setTimeout(syncTaxWorkspace, 0);
    }
    if (event.target?.closest?.('.family-tabs .family-tab') && taxWorkspaceActive()) {
      loadedOnce = false;
      window.setTimeout(() => {
        loadRisk({force: true});
        refreshWhatIfForTaxWorkspace();
      }, 0);
    }
  });

  document.addEventListener('click', event => {
    if (event.target?.closest?.('#financialIncomeWhatIfPanel') && taxWorkspaceActive()) {
      beginWhatIfEstimatedModeSpoof();
    }
  }, true);
  document.addEventListener('change', event => {
    if (event.target?.closest?.('#financialIncomeWhatIfPanel') && taxWorkspaceActive()) {
      beginWhatIfEstimatedModeSpoof();
    }
  }, true);
  document.addEventListener('submit', event => {
    if (event.target?.closest?.('#financialIncomeWhatIfPanel') && taxWorkspaceActive()) {
      beginWhatIfEstimatedModeSpoof();
    }
  }, true);

  window.WealthTaxWorkspace = {
    isActive: taxWorkspaceActive,
    ensure: ensureTaxWorkspace,
    sync: syncTaxWorkspace,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
