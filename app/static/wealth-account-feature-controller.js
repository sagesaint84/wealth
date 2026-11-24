(() => {
  "use strict";

  function create(app) {
    const securitiesAccountsView = window.WealthSecuritiesAccountsView.create({
      html: app.html, number: app.number, signClass: app.signClass, maskBrokerAccountNo: app.maskBrokerAccountNo, accountReorder: window.WealthAccountReorder,
    });
    function renderAccounts(items) {
      const container = app.$("#accountList");
      if (!container) return;
      if (!items || !items.length) {
        securitiesAccountsView.renderEmpty(container);
        return;
      }
      const accountTaxBenefits = app.calculateOwnerYearPensionTaxBenefits(items);
      const groups = new Map();
      items.forEach((item) => {
        const current = groups.get(item.broker) || { broker: item.broker, count: 0, items: [] };
        current.count += 1;
        current.items.push(item);
        groups.set(item.broker, current);
      });
      const displayGroups = [...groups.values()].map(group => ({
        broker: group.broker,
        count: group.count,
        items: group.items.map(account => {
          const stockVal = Number(account.stock_value_krw || 0);
          const cashKrw = Number(account.cash_krw || 0);
          const cashUsd = Number(account.cash_usd || 0);
          const usdRate = Number(app.dashboard?.fx_rates?.USD || app.dashboard?.summary?.usd_krw_rate || app.rawDashboard?.summary?.usd_krw_rate || 1400);
          const cashTotalKrw = account.cash_total_krw !== undefined && account.cash_total_krw !== null
            ? Number(account.cash_total_krw)
            : (cashKrw + cashUsd * usdRate);
          const totalVal = Number(account.market_value_krw !== undefined ? account.market_value_krw : (stockVal + cashTotalKrw));
          const profitVal = Number(account.profit_krw || 0);

          const accountType = String(account.account_type || "").toLowerCase();
          const accountName = String(account.name || account.account_name || "").toLowerCase();
          const aType = accountType.startsWith("irp") || accountName.includes("irp")
            ? "irp"
            : (accountType.startsWith("pension_savings") || accountName.includes("연금")
              ? "pension_savings"
              : (accountType === "isa" || accountName.includes("isa") ? "isa" : "general"));
          const isTaxDeductible = app.isAccountTaxDeductible(account);

          let pension = null;
          if (aType === "pension_savings" || aType === "irp") {
            const dep = Number(account.annual_deposit) || 0;
            const ownerKey = String(account.owner || "모두");
            const currentSaved = accountTaxBenefits.current.byOwner[ownerKey]?.taxSaved || 0;
            const accountKey = String(account.id || '');
            const cumSaved = accountTaxBenefits.cumulative.byAccount[accountKey]?.taxSaved || 0;
            const rate = isTaxDeductible ? (account.income_level === "high" ? 13.2 : 16.5) : null;
            pension = { dep, currentSaved, cumSaved, rate };
          }
          return { account, stockVal, cashKrw, cashUsd, cashTotalKrw, totalVal, profitVal, aType, isTaxDeductible, pension };
        }),
      }));
      securitiesAccountsView.renderAccounts(container, displayGroups);
    }

    // ── 4-1. 예·적금, 일반 은행 계좌 및 대출·마이너스통장 ───────────────────────
    let rawBankAccounts = [];
    let rawSavingsAccounts = [];
    let rawLoanAccounts = [];
    let currentSavingsSubtab = 'all'; // 'all' (전체) | 'banks' (자유) | 'savings' (예·적금) | 'loans' (대출)

    const LOAN_TYPE_LABELS = {
      minus: "마이너스통장",
      credit: "신용대출",
      mortgage: "담보대출",
      etc: "기타 대출",
    };

    const REPAYMENT_TYPE_LABELS = {
      bullet: "만기일시상환",
      amortizing: "원리금균등",
      principal: "원금균등",
    };

    const bankingView = window.WealthBankingView.create({ $: app.$, document, html: app.html, number: app.number, maskBrokerAccountNo: app.maskBrokerAccountNo, getSavingsContributions: () => window.WealthSavingsContributions });

    function renderSavings(savingsList, bankList, loanList, owner = '모두') {
      rawSavingsAccounts = savingsList || [];
      rawBankAccounts = bankList || [];
      if (Array.isArray(loanList)) {
        rawLoanAccounts = loanList;
      } else if (typeof loanList === 'string') {
        owner = loanList;
      }
      renderSavingsWithOwner(owner);
    }

    function renderSavingsWithOwner(owner = '모두') {
      const o = owner || app.currentOwner || '모두';
      const filteredSavings = window.WealthDashboardOwnerModel.selectOwnedAccounts(rawSavingsAccounts, o);
      const filteredBanks = window.WealthDashboardOwnerModel.selectOwnedAccounts(rawBankAccounts, o);
      const filteredLoans = window.WealthDashboardOwnerModel.selectOwnedAccounts(rawLoanAccounts, o);

      // 1) 자유통장 잔고 분리
      const positiveBanks = filteredBanks.filter(b => (Number(b.balance) || 0) >= 0);
      const minusDebtBanks = filteredBanks.filter(b => (Number(b.balance) || 0) < 0);
      const minusBanks = minusDebtBanks; // 하위 호환 참조 유지

      // 2) 대출 탭에 표시할 마통 계좌: 실제 음수 잔고이거나 약정 한도(limit_amount > 0)가 등록된 계좌
      const minusOrCreditLineBanks = filteredBanks.filter(b => (Number(b.balance) || 0) < 0 || (Number(b.limit_amount) || 0) > 0);

      const totalPositiveBank = positiveBanks.reduce((sum, b) => sum + (Number(b.balance) || 0), 0);
      const representedOverdraftBanks = new Set(filteredLoans
        .filter(l => l.loan_type === 'minus' && Number(l.current_balance) > 0 && l.overdraft_bank_account_id)
        .map(l => `${l.owner || '모두'}\u0000${l.overdraft_bank_account_id}`));
      const unrepresentedMinusBanks = minusDebtBanks.filter(b => !representedOverdraftBanks.has(`${b.owner || '모두'}\u0000${b.id}`));
      const totalMinusDebt = unrepresentedMinusBanks.reduce((sum, b) => sum + Math.abs(Number(b.balance) || 0), 0);

      const totalPaid = filteredSavings.reduce((sum, s) => sum + (Number(s.current_value) || Number(s.current_paid_amount) || 0), 0);
      const totalMaturity = filteredSavings.reduce((sum, s) => sum + (Number(s.calc?.maturity_total) || 0), 0);
      const totalPureLoan = filteredLoans.reduce((sum, l) => sum + (Number(l.current_balance) || 0), 0);
      const totalCombinedDebt = totalPureLoan + totalMinusDebt;

      // 순수 대출 이자 + 자유연동 마통 월 예상 이자 합산 (실제 음수 잔고일 때만 이자 발생)
      const totalMinusInterest = unrepresentedMinusBanks.reduce((sum, b) => {
        const debt = Math.abs(Number(b.balance || 0));
        const rate = Number(b.interest_rate || 0);
        return sum + (rate > 0 ? Math.round(debt * (rate / 100) / 12) : 0);
      }, 0);
      const totalPureLoanInterest = filteredLoans.reduce((sum, l) => sum + (Number(l.monthly_interest) || Number(l.calc?.monthly_interest) || 0), 0);
      const totalLoanInterest = totalPureLoanInterest + totalMinusInterest;

      // 상단 요약 카드 집계
      if (app.$("#totalBankBalanceVal")) app.$("#totalBankBalanceVal").textContent = `₩${app.number(totalPositiveBank, 0)}`;
      if (app.$("#totalSavingsPaidVal")) app.$("#totalSavingsPaidVal").textContent = `₩${app.number(totalPaid, 0)}`;
      if (app.$("#totalSavingsMaturityVal")) app.$("#totalSavingsMaturityVal").textContent = `₩${app.number(totalMaturity, 0)}`;
      if (app.$("#totalLoanBalanceVal")) app.$("#totalLoanBalanceVal").textContent = `₩${app.number(totalCombinedDebt, 0)}`;
      if (app.$("#totalLoanInterestSub")) {
        const activeMinusCount = minusDebtBanks.length;
        const minusNote = activeMinusCount > 0 ? ` (마통 ${activeMinusCount}건 사용 중)` : '';
        app.$("#totalLoanInterestSub").textContent = `월 예상 이자: ₩${app.number(totalLoanInterest, 0)}${minusNote}`;
      }

      const totalLoanListCount = filteredLoans.length + minusOrCreditLineBanks.length;
      const totalBankAllCount = filteredBanks.length + filteredSavings.length + totalLoanListCount;
      if (app.$("#allBankCount")) app.$("#allBankCount").textContent = totalBankAllCount;
      if (app.$("#banksCount")) app.$("#banksCount").textContent = filteredBanks.length;
      if (app.$("#savingsCount")) app.$("#savingsCount").textContent = filteredSavings.length;
      if (app.$("#loansCount")) app.$("#loansCount").textContent = totalLoanListCount;

      // 서브탭 표시 상태 동기화
      const isAll = currentSavingsSubtab === 'all';
      const isBanks = currentSavingsSubtab === 'banks';
      const isSavings = currentSavingsSubtab === 'savings';
      const isLoans = currentSavingsSubtab === 'loans';

      const secFree = app.$("#bankSectionFree");
      const secSavings = app.$("#bankSectionSavings");
      const secLoans = app.$("#bankSectionLoans");
      const titleFree = app.$("#bankTitleFree");
      const titleSavings = app.$("#bankTitleSavings");
      const titleLoans = app.$("#bankTitleLoans");

      if (secFree) secFree.style.display = (isAll || isBanks) ? 'block' : 'none';
      if (secSavings) secSavings.style.display = (isAll || isSavings) ? 'block' : 'none';
      if (secLoans) secLoans.style.display = (isAll || isLoans) ? 'block' : 'none';

      if (titleFree) {
        titleFree.style.display = isAll ? 'flex' : 'none';
        titleFree.innerHTML = `<span>🏦 자유입출금 통장 (${filteredBanks.length}건)</span>`;
      }
      if (titleSavings) {
        titleSavings.style.display = isAll ? 'flex' : 'none';
        titleSavings.innerHTML = `<span>💰 예·적금 상품 (${filteredSavings.length}건)</span>`;
      }
      if (titleLoans) {
        titleLoans.style.display = isAll ? 'flex' : 'none';
        titleLoans.innerHTML = `<span>💳 대출 · 마이너스통장 (${totalLoanListCount}건)</span>`;
      }

      if (app.$("#banksListWrap")) app.$("#banksListWrap").style.display = (isAll || isBanks) ? 'block' : 'none';
      if (app.$("#savingsGrid")) app.$("#savingsGrid").style.display = (isAll || isSavings) ? 'grid' : 'none';
      if (app.$("#loansGrid")) app.$("#loansGrid").style.display = (isAll || isLoans) ? 'grid' : 'none';
      document.querySelectorAll('.savings-subtab').forEach(b => b.classList.toggle('active', b.dataset.subtab === currentSavingsSubtab));

      // 은행 계좌 매핑 사전 (출금/입금 통장 표시용)
      const bankMap = new Map();
      rawBankAccounts.forEach(b => bankMap.set(b.id, `${b.bank_name} ${b.account_name}`));

      // 1) 예·적금 카드 그리드 렌더링
      const savingsGrid = app.$("#savingsGrid");
      if (savingsGrid) {
        const savingsRows = filteredSavings.map(s => {
          const isHousing = s.saving_type === 'housing' || !s.end_date;
          const calc = s.calc || {};
          const withdrawName = s.withdraw_account_id ? (bankMap.get(s.withdraw_account_id) || '연결통장') : '미설정';
          const depositName = s.deposit_account_id ? (bankMap.get(s.deposit_account_id) || '연결통장') : '미설정';

          const curVal = Number(s.current_value || s.current_paid_amount || 0);
          const progress = isHousing ? 100 : Math.min(100, Math.max(0, s.progress_percent || 0));
          const maturityValue = isHousing ? (curVal + (calc.after_tax_interest || 0)) : (calc.maturity_total || 0);
          return { s, withdrawName, depositName, curVal, progress, maturityValue };
        });
        bankingView.renderSavings(savingsGrid, savingsRows);
      }

      // 2) 자유입출금 통장 목록 테이블 렌더링
      const banksWrap = app.$("#banksListWrap");
      if (banksWrap) {
        const bankRows = filteredBanks.map(b => {
          const bal = Number(b.balance || 0);
          return { b, bal, isMinus: bal < 0 };
        });
        bankingView.renderBanks(banksWrap, bankRows);
      }

      // 3) 대출·마이너스통장 카드 그리드 렌더링
      const loansGrid = app.$("#loansGrid");
      if (loansGrid) {
        const allLoanItems = [...filteredLoans];
        // 자유입출금 계좌 중 음수 잔고 부채이거나 마통 약정한도(limit_amount > 0)가 있는 계좌도 대출 탭에 연동 표시
        minusOrCreditLineBanks.forEach(mb => {
          const rawBal = Number(mb.balance || 0);
          const isMinus = rawBal < 0;
          const curBal = isMinus ? Math.abs(rawBal) : 0;
          const limitAmt = Number(mb.limit_amount || 0);
          const rate = Number(mb.interest_rate || 0);
          const monthlyInt = (curBal > 0 && rate > 0) ? Math.round(curBal * (rate / 100) / 12) : 0;
          let dDay = null;
          if (mb.maturity_date) {
            try {
              const endDt = new Date(mb.maturity_date.substring(0, 10));
              const nowDt = new Date();
              nowDt.setHours(0, 0, 0, 0);
              dDay = Math.round((endDt - nowDt) / (1000 * 60 * 60 * 24));
            } catch (e) {}
          }

          allLoanItems.push({
            id: mb.id,
            is_from_bank: true,
            loan_type: "minus",
            bank_name: mb.bank_name,
            product_name: `${mb.account_name} (자유통장 연동)`,
            owner: mb.owner,
            current_balance: curBal,
            raw_balance: rawBal,
            limit_amount: limitAmt,
            interest_rate: rate,
            monthly_interest: monthlyInt,
            repayment_type: "bullet",
            maturity_date: mb.maturity_date || "",
            d_day: dDay,
            linked_account_id: mb.id,
            memo: mb.memo || (isMinus ? "자유입출금 마이너스 잔고 부채" : "자유입출금 연동 마이너스통장 (한도 대기)"),
          });
        });

        const loanRows = allLoanItems.map(l => {
          const curBal = Number(l.current_balance || 0);
          const limitAmt = Number(l.limit_amount || 0);
          const monthlyInt = Number(l.monthly_interest || l.calc?.monthly_interest || 0);
          const monthlyPay = Number(l.monthly_payment || l.calc?.monthly_payment || monthlyInt);

          let utilPercent = 0;
          if (l.loan_type === 'minus' && limitAmt > 0) {
            utilPercent = Math.min(100, Math.round((curBal / limitAmt) * 100));
          }

          const linkedAccountText = l.linked_account_id ? (bankMap.get(l.linked_account_id) || "연결통장") : "미지정";
          const isUnusedMinus = l.is_from_bank && curBal === 0;
          return { l, curBal, limitAmt, monthlyInt, monthlyPay, utilPercent, linkedAccountText, isUnusedMinus };
        });
        bankingView.renderLoans(loansGrid, loanRows, LOAN_TYPE_LABELS, REPAYMENT_TYPE_LABELS);
      }
      window.WealthAccountReorder?.rendered('banking');
    }

    function calcSavingInterestPreview() {
      const type = app.$("#savingTypeSelect")?.value || "deposit";
      const months = Number(app.$("#savingDurationMonths")?.value) || 12;
      const rate = (Number(app.$("#savingInterestRate")?.value) || 0) / 100;
      const taxType = app.$("#savingTaxType")?.value || "normal";

      let principal = 0;
      let preTax = 0;

      if (type === "deposit") {
        principal = Number(app.$("#savingTargetAmount")?.value) || 0;
        preTax = principal * rate * (months / 12);
      } else if (type === "housing") {
        const curPaid = Number(app.$("#savingCurrentPaid")?.value) || 0;
        const monthly = Number(app.$("#savingMonthlyAmount")?.value) || 0;
        principal = curPaid > 0 ? curPaid : monthly;
        preTax = principal * rate;
      } else {
        const monthly = Number(app.$("#savingMonthlyAmount")?.value) || 0;
        principal = monthly * months;
        preTax = monthly * rate * (months * (months + 1) / 24);
      }

      let taxRate = 0.154;
      if (taxType === "preferential") taxRate = 0.014;
      else if (taxType === "tax_free") taxRate = 0.0;

      const tax = Math.floor(preTax * taxRate);
      const afterTax = preTax - tax;
      const maturity = principal + afterTax;

      bankingView.renderSavingPreview({ principal, preTax, tax, maturity });
    }

    function calcBankMinusPreview() {
      const balInput = Number(app.$("#bankBalanceInput")?.value || 0);
      const limitInput = Number(app.$("#bankLimitAmount")?.value || 0);
      const rateInput = Number(app.$("#bankInterestRate")?.value || 0);

      const previewBox = app.$("#bankMinusPreviewBox");
      if (!previewBox) return;

      const isMinus = balInput < 0;
      if (isMinus || limitInput > 0 || rateInput > 0) {
        previewBox.style.display = "flex";
        // 잔고가 음수일 때만 실제 대출 사용액(부채)
        const debt = isMinus ? Math.abs(balInput) : 0;
        const monthlyInt = (debt > 0 && rateInput > 0) ? Math.round(debt * (rateInput / 100) / 12) : 0;
        const utilPercent = (debt > 0 && limitInput > 0) ? Math.min(100, Math.round((debt / limitInput) * 100)) : 0;

        bankingView.renderBankMinusPreview({ debt, monthlyInt, utilPercent, limitInput });
      } else {
        previewBox.style.display = "none";
      }
    }

    function openBankAccountDialog(account = null, fromLoan = false) {
      window.WealthSavingsDialogController.openBank({
        $: app.$, account, fromLoan, currentOwner: app.currentOwner,
        isMinusAccount: () => account && (Number(account.balance) < 0 || Number(account.limit_amount) > 0 || fromLoan),
        calcBankMinusPreview, refreshDialogKoreanHints: app.refreshDialogKoreanHints,
      });
    }

    function openSavingAccountDialog(saving = null) {
      window.WealthSavingsDialogController.openSaving({
        $: app.$, saving, currentOwner: app.currentOwner, rawBankAccounts,
        isHousingSaving: () => saving ? (saving.saving_type === "housing" || !saving.end_date) : false,
        updateSavingTypeFields, calcSavingInterestPreview, refreshDialogKoreanHints: app.refreshDialogKoreanHints,
      });
    }

    function updateSavingAutoContributionFields() {
      const form = app.$("#savingAccountForm");
      const enabled = app.$("#savingAutoContributionEnabled");
      const debit = app.$("#savingAutoDebitBalance");
      if (!form || !enabled || !debit) return;
      const eligible = ["installment", "free", "housing"].includes(app.$("#savingTypeSelect")?.value);
      app.$("#savingAutoContributionSettings").hidden = !eligible;
      enabled.disabled = !eligible;
      if (!eligible) enabled.checked = false;
      const active = eligible && enabled.checked;
      app.$("#savingAutoDebitSettings").hidden = !active;
      debit.disabled = !active;
      app.$("#savingAutoDebitWarning").hidden = !active || debit.checked;
      const day = form.elements.auto_transfer_day;
      day.required = active;
      day.min = active ? "1" : "0";
      const monthly = app.$("#savingMonthlyAmount");
      monthly.required = active;
      monthly.min = active ? "0.01" : "0";
      const withdraw = app.$("#savingWithdrawAccountSelect");
      withdraw.required = active;
      const owner = form.elements.owner.value || "모두";
      const selected = withdraw.value;
      const banks = rawBankAccounts.filter(b => !active || ((b.currency || "KRW") === "KRW"
        && (owner === "모두" || [owner, "모두"].includes(b.owner || "모두"))));
      window.WealthBankAccountOptions.render(withdraw, banks, {
        placeholder: "-- 은행 계좌 선택 --", separator: " - ", emptyMissingId: true,
      });
      withdraw.value = selected;
    }

    function updateSavingTypeFields() {
      updateSavingAutoContributionFields();
      const type = app.$("#savingTypeSelect")?.value || "deposit";
      const monthlyLabel = app.$("#monthlyAmountLabel");
      const targetLabel = app.$("#targetAmountLabel");
      const noMaturityCheck = app.$("#savingNoMaturityCheck");
      const endDateInput = app.$("#savingEndDate");
      const durationInput = app.$("#savingDurationMonths");
      const durationLabel = app.$("#savingDurationLabel");

      const isHousing = type === "housing";
      if (isHousing && noMaturityCheck) {
        noMaturityCheck.checked = true;
      }
      const isNoMaturity = isHousing || Boolean(noMaturityCheck?.checked);

      if (endDateInput) {
        if (isNoMaturity) {
          endDateInput.value = "";
          endDateInput.removeAttribute("required");
          endDateInput.disabled = true;
          endDateInput.style.opacity = "0.4";
        } else {
          endDateInput.disabled = false;
          endDateInput.style.opacity = "1";
          endDateInput.setAttribute("required", "");
          if (!endDateInput.value) {
            const nextYear = new Date();
            nextYear.setFullYear(nextYear.getFullYear() + 1);
            endDateInput.value = nextYear.toISOString().slice(0, 10);
          }
        }
      }

      if (durationLabel && durationInput) {
        if (isNoMaturity) {
          durationLabel.style.display = "none";
          durationInput.removeAttribute("required");
          durationInput.value = "0";
        } else {
          durationLabel.style.display = "";
          durationInput.setAttribute("required", "");
          if (Number(durationInput.value) <= 0) durationInput.value = "12";
        }
      }

      if (type === "deposit") {
        if (monthlyLabel) monthlyLabel.style.display = "none";
        if (targetLabel) {
          targetLabel.style.display = "";
          targetLabel.childNodes[0].nodeValue = "총 예치 원금 (KRW)\n";
        }
      } else if (type === "housing") {
        if (monthlyLabel) {
          monthlyLabel.style.display = "";
          monthlyLabel.childNodes[0].nodeValue = "월 납입 금액 (선택)\n";
        }
        if (targetLabel) targetLabel.style.display = "none";
      } else {
        if (monthlyLabel) {
          monthlyLabel.style.display = "";
          monthlyLabel.childNodes[0].nodeValue = "월 납입 금액 (KRW)\n";
        }
        if (targetLabel) {
          targetLabel.style.display = "";
          targetLabel.childNodes[0].nodeValue = "만기 목표 원금 (KRW)\n";
        }
      }
    }

    function calcLoanPreview() {
      const curBal = Number(document.getElementById('loanCurrentBalance')?.value) || 0;
      const rate = Number(document.getElementById('loanInterestRate')?.value) || 0;
      const repayType = document.getElementById('loanRepaymentType')?.value || 'bullet';

      const monthlyRate = (rate / 100) / 12;
      const monthlyInterest = Math.round(curBal * monthlyRate);

      let monthlyPayment = monthlyInterest;
      if (repayType === 'amortizing' && curBal > 0 && monthlyRate > 0) {
        const factor = Math.pow(1 + monthlyRate, 12);
        monthlyPayment = Math.round(curBal * (monthlyRate * factor) / (factor - 1));
      } else if (repayType === 'principal' && curBal > 0) {
        monthlyPayment = Math.round(curBal / 12) + monthlyInterest;
      }

      bankingView.renderLoanPreview({ curBal, rate, monthlyInterest, monthlyPayment });
    }

    function refreshLoanOverdraftBankOptions(selectedValue = null) {
      const form = app.$("#loanAccountForm");
      const label = app.$("#loanOverdraftBankLabel");
      const select = app.$("#loanOverdraftBankSelect");
      if (!form || !label || !select) return;

      const loanType = form.querySelector("[name='loan_type']")?.value || "minus";
      const owner = form.querySelector("[name='owner']")?.value || "모두";
      const currentLoanId = form.querySelector("[name='id']")?.value || "";
      label.style.display = loanType === "minus" ? "" : "none";
      if (loanType !== "minus") {
        select.value = "";
        return;
      }

      const previousValue = selectedValue !== null ? selectedValue : select.value;
      const occupiedBankIds = new Set(
        rawLoanAccounts
          .filter(l => l.id !== currentLoanId && l.loan_type === "minus" && l.overdraft_bank_account_id)
          .map(l => l.overdraft_bank_account_id)
      );
      const eligibleBanks = rawBankAccounts.filter(b =>
        String(b.currency || "KRW").toUpperCase() === "KRW" &&
        Number(b.balance || 0) >= 0 &&
        (b.owner || "모두") === owner &&
        !occupiedBankIds.has(b.id)
      );
      window.WealthBankAccountOptions.render(select, eligibleBanks, {
        placeholder: "-- 자동 상계 사용 안 함 --",
      });
      select.value = eligibleBanks.some(b => b.id === previousValue) ? previousValue : "";
    }

    function openLoanAccountDialog(loan = null) {
      window.WealthSavingsDialogController.openLoan({
        $: app.$, loan, currentOwner: app.currentOwner, rawBankAccounts, refreshLoanOverdraftBankOptions,
        calcLoanPreview, refreshDialogKoreanHints: app.refreshDialogKoreanHints,
      });
    }

    function openIntegratedBankDialog() {
      if (currentSavingsSubtab === 'savings') {
        openSavingAccountDialog();
      } else if (currentSavingsSubtab === 'loans') {
        openLoanAccountDialog();
      } else {
        openBankAccountDialog();
      }
    }

    function openAccountCashDialog(account) {
      const form = app.$("#accountCashForm");
      if (!form || !account) return;
      form.reset();
      form.dataset.accountId = account.id;
      app.$("#accountCashDialogTitle").textContent = `[${account.broker} · ${account.name}] 예수금 입력 / 수정`;
      form.cash_krw.value = account.cash_krw || "";
      form.cash_usd.value = account.cash_usd || "";
      app.$("#accountCashDialog")?.showModal();
    }

    let accountCurrentYearlyList = [];

    function renderAccountYearlyFormRows(form = document.getElementById("accountEditForm")) {
      const container = form?.querySelector("#accountYearlyList");
      if (!container) return;

      const accType = form.querySelector(".account-type-select")?.value || "pension_savings";
      const defaultIncomeLvl = form.querySelector(".pension-income-level")?.value || "low";
      const baseLimit = accType === "pension_savings" ? 6000000 : 9000000;

      let cumulativeSaved = 0;
      let cumulativeDeposit = 0;

      let rows = [];
      if (accountCurrentYearlyList?.length) {
        // Sort descending by year
        accountCurrentYearlyList.sort((a, b) => Number(b.year || 0) - Number(a.year || 0));

        rows = accountCurrentYearlyList.map((yc, idx) => {
          const yr = String(yc.year || "").trim();
          const dep = Number(yc.deposit || 0);
          const isDed = yc.is_deductible !== false && String(yc.is_deductible) !== "false";
          const incLvl = yc.income_level || defaultIncomeLvl;
          const rate = incLvl === "high" ? 13.2 : 16.5;
          const target = isDed ? Math.min(dep, baseLimit) : 0;
          const saved = isDed ? Math.floor(target * (rate / 100)) : 0;

          cumulativeDeposit += dep;
          if (isDed) cumulativeSaved += saved;

          return { idx, yr, dep, isDed, rate, saved };
        });
      }

      app.accountYearlyView.render(form, container, rows, { cumulativeSaved, cumulativeDeposit });
    }

    function updateAccountTaxBenefitFields(form) {
      if (!form) return;
      const accType = form.querySelector(".account-type-select")?.value || "general";
      const taxGroup = form.querySelector(".pension-tax-benefit-group");
      const isPension = accType === "pension_savings" || accType === "irp";
      if (taxGroup) taxGroup.style.display = isPension ? "block" : "none";

      if (isPension) {
        const isDeductible = form.querySelector(".pension-tax-deductible")?.value !== "false";
        const annualDep = Number(form.querySelector(".pension-annual-deposit")?.value) || 0;
        const isaTr = Number(form.querySelector(".pension-isa-transfer")?.value) || 0;
        const incomeLvl = form.querySelector(".pension-income-level")?.value || "low";
        const rate = incomeLvl === "low" ? 16.5 : 13.2;

        const baseLimit = isDeductible ? (accType === "pension_savings" ? 6000000 : 9000000) : 0;
        const baseTarget = Math.min(annualDep, baseLimit);
        const isaTarget = Math.min(isaTr * 0.10, 3000000);
        const totalTarget = baseTarget + isaTarget;
        const totalRefund = Math.floor(totalTarget * (rate / 100));

        const targetEl = form.querySelector(".pension-deduction-target-text");
        const refundEl = form.querySelector(".pension-tax-refund-text");

        if (!isDeductible) {
          if (targetEl) targetEl.textContent = isaTarget > 0 ? ` (ISA 추가 ₩${app.number(isaTarget, 0)})` : '';
          if (refundEl) refundEl.innerHTML = isaTarget > 0
            ? `+₩${app.number(Math.floor(isaTarget * (rate / 100)), 0)} <span style="font-size:11px;color:#a7f3d0;">(원금 ₩${app.number(annualDep, 0)} 비과세)</span>`
            : `<span style="color:#a7f3d0;font-size:12px;">₩0 (원금 비과세 인출 대상)</span>`;
        } else {
          if (targetEl) targetEl.textContent = isaTarget > 0 ? ` (ISA 추가 ₩${app.number(isaTarget, 0)})` : '';
          if (refundEl) refundEl.textContent = `₩${app.number(totalRefund, 0)} (${rate}%)`;
        }
      }
    }

    let editingAccountYearlyIndex = null;

    function resetAddAccountYearlyBtn() {
      const btn = document.getElementById("addAccountYearlyBtn");
      if (btn) {
        btn.innerHTML = `<span>➕</span> <span>연도 추가 / 반영</span>`;
        btn.style.background = "linear-gradient(135deg, #0284c7, #0ea5e9)";
      }
    }

    function setEditingAccountYearlyBtn(yr) {
      const btn = document.getElementById("addAccountYearlyBtn");
      if (btn) {
        btn.innerHTML = `<span>✏️</span> <span>[${yr}년] 수정 반영</span>`;
        btn.style.background = "linear-gradient(135deg, #059669, #10b981)";
      }
    }

    function handleAddAccountYearly() {
      const editForm = document.getElementById("accountEditForm");
      const yrInput = editForm?.querySelector(".pension-entry-year") || document.getElementById("accountInputYear");
      const depInput = editForm?.querySelector(".pension-annual-deposit") || document.getElementById("accountInputDeposit");
      const dedInput = editForm?.querySelector(".pension-tax-deductible") || document.getElementById("accountInputDeductible");
      const incInput = editForm?.querySelector(".pension-income-level") || document.getElementById("accountInputIncomeLevel");

      const rawYr = (yrInput?.value || "").trim();
      const yr = app.normalizeYear(rawYr);
      const dep = Number(depInput?.value) || 0;
      const isDed = dedInput ? dedInput.value !== "false" : true;
      const incLvl = incInput?.value || "low";

      if (!yr) {
        alert("연도를 올바르게 입력해 주세요 (예: 2024 또는 24년).");
        yrInput?.focus();
        return;
      }
      if (dep < 0) {
        alert("납입액을 0원 이상 입력해 주세요.");
        depInput?.focus();
        return;
      }

      // 상단 입력창에도 정규화된 4자리 연도로 표시
      if (yrInput) yrInput.value = yr;

      if (editingAccountYearlyIndex !== null && accountCurrentYearlyList[editingAccountYearlyIndex]) {
        const oldYr = accountCurrentYearlyList[editingAccountYearlyIndex].year;
        accountCurrentYearlyList[editingAccountYearlyIndex].year = yr;
        accountCurrentYearlyList[editingAccountYearlyIndex].deposit = dep;
        accountCurrentYearlyList[editingAccountYearlyIndex].is_deductible = isDed;
        accountCurrentYearlyList[editingAccountYearlyIndex].income_level = incLvl;
        editingAccountYearlyIndex = null;
        resetAddAccountYearlyBtn();
        app.toast(`[${oldYr}년 ➔ ${yr}년 ₩${app.number(dep, 0)}] 수정이 반영되었습니다. 하단 [저장]을 눌러 최종 저장하세요.`);
      } else {
        // 기존 연도 확인 (있으면 갱신, 없으면 추가)
        const existingIdx = accountCurrentYearlyList.findIndex(y => app.normalizeYear(y.year) === yr);
        if (existingIdx >= 0) {
          accountCurrentYearlyList[existingIdx].year = yr;
          accountCurrentYearlyList[existingIdx].deposit = dep;
          accountCurrentYearlyList[existingIdx].is_deductible = isDed;
          accountCurrentYearlyList[existingIdx].income_level = incLvl;
          app.toast(`[${yr}년 ₩${app.number(dep, 0)}] 이력이 반영되었습니다. 하단 [저장]을 눌러 최종 저장하세요.`);
        } else {
          accountCurrentYearlyList.push({
            year: yr,
            deposit: dep,
            is_deductible: isDed,
            income_level: incLvl
          });
          app.toast(`[${yr}년 ₩${app.number(dep, 0)}] 이력이 목록에 추가되었습니다. 하단 [저장]을 눌러 최종 저장하세요.`);
        }
      }

      // 연도 내림차순 정렬 후 렌더링
      accountCurrentYearlyList.sort((a, b) => Number(b.year || 0) - Number(a.year || 0));
      renderAccountYearlyFormRows(editForm);
      updateAccountTaxBenefitFields(editForm);
      app.refreshDialogKoreanHints(editForm);
    }


    let currentEditingAccountId = null;

    function openAccountEditDialog(account) {
      const form = app.$("#accountEditForm");
      if (!form || !account) return;
      form.reset();
      editingAccountYearlyIndex = null;
      resetAddAccountYearlyBtn();
      currentEditingAccountId = account.id;
      form.removeAttribute("data-account-id");
      form.removeAttribute("data-account-edit-id");
      delete form.dataset.accountId;
      delete form.dataset.accountEditId;
      let idInput = form.querySelector("[name='id']");
      if (!idInput) {
        idInput = document.createElement("input");
        idInput.type = "hidden";
        idInput.name = "id";
        form.prepend(idInput);
      }
      idInput.value = account.id;
      form.broker.value = account.broker || "";
      form.name.value = account.name || "";
      if (form.account_no) form.account_no.value = account.account_no || "";
      if (form.owner) form.owner.value = account.owner || "모두";
      if (form.cash_krw) form.cash_krw.value = account.cash_krw || "";
      if (form.cash_usd) form.cash_usd.value = account.cash_usd || "";

      const aName = (account.name || "").toLowerCase();
      const aType = account.account_type || (aName.includes("연금") ? "pension_savings" : (aName.includes("irp") ? "irp" : (aName.includes("isa") ? "isa" : "general")));
      const typeSelect = form.querySelector(".account-type-select");
      if (typeSelect) typeSelect.value = aType;

      const isTaxDeductible = app.isAccountTaxDeductible(account);
      const dedSel = form.querySelector(".pension-tax-deductible");
      if (dedSel) dedSel.value = isTaxDeductible ? "true" : "false";

      const incomeLvl = form.querySelector(".pension-income-level");
      const acctIncomeLvl = account.income_level || "low";
      if (incomeLvl) incomeLvl.value = acctIncomeLvl;
      const annualDep = form.querySelector(".pension-annual-deposit");
      if (annualDep) annualDep.value = (account.annual_deposit !== undefined && account.annual_deposit !== null && account.annual_deposit !== "") ? account.annual_deposit : "";
      const isaTr = form.querySelector(".pension-isa-transfer");
      if (isaTr) isaTr.value = (account.isa_transfer_amount !== undefined && account.isa_transfer_amount !== null && account.isa_transfer_amount !== "") ? account.isa_transfer_amount : "";
      const isaYear = form.querySelector(".pension-isa-year");
      if (isaYear) isaYear.value = account.isa_transfer_year || "2026";

      accountCurrentYearlyList = Array.isArray(account.yearly_contributions)
        ? JSON.parse(JSON.stringify(account.yearly_contributions))
        : [];

      const curYrStr = String(new Date().getFullYear());
      const acctAnnualDep = Number(account.annual_deposit) || 0;
      if ((aType === "pension_savings" || aType === "irp") && accountCurrentYearlyList.length === 0 && acctAnnualDep > 0) {
        accountCurrentYearlyList.push({
          year: curYrStr,
          deposit: acctAnnualDep,
          is_deductible: isTaxDeductible,
          income_level: acctIncomeLvl
        });
      }

      // Sort descending by year
      accountCurrentYearlyList.sort((a, b) => Number(b.year || 0) - Number(a.year || 0));

      // If account has an income_level, fill it in for yearly items that don't have one
      if (account.income_level) {
        accountCurrentYearlyList.forEach(item => {
          if (!item.income_level) item.income_level = acctIncomeLvl;
        });
      }

      // Set top input year & values
      const yrInput = form.querySelector(".pension-entry-year");
      if (yrInput) {
        if (accountCurrentYearlyList.length > 0) {
          const topItem = accountCurrentYearlyList[0];
          yrInput.value = topItem.year || curYrStr;
          if (annualDep) {
            annualDep.value = (topItem.deposit !== undefined && topItem.deposit !== null) ? topItem.deposit : (account.annual_deposit || "");
          }
          if (dedSel && topItem.is_deductible !== undefined) {
            dedSel.value = (topItem.is_deductible !== false && String(topItem.is_deductible) !== "false") ? "true" : "false";
          }
          if (incomeLvl) {
            incomeLvl.value = topItem.income_level || acctIncomeLvl;
          }
        } else {
          yrInput.value = curYrStr;
          if (annualDep) annualDep.value = (account.annual_deposit && account.annual_deposit > 0) ? account.annual_deposit : "";
        }
      }

      updateAccountTaxBenefitFields(form);
      renderAccountYearlyFormRows(form);
      app.refreshDialogKoreanHints(app.$("#accountEditDialog"));
      app.$("#accountEditDialog")?.showModal();
    }

    let isSavingAccount = false;

    async function saveEditAccount() {
      if (isSavingAccount) return;
      const form = document.getElementById("accountEditForm");
      if (!form) return;
      const saveBtn = document.getElementById("accountEditSaveBtn");
      isSavingAccount = true;
      if (saveBtn) app.busy(saveBtn, true);

      try {
        const accountId = form.querySelector("[name='id']")?.value || currentEditingAccountId || form.dataset.accountId || form.getAttribute("data-account-id");
        if (!accountId) {
          alert("계좌 식별자(ID)를 찾을 수 없습니다. 다시 시도해 주세요.");
          return;
        }
        const existingAcct = (app.dashboard?.accounts || []).find(a => a.id === accountId) || (app.rawDashboard?.accounts || []).find(a => a.id === accountId);
        const broker = (form.querySelector("[name='broker']")?.value || "").trim() || (existingAcct?.broker || "");
        const name = (form.querySelector("[name='name']")?.value || "").trim() || (existingAcct?.name || "");
        const owner = (form.querySelector("[name='owner']")?.value || "").trim() || (existingAcct?.owner || "모두");
        const account_no = (form.querySelector("[name='account_no']")?.value || "").trim();

        if (!broker || !name) {
          alert("증권사와 계좌 이름을 모두 입력해 주세요.");
          return;
        }

        const account_type = form.querySelector(".account-type-select")?.value || "general";
        let isDeductible = form.querySelector(".pension-tax-deductible")?.value === "true";
        let income_level = form.querySelector(".pension-income-level")?.value || "low";
        let annual_deposit = Number(form.querySelector(".pension-annual-deposit")?.value) || 0;
        const isa_transfer_amount = Number(form.querySelector(".pension-isa-transfer")?.value) || 0;
        const isa_transfer_year = form.querySelector(".pension-isa-year")?.value || "2026";
        const cash_krw = Number(form.querySelector("[name='cash_krw']")?.value) || 0;
        const cash_usd = Number(form.querySelector("[name='cash_usd']")?.value) || 0;

        // 만약 특정 연도 항목을 [수정] 모드로 변경 중인 상태에서 바로 [저장]을 누른 경우
        let editingIndexApplied = false;
        if (editingAccountYearlyIndex !== null && accountCurrentYearlyList[editingAccountYearlyIndex]) {
          const rawYr = (form.querySelector(".pension-entry-year")?.value || "").trim();
          const normYr = app.normalizeYear(rawYr) || accountCurrentYearlyList[editingAccountYearlyIndex].year;
          accountCurrentYearlyList[editingAccountYearlyIndex].year = normYr;
          accountCurrentYearlyList[editingAccountYearlyIndex].deposit = annual_deposit;
          accountCurrentYearlyList[editingAccountYearlyIndex].is_deductible = isDeductible;
          accountCurrentYearlyList[editingAccountYearlyIndex].income_level = income_level;
          editingAccountYearlyIndex = null;
          resetAddAccountYearlyBtn();
          editingIndexApplied = true;
        }

        const yearly_contributions = [];
        accountCurrentYearlyList.forEach(item => {
          if (item && item.year) {
            const normYr = app.normalizeYear(item.year);
            if (normYr) {
              yearly_contributions.push({
                year: normYr,
                deposit: Number(item.deposit || 0),
                is_deductible: item.is_deductible !== false && String(item.is_deductible) !== "false",
                income_level: item.income_level || income_level
              });
            }
          }
        });

        // 상단 입력창에 입력된 연도/금액 동기화 (수정 모드에서 이미 반영된 경우 중복 방지)
        if (!editingIndexApplied && (account_type === "pension_savings" || account_type === "irp")) {
          const rawTopYr = (form.querySelector(".pension-entry-year")?.value || "").trim();
          const topYr = app.normalizeYear(rawTopYr);
          if (topYr) {
            const existing = yearly_contributions.find(y => app.normalizeYear(y.year) === topYr);
            if (existing) {
              existing.deposit = annual_deposit;
              existing.is_deductible = isDeductible;
              existing.income_level = income_level;
            } else if (annual_deposit > 0) {
              yearly_contributions.push({
                year: topYr,
                deposit: annual_deposit,
                is_deductible: isDeductible,
                income_level: income_level
              });
            }
          }
        }

        // 연도 내림차순 정렬
        yearly_contributions.sort((a, b) => Number(b.year || 0) - Number(a.year || 0));

        // 최신 연도 입금액을 annual_deposit에 동기화
        if (yearly_contributions.length > 0) {
          const curYearStr = String(new Date().getFullYear());
          const matchedCur = yearly_contributions.find(y => y.year === curYearStr);
          if (matchedCur) {
            annual_deposit = matchedCur.deposit;
          } else {
            annual_deposit = yearly_contributions[0].deposit;
          }
        } else {
          annual_deposit = 0;
        }

        // 전역 상태 동기화
        accountCurrentYearlyList = JSON.parse(JSON.stringify(yearly_contributions));

        // 1. 메모리 데이터 즉시 갱신 (Optimistic Update)
        const updateAcctInMemory = (acctObj) => {
          if (!acctObj) return;
          acctObj.broker = broker;
          acctObj.name = name;
          acctObj.account_no = account_no;
          acctObj.owner = owner;
          acctObj.account_type = account_type;
          acctObj.tax_deductible = isDeductible;
          acctObj.income_level = income_level;
          acctObj.annual_deposit = annual_deposit;
          acctObj.isa_transfer_amount = isa_transfer_amount;
          acctObj.isa_transfer_year = isa_transfer_year;
          acctObj.yearly_contributions = yearly_contributions;
          acctObj.cash_krw = cash_krw;
          acctObj.cash_usd = cash_usd;
          const usdRate = Number(app.dashboard?.summary?.usd_krw_rate || app.rawDashboard?.summary?.usd_krw_rate || 1400);
          acctObj.cash_total_krw = cash_krw + (cash_usd * usdRate);
          acctObj.market_value_krw = Number(acctObj.stock_value_krw || 0) + acctObj.cash_total_krw;
        };

        if (app.rawDashboard && Array.isArray(app.rawDashboard.accounts)) {
          updateAcctInMemory(app.rawDashboard.accounts.find(a => a.id === accountId));
        }
        if (app.dashboard && Array.isArray(app.dashboard.accounts)) {
          updateAcctInMemory(app.dashboard.accounts.find(a => a.id === accountId));
        }

        // 2. 화면 즉시 재렌더링
        if (app.rawDashboard || app.dashboard) app.renderWithOwner(app.rawDashboard || app.dashboard, app.currentOwner);

        // 3. 다이얼로그 즉시 닫기
        document.getElementById("accountEditDialog")?.close();

        // 4. 서버 PUT API 전송
        const res = await app.api(`/api/accounts/${accountId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            broker,
            name,
            account_no,
            owner,
            account_type,
            tax_deductible: isDeductible,
            income_level,
            annual_deposit,
            isa_transfer_amount,
            isa_transfer_year,
            yearly_contributions,
            cash_krw,
            cash_usd
          })
        });

        if (account_type === "pension_savings" || account_type === "irp") {
          app.toast(`[${name}] ${isDeductible ? '🎯 세액공제 신청' : '🌿 세액공제 제외(비공제)'} (납입 ₩${app.number(annual_deposit, 0)}) 저장되었습니다.`);
        } else {
          app.toast(`[${name}] 계좌 정보 및 예수금이 저장되었습니다.`);
        }
        await app.loadDashboard();
      } catch (err) {
        console.error("계좌 수정 오류:", err);
        alert(`계좌 정보 저장 중 오류가 발생했습니다: ${err.message || err}`);
        app.toast(err.message || String(err), true);
        await app.loadDashboard();
      } finally {
        isSavingAccount = false;
        if (saveBtn) app.busy(saveBtn, false);
      }
    }

    let isSavingNewAccount = false;

    async function saveNewAccount() {
      if (isSavingNewAccount) return;
      const form = document.getElementById("accountAddForm");
      if (!form) return;
      const broker = (form.querySelector("[name='broker']")?.value || "").trim();
      const account_name = (form.querySelector("[name='account_name']")?.value || "").trim();
      const account_no = (form.querySelector("[name='account_no']")?.value || "").trim();
      const owner = (form.querySelector("[name='owner']")?.value || "모두").trim();
      const account_type = form.querySelector(".account-type-select")?.value || "general";
      const isDeductible = form.querySelector(".pension-tax-deductible")?.value === "true";
      const income_level = form.querySelector(".pension-income-level")?.value || "low";
      const annual_deposit = Number(form.querySelector(".pension-annual-deposit")?.value) || 0;
      const isa_transfer_amount = Number(form.querySelector(".pension-isa-transfer")?.value) || 0;
      const isa_transfer_year = form.querySelector(".pension-isa-year")?.value || "2026";
      const cash_krw = Number(form.querySelector("[name='cash_krw']")?.value) || 0;
      const cash_usd = Number(form.querySelector("[name='cash_usd']")?.value) || 0;

      if (!broker || !account_name) {
        alert("증권사와 계좌 이름을 모두 입력해 주세요.");
        return;
      }

      const saveBtn = document.getElementById("accountAddSaveBtn");
      isSavingNewAccount = true;
      if (saveBtn) app.busy(saveBtn, true);

      try {
        const res = await app.api("/api/accounts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            broker,
            account_name,
            name: account_name,
            account_no,
            owner,
            account_type,
            tax_deductible: isDeductible,
            income_level,
            annual_deposit,
            isa_transfer_amount,
            isa_transfer_year,
            yearly_contributions: (annual_deposit > 0 && (account_type === 'pension_savings' || account_type === 'irp')) ? [{
              year: "2026",
              deposit: annual_deposit,
              is_deductible: isDeductible,
              income_level: income_level
            }] : [],
            cash_krw,
            cash_usd
          })
        });
        document.getElementById("accountAddDialog")?.close();
        form.reset();
        app.toast(`[${account_name}] ${isDeductible ? '🎯 세액공제 신청' : '🌿 세액공제 제외(비공제)'} 계좌가 추가되었습니다.`);
        await app.loadDashboard();
      } catch (err) {
        console.error("계좌 추가 오류:", err);
        alert(`계좌 추가 중 오류가 발생했습니다: ${err.message}`);
        app.toast(err.message, true);
      } finally {
        isSavingNewAccount = false;
        if (saveBtn) app.busy(saveBtn, false);
      }
    }

    function bindBankForms() {
      document.querySelectorAll('.bank-category-switcher').forEach(sel => {
        sel.addEventListener('change', (e) => {
          const nextType = e.target.value;
          app.closeDialog('bankAccountDialog');
          app.closeDialog('savingAccountDialog');
          app.closeDialog('loanAccountDialog');
          if (nextType === 'savings') {
            openSavingAccountDialog();
          } else if (nextType === 'loans') {
            openLoanAccountDialog();
          } else {
            openBankAccountDialog();
          }
        });
      });

      const savingForm = app.$("#savingAccountForm");
      if (savingForm) {
        savingForm.addEventListener("input", () => {
          updateSavingTypeFields();
          calcSavingInterestPreview();
        });
        savingForm.addEventListener("change", () => {
          updateSavingTypeFields();
          calcSavingInterestPreview();
        });
        app.$("#savingNoMaturityCheck")?.addEventListener("change", () => {
          updateSavingTypeFields();
          calcSavingInterestPreview();
        });

        savingForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fd = new FormData(savingForm);
          const isNoMaturity = fd.get("saving_type") === "housing" || Boolean(app.$("#savingNoMaturityCheck")?.checked);
          const payload = {
            id: fd.get("id") || undefined,
            saving_type: fd.get("saving_type") || "deposit",
            owner: fd.get("owner") || "모두",
            bank_name: fd.get("bank_name") || "",
            product_name: fd.get("product_name") || "",
            start_date: fd.get("start_date") || "",
            end_date: isNoMaturity ? "" : (fd.get("end_date") || ""),
            duration_months: isNoMaturity ? 0 : (Number(fd.get("duration_months")) || 12),
            interest_rate: Number(fd.get("interest_rate")) || 0,
            monthly_amount: Number(fd.get("monthly_amount")) || 0,
            target_amount: Number(fd.get("target_amount")) || 0,
            current_paid_amount: Number(fd.get("current_paid_amount")) || 0,
            tax_type: fd.get("tax_type") || "normal",
            auto_transfer_day: Number(fd.get("auto_transfer_day")) || 0,
            auto_contribution_enabled: app.$("#savingAutoContributionEnabled").checked,
            auto_contribution_debit_balance: app.$("#savingAutoDebitBalance").checked,
            withdraw_account_id: fd.get("withdraw_account_id") || "",
            deposit_account_id: fd.get("deposit_account_id") || "",
            memo: fd.get("memo") || "",
          };

          try {
            await app.api("/api/savings-accounts", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            app.toast("예·적금 상품이 저장되었습니다.");
            app.closeDialog("savingAccountDialog");
            await app.loadDashboard();
          } catch (err) {
            app.toast(err.message || "예·적금 저장 실패", true);
          }
        });
      }

      const bankForm = app.$("#bankAccountForm");
      if (bankForm) {
        bankForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fd = new FormData(bankForm);
          const payload = {
            id: fd.get("id") || undefined,
            bank_name: fd.get("bank_name") || "",
            account_name: fd.get("account_name") || "",
            account_number: fd.get("account_number") || "",
            owner: fd.get("owner") || "모두",
            balance: Number(fd.get("balance")) || 0,
            limit_amount: Number(fd.get("limit_amount")) || 0,
            interest_rate: Number(fd.get("interest_rate")) || 0,
            maturity_date: fd.get("maturity_date") || "",
            currency: "KRW",
            memo: fd.get("memo") || "",
          };

          try {
            await app.api("/api/bank-accounts", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            app.toast("자유입출금 통장(마통) 정보가 저장되었습니다.");
            app.closeDialog("bankAccountDialog");
            await app.loadDashboard();
          } catch (err) {
            app.toast(err.message || "통장 저장 실패", true);
          }
        });

        ["bankBalanceInput", "bankLimitAmount", "bankInterestRate"].forEach(id => {
          document.getElementById(id)?.addEventListener("input", calcBankMinusPreview);
          document.getElementById(id)?.addEventListener("change", calcBankMinusPreview);
        });
      }
    }

    function bindSecuritiesTaxPreview() {
      ["accountAddForm", "accountEditForm"].forEach(id => {
        const f = document.getElementById(id);
        if (f) {
          f.addEventListener("input", () => updateAccountTaxBenefitFields(f));
          f.addEventListener("change", (e) => {
            if (e.target && e.target.matches(".pension-income-level")) {
              const newInc = e.target.value || "low";
              if (id === "accountEditForm" && accountCurrentYearlyList && accountCurrentYearlyList.length > 0) {
                accountCurrentYearlyList.forEach(item => {
                  item.income_level = newInc;
                });
                renderAccountYearlyFormRows(f);
              }
            }
            updateAccountTaxBenefitFields(f);
          });
        }
      });
    }

    function bindLoanForm() {
      const loanForm = app.$("#loanAccountForm");
      if (loanForm) {
        loanForm.addEventListener("submit", async (e) => {
          e.preventDefault();
          const fd = new FormData(loanForm);
          const payload = {
            id: fd.get("id") || undefined,
            loan_type: fd.get("loan_type") || "minus",
            owner: fd.get("owner") || "모두",
            bank_name: fd.get("bank_name") || "",
            product_name: fd.get("product_name") || "",
            limit_amount: Number(fd.get("limit_amount")) || 0,
            current_balance: Number(fd.get("current_balance")) || 0,
            interest_rate: Number(fd.get("interest_rate")) || 0,
            repayment_type: fd.get("repayment_type") || "bullet",
            linked_account_id: fd.get("linked_account_id") || "",
            overdraft_bank_account_id: fd.get("overdraft_bank_account_id") || "",
            maturity_date: fd.get("maturity_date") || "",
            memo: fd.get("memo") || "",
          };

          try {
            await app.api("/api/loan-accounts", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload),
            });
            app.toast("대출·마이너스통장이 저장되었습니다.");
            app.closeDialog("loanAccountDialog");
            await app.loadDashboard();
          } catch (err) {
            app.toast(err.message || "대출·마이너스통장 저장 실패", true);
          }
        });

        ["loanCurrentBalance", "loanInterestRate", "loanRepaymentType"].forEach(id => {
          document.getElementById(id)?.addEventListener("input", calcLoanPreview);
          document.getElementById(id)?.addEventListener("change", calcLoanPreview);
        });

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
    }

    function bindAccountList() {
      app.$("#accountList")?.addEventListener("click", async (e) => {
        const toggleTaxBtn = e.target.closest("[data-toggle-tax-account-id]");
        const cashBtn = e.target.closest("[data-cash-id]");
        const editBtn = e.target.closest("[data-account-edit-id]");
        const delBtn = e.target.closest("[data-account-del-id]");

        if (toggleTaxBtn) {
          const accId = toggleTaxBtn.dataset.toggleTaxAccountId;
          const acct = (app.dashboard?.accounts || []).find(a => a.id === accId) || (app.rawDashboard?.accounts || []).find(a => a.id === accId);
          if (acct) {
            const currentDed = app.isAccountTaxDeductible(acct);
            const newDed = !currentDed;
            const acctName = acct.name || "";
            acct.tax_deductible = newDed;
            if (app.rawDashboard && Array.isArray(app.rawDashboard.accounts)) {
              const rAcct = app.rawDashboard.accounts.find(a => a.id === accId);
              if (rAcct) { rAcct.tax_deductible = newDed; }
            }
            if (app.dashboard && Array.isArray(app.dashboard.accounts)) {
              const dAcct = app.dashboard.accounts.find(a => a.id === accId);
              if (dAcct) { dAcct.tax_deductible = newDed; }
            }
            app.renderWithOwner(app.rawDashboard || app.dashboard, app.currentOwner);
            try {
              await app.api(`/api/accounts/${accId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  broker: acct.broker,
                  name: acctName,
                  owner: acct.owner || "모두",
                  account_type: acct.account_type || "pension_savings",
                  tax_deductible: newDed,
                  income_level: acct.income_level || "low",
                  annual_deposit: Number(acct.annual_deposit) || 0,
                  isa_transfer_amount: Number(acct.isa_transfer_amount) || 0,
                  isa_transfer_year: acct.isa_transfer_year || "2026",
                  yearly_contributions: acct.yearly_contributions || []
                })
              });
              app.toast(`[${acctName}] ${newDed ? '🎯 세액공제 신청' : '🌿 세액공제 제외(비공제)'}으로 전환되었습니다.`);
              await app.loadDashboard();
            } catch (err) {
              alert(`전환 실패: ${err.message}`);
              await app.loadDashboard();
            }
          }
          return;
        }
        if (cashBtn) {
          const acct = (app.dashboard?.accounts || []).find(a => a.id === cashBtn.dataset.cashId) || (app.rawDashboard?.accounts || []).find(a => a.id === cashBtn.dataset.cashId);
          if (acct) openAccountCashDialog(acct);
          return;
        }
        if (editBtn) {
          const acct = (app.dashboard?.accounts || []).find(a => a.id === editBtn.dataset.accountEditId) || (app.rawDashboard?.accounts || []).find(a => a.id === editBtn.dataset.accountEditId);
          if (acct) openAccountEditDialog(acct);
          return;
        }
        if (delBtn && confirm("이 계좌를 삭제할까요? 연결된 보유종목도 함께 삭제됩니다.")) {
          await app.action(delBtn, () => app.api(`/api/accounts/${delBtn.dataset.accountDelId}`, { method: "DELETE" }));
        }
      });
    }

    function bindSaveButtons() {
      document.getElementById("accountEditSaveBtn")?.addEventListener("click", (e) => {
        e.preventDefault();
        saveEditAccount();
      });
      document.getElementById("accountAddSaveBtn")?.addEventListener("click", (e) => {
        e.preventDefault();
        saveNewAccount();
      });

      app.$("#accountEditForm")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.target.closest("textarea")) {
          e.preventDefault();
          saveEditAccount();
        }
      });
      app.$("#accountAddForm")?.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.target.closest("textarea")) {
          e.preventDefault();
          saveNewAccount();
        }
      });
    }

    function openAccountAddDialog() {
      const form = document.getElementById("accountAddForm");
      if (form) {
        form.reset();
        const ownerSelect = form.querySelector("[name='owner']");
        if (ownerSelect && app.currentOwner !== "모두") {
          ownerSelect.value = app.currentOwner;
        }
      }
      document.getElementById("accountAddDialog")?.showModal();
    }

    function editAccountFromRow(e, acctEditBtn) {
      e.preventDefault();
      const aid = acctEditBtn.dataset.accountEditId;
      const acct = (app.dashboard?.accounts || []).find(a => a.id === aid) || (app.rawDashboard?.accounts || []).find(a => a.id === aid);
      if (acct) {
        openAccountEditDialog(acct);
      } else {
        console.warn("[openAccountEditDialog] 계좌를 찾을 수 없습니다:", aid);
      }
    }

    function editLoanAccount(loanEditBtn) {
      const lid = loanEditBtn.dataset.loanEditId;
      const loan = rawLoanAccounts.find(l => l.id === lid);
      if (loan) openLoanAccountDialog(loan);
    }

    async function deleteLoanAccount(loanDelBtn) {
      const lid = loanDelBtn.dataset.loanDelId;
      if (confirm('이 대출·마이너스통장 항목을 삭제하시겠습니까?')) {
        try {
          await app.api(`/api/loan-accounts/${lid}`, { method: 'DELETE' });
          app.toast('대출·마이너스통장이 삭제되었습니다.');
          await app.loadDashboard();
        } catch (err) {
          app.toast(err.message || '삭제 실패', true);
        }
      }
    }

    function selectSavingsSubtab(subtabBtn) {
      const subtab = subtabBtn.dataset.subtab;
      currentSavingsSubtab = subtab;
      document.querySelectorAll('.savings-subtab').forEach(b => b.classList.toggle('active', b.dataset.subtab === subtab));
      renderSavingsWithOwner(app.currentOwner);
    }

    function editSavingAccount(savingEditBtn) {
      const sid = savingEditBtn.dataset.savingEditId;
      const saving = rawSavingsAccounts.find(s => s.id === sid);
      if (saving) openSavingAccountDialog(saving);
    }

    async function deleteSavingAccount(savingDelBtn) {
      const sid = savingDelBtn.dataset.savingDelId;
      if (confirm('이 예·적금 상품을 삭제하시겠습니까?')) {
        try {
          await app.api(`/api/savings-accounts/${sid}`, { method: 'DELETE' });
          app.toast('예·적금 상품이 삭제되었습니다.');
          await app.loadDashboard();
        } catch (err) {
          app.toast(err.message || '삭제 실패', true);
        }
      }
    }

    function editBankAccount(bankEditBtn) {
      const bid = bankEditBtn.dataset.bankEditId;
      const bank = rawBankAccounts.find(b => b.id === bid);
      if (bank) openBankAccountDialog(bank);
    }

    async function deleteBankAccount(bankDelBtn) {
      const bid = bankDelBtn.dataset.bankDelId;
      if (confirm('이 은행 계좌를 삭제하시겠습니까?')) {
        try {
          await app.api(`/api/bank-accounts/${bid}`, { method: 'DELETE' });
          app.toast('은행 계좌가 삭제되었습니다.');
          await app.loadDashboard();
        } catch (err) {
          app.toast(err.message || '삭제 실패', true);
        }
      }
    }

    function bindSecuritiesYearlyForm() {
      // 연금/IRP 연도별 이력 관리 이벤트 (상단 입력값 -> 하단 이력에 추가/갱신)
      document.getElementById("addAccountYearlyBtn")?.addEventListener("click", (e) => {
        e.preventDefault();
        handleAddAccountYearly();
      });

      // 연도 입력창 변경 시 해당 연도 기존 이력 데이터 자동 로드 및 정규화
      document.getElementById("accountInputYear")?.addEventListener("change", (e) => {
        const rawYr = (e.target.value || "").trim();
        const yr = app.normalizeYear(rawYr);
        if (!yr) return;
        e.target.value = yr;
        const match = accountCurrentYearlyList.find(y => app.normalizeYear(y.year) === yr);
        const editForm = document.getElementById("accountEditForm");
        if (!editForm) return;
        const depInput = editForm.querySelector(".pension-annual-deposit");
        const dedInput = editForm.querySelector(".pension-tax-deductible");
        const incInput = editForm.querySelector(".pension-income-level");
        if (match) {
          if (depInput) depInput.value = (match.deposit !== undefined && match.deposit !== null) ? match.deposit : "";
          if (dedInput) dedInput.value = match.is_deductible !== false ? "true" : "false";
          if (incInput && match.income_level) incInput.value = match.income_level;
        }
        updateAccountTaxBenefitFields(editForm);
        app.refreshDialogKoreanHints(editForm);
      });

      document.getElementById("accountInputYear")?.addEventListener("blur", (e) => {
        const norm = app.normalizeYear(e.target.value);
        if (norm) e.target.value = norm;
      });

      document.getElementById("accountYearlyList")?.addEventListener("click", (e) => {
        const delBtn = e.target.closest(".account-yearly-del-btn");
        if (delBtn) {
          const idx = Number(delBtn.dataset.index);
          if (!isNaN(idx) && accountCurrentYearlyList[idx]) {
            const removedYr = accountCurrentYearlyList[idx].year;
            accountCurrentYearlyList.splice(idx, 1);
            if (editingAccountYearlyIndex === idx) {
              editingAccountYearlyIndex = null;
              resetAddAccountYearlyBtn();
            } else if (editingAccountYearlyIndex !== null && editingAccountYearlyIndex > idx) {
              editingAccountYearlyIndex--;
            }
            renderAccountYearlyFormRows();
            app.toast(`${removedYr}년 이력이 삭제되었습니다.`);

            // 상단 입력창이 삭제된 연도를 가리키고 있었다면 초기화하여 저장 시 부활 방지
            const editForm = document.getElementById("accountEditForm");
            const yrInput = editForm?.querySelector(".pension-entry-year");
            const depInput = editForm?.querySelector(".pension-annual-deposit");
            if (yrInput && app.normalizeYear(yrInput.value) === app.normalizeYear(removedYr)) {
              if (accountCurrentYearlyList.length > 0) {
                yrInput.value = accountCurrentYearlyList[0].year;
                if (depInput) depInput.value = accountCurrentYearlyList[0].deposit || "";
              } else {
                yrInput.value = String(new Date().getFullYear());
                if (depInput) depInput.value = "";
              }
              app.refreshDialogKoreanHints(editForm);
              updateAccountTaxBenefitFields(editForm);
            }
          }
          return;
        }

        const editBtn = e.target.closest(".account-yearly-edit-btn") || e.target.closest(".account-yearly-card");
        if (editBtn) {
          const idx = Number(editBtn.dataset.index);
          const item = accountCurrentYearlyList[idx];
          if (item) {
            editingAccountYearlyIndex = idx;
            const editForm = document.getElementById("accountEditForm");
            const yrInput = editForm?.querySelector(".pension-entry-year") || document.getElementById("accountInputYear");
            const depInput = editForm?.querySelector(".pension-annual-deposit") || document.getElementById("accountInputDeposit");
            const dedInput = editForm?.querySelector(".pension-tax-deductible") || document.getElementById("accountInputDeductible");
            const incInput = editForm?.querySelector(".pension-income-level") || document.getElementById("accountInputIncomeLevel");

            if (yrInput) yrInput.value = item.year || "";
            if (depInput) {
              depInput.value = item.deposit || "";
              app.refreshDialogKoreanHints(app.$("#accountEditDialog"));
              depInput.focus();
              depInput.select();
            }
            if (dedInput) dedInput.value = (item.is_deductible !== false && String(item.is_deductible) !== "false") ? "true" : "false";
            if (incInput) incInput.value = item.income_level || "low";

            setEditingAccountYearlyBtn(item.year || "");
            updateAccountTaxBenefitFields(editForm);
            app.toast(`[${item.year}년] 수정 모드: 연도나 납입액을 변경한 후 [수정 반영] 또는 하단 [저장]을 눌러주세요.`);
          }
          return;
        }
      });
    }

    return {
      publicActions: {
        renderAccounts,
        renderSavings,
        renderSavingsWithOwner,
        calcSavingInterestPreview,
        calcBankMinusPreview,
        openBankAccountDialog,
        openSavingAccountDialog,
        updateSavingAutoContributionFields,
        updateSavingTypeFields,
        calcLoanPreview,
        refreshLoanOverdraftBankOptions,
        openLoanAccountDialog,
        openIntegratedBankDialog,
        openAccountCashDialog,
        renderAccountYearlyFormRows,
        updateAccountTaxBenefitFields,
        resetAddAccountYearlyBtn,
        setEditingAccountYearlyBtn,
        handleAddAccountYearly,
        openAccountEditDialog,
        saveEditAccount,
        saveNewAccount,
      },
      actions: {
        bindBankForms,
        bindSecuritiesTaxPreview,
        bindLoanForm,
        bindAccountList,
        bindSaveButtons,
        openAccountAddDialog,
        editAccountFromRow,
        editLoanAccount,
        deleteLoanAccount,
        selectSavingsSubtab,
        editSavingAccount,
        deleteSavingAccount,
        editBankAccount,
        deleteBankAccount,
        bindSecuritiesYearlyForm,
      },
      get rawBankAccounts() { return rawBankAccounts; },
      get rawSavingsAccounts() { return rawSavingsAccounts; },
      get rawLoanAccounts() { return rawLoanAccounts; },
      loanTypeLabels: LOAN_TYPE_LABELS,
    };
  }

  window.WealthAccountFeatureController = { create };
})();
