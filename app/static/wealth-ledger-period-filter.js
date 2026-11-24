(() => {
  'use strict';

  const period = window.WealthPeriodFilter;
  const ledger = window.WealthLedgerFeature;
  if (!period || !ledger) {
    console.error('Ledger period controls require WealthPeriodFilter and WealthLedgerFeature.');
    return;
  }

  function currentKstYear() {
    if (typeof getKstYearMonth === 'function') return Number(getKstYearMonth().year);
    return new Date().getFullYear();
  }

  function ledgerYearOptions() {
    const selected = ledger.getYear();
    return period.fixedYearRange(currentKstYear(), 6, selected);
  }

  function ensureLedgerYearFilter() {
    const monthControl = document.querySelector('.ledger-month-control');
    if (!monthControl) return null;

    let select = document.getElementById('ledgerYearSelect');
    if (!select) {
      select = document.createElement('select');
      select.id = 'ledgerYearSelect';
      select.className = 'heatmap-select';
      select.style.minWidth = '104px';
      select.style.fontSize = '12px';
      select.setAttribute('aria-label', '가계부 연도 선택');
      select.title = '연도를 선택하면 해당 연도 전체를 조회합니다.';
      monthControl.appendChild(select);

      select.addEventListener('change', () => {
        const year = Number(select.value);
        if (!Number.isInteger(year)) return;
        void ledger.selectAnnualYear(year);
      });

      select.addEventListener('pointerdown', () => {
        // 실현손익/배당·이자와 동일하게 연도 컨트롤을 조작하면 연간 보기로 전환한다.
        ledger.setAnnualView(true);
      }, true);
      select.addEventListener('click', () => {
        if (!ledger.isAnnualView()) return;
        const year = Number(select.value);
        if (Number.isInteger(year) && year === Number(ledger.getYear())) void ledger.loadLedger();
      });
    }

    const years = ledgerYearOptions();
    const html = years.map((year) => `<option value="${year}">${year}년</option>`).join('');
    if (select.innerHTML !== html) select.innerHTML = html;
    select.value = String(ledger.getYear());
    return select;
  }

  function updateLedgerHeaderForAnnual(data) {
    const monthText = document.getElementById('ledgerCurrentMonthText');
    const picker = document.getElementById('ledgerMonthPicker');
    if (monthText) monthText.textContent = period.scopeLabel(data.year, null);
    if (picker) picker.value = '';

    const incomeLabel = document.querySelector('.ledger-stat-income .saving-stat-label');
    const expenseLabel = document.querySelector('.ledger-stat-expense .saving-stat-label');
    if (incomeLabel) incomeLabel.textContent = '💰 연간 총 수입';
    if (expenseLabel) expenseLabel.textContent = '💳 연간 총 지출';

    const trendPanel = document.getElementById('ledgerTrendContainer')?.closest('.ledger-sub-panel');
    const trendTitle = trendPanel?.querySelector('h3');
    if (trendTitle && window.WealthLedgerChartModule?.state === 'failed') trendTitle.textContent = `${data.year}년 1월 ~ 12월 현금흐름 추이`;

    const cols = [...document.querySelectorAll('#ledgerTrendContainer .ledger-trend-col')];
    cols.forEach((col, idx) => {
      const month = idx + 1;
      col.dataset.ledgerMonth = String(month);
      col.style.cursor = 'pointer';
      col.title = `${data.year}년 ${month}월 상세 보기`;
    });
  }

  function updateLedgerHeaderForMonthly(data) {
    const incomeLabel = document.querySelector('.ledger-stat-income .saving-stat-label');
    const expenseLabel = document.querySelector('.ledger-stat-expense .saving-stat-label');
    if (incomeLabel) incomeLabel.textContent = '💰 이번 달 총 수입';
    if (expenseLabel) expenseLabel.textContent = '💳 이번 달 총 지출';

    const trendPanel = document.getElementById('ledgerTrendContainer')?.closest('.ledger-sub-panel');
    const trendTitle = trendPanel?.querySelector('h3');
    if (trendTitle && window.WealthLedgerChartModule?.state === 'failed') trendTitle.textContent = '최근 6개월 현금흐름 추이';

    document.querySelectorAll('#ledgerTrendContainer .ledger-trend-col').forEach((col) => {
      delete col.dataset.ledgerMonth;
      col.style.cursor = '';
    });
    const select = ensureLedgerYearFilter();
    if (select) select.value = String(data?.year ?? ledger.getYear());
  }

  function renderLedgerPeriodAware(data, render) {
    if (data.__ledger_annual_view || ledger.isAnnualView()) {
      render({ ...data, month: Number(ledger.getMonth()) || 1 });
      updateLedgerHeaderForAnnual(data);
    } else {
      render(data);
      updateLedgerHeaderForMonthly(data);
    }
    ensureLedgerYearFilter();
  }

  ledger.setPeriodRenderer(renderLedgerPeriodAware);

  document.addEventListener('pointerdown', (event) => {
    if (event.target?.closest?.('#ledgerPrevMonthBtn, #ledgerNextMonthBtn, #ledgerTodayMonthBtn, #ledgerMonthPicker')) {
      ledger.setAnnualView(false);
    }
  }, true);

  document.addEventListener('change', (event) => {
    if (event.target?.id === 'ledgerMonthPicker') ledger.setAnnualView(false);
  }, true);

  document.addEventListener('click', (event) => {
    const col = event.target?.closest?.('#ledgerTrendContainer .ledger-trend-col[data-ledger-month]');
    if (!col || !ledger.isAnnualView()) return;
    const month = Number(col.dataset.ledgerMonth);
    if (!Number.isInteger(month) || month < 1 || month > 12) return;
    void ledger.selectMonth(ledger.getYear(), month);
  });

  function install() {
    ensureLedgerYearFilter();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();

  window.WealthLedgerPeriodFilter = {
    isAnnualView: ledger.isAnnualView,
    setAnnualView: ledger.setAnnualView,
    mergeAnnualLedger: window.WealthLedgerData.mergeAnnualLedger,
    ensureLedgerYearFilter,
  };
})();
