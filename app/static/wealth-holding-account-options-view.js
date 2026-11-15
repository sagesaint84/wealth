(() => {
  'use strict';

  function render({ $, html, accounts, selectedId, validationMessage }) {
    const types = {general:'일반',isa:'ISA',pension_savings:'연금저축',pension:'연금저축',irp:'IRP'};
    const select = $('#holdingAccountSelect');
    if (select) {
      select.innerHTML = '<option value="">직접 입력 또는 등록 계좌 선택</option>' +
        accounts.map(a => `<option value="${html(a.id)}" data-broker="${html(a.broker)}" data-name="${html(a.name)}" data-owner="${html(a.owner || '모두')}">${html(a.owner || '모두')} · ${html(a.broker)} · ${html(a.name)} · ${html(types[a.account_type || 'general'])}</option>`).join('');
      select.setCustomValidity('');
      if (validationMessage) {
        // Never turn a missing edit link into an implicit new manual account.
        const option = new Option('기존 연결 계좌 확인 필요', selectedId);
        select.add(option);
        select.setCustomValidity(validationMessage);
      }
      select.value = selectedId;
    }
    const names = $('#holdingAccountDatalist');
    if (names) names.innerHTML = [...new Set(accounts.map(a => a.name).filter(Boolean))].map(name => `<option value="${html(name)}"></option>`).join('');
  }

  window.WealthHoldingAccountOptionsView = Object.freeze({ render });
})();
