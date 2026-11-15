(() => {
  'use strict';

  function openPicker(monthPicker) {
    try {
      if (typeof monthPicker.showPicker === 'function') {
        monthPicker.showPicker();
      } else {
        monthPicker.focus();
        monthPicker.click();
      }
    } catch (err) {
      monthPicker.click();
    }
  }

  function bind({
    prefix, getKstYearMonth, shiftYearMonth, parseYearMonth,
    getYear, getMonth, beforeSelect, onMonthSelected,
  }) {
    const prevBtn = document.getElementById(prefix + 'PrevMonthBtn');
    const nextBtn = document.getElementById(prefix + 'NextMonthBtn');
    const todayBtn = document.getElementById(prefix + 'TodayMonthBtn');
    const monthText = document.getElementById(prefix + 'CurrentMonthText');
    const monthPicker = document.getElementById(prefix + 'MonthPicker');

    function shift(delta) {
      beforeSelect?.();
      const curYear = (getYear() === 'all' || !getYear()) ? getKstYearMonth().year : getYear();
      const curMonth = getMonth() || getKstYearMonth().month;
      const shifted = shiftYearMonth(curYear, curMonth, delta);
      return onMonthSelected(shifted.year, shifted.month);
    }

    prevBtn?.addEventListener('click', async () => { await shift(-1); });
    nextBtn?.addEventListener('click', async () => { await shift(1); });
    todayBtn?.addEventListener('click', async () => {
      beforeSelect?.();
      const cur = getKstYearMonth();
      await onMonthSelected(cur.year, cur.month);
    });

    if (monthText && monthPicker) {
      monthText.addEventListener('click', () => openPicker(monthPicker));

      monthPicker.addEventListener('change', async (e) => {
        const parsed = parseYearMonth(e.target.value);
        if (parsed) {
          beforeSelect?.();
          await onMonthSelected(parsed.year, parsed.month);
        }
      });
    }
  }

  window.WealthIncomeMonthNavigation = { bind, openPicker };
})();
