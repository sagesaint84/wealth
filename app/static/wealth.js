

// Dates are current before any API request; initial HTML contains neutral labels.
function initializeSummaryPeriodLabels() {
  const {year, month} = getKstYearMonth();
  for (const prefix of ['pnl', 'div']) {
    const yearLabel = document.querySelector(`#${prefix}YearLabel`);
    const monthLabel = document.querySelector(`#${prefix}MonthLabel`);
    if (yearLabel) yearLabel.textContent = `${String(year).slice(2)}년`;
    if (monthLabel) monthLabel.textContent = `${String(month).padStart(2, '0')}월`;
  }
  for (const prefix of ['pnl', 'dividend']) {
    const text = document.querySelector(`#${prefix}CurrentMonthText`);
    const picker = document.querySelector(`#${prefix}MonthPicker`);
    const select = document.querySelector(`#${prefix}YearSelect`);
    if (text) text.textContent = `${year}년 ${month}월`;
    if (picker) picker.value = `${year}-${String(month).padStart(2, '0')}`;
    if (select?.options?.[0]) {
      select.options[0].value = String(year);
      select.options[0].textContent = `${year}년`;
      select.value = String(year);
    }
  }
}
initializeSummaryPeriodLabels();

const $ = (selector) => document.querySelector(selector);
let dashboard = null;
let rawDashboard = null; // 필터링 전 원본 서버 데이터
let currentOwner = '모두'; // 선택된 가족 구성원

// ── 가족 구성원 선택 – 모든 섹션(요약/기록/히트맵/배당/손익/보유종목/계좌) 전역 동기화 ───────
function selectOwner(owner) {
  if (currentOwner !== (owner || '모두') && typeof invalidateStartupReads === 'function') invalidateStartupReads();
  currentOwner = owner || '모두';
  syncHoldingSignalsContext();
  document.querySelectorAll('.family-tabs .family-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.owner === currentOwner);
  });
  if (rawDashboard) {
    renderWithOwner(rawDashboard, currentOwner);
  } else {
    loadAssetRecords(currentOwner);
    if (isLedgerViewActive()) loadLedger();
  }
  dividendData = null;
  if (currentDividendMode === 'estimated') loadDividends(currentOwner);
  loadActualDividends(currentOwner, selectedDividendYear);
  loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType);
  updateOverviewCardsAllTime(currentOwner);
}

// ── 핵심 요약 패널의 실현손익 및 실제 배당금 전체 기간(All-Time) 갱신 ─────────
async function updateOverviewCardsAllTime(owner = currentOwner) {
  if (globalThis.WealthStartup?.visible('summaryRealizedPnl') === false) { globalThis.WealthStartup.count('inactive_skipped'); return; }
  const generation = updateOverviewCardsAllTime.generation = (updateOverviewCardsAllTime.generation || 0) + 1;
  const [pnlResult, dividendResult] = await Promise.allSettled([
    api(`/api/realized-pnl?owner=${encodeURIComponent(owner)}&year=all&trade_type=all`),
    api(`/api/actual-dividends?owner=${encodeURIComponent(owner)}&year=all`),
  ]);
  if (generation !== updateOverviewCardsAllTime.generation || owner !== currentOwner
      || globalThis.WealthStartup?.visible('summaryRealizedPnl') === false) { globalThis.WealthStartup?.count('stale_ignored'); return; }
  let totalPnl = 0;
  try {
    if (pnlResult.status === 'rejected') throw pnlResult.reason;
    const pnlRes = pnlResult.value;
    if (pnlRes) {
      const pnlView = buildRealizedPnlDisplaySummary(pnlRes, [], true);
      totalPnl = pnlView.totalPnlKrw;
      const winRate = pnlView.winRate;
      const recordCount = pnlView.recordCount;

      const summaryPnlEl = $("#summaryRealizedPnl");
      if (summaryPnlEl) {
        summaryPnlEl.textContent = `${totalPnl > 0 ? '+' : ''}${money(totalPnl)}`;
        summaryPnlEl.className = `${totalPnl > 0 ? 'gain up' : (totalPnl < 0 ? 'loss down' : '')}`;
      }
      const subEl = $("#summaryRealizedPnlSub");
      if (subEl) {
        subEl.textContent = `승률 ${number(winRate, 1)}% · 총 ${recordCount}건 실현${pnlView.completenessNote ? ` · ${pnlView.completenessNote}` : ''}`;
      }
    }
  } catch (err) {
    console.error("핵심 요약 실현손익 갱신 실패:", err);
  }

  try {
    if (dividendResult.status === 'rejected') throw dividendResult.reason;
    const divRes = dividendResult.value;
    if (divRes) {
      const totalActual = Number(divRes.total_actual_dividend_krw || 0);
      const actualEl = $("#summaryActualDividend");
      if (actualEl) {
        actualEl.textContent = money(totalActual);
      }

    }
  } catch (err) {
    console.error("핵심 요약 실제 배당금 갱신 실패:", err);
  }
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

function computeFilteredClassifications(holdings, accounts, fxRates, owner = '모두', rawData = null) {
  const usdKrw = (fxRates || {})['USD'] || 1385;
  const groups = {};
  let totalValue = 0;
  const src = rawData || rawDashboard || {};

  const filterByOwner = (arr) => owner === '모두' ? (arr || []) : (arr || []).filter(x => (x.owner || '모두') === owner);

  // 1. 부동산 순에퀴티 (자가 & 임대 투자자산) 및 임차보증금 (안전자산)
  const allREs = src.real_estates || realEstateFeature.rawRealEstates || [];
  let totalREInvestEquity = 0;
  let totalTenantDepositVal = 0;
  let reInvestCount = 0;
  let reLeaseCount = 0;

  allREs.forEach(r => {
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
        return;
      }
    }

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

  const curBanks = filterByOwner(src.bank_accounts || accountFeature.rawBankAccounts || []);
  const bankCashTotal = curBanks.reduce((acc, b) => acc + Math.max(0, Number(b.balance) || 0), 0);

  const curSavings = filterByOwner(src.savings_accounts || accountFeature.rawSavingsAccounts || []);
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
  const curInsurances = filterByOwner(src.insurance_accounts || insuranceFeature.rawInsuranceAccounts || []);
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

function computeFilteredDayChange(holdings, rawDayChange, owner = '모두', currentTotalValue = 0) {
  const targetOwner = owner || '모두';
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const dayStr = String(now.getDate()).padStart(2, '0');
  const todayStr = `${year}-${month}-${dayStr}`;

  // 1. 자산기록(allAssetRecords)에서 오늘 이전(date < todayStr)의 해당 owner 직전 기록 찾기
  const ownerRecords = (allAssetRecords || []).filter(r => 
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

function renderWithOwner(data, owner) {
  let targetOwner = owner;
  let targetData = data;
  if (typeof data === 'string' && owner === undefined) {
    targetOwner = data;
    targetData = rawDashboard || dashboard;
  }
  const effectiveOwner = targetOwner || currentOwner || '모두';
  const src = rawDashboard || targetData || dashboard;
  if (!src) return;

  const filteredData = Object.assign({}, src);

  if (effectiveOwner !== '모두') {
    const owned = window.WealthDashboardOwnerModel.selectAccountsAndHoldings(src, effectiveOwner);
    filteredData.accounts = owned.accounts;
    filteredData.holdings = owned.holdings;

    filteredData.summary               = computeFilteredSummary(filteredData.accounts, filteredData.holdings, src.fx_rates);
    filteredData.classifications       = computeFilteredClassifications(filteredData.holdings, filteredData.accounts, src.fx_rates, effectiveOwner, src);
    filteredData.sector_classifications= computeFilteredSectors(filteredData.holdings, filteredData.accounts, src.fx_rates);
    filteredData.currency_summary      = computeFilteredCurrencySummary(filteredData.holdings, filteredData.accounts, src.fx_rates);
    filteredData.day_change            = src.daily_metrics_by_owner?.[effectiveOwner]
      || computeFilteredDayChange(filteredData.holdings, src.day_change, effectiveOwner, filteredData.summary?.total_stock_value_krw);
  } else {
    filteredData.accounts              = src.accounts               || [];
    filteredData.holdings              = src.holdings               || [];
    filteredData.summary               = src.summary                || {};
    filteredData.classifications       = computeFilteredClassifications(filteredData.holdings, filteredData.accounts, src.fx_rates, '모두', src);
    filteredData.sector_classifications= src.sector_classifications || [];
    filteredData.currency_summary      = src.currency_summary       || {};
    filteredData.day_change            = src.daily_metrics_by_owner?.['모두'] || src.day_change || {};
  }

  render(filteredData);
  loadAssetRecords(effectiveOwner);
  if (isLedgerViewActive()) loadLedger();
}

const appShell = window.WealthAppShellController.create({
  window, document, updateKoreanCurrencyHint, loadLedger: () => loadLedger(),
});
Object.assign(window, {
  closeDialog: appShell.closeDialog,
  initAppTheme: appShell.initAppTheme,
  initAppVersion: appShell.initAppVersion,
  setAppTheme: appShell.setAppTheme,
  switchMainModule: appShell.switchMainModule,
  triggerPwaInstall: appShell.triggerPwaInstall,
});
appShell.bindDialogCancel();

const splitDateInput = window.WealthSplitDateInputController.create({
  window, document, getDaysInMonth: window.WealthDateHelper.getDaysInMonth,
});
window.setupAutoAdvancingDateInput = splitDateInput.setupAutoAdvancingDateInput;

const number = (value, digits = 2) => Number(value || 0).toLocaleString("ko-KR", { maximumFractionDigits: digits });
const money = (value, currency = "KRW") =>
  window.WealthFormat.createCurrencyFormatter(currency, number)(value);

function formatKoreanMoneyFriendly(val) {
  if (val === null || val === undefined || val === '') return '';
  const num = Number(val);
  if (isNaN(num) || num === 0) return '';

  const isNegative = num < 0;
  const rawNum = Math.abs(Math.round(num));
  if (rawNum === 0) return '';

  if (rawNum < 10000) {
    return `${isNegative ? '-' : ''}${rawNum.toLocaleString()}원`;
  }

  const units = ['', '만', '억', '조', '경'];
  const parts = [];
  let unitIdx = 0;
  let absNum = rawNum;

  while (absNum > 0 && unitIdx < units.length) {
    const chunk = absNum % 10000;
    if (chunk > 0) {
      const unit = units[unitIdx];
      let chunkStr = '';
      if (chunk >= 1000 && chunk % 1000 === 0) {
        chunkStr = `${chunk / 1000}천`;
      } else if (chunk >= 100 && chunk % 100 === 0 && chunk < 1000) {
        chunkStr = `${chunk / 100}백`;
      } else {
        chunkStr = chunk.toLocaleString();
      }
      parts.unshift(`${chunkStr}${unit}`);
    }
    absNum = Math.floor(absNum / 10000);
    unitIdx++;
  }

  let result = parts.join(' ') + ' 원';

  // 1,000만 ~ 9,999만 또는 1억 ~ 9.9억일 때 상세 한글 독음 (예: "1,500만 원 (1천 5백만 원)")
  if (rawNum >= 10000000 && rawNum < 100000000) {
    const cheon = Math.floor(rawNum / 10000000);
    const baek = Math.floor((rawNum % 10000000) / 1000000);
    let spoken = `${cheon}천`;
    if (baek > 0) spoken += ` ${baek}백`;
    spoken += '만 원';
    if (!result.includes(spoken)) {
      result += ` (${spoken})`;
    }
  } else if (rawNum >= 100000000 && rawNum < 1000000000) {
    const eok = Math.floor(rawNum / 100000000);
    const cheon = Math.floor((rawNum % 100000000) / 10000000);
    const baek = Math.floor((rawNum % 10000000) / 1000000);
    let spoken = `${eok}억`;
    if (cheon > 0) spoken += ` ${cheon}천`;
    if (baek > 0) spoken += ` ${baek}백`;
    spoken += '만 원';
    if (!result.includes(spoken)) {
      result += ` (${spoken})`;
    }
  }

  return isNegative ? `-${result} (마이너스)` : result;
}

function updateKoreanCurrencyHint(input) {
  if (!input) return;
  let hintEl = input.parentElement?.querySelector('.korean-currency-hint');
  if (!hintEl) {
    hintEl = document.createElement('div');
    hintEl.className = 'korean-currency-hint';
    hintEl.style.cssText = 'font-size:11.5px;font-weight:700;color:#38bdf8;margin-top:3px;display:flex;align-items:center;gap:4px;line-height:1.3;transition:all 0.15s ease;';
    input.parentElement?.appendChild(hintEl);
  }

  const val = input.value;
  const formatted = formatKoreanMoneyFriendly(val);
  if (formatted) {
    const isMinus = Number(val) < 0;
    hintEl.style.display = 'flex';
    hintEl.style.color = isMinus ? '#fb7185' : '#38bdf8';
    hintEl.innerHTML = `<span style="font-size:11px;">💬</span> <span>${formatted}</span>`;
  } else {
    hintEl.style.display = 'none';
    hintEl.innerHTML = '';
  }
}

function refreshDialogKoreanHints(dialogEl) {
  if (!dialogEl) return;
  dialogEl.querySelectorAll('[data-korean-currency]').forEach(inp => updateKoreanCurrencyHint(inp));
}

appShell.bindMoneyHints();

const html = window.WealthFormat.escapeHtml;
const escapeHtml = html;
const brokerUI = window.WealthBrokerUI.create({ document, html });
window.escapeHtml = html;
const signClass = (value) => Number(value) < 0 ? "down" : "up";

appShell.bindDialogControls();

function sparkline(points, change) { return marketView.sparkline(points, change); }

const apiClient = globalThis.WealthApiClient.create({
  getStartup: () => globalThis.WealthStartup,
  invalidateLedgerRead: () => ledgerFeature.invalidateRead(),
});
Object.assign(globalThis, {
  api: apiClient.api,
  apiRequest: apiClient.apiRequest,
  invalidateStartupReads: apiClient.invalidateStartupReads,
  finishStartupIncomeReads: apiClient.finishStartupIncomeReads,
});

// Classic-script consumers read the current epoch and inspect pending reads.
Object.defineProperties(globalThis, {
  startupReadEpoch: { configurable: true, get: apiClient.getReadEpoch },
  startupIncomeReuse: { configurable: true, get: apiClient.isStartupIncomeReuseEnabled },
  startupReadPending: { configurable: true, value: apiClient.pendingReads },
});

globalThis.WealthStartup = globalThis.WealthStartupReadController.create({
  getUserProfile: () => typeof currentUserProfile === 'undefined' ? null : currentUserProfile,
  get startupReadEpoch() { return apiClient.getReadEpoch(); },
  get currentOwner() { return currentOwner; },
  get selectedDividendYear() { return selectedDividendYear; },
  get selectedPnlYear() { return selectedPnlYear; },
  get currentPnlTradeType() { return currentPnlTradeType; },
  get currentDividendMode() { return currentDividendMode; },
  get ledgerFeature() { return ledgerFeature; },
  isDividendEntryPending: () => typeof setIncomeTab === 'function' && setIncomeTab.pendingTarget === 'dividend',
  loadMarkets: () => loadMarkets(),
  loadAssetRecords: owner => loadAssetRecords(owner),
  loadLedger: () => loadLedger(),
  loadDividends: (owner, options) => loadDividends(owner, options),
  loadActualDividends: (owner, year, prepared) => loadActualDividends(owner, year, prepared),
  loadRealizedPnl: (owner, year, tradeType) => loadRealizedPnl(owner, year, tradeType),
  updateOverviewCardsAllTime: owner => updateOverviewCardsAllTime(owner),
});

const fetchJson = api;
window.fetchJson = api;

const operationFeedback = window.WealthOperationFeedback.create({ $ });
function toast(message, isError = false) { return operationFeedback.toast(message, isError); }
function busy(button, enabled) { return operationFeedback.busy(button, enabled); }
async function action(button, request, after = loadDashboard) {
  return operationFeedback.action(button, request, after);
}

// ── 기간별 자산기록 필터링 ──────────────────────────────────────────────────
function filterRecordsByPeriod(records, period) { return window.WealthStockRecordsModel.filterRecordsByPeriod(records, period); }

function buildPreviousRecordMap(records) { return window.WealthStockRecordsModel.buildPreviousRecordMap(records); }

// ── 1. 주요 지수 렌더링 ──────────────────────────────────────────────────────
// ── 1. 주요 지수 렌더링 ──────────────────────────────────────────────────────
const investmentFeature = window.WealthInvestmentFeatureController.create({
  get $() { return $; },
  get action() { return action; },
  get api() { return api; },
  get attachStockAutoFill() { return attachStockAutoFill; },
  get calcAccountCumulativeTaxSaved() { return calcAccountCumulativeTaxSaved; },
  get calculateOwnerYearPensionTaxBenefits() { return calculateOwnerYearPensionTaxBenefits; },
  get classifyHolding() { return classifyHolding; },
  get currentOwner() { return currentOwner; },
  get currentUserProfile() { return currentUserProfile; },
  get currentWealthView() { return currentWealthView; },
  get dashboard() { return dashboard; },
  get getTaxCategory() { return getTaxCategory; },
  get html() { return html; },
  get isAccountTaxDeductible() { return isAccountTaxDeductible; },
  get isTaxAdvantagedAccount() { return isTaxAdvantagedAccount; },
  get loadDashboard() { return loadDashboard; },
  get marketView() { return marketView; },
  get money() { return money; },
  get number() { return number; },
  get populateStockDatalists() { return populateStockDatalists; },
  get rawDashboard() { return rawDashboard; },
  get renderMarkets() { return renderMarkets; },
  get signClass() { return signClass; },
  get toast() { return toast; },
});
Object.assign(window, investmentFeature.publicActions);
// Older planning and chart scripts use these live values from the feature owner.
Object.defineProperties(window, Object.getOwnPropertyDescriptors(investmentFeature.legacyState)); // '3Y' | '5Y' | '10Y' | 'MAX'

// Display preferences are local to this browser and authenticated account.
// Unknown/new cards are visible by default; an empty selection is intentional.
const marketPreferences = window.WealthMarketCardPreferences.create({ getCurrentUserProfile: () => currentUserProfile, renderMarkets, document, window });
const marketCardKey = marketPreferences.marketCardKey;
const marketView = window.WealthMarketView.create({
  $, html, number, document, getCurrentMarketPeriod: () => currentMarketPeriod,
  getCurrentMarketAllSub: () => currentMarketAllSub, marketCardKey, hiddenMarketCards, marketCardSettings,
});
function marketPreferenceKey() { return marketPreferences.marketPreferenceKey(); }
function hiddenMarketCards() { return marketPreferences.hiddenMarketCards(); }
function marketCardSettings(items) { return marketPreferences.marketCardSettings(items); }

function renderMarketFearGreed(item) { return marketView.renderMarketFearGreed(item); }

function renderMarkets(result) { return marketView.renderMarkets(result); }

// ── 대시보드 전역 기간 탭 연동 (주요지수 ↔ 자산기록 ↔ 자산히트맵) ──────────────


// 주요지수 기간 선택 탭 이벤트 등록
investmentFeature.actions.bindMarketPeriod();

async function loadMarkets() {
  if (globalThis.WealthStartup?.visible('marketGrid') === false) { globalThis.WealthStartup.count('inactive_skipped'); return; }
  const generation = loadMarkets.generation = (loadMarkets.generation || 0) + 1;
  try {
    const data = await api('/api/market-overview');
    if (generation !== loadMarkets.generation || globalThis.WealthStartup?.visible('marketGrid') === false) { globalThis.WealthStartup?.count('stale_ignored'); return; }
    renderMarkets(data);
  }
  catch (error) {
    if (generation !== loadMarkets.generation || globalThis.WealthStartup?.visible('marketGrid') === false) return;
    const grid = $("#marketGrid");
    if (grid) grid.innerHTML = `<article class="market-card"><p>시장 스냅샷을 불러오지 못했습니다.</p><small>${html(error.message)}</small></article>`;
  }
}

// ── 2. 핵심 요약 렌더링 ──────────────────────────────────────────────────────
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

const investmentSummaryView = window.WealthInvestmentSummaryView.create({ $, money, number });

function renderSummary(data) {
  const s = data.summary || {}, currencies = data.currency_summary || {};
  const krw = currencies.KRW || {}, usd = currencies.USD || {};
  const o = currentOwner || '모두';
  const filterByOwner = (arr) => o === '모두' ? (arr || []) : (arr || []).filter(x => (x.owner || '모두') === o);

  // 1. 총 부채 및 자산 계산
  const curLoans = filterByOwner(data.loan_accounts || accountFeature.rawLoanAccounts || []);
  const curBanks = filterByOwner(data.bank_accounts || accountFeature.rawBankAccounts || []);
  const curSavings = filterByOwner(data.savings_accounts || accountFeature.rawSavingsAccounts || []);
  const curInsurances = filterByOwner(data.insurance_accounts || insuranceFeature.rawInsuranceAccounts || []);
  const allREs = data.real_estates || realEstateFeature.rawRealEstates || [];

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
    const ownerships = (r.ownerships && r.ownerships.length) 
      ? r.ownerships 
      : [{ owner: r.owner || '모두', ratio: 100 }];

    let share = 1.0;
    if (o !== '모두') {
      let matched = ownerships.find(x => x.owner === o);
      if (!matched && r.owner && r.owner.includes(o)) {
        const m = r.owner.match(new RegExp(`${o}\\s*([0-9.]+)%`));
        if (m) {
          share = parseFloat(m[1]) / 100;
        } else {
          share = 0.5;
        }
      } else if (matched && matched.ratio > 0) {
        share = (matched.ratio || 100) / 100;
      } else {
        return;
      }
    }

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
  const curRealized = data.realized_pnl_summary || rawDashboard?.realized_pnl_summary || {};
  const rawPnlList = data.realized_pnl_records || rawDashboard?.realized_pnl_records || pnlData?.records || [];
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
  let totalRealizedKrw = realizedView.totalPnlKrw;
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

  const summaryPnlSubEl = $("#summaryRealizedPnlSub");
  if (summaryPnlSubEl) {
    summaryPnlSubEl.textContent = `승률 ${number(realizedView.winRate, 1)}% · 총 ${realizedView.recordCount}건 실현${realizedView.completenessNote ? ` · ${realizedView.completenessNote}` : ''}`;
  }

  // 5. 총 배당금 및 이자 (연도별/월별 실시간 집계)
  const curDiv = data.dividend_summary || rawDashboard?.dividend_summary || {};
  const divRecords = filterByOwner(data.actual_dividend_records || rawDashboard?.actual_dividend_records || actualDividendData?.records || []);

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
  const allHoldings = data.holdings || rawDashboard?.holdings || [];
  const ownedAcctIds = new Set((data.accounts || []).map(a => a.id));
  const curHoldings = o === '모두' 
    ? allHoldings 
    : allHoldings.filter(h => (h.owner && h.owner === o) || ownedAcctIds.has(h.account_id) || (h.owner || '모두') === o);

  const usdKrwRate = (data.fx_rates || rawDashboard?.fx_rates || {})['USD'] || 1385;
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

  // Existing asset-mode totals are projected to the page-local HOME renderer below.
  const totalExpectedProfit = (Number(s.profit_krw) || 0) + totalREProfit;
  const stockPurchaseCost = Math.max(0, totalStockVal - (Number(s.profit_krw) || 0));
  const totalCombinedCost = stockPurchaseCost + totalREPurchaseVal;
  const combinedReturnRate = totalCombinedCost > 0 ? ((totalExpectedProfit / totalCombinedCost) * 100) : 0;
  // Reuse the same property return rule already shown by the real-estate view.
  const realEstateReturnRate = totalREPurchaseVal > 0 ? (totalREProfit / totalREPurchaseVal) * 100 : 0;

  // The investment summary has one stock-only renderer.
  // 2. 총 주식자산
  if ($("#totalInvestRow")) $("#totalInvestRow").style.display = "flex";
  if ($("#totalInvestLabelText")) $("#totalInvestLabelText").textContent = "총 주식자산";
  if ($("#totalValue")) $("#totalValue").textContent = money(totalStockVal);

  // 2-1. 원화 주식 카드 표시
  if ($("#krwStockRow")) $("#krwStockRow").style.display = "flex";
  if ($("#summaryKrwStockVal")) $("#summaryKrwStockVal").textContent = money(krwStockVal);
  if ($("#summaryKrwStockProfit")) {
    const kSign = krwStockProfit >= 0 ? "+" : "";
    const krSign = krwStockReturnRate >= 0 ? "+" : "";
    $("#summaryKrwStockProfit").textContent = `${kSign}${money(krwStockProfit)} (${krSign}${number(krwStockReturnRate, 2)}%)`;
    $("#summaryKrwStockProfit").style.color = krwStockProfit >= 0 ? "#f43f5e" : "#38bdf8";
  }
  if ($("#summaryKrwStockCount")) {
    $("#summaryKrwStockCount").textContent = `${krwHoldingCount}개 종목`;
  }

  // 2-2. 달러 주식 카드 표시
  if ($("#usdStockRow")) $("#usdStockRow").style.display = "flex";
  if ($("#summaryUsdStockValKrw")) $("#summaryUsdStockValKrw").textContent = money(usdStockValKrw);
  if ($("#summaryUsdStockValUsd")) {
    $("#summaryUsdStockValUsd").textContent = `$${number(usdStockValUsd, 2)} (${usdHoldingCount}개 종목)`;
  }
  if ($("#summaryUsdStockProfit")) {
    const uSign = usdStockProfitKrw >= 0 ? "+" : "";
    const urSign = usdStockReturnRate >= 0 ? "+" : "";
    $("#summaryUsdStockProfit").textContent = `${uSign}${money(usdStockProfitKrw)} (${urSign}${number(usdStockReturnRate, 2)}%)`;
    $("#summaryUsdStockProfit").style.color = usdStockProfitKrw >= 0 ? "#f43f5e" : "#38bdf8";
  }

  // 3. 주식 기대수익 (주식 평가손익) & 일간 수익
  if ($("#expectedProfitRow")) $("#expectedProfitRow").style.display = "flex";
  if ($("#profitLabelText")) $("#profitLabelText").textContent = "주식 기대수익";
  if ($("#totalProfit")) {
    $("#totalProfit").textContent = money(s.profit_krw);
  }
  const profitRateEl = $("#profitRate");
  if (profitRateEl) {
    profitRateEl.textContent = `(${s.return_rate >= 0 ? "+" : ""}${number(s.return_rate)}%)`;
  }
  // Share the existing stock-profit tone, including its zero/missing fallback.
  const totalProfitNonnegative = (s.profit_krw || 0) >= 0;
  const totalProfitColor = totalProfitNonnegative ? "#f43f5e" : "#38bdf8";
  for (const node of [$("#expectedProfitRow .wealth-profit-label"), $("#totalProfit"), profitRateEl]) {
    if (!node) continue;
    node.style.color = totalProfitColor;
    // Existing semantic rules also exclude this amount from White's neutral strong override.
    node.classList.toggle("up", totalProfitNonnegative);
    node.classList.toggle("down", !totalProfitNonnegative);
  }

  // 4. 주식 실현손익
  if ($("#realizedPnlRow")) $("#realizedPnlRow").style.display = "flex";
  if ($("#pnlLabelText")) $("#pnlLabelText").textContent = "주식 실현손익";
  if ($("#summaryRealizedPnl")) {
    $("#summaryRealizedPnl").textContent = `${totalRealizedKrw >= 0 ? "+" : ""}${money(totalRealizedKrw)}`;
    $("#summaryRealizedPnl").className = totalRealizedKrw > 0 ? 'gain up' : (totalRealizedKrw < 0 ? 'loss down' : '');
    $("#summaryRealizedPnl").style.color = totalRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
  }
  if ($("#pnlYearLabel")) $("#pnlYearLabel").textContent = `${currYear2Digit}년`;
  if ($("#summaryRealizedPnlYear")) {
    $("#summaryRealizedPnlYear").textContent = `${yearRealizedKrw >= 0 ? '+' : ''}${money(yearRealizedKrw)}`;
    $("#summaryRealizedPnlYear").className = yearRealizedKrw > 0 ? 'gain up' : (yearRealizedKrw < 0 ? 'loss down' : '');
    $("#summaryRealizedPnlYear").style.color = yearRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
  }
  if ($("#pnlMonthLabel")) $("#pnlMonthLabel").textContent = `${currMonthStr}월`;
  if ($("#summaryRealizedPnlMonth")) {
    $("#summaryRealizedPnlMonth").textContent = `${monthRealizedKrw >= 0 ? '+' : ''}${money(monthRealizedKrw)}`;
    $("#summaryRealizedPnlMonth").className = monthRealizedKrw > 0 ? 'gain up' : (monthRealizedKrw < 0 ? 'loss down' : '');
    $("#summaryRealizedPnlMonth").style.color = monthRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
  }

  // 5. 배당금 (주식 탭에서 별도 표시)
  if ($("#dividendRow")) $("#dividendRow").style.display = "flex";
  if ($("#divLabelText")) $("#divLabelText").textContent = "배당금";
  if ($("#summaryActualDividend")) {
    $("#summaryActualDividend").textContent = money(totalActualDivKrw);
  }
  if ($("#divYearLabel")) $("#divYearLabel").textContent = `${currYear2Digit}년`;
  if ($("#summaryActualDivYear")) {
    $("#summaryActualDivYear").textContent = `${yearActualDivKrw >= 0 ? '+' : ''}${money(yearActualDivKrw)}`;
  }
  if ($("#divMonthLabel")) $("#divMonthLabel").textContent = `${currMonthStr}월`;
  if ($("#summaryActualDivMonth")) {
    $("#summaryActualDivMonth").textContent = `${monthActualDivKrw >= 0 ? '+' : ''}${money(monthActualDivKrw)}`;
  }

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
  investmentSummaryView.renderDailyPnl({
    profit: hasDayProfit ? dayProfit : null,
    rate: Number.isFinite(rate) ? rate : null,
    partial: day.price_profit_status === 'partial',
    date: day.date,
  });

  const krwStock = krw.stock_value_krw || (Number(krw.market_value_krw || 0) - Number(krw.cash || 0));
  investmentSummaryView.renderCurrency({ currency: "KRW", marketValue: krw.market_value_krw || 0, stockValue: krwStock, cash: krw.cash || 0 });

  const usdStock = usd.stock_value || (Number(usd.market_value || 0) - Number(usd.cash || 0));
  investmentSummaryView.renderCurrency({ currency: "USD", marketValue: usd.market_value || 0, stockValue: usdStock, cash: usd.cash || 0 });

  $("#updatedAt") && ($("#updatedAt").textContent = data.updated_at ? `마지막 자산 반영 ${new Date(data.updated_at).toLocaleString("ko-KR")}` : "아직 보유종목이 없습니다.");
  $("#accountCaption") && ($("#accountCaption").textContent = `전체 ${number(s.account_count, 0)}개 계좌`);
  // Presentation-only projection of the existing totals; no second calculation policy.
  window.dispatchEvent(new CustomEvent('wealth:summary', { detail: {
    owner: o, netWorth, debt: totalAllDebt, cash: totalAllCash,
    invest: totalInvestAssets, expected: totalExpectedProfit, expectedRate: combinedReturnRate,
    propertyExpected: totalREProfit, propertyExpectedRate: realEstateReturnRate,
    propertyPurchaseValue: totalREPurchaseVal,
    stockExpected: Number(s.profit_krw) || 0, stockExpectedRate: Number(s.return_rate) || 0,
    realized: combinedRealizedKrw, safe: totalSafeAssets,
    stock: totalStockVal, property: totalREInvestEquity,
    deposits: totalTenantDepositVal, insurance: insuranceTotal,
    insuranceReturn: window.WealthInsuranceReturnDisplay?.(data.insurance_accounts || insuranceFeature.rawInsuranceAccounts || [], o),
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
  }}));
}

// ── 3. 투자자산 분류 & 섹터별 도넛 원그래프 ──────────────────────────────────


function maskBrokerAccountNo(value) {
  const normalized = String(value || "").replace(/[\s-]+/g, "");
  return normalized ? `계좌 ****${normalized.slice(-4)}` : "";
}

investmentFeature.actions.bindSectorColors();

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

// ── 4. 계좌 목록 렌더링 ──────────────────────────────────────────────────────
const accountYearlyView = window.WealthAccountYearlyView.create({ html, number });

const accountFeature = window.WealthAccountFeatureController.create({
  $,
  accountYearlyView,
  action,
  api,
  busy,
  calculateOwnerYearPensionTaxBenefits,
  closeDialog,
  get currentOwner() { return currentOwner; },
  get dashboard() { return dashboard; },
  html,
  isAccountTaxDeductible,
  loadDashboard,
  maskBrokerAccountNo,
  normalizeYear,
  number,
  get rawDashboard() { return rawDashboard; },
  refreshDialogKoreanHints,
  renderWithOwner,
  signClass,
  toast,
});
const {
  renderAccounts,
  renderSavings,
  openBankAccountDialog,
  openSavingAccountDialog,
  openLoanAccountDialog,
  openIntegratedBankDialog,
} = accountFeature.publicActions;
Object.assign(window, accountFeature.publicActions);

// ── 4-2. 통합 계좌 카테고리 탭 (증권 / 은행 / 보험) ─────────────────────────
const insuranceFeature = window.WealthInsurancePensionFeatureController.create({
  $,
  accountYearlyView,
  api,
  calculateOwnerYearPensionTaxBenefits,
  closeDialog,
  get currentAccountCategory() { return currentAccountCategory; },
  get currentOwner() { return currentOwner; },
  get dashboard() { return dashboard; },
  getTaxCategory,
  html,
  isAccountTaxDeductible,
  isContributionTaxDeductible,
  isTaxAdvantagedAccount,
  loadDashboard,
  number,
  get rawDashboard() { return rawDashboard; },
  refreshDialogKoreanHints,
  toast,
});
const {
  renderAssetTaxInformation,
  renderInsurance,
  openInsuranceAccountDialog,
} = insuranceFeature.publicActions;
Object.assign(window, insuranceFeature.publicActions);
let currentAccountCategory = window.WealthAssetCategoryState?.current() || 'securities';

// 머니 로그는 캘린더, 실현손익, 배당·이자, 가계부, 공모주 패널을 공유하며 화면만 전환합니다.
let currentIncomeTab = 'calendar';
function setIncomeTab(tab, { updateHash = true, loadContent = true } = {}) {
  const preparedDividend = arguments[1]?.preparedDividend || null;
  const selection = setIncomeTab.pendingIncomeTabSelection = (setIncomeTab.pendingIncomeTabSelection || 0) + 1;
  setIncomeTab.cancelPending?.();
  setIncomeTab.cancelPending = null;
  const tabs = document.getElementById('incomeTabs');
  const ui = window.WealthIncomeTabsController;
  const clearPending = () => ui.clearPending(document, tabs);
  clearPending();
  setIncomeTab.pendingTarget = null;
  // Hash restoration runs before the later currentDividendMode declaration.
  if (tab === 'dividend' && (document.querySelector?.('#dividendModeTabs .heatmap-tab.active')?.dataset?.divMode || 'actual') === 'actual' && !preparedDividend) {
    // Route selection is synchronous; only the first chart frame is deferred.
    // layout.navigate() may have run before this function was registered.
    currentIncomeTab = 'dividend';
    ui.applySelection(document, currentIncomeTab, false);
    if (updateHash) history.replaceState(null, '', '#dividend');
    setIncomeTab.pendingTarget = 'dividend';
    let cancelled = false, releaseWait = null;
    setIncomeTab.cancelPending = () => { cancelled = true; releaseWait?.(); clearPending(); };
    const current = () => !cancelled && selection === setIncomeTab.pendingIncomeTabSelection
      && (!document.querySelector('.wealth-workspace') || document.querySelector('.wealth-workspace').dataset.activeView === 'income');
    const waitReady = (event, ready) => ready() ? Promise.resolve() : new Promise(resolve => {
      const finish = () => { window.removeEventListener(event, finish); releaseWait = null; resolve(); };
      releaseWait = finish;
      window.addEventListener(event, finish, {once:true});
    });
    ui.showPendingStatus(document, tabs);
    // Keep the existing controls usable while the first chart frame is prepared.
    if (currentIncomeTab !== 'dividend' || !document.querySelector('#dividendBarChartWrap .wealth-unified-chart-shell')) {
      ui.showPendingControls(document);
    }
    return (async () => {
      try {
        await waitReady('wealth:assets-ready', () => !globalThis.WealthStartup || globalThis.WealthStartup.canRead());
        if (!current()) return false;
        await waitReady('wealth:unified-ready', () => !!window.WealthUnifiedTimeseries?.prepareDividend);
        if (!current()) return false;
        const scope = window.WealthUnifiedTimeseries.dividendScopeKey();
        const prepared = await window.WealthUnifiedTimeseries.prepareDividend({refresh:true});
        if (!current()) return false;
        if (scope !== window.WealthUnifiedTimeseries.dividendScopeKey()) return setIncomeTab(tab, {updateHash, loadContent});
        if (prepared.readEpoch !== apiClient.getReadEpoch())
          return setIncomeTab(tab, {updateHash, loadContent});
        setIncomeTab.cancelPending = null;
        return setIncomeTab(tab, {updateHash, loadContent, preparedDividend:prepared});
      } finally {
        if (selection === setIncomeTab.pendingIncomeTabSelection) {
          clearPending(); setIncomeTab.pendingTarget = null; setIncomeTab.cancelPending = null;
        }
      }
    })();
  }

  const isKnownTab = ['calendar', 'pnl', 'dividend', 'ledger', 'ipo'].includes(tab);
  const _legacyCheck = ['pnl', 'dividend', 'ledger'].includes(tab);
  currentIncomeTab = isKnownTab ? tab : 'calendar';
  ui.applySelection(document, currentIncomeTab, true);
  if (preparedDividend && !window.WealthUnifiedTimeseries.commitDividend(preparedDividend)) {
    document.getElementById('dividendPanel')?.classList.add('wealth-income-hidden');
    return false;
  }
  if (currentIncomeTab === 'pnl' || currentIncomeTab === 'dividend') {
    window.WealthUnifiedTimeseries?.refreshVisiblePanZoom?.(
      currentIncomeTab === 'pnl' ? 'pnlBarChartWrap' : 'dividendBarChartWrap'
    );
  }
  if (updateHash) {
    const hash = currentIncomeTab === 'calendar' ? '#income' : `#${currentIncomeTab}`;
    history.replaceState(null, '', hash);
  }
  if ((loadContent || preparedDividend) && !currentUserProfile?.must_change_password) {
    globalThis.dispatchEvent?.(new CustomEvent('wealth:income-view'));
    void globalThis.WealthStartup?.loadVisible(preparedDividend);
    if (currentIncomeTab === 'calendar') window.loadCalendar?.();
    if (currentIncomeTab === 'ledger' && currentUserProfile && currentUserProfile.username !== 'admin') loadLedger();
    if (currentIncomeTab === 'ipo') window.loadIpoSchedule?.();
  }
}
window.setIncomeTab = setIncomeTab;

document.getElementById('incomeTabs')?.addEventListener('click', event => {
  const tab = event.target.closest('.income-tab');
  if (tab) void setIncomeTab(tab.dataset.income);
});
setIncomeTab(document.querySelector('.wealth-workspace')?.dataset.incomeTab || ({ pnl: 'pnl', dividend: 'dividend', ledger: 'ledger', ipo: 'ipo' }[location.hash.slice(1)] || 'calendar'), { updateHash: false, loadContent: false });

function switchAccountCategory(category) {
  category = window.WealthAssetCategoryState?.select(category) || category;
  currentAccountCategory = category;
  window.WealthAccountReorder?.setCategory(category);
  window.WealthIncomeTabsController.applyTabSelection(document.querySelectorAll('.account-cat-tab'), 'cat', category);

  const secPanel = document.getElementById('catPanelSecurities');
  const bnkPanel = document.getElementById('catPanelBanking');
  const insPanel = document.getElementById('catPanelInsurance');
  const rePanel = document.getElementById('catPanelRealEstate');
  const taxPanel = document.getElementById('catPanelTax');

  if (secPanel) secPanel.style.display = category === 'securities' ? 'block' : 'none';
  if (bnkPanel) bnkPanel.style.display = category === 'banking' ? 'block' : 'none';
  if (insPanel) insPanel.style.display = category === 'insurance' ? 'block' : 'none';
  if (rePanel) rePanel.style.display = category === 'real_estate' ? 'block' : 'none';
  if (taxPanel) taxPanel.style.display = category === 'tax' ? 'block' : 'none';
  if (category === 'tax') renderAssetTaxInformation();

  const secActs = document.getElementById('securitiesActions');
  const bnkActs = document.getElementById('bankingActions');
  const insActs = document.getElementById('insuranceActions');
  const reActs = document.getElementById('realEstateActions');

  if (secActs) secActs.style.display = category === 'securities' ? 'flex' : 'none';
  if (bnkActs) bnkActs.style.display = category === 'banking' ? 'flex' : 'none';
  if (insActs) insActs.style.display = category === 'insurance' ? 'flex' : 'none';
  if (reActs) reActs.style.display = category === 'real_estate' ? 'flex' : 'none';
}

switchAccountCategory(currentAccountCategory);

// Check URL query parameters for callback result notifications
(() => {
  if (typeof URLSearchParams === 'undefined' || typeof window === 'undefined' || !window.location || !window.location.search) {
    return;
  }
  const params = new URLSearchParams(window.location.search);
  if (params.get('kftc_connected') === '1') {
    window.addEventListener('DOMContentLoaded', () => {
      toast('🎉 금융결제원 오픈뱅킹 연결이 성공적으로 완료되었습니다!');
      if (typeof history !== 'undefined' && history.replaceState) {
        history.replaceState(null, '', window.location.pathname);
      }
    });
  } else if (params.get('kftc_error')) {
    const errCode = params.get('kftc_error');
    window.addEventListener('DOMContentLoaded', () => {
      toast(`오픈뱅킹 인증에 실패했습니다 (${errCode}).`, true);
      if (typeof history !== 'undefined' && history.replaceState) {
        history.replaceState(null, '', window.location.pathname);
      }
    });
  }
})();

insuranceFeature.actions.bindPensionHistory();

// ── 4-3. 부동산 (자가 / 임대 / 임차 / 매도) 자산 관리 ──────────────────────────────
const incomeFeature = window.WealthIncomeFeatureController.create({
  get $() { return $; },
  get action() { return action; },
  get api() { return api; },
  get attachStockAutoFill() { return attachStockAutoFill; },
  get buildRealizedPnlDisplaySummary() { return buildRealizedPnlDisplaySummary; },
  get currentOwner() { return currentOwner; },
  get dashboard() { return dashboard; },
  get finiteRealizedPnlNumber() { return finiteRealizedPnlNumber; },
  get html() { return html; },
  get loadDashboard() { return loadDashboard; },
  get loadMarkets() { return loadMarkets; },
  get money() { return money; },
  get number() { return number; },
  get populateStockDatalists() { return populateStockDatalists; },
  get rawDashboard() { return rawDashboard; },
  get realEstateFeature() { return realEstateFeature; },
  get renderRealEstate() { return renderRealEstate; },
  get renderRealEstateWithOwner() { return renderRealEstateWithOwner; },
  get setIncomeTab() { return setIncomeTab; },
  get setupAutoAdvancingDateInput() { return setupAutoAdvancingDateInput; },
  get startupReadEpoch() { return apiClient.getReadEpoch(); },
  get toast() { return toast; },
  get updateKoreanCurrencyHint() { return updateKoreanCurrencyHint; },
  get updateOverviewCardsAllTime() { return updateOverviewCardsAllTime; },
});
// Later scripts replace selected public loaders and renderers to apply source and broker filters.
Object.assign(window, incomeFeature.publicActions);
// Existing classic-script consumers still share these live values.
Object.defineProperties(window, Object.getOwnPropertyDescriptors(incomeFeature.legacyState));

const realEstateFeature = window.WealthRealEstateFeatureController.create({
  $,
  api,
  closeDialog,
  get currentOwner() { return currentOwner; },
  html,
  loadDashboard,
  loadRealizedPnl,
  loanTypeLabels: accountFeature.loanTypeLabels,
  number,
  get pnlData() { return pnlData; },
  get rawDashboard() { return rawDashboard; },
  get rawLoanAccounts() { return accountFeature.rawLoanAccounts; },
  refreshDialogKoreanHints,
  toast,
  updateKoreanCurrencyHint,
});
const {
  renderRealEstate,
  renderRealEstateWithOwner,
  openRealEstateDialog,
} = realEstateFeature.publicActions;
Object.assign(window, realEstateFeature.publicActions);

investmentFeature.actions.bindHoldingSignals();

// ── 8-1. 절세계좌 보유종목 및 계좌별 자산 렌더링 ──────────────────────────────
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

// Shared totals/raw asset state remain eager; only stock-page DOM work is lazy.
function currentWealthView() {
  return document.querySelector('.wealth-workspace')?.dataset.activeView || 'invest';
}
function isLedgerViewActive() {
  return appShell.getCurrentModule() === 'ledger' ||
    (currentWealthView() === 'income' && currentIncomeTab === 'ledger');
}


// ── 9. 대시보드 렌더링 총괄 ──────────────────────────────────────────────────
function render(data) {
  globalThis.WealthStartup?.count('render');
  dashboard = data;
  renderSummary(data);
  renderAccounts(data.accounts);
  renderSavings(data.savings_accounts || [], data.bank_accounts || [], data.loan_accounts || [], currentOwner);
  renderInsurance(data.insurance_accounts || [], currentOwner);
  renderRealEstate(data.real_estates || [], currentOwner, data.sold_real_estates);
  renderInvestmentView(data);
  window.dispatchEvent(new CustomEvent('wealth:portfolio', { detail: {
    accounts: data.accounts || [], holdings: data.holdings || [],
    owner: currentOwner, fxRates: data.fx_rates || {},
  }}));
}

async function loadDashboard(recordSnapshots = false) {
  const generation = loadDashboard.generation = (loadDashboard.generation || 0) + 1;
  const suffix = recordSnapshots ? "?record_snapshots=true" : "";
  const data = await api(`/api/dashboard${suffix}`);
  if (generation !== loadDashboard.generation) { globalThis.WealthStartup?.count('stale_ignored'); return; }
  rawDashboard = data;
  dashboard = data;
  renderWithOwner(data, currentOwner);
  globalThis.WealthStartup?.dashboardRendered(data);
}

function normalizeYear(val) {
  if (!val) return "";
  const digits = String(val).replace(/\D/g, "");
  if (!digits) return "";
  const num = parseInt(digits, 10);
  if (num >= 2000 && num <= 2099) return String(num);
  if (num >= 0 && num <= 99) return String(2000 + num);
  if (num >= 1970 && num < 2000) return String(num);
  return String(num);
}
window.normalizeYear = normalizeYear;

// ── 14. 가족 구성원 관리 함수들 ──────────────────────────────────────────────
const familyFeature = window.WealthFamilyFeatureController.create({
  api,
  get currentOwner() { return currentOwner; },
  loadDashboard,
  toast,
});
const {
  openFamilyManager,
  loadFamilyMembers,
} = familyFeature.publicActions;
Object.assign(window, familyFeature.publicActions);

window.WealthGlobalActionController.bind({
  document, appShell, selectOwner, switchAccountCategory, openFamilyManager,
  accountActions: accountFeature.actions,
  familyActions: familyFeature.actions,
  incomeActions: incomeFeature.actions,
  insuranceActions: insuranceFeature.actions,
  investmentActions: investmentFeature.actions,
  realEstateActions: realEstateFeature.actions,
  confirm: (message) => window.confirm(message),
  openIntegratedBankDialog, openBankAccountDialog, openSavingAccountDialog, openLoanAccountDialog,
  openInsuranceAccountDialog, openRealEstateDialog,
});

// ── 이벤트 리스너 바인딩 ─────────────────────────────────────────────────────

// 1. 상단 계좌 연결 & 갱신 버튼
$("#syncAccountsButton")?.addEventListener("click", (e) => action(e.currentTarget, async () => {
  window.dispatchEvent(new CustomEvent('wealth:sync', {detail: {state: 'running'}}));
  try {
    const result = await api("/api/sync/all", { method: "POST" });
    await loadDashboard();
    const hasPartial = result.brokers?.some(item => ['PARTIAL_SUCCESS', 'API_ERROR', 'PARSE_ERROR', 'INTERNAL_ERROR'].includes(item.status));
    window.dispatchEvent(new CustomEvent('wealth:sync', {detail: {
      state: hasPartial || result.errors?.length ? 'partial' : result.synced > 0 ? 'success' : 'empty',
      message: result.message,
      brokers: result.brokers || [],
    }}));
    return result;
  } catch (error) {
    window.dispatchEvent(new CustomEvent('wealth:sync', {detail: {state: 'error'}}));
    throw error;
  }
}, async () => { await loadMarkets(); }));
$("#refreshButton")?.addEventListener("click", (e) => action(e.currentTarget, () => api("/api/refresh-prices", { method: "POST" }), async () => { await loadDashboard(); await loadMarkets(); }));
$("#refreshMarketButton")?.addEventListener("click", (e) => action(e.currentTarget, () => api("/api/refresh-prices", { method: "POST" }), async () => { await loadDashboard(); await loadMarkets(); }));
$("#demoButton")?.addEventListener("click", (e) => action(e.currentTarget, () => api("/api/demo", { method: "POST" })));
investmentFeature.actions.bindInvestmentControls();
$("#clearButton")?.addEventListener("click", () => {
  if (confirm("저장된 보유내역을 모두 지울까요?")) {
    action($("#clearButton"), () => api("/api/clear", { method: "POST" }));
  }
});

investmentFeature.actions.bindHoldingsList();

// 9. 계좌 목록 클릭
accountFeature.actions.bindAccountList();

// 10. 자산기록 리스트 수정/삭제 및 절세계좌 필터 클릭
investmentFeature.actions.bindRecordsAndAccountFields();

// 실현손익 추가/수정 팝업 내 등록된 계좌 선택 시 자동 채움
incomeFeature.actions.bindAccountSelects();

// 11. 폼 서브밋 핸들러들
investmentFeature.actions.bindHoldingForms();

document.getElementById("accountImportBtn")?.addEventListener("click", () => {
  document.getElementById("accountImportDialog")?.showModal();
});
$("#accountImportForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  const file = $("#accountImportFile")?.files[0];
  if (!file) return;
  const formData = new FormData(); formData.append("file", file);
  try {
    const result = await api("/api/import-accounts", { method: "POST", body: formData });
    form.closest("dialog")?.close(); form.reset();
    toast(`증권계좌 ${result.created || 0}개를 추가했습니다.${result.duplicates ? ` 중복 ${result.duplicates}건은 건너뛰었습니다.` : ""}`);
    await loadDashboard();
  } catch (error) { toast(error.message, true); }
});

investmentFeature.actions.bindAssetRecordForm();

$("#accountCashForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  const accountId = form.dataset.accountId;
  const cashKrw = Number(form.cash_krw.value || 0);
  const cashUsd = Number(form.cash_usd.value || 0);
  try {
    const res = await api(`/api/accounts/${accountId}/cash`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cash_krw: cashKrw, cash_usd: cashUsd })
    });
    form.closest("dialog")?.close();
    toast(res.message);
    await loadDashboard();
  } catch (err) {
    toast(err.message, true);
  }
});

accountFeature.actions.bindSaveButtons();

// ── 종목 사전 및 양방향 자동완성 (종목코드 ↔ 종목명) ─────────────────────────
const stockAutocomplete = window.WealthStockAutocomplete.create({
  api, html, document, getDashboard: () => dashboard,
  getActualDividendData: () => actualDividendData, getPnlData: () => pnlData,
});
function populateStockDatalists() { return stockAutocomplete.populateStockDatalists(); }
function attachStockAutoFill(formId, updateFieldsFn) { return stockAutocomplete.attachStockAutoFill(formId, updateFieldsFn); }


// 실제 배당금 파일 가져오기 폼 이벤트
incomeFeature.actions.bindDividendImport();

// 12. 데이터 백업 / 복원
document.getElementById('exportButton')?.addEventListener('click', async () => {
  try {
    const response = await fetch('/api/export', { credentials: 'include' });
    if (!response.ok) throw new Error('백업 데이터를 다운로드하지 못했습니다.');
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `wealth_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast('백업 파일을 다운로드했습니다.');
  } catch (err) {
    toast(err.message, true);
  }
});

document.getElementById('importBackupBtn')?.addEventListener('click', () => {
  document.getElementById('importBackupFile')?.click();
});

document.getElementById('importBackupFile')?.addEventListener('change', async (e) => {
  const file = e.target.files?.[0];
  if (!file) return;
  if (!confirm(`'${file.name}' 파일로 데이터를 복원할까요?\n현재 데이터는 덮어쓰입니다.`)) {
    e.target.value = '';
    return;
  }
  const btn = document.getElementById('importBackupBtn');
  btn && (btn.disabled = true);
  try {
    const formData = new FormData();
    formData.append('file', file);
    const result = await api('/api/import-backup', { method: 'POST', body: formData });
    toast(result.message || '데이터를 복원했습니다.');
    await loadDashboard();
    await loadAssetRecords(currentOwner);
    if (typeof loadLedger === 'function') {
      await loadLedger();
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    e.target.value = '';
    btn && (btn.disabled = false);
  }
});

appShell.bindPwa();

incomeFeature.actions.bindEstimatedTooltip();
incomeFeature.actions.bindRecordForms();

// ── 화면 테마 관리 (Theme Switcher) ────────────────────────────────────────
// 창 크기 변경 시 활성화된 히트맵 재계산

investmentFeature.actions.bindHeatmapResize();

const userAccessFeature = window.WealthUserAccessFeatureController.create({
  window, document, api, html, toast, loadFamilyMembers, loadDashboard, finishStartupIncomeReads,
});
Object.defineProperty(window, 'currentUserProfile', {
  configurable: true,
  get: userAccessFeature.getCurrentUserProfile,
});
Object.assign(window, userAccessFeature.actions);

const userCredentialsFeature = window.WealthUserCredentialsFeatureController.create({ window, document, api, toast });
Object.assign(window, userCredentialsFeature.actions);

function initSavingsListeners() {
  accountFeature.actions.bindBankForms();
  insuranceFeature.actions.bindForm(accountFeature.actions.bindSecuritiesYearlyForm);
  accountFeature.actions.bindSecuritiesTaxPreview();
  accountFeature.actions.bindLoanForm();
  realEstateFeature.actions.bindForm();
}

// ===========================================================================
// 📒 SMART FAMILY HOUSEHOLD LEDGER (스마트 가족 가계부 모듈)
// ===========================================================================
const ledgerFeature = window.WealthLedgerFeatureController.create({
  window, document, $, html, number, api, toast, busy, loadDashboard,
  setupAutoAdvancingDateInput, getKstYearMonth, shiftYearMonth, parseYearMonth,
  getOwner: () => currentOwner,
  getUsername: () => currentUserProfile?.username || '',
  getReadEpoch: apiClient.getReadEpoch,
  invalidateStartupReads,
  getAccounts: () => ({ rawDashboard, dashboard, rawBankAccounts: accountFeature.rawBankAccounts, rawSavingsAccounts: accountFeature.rawSavingsAccounts }),
});
window.WealthLedgerFeature = ledgerFeature;
Object.assign(window, ledgerFeature.actions);

// The existing chart extensions still read these classic-script bindings.
Object.defineProperties(window, {
  currentLedgerYear: { configurable: true, get: ledgerFeature.getYear },
  currentLedgerMonth: { configurable: true, get: ledgerFeature.getMonth },
  rawLedgerData: { configurable: true, get: ledgerFeature.getData, set: ledgerFeature.setData },
});
const { loadLedger } = ledgerFeature;

const brokerImports = window.WealthBrokerImportFeatureController.create({
  window, document, brokerUI, html, number, money,
  getDashboard: () => dashboard,
  loadDashboard, updateOverviewCardsAllTime, invalidateStartupReads,
  loadRealizedPnl: incomeFeature.publicActions.loadRealizedPnl,
  loadActualDividends: incomeFeature.publicActions.loadActualDividends,
  getOwner: () => currentOwner,
  getDividendYear: () => incomeFeature.legacyState.selectedDividendYear,
  getDividendMode: () => incomeFeature.legacyState.currentDividendMode,
});
Object.assign(window, brokerImports.actions);

async function bootstrap() {
  return appShell.bootstrap({
    brokerImports,
    initializeSession: () => initAuthSession(),
    initializeFeatures() {
      initSavingsListeners();
      ledgerFeature.initListeners();
      initPnlMonthNavListeners();
      initDividendMonthNavListeners();
      setupAutoAdvancingDateInput("#pnlSplitDateWrap");
      setupAutoAdvancingDateInput("#divSplitDateWrap");
      setupAutoAdvancingDateInput("#ledgerTxSplitDateWrap");
      setupAutoAdvancingDateInput("#ledgerPaySplitDateWrap");
    },
  });
}

appShell.bindLifecycle({
  bootstrap,
  getDashboard: () => rawDashboard,
  getUserProfile: () => currentUserProfile,
  getIncomeTab: () => currentIncomeTab,
  cancelPendingIncome: () => setIncomeTab.cancelPending?.(),
  renderInvestmentView,
});
