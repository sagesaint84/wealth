(() => {
  "use strict";

  function create({ html, number }) {
    function renderList(listContainer, recs) {
      if (recs.length === 0) {
        listContainer.innerHTML = `<div class="empty" style="padding:15px 0;"><p style="margin:0;font-size:12px;color:#94a3b8;">등록된 정기 고정지출이 없습니다.</p></div>`;
      } else {
        listContainer.innerHTML = recs.map(({ r, status }) => {
          let statusBadge;
          if (status === "deducted") {
            statusBadge = `<span style="color:#4ade80;font-size:11px;font-weight:600;">✅ 당월 자동출금 완료 (${html(r.last_deducted_date)})</span>`;
          } else if (status === "pending") {
            statusBadge = `<span style="color:#facc15;font-size:11px;font-weight:600;">⏳ 매월 ${html(String(r.day_of_month))}일 자동출금 대기</span>`;
          } else {
            statusBadge = `<span style="color:#94a3b8;font-size:11px;">수동 납부</span>`;
          }
          const itemIdArgument = html(JSON.stringify(String(r.id)));

          const acctBadge = r.linked_account_name ? `
            <span style="display:inline-block;font-size:10px;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);padding:1px 6px;border-radius:4px;margin-left:4px;">
              🏦 ${html(r.linked_account_name)}
            </span>
          ` : "";

          return `
            <div class="ledger-recurring-item">
              <div>
                <div class="ledger-recurring-title">
                  <span>${html(r.name)}</span>
                  <span class="saving-owner-badge" style="font-size:10px;padding:1px 5px;">${html(r.owner || '모두')}</span>
                  ${acctBadge}
                </div>
                <div class="ledger-recurring-meta">
                  <span>매월 ${html(String(r.day_of_month))}일</span>
                  <span>·</span>
                  <span>${html(r.category)}</span>
                  <span>·</span>
                  <span>${html(r.pay_method)}</span>
                  <span>·</span>
                  ${statusBadge}
                </div>
              </div>
              <div style="display:flex;align-items:center;gap:6px;">
                <strong class="ledger-recurring-amt">₩${number(r.amount, 0)}</strong>
                <button class="account-action-button" onclick="editRecurringItem(${itemIdArgument})" title="수정" type="button" style="padding:3px 7px;font-size:12px;">✎</button>
                <button class="account-action-button mini-delete-button" onclick="deleteRecurringItem(${itemIdArgument})" title="삭제" type="button" style="padding:3px 7px;font-size:12px;">🗑️</button>
              </div>
            </div>
          `;
        }).join("");
      }
    }

    return Object.freeze({ renderList });
  }

  window.WealthLedgerRecurringView = Object.freeze({ create });
})();
