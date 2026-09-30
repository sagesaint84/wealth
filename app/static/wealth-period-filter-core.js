(() => {
  'use strict';
  if (window.WealthPeriodFilter) return;

  const text = (value) => String(value ?? '').normalize('NFKC').replace(/\s+/g, ' ').trim();

  function normalizeYear(value, fallback = 'all') {
    const normalized = text(value);
    if (!normalized || normalized === '전체') return fallback;
    if (normalized === 'all') return 'all';
    return /^\d{4}$/.test(normalized) ? normalized : fallback;
  }

  function normalizeMonth(value) {
    if (value === null || value === undefined || value === '' || value === 'all' || value === '전체') return null;
    const month = Number(value);
    return Number.isInteger(month) && month >= 1 && month <= 12 ? month : null;
  }

  function recordYear(record, dateField = 'date') {
    return text(record?.[dateField]).slice(0, 4);
  }

  function recordMonth(record, dateField = 'date') {
    const month = Number(text(record?.[dateField]).slice(5, 7));
    return Number.isInteger(month) && month >= 1 && month <= 12 ? month : null;
  }

  function matchesPeriod(record, { year = 'all', month = null, dateField = 'date' } = {}) {
    const normalizedYear = normalizeYear(year, 'all');
    const normalizedMonth = normalizeMonth(month);
    if (normalizedYear !== 'all' && recordYear(record, dateField) !== normalizedYear) return false;
    if (normalizedMonth !== null && recordMonth(record, dateField) !== normalizedMonth) return false;
    return true;
  }

  function filterRecords(records, scope = {}) {
    return (Array.isArray(records) ? records : []).filter((record) => matchesPeriod(record, scope));
  }

  function availableYears(records, { dateField = 'date', fallbackYear = null } = {}) {
    const years = [...new Set((Array.isArray(records) ? records : [])
      .map((record) => recordYear(record, dateField))
      .filter((year) => /^\d{4}$/.test(year)))];
    if (!years.length && fallbackYear && /^\d{4}$/.test(String(fallbackYear))) years.push(String(fallbackYear));
    return years.sort((a, b) => b.localeCompare(a));
  }

  function fixedYearRange(anchorYear, count = 6, selectedYear = null) {
    const anchor = Number(anchorYear);
    const years = [];
    if (Number.isInteger(anchor) && anchor >= 1900) {
      for (let offset = 0; offset < Math.max(1, Number(count) || 1); offset += 1) {
        years.push(String(anchor - offset));
      }
    }
    const selected = normalizeYear(selectedYear, 'all');
    if (selected !== 'all' && !years.includes(selected)) years.push(selected);
    return [...new Set(years)].sort((a, b) => b.localeCompare(a));
  }

  function scopeLabel(year, month, { allLabel = '전체 기간', annualSuffix = '년 전체' } = {}) {
    const normalizedYear = normalizeYear(year, 'all');
    const normalizedMonth = normalizeMonth(month);
    if (normalizedYear === 'all') return allLabel;
    if (normalizedMonth === null) return `${normalizedYear}${annualSuffix}`;
    return `${normalizedYear}년 ${normalizedMonth}월`;
  }

  function groupByMonth(records, year = 'all', dateField = 'date') {
    const normalizedYear = normalizeYear(year, 'all');
    return Array.from({ length: 12 }, (_, idx) => {
      const month = idx + 1;
      return {
        month,
        items: filterRecords(records, { year: normalizedYear, month, dateField }),
      };
    });
  }

  function groupByYear(records, years, dateField = 'date') {
    return (Array.isArray(years) ? years : []).map((year) => ({
      year: String(year),
      items: filterRecords(records, { year: String(year), month: null, dateField }),
    }));
  }

  window.WealthPeriodFilter = {
    text,
    normalizeYear,
    normalizeMonth,
    recordYear,
    recordMonth,
    matchesPeriod,
    filterRecords,
    availableYears,
    fixedYearRange,
    scopeLabel,
    groupByMonth,
    groupByYear,
  };
})();
