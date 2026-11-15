(() => {
  'use strict';

  const resolutionMessage = (status) => ({
    MAPPED: '연결된 계좌',
    AUTO_SELECTED: '등록 계좌 자동선택',
    AMBIGUOUS_ACCOUNT: '계좌를 선택하세요',
    NO_ACCOUNT_CANDIDATE: '등록된 같은 증권사 계좌가 없습니다',
    BROKER_UNKNOWN: '증권사를 확인할 수 없습니다',
    MAPPING_CONFLICT: '기존 계좌 연결을 변경할 수 없습니다',
  }[status] || '계좌를 선택하세요');

  function renderAccountStatus(element, status) {
    element.textContent = resolutionMessage(status);
  }

  function renderAllocationSummary(element, summary) {
    element.textContent = summary
      ? `매도 ${summary.sold}주 · 잔여 ${summary.remaining}주 · ${summary.detail}`
      : '공모가 기준 배정수량을 입력하세요';
  }

  function renderSaleLinks(container, links, escapeHtml) {
    container.innerHTML = links.map(({ recordId, quantity, date, showDetail }) => {
      const id = escapeHtml(recordId);
      const matched = escapeHtml(quantity);
      const label = showDetail
        ? `${escapeHtml(date)} · ${matched}주 연결됨`
        : `${matched}주 · 연결된 실현손익 기록을 찾을 수 없음`;
      const detail = showDetail
        ? `<button type="button" class="button secondary compact ipo-pnl-detail" data-pnl-record-id="${id}">기록 상세</button>`
        : '';
      return `<div class="ipo-sale-link-row"><span>${label}</span>${detail}<button type="button" class="button secondary compact ipo-sale-unlink" data-pnl-record-id="${id}">연결 해제</button></div>`;
    }).join('');
  }

  function renderOptions(select, options, placeholder, escapeHtml) {
    const emptyOption = placeholder ? `<option value="">${escapeHtml(placeholder)}</option>` : '';
    select.innerHTML = emptyOption + options.map(({ id, label }) =>
      `<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`
    ).join('');
  }

  window.WealthIpoApplicantView = Object.freeze({ renderOptions, renderAccountStatus, renderAllocationSummary, renderSaleLinks });
})();
