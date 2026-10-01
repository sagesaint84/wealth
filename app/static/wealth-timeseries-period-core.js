/* Pure time-series bucketing helpers shared by all Wealth chart adapters. */
(function (root) {
  'use strict';

  const MODES = Object.freeze({
    DAY: '1D',
    WEEK: '1W',
    MONTH: '1M',
    YEAR: '1Y',
    ALL: 'ALL',
  });

  const pad2 = value => String(value).padStart(2, '0');
  const finite = value => Number.isFinite(Number(value)) ? Number(value) : 0;

  function parseDate(value) {
    const text = String(value || '').trim();
    const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) return null;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(Date.UTC(year, month - 1, day));
    if (
      date.getUTCFullYear() !== year
      || date.getUTCMonth() !== month - 1
      || date.getUTCDate() !== day
    ) return null;
    return date;
  }

  function isoDate(date) {
    return `${date.getUTCFullYear()}-${pad2(date.getUTCMonth() + 1)}-${pad2(date.getUTCDate())}`;
  }

  function startOfWeek(date) {
    const copy = new Date(date.getTime());
    const weekday = copy.getUTCDay();
    const offset = weekday === 0 ? -6 : 1 - weekday;
    copy.setUTCDate(copy.getUTCDate() + offset);
    return copy;
  }

  function bucketKey(dateValue, mode) {
    const date = dateValue instanceof Date ? dateValue : parseDate(dateValue);
    if (!date) return '';
    if (mode === MODES.DAY) return isoDate(date);
    if (mode === MODES.WEEK) return isoDate(startOfWeek(date));
    if (mode === MODES.MONTH) return `${date.getUTCFullYear()}-${pad2(date.getUTCMonth() + 1)}`;
    if (mode === MODES.YEAR) return String(date.getUTCFullYear());
    return isoDate(date);
  }

  function modeForAll(records, dateField = 'date') {
    const dates = (Array.isArray(records) ? records : [])
      .map(record => parseDate(record?.[dateField]))
      .filter(Boolean)
      .sort((a, b) => a - b);
    if (dates.length < 2) return MODES.DAY;
    const spanDays = Math.max(1, Math.round((dates.at(-1) - dates[0]) / 86400000));
    if (spanDays <= 120) return MODES.DAY;
    if (spanDays <= 730) return MODES.WEEK;
    if (spanDays <= 3650) return MODES.MONTH;
    return MODES.YEAR;
  }

  function effectiveMode(records, mode, dateField = 'date') {
    return mode === MODES.ALL ? modeForAll(records, dateField) : mode;
  }

  function bucketLabel(key, mode) {
    if (!key) return '';
    if (mode === MODES.DAY) {
      const [, month, day] = key.split('-');
      return `${Number(month)}/${Number(day)}`;
    }
    if (mode === MODES.WEEK) {
      const date = parseDate(key);
      if (!date) return key;
      return `${date.getUTCMonth() + 1}/${date.getUTCDate()}주`;
    }
    if (mode === MODES.MONTH) {
      return `${Number(key.slice(5, 7))}월`;
    }
    return key;
  }

  function bucketYear(key, mode) {
    if (!key) return '';
    return mode === MODES.YEAR ? key : key.slice(0, 4);
  }

  function groupRecords(records, mode, dateField = 'date') {
    const source = (Array.isArray(records) ? records : [])
      .filter(record => parseDate(record?.[dateField]))
      .sort((a, b) => String(a?.[dateField] || '').localeCompare(String(b?.[dateField] || '')));
    const resolved = effectiveMode(source, mode, dateField);
    const grouped = new Map();
    source.forEach(record => {
      const key = bucketKey(record?.[dateField], resolved);
      if (!key) return;
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(record);
    });
    return {
      mode: resolved,
      buckets: [...grouped.entries()].map(([key, items], index, all) => ({
        key,
        label: bucketLabel(key, resolved),
        year: bucketYear(key, resolved),
        yearMarker: index === 0 || bucketYear(key, resolved) !== bucketYear(all[index - 1][0], resolved),
        items,
      })),
    };
  }

  function aggregateState(records, mode, {
    dateField = 'date',
    valueField = 'value',
    changeField = null,
  } = {}) {
    const grouped = groupRecords(records, mode, dateField);
    let previousClose = null;
    const buckets = grouped.buckets.map(bucket => {
      const last = bucket.items.at(-1);
      const close = finite(last?.[valueField]);
      const change = changeField
        ? bucket.items.reduce((sum, item) => sum + finite(item?.[changeField]), 0)
        : (previousClose == null ? 0 : close - previousClose);
      previousClose = close;
      return {
        ...bucket,
        close,
        change,
        last,
      };
    });
    return { mode: grouped.mode, buckets };
  }

  function aggregateFlow(records, mode, {
    dateField = 'date',
    fields = [],
  } = {}) {
    const grouped = groupRecords(records, mode, dateField);
    const buckets = grouped.buckets.map(bucket => {
      const values = {};
      fields.forEach(field => {
        values[field] = bucket.items.reduce((sum, item) => sum + finite(item?.[field]), 0);
      });
      return {
        ...bucket,
        values,
      };
    });
    return { mode: grouped.mode, buckets };
  }

  const api = {
    MODES,
    parseDate,
    isoDate,
    startOfWeek,
    bucketKey,
    bucketLabel,
    bucketYear,
    modeForAll,
    effectiveMode,
    groupRecords,
    aggregateState,
    aggregateFlow,
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.WealthTimeseriesPeriodCore = api;
})(typeof window !== 'undefined' ? window : globalThis);
