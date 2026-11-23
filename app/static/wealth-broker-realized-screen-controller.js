(() => {
  'use strict';

  function create({
    document, brokerUI, state, prefix, statusButtonId, fetchButtonId, importButtonId,
    html, brokerRealizedDisplayRow, formatNumber, syncBrokerRowImportOptions, populateDestinationAccounts,
    previewScreenController, maskAccountDisplayLabel, brokerPreviewStatusLabel,
    pnlDigits, defaultCurrency, updateCommitButton, renderBrokerImportPreviewDetails,
    messageId = `${prefix}Message`, loadingButtonIds, feedTable,
  }) {
    function showMessage(message, type = 'info') { return brokerUI.showBrokerMessage(messageId, message, type); }

    function hideMessage() { brokerUI.hideBrokerMessage(messageId); }

    function renderFeedTable(rows, context, status = 'ok') {
      const tbody = document.getElementById(feedTable?.bodyId ?? `${prefix}TableBody`);
      if (!tbody) return;
      if (feedTable) {
        const { checkboxClass, emptyMessage, adaptRow, toss = false, beforeRender,
          shouldSyncRowOptions, readIndex, onUpdate } = feedTable;
        beforeRender?.();
        brokerUI.renderRealizedTable({
          body: tbody, rows: rows || [], status, emptyMessage, selection: state,
          checkboxClass, adapt: row => adaptRow(row, context), toss,
        });
        if (!shouldSyncRowOptions || shouldSyncRowOptions(rows, status)) {
          syncBrokerRowImportOptions(state);
        }
        brokerUI.bindFeedSelection(tbody, `.${checkboxClass}`, event => {
          const index = readIndex(event.target);
          if (event.target.checked) {
            state.selectedIndices.add(index);
          } else {
            state.selectedIndices.delete(index);
          }
          onUpdate();
        });
        return;
      }
      brokerUI.renderBrokerImportFeedTable({
        body: tbody, state, checkboxClass: `${prefix}-row-check`,
        emptyMessage: '조회 버튼을 눌러 실현손익을 조회하세요.',
        adapt: row => brokerRealizedDisplayRow(row, { market: state.market, currency: state.market === 'us' ? 'USD' : 'KRW', formatNumber }),
        syncRowOptions: syncBrokerRowImportOptions,
        onUpdate: updateSelectionUI,
      });
    }

    function updateSelectionUI() {
      populateDestinationAccounts();
      brokerUI.renderBrokerImportSelectionState(state, {
        badgeId: `${prefix}SelectedCountBadge`,
        buttonId: importButtonId,
        destinationSelectId: `${prefix}DestinationAccount`,
      });
      syncBrokerRowImportOptions(state);
    }

    function renderPreviewModal(data) {
      const counts = data.counts || {};
      const dest = data.destination_account || {};
      previewScreenController.renderPreviewModal({
        document, brokerUI, data, prefix, counts,
        destination: brokerUI.brokerPreviewDestinationText(dest, maskAccountDisplayLabel),
        html, statusLabel: brokerPreviewStatusLabel, formatNumber,
        pnlDigits, defaultCurrency,
        updateCommitButton, renderDetails: renderBrokerImportPreviewDetails,
      });
    }

    function renderLoading(loading) {
      if (loadingButtonIds) {
        loadingButtonIds.forEach(id => brokerUI.setButtonDisabled(id, loading));
        return;
      }
      brokerUI.setAccountFeedButtonsDisabled(statusButtonId, fetchButtonId, loading, state.sourceAccountKey);
    }

    function bindImportEvents({
      confirmButtonId, closeButtonId, cancelButtonId, setLoading, openPreview, closeModal, updateCommitButton, commit,
      sourceAccountChanged,
    }) {
      document.getElementById(`${prefix}SourceAccount`)?.addEventListener('change', event => {
        sourceAccountChanged(event.target.value);
        updateSelectionUI();
        setLoading(false);
      });
      document.getElementById(`${prefix}DestinationAccount`)?.addEventListener('change', updateSelectionUI);
      document.getElementById(`${prefix}SelectAll`)?.addEventListener('change', event => {
        state.rows.forEach((_, index) => {
          if (state.importedIndices.has(index)) return;
          if (event.target.checked) state.selectedIndices.add(index);
          else state.selectedIndices.delete(index);
        });
        renderFeedTable();
        updateSelectionUI();
      });
      document.getElementById(importButtonId)?.addEventListener('click', openPreview);
      document.getElementById(closeButtonId)?.addEventListener('click', closeModal);
      document.getElementById(cancelButtonId)?.addEventListener('click', closeModal);
      document.getElementById(`${prefix}IncludePossibleDuplicates`)?.addEventListener('change', updateCommitButton);
      document.getElementById(confirmButtonId)?.addEventListener('click', commit);
    }

    return Object.freeze({
      showMessage, hideMessage, renderLoading, renderFeedTable, updateSelectionUI, renderPreviewModal, bindImportEvents,
    });
  }

  window.WealthBrokerRealizedScreenController = Object.freeze({ create });
})();
