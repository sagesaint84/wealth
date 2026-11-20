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

    function cardFormControls() {
      return {
        form: document.getElementById("ledgerCardForm"),
        title: document.getElementById("ledgerCardFormTitle"),
        cancelButton: document.getElementById("ledgerCardFormCancelBtn"),
      };
    }

    function showCardFormMode({ title, cancelButton }, editing) {
      if (title) title.textContent = editing ? "✎ 카드 정보 수정" : "➕ 신규 카드 등록";
      if (cancelButton) cancelButton.style.display = editing ? "inline-block" : "none";
    }

    function resetCardForm() {
      const controls = cardFormControls();
      const { form } = controls;
      if (!form) return;
      form.reset();
      delete form.dataset.cardId;
      showCardFormMode(controls, false);
    }

    function editCardForm(card) {
      const controls = cardFormControls();
      const { form } = controls;
      if (!form || !card) return;

      form.dataset.cardId = card.id;
      form.querySelector("[name='card_company']").value = card.card_company || "현대카드";
      form.querySelector("[name='card_name']").value = card.card_name || "";
      form.querySelector("[name='owner']").value = card.owner || "모두";
      form.querySelector("[name='payment_day']").value = card.payment_day || "14";
      form.querySelector("[name='linked_account_id']").value = card.linked_account_id || "";
      form.querySelector("[name='memo']").value = card.memo || "";
      showCardFormMode(controls, true);
    }

    function showTransactionAccount(cardBox, accBox, accLabel, nextBalLabel, income) {
      if (cardBox) cardBox.style.display = "none";
      if (accBox) accBox.style.display = "block";
      if (accLabel) accLabel.textContent = income
        ? "🏦 입금 연동 계좌 선택 (선택 시 잔액 즉시 증가)"
        : "🏦 출금 연동 계좌 선택 (선택 시 잔액 즉시 차감)";
      if (nextBalLabel) nextBalLabel.textContent = income
        ? "적용 후 예상 잔액 (+입금):"
        : "적용 후 예상 잔액 (-출금):";
    }

    function applyTransactionType(type) {
      const payMethodTypeLabel = document.getElementById("ledgerTxPayMethodTypeLabel");
      if (payMethodTypeLabel) payMethodTypeLabel.style.display = type === "income" || type === "transfer" ? "none" : "block";
      if (type === "income" || type === "transfer") {
        showTransactionAccount(
          document.getElementById("ledgerTxCardSelectBox"),
          document.getElementById("ledgerTxAccountSelectBox"),
          document.getElementById("ledgerTxAccountSelectLabel"),
          document.getElementById("ledgerNextBalanceLabel"),
          type === "income",
        );
      }
    }

    function applyPaymentMethod(paymentMethod) {
      const cardBox = document.getElementById("ledgerTxCardSelectBox");
      const accBox = document.getElementById("ledgerTxAccountSelectBox");
      if (paymentMethod === "credit_card") {
        if (cardBox) cardBox.style.display = "block";
        if (accBox) accBox.style.display = "none";
        const previewBox = document.getElementById("ledgerBalancePreviewBox");
        if (previewBox) previewBox.style.display = "none";
      } else {
        showTransactionAccount(
          cardBox, accBox,
          document.getElementById("ledgerTxAccountSelectLabel"),
          document.getElementById("ledgerNextBalanceLabel"),
          false,
        );
      }
    }

    return Object.freeze({ render, renderLedgerCategories, resetCardForm, editCardForm, applyTransactionType, applyPaymentMethod });
  }
  window.WealthLedgerScreenController = Object.freeze({ create });
})();
