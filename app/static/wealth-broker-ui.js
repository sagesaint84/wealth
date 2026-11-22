(() => {
  "use strict";

  function create({ document, html }) {
    function mountImportControls(screen) {
      const card = document.getElementById(screen.cardId);
      const controls = card?.querySelector('.toss-wts-controls');
      const bar = document.getElementById(screen.importBarId);
      const destination = document.getElementById(screen.destinationId);
      const fetchButton = document.getElementById(screen.fetchId);
      const importButton = document.getElementById(screen.importButtonId);
      const badge = document.getElementById(screen.selectedCountId);
      if (!controls || !bar || !destination || !fetchButton || !importButton || !badge) return;
      const active = document.activeElement;
      const cursorStart = active?.selectionStart;
      const cursorEnd = active?.selectionEnd;
      const destinationWrap = destination.closest('.toss-wts-account-control, .toss-wts-dest-wrap');
      const fromWrap = document.getElementById(screen.fromId)?.closest('.toss-wts-control-item');
      const toWrap = document.getElementById(screen.toId)?.closest('.toss-wts-control-item');
      if (!destinationWrap || !fromWrap || !toWrap) return;
      const previousFetchWrap = fetchButton.parentElement;
      const oldActionWrappers = Array.from(bar.querySelectorAll('.toss-wts-import-bar-left, .toss-wts-import-bar-right'));
      destinationWrap.className = 'toss-wts-control-item toss-wts-account-control';
      // Reparent existing controls; values, IDs, disabled state and listeners survive.
      bar.append(fetchButton, importButton, badge);
      bar.className = 'toss-wts-control-action toss-wts-import-actions';
      bar.style.display = 'flex';
      badge.setAttribute('aria-live', 'polite');
      const removeIfEmpty = element => {
        if (element && element !== bar && element.children.length === 0 && !element.textContent.trim()) element.remove();
      };
      // The destination may still be inside an old action wrapper.
      controls.appendChild(destinationWrap);
      oldActionWrappers.forEach(removeIfEmpty);
      if (previousFetchWrap?.classList.contains('toss-wts-control-action')) removeIfEmpty(previousFetchWrap);
      const items = Array.from(controls.children).filter(element => element.classList.contains('toss-wts-control-item'));
      const sourceItems = items.filter(element => element.querySelector('select[id$="SourceAccount"]'));
      const conditions = items.filter(element => !sourceItems.includes(element) && element !== fromWrap && element !== toWrap && element !== destinationWrap);
      controls.append(...sourceItems, ...conditions, fromWrap, toWrap, destinationWrap, bar);
      if (active && controls.contains(active) && document.activeElement !== active) {
        active.focus({ preventScroll: true });
        if (cursorStart != null && cursorEnd != null) {
          try { active.setSelectionRange(cursorStart, cursorEnd); } catch (_) {}
        }
      }
    }

    function renderFeedImportOptions(body, { resolvePreference, isImported, rowName, onStockType, onFeeInput }) {
      body.querySelectorAll('.wts-import-type-cell').forEach(cell => {
        const index = Number(cell.dataset.index);
        const pref = resolvePreference(index);
        const disabled = isImported(index) ? ' disabled' : '';
        const name = rowName(index);
        cell.innerHTML = `<select class="broker-stock-type-select toss-wts-select" data-index="${index}" aria-label="${html(name)} 유형"${disabled}>` +
          `<option value="general"${pref.stock_type === 'ipo' ? '' : ' selected'}>일반주식</option>` +
          `<option value="ipo"${pref.stock_type === 'ipo' ? ' selected' : ''}>공모주</option></select>` +
          `<label class="broker-ipo-fee-wrap"${pref.stock_type === 'ipo' ? '' : ' hidden'}>공모청약비 ` +
          `<input class="broker-ipo-fee-input toss-wts-input" type="number" min="0" step="1" data-index="${index}" aria-label="${html(name)} 공모청약비" value="${html(String(pref.ipo_subscription_fee_krw ?? 2000))}"${disabled}>원</label>`;
        cell.querySelector('select').addEventListener('change', event => {
          onStockType(index, event.target.value);
          cell.querySelector('label').hidden = event.target.value !== 'ipo';
        });
        cell.querySelector('input').addEventListener('input', event => onFeeInput(index, event.target.value));
      });
    }

    const brokerScreens = new Map();
    const semanticLabels = { unchecked: '상태 미확인', checking: '확인 중', ready: '조회 가능',
      action_required: '추가 확인 필요', error: '상태 확인 실패' };

    function renderBrokerState(key, semantic, detail = '') {
      const screen = brokerScreens.get(key);
      if (!screen) return;
      const state = Object.hasOwn(semanticLabels, semantic) ? semantic : 'unchecked';
      screen.statusIds.forEach(id => {
        const element = document.getElementById(id);
        if (!element) return;
        element.dataset.state = state;
        element.setAttribute('role', 'status');
        element.setAttribute('aria-live', 'polite');
        renderStatus(id, semanticLabels[state] + (detail ? ` · ${detail}` : ''),
          state === 'ready' ? 'ready' : state === 'error' ? 'error' : '');
      });
      const banner = document.getElementById(screen.bannerId);
      if (banner) banner.textContent = `${screen.name}에서 제공한 실현손익 조회 자료입니다. 조회 결과는 자동 저장되지 않습니다. 선택한 항목은 미리보기와 명시적인 가져오기 승인으로 반영합니다. 지원 시장: ${screen.markets}. ${screen.notice}` + (detail ? ` 현재 상태: ${detail}` : '');
    }

    const realizedColumns = ['선택', '거래일자', '종목명(코드)', '시장/통화', '거래/가져오기 유형', '매도수량', '매수금액', '매도금액', '실현손익', '수익률', '수수료/제세금'];

    // Reflect rendered row controls only; selection data remains in Controllers.
    function syncFeedSelection(body) {
      const all = body.closest('table')?.querySelector('thead input[type="checkbox"]');
      if (!all) return;
      const inputs = Array.from(body.querySelectorAll('input[type="checkbox"][data-index]'));
      const checked = inputs.filter(input => input.checked).length;
      all.checked = inputs.length > 0 && checked === inputs.length;
      all.indeterminate = checked > 0 && checked < inputs.length;
    }

    function renderRealizedTable({ body, rows, status, emptyMessage, selection, checkboxClass, adapt, toss }) {
      const table = body.closest('table');
      const head = table?.querySelector('thead');
      if (head) {
        const selectAll = head.querySelector('input[type="checkbox"]');
        const legacyExtra = head.querySelector('#kisColFxOrExpense, #nhExpenseColumn, #kiwoomExpenseColumn, #kbExpenseColumn');
        const extraId = legacyExtra?.id;
        head.innerHTML = '<tr>' + realizedColumns.map((label, index) => `<th${index >= 5 ? ' class="num"' : ''}>${html(label)}</th>`).join('') + '</tr>';
        if (selectAll) head.querySelector('th').replaceChildren(selectAll);
        if (extraId) head.querySelector('th:last-child').id = extraId;
      }
      if (status === 'error' || status === 'loading' || !rows.length) {
        body.innerHTML = status === 'loading' ? brokerTableLoadingRow(11, '조회 중입니다...')
          : brokerTableEmptyRow(11, status === 'error' ? '조회에 실패했습니다.' : emptyMessage);
        syncFeedSelection(body);
        return;
      }
      body.innerHTML = rows.map((row, index) => {
        const display = adapt(row);
        const selected = selection.selectedIndices.has(index);
        const imported = selection.importedIndices.has(index);
        const check = feedSelectionCell({ index, selected, imported, checkboxClass,
          badgeClass: 'toss-wts-imported-badge', importedText: '완료' });
        const cells = [check, html(display.date), `<strong>${html(display.name)}</strong><br><code>${html(display.code)}</code>`,
          html(display.context), html(display.type), html(display.quantity), html(display.buy), html(display.sell),
          html(display.pnl), html(display.rate), html(display.expenses)];
        return `<tr class="${selected ? 'selected' : ''} ${imported ? 'imported-row' : ''}">` + cells.map((cell, column) => {
          const typeCell = column === 4;
          const className = typeCell ? 'wts-import-type-cell' : (column >= 5 ? 'num' : '');
          return `<td class="${className}${column === 8 ? ' ' + display.tone : ''}"${typeCell ? ` data-index="${index}"` : ''}>${cell}</td>`;
        }).join('') + '</tr>';
      }).join('');
      syncFeedSelection(body);
    }

    function feedSelectionCell({ index, selected, imported, checkboxClass, badgeClass,
                                 importedText, importedTitle = '' }) {
      if (imported) {
        const title = importedTitle ? ` title="${html(importedTitle)}"` : '';
        return `<span class="${html(badgeClass)}"${title}>${html(importedText)}</span>`;
      }
      return `<input type="checkbox" class="${html(checkboxClass)}" data-index="${html(String(index))}" ${selected ? 'checked' : ''}>`;
    }

    function bindFeedSelection(body, selector, onChange) {
      body.querySelectorAll(selector).forEach(input => input.addEventListener('change', event => {
        onChange(event);
        syncFeedSelection(body);
      }));
    }

    function initializeBrokerScreens(screens, onSwitch, extraDateFields = []) {
      const range = window.WealthDateHelper.getKstDateRange(30);
      [...screens, ...extraDateFields].forEach(screen => {
        applyDefaultDateRange(document.getElementById(screen.fromId), document.getElementById(screen.toId), range);
      });
      screens.forEach(screen => {
        brokerScreens.set(screen.key, screen);
        mountImportControls(screen);
        const card = document.getElementById(screen.cardId);
        const badge = card?.querySelector('.toss-wts-badge');
        if (badge) badge.textContent = `${screen.connection} · 읽기 전용`;
        renderBrokerState(screen.key, 'unchecked');
        const body = document.getElementById(screen.cardId)?.querySelector('.toss-wts-table tbody');
        if (body) renderRealizedTable({ body, rows: [], emptyMessage: body.textContent.trim() });
        document.getElementById(screen.tabId)?.addEventListener('click', () => onSwitch(screen.key));
        document.getElementById(screen.checkId)?.addEventListener('click', screen.onCheck);
        document.getElementById(screen.fetchId)?.addEventListener('click', screen.onFetch);
      });
    }

    function showBrokerScreen(screens, key) {
      const active = screens.find(screen => screen.key === key) || screens[0];
      screens.forEach(screen => {
        document.getElementById(screen.tabId)?.classList.remove('active');
        const card = document.getElementById(screen.cardId);
        if (card) card.style.display = 'none';
      });
      const card = document.getElementById(active.cardId);
      if (card) card.style.display = 'block';
      document.getElementById(active.tabId)?.classList.add('active');
    }

    function renderFeedMetadata(element, markup) {
      if (markup === null) {
        element.style.display = 'none';
        element.innerHTML = '';
        return;
      }
      element.innerHTML = markup;
      element.style.display = 'flex';
    }

    function renderStaleHint(id, visible, message) {
      const element = document.getElementById(id);
      if (!element) return;
      if (visible) {
        renderStatus(id, message);
        element.style.display = 'block';
      } else {
        element.style.display = 'none';
      }
    }

    function renderStatus(id, text, stateClass) {
      const element = document.getElementById(id);
      if (!element) return;
      if (stateClass !== undefined) element.className = `toss-wts-status-text ${stateClass}`.trim();
      element.textContent = text;
    }

    function hideBrokerMessage(id) {
      const element = document.getElementById(id);
      if (!element) return;
      element.style.display = 'none';
      element.textContent = '';
    }

    function renderDestinationAccount(id, { text, accountText, ownerText }) {
      const element = document.getElementById(id);
      if (!element) return;
      if (accountText === undefined) {
        element.textContent = text;
        return;
      }
      const emphasis = document.createElement('strong');
      emphasis.textContent = accountText;
      element.replaceChildren(document.createTextNode('귀속 계좌: '), emphasis,
                              document.createTextNode(` (${ownerText})`));
    }

    function renderPreviewCounts(counts, ids, formatCount = value => String(value || 0)) {
      ['new', 'already_imported', 'possible_duplicate', 'invalid'].forEach(key => {
        const element = ids[key] ? document.getElementById(ids[key]) : null;
        if (element) element.textContent = formatCount(counts[key]);
      });
    }

    function renderPreviewSummary({ counts, countIds, formatCount, destinationId, destination,
                                    accountFirst = false, duplicate }) {
      if (accountFirst) renderDestinationAccount(destinationId, destination);
      renderPreviewCounts(counts, countIds, formatCount);
      if (!accountFirst) renderDestinationAccount(destinationId, destination);
      const wrap = document.getElementById(duplicate.wrapId);
      const checkbox = document.getElementById(duplicate.checkboxId);
      if (duplicate.presence === 'both' && (!wrap || !checkbox)) return;
      if (duplicate.presence === 'wrap' && !wrap) return;
      if (duplicate.resetFirst && checkbox) checkbox.checked = false;
      if (wrap) wrap.style.display = duplicate.visible ? 'block' : 'none';
      if (!duplicate.resetFirst && checkbox) checkbox.checked = false;
    }

    function setModalVisible(overlayId, visible) {
      const overlay = document.getElementById(overlayId);
      if (overlay) overlay.style.display = visible ? 'flex' : 'none';
    }

    function setButtonDisabled(id, disabled) {
      const button = document.getElementById(id);
      if (button) button.disabled = disabled;
    }

    function setAccountFeedButtonsDisabled(statusButtonId, fetchButtonId, loading, sourceAccountKey) {
      setButtonDisabled(statusButtonId, loading);
      setButtonDisabled(fetchButtonId, loading || !sourceAccountKey);
    }

    function populateBrokerSourceAccountSelect(select, accounts, fallbackLabel) {
      const current = select.value;
      select.innerHTML = '<option value="">원본 계좌 선택...</option>';
      accounts.forEach(account => {
        appendSelectOption(select, account.source_account_key, account.source_account_label || fallbackLabel);
      });
      select.disabled = accounts.length === 0;
      if (current && Array.from(select.options).some(option => option.value === current)) {
        select.value = current;
      } else if (accounts.length === 1) {
        select.value = accounts[0].source_account_key;
      }
      return select.value;
    }

    function populateBrokerDestinationAccountSelect(select, accounts, preferred, maskAccountDisplayLabel) {
      const current = select.value;
      select.innerHTML = '<option value="">귀속 계좌 선택...</option>';
      accounts.forEach(account => {
        const id = String(account.id || '');
        const name = maskAccountDisplayLabel(account.account_name || account.name || `계좌 ${id}`);
        const owner = account.owner ? ` (${account.owner})` : '';
        appendSelectOption(select, id, `[${account.broker || 'Wealth'}] ${name}${owner}`);
      });
      if (select.options.length === 1) {
        select.options[0].textContent = '해당 증권사 계좌를 먼저 등록하세요.';
      }
      const hasOption = value => Array.from(select.options).some(option => option.value === value);
      if (current && hasOption(current)) {
        select.value = current;
      } else if (preferred && hasOption(String(preferred))) {
        select.value = String(preferred);
      }
    }

    function appendSelectOption(select, value, label) {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    }

    function renderSelectAllState(id, checked, disabled) {
      const checkbox = document.getElementById(id);
      if (!checkbox) return;
      checkbox.checked = checked;
      if (disabled !== undefined) setButtonDisabled(id, disabled);
    }

    function renderBrokerImportSelectionState(state, { badgeId, buttonId, destinationSelectId }) {
      const count = state.selectedIndices.size;
      renderSelectionState({
        badgeId,
        count,
        buttonId,
        disabled: count === 0 || !document.getElementById(destinationSelectId)?.value || state.loading || state.importing,
      });
    }

    function renderSelectionState({ badgeId, count, buttonId, disabled, barId, barDisplay }) {
      const badge = document.getElementById(badgeId);
      if (badge) badge.textContent = `선택 ${count}건`;
      if (barId !== undefined) {
        const bar = document.getElementById(barId);
        if (bar) bar.style.display = barDisplay;
      }
      setButtonDisabled(buttonId, disabled);
    }

    // Date arithmetic belongs to WealthDateHelper; this owner only initializes
    // empty UI fields. Never synchronize or overwrite a user's chosen range.
    function applyDefaultDateRange(fromInput, toInput, range = window.WealthDateHelper.getKstDateRange(30)) {
      if (fromInput && !fromInput.value) fromInput.value = range.fromDate;
      if (toInput && !toInput.value) toInput.value = range.toDate;
    }

    function brokerErrorText(error, fallback) {
      return error?.detail?.message || error?.detail?.code || fallback;
    }

    function showBrokerMessage(id, message, type) {
      const el = document.getElementById(id);
      if (!el) return;
      el.setAttribute('role', type === 'error' ? 'alert' : 'status');
      el.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');
      el.className = `toss-wts-message ${type}`;
      el.textContent = message;
      el.style.display = 'block';
    }

    function brokerTableEmptyRow(colspan, message) {
      return `<tr><td colspan="${colspan}" class="toss-wts-empty">${html(message)}</td></tr>`;
    }

    function brokerTableLoadingRow(colspan, message) {
      return `<tr><td colspan="${colspan}" class="toss-wts-loading">⏳ ${html(message)}</td></tr>`;
    }

    function brokerImportPreviewRow({
      feedIndex, itemIndex, itemName, itemNameSizeClass, itemDate, isIpo,
      currentFee, providerPnl, finalPnl, memo, feeText,
    }) {
      return `<div class="broker-import-modal-row" data-feed-index="${feedIndex}" data-item-index="${itemIndex}" style="margin-top:8px;padding:8px;border:1px solid var(--border);border-radius:8px;">` +
        `<div class="broker-import-item-header">` +
          `<div class="broker-import-item-title">` +
            `<strong class="broker-import-item-name ${itemNameSizeClass}">${html(itemName)}</strong>` +
            `${itemDate ? `<span class="muted" style="font-size:12px;margin-left:6px;">(${html(itemDate)})</span>` : ''}` +
          `</div>` +
          `<div class="broker-import-item-controls">` +
            `<label style="font-size:12px;">유형: ` +
              `<select class="modal-broker-stock-type toss-wts-select" data-feed-index="${feedIndex}" data-item-index="${itemIndex}" style="padding:2px 6px;font-size:12px;">` +
                `<option value="general" ${isIpo ? '' : 'selected'}>일반주식</option>` +
                `<option value="ipo" ${isIpo ? 'selected' : ''}>공모주</option>` +
              `</select>` +
            `</label>` +
            `<label class="modal-broker-fee-wrap" data-item-index="${itemIndex}" style="font-size:12px;${isIpo ? 'display:inline-flex;align-items:center;gap:4px;' : 'display:none;'}">공모청약비: ` +
              `<input class="modal-broker-ipo-fee toss-wts-input" data-feed-index="${feedIndex}" data-item-index="${itemIndex}" type="number" min="0" step="1" value="${html(String(currentFee))}" style="width:75px;padding:2px 6px;font-size:12px;" required> 원` +
            `</label>` +
          `</div>` +
        `</div>` +
        `<div class="modal-broker-effect" style="margin-top:6px;font-size:12px;color:var(--text-muted);">` +
          (isIpo ? (
            `유형: <strong>공모주</strong> · 공모청약비 ${html(feeText)}원 · ` +
            `제공사 손익 <strong class="broker-import-pnl ${providerPnl.toneClass}">${html(providerPnl.text)}</strong> · 최종 Wealth 손익 <strong class="broker-import-pnl ${finalPnl.toneClass}">${html(finalPnl.text)}</strong>` +
            `${memo ? `<br><span class="muted">메모: ${html(memo)}</span>` : ''}`
          ) : (
            `유형: <strong>일반주식</strong> · 최종 Wealth 손익 <strong class="broker-import-pnl ${finalPnl.toneClass}">${html(finalPnl.text)}</strong>` +
            `${memo ? `<br><span class="muted">메모: ${html(memo)}</span>` : ''}`
          )) +
        `</div>` +
      `</div>`;
    }

    return Object.freeze({ renderFeedImportOptions, renderBrokerState, renderRealizedTable, feedSelectionCell, bindFeedSelection, initializeBrokerScreens, showBrokerScreen, renderFeedMetadata, renderStaleHint, renderStatus, hideBrokerMessage, renderPreviewSummary, renderDestinationAccount, renderPreviewCounts, setModalVisible, appendSelectOption, populateBrokerSourceAccountSelect, populateBrokerDestinationAccountSelect, renderSelectAllState, renderSelectionState, renderBrokerImportSelectionState, setButtonDisabled, setAccountFeedButtonsDisabled, applyDefaultDateRange, brokerImportPreviewRow, brokerErrorText, showBrokerMessage, brokerTableEmptyRow, brokerTableLoadingRow });
  }
  window.WealthBrokerUI = Object.freeze({ create });
})();
