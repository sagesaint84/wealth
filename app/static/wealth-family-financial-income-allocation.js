(() => {
  'use strict';

  const API_PATH = '/api/dividends/financial-income-family-allocation-simulation';
  const money = value => value === null || value === undefined
    ? '확인 불가'
    : `₩${Math.round(Number(value)).toLocaleString('ko-KR')}`;
  const escapeHtml = value => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
  const estimated = () => document.querySelector(
    '#dividendModeTabs .heatmap-tab.active'
  )?.dataset?.divMode === 'estimated';

  function options(members) {
    return members
      .map(member => `<option value="${escapeHtml(member.owner)}">${escapeHtml(member.owner)}</option>`)
      .join('');
  }

  function threshold(state, label) {
    if (!state) return `${label} 확인 불가`;
    if (state.exceeded) return `${label} 초과`;
    if (state.at_or_above) return `${label} 도달 · 초과 아님`;
    return `${label} 미만`;
  }

  function render(data) {
    const root = document.querySelector('#familyFinancialIncomeAllocationBody');
    if (!root) return;
    const members = Array.isArray(data?.members) ? data.members : [];
    root.innerHTML = `
      <div class="family-fi-allocation-controls">
        <label>보내는 구성원 <select id="familyAllocationFrom">${options(members)}</select></label>
        <label>받는 구성원 <select id="familyAllocationTo">${options(members)}</select></label>
        <label>가상 배분 미래 금융소득 <input id="familyAllocationAmount" inputmode="numeric" data-korean-currency value="0" aria-label="가상 배분 미래 금융소득 원" /> 원</label>
        <button id="familyAllocationRun" type="button" class="button secondary compact">시뮬레이션 실행</button>
      </div>
      <div class="family-fi-risk-grid">${members.map(member => `
        <article class="family-fi-risk-card">
          <strong>${escapeHtml(member.owner)}</strong>
          <div class="family-fi-allocation-row">배분 가능 미래소득 ${money(member.allocatable_future_financial_income_krw)}</div>
          <div class="family-fi-allocation-row">배분 전 ${money(member.before_projected_gross_screening_income_krw)}</div>
          <div class="family-fi-allocation-row">배분 후 ${money(member.after_projected_gross_screening_income_krw)}</div>
          <div class="family-fi-allocation-row">변화 ${member.difference_gross_screening_income_krw >= 0 ? '+' : ''}${money(member.difference_gross_screening_income_krw)}</div>
          <small>${threshold(member.thresholds?.watch?.after, '1천만원 watch')} · ${threshold(member.thresholds?.comprehensive_tax?.after, '2천만원')}</small>
        </article>`).join('')}</div>
      <div class="family-fi-risk-note" style="margin-top:10px;">가족 합계에는 2천만원 종합과세 기준을 적용하지 않습니다. ${escapeHtml(data?.data_quality?.legal_tax_notice || '')}</div>`;
    document.querySelector('#familyAllocationRun')?.addEventListener('click', run);
  }

  function error(message) {
    const root = document.querySelector('#familyFinancialIncomeAllocationBody');
    if (root) {
      root.insertAdjacentHTML(
        'beforeend',
        `<div class="family-fi-risk-error">${escapeHtml(message || '시뮬레이션을 완료하지 못했습니다.')}</div>`
      );
    }
  }

  async function request(allocations) {
    const response = await fetch(API_PATH, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', Accept: 'application/json'},
      credentials: 'same-origin',
      cache: 'no-store',
      body: JSON.stringify({allocations}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload?.detail?.code || `HTTP ${response.status}`);
    render(payload);
  }

  async function run() {
    const from = document.querySelector('#familyAllocationFrom')?.value;
    const to = document.querySelector('#familyAllocationTo')?.value;
    const raw = document.querySelector('#familyAllocationAmount')?.value?.replaceAll(',', '');
    try {
      await request([{
        from_owner: from,
        to_owner: to,
        financial_income_gross_krw: raw,
      }]);
    } catch (err) {
      error(err?.message);
    }
  }

  async function load() {
    if (
      !estimated()
      || document.querySelector('#familyFinancialIncomeAllocationPanel')?.dataset.loaded
    ) return;
    try {
      await request([]);
      document.querySelector('#familyFinancialIncomeAllocationPanel').dataset.loaded = 'true';
    } catch (err) {
      error(err?.message);
    }
  }

  function mount() {
    const risk = document.querySelector('#familyFinancialIncomeRiskPanel');
    if (!risk || document.querySelector('#familyFinancialIncomeAllocationPanel')) return;
    risk.insertAdjacentHTML(
      'afterend',
      `<section id="familyFinancialIncomeAllocationPanel" class="family-fi-risk-panel family-fi-allocation-panel"><div class="family-fi-risk-head"><div><span class="family-fi-risk-kicker">FAMILY ALLOCATION SIMULATION</span><h3>배우자·자녀 가상 배분 비교</h3><p>아직 발생하지 않은 미래 금융소득만 가정해 구성원별 screening 변화를 비교합니다. 이미 받은 소득의 귀속이나 실제 자산 이전, 세금 결론을 바꾸지 않습니다.</p></div></div><div id="familyFinancialIncomeAllocationBody" class="family-fi-risk-placeholder">가상 배분 기준을 불러오는 중입니다.</div></section>`
    );
    load();
  }

  document.addEventListener('click', event => {
    if (event.target?.closest?.('#dividendModeTabs .heatmap-tab')) {
      window.setTimeout(load, 0);
    }
  });
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, {once: true});
  } else {
    mount();
  }
})();
