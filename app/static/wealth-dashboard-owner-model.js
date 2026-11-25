(() => {
  'use strict';

  function selectOwnedAccounts(accounts, owner) {
    return owner === '모두' ? accounts : accounts.filter(account => (account.owner || '모두') === owner);
  }

  function selectAccountsAndHoldings(source, owner) {
    if (owner === '모두') {
      return { accounts: source.accounts || [], holdings: source.holdings || [] };
    }

    const accounts = selectOwnedAccounts(source.accounts || [], owner);
    const ownedIds = new Set(accounts.map(account => account.id));
    const holdings = (source.holdings || []).filter(holding =>
      ownedIds.has(holding.account_id) || (holding.owner && holding.owner === owner)
    );
    return { accounts, holdings };
  }

  function propertyOwnerShare(r, owner) {
    const ownerships = (r.ownerships && r.ownerships.length)
      ? r.ownerships
      : [{ owner: r.owner || '모두', ratio: 100 }];

    let share = 1.0;
    if (owner !== '모두') {
      let matched = ownerships.find(x => x.owner === owner);
      if (!matched && r.owner && r.owner.includes(owner)) {
        const m = r.owner.match(new RegExp(`${owner}\\s*([0-9.]+)%`));
        if (m) {
          share = parseFloat(m[1]) / 100;
        } else {
          share = 0.5;
        }
      } else if (matched && matched.ratio > 0) {
        share = (matched.ratio || 100) / 100;
      } else {
        return null;
      }
    }

    return share;
  }

  // ── 필터링된 데이터로 핵심 요약 재계산 ──────────────────────────────────────
  function computeFilteredSummary(accounts, holdings, fxRates) {
    const usdKrw = (fxRates || {})['USD'] || 1385;
    let total_stock_value_krw = 0, total_cash_krw = 0, total_cost_krw = 0, profit_krw = 0;
    let cash_krw = 0, cash_usd = 0;

    holdings.forEach(h => {
      total_stock_value_krw += Number(h.market_value_krw || 0);
      total_cost_krw        += Number(h.cost_value_krw  || 0);
      profit_krw            += Number(h.profit_krw      || 0);
    });
    accounts.forEach(a => {
      cash_krw += Number(a.cash_krw || 0);
      cash_usd += Number(a.cash_usd || 0);
    });
    total_cash_krw = cash_krw + cash_usd * usdKrw;
    const total_value_krw = total_stock_value_krw + total_cash_krw;
    const return_rate = total_cost_krw > 0 ? (profit_krw / total_cost_krw) * 100 : 0;
    return {
      total_value_krw, total_stock_value_krw, total_cash_krw,
      total_cost_krw, profit_krw, return_rate, cash_krw, cash_usd,
      holding_count: holdings.length,
      account_count: accounts.length,
    };
  }

  const KR_ETF_PREFIXES = ['KODEX','TIGER','ACE','SOL','PLUS','RISE','HANARO','KOSEF','ARIRANG','KOACT','WON','1Q','KIWOOM','TIMEFOLIO','WOORI','KBSTAR'];
  const OVERSEAS_KEYWORDS = ['미국','S&P','나스닥','NASDAQ','다우','DOW','글로벌','GLOBAL','차이나','중국','CHINA','인도','INDIA','일본','JAPAN','TOPIX','NIKKEI','유로','EURO','베트남','VIETNAM','FANG','필라델피아','빅테크','BIG TECH','월드','WORLD','선진국','신흥국','MSCI','유럽','대만','해외'];
  const US_ETF_TICKERS = new Set([
    'QQQ','QQQM','SPY','VOO','IVV','TLT','TQQQ','QLD','SOXL','SOXS','SQQQ','SCHD','JEPI','JEPQ','DIA','IWM','VNQ','GLD','SLV','SPYG',
    'QNDX','SMH','XLK','XLE','XLF','XLV','XLY','XLP','XLI','XLU','XLRE','XLB','IEF','SHY','BND','AGG','VT','VTI','VXUS','ARKK',
    'BIL','SHV','VGK','EEM','VWO','HYG','LQD','JNK','TMF','UPRO','SPXU','LABU','LABD','NUGT','DUST','FNGU','BULZ'
  ]);

  function classifyHolding(h) {
    const name = h.name || '';
    const nameUpper = name.toUpperCase();
    const codeUpper = (h.code || '').toUpperCase().trim();
    const currency = (h.currency || 'KRW').toUpperCase();

    if (currency === 'KRW') {
      const isKrEtf = KR_ETF_PREFIXES.some(p => nameUpper.startsWith(p)) || nameUpper.includes('ETF');
      if (isKrEtf) {
        if (OVERSEAS_KEYWORDS.some(k => nameUpper.includes(k))) return '국내상장해외ETF';
        return '국내ETF';
      }
      return '국내주식';
    } else {
      if (
        US_ETF_TICKERS.has(codeUpper) ||
        nameUpper.includes('ETF') ||
        nameUpper.includes('TRUST') ||
        nameUpper.includes('FUND') ||
        nameUpper.includes('ISHARES') ||
        nameUpper.includes('VANGUARD') ||
        nameUpper.includes('INVESCO') ||
        nameUpper.includes('SPDR')
      ) {
        return '해외ETF';
      }
      return '해외주식';
    }
  }

  function computeFilteredClassifications(holdings, accounts, fxRates, owner = '모두', rawData = null, inputs = {}) {
    const usdKrw = (fxRates || {})['USD'] || 1385;
    const groups = {};
    let totalValue = 0;
    const src = rawData || inputs.rawDashboard || {};

    const filterByOwner = arr => selectOwnedAccounts(arr || [], owner);

    // 1. 부동산 순에퀴티 (자가 & 임대 투자자산) 및 임차보증금 (안전자산)
    const allREs = src.real_estates || inputs.rawRealEstates || [];
    let totalREInvestEquity = 0;
    let totalTenantDepositVal = 0;
    let reInvestCount = 0;
    let reLeaseCount = 0;

    allREs.forEach(r => {
      const share = propertyOwnerShare(r, owner);
      if (share === null) return;

      const pType = r.property_type || 'own';
      if (pType !== 'lease') {
        const pVal = (Number(r.current_price) || 0) * share;
        totalREInvestEquity += pVal;
        reInvestCount += 1;
      } else {
        totalTenantDepositVal += ((Number(r.deposit_amount) || 0) * share);
        reLeaseCount += 1;
      }
    });

    if (totalREInvestEquity > 0) {
      groups['부동산'] = {
        name: '부동산',
        market_value_krw: totalREInvestEquity,
        cost_value_krw: totalREInvestEquity,
        profit_krw: 0,
        holding_count: reInvestCount,
      };
      totalValue += totalREInvestEquity;
    }

    if (totalTenantDepositVal > 0) {
      groups['임차보증금'] = {
        name: '임차보증금',
        market_value_krw: totalTenantDepositVal,
        cost_value_krw: totalTenantDepositVal,
        profit_krw: 0,
        holding_count: reLeaseCount,
      };
      totalValue += totalTenantDepositVal;
    }

    // 2. 주식 및 ETF 보유종목 분류
    holdings.forEach(h => {
      let name = classifyHolding(h);
      if (name === '해외주식') name = '해외ETF'; // 해외ETF / 해외주식 통합 표시
      if (!groups[name]) groups[name] = { name, market_value_krw: 0, cost_value_krw: 0, profit_krw: 0, holding_count: 0 };
      const g = groups[name];
      g.market_value_krw += Number(h.market_value_krw || 0);
      g.cost_value_krw   += Number(h.cost_value_krw   || 0);
      g.profit_krw       += Number(h.profit_krw        || 0);
      g.holding_count    += 1;
      totalValue         += Number(h.market_value_krw || 0);
    });

    // 3. 현금·예수금 (증권사 예수금 + 은행 입출금 잔액 + 예적금 잔액)
    let cashKrw = 0, cashUsd = 0;
    (accounts || []).forEach(a => {
      cashKrw += Number(a.cash_krw || a.cash || 0);
      cashUsd += Number(a.cash_usd || 0);
    });
    const stockCashTotal = cashKrw + cashUsd * usdKrw;

    const curBanks = filterByOwner(src.bank_accounts || inputs.rawBankAccounts || []);
    const bankCashTotal = curBanks.reduce((acc, b) => acc + Math.max(0, Number(b.balance) || 0), 0);

    const curSavings = filterByOwner(src.savings_accounts || inputs.rawSavingsAccounts || []);
    const savingsTotal = curSavings.reduce((acc, s) => acc + (Number(s.current_value) || Number(s.current_paid_amount) || Number(s.balance) || 0), 0);

    const totalAllCash = stockCashTotal + bankCashTotal + savingsTotal;
    if (totalAllCash > 0) {
      groups['현금·예수금'] = {
        name: '현금·예수금',
        market_value_krw: totalAllCash,
        cost_value_krw: totalAllCash,
        profit_krw: 0,
        holding_count: (accounts || []).length + curBanks.length + curSavings.length,
      };
      totalValue += totalAllCash;
    }

    // 4. 보험 (해약환급금 / 예상 수령액 / 20년 환산 총자산)
    const curInsurances = filterByOwner(src.insurance_accounts || inputs.rawInsuranceAccounts || []);
    const insuranceTotal = curInsurances.reduce((acc, ins) => acc + (Number(ins.expected_amount) || Number(ins.converted_total_asset) || Number(ins.total_paid_amount) || Number(ins.expected_refund_amount) || Number(ins.accumulated_paid_amount) || 0), 0);
    if (insuranceTotal > 0) {
      groups['보험'] = {
        name: '보험',
        market_value_krw: insuranceTotal,
        cost_value_krw: insuranceTotal,
        profit_krw: 0,
        holding_count: curInsurances.length,
      };
      totalValue += insuranceTotal;
    }

    return Object.values(groups).map(g => ({
      ...g,
      return_rate: g.cost_value_krw > 0 ? (g.profit_krw / g.cost_value_krw) * 100 : 0,
      weight: totalValue > 0 ? (g.market_value_krw / totalValue) * 100 : 0,
    })).sort((a, b) => (b.weight || 0) - (a.weight || 0));
  }

  function computeFilteredSectors(holdings, accounts, fxRates) {
    const usdKrw = (fxRates || {})['USD'] || 1385;
    const groups = {};
    let totalValue = 0;
    holdings.forEach(h => {
      const sec = h.sector || '기타';
      if (!groups[sec]) groups[sec] = { name: sec, market_value_krw: 0, cost_value_krw: 0, profit_krw: 0, holding_count: 0 };
      const g = groups[sec];
      g.market_value_krw += Number(h.market_value_krw || 0);
      g.cost_value_krw   += Number(h.cost_value_krw   || 0);
      g.profit_krw       += Number(h.profit_krw        || 0);
      g.holding_count    += 1;
      totalValue         += Number(h.market_value_krw || 0);
    });
    let cashKrw = 0, cashUsd = 0;
    (accounts || []).forEach(a => {
      cashKrw += Number(a.cash_krw || 0);
      cashUsd += Number(a.cash_usd || 0);
    });
    const totalCash = cashKrw + cashUsd * usdKrw;
    if (totalCash > 0) {
      groups['현금·예수금'] = {
        name: '현금·예수금', market_value_krw: totalCash,
        cost_value_krw: totalCash, profit_krw: 0, holding_count: 0,
      };
      totalValue += totalCash;
    }
    return Object.values(groups).map(g => ({
      ...g,
      return_rate: g.cost_value_krw > 0 ? (g.profit_krw / g.cost_value_krw) * 100 : 0,
      weight: totalValue > 0 ? (g.market_value_krw / totalValue) * 100 : 0,
    })).sort((a, b) => b.market_value_krw - a.market_value_krw);
  }

  function computeFilteredCurrencySummary(holdings, accounts, fxRates) {
    const usdKrw = (fxRates || {})['USD'] || 1385;
    let krwStock = 0, usdStock = 0;
    let krwCash = 0, usdCash = 0;
    holdings.forEach(h => {
      if (h.currency === 'KRW') krwStock += Number(h.market_value_krw || 0);
      else usdStock += Number(h.market_value || (Number(h.market_value_krw || 0) / usdKrw));
    });
    accounts.forEach(a => {
      krwCash += Number(a.cash_krw || 0);
      usdCash += Number(a.cash_usd || 0);
    });
    return {
      KRW: {
        currency: 'KRW',
        stock_value_krw: krwStock,
        cash: krwCash,
        market_value_krw: krwStock + krwCash,
      },
      USD: {
        currency: 'USD',
        stock_value: usdStock,
        cash: usdCash,
        market_value: usdStock + usdCash,
        market_value_krw: (usdStock + usdCash) * usdKrw,
      },
    };
  }

  function computeFilteredDayChange(holdings, rawDayChange, owner = '모두', currentTotalValue = 0, inputs = {}) {
    const targetOwner = owner || '모두';
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const dayStr = String(now.getDate()).padStart(2, '0');
    const todayStr = `${year}-${month}-${dayStr}`;

    // 1. 자산기록(allAssetRecords)에서 오늘 이전(date < todayStr)의 해당 owner 직전 기록 찾기
    const ownerRecords = (inputs.allAssetRecords || []).filter(r =>
      (r.owner || '모두') === targetOwner &&
      r.date &&
      r.date < todayStr &&
      Number(r.total_value_krw || 0) > 0
    );

    if (ownerRecords.length > 0) {
      ownerRecords.sort((a, b) => String(a.date).localeCompare(String(b.date)));
      const lastRec = ownerRecords[ownerRecords.length - 1];
      const prevVal = Number(lastRec.total_value_krw || 0);
      const prevDate = lastRec.date;
      const change_krw = currentTotalValue - prevVal;
      const change_rate = prevVal > 0 ? (change_krw / prevVal) * 100 : 0;
      return {
        day_profit_krw: null,
        price_profit_status: 'unavailable',
        record_change_rate: change_rate,
        record_change_krw: change_krw,
        change_rate,
        change_krw,
        date: prevDate,
        value_krw: prevVal,
      };
    }

    // A display-only 1D rate without prior session provenance must never be
    // promoted to today's canonical price P/L.
    return {
      day_profit_krw: null,
      price_profit_status: 'unavailable',
      record_change_rate: null,
      record_change_krw: null,
      change_rate: null,
      change_krw: null,
      date: (rawDayChange || {}).date || "전일",
    };
  }

  function calculateDashboardDebt(bankAccounts, loanAccounts) {
    const banks = Array.isArray(bankAccounts) ? bankAccounts : [];
    const loans = Array.isArray(loanAccounts) ? loanAccounts : [];
    const totalPureDebt = loans.reduce((acc, loan) => acc + (Number(loan.current_balance) || 0), 0);
    const representedOverdraftBanks = new Set(
      loans
        .filter(loan => (
          String(loan.loan_type || "") === "minus"
          && String(loan.overdraft_bank_account_id || "").trim()
          && (Number(loan.current_balance) || 0) > 0
        ))
        .map(loan => `${String(loan.owner || "모두")}\u0000${String(loan.overdraft_bank_account_id).trim()}`)
    );
    const totalMinusBankDebt = banks.reduce((acc, bank) => {
      const balance = Number(bank.balance) || 0;
      if (balance >= 0) return acc;
      const relationshipKey = `${String(bank.owner || "모두")}\u0000${String(bank.id || "").trim()}`;
      return representedOverdraftBanks.has(relationshipKey) ? acc : acc + Math.abs(balance);
    }, 0);
    return { totalPureDebt, totalMinusBankDebt };
  }

  function finiteRealizedPnlNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function summarizeRealizedPnlRows(records) {
    const rows = Array.isArray(records) ? records : [];
    let totalPnlKrw = 0;
    let convertedRecordCount = 0;
    let unconvertedRecordCount = 0;
    let winCount = 0;
    let lossCount = 0;
    rows.forEach(record => {
      const pnlKrw = finiteRealizedPnlNumber(record?.pnl_krw);
      if (pnlKrw === null) unconvertedRecordCount += 1;
      else {
        totalPnlKrw += pnlKrw;
        convertedRecordCount += 1;
      }
      const nativePnl = finiteRealizedPnlNumber(record?.pnl);
      const signValue = nativePnl === null ? pnlKrw : nativePnl;
      if (signValue > 0) winCount += 1;
      else if (signValue < 0) lossCount += 1;
    });
    const classifiedCount = winCount + lossCount;
    return {
      totalPnlKrw,
      convertedRecordCount,
      unconvertedRecordCount,
      recordCount: rows.length,
      winCount,
      lossCount,
      winRate: classifiedCount ? (winCount / classifiedCount) * 100 : 0,
      summaryComplete: unconvertedRecordCount === 0,
    };
  }

  function buildRealizedPnlDisplaySummary(summary = {}, records = [], preferCanonical = true) {
    const rowSummary = summarizeRealizedPnlRows(records);
    const canonicalTotal = finiteRealizedPnlNumber(summary?.total_pnl_krw);
    const canonicalUnconverted = finiteRealizedPnlNumber(summary?.unconverted_record_count);
    const canonicalConverted = finiteRealizedPnlNumber(summary?.converted_record_count);
    const canonicalRecordCount = finiteRealizedPnlNumber(summary?.record_count);
    const canonicalWinRate = finiteRealizedPnlNumber(summary?.win_rate);
    const useCanonical = preferCanonical && canonicalTotal !== null;
    const unconvertedRecordCount = useCanonical && canonicalUnconverted !== null
      ? canonicalUnconverted : rowSummary.unconvertedRecordCount;
    const summaryComplete = useCanonical && typeof summary?.summary_complete === 'boolean'
      ? summary.summary_complete : unconvertedRecordCount === 0;
    return {
      totalPnlKrw: useCanonical ? canonicalTotal : rowSummary.totalPnlKrw,
      convertedRecordCount: useCanonical && canonicalConverted !== null ? canonicalConverted : rowSummary.convertedRecordCount,
      unconvertedRecordCount,
      recordCount: useCanonical && canonicalRecordCount !== null ? canonicalRecordCount : rowSummary.recordCount,
      winRate: useCanonical && canonicalWinRate !== null ? canonicalWinRate : rowSummary.winRate,
      summaryComplete,
      canonicalUsed: useCanonical,
      completenessNote: summaryComplete
        ? ''
        : (unconvertedRecordCount > 0 ? `미환산 해외 실현손익 ${unconvertedRecordCount}건 포함` : '원화 실현손익 합계 미완성'),
    };
  }

  function buildOwnerDashboard(src, effectiveOwner, inputs) {
    const filteredData = Object.assign({}, src);

    if (effectiveOwner !== '모두') {
      const owned = selectAccountsAndHoldings(src, effectiveOwner);
      filteredData.accounts = owned.accounts;
      filteredData.holdings = owned.holdings;

      filteredData.summary               = computeFilteredSummary(filteredData.accounts, filteredData.holdings, src.fx_rates);
      filteredData.classifications       = computeFilteredClassifications(filteredData.holdings, filteredData.accounts, src.fx_rates, effectiveOwner, src, inputs);
      filteredData.sector_classifications= computeFilteredSectors(filteredData.holdings, filteredData.accounts, src.fx_rates);
      filteredData.currency_summary      = computeFilteredCurrencySummary(filteredData.holdings, filteredData.accounts, src.fx_rates);
      filteredData.day_change            = src.daily_metrics_by_owner?.[effectiveOwner]
        || computeFilteredDayChange(filteredData.holdings, src.day_change, effectiveOwner, filteredData.summary?.total_stock_value_krw, inputs);
    } else {
      filteredData.accounts              = src.accounts               || [];
      filteredData.holdings              = src.holdings               || [];
      filteredData.summary               = src.summary                || {};
      filteredData.classifications       = computeFilteredClassifications(filteredData.holdings, filteredData.accounts, src.fx_rates, '모두', src, inputs);
      filteredData.sector_classifications= src.sector_classifications || [];
      filteredData.currency_summary      = src.currency_summary       || {};
      filteredData.day_change            = src.daily_metrics_by_owner?.['모두'] || src.day_change || {};
    }

    return filteredData;
  }

  function buildDashboardSummary(data, o, inputs, getKstYearMonth) {
    const s = data.summary || {}, currencies = data.currency_summary || {};
    const krw = currencies.KRW || {}, usd = currencies.USD || {};
    const filterByOwner = arr => selectOwnedAccounts(arr || [], o);

    // 1. 총 부채 및 자산 계산
    const curLoans = filterByOwner(data.loan_accounts || inputs.rawLoanAccounts || []);
    const curBanks = filterByOwner(data.bank_accounts || inputs.rawBankAccounts || []);
    const curSavings = filterByOwner(data.savings_accounts || inputs.rawSavingsAccounts || []);
    const curInsurances = filterByOwner(data.insurance_accounts || inputs.rawInsuranceAccounts || []);
    const allREs = data.real_estates || inputs.rawRealEstates || [];

    const posBanks = curBanks.filter(b => (Number(b.balance) || 0) >= 0);

    const totalInvestVal = Number(s.total_value_krw || 0);
    const totalStockVal = s.total_stock_value_krw || (totalInvestVal - Number(s.total_cash_krw || 0));
    const totalPositiveBankVal = posBanks.reduce((acc, b) => acc + (Number(b.balance) || 0), 0);
    const totalSavingVal = curSavings.reduce((acc, sv) => acc + (Number(sv.current_value) || Number(sv.current_paid_amount) || Number(sv.balance) || 0), 0);
    const totalAllCash = Number(s.total_cash_krw || 0) + totalPositiveBankVal + totalSavingVal;
    const insuranceTotal = curInsurances.reduce((acc, ins) => acc + (Number(ins.expected_amount) || Number(ins.converted_total_asset) || Number(ins.total_paid_amount) || Number(ins.expected_refund_amount) || Number(ins.accumulated_paid_amount) || 0), 0);

    const { totalMinusBankDebt, totalPureDebt } = calculateDashboardDebt(curBanks, curLoans);

    // 부동산 순에퀴티 & 전세보증금 부채 & 평가손익(예상 수익)
    let totalREVal = 0;
    let totalREPurchaseVal = 0;
    let totalREProfit = 0;
    let totalTenantDepositVal = 0;
    let totalLandlordDepositDebt = 0;
    let totalREInvestEquity = 0;

    allREs.forEach(r => {
      const share = propertyOwnerShare(r, o);
      if (share === null) return;

      const pType = r.property_type || 'own';
      if (pType !== 'lease') {
        const pVal = (Number(r.current_price) || 0) * share;
        const purchVal = (Number(r.purchase_price) || 0) * share;
        const depDebt = pType === 'rental' ? ((Number(r.deposit_amount) || 0) * share) : 0;
        totalREVal += pVal;
        totalLandlordDepositDebt += depDebt;
        totalREInvestEquity += pVal; // 부동산 시세 100% 반영
        if (purchVal > 0) {
          totalREPurchaseVal += purchVal;
          totalREProfit += (pVal - purchVal);
        } else if (pVal > 0) {
          totalREPurchaseVal += pVal;
        }
      } else {
        const depVal = ((Number(r.deposit_amount) || 0) * share);
        totalTenantDepositVal += depVal;
      }
    });

    const totalAllDebt = totalPureDebt + totalMinusBankDebt + totalLandlordDepositDebt;
    const totalInvestAssets = totalREInvestEquity + totalStockVal;
    const totalSafeAssets = totalAllCash + totalTenantDepositVal + insuranceTotal;
    const netWorth = (totalInvestAssets + totalSafeAssets) - totalAllDebt;

    // 4. 총 실현손익 (연도별/월별 실시간 집계 - 주식/공모주 순수 실현손익)
    const curRealized = data.realized_pnl_summary || inputs.rawDashboard?.realized_pnl_summary || {};
    const rawPnlList = data.realized_pnl_records || inputs.rawDashboard?.realized_pnl_records || inputs.pnlData?.records || [];
    // 부동산 매도 기록 완전 배제 (주식/공모주 실현손익만 엄격 집계)
    const isReRec = (r) => {
      const at = String(r.asset_type || '').toLowerCase();
      const c = String(r.code || '').toUpperCase();
      const b = String(r.broker || '').trim();
      const n = String(r.name || '');
      return at === 'real_estate' || c === 'REAL_ESTATE' || b === '부동산' || n.startsWith('[부동산]') || Boolean(r.re_id) || Boolean(r.real_estate_name);
    };
    const stockPnlRecords = rawPnlList.filter(r => !isReRec(r));
    const pnlRecords = filterByOwner(stockPnlRecords);

    const currentPeriod = getKstYearMonth();
    const currFullYear = String(currentPeriod.year);
    const currYear2Digit = currFullYear.slice(2);
    const currMonthNum = currentPeriod.month;
    const currMonthStr = currMonthNum < 10 ? `0${currMonthNum}` : `${currMonthNum}`;
    const currYearMonthPrefix = `${currFullYear}-${currMonthStr}`;

    const realizedView = buildRealizedPnlDisplaySummary(curRealized, pnlRecords, o === '모두');
    const totalRealizedKrw = realizedView.totalPnlKrw;
    let yearRealizedKrw = 0;
    let monthRealizedKrw = 0;

    if (pnlRecords.length > 0) {
      pnlRecords.forEach(r => {
        const compactDate = String(r.date || '').replaceAll('-', '');
        const p = finiteRealizedPnlNumber(r.pnl_krw);
        if (p === null) return;
        if (compactDate.startsWith(currFullYear)) yearRealizedKrw += p;
        if (compactDate.startsWith(`${currFullYear}${currMonthStr}`)) monthRealizedKrw += p;
      });
    }

    // 5. 총 배당금 및 이자 (연도별/월별 실시간 집계)
    const curDiv = data.dividend_summary || inputs.rawDashboard?.dividend_summary || {};
    const divRecords = filterByOwner(data.actual_dividend_records || inputs.rawDashboard?.actual_dividend_records || inputs.actualDividendData?.records || []);

    let totalActualDivKrw = Number(curDiv.total_actual_dividend_krw || curDiv.actual_dividend_krw || 0);
    let yearActualDivKrw = 0;
    let monthActualDivKrw = 0;

    if (divRecords.length > 0) {
      divRecords.forEach(r => {
        const d = String(r.date || '');
        const amt = Number(r.amount_krw || r.dividend_krw || r.amount || 0);
        if (d.startsWith(currFullYear)) yearActualDivKrw += amt;
        if (d.startsWith(currYearMonthPrefix)) monthActualDivKrw += amt;
      });
      if (o !== '모두') {
        totalActualDivKrw = divRecords.reduce((sum, r) => sum + Number(r.amount_krw || r.dividend_krw || r.amount || 0), 0);
      }
    }

    // 통합 실현손익 (매매차익 + 배당금 및 이자)
    const combinedRealizedKrw = totalRealizedKrw + totalActualDivKrw;
    const combinedYearRealizedKrw = yearRealizedKrw + yearActualDivKrw;
    const combinedMonthRealizedKrw = monthRealizedKrw + monthActualDivKrw;

    // 원화 및 달러 주식 세부 계산 (소유자별 보유종목 직접 정밀 집계)
    const allHoldings = data.holdings || inputs.rawDashboard?.holdings || [];
    const ownedAcctIds = new Set((data.accounts || []).map(a => a.id));
    const curHoldings = o === '모두'
      ? allHoldings
      : allHoldings.filter(h => (h.owner && h.owner === o) || ownedAcctIds.has(h.account_id) || (h.owner || '모두') === o);

    const usdKrwRate = (data.fx_rates || inputs.rawDashboard?.fx_rates || {})['USD'] || 1385;
    let krwStockVal = 0, krwStockCost = 0;
    let usdStockValUsd = 0, usdStockValKrw = 0, usdStockCostUsd = 0, usdStockCostKrw = 0;
    let krwHoldingCount = 0, usdHoldingCount = 0;

    curHoldings.forEach(h => {
      const curr = (h.currency || 'KRW').toUpperCase();
      const mValKrw = Number(h.market_value_krw || 0);
      const cValKrw = Number(h.cost_value_krw || 0);
      const mValNative = Number(h.market_value != null ? h.market_value : (mValKrw / usdKrwRate));
      const cValNative = Number(h.cost_value != null ? h.cost_value : (cValKrw / usdKrwRate));

      if (curr === 'KRW') {
        krwStockVal += mValKrw;
        krwStockCost += cValKrw;
        krwHoldingCount += 1;
      } else {
        usdStockValUsd += mValNative;
        usdStockValKrw += mValKrw || (mValNative * usdKrwRate);
        usdStockCostUsd += cValNative;
        usdStockCostKrw += cValKrw || (cValNative * usdKrwRate);
        usdHoldingCount += 1;
      }
    });

    const krwStockProfit = krwStockVal - krwStockCost;
    const krwStockReturnRate = krwStockCost > 0 ? (krwStockProfit / krwStockCost) * 100 : 0;

    const usdStockProfitUsd = usdStockValUsd - usdStockCostUsd;
    const usdStockProfitKrw = usdStockValKrw - usdStockCostKrw;
    const usdStockReturnRate = usdStockCostUsd > 0 ? (usdStockProfitUsd / usdStockCostUsd) * 100 : 0;

    // HOME keeps the combined stock and property totals.
    const totalExpectedProfit = (Number(s.profit_krw) || 0) + totalREProfit;
    const stockPurchaseCost = Math.max(0, totalStockVal - (Number(s.profit_krw) || 0));
    const totalCombinedCost = stockPurchaseCost + totalREPurchaseVal;
    const combinedReturnRate = totalCombinedCost > 0 ? ((totalExpectedProfit / totalCombinedCost) * 100) : 0;
    // Reuse the same property return rule already shown by the real-estate view.
    const realEstateReturnRate = totalREPurchaseVal > 0 ? (totalREProfit / totalREPurchaseVal) * 100 : 0;

    // Canonical session-gated price P/L and record-to-record valuation change
    // are separate metrics. The latter may contain trades, quantity changes,
    // and FX translation effects.
    const day = data.day_change || {};
    const dayProfit = day.day_profit_krw;
    const stockValue = s.total_stock_value_krw;
    const hasDayProfit = Number.isFinite(dayProfit);
    const rate = hasDayProfit && Number.isFinite(stockValue)
      && stockValue > 0 && day.price_profit_status === 'complete'
      ? dayProfit / stockValue * 100 : null;
    const krwStock = krw.stock_value_krw || (Number(krw.market_value_krw || 0) - Number(krw.cash || 0));
    const usdStock = usd.stock_value || (Number(usd.market_value || 0) - Number(usd.cash || 0));

    return {
      card: {
        s, totalStockVal, krwStockVal, krwStockProfit, krwStockReturnRate, krwHoldingCount,
        usdStockValKrw, usdStockValUsd, usdStockProfitKrw, usdStockReturnRate, usdHoldingCount,
        realizedView, totalRealizedKrw, yearRealizedKrw, monthRealizedKrw,
        totalActualDivKrw, yearActualDivKrw, monthActualDivKrw, currYear2Digit, currMonthStr,
        dailyPnl: {
          profit: hasDayProfit ? dayProfit : null,
          rate: Number.isFinite(rate) ? rate : null,
          partial: day.price_profit_status === 'partial',
          date: day.date,
        },
        krwCurrency: { currency: "KRW", marketValue: krw.market_value_krw || 0, stockValue: krwStock, cash: krw.cash || 0 },
        usdCurrency: { currency: "USD", marketValue: usd.market_value || 0, stockValue: usdStock, cash: usd.cash || 0 },
        updatedAt: data.updated_at,
      },
      home: {
        owner: o, netWorth, debt: totalAllDebt, cash: totalAllCash,
        invest: totalInvestAssets, expected: totalExpectedProfit, expectedRate: combinedReturnRate,
        propertyExpected: totalREProfit, propertyExpectedRate: realEstateReturnRate,
        propertyPurchaseValue: totalREPurchaseVal,
        stockExpected: Number(s.profit_krw) || 0, stockExpectedRate: Number(s.return_rate) || 0,
        realized: combinedRealizedKrw, safe: totalSafeAssets,
        stock: totalStockVal, property: totalREInvestEquity,
        deposits: totalTenantDepositVal, insurance: insuranceTotal,
        realizedTrade: totalRealizedKrw, dividendInterest: totalActualDivKrw,
        realizedYear: combinedYearRealizedKrw, realizedMonth: combinedMonthRealizedKrw,
        dayProfit: Number((data.day_change || {}).day_profit_krw || 0),
        dayRate: 0,
        recordChange: (data.day_change || {}).record_change_krw,
        recordChangeRate: (data.day_change || {}).record_change_rate,
        dayDate: (data.day_change || {}).date || null,
        classifications: data.classifications || [],
        updatedAt: data.updated_at || null,
        fxRates: data.fx_rates || {},
      },
    };
  }

  window.WealthDashboardOwnerModel = Object.freeze({
    selectOwnedAccounts, selectAccountsAndHoldings,
    computeFilteredSummary, classifyHolding, computeFilteredClassifications,
    computeFilteredSectors, computeFilteredCurrencySummary, computeFilteredDayChange,
    calculateDashboardDebt, finiteRealizedPnlNumber, summarizeRealizedPnlRows, buildRealizedPnlDisplaySummary,
    buildOwnerDashboard, buildDashboardSummary,
  });
})();
