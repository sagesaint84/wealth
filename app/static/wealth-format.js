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

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[character]));
  }

  // Reuse Intl for one display pass; callers retain their existing fallback.
  function createCurrencyFormatter(currency, fallback) {
    let formatter;
    try {
      formatter = new Intl.NumberFormat('ko-KR', {
        style: 'currency', currency, maximumFractionDigits: currency === 'KRW' ? 0 : 2,
      });
    } catch { /* Preserve the caller's legacy fallback. */ }
    return value => {
      if (!formatter) return fallback(value);
      try { return formatter.format(Number(value || 0)); }
      catch { return fallback(value); }
    };
  }

  function escapeOptionalHtml(value) {
    return value ? escapeHtml(value) : '';
  }

  window.WealthFormat = Object.freeze({ formatMoney, roundGroupedKoKr, fixedNumberKoKr, createCurrencyFormatter, escapeHtml, escapeOptionalHtml });
})();
