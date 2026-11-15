(() => {
  'use strict';

  function create({ document, $, html, number, renderLedgerChart, renderLedgerTransactions }) {
    function render(data) {
      // 1. 헤더 월 텍스트 & 소유자 뱃지 & 월 피커 동기화
      const monthText = document.getElementById("ledgerCurrentMonthText");
      if (monthText) monthText.textContent = `${data.year}년 ${data.month}월`;
      const monthPicker = document.getElementById("ledgerMonthPicker");
      if (monthPicker) monthPicker.value = `${data.year}-${String(data.month).padStart(2, '0')}`;
      const ownerPill = document.getElementById("ledgerOwnerPill");
      if (ownerPill) ownerPill.textContent = `소유자: ${data.owner || "모두"}`;

      // 2. 요약 카드 4종
      if ($("#ledgerTotalIncomeVal")) $("#ledgerTotalIncomeVal").textContent = `₩${number(data.total_income, 0)}`;
      if ($("#ledgerTotalExpenseVal")) $("#ledgerTotalExpenseVal").textContent = `₩${number(data.total_expense, 0)}`;
      if ($("#ledgerNetSavingsVal")) {
        const sVal = data.net_savings;
        const prefix = sVal > 0 ? "+" : "";
        $("#ledgerNetSavingsVal").textContent = `${prefix}₩${number(sVal, 0)}`;
        $("#ledgerNetSavingsVal").style.color = sVal >= 0 ? "#38bdf8" : "#f43f5e";
      }
      if ($("#ledgerSavingsRateVal")) $("#ledgerSavingsRateVal").textContent = `저축률 ${data.savings_rate}%`;
      if ($("#ledgerRecurringTotalVal")) $("#ledgerRecurringTotalVal").textContent = `₩${number(data.recurring_expense_total, 0)}`;

      // 3. 카테고리 지출 분석 렌더링
      renderLedgerCategories(data.category_expenses || []);

      // 4. One chart owner; wait for the loader before choosing failure fallback.
      void renderLedgerChart();

      // 5. 상세 거래 내역 타임라인 렌더링
      renderLedgerTransactions(data.transactions || []);
    }

    function renderLedgerCategories(cats) {
      const container = document.getElementById("ledgerCategoryContainer");
      if (!container) return;
      if (!cats || cats.length === 0) {
        container.innerHTML = `<div class="empty" style="padding:30px 0;"><p style="margin:0;font-size:12.5px;">이번 달 지출 내역이 없습니다.</p></div>`;
        return;
      }

      container.innerHTML = cats.map(c => {
        return `
          <div class="ledger-cat-row">
            <div class="ledger-cat-head">
              <span class="ledger-cat-name">${html(c.category)}</span>
              <span class="ledger-cat-amt">₩${number(c.amount, 0)} <small class="ledger-cat-pct">(${c.percent}%)</small></span>
            </div>
            <div class="ledger-cat-bar-track">
              <div class="ledger-cat-bar-fill" style="width:${Math.min(100, Math.max(2, c.percent))}%;"></div>
            </div>
          </div>
        `;
      }).join("");
    }

    return Object.freeze({ render, renderLedgerCategories });
  }
  window.WealthLedgerScreenController = Object.freeze({ create });
})();
