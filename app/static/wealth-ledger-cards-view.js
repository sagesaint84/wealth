(() => {
  "use strict";

  function create({ document, html, number }) {
    function renderLedgerCardsList(cards) {
      const listContainer = document.getElementById("ledgerCardsList");
      if (!listContainer) return;

      if (!cards || cards.length === 0) {
        listContainer.innerHTML = `<div class="empty" style="grid-column:1/-1;padding:24px 0;"><p style="margin:0;font-size:12.5px;color:#94a3b8;">등록된 신용카드가 없습니다. 아래 폼에서 카드를 추가해 보세요!</p></div>`;
        return;
      }

      listContainer.innerHTML = cards.map(c => {
        const unpaid = Number(c.unpaid_amount || 0);
        const count = Number(c.unpaid_count || 0);
        const hasUnpaid = unpaid > 0;
        const cardIdArgument = html(JSON.stringify(String(c.id)));

        return `
          <div class="ledger-credit-card-item">
            <div>
              <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div>
                  <span class="ledger-card-company-tag">${html(c.card_company)}</span>
                  <span class="ledger-card-owner-tag">(${html(c.owner || '모두')})</span>
                </div>
                <div style="display:flex;gap:4px;">
                  <button class="account-action-button" onclick="editLedgerCard(${cardIdArgument})" title="카드 정보 수정" type="button">✎</button>
                  <button class="account-action-button mini-delete-button" onclick="deleteLedgerCard(${cardIdArgument})" title="카드 삭제" type="button">🗑</button>
                </div>
              </div>
              <h4 class="ledger-card-name">${html(c.card_name)}</h4>
              <p class="ledger-card-meta">
                📅 매월 <strong class="ledger-card-day">${html(String(c.payment_day))}일</strong> 결제 · 결제계좌: <strong class="ledger-card-acct">${html(c.linked_account_name || '미지정')}</strong>
              </p>
              ${c.memo ? `<p class="ledger-card-memo">${html(c.memo)}</p>` : ''}
            </div>

            <div class="ledger-card-foot">
              <div>
                <span class="ledger-card-unpaid-label">청구 예정액</span>
                <div class="ledger-card-unpaid-val" style="color:${hasUnpaid ? '#f43f5e' : 'inherit'};">₩${number(unpaid, 0)} <span class="ledger-card-unpaid-count">(${count}건)</span></div>
              </div>
              <button class="button compact ${hasUnpaid ? 'primary' : 'secondary'}" type="button" onclick="openLedgerCardPayModal(${cardIdArgument})" ${!hasUnpaid ? 'disabled style="opacity:0.5;"' : ''}>
                💳 결제/정산
              </button>
            </div>
          </div>
        `;
      }).join("");
    }

    return Object.freeze({ renderLedgerCardsList });
  }

  window.WealthLedgerCardsView = Object.freeze({ create });
})();
