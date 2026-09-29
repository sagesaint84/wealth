(() => {
  'use strict';

  const PDFJS_URL = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs';
  const PDFJS_WORKER_URL = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs';
  const PDF_MAX_BYTES = 10 * 1024 * 1024;
  const HEADER_TEXTS = new Set([
    '금융기관명 / 계좌번호',
    '지점명 / 상품정보',
    '개설일 / 최종거래일',
    '상태 / 잔액',
  ]);
  const REVIEW_BROKER_PRODUCT = /(퇴직연금|선물|옵션|금현물|금융상품)/i;
  const REVIEW_BANK_PRODUCT = /(주택청약|청약|적금|정기예금|외화)/i;

  let pdfjsPromise = null;
  let previewState = null;

  function text(value) {
    return String(value ?? '').normalize('NFKC').replace(/\s+/g, ' ').trim();
  }

  function digits(value) {
    return String(value ?? '').replace(/\D/g, '');
  }

  function canonicalInstitution(value) {
    return text(value)
      .toLowerCase()
      .replace(/[\s._()\-]/g, '')
      .replace(/투자증권$/u, '')
      .replace(/증권$/u, '')
      .replace(/은행$/u, '');
  }

  function maskAccountNo(value) {
    const normalized = digits(value);
    if (!normalized) return '번호 확인 필요';
    const tail = normalized.slice(-4);
    return `${'•'.repeat(Math.max(4, Math.min(8, normalized.length - 4)))}${tail}`;
  }

  function money(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? `₩${Math.round(number).toLocaleString('ko-KR')}` : '-';
  }

  function isRowAnchor(item) {
    const value = text(item?.str);
    const x = Number(item?.transform?.[4]);
    return /^\d{1,2}$/.test(value) && Number.isFinite(x) && x > 10 && x < 75;
  }

  function filteredToken(value) {
    const normalized = text(value);
    if (!normalized) return '';
    if (HEADER_TEXTS.has(normalized)) return '';
    if (normalized.startsWith('상기 계좌 중 일부는')) return '';
    return normalized;
  }

  function rowsFromPdfPages(pages) {
    const rows = [];
    let current = null;
    let reportDate = '';
    const allText = [];

    for (const pageItems of pages || []) {
      for (const item of pageItems || []) {
        const token = filteredToken(item?.str);
        if (!token) continue;
        allText.push(token);
        const dateMatch = token.match(/조회기준일\s*:\s*(\d{4}-\d{2}-\d{2})/);
        if (dateMatch) reportDate = dateMatch[1];

        if (isRowAnchor(item)) {
          if (current) rows.push(current);
          current = { source_row: Number(token), tokens: [] };
          continue;
        }
        if (current) current.tokens.push(token);
      }
    }
    if (current) rows.push(current);

    if (!reportDate) {
      const match = allText.join(' ').match(/조회기준일\s*:\s*(\d{4}-\d{2}-\d{2})/);
      reportDate = match ? match[1] : '';
    }

    const parsed = rows.map(parseRowTokens).filter(Boolean);
    return { report_date: reportDate, rows: parsed };
  }

  function parseRowTokens(raw) {
    const tokens = Array.isArray(raw?.tokens) ? raw.tokens.map(text).filter(Boolean) : [];
    if (!tokens.length) return null;

    let accountIndex = -1;
    let institution = '';
    let accountNo = '';
    for (let index = 0; index < tokens.length; index += 1) {
      const token = tokens[index];
      if (/^\d{7,}$/.test(token)) {
        accountIndex = index;
        accountNo = token;
        institution = tokens.slice(0, index).join(' ');
        break;
      }
      const combined = token.match(/^(.*?)(\d{7,})$/u);
      if (combined && combined[1]) {
        accountIndex = index;
        institution = combined[1].trim();
        accountNo = combined[2];
        break;
      }
    }
    if (accountIndex < 0 || !institution || !accountNo) return null;

    const dateIndexes = [];
    const dates = [];
    tokens.forEach((token, index) => {
      if (/^\d{4}-\d{2}-\d{2}$/.test(token)) {
        dateIndexes.push(index);
        dates.push(token);
      }
    });
    const firstDateIndex = dateIndexes.length ? dateIndexes[0] : tokens.length;
    const middle = tokens.slice(accountIndex + 1, firstDateIndex);
    const slashIndex = middle.indexOf('/');
    let branch = '';
    let product = '';
    if (slashIndex >= 0) {
      branch = middle.slice(0, slashIndex).join(' ').trim();
      product = middle.slice(slashIndex + 1).join(' ').trim();
    } else {
      product = middle.join(' ').trim();
    }

    const status = tokens.find((token) => token === '활동성' || token === '비활동성') || '';
    const joined = tokens.join(' ');
    const balanceMatches = [...joined.matchAll(/([0-9][0-9,]*)\s*원/g)];
    const lastBalance = balanceMatches.length ? balanceMatches[balanceMatches.length - 1][1] : '0';
    const balanceKrw = Number(lastBalance.replace(/,/g, '')) || 0;

    return {
      source_row: Number(raw.source_row || 0),
      institution: text(institution),
      account_no: digits(accountNo),
      branch: text(branch),
      product: text(product),
      opened_at: dates[0] || '',
      last_transaction_at: dates[1] || '',
      status,
      reported_balance_krw: balanceKrw,
    };
  }

  function documentKind(rows) {
    const valid = (rows || []).filter((row) => row?.institution);
    if (!valid.length) return 'unknown';
    const securities = valid.filter((row) => /증권/u.test(row.institution)).length;
    return securities >= Math.ceil(valid.length * 0.6) ? 'brokerage' : 'bank';
  }

  function suggestedBrokerType(product) {
    const value = text(product).toLowerCase();
    if (/중개형\s*isa|\bisa\b/i.test(value)) return 'isa';
    if (/연금저축/i.test(value)) return 'pension_savings';
    if (/개인형\s*irp|\birp\b/i.test(value)) return 'irp';
    return 'general';
  }

  function needsReview(kind, row) {
    if (kind === 'brokerage') return REVIEW_BROKER_PRODUCT.test(text(row?.product));
    if (kind === 'bank') return REVIEW_BANK_PRODUCT.test(text(row?.product));
    return true;
  }

  function normalizeExisting(payload) {
    const brokerAccounts = Array.isArray(payload?.brokerAccounts) ? payload.brokerAccounts : [];
    const bankAccounts = Array.isArray(payload?.bankAccounts) ? payload.bankAccounts : [];
    return {
      brokerAccounts: brokerAccounts.map((account) => ({
        institution: canonicalInstitution(account?.broker),
        account_no: digits(account?.account_no),
        owner: text(account?.owner || '모두'),
      })),
      bankAccounts: bankAccounts.map((account) => ({
        institution: canonicalInstitution(account?.bank_name),
        account_no: digits(account?.account_number),
        owner: text(account?.owner || '모두'),
      })),
    };
  }

  function decorateRows(parsed, owner, existing) {
    const kind = documentKind(parsed?.rows || []);
    const normalized = normalizeExisting(existing || {});
    return (parsed?.rows || []).map((row, index) => {
      const pool = kind === 'brokerage' ? normalized.brokerAccounts : normalized.bankAccounts;
      const institution = canonicalInstitution(row.institution);
      const accountNo = digits(row.account_no);
      const duplicate = pool.find((item) => item.account_no && item.account_no === accountNo && item.institution === institution);
      const ownerConflict = Boolean(duplicate && duplicate.owner && duplicate.owner !== owner);
      const review = needsReview(kind, row);
      const duplicateSameOwner = Boolean(duplicate && !ownerConflict);
      const inactive = row.status === '비활동성';
      let importStatus = 'new';
      if (ownerConflict) importStatus = 'owner_conflict';
      else if (duplicateSameOwner) importStatus = 'duplicate';
      else if (review) importStatus = 'review';
      else if (inactive) importStatus = 'inactive';
      return {
        ...row,
        preview_index: index,
        kind,
        suggested_type: kind === 'brokerage' ? suggestedBrokerType(row.product) : 'bank_account',
        import_status: importStatus,
        default_selected: importStatus === 'new',
      };
    });
  }

  function csvCell(value) {
    const raw = String(value ?? '');
    return /[",\n]/.test(raw) ? `"${raw.replace(/"/g, '""')}"` : raw;
  }

  function brokerageCsv(rows, owner) {
    const headers = ['소유자','증권사','계좌명','계좌번호','계좌유형','원화예수금','달러예수금','세액공제적용','소득구간','올해연금납입액','ISA전환입금액','ISA전환연도'];
    const year = new Date().getFullYear();
    const lines = [headers.join(',')];
    rows.forEach((row) => {
      const accountName = row.product || row.branch || 'AccountInfo 계좌';
      const values = [owner,row.institution,accountName,row.account_no,row.suggested_type,0,0,'미적용','low',0,0,year];
      lines.push(values.map(csvCell).join(','));
    });
    return `\ufeff${lines.join('\r\n')}`;
  }

  async function loadPdfJs() {
    if (!pdfjsPromise) {
      pdfjsPromise = import(PDFJS_URL).then((pdfjs) => {
        pdfjs.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
        return pdfjs;
      });
    }
    return pdfjsPromise;
  }

  async function parsePdfFile(file) {
    if (!file || !/\.pdf$/i.test(file.name || '')) throw new Error('AccountInfo PDF 파일을 선택해 주세요.');
    if (file.size > PDF_MAX_BYTES) throw new Error('PDF 파일은 10MB 이하만 가져올 수 있습니다.');
    const bytes = new Uint8Array(await file.arrayBuffer());
    const signature = new TextDecoder('latin1').decode(bytes.slice(0, 5));
    if (signature !== '%PDF-') throw new Error('올바른 PDF 파일이 아닙니다.');
    let pdfjs;
    try {
      pdfjs = await loadPdfJs();
    } catch (_) {
      throw new Error('PDF 분석 모듈을 불러오지 못했습니다. 네트워크를 확인하거나 CSV/XLSX 가져오기를 사용해 주세요.');
    }
    const doc = await pdfjs.getDocument({ data: bytes }).promise;
    const pages = [];
    for (let pageNo = 1; pageNo <= doc.numPages; pageNo += 1) {
      const page = await doc.getPage(pageNo);
      const content = await page.getTextContent();
      pages.push(content.items || []);
    }
    const parsed = rowsFromPdfPages(pages);
    if (!parsed.rows.length) throw new Error('AccountInfo 계좌 행을 찾지 못했습니다. 지원되는 계좌통합현황 PDF인지 확인해 주세요.');
    if (!parsed.report_date) throw new Error('AccountInfo 조회기준일을 확인하지 못했습니다.');
    return parsed;
  }

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', ...options });
    const type = response.headers.get('content-type') || '';
    const payload = type.includes('application/json') ? await response.json() : null;
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === 'string' ? detail : (detail?.message || payload?.message || `요청 실패 (${response.status})`);
      throw new Error(message);
    }
    return payload || {};
  }

  async function loadExistingAccounts() {
    const [brokerPayload, savingsPayload] = await Promise.all([
      jsonFetch('/api/accounts?group=All&owner=모두'),
      jsonFetch('/api/savings'),
    ]);
    return {
      brokerAccounts: brokerPayload?.accounts || [],
      bankAccounts: savingsPayload?.bank_accounts || [],
    };
  }

  function accountOwners() {
    const values = [...document.querySelectorAll('.family-tab[data-owner]')]
      .map((node) => text(node.dataset.owner))
      .filter((value) => value && value !== '모두');
    return [...new Set(values)];
  }

  function ensureOwnerSelect(form) {
    let select = document.getElementById('accountInfoImportOwner');
    if (select) return select;
    const fileInput = document.getElementById('accountImportFile');
    const fileLabel = fileInput?.closest('label');
    if (!fileLabel) return null;
    const label = document.createElement('label');
    label.id = 'accountInfoOwnerLabel';
    label.style.display = 'none';
    label.textContent = 'PDF 계좌 소유자';
    select = document.createElement('select');
    select.id = 'accountInfoImportOwner';
    select.required = false;
    const owners = accountOwners();
    const activeOwner = text(document.querySelector('.family-tab.active[data-owner]')?.dataset?.owner);
    const options = owners.length ? owners : ['모두'];
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = '소유자를 선택하세요';
    select.appendChild(placeholder);
    options.forEach((owner) => {
      const option = document.createElement('option');
      option.value = owner;
      option.textContent = owner;
      if (activeOwner && activeOwner !== '모두' && owner === activeOwner) option.selected = true;
      select.appendChild(option);
    });
    label.appendChild(select);
    fileLabel.parentElement?.insertBefore(label, fileLabel);
    select.addEventListener('change', () => { previewState = null; clearPreview(); });
    return select;
  }

  function ensurePreviewHost(form) {
    let host = document.getElementById('accountInfoPdfPreview');
    if (!host) {
      host = document.createElement('div');
      host.id = 'accountInfoPdfPreview';
      host.style.cssText = 'display:none;margin-top:12px;max-height:58vh;overflow:auto;border:1px solid rgba(148,163,184,.18);border-radius:10px;padding:10px;background:rgba(15,23,42,.35);';
      const actions = form.querySelector('.dialog-actions');
      form.insertBefore(host, actions || null);
    }
    return host;
  }

  function clearPreview() {
    const host = document.getElementById('accountInfoPdfPreview');
    if (host) { host.style.display = 'none'; host.replaceChildren(); }
    const submit = document.querySelector('#accountImportForm button[type="submit"]');
    if (submit) submit.textContent = '가져오기';
  }

  function statusLabel(status) {
    return {
      new: ['신규', '#6ee7b7'],
      inactive: ['비활동성 · 선택', '#94a3b8'],
      review: ['확인 필요', '#fbbf24'],
      duplicate: ['이미 등록됨', '#94a3b8'],
      owner_conflict: ['다른 소유자와 충돌', '#fb7185'],
    }[status] || ['확인 필요', '#fbbf24'];
  }

  function renderPreview(parsed, rows, owner, file) {
    const form = document.getElementById('accountImportForm');
    const host = ensurePreviewHost(form);
    const dialog = document.getElementById('accountImportDialog');
    if (dialog) dialog.style.maxWidth = '1120px';
    host.style.display = 'block';
    host.replaceChildren();

    const kind = documentKind(rows);
    const title = document.createElement('div');
    title.style.cssText = 'display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:8px;';
    const newCount = rows.filter((row) => row.import_status === 'new').length;
    const dupCount = rows.filter((row) => row.import_status === 'duplicate').length;
    const reviewCount = rows.filter((row) => ['review','inactive','owner_conflict'].includes(row.import_status)).length;
    title.innerHTML = `<div><strong>AccountInfo PDF 미리보기</strong><div style="margin-top:3px;color:#94a3b8;font-size:11px;">${kind === 'brokerage' ? '증권' : '은행'} · 조회기준일 ${parsed.report_date} · ${rows.length}계좌 · 소유자 ${owner}</div></div><div style="font-size:11px;color:#94a3b8;">신규 ${newCount} · 기존 ${dupCount} · 확인 ${reviewCount}</div>`;
    host.appendChild(title);

    const note = document.createElement('div');
    note.style.cssText = 'margin-bottom:8px;padding:7px 9px;border-radius:8px;background:rgba(30,41,59,.48);font-size:10.8px;color:#cbd5e1;line-height:1.5;';
    note.textContent = kind === 'brokerage'
      ? 'AccountInfo의 증권계좌 잔액은 예수금으로 간주하지 않습니다. 가져온 증권계좌의 KRW/USD 예수금은 0원으로 시작하며 PDF 잔액은 저장하지 않습니다.'
      : '은행 PDF의 잔액은 일반 은행계좌 잔액으로 저장합니다. 청약·적금·외화 상품은 확인 필요로 기본 선택하지 않으므로 상품 성격을 확인한 뒤 선택하세요.';
    host.appendChild(note);

    const table = document.createElement('table');
    table.style.cssText = 'width:100%;border-collapse:collapse;font-size:10.8px;min-width:850px;';
    table.innerHTML = '<thead><tr style="color:#94a3b8;border-bottom:1px solid rgba(148,163,184,.2);"><th style="padding:6px;text-align:left;">선택</th><th style="padding:6px;text-align:left;">금융기관</th><th style="padding:6px;text-align:left;">계좌</th><th style="padding:6px;text-align:left;">상품</th><th style="padding:6px;text-align:left;">상태</th><th style="padding:6px;text-align:right;">PDF 잔액</th><th style="padding:6px;text-align:left;">가져오기 상태</th></tr></thead>';
    const body = document.createElement('tbody');
    rows.forEach((row) => {
      const [label, color] = statusLabel(row.import_status);
      const disabled = row.import_status === 'duplicate' || row.import_status === 'owner_conflict';
      const tr = document.createElement('tr');
      tr.style.borderTop = '1px solid rgba(148,163,184,.08)';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.dataset.accountInfoIndex = String(row.preview_index);
      checkbox.checked = row.default_selected === true;
      checkbox.disabled = disabled;
      const selectTd = document.createElement('td');
      selectTd.style.padding = '7px 6px';
      selectTd.appendChild(checkbox);
      tr.appendChild(selectTd);
      const values = [
        row.institution,
        maskAccountNo(row.account_no),
        row.product || row.branch || '-',
        row.status || '-',
      ];
      values.forEach((value) => {
        const td = document.createElement('td'); td.style.padding = '7px 6px'; td.textContent = value; tr.appendChild(td);
      });
      const bal = document.createElement('td'); bal.style.cssText = 'padding:7px 6px;text-align:right;white-space:nowrap;'; bal.textContent = money(row.reported_balance_krw); tr.appendChild(bal);
      const st = document.createElement('td'); st.style.cssText = `padding:7px 6px;color:${color};font-weight:700;white-space:nowrap;`; st.textContent = label; tr.appendChild(st);
      body.appendChild(tr);
    });
    table.appendChild(body);
    const wrap = document.createElement('div'); wrap.style.overflowX = 'auto'; wrap.appendChild(table); host.appendChild(wrap);

    const privacy = document.createElement('div');
    privacy.style.cssText = 'margin-top:8px;color:#64748b;font-size:10px;';
    privacy.textContent = '계좌번호는 미리보기에서 마스킹됩니다. PDF 파일 자체는 Wealth 서버나 외부 분석 서비스로 업로드하지 않고 현재 브라우저에서만 읽습니다.';
    host.appendChild(privacy);

    previewState = { file, parsed, rows, owner };
    const submit = form.querySelector('button[type="submit"]');
    if (submit) submit.textContent = '선택 계좌 추가';
  }

  async function previewPdf(file, owner) {
    const parsed = await parsePdfFile(file);
    const existing = await loadExistingAccounts();
    const rows = decorateRows(parsed, owner, existing);
    renderPreview(parsed, rows, owner, file);
  }

  function selectedRows() {
    if (!previewState) return [];
    const selected = new Set([...document.querySelectorAll('#accountInfoPdfPreview input[data-account-info-index]:checked')]
      .map((input) => Number(input.dataset.accountInfoIndex)));
    return previewState.rows.filter((row) => selected.has(row.preview_index));
  }

  async function applyBrokerage(rows, owner) {
    if (!rows.length) return { created: 0, duplicates: 0, invalid: 0 };
    const csv = brokerageCsv(rows, owner);
    const formData = new FormData();
    formData.append('file', new Blob([csv], { type: 'text/csv;charset=utf-8' }), 'accountinfo_accounts.csv');
    return jsonFetch('/api/import-accounts', { method: 'POST', body: formData });
  }

  async function applyBanks(rows, owner, reportDate) {
    let created = 0;
    for (const row of rows) {
      const memoParts = [`AccountInfo ${reportDate}`, row.status || '', row.branch || ''].filter(Boolean);
      await jsonFetch('/api/bank-accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bank_name: row.institution,
          account_name: row.product || row.branch || 'AccountInfo 계좌',
          account_number: row.account_no,
          owner,
          balance: Number(row.reported_balance_krw || 0),
          limit_amount: 0,
          interest_rate: 0,
          maturity_date: '',
          currency: 'KRW',
          memo: memoParts.join(' · '),
        }),
      });
      created += 1;
    }
    return { created };
  }

  async function applyPreview() {
    if (!previewState) return;
    const rows = selectedRows();
    if (!rows.length) throw new Error('추가할 계좌를 하나 이상 선택해 주세요.');

    const freshExisting = await loadExistingAccounts();
    const refreshed = decorateRows(previewState.parsed, previewState.owner, freshExisting);
    const selectedSourceRows = new Set(rows.map((row) => row.source_row));
    const safeRows = refreshed.filter((row) => selectedSourceRows.has(row.source_row) && !['duplicate','owner_conflict'].includes(row.import_status));
    if (!safeRows.length) throw new Error('선택한 계좌가 모두 이미 등록되었거나 소유자 충돌 상태입니다.');

    let result;
    if (documentKind(safeRows) === 'brokerage') {
      result = await applyBrokerage(safeRows, previewState.owner);
    } else {
      result = await applyBanks(safeRows, previewState.owner, previewState.parsed.report_date);
    }
    return result;
  }

  function setBusy(form, busy) {
    const submit = form.querySelector('button[type="submit"]');
    if (!submit) return;
    submit.disabled = busy;
    if (busy) submit.dataset.beforeBusyText = submit.textContent;
    submit.textContent = busy ? '처리 중…' : (submit.dataset.beforeBusyText || (previewState ? '선택 계좌 추가' : '가져오기'));
  }

  function isPdfFile(file) {
    return Boolean(file && (/\.pdf$/i.test(file.name || '') || file.type === 'application/pdf'));
  }

  function install() {
    const form = document.getElementById('accountImportForm');
    const fileInput = document.getElementById('accountImportFile');
    const dialog = document.getElementById('accountImportDialog');
    if (!form || !fileInput || !dialog) return;

    fileInput.setAttribute('accept', '.csv,.xlsx,.xlsm,.pdf,application/pdf');
    const description = dialog.querySelector('.dialog-description');
    if (description && !description.dataset.accountInfoEnhanced) {
      description.dataset.accountInfoEnhanced = '1';
      description.insertAdjacentHTML('afterend', '<p style="margin:-4px 0 10px;color:#94a3b8;font-size:11px;line-height:1.5;">AccountInfo의 <strong>계좌통합현황 PDF</strong>도 지원합니다. PDF는 저장 전에 마스킹된 미리보기에서 신규/중복/확인 필요 계좌를 선택합니다.</p>');
    }
    const ownerSelect = ensureOwnerSelect(form);
    ensurePreviewHost(form);

    fileInput.addEventListener('change', () => {
      previewState = null;
      clearPreview();
      const pdf = isPdfFile(fileInput.files?.[0]);
      const ownerLabel = document.getElementById('accountInfoOwnerLabel');
      if (ownerLabel) ownerLabel.style.display = pdf ? 'block' : 'none';
      if (!pdf) dialog.style.maxWidth = '540px';
    });

    form.addEventListener('submit', async (event) => {
      const file = fileInput.files?.[0];
      if (!isPdfFile(file)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const owner = text(ownerSelect?.value);
      if (!owner) {
        window.alert('PDF에 추가할 계좌의 소유자를 선택해 주세요.');
        return;
      }
      try {
        setBusy(form, true);
        if (previewState && previewState.file === file && previewState.owner === owner) {
          const result = await applyPreview();
          const created = Number(result?.created || 0);
          if (typeof window.toast === 'function') window.toast(`AccountInfo 계좌 ${created}개를 추가했습니다.`);
          else window.alert(`AccountInfo 계좌 ${created}개를 추가했습니다.`);
          dialog.close();
          window.location.reload();
        } else {
          await previewPdf(file, owner);
        }
      } catch (error) {
        const message = error?.message || 'AccountInfo PDF를 처리하지 못했습니다.';
        if (typeof window.toast === 'function') window.toast(message, true);
        else window.alert(message);
      } finally {
        setBusy(form, false);
      }
    }, true);

    const bankingActions = document.getElementById('bankingActions');
    if (bankingActions && !document.getElementById('accountInfoBankImportBtn')) {
      const button = document.createElement('button');
      button.id = 'accountInfoBankImportBtn';
      button.type = 'button';
      button.className = 'button secondary compact';
      button.title = 'AccountInfo 은행/증권 계좌통합현황 PDF 가져오기';
      button.textContent = '📂 AccountInfo PDF';
      button.addEventListener('click', () => {
        previewState = null;
        clearPreview();
        const ownerLabel = document.getElementById('accountInfoOwnerLabel');
        if (ownerLabel) ownerLabel.style.display = 'block';
        fileInput.value = '';
        dialog.showModal();
      });
      bankingActions.appendChild(button);
    }
  }

  const exported = {
    text,
    digits,
    canonicalInstitution,
    maskAccountNo,
    isRowAnchor,
    rowsFromPdfPages,
    parseRowTokens,
    documentKind,
    suggestedBrokerType,
    needsReview,
    decorateRows,
    brokerageCsv,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = exported;
  if (typeof window !== 'undefined') window.WealthAccountInfoImport = exported;
  if (typeof document === 'undefined') return;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();
