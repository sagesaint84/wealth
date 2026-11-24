(() => {
  'use strict';

  function loadMonth(api, year, month, owner) {
    return api(`/api/ledger?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}&owner=${encodeURIComponent(owner)}`);
  }

  function loadCards(api, owner) {
    return api(`/api/ledger/cards?owner=${encodeURIComponent(owner)}`);
  }

  const moneyNumber = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;

  function aggregateCategories(months, key, total, normalizeText) {
    const sums = new Map();
    months.forEach((item) => {
      (item?.[key] || []).forEach((row) => {
        const category = normalizeText(row?.category) || (key === 'category_expenses' ? '기타지출' : '기타수입');
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
    const normalizeText = globalThis.WealthPeriodFilter.text;
    const monthRows = months.filter(Boolean);
    const totalIncome = monthRows.reduce((sum, row) => sum + moneyNumber(row.total_income), 0);
    const totalExpense = monthRows.reduce((sum, row) => sum + moneyNumber(row.total_expense), 0);
    const totalTransfer = monthRows.reduce((sum, row) => sum + moneyNumber(row.total_transfer), 0);
    const netSavings = totalIncome - totalExpense;
    const last = monthRows.at(-1) || {};
    const transactions = monthRows
      .flatMap((row) => Array.isArray(row.transactions) ? row.transactions : [])
      .sort((a, b) => normalizeText(b?.date).localeCompare(normalizeText(a?.date)));

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
      category_expenses: aggregateCategories(monthRows, 'category_expenses', totalExpense, normalizeText),
      category_incomes: aggregateCategories(monthRows, 'category_incomes', totalIncome, normalizeText),
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

  globalThis.WealthLedgerData = Object.freeze({ loadMonth, loadCards, mergeAnnualLedger });
})();
