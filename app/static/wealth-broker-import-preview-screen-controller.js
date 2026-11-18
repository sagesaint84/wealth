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

  function renderTableRows({ document, bodyId, items, html, statusLabel, formatNumber,
                             pnlDigits, defaultCurrency }) {
    const body = document.getElementById(bodyId);
    if (!body) return;
    body.innerHTML = items.map(item => {
      const candidate = item.candidate || {};
      return `<tr><td><span class="badge">${html(statusLabel(item.status))}</span></td><td>${html(candidate.date || '-')}</td><td>${html(candidate.name || '-')}</td><td class="num">${formatNumber(candidate.quantity)}</td><td class="num">${formatNumber(candidate.pnl, pnlDigits)} ${html(candidate.currency || defaultCurrency)}</td></tr>`;
    }).join('');
  }

  // NH, Kiwoom and KB share these preview DOM IDs and screen order.
  // Eligibility and ticket decisions stay in the supplied Controller callback.
  function renderPreviewModal({ document, brokerUI, data, prefix, counts, destination,
                                html, statusLabel, formatNumber, pnlDigits, defaultCurrency,
                                updateCommitButton, renderDetails }) {
    const overlayId = `${prefix}ImportModalOverlay`;
    brokerUI.renderPreviewSummary({
      counts, countIds: {
        new: `${prefix}ModalCountNew`, already_imported: `${prefix}ModalCountAlready`,
        possible_duplicate: `${prefix}ModalCountDup`, invalid: `${prefix}ModalCountInvalid`,
      },
      destinationId: `${prefix}ModalDestAccountDisplay`, destination,
      duplicate: { wrapId: `${prefix}DupOverrideWrap`, checkboxId: `${prefix}IncludePossibleDuplicates`,
        visible: counts.possible_duplicate, presence: 'independent' },
    });
    renderTableRows({ document, bodyId: `${prefix}ModalItemsBody`, items: data.items || [],
      html, statusLabel, formatNumber, pnlDigits, defaultCurrency });
    updateCommitButton();
    renderDetails(data, overlayId);
    brokerUI.setModalVisible(overlayId, true);
  }

  function renderDetails({ document, overlayId, prepare }) {
    const overlay = document.getElementById(overlayId);
    const modalBody = overlay?.querySelector('.toss-wts-modal-body');
    if (!modalBody) return;
    let details = modalBody.querySelector('.broker-import-preview-details');
    if (!details) {
      details = document.createElement('div');
      details.className = 'broker-import-preview-details';
      modalBody.appendChild(details);
    }

    const { onStockTypeChange, onFeeInput, onFeeChange, ...rows } = prepare();
    if (!renderRows({ document, details, ...rows })) return;
    details.querySelectorAll('.modal-broker-stock-type').forEach(select => {
      select.addEventListener('change', onStockTypeChange);
    });
    details.querySelectorAll('.modal-broker-ipo-fee').forEach(input => {
      input.addEventListener('input', onFeeInput);
      input.addEventListener('change', onFeeChange);
    });
  }

  window.WealthBrokerImportPreviewScreenController = Object.freeze({ renderRows, renderDetails, renderTableRows, renderPreviewModal });
})();
