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

    function renderLedgerTrendFallback(trend, year, month) {
      if (window.WealthLedgerChartModule.state !== 'failed') return;
      const container = document.getElementById("ledgerTrendContainer");
      if (!container) return;
      if (!trend || trend.length === 0) {
        container.innerHTML = `<div class="empty" style="padding:30px 0;"><p style="margin:0;font-size:12.5px;">추이 데이터가 없습니다.</p></div>`;
        return;
      }

      const maxVal = Math.max(...trend.map(t => Math.max(t.income, t.expense)), 100000);

      const barsHtml = trend.map(t => {
        const incH = Math.round((t.income / maxVal) * 100);
        const expH = Math.round((t.expense / maxVal) * 100);
        const isCurrent = t.month === month && t.year === year;

        return `
          <div class="ledger-trend-col">
            <div class="ledger-trend-bars">
              <div class="ledger-bar-inc" style="height:${Math.max(2, incH)}%;" title="수입 ₩${number(t.income, 0)}"></div>
              <div class="ledger-bar-exp" style="height:${Math.max(2, expH)}%;" title="지출 ₩${number(t.expense, 0)}"></div>
            </div>
            <span class="ledger-trend-label ${isCurrent ? 'current' : ''}">${html(t.label)}</span>
          </div>
        `;
      }).join("");

      container.innerHTML = `
        <div class="ledger-trend-legend" style="display:flex;justify-content:flex-end;gap:12px;font-size:11px;margin-bottom:8px;">
          <span style="display:inline-flex;align-items:center;gap:4px;"><i style="width:8px;height:8px;border-radius:2px;background:#4ade80;display:inline-block;"></i> 수입</span>
          <span style="display:inline-flex;align-items:center;gap:4px;"><i style="width:8px;height:8px;border-radius:2px;background:#f43f5e;display:inline-block;"></i> 지출</span>
        </div>
        <div class="ledger-trend-chart">${barsHtml}</div>
      `;
    }

    function updateLedgerCategoryOptions(selectedCat = null, categories) {
      const type = document.getElementById("ledgerTxTypeSelect")?.value || "expense";
      const catSelect = document.getElementById("ledgerTxCategorySelect");
      if (!catSelect) return;

      const defaultCats = {
        expense: ["식비/외식", "주거/통신", "교통/차량", "쇼핑/생활용품", "교육/학습", "의료/건강", "문화/여가", "경조사/선물", "금융/보험/이자", "기타지출"],
        income: ["급여/상여", "사업소득", "배당/금융수익", "용돈/이전소득", "부수입/기타수입"],
        transfer: ["계좌이체/저축", "투자이체", "카드대금결제"]
      };

      const cats = (categories?.[type]) || defaultCats[type] || [];
      catSelect.innerHTML = cats.map(c => `<option value="${html(c)}" ${c === selectedCat ? 'selected' : ''}>${html(c)}</option>`).join("");
    }

    function populateLedgerAccountOptions(selectedAccountId = '', filterOwner = '모두', { rawDashboard, dashboard, rawBankAccounts, rawSavingsAccounts }) {
      const accSelect = document.getElementById("ledgerTxAccountSelect");
      const cardLinkedSelect = document.getElementById("ledgerCardLinkedAccountSelect");

      const src = rawDashboard || dashboard || {};
      const banks = src.bank_accounts || rawBankAccounts || [];
      const savings = src.savings_accounts || rawSavingsAccounts || [];
      const securities = src.accounts || [];

      const filterFn = (arr) => {
        if (!filterOwner || filterOwner === '모두') return arr;
        return arr.filter(x => (x.owner || '모두') === filterOwner || (x.owner || '모두') === '모두');
      };

      const filteredBanks = filterFn(banks);
      const filteredSavings = filterFn(savings);
      const filteredSecurities = filterFn(securities);

      let html = `<option value="">-- 계좌 연동 안 함 (단순 기록) --</option>`;

      if (filteredBanks.length > 0) {
        html += `<optgroup label="🏦 은행 자유입출금 통장">`;
        filteredBanks.forEach(b => {
          const name = `${b.bank_name || '은행'} ${b.account_name || b.alias || '자유통장'}`.trim();
          const bal = Number(b.balance) || 0;
          const ownerBadge = b.owner && b.owner !== '모두' ? ` (${b.owner})` : '';
          html += `<option value="${b.id}" data-balance="${bal}" data-name="${name}" ${b.id === selectedAccountId ? 'selected' : ''}>${name}${ownerBadge} (잔액 ₩${number(bal, 0)})</option>`;
        });
        html += `</optgroup>`;
      }

      if (filteredSavings.length > 0) {
        html += `<optgroup label="💰 예·적금 계좌">`;
        filteredSavings.forEach(s => {
          const name = `${s.bank_name || '은행'} ${s.product_name || '예적금'}`.trim();
          const bal = Number(s.balance) || Number(s.current_paid_amount) || 0;
          const ownerBadge = s.owner && s.owner !== '모두' ? ` (${s.owner})` : '';
          html += `<option value="${s.id}" data-balance="${bal}" data-name="${name}" ${s.id === selectedAccountId ? 'selected' : ''}>${name}${ownerBadge} (불입액 ₩${number(bal, 0)})</option>`;
        });
        html += `</optgroup>`;
      }

      if (filteredSecurities.length > 0) {
        html += `<optgroup label="📈 증권사 예수금 계좌">`;
        filteredSecurities.forEach(a => {
          const name = `${a.broker || a.name || '증권사'} (${a.account_type || '위탁'})`.trim();
          const bal = Number(a.cash_krw || a.cash || 0);
          const ownerBadge = a.owner && a.owner !== '모두' ? ` (${a.owner})` : '';
          html += `<option value="${a.id}" data-balance="${bal}" data-name="${name}" ${a.id === selectedAccountId ? 'selected' : ''}>${name}${ownerBadge} (예수금 ₩${number(bal, 0)})</option>`;
        });
        html += `</optgroup>`;
      }

      if (accSelect) {
        accSelect.innerHTML = html;
        if (selectedAccountId) accSelect.value = selectedAccountId;
      }

      // 신용카드 모달 내 출금통장 드롭다운에는 은행 통장 우선 주입
      if (cardLinkedSelect) {
        let bankHtml = `<option value="">-- 출금 결제계좌 선택 --</option>`;
        banks.forEach(b => {
          const name = `${b.bank_name || '은행'} ${b.account_name || b.alias || '통장'}`.trim();
          const ownerBadge = b.owner && b.owner !== '모두' ? ` (${b.owner})` : '';
          bankHtml += `<option value="${b.id}" data-name="${name}">${name}${ownerBadge} (잔액 ₩${number(b.balance || 0, 0)})</option>`;
        });
        cardLinkedSelect.innerHTML = bankHtml;
      }
    }

    function populateLedgerCardOptions(selectedCardId = '', filterOwner = '모두', cards) {
      const cardSelect = document.getElementById("ledgerTxCardSelect");
      if (!cardSelect) return;

      const filterCards = (!filterOwner || filterOwner === '모두')
        ? cards
        : cards.filter(c => (c.owner || '모두') === filterOwner || (c.owner || '모두') === '모두');

      let html = `<option value="">-- 등록된 신용카드 선택 --</option>`;
      if (filterCards.length > 0) {
        filterCards.forEach(c => {
          const unpaid = Number(c.unpaid_amount || 0);
          const label = `[${c.card_company}] ${c.card_name} (${c.owner || '모두'}, 매월 ${c.payment_day}일 결제) - 미결제 ₩${number(unpaid, 0)}`;
          html += `<option value="${c.id}" data-company="${c.card_company}" data-name="${c.card_name}" data-owner="${c.owner}" data-account-id="${c.linked_account_id || ''}" data-account-name="${c.linked_account_name || ''}" data-unpaid="${unpaid}" ${c.id === selectedCardId ? 'selected' : ''}>${label}</option>`;
        });
      } else {
        html += `<option value="" disabled>(등록된 카드가 없습니다. 카드 관리에서 등록해주세요)</option>`;
      }
      cardSelect.innerHTML = html;
      if (selectedCardId) cardSelect.value = selectedCardId;
    }

    function updateLedgerBalancePreview() {
      const form = document.getElementById("ledgerTxForm");
      const previewBox = document.getElementById("ledgerBalancePreviewBox");
      const prevEl = document.getElementById("ledgerPrevBalanceText");
      const nextEl = document.getElementById("ledgerNextBalanceText");
      if (!form || !previewBox || !prevEl || !nextEl) return;

      const typeVal = form.querySelector("[name='type']")?.value || "expense";
      const payMethodType = form.querySelector("[name='pay_method_type']")?.value || "credit_card";

      // 지출이면서 신용카드인 경우 계좌 잔액 프리뷰 불필요
      if (typeVal === "expense" && payMethodType === "credit_card") {
        previewBox.style.display = "none";
        return;
      }

      const accSelect = form.querySelector("[name='account_id']");
      const selectedOpt = accSelect?.selectedOptions?.[0];
      const accId = accSelect?.value;

      if (!accId || !selectedOpt || selectedOpt.value === "") {
        previewBox.style.display = "none";
        return;
      }

      const prevBal = Number(selectedOpt.dataset.balance) || 0;
      const amtVal = Number(form.querySelector("[name='amount']")?.value) || 0;

      let nextBal = prevBal;
      if (typeVal === "income") {
        nextBal = prevBal + amtVal;
      } else {
        nextBal = Math.max(0, prevBal - amtVal);
      }

      prevEl.textContent = `₩${number(prevBal, 0)}`;
      nextEl.textContent = `₩${number(nextBal, 0)}`;
      if (typeVal === "income") {
        nextEl.style.color = "#4ade80";
      } else {
        nextEl.style.color = "#38bdf8";
      }
      previewBox.style.display = "block";
    }

    function populateRecurringAccounts({ rawBankAccounts, dashboard }) {
      const sel = document.getElementById("recAccountSelect");
      if (!sel) return;

      const banks = rawBankAccounts || [];
      const secAccounts = dashboard?.accounts || [];
      let htmlOpts = '<option value="">-- 출금 통장 선택 (은행/증권 계좌) --</option>';

      if (banks.length > 0) {
        htmlOpts += '<optgroup label="🏦 일반 은행 통장">';
        banks.forEach(b => {
          const bName = b.bank_name || b.name || "은행";
          const pName = b.product_name || "입출금통장";
          const bal = Number(b.balance) || 0;
          htmlOpts += `<option value="${html(b.id)}">[${html(bName)}] ${html(pName)} (${html(b.owner || '모두')}) - 잔액 ₩${number(bal, 0)}</option>`;
        });
        htmlOpts += '</optgroup>';
      }

      if (secAccounts.length > 0) {
        htmlOpts += '<optgroup label="📈 증권사 계좌 (예수금)">';
        secAccounts.forEach(a => {
          const broker = a.broker || "증권사";
          const aName = a.name || "계좌";
          const cash = Number(a.cash_krw || a.cash || 0);
          htmlOpts += `<option value="${html(a.id)}">[${html(broker)}] ${html(aName)} (${html(a.owner || '모두')}) - 예수금 ₩${number(cash, 0)}</option>`;
        });
        htmlOpts += '</optgroup>';
      }

      sel.innerHTML = htmlOpts;
    }

    function handleLedgerFileSelect(input) {
      const file = input.files?.[0];
      const nameEl = document.getElementById("ledgerSelectedFileName");
      const uploadBtn = document.getElementById("ledgerFileUploadBtn");
      if (file) {
        if (nameEl) {
          nameEl.textContent = `선택된 파일: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
          nameEl.style.display = "block";
        }
        if (uploadBtn) uploadBtn.style.display = "inline-block";
      } else {
        if (nameEl) nameEl.style.display = "none";
        if (uploadBtn) uploadBtn.style.display = "none";
      }
    }

    function toggleRecurringAccountSelect() {
      const method = document.getElementById("recPayMethod")?.value;
      const grp = document.getElementById("recAccountGroup");
      if (grp) {
        grp.style.display = method === "자동이체" ? "block" : "none";
      }
    }

    function recurringFormControls() {
      return {
        editIdEl: document.getElementById("recEditId"),
        nameEl: document.getElementById("recName"),
        amountEl: document.getElementById("recAmount"),
        dayEl: document.getElementById("recDay"),
        catEl: document.getElementById("recCategory"),
        ownerEl: document.getElementById("recOwner"),
        payMethodEl: document.getElementById("recPayMethod"),
        acctSel: document.getElementById("recAccountSelect"),
        autoDeductEl: document.getElementById("recAutoDeduct"),
        titleEl: document.getElementById("recurringFormTitle"),
        addBtn: document.getElementById("addRecurringBtn"),
        cancelBtn: document.getElementById("cancelRecurringEditBtn"),
      };
    }

    function editRecurringForm(rec) {
      if (!rec) return;

      const {
        editIdEl, nameEl, amountEl, dayEl, catEl, ownerEl, payMethodEl,
        acctSel, autoDeductEl, titleEl, addBtn, cancelBtn,
      } = recurringFormControls();

      if (editIdEl) editIdEl.value = rec.id;
      if (nameEl) nameEl.value = rec.name || "";
      if (amountEl) amountEl.value = rec.amount || "";
      if (dayEl) dayEl.value = rec.day_of_month || 1;
      if (catEl) catEl.value = rec.category || "주거/통신";
      if (ownerEl) ownerEl.value = rec.owner || "모두";
      if (payMethodEl) payMethodEl.value = rec.pay_method || "자동이체";

      toggleRecurringAccountSelect();
      if (acctSel && rec.linked_account_id) {
        acctSel.value = rec.linked_account_id;
      }
      if (autoDeductEl) {
        autoDeductEl.checked = rec.auto_deduct ?? true;
      }

      if (titleEl) {
        titleEl.textContent = "✎ 고정지출 항목 수정";
        titleEl.style.color = "#38bdf8";
      }
      if (addBtn) {
        addBtn.textContent = "고정지출 항목 저장";
        addBtn.style.background = "linear-gradient(135deg, #0284c7, #0369a1)";
      }
      if (cancelBtn) {
        cancelBtn.style.display = "inline-block";
      }

      nameEl?.focus();
    }

    function cancelRecurringEdit() {
      const {
        editIdEl, nameEl, amountEl, dayEl, catEl, ownerEl, payMethodEl,
        acctSel, autoDeductEl, titleEl, addBtn, cancelBtn,
      } = recurringFormControls();

      if (editIdEl) editIdEl.value = "";
      if (nameEl) nameEl.value = "";
      if (amountEl) amountEl.value = "";
      if (dayEl) dayEl.value = "1";
      if (catEl) catEl.value = "주거/통신";
      if (ownerEl) ownerEl.value = "모두";
      if (payMethodEl) payMethodEl.value = "자동이체";

      toggleRecurringAccountSelect();
      if (acctSel) acctSel.value = "";
      if (autoDeductEl) autoDeductEl.checked = true;

      if (titleEl) {
        titleEl.textContent = "➕ 새 고정지출 추가";
        titleEl.style.color = "#c084fc";
      }
      if (addBtn) {
        addBtn.textContent = "고정지출 항목 추가";
        addBtn.style.background = "linear-gradient(135deg, #a855f7, #7c3aed)";
      }
      if (cancelBtn) {
        cancelBtn.style.display = "none";
      }
    }

    function openLedgerExcelModal() {
      document.getElementById("ledgerExcelDialog")?.showModal();
    }

    function filterLedgerList(transactions) {
      if (!transactions) return;
      const typeFilter = document.getElementById("ledgerFilterType")?.value || "all";
      const searchText = document.getElementById("ledgerSearchInput")?.value || "";
      const filtered = window.WealthLedgerTransactionsModel.filterTransactions(
        transactions, typeFilter, searchText,
      );

      renderLedgerTransactions(filtered);
    }

    function showCardPaymentDialog(card) {
      const dialog = document.getElementById("ledgerCardPayDialog");
      const nameEl = document.getElementById("ledgerPayCardName");
      const unpaidEl = document.getElementById("ledgerPayUnpaidAmount");
      const accEl = document.getElementById("ledgerPayAccountName");
      const dateInput = document.getElementById("ledgerPayDateInput");
      const amountInput = document.getElementById("ledgerPayAmountInput");

      if (nameEl) nameEl.textContent = `[${card.card_company}] ${card.card_name} (${card.owner || '모두'})`;
      if (unpaidEl) unpaidEl.textContent = `₩${number(card.unpaid_amount || 0, 0)}`;
      if (accEl) accEl.textContent = card.linked_account_name || "(연결된 결제계좌 없음)";
      if (dateInput) dateInput.value = new Date().toISOString().slice(0, 10);
      document.getElementById("ledgerPaySplitDateWrap")?._syncFromNative?.();
      if (amountInput) amountInput.value = card.unpaid_amount || 0;

      if (dialog) dialog.showModal();
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

    return Object.freeze({
      render, renderLedgerCategories, renderLedgerTrendFallback,
      updateLedgerCategoryOptions, populateLedgerAccountOptions, populateLedgerCardOptions,
      updateLedgerBalancePreview, populateRecurringAccounts, handleLedgerFileSelect,
      filterLedgerList, toggleRecurringAccountSelect, editRecurringForm, cancelRecurringEdit,
      showCardPaymentDialog, openLedgerExcelModal,
      resetCardForm, editCardForm, applyTransactionType, applyPaymentMethod,
    });
  }
  window.WealthLedgerScreenController = Object.freeze({ create });
})();
