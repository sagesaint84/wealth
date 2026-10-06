(() => {
  'use strict';

  const period = window.WealthPeriodFilter;
  if (!period || typeof api !== 'function' || typeof renderLedger !== 'function') {
    console.error('Ledger period filter requires WealthPeriodFilter, api, and renderLedger.');
    return;
  }

  const originalRenderLedger = renderLedger;
  let annualView = false;
  let requestSequence = 0;

  const moneyNumber = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;

  function currentKstYear() {
    if (typeof getKstYearMonth === 'function') return Number(getKstYearMonth().year);
    return new Date().getFullYear();
  }

  function ledgerYearOptions() {
    const selected = typeof currentLedgerYear !== 'undefined' ? currentLedgerYear : currentKstYear();
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
        currentLedgerYear = year;
        annualView = true;
        void window.loadLedger();
      });

      select.addEventListener('pointerdown', () => {
        // 실현손익/배당·이자와 동일하게 연도 컨트롤을 조작하면 연간 보기로 전환한다.
        annualView = true;
      }, true);
      select.addEventListener('click', () => {
        if (!annualView) return;
        const year = Number(select.value);
        if (Number.isInteger(year) && year === Number(currentLedgerYear)) void window.loadLedger();
      });
    }

    const years = ledgerYearOptions();
    const html = years.map((year) => `<option value="${year}">${year}년</option>`).join('');
    if (select.innerHTML !== html) select.innerHTML = html;
    select.value = String(currentLedgerYear);
    return select;
  }

  function enterMonthlyView() {
    annualView = false;
  }

  async function fetchLedgerMonth(owner, year, month) {
    return api(`/api/ledger?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&owner=${encodeURIComponent(owner)}`);
  }

  function aggregateCategories(months, key, total) {
    const sums = new Map();
    months.forEach((item) => {
      (item?.[key] || []).forEach((row) => {
        const category = period.text(row?.category) || (key === 'category_expenses' ? '기타지출' : '기타수입');
        sums.set(category, (sums.get(category) || 0) + moneyNumber(row?.amount));
      });
    });
    return [...sums.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([category, amount]) => ({
        category,
        amount,
        ...(key === 'category_expenses' ? { percent: total > 0 ? Math.round((amount / total) * 1000) / 10 : 0 } : {}),
      }));
  }

  function mergeAnnualLedger(months, owner, year) {
    const monthRows = months.filter(Boolean);
    const totalIncome = monthRows.reduce((sum, row) => sum + moneyNumber(row.total_income), 0);
    const totalExpense = monthRows.reduce((sum, row) => sum + moneyNumber(row.total_expense), 0);
    const totalTransfer = monthRows.reduce((sum, row) => sum + moneyNumber(row.total_transfer), 0);
    const netSavings = totalIncome - totalExpense;
    const last = monthRows.at(-1) || {};
    const transactions = monthRows
      .flatMap((row) => Array.isArray(row.transactions) ? row.transactions : [])
      .sort((a, b) => period.text(b?.date).localeCompare(period.text(a?.date)));

    return {
      ...last,
      year,
      month: null,
      owner,
      period_mode: 'annual',
      total_income: totalIncome,
      total_expense: totalExpense,
      total_transfer: totalTransfer,
      net_savings: netSavings,
      savings_rate: totalIncome > 0 ? Math.round((netSavings / totalIncome) * 1000) / 10 : 0,
      recurring_expense_total: moneyNumber(last.recurring_expense_total),
      category_expenses: aggregateCategories(monthRows, 'category_expenses', totalExpense),
      category_incomes: aggregateCategories(monthRows, 'category_incomes', totalIncome),
      monthly_trend: Array.from({ length: 12 }, (_, idx) => {
        const month = idx + 1;
        const row = monthRows.find((item) => Number(item.month) === month) || {};
        const income = moneyNumber(row.total_income);
        const expense = moneyNumber(row.total_expense);
        return { year, month, label: `${month}월`, income, expense, savings: income - expense };
      }),
      transactions,
      record_count: transactions.length,
      __ledger_annual_view: true,
    };
  }

  async function loadAnnualLedger(owner, year, sequence) {
    const rows = [];
    for (let month = 1; month <= 12; month += 1) {
      const row = await fetchLedgerMonth(owner, year, month);
      if (sequence !== requestSequence) return null;
      rows.push(row);
    }
    return mergeAnnualLedger(rows, owner, year);
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
    if (trendTitle) trendTitle.textContent = `${data.year}년 1월 ~ 12월 현금흐름 추이`;

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
    if (trendTitle) trendTitle.textContent = '최근 6개월 현금흐름 추이';

    document.querySelectorAll('#ledgerTrendContainer .ledger-trend-col').forEach((col) => {
      delete col.dataset.ledgerMonth;
      col.style.cursor = '';
    });
    const select = ensureLedgerYearFilter();
    if (select) select.value = String(data?.year ?? currentLedgerYear);
  }

  function renderLedgerPeriodAware(data) {
    if (!data) return;
    if (data.__ledger_annual_view || annualView) {
      const renderData = { ...data, month: Number(currentLedgerMonth) || 1 };
      originalRenderLedger(renderData);
      updateLedgerHeaderForAnnual(data);
    } else {
      originalRenderLedger(data);
      updateLedgerHeaderForMonthly(data);
    }
    ensureLedgerYearFilter();
  }

  window.renderLedger = renderLedgerPeriodAware;

  window.loadLedger = async function loadLedgerWithPeriodScope() {
    const sequence = ++requestSequence;
    const owner = typeof currentOwner !== 'undefined' && currentOwner ? currentOwner : '모두';
    const year = Number(currentLedgerYear) || currentKstYear();
    try {
      const data = annualView
        ? await loadAnnualLedger(owner, year, sequence)
        : await fetchLedgerMonth(owner, year, Number(currentLedgerMonth) || 1);
      if (!data || sequence !== requestSequence) return;
      if (typeof rawLedgerData !== 'undefined') rawLedgerData = data;
      renderLedgerPeriodAware(data);
      return data;
    } catch (err) {
      console.error('가계부 기간 조회 오류:', err);
      return undefined;
    }
  };

  document.addEventListener('pointerdown', (event) => {
    if (event.target?.closest?.('#ledgerPrevMonthBtn, #ledgerNextMonthBtn, #ledgerTodayMonthBtn, #ledgerMonthPicker')) {
      enterMonthlyView();
    }
  }, true);

  document.addEventListener('change', (event) => {
    if (event.target?.id === 'ledgerMonthPicker') enterMonthlyView();
  }, true);

  document.addEventListener('click', (event) => {
    const col = event.target?.closest?.('#ledgerTrendContainer .ledger-trend-col[data-ledger-month]');
    if (!col || !annualView) return;
    const month = Number(col.dataset.ledgerMonth);
    if (!Number.isInteger(month) || month < 1 || month > 12) return;
    currentLedgerMonth = month;
    annualView = false;
    void window.loadLedger();
  });

  function install() {
    ensureLedgerYearFilter();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();

  window.WealthLedgerPeriodFilter = {
    isAnnualView: () => annualView,
    setAnnualView(value) { annualView = Boolean(value); },
    mergeAnnualLedger,
    ensureLedgerYearFilter,
  };
})();
