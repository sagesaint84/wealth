(() => {
  'use strict';

  function detailHeader(title, clearLabel) {
    const button = clearLabel ? `<button type="button" class="button text compact" id="clearDivMonthBtn" style="font-size:11px;margin-left:auto;">✕ ${clearLabel}</button>` : '';
    return `<div class="div-detail-header">${title}${button}</div>`;
  }

  function emptyDetail(message) {
    return `<div class="empty" style="padding:16px;">${message}</div>`;
  }

  function render({ container, title, items, month, hasBucketDetail, currentDivSortField, currentDivSortOrder, html, money, number }) {
    const header = detailHeader(title, month ? (hasBucketDetail ? '선택 해제' : '전체 보기') : '');
    if (!items.length) {
      container.innerHTML = `
        ${header}
        ${emptyDetail(`등록된 실제 배당금 내역이 없습니다. 상단의 <strong>[➕ 배당 추가]</strong> 또는 <strong>[📂 가져오기]</strong> 버튼으로 입금 내역을 기록해보세요.`)}
      `;
      return;
    }

    const rowsHtml = items.map(item => {
      const isUsd = item.currency === 'USD';
      const origAmt = isUsd ? `$${number(item.amount, 2)}` : money(item.amount_krw);
      const fxInfo = isUsd ? `<br><small class="td-fx-info">환율 ${number(item.fx_rate, 1)}원</small>` : '';

      return `
        <tr>
          <td class="center td-date">${html(item.date)}</td>
          <td class="center"><span class="td-owner-badge">${html(item.owner || '모두')}</span></td>
          <td class="td-stock-col">
            <strong class="td-stock-name">${html(item.name || item.code)}</strong>
            <div class="td-stock-code">${html(item.code || '')}</div>
          </td>
          <td class="center"><span class="td-owner-badge">${item.income_kind === 'interest' ? '이자' : html(item.tax_estimate?.tax_type_label || '일반 배당')}</span></td>
          <td class="center"><span class="td-currency">${html(item.currency || 'KRW')}</span></td>
          <td class="num td-orig-amt">${origAmt}${fxInfo}</td>
          <td class="num td-krw-amt pnl-gain-val" style="font-size:13.5px;font-weight:700;">${money(item.amount_krw)}</td>
          <td class="td-memo">${html(item.memo || '-')}${item.source === 'ledger_interest' ? `<br><span class="td-owner-badge">가계부 연동</span><br>${html(item.account_name || '')}` : ''}</td>
          <td class="center" style="white-space:nowrap;">
            ${item.source === 'ledger_interest' ? '<span title="원본 가계부 거래에서 수정하거나 삭제해 주세요">가계부에서 수정</span>' : item.income_kind === 'interest' ? '<span title="이자 내역은 읽기 전용입니다">읽기 전용</span>' : `<div class="account-row-actions" style="justify-content:center;">
              <button class="account-action-button edit-actual-div-btn" data-id="${html(String(item.id))}" title="배당 수정" type="button">✎</button>
              <button class="account-action-button mini-delete-button delete-actual-div-btn" data-id="${html(String(item.id))}" title="배당 삭제" type="button">🗑️</button>
            </div>`}
          </td>
        </tr>
      `;
    }).join('');

    container.innerHTML = `
      ${header}
      <div class="detail-table-wrap">
        <table class="detail-table">
          <thead>
            <tr>
              <th class="center sortable-th ${currentDivSortField === 'date' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="date" style="width:95px;">입금일 <span class="sort-icon"></span></th>
              <th class="center sortable-th ${currentDivSortField === 'owner' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="owner" style="width:75px;">소유자 <span class="sort-icon"></span></th>
              <th class="sortable-th ${currentDivSortField === 'name' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="name">종목명 (코드) <span class="sort-icon"></span></th>
              <th class="center" style="width:55px;">유형</th>
              <th class="center" style="width:60px;">통화</th>
              <th class="sortable-th ${currentDivSortField === 'amount' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="amount" style="text-align:right;width:115px;">입금액 <span class="sort-icon"></span></th>
              <th class="sortable-th ${currentDivSortField === 'amount_krw' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="amount_krw" style="text-align:right;width:125px;">원화 환산금액 <span class="sort-icon"></span></th>
              <th>메모 / 계좌</th>
              <th class="center" style="width:65px;">관리</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderEstimated({ container, title, items, month, html, money, number }) {
    if (!items.length) {
      const emptyMsg = month ? `${month}월에 지급 예정인 배당금 내역이 없습니다.` : `배당(분배금)을 지급하는 보유 종목이 없습니다. (무배당/성장형 종목)`;
      container.innerHTML = `
        ${detailHeader(title)}
        ${emptyDetail(emptyMsg)}
      `;
      return;
    }

    const cardsHtml = items.map(item => {
      const isUsd = item.currency === 'USD';
      const origText = isUsd ? `$${number(item.payout_orig, 2)}` : money(item.payout_krw);
      const cycleText = item.months ? (item.months.length === 12 ? '월배당' : (item.months.length === 4 ? '분기배당' : `${item.months.join(', ')}월`)) : '';

      return `
        <div class="div-item-card">
          <div class="div-item-info">
            <strong>${html(item.name)}</strong>
            <span>${html(item.code)} · ${number(item.quantity, 2)}주 ${cycleText ? '· ' + cycleText : ''}</span>
          </div>
          <div class="div-item-val">
            <strong>${money(item.payout_krw)}</strong>
            <small>${isUsd ? origText + ' · ' : ''}수익률 ${number(item.div_yield, 2)}%</small>
          </div>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      ${detailHeader(title, month ? '전체 보기' : '')}
      <div class="div-detail-grid">
        ${cardsHtml}
      </div>
    `;
  }

  window.WealthActualDividendDetailView = { render, renderEstimated };
})();
