(() => {
  'use strict';

  const STYLE_ID = 'wealthAccountSectionSummaryStyle';
  const SECURITIES_HOST_ID = 'securitiesAccountSectionSummary';
  const BANK_HOST_ID = 'bankAccountSectionSummary';
  let refreshToken = 0;
  let refreshTimer = 0;

  function text(value) {
    return String(value ?? '').normalize('NFKC').replace(/\s+/g, ' ').trim();
  }

  function number(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n : 0;
  }

  function html(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function moneyKrw(value) {
    return `₩${Math.round(number(value)).toLocaleString('ko-KR')}`;
  }

  function moneyUsd(value) {
    const n = number(value);
    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  }

  function currentOwner() {
    return text(document.querySelector('.family-tab.active[data-owner]')?.dataset?.owner) || '모두';
  }

  function filterOwner(items, owner) {
    const list = Array.isArray(items) ? items : [];
    if (!owner || owner === '모두') return list;
    return list.filter((item) => text(item?.owner || '모두') === owner);
  }

  function institutionCount(items, field) {
    return new Set((items || []).map((item) => text(item?.[field])).filter(Boolean)).size;
  }

  function ownerBreakdown(items) {
    const counts = new Map();
    (items || []).forEach((item) => {
      const owner = text(item?.owner || '모두');
      if (!owner || owner === '모두') return;
      counts.set(owner, (counts.get(owner) || 0) + 1);
    });
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'ko'))
      .map(([owner, count]) => `${html(owner)} ${count}`)
      .join(' · ');
  }

  function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      .account-section-summary { margin: 0 0 14px; }
      .account-section-summary-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
      .account-section-summary-card { min-width:0; padding:13px 14px; border:1px solid rgba(71,85,105,.42); border-radius:11px; background:rgba(15,23,42,.5); }
      .account-section-summary-label { color:#8fa4c8; font-size:11.5px; font-weight:600; letter-spacing:.01em; }
      .account-section-summary-value { margin-top:5px; color:#f8fafc; font-size:18px; line-height:1.15; font-weight:800; overflow-wrap:anywhere; }
      .account-section-summary-sub { margin-top:5px; color:#7690b9; font-size:11px; line-height:1.35; }
      .account-section-owner-line { margin-top:9px; padding:8px 11px; border:1px solid rgba(51,65,85,.42); border-radius:9px; background:rgba(15,23,42,.28); color:#8fa4c8; font-size:11.5px; }
      .account-section-owner-line strong { color:#cbd5e1; margin-right:7px; }
      .account-section-summary-error { padding:9px 11px; border:1px solid rgba(245,158,11,.28); border-radius:9px; color:#fbbf24; font-size:11.5px; background:rgba(120,53,15,.08); }
      @media (max-width: 980px) { .account-section-summary-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } }
      @media (max-width: 620px) { .account-section-summary-grid { grid-template-columns:1fr; } }
    `;
    document.head.appendChild(style);
  }

  function ensureHost(panelId, hostId, beforeId) {
    const panel = document.getElementById(panelId);
    if (!panel) return null;
    let host = document.getElementById(hostId);
    if (host) return host;
    host = document.createElement('div');
    host.id = hostId;
    host.className = 'account-section-summary';
    const before = document.getElementById(beforeId);
    if (before?.parentElement === panel) panel.insertBefore(host, before);
    else panel.prepend(host);
    return host;
  }

  function card(label, value, sub = '') {
    return `<div class="account-section-summary-card"><div class="account-section-summary-label">${html(label)}</div><div class="account-section-summary-value">${value}</div>${sub ? `<div class="account-section-summary-sub">${sub}</div>` : ''}</div>`;
  }

  function renderInto(host, markup) {
    if (!host || host.innerHTML === markup) return;
    host.innerHTML = markup;
  }

  function renderSecuritiesSummary(allAccounts, owner) {
    const host = ensureHost('catPanelSecurities', SECURITIES_HOST_ID, 'accountList');
    if (!host) return;
    const accounts = filterOwner(allAccounts, owner);
    const brokers = institutionCount(accounts, 'broker');
    const stockValue = accounts.reduce((sum, account) => sum + number(account?.stock_value_krw), 0);
    const totalValue = accounts.reduce((sum, account) => {
      const explicit = account?.market_value_krw;
      if (explicit !== undefined && explicit !== null) return sum + number(explicit);
      return sum + number(account?.stock_value_krw) + number(account?.cash_total_krw ?? account?.cash_krw);
    }, 0);
    const cashKrw = accounts.reduce((sum, account) => sum + number(account?.cash_krw), 0);
    const cashUsd = accounts.reduce((sum, account) => sum + number(account?.cash_usd), 0);
    const ownerLine = owner === '모두' ? ownerBreakdown(allAccounts) : '';
    const markup = `
      <div class="account-section-summary-grid">
        ${card('총 증권계좌', `${accounts.length.toLocaleString('ko-KR')}개`, `${brokers.toLocaleString('ko-KR')}개 증권사`)}
        ${card('총 증권자산', moneyKrw(totalValue), '주식자산 + 예수금')}
        ${card('주식자산', moneyKrw(stockValue), '현재 평가금액 기준')}
        ${card('예수금', moneyKrw(cashKrw), cashUsd ? `${moneyUsd(cashUsd)} 별도 보유` : '원화 예수금')}
      </div>
      ${ownerLine ? `<div class="account-section-owner-line"><strong>소유자별 계좌</strong>${ownerLine}</div>` : ''}
    `;
    renderInto(host, markup);
  }

  function bankAgreementState(payload, owner) {
    const banks = filterOwner(payload?.bank_accounts, owner);
    const savings = filterOwner(payload?.savings_accounts, owner);
    const loans = filterOwner(payload?.loan_accounts, owner);
    const linkedBankIds = new Set(loans.map((item) => text(item?.overdraft_bank_account_id)).filter(Boolean));
    const creditLineBanks = banks.filter((item) => {
      const hasAgreement = number(item?.balance) < 0 || number(item?.limit_amount) > 0;
      return hasAgreement && !linkedBankIds.has(text(item?.id));
    });
    const agreements = [...loans, ...creditLineBanks];
    return { banks, savings, loans, creditLineBanks, agreements };
  }

  function syncBankCountBadges(actualAccountCount, agreementCount) {
    const values = [
      ['bankingTabCount', actualAccountCount],
      ['allBankCount', actualAccountCount],
      ['loansCount', agreementCount],
    ];
    values.forEach(([id, value]) => {
      const node = document.getElementById(id);
      const expected = String(value);
      if (node && node.textContent !== expected) node.textContent = expected;
    });
  }

  function renderBankSummary(payload, owner) {
    const host = ensureHost('catPanelBanking', BANK_HOST_ID, 'savingsSummaryCards');
    if (!host) return;
    const { banks, savings, loans, agreements } = bankAgreementState(payload, owner);

    // Deposit accounts are counted once. A loan/overdraft is a separate agreement,
    // including legacy bank-account credit lines represented by limit_amount > 0.
    const bankAccounts = [...banks, ...savings];
    const institutions = new Set(bankAccounts.map((item) => text(item?.bank_name)).filter(Boolean)).size;
    const loanDebt = loans.reduce((sum, item) => sum + Math.max(0, number(item?.current_balance)), 0);
    const legacyMinusDebt = banks.reduce((sum, item) => {
      const balance = number(item?.balance);
      return sum + (balance < 0 ? Math.abs(balance) : 0);
    }, 0);
    const currentDebt = loanDebt + legacyMinusDebt;
    const ownerLine = owner === '모두' ? ownerBreakdown(bankAccounts) : '';
    const markup = `
      <div class="account-section-summary-grid">
        ${card('총 은행계좌', `${bankAccounts.length.toLocaleString('ko-KR')}개`, `${institutions.toLocaleString('ko-KR')}개 금융기관`)}
        ${card('자유입출금', `${banks.length.toLocaleString('ko-KR')}개`, '일반 은행계좌')}
        ${card('예·적금', `${savings.length.toLocaleString('ko-KR')}개`, '예금 · 적금 · 청약')}
        ${card('대출·한도약정', `${agreements.length.toLocaleString('ko-KR')}개`, `현재 부채 ${moneyKrw(currentDebt)}`)}
      </div>
      ${ownerLine ? `<div class="account-section-owner-line"><strong>소유자별 계좌</strong>${ownerLine}</div>` : ''}
    `;
    renderInto(host, markup);
    syncBankCountBadges(bankAccounts.length, agreements.length);
  }

  async function jsonFetch(url) {
    const response = await fetch(url, { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`요청 실패 (${response.status})`);
    return response.json();
  }

  async function refreshAccountSectionSummaries() {
    const token = ++refreshToken;
    const owner = currentOwner();
    try {
      const [accountPayload, dashboardPayload] = await Promise.all([
        jsonFetch('/api/accounts?group=All&owner=모두'),
        jsonFetch('/api/dashboard'),
      ]);
      if (token !== refreshToken) return;
      renderSecuritiesSummary(accountPayload?.accounts || [], owner);
      renderBankSummary(dashboardPayload || {}, owner);
    } catch (error) {
      if (token !== refreshToken) return;
      const message = `<div class="account-section-summary-error">계좌 요약을 불러오지 못했습니다. 기존 계좌 목록은 그대로 사용할 수 있습니다.</div>`;
      renderInto(ensureHost('catPanelSecurities', SECURITIES_HOST_ID, 'accountList'), message);
      renderInto(ensureHost('catPanelBanking', BANK_HOST_ID, 'savingsSummaryCards'), message);
      console.warn('[account-section-summary] refresh failed', error);
    }
  }

  function scheduleRefresh(delay = 40) {
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(() => { void refreshAccountSectionSummaries(); }, delay);
  }

  function installObservers() {
    const accountList = document.getElementById('accountList');
    if (accountList) {
      const observer = new MutationObserver(() => scheduleRefresh(80));
      observer.observe(accountList, { childList: true, subtree: true });
    }
    const savingsCards = document.getElementById('savingsSummaryCards');
    if (savingsCards) {
      const observer = new MutationObserver(() => scheduleRefresh(80));
      observer.observe(savingsCards, { childList: true, subtree: true });
    }
  }

  function loadIpoSaleBridgeScript() {
    if (window.WealthIpoSaleBridge || document.getElementById('wealthIpoSaleBridgeScript')) return;
    const script = document.createElement('script');
    script.id = 'wealthIpoSaleBridgeScript';
    script.src = '/static/wealth-ipo-sale-bridge.js?v=10.6c';
    script.async = false;
    document.head.appendChild(script);
  }

  function install() {
    ensureStyle();
    ensureHost('catPanelSecurities', SECURITIES_HOST_ID, 'accountList');
    ensureHost('catPanelBanking', BANK_HOST_ID, 'savingsSummaryCards');
    installObservers();
    document.addEventListener('click', (event) => {
      if (event.target?.closest?.('.family-tab[data-owner]')) scheduleRefresh(0);
    }, true);
    window.addEventListener('focus', () => scheduleRefresh(0));
    loadIpoSaleBridgeScript();
    scheduleRefresh(0);
  }

  const exported = {
    text,
    number,
    filterOwner,
    institutionCount,
    ownerBreakdown,
    bankAgreementState,
    syncBankCountBadges,
    renderSecuritiesSummary,
    renderBankSummary,
    refreshAccountSectionSummaries,
    loadIpoSaleBridgeScript,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = exported;
  if (typeof window !== 'undefined') window.WealthAccountSectionSummary = exported;
  if (typeof document === 'undefined') return;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
