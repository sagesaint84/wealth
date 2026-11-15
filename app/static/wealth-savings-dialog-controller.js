(() => {
  'use strict';

  function openBank({
    $, account, fromLoan, currentOwner, isMinusAccount,
    calcBankMinusPreview, refreshDialogKoreanHints,
  }) {
    const dialog = $("#bankAccountDialog");
    const form = $("#bankAccountForm");
    if (!dialog || !form) return;
    form.reset();
    form.querySelector("[name='id']").value = account ? account.id : "";

    const typeRow = form.querySelector(".bank-type-select-row");
    const switcher = form.querySelector(".bank-category-switcher");
    if (typeRow) typeRow.style.display = account ? "none" : "block";
    if (switcher) switcher.value = "free";

    const isMinus = isMinusAccount();
    if ($("#bankAccountDialogTitle")) {
      if (account) {
        $("#bankAccountDialogTitle").textContent = isMinus ? "자유연동 마이너스통장 수정" : "자유입출금 통장 수정";
      } else {
        $("#bankAccountDialogTitle").textContent = fromLoan ? "마이너스통장 (자유연동) 추가" : "자유입출금 통장 추가";
      }
    }

    if (account) {
      form.querySelector("[name='bank_name']").value = account.bank_name || "";
      form.querySelector("[name='account_name']").value = account.account_name || "";
      form.querySelector("[name='account_number']").value = account.account_number || "";
      form.querySelector("[name='owner']").value = account.owner || "모두";
      form.querySelector("[name='balance']").value = account.balance ?? 0;
      form.querySelector("[name='limit_amount']").value = account.limit_amount || "";
      form.querySelector("[name='interest_rate']").value = account.interest_rate || "";
      form.querySelector("[name='maturity_date']").value = account.maturity_date || "";
      form.querySelector("[name='memo']").value = account.memo || "";
    } else {
      form.querySelector("[name='owner']").value = currentOwner !== "모두" ? currentOwner : "모두";
    }

    calcBankMinusPreview();
    refreshDialogKoreanHints(dialog);
    dialog.showModal();
  }

  function openSaving({
    $, saving, currentOwner, rawBankAccounts, isHousingSaving,
    updateSavingTypeFields, calcSavingInterestPreview, refreshDialogKoreanHints,
  }) {
    const dialog = $("#savingAccountDialog");
    const form = $("#savingAccountForm");
    if (!dialog || !form) return;
    form.reset();
    form.querySelector("[name='id']").value = saving ? saving.id : "";

    const typeRow = form.querySelector(".bank-type-select-row");
    const switcher = form.querySelector(".bank-category-switcher");
    if (typeRow) typeRow.style.display = saving ? "none" : "block";
    if (switcher) switcher.value = "savings";

    if ($("#savingAccountDialogTitle")) {
      $("#savingAccountDialogTitle").textContent = saving ? "예·적금 상품 수정" : "예·적금 상품 추가";
    }

    const withdrawSel = $("#savingWithdrawAccountSelect");
    const depositSel = $("#savingDepositAccountSelect");
    for (const select of [withdrawSel, depositSel]) {
      if (select) window.WealthBankAccountOptions.render(select, rawBankAccounts, {
        placeholder: "-- 은행 계좌 선택 --",
        separator: " - ",
        preserveMissingLabels: true,
      });
    }

    const isHousing = isHousingSaving();
    const noMaturityCheck = $("#savingNoMaturityCheck");
    if (noMaturityCheck) noMaturityCheck.checked = isHousing;

    if (saving) {
      const { fields, withdrawAccountId, depositAccountId, memo } =
        window.WealthSavingsFormModel.editValues(saving, isHousing);
      for (const [name, value] of Object.entries(fields)) {
        form.querySelector(`[name='${name}']`).value = value;
      }
      if (withdrawSel) withdrawSel.value = withdrawAccountId;
      if (depositSel) depositSel.value = depositAccountId;
      form.querySelector("[name='memo']").value = memo;
    } else {
      form.querySelector("[name='owner']").value = currentOwner !== "모두" ? currentOwner : "모두";
      const todayStr = new Date().toISOString().slice(0, 10);
      form.querySelector("[name='start_date']").value = todayStr;
      const nextYear = new Date();
      nextYear.setFullYear(nextYear.getFullYear() + 1);
      form.querySelector("[name='end_date']").value = nextYear.toISOString().slice(0, 10);
    }

    window.WealthSavingsContributions?.protectTotal(saving);
    $("#savingAutoContributionEnabled").checked = saving?.auto_contribution_enabled === true;
    $("#savingAutoDebitBalance").checked = typeof saving?.auto_contribution_debit_balance === "boolean"
      ? saving.auto_contribution_debit_balance : true;
    updateSavingTypeFields();
    calcSavingInterestPreview();
    refreshDialogKoreanHints(dialog);
    dialog.showModal();
  }

  function openLoan({
    $, loan, currentOwner, rawBankAccounts, refreshLoanOverdraftBankOptions,
    calcLoanPreview, refreshDialogKoreanHints,
  }) {
    const dialog = $("#loanAccountDialog");
    const form = $("#loanAccountForm");
    if (!dialog || !form) return;
    form.reset();
    form.querySelector("[name='id']").value = loan ? loan.id : "";

    const typeRow = form.querySelector(".bank-type-select-row");
    const switcher = form.querySelector(".bank-category-switcher");
    if (typeRow) typeRow.style.display = loan ? "none" : "block";
    if (switcher) switcher.value = "loans";

    if ($("#loanAccountDialogTitle")) {
      $("#loanAccountDialogTitle").textContent = loan ? "대출 · 마이너스통장 수정" : "대출 · 마이너스통장 추가";
    }

    const select = $("#loanLinkedAccountSelect");
    if (select) {
      window.WealthBankAccountOptions.render(select, rawBankAccounts, {
        placeholder: "-- 출금 은행 계좌 선택 (선택사항) --",
      });
    }

    if (loan) {
      const initial = window.WealthLoanFormModel.editValues(loan);
      for (const [name, value] of Object.entries(initial.fields)) {
        form.querySelector(`[name='${name}']`).value = value;
      }
      if (select) select.value = initial.linkedAccountId;
      refreshLoanOverdraftBankOptions(initial.overdraftBankAccountId);
      form.querySelector("[name='maturity_date']").value = initial.maturityDate;
      form.querySelector("[name='memo']").value = initial.memo;
    } else {
      form.querySelector("[name='owner']").value = currentOwner !== "모두" ? currentOwner : "모두";
      form.querySelector("[name='loan_type']").value = "minus";
      form.querySelector("[name='repayment_type']").value = "bullet";
      refreshLoanOverdraftBankOptions("");
    }

    calcLoanPreview();
    refreshDialogKoreanHints(dialog);
    dialog.showModal();
  }

  function openCategory(type, { openBankAccountDialog, openSavingAccountDialog, openLoanAccountDialog }) {
    if (type === 'savings') {
      openSavingAccountDialog();
    } else if (type === 'loans') {
      openLoanAccountDialog();
    } else {
      openBankAccountDialog();
    }
  }

  function bindCategorySwitchers({ closeDialog, ...openers }) {
    document.querySelectorAll('.bank-category-switcher').forEach(sel => {
      sel.addEventListener('change', (e) => {
        const nextType = e.target.value;
        closeDialog('bankAccountDialog');
        closeDialog('savingAccountDialog');
        closeDialog('loanAccountDialog');
        openCategory(nextType, openers);
      });
    });
  }

  function bindSavingInputs({ $, savingForm, updateSavingTypeFields, calcSavingInterestPreview }) {
    const refresh = () => {
      updateSavingTypeFields();
      calcSavingInterestPreview();
    };
    savingForm.addEventListener("input", refresh);
    savingForm.addEventListener("change", refresh);
    $("#savingNoMaturityCheck")?.addEventListener("change", refresh);
  }

  function bindPreviewInputs(ids, preview) {
    ids.forEach(id => {
      document.getElementById(id)?.addEventListener("input", preview);
      document.getElementById(id)?.addEventListener("change", preview);
    });
  }

  function bindBankInputs(calcBankMinusPreview) {
    bindPreviewInputs(["bankBalanceInput", "bankLimitAmount", "bankInterestRate"], calcBankMinusPreview);
  }

  function bindLoanInputs(calcLoanPreview, refreshLoanOverdraftBankOptions) {
    bindPreviewInputs(["loanCurrentBalance", "loanInterestRate", "loanRepaymentType"], calcLoanPreview);
    document.getElementById("loanTypeSelect")?.addEventListener("change", (e) => {
      const isMinus = e.target.value === "minus";
      const limitLabel = document.getElementById("loanLimitLabel");
      if (limitLabel) limitLabel.style.display = isMinus ? "" : "none";
      refreshLoanOverdraftBankOptions();
    });
    document.getElementById("loanOwnerSelect")?.addEventListener("change", () => {
      refreshLoanOverdraftBankOptions();
    });
  }

  window.WealthSavingsDialogController = {
    openBank, openSaving, openLoan, openCategory, bindCategorySwitchers,
    bindSavingInputs, bindBankInputs, bindLoanInputs,
  };
})();
