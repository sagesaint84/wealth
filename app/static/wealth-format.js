/* Pure display formatting. No DOM, feature state, input events or API access. */
(() => {
  'use strict';

  function roundGroupedKoKr(value) {
    return Math.round(value).toLocaleString('ko-KR');
  }

  function formatMoney(num) {
    if (num === null || num === undefined || isNaN(num)) return '—';
    return roundGroupedKoKr(num);
  }

  function fixedNumberKoKr(value, digits = 0) {
    if (value === null || value === undefined || value === '') return '—';
    const number = Number(value);
    return Number.isFinite(number) ? number.toLocaleString('ko-KR', { minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—';
  }

  window.WealthFormat = Object.freeze({ formatMoney, roundGroupedKoKr, fixedNumberKoKr });
})();
