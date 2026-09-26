(() => {
  'use strict';

  const API_PATH = '/api/dividends/financial-income-family-risk';
  let loading = false;
  let loadedOnce = false;

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

  function estimatedModeActive() {
    const active = document.querySelector('#dividendModeTabs .heatmap-tab.active');
    return active?.dataset?.divMode === 'estimated';
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
        ? `<div class="family-fi-risk-warning">가족 참고 합계가 불완전합니다. 소유자 미분류 보유자산 ${Number(unassigned.holding_count || 0).toLocaleString('ko-KR')}건 · 올해 실제 금융소득 기록 ${Number(unassigned.actual_record_count || 0).toLocaleString('ko-KR')}건을 확인하세요.</div>`
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
    if (loading || (!force && loadedOnce) || !estimatedModeActive()) return;
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

  function syncVisibility() {
    const panel = document.getElementById('familyFinancialIncomeRiskPanel');
    if (!panel) return;
    const visible = estimatedModeActive();
    panel.style.display = visible ? 'block' : 'none';
    if (visible) loadRisk();
  }

  function mount() {
    if (document.getElementById('familyFinancialIncomeRiskPanel')) return;
    const summary = document.querySelector('#dividendPanel .dividend-summary-cards');
    if (!summary) return;
    summary.insertAdjacentHTML('afterend', panelMarkup());
    document.getElementById('familyFinancialIncomeRiskRefresh')?.addEventListener('click', () => {
      loadedOnce = false;
      loadRisk({ force: true });
    });
    syncVisibility();
  }

  document.addEventListener('click', event => {
    if (event.target?.closest?.('#dividendModeTabs .heatmap-tab')) {
      window.setTimeout(syncVisibility, 0);
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
