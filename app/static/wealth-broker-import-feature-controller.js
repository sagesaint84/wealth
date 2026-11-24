/* Broker import workflows and their screen bindings. Provider contracts stay in their adapters. */
(() => {
  'use strict';

  function create({
    window, document, brokerUI, html, number, money, getDashboard,
    loadDashboard, loadRealizedPnl, loadActualDividends, updateOverviewCardsAllTime,
    invalidateStartupReads, getOwner, getDividendYear, getDividendMode,
  }) {
    // ── 토스 WTS 실현손익 피드 (선택 가져오기 UX) ──────────────────────────────────
    const tossWtsState = {
      status: null,
      confirmed: false,
      loading: false,
      rows: [],
      selectionTokens: [],
      selectedIndices: new Set(),
      importedIndices: new Set(),
      importPreferences: new Map(),
      previewTicket: null,
      lastRequested: null,    // { from_date, to_date, profit_rate_basis } from response.requested
      fetchedBasis: null,     // response.requested.profit_rate_basis
      fetchedFromDate: null,  // response.requested.from_date
      fetchedToDate: null,    // response.requested.to_date
      providerEffective: null, // actual range sent to the provider CLI
      fetchedAt: null,        // response.fetched_at
    };

    const tossWtsScreenController = window.WealthBrokerRealizedScreenController.create({
      document, brokerUI, state: tossWtsState, prefix: 'tossWts', syncBrokerRowImportOptions,
      loadingButtonIds: ['btnCheckTossWtsStatus', 'btnConfirmTossWtsSession',
        'btnCheckTossWtsIncomeStatus', 'btnConfirmTossWtsIncomeSession', 'btnFetchTossWtsFeed'],
      feedTable: {
        bodyId: 'tossWtsTableBody', checkboxClass: 'wts-row-cb', toss: true,
        emptyMessage: '선택한 기간에 조회된 실현손익 내역이 없습니다.',
        adaptRow: (row, basis) => brokerRealizedDisplayRow(row, {
          market: '', currency: basis, toss: true, formatNumber: number,
        }),
        shouldSyncRowOptions: (rows, status) => rows?.length && status !== 'error',
        readIndex: target => parseInt(target.dataset.index, 10),
        onUpdate: updateWtsSelectionUI,
      },
    });

    function showTossWtsMessage(msg, type = 'info') {
      return tossWtsScreenController.showMessage(msg, type);
    }

    function hideTossWtsMessage() {
      tossWtsScreenController.hideMessage();
    }

    function clearTossWtsFetchLoadingRow(message = '조회에 실패했습니다. 조건을 확인한 뒤 다시 시도하세요.') {
      const tbody = document.getElementById('tossWtsTableBody');
      if (!tbody || !tbody.querySelector('.toss-wts-loading')) return;
      brokerUI.renderRealizedTable({ body: tbody, rows: [], emptyMessage: message });
    }

    function updateTossWtsStatusUI(text, stateClass) {
      const semantic = stateClass === 'confirmed' ? 'ready' : stateClass === 'ready' || stateClass === 'action_required' ? 'action_required' : 'error';
      brokerUI.renderBrokerState('toss', semantic, text);
    }

    function setTossWtsLoading(isLoading) {
      tossWtsState.loading = isLoading;
      tossWtsScreenController.renderLoading(isLoading);
    }

    function checkTossWtsFormStale() {
      const staleEl = document.getElementById('tossWtsStaleHint');
      if (!staleEl) return;

      if (!tossWtsState.lastRequested || !tossWtsState.rows || tossWtsState.rows.length === 0) {
        brokerUI.renderStaleHint(staleEl.id, false);
        return;
      }

      const curFrom = document.getElementById('tossWtsFromDate')?.value?.trim();
      const curTo = document.getElementById('tossWtsToDate')?.value?.trim();
      const curBasis = document.getElementById('tossWtsBasisSelect')?.value;

      const isStale = (
        curFrom !== tossWtsState.fetchedFromDate ||
        curTo !== tossWtsState.fetchedToDate ||
        curBasis !== tossWtsState.fetchedBasis
      );

      brokerUI.renderStaleHint(staleEl.id, isStale, '조회 조건이 변경되었습니다. [WTS 조회]를 눌러 다시 조회하세요.');
    }

    function updateTossWtsMetaUI() {
      const metaEl = document.getElementById('tossWtsMeta');
      if (!metaEl) return;

      if (!tossWtsState.lastRequested || !tossWtsState.rows) {
        brokerUI.renderFeedMetadata(metaEl, null);
        checkTossWtsFormStale();
        return;
      }

      const basis = tossWtsState.fetchedBasis || 'KRW';
      const fromDate = tossWtsState.fetchedFromDate || '-';
      const toDate = tossWtsState.fetchedToDate || '-';
      const effectiveToDate = tossWtsState.providerEffective?.to_date || toDate;
      const effectiveRangeNote = effectiveToDate !== toDate
        ? `<span class="toss-wts-meta-sep">·</span><span class="toss-wts-meta-item">실제 조회 종료: <strong>${html(effectiveToDate)}</strong></span>`
        : '';
      const count = tossWtsState.rows.length;
      const timeStr = tossWtsState.fetchedAt ? new Date(tossWtsState.fetchedAt).toLocaleTimeString('ko-KR') : '';

      brokerUI.renderFeedMetadata(metaEl, `
    <span class="toss-wts-meta-item">조회 기간: <strong>${html(fromDate)} ~ ${html(toDate)}</strong></span>
    <span class="toss-wts-meta-sep">·</span>
    <span class="toss-wts-meta-item">수익률 기준: <strong>${html(basis)}</strong></span>
    ${effectiveRangeNote}
    ${timeStr ? `<span class="toss-wts-meta-sep">·</span><span class="toss-wts-meta-item">조회 시각: ${html(timeStr)}</span>` : ''}
    <span class="toss-wts-meta-sep">·</span>
    <span class="toss-wts-meta-item"><strong>${count}건</strong></span>
  `);
      checkTossWtsFormStale();
    }

    async function checkTossWtsStatus() {
      if (tossWtsState.loading) return;
      setTossWtsLoading(true);
      brokerUI.renderBrokerState('toss', 'checking', '상태 확인 중');
      try {
        const res = await fetch('/api/toss-wts/status');
        if (res.status === 403) {
          updateTossWtsStatusUI('권한 없음', 'error');
          showTossWtsMessage('이 사용자에게는 토스 WTS 조회 권한이 없습니다.', 'error');
          return;
        }
        if (!res.ok) {
          updateTossWtsStatusUI('연결 상태 확인 불가', 'error');
          showTossWtsMessage('토스 WTS 연결 상태를 확인할 수 없습니다.', 'error');
          return;
        }
        const data = await res.json();
        tossWtsState.status = data;
        if (data.adapter_ready) {
          updateTossWtsStatusUI('준비 완료', 'ready');
          showTossWtsMessage('토스 WTS 어댑터가 준비되었습니다. 조회를 위해 [WTS 런타임 확인]을 진행하세요.', 'info');
        } else {
          const errMap = {
            NOT_CONFIGURED: 'WTS 비활성',
            SESSION_MISSING: '세션 확인 필요',
          };
          const desc = errMap[data.error_code] || '연결 상태 확인 불가';
          updateTossWtsStatusUI(desc, 'action_required');
          showTossWtsMessage(`토스 WTS 상태: ${desc}`, 'error');
        }
      } catch (err) {
        updateTossWtsStatusUI('연결 상태 확인 불가', 'error');
        showTossWtsMessage('토스 WTS 상태 확인 중 네트워크 오류가 발생했습니다.', 'error');
      } finally {
        setTossWtsLoading(false);
      }
    }

    async function confirmTossWtsSession() {
      if (tossWtsState.loading) return;
      setTossWtsLoading(true);
      brokerUI.renderBrokerState('toss', 'checking', '상태 확인 중');
      try {
        const res = await fetch('/api/toss-wts/feed/confirm', { method: 'POST' });
        if (res.status === 403) {
          tossWtsState.confirmed = false;
          updateTossWtsStatusUI('권한 없음', 'error');
          showTossWtsMessage('이 사용자에게는 토스 WTS 조회 권한이 없습니다.', 'error');
          return;
        }
        if (res.status === 503) {
          tossWtsState.confirmed = false;
          updateTossWtsStatusUI('연결 상태 확인 불가', 'error');
          showTossWtsMessage('토스 WTS 연동 런타임을 사용할 수 없습니다.', 'error');
          return;
        }
        if (!res.ok) {
          tossWtsState.confirmed = false;
          updateTossWtsStatusUI('런타임 확인 필요', 'action_required');
          showTossWtsMessage('WTS 런타임 확인에 실패했습니다.', 'error');
          return;
        }
        const data = await res.json();
        if (data.confirmed) {
          tossWtsState.confirmed = true;
          updateTossWtsStatusUI('런타임 확인 완료', 'confirmed');
          showTossWtsMessage('WTS 로컬 런타임이 확인되었습니다. 실현손익 및 배당·이자 조회가 가능합니다.', 'success');
        } else {
          tossWtsState.confirmed = false;
          updateTossWtsStatusUI('런타임 확인 필요', 'action_required');
          showTossWtsMessage('WTS 런타임 확인에 실패했습니다.', 'error');
        }
      } catch (err) {
        tossWtsState.confirmed = false;
        updateTossWtsStatusUI('연결 상태 확인 불가', 'error');
        showTossWtsMessage('WTS 런타임 확인 중 네트워크 오류가 발생했습니다.', 'error');
      } finally {
        setTossWtsLoading(false);
      }
    }

    async function fetchTossWtsRealizedFeed() {
      if (tossWtsState.loading) return;
      const fromInput = document.getElementById('tossWtsFromDate');
      const toInput = document.getElementById('tossWtsToDate');
      const basisSelect = document.getElementById('tossWtsBasisSelect');
      const reqFromDate = fromInput?.value?.trim();
      const reqToDate = toInput?.value?.trim();
      const reqBasis = basisSelect?.value || 'KRW';

      if (!reqFromDate || !reqToDate) {
        showTossWtsMessage('시작일과 종료일을 입력해주세요.', 'error');
        return;
      }
      if (reqFromDate > reqToDate) {
        showTossWtsMessage('시작일은 종료일보다 이전이어야 합니다.', 'error');
        return;
      }

      setTossWtsLoading(true);
      const tbody = document.getElementById('tossWtsTableBody');
      if (tbody && (!tossWtsState.rows || tossWtsState.rows.length === 0)) {
        brokerUI.renderRealizedTable({ body: tbody, rows: [], status: 'loading' });
      }
      showTossWtsMessage('토스 WTS 실현손익을 조회하는 중입니다...', 'info');

      try {
        const res = await fetch('/api/toss-wts/realized-feed/fetch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            from_date: reqFromDate,
            to_date: reqToDate,
            profit_rate_basis: reqBasis,
          }),
        });

        let errorCode = null;
        if (!res.ok) {
          try {
            const errorPayload = await res.json();
            errorCode = errorPayload?.detail?.code || errorPayload?.code || null;
          } catch (err) {
            errorCode = null;
          }
        }

        if (res.status === 403) {
          clearTossWtsFetchLoadingRow('조회 권한이 없습니다.');
          showTossWtsMessage('이 사용자에게는 토스 WTS 조회 권한이 없습니다.', 'error');
          updateTossWtsMetaUI();
          return;
        }
        if (res.status === 409) {
          clearTossWtsFetchLoadingRow('WTS 런타임 확인이 필요합니다.');
          showTossWtsMessage("WTS 런타임 확인이 필요합니다. 먼저 [WTS 런타임 확인] 버튼을 눌러주세요.", 'error');
          updateTossWtsMetaUI();
          return;
        }
        if (res.status === 502 || res.status === 503) {
          const timezoneConflict = errorCode === 'TOSSCTL_DATE_TIMEZONE_CONFLICT';
          clearTossWtsFetchLoadingRow(timezoneConflict ? '오늘 데이터는 오전 9시 이후 조회할 수 있습니다.' : undefined);
          showTossWtsMessage(
            timezoneConflict
              ? 'WTS CLI 날짜 제한으로 오늘 데이터는 오전 9시 이후 조회할 수 있습니다.'
              : '토스 WTS 연동 런타임을 사용할 수 없습니다.',
            'error',
          );
          updateTossWtsMetaUI();
          return;
        }
        if (res.status === 400) {
          clearTossWtsFetchLoadingRow('조회 요청 조건이 유효하지 않습니다.');
          showTossWtsMessage('조회 요청 파라미터가 유효하지 않습니다.', 'error');
          updateTossWtsMetaUI();
          return;
        }
        if (!res.ok) {
          clearTossWtsFetchLoadingRow();
          showTossWtsMessage(`토스 WTS 조회 중 오류가 발생했습니다. (${res.status})`, 'error');
          updateTossWtsMetaUI();
          return;
        }

        const data = await res.json();
        tossWtsState.lastRequested = data.requested || {
          from_date: reqFromDate,
          to_date: reqToDate,
          profit_rate_basis: reqBasis,
        };
        tossWtsState.fetchedBasis = tossWtsState.lastRequested.profit_rate_basis;
        tossWtsState.fetchedFromDate = tossWtsState.lastRequested.from_date;
        tossWtsState.fetchedToDate = tossWtsState.lastRequested.to_date;
        tossWtsState.providerEffective = data.provider_effective || {
          from_date: tossWtsState.fetchedFromDate,
          to_date: tossWtsState.fetchedToDate,
        };
        tossWtsState.fetchedAt = data.fetched_at;
        brokerRealizedFeedController.applySuccessfulFeed(tossWtsState, data.rows || [], data.selection_tokens || []);

        if (data.date_compatibility?.adjusted) {
          showTossWtsMessage(
            `WTS CLI 날짜 제한으로 현재 ${tossWtsState.providerEffective.to_date}까지 조회했습니다. 오늘 데이터는 오전 9시 이후 조회할 수 있습니다.`,
            'info',
          );
        } else {
          hideTossWtsMessage();
        }
        populateWtsAccounts();
        renderTossWtsFeedTable(tossWtsState.rows, tossWtsState.fetchedBasis, 'ok');
        updateTossWtsMetaUI();
        updateWtsSelectionUI();
      } catch (err) {
        clearTossWtsFetchLoadingRow();
        showTossWtsMessage('토스 WTS 조회 중 네트워크 오류가 발생했습니다.', 'error');
        updateTossWtsMetaUI();
      } finally {
        setTossWtsLoading(false);
      }
    }

    function updateWtsSelectionUI() {
      const destSelect = document.getElementById('wtsDestinationAccount');
      const count = tossWtsState.selectedIndices ? tossWtsState.selectedIndices.size : 0;
      brokerUI.renderSelectionState({ badgeId: 'wtsSelectedCountBadge', count,
        buttonId: 'btnWtsImportSelected', disabled: count === 0 || !destSelect?.value });
      const selectAll = document.getElementById('wtsSelectAll');
      if (selectAll && tossWtsState.rows) {
        const importableCount = tossWtsState.rows.filter((_, idx) => !tossWtsState.importedIndices.has(idx)).length;
        brokerUI.renderSelectAllState('wtsSelectAll', importableCount > 0 && count === importableCount, importableCount === 0);
      }
      syncBrokerRowImportOptions(tossWtsState);
    }

    function populateWtsAccounts() {
      const dashboard = getDashboard();
      const select = document.getElementById('wtsDestinationAccount');
      if (!select) return;

      const accounts = ((dashboard && dashboard.accounts) || []).filter(account => {
        const broker = String(account.broker || '').trim().toLowerCase();
        return broker.includes('토스') || broker.includes('toss');
      });

      const currentVal = select.value;

      select.innerHTML = '<option value="">토스증권 계좌를 선택하세요</option>' +
        accounts.map(acc => {
          const broker = acc.broker || '토스증권';
          const name = maskAccountDisplayLabel(acc.account_name || acc.name || '계좌');
          const owner = acc.owner ? ` (${acc.owner})` : '';
          return `<option value="${html(acc.id)}">${html(broker)} - ${html(name)}${html(owner)}</option>`;
        }).join('');

      if (currentVal && accounts.some(a => String(a.id) === currentVal)) {
        select.value = currentVal;
      } else {
        select.value = '';
      }
      window.WealthTransactionDefaults?.restoreImportSelection(select, 'toss_wts_realized', accounts);
    }

    let currentPreviewData = null;

    async function openWtsImportPreview() {
      const destSelect = document.getElementById('wtsDestinationAccount');
      const destAccountId = destSelect?.value;
      if (!destAccountId) {
        showTossWtsMessage('귀속할 Wealth 계좌를 선택해주세요.', 'error');
        return;
      }
      if (!tossWtsState.selectedIndices || tossWtsState.selectedIndices.size === 0) {
        showTossWtsMessage('추가할 실현손익 항목을 선택해주세요.', 'error');
        return;
      }

      const selectedItems = Array.from(tossWtsState.selectedIndices).sort((a, b) => a - b).map(idx => {
        return brokerImportSelectedItem(tossWtsState, idx);
      }).filter(Boolean);

      setTossWtsLoading(true);
      try {
        const res = await fetch('/api/toss-wts/realized-feed/import-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            selected_items: selectedItems,
            account_id: destAccountId,
            profit_rate_basis: tossWtsState.fetchedBasis || 'KRW',
          }),
        });

        if (!res.ok) {
          tossWtsState.previewTicket = null;
          if (currentPreviewData) currentPreviewData.preview_ticket = null;
          updateWtsCommitButton();
          const err = await res.json().catch(() => ({}));
          showTossWtsMessage(`가져오기 미리보기 실패: ${err.detail?.message || err.detail?.code || res.status}`, 'error');
          return;
        }

        const data = await res.json();
        currentPreviewData = data;
        tossWtsState.previewTicket = data.preview_ticket;
        renderWtsImportModal(data);
      } catch (err) {
        tossWtsState.previewTicket = null;
        if (currentPreviewData) currentPreviewData.preview_ticket = null;
        updateWtsCommitButton();
        showTossWtsMessage('가져오기 미리보기 중 네트워크 오류가 발생했습니다.', 'error');
      } finally {
        setTossWtsLoading(false);
      }
    }

    function renderWtsImportModal(data) {
      const overlay = document.getElementById('wtsImportModalOverlay');
      if (!overlay) return;

      const counts = data.counts || { new: 0, already_imported: 0, possible_duplicate: 0, invalid: 0 };
      const destAcc = data.destination_account || {};
      const destText = `${destAcc.broker || ''} - ${maskAccountDisplayLabel(destAcc.account_name || '')} (${destAcc.owner || '모두'})`;

      brokerUI.renderPreviewSummary({
        counts, countIds: {
        new: 'wtsCountNew', already_imported: 'wtsCountAlready',
        possible_duplicate: 'wtsCountDup', invalid: 'wtsCountInvalid',
      },
        formatCount: value => `${value}건`,
        destinationId: 'wtsModalDestAccountName', destination: { text: destText },
        accountFirst: true,
        duplicate: { wrapId: 'wtsDupOverrideWrap', checkboxId: 'wtsIncludePossibleDuplicates',
          visible: counts.possible_duplicate > 0, presence: 'both', resetFirst: true },
      });
      updateWtsCommitButton();
      renderBrokerImportPreviewDetails(data, 'wtsImportModalOverlay');
      brokerUI.setModalVisible('wtsImportModalOverlay', true);
    }

    function updateWtsCommitButton() {
      const commitBtn = document.getElementById('btnWtsConfirmCommit');
      const dupCheckbox = document.getElementById('wtsIncludePossibleDuplicates');
      if (!commitBtn) return;
      const newCount = (currentPreviewData?.counts?.new) || 0;
      const dupCount = (currentPreviewData?.counts?.possible_duplicate) || 0;
      const includeDup = Boolean(dupCheckbox?.checked);
      const totalEligible = newCount + (includeDup ? dupCount : 0);

      if (totalEligible > 0 && currentPreviewData?.preview_ticket && tossWtsState.previewTicket && !tossWtsState.importing) {
        brokerUI.setButtonDisabled('btnWtsConfirmCommit', false);
        commitBtn.textContent = `신규 ${totalEligible}건 Wealth에 추가`;
      } else {
        brokerUI.setButtonDisabled('btnWtsConfirmCommit', true);
        commitBtn.textContent = totalEligible > 0 ? `신규 ${totalEligible}건 Wealth에 추가` : '신규 0건 Wealth에 추가';
      }
    }

    function closeWtsImportModal() {
      brokerUI.setModalVisible('wtsImportModalOverlay', false);
      currentPreviewData = null;
      tossWtsState.previewTicket = null;
    }

    async function commitWtsImport() {
      if (!currentPreviewData || !tossWtsState.previewTicket) return;
      const destSelect = document.getElementById('wtsDestinationAccount');
      const destAccountId = destSelect?.value;
      const dupCheckbox = document.getElementById('wtsIncludePossibleDuplicates');
      const includeDup = Boolean(dupCheckbox?.checked);

      const selectedItems = Array.from(tossWtsState.selectedIndices).sort((a, b) => a - b).map(idx => {
        return brokerImportSelectedItem(tossWtsState, idx);
      }).filter(Boolean);

      const commitBtn = document.getElementById('btnWtsConfirmCommit');
      if (commitBtn) commitBtn.disabled = true;

      try {
        const res = await fetch('/api/toss-wts/realized-feed/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            selected_items: selectedItems,
            account_id: destAccountId,
            preview_ticket: currentPreviewData.preview_ticket,
            include_possible_duplicates: includeDup,
            profit_rate_basis: tossWtsState.fetchedBasis || 'KRW',
          }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          showTossWtsMessage(`실현손익 추가 실패: ${err.detail?.message || err.detail?.code || res.status}`, 'error');
          if (commitBtn) commitBtn.disabled = false;
          return;
        }

        const result = await res.json();
        closeWtsImportModal();

        for (const idx of tossWtsState.selectedIndices) {
          tossWtsState.importedIndices.add(idx);
        }
        tossWtsState.selectedIndices.clear();

        showTossWtsMessage(`${result.imported}건을 Wealth 실현손익에 추가했습니다. (중복 제외: ${result.already_imported}건)`, 'success');
        renderTossWtsFeedTable(tossWtsState.rows, tossWtsState.fetchedBasis, 'ok');
        updateWtsSelectionUI();

        if (typeof loadRealizedPnl === 'function') {
          loadRealizedPnl();
        } else if (typeof loadDashboard === 'function') {
          loadDashboard();
        }
      } catch (err) {
        showTossWtsMessage('실현손익 추가 중 네트워크 오류가 발생했습니다.', 'error');
        if (commitBtn) commitBtn.disabled = false;
      }
    }

    // Display-only adapters: never mutate rows or calculate financial results.
    function brokerRealizedDisplayRow(row, { market, currency, formatNumber, toss = false, kis = false }) {
      const present = value => value !== null && value !== undefined && value !== '';
      const amount = value => present(value) ? (toss ? (currency === 'USD' ? number(value, 2) : money(value)) : kis
        ? (market === 'us' ? Number(value).toLocaleString('en-US', { minimumFractionDigits: 2 }) : window.WealthFormat.roundGroupedKoKr(value))
        : formatNumber(value, currency === 'USD' ? 2 : 0)) : '';
      const rawAmount = field => toss ? row[field]?.[currency === 'USD' ? 'usd' : 'krw']
        : (kis && market === 'us' ? (row['foreign_' + field] ?? row[field]) : row[field]);
      const pnl = toss ? row.profit_loss?.[currency === 'USD' ? 'usd' : 'krw'] : kis ? row.profit_loss : row.pnl;
      const actualCurrency = toss ? currency : (row.currency || currency);
      const fees = [];
      if (present(row.fee)) fees.push('수수료 ' + amount(row.fee));
      if (present(row.tax)) fees.push('제세금 ' + amount(row.tax));
      if (market === 'us' && present(row.expenses_total)) fees.push('해외 제비용 합계 ' + amount(row.expenses_total));
      if (kis && market === 'us') {
        if (present(row.profit_loss_krw)) fees.push('원화손익 ' + window.WealthFormat.roundGroupedKoKr(row.profit_loss_krw) + '원');
        if (present(row.fx_rate)) fees.push('환율 @' + Number(row.fx_rate).toFixed(1));
      }
      const marketValue = toss ? row.market_type : market;
      return {
        date: row.date || '', name: row.name || '', code: row.code || row.symbol || row.product_code || '',
        context: [marketValue, actualCurrency].filter(Boolean).join(' / '),
        type: row.trade_type || row.transaction_type || '',
        quantity: present(row.quantity) ? (kis ? Number(row.quantity).toLocaleString() : formatNumber(row.quantity, toss && !Number.isInteger(Number(row.quantity)) ? 2 : 0)) : '',
        buy: amount(rawAmount('buy_amount')), sell: amount(rawAmount('sell_amount')),
        pnl: present(pnl) ? (Number(pnl) > 0 ? '+' : '') + (kis && market === 'us'
          ? Number(pnl).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : amount(pnl)) : '',
        tone: present(pnl) ? (Number(pnl) > 0 ? 'pos' : Number(pnl) < 0 ? 'neg' : '') : '',
        rate: present(row.profit_rate) ? (Number(row.profit_rate) > 0 ? '+' : '') + Number(row.profit_rate).toFixed(2) + '%' : '',
        expenses: fees.join(' · '),
      };
    }

    function renderTossWtsFeedTable(rows, basis = 'KRW', status = 'ok') {
      tossWtsScreenController.renderFeedTable(rows, basis, status);
    }

    // ── 토스 WTS 배당·이자 피드 (선택 가져오기) ───────────────────────────────────
    const tossWtsIncomeState = {
      loading: false,
      importing: false,
      rows: [],
      selectionTokens: [],
      selectedIndices: new Set(),
      importedIndices: new Set(),
      previewTicket: null,
      previewData: null,
      fetchedFromDate: null,
      fetchedToDate: null,
    };

    function showTossWtsIncomeMessage(message, type = 'info') { return brokerUI.showBrokerMessage('tossWtsIncomeMessage', message, type); }

    function setTossWtsIncomeLoading(loading) {
      tossWtsIncomeState.loading = loading;
      brokerUI.setButtonDisabled('btnFetchTossWtsIncome', loading);
      if (loading) brokerUI.setButtonDisabled('btnWtsIncomeImportSelected', true);
      if (!loading) updateTossWtsIncomeSelectionUI();
    }

    function tossWtsIncomeTypeLabel(type) {
      const labels = {
        dividend: '배당',
        distribution: '분배금',
        account_interest: '예탁금 이자',
      };
      return labels[type] || '기타';
    }

    function tossWtsIncomeAmount(value, currency) {
      if (value == null || value === '') return '—';
      const numberValue = Number(value);
      if (!Number.isFinite(numberValue)) return '—';
      return String(currency || '').toUpperCase() === 'USD'
        ? `$${number(numberValue, 2)}`
        : `₩${money(numberValue)}`;
    }

    function populateTossWtsIncomeAccounts() {
      const dashboard = getDashboard();
      const select = document.getElementById('wtsIncomeDestinationAccount');
      if (!select) return;
      const current = select.value;
      const accounts = ((dashboard && dashboard.accounts) || []).filter(account => {
        const broker = String(account.broker || '').trim().toLowerCase();
        return broker.includes('토스') || broker.includes('toss');
      });
      select.innerHTML = '<option value="">토스증권 계좌를 선택하세요</option>' + accounts.map(account => {
        const label = maskAccountDisplayLabel(account.account_name || account.name || '계좌');
        const owner = account.owner ? ` (${account.owner})` : '';
        return `<option value="${html(String(account.id || ''))}">${html(account.broker || '토스증권')} - ${html(label)}${html(owner)}</option>`;
      }).join('');
      if (current && accounts.some(account => String(account.id) === current)) {
        select.value = current;
      } else {
        select.value = '';
      }
      window.WealthTransactionDefaults?.restoreImportSelection(select, 'toss_wts_income', accounts);
    }

    function updateTossWtsIncomeMeta(data = null) {
      const el = document.getElementById('tossWtsIncomeMeta');
      if (!el) return;
      if (!data) {
        brokerUI.renderFeedMetadata(el, null);
        return;
      }
      const requested = data.requested || {};
      brokerUI.renderFeedMetadata(el, `
    <span class="toss-wts-meta-item">조회 기간: <strong>${html(requested.from_date || '-')} ~ ${html(requested.to_date || '-')}</strong></span>
    <span class="toss-wts-meta-sep">·</span>
    <span class="toss-wts-meta-item">거래원장 <strong>${Number(data.fetched || 0)}건</strong></span>
    <span class="toss-wts-meta-sep">·</span>
    <span class="toss-wts-meta-item">가져오기 대상 <strong>${Number(data.eligible || 0)}건</strong></span>
    <span class="toss-wts-meta-sep">·</span>
    <span class="toss-wts-meta-item">제외 ${Number(data.ignored || 0)}건 · 무효 ${Number(data.invalid || 0)}건</span>
  `);
    }

    function renderTossWtsIncomeTable() {
      const tbody = document.getElementById('tossWtsIncomeTableBody');
      if (!tbody) return;
      const rows = tossWtsIncomeState.rows || [];
      if (!rows.length) {
        tbody.innerHTML = brokerUI.brokerTableEmptyRow(8, '선택한 기간에 가져올 배당·이자 내역이 없습니다.');
        return;
      }
      tbody.innerHTML = rows.map((row, index) => {
        const imported = tossWtsIncomeState.importedIndices.has(index);
        const selected = tossWtsIncomeState.selectedIndices.has(index);
        const check = brokerUI.feedSelectionCell({
          index, selected, imported, checkboxClass: 'wts-income-row-cb',
          badgeClass: 'toss-wts-badge-imported', importedText: '처리됨',
        });
        const market = String(row.market || '').toUpperCase();
        const marketBadge = market === 'KR'
          ? '<span class="toss-wts-market-badge kr">국내</span>'
          : '<span class="toss-wts-market-badge us">해외</span>';
        const typeLabel = tossWtsIncomeTypeLabel(row.income_type);
        const typeClass = `income-${String(row.income_type || 'other').replace(/[^a-z_]/g, '')}`;
        const dateText = String(row.datetime || '').slice(0, 10);
        const currency = String(row.currency || '').toUpperCase();
        return `<tr>
      <td class="center">${check}</td>
      <td class="center">${html(dateText)}</td>
      <td class="center"><span class="toss-wts-income-type ${typeClass}">${html(typeLabel)}</span></td>
      <td class="center">${marketBadge}</td>
      <td><strong>${html(row.display_name || row.stock_name || '-')}</strong>${row.display_code ? ` <small class="muted">(${html(row.display_code)})</small>` : ''}</td>
      <td class="right">${tossWtsIncomeAmount(row.gross_amount, currency)}</td>
      <td class="right">${tossWtsIncomeAmount(row.tax, currency)}</td>
      <td class="right" style="font-weight:700;">${tossWtsIncomeAmount(row.net_amount, currency)}</td>
    </tr>`;
      }).join('');
      tbody.querySelectorAll('.wts-income-row-cb').forEach(cb => {
        cb.addEventListener('change', event => {
          const index = Number(event.target.dataset.index);
          if (event.target.checked) tossWtsIncomeState.selectedIndices.add(index);
          else tossWtsIncomeState.selectedIndices.delete(index);
          updateTossWtsIncomeSelectionUI();
        });
      });
    }

    function updateTossWtsIncomeSelectionUI() {
      const count = tossWtsIncomeState.selectedIndices.size;
      const account = document.getElementById('wtsIncomeDestinationAccount');
      brokerUI.renderSelectionState({ badgeId: 'wtsIncomeSelectedCountBadge', count,
        buttonId: 'btnWtsIncomeImportSelected',
        disabled: tossWtsIncomeState.loading || tossWtsIncomeState.importing || count === 0 || !account?.value });
      const selectAll = document.getElementById('wtsIncomeSelectAll');
      if (selectAll) {
        const available = tossWtsIncomeState.rows.filter((_, index) => !tossWtsIncomeState.importedIndices.has(index)).length;
        brokerUI.renderSelectAllState('wtsIncomeSelectAll', available > 0 && count === available, available === 0);
      }
    }

    function selectedTossWtsIncomeItems() {
      return Array.from(tossWtsIncomeState.selectedIndices).sort((a, b) => a - b).map(index => {
        const row = tossWtsIncomeState.rows[index];
        const selectionToken = tossWtsIncomeState.selectionTokens[index];
        return row && selectionToken ? { row, selection_token: selectionToken } : null;
      }).filter(Boolean);
    }

    async function fetchTossWtsIncomeFeed() {
      if (tossWtsIncomeState.loading) return;
      const fromDate = document.getElementById('tossWtsIncomeFromDate')?.value?.trim();
      const toDate = document.getElementById('tossWtsIncomeToDate')?.value?.trim();
      if (!fromDate || !toDate || fromDate > toDate) {
        showTossWtsIncomeMessage('올바른 시작일과 종료일을 입력해주세요.', 'error');
        return;
      }
      setTossWtsIncomeLoading(true);
      const tbody = document.getElementById('tossWtsIncomeTableBody');
      if (tbody) tbody.innerHTML = brokerUI.brokerTableLoadingRow(8, '배당·이자 거래원장을 조회하는 중입니다...');
      showTossWtsIncomeMessage('토스 WTS 배당·이자를 조회하는 중입니다...', 'info');
      try {
        const response = await fetch('/api/toss-wts/income-feed/fetch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ from_date: fromDate, to_date: toDate }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          const code = payload?.detail?.code || payload?.code || response.status;
          if (response.status === 409) {
            showTossWtsIncomeMessage('WTS 런타임 확인이 필요합니다. 위의 [WTS 런타임 확인] 버튼을 먼저 눌러주세요.', 'error');
          } else if (response.status === 403) {
            showTossWtsIncomeMessage('이 사용자에게는 토스 WTS 조회 권한이 없습니다.', 'error');
          } else {
            showTossWtsIncomeMessage(`배당·이자 조회에 실패했습니다. (${code})`, 'error');
          }
          if (tbody) tbody.innerHTML = brokerUI.brokerTableEmptyRow(8, '조회에 실패했습니다.');
          return;
        }
        const pairs = (payload.rows || []).map((row, index) => ({ row, token: (payload.selection_tokens || [])[index] || '' }));
        pairs.sort((a, b) => String(b.row?.datetime || '').localeCompare(String(a.row?.datetime || '')));
        tossWtsIncomeState.rows = pairs.map(item => item.row);
        tossWtsIncomeState.selectionTokens = pairs.map(item => item.token);
        tossWtsIncomeState.selectedIndices.clear();
        tossWtsIncomeState.importedIndices.clear();
        tossWtsIncomeState.previewTicket = null;
        tossWtsIncomeState.previewData = null;
        tossWtsIncomeState.fetchedFromDate = payload.requested?.from_date || fromDate;
        tossWtsIncomeState.fetchedToDate = payload.requested?.to_date || toDate;
        populateTossWtsIncomeAccounts();
        renderTossWtsIncomeTable();
        updateTossWtsIncomeSelectionUI();
        updateTossWtsIncomeMeta(payload);
        if (tossWtsIncomeState.rows.length) {
          showTossWtsIncomeMessage(`${tossWtsIncomeState.rows.length}건의 검증된 배당·이자 내역을 찾았습니다.`, 'success');
        } else {
          showTossWtsIncomeMessage('선택한 기간에 가져올 배당·이자 내역이 없습니다.', 'info');
        }
      } catch (error) {
        if (tbody) tbody.innerHTML = brokerUI.brokerTableEmptyRow(8, '조회 중 네트워크 오류가 발생했습니다.');
        showTossWtsIncomeMessage('배당·이자 조회 중 네트워크 오류가 발생했습니다.', 'error');
      } finally {
        setTossWtsIncomeLoading(false);
      }
    }

    function renderTossWtsIncomePreviewModal(data) {
      const overlay = document.getElementById('wtsIncomeImportModalOverlay');
      if (!overlay) return;
      const counts = data.counts || {};
      const destination = data.destination_account || {};
      brokerUI.renderPreviewSummary({
        counts, countIds: {
        new: 'wtsIncomeCountNew', already_imported: 'wtsIncomeCountAlready',
        possible_duplicate: 'wtsIncomeCountDup', invalid: 'wtsIncomeCountInvalid',
      },
        formatCount: value => `${Number(value || 0)}건`,
        destinationId: 'wtsIncomeModalDestAccount', destination: {
        text: `${destination.broker || '토스증권'} - ${maskAccountDisplayLabel(destination.account_name || '')} (${destination.owner || '모두'})`,
      },
        accountFirst: true,
        duplicate: { wrapId: 'wtsIncomeDupOverrideWrap', checkboxId: 'wtsIncomeIncludePossibleDuplicates',
          visible: Number(counts.possible_duplicate || 0) > 0, presence: 'independent', resetFirst: true },
      });
      updateTossWtsIncomeCommitButton();
      brokerUI.setModalVisible('wtsIncomeImportModalOverlay', true);
    }

    async function openTossWtsIncomeImportPreview() {
      const accountId = document.getElementById('wtsIncomeDestinationAccount')?.value;
      const selectedItems = selectedTossWtsIncomeItems();
      if (!accountId) {
        showTossWtsIncomeMessage('귀속할 토스증권 Wealth 계좌를 선택해주세요.', 'error');
        return;
      }
      if (!selectedItems.length) {
        showTossWtsIncomeMessage('가져올 배당·이자 항목을 선택해주세요.', 'error');
        return;
      }
      setTossWtsIncomeLoading(true);
      try {
        const response = await fetch('/api/toss-wts/income-feed/import-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ selected_items: selectedItems, account_id: accountId }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          tossWtsIncomeState.previewTicket = null;
          tossWtsIncomeState.previewData = null;
          showTossWtsIncomeMessage(`가져오기 미리보기에 실패했습니다. (${payload?.detail?.code || response.status})`, 'error');
          return;
        }
        tossWtsIncomeState.previewTicket = payload.preview_ticket;
        tossWtsIncomeState.previewData = payload;
        renderTossWtsIncomePreviewModal(payload);
      } catch (error) {
        tossWtsIncomeState.previewTicket = null;
        tossWtsIncomeState.previewData = null;
        showTossWtsIncomeMessage('가져오기 미리보기 중 네트워크 오류가 발생했습니다.', 'error');
      } finally {
        setTossWtsIncomeLoading(false);
      }
    }

    function updateTossWtsIncomeCommitButton() {
      const button = document.getElementById('btnWtsIncomeConfirmCommit');
      if (!button) return;
      const counts = tossWtsIncomeState.previewData?.counts || {};
      const includeDup = Boolean(document.getElementById('wtsIncomeIncludePossibleDuplicates')?.checked);
      const total = Number(counts.new || 0) + (includeDup ? Number(counts.possible_duplicate || 0) : 0);
      brokerUI.setButtonDisabled('btnWtsIncomeConfirmCommit', tossWtsIncomeState.importing || !tossWtsIncomeState.previewTicket || total <= 0);
      button.textContent = `${total}건 가져오기`;
    }

    function closeTossWtsIncomeImportModal() {
      brokerUI.setModalVisible('wtsIncomeImportModalOverlay', false);
      tossWtsIncomeState.previewTicket = null;
      tossWtsIncomeState.previewData = null;
    }

    async function commitTossWtsIncomeImport() {
      if (!tossWtsIncomeState.previewTicket || !tossWtsIncomeState.previewData) return;
      const accountId = document.getElementById('wtsIncomeDestinationAccount')?.value;
      const selectedItems = selectedTossWtsIncomeItems();
      const includeDup = Boolean(document.getElementById('wtsIncomeIncludePossibleDuplicates')?.checked);
      tossWtsIncomeState.importing = true;
      updateTossWtsIncomeCommitButton();
      try {
        const response = await fetch('/api/toss-wts/income-feed/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            selected_items: selectedItems,
            account_id: accountId,
            preview_ticket: tossWtsIncomeState.previewTicket,
            include_possible_duplicates: includeDup,
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          showTossWtsIncomeMessage(`배당·이자 가져오기에 실패했습니다. (${payload?.detail?.code || response.status})`, 'error');
          return;
        }
        // This import uses fetch directly, so it must also invalidate navigation
        // response handoffs before the normal post-import reload.
        invalidateStartupReads();
        for (const index of tossWtsIncomeState.selectedIndices) tossWtsIncomeState.importedIndices.add(index);
        tossWtsIncomeState.selectedIndices.clear();
        closeTossWtsIncomeImportModal();
        renderTossWtsIncomeTable();
        updateTossWtsIncomeSelectionUI();
        showTossWtsIncomeMessage(
          `${Number(payload.imported || 0)}건을 가져왔습니다. 이미 가져옴 ${Number(payload.already_imported || 0)}건, 중복 제외 ${Number(payload.possible_duplicate_skipped || 0)}건.`,
          'success',
        );
        if (typeof loadActualDividends === 'function') await loadActualDividends(getOwner(), getDividendYear());
        if (typeof updateOverviewCardsAllTime === 'function') await updateOverviewCardsAllTime(getOwner());
      } catch (error) {
        showTossWtsIncomeMessage('배당·이자 가져오기 중 네트워크 오류가 발생했습니다.', 'error');
      } finally {
        tossWtsIncomeState.importing = false;
        updateTossWtsIncomeCommitButton();
      }
    }

    function initTossWtsIncomeUI() {
      document.getElementById('btnCheckTossWtsIncomeStatus')?.addEventListener('click', checkTossWtsStatus);
      document.getElementById('btnConfirmTossWtsIncomeSession')?.addEventListener('click', confirmTossWtsSession);
      document.getElementById('btnFetchTossWtsIncome')?.addEventListener('click', fetchTossWtsIncomeFeed);
      const incomeSection = document.getElementById('tossWtsIncomeSection');
      if (incomeSection) {
        incomeSection.style.display = getDividendMode() === 'actual' ? 'flex' : 'none';
      }
      document.getElementById('wtsIncomeDestinationAccount')?.addEventListener('change', updateTossWtsIncomeSelectionUI);
      document.getElementById('wtsIncomeSelectAll')?.addEventListener('change', event => {
        tossWtsIncomeState.rows.forEach((_, index) => {
          if (!tossWtsIncomeState.importedIndices.has(index)) {
            if (event.target.checked) tossWtsIncomeState.selectedIndices.add(index);
            else tossWtsIncomeState.selectedIndices.delete(index);
          }
        });
        renderTossWtsIncomeTable();
        updateTossWtsIncomeSelectionUI();
      });
      document.getElementById('btnWtsIncomeImportSelected')?.addEventListener('click', openTossWtsIncomeImportPreview);
      document.getElementById('btnWtsIncomeModalClose')?.addEventListener('click', closeTossWtsIncomeImportModal);
      document.getElementById('btnWtsIncomeModalCancel')?.addEventListener('click', closeTossWtsIncomeImportModal);
      document.getElementById('wtsIncomeIncludePossibleDuplicates')?.addEventListener('change', updateTossWtsIncomeCommitButton);
      document.getElementById('btnWtsIncomeConfirmCommit')?.addEventListener('click', commitTossWtsIncomeImport);
      populateTossWtsIncomeAccounts();
    }

    function initTossWtsUI() {
      const fromInput = document.getElementById('tossWtsFromDate');
      const toInput = document.getElementById('tossWtsToDate');
      const basisSelect = document.getElementById('tossWtsBasisSelect');

      document.getElementById('btnConfirmTossWtsSession')?.addEventListener('click', confirmTossWtsSession);

      // Import bar listeners
      document.getElementById('wtsSelectAll')?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        if (tossWtsState.rows) {
          tossWtsState.rows.forEach((_, idx) => {
            if (!tossWtsState.importedIndices.has(idx)) {
              if (checked) {
                tossWtsState.selectedIndices.add(idx);
              } else {
                tossWtsState.selectedIndices.delete(idx);
              }
            }
          });
          renderTossWtsFeedTable(tossWtsState.rows, tossWtsState.fetchedBasis, 'ok');
          updateWtsSelectionUI();
        }
      });

      document.getElementById('wtsDestinationAccount')?.addEventListener('change', updateWtsSelectionUI);
      document.getElementById('btnWtsImportSelected')?.addEventListener('click', openWtsImportPreview);

      // Modal listeners
      document.getElementById('btnWtsModalClose')?.addEventListener('click', closeWtsImportModal);
      document.getElementById('btnWtsModalCancel')?.addEventListener('click', closeWtsImportModal);
      document.getElementById('wtsIncludePossibleDuplicates')?.addEventListener('change', updateWtsCommitButton);
      document.getElementById('btnWtsConfirmCommit')?.addEventListener('click', commitWtsImport);

      // Form input changes do NOT auto-fetch or re-interpret existing rows!
      // They only trigger staleness detection against last successful request metadata.
      basisSelect?.addEventListener('change', checkTossWtsFormStale);
      fromInput?.addEventListener('input', checkTossWtsFormStale);
      toInput?.addEventListener('input', checkTossWtsFormStale);
      initTossWtsIncomeUI();
    }

    // ── Broker Realized Feed Shared Helpers ─────────────────────────────────────
    function brokerRealizedDateKey(value) {
      return window.WealthBrokerRealizedFeedController.dateKey(value);
    }

    function sortBrokerRealizedFeedRows(rows, tokens) {
      return window.WealthBrokerRealizedFeedController.sortRows(rows, tokens);
    }

    // Wealth-side

    const brokerRealizedFeedController = window.WealthBrokerRealizedFeedController.create();

    function brokerPreviewStatusLabel(status) {
      const labels = {
        NEW: '신규 등록 가능',
        ALREADY_IMPORTED: '이미 가져옴',
        POSSIBLE_DUPLICATE: '중복 의심',
        INVALID: '유효하지 않음',
      };
      return labels[status] || '유효하지 않음';
    }

    function brokerImportPreference(state, index) {
      if (!state.importPreferences) {
        state.importPreferences = new Map();
      }
      let pref = state.importPreferences.get(index);
      if (!pref) {
        pref = {
          stock_type: 'general',
          ipo_subscription_fee_krw: 2000,
        };
        state.importPreferences.set(index, pref);
      }
      return pref;
    }

    function brokerImportSelectedItem(state, index) {
      const row = state.rows?.[index];
      const token = state.selectionTokens?.[index] || '';
      if (!row || !token) return null;
      const pref = brokerImportPreference(state, index);
      return {
        row,
        selection_token: token,
        wealth_import: {
          stock_type: pref.stock_type === 'ipo' ? 'ipo' : 'general',
          ipo_subscription_fee_krw: pref.stock_type === 'ipo' ? Number(pref.ipo_subscription_fee_krw ?? 2000) : 0,
        },
      };
    }

    function syncBrokerRowImportOptions(state) {
      const screen = realizedBrokerScreens.find(screen => screen.state === state);
      const body = screen && document.getElementById(screen.cardId)?.querySelector('.toss-wts-table tbody');
      if (!body) return;
      brokerUI.renderFeedImportOptions(body, {
        resolvePreference: index => brokerImportPreference(state, index),
        isImported: index => state.importedIndices.has(index),
        rowName: index => state.rows[index]?.name || '종목',
        onStockType(index, value) {
          brokerImportPreference(state, index).stock_type = value;
          state.previewTicket = null;
        },
        onFeeInput(index, value) {
          brokerImportPreference(state, index).ipo_subscription_fee_krw = value === '' ? '' : parseInt(value, 10);
          state.previewTicket = null;
        },
      });
    }

    function getBrokerContextByOverlayId(overlayId) {
      if (overlayId === 'wtsImportModalOverlay') {
        return {
          brokerKey: 'toss',
          state: tossWtsState,
          refreshPreview: openWtsImportPreview,
          commitButtonId: 'btnWtsConfirmCommit',
        };
      }
      if (overlayId === 'kisImportModalOverlay') {
        return {
          brokerKey: 'kis',
          state: kisRealizedState,
          refreshPreview: openKisImportPreview,
          commitButtonId: 'btnKisConfirmCommit',
        };
      }
      if (overlayId === 'nhImportModalOverlay') {
        return {
          brokerKey: 'nh',
          state: nhRealizedState,
          refreshPreview: openNhImportPreview,
          commitButtonId: 'btnNhConfirmCommit',
        };
      }
      if (overlayId === 'kiwoomImportModalOverlay') {
        return {
          brokerKey: 'kiwoom',
          state: kiwoomRealizedState,
          refreshPreview: openKiwoomImportPreview,
          commitButtonId: 'btnKiwoomConfirmCommit',
        };
      }
      if (overlayId === 'kbImportModalOverlay') {
        return {
          brokerKey: 'kb',
          state: kbRealizedState,
          refreshPreview: openKbImportPreview,
          commitButtonId: 'btnKbConfirmCommit',
        };
      }
      return null;
    }

    let brokerPreviewRefreshTimer = null;
    function scheduleBrokerPreviewRefresh(overlayId) {
      if (brokerPreviewRefreshTimer) clearTimeout(brokerPreviewRefreshTimer);
      brokerPreviewRefreshTimer = setTimeout(async () => {
        brokerPreviewRefreshTimer = null;
        const ctx = getBrokerContextByOverlayId(overlayId);
        if (ctx && ctx.refreshPreview) {
          await ctx.refreshPreview();
        }
      }, 350);
    }

    function setModalRecalculating(overlayId, isRecalculating) {
      const ctx = getBrokerContextByOverlayId(overlayId);
      if (!ctx) return;
      const commitBtn = document.getElementById(ctx.commitButtonId);
      if (commitBtn && isRecalculating) {
        commitBtn.disabled = true;
        commitBtn.textContent = '재계산 중...';
      }
    }

    function brokerImportPnlPresentation(candidate, value) {
      const numeric = Number(value ?? 0);
      const amount = Number.isFinite(numeric) ? numeric : 0;
      const market = String(candidate?.market_type || candidate?.market || '').trim().toUpperCase();
      const currency = String(
        candidate?.currency || (market === 'US' || market === 'OVERSEAS' ? 'USD' : 'KRW')
      ).trim().toUpperCase();

      const sign = amount > 0 ? '+' : (amount < 0 ? '-' : '');
      const absolute = Math.abs(amount);
      const text = currency === 'USD'
        ? `${sign}$${number(absolute, 2)}`
        : `${sign}${money(absolute)}`;
      const toneClass = amount > 0
        ? 'pnl-positive'
        : (amount < 0 ? 'pnl-negative' : '');
      return { text, toneClass };
    }

    function brokerImportNameSizeClass(name) {
      const compactLength = Array.from(String(name || '').replace(/\s+/g, '')).length;
      if (compactLength >= 24) return 'is-very-long';
      if (compactLength >= 17) return 'is-long';
      return '';
    }

    function renderBrokerImportPreviewDetails(data, overlayId) {
      window.WealthBrokerImportPreviewScreenController.renderDetails({
        document, overlayId,
        prepare() {
          const ctx = getBrokerContextByOverlayId(overlayId);
          const state = ctx?.state;
          const selectedIndices = state ? Array.from(state.selectedIndices || []).sort((a, b) => a - b) : [];
          return {
            data, brokerImportPreviewRow: brokerUI.brokerImportPreviewRow,
            formatters: { brokerImportNameSizeClass, brokerImportPnlPresentation },
            resolveRow(item) {
              const choice = item.wealth_import;
              const feedIndex = selectedIndices[item.index] !== undefined ? selectedIndices[item.index] : item.index;
              const preference = state ? brokerImportPreference(state, feedIndex) : choice;
              return { feedIndex, preference };
            },
            async onStockTypeChange(event) {
              const fIdx = Number(event.target.dataset.feedIndex);
              const val = event.target.value;
              if (state) {
                const pref = brokerImportPreference(state, fIdx);
                pref.stock_type = val === 'ipo' ? 'ipo' : 'general';
                if (pref.stock_type === 'ipo') {
                  if (pref.ipo_subscription_fee_krw === '' || pref.ipo_subscription_fee_krw == null || Number(pref.ipo_subscription_fee_krw) === 0) {
                    pref.ipo_subscription_fee_krw = 2000;
                  }
                }
                state.previewTicket = null;
                if (ctx?.brokerKey === 'toss') {
                  tossWtsState.previewTicket = null;
                  if (currentPreviewData) currentPreviewData.preview_ticket = null;
                }
                if (ctx) {
                  syncBrokerRowImportOptions(state);
                }
              }
              setModalRecalculating(overlayId, true);
              if (ctx?.refreshPreview) {
                await ctx.refreshPreview();
              }
            },
            onFeeInput(event) {
              const fIdx = Number(event.target.dataset.feedIndex);
              if (state) {
                const pref = brokerImportPreference(state, fIdx);
                pref.ipo_subscription_fee_krw = event.target.value;
                state.previewTicket = null;
                if (ctx?.brokerKey === 'toss') {
                  tossWtsState.previewTicket = null;
                  if (currentPreviewData) currentPreviewData.preview_ticket = null;
                }
                if (ctx) {
                  syncBrokerRowImportOptions(state);
                }
              }
              setModalRecalculating(overlayId, true);
              scheduleBrokerPreviewRefresh(overlayId);
            },
            async onFeeChange() {
              if (brokerPreviewRefreshTimer) {
                clearTimeout(brokerPreviewRefreshTimer);
                brokerPreviewRefreshTimer = null;
              }
              if (ctx?.refreshPreview) {
                await ctx.refreshPreview();
              }
            },
          };
        },
      });
    }

    // ── 한국투자증권 (KIS) 실현손익 피드 및 선택 가져오기 ────────────────────────
    // Display-only masking for destination account labels.  It deliberately never
    // changes the persisted account name or the value submitted to the server.
    function maskAccountDisplayLabel(value) {
      if (typeof value !== 'string') return value || '';
      return value.replace(/[\d*](?:[\d* -]*[\d*])?/g, matched => {
        const positions = [...matched].map((char, index) => /\d/.test(char) ? index : -1).filter(index => index >= 0);
        const alreadyMasked = matched.includes('**');
        if (positions.length < 8 && !alreadyMasked) return matched;
        const visible = new Set(positions.slice(-4));
        return [...matched].map((char, index) => /\d/.test(char) && !visible.has(index) ? '*' : char).join('');
      });
    }

    const kisRealizedState = {
      status: null,
      configured: false,
      hasAccount: false,
      maskedAccount: '',
      accountScope: '',
      loading: false,
      importing: false,
      rows: [],
      selectionTokens: [],
      selectedIndices: new Set(),
      importedIndices: new Set(),
      importPreferences: new Map(),
      lastRequested: null,
      fetchedMarket: null,
      fetchedFromDate: null,
      fetchedToDate: null,
      fetchedAt: null,
      previewTicket: null,
      currentPreviewClassification: null,
    };
    const kisScreenController = window.WealthBrokerRealizedScreenController.create({
      document, brokerUI, state: kisRealizedState, prefix: 'kis', syncBrokerRowImportOptions,
      loadingButtonIds: ['btnCheckKisStatus', 'btnFetchKisFeed'],
      feedTable: {
        bodyId: 'kisTableBody', checkboxClass: 'kis-row-check',
        emptyMessage: '조회된 실현손익 내역이 없습니다.',
        beforeRender: () => {
          const selectAll = document.getElementById('kisSelectAll');
          if (selectAll) selectAll.checked = false;
        },
        adaptRow: (row, market) => brokerRealizedDisplayRow(row, {
          market, currency: market === 'us' ? 'USD' : 'KRW', kis: true, formatNumber: number,
        }),
        readIndex: target => parseInt(target.getAttribute('data-index'), 10),
        onUpdate: updateKisSelectionUI,
      },
    });

    function showKisMessage(msg, type = 'info') {
      return kisScreenController.showMessage(msg, type);
    }

    function hideKisMessage() {
      kisScreenController.hideMessage();
    }

    function updateKisStatusUI(text, stateClass) {
      brokerUI.renderBrokerState('kis', stateClass, text);
    }

    function setKisLoading(isLoading) {
      kisRealizedState.loading = isLoading;
      kisScreenController.renderLoading(isLoading);
    }

    function checkKisFormStale() {
      const staleEl = document.getElementById('kisStaleHint');
      if (!staleEl) return;

      if (!kisRealizedState.lastRequested || !kisRealizedState.rows || kisRealizedState.rows.length === 0) {
        brokerUI.renderStaleHint(staleEl.id, false);
        return;
      }

      const curMarket = document.getElementById('kisMarketSelect')?.value?.trim();
      const curFrom = document.getElementById('kisFromDate')?.value?.trim();
      const curTo = document.getElementById('kisToDate')?.value?.trim();

      const isStale = (
        curMarket !== kisRealizedState.fetchedMarket ||
        curFrom !== kisRealizedState.fetchedFromDate ||
        curTo !== kisRealizedState.fetchedToDate
      );

      brokerUI.renderStaleHint(staleEl.id, isStale, '조회 조건이 변경되었습니다. [한투 실현손익 조회]를 눌러 다시 조회하세요.');
    }

    function updateKisMetaUI() {
      const metaEl = document.getElementById('kisMeta');
      if (!metaEl) return;

      if (!kisRealizedState.lastRequested || !kisRealizedState.rows) {
        brokerUI.renderFeedMetadata(metaEl, null);
        checkKisFormStale();
        return;
      }

      const mktLabel = kisRealizedState.fetchedMarket === 'us' ? '해외주식 (USD)' : '국내주식 (KRW)';
      const fromDate = kisRealizedState.fetchedFromDate || '-';
      const toDate = kisRealizedState.fetchedToDate || '-';
      const count = kisRealizedState.rows.length;
      const timeStr = kisRealizedState.fetchedAt ? new Date(kisRealizedState.fetchedAt).toLocaleTimeString('ko-KR') : '';

      brokerUI.renderFeedMetadata(metaEl, `
    <span class="toss-wts-meta-item">조회 시장: <strong>${html(mktLabel)}</strong></span>
    <span class="toss-wts-meta-sep">·</span>
    <span class="toss-wts-meta-item">조회 기간: <strong>${html(fromDate)} ~ ${html(toDate)}</strong></span>
    ${timeStr ? `<span class="toss-wts-meta-sep">·</span><span class="toss-wts-meta-item">조회 시각: ${html(timeStr)}</span>` : ''}
    <span class="toss-wts-meta-sep">·</span>
    <span class="toss-wts-meta-item"><strong>${count}건</strong></span>
  `);
      checkKisFormStale();
    }

    async function checkKisStatus() {
      if (kisRealizedState.loading) return;
      setKisLoading(true);
      brokerUI.renderBrokerState('kis', 'checking', '상태 확인 중');
      try {
        const res = await fetch('/api/kis/status');
        if (!res.ok) {
          updateKisStatusUI('상태 확인 실패', 'error');
          showKisMessage('한국투자증권 연동 상태 확인에 실패했습니다.', 'error');
          return;
        }
        const data = await res.json();
        kisRealizedState.status = data;
        kisRealizedState.configured = !!data.configured;
        kisRealizedState.hasAccount = !!data.has_account;
        kisRealizedState.maskedAccount = data.masked_account || '';
        kisRealizedState.sourceAccountKey = data.source_account_key || '';
        kisRealizedState.sourceAccountLabel = data.source_account_label || data.masked_account || '';
        kisRealizedState.mappedDestAccountId = data.auto_selected_account_id || data.mapped_destination_account_id || '';

        if (!data.configured) {
          updateKisStatusUI('미설정 (API 키 필요)', 'action_required');
          showKisMessage('상단 [OpenAPI] 버튼에서 한국투자증권 AppKey와 AppSecret을 등록하세요.', 'warning');
        } else if (!data.has_account) {
          updateKisStatusUI('계좌 미등록', 'action_required');
          showKisMessage('상단 [OpenAPI] 버튼에서 한국투자증권 계좌번호를 등록하세요.', 'warning');
        } else {
          updateKisStatusUI(`계좌: ${maskAccountDisplayLabel(data.masked_account || '확인됨')}`, 'ready');
          hideKisMessage();
        }
      } catch (err) {
        updateKisStatusUI('연결 오류', 'error');
        showKisMessage('네트워크 오류가 발생했습니다.', 'error');
      } finally {
        setKisLoading(false);
      }
    }

    async function fetchKisRealizedFeed() {
      if (kisRealizedState.loading) return;
      hideKisMessage();

      const market = document.getElementById('kisMarketSelect')?.value?.trim() || 'kr';
      const fromDate = document.getElementById('kisFromDate')?.value?.trim();
      const toDate = document.getElementById('kisToDate')?.value?.trim();

      if (!fromDate || !toDate) {
        showKisMessage('시작일과 종료일을 모두 선택하세요.', 'warning');
        return;
      }
      if (fromDate > toDate) {
        showKisMessage('시작일은 종료일보다 이전이거나 같아야 합니다.', 'warning');
        return;
      }

      setKisLoading(true);
      try {
        const res = await fetch('/api/kis/realized-feed/fetch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ market, from_date: fromDate, to_date: toDate }),
        });

        if (res.status === 400 || res.status === 502) {
          const err = await res.json().catch(() => ({}));
          const msg = err.detail?.message || err.detail?.code || '조회 실패';
          showKisMessage(msg, 'error');
          renderKisFeedTable([], market, 'empty');
          return;
        }
        if (!res.ok) {
          showKisMessage(`조회 실패 (HTTP ${res.status})`, 'error');
          renderKisFeedTable([], market, 'empty');
          return;
        }

        const data = await res.json();
        brokerRealizedFeedController.applySuccessfulFeed(kisRealizedState, data.rows || [], data.selection_tokens || []);
        kisRealizedState.currentPreviewClassification = null;
        kisRealizedState.lastRequested = data.requested;
        kisRealizedState.fetchedMarket = data.market || market;
        kisRealizedState.fetchedFromDate = data.requested?.from_date || fromDate;
        kisRealizedState.fetchedToDate = data.requested?.to_date || toDate;
        kisRealizedState.fetchedAt = data.fetched_at || new Date().toISOString();

        renderKisFeedTable(kisRealizedState.rows, kisRealizedState.fetchedMarket, data.state);
        updateKisMetaUI();
        updateKisSelectionUI();

        if (kisRealizedState.rows.length === 0) {
          showKisMessage('해당 기간의 실현손익 내역이 없습니다.', 'info');
        }
      } catch (err) {
        showKisMessage('조회 중 네트워크 오류가 발생했습니다.', 'error');
      } finally {
        setKisLoading(false);
      }
    }

    function renderKisFeedTable(rows, market, state) {
      kisScreenController.renderFeedTable(rows, market);
    }

    function updateKisSelectionUI() {
      const selectAll = document.getElementById('kisSelectAll');
      const accountSelect = document.getElementById('kisDestinationAccount');

      populateKisDestinationAccounts();

      const count = kisRealizedState.selectedIndices.size;
      const hasAccount = !!accountSelect?.value;
      brokerUI.renderSelectionState({ badgeId: 'kisSelectedCountBadge', count,
        buttonId: 'btnKisImportSelected', disabled: count === 0 || !hasAccount });

      if (selectAll && kisRealizedState.rows) {
        const unimportedCount = kisRealizedState.rows.filter((_, idx) => !kisRealizedState.importedIndices.has(idx)).length;
        brokerUI.renderSelectAllState('kisSelectAll', unimportedCount > 0 && count === unimportedCount);
      }
      syncBrokerRowImportOptions(kisRealizedState);
    }

    function realizedBrokerId(value) {
      const text = String(value || '').trim().toLowerCase();
      if (['kis', '한국투자증권', '한투'].includes(text)) return 'kis';
      if (['nh', 'nh투자증권', '나무', 'namuh', 'qv', 'nh투자증권(나무)', '나무증권'].includes(text)) return 'nh';
      if (['kiwoom', '키움증권', '키움', '영웅문'].includes(text)) return 'kiwoom';
      if (['kb', 'kb증권', 'm-able', '마블', '현대증권', 'kb securities'].includes(text)) return 'kb';
      return '';
    }

    function realizedDestinationAccounts(accounts, provider, candidateIds) {
      const allowedIds = Array.isArray(candidateIds) ? new Set(candidateIds.map(String)) : null;
      return accounts.filter(account => (
        realizedBrokerId(account.broker) === provider
        && (!allowedIds || allowedIds.has(String(account.id || '')))
      ));
    }

    function setRealizedDestinationEmptyMessage(select) {
      if (select && select.options.length === 1) {
        select.options[0].textContent = '해당 증권사 계좌를 먼저 등록하세요.';
      }
    }

    function populateKisDestinationAccounts() {
      const dashboard = getDashboard();
      const select = document.getElementById('kisDestinationAccount');
      if (!select) return;

      const accounts = (dashboard && Array.isArray(dashboard.accounts))
        ? dashboard.accounts
        : (typeof window !== 'undefined' && Array.isArray(window.pnlState?.accounts) ? window.pnlState.accounts : []);

      const curVal = select.value;
      select.innerHTML = '<option value="">귀속 계좌 선택...</option>';

      const key = kisRealizedState.sourceAccountKey || '';
      const localMapped = key ? localStorage.getItem('kis_account_map_' + key) : null;
      const mappedId = kisRealizedState.mappedDestAccountId || localMapped;

      realizedDestinationAccounts(accounts, 'kis', kisRealizedState.status?.candidate_account_ids).forEach(acc => {
        const id = String(acc.id || '');
        const broker = acc.broker || '';
        const name = maskAccountDisplayLabel(acc.account_name || acc.name || `계좌 ${id}`);
        const owner = acc.owner ? ` (${acc.owner})` : '';
        const label = `[${broker}] ${name}${owner}`;

        const opt = document.createElement('option');
        opt.value = id;
        opt.textContent = label;
        select.appendChild(opt);
      });
      setRealizedDestinationEmptyMessage(select);

      // First use: DO NOT auto-select based on broker name or single account.
      // Require explicit choice unless a verified persistent mapping exists.
      if (curVal && Array.from(select.options).some(o => o.value === curVal)) {
        select.value = curVal;
      } else if (mappedId && Array.from(select.options).some(o => o.value === String(mappedId))) {
        select.value = String(mappedId);
      } else {
        select.value = '';
      }
    }

    function kisSelectedItems() {
      return brokerRealizedFeedController.selectedImportItems(kisRealizedState, brokerImportSelectedItem);
    }

    async function openKisImportPreview() {
      if (kisRealizedState.selectedIndices.size === 0) return;
      const accountSelect = document.getElementById('kisDestinationAccount');
      const accountId = accountSelect?.value;
      if (!accountId) {
        showKisMessage('귀속할 Wealth 계좌를 선택하세요.', 'warning');
        return;
      }

      const selectedItems = kisSelectedItems();
      if (selectedItems.length === 0) return;

      setKisLoading(true);
      try {
        const res = await fetch('/api/kis/realized-feed/import-preview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            selected_items: selectedItems,
            account_id: accountId,
            market: kisRealizedState.fetchedMarket || 'kr',
          }),
        });

        if (!res.ok) {
          kisRealizedState.previewTicket = null;
          updateKisCommitButton();
          const err = await res.json().catch(() => ({}));
          showKisMessage(err.detail?.message || '미리보기 검증 실패', 'error');
          return;
        }

        const data = await res.json();
        kisRealizedState.previewTicket = data.preview_ticket;
        kisRealizedState.currentPreviewClassification = data;
        renderKisPreviewModal(data);
      } catch (err) {
        kisRealizedState.previewTicket = null;
        updateKisCommitButton();
        showKisMessage('미리보기 통신 오류', 'error');
      } finally {
        setKisLoading(false);
      }
    }

    function renderKisPreviewModal(data) {
      const overlay = document.getElementById('kisImportModalOverlay');
      if (!overlay) return;

      const counts = data.counts || { new: 0, already_imported: 0, possible_duplicate: 0, invalid: 0 };
      const dest = data.destination_account || {};

      brokerUI.renderPreviewSummary({
        counts, countIds: {
        new: 'kisModalCountNew', already_imported: 'kisModalCountAlready',
        possible_duplicate: 'kisModalCountDup', invalid: 'kisModalCountInvalid',
      },
        destinationId: 'kisModalDestAccountDisplay', destination: {
        accountText: `[${dest.broker || '한국투자증권'}] ${maskAccountDisplayLabel(dest.account_name || '-')}`,
        ownerText: dest.owner || '모두',
      },
        duplicate: { wrapId: 'kisDupOverrideWrap', checkboxId: 'kisIncludePossibleDuplicates',
          visible: counts.possible_duplicate > 0, presence: 'wrap' },
      });
      const itemsBody = document.getElementById('kisModalItemsBody');
      if (itemsBody) {
        const rowsHtml = (data.items || []).map(it => {
          const cand = it.candidate || it.row || {};
          const pnlVal = Number(cand.pnl !== undefined ? cand.pnl : (cand.profit_loss || 0));
          const pnlSign = pnlVal > 0 ? '+' : '';
          const pnlCls = pnlVal > 0 ? 'pos' : (pnlVal < 0 ? 'neg' : '');
          const nameVal = cand.name || cand.prdt_name || '-';
          const dateVal = cand.date || cand.trad_dt || '-';
          const qtyVal = cand.source_meta?.quantity ? Number(cand.source_meta.quantity).toLocaleString() : (cand.quantity ? Number(cand.quantity).toLocaleString() : '-');
          const curVal = cand.currency || (kisRealizedState.fetchedMarket === 'us' ? 'USD' : 'KRW');

          return `
        <tr>
          <td><span class="badge">${html(brokerPreviewStatusLabel(it.status))}</span></td>
          <td>${html(dateVal)}</td>
          <td><strong>${html(nameVal)}</strong></td>
          <td class="num">${qtyVal}</td>
          <td class="num ${pnlCls}">${pnlSign}${pnlVal.toLocaleString()} ${html(curVal)}</td>
        </tr>
      `;
        });
        itemsBody.innerHTML = rowsHtml.join('');
      }

      updateKisCommitButton();
      renderBrokerImportPreviewDetails(data, 'kisImportModalOverlay');
      brokerUI.setModalVisible('kisImportModalOverlay', true);
    }

    function updateKisCommitButton() {
      const commitBtn = document.getElementById('btnKisConfirmCommit');
      const dupCheck = document.getElementById('kisIncludePossibleDuplicates');
      const data = kisRealizedState.currentPreviewClassification;
      if (!commitBtn || !data) return;

      const counts = data.counts || {};
      const newCnt = Number(counts.new || 0);
      const dupCnt = Number(counts.possible_duplicate || 0);
      const includeDup = !!dupCheck?.checked;
      const eligibleCount = newCnt + (includeDup ? dupCnt : 0);

      commitBtn.textContent = `${eligibleCount}건 가져오기 완료`;
      brokerUI.setButtonDisabled('btnKisConfirmCommit', eligibleCount === 0 || !kisRealizedState.previewTicket || kisRealizedState.importing);
    }

    function closeKisImportModal() {
      brokerUI.setModalVisible('kisImportModalOverlay', false);
      kisRealizedState.currentPreviewClassification = null;
      kisRealizedState.previewTicket = null;
    }

    async function commitKisImport() {
      if (kisRealizedState.importing || !kisRealizedState.previewTicket) return;
      kisRealizedState.importing = true;
      updateKisCommitButton();

      const data = kisRealizedState.currentPreviewClassification;
      const accountId = data?.destination_account?.id || document.getElementById('kisDestinationAccount')?.value;
      const previewTicket = kisRealizedState.previewTicket;
      const dupCheck = document.getElementById('kisIncludePossibleDuplicates');
      const includePossibleDuplicates = !!dupCheck?.checked;

      const selectedItems = kisSelectedItems();

      setKisLoading(true);
      try {
        const res = await fetch('/api/kis/realized-feed/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            selected_items: selectedItems,
            account_id: accountId,
            preview_ticket: previewTicket,
            include_possible_duplicates: includePossibleDuplicates,
            market: kisRealizedState.fetchedMarket || 'kr',
          }),
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          showKisMessage(err.detail?.message || '가져오기 실패', 'error');
          return;
        }

        const result = await res.json();
        closeKisImportModal();

        kisRealizedState.selectedIndices.forEach(idx => {
          kisRealizedState.importedIndices.add(idx);
        });
        kisRealizedState.selectedIndices.clear();
        kisRealizedState.previewTicket = null;

        renderKisFeedTable(kisRealizedState.rows, kisRealizedState.fetchedMarket, 'ok');
        updateKisSelectionUI();

        showKisMessage(`한국투자증권 실현손익 ${result.imported}건을 성공적으로 Wealth 계좌에 가져왔습니다.`, 'success');

        if (typeof loadPnlRecords === 'function') {
          loadPnlRecords();
        }
        if (typeof fetchDashboard === 'function') {
          fetchDashboard();
        }
      } catch (err) {
        showKisMessage('가져오기 처리 중 네트워크 오류가 발생했습니다.', 'error');
      } finally {
        kisRealizedState.importing = false;
        setKisLoading(false);
        updateKisCommitButton();
        updateKisSelectionUI();
      }
    }

    // ── NH투자증권 (NH) 실현손익 UI ─────────────────────────────────────────────
    // NH keeps its own state so broker tabs cannot share signed rows or preview tickets.
    function refreshBrokerImportedResults() {
      if (typeof loadPnlRecords === 'function') loadPnlRecords();
      if (typeof loadDashboard === 'function') loadDashboard();
      else if (typeof fetchDashboard === 'function') fetchDashboard();
    }

    function populateOpenApiDestinationAccounts(select, state, broker) {
      const dashboard = getDashboard();
      const accounts = (dashboard && Array.isArray(dashboard.accounts)) ? dashboard.accounts : (typeof window !== 'undefined' && Array.isArray(window.pnlState?.accounts) ? window.pnlState.accounts : []);
      const source = state.accounts.find(a => a.source_account_key === state.sourceAccountKey);
      const allowedAccounts = realizedDestinationAccounts(accounts, broker, source?.candidate_account_ids);
      brokerUI.populateBrokerDestinationAccountSelect(select, allowedAccounts, state.mappedDestAccountId, maskAccountDisplayLabel);
    }

    const brokerRealizedScreenDependencies = {
      document, brokerUI, html, brokerRealizedDisplayRow, syncBrokerRowImportOptions,
      previewScreenController: window.WealthBrokerImportPreviewScreenController,
      maskAccountDisplayLabel, brokerPreviewStatusLabel, renderBrokerImportPreviewDetails,
    };

    function createMappedImport({
      state, providerName, previewUrl, commitUrl, destinationId, duplicateToggleId,
      commitButtonId, overlayId, resolveMarket, reportMappingResult = false,
      selectedItems, setLoading, hideMessage, showMessage, renderPreviewModal,
      renderFeedTable, updateSelectionUI, errorText,
    }) {
      function includeDuplicates() {
        return !!document.getElementById(duplicateToggleId)?.checked;
      }

      function updateCommitButton() {
        const counts = state.preview?.counts || {};
        const include = includeDuplicates();
        const eligible = (counts.new || 0) + (include ? (counts.possible_duplicate || 0) : 0);
        brokerUI.renderBrokerImportCommitButton(commitButtonId, eligible, state.previewTicket, state.importing);
      }

      function closeModal() {
        brokerUI.setModalVisible(overlayId, false);
        brokerRealizedFeedController.clearImportPreview(state);
      }

      function destinationAccountId() {
        return document.getElementById(destinationId)?.value;
      }

      function importPayload(items, accountId) {
        return {
          selected_items: items,
          account_id: accountId,
          market: resolveMarket(),
          source_account_key: state.sourceAccountKey,
        };
      }

      function post(url, payload) {
        return fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }

      async function openPreview() {
        const accountId = destinationAccountId();
        const items = selectedItems();
        if (!accountId) return showMessage('귀속할 Wealth 계좌를 선택하세요.', 'warning');
        if (!items.length) return;

        return brokerRealizedFeedController.previewOpenApiImport({
          state,
          request: () => post(previewUrl, importPayload(items, accountId)),
          setLoading, hideMessage, showMessage, renderPreviewModal, updateCommitButton,
          errorText, errorFallback: `${providerName} 미리보기 검증에 실패했습니다.`,
        });
      }

      function showResult(data) {
        if (reportMappingResult && (data.partial_success || data.mapping_warning === 'MAPPING_PERSISTENCE_FAILED')) {
          showMessage(`${providerName} 실현손익 ${data.imported || 0}건 가져오기를 완료했으나, 계좌 매핑 저장에 실패했습니다. 재시도 시 손익 중복 없이 매핑을 복구할 수 있습니다.`, 'warning');
        } else if (reportMappingResult && data.mapping_repaired) {
          showMessage(`${providerName} 실현손익 ${data.imported || 0}건을 가져오고 계좌 매핑을 복구했습니다.`, 'success');
        } else {
          showMessage(`${providerName} 실현손익 ${data.imported || 0}건을 Wealth 계좌에 가져왔습니다.`, 'success');
        }
      }

      async function commit() {
        if (state.importing || !state.previewTicket) return;
        state.importing = true;
        return brokerRealizedFeedController.commitOpenApiImport({
          state,
          destinationAccountId: () => state.preview?.destination_account?.id || destinationAccountId(),
          request: accountId => post(commitUrl, {
            ...importPayload(selectedItems(), accountId),
            preview_ticket: state.previewTicket,
            include_possible_duplicates: includeDuplicates(),
          }),
          updateCommitButton, updateSelectionUI, closeModal, renderFeedTable, showResult,
          refreshResults: refreshBrokerImportedResults,
          showMessage, errorText, errorFallback: `${providerName} 가져오기에 실패했습니다.`,
        });
      }

      return Object.freeze({ openPreview, updateCommitButton, closeModal, commit });
    }

    const nhRealizedState = {
      status: null, accounts: [], sourceAccountKey: '', mappedDestAccountId: '',
      loading: false, importing: false, rows: [], selectionTokens: [],
      selectedIndices: new Set(), importedIndices: new Set(), market: 'kr',
      importPreferences: new Map(),
      previewTicket: null, preview: null,
    };
    const nhScreenController = window.WealthBrokerRealizedScreenController.create({
      ...brokerRealizedScreenDependencies, state: nhRealizedState, prefix: 'nh',
      statusButtonId: 'btnCheckNhStatus', fetchButtonId: 'btnFetchNhFeed', importButtonId: 'btnNhImportSelected',
      formatNumber: nhNumber, pnlDigits: 2, defaultCurrency: '',
      populateDestinationAccounts: populateNhDestinationAccounts, updateCommitButton: updateNhCommitButton,
    });

    const nhMappedImport = createMappedImport({
      state: nhRealizedState, providerName: 'NH',
      previewUrl: '/api/nh/realized-feed/import-preview',
      commitUrl: '/api/nh/realized-feed/import',
      destinationId: 'nhDestinationAccount', duplicateToggleId: 'nhIncludePossibleDuplicates',
      commitButtonId: 'btnNhConfirmCommit', overlayId: 'nhImportModalOverlay',
      resolveMarket: () => nhRealizedState.market,
      selectedItems: nhSelectedItems, setLoading: setNhLoading,
      hideMessage: hideNhMessage, showMessage: showNhMessage,
      renderPreviewModal: renderNhPreviewModal, renderFeedTable: renderNhFeedTable,
      updateSelectionUI: updateNhSelectionUI, errorText: nhSafeError,
    });

    function showNhMessage(message, type = 'info') {
      return nhScreenController.showMessage(message, type);
    }
    function hideNhMessage() {
      return nhScreenController.hideMessage();
    }
    function setNhLoading(loading) {
      nhRealizedState.loading = loading;
      nhScreenController.renderLoading(loading);
    }
    function nhSafeError(error, fallback) { return brokerUI.brokerErrorText(error, fallback); }
    function nhSelectedItems() {
      return brokerRealizedFeedController.selectedImportItems(nhRealizedState, brokerImportSelectedItem);
    }
    function populateNhSourceAccounts() {
      const select = document.getElementById('nhSourceAccount'); if (!select) return;
      nhRealizedState.sourceAccountKey = brokerUI.populateBrokerSourceAccountSelect(select, nhRealizedState.accounts, '마스킹된 NH 계좌');
      nhRealizedState.mappedDestAccountId = brokerRealizedFeedController.mappedDestinationAccountId(nhRealizedState, nhRealizedState.sourceAccountKey);
    }
    async function checkNhStatus() {
      return brokerRealizedFeedController.checkOpenApiStatus({
        state: nhRealizedState,
        request: () => fetch('/api/nh/status'),
        setLoading: setNhLoading, hideMessage: hideNhMessage, showMessage: showNhMessage,
        renderState: (status, text) => brokerUI.renderBrokerState('nh', status, text),
        populateSourceAccounts: populateNhSourceAccounts, updateSelectionUI: updateNhSelectionUI,
        errorText: nhSafeError, errorFallback: 'NH 연동 상태 확인에 실패했습니다.',
        configurationWarning: 'NH투자증권 OpenAPI 설정이 필요합니다.',
        noAccountsWarning: '조회 가능한 NH 계좌가 없습니다.',
      });
    }
    function populateNhDestinationAccounts() {
      const select = document.getElementById('nhDestinationAccount'); if (!select) return;
      populateOpenApiDestinationAccounts(select, nhRealizedState, 'nh');
    }
    async function fetchNhRealizedFeed() {
      if (nhRealizedState.loading) return;
      const market = document.getElementById('nhMarketSelect')?.value || 'kr'; const fromDate = document.getElementById('nhFromDate')?.value; const toDate = document.getElementById('nhToDate')?.value;
      if (!nhRealizedState.sourceAccountKey) return showNhMessage('마스킹된 NH 원본 계좌를 선택하세요.', 'warning');
      if (!fromDate || !toDate || fromDate > toDate) return showNhMessage('유효한 시작일과 종료일을 선택하세요.', 'warning');
      return brokerRealizedFeedController.fetchOpenApiRealizedFeed({
        state: nhRealizedState,
        request: () => fetch('/api/nh/realized-feed/fetch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ market, from_date: fromDate, to_date: toDate, source_account_key: nhRealizedState.sourceAccountKey }) }),
        resolveMarket: data => data.market || market,
        setLoading: setNhLoading, hideMessage: hideNhMessage, showMessage: showNhMessage,
        renderMetadata: (market, rowCount) => brokerUI.renderBrokerFetchMetadata('nhMeta', market, rowCount),
        renderFeedTable: renderNhFeedTable, updateSelectionUI: updateNhSelectionUI,
        emptyMessage: '해당 기간의 실현손익 내역이 없습니다.',
        errorText: nhSafeError, errorFallback: 'NH 실현손익 조회에 실패했습니다.',
      });
    }
    function nhNumber(value, digits = 0) { return window.WealthFormat.fixedNumberKoKr(value, digits); }
    function renderNhFeedTable() {
      return nhScreenController.renderFeedTable();
    }
    function updateNhSelectionUI() {
      return nhScreenController.updateSelectionUI();
    }
    async function openNhImportPreview() {
      return nhMappedImport.openPreview();
    }
    function renderNhPreviewModal(data) {
      return nhScreenController.renderPreviewModal(data);
    }
    function updateNhCommitButton() {
      return nhMappedImport.updateCommitButton();
    }
    function closeNhImportModal() {
      return nhMappedImport.closeModal();
    }
    async function commitNhImport() {
      return nhMappedImport.commit();
    }

    // ── 키움증권 (Kiwoom) 실현손익 UI ──────────────────────────────────────────
    const kiwoomRealizedState = {
      status: null, accounts: [], sourceAccountKey: '', mappedDestAccountId: '',
      loading: false, importing: false, rows: [], selectionTokens: [],
      selectedIndices: new Set(), importedIndices: new Set(), market: 'kr',
      importPreferences: new Map(),
      previewTicket: null, preview: null,
    };
    const kiwoomScreenController = window.WealthBrokerRealizedScreenController.create({
      ...brokerRealizedScreenDependencies, state: kiwoomRealizedState, prefix: 'kiwoom',
      statusButtonId: 'btnCheckKiwoomStatus', fetchButtonId: 'btnFetchKiwoomFeed', importButtonId: 'btnKiwoomImportSelected',
      formatNumber: kiwoomNumber, pnlDigits: 2, defaultCurrency: '',
      populateDestinationAccounts: populateKiwoomDestinationAccounts, updateCommitButton: updateKiwoomCommitButton,
    });

    const kiwoomMappedImport = createMappedImport({
      state: kiwoomRealizedState, providerName: '키움',
      previewUrl: '/api/kiwoom/realized-feed/import-preview',
      commitUrl: '/api/kiwoom/realized-feed/import',
      destinationId: 'kiwoomDestinationAccount', duplicateToggleId: 'kiwoomIncludePossibleDuplicates',
      commitButtonId: 'btnKiwoomConfirmCommit', overlayId: 'kiwoomImportModalOverlay',
      resolveMarket: () => kiwoomRealizedState.market,
      selectedItems: kiwoomSelectedItems, setLoading: setKiwoomLoading,
      hideMessage: hideKiwoomMessage, showMessage: showKiwoomMessage,
      renderPreviewModal: renderKiwoomPreviewModal, renderFeedTable: renderKiwoomFeedTable,
      updateSelectionUI: updateKiwoomSelectionUI, errorText: kiwoomSafeError,
      reportMappingResult: true,
    });

    function showKiwoomMessage(message, type = 'info') {
      return kiwoomScreenController.showMessage(message, type);
    }
    function hideKiwoomMessage() {
      return kiwoomScreenController.hideMessage();
    }
    function setKiwoomLoading(loading) {
      kiwoomRealizedState.loading = loading;
      kiwoomScreenController.renderLoading(loading);
    }
    function kiwoomSafeError(error, fallback) { return brokerUI.brokerErrorText(error, fallback); }
    function kiwoomSelectedItems() {
      return brokerRealizedFeedController.selectedImportItems(kiwoomRealizedState, brokerImportSelectedItem);
    }
    function populateKiwoomSourceAccounts() {
      const select = document.getElementById('kiwoomSourceAccount'); if (!select) return;
      kiwoomRealizedState.sourceAccountKey = brokerUI.populateBrokerSourceAccountSelect(select, kiwoomRealizedState.accounts, '마스킹된 키움 계좌');
      kiwoomRealizedState.mappedDestAccountId = brokerRealizedFeedController.mappedDestinationAccountId(kiwoomRealizedState, kiwoomRealizedState.sourceAccountKey);
    }
    async function checkKiwoomStatus() {
      return brokerRealizedFeedController.checkOpenApiStatus({
        state: kiwoomRealizedState,
        request: () => fetch('/api/kiwoom/status'),
        setLoading: setKiwoomLoading, hideMessage: hideKiwoomMessage, showMessage: showKiwoomMessage,
        renderState: (status, text) => brokerUI.renderBrokerState('kiwoom', status, text),
        populateSourceAccounts: populateKiwoomSourceAccounts, updateSelectionUI: updateKiwoomSelectionUI,
        errorText: kiwoomSafeError, errorFallback: '키움 연동 상태 확인에 실패했습니다.',
        configurationWarning: '키움증권 OpenAPI 설정이 필요합니다.',
        noAccountsWarning: '조회 가능한 키움 계좌가 없습니다.',
      });
    }
    function populateKiwoomDestinationAccounts() {
      const select = document.getElementById('kiwoomDestinationAccount'); if (!select) return;
      populateOpenApiDestinationAccounts(select, kiwoomRealizedState, 'kiwoom');
    }
    async function fetchKiwoomRealizedFeed() {
      if (kiwoomRealizedState.loading) return;
      const market = document.getElementById('kiwoomMarketSelect')?.value || 'kr';
      const fromDate = document.getElementById('kiwoomFromDate')?.value;
      const toDate = document.getElementById('kiwoomToDate')?.value;
      if (!kiwoomRealizedState.sourceAccountKey) return showKiwoomMessage('마스킹된 키움 원본 계좌를 선택하세요.', 'warning');
      if (!fromDate || !toDate || fromDate > toDate) return showKiwoomMessage('유효한 시작일과 종료일을 선택하세요.', 'warning');
      return brokerRealizedFeedController.fetchOpenApiRealizedFeed({
        state: kiwoomRealizedState,
        request: () => fetch('/api/kiwoom/realized-feed/fetch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ market, from_date: fromDate, to_date: toDate, source_account_key: kiwoomRealizedState.sourceAccountKey })
        }),
        resolveMarket: data => data.market || market,
        setLoading: setKiwoomLoading, hideMessage: hideKiwoomMessage, showMessage: showKiwoomMessage,
        renderMetadata: (market, rowCount) => brokerUI.renderBrokerFetchMetadata('kiwoomMeta', market, rowCount),
        renderFeedTable: renderKiwoomFeedTable, updateSelectionUI: updateKiwoomSelectionUI,
        emptyMessage: '해당 기간의 실현손익 내역이 없습니다.',
        errorText: kiwoomSafeError, errorFallback: '키움 실현손익 조회에 실패했습니다.',
      });
    }
    function kiwoomNumber(value, digits = 0) { return window.WealthFormat.fixedNumberKoKr(value, digits); }
    function renderKiwoomFeedTable() {
      return kiwoomScreenController.renderFeedTable();
    }
    function updateKiwoomSelectionUI() {
      return kiwoomScreenController.updateSelectionUI();
    }
    async function openKiwoomImportPreview() {
      return kiwoomMappedImport.openPreview();
    }
    function renderKiwoomPreviewModal(data) {
      return kiwoomScreenController.renderPreviewModal(data);
    }
    function updateKiwoomCommitButton() {
      return kiwoomMappedImport.updateCommitButton();
    }
    function closeKiwoomImportModal() {
      return kiwoomMappedImport.closeModal();
    }
    async function commitKiwoomImport() {
      return kiwoomMappedImport.commit();
    }
    function initKiwoomRealizedUI() {
      kiwoomScreenController.bindImportEvents({
        confirmButtonId: 'btnKiwoomConfirmCommit', closeButtonId: 'btnKiwoomModalClose', cancelButtonId: 'btnKiwoomModalCancel',
        setLoading: setKiwoomLoading, openPreview: openKiwoomImportPreview, closeModal: closeKiwoomImportModal,
        updateCommitButton: updateKiwoomCommitButton, commit: commitKiwoomImport,
        sourceAccountChanged: key => {
          kiwoomRealizedState.sourceAccountKey = key;
          kiwoomRealizedState.mappedDestAccountId = brokerRealizedFeedController.mappedDestinationAccountId(kiwoomRealizedState, key);
        },
      });
    }

    // ── KB증권 (KB Securities) 실현손익 UI ──────────────────────────────────────
    const kbRealizedState = {
      status: null, accounts: [], sourceAccountKey: '', mappedDestAccountId: '',
      loading: false, importing: false, rows: [], selectionTokens: [],
      selectedIndices: new Set(), importedIndices: new Set(), market: 'kr',
      importPreferences: new Map(),
      previewTicket: null, preview: null,
    };
    const kbScreenController = window.WealthBrokerRealizedScreenController.create({
      ...brokerRealizedScreenDependencies, state: kbRealizedState, prefix: 'kb',
      statusButtonId: 'btnCheckKbStatus', fetchButtonId: 'btnFetchKbFeed', importButtonId: 'btnKbImportSelected',
      formatNumber: kbNumber, pnlDigits: 0, defaultCurrency: 'KRW',
      populateDestinationAccounts: populateKbDestinationAccounts, updateCommitButton: updateKbCommitButton,
    });

    const kbMappedImport = createMappedImport({
      state: kbRealizedState, providerName: 'KB',
      previewUrl: '/api/kb/realized-feed/import-preview',
      commitUrl: '/api/kb/realized-feed/import',
      destinationId: 'kbDestinationAccount', duplicateToggleId: 'kbIncludePossibleDuplicates',
      commitButtonId: 'btnKbConfirmCommit', overlayId: 'kbImportModalOverlay',
      resolveMarket: () => 'kr',
      selectedItems: kbSelectedItems, setLoading: setKbLoading,
      hideMessage: hideKbMessage, showMessage: showKbMessage,
      renderPreviewModal: renderKbPreviewModal, renderFeedTable: renderKbFeedTable,
      updateSelectionUI: updateKbSelectionUI, errorText: kbSafeError,
      reportMappingResult: true,
    });

    function showKbMessage(message, type = 'info') {
      return kbScreenController.showMessage(message, type);
    }
    function hideKbMessage() {
      return kbScreenController.hideMessage();
    }
    function setKbLoading(loading) {
      kbRealizedState.loading = loading;
      kbScreenController.renderLoading(loading);
    }
    function kbSafeError(error, fallback) { return brokerUI.brokerErrorText(error, fallback); }
    function kbSelectedItems() {
      return brokerRealizedFeedController.selectedImportItems(kbRealizedState, brokerImportSelectedItem);
    }
    function populateKbSourceAccounts() {
      const select = document.getElementById('kbSourceAccount'); if (!select) return;
      kbRealizedState.sourceAccountKey = brokerUI.populateBrokerSourceAccountSelect(select, kbRealizedState.accounts, '마스킹된 KB 계좌');
      kbRealizedState.mappedDestAccountId = brokerRealizedFeedController.mappedDestinationAccountId(kbRealizedState, kbRealizedState.sourceAccountKey);
    }
    async function checkKbStatus() {
      return brokerRealizedFeedController.checkOpenApiStatus({
        state: kbRealizedState,
        request: () => fetch('/api/kb/status'),
        setLoading: setKbLoading, hideMessage: hideKbMessage, showMessage: showKbMessage,
        renderState: (status, text) => brokerUI.renderBrokerState('kb', status, text),
        populateSourceAccounts: populateKbSourceAccounts, updateSelectionUI: updateKbSelectionUI,
        errorText: kbSafeError, errorFallback: 'KB 연동 상태 확인에 실패했습니다.',
        configurationWarning: 'KB증권 OpenAPI 설정이 필요합니다.',
        noAccountsWarning: '조회 가능한 KB 계좌가 없습니다.',
      });
    }
    function populateKbDestinationAccounts() {
      const select = document.getElementById('kbDestinationAccount'); if (!select) return;
      populateOpenApiDestinationAccounts(select, kbRealizedState, 'kb');
    }
    async function fetchKbRealizedFeed() {
      if (kbRealizedState.loading) return;
      const market = document.getElementById('kbMarketSelect')?.value || 'kr';
      if (market !== 'kr') {
        return showKbMessage('KB 해외주식 실현손익은 현재 Open API에서 지원되지 않습니다.', 'warning');
      }
      const fromDate = document.getElementById('kbFromDate')?.value;
      const toDate = document.getElementById('kbToDate')?.value;
      if (!kbRealizedState.sourceAccountKey) return showKbMessage('마스킹된 KB 원본 계좌를 선택하세요.', 'warning');
      if (!fromDate || !toDate || fromDate > toDate) return showKbMessage('유효한 시작일과 종료일을 선택하세요.', 'warning');
      return brokerRealizedFeedController.fetchOpenApiRealizedFeed({
        state: kbRealizedState,
        request: () => fetch('/api/kb/realized-feed/fetch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ market: 'kr', from_date: fromDate, to_date: toDate, source_account_key: kbRealizedState.sourceAccountKey })
        }),
        resolveMarket: () => 'kr',
        setLoading: setKbLoading, hideMessage: hideKbMessage, showMessage: showKbMessage,
        renderMetadata: (market, rowCount) => brokerUI.renderBrokerFetchMetadata('kbMeta', market, rowCount),
        renderFeedTable: renderKbFeedTable, updateSelectionUI: updateKbSelectionUI,
        emptyMessage: '해당 기간의 실현손익 내역이 없습니다.',
        errorText: kbSafeError, errorFallback: 'KB 실현손익 조회에 실패했습니다.',
      });
    }
    function kbNumber(value, digits = 0) { return window.WealthFormat.fixedNumberKoKr(value, digits); }
    function renderKbFeedTable() {
      return kbScreenController.renderFeedTable();
    }
    function updateKbSelectionUI() {
      return kbScreenController.updateSelectionUI();
    }
    async function openKbImportPreview() {
      return kbMappedImport.openPreview();
    }
    function renderKbPreviewModal(data) {
      return kbScreenController.renderPreviewModal(data);
    }
    function updateKbCommitButton() {
      return kbMappedImport.updateCommitButton();
    }
    function closeKbImportModal() {
      return kbMappedImport.closeModal();
    }
    async function commitKbImport() {
      return kbMappedImport.commit();
    }
    function initKbRealizedUI() {
      kbScreenController.bindImportEvents({
        confirmButtonId: 'btnKbConfirmCommit', closeButtonId: 'btnKbModalClose', cancelButtonId: 'btnKbModalCancel',
        setLoading: setKbLoading, openPreview: openKbImportPreview, closeModal: closeKbImportModal,
        updateCommitButton: updateKbCommitButton, commit: commitKbImport,
        sourceAccountChanged: key => {
          kbRealizedState.sourceAccountKey = key;
          kbRealizedState.mappedDestAccountId = brokerRealizedFeedController.mappedDestinationAccountId(kbRealizedState, key);
        },
      });
      document.getElementById('kbMarketSelect')?.addEventListener('change', () => {
        const val = document.getElementById('kbMarketSelect')?.value;
        if (val !== 'kr') {
          showKbMessage('KB 해외주식 실현손익은 현재 Open API에서 지원되지 않습니다.', 'warning');
        } else {
          hideKbMessage();
        }
      });
    }

    function switchRealizedBroker(broker) {
      brokerUI.showBrokerScreen(realizedBrokerScreens, broker);
    }

    function initNhRealizedUI() {
      nhScreenController.bindImportEvents({
        confirmButtonId: 'btnNhConfirmCommit', closeButtonId: 'btnNhModalClose', cancelButtonId: 'btnNhModalCancel',
        setLoading: setNhLoading, openPreview: openNhImportPreview, closeModal: closeNhImportModal,
        updateCommitButton: updateNhCommitButton, commit: commitNhImport,
        sourceAccountChanged: key => {
          const mappedId = brokerRealizedFeedController.mappedDestinationAccountId(nhRealizedState, key);
          nhRealizedState.sourceAccountKey = key;
          nhRealizedState.mappedDestAccountId = mappedId;
        },
      });
    }

    function initKisRealizedUI() {
      const fromInput = document.getElementById('kisFromDate');
      const toInput = document.getElementById('kisToDate');
      const marketSelect = document.getElementById('kisMarketSelect');




      document.getElementById('kisSelectAll')?.addEventListener('change', (e) => {
        const checked = e.target.checked;
        if (kisRealizedState.rows) {
          kisRealizedState.rows.forEach((_, idx) => {
            if (!kisRealizedState.importedIndices.has(idx)) {
              if (checked) {
                kisRealizedState.selectedIndices.add(idx);
              } else {
                kisRealizedState.selectedIndices.delete(idx);
              }
            }
          });
          renderKisFeedTable(kisRealizedState.rows, kisRealizedState.fetchedMarket, 'ok');
          updateKisSelectionUI();
        }
      });

      document.getElementById('kisDestinationAccount')?.addEventListener('change', (e) => {
        const key = kisRealizedState.sourceAccountKey;
        const val = e.target.value;
        if (key && val) {
          localStorage.setItem('kis_account_map_' + key, val);
          kisRealizedState.mappedDestAccountId = val;
        }
        updateKisSelectionUI();
      });
      document.getElementById('btnKisImportSelected')?.addEventListener('click', openKisImportPreview);

      document.getElementById('btnKisModalClose')?.addEventListener('click', closeKisImportModal);
      document.getElementById('btnKisModalCancel')?.addEventListener('click', closeKisImportModal);
      document.getElementById('kisIncludePossibleDuplicates')?.addEventListener('change', updateKisCommitButton);
      document.getElementById('btnKisConfirmCommit')?.addEventListener('click', commitKisImport);

      marketSelect?.addEventListener('change', checkKisFormStale);
      fromInput?.addEventListener('input', checkKisFormStale);
      toInput?.addEventListener('input', checkKisFormStale);

      initNhRealizedUI();
    }

    const realizedBrokerScreens = [
      { key: 'toss',
        state: tossWtsState, importBarId: 'tossWtsImportBar', destinationId: 'wtsDestinationAccount', importButtonId: 'btnWtsImportSelected', selectedCountId: 'wtsSelectedCountBadge',
        name: '토스증권', connection: 'WTS', markets: '국내·해외', notice: 'WTS 런타임·세션 및 계좌 범위를 확인하세요. 조회 자료는 가져오기 전 Wealth 자산·실현손익 합계에 반영되지 않습니다.',
        statusIds: ['tossWtsStatusText', 'tossWtsIncomeStatusText'], bannerId: 'tossWtsBannerText', tabId: 'btnTabBrokerToss', cardId: 'tossWtsCard', fromId: 'tossWtsFromDate', toId: 'tossWtsToDate',
        checkId: 'btnCheckTossWtsStatus', onCheck: checkTossWtsStatus, fetchId: 'btnFetchTossWtsFeed', onFetch: fetchTossWtsRealizedFeed },
      { key: 'kis',
        state: kisRealizedState, importBarId: 'kisImportBar', destinationId: 'kisDestinationAccount', importButtonId: 'btnKisImportSelected', selectedCountId: 'kisSelectedCountBadge',
        name: '한국투자증권', connection: 'OpenAPI', markets: '국내·해외', notice: 'API 키와 원본 계좌 설정을 확인하세요. 계좌 범위는 상태 확인 응답을 확인해야 합니다.',
        statusIds: ['kisStatusText'], bannerId: 'kisBannerText', tabId: 'btnTabBrokerKis', cardId: 'kisRealizedCard', fromId: 'kisFromDate', toId: 'kisToDate',
        checkId: 'btnCheckKisStatus', onCheck: checkKisStatus, fetchId: 'btnFetchKisFeed', onFetch: fetchKisRealizedFeed },
      { key: 'nh',
        state: nhRealizedState, importBarId: 'nhImportBar', destinationId: 'nhDestinationAccount', importButtonId: 'btnNhImportSelected', selectedCountId: 'nhSelectedCountBadge',
        name: 'NH투자증권', connection: 'OpenAPI', markets: '국내·해외', notice: '마스킹된 원본 계좌를 선택한 뒤 조회하세요.',
        statusIds: ['nhStatusText'], bannerId: 'nhBannerText', tabId: 'btnTabBrokerNh', cardId: 'nhRealizedCard', fromId: 'nhFromDate', toId: 'nhToDate',
        checkId: 'btnCheckNhStatus', onCheck: checkNhStatus, fetchId: 'btnFetchNhFeed', onFetch: fetchNhRealizedFeed },
      { key: 'kiwoom',
        state: kiwoomRealizedState, importBarId: 'kiwoomImportBar', destinationId: 'kiwoomDestinationAccount', importButtonId: 'btnKiwoomImportSelected', selectedCountId: 'kiwoomSelectedCountBadge',
        name: '키움증권', connection: 'OpenAPI', markets: '국내·해외', notice: '마스킹된 원본 계좌를 선택한 뒤 조회하세요.',
        statusIds: ['kiwoomStatusText'], bannerId: 'kiwoomBannerText', tabId: 'btnTabBrokerKiwoom', cardId: 'kiwoomRealizedCard', fromId: 'kiwoomFromDate', toId: 'kiwoomToDate',
        checkId: 'btnCheckKiwoomStatus', onCheck: checkKiwoomStatus, fetchId: 'btnFetchKiwoomFeed', onFetch: fetchKiwoomRealizedFeed },
      { key: 'kb',
        state: kbRealizedState, importBarId: 'kbImportBar', destinationId: 'kbDestinationAccount', importButtonId: 'btnKbImportSelected', selectedCountId: 'kbSelectedCountBadge',
        name: 'KB증권', connection: 'OpenAPI', markets: '국내', notice: '국내주식 실현손익만 지원합니다. 마스킹된 원본 계좌를 선택하세요.',
        statusIds: ['kbStatusText'], bannerId: 'kbBannerText', tabId: 'btnTabBrokerKb', cardId: 'kbRealizedCard', fromId: 'kbFromDate', toId: 'kbToDate',
        checkId: 'btnCheckKbStatus', onCheck: checkKbStatus, fetchId: 'btnFetchKbFeed', onFetch: fetchKbRealizedFeed },
    ];

    function initializeScreens() {
      brokerUI.initializeBrokerScreens(realizedBrokerScreens, switchRealizedBroker, [
        { fromId: 'tossWtsIncomeFromDate', toId: 'tossWtsIncomeToDate' },
      ]);
    }

    function bindEvents() {
      initTossWtsUI();
      initKisRealizedUI();
      initKiwoomRealizedUI();
      initKbRealizedUI();
    }

    const actions = Object.freeze({
      tossWtsState,
      tossWtsIncomeState,
      kisRealizedState,
      nhRealizedState,
      kiwoomRealizedState,
      kbRealizedState,
      showTossWtsMessage,
      hideTossWtsMessage,
      clearTossWtsFetchLoadingRow,
      updateTossWtsStatusUI,
      setTossWtsLoading,
      checkTossWtsFormStale,
      updateTossWtsMetaUI,
      checkTossWtsStatus,
      confirmTossWtsSession,
      fetchTossWtsRealizedFeed,
      updateWtsSelectionUI,
      populateWtsAccounts,
      openWtsImportPreview,
      renderWtsImportModal,
      updateWtsCommitButton,
      closeWtsImportModal,
      commitWtsImport,
      brokerRealizedDisplayRow,
      renderTossWtsFeedTable,
      showTossWtsIncomeMessage,
      setTossWtsIncomeLoading,
      tossWtsIncomeTypeLabel,
      tossWtsIncomeAmount,
      populateTossWtsIncomeAccounts,
      updateTossWtsIncomeMeta,
      renderTossWtsIncomeTable,
      updateTossWtsIncomeSelectionUI,
      selectedTossWtsIncomeItems,
      fetchTossWtsIncomeFeed,
      renderTossWtsIncomePreviewModal,
      openTossWtsIncomeImportPreview,
      updateTossWtsIncomeCommitButton,
      closeTossWtsIncomeImportModal,
      commitTossWtsIncomeImport,
      initTossWtsIncomeUI,
      initTossWtsUI,
      brokerRealizedDateKey,
      sortBrokerRealizedFeedRows,
      brokerPreviewStatusLabel,
      brokerImportPreference,
      brokerImportSelectedItem,
      syncBrokerRowImportOptions,
      getBrokerContextByOverlayId,
      scheduleBrokerPreviewRefresh,
      setModalRecalculating,
      brokerImportPnlPresentation,
      brokerImportNameSizeClass,
      renderBrokerImportPreviewDetails,
      maskAccountDisplayLabel,
      showKisMessage,
      hideKisMessage,
      updateKisStatusUI,
      setKisLoading,
      checkKisFormStale,
      updateKisMetaUI,
      checkKisStatus,
      fetchKisRealizedFeed,
      renderKisFeedTable,
      updateKisSelectionUI,
      realizedBrokerId,
      realizedDestinationAccounts,
      setRealizedDestinationEmptyMessage,
      populateKisDestinationAccounts,
      kisSelectedItems,
      openKisImportPreview,
      renderKisPreviewModal,
      updateKisCommitButton,
      closeKisImportModal,
      commitKisImport,
      refreshBrokerImportedResults,
      populateOpenApiDestinationAccounts,
      showNhMessage,
      hideNhMessage,
      setNhLoading,
      nhSafeError,
      nhSelectedItems,
      populateNhSourceAccounts,
      checkNhStatus,
      populateNhDestinationAccounts,
      fetchNhRealizedFeed,
      nhNumber,
      renderNhFeedTable,
      updateNhSelectionUI,
      openNhImportPreview,
      renderNhPreviewModal,
      updateNhCommitButton,
      closeNhImportModal,
      commitNhImport,
      showKiwoomMessage,
      hideKiwoomMessage,
      setKiwoomLoading,
      kiwoomSafeError,
      kiwoomSelectedItems,
      populateKiwoomSourceAccounts,
      checkKiwoomStatus,
      populateKiwoomDestinationAccounts,
      fetchKiwoomRealizedFeed,
      kiwoomNumber,
      renderKiwoomFeedTable,
      updateKiwoomSelectionUI,
      openKiwoomImportPreview,
      renderKiwoomPreviewModal,
      updateKiwoomCommitButton,
      closeKiwoomImportModal,
      commitKiwoomImport,
      initKiwoomRealizedUI,
      showKbMessage,
      hideKbMessage,
      setKbLoading,
      kbSafeError,
      kbSelectedItems,
      populateKbSourceAccounts,
      checkKbStatus,
      populateKbDestinationAccounts,
      fetchKbRealizedFeed,
      kbNumber,
      renderKbFeedTable,
      updateKbSelectionUI,
      openKbImportPreview,
      renderKbPreviewModal,
      updateKbCommitButton,
      closeKbImportModal,
      commitKbImport,
      initKbRealizedUI,
      switchRealizedBroker,
      initNhRealizedUI,
      initKisRealizedUI,
    });

    return Object.freeze({ actions, initializeScreens, bindEvents });
  }

  window.WealthBrokerImportFeatureController = Object.freeze({ create });
})();
