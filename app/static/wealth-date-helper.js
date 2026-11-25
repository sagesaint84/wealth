(() => {
  'use strict';

  function getKstDateParts(now = new Date()) {
    try {
      const parts = new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Seoul',
        year: 'numeric',
        month: 'numeric',
        day: 'numeric',
      }).formatToParts(now).reduce((acc, p) => {
        if (p.type !== 'literal') acc[p.type] = p.value;
        return acc;
      }, {});
      const year = parseInt(parts.year, 10);
      const month = parseInt(parts.month, 10);
      const day = parseInt(parts.day, 10);
      return { year, month, day };
    } catch (e) {
      const d = new Date(new Date(now).getTime() + 9 * 60 * 60 * 1000);
      return { year: d.getUTCFullYear(), month: d.getUTCMonth() + 1, day: d.getUTCDate() };
    }
  }

  function getKstYearMonth(now = new Date()) {
    const { year, month } = getKstDateParts(now);
    const key = `${year}-${String(month).padStart(2, '0')}`;
    return { year, month, key };
  }

  function getKstIsoDate(now = new Date()) {
    const { year, month, day } = getKstDateParts(now);
    return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  }

  function getKstDateRange(dayCount = 30, now = new Date()) {
    const count = Number(dayCount);
    if (!Number.isInteger(count) || count < 1) throw new RangeError('dayCount must be a positive integer');
    const { year, month, day } = getKstDateParts(now);
    const todayUtc = Date.UTC(year, month - 1, day);
    const start = new Date(todayUtc - (count - 1) * 24 * 60 * 60 * 1000);
    const format = date => `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`;
    return { fromDate: format(start), toDate: format(new Date(todayUtc)) };
  }

  function shiftYearMonth(year, month, delta) {
    let y = Number(year);
    let m = Number(month) + Number(delta);
    while (m < 1) {
      m += 12;
      y -= 1;
    }
    while (m > 12) {
      m -= 12;
      y += 1;
    }
    const key = `${y}-${String(m).padStart(2, '0')}`;
    return { year: y, month: m, key };
  }

  function parseYearMonth(str) {
    if (typeof str !== 'string') return null;
    const trimmed = str.trim();
    const m1 = trimmed.match(/^(\d{4})-(\d{1,2})$/);
    if (m1) {
      const y = parseInt(m1[1], 10);
      const m = parseInt(m1[2], 10);
      if (m >= 1 && m <= 12) {
        return { year: y, month: m, key: `${y}-${String(m).padStart(2, '0')}` };
      }
    }
    const m2 = trimmed.match(/^(\d{4})년\s*(\d{1,2})월$/);
    if (m2) {
      const y = parseInt(m2[1], 10);
      const m = parseInt(m2[2], 10);
      if (m >= 1 && m <= 12) {
        return { year: y, month: m, key: `${y}-${String(m).padStart(2, '0')}` };
      }
    }
    return null;
  }

  // Split inputs use calendar month lengths while keeping their browser-local fallback date.
  function getDaysInMonth(year, month) {
    return new Date(year, month, 0).getDate();
  }

  const api = { getKstDateParts, getKstYearMonth, getKstIsoDate, getKstDateRange, shiftYearMonth, parseYearMonth };
  window.WealthDateHelper = { ...api, getDaysInMonth };
  // Preserve legacy classic-script globals as references to the same owner.
  Object.assign(window, api);
})();
