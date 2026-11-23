(() => {
  'use strict';

  function create({
    document, brokerUI, state, prefix, statusButtonId, fetchButtonId, importButtonId,
    html, brokerRealizedDisplayRow, formatNumber, syncBrokerRowImportOptions, populateDestinationAccounts,
    previewScreenController, maskAccountDisplayLabel, brokerPreviewStatusLabel,
    pnlDigits, defaultCurrency, updateCommitButton, renderBrokerImportPreviewDetails,
  }) {
    function showMessage(message, type = 'info') { return brokerUI.showBrokerMessage(`${prefix}Message`, message, type); }

    function hideMessage() { brokerUI.hideBrokerMessage(`${prefix}Message`); }

    function renderFeedTable() {
      const tbody = document.getElementById(`${prefix}TableBody`);
      if (!tbody) return;
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
      brokerUI.setAccountFeedButtonsDisabled(statusButtonId, fetchButtonId, loading, state.sourceAccountKey);
    }

    return Object.freeze({
      showMessage, hideMessage, renderLoading, renderFeedTable, updateSelectionUI, renderPreviewModal,
    });
  }

  window.WealthBrokerRealizedScreenController = Object.freeze({ create });
})();
