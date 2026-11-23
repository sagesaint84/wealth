(() => {
  'use strict';

  function create({
    document, brokerUI, state,
    html, brokerRealizedDisplayRow, nhNumber, syncBrokerRowImportOptions, populateNhDestinationAccounts,
    previewScreenController, maskAccountDisplayLabel, brokerPreviewStatusLabel,
    updateNhCommitButton, renderBrokerImportPreviewDetails,
  }) {
    function showNhMessage(message, type = 'info') { return brokerUI.showBrokerMessage('nhMessage', message, type); }

    function hideNhMessage() { brokerUI.hideBrokerMessage('nhMessage'); }

    function renderNhFeedTable() {
      const tbody = document.getElementById('nhTableBody');
      if (!tbody) return;
      brokerUI.renderBrokerImportFeedTable({
        body: tbody, state: state, checkboxClass: 'nh-row-check',
        emptyMessage: '조회 버튼을 눌러 실현손익을 조회하세요.',
        adapt: row => brokerRealizedDisplayRow(row, { market: state.market, currency: state.market === 'us' ? 'USD' : 'KRW', formatNumber: nhNumber }),
        syncRowOptions: syncBrokerRowImportOptions,
        onUpdate: updateNhSelectionUI,
      });
    }

    function updateNhSelectionUI() {
      populateNhDestinationAccounts();
      brokerUI.renderBrokerImportSelectionState(state, {
        badgeId: 'nhSelectedCountBadge',
        buttonId: 'btnNhImportSelected',
        destinationSelectId: 'nhDestinationAccount',
      });
      syncBrokerRowImportOptions(state);
    }

    function renderNhPreviewModal(data) {
      const counts = data.counts || {};
      const dest = data.destination_account || {};
      previewScreenController.renderPreviewModal({
        document, brokerUI, data, prefix: 'nh', counts,
        destination: brokerUI.brokerPreviewDestinationText(dest, maskAccountDisplayLabel),
        html, statusLabel: brokerPreviewStatusLabel, formatNumber: nhNumber,
        pnlDigits: 2, defaultCurrency: '',
        updateCommitButton: updateNhCommitButton, renderDetails: renderBrokerImportPreviewDetails,
      });
    }

    function renderNhLoading(loading) {
      brokerUI.setAccountFeedButtonsDisabled('btnCheckNhStatus', 'btnFetchNhFeed', loading, state.sourceAccountKey);
    }

    return Object.freeze({
      showNhMessage, hideNhMessage, renderNhLoading, renderNhFeedTable, updateNhSelectionUI, renderNhPreviewModal,
    });
  }

  window.WealthBrokerNhScreenController = Object.freeze({ create });
})();
