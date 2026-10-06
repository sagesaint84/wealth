(() => {
  'use strict';

  let canonicalIpos = [];
  let latestUpdatedAt = null;
  let synced = false;

  const monthKey = (year, month) => `${year}-${String(month).padStart(2, '0')}`;

  function currentKey() {
    const state = window.WealthIpoState;
    const year = Number(state?.getHistoryYear?.());
    const month = Number(state?.getHistoryMonth?.());
    if (Number.isInteger(year) && Number.isInteger(month) && month >= 1 && month <= 12) {
      return monthKey(year, month);
    }
    return window.WealthIpoDate?.currentKstYearMonth?.().key || null;
  }

  function projectedForMonth(key) {
    return canonicalIpos.map(item => {
      const localSort = item?.presentation_month_sort_dates?.[key];
      return {
        ...item,
        presentation_sort_date: localSort || item?.presentation_sort_date || '',
      };
    });
  }

  function applyMonth(key, { render = false } = {}) {
    const state = window.WealthIpoState;
    if (!state || !key || canonicalIpos.length === 0) return;
    state.setMarketIpos?.(projectedForMonth(key));
    if (render) state.renderIpoList?.();
  }

  async function syncFromServer({ forceRender = false } = {}) {
    const state = window.WealthIpoState;
    if (!state) return;
    try {
      const payload = await window.fetchJson('/api/ipo/market', synced ? { cache: 'no-store' } : {});
      synced = true;
      const items = Array.isArray(payload?.ipos) ? payload.ipos : [];
      const changed = payload?.updated_at !== latestUpdatedAt;
      canonicalIpos = items;
      latestUpdatedAt = payload?.updated_at || null;
      if (changed || forceRender) applyMonth(currentKey(), { render: true });
    } catch (err) {
      console.warn('IPO 월별 이벤트 표시 데이터를 불러오지 못했습니다:', err);
    }
  }

  function targetKeyForClick(target) {
    const state = window.WealthIpoState;
    const date = window.WealthIpoDate;
    if (!state || !date) return null;
    const year = Number(state.getHistoryYear?.());
    const month = Number(state.getHistoryMonth?.());
    if (!Number.isInteger(year) || !Number.isInteger(month)) return null;
    if (target.closest?.('#ipoPrevMonthBtn')) return date.shiftIpoMonth(year, month, -1).key;
    if (target.closest?.('#ipoNextMonthBtn')) return date.shiftIpoMonth(year, month, 1).key;
    if (target.closest?.('#ipoTodayMonthBtn')) return date.currentKstYearMonth().key;
    return null;
  }

  function mount() {
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper || !window.WealthIpoState) return;

    // Capture runs before the core month handlers (and before the compact-view
    // future-month interceptor), so the core renderer receives a projection
    // whose sort date belongs to the month the user is moving into.
    wrapper.addEventListener('click', event => {
      const key = targetKeyForClick(event.target);
      if (key) applyMonth(key, { render: false });
    }, true);

    wrapper.addEventListener('change', event => {
      if (!event.target?.matches?.('#ipoMonthPicker')) return;
      const value = String(event.target.value || '');
      if (/^\d{4}-\d{2}$/.test(value)) applyMonth(value, { render: false });
    }, true);

    const refreshButton = document.getElementById('ipoRefreshBtn');
    if (refreshButton) {
      const observer = new MutationObserver(() => {
        if (!refreshButton.hasAttribute('aria-busy')) void syncFromServer({ forceRender: true });
      });
      observer.observe(refreshButton, { attributes: true, attributeFilter: ['aria-busy'] });
    }

    window.addEventListener('wealth-ipo-app-updated', () => {
      window.setTimeout(() => void syncFromServer({ forceRender: true }), 0);
    });

    void syncFromServer({ forceRender: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
