/* Actual payment history only; transfer-day metadata never executes here. */
(() => {
  const eligible = s => ['installment', 'free', 'housing'].includes(s.saving_type);
  const dialog = () => document.getElementById('savingContributionsDialog');
  const form = () => document.getElementById('savingContributionForm');
  const input = name => form().elements.namedItem(name);
  let saving = null, banks = [], requestId = '', editingId = '', busy = false;
  const money = value => `₩${number(Number(value) || 0, 0)}`;
  const notice = text => { document.getElementById('savingContributionNotice').textContent = text; };
  const compatible = b => (saving.owner || '모두') === '모두' || [saving.owner, '모두'].includes(b.owner || '모두');
  function card(s) {
    if (!eligible(s)) return '';
    const rows = s.contributions || [];
    const latest = rows.map(r => r.date).sort().at(-1);
    return `<div class="saving-contribution-card"><span>현재 누적 납입액 <strong>${money(s.current_paid_amount)}</strong></span><span>납입 이력 ${rows.length}건${latest ? ` · 최근 ${html(latest)}` : ''}</span><button type="button" class="button secondary compact" data-saving-contributions-id="${html(s.id)}" aria-label="${html(s.product_name)} 납입 내역">납입 내역</button></div>`;
  }
  function protectTotal(s) {
    const field = document.getElementById('savingCurrentPaid');
    const started = Boolean(s && Object.hasOwn(s, 'contribution_opening_amount'));
    field.readOnly = started;
    document.getElementById('savingCurrentPaidNotice').hidden = !started;
  }
  function resetForm() {
    form().reset();
    editingId = '';
    requestId = crypto.randomUUID();
    input('date').value = new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Seoul'}).format(new Date());
    input('withdraw_account_id').innerHTML = '<option value="">선택 안 함</option>' + banks.filter(compatible).map(b => `<option value="${html(b.id)}">${html(b.bank_name || '')} · ${html(b.account_name || '은행계좌')}</option>`).join('');
    document.getElementById('savingContributionSave').textContent = '납입 기록 저장';
    document.getElementById('savingContributionCancelEdit').hidden = true;
    window.WealthMoneyInput?.scan(form());
    window.WealthMoneyInput?.renderHint(input('amount'));
  }
  function render() {
    const rows = [...(saving.contributions || [])].sort((a,b) => b.date.localeCompare(a.date) || b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id));
    const started = Object.hasOwn(saving, 'contribution_opening_amount');
    const historyTotal = rows.reduce((sum,r) => sum + Number(r.amount), 0);
    const opening = started ? saving.contribution_opening_amount : saving.current_paid_amount;
    document.getElementById('savingContributionsTitle').textContent = `${saving.product_name} · 납입 내역`;
    document.getElementById('savingContributionSummary').innerHTML = `<div>기초 누적액<strong>${money(opening)}</strong></div><div>이력 합계<strong>${money(historyTotal)}</strong></div><div>현재 누적액<strong>${money(saving.current_paid_amount)}</strong></div>`;
    document.getElementById('savingContributionHistory').innerHTML = rows.length ? rows.map(r => `<article class="saving-contribution-row" data-contribution-id="${html(r.id)}"><div><time>${html(r.date)}</time> <span class="saving-contribution-source">${r.source === 'auto' ? '자동' : '수동'}</span></div><strong>${money(r.amount)}</strong><div class="saving-contribution-reference">${html(r.withdraw_account_name || '출금계좌 미지정')}</div><div class="saving-contribution-memo">${html(r.memo)}</div><div class="saving-contribution-actions">${r.source === 'manual' ? `<button type="button" class="button secondary compact" data-contribution-edit="${html(r.id)}" aria-label="${html(r.date)} ${money(r.amount)} 납입 수정">수정</button><button type="button" class="button secondary compact" data-contribution-delete="${html(r.id)}" aria-label="${html(r.date)} ${money(r.amount)} 납입 삭제">삭제</button>` : '<span>자동 납입은 직접 수정할 수 없습니다.</span>'}</div></article>`).join('') : '<p class="empty">아직 기록된 납입 내역이 없습니다.</p>';
  }
  async function refresh() {
    const data = await api('/api/savings');
    const current = data.savings_accounts.find(s => s.id === saving.id);
    if (!current || !eligible(current)) throw Error('납입 내역을 지원하는 상품을 찾을 수 없습니다.');
    saving = current;
    banks = data.bank_accounts || [];
    render();
  }
  async function open(id) {
    try {
      saving = {id};
      await refresh();
      resetForm(); notice('');
      dialog().showModal();
    } catch (error) { toast(error.message, true); }
  }
  function edit(id) {
    const row = saving.contributions.find(r => r.id === id);
    if (!row || row.source !== 'manual') return;
    resetForm(); editingId = id;
    for (const key of ['date', 'amount', 'memo']) input(key).value = row[key];
    if (row.withdraw_account_id && ![...input('withdraw_account_id').options].some(o => o.value === row.withdraw_account_id)) {
      const option = new Option(`${row.withdraw_account_name} (과거 계좌)`, row.withdraw_account_id);
      input('withdraw_account_id').add(option);
    }
    input('withdraw_account_id').value = row.withdraw_account_id;
    document.getElementById('savingContributionSave').textContent = '납입 기록 수정';
    document.getElementById('savingContributionCancelEdit').hidden = false;
    window.WealthMoneyInput?.renderHint(input('amount'));
    input('date').focus(); notice('');
  }
  async function save(event) {
    event.preventDefault();
    if (busy) return;
    const amount = Number(input('amount').value);
    if (!Number.isFinite(amount) || amount <= 0) { notice('납입금액은 0보다 큰 숫자여야 합니다.'); return; }
    busy = true;
    document.getElementById('savingContributionSave').disabled = true;
    try {
      const body = {id: editingId || requestId, date: input('date').value, amount, source:'manual', withdraw_account_id:input('withdraw_account_id').value, memo:input('memo').value};
      const path = `/api/savings-accounts/${encodeURIComponent(saving.id)}/contributions` + (editingId ? `/${encodeURIComponent(editingId)}` : '');
      await api(path, {method: editingId ? 'PUT' : 'POST', body:JSON.stringify(body)});
      await refresh(); resetForm(); notice('납입 기록이 저장되었습니다. 통장 잔액은 변경되지 않습니다.');
      await loadDashboard();
    } catch (error) { notice(error.message); }
    finally { busy = false; document.getElementById('savingContributionSave').disabled = false; }
  }
  async function remove(id) {
    if (busy || !confirm('이 납입 기록을 삭제하시겠습니까? 통장 잔액은 변경되지 않습니다.')) return;
    busy = true;
    try {
      await api(`/api/savings-accounts/${encodeURIComponent(saving.id)}/contributions/${encodeURIComponent(id)}`, {method:'DELETE'});
      await refresh(); resetForm(); notice('납입 기록이 삭제되었습니다.'); await loadDashboard();
    } catch (error) { notice(error.message); }
    finally { busy = false; }
  }
  document.addEventListener('click', event => {
    const opener = event.target.closest('[data-saving-contributions-id]');
    if (opener) open(opener.dataset.savingContributionsId);
    const editButton = event.target.closest('[data-contribution-edit]');
    if (editButton && !busy) edit(editButton.dataset.contributionEdit);
    const deleteButton = event.target.closest('[data-contribution-delete]');
    if (deleteButton) remove(deleteButton.dataset.contributionDelete);
  });
  document.addEventListener('DOMContentLoaded', () => {
    form().addEventListener('submit', save);
    document.getElementById('savingContributionCancelEdit').addEventListener('click', () => { resetForm(); notice(''); });
    document.getElementById('savingContributionsClose').addEventListener('click', () => dialog().close());
  });
  window.WealthSavingsContributions = {card, protectTotal, open};
})();
