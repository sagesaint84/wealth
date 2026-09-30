(() => {
  'use strict';

  let selectedBroker = 'all';
  let latestRawPnlData = null;
  let applyingBrokerView = false;

  let selectedDividendBroker = 'all';
  let latestRawDividendData = null;
  let dividendRequestSequence = 0;

  const text = (value) => String(value ?? '').normalize('NFKC').replace(/\s+/g, ' ').trim();

  function syncDividendAnnualLabel() {
    const label = document.getElementById('dividendCurrentMonthText');
    const picker = document.getElementById('dividendMonthPicker');
    if (label && typeof selectedDividendYear !== 'undefined') {
      label.textContent = selectedDividendYear === 'all' ? '전체 기간' : `${selectedDividendYear}년 전체`;
    }
    if (picker) picker.value = '';
  }

  function clearDividendMonthForYearSelection() {
    if (typeof selectedDividendMonth === 'undefined' || selectedDividendMonth === null) return;
    selectedDividendMonth = null;
    if (typeof syncDividendMonthNavUI === 'function') syncDividendMonthNavUI();

    if (typeof currentDividendMode !== 'undefined' && currentDividendMode === 'actual') {
      if (typeof actualDividendData !== 'undefined' && actualDividendData && typeof renderActualDividends === 'function') {
        renderActualDividends(actualDividendData);
      }
      syncDividendAnnualLabel();
      return;
    }
    if (typeof dividendData !== 'undefined' && dividendData && typeof renderDividends === 'function') {
      renderDividends(dividendData);
    }
    syncDividendAnnualLabel();
  }

  function brokerLabel(record) {
    return text(record?.broker);
  }

  function brokerMatches(record, broker) {
    const label = brokerLabel(record);
    if (broker === '__unassigned__') return !label;
    return label === broker;
  }

  function brokerChoicesFromRecords(records) {
    const counts = new Map();
    let unassigned = 0;
    (Array.isArray(records) ? records : []).forEach((record) => {
      const broker = brokerLabel(record);
      if (!broker) {
        unassigned += 1;
        return;
      }
      counts.set(broker, (counts.get(broker) || 0) + 1);
    });
    return {
      rows: [...counts.entries()].sort((a, b) => a[0].localeCompare(b[0], 'ko')),
      unassigned,
    };
  }

  function escapeOption(value) {
    return text(value)
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }

  function allDividendIncomeRecords(rawData) {
    return [
      ...(Array.isArray(rawData?.records) ? rawData.records : []),
      ...(Array.isArray(rawData?.interest_records) ? rawData.interest_records : []),
    ];
  }

  function dividendAvailableYears(rawData) {
    const years = [...new Set(allDividendIncomeRecords(rawData)
      .map((record) => text(record?.date).slice(0, 4))
      .filter((year) => /^\d{4}$/.test(year)))];
    if (!years.length && typeof selectedDividendYear !== 'undefined' && /^\d{4}$/.test(String(selectedDividendYear))) {
      years.push(String(selectedDividendYear));
    }
    return years.sort((a, b) => b.localeCompare(a));
  }

  function dividendBrokerChoices(rawData) {
    return brokerChoicesFromRecords(allDividendIncomeRecords(rawData));
  }

  function dividendAmountKrw(record) {
    const value = Number(record?.amount_krw);
    return Number.isFinite(value) ? value : 0;
  }

  function dividendRecordMatches(record, year, broker) {
    const date = text(record?.date);
    const yearMatches = !year || year === 'all' || date.slice(0, 4) === String(year);
    const brokerMatchesScope = broker === 'all' || brokerMatches(record, broker);
    return yearMatches && brokerMatchesScope;
  }

  function buildDividendMonthBucket(records, month) {
    const items = (Array.isArray(records) ? records : [])
      .filter((record) => Number(text(record?.date).slice(5, 7)) === Number(month))
      .sort((a, b) => text(b?.date).localeCompare(text(a?.date)));
    return {
      month,
      total_krw: Math.round(items.reduce((sum, record) => sum + dividendAmountKrw(record), 0)),
      items,
    };
  }

  function buildDividendYearBucket(records, year) {
    const items = (Array.isArray(records) ? records : [])
      .filter((record) => text(record?.date).slice(0, 4) === String(year))
      .sort((a, b) => text(b?.date).localeCompare(text(a?.date)));
    return {
      year: String(year),
      total_krw: Math.round(items.reduce((sum, record) => sum + dividendAmountKrw(record), 0)),
      items,
    };
  }

  function buildDividendFilteredData(rawData, year, broker = selectedDividendBroker) {
    if (!rawData) return rawData;
    const selectedYear = year || 'all';
    const availableYears = dividendAvailableYears(rawData);
    const allDividends = Array.isArray(rawData.records) ? rawData.records : [];
    const allInterest = Array.isArray(rawData.interest_records) ? rawData.interest_records : [];
    const brokerScopedDividends = broker === 'all'
      ? allDividends
      : allDividends.filter((record) => brokerMatches(record, broker));
    const records = allDividends
      .filter((record) => dividendRecordMatches(record, selectedYear, broker))
      .sort((a, b) => text(b?.date).localeCompare(text(a?.date)));
    const interestRecords = allInterest
      .filter((record) => dividendRecordMatches(record, selectedYear, broker))
      .sort((a, b) => text(b?.date).localeCompare(text(a?.date)));
    const totalDividend = records.reduce((sum, record) => sum + dividendAmountKrw(record), 0);
    const totalInterest = interestRecords.reduce((sum, record) => sum + dividendAmountKrw(record), 0);
    const payingCodes = new Set(records.map((record) => text(record?.code)).filter(Boolean));

    return {
      ...rawData,
      year: String(selectedYear),
      available_years: availableYears,
      total_actual_dividend_krw: Math.round(totalDividend),
      monthly_avg_dividend_krw: Math.round(totalDividend / 12),
      record_count: records.length,
      paying_stock_count: payingCodes.size,
      monthly_schedule: Array.from({ length: 12 }, (_, idx) => buildDividendMonthBucket(records, idx + 1)),
      yearly_schedule: [...availableYears]
        .sort()
        .map((availableYear) => buildDividendYearBucket(brokerScopedDividends, availableYear)),
      records,
      total_actual_interest_krw: Math.round(totalInterest),
      interest_record_count: interestRecords.length,
      interest_records: interestRecords,
      __dividend_filtered_view: true,
    };
  }

  function ensureDividendBrokerFilter(rawData = latestRawDividendData) {
    const yearSelect = document.getElementById('dividendYearSelect');
    if (!yearSelect?.parentElement) return null;

    let select = document.getElementById('dividendBrokerFilter');
    if (!select) {
      select = document.createElement('select');
      select.id = 'dividendBrokerFilter';
      select.className = 'heatmap-select';
      select.style.minWidth = '130px';
      select.style.fontSize = '12px';
      select.setAttribute('aria-label', '배당·이자 증권사 선택');
      yearSelect.parentElement.appendChild(select);
      select.addEventListener('change', () => {
        selectedDividendBroker = select.value || 'all';
        renderDividendView();
      });
    }

    const { rows, unassigned } = dividendBrokerChoices(rawData);
    const values = new Set(['all', ...rows.map(([broker]) => broker)]);
    if (unassigned) values.add('__unassigned__');
    if (!values.has(selectedDividendBroker)) selectedDividendBroker = 'all';

    const options = [
      '<option value="all">전체 증권사</option>',
      ...rows.map(([broker, count]) => `<option value="${escapeOption(broker)}">${escapeOption(broker)} (${count})</option>`),
      ...(unassigned ? [`<option value="__unassigned__">증권사 미지정 (${unassigned})</option>`] : []),
    ];
    const html = options.join('');
    if (select.innerHTML !== html) select.innerHTML = html;
    select.value = selectedDividendBroker;
    return select;
  }

  function renderDividendView() {
    if (!latestRawDividendData) return;
    ensureDividendBrokerFilter(latestRawDividendData);
    const year = typeof selectedDividendYear !== 'undefined' ? selectedDividendYear : 'all';
    const view = buildDividendFilteredData(latestRawDividendData, year, selectedDividendBroker);
    if (typeof actualDividendData !== 'undefined') actualDividendData = view;
    if (typeof currentDividendMode !== 'undefined' && currentDividendMode === 'actual' && typeof renderActualDividends === 'function') {
      renderActualDividends(view);
    }
    if (typeof updateDividendYearOptions === 'function') updateDividendYearOptions(view?.available_years || []);
    if (typeof selectedDividendMonth !== 'undefined' && selectedDividendMonth === null) syncDividendAnnualLabel();
  }

  async function loadActualDividendScope(owner, year) {
    const requestSequence = ++dividendRequestSequence;
    const activeOwner = owner ?? (typeof currentOwner !== 'undefined' ? currentOwner : '모두');
    const activeYear = year ?? (typeof selectedDividendYear !== 'undefined' ? selectedDividendYear : 'all');
    try {
      const rawData = await api(`/api/actual-dividends?owner=${encodeURIComponent(activeOwner)}&year=all`);
      if (requestSequence !== dividendRequestSequence) return;
      latestRawDividendData = rawData;
      ensureDividendBrokerFilter(rawData);
      const view = buildDividendFilteredData(rawData, activeYear, selectedDividendBroker);
      if (typeof actualDividendData !== 'undefined') actualDividendData = view;
      if (typeof currentDividendMode !== 'undefined' && currentDividendMode === 'actual' && typeof renderActualDividends === 'function') {
        renderActualDividends(view);
      }
      if (typeof updateDividendYearOptions === 'function') updateDividendYearOptions(view?.available_years || []);
      if (typeof selectedDividendMonth !== 'undefined' && selectedDividendMonth === null) syncDividendAnnualLabel();
      return view;
    } catch (err) {
      console.error('실제 배당·이자 정보를 불러오지 못했습니다.', err);
      return undefined;
    }
  }

  if (typeof loadActualDividends === 'function') {
    window.loadActualDividends = loadActualDividendScope;
  }

  function finitePnlKrw(record) {
    const raw = record?.pnl_krw;
    if (raw === null || raw === undefined || raw === '') return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  }

  function summarizeRows(records) {
    if (typeof summarizeRealizedPnlRows === 'function') {
      return summarizeRealizedPnlRows(records);
    }
    let totalPnlKrw = 0;
    let convertedRecordCount = 0;
    let unconvertedRecordCount = 0;
    let winCount = 0;
    let lossCount = 0;
    records.forEach((record) => {
      const value = finitePnlKrw(record);
      if (value === null) {
        unconvertedRecordCount += 1;
        return;
      }
      convertedRecordCount += 1;
      totalPnlKrw += value;
      if (value > 0) winCount += 1;
      else if (value < 0) lossCount += 1;
    });
    const classified = winCount + lossCount;
    return {
      totalPnlKrw,
      convertedRecordCount,
      unconvertedRecordCount,
      recordCount: records.length,
      winCount,
      lossCount,
      winRate: classified ? (winCount / classified) * 100 : 0,
      summaryComplete: unconvertedRecordCount === 0,
    };
  }

  function buildBucket(records, key, value) {
    const items = records
      .filter((record) => {
        const date = text(record?.date);
        if (key === 'month') return Number(date.slice(5, 7)) === Number(value);
        return date.slice(0, 4) === String(value);
      })
      .sort((a, b) => text(b?.date).localeCompare(text(a?.date)));

    let total = 0;
    let wins = 0;
    let losses = 0;
    let converted = 0;
    let unconverted = 0;
    items.forEach((record) => {
      const amount = finitePnlKrw(record);
      if (amount === null) {
        unconverted += 1;
        return;
      }
      converted += 1;
      total += amount;
      if (amount > 0) wins += amount;
      else if (amount < 0) losses += amount;
    });

    return {
      [key]: value,
      total_krw: Math.round(total),
      win_krw: Math.round(wins),
      loss_krw: Math.round(losses),
      converted_record_count: converted,
      unconverted_record_count: unconverted,
      summary_complete: unconverted === 0,
      items,
    };
  }

  function buildBrokerFilteredData(rawData) {
    if (!rawData || selectedBroker === 'all') return rawData;
    const sourceRecords = Array.isArray(rawData.records) ? rawData.records : [];
    const records = sourceRecords.filter((record) => brokerMatches(record, selectedBroker));
    const summary = summarizeRows(records);
    const availableYears = Array.isArray(rawData.available_years) ? rawData.available_years : [];

    let totalWin = 0;
    let totalLoss = 0;
    records.forEach((record) => {
      const value = finitePnlKrw(record);
      if (value === null) return;
      if (value > 0) totalWin += value;
      else if (value < 0) totalLoss += value;
    });

    return {
      ...rawData,
      total_pnl_krw: Math.round(summary.totalPnlKrw || 0),
      total_win_krw: Math.round(totalWin),
      total_loss_krw: Math.round(totalLoss),
      win_count: summary.winCount || 0,
      loss_count: summary.lossCount || 0,
      win_rate: summary.winRate || 0,
      record_count: records.length,
      converted_record_count: summary.convertedRecordCount || 0,
      unconverted_record_count: summary.unconvertedRecordCount || 0,
      win_loss_record_count: (summary.winCount || 0) + (summary.lossCount || 0),
      summary_complete: Boolean(summary.summaryComplete),
      monthly_schedule: Array.from({ length: 12 }, (_, idx) => buildBucket(records, 'month', idx + 1)),
      yearly_schedule: availableYears
        .map(String)
        .sort()
        .map((availableYear) => buildBucket(records, 'year', availableYear)),
      records,
      __broker_filtered_view: true,
    };
  }

  function brokerChoices(rawData) {
    return brokerChoicesFromRecords(rawData?.records || []);
  }

  function ensureBrokerFilter(rawData = latestRawPnlData) {
    const yearSelect = document.getElementById('pnlYearSelect');
    if (!yearSelect?.parentElement) return null;

    let select = document.getElementById('pnlBrokerFilter');
    if (!select) {
      select = document.createElement('select');
      select.id = 'pnlBrokerFilter';
      select.className = 'heatmap-select';
      select.style.minWidth = '130px';
      select.style.fontSize = '12px';
      select.setAttribute('aria-label', '실현손익 증권사 선택');
      yearSelect.parentElement.appendChild(select);
      select.addEventListener('change', () => {
        selectedBroker = select.value || 'all';
        applyBrokerFilter();
      });
    }

    const { rows, unassigned } = brokerChoices(rawData);
    const values = new Set(['all', ...rows.map(([broker]) => broker)]);
    if (unassigned) values.add('__unassigned__');
    if (!values.has(selectedBroker)) selectedBroker = 'all';

    const options = [
      '<option value="all">전체 증권사</option>',
      ...rows.map(([broker, count]) => `<option value="${escapeOption(broker)}">${escapeOption(broker)} (${count})</option>`),
      ...(unassigned ? [`<option value="__unassigned__">증권사 미지정 (${unassigned})</option>`] : []),
    ];
    const html = options.join('');
    if (select.innerHTML !== html) select.innerHTML = html;
    select.value = selectedBroker;
    return select;
  }

  const originalRenderRealizedPnl = typeof renderRealizedPnl === 'function' ? renderRealizedPnl : null;

  function renderBrokerView(rawData) {
    if (!originalRenderRealizedPnl || !rawData) return;
    const view = buildBrokerFilteredData(rawData);
    if (typeof pnlData !== 'undefined') pnlData = view;
    applyingBrokerView = true;
    try {
      originalRenderRealizedPnl(view);
    } finally {
      applyingBrokerView = false;
    }
    ensureBrokerFilter(rawData);
  }

  function applyBrokerFilter() {
    const rawData = latestRawPnlData || (typeof pnlData !== 'undefined' ? pnlData : null);
    if (!rawData) return;
    renderBrokerView(rawData.__broker_filtered_view ? latestRawPnlData : rawData);
  }

  if (originalRenderRealizedPnl) {
    window.renderRealizedPnl = function wealthRenderRealizedPnlWithBroker(data) {
      if (!applyingBrokerView && data && !data.__broker_filtered_view) latestRawPnlData = data;
      const rawData = latestRawPnlData || data;
      renderBrokerView(rawData);
    };
  }

  document.addEventListener('pointerdown', (event) => {
    if (event.target?.id === 'dividendYearSelect') clearDividendMonthForYearSelection();
  }, true);

  document.addEventListener('keydown', (event) => {
    if (event.target?.id !== 'dividendYearSelect') return;
    if (event.key === 'Enter' || event.key === ' ') clearDividendMonthForYearSelection();
  }, true);

  const observer = new MutationObserver(() => {
    if (!document.getElementById('pnlBrokerFilter')) {
      const data = latestRawPnlData || (typeof pnlData !== 'undefined' ? pnlData : null);
      ensureBrokerFilter(data);
    }
    if (!document.getElementById('dividendBrokerFilter')) {
      ensureDividendBrokerFilter(latestRawDividendData);
    }
  });

  function install() {
    const pnl = typeof pnlData !== 'undefined' ? pnlData : null;
    if (pnl && !pnl.__broker_filtered_view) latestRawPnlData = pnl;
    ensureBrokerFilter(latestRawPnlData || pnl);
    ensureDividendBrokerFilter(latestRawDividendData);
    observer.observe(document.body, { childList: true, subtree: true });

    if (typeof api === 'function' && typeof loadActualDividends === 'function') {
      const owner = typeof currentOwner !== 'undefined' ? currentOwner : '모두';
      const year = typeof selectedDividendYear !== 'undefined' ? selectedDividendYear : 'all';
      void window.loadActualDividends(owner, year);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();

  window.WealthIncomePeriodBrokerFilter = {
    text,
    buildBrokerFilteredData,
    brokerChoices,
    buildDividendFilteredData,
    dividendAvailableYears,
    dividendBrokerChoices,
    clearDividendMonthForYearSelection,
    syncDividendAnnualLabel,
  };
})();
