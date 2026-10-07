(() => {
  'use strict';

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
    return (window.WealthIpoState?.getCanonicalMarketIpos?.() || []).map(item => {
      const localSort = item?.presentation_month_sort_dates?.[key];
      return {
        ...item,
        presentation_sort_date: localSort || item?.presentation_sort_date || '',
      };
    });
  }

  function applyMonth(key, { render = false } = {}) {
    const state = window.WealthIpoState;
    if (!state || !key) return;
    state.setMarketIpos?.(projectedForMonth(key), { projection: true });
    if (render) state.renderIpoList?.();
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

    window.addEventListener('wealth:ipo-market-changed', () => applyMonth(currentKey()));
    applyMonth(currentKey(), { render: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mount, { once: true });
  } else {
    mount();
  }
})();
