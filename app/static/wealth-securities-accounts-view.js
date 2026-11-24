/* Securities account list View. Financial helpers and account actions remain caller-owned. */
(() => {
  'use strict';

  function create({ html, number, signClass, maskBrokerAccountNo, accountReorder }) {
function renderEmpty(container) {
  window.WealthOperationFeedback.renderEmpty(container, '동기화된 계좌가 없습니다.');
}

function renderAccounts(container, groups) {
  container.innerHTML = groups.map(group => {
    const accounts = group.items.map(row => {
      const { account, stockVal, cashKrw, cashUsd, cashTotalKrw, totalVal, profitVal,
        aType, isTaxDeductible, pension } = row;
      const cashDetailParts = [];
      if (cashKrw > 0 || cashTotalKrw === 0) cashDetailParts.push(`₩${number(cashKrw, 0)}`);
      if (cashUsd > 0) cashDetailParts.push(`$${number(cashUsd, 2)}`);
      const cashFormatted = cashDetailParts.length ? cashDetailParts.join(" / ") : `₩${number(cashTotalKrw, 0)}`;

      let typeBadge = "";
      if (aType === "pension_savings") {
        if (isTaxDeductible) {
          typeBadge = `<span class="account-type-tag pension" data-toggle-tax-account-id="${html(account.id)}" title="클릭 시 '비공제'로 즉시 전환" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(56,189,248,0.18);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);margin-right:4px;cursor:pointer;">연금(공제O) 🔄</span>`;
        } else {
          typeBadge = `<span class="account-type-tag non-deductible" data-toggle-tax-account-id="${html(account.id)}" title="클릭 시 '세액공제 신청'으로 즉시 전환" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.4);margin-right:4px;cursor:pointer;">연금(비공제) 🔄</span>`;
        }
      } else if (aType === "irp") {
        if (isTaxDeductible) {
          typeBadge = `<span class="account-type-tag irp" data-toggle-tax-account-id="${html(account.id)}" title="클릭 시 '비공제'로 즉시 전환" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(168,85,247,0.18);color:#c084fc;border:1px solid rgba(168,85,247,0.4);margin-right:4px;cursor:pointer;">IRP(공제O) 🔄</span>`;
        } else {
          typeBadge = `<span class="account-type-tag non-deductible" data-toggle-tax-account-id="${html(account.id)}" title="클릭 시 '세액공제 신청'으로 즉시 전환" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.4);margin-right:4px;cursor:pointer;">IRP(비공제) 🔄</span>`;
        }
      } else if (aType === "isa") {
        typeBadge = '<span class="account-type-tag isa" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.4);margin-right:4px;">ISA</span>';
      }

      let taxBenefitBox = "";
      if (aType === "pension_savings" || aType === "irp") {
        const { dep, currentSaved, cumSaved, rate } = pension;
        if (!isTaxDeductible) {
          taxBenefitBox = `
            <div style="margin-top:5px;display:inline-flex;align-items:center;gap:6px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.35);border-radius:6px;padding:3px 8px;font-size:11.5px;color:#34d399;font-weight:600;">
              <span>🌿 비공제 계좌</span>
              <span style="color:#cbd5e1;font-weight:normal;">(납입 ₩${number(dep, 0)} · 원금 비과세 인출 대상)</span>
            </div>
          `;
        } else {
          const cumText = cumSaved > 0 ? ` · 누적 절세 <strong style="color:#4ade80;font-weight:700;">+₩${number(cumSaved, 0)}</strong>` : '';
          taxBenefitBox = `
            <div style="margin-top:5px;display:inline-flex;align-items:center;gap:6px;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.35);border-radius:6px;padding:3px 8px;font-size:11.5px;color:#38bdf8;font-weight:600;">
              <span>💎 세액공제 신청</span>
              <span style="color:#cbd5e1;font-weight:normal;">(납입 ₩${number(dep, 0)} · 소유자 합산 예상 환급 <strong style="color:#4ade80;font-weight:700;">+₩${number(currentSaved, 0)}</strong> / ${rate}%${cumText})</span>
            </div>
          `;
        }
      }

      return `<div class="account-row" data-order-id="${html(account.id || '')}" data-order-label="${html(account.name || '계좌')}">
        <div class="account-row-info">
          <div class="account-row-title-line" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            ${typeBadge}
            <strong class="account-name-text" style="font-size:14px;font-weight:700;">${html(account.name)}</strong>
            <span class="saving-owner-badge" style="font-size:10.5px;padding:1px 6px;">${html(account.owner || '모두')}</span>
            ${account.account_no ? `<span style="font-size:10.5px;color:#94a3b8;">${html(maskBrokerAccountNo(account.account_no))}</span>` : ''}
          </div>
          <div class="account-row-sub-line" style="font-size:12px;color:#94a3b8;margin-top:2px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <span>주식자산 <strong style="font-weight:600;">₩${number(stockVal, 0)}</strong> (${number(account.holding_count, 0)}종목)</span>
            <span style="color:#475569;">·</span>
            <span>예수금 <strong style="color:#38bdf8;font-weight:600;">${cashFormatted}</strong></span>
          </div>
          ${taxBenefitBox}
        </div>
        <div class="account-row-right">
          <div class="account-row-values">
            <div class="account-total-label" style="font-size:10.5px;color:#94a3b8;margin-bottom:1px;font-weight:500;">통장 총 자산</div>
            <strong class="account-total-val" style="font-size:15px;font-weight:800;letter-spacing:-0.3px;">₩${number(totalVal, 0)}</strong>
            ${profitVal !== 0 ? `
              <div class="account-profit-val ${signClass(profitVal)}" style="font-size:11.5px;margin-top:2px;font-weight:700;">
                ${profitVal > 0 ? '+' : ''}₩${number(profitVal, 0)}
              </div>
            ` : ''}
          </div>
          <div class="account-row-actions" style="display:flex;align-items:center;gap:5px;">
            <button class="account-action-button" data-account-edit-id="${html(account.id)}" title="계좌 정보 및 예수금 수정" type="button">✎</button>
            <button class="mini-delete-button" data-account-del-id="${html(account.id)}" title="계좌 삭제" type="button">🗑️</button>
          </div>
        </div>
      </div>`;
    }).join("");
    return `<section class="broker-group" data-order-institution="${html(group.broker || '기타')}"><div class="broker-head"><strong>${html(group.broker)}</strong><span>${number(group.count, 0)}개 계좌</span></div><div class="broker-accounts">${accounts}</div></section>`;
  }).join("");
  accountReorder?.rendered('securities');
}

    return Object.freeze({ renderAccounts, renderEmpty });
  }

  window.WealthSecuritiesAccountsView = Object.freeze({ create });
})();
