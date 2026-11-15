(() => {
  'use strict';

  function open({ $, record, resolveAccountSelection, fillHoldingAccountOptions, populateStockDatalists, attachStockAutoFill }) {
    const form = $('#holdingForm');
    if (!form) return;
    form.reset();
    form.dataset.recordId = record ? String(record.id) : '';
    $('#holdingDialogTitle') && ($('#holdingDialogTitle').textContent = record ? '보유종목 수정' : '보유종목 직접 추가');
    const { linked, owner, selectedId } = resolveAccountSelection(record);
    fillHoldingAccountOptions(owner, selectedId);
    populateStockDatalists();
    attachStockAutoFill('holdingForm');
    form.broker.value = linked?.broker || record?.broker || '기타 증권사';
    form.account_name.value = linked?.name || record?.account_name || '내 주식 계좌';
    form.code.value = record?.code || '';
    form.name.value = record?.name || '';
    form.quantity.value = record?.quantity ?? '';
    form.avg_price.value = record?.avg_price ?? '';
    form.current_price.value = record?.current_price ?? '';
    form.currency.value = record?.currency || 'KRW';
    form.market.value = record?.market || '';
    if (form.sector) form.sector.value = record?.sector || '';
    if (form.owner) form.owner.value = owner;
    $('#holdingDialog')?.showModal();
  }

  window.WealthHoldingDialogController = { open };
})();
