(() => {
  "use strict";

  function create({ document, html, number }) {
    function renderLedgerTransactions(txs) {
      const container = document.getElementById("ledgerTxListContainer");
      const countBadge = document.getElementById("ledgerTxCountBadge");
      if (!container) return;

      if (countBadge) countBadge.textContent = `${txs.length}건`;

      if (!txs || txs.length === 0) {
        container.innerHTML = `<div class="empty" style="padding:40px 0;"><p style="margin:0;font-size:13px;color:#94a3b8;">등록된 거래 내역이 없습니다. [➕ 내역 추가]를 눌러 첫 거래를 추가해 보세요!</p></div>`;
        return;
      }

      const rowsHtml = txs.map(t => {
        const isIncome = t.type === "income";
        const isTransfer = t.type === "transfer";
        const typeLabel = isIncome ? "수입" : (isTransfer ? "이체" : "지출");
        const badgeClass = isIncome ? "income" : (isTransfer ? "transfer" : "expense");
        const amtColor = isIncome ? "#4ade80" : (isTransfer ? "#38bdf8" : "#f43f5e");
        const amtSign = isIncome ? "+" : (isTransfer ? "⇄ " : "-");

        return `
          <tr class="ledger-tx-row">
            <td class="ledger-tx-cell-date">${html(t.date)}</td>
            <td class="ledger-tx-cell-type"><span class="ledger-badge ${badgeClass}">${typeLabel}</span></td>
            <td class="ledger-tx-cell-cat"><span class="ledger-cat-badge">${html(t.category)}</span></td>
            <td class="ledger-tx-cell-merchant">
              <strong>${html(t.merchant || t.description || '-')}</strong>
              ${t.memo ? `<small class="ledger-tx-memo">${html(t.memo)}</small>` : ''}
            </td>
            <td class="ledger-tx-cell-owner"><span class="saving-owner-badge">${html(t.owner || '모두')}</span></td>
            <td class="ledger-tx-cell-pay">
              <span>${html(t.pay_method || '-')}</span>
              ${t.is_card_payment && !t.is_settled ? `<span class="ledger-status-pill unsettled">미결제</span>` : ''}
              ${t.is_card_payment && t.is_settled ? `<span class="ledger-status-pill settled">정산완료</span>` : ''}
            </td>
            <td class="ledger-tx-cell-amt" style="color:${amtColor};">
              ${amtSign}₩${number(t.amount, 0)}
            </td>
            <td style="text-align:right;white-space:nowrap;">
              <button class="account-action-button" onclick="openLedgerTxModal('${t.id}')" title="수정" type="button">✎</button>
              <button class="account-action-button mini-delete-button" onclick="deleteLedgerTransaction('${t.id}')" title="삭제" type="button">🗑️</button>
            </td>
          </tr>
        `;
      }).join("");

      container.innerHTML = `
        <table class="ledger-tx-table">
          <thead>
            <tr>
              <th>일자</th>
              <th>구분</th>
              <th>카테고리</th>
              <th>내용 / 가맹점</th>
              <th>소유자</th>
              <th>결제수단</th>
              <th style="text-align:right;">금액</th>
              <th style="text-align:right;">관리</th>
            </tr>
          </thead>
          <tbody>${rowsHtml}</tbody>
        </table>
      `;
    }

    return Object.freeze({ renderLedgerTransactions });
  }

  window.WealthLedgerTransactionsView = Object.freeze({ create });
})();
