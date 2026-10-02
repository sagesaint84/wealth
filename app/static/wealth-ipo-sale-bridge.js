(() => {
  'use strict';

  const SCRIPT_STYLE_ID = 'wealthIpoSaleBridgeStyle';
  const DIALOG_ID = 'ipoManualSaleDialog';
  let activeContext = null;
  let saving = false;

  function text(value) {
    return String(value ?? '').normalize('NFKC').replace(/\s+/g, ' ').trim();
  }

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function kstToday(now = new Date()) {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(now).reduce((result, part) => {
      if (part.type !== 'literal') result[part.type] = part.value;
      return result;
    }, {});
    return `${parts.year}-${parts.month}-${parts.day}`;
  }

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, { credentials: 'same-origin', ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === 'string'
        ? detail
        : (detail?.message || payload?.message || `요청 실패 (${response.status})`);
      throw new Error(message);
    }
    return payload;
  }

  function ensureStyle() {
    if (document.getElementById(SCRIPT_STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = SCRIPT_STYLE_ID;
    style.textContent = `
      .ipo-manual-sale-tools { display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:6px; }
      .ipo-manual-sale-hint { color:#8fa4c8;font-size:11px;line-height:1.35; }
      .ipo-manual-sale-message { color:#67e8f9;font-size:11px;line-height:1.35;min-height:14px; }
      #${DIALOG_ID} { max-width:520px;width:94vw; }
      #${DIALOG_ID} .ipo-manual-sale-note { margin:0 0 12px;padding:10px 12px;border:1px solid rgba(56,189,248,.22);border-radius:9px;background:rgba(14,116,144,.08);color:#9fb6d7;font-size:11.5px;line-height:1.5; }
      #${DIALOG_ID} .ipo-manual-sale-grid { display:grid;grid-template-columns:1fr 1fr;gap:10px; }
      #${DIALOG_ID} .ipo-manual-sale-grid label { display:flex;flex-direction:column;gap:5px;color:#aebbd4;font-size:12px; }
      #${DIALOG_ID} .ipo-manual-sale-grid input { width:100%;box-sizing:border-box; }
      #${DIALOG_ID} .ipo-manual-sale-wide { grid-column:1/-1; }
      #${DIALOG_ID} .ipo-manual-sale-status { min-height:18px;margin-top:8px;color:#fbbf24;font-size:11.5px; }
      @media (max-width:620px) { #${DIALOG_ID} .ipo-manual-sale-grid { grid-template-columns:1fr; } #${DIALOG_ID} .ipo-manual-sale-wide { grid-column:auto; } }
    `;
    document.head.appendChild(style);
  }

  function ensureDialog() {
    let dialog = document.getElementById(DIALOG_ID);
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = DIALOG_ID;
    dialog.className = 'dialog';
    dialog.innerHTML = `
      <div class="dialog-head">
        <h2>📦 공모주 매도 실현손익 기록</h2>
        <button type="button" class="close ipo-manual-sale-close" aria-label="닫기">×</button>
      </div>
      <p class="ipo-manual-sale-note">
        이 화면은 증권사에서 확인한 실제 매도 실현손익을 Wealth의 기존 실현손익 원장에 기록합니다.
        Wealth가 매도 손익이나 세금을 임의 계산하지 않습니다. 기록 후 기존 <strong>매도 연결</strong> 버튼으로 배정 내역과 연결합니다.
      </p>
      <form id="ipoManualSaleForm" onsubmit="return false;">
        <div class="ipo-manual-sale-grid">
          <label>매도일
            <input name="date" type="date" required />
          </label>
          <label>매도수량
            <input name="quantity" type="number" min="1" step="1" required />
          </label>
          <label class="ipo-manual-sale-wide">실현손익 (KRW · 증권사 확인 금액)
            <input name="pnl_krw" type="number" step="1" required placeholder="예: 125000" />
          </label>
          <label>공모청약비
            <input name="ipo_subscription_fee_krw" type="number" min="0" step="1" value="2000" required />
          </label>
          <label>매도금액 (선택)
            <input name="sell_amount" type="number" min="0" step="1" placeholder="0" />
          </label>
          <label>수수료 (선택)
            <input name="fee" type="number" min="0" step="1" placeholder="0" />
          </label>
          <label>세금 (선택)
            <input name="tax" type="number" min="0" step="1" placeholder="0" />
          </label>
        </div>
        <div class="ipo-manual-sale-status" role="status"></div>
        <div class="dialog-actions" style="margin-top:14px;">
          <button type="button" class="button secondary ipo-manual-sale-cancel">취소</button>
          <button type="submit" class="button primary ipo-manual-sale-save">실현손익 기록</button>
        </div>
      </form>
    `;
    document.body.appendChild(dialog);
    dialog.querySelector('.ipo-manual-sale-close')?.addEventListener('click', () => dialog.close());
    dialog.querySelector('.ipo-manual-sale-cancel')?.addEventListener('click', () => dialog.close());
    dialog.querySelector('#ipoManualSaleForm')?.addEventListener('submit', saveManualSale);
    return dialog;
  }

  function setDialogStatus(message, isError = false) {
    const node = document.querySelector(`#${DIALOG_ID} .ipo-manual-sale-status`);
    if (!node) return;
    node.textContent = message || '';
    node.style.color = isError ? '#fb7185' : '#67e8f9';
  }

  function setControlMessage(context, message) {
    const node = context?.applicant?.querySelector('.ipo-manual-sale-message');
    if (node) node.textContent = message || '';
  }

  async function marketRecord(ipoId) {
    const payload = await jsonFetch('/api/ipo/market');
    return (Array.isArray(payload?.ipos) ? payload.ipos : []).find((item) => text(item?.ipo_id) === ipoId) || null;
  }

  async function accountRecord(accountId) {
    const payload = await jsonFetch('/api/accounts?group=All&owner=모두');
    return (Array.isArray(payload?.accounts) ? payload.accounts : []).find((item) => text(item?.id) === accountId) || null;
  }

  function contextFromButton(button) {
    const applicant = button?.closest?.('.ipo-applicant-account');
    const card = button?.closest?.('.ipo-card');
    if (!applicant || !card) return null;
    const accountSelect = applicant.querySelector('.ipo-applicant-account-select');
    const allocationControl = applicant.querySelector('.ipo-allocation-control');
    return {
      applicant,
      allocationControl,
      ipoId: text(applicant.dataset.ipo || card.dataset.ipoId),
      owner: text(applicant.dataset.owner),
      accountId: text(accountSelect?.value),
      companyName: text(card.querySelector('.ipo-company-name')?.textContent),
      stockCode: text(card.querySelector('.ipo-code-badge')?.textContent),
      saleSelect: allocationControl?.querySelector('.ipo-sale-candidate'),
      saleQuantity: allocationControl?.querySelector('.ipo-sale-match-quantity'),
      saleLinkSave: allocationControl?.querySelector('.ipo-sale-link-save'),
    };
  }

  async function openManualSale(button) {
    const context = contextFromButton(button);
    if (!context?.ipoId || !context.owner) return;
    if (!context.accountId) {
      setControlMessage(context, '청약 계좌를 먼저 연결해 주세요.');
      return;
    }
    try {
      const [allocation, market] = await Promise.all([
        jsonFetch(`/api/ipo/applications/${encodeURIComponent(context.ipoId)}/applicants/${encodeURIComponent(context.owner)}/allocation`),
        marketRecord(context.ipoId),
      ]);
      const remaining = number(allocation?.allocation?.remaining_quantity);
      if (!allocation?.allocation || remaining <= 0) {
        setControlMessage(context, '먼저 배정수량을 저장하거나 남은 배정수량을 확인해 주세요.');
        return;
      }
      const listingDate = text(market?.actual_listing_date || market?.expected_listing_date);
      const today = kstToday();
      if (listingDate && today < listingDate) {
        setControlMessage(context, `상장일(${listingDate}) 이후 실제 매도 기록을 추가할 수 있습니다.`);
        return;
      }
      context.market = market;
      context.remainingQuantity = remaining;
      activeContext = context;
      const dialog = ensureDialog();
      const form = dialog.querySelector('#ipoManualSaleForm');
      form.reset();
      form.elements.date.value = today;
      form.elements.date.min = listingDate || '';
      form.elements.date.max = today;
      form.elements.quantity.value = String(remaining);
      form.elements.quantity.max = String(remaining);
      setDialogStatus(`${context.companyName || context.stockCode} · ${context.owner} · 잔여 ${remaining}주`);
      dialog.showModal();
    } catch (error) {
      setControlMessage(context, error?.message || '매도 기록 준비에 실패했습니다.');
    }
  }

  function optionForCandidate(item) {
    const option = document.createElement('option');
    option.value = text(item?.pnl_record_id);
    option.dataset.available = String(number(item?.available_quantity));
    option.textContent = `${text(item?.date) || '-'} · ${number(item?.available_quantity)}주`;
    return option;
  }

  async function refreshSaleCandidates(context, preferredId = '', preferredQuantity = 0) {
    const response = await jsonFetch(`/api/ipo/applications/${encodeURIComponent(context.ipoId)}/applicants/${encodeURIComponent(context.owner)}/allocation/sale-candidates`);
    const sales = Array.isArray(response?.candidates) ? response.candidates : [];
    const select = context.saleSelect;
    if (!select) return false;
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = sales.length ? '매도 후보 선택' : '매도 후보 없음';
    select.replaceChildren(placeholder, ...sales.map(optionForCandidate));
    const disabled = sales.length === 0;
    select.disabled = disabled;
    if (context.saleQuantity) context.saleQuantity.disabled = disabled;
    if (context.saleLinkSave) context.saleLinkSave.disabled = disabled;

    if (preferredId && sales.some((item) => text(item?.pnl_record_id) === preferredId)) {
      select.value = preferredId;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      if (context.saleQuantity && preferredQuantity > 0) {
        context.saleQuantity.value = String(preferredQuantity);
        const selected = select.options[select.selectedIndex];
        context.saleQuantity.max = selected?.dataset.available || String(preferredQuantity);
      }
      if (context.saleLinkSave) context.saleLinkSave.disabled = false;
      return true;
    }
    return false;
  }

  async function saveManualSale(event) {
    event?.preventDefault?.();
    if (saving || !activeContext) return;
    const dialog = ensureDialog();
    const form = dialog.querySelector('#ipoManualSaleForm');
    const saveButton = dialog.querySelector('.ipo-manual-sale-save');
    const context = activeContext;
    const date = text(form.elements.date.value);
    const quantity = number(form.elements.quantity.value);
    const pnlKrw = Number(form.elements.pnl_krw.value);
    const ipoSubscriptionFeeKrw = Number(form.elements.ipo_subscription_fee_krw.value);
    const listingDate = text(context.market?.actual_listing_date || context.market?.expected_listing_date);
    const today = kstToday();
    if (!date || !Number.isInteger(quantity) || quantity <= 0 || quantity > context.remainingQuantity) {
      setDialogStatus(`매도수량은 1~${context.remainingQuantity}주 사이의 정수여야 합니다.`, true);
      return;
    }
    if (listingDate && date < listingDate) {
      setDialogStatus(`매도일은 상장일(${listingDate}) 이후여야 합니다.`, true);
      return;
    }
    if (date > today) {
      setDialogStatus('미래 날짜의 실제 매도 기록은 추가할 수 없습니다.', true);
      return;
    }
    if (!Number.isFinite(pnlKrw)) {
      setDialogStatus('증권사에서 확인한 실현손익 금액을 입력해 주세요.', true);
      return;
    }

    if (!Number.isInteger(ipoSubscriptionFeeKrw) || ipoSubscriptionFeeKrw < 0) {
      setDialogStatus('공모청약비는 0원 이상의 정수로 입력해 주세요.', true);
      return;
    }
    const finalWealthPnlKrw = pnlKrw - ipoSubscriptionFeeKrw;
    const subscriptionFeeMemo = ipoSubscriptionFeeKrw === 2000
      ? '공모수수료 2천원 차감'
      : `공모수수료 ${ipoSubscriptionFeeKrw.toLocaleString('ko-KR')}원 차감`;

    saving = true;
    if (saveButton) {
      saveButton.disabled = true;
      saveButton.textContent = '기록 중…';
    }
    try {
      const account = await accountRecord(context.accountId);
      if (!account) throw new Error('연결된 Wealth 증권계좌를 찾을 수 없습니다.');
      const payload = {
        date,
        owner: context.owner,
        broker: text(account.broker),
        account_id: text(account.id),
        account_name: text(account.name || account.account_name),
        code: context.stockCode,
        name: context.companyName || context.stockCode,
        asset_type: 'ipo',
        currency: 'KRW',
        pnl: finalWealthPnlKrw,
        pnl_krw: finalWealthPnlKrw,
        provider_realized_pnl: pnlKrw,
        ipo_subscription_fee_krw: ipoSubscriptionFeeKrw,
        is_ipo: true,
        quantity,
        memo: `공모주 배정 매도 실현손익 · ${subscriptionFeeMemo}`,
      };
      ['sell_amount', 'fee', 'tax'].forEach((field) => {
        const raw = text(form.elements[field]?.value);
        if (raw !== '') payload[field] = Number(raw);
      });

      const created = await jsonFetch('/api/realized-pnl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const recordId = text(created?.record?.id);
      if (!recordId) throw new Error('실현손익 기록 ID를 확인할 수 없습니다.');
      const selected = await refreshSaleCandidates(context, recordId, quantity);
      if (!selected) throw new Error('기록은 저장됐지만 매도 후보 조건과 일치하지 않습니다. 계좌·종목·일자를 확인해 주세요.');
      setControlMessage(context, '실현손익 기록 완료 · 아래 “매도 연결”을 눌러 배정 내역과 연결하세요.');
      dialog.close();
      if (typeof window.loadRealizedPnl === 'function') void window.loadRealizedPnl();
    } catch (error) {
      setDialogStatus(error?.message || '실현손익 기록에 실패했습니다.', true);
    } finally {
      saving = false;
      if (saveButton) {
        saveButton.disabled = false;
        saveButton.textContent = '실현손익 기록';
      }
    }
  }

  function syncApplicant(applicant) {
    const control = applicant?.querySelector?.('.ipo-allocation-control');
    if (!control || control.querySelector('.ipo-manual-sale-tools')) return;
    const tools = document.createElement('div');
    tools.className = 'ipo-manual-sale-tools';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button secondary compact ipo-manual-sale-create';
    button.textContent = '➕ 매도 기록 추가';
    button.title = '증권사에서 확인한 공모주 매도 실현손익을 기록합니다.';
    const hint = document.createElement('span');
    hint.className = 'ipo-manual-sale-hint';
    hint.textContent = '매도 후보가 없으면 실제 실현손익 기록을 먼저 추가하세요.';
    const message = document.createElement('span');
    message.className = 'ipo-manual-sale-message';
    tools.append(button, hint, message);
    control.appendChild(tools);
  }

  function syncAllApplicants(root = document) {
    root.querySelectorAll?.('.ipo-applicant-account').forEach(syncApplicant);
  }

  function install() {
    ensureStyle();
    ensureDialog();
    const wrapper = document.getElementById('ipoListWrapper');
    if (!wrapper) return;
    syncAllApplicants(wrapper);
    wrapper.addEventListener('click', (event) => {
      const button = event.target?.closest?.('.ipo-manual-sale-create');
      if (button) void openManualSale(button);
    });
    const observer = new MutationObserver((records) => {
      let shouldSync = false;
      for (const record of records) {
        for (const node of record.addedNodes || []) {
          if (node?.nodeType !== 1) continue;
          if (node.matches?.('.ipo-applicant-account') || node.querySelector?.('.ipo-applicant-account')) {
            shouldSync = true;
            break;
          }
        }
        if (shouldSync) break;
      }
      if (shouldSync) queueMicrotask(() => syncAllApplicants(wrapper));
    });
    observer.observe(wrapper, { childList: true, subtree: true });
  }

  const exported = {
    text,
    number,
    kstToday,
    contextFromButton,
    optionForCandidate,
    syncApplicant,
    syncAllApplicants,
    refreshSaleCandidates,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = exported;
  if (typeof window !== 'undefined') window.WealthIpoSaleBridge = exported;
  if (typeof document === 'undefined') return;

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
})();