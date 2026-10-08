/* Lazily extend household-ledger cashflow history when the shared chart reaches its widest loaded range. */
(() => {
  'use strict';

  const LEDGER_VIEWPORT = '.wealth-timeseries-viewport[data-panzoom-kind="ledger"]';
  const LEDGER_CHART = '.ledger-trend-chart';
  const YEAR_STYLE_ID = 'wealthLedgerTimeseriesYearStyles';
  const ZOOM_STEP = 1.16;
  const EPSILON = 0.015;

  let loading = false;
  let requestSequence = 0;

  const numeric = value => Number.isFinite(Number(value)) ? Number(value) : 0;

  function monthKey(row) {
    const year = Number(row?.year);
    const month = Number(row?.month);
    if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) return '';
    return `${year}-${String(month).padStart(2, '0')}`;
  }

  function shiftMonth(year, month, delta) {
    if (typeof shiftYearMonth === 'function') return shiftYearMonth(year, month, delta);
    let y = Number(year);
    let m = Number(month) + Number(delta);
    while (m < 1) { m += 12; y -= 1; }
    while (m > 12) { m -= 12; y += 1; }
    return { year: y, month: m, key: `${y}-${String(m).padStart(2, '0')}` };
  }

  function activeData() {
    if (typeof rawLedgerData === 'undefined' || !rawLedgerData) return null;
    if (!Array.isArray(rawLedgerData.monthly_trend) || !rawLedgerData.monthly_trend.length) return null;
    return rawLedgerData;
  }

  function activeOwner() {
    return typeof currentOwner !== 'undefined' && currentOwner ? currentOwner : '모두';
  }

  function mergeTrend(olderRows, currentRows) {
    const byMonth = new Map();
    [...olderRows, ...currentRows].forEach(row => {
      const key = monthKey(row);
      if (!key) return;
      const income = numeric(row?.income);
      const expense = numeric(row?.expense);
      byMonth.set(key, {
        year: Number(row.year),
        month: Number(row.month),
        label: row.label || `${Number(row.month)}월`,
        income,
        expense,
        savings: Number.isFinite(Number(row?.savings)) ? Number(row.savings) : income - expense,
      });
    });
    return [...byMonth.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([, row]) => row);
  }

  function isAnnualView(data) {
    if (data?.__ledger_annual_view) return true;
    return Boolean(window.WealthLedgerPeriodFilter?.isAnnualView?.());
  }

  function ensureYearLabelStyles() {
    if (document.getElementById(YEAR_STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = YEAR_STYLE_ID;
    style.textContent = `
      #ledgerTrendContainer .ledger-trend-year {
        display: block;
        margin-top: 3px;
        color: #6f82ad;
        font-size: 9px;
        font-weight: 700;
        line-height: 1;
        white-space: nowrap;
      }
      @media (max-width: 720px) {
        #ledgerTrendContainer .ledger-trend-year {
          font-size: 8px;
        }
      }
    `;
    document.head.append(style);
  }

  function annotateYearLabels(trend) {
    if (!Array.isArray(trend) || !trend.length) return;
    const cols = [...document.querySelectorAll('#ledgerTrendContainer .ledger-trend-col')];
    cols.forEach((col, index) => {
      const row = trend[index];
      const label = col.querySelector('.ledger-trend-label');
      if (!label) return;

      const existing = label.querySelector('.ledger-trend-year');
      const year = Number(row?.year);
      const month = Number(row?.month);
      const shouldShow = Number.isInteger(year) && month === 1;

      if (!shouldShow) {
        if (existing) existing.remove();
        return;
      }

      const text = `${year}년`;
      if (existing) {
        if (existing.textContent !== text) existing.textContent = text;
        return;
      }

      const yearLabel = document.createElement('span');
      yearLabel.className = 'ledger-trend-year';
      yearLabel.textContent = text;
      yearLabel.setAttribute('aria-label', `${year}년 시작`);
      label.append(yearLabel);
    });
  }

  function updateTrendHeader(trend) {
    if (!trend.length) return;
    const first = trend[0];
    const last = trend.at(-1);
    const panel = document.getElementById('ledgerTrendContainer')?.closest('.ledger-sub-panel');
    const title = panel?.querySelector('h3');
    if (title) {
      const firstText = `${first.year}년 ${first.month}월`;
      const lastText = `${last.year}년 ${last.month}월`;
      title.textContent = `${firstText} ~ ${lastText} 현금흐름 추이`;
    }
  }

  function restoreAnnualMonthLinks(trend, data) {
    const annual = isAnnualView(data);
    const selectedYear = Number(data?.year);
    document.querySelectorAll('#ledgerTrendContainer .ledger-trend-col').forEach((col, index) => {
      const row = trend[index];
      const clickable = annual && row && Number(row.year) === selectedYear;
      if (clickable) {
        col.dataset.ledgerMonth = String(row.month);
        col.style.cursor = 'pointer';
        col.title = `${selectedYear}년 ${row.month}월 상세 보기`;
      } else {
        delete col.dataset.ledgerMonth;
        col.style.cursor = '';
        col.removeAttribute('title');
      }
    });
  }

  function viewportScale(viewport, chart) {
    const base = Math.max(1, viewport.clientWidth);
    return chart.getBoundingClientRect().width / base;
  }

  function atWidestLoadedRange(viewport) {
    const chart = viewport.querySelector(LEDGER_CHART);
    if (!chart || !viewport.clientWidth) return false;
    return viewportScale(viewport, chart) <= 1 + EPSILON;
  }

  function restoreVisibleCount(previousCount, newCount) {
    const desiredVisible = Math.min(newCount, Math.max(1, previousCount * ZOOM_STEP));
    const desiredScale = Math.max(1, newCount / desiredVisible);

    requestAnimationFrame(() => requestAnimationFrame(() => {
      const viewport = document.querySelector(LEDGER_VIEWPORT);
      const chart = viewport?.querySelector(LEDGER_CHART);
      if (!viewport || !chart || !viewport.clientWidth) return;

      const rect = viewport.getBoundingClientRect();
      for (let i = 0; i < 48; i += 1) {
        if (viewportScale(viewport, chart) <= desiredScale + EPSILON) break;
        viewport.dispatchEvent(new WheelEvent('wheel', {
          deltaY: 100,
          clientX: rect.left + viewport.clientWidth / 2,
          clientY: rect.top + Math.min(40, viewport.clientHeight / 2),
          bubbles: false,
          cancelable: true,
        }));
      }
    }));
  }

  async function fetchOlderChunk(data, sequence) {
    const currentTrend = Array.isArray(data.monthly_trend) ? data.monthly_trend : [];
    const first = currentTrend[0];
    if (!first) return null;
    const previousEnd = shiftMonth(Number(first.year), Number(first.month), -1);
    const owner = activeOwner();
    const response = await api(
      `/api/ledger?year=${encodeURIComponent(previousEnd.year)}`
      + `&month=${encodeURIComponent(previousEnd.month)}`
      + `&owner=${encodeURIComponent(owner)}`,
    );
    if (sequence !== requestSequence || activeData() !== data || owner !== activeOwner() || !response) return null;
    return Array.isArray(response.monthly_trend) ? response.monthly_trend : [];
  }

  async function expandHistory(viewport) {
    if (window.WealthUnifiedTimeseries?.extendLedgerHistory) {
      return window.WealthUnifiedTimeseries.extendLedgerHistory();
    }
    if (window.WealthLedgerChartModule?.state !== 'failed') return;
    if (loading) return;
    const data = activeData();
    if (!data || typeof api !== 'function' || typeof renderLedgerTrendFallback !== 'function') return;

    const oldTrend = data.monthly_trend;
    const previousCount = oldTrend.length;
    const sequence = ++requestSequence;
    loading = true;
    viewport.dataset.ledgerHistoryLoading = '1';

    try {
      const older = await fetchOlderChunk(data, sequence);
      if (!older || sequence !== requestSequence || activeData() !== data) return;
      const merged = mergeTrend(older, oldTrend);
      if (merged.length <= previousCount) return;

      rawLedgerData = { ...data, monthly_trend: merged };
      renderLedgerTrendFallback(merged);
      annotateYearLabels(merged);
      updateTrendHeader(merged);
      restoreAnnualMonthLinks(merged, rawLedgerData);
      restoreVisibleCount(previousCount, merged.length);
    } catch (error) {
      console.error('가계부 과거 현금흐름 확장 오류:', error);
    } finally {
      loading = false;
      const currentViewport = document.querySelector(LEDGER_VIEWPORT);
      if (currentViewport) delete currentViewport.dataset.ledgerHistoryLoading;
    }
  }

  document.addEventListener('wheel', event => {
    if (!event.isTrusted || event.deltaY <= 0 || Math.abs(event.deltaY) < Math.abs(event.deltaX)) return;
    const viewport = event.target?.closest?.(LEDGER_VIEWPORT);
    if (!viewport || !atWidestLoadedRange(viewport)) return;

    // At the current data boundary, consume one downward wheel gesture to load
    // the preceding six-month chunk. The shared pan/zoom module handles all
    // wheel gestures again as soon as the enlarged series has been rendered.
    event.preventDefault();
    event.stopPropagation();
    void expandHistory(viewport);
  }, { capture: true, passive: false });

  function installYearLabels() {
    ensureYearLabelStyles();
    const container = document.getElementById('ledgerTrendContainer');
    if (!container) return;

    const apply = () => {
      const data = activeData();
      if (data) annotateYearLabels(data.monthly_trend);
    };
    apply();

    if (typeof MutationObserver === 'function') {
      const observer = new MutationObserver(apply);
      observer.observe(container, { childList: true, subtree: true });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installYearLabels, { once: true });
  } else {
    installYearLabels();
  }

  window.WealthLedgerTimeseriesHistory = {
    mergeTrend,
    annotateYearLabels,
    updateTrendHeader,
    expandHistory,
  };
})();
