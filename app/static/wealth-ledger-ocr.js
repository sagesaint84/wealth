(() => {
  'use strict';
  let revision = 0, controller = null;
  const panel = document.getElementById('ledgerOcrPanel');
  if (!panel) return;
  const fileInput = document.getElementById('ledgerOcrFile');
  const button = document.getElementById('ledgerOcrAnalyze');
  const status = document.getElementById('ledgerOcrStatus');
  const review = document.getElementById('ledgerOcrReview');
  const type = document.getElementById('ledgerOcrType');
  function cancel() {
    revision++;
    controller?.abort(); controller = null;
    button.disabled = false; fileInput.disabled = false; type.disabled = false;
    review.replaceChildren(); status.textContent = ''; fileInput.value = '';
  }
  function text(tag, value) {
    const node = document.createElement(tag); node.textContent = value; return node;
  }
  function dateLabel(row) {
    if (row.transaction_date) return row.transaction_date;
    const parts = row.transaction_date_parts;
    return parts?.month && parts?.day ? `${parts.month}월 ${parts.day}일 · 연도 미확인` : '미확인';
  }
  function render(data) {
    review.replaceChildren();
    review.append(text('p', `거래 후보 ${data.rows.length}개 · 모든 행 검토 필요 · 저장 기능 없음`));
    for (const warning of data.warnings) review.append(text('p', warning));
    for (const row of data.rows) {
      const card = document.createElement('article'); card.className = 'ledger-ocr-row';
      card.append(text('h4', row.counterparty || row.merchant || '거래처 미확인'));
      const fields = [
        ['거래일', dateLabel(row)], ['시간', row.transaction_time || '미확인'],
        ['금액', row.amount === null ? '미확인' : `${row.direction === 'inflow' ? '+' : row.direction === 'outflow' ? '-' : ''}₩${BigInt(row.amount).toLocaleString('ko-KR')}`],
        ['방향', row.direction === 'inflow' ? '입금 후보' : row.direction === 'outflow' ? '출금 후보' : '미확인'],
        ['거래 후 잔액', row.balance_after === null ? '미확인' : `₩${BigInt(row.balance_after).toLocaleString('ko-KR')}`],
        ['종류 후보', ({card_approval_candidate:'카드 승인 후보',card_cancellation:'취소 후보',refund:'환불 후보',card_bill:'카드대금 후보',bank_transfer:'이체 후보'})[row.transaction_type_candidate] || '미확인'],
      ];
      const list = document.createElement('dl');
      for (const [label, value] of fields) { list.append(text('dt', label), text('dd', value)); }
      card.append(list, text('p', `페이지 ${row.source_location.page} · 행 ${row.source_location.line} · 검토 필요`));
      for (const warning of row.warnings) card.append(text('p', warning));
      review.append(card);
    }
  }
  button.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) { status.textContent = '파일을 선택해 주세요.'; return; }
    if (file.size > 10 * 1024 * 1024) { status.textContent = '10MiB 이하 파일을 선택해 주세요.'; return; }
    const active = ++revision;
    controller?.abort(); controller = new AbortController();
    button.disabled = true; fileInput.disabled = true; type.disabled = true;
    review.replaceChildren(); status.textContent = '오프라인 분석 중…';
    try {
      const response = await fetch(`/api/ledger/document-import/preview?document_type=${encodeURIComponent(type.value)}`, {
        method:'POST', credentials:'same-origin', headers:{'Content-Type':file.type || 'application/octet-stream'},
        body:file, signal:controller.signal,
      });
      const data = await response.json();
      if (active !== revision) return;
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '분석하지 못했습니다.');
      render(data); status.textContent = '읽기 전용 미리보기입니다. 금액·날짜·거래처를 원문과 확인해 주세요.';
    } catch (error) {
      if (active === revision && error.name !== 'AbortError') status.textContent = error.message || '분석하지 못했습니다.';
    } finally {
      if (active === revision) { button.disabled = false; fileInput.disabled = false; type.disabled = false; controller = null; }
    }
  });
  document.getElementById('ledgerExcelDialog')?.addEventListener('close', cancel);
})();
