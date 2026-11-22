(() => {
  'use strict';

  function brokerRealizedDateKey(value) {
    if (!value) return '';
    return String(value).replace(/[^0-9]/g, '').slice(0, 8);
  }

  function sortBrokerRealizedFeedRows(rows, tokens) {
    const list = (rows || []).map((row, idx) => ({
      row,
      token: (tokens && tokens[idx]) || '',
      originalIndex: idx,
    }));
    list.sort((a, b) => {
      const dateA = brokerRealizedDateKey(a.row?.date || a.row?.trad_dt || a.row?.trade_date || '');
      const dateB = brokerRealizedDateKey(b.row?.date || b.row?.trad_dt || b.row?.trade_date || '');
      if (dateA !== dateB) {
        return dateA < dateB ? 1 : -1; // newest first
      }
      const codeA = String(a.row?.code || a.row?.pdno || a.row?.symbol || a.row?.product_code || '');
      const codeB = String(b.row?.code || b.row?.pdno || b.row?.symbol || b.row?.product_code || '');
      if (codeA !== codeB) {
        return codeA.localeCompare(codeB);
      }
      const hashA = String(a.row?.canonical_hash || '');
      const hashB = String(b.row?.canonical_hash || '');
      if (hashA !== hashB) {
        return hashA.localeCompare(hashB);
      }
      const occA = Number(a.row?.source_occurrence || 0);
      const occB = Number(b.row?.source_occurrence || 0);
      if (occA !== occB) {
        return occA - occB;
      }
      return a.originalIndex - b.originalIndex;
    });
    return {
      rows: list.map(item => item.row),
      selectionTokens: list.map(item => item.token),
    };
  }

  function create() {
    function applySuccessfulFeed(state, rows, selectionTokens) {
      const sortedFeed = sortBrokerRealizedFeedRows(rows, selectionTokens);
      state.rows = sortedFeed.rows;
      state.selectionTokens = sortedFeed.selectionTokens;
      state.selectedIndices.clear();
      state.importedIndices.clear();
      state.importPreferences.clear();
      state.previewTicket = null;
    }

    function selectedImportItems(state, buildItem) {
      return Array.from(state.selectedIndices)
        .sort((a, b) => a - b)
        .map(index => buildItem(state, index))
        .filter(Boolean);
    }

    return Object.freeze({ applySuccessfulFeed, selectedImportItems });
  }

  window.WealthBrokerRealizedFeedController = Object.freeze({ create, sortRows: sortBrokerRealizedFeedRows, dateKey: brokerRealizedDateKey });
})();
