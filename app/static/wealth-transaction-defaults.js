/* User-scoped explicit preferences; never saved as a side effect of a transaction/import. */
(() => {
  const form = () => document.getElementById('ledgerTxForm');
  const field = name => form()?.querySelector(`[name='${name}']`);
  let defaults = {};
  let importDefaults = {};
  function notice(message) { const el = document.getElementById('ledgerDefaultNotice'); if (el) el.textContent = message; }
  function selectExisting(name, id) {
    const select = field(name);
    if (!select) return false;
    const valid = !id || [...select.options].some(option => option.value === id && !option.disabled);
    select.value = valid ? id || '' : '';
    return valid;
  }
  async function load() {
    defaults = {};
    try { defaults = (await api('/api/ledger/preferences')).transaction_defaults || {}; }
    catch (_) { notice('기본값을 불러오지 못했습니다. 카드/계좌를 직접 선택해 주세요.'); }
  }
  function apply() {
    if (!form() || form().dataset.txId) return;
    const owner = field('owner').value;
    const type = field('type').value;
    const pref = defaults[owner] || {};
    let valid = true;
    if (type === 'expense') {
      field('pay_method_type').value = ['credit_card', 'bank_account', 'cash'].includes(pref.expense_payment_method) ? pref.expense_payment_method : 'credit_card';
      onLedgerPayMethodTypeChanged();
      const cardValid = selectExisting('card_id', pref.expense_card_id);
      const accountValid = selectExisting('account_id', pref.expense_account_id);
      valid = cardValid && accountValid;
    } else {
      selectExisting('card_id', '');
      valid = selectExisting('account_id', pref[type === 'income' ? 'income_account_id' : 'transfer_account_id']);
    }
    notice(valid ? '' : '저장된 기본값을 사용할 수 없습니다. 다시 지정해 주세요.');
    updateLedgerBalancePreview();
    eligibility();
  }
  async function save(clear = false) {
    const owner = field('owner').value;
    const type = field('type').value;
    const pref = {...(defaults[owner] || {})};
    if (type === 'expense') {
      if (clear) ['expense_payment_method', 'expense_card_id', 'expense_account_id'].forEach(key => delete pref[key]);
      else Object.assign(pref, {expense_payment_method: field('pay_method_type').value,
        expense_card_id: field('card_id').value, expense_account_id: field('account_id').value});
    } else {
      const key = type === 'income' ? 'income_account_id' : 'transfer_account_id';
      if (clear) delete pref[key]; else pref[key] = field('account_id').value;
    }
    try {
      defaults = (await api('/api/ledger/preferences/transaction-defaults', {method: 'PUT',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({owner, defaults: pref})})).transaction_defaults;
      notice(clear ? '이 거래 유형의 기본값을 해제했습니다.' : '현재 선택을 기본값으로 지정했습니다.');
    } catch (error) { notice(error.message); }
  }
  function eligibility() {
    const box = document.getElementById('ledgerInterestLinkBox');
    const input = document.getElementById('ledgerInterestLink');
    if (!box || !input || !form()) return;
    const income = field('type').value === 'income' && field('category').value === '배당/금융수익';
    box.hidden = !income;
    const owner = field('owner').value;
    const banks = (rawDashboard || dashboard || {}).bank_accounts || [];
    const bank = banks.find(a => a.id === field('account_id').value &&
      (owner === '모두' || [owner, '모두'].includes(a.owner || '모두')) && (a.currency || 'KRW') === 'KRW');
    input.disabled = !income || !bank;
    if (input.disabled) input.checked = false;
    document.getElementById('ledgerInterestLinkHint').textContent = bank ? '잔액은 가계부에서 한 번만 반영됩니다.' : 'KRW 은행계좌를 먼저 선택해 주세요.';
  }
  function restoreInterest(tx) {
    document.getElementById('ledgerInterestLink').checked = Boolean(tx?.mirror_to_dividend_interest);
    eligibility();
  }
  async function loadImports() {
    importDefaults = {};
    try { importDefaults = (await api('/api/import-destination-defaults')).defaults || {}; }
    catch (_) { /* Failed preference load must never invent a destination. */ }
  }
  function importSelection(select, workflow, current, accounts) {
    const eligible = accounts.filter(a => currentOwner === '모두' || !currentOwner || [currentOwner, '모두'].includes(a.owner || '모두'));
    const preferred = current || importDefaults[workflow] || '';
    select.value = eligible.some(a => String(a.id) === preferred) ? preferred : '';
    const message = document.getElementById(`${select.id}DefaultNotice`);
    if (message) message.textContent = preferred && !select.value ? '저장된 기본값을 사용할 수 없습니다. 직접 선택해 주세요.' : (select.value === importDefaults[workflow] && select.value ? '기본 목적 계좌' : '');
  }
  async function restoreImportSelection(select, workflow, accounts) {
    await loadImports();
    importSelection(select, workflow, select.value, accounts);
  }
  async function saveImport(workflow, selectId, clear) {
    const select = document.getElementById(selectId);
    const message = document.getElementById(`${selectId}DefaultNotice`);
    if (!clear && !select.value) { message.textContent = '계좌를 먼저 선택해 주세요.'; return; }
    try {
      importDefaults = (await api('/api/import-destination-defaults', {method: 'PUT', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({workflow, account_id: clear ? '' : select.value, owner: currentOwner || '모두'})})).defaults;
      message.textContent = clear ? '기본 목적 계좌를 해제했습니다.' : '이 계좌를 기본값으로 기억합니다.';
    } catch (error) { message.textContent = error.message; }
  }
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('ledgerDefaultSave')?.addEventListener('click', () => save());
    document.getElementById('ledgerDefaultClear')?.addEventListener('click', () => save(true));
    form()?.addEventListener('change', event => {
      if (['type', 'owner'].includes(event.target.name)) apply();
      eligibility();
    });
    [['toss_wts_realized', 'wtsDestinationAccount'], ['toss_wts_income', 'wtsIncomeDestinationAccount']].forEach(([workflow, id]) => {
      document.getElementById(`${id}Remember`)?.addEventListener('click', () => saveImport(workflow, id, false));
      document.getElementById(`${id}Clear`)?.addEventListener('click', () => saveImport(workflow, id, true));
    });
  });
  window.WealthTransactionDefaults = {load, apply, eligibility, restoreInterest, loadImports, importSelection, restoreImportSelection};
})();
