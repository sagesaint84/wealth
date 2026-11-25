(() => {
  'use strict';

  function isAccountTaxDeductible(account) {
    if (!account) return true;
    const accountType = String(account.account_type || "").toLowerCase();
    if (accountType === "pension_savings_non_deductible" || accountType === "irp_non_deductible") return false;
    const val = account.tax_deductible;
    if (val === false || val === "false" || val === 0 || val === "0") return false;
    if (val === true || val === "true" || val === 1 || val === "1") return true;

    // 설정값이 없을 때(null / undefined)는 계좌명으로 스마트 판별
    const name = (account.name || account.account_name || "").toLowerCase();
    if (name.includes("공제x") || name.includes("공제 x") || name.includes("세액공제x") || name.includes("세액공제 x") || name.includes("비공제") || name.includes("미공제") || name.includes("공제제외") || name.includes("공제 안") || name.includes("공제안")) {
      return false;
    }
    return true;
  }

  function isContributionTaxDeductible(value) {
    return !(value === false || value === 0 || value === "0" || String(value).toLowerCase() === "false");
  }

  function isTaxAdvantagedAccount(account) {
    if (!account) return false;
    const aType = (account.account_type || "").toLowerCase();
    const aName = (account.name || account.account_name || "").toLowerCase();
    if (aType === "pension_savings" || aType === "pension_savings_non_deductible" || aType === "irp" || aType === "irp_non_deductible" || aType === "isa") return true;
    if (aName.includes("연금") || aName.includes("irp") || aName.includes("isa")) return true;
    return false;
  }

  function getTaxCategory(item) {
    if (!item) return 'pension_savings';
    const aType = (item.account_type || '').toLowerCase();
    const aName = (item.name || item.account_name || '').toLowerCase();
    if (aType === 'isa' || aName.includes('isa')) return 'isa';
    if (aType === 'irp' || aType === 'irp_non_deductible' || aName.includes('irp')) return 'irp';
    return 'pension_savings';
  }

  function calculateOwnerYearPensionTaxBenefits(accounts) {
    const pensionAccounts = (Array.isArray(accounts) ? accounts : []).filter(a => {
      return isTaxAdvantagedAccount(a) && getTaxCategory(a) !== 'isa';
    });
    const currentYear = String(new Date().getFullYear());

    const rateFor = (incomeLevel, fallback = 'low') => {
      const level = incomeLevel === 'high' || incomeLevel === 'low' ? incomeLevel : fallback;
      return level === 'high' ? 0.132 : 0.165;
    };
    const safeAmount = value => {
      const amount = Number(value);
      return Number.isFinite(amount) ? Math.max(0, amount) : 0;
    };
    const emptyTotals = () => ({
      eligibleContribution: 0,
      pensionEligibleContribution: 0,
      irpEligibleContribution: 0,
      isaDeductionTarget: 0,
      taxSaved: 0,
      pensionTaxSaved: 0,
      irpTaxSaved: 0,
    });

    const allocate = entries => {
      const totals = emptyTotals();
      const byOwner = {};
      const byOwnerYear = {};
      const byAccount = {};
      const grouped = new Map();
      entries.forEach(entry => {
        const key = `${entry.owner}\u0000${entry.year}`;
        if (!grouped.has(key)) grouped.set(key, []);
        grouped.get(key).push(entry);
      });

      grouped.forEach(groupEntries => {
        let pensionRemaining = 6000000;
        let combinedRemaining = 9000000;
        const groupTotals = emptyTotals();
        for (const category of ['pension_savings', 'irp']) {
          groupEntries.forEach(entry => {
            if (entry.category !== category) return;
            let eligible = Math.min(entry.deposit, combinedRemaining);
            if (category === 'pension_savings') {
              eligible = Math.min(eligible, pensionRemaining);
              pensionRemaining -= eligible;
            }
            combinedRemaining -= eligible;
            const saved = Math.floor(eligible * entry.rate);
            if (!byAccount[entry.accountKey]) byAccount[entry.accountKey] = emptyTotals();
            const accountTotals = byAccount[entry.accountKey];
            groupTotals.eligibleContribution += eligible;
            groupTotals.taxSaved += saved;
            accountTotals.eligibleContribution += eligible;
            accountTotals.taxSaved += saved;
            if (category === 'pension_savings') {
              groupTotals.pensionEligibleContribution += eligible;
              groupTotals.pensionTaxSaved += saved;
              accountTotals.pensionEligibleContribution += eligible;
              accountTotals.pensionTaxSaved += saved;
            } else {
              groupTotals.irpEligibleContribution += eligible;
              groupTotals.irpTaxSaved += saved;
              accountTotals.irpEligibleContribution += eligible;
              accountTotals.irpTaxSaved += saved;
            }
          });
        }

        const first = groupEntries[0];
        const ownerTotals = byOwner[first.owner] || emptyTotals();
        Object.keys(groupTotals).forEach(key => {
          totals[key] += groupTotals[key];
          ownerTotals[key] += groupTotals[key];
        });
        byOwner[first.owner] = ownerTotals;
        byOwnerYear[`${first.owner}\u0000${first.year}`] = groupTotals;
      });
      return { ...totals, byOwner, byOwnerYear, byAccount };
    };

    const currentEntries = [];
    const cumulativeEntries = [];
    const currentIsaByCategory = { pension_savings: 0, irp: 0 };
    const cumulativeIsaByCategory = { pension_savings: 0, irp: 0 };
    const currentIsaByOwner = {};
    const cumulativeIsaByOwner = {};
    const currentIsaTargetByOwner = {};
    const cumulativeIsaTargetByOwner = {};
    const currentIsaByAccount = {};
    const cumulativeIsaByAccount = {};

    pensionAccounts.forEach(account => {
      const accountKey = String(account.id || '');
      const owner = String(account.owner || '모두');
      const category = getTaxCategory(account);
      const defaultIncomeLevel = account.income_level === 'high' ? 'high' : 'low';
      const accountDeductible = isAccountTaxDeductible(account)
        && !String(account.account_type || '').toLowerCase().endsWith('_non_deductible');
      const currentRate = rateFor(defaultIncomeLevel);
      if (accountDeductible) {
        currentEntries.push({
          owner,
          year: currentYear,
          accountKey,
          category,
          deposit: safeAmount(account.annual_deposit),
          rate: currentRate,
        });
      }

      const isaTarget = Math.min(safeAmount(account.isa_transfer_amount) * 0.10, 3000000);
      const currentIsaSaved = Math.floor(isaTarget * currentRate);
      currentIsaByCategory[category] += currentIsaSaved;
      currentIsaByOwner[owner] = (currentIsaByOwner[owner] || 0) + currentIsaSaved;
      currentIsaTargetByOwner[owner] = (currentIsaTargetByOwner[owner] || 0) + isaTarget;
      currentIsaByAccount[accountKey] = {
        category,
        saved: (currentIsaByAccount[accountKey]?.saved || 0) + currentIsaSaved,
        target: (currentIsaByAccount[accountKey]?.target || 0) + isaTarget,
      };

      const yearly = Array.isArray(account.yearly_contributions) ? account.yearly_contributions : [];
      if (yearly.length > 0) {
        if (!accountDeductible) return;
        yearly.forEach(contribution => {
          if (!isContributionTaxDeductible(contribution.is_deductible)) return;
          cumulativeEntries.push({
            owner,
            year: String(contribution.year || '').trim(),
            accountKey,
            category,
            deposit: safeAmount(contribution.deposit),
            rate: rateFor(contribution.income_level, defaultIncomeLevel),
          });
        });
      } else {
        if (accountDeductible) {
          cumulativeEntries.push({
            owner,
            year: currentYear,
            accountKey,
            category,
            deposit: safeAmount(account.annual_deposit),
            rate: currentRate,
          });
        }
        cumulativeIsaByCategory[category] += currentIsaSaved;
        cumulativeIsaByOwner[owner] = (cumulativeIsaByOwner[owner] || 0) + currentIsaSaved;
        cumulativeIsaTargetByOwner[owner] = (cumulativeIsaTargetByOwner[owner] || 0) + isaTarget;
        cumulativeIsaByAccount[accountKey] = {
          category,
          saved: (cumulativeIsaByAccount[accountKey]?.saved || 0) + currentIsaSaved,
          target: (cumulativeIsaByAccount[accountKey]?.target || 0) + isaTarget,
        };
      }
    });

    const current = allocate(currentEntries);
    const cumulative = allocate(cumulativeEntries);
    const addIsa = (result, byCategory, byOwner, targetByOwner, byAccount) => {
      result.pensionTaxSaved += byCategory.pension_savings;
      result.irpTaxSaved += byCategory.irp;
      result.taxSaved += byCategory.pension_savings + byCategory.irp;
      Object.entries(byOwner).forEach(([owner, saved]) => {
        if (!result.byOwner[owner]) result.byOwner[owner] = emptyTotals();
        result.byOwner[owner].taxSaved += saved;
      });
      Object.entries(targetByOwner).forEach(([owner, target]) => {
        if (!result.byOwner[owner]) result.byOwner[owner] = emptyTotals();
        result.isaDeductionTarget += target;
        result.byOwner[owner].isaDeductionTarget += target;
      });
      Object.entries(byAccount).forEach(([accountKey, allocation]) => {
        if (!result.byAccount[accountKey]) result.byAccount[accountKey] = emptyTotals();
        const accountTotals = result.byAccount[accountKey];
        accountTotals.isaDeductionTarget += allocation.target;
        accountTotals.taxSaved += allocation.saved;
        if (allocation.category === 'pension_savings') {
          accountTotals.pensionTaxSaved += allocation.saved;
        } else {
          accountTotals.irpTaxSaved += allocation.saved;
        }
      });
    };
    addIsa(current, currentIsaByCategory, currentIsaByOwner, currentIsaTargetByOwner, currentIsaByAccount);
    addIsa(cumulative, cumulativeIsaByCategory, cumulativeIsaByOwner, cumulativeIsaTargetByOwner, cumulativeIsaByAccount);

    return { current, cumulative };
  }

  function calcAccountCumulativeTaxSaved(account, accounts) {
    if (!account || !Array.isArray(accounts)) return 0;
    const category = getTaxCategory(account);
    if (category !== 'pension_savings' && category !== 'irp') return 0;
    const owner = String(account.owner || '모두');
    const benefits = calculateOwnerYearPensionTaxBenefits(accounts);
    return benefits.cumulative.byOwner[owner]?.taxSaved || 0;
  }

  window.WealthPensionTaxModel = Object.freeze({
    isAccountTaxDeductible,
    isContributionTaxDeductible,
    isTaxAdvantagedAccount,
    getTaxCategory,
    calculateOwnerYearPensionTaxBenefits,
    calcAccountCumulativeTaxSaved,
  });
})();
