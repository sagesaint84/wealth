(() => {
  'use strict';

  function prepareRow(item, feedIndex, preference, { brokerImportNameSizeClass, brokerImportPnlPresentation }) {
    const choice = item.wealth_import;
    const currentStockType = preference.stock_type || choice.stock_type || 'general';
    const isIpo = currentStockType === 'ipo';
    const currentFee = (preference.ipo_subscription_fee_krw !== undefined && preference.ipo_subscription_fee_krw !== null && preference.ipo_subscription_fee_krw !== '')
      ? preference.ipo_subscription_fee_krw
      : (choice.ipo_subscription_fee_krw ?? 2000);
    const candidate = item.candidate || {};
    const itemName = candidate.name || candidate.prdt_name || candidate.code || `선택 항목 ${item.index + 1}`;
    const itemNameSizeClass = brokerImportNameSizeClass(itemName);
    const itemDate = candidate.date || '';
    const providerPnl = brokerImportPnlPresentation(candidate, choice.provider_realized_pnl ?? candidate.pnl ?? 0);
    const finalPnl = brokerImportPnlPresentation(candidate, choice.final_wealth_pnl ?? choice.provider_realized_pnl ?? candidate.pnl ?? 0);

    return {
      feedIndex, itemIndex: item.index, itemName, itemNameSizeClass, itemDate, isIpo,
      currentFee, providerPnl, finalPnl, memo: choice.memo,
      feeText: isIpo ? Number(choice.ipo_subscription_fee_krw ?? currentFee ?? 0).toLocaleString('ko-KR') : '',
    };
  }

  window.WealthBrokerImportPreviewModel = Object.freeze({ prepareRow });
})();
