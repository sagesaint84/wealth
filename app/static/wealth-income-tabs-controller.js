(() => {
  'use strict';

  function applyTabSelection(tabs, key, selected) {
    tabs.forEach(button => {
      const active = button.dataset[key] === selected;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
  }

  function applySelection(document, currentIncomeTab, showPanels) {
    const workspace = document.querySelector?.('.wealth-workspace');
    if (workspace) workspace.dataset.incomeTab = currentIncomeTab;
    if (showPanels) {
      document.getElementById('calendarPanel')?.classList.toggle('wealth-income-hidden', currentIncomeTab !== 'calendar');
      document.getElementById('realizedPnlPanel')?.classList.toggle('wealth-income-hidden', currentIncomeTab !== 'pnl');
      document.getElementById('dividendPanel')?.classList.toggle('wealth-income-hidden', currentIncomeTab !== 'dividend');
      document.getElementById('ledgerSectionPanel')?.classList.toggle('wealth-income-hidden', currentIncomeTab !== 'ledger');
      document.getElementById('ipoPanel')?.classList.toggle('wealth-income-hidden', currentIncomeTab !== 'ipo');
    }
    applyTabSelection(document.querySelectorAll('#incomeTabs .income-tab'), 'income', currentIncomeTab);
  }

  function clearPending(document, tabs) {
    // Restore the original nodes, including their listeners and input state.
    const controls = document.getElementById('dividendPendingControls');
    const panel = document.getElementById('dividendPanel');
    const head = controls?.querySelector('.dividend-head');
    if (head && panel) panel.prepend(head);
    controls?.remove();
    tabs?.removeAttribute?.('aria-busy');
    document.getElementById('incomeChartStatus')?.remove();
  }

  function showPendingStatus(document, tabs) {
    tabs?.setAttribute?.('aria-busy', 'true');
    if (tabs?.insertAdjacentElement) {
      const status = document.createElement('p');
      status.id = 'incomeChartStatus'; status.className = 'muted'; status.setAttribute('role','status');
      status.textContent = '배당 차트를 준비 중입니다…'; tabs.insertAdjacentElement('afterend', status);
    }
    // Only the data panel waits for the first unified frame. Keep the existing
    // controls usable in the same workspace while that panel is being prepared.
  }

  function showPendingControls(document) {
    const panel = document.getElementById('dividendPanel');
    const head = panel?.querySelector('.dividend-head');
    if (head) {
      const controls = document.createElement('section');
      controls.id = 'dividendPendingControls';
      controls.className = 'panel dividend-panel';
      controls.setAttribute('aria-label', '배당금 입력 및 조회');
      panel.before(controls);
      controls.append(head);
    }
    panel?.classList.add('wealth-income-hidden');
    ['calendarPanel','realizedPnlPanel','ledgerSectionPanel','ipoPanel'].forEach(id =>
      document.getElementById(id)?.classList.add('wealth-income-hidden'));
  }

  window.WealthIncomeTabsController = Object.freeze({ applyTabSelection, applySelection, clearPending, showPendingStatus, showPendingControls });
})();
