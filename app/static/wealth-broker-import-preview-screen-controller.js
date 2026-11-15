(() => {
  'use strict';

  function renderRows({ document, details, data, brokerImportPreviewRow, formatters, resolveRow }) {
    const activeEl = document.activeElement;
    const activeFeedIndex = activeEl?.dataset?.feedIndex;
    const activeIsFee = activeEl?.classList?.contains('modal-broker-ipo-fee');
    const cursorStart = activeEl?.selectionStart;
    const cursorEnd = activeEl?.selectionEnd;

    const items = (data.items || []).filter(item => item.wealth_import);
    if (!items.length) {
      details.innerHTML = '';
      return false;
    }

    details.innerHTML = items.map(item => {
      const { feedIndex, preference } = resolveRow(item);
      const row = window.WealthBrokerImportPreviewModel.prepareRow(item, feedIndex, preference, formatters);
      return brokerImportPreviewRow(row);
    }).join('');

    if (activeFeedIndex != null && activeIsFee) {
      const newEl = details.querySelector(`.modal-broker-ipo-fee[data-feed-index="${activeFeedIndex}"]`);
      if (newEl) {
        newEl.focus();
        if (cursorStart != null && cursorEnd != null) {
          try { newEl.setSelectionRange(cursorStart, cursorEnd); } catch (_) {}
        }
      }
    }
    return true;
  }

  window.WealthBrokerImportPreviewScreenController = Object.freeze({ renderRows });
})();
