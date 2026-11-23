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

    function clearImportPreview(state) {
      state.preview = null;
      state.previewTicket = null;
    }

    async function checkOpenApiStatus({
      state, request, setLoading, hideMessage, showMessage, renderState,
      populateSourceAccounts, updateSelectionUI, errorText, errorFallback,
      configurationWarning, noAccountsWarning,
    }) {
      if (state.loading) return;
      setLoading(true);
      hideMessage();
      renderState('checking', '상태 확인 중');
      try {
        const res = await request();
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw data;
        state.status = data;
        state.accounts = Array.isArray(data.accounts) ? data.accounts : [];
        populateSourceAccounts();
        if (!data.configured) {
          renderState('action_required', '미설정 (API 키 필요)');
          showMessage(configurationWarning, 'warning');
        } else if (!state.accounts.length) {
          renderState('action_required', '계좌 미등록');
          showMessage(noAccountsWarning, 'warning');
        } else {
          renderState(state.sourceAccountKey ? 'ready' : 'action_required', '계좌 선택 가능');
        }
      } catch (error) {
        renderState('error', '상태 확인 실패');
        showMessage(errorText(error, errorFallback), 'error');
      } finally {
        setLoading(false);
        updateSelectionUI();
      }
    }

    async function fetchOpenApiRealizedFeed({
      state, request, resolveMarket, setLoading, hideMessage, showMessage,
      renderMetadata, renderFeedTable, updateSelectionUI, emptyMessage, errorText, errorFallback,
    }) {
      setLoading(true);
      hideMessage();
      try {
        const res = await request();
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw data;
        applySuccessfulFeed(state, data.rows || [], data.selection_tokens || []);
        state.preview = null;
        state.market = resolveMarket(data);
        renderMetadata(state.market, state.rows.length);
        renderFeedTable();
        updateSelectionUI();
        if (!state.rows.length) showMessage(emptyMessage, 'info');
      } catch (error) {
        showMessage(errorText(error, errorFallback), 'error');
        renderFeedTable();
      } finally {
        setLoading(false);
      }
    }

    function mappedDestinationAccountId(state, sourceAccountKey) {
      const sourceAccount = state.accounts.find(account => account.source_account_key === sourceAccountKey);
      return sourceAccount?.auto_selected_account_id || sourceAccount?.mapped_destination_account_id || '';
    }

    async function previewOpenApiImport({
      state, request, setLoading, hideMessage, showMessage, renderPreviewModal,
      updateCommitButton, errorText, errorFallback,
    }) {
      setLoading(true);
      hideMessage();
      try {
        const res = await request();
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          state.previewTicket = null;
          updateCommitButton();
          throw data;
        }
        state.preview = data;
        state.previewTicket = data.preview_ticket;
        renderPreviewModal(data);
      } catch (error) {
        state.previewTicket = null;
        updateCommitButton();
        showMessage(errorText(error, errorFallback), 'error');
      } finally {
        setLoading(false);
      }
    }

    async function commitOpenApiImport({
      state, destinationAccountId, request, updateCommitButton, updateSelectionUI,
      closeModal, renderFeedTable, showResult, refreshResults, showMessage, errorText, errorFallback,
    }) {
      updateCommitButton();
      const accountId = destinationAccountId();
      try {
        const res = await request(accountId);
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw data;
        state.selectedIndices.forEach(index => state.importedIndices.add(index));
        state.selectedIndices.clear();
        state.previewTicket = null;
        closeModal();
        renderFeedTable();
        updateSelectionUI();
        showResult(data);
        refreshResults();
      } catch (error) {
        showMessage(errorText(error, errorFallback), 'error');
      } finally {
        state.importing = false;
        updateCommitButton();
        updateSelectionUI();
      }
    }

    return Object.freeze({
      applySuccessfulFeed, selectedImportItems, clearImportPreview, checkOpenApiStatus, fetchOpenApiRealizedFeed,
      mappedDestinationAccountId, previewOpenApiImport, commitOpenApiImport,
    });
  }

  window.WealthBrokerRealizedFeedController = Object.freeze({ create, sortRows: sortBrokerRealizedFeedRows, dateKey: brokerRealizedDateKey });
})();
