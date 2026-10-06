(() => {
  'use strict';

  const period = window.WealthPeriodFilter;
  if (!period) {
    console.error('WealthPeriodFilter core is required before realized P/L year intent sync.');
    return;
  }

  const originalSyncPnlMonthNavUI = typeof syncPnlMonthNavUI === 'function'
    ? syncPnlMonthNavUI
    : null;

  function syncPnlPeriodNavUI() {
    if (typeof selectedPnlYear === 'undefined') {
      originalSyncPnlMonthNavUI?.();
      return;
    }

    const textEl = document.getElementById('pnlCurrentMonthText');
    const pickerEl = document.getElementById('pnlMonthPicker');
    const selectEl = document.getElementById('pnlYearSelect');
    const year = String(selectedPnlYear || 'all');

    if (year === 'all') {
      if (textEl) textEl.textContent = '전체 기간';
      if (pickerEl) pickerEl.value = '';
      if (selectEl && selectEl.value !== 'all') selectEl.value = 'all';
      return;
    }

    if (typeof selectedPnlMonth !== 'undefined' && selectedPnlMonth === null) {
      if (textEl) textEl.textContent = period.scopeLabel(year, null);
      if (pickerEl) pickerEl.value = '';
      if (selectEl && selectEl.value !== year) selectEl.value = year;
      return;
    }

    originalSyncPnlMonthNavUI?.();
  }

  // Replace the legacy month-only label sync with an annual-aware adapter.
  window.syncPnlMonthNavUI = syncPnlPeriodNavUI;

  function clearPnlMonthForYearSelection() {
    const activeBucket = Boolean(window.WealthUnifiedTimeseries?.getDetail('pnl'));
    window.WealthUnifiedTimeseries?.clearDetail('pnl', {render:false});
    if (typeof selectedPnlMonth === 'undefined' || (selectedPnlMonth === null && !activeBucket)) return;
    selectedPnlMonth = null;
    syncPnlPeriodNavUI();

    // The current API response already contains the selected year's records.
    // Re-render immediately so re-selecting the same year does not require a
    // synthetic year change (for example 2026 -> 2025 -> 2026).
    if (typeof pnlData !== 'undefined' && pnlData && typeof renderRealizedPnl === 'function') {
      renderRealizedPnl(pnlData);
    }
  }

  document.addEventListener('pointerdown', (event) => {
    if (event.target?.id === 'pnlYearSelect') clearPnlMonthForYearSelection();
  }, true);

  document.addEventListener('keydown', (event) => {
    if (event.target?.id !== 'pnlYearSelect') return;
    if (event.key === 'Enter' || event.key === ' ') clearPnlMonthForYearSelection();
  }, true);

  window.WealthPnlYearIntent = {
    clearPnlMonthForYearSelection,
    syncPnlPeriodNavUI,
  };
})();
