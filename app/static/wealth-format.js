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

  window.WealthFormat = Object.freeze({ formatMoney, roundGroupedKoKr });
})();
