(() => {
  'use strict';

  function filterTransactions(transactions, typeFilter, searchText) {
    const searchQ = searchText.toLowerCase().trim();
    return transactions.filter(t => {
      if (typeFilter !== "all" && t.type !== typeFilter) return false;
      if (searchQ) {
        const matchMerchant = (t.merchant || "").toLowerCase().includes(searchQ);
        const matchMemo = (t.memo || "").toLowerCase().includes(searchQ);
        const matchCat = (t.category || "").toLowerCase().includes(searchQ);
        if (!matchMerchant && !matchMemo && !matchCat) return false;
      }
      return true;
    });
  }

  window.WealthLedgerTransactionsModel = Object.freeze({ filterTransactions });
})();
