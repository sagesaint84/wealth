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

  function renderMembers(ipoId, members, escapeHtml) {
      let memberCheckboxesHtml = '';
      members.forEach(({ member, checked: selected }) => {
        const checked = selected ? 'checked' : '';
        memberCheckboxesHtml += `
          <label class="ipo-member-checkbox-label">
            <input type="checkbox" class="ipo-member-chk" data-ipo="${escapeHtml(ipoId)}" data-member="${escapeHtml(member)}" ${checked} />
            <span>${escapeHtml(member)}</span>
          </label>`;
      });
    return memberCheckboxesHtml;
  }

  // Owners and authorization have already been resolved by the Controller.
  function renderApplicants(ipoId, owners, escapeHtml) {
      let applicantAccountsHtml = '';
      owners.forEach(member => {
        applicantAccountsHtml += `
          <div class="ipo-applicant-account" data-ipo="${escapeHtml(ipoId)}" data-owner="${escapeHtml(member)}">
            <span class="ipo-applicant-account-title">${escapeHtml(member)} 청약 계좌</span>
            <select class="ipo-applicant-broker" aria-label="${escapeHtml(member)} 증권사" disabled>
              <option>증권사 불러오는 중…</option>
            </select>
            <select class="ipo-applicant-account-select" aria-label="${escapeHtml(member)} Wealth 계좌" disabled>
              <option>계좌를 선택하세요</option>
            </select>
            <button type="button" class="button secondary compact ipo-applicant-account-save" disabled>계좌 연결</button>
            <span class="ipo-applicant-account-status" aria-live="polite"></span>
            <div class="ipo-allocation-control">
              <label>배정수량 <input class="ipo-allocation-quantity" type="number" min="0" step="1" disabled /></label>
              <button type="button" class="button secondary compact ipo-allocation-save" disabled>배정 저장</button>
              <span class="ipo-allocation-summary" aria-live="polite"></span>
              <select class="ipo-sale-candidate" aria-label="매도 실현손익 후보" disabled><option value="">매도 후보 없음</option></select>
              <input class="ipo-sale-match-quantity" type="number" min="1" step="1" aria-label="연결 매도 수량" disabled />
              <button type="button" class="button secondary compact ipo-sale-link-save" disabled>매도 연결</button>
              <div class="ipo-sale-links" aria-live="polite"></div>
            </div>
          </div>`;
      });
    return applicantAccountsHtml;
  }

  window.WealthIpoApplicantView = Object.freeze({ renderOptions, renderAccountStatus, renderAllocationSummary, renderSaleLinks, renderMembers, renderApplicants });
})();
