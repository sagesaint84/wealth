(() => {
  'use strict';

  let refreshing = false;

  function text(value) {
    return String(value ?? '').normalize('NFKC').replace(/\s+/g, ' ').trim();
  }

  function domOwners() {
    return [...new Set([...document.querySelectorAll('.family-tab[data-owner]')]
      .map((node) => text(node.dataset.owner))
      .filter((value) => value && value !== '모두'))];
  }

  async function apiOwners() {
    const response = await fetch('/api/family-members', { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`가족 구성원 조회 실패 (${response.status})`);
    const payload = await response.json();
    return [...new Set((Array.isArray(payload?.members) ? payload.members : [])
      .map(text)
      .filter((value) => value && value !== '모두'))];
  }

  function renderOwnerOptions(select, owners) {
    if (!select) return;
    const previous = text(select.value);
    const activeOwner = text(document.querySelector('.family-tab.active[data-owner]')?.dataset?.owner);
    const normalized = [...new Set((owners || []).map(text).filter((value) => value && value !== '모두'))];
    const options = normalized.length ? normalized : ['모두'];

    select.replaceChildren();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = '소유자를 선택하세요';
    select.appendChild(placeholder);

    options.forEach((owner) => {
      const option = document.createElement('option');
      option.value = owner;
      option.textContent = owner;
      select.appendChild(option);
    });

    const preferred = options.includes(previous)
      ? previous
      : (activeOwner !== '모두' && options.includes(activeOwner) ? activeOwner : '');
    select.value = preferred;
  }

  async function refreshOwnerOptions() {
    const select = document.getElementById('accountInfoImportOwner');
    if (!select || refreshing) return;
    refreshing = true;
    try {
      let owners = domOwners();
      try {
        owners = [...new Set([...owners, ...(await apiOwners())])];
      } catch (_) {
        // The already-rendered family tabs remain a safe fallback if the API is temporarily unavailable.
      }
      renderOwnerOptions(select, owners);
    } finally {
      refreshing = false;
    }
  }

  function previewIsReady() {
    const host = document.getElementById('accountInfoPdfPreview');
    return Boolean(host && host.style.display !== 'none' && host.childElementCount > 0);
  }

  function syncSubmitActionLabel() {
    const submit = document.querySelector('#accountImportForm button[type="submit"]');
    if (!submit || submit.disabled) return;
    const expected = previewIsReady() ? '선택 계좌 추가' : '가져오기';
    if (submit.textContent !== expected) submit.textContent = expected;
  }

  function setNodeLabel(node, label, title) {
    if (!node) return;
    if (node.textContent !== label) node.textContent = label;
    if (node.title !== title) node.title = title;
  }

  function syncAccountActionLabels() {
    setNodeLabel(
      document.getElementById('accountImportBtn'),
      '📂 증권계좌 가져오기',
      '증권계좌 가져오기',
    );
    setNodeLabel(
      document.getElementById('addBankIntegratedBtn'),
      '➕ 은행계좌 추가',
      '은행계좌 추가',
    );
    setNodeLabel(
      document.getElementById('accountInfoBankImportBtn'),
      '📂 은행계좌 가져오기',
      'AccountInfo 은행계좌 가져오기',
    );
  }

  function containsAccountAction(node) {
    if (!node || node.nodeType !== 1) return false;
    if (['accountImportBtn', 'addBankIntegratedBtn', 'accountInfoBankImportBtn'].includes(node.id)) return true;
    return Boolean(node.querySelector?.('#accountImportBtn, #addBankIntegratedBtn, #accountInfoBankImportBtn'));
  }

  function loadAccountSectionSummaryScript() {
    if (window.WealthAccountSectionSummary || document.getElementById('wealthAccountSectionSummaryScript')) return;
    const script = document.createElement('script');
    script.id = 'wealthAccountSectionSummaryScript';
    script.src = '/static/wealth-account-section-summary.js?v=10.6b';
    script.async = false;
    document.head.appendChild(script);
  }

  function install() {
    const scheduleRefresh = () => queueMicrotask(() => { void refreshOwnerOptions(); });
    const scheduleActionSync = () => queueMicrotask(syncSubmitActionLabel);
    const scheduleToolbarSync = () => queueMicrotask(syncAccountActionLabels);

    document.addEventListener('click', (event) => {
      const target = event.target;
      if (target?.id === 'accountInfoBankImportBtn' || target?.closest?.('#accountImportDialog')) {
        scheduleRefresh();
        scheduleActionSync();
      }
    }, true);

    document.addEventListener('change', (event) => {
      if (event.target?.id === 'accountImportFile') {
        scheduleRefresh();
        scheduleActionSync();
      }
    }, true);

    const observer = new MutationObserver((records) => {
      let shouldRefreshOwner = false;
      let shouldSyncToolbar = false;
      for (const record of records) {
        for (const node of record.addedNodes || []) {
          if (node?.nodeType !== 1) continue;
          if (node.id === 'accountInfoImportOwner' || node.querySelector?.('#accountInfoImportOwner')) {
            shouldRefreshOwner = true;
          }
          if (containsAccountAction(node)) shouldSyncToolbar = true;
        }
      }
      if (shouldRefreshOwner) scheduleRefresh();
      if (shouldSyncToolbar) scheduleToolbarSync();
    });
    observer.observe(document.body, { childList: true, subtree: true });

    const form = document.getElementById('accountImportForm');
    if (form) {
      const actionObserver = new MutationObserver(scheduleActionSync);
      actionObserver.observe(form, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['style', 'disabled'],
      });
    }

    scheduleRefresh();
    scheduleActionSync();
    scheduleToolbarSync();
    loadAccountSectionSummaryScript();
  }

  const exported = {
    text,
    domOwners,
    renderOwnerOptions,
    previewIsReady,
    syncSubmitActionLabel,
    setNodeLabel,
    syncAccountActionLabels,
    containsAccountAction,
    loadAccountSectionSummaryScript,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = exported;
  if (typeof window !== 'undefined') window.WealthAccountInfoOwnerOptions = exported;
  if (typeof document === 'undefined') return;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
