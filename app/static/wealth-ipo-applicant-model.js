(() => {
  'use strict';

  function accountOptions(candidates) {
    return (candidates || []).map(item => ({
      id: item.account_id,
      label: [item.account_name, item.owner, item.account_type].filter(Boolean).join(' · ') || '등록 계좌',
    }));
  }

  function allocationSummary(allocation, hasDanglingLinks) {
    return {
      sold: allocation.sold_quantity,
      remaining: allocation.remaining_quantity,
      detail: hasDanglingLinks
        ? '연결된 실현손익 기록을 찾을 수 없음'
        : `실현손익 ${Number(allocation.realized_pnl_krw || 0).toLocaleString('ko-KR')}원`,
    };
  }

  function saleLinks(links) {
    return (links || []).map(link => ({
      recordId: link.pnl_record_id,
      quantity: link.matched_quantity,
      date: link.date || '',
      showDetail: !link.missing_pnl_record,
    }));
  }

  window.WealthIpoApplicantModel = Object.freeze({ accountOptions, allocationSummary, saleLinks });
})();
