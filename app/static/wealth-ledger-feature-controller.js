/* Ledger selection, reads and write workflows. The screen and views own rendering. */
(() => {
  'use strict';

  function create({
    window, document, $, html, number, api, toast, busy, loadDashboard,
    setupAutoAdvancingDateInput, getKstYearMonth, shiftYearMonth, parseYearMonth,
    getOwner, getUsername, getReadEpoch, getAccounts, invalidateStartupReads,
  }) {
    const initialPeriod = getKstYearMonth();
    let currentLedgerYear = initialPeriod.year;
    let currentLedgerMonth = initialPeriod.month;
    let rawLedgerData = null;
    let annualView = false;
    let periodRenderer = null;
    let pendingRead = null;
    let readSequence = 0;

    function invalidateRead() {
      readSequence++;
      pendingRead = null;
    }

    // File and OCR imports keep their existing fetch contracts, outside the shared API wrapper.
    function invalidateAfterExternalWrite() {
      invalidateRead();
      invalidateStartupReads();
    }

    function setData(data) {
      rawLedgerData = data;
    }

    function isAnnualView() {
      return annualView;
    }

    function setAnnualView(value) {
      annualView = Boolean(value);
    }

    function selectAnnualYear(year) {
      currentLedgerYear = year;
      setAnnualView(true);
      return loadLedger();
    }

    function selectMonth(year, month) {
      setAnnualView(false);
      currentLedgerYear = year;
      currentLedgerMonth = month;
      return loadLedger();
    }

    function setPeriodRenderer(render) {
      periodRenderer = render;
    }

    function readScope() {
      return {
        owner: getOwner() || "모두",
        username: getUsername(),
        year: Number(currentLedgerYear) || getKstYearMonth().year,
        month: Number(currentLedgerMonth) || 1,
        annual: annualView,
        epoch: getReadEpoch(),
      };
    }

    function isVisible() {
      return window.WealthStartup?.visible('ledgerSectionPanel') !== false;
    }

    async function loadLedger() {
      if (!isVisible()) {
        window.WealthStartup?.count('inactive_skipped');
        return;
      }
      const scope = readScope();
      const key = JSON.stringify(scope);
      if (pendingRead?.key === key) return pendingRead.promise;

      const entry = { key, sequence: ++readSequence, promise: null };
      pendingRead = entry;
      const isCurrent = () => entry.sequence === readSequence && isVisible() && key === JSON.stringify(readScope());
      const { owner, year, month, annual } = scope;
      entry.promise = (async () => {
        try {
          let data;
          if (annual) {
            const rows = [];
            for (let monthIndex = 1; monthIndex <= 12; monthIndex++) {
              const row = await window.WealthLedgerData.loadMonth(api, year, monthIndex, owner);
              if (!isCurrent()) {
                window.WealthStartup?.count('stale_ignored');
                return;
              }
              rows.push(row);
            }
            data = window.WealthLedgerData.mergeAnnualLedger(rows, owner, year);
          } else {
            data = await window.WealthLedgerData.loadMonth(api, year, month, owner);
          }
          if (!isCurrent()) {
            window.WealthStartup?.count('stale_ignored');
            return;
          }
          if (!data) return;
          renderLedger(data);
          return data;
        } catch (err) {
          console.error("가계부 로드 오류:", err);
        } finally {
          if (pendingRead === entry) pendingRead = null;
        }
      })();
      return entry.promise;
    }

    function renderScreen(data) {
      window.WealthStartup?.count('render');
      setData(data);
      ledgerScreenController.render(data);
    }

    function renderLedger(data) {
      if (!data) return;
      if (periodRenderer) periodRenderer(data, renderScreen);
      else renderScreen(data);
    }

    // Absence of the API means loading, never failure. The production loader settles
    // this promise only after registration or an explicit script/dependency failure.
    let settleLedgerChartModule;
    window.WealthLedgerChartModule = {
      state: 'loading',
      ready: new Promise(resolve => { settleLedgerChartModule = resolve; }),
      settle(state) {
        if (this.state !== 'loading') return;
        this.state = state;
        settleLedgerChartModule(state);
      },
    };
    window.addEventListener('wealth:unified-ready', () => window.WealthLedgerChartModule.settle('ready'), { once: true });
    let ledgerChartRenderSequence = 0;
    async function renderLedgerChart() {
      const sequence = ++ledgerChartRenderSequence;
      const state = await window.WealthLedgerChartModule.ready;
      if (sequence !== ledgerChartRenderSequence || !rawLedgerData) return;
      if (state === 'ready') await window.WealthUnifiedTimeseries.renderLedger(rawLedgerData);
      else renderLedgerTrendFallback(rawLedgerData.monthly_trend || []);
    }
    const ledgerScreenController = window.WealthLedgerScreenController.create({ document, $, html, number, renderLedgerChart, renderLedgerTransactions });
    const {
      renderLedgerCategories, updateLedgerBalancePreview, handleLedgerFileSelect,
      toggleRecurringAccountSelect, cancelRecurringEdit, openLedgerExcelModal,
    } = ledgerScreenController;

    function filterLedgerList() {
      ledgerScreenController.filterLedgerList(rawLedgerData?.transactions);
    }

    function editRecurringItem(recId) {
      const rec = (rawLedgerData?.recurring || []).find(r => r.id === recId);
      ledgerScreenController.editRecurringForm(rec);
    }

    function renderLedgerTrendFallback(trend) {
      ledgerScreenController.renderLedgerTrendFallback(trend, currentLedgerYear, currentLedgerMonth);
    }

    const ledgerTransactionsView = window.WealthLedgerTransactionsView.create({ document, html, number });
    function renderLedgerTransactions(txs) {
      return ledgerTransactionsView.renderLedgerTransactions(txs);
    }

    function updateLedgerCategoryOptions(selectedCat = null) {
      return ledgerScreenController.updateLedgerCategoryOptions(selectedCat, rawLedgerData?.categories);
    }

    function populateLedgerAccountOptions(selectedAccountId = '', filterOwner = '모두') {
      return ledgerScreenController.populateLedgerAccountOptions(selectedAccountId, filterOwner, getAccounts());
    }

    function populateLedgerCardOptions(selectedCardId = '', filterOwner = '모두') {
      return ledgerScreenController.populateLedgerCardOptions(selectedCardId, filterOwner, rawLedgerData?.cards || []);
    }

    function onLedgerTxTypeChanged() {
      const form = document.getElementById("ledgerTxForm");
      if (!form) return;
      const typeVal = form.querySelector("[name='type']")?.value || "expense";

      updateLedgerCategoryOptions();
      ledgerScreenController.applyTransactionType(typeVal);

      if (typeVal !== "income" && typeVal !== "transfer") {
        onLedgerPayMethodTypeChanged();
        return;
      }
      updateLedgerBalancePreview();
    }

    function onLedgerPayMethodTypeChanged() {
      const form = document.getElementById("ledgerTxForm");
      if (!form) return;
      const payMethodType = form.querySelector("[name='pay_method_type']")?.value || "credit_card";
      const owner = form.querySelector("[name='owner']")?.value || getOwner() || "모두";

      ledgerScreenController.applyPaymentMethod(payMethodType);
      if (payMethodType === "credit_card") {
        populateLedgerCardOptions(form.querySelector("[name='card_id']")?.value, owner);
      } else {
        updateLedgerBalancePreview();
      }
    }

    function onLedgerTxOwnerChanged() {
      const form = document.getElementById("ledgerTxForm");
      if (!form) return;
      const owner = form.querySelector("[name='owner']")?.value || "모두";
      const curAcc = form.querySelector("[name='account_id']")?.value || "";
      const curCard = form.querySelector("[name='card_id']")?.value || "";
      populateLedgerAccountOptions(curAcc, owner);
      populateLedgerCardOptions(curCard, owner);
      updateLedgerBalancePreview();
    }

    function onLedgerCardSelectChanged() {
      // 신용카드 선택 변경 시 동작
    }

    async function openLedgerTxModal(txId = null) {
      const dialog = document.getElementById("ledgerTxDialog");
      const form = document.getElementById("ledgerTxForm");
      const title = document.getElementById("ledgerTxDialogTitle");
      if (!dialog || !form) return;

      await window.WealthTransactionDefaults?.load();

      setupAutoAdvancingDateInput("#ledgerTxSplitDateWrap");

      form.dataset.txId = txId || "";

      // 입력 변경 시 실시간 잔액 미리보기 이벤트 연결
      const amountInput = form.querySelector("[name='amount']");
      if (amountInput && !amountInput.dataset.previewBound) {
        amountInput.dataset.previewBound = "true";
        amountInput.addEventListener("input", updateLedgerBalancePreview);
      }

      if (txId && rawLedgerData?.transactions) {
        const tx = rawLedgerData.transactions.find(t => t.id === txId);
        if (tx) {
          if (title) title.textContent = "수입 / 지출 내역 수정";
          form.querySelector("[name='date']").value = tx.date || new Date().toISOString().slice(0, 10);
          document.getElementById("ledgerTxSplitDateWrap")?._syncFromNative?.();
          form.querySelector("[name='type']").value = tx.type || "expense";
          form.querySelector("[name='owner']").value = tx.owner || "모두";
          form.querySelector("[name='amount']").value = tx.amount || "";
          form.querySelector("[name='merchant']").value = tx.merchant || tx.description || "";
          form.querySelector("[name='memo']").value = tx.memo || "";

          // 카드 지출인지 체크
          const isCard = Boolean(tx.card_id || tx.is_card_payment);
          const payMethodTypeSelect = form.querySelector("[name='pay_method_type']");
          if (payMethodTypeSelect) {
            payMethodTypeSelect.value = isCard ? "credit_card" : "bank_account";
          }

          onLedgerTxTypeChanged();
          updateLedgerCategoryOptions(tx.category);
          populateLedgerAccountOptions(tx.account_id || "", tx.owner || "모두");
          populateLedgerCardOptions(tx.card_id || "", tx.owner || "모두");
          updateLedgerBalancePreview();
          window.WealthTransactionDefaults?.restoreInterest(tx);
          dialog.showModal();
          return;
        }
      }

      if (title) title.textContent = "수입 / 지출 내역 등록";
      form.reset();
      form.querySelector("[name='date']").value = new Date().toISOString().slice(0, 10);
      document.getElementById("ledgerTxSplitDateWrap")?._syncFromNative?.();
      form.querySelector("[name='owner']").value = getOwner() || "모두";
      form.querySelector("[name='type']").value = "expense";
      const payMethodTypeSelect = form.querySelector("[name='pay_method_type']");
      if (payMethodTypeSelect) payMethodTypeSelect.value = "credit_card";

      onLedgerTxTypeChanged();
      populateLedgerAccountOptions("", getOwner() || "모두");
      populateLedgerCardOptions("", getOwner() || "모두");
      updateLedgerBalancePreview();
      form.dataset.newTxId = crypto.randomUUID();
      window.WealthTransactionDefaults?.apply();
      window.WealthTransactionDefaults?.restoreInterest(null);
      dialog.showModal();
    }

    async function saveLedgerTransaction() {
      const form = document.getElementById("ledgerTxForm");
      if (!form) return;

      const txId = form.dataset.txId;
      const dateVal = form.querySelector("[name='date']")?.value;
      const typeVal = form.querySelector("[name='type']")?.value;
      const amountVal = Number(form.querySelector("[name='amount']")?.value) || 0;
      const categoryVal = form.querySelector("[name='category']")?.value;
      const ownerVal = form.querySelector("[name='owner']")?.value || "모두";
      const merchantVal = (form.querySelector("[name='merchant']")?.value || "").trim();
      const memoVal = (form.querySelector("[name='memo']")?.value || "").trim();

      if (!amountVal || amountVal <= 0) {
        alert("금액을 0원보다 크게 입력해 주세요.");
        return;
      }
      if (!merchantVal) {
        alert("내용(가맹점)을 입력해 주세요.");
        return;
      }

      let payMethodVal = "신용/체크카드";
      let cardIdVal = "";
      let cardNameVal = "";
      let accountIdVal = "";
      let accountNameVal = "";
      let isCard = false;

      if (typeVal === "income") {
        const accSelect = form.querySelector("[name='account_id']");
        const selectedOpt = accSelect?.selectedOptions?.[0];
        accountIdVal = accSelect?.value || "";
        accountNameVal = selectedOpt ? (selectedOpt.dataset.name || selectedOpt.textContent || "") : "";
        payMethodVal = accountNameVal ? `입금 (${accountNameVal})` : "계좌입금";
      } else if (typeVal === "transfer") {
        const accSelect = form.querySelector("[name='account_id']");
        const selectedOpt = accSelect?.selectedOptions?.[0];
        accountIdVal = accSelect?.value || "";
        accountNameVal = selectedOpt ? (selectedOpt.dataset.name || selectedOpt.textContent || "") : "";
        payMethodVal = accountNameVal ? `이체출금 (${accountNameVal})` : "계좌이체";
      } else {
        // expense
        const payMethodType = form.querySelector("[name='pay_method_type']")?.value || "credit_card";
        if (payMethodType === "credit_card") {
          const cardSelect = form.querySelector("[name='card_id']");
          const selectedCardOpt = cardSelect?.selectedOptions?.[0];
          cardIdVal = cardSelect?.value || "";
          if (cardIdVal && selectedCardOpt) {
            cardNameVal = selectedCardOpt.dataset.name ? `[${selectedCardOpt.dataset.company || '신용카드'}] ${selectedCardOpt.dataset.name}` : selectedCardOpt.textContent;
            payMethodVal = cardNameVal;
            isCard = true;
          } else {
            payMethodVal = "신용카드";
          }
        } else if (payMethodType === "cash") {
          payMethodVal = "현금";
        } else {
          // bank_account
          const accSelect = form.querySelector("[name='account_id']");
          const selectedOpt = accSelect?.selectedOptions?.[0];
          accountIdVal = accSelect?.value || "";
          accountNameVal = selectedOpt ? (selectedOpt.dataset.name || selectedOpt.textContent || "") : "";
          payMethodVal = accountNameVal ? `체크/계좌출금 (${accountNameVal})` : "계좌출금";
        }
      }

      const payload = {
        ...(txId ? {} : {id: form.dataset.newTxId}),
        mirror_to_dividend_interest: Boolean(document.getElementById('ledgerInterestLink')?.checked),
        date: dateVal,
        type: typeVal,
        amount: amountVal,
        category: categoryVal,
        owner: ownerVal,
        pay_method: payMethodVal,
        card_id: cardIdVal,
        card_name: cardNameVal,
        is_card_payment: isCard,
        account_id: accountIdVal,
        account_name: accountNameVal,
        merchant: merchantVal,
        memo: memoVal
      };

      try {
        if (txId) {
          await api(`/api/ledger/transactions/${txId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          toast("내역이 수정되었습니다.");
        } else {
          await api("/api/ledger/transactions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          toast("내역이 등록되었습니다.");
        }
        document.getElementById("ledgerTxDialog")?.close();
        await loadLedger();
        // 은행 계좌 연동 변동 시 대시보드 새로고침
        if (accountIdVal && !isCard) {
          loadDashboard();
        }
      } catch (err) {
        alert(`저장 중 오류: ${err.message}`);
      }
    }

    // ---------------------------------------------------------------------------
    // Credit Cards Management & Billing Settlement UI
    // ---------------------------------------------------------------------------

    let activePayTargetCard = null;

    async function openLedgerCardsModal() {
      const dialog = document.getElementById("ledgerCardsDialog");
      if (!dialog) return;
      resetLedgerCardForm();
      populateLedgerAccountOptions();
      await refreshLedgerCardsList();
      dialog.showModal();
    }

    async function refreshLedgerCardsList() {
      const listContainer = document.getElementById("ledgerCardsList");
      if (!listContainer) return;

      try {
        const owner = getOwner() || "모두";
        const cards = await globalThis.WealthLedgerData.loadCards(api, owner);
        if (rawLedgerData) rawLedgerData.cards = cards;
        renderLedgerCardsList(cards || []);
      } catch (err) {
        console.error("카드 목록 조회 오류:", err);
      }
    }

    const ledgerCardsView = window.WealthLedgerCardsView.create({ document, html, number });
    function renderLedgerCardsList(cards) { return ledgerCardsView.renderLedgerCardsList(cards); }

    function resetLedgerCardForm() {
      ledgerScreenController.resetCardForm();
    }

    function editLedgerCard(cardId) {
      if (!cardId) return;
      const card = (rawLedgerData?.cards || []).find(c => c.id === cardId);
      ledgerScreenController.editCardForm(card);
    }

    async function saveLedgerCard() {
      const form = document.getElementById("ledgerCardForm");
      if (!form) return;

      const cardId = form.dataset.cardId;
      const company = form.querySelector("[name='card_company']")?.value;
      const name = (form.querySelector("[name='card_name']")?.value || "").trim();
      const owner = form.querySelector("[name='owner']")?.value || "모두";
      const day = Number(form.querySelector("[name='payment_day']")?.value) || 14;
      const linkedAccSelect = form.querySelector("[name='linked_account_id']");
      const linkedAccId = linkedAccSelect?.value || "";
      const linkedAccOpt = linkedAccSelect?.selectedOptions?.[0];
      const linkedAccName = linkedAccOpt ? (linkedAccOpt.dataset.name || linkedAccOpt.textContent || "") : "";
      const memo = (form.querySelector("[name='memo']")?.value || "").trim();

      if (!name) {
        alert("카드명을 입력해 주세요.");
        return;
      }

      const payload = {
        card_company: company,
        card_name: name,
        owner: owner,
        payment_day: day,
        linked_account_id: linkedAccId,
        linked_account_name: linkedAccName,
        memo: memo
      };

      try {
        if (cardId) {
          await api(`/api/ledger/cards/${cardId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          toast("카드 정보가 수정되었습니다.");
        } else {
          await api("/api/ledger/cards", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          toast("신규 카드가 등록되었습니다.");
        }
        resetLedgerCardForm();
        await refreshLedgerCardsList();
        await loadLedger();
      } catch (err) {
        alert(`카드 저장 오류: ${err.message}`);
      }
    }

    async function deleteLedgerCard(cardId) {
      if (!confirm("이 카드를 삭제하시겠습니까? (이전 거래 내역은 유지됩니다)")) return;
      try {
        await api(`/api/ledger/cards/${cardId}`, { method: "DELETE" });
        toast("카드가 삭제되었습니다.");
        await refreshLedgerCardsList();
        await loadLedger();
      } catch (err) {
        alert(`카드 삭제 오류: ${err.message}`);
      }
    }

    function openLedgerCardPayModal(cardId) {
      const cards = rawLedgerData?.cards || [];
      const card = cards.find(c => c.id === cardId);
      if (!card) return;

      setupAutoAdvancingDateInput("#ledgerPaySplitDateWrap");

      activePayTargetCard = card;
      ledgerScreenController.showCardPaymentDialog(card);
    }

    async function executeCardPayment() {
      if (!activePayTargetCard) return;
      const dateInput = document.getElementById("ledgerPayDateInput");
      const amountInput = document.getElementById("ledgerPayAmountInput");
      const payDate = dateInput?.value || new Date().toISOString().slice(0, 10);
      const payAmount = Number(amountInput?.value) || 0;

      if (payAmount <= 0) {
        alert("결제 금액은 0원보다 커야 합니다.");
        return;
      }

      const payload = {
        date: payDate,
        amount: payAmount,
        account_id: activePayTargetCard.linked_account_id || "",
        account_name: activePayTargetCard.linked_account_name || ""
      };

      try {
        const res = await api(`/api/ledger/cards/${activePayTargetCard.id}/pay`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        toast(res.message || "카드대금 결제 및 정산이 완료되었습니다.");
        document.getElementById("ledgerCardPayDialog")?.close();
        await refreshLedgerCardsList();
        await loadLedger();
        if (activePayTargetCard.linked_account_id) {
          loadDashboard();
        }
      } catch (err) {
        alert(`결제 처리 오류: ${err.message}`);
      }
    }

    async function deleteLedgerTransaction(txId) {
      if (!confirm("이 거래 내역을 삭제하시겠습니까?")) return;
      try {
        await api(`/api/ledger/transactions/${txId}`, { method: "DELETE" });
        toast("내역이 삭제되었습니다.");
        await loadLedger();
      } catch (err) {
        alert(`삭제 중 오류: ${err.message}`);
      }
    }

    // 고정지출 모달 관리
    const ledgerRecurringView = window.WealthLedgerRecurringView.create({ html, number });

    function openLedgerRecurringModal() {
      const dialog = document.getElementById("ledgerRecurringDialog");
      const listContainer = document.getElementById("ledgerRecurringList");
      if (!dialog || !listContainer) return;

      ledgerScreenController.populateRecurringAccounts(getAccounts());
      toggleRecurringAccountSelect();

      const recs = rawLedgerData?.recurring || [];
      const now = new Date();
      const curPrefix = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

      const items = recs.map(r => {
        const isDeductedThisMonth = (r.last_deducted_date || "").startsWith(curPrefix);
        const status = r.auto_deduct && r.linked_account_id
          ? (isDeductedThisMonth ? "deducted" : "pending")
          : "manual";
        return { r, status };
      });
      ledgerRecurringView.renderList(listContainer, items);

      dialog.showModal();
    }

    async function triggerRecurringProcess() {
      try {
        const res = await api("/api/ledger/recurring/process", { method: "POST" });
        toast(res.message || "자동이체 출금 정산이 완료되었습니다.");
        await loadLedger();
        await loadDashboard();
        openLedgerRecurringModal();
      } catch (err) {
        alert(`자동이체 정산 오류: ${err.message}`);
      }
    }

    async function saveNewRecurringItem() {
      const editId = document.getElementById("recEditId")?.value.trim();
      const name = document.getElementById("recName")?.value.trim();
      const amount = Number(document.getElementById("recAmount")?.value) || 0;
      const day = Number(document.getElementById("recDay")?.value) || 1;
      const category = document.getElementById("recCategory")?.value;
      const owner = document.getElementById("recOwner")?.value || "모두";
      const payMethod = document.getElementById("recPayMethod")?.value || "자동이체";
      const isAutoTransfer = payMethod === "자동이체";

      const acctSel = document.getElementById("recAccountSelect");
      const linked_account_id = isAutoTransfer ? (acctSel?.value || "").trim() : "";
      let linked_account_name = "";
      if (isAutoTransfer && acctSel && acctSel.selectedIndex > 0) {
        const optText = acctSel.options[acctSel.selectedIndex].text;
        linked_account_name = optText.split(" - 잔액")[0].split(" - 예수금")[0].trim();
      }
      const auto_deduct = isAutoTransfer ? (document.getElementById("recAutoDeduct")?.checked ?? true) : false;

      if (!name || amount <= 0) {
        alert("항목 이름과 올바른 금액을 입력해 주세요.");
        return;
      }

      if (isAutoTransfer && auto_deduct && !linked_account_id) {
        alert("자동이체 출금 처리를 위해 연동할 통장(계좌)을 선택해 주세요.");
        return;
      }

      const payload = {
        name,
        amount,
        day_of_month: day,
        category,
        owner,
        pay_method: payMethod,
        linked_account_id,
        linked_account_name,
        auto_deduct,
      };

      try {
        if (editId) {
          await api(`/api/ledger/recurring/${editId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          toast(`[${name}] 고정지출 항목이 수정되었습니다.`);
        } else {
          await api("/api/ledger/recurring", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          toast(`[${name}] 고정지출 항목이 등록되었습니다.`);
        }

        cancelRecurringEdit();
        await loadLedger();
        await loadDashboard();
        openLedgerRecurringModal();
      } catch (err) {
        alert(`고정지출 저장 오류: ${err.message}`);
      }
    }

    async function deleteRecurringItem(recId) {
      if (!confirm("이 고정지출 항목을 삭제하시겠습니까?")) return;
      try {
        await api(`/api/ledger/recurring/${recId}`, { method: "DELETE" });
        toast("고정지출 항목이 삭제되었습니다.");
        await loadLedger();
        await loadDashboard();
        openLedgerRecurringModal();
      } catch (err) {
        alert(`삭제 중 오류: ${err.message}`);
      }
    }

    // 엑셀/텍스트 일괄 가져오기
    async function uploadLedgerFile() {
      const fileInput = document.getElementById("ledgerFileInput");
      const file = fileInput?.files?.[0];
      const owner = document.getElementById("ledgerImportOwner")?.value || "모두";
      const uploadBtn = document.getElementById("ledgerFileUploadBtn");

      if (!file) {
        alert("업로드할 엑셀(.xlsx) 또는 CSV 파일을 선택해 주세요.");
        return;
      }

      const formData = new FormData();
      formData.append("file", file);
      formData.append("owner", owner);

      if (uploadBtn) busy(uploadBtn, true);

      try {
        const res = await fetch("/api/ledger/import-file", {
          method: "POST",
          body: formData,
          credentials: "include"
        });
        const result = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(result.detail || result.message || "파일 업로드에 실패했습니다.");

        document.getElementById("ledgerExcelDialog")?.close();
        if (fileInput) fileInput.value = "";
        const nameEl = document.getElementById("ledgerSelectedFileName");
        if (nameEl) nameEl.style.display = "none";
        if (uploadBtn) uploadBtn.style.display = "none";

        toast(result.message || "거래 내역을 성공적으로 가져왔습니다.");
        invalidateAfterExternalWrite();
        await loadLedger();
      } catch (err) {
        alert(`엑셀 파일 등록 오류: ${err.message}`);
      } finally {
        if (uploadBtn) busy(uploadBtn, false);
      }
    }

    async function processLedgerTextImport() {
      const text = document.getElementById("ledgerImportText")?.value.trim();
      const owner = document.getElementById("ledgerImportOwner")?.value || "모두";
      if (!text) {
        alert("가져올 거래내역 텍스트를 입력해 주세요.");
        return;
      }

      const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
      let successCount = 0;

      for (const line of lines) {
        const parts = line.split(/[\t, ]+/);
        if (parts.length >= 3) {
          const dateVal = parts[0];
          const merchantVal = parts.slice(1, -1).join(" ");
          const rawAmt = parts[parts.length - 1].replace(/[^0-9.-]+/g, "");
          const amountVal = Math.abs(Number(rawAmt)) || 0;
          const isInc = line.includes("급여") || line.includes("입금") || line.includes("수익") || (Number(rawAmt) > 0 && line.includes("+"));

          if (dateVal && merchantVal && amountVal > 0) {
            try {
              await api("/api/ledger/transactions", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  date: dateVal.length === 8 ? `${dateVal.slice(0,4)}-${dateVal.slice(4,6)}-${dateVal.slice(6,8)}` : dateVal,
                  type: isInc ? "income" : "expense",
                  amount: amountVal,
                  category: isInc ? "급여/상여" : "식비/외식",
                  owner,
                  merchant: merchantVal
                })
              });
              successCount++;
            } catch (e) {}
          }
        }
      }

      document.getElementById("ledgerExcelDialog")?.close();
      toast(`${successCount}건의 거래 내역을 일괄 가져왔습니다.`);
      await loadLedger();
    }

    function initLedgerListeners() {
      window.WealthIncomeMonthNavigation.bind({
        prefix: 'ledger', getKstYearMonth, shiftYearMonth, parseYearMonth,
        getYear: () => currentLedgerYear,
        getMonth: () => currentLedgerMonth,
        onMonthSelected: selectMonth,
        wheel: true,
      });
    }

    const actions = Object.freeze({
      cancelRecurringEdit,
      deleteLedgerCard,
      deleteLedgerTransaction,
      deleteRecurringItem,
      editLedgerCard,
      editRecurringItem,
      executeCardPayment,
      filterLedgerList,
      handleLedgerFileSelect,
      onLedgerCardSelectChanged,
      onLedgerPayMethodTypeChanged,
      onLedgerTxOwnerChanged,
      onLedgerTxTypeChanged,
      openLedgerCardPayModal,
      openLedgerCardsModal,
      openLedgerExcelModal,
      openLedgerRecurringModal,
      openLedgerTxModal,
      populateLedgerAccountOptions,
      populateLedgerCardOptions,
      processLedgerImport: processLedgerTextImport,
      processLedgerTextImport,
      resetLedgerCardForm,
      saveLedgerCard,
      saveLedgerTransaction,
      saveNewRecurringItem,
      toggleRecurringAccountSelect,
      triggerRecurringProcess,
      updateLedgerBalancePreview,
      updateLedgerCategoryOptions,
      uploadLedgerFile,
      loadLedger,
      renderLedger,
      renderLedgerChart,
      renderLedgerTrendFallback,
      renderLedgerTransactions,
      renderLedgerCategories,
      navigateLedgerMonth: selectMonth,
    });

    return Object.freeze({
      actions, loadLedger, invalidateRead, invalidateAfterExternalWrite,
      getYear: () => currentLedgerYear,
      getMonth: () => currentLedgerMonth,
      getData: () => rawLedgerData,
      setData, isAnnualView, setAnnualView, selectAnnualYear, selectMonth, setPeriodRenderer,
      initListeners: initLedgerListeners,
    });
  }

  window.WealthLedgerFeatureController = Object.freeze({ create });
})();
