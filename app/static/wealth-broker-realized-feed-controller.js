(() => {
  'use strict';

  function create({ sortRows }) {
    function applySuccessfulFeed(state, rows, selectionTokens) {
      const sortedFeed = sortRows(rows, selectionTokens);
      state.rows = sortedFeed.rows;
      state.selectionTokens = sortedFeed.selectionTokens;
      state.selectedIndices.clear();
      state.importedIndices.clear();
      state.importPreferences.clear();
      state.previewTicket = null;
    }

    return Object.freeze({ applySuccessfulFeed });
  }

  window.WealthBrokerRealizedFeedController = Object.freeze({ create });
})();
