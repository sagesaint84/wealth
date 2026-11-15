(() => {
  'use strict';

  function loadMonth(api, year, month, owner) {
    return api(`/api/ledger?year=${year}&month=${month}&owner=${encodeURIComponent(owner)}`);
  }

  function loadCards(api, owner) {
    return api(`/api/ledger/cards?owner=${encodeURIComponent(owner)}`);
  }

  globalThis.WealthLedgerData = Object.freeze({ loadMonth, loadCards });
})();
