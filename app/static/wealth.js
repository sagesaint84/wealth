let allAssetRecords = [];
let assetRecords = [];
let currentRecordPeriod = 'ALL'; // '1M' | '3M' | '6M' | '1Y' | 'ALL'
let currentRecordView = 'combo'; // 'combo' | 'tax_accounts'
let currentTaxAccountFilter = 'all'; // 'all' | 'isa' | 'irp' | 'pension_savings' | acc_<id>
let currentAllocTab = 'asset_class'; // 'asset_class' | 'sector'
let currentStockChartCode = '';
let currentStockChartName = '';
let currentStockChartPrice = 0;
let currentStockChartCurrency = 'KRW';
let currentStockChartPeriod = '1M'; // '1D' | '1W' | '1M' | '1Y'
let holdingSortField = 'market_value_krw';
let holdingSortOrder = 'desc'; // 'asc' | 'desc'
let taxHoldingSortField = 'market_value_krw';
let taxHoldingSortOrder = 'desc'; // 'asc' | 'desc'
let currentPnlSortField = 'date';
let currentPnlSortOrder = 'desc'; // 'asc' | 'desc'
let currentDivSortField = 'date';
let currentDivSortOrder = 'desc'; // 'asc' | 'desc'
let heatmapViewMode = localStorage.getItem("heatmap_view_mode") || "treemap"; // 'treemap' | 'cards'
let heatmapPeriod = localStorage.getItem("heatmap_period") || "1D";
let heatmapTheme = localStorage.getItem("heatmap_theme") || "kr";
let heatmapMaxCap = localStorage.getItem("heatmap_max_cap") || "auto";

const $ = (selector) => document.querySelector(selector);
let dashboard = null;
let rawDashboard = null; // 필터링 전 원본 서버 데이터
let currentOwner = '모두'; // 선택된 가족 구성원

// ── 가족 구성원 선택 – 모든 섹션(요약/기록/히트맵/배당/손익/보유종목/계좌) 전역 동기화 ───────
function selectOwner(owner) {
  currentOwner = owner || '모두';
  document.querySelectorAll('.family-tabs .family-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.owner === currentOwner);
  });
  if (rawDashboard) renderWithOwner(rawDashboard, currentOwner);
  loadAssetRecords(currentOwner);
  loadDividends(currentOwner);
  loadActualDividends(currentOwner, selectedDividendYear);
  loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType);
  updateOverviewCardsAllTime(currentOwner);
  loadLedger();
}

// ── 핵심 요약 패널의 실현손익 및 실제 배당금 전체 기간(All-Time) 갱신 ─────────
async function updateOverviewCardsAllTime(owner = currentOwner) {
  let totalPnl = 0;
  try {
    const pnlRes = await api(`/api/realized-pnl?owner=${encodeURIComponent(owner)}&year=all&trade_type=all`);
    if (pnlRes) {
      totalPnl = Number(pnlRes.total_pnl_krw || 0);
      const winRate = Number(pnlRes.win_rate || 0);
      const recordCount = Number(pnlRes.record_count || 0);

      const isStockTab = (currentAllocTab === 'sector');
      if (isStockTab) {
        const summaryPnlEl = $("#summaryRealizedPnl");
        if (summaryPnlEl) {
          summaryPnlEl.textContent = `${totalPnl > 0 ? '+' : ''}${money(totalPnl)}`;
          summaryPnlEl.className = `${totalPnl > 0 ? 'gain up' : (totalPnl < 0 ? 'loss down' : '')}`;
        }
        const subEl = $("#summaryRealizedPnlSub");
        if (subEl) {
          subEl.textContent = `승률 ${number(winRate, 1)}% · 총 ${recordCount}건 실현`;
        }
      }
    }
  } catch (err) {
    console.error("핵심 요약 실현손익 갱신 실패:", err);
  }

  try {
    const divRes = await api(`/api/actual-dividends?owner=${encodeURIComponent(owner)}&year=all`);
    if (divRes) {
      const totalActual = Number(divRes.total_actual_dividend_krw || 0);
      const actualEl = $("#summaryActualDividend");
      if (actualEl) {
        actualEl.textContent = money(totalActual);
      }
      const isStockTab = (currentAllocTab === 'sector');
      if (!isStockTab) {
        const combined = totalPnl + totalActual;
        const summaryPnlEl = $("#summaryRealizedPnl");
        if (summaryPnlEl) {
          summaryPnlEl.textContent = `${combined >= 0 ? '+' : ''}${money(combined)}`;
          summaryPnlEl.className = `${combined > 0 ? 'gain up' : (combined < 0 ? 'loss down' : '')}`;
        }
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

const ASSET_CLASS_ORDER = {
  '부동산': 1,
  '국내주식': 2,
  '국내ETF': 3,
  '국내상장해외ETF': 4,
  '해외ETF': 5,
  '해외주식': 6,
  '현금·예수금': 7,
  '보험': 8,
};

function computeFilteredClassifications(holdings, accounts, fxRates, owner = '모두', rawData = null) {
  const usdKrw = (fxRates || {})['USD'] || 1385;
  const groups = {};
  let totalValue = 0;
  const src = rawData || rawDashboard || {};

  const filterByOwner = (arr) => owner === '모두' ? (arr || []) : (arr || []).filter(x => (x.owner || '모두') === owner);

  // 1. 부동산 순에퀴티 (자가 & 임대 투자자산) 및 임차보증금 (안전자산)
  const allREs = src.real_estates || rawRealEstates || [];
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

  const curBanks = filterByOwner(src.bank_accounts || rawBankAccounts || []);
  const bankCashTotal = curBanks.reduce((acc, b) => acc + Math.max(0, Number(b.balance) || 0), 0);

  const curSavings = filterByOwner(src.savings_accounts || rawSavingsAccounts || []);
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
  const curInsurances = filterByOwner(src.insurance_accounts || rawInsuranceAccounts || []);
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
      change_rate,
      change_krw,
      date: prevDate,
      value_krw: prevVal,
    };
  }

  // 2. 만약 해당 소유자의 이전 스냅샷이 없다면 보유종목 등락률 가중평균으로 fallback
  if (!rawDayChange) return {};
  let totalStockVal = 0, weightedChange = 0;
  holdings.forEach(h => {
    const val = Number(h.market_value_krw || 0);
    const rate = Number(h.day_change_rate || 0);
    totalStockVal += val;
    weightedChange += val * rate;
  });
  if (totalStockVal === 0) {
    return {
      change_rate: 0,
      change_krw: 0,
      date: (rawDayChange || {}).date || "전일",
    };
  }
  const change_rate = weightedChange / totalStockVal;
  const change_krw  = totalStockVal * change_rate / (100 + change_rate) || 0;
  return {
    change_rate,
    change_krw,
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
    filteredData.accounts = (src.accounts || []).filter(a => (a.owner || '모두') === effectiveOwner);
    const ownedIds = new Set(filteredData.accounts.map(a => a.id));
    filteredData.holdings = (src.holdings || []).filter(h => ownedIds.has(h.account_id) || (h.owner && h.owner === effectiveOwner));

    filteredData.summary               = computeFilteredSummary(filteredData.accounts, filteredData.holdings, src.fx_rates);
    filteredData.classifications       = computeFilteredClassifications(filteredData.holdings, filteredData.accounts, src.fx_rates, effectiveOwner, src);
    filteredData.sector_classifications= computeFilteredSectors(filteredData.holdings, filteredData.accounts, src.fx_rates);
    filteredData.currency_summary      = computeFilteredCurrencySummary(filteredData.holdings, filteredData.accounts, src.fx_rates);
    filteredData.day_change            = computeFilteredDayChange(filteredData.holdings, src.day_change, effectiveOwner, filteredData.summary?.total_value_krw);
  } else {
    filteredData.accounts              = src.accounts               || [];
    filteredData.holdings              = src.holdings               || [];
    filteredData.summary               = src.summary                || {};
    filteredData.classifications       = computeFilteredClassifications(filteredData.holdings, filteredData.accounts, src.fx_rates, '모두', src);
    filteredData.sector_classifications= src.sector_classifications || [];
    filteredData.currency_summary      = src.currency_summary       || {};
    filteredData.day_change            = computeFilteredDayChange(filteredData.holdings, src.day_change, '모두', filteredData.summary?.total_value_krw);
  }

  render(filteredData);
  loadAssetRecords(effectiveOwner);
  loadLedger();
}

// 다이얼로그 닫기 버튼 공통 처리
document.addEventListener("click", (event) => {
  const button = event.target.closest(".dialog .close, .dialog .dialog-actions button[value='cancel']");
  if (!button) return;
  event.preventDefault();
  button.closest("dialog")?.close();
});

const number = (value, digits = 2) => Number(value || 0).toLocaleString("ko-KR", { maximumFractionDigits: digits });
const money = (value, currency = "KRW") => {
  try { return new Intl.NumberFormat("ko-KR", { style: "currency", currency, maximumFractionDigits: currency === "KRW" ? 0 : 2 }).format(Number(value || 0)); }
  catch { return number(value); }
};

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

document.addEventListener('input', (e) => {
  if (e.target && e.target.hasAttribute('data-korean-currency')) {
    updateKoreanCurrencyHint(e.target);
  }
});

const html = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
const escapeHtml = html;
window.escapeHtml = html;
const signClass = (value) => Number(value) < 0 ? "down" : "up";

function closeDialog(idOrEl) {
  try {
    const el = typeof idOrEl === 'string' ? document.getElementById(idOrEl) : idOrEl;
    if (!el) return;
    if (typeof el.close === 'function') {
      el.close();
    } else {
      el.removeAttribute('open');
      el.style.display = 'none';
    }
  } catch (err) {
    console.error('[DIALOG] closeDialog error:', err);
  }
}
window.closeDialog = closeDialog;

// 다이얼로그 닫기 버튼 위임 (※ 팝업 외 배경 클릭 시에는 닫히지 않도록 보호)
document.addEventListener('click', (e) => {
  // 닫기 버튼 클릭 처리 (.close, [data-close-dialog], .dialog-close-btn, [aria-label="닫기"] 등)
  const closeBtn = e.target.closest('[data-close-dialog], .close, .dialog-close-btn, [aria-label="닫기"]');
  if (closeBtn) {
    const targetId = closeBtn.getAttribute('data-close-dialog');
    if (targetId) {
      closeDialog(targetId);
      return;
    }
    const dialog = closeBtn.closest('dialog');
    if (dialog && dialog.id !== 'forcePasswordModal') {
      closeDialog(dialog);
      return;
    }
  }
});

// 다이얼로그 내부 입력창에서 Enter 키 누를 때 화면이 닫히지 않고 [저장] 버튼 자동 실행
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Enter') return;
  if (e.isComposing) return; // 한글 조합 중 엔터는 무시

  // textarea 내에서의 줄바꿈은 허용
  if (e.target && e.target.tagName === 'TEXTAREA') return;

  const dialog = e.target?.closest?.('dialog');
  if (!dialog || !dialog.open) return;

  // input, select 등 다이얼로그 폼 입력 요소에서 Enter를 친 경우
  if (e.target && ['INPUT', 'SELECT'].includes(e.target.tagName)) {
    e.preventDefault(); // 기본 submit 또는 dialog 자동 닫기 방지

    // 해당 다이얼로그 안의 [저장] 버튼 우선 탐색 후 클릭
    const saveBtn = dialog.querySelector('#accountAddSaveBtn, button[type="submit"]:not([value="cancel"]), button.primary:not([value="cancel"])');
    if (saveBtn) {
      saveBtn.click();
    } else {
      const form = dialog.querySelector('form');
      if (form) {
        if (typeof form.requestSubmit === 'function') form.requestSubmit();
        else form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
      }
    }
  }
});


function sparkline(points, change) {
  if (!points || points.length < 2) {
    if (points && points.length === 1) points = [points[0], points[0]];
    else return "<span class=\"spark-empty\">—</span>";
  }
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || (min * 0.01) || 1;
  const h = 42;
  const w = 110;
  const pad = 4;

  const coords = points.map((point, index) => {
    const x = (index / (points.length - 1)) * (w - pad * 2) + pad;
    const y = (h - pad) - ((point - min) / span) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  const polylineStr = coords.join(" ");
  const lastCoord = coords[coords.length - 1].split(",");
  const lastX = lastCoord[0];
  const lastY = lastCoord[1];

  const isUp = Number(change) > 0;
  const isDown = Number(change) < 0;
  const color = isUp ? "#ff5c77" : (isDown ? "#4f9dff" : "#98a6c8");

  return `
    <svg class="sparkline" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="${polylineStr}" fill="none" stroke="${color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" />
      <circle cx="${lastX}" cy="${lastY}" r="3" fill="${color}" />
    </svg>
  `;
}

async function api(url, options = {}) {
  options.credentials = options.credentials || 'include';
  const response = await fetch(url, options);
  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('로그인이 필요합니다.');
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || result.message || "요청을 처리하지 못했습니다.");
  return result;
}

const fetchJson = api;
window.fetchJson = api;

let toastTimer;
function toast(message, isError = false) {
  const element = $("#toast");
  if (!element) return;
  element.textContent = message;
  element.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.className = "toast"; }, 3600);
}

function busy(button, enabled) {
  if (!button) return;
  button.dataset.label ??= button.textContent;
  button.disabled = enabled;
  button.textContent = enabled ? "처리 중…" : button.dataset.label;
}

async function action(button, request, after = loadDashboard) {
  busy(button, true);
  try {
    const result = await request();
    toast(result.message || "반영했습니다.");
    if (after) await after();
  } catch (error) {
    toast(error.message, true);
  } finally {
    busy(button, false);
  }
}

// ── 기간별 자산기록 필터링 ──────────────────────────────────────────────────
function filterRecordsByPeriod(records, period) {
  if (!records || !records.length || period === 'ALL') return records || [];
  const sorted = [...records].sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')));

  if (period === '1D') {
    // 일간: 전날과 당일 2일만 비교
    return sorted.slice(-2);
  }
  if (period === '1W') {
    // 주간: 5일간 비교
    return sorted.slice(-5);
  }
  if (period === '1M') {
    // 월간: 1달간 비교 (최근 30일)
    const now = new Date();
    const cutoff = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const mList = sorted.filter(r => r.date && r.date >= cutoff);
    return mList.length >= 2 ? mList : sorted.slice(-30);
  }
  if (period === '1Y') {
    // 연간: 1년간 비교 (최근 365일)
    const now = new Date();
    const cutoff = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
    const yList = sorted.filter(r => r.date && r.date >= cutoff);
    return yList.length >= 2 ? yList : sorted.slice(-365);
  }
  return sorted;
}

// ── 1. 주요 지수 렌더링 ──────────────────────────────────────────────────────
// ── 1. 주요 지수 렌더링 ──────────────────────────────────────────────────────
let currentMarketPeriod = '1D';
let currentMarketAllSub = '3Y'; // '3Y' | '5Y' | '10Y' | 'MAX'
let marketOverviewData = null;

function renderMarkets(result) {
  if (result) marketOverviewData = result;
  if (!marketOverviewData) return;

  const mkts = marketOverviewData.markets || [];
  const fx = marketOverviewData.exchange_rate || {};
  let period = currentMarketPeriod || '1D';
  if (period === 'ALL') {
    period = currentMarketAllSub || '3Y';
  }

  const allCards = [
    ...mkts.map(m => {
      const pStat = (m.periods && (m.periods[period] || m.periods['ALL'])) || {};
      const change = pStat.change != null ? pStat.change : (m.change != null ? m.change : m.change_price);
      const changeRate = pStat.change_rate != null ? pStat.change_rate : m.change_rate;
      const series = (pStat.series && pStat.series.length) ? pStat.series : (m.series || [m.price || 0]);
      let lbl = m.label || m.name;
      if (lbl === "S&P 500") lbl = "S&P";
      if (lbl === "달러 환율") lbl = "달러";
      return {
        symbol: m.symbol,
        label: lbl,
        price: m.price != null ? m.price : m.current_price,
        currency: m.currency || 'KRW',
        change: change,
        change_rate: changeRate,
        series: series,
      };
    }),
    (() => {
      const fxPStat = (fx.periods && (fx.periods[period] || fx.periods['ALL'])) || {};
      const fxChange = fxPStat.change != null ? fxPStat.change : (fx.change != null ? fx.change : fx.change_price);
      const fxChangeRate = fxPStat.change_rate != null ? fxPStat.change_rate : fx.change_rate;
      const fxSeries = (fxPStat.series && fxPStat.series.length) ? fxPStat.series : (fx.series || [fx.rate || 1385]);
      return {
        symbol: "USD/KRW",
        label: "달러",
        price: fx.rate,
        currency: "KRW",
        change: fxChange,
        change_rate: fxChangeRate,
        series: fxSeries,
      };
    })()
  ];

  // 순서: 코스피 -> 코스닥 -> 달러 -> S&P -> 나스닥 -> 반도체
  const ORDER = ["코스피", "코스닥", "달러", "S&P", "나스닥", "반도체"];
  const rows = ORDER.map(name => allCards.find(c => c.label === name)).filter(Boolean);
  allCards.forEach(c => {
    if (!rows.includes(c)) rows.push(c);
  });

  const grid = $("#marketGrid");
  if (!grid) return;

  grid.innerHTML = rows.map((item) => {
    const isFx = item.symbol === "USD/KRW";
    const priceText = isFx ? `${number(item.price, 1)}원` : number(item.price, 2);

    const isUp = Number(item.change_rate) > 0;
    const isDown = Number(item.change_rate) < 0;
    const sign = isUp ? "+" : "";
    const colorClass = isUp ? "up" : (isDown ? "down" : "");

    let changePointText = "";
    let changeRateText = "";
    if (item.change_rate != null) {
      changePointText = item.change != null ? `${sign}${number(item.change, 2)}` : "—";
      changeRateText = `${sign}${number(item.change_rate, 2)}%`;
    } else {
      changePointText = "—";
      changeRateText = "—";
    }

    const chartHtml = sparkline(item.series, item.change_rate);

    return `
      <article class="market-card toss-market-card">
        <div class="market-chart-col">
          ${chartHtml}
        </div>
        <div class="market-info-col">
          <strong class="market-title">${html(item.label)}</strong>
          <strong class="market-price ${colorClass}">${priceText}</strong>
          <span class="market-change-point ${colorClass}">${changePointText}</span>
          <span class="market-change-rate ${colorClass}">${changeRateText}</span>
        </div>
      </article>
    `;
  }).join("");
}

// ── 대시보드 전역 기간 탭 연동 (주요지수 ↔ 자산기록 ↔ 자산히트맵) ──────────────
function setDashboardPeriod(period, subOption = null) {
  if (!period) return;
  const p = period.toUpperCase();

  let mktPeriod = p;      // 주요지수: 1D, 1W, 1M, 1Y, ALL
  let recPeriod = p;      // 자산기록: 1D, 1W, 1M, 1Y, ALL
  let hmPeriod = p;       // 자산히트맵: 1D, 1W, 1M, 1Y, TOTAL

  if (p === 'TOTAL') {
    mktPeriod = 'ALL';
    recPeriod = 'ALL';
    hmPeriod = 'TOTAL';
  } else if (p === 'ALL' || ['3Y', '5Y', '10Y', 'MAX'].includes(p)) {
    mktPeriod = 'ALL';
    recPeriod = 'ALL';
    hmPeriod = 'TOTAL';
    if (['3Y', '5Y', '10Y', 'MAX'].includes(p)) {
      currentMarketAllSub = p;
    }
  }

  if (subOption && ['3Y', '5Y', '10Y', 'MAX'].includes(subOption.toUpperCase())) {
    currentMarketAllSub = subOption.toUpperCase();
  }

  // 1. 주요지수 탭 동기화
  currentMarketPeriod = mktPeriod;
  document.querySelectorAll("#marketPeriodTabs .heatmap-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.period === mktPeriod);
  });
  const selectEl = document.getElementById("marketPeriodSelect");
  if (selectEl && selectEl.value !== currentMarketAllSub) {
    selectEl.value = currentMarketAllSub;
  }
  if (marketOverviewData) {
    renderMarkets(marketOverviewData);
  }

  // 2. 자산기록 탭 동기화
  currentRecordPeriod = recPeriod;
  document.querySelectorAll("#recordPeriodTabs .heatmap-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.period === recPeriod);
  });
  if (window.assetRecords || assetRecords) {
    renderAssetRecords(window.assetRecords || assetRecords);
  }

  // 3. 자산히트맵 탭 동기화
  heatmapPeriod = hmPeriod;
  localStorage.setItem("heatmap_period", heatmapPeriod);
  document.querySelectorAll("#heatmapPeriodTabs .heatmap-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.period === hmPeriod);
  });
  if (dashboard) {
    renderHeatmaps(dashboard);
  }
}

// 주요지수 기간 선택 탭 이벤트 등록
document.addEventListener("click", (e) => {
  const btn = e.target.closest("#marketPeriodTabs .heatmap-tab");
  if (!btn) return;
  const period = btn.dataset.period;
  if (!period) return;
  setDashboardPeriod(period);
});

// 주요지수 전체 서브선택 드롭다운 이벤트 등록
document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "marketPeriodSelect") {
    setDashboardPeriod("ALL", e.target.value);
  }
});

async function loadMarkets() {
  try { renderMarkets(await api("/api/market-overview")); }
  catch (error) {
    const grid = $("#marketGrid");
    if (grid) grid.innerHTML = `<article class="market-card"><p>시장 스냅샷을 불러오지 못했습니다.</p><small>${html(error.message)}</small></article>`;
  }
}

// ── 2. 핵심 요약 렌더링 ──────────────────────────────────────────────────────
function renderSummary(data) {
  const s = data.summary || {}, currencies = data.currency_summary || {};
  const krw = currencies.KRW || {}, usd = currencies.USD || {};
  const o = currentOwner || '모두';
  const filterByOwner = (arr) => o === '모두' ? (arr || []) : (arr || []).filter(x => (x.owner || '모두') === o);

  // 1. 총 부채 및 자산 계산
  const curLoans = filterByOwner(data.loan_accounts || rawLoanAccounts || []);
  const curBanks = filterByOwner(data.bank_accounts || rawBankAccounts || []);
  const curSavings = filterByOwner(data.savings_accounts || rawSavingsAccounts || []);
  const curInsurances = filterByOwner(data.insurance_accounts || rawInsuranceAccounts || []);
  const allREs = data.real_estates || rawRealEstates || [];

  const posBanks = curBanks.filter(b => (Number(b.balance) || 0) >= 0);
  const negBanks = curBanks.filter(b => (Number(b.balance) || 0) < 0);

  const totalInvestVal = Number(s.total_value_krw || 0);
  const totalStockVal = s.total_stock_value_krw || (totalInvestVal - Number(s.total_cash_krw || 0));
  const totalPositiveBankVal = posBanks.reduce((acc, b) => acc + (Number(b.balance) || 0), 0);
  const totalSavingVal = curSavings.reduce((acc, sv) => acc + (Number(sv.current_value) || Number(sv.current_paid_amount) || Number(sv.balance) || 0), 0);
  const totalAllCash = Number(s.total_cash_krw || 0) + totalPositiveBankVal + totalSavingVal;
  const insuranceTotal = curInsurances.reduce((acc, ins) => acc + (Number(ins.expected_amount) || Number(ins.converted_total_asset) || Number(ins.total_paid_amount) || Number(ins.expected_refund_amount) || Number(ins.accumulated_paid_amount) || 0), 0);

  const totalMinusBankDebt = negBanks.reduce((acc, b) => acc + Math.abs(Number(b.balance) || 0), 0);
  const totalPureDebt = curLoans.reduce((acc, l) => acc + (Number(l.current_balance) || 0), 0);

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

  const now = new Date();
  const currFullYear = now.getFullYear().toString();
  const currYear2Digit = currFullYear.slice(2);
  const currMonthNum = now.getMonth() + 1;
  const currMonthStr = currMonthNum < 10 ? `0${currMonthNum}` : `${currMonthNum}`;
  const currYearMonthPrefix = `${currFullYear}-${currMonthStr}`;

  let totalRealizedKrw = Number(curRealized.total_realized_profit_krw || curRealized.total_pnl_krw || 0);
  let yearRealizedKrw = 0;
  let monthRealizedKrw = 0;

  if (pnlRecords.length > 0) {
    pnlRecords.forEach(r => {
      const d = String(r.date || '');
      const p = Number(r.pnl_krw || 0);
      if (d.startsWith(currFullYear)) yearRealizedKrw += p;
      if (d.startsWith(currYearMonthPrefix)) monthRealizedKrw += p;
    });
    totalRealizedKrw = pnlRecords.reduce((sum, r) => sum + Number(r.pnl_krw || 0), 0);
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

  const isStockTab = (currentAllocTab === 'sector');

  // =========================================================================
  // [자산] 탭 vs [주식] 탭 조건부 좌측 요약 렌더링
  // =========================================================================
  if (isStockTab) {
    // -----------------------------------------------------------------------
    // MODE B: [주식] 탭 선택 시 (주식 전용 뷰)
    // -----------------------------------------------------------------------
    // 1. 순자산 행 숨김
    if ($("#netWorthRow")) $("#netWorthRow").style.display = "none";

    // 2. 총 주식자산
    if ($("#totalInvestRow")) $("#totalInvestRow").style.display = "flex";
    if ($("#totalInvestLabelText")) $("#totalInvestLabelText").textContent = "총 주식자산";
    if ($("#totalValue")) $("#totalValue").textContent = money(totalStockVal);
    if ($("#subAssetBreakdown")) $("#subAssetBreakdown").style.display = "none";

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
      $("#totalProfit").style.color = (s.profit_krw || 0) >= 0 ? "#f43f5e" : "#38bdf8";
    }
    const profitRateEl = $("#profitRate");
    if (profitRateEl) {
      profitRateEl.textContent = `(${s.return_rate >= 0 ? "+" : ""}${number(s.return_rate)}%)`;
      profitRateEl.style.color = (s.profit_krw || 0) >= 0 ? "#f43f5e" : "#38bdf8";
    }

    // 4. 주식 실현손익
    if ($("#realizedPnlRow")) $("#realizedPnlRow").style.display = "flex";
    if ($("#pnlLabelText")) $("#pnlLabelText").textContent = "주식 실현손익";
    if ($("#summaryRealizedPnl")) {
      $("#summaryRealizedPnl").textContent = `${totalRealizedKrw >= 0 ? "+" : ""}${money(totalRealizedKrw)}`;
      $("#summaryRealizedPnl").style.color = totalRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
    }
    if ($("#pnlSubBreakdown")) $("#pnlSubBreakdown").style.display = "none";
    if ($("#pnlYearLabel")) $("#pnlYearLabel").textContent = `${currYear2Digit}년`;
    if ($("#summaryRealizedPnlYear")) {
      $("#summaryRealizedPnlYear").textContent = `${yearRealizedKrw >= 0 ? '+' : ''}${money(yearRealizedKrw)}`;
      $("#summaryRealizedPnlYear").style.color = yearRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
    }
    if ($("#pnlMonthLabel")) $("#pnlMonthLabel").textContent = `${currMonthStr}월`;
    if ($("#summaryRealizedPnlMonth")) {
      $("#summaryRealizedPnlMonth").textContent = `${monthRealizedKrw >= 0 ? '+' : ''}${money(monthRealizedKrw)}`;
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

    // 6. 안전자산 행 숨김
    if ($("#safeAssetRow")) $("#safeAssetRow").style.display = "none";

  } else {
    // -----------------------------------------------------------------------
    // MODE A: [자산] 탭 선택 시 (자산 종합 뷰)
    // -----------------------------------------------------------------------
    // 1. 순자산 (흰색) & 총부채 (푸른색)
    if ($("#netWorthRow")) $("#netWorthRow").style.display = "flex";
    if ($("#summaryNetWorth")) $("#summaryNetWorth").textContent = money(netWorth);
    if ($("#summaryTotalDebtCaption")) {
      $("#summaryTotalDebtCaption").textContent = totalAllDebt > 0 
        ? `총부채 ₩${number(totalAllDebt, 0)}` 
        : `부채 ₩0`;
    }

    // 원화/달러 주식 행 숨김 (자산 탭 전용 뷰에서는 투자자산 카드 내 주식으로 통합 표시)
    if ($("#krwStockRow")) $("#krwStockRow").style.display = "none";
    if ($("#usdStockRow")) $("#usdStockRow").style.display = "none";

    // 2. 투자자산 (부동산 + 주식)
    if ($("#totalInvestRow")) $("#totalInvestRow").style.display = "flex";
    if ($("#totalInvestLabelText")) $("#totalInvestLabelText").textContent = "투자자산";
    if ($("#totalValue")) $("#totalValue").textContent = money(totalInvestAssets);
    if ($("#subAssetBreakdown")) $("#subAssetBreakdown").style.display = "flex";
    if ($("#subRealEstateVal")) $("#subRealEstateVal").textContent = `부동산 ${money(totalREInvestEquity)}`;
    if ($("#subStockVal")) $("#subStockVal").textContent = `주식 ${money(totalStockVal)}`;

    // 3. 기대수익 (주식 평가손익 + 부동산 예상 수익 통합 반영!) & 일간 수익
    const totalExpectedProfit = (Number(s.profit_krw) || 0) + totalREProfit;
    const stockPurchaseCost = Math.max(0, totalStockVal - (Number(s.profit_krw) || 0));
    const totalCombinedCost = stockPurchaseCost + totalREPurchaseVal;
    const combinedReturnRate = totalCombinedCost > 0 ? ((totalExpectedProfit / totalCombinedCost) * 100) : 0;

    if ($("#expectedProfitRow")) $("#expectedProfitRow").style.display = "flex";
    if ($("#profitLabelText")) $("#profitLabelText").textContent = "기대수익";
    if ($("#totalProfit")) {
      $("#totalProfit").textContent = money(totalExpectedProfit);
      $("#totalProfit").style.color = totalExpectedProfit >= 0 ? "#f43f5e" : "#38bdf8";
    }
    const profitRateEl = $("#profitRate");
    if (profitRateEl) {
      profitRateEl.textContent = `(${combinedReturnRate >= 0 ? "+" : ""}${number(combinedReturnRate)}%)`;
      profitRateEl.style.color = totalExpectedProfit >= 0 ? "#f43f5e" : "#38bdf8";
    }

    // 4. 실현손익 (총 실현손익과 배당 및 이자를 포함하여 통합 합산 표시!)
    if ($("#realizedPnlRow")) $("#realizedPnlRow").style.display = "flex";
    if ($("#pnlLabelText")) $("#pnlLabelText").textContent = "실현손익";
    if ($("#summaryRealizedPnl")) {
      $("#summaryRealizedPnl").textContent = `${combinedRealizedKrw >= 0 ? "+" : ""}${money(combinedRealizedKrw)}`;
      $("#summaryRealizedPnl").style.color = combinedRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
    }
    if ($("#pnlSubBreakdown")) {
      $("#pnlSubBreakdown").style.display = "flex";
      $("#pnlSubBreakdown").innerHTML = `
        <span style="color:#cbd5e1;display:block;">매매차익 ₩${number(totalRealizedKrw, 0)}</span>
        <span style="color:#cbd5e1;display:block;">배당/이자 ₩${number(totalActualDivKrw, 0)}</span>
      `;
    }
    if ($("#pnlYearLabel")) $("#pnlYearLabel").textContent = `${currYear2Digit}년`;
    if ($("#summaryRealizedPnlYear")) {
      $("#summaryRealizedPnlYear").textContent = `${combinedYearRealizedKrw >= 0 ? '+' : ''}${money(combinedYearRealizedKrw)}`;
      $("#summaryRealizedPnlYear").style.color = combinedYearRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
    }
    if ($("#pnlMonthLabel")) $("#pnlMonthLabel").textContent = `${currMonthStr}월`;
    if ($("#summaryRealizedPnlMonth")) {
      $("#summaryRealizedPnlMonth").textContent = `${combinedMonthRealizedKrw >= 0 ? '+' : ''}${money(combinedMonthRealizedKrw)}`;
      $("#summaryRealizedPnlMonth").style.color = combinedMonthRealizedKrw >= 0 ? "#f43f5e" : "#38bdf8";
    }

    // 5. 배당금 행 숨김 (실현손익에 통합 표기됨)
    if ($("#dividendRow")) $("#dividendRow").style.display = "none";

    // 6. 안전자산 (예수금·예금, 임차보증금, 보험)
    if ($("#safeAssetRow")) $("#safeAssetRow").style.display = "flex";
    if ($("#summarySafeAssetVal")) $("#summarySafeAssetVal").textContent = money(totalSafeAssets);
    if ($("#subSafeCashVal")) $("#subSafeCashVal").textContent = `예수금 및 예금 ${money(totalAllCash)}`;
    if ($("#subSafeLeaseVal")) $("#subSafeLeaseVal").textContent = `임차보증금 ${money(totalTenantDepositVal)}`;
    if ($("#subSafeInsuranceVal")) $("#subSafeInsuranceVal").textContent = `보험 ${money(insuranceTotal)}`;
  }

  // 일간 수익 서브라인 (자산/주식 공통)
  const day = data.day_change || {};
  if ($("#dayProfitVal")) {
    if (day.change_krw != null) {
      const sign = day.change_krw >= 0 ? "+" : "";
      const rateSign = (day.change_rate || 0) >= 0 ? "+" : "";
      $("#dayProfitVal").textContent = `일간 수익 ${sign}${money(day.change_krw)} (${rateSign}${number(day.change_rate)}%)`;
      $("#dayProfitVal").style.color = day.change_krw >= 0 ? "#f43f5e" : "#38bdf8";
    } else {
      $("#dayProfitVal").textContent = `일간 수익 —`;
      $("#dayProfitVal").style.color = "#94a3b8";
    }
  }
  if ($("#dayCaption")) $("#dayCaption").textContent = day.date ? `${day.date} 대비` : "전일 대비";

  const krwStock = krw.stock_value_krw || (Number(krw.market_value_krw || 0) - Number(krw.cash || 0));
  $("#krwValue") && ($("#krwValue").textContent = money(krw.market_value_krw || 0));
  $("#krwCaption") && ($("#krwCaption").textContent = `주식 평가 ${money(krwStock)}`);
  const krwCashBadgeEl = $("#krwCashBadge");
  if (krwCashBadgeEl) krwCashBadgeEl.textContent = `(예수금 ${money(krw.cash || 0)})`;

  const usdStock = usd.stock_value || (Number(usd.market_value || 0) - Number(usd.cash || 0));
  $("#usdValue") && ($("#usdValue").textContent = money(usd.market_value || 0, "USD"));
  $("#usdCaption") && ($("#usdCaption").textContent = `주식 평가 ${money(usdStock, "USD")}`);
  const usdCashBadgeEl = $("#usdCashBadge");
  if (usdCashBadgeEl) usdCashBadgeEl.textContent = `(예수금 ${money(usd.cash || 0, "USD")})`;

  $("#updatedAt") && ($("#updatedAt").textContent = data.updated_at ? `마지막 자산 반영 ${new Date(data.updated_at).toLocaleString("ko-KR")}` : "아직 보유종목이 없습니다.");
  $("#accountCaption") && ($("#accountCaption").textContent = `전체 ${number(s.account_count, 0)}개 계좌`);
  // Presentation-only projection of the existing totals; no second calculation policy.
  window.dispatchEvent(new CustomEvent('wealth:summary', { detail: {
    owner: o, netWorth, debt: totalAllDebt, cash: totalAllCash,
    stock: totalStockVal, property: totalREInvestEquity,
    deposits: totalTenantDepositVal, insurance: insuranceTotal,
    updatedAt: data.updated_at || null,
    fxRates: data.fx_rates || {},
  }}));
}

// ── 3. 투자자산 분류 & 섹터별 도넛 원그래프 ──────────────────────────────────
const SECTOR_COLORS = [
  '#8e70fa', '#38bdf8', '#34d399', '#f59e0b', '#ec4899',
  '#a78bfa', '#06b6d4', '#10b981', '#f97316', '#fb7185',
  '#6366f1', '#14b8a6', '#84cc16', '#eab308', '#d946ef', '#64748b'
];

function renderAllocationDonut(items, emptyMsg = "투자자산 데이터가 없습니다.") {
  const wrap = $("#sectorDonutWrap");
  if (!wrap) return;

  const validItems = (items || []).filter(s => s.market_value_krw > 0);
  if (!validItems.length) {
    wrap.innerHTML = `<div class="empty">${html(emptyMsg)}</div>`;
    return;
  }

  const total = validItems.reduce((sum, s) => sum + s.market_value_krw, 0);
  const size = 140, r = 54, cx = 70, cy = 70, strokeWidth = 24;
  const circumference = 2 * Math.PI * r;

  let offset = 0;
  const slices = validItems.map((s, idx) => {
    const pct = total > 0 ? (s.market_value_krw / total) : 0;
    const dash = pct * circumference;
    const color = SECTOR_COLORS[idx % SECTOR_COLORS.length];
    const el = `
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${color}" stroke-width="${strokeWidth}"
        stroke-dasharray="${dash.toFixed(2)} ${(circumference - dash).toFixed(2)}"
        stroke-dashoffset="${(-offset).toFixed(2)}" stroke-linecap="round"
        class="clickable-sector-slice" data-sector-filter="${html(s.name)}" style="cursor:pointer;">
        <title>${s.name}: ${money(s.market_value_krw)} (${(pct * 100).toFixed(1)}%) - 클릭하여 종목 검색</title>
      </circle>
    `;
    offset += dash;
    return el;
  }).join('');

  const topItems = validItems.slice(0, 6);
  const legendHtml = topItems.map((s, idx) => {
    const color = SECTOR_COLORS[idx % SECTOR_COLORS.length];
    return `
      <div class="sector-legend-item clickable-sector-item" data-sector-filter="${html(s.name)}" style="cursor:pointer;" title="${html(s.name)} 관련 종목 검색">
        <span style="display:flex;align-items:center;gap:6px;">
          <i class="sector-legend-color" style="background:${color};"></i>
          <strong>${html(s.name)}</strong>
        </span>
        <span class="muted">${number(s.weight, 1)}%</span>
      </div>
    `;
  }).join('');

  wrap.innerHTML = `
    <div class="sector-donut-container">
      <div class="sector-donut-svg-wrap">
        <svg class="sector-donut-svg" viewBox="0 0 ${size} ${size}">
          ${slices}
        </svg>
      </div>
      <div class="sector-legend-list">
        ${legendHtml}
      </div>
    </div>
  `;
}

// ── 자산 분류 (섹터/자산군) 클릭 시 보유종목 자동 검색 & 스크롤 연동 ─────────────
function filterHoldingsByClassification(name) {
  if (!name) return;
  const searchInput = $("#searchInput");
  if (!searchInput) return;

  const currentVal = searchInput.value.trim();
  // 동일 항목 재클릭 시 검색어 해제(토글)
  if (currentVal.toLowerCase() === name.toLowerCase()) {
    searchInput.value = '';
  } else {
    searchInput.value = name;
  }

  if (dashboard) renderHoldings(dashboard);

  // 보유종목 섹션이 접혀있다면 펼침
  const holdingsPanel = document.getElementById('holdingsPanel');
  if (holdingsPanel && holdingsPanel.classList.contains('is-collapsed')) {
    if (typeof toggleSection === 'function') {
      toggleSection('holdings');
    }
  }

  // 보유종목 섹션으로 부드럽게 스크롤 & 검색창 하이라이트
  if (holdingsPanel) {
    holdingsPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  searchInput.focus();
  searchInput.classList.remove('search-pulse');
  void searchInput.offsetWidth; // re-flow
  searchInput.classList.add('search-pulse');
}

function renderClassifications(items) {
  const list = $("#classificationList");
  const donutWrap = $("#sectorDonutWrap");
  if (!list) return;

  if (donutWrap) donutWrap.style.display = 'block';
  list.classList.add('sector-mode');
  list.style.display = 'flex';
  list.style.flexDirection = 'column';

  if (currentAllocTab === 'sector') {
    const sectors = dashboard?.sector_classifications || rawDashboard?.sector_classifications || [];
    renderAllocationDonut(sectors, '섹터별 투자자산 데이터가 없습니다.');
    list.innerHTML = sectors.length ? sectors.map((item) => `
      <div class="classification-row clickable-sector-row" data-sector-filter="${html(item.name)}" style="cursor:pointer;" title="🔍 클릭하여 '${html(item.name)}' 보유종목 보기">
        <div class="classification-title">
          <strong>${html(item.name)}</strong>
          <span>${number(item.holding_count, 0)}종목 · ${number(item.weight, 1)}%</span>
        </div>
        <div class="classification-value">
          <span>${money(item.market_value_krw)}</span>
          <b class="${signClass(item.profit_krw)}">${item.return_rate >= 0 ? "+" : ""}${number(item.return_rate, 2)}%</b>
        </div>
        <div class="bar"><i style="width:${Math.min(item.weight, 100)}%"></i></div>
      </div>
    `).join("") : '<div class="empty">섹터별 투자자산 데이터가 없습니다.</div>';
  } else {
    const classes = dashboard?.classifications || rawDashboard?.classifications || items || [];
    renderAllocationDonut(classes, '자산군별 투자자산 데이터가 없습니다.');
    list.innerHTML = classes.length ? classes.map((item) => {
      let subLabel = `${number(item.holding_count, 0)}종목 · ${number(item.weight, 1)}%`;
      if (item.name === '부동산') {
        subLabel = `부동산 순에퀴티 · ${number(item.weight, 1)}%`;
      } else if (item.name === '현금·예수금') {
        subLabel = `은행 예수금 포함 · ${number(item.weight, 1)}%`;
      } else if (item.name === '보험') {
        subLabel = `예상 수령액/해약환급금 · ${number(item.weight, 1)}%`;
      }

      const showProfit = item.name !== '현금·예수금' && item.name !== '부동산' && item.name !== '보험';

      return `
        <div class="classification-row clickable-sector-row" data-sector-filter="${html(item.name)}" style="cursor:pointer;" title="🔍 클릭하여 '${html(item.name)}' 상세 보기">
          <div class="classification-title">
            <strong>${html(item.name)}</strong>
            <span>${subLabel}</span>
          </div>
          <div class="classification-value">
            <span>${money(item.market_value_krw)}</span>
            ${showProfit ? `<b class="${signClass(item.profit_krw)}">${item.return_rate >= 0 ? "+" : ""}${number(item.return_rate, 2)}%</b>` : `<span style="font-size:11.5px;color:#94a3b8;font-weight:600;">${number(item.weight, 1)}%</span>`}
          </div>
          <div class="bar"><i style="width:${Math.min(item.weight, 100)}%"></i></div>
        </div>
      `;
    }).join("") : '<div class="empty">자산을 불러오면 분류별 수익률을 표시합니다.</div>';
  }
}

function isAccountTaxDeductible(account) {
  if (!account) return true;
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

function isTaxAdvantagedAccount(account) {
  if (!account) return false;
  const aType = (account.account_type || "").toLowerCase();
  const aName = (account.name || account.account_name || "").toLowerCase();
  if (aType === "pension_savings" || aType === "irp" || aType === "isa") return true;
  if (aName.includes("연금") || aName.includes("irp") || aName.includes("isa")) return true;
  return false;
}

// ── 4. 계좌 목록 렌더링 ──────────────────────────────────────────────────────
function renderAccounts(items) {
  const container = $("#accountList");
  if ($("#securitiesTabCount")) $("#securitiesTabCount").textContent = (items || []).length;
  if (!container) return;
  if (!items || !items.length) { container.innerHTML = '<div class="empty">동기화된 계좌가 없습니다.</div>'; return; }
  const groups = new Map();
  items.forEach((item) => {
    const current = groups.get(item.broker) || { broker: item.broker, count: 0, items: [] };
    current.count += 1;
    current.items.push(item);
    groups.set(item.broker, current);
  });
  container.innerHTML = [...groups.values()].map((group) => {
    const accounts = group.items.map((account) => {
      const stockVal = Number(account.stock_value_krw || 0);
      const cashKrw = Number(account.cash_krw || 0);
      const cashUsd = Number(account.cash_usd || 0);
      const usdRate = Number(dashboard?.fx_rates?.USD || dashboard?.summary?.usd_krw_rate || rawDashboard?.summary?.usd_krw_rate || 1400);
      const cashTotalKrw = account.cash_total_krw !== undefined && account.cash_total_krw !== null
        ? Number(account.cash_total_krw)
        : (cashKrw + cashUsd * usdRate);
      const totalVal = Number(account.market_value_krw !== undefined ? account.market_value_krw : (stockVal + cashTotalKrw));
      const profitVal = Number(account.profit_krw || 0);

      const cashDetailParts = [];
      if (cashKrw > 0 || cashTotalKrw === 0) cashDetailParts.push(`₩${number(cashKrw, 0)}`);
      if (cashUsd > 0) cashDetailParts.push(`$${number(cashUsd, 2)}`);
      const cashFormatted = cashDetailParts.length ? cashDetailParts.join(" / ") : `₩${number(cashTotalKrw, 0)}`;

      const aName = (account.name || "").toLowerCase();
      const aType = account.account_type || (aName.includes("연금") ? "pension_savings" : (aName.includes("irp") ? "irp" : (aName.includes("isa") ? "isa" : "general")));
      const isTaxDeductible = isAccountTaxDeductible(account);

      let typeBadge = "";
      if (aType === "pension_savings") {
        if (isTaxDeductible) {
          typeBadge = `<span class="account-type-tag pension" data-toggle-tax-account-id="${account.id}" title="클릭 시 '비공제'로 즉시 전환" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(56,189,248,0.18);color:#38bdf8;border:1px solid rgba(56,189,248,0.4);margin-right:4px;cursor:pointer;">연금(공제O) 🔄</span>`;
        } else {
          typeBadge = `<span class="account-type-tag non-deductible" data-toggle-tax-account-id="${account.id}" title="클릭 시 '세액공제 신청'으로 즉시 전환" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.4);margin-right:4px;cursor:pointer;">연금(비공제) 🔄</span>`;
        }
      } else if (aType === "irp") {
        if (isTaxDeductible) {
          typeBadge = `<span class="account-type-tag irp" data-toggle-tax-account-id="${account.id}" title="클릭 시 '비공제'로 즉시 전환" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(168,85,247,0.18);color:#c084fc;border:1px solid rgba(168,85,247,0.4);margin-right:4px;cursor:pointer;">IRP(공제O) 🔄</span>`;
        } else {
          typeBadge = `<span class="account-type-tag non-deductible" data-toggle-tax-account-id="${account.id}" title="클릭 시 '세액공제 신청'으로 즉시 전환" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.4);margin-right:4px;cursor:pointer;">IRP(비공제) 🔄</span>`;
        }
      } else if (aType === "isa") {
        typeBadge = '<span class="account-type-tag isa" style="font-size:10.5px;padding:2px 6px;border-radius:4px;background:rgba(16,185,129,0.18);color:#34d399;border:1px solid rgba(16,185,129,0.4);margin-right:4px;">ISA</span>';
      }

      let taxBenefitBox = "";
      if (aType === "pension_savings" || aType === "irp") {
        const dep = Number(account.annual_deposit) || 0;
        const isaTr = Number(account.isa_transfer_amount) || 0;
        const cumSaved = calcAccountCumulativeTaxSaved(account);
        if (!isTaxDeductible) {
          taxBenefitBox = `
            <div style="margin-top:5px;display:inline-flex;align-items:center;gap:6px;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.35);border-radius:6px;padding:3px 8px;font-size:11.5px;color:#34d399;font-weight:600;">
              <span>🌿 비공제 계좌</span>
              <span style="color:#cbd5e1;font-weight:normal;">(납입 ₩${number(dep, 0)} · 원금 비과세 인출 대상${cumSaved > 0 ? ` · 누적 절세 <strong style="color:#4ade80;">+₩${number(cumSaved, 0)}</strong>` : ''})</span>
            </div>
          `;
        } else {
          const rate = account.income_level === "high" ? 13.2 : 16.5;
          const baseLimit = aType === "pension_savings" ? 6000000 : 9000000;
          const baseTarget = Math.min(dep, baseLimit);
          const isaTarget = Math.min(isaTr * 0.10, 3000000);
          const refund = Math.floor((baseTarget + isaTarget) * (rate / 100));
          const cumText = cumSaved > 0 ? ` · 누적 절세 <strong style="color:#4ade80;font-weight:700;">+₩${number(cumSaved, 0)}</strong>` : '';
          taxBenefitBox = `
            <div style="margin-top:5px;display:inline-flex;align-items:center;gap:6px;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.35);border-radius:6px;padding:3px 8px;font-size:11.5px;color:#38bdf8;font-weight:600;">
              <span>💎 세액공제 신청</span>
              <span style="color:#cbd5e1;font-weight:normal;">(납입 ₩${number(dep, 0)} → 예상 환급 <strong style="color:#4ade80;font-weight:700;">+₩${number(refund, 0)}</strong> / ${rate}%${cumText})</span>
            </div>
          `;
        }
      }

      return `<div class="account-row">
        <div class="account-row-info">
          <div class="account-row-title-line" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            ${typeBadge}
            <strong class="account-name-text" style="font-size:14px;font-weight:700;">${html(account.name)}</strong>
            <span class="saving-owner-badge" style="font-size:10.5px;padding:1px 6px;">${html(account.owner || '모두')}</span>
          </div>
          <div class="account-row-sub-line" style="font-size:12px;color:#94a3b8;margin-top:2px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <span>주식자산 <strong style="font-weight:600;">₩${number(stockVal, 0)}</strong> (${number(account.holding_count, 0)}종목)</span>
            <span style="color:#475569;">·</span>
            <span>예수금 <strong style="color:#38bdf8;font-weight:600;">${cashFormatted}</strong></span>
          </div>
          ${taxBenefitBox}
        </div>
        <div class="account-row-right">
          <div class="account-row-values">
            <div class="account-total-label" style="font-size:10.5px;color:#94a3b8;margin-bottom:1px;font-weight:500;">통장 총 자산</div>
            <strong class="account-total-val" style="font-size:15px;font-weight:800;letter-spacing:-0.3px;">₩${number(totalVal, 0)}</strong>
            ${profitVal !== 0 ? `
              <div class="account-profit-val ${signClass(profitVal)}" style="font-size:11.5px;margin-top:2px;font-weight:700;">
                ${profitVal > 0 ? '+' : ''}₩${number(profitVal, 0)}
              </div>
            ` : ''}
          </div>
          <div class="account-row-actions" style="display:flex;align-items:center;gap:5px;">
            <button class="account-action-button" data-account-edit-id="${account.id}" title="계좌 정보 및 예수금 수정" type="button">✎</button>
            <button class="mini-delete-button" data-account-del-id="${account.id}" title="계좌 삭제" type="button">🗑️</button>
          </div>
        </div>
      </div>`;
    }).join("");
    return `<section class="broker-group"><div class="broker-head"><strong>${html(group.broker)}</strong><span>${number(group.count, 0)}개 계좌</span></div><div class="broker-accounts">${accounts}</div></section>`;
  }).join("");
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
  const o = owner || currentOwner || '모두';
  const filteredSavings = o === '모두' 
    ? rawSavingsAccounts 
    : rawSavingsAccounts.filter(s => (s.owner || '모두') === o);
  const filteredBanks = o === '모두' 
    ? rawBankAccounts 
    : rawBankAccounts.filter(b => (b.owner || '모두') === o);
  const filteredLoans = o === '모두' 
    ? rawLoanAccounts 
    : rawLoanAccounts.filter(l => (l.owner || '모두') === o);

  // 1) 자유통장 잔고 분리
  const positiveBanks = filteredBanks.filter(b => (Number(b.balance) || 0) >= 0);
  const minusDebtBanks = filteredBanks.filter(b => (Number(b.balance) || 0) < 0);
  const minusBanks = minusDebtBanks; // 하위 호환 참조 유지

  // 2) 대출 탭에 표시할 마통 계좌: 실제 음수 잔고이거나 약정 한도(limit_amount > 0)가 등록된 계좌
  const minusOrCreditLineBanks = filteredBanks.filter(b => (Number(b.balance) || 0) < 0 || (Number(b.limit_amount) || 0) > 0);

  const totalPositiveBank = positiveBanks.reduce((sum, b) => sum + (Number(b.balance) || 0), 0);
  const totalMinusDebt = minusDebtBanks.reduce((sum, b) => sum + Math.abs(Number(b.balance) || 0), 0);

  const totalPaid = filteredSavings.reduce((sum, s) => sum + (Number(s.current_value) || Number(s.current_paid_amount) || 0), 0);
  const totalMaturity = filteredSavings.reduce((sum, s) => sum + (Number(s.calc?.maturity_total) || 0), 0);
  const totalPureLoan = filteredLoans.reduce((sum, l) => sum + (Number(l.current_balance) || 0), 0);
  const totalCombinedDebt = totalPureLoan + totalMinusDebt;

  // 순수 대출 이자 + 자유연동 마통 월 예상 이자 합산 (실제 음수 잔고일 때만 이자 발생)
  const totalMinusInterest = minusDebtBanks.reduce((sum, b) => {
    const debt = Math.abs(Number(b.balance || 0));
    const rate = Number(b.interest_rate || 0);
    return sum + (rate > 0 ? Math.round(debt * (rate / 100) / 12) : 0);
  }, 0);
  const totalPureLoanInterest = filteredLoans.reduce((sum, l) => sum + (Number(l.monthly_interest) || Number(l.calc?.monthly_interest) || 0), 0);
  const totalLoanInterest = totalPureLoanInterest + totalMinusInterest;

  // 상단 요약 카드 집계
  if ($("#totalBankBalanceVal")) $("#totalBankBalanceVal").textContent = `₩${number(totalPositiveBank, 0)}`;
  if ($("#totalSavingsPaidVal")) $("#totalSavingsPaidVal").textContent = `₩${number(totalPaid, 0)}`;
  if ($("#totalSavingsMaturityVal")) $("#totalSavingsMaturityVal").textContent = `₩${number(totalMaturity, 0)}`;
  if ($("#totalLoanBalanceVal")) $("#totalLoanBalanceVal").textContent = `₩${number(totalCombinedDebt, 0)}`;
  if ($("#totalLoanInterestSub")) {
    const activeMinusCount = minusDebtBanks.length;
    const minusNote = activeMinusCount > 0 ? ` (마통 ${activeMinusCount}건 사용 중)` : '';
    $("#totalLoanInterestSub").textContent = `월 예상 이자: ₩${number(totalLoanInterest, 0)}${minusNote}`;
  }

  const totalLoanListCount = filteredLoans.length + minusOrCreditLineBanks.length;
  const totalBankAllCount = filteredBanks.length + filteredSavings.length + totalLoanListCount;
  if ($("#allBankCount")) $("#allBankCount").textContent = totalBankAllCount;
  if ($("#banksCount")) $("#banksCount").textContent = filteredBanks.length;
  if ($("#savingsCount")) $("#savingsCount").textContent = filteredSavings.length;
  if ($("#loansCount")) $("#loansCount").textContent = totalLoanListCount;
  if ($("#bankingTabCount")) $("#bankingTabCount").textContent = totalBankAllCount;

  // 서브탭 표시 상태 동기화
  const isAll = currentSavingsSubtab === 'all';
  const isBanks = currentSavingsSubtab === 'banks';
  const isSavings = currentSavingsSubtab === 'savings';
  const isLoans = currentSavingsSubtab === 'loans';

  const secFree = $("#bankSectionFree");
  const secSavings = $("#bankSectionSavings");
  const secLoans = $("#bankSectionLoans");
  const titleFree = $("#bankTitleFree");
  const titleSavings = $("#bankTitleSavings");
  const titleLoans = $("#bankTitleLoans");

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

  if ($("#banksListWrap")) $("#banksListWrap").style.display = (isAll || isBanks) ? 'block' : 'none';
  if ($("#savingsGrid")) $("#savingsGrid").style.display = (isAll || isSavings) ? 'grid' : 'none';
  if ($("#loansGrid")) $("#loansGrid").style.display = (isAll || isLoans) ? 'grid' : 'none';
  document.querySelectorAll('.savings-subtab').forEach(b => b.classList.toggle('active', b.dataset.subtab === currentSavingsSubtab));

  // 은행 계좌 매핑 사전 (출금/입금 통장 표시용)
  const bankMap = new Map();
  rawBankAccounts.forEach(b => bankMap.set(b.id, `${b.bank_name} ${b.account_name}`));

  // 1) 예·적금 카드 그리드 렌더링
  const savingsGrid = $("#savingsGrid");
  if (savingsGrid) {
    if (!filteredSavings.length) {
      savingsGrid.innerHTML = '<div class="empty" style="grid-column:1/-1;">등록된 예·적금 상품이 없습니다. 상단 [🏦 계좌 추가]에서 예·적금을 선택하세요.</div>';
    } else {
      savingsGrid.innerHTML = filteredSavings.map(s => {
        const isHousing = s.saving_type === 'housing' || !s.end_date;
        const typeLabel = s.saving_type === 'housing' ? '주택청약' : (s.saving_type === 'deposit' ? '정기예금' : (s.saving_type === 'installment' ? '정기적금' : '자유적금'));
        const typeClass = s.saving_type === 'housing' ? 'housing' : (s.saving_type || 'deposit');
        const dDayText = isHousing ? '만기 없음' : (s.d_day != null ? (s.d_day <= 0 ? '만기 달성' : `D-${s.d_day}`) : '자유적립');
        const dDayClass = isHousing ? 'd-day-badge' : (s.d_day != null && s.d_day <= 0 ? 'd-day-badge done' : 'd-day-badge');

        const calc = s.calc || {};
        const taxLabel = s.tax_type === 'preferential' ? '세금우대 (1.4%)' : (s.tax_type === 'tax_free' ? '비과세 (0%)' : '일반과세 (15.4%)');

        const withdrawName = s.withdraw_account_id ? (bankMap.get(s.withdraw_account_id) || '연결통장') : '미설정';
        const depositName = s.deposit_account_id ? (bankMap.get(s.deposit_account_id) || '연결통장') : '미설정';

        const curVal = Number(s.current_value || s.current_paid_amount || 0);
        const transferInfo = isHousing
          ? (s.monthly_amount > 0 ? (s.auto_transfer_day ? `매월 ${s.auto_transfer_day}일 이체 · 월 ₩${number(s.monthly_amount, 0)}` : `월 ₩${number(s.monthly_amount, 0)} 납입`) : '자유 납입')
          : (s.saving_type === 'deposit' 
              ? `예치원금: ₩${number(s.target_amount || calc.total_principal || 0, 0)}`
              : (s.auto_transfer_day ? `매월 ${s.auto_transfer_day}일 이체 · 월 ₩${number(s.monthly_amount || 0, 0)}` : `월 ₩${number(s.monthly_amount || 0, 0)}`));

        return `
          <div class="saving-card ${isHousing ? 'housing-card' : ''}">
            <div class="saving-card-header">
              <div class="saving-card-title-group">
                <div class="saving-badge-row">
                  <span class="saving-type-badge ${typeClass}">${typeLabel}</span>
                  <span class="saving-owner-badge">${html(s.owner || '모두')}</span>
                  ${dDayText ? `<span class="${dDayClass}">${dDayText}</span>` : ''}
                </div>
                <h3 class="saving-product-name">${html(s.product_name)}</h3>
                <span class="saving-bank-name">${html(s.bank_name)}</span>
              </div>
              <div class="account-row-actions saving-card-actions">
                <button class="account-action-button" data-saving-edit-id="${s.id}" title="수정" type="button">✎</button>
                <button class="mini-delete-button" data-saving-del-id="${s.id}" title="삭제" type="button">🗑️</button>
              </div>
            </div>

            <!-- 진행률 프로그레스 바 -->
            <div class="saving-progress-wrap">
              <div class="saving-progress-meta">
                <span>${isHousing ? `불입 현황 (${s.start_date || '가입일'} ~ 만기 없음${s.elapsed_months ? ` · ${s.elapsed_months}개월 경과` : ''})` : `진행률 (${s.start_date || '가입'} ~ ${s.end_date || '만기'})`}</span>
                <strong>${isHousing ? '진행중' : `${s.progress_percent || 0}%`}</strong>
              </div>
              <div class="saving-progress-track">
                <div class="saving-progress-bar" style="width: ${isHousing ? 100 : Math.min(100, Math.max(0, s.progress_percent || 0))}%;"></div>
              </div>
            </div>

            <!-- 세부 정보 그리드 -->
            <div class="saving-card-details">
              <div class="saving-detail-row">
                <span class="saving-detail-label">약정 금리</span>
                <span class="saving-detail-val" style="color:#38bdf8;">연 ${s.interest_rate}%</span>
              </div>
              <div class="saving-detail-row">
                <span class="saving-detail-label">계약 기간</span>
                <span class="saving-detail-val">${isHousing ? '자유 / 무기한' : `${s.duration_months}개월`}</span>
              </div>
              <div class="saving-detail-row" style="grid-column:1/-1;">
                <span class="saving-detail-label">납입 조건</span>
                <span class="saving-detail-val">${transferInfo}</span>
              </div>
              <div class="saving-detail-row">
                <span class="saving-detail-label">출금 통장</span>
                <span class="saving-detail-val" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${html(withdrawName)}">${html(withdrawName)}</span>
              </div>
              <div class="saving-detail-row">
                <span class="saving-detail-label">만기 입금</span>
                <span class="saving-detail-val" style="max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${html(depositName)}">${html(depositName)}</span>
              </div>
            </div>

            <!-- 세전·세후 이자 하이라이트 박스 -->
            <div class="saving-interest-box" style="${isHousing ? 'background:rgba(56,189,248,0.06);border-color:rgba(56,189,248,0.25);' : ''}">
              <div class="saving-interest-row">
                <span style="color:#8fa0c5;">${isHousing ? '현재 누적 납입원금' : '총 불입원금'}</span>
                <span style="color:#e2e8f0;font-weight:600;">₩${number(isHousing ? curVal : (calc.total_principal || 0), 0)}</span>
              </div>
              <div class="saving-interest-row">
                <span style="color:#8fa0c5;">${isHousing ? '연간 예상 이자' : '세전 이자'}</span>
                <span style="color:#38bdf8;font-weight:600;">+₩${number(calc.pre_tax_interest || 0, 0)}</span>
              </div>
              <div class="saving-interest-row">
                <span style="color:#8fa0c5;">소득세 (${taxLabel})</span>
                <span style="color:#f43f5e;font-weight:600;">-₩${number(calc.tax_amount || 0, 0)}</span>
              </div>
              <div class="saving-interest-row maturity-row">
                <span>${isHousing ? '현재 평가액 (원금+세후이자)' : '만기 예상 실수령액'}</span>
                <span style="color:#42d5a3;font-size:14px;">₩${number(isHousing ? (curVal + (calc.after_tax_interest || 0)) : (calc.maturity_total || 0), 0)}</span>
              </div>
            </div>
          </div>
        `;
      }).join("");
    }
  }

  // 2) 자유입출금 통장 목록 테이블 렌더링
  const banksWrap = $("#banksListWrap");
  if (banksWrap) {
    if (!filteredBanks.length) {
      banksWrap.innerHTML = '<div class="empty">등록된 자유입출금 통장이 없습니다. 상단 [🏦 계좌 추가]에서 자유입출금 통장을 선택하세요.</div>';
    } else {
      banksWrap.innerHTML = `
        <table class="banks-table">
          <thead>
            <tr>
              <th>은행</th>
              <th>계좌 이름</th>
              <th>계좌 번호</th>
              <th>소유자</th>
              <th style="text-align:right;">잔고 (KRW)</th>
              <th>메모</th>
              <th style="text-align:center;">관리</th>
            </tr>
          </thead>
          <tbody>
            ${filteredBanks.map(b => {
              const bal = Number(b.balance || 0);
              const isMinus = bal < 0;
              const formattedBal = isMinus ? `-₩${number(Math.abs(bal), 0)}` : `₩${number(bal, 0)}`;
              const balStyle = isMinus ? 'color:#fb7185;font-weight:700;' : 'color:#38bdf8;font-weight:700;';
              const minusBadge = isMinus ? '<span class="saving-type-badge loan-minus" style="font-size:10px;padding:2px 6px;margin-left:6px;vertical-align:middle;">🔴 마통</span>' : '';

              return `
                <tr style="${isMinus ? 'background:rgba(244,63,94,0.03);' : ''}">
                  <td><strong>${html(b.bank_name)}</strong></td>
                  <td>${html(b.account_name)}${minusBadge}</td>
                  <td style="color:#8fa0c5;font-family:monospace;">${html(b.account_number || '-')}</td>
                  <td><span class="saving-owner-badge">${html(b.owner || '모두')}</span></td>
                  <td style="text-align:right;${balStyle}">${formattedBal}</td>
                  <td style="color:#8fa0c5;font-size:11.5px;">${html(b.memo || '')}</td>
                  <td style="text-align:center;">
                    <div class="account-row-actions" style="justify-content:center;">
                      <button class="account-action-button" data-bank-edit-id="${b.id}" title="통장 수정" type="button">✎</button>
                      <button class="mini-delete-button" data-bank-del-id="${b.id}" title="통장 삭제" type="button">🗑️</button>
                    </div>
                  </td>
                </tr>
              `;
            }).join("")}
          </tbody>
        </table>
      `;
    }
  }

  // 3) 대출·마이너스통장 카드 그리드 렌더링
  const loansGrid = $("#loansGrid");
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

    if (!allLoanItems.length) {
      loansGrid.innerHTML = '<div class="empty" style="grid-column:1/-1;">등록된 대출 또는 마이너스통장이 없습니다. 상단 [💳 대출 추가] 버튼을 눌러보세요.</div>';
    } else {
      loansGrid.innerHTML = allLoanItems.map(l => {
        const typeLabel = l.is_from_bank ? "자유연동 마통" : (LOAN_TYPE_LABELS[l.loan_type] || "대출");
        const repayLabel = REPAYMENT_TYPE_LABELS[l.repayment_type] || "만기일시";
        const dDayText = l.d_day != null ? (l.d_day <= 0 ? "만기 경과" : `만기 D-${l.d_day}`) : "";
        const dDayClass = l.d_day != null && l.d_day <= 0 ? "d-day-badge done" : "d-day-badge";

        const curBal = Number(l.current_balance || 0);
        const limitAmt = Number(l.limit_amount || 0);
        const monthlyInt = Number(l.monthly_interest || l.calc?.monthly_interest || 0);
        const monthlyPay = Number(l.monthly_payment || l.calc?.monthly_payment || monthlyInt);

        let utilPercent = 0;
        if (l.loan_type === 'minus' && limitAmt > 0) {
          utilPercent = Math.min(100, Math.round((curBal / limitAmt) * 100));
        }

        const linkedAccountText = l.linked_account_id ? (bankMap.get(l.linked_account_id) || "연결통장") : "미지정";
        const editAttr = l.is_from_bank ? `data-bank-edit-id="${l.id}"` : `data-loan-edit-id="${l.id}"`;
        const delAttr = l.is_from_bank ? `data-bank-del-id="${l.id}"` : `data-loan-del-id="${l.id}"`;

        const isUnusedMinus = l.is_from_bank && curBal === 0;

        return `
          <div class="saving-card loan-card ${isUnusedMinus ? 'unused-minus-card' : ''}">
            <div class="saving-card-header">
              <div class="saving-card-title-group">
                <div class="saving-badge-row">
                  ${isUnusedMinus ? `
                    <span class="saving-type-badge loan-credit" style="background:rgba(56,189,248,0.12);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);">🟢 자유연동 마통 (미사용)</span>
                  ` : `
                    <span class="saving-type-badge ${l.loan_type === 'minus' ? 'loan-minus' : 'loan-credit'}">${typeLabel}</span>
                  `}
                  <span class="saving-owner-badge">${html(l.owner || '모두')}</span>
                  ${dDayText ? `<span class="${dDayClass}">${dDayText}</span>` : ''}
                </div>
                <h3 class="saving-product-name">${html(l.product_name)}</h3>
                <span class="saving-bank-name">${html(l.bank_name)}</span>
              </div>
              <div class="account-row-actions saving-card-actions">
                <button class="account-action-button" ${editAttr} title="수정" type="button">✎</button>
                <button class="mini-delete-button" ${delAttr} title="삭제" type="button">🗑️</button>
              </div>
            </div>

            ${l.loan_type === 'minus' && limitAmt > 0 ? `
              <div class="saving-progress-wrap">
                <div class="saving-progress-meta">
                  <span>한도 소진율 (한도: ₩${number(limitAmt, 0)})</span>
                  <strong style="color:${utilPercent >= 80 ? '#fb7185' : '#38bdf8'};">${utilPercent}% ${isUnusedMinus ? '(전액 잔여)' : ''}</strong>
                </div>
                <div class="saving-progress-track">
                  <div class="saving-progress-bar" style="width: ${utilPercent}%; background: ${utilPercent >= 80 ? '#fb7185' : '#38bdf8'};"></div>
                </div>
              </div>
            ` : (l.is_from_bank ? `
              <div style="font-size:11px;color:#94a3b8;background:rgba(255,255,255,0.03);padding:6px 10px;border-radius:6px;margin:8px 0 4px;display:flex;justify-content:space-between;align-items:center;">
                <span>마통 한도 미설정</span>
                <button type="button" ${editAttr} style="background:none;border:none;color:#38bdf8;cursor:pointer;font-size:11px;padding:0;text-decoration:underline;">한도/금리 설정 ✎</button>
              </div>
            ` : '')}

            <div class="saving-card-details">
              <div class="saving-detail-row">
                <span class="saving-detail-label">약정 금리</span>
                <span class="saving-detail-val" style="${l.interest_rate > 0 ? (isUnusedMinus ? 'color:#38bdf8;font-weight:700;' : 'color:#fb7185;font-weight:700;') : 'color:#94a3b8;font-size:11px;'}">${l.interest_rate > 0 ? `연 ${l.interest_rate}%` : (l.is_from_bank ? '미설정 (✎ 수정)' : '-')}</span>
              </div>
              ${monthlyInt > 0 ? `
                <div class="saving-detail-row">
                  <span class="saving-detail-label">월 예상 이자</span>
                  <span class="saving-detail-val" style="color:#fb7185;font-weight:700;">₩${number(monthlyInt, 0)}</span>
                </div>
              ` : (isUnusedMinus ? `
                <div class="saving-detail-row">
                  <span class="saving-detail-label">월 예상 이자</span>
                  <span class="saving-detail-val" style="color:#38bdf8;font-weight:700;">₩0 (미발생)</span>
                </div>
              ` : '')}
              <div class="saving-detail-row">
                <span class="saving-detail-label">상환 방식</span>
                <span class="saving-detail-val">${l.is_from_bank ? '자유잔고 차감' : repayLabel}</span>
              </div>
              ${!l.is_from_bank && l.linked_account_id ? `
                <div class="saving-detail-row">
                  <span class="saving-detail-label">이자 출금 통장</span>
                  <span class="saving-detail-val" style="font-size:11px;">${html(linkedAccountText)}</span>
                </div>
              ` : ''}
              ${l.maturity_date ? `
                <div class="saving-detail-row" style="grid-column:1/-1;">
                  <span class="saving-detail-label">만기일</span>
                  <span class="saving-detail-val">${html(l.maturity_date)}</span>
                </div>
              ` : ''}
              ${l.memo ? `
                <div class="saving-detail-row" style="grid-column:1/-1;">
                  <span class="saving-detail-label">메모</span>
                  <span class="saving-detail-val" style="color:#94a3b8;font-size:11px;">${html(l.memo)}</span>
                </div>
              ` : ''}
            </div>

            ${isUnusedMinus ? `
              <div class="saving-interest-box" style="background:rgba(56,189,248,0.06);border-color:rgba(56,189,248,0.25);">
                <div class="saving-interest-row maturity-row" style="padding-top:0;border-top:none;">
                  <span style="color:#38bdf8;font-weight:600;">현재 대출 잔액</span>
                  <span style="color:#38bdf8;font-size:15px;font-weight:700;">₩0 (대출 미사용)</span>
                </div>
                <div class="saving-interest-row" style="padding-top:4px;font-size:11px;color:#94a3b8;">
                  <span>자유통장 잔고 유지중</span>
                  <span style="color:#38bdf8;font-weight:600;">+₩${number(l.raw_balance || 0, 0)}</span>
                </div>
              </div>
            ` : `
              <div class="saving-interest-box" style="background:rgba(244,63,94,0.06);border-color:rgba(244,63,94,0.2);">
                <div class="saving-interest-row maturity-row" style="padding-top:0;border-top:none;">
                  <span style="color:#fb7185;font-weight:600;">현재 대출 잔액 (부채)</span>
                  <span style="color:#fb7185;font-size:15px;font-weight:700;">₩${number(curBal, 0)}</span>
                </div>
                ${l.repayment_type === 'amortizing' ? `
                  <div class="saving-interest-row" style="padding-top:4px;font-size:11px;color:#94a3b8;">
                    <span>월 총 상환액 (원금+이자)</span>
                    <span>₩${number(monthlyPay, 0)}</span>
                  </div>
                ` : ''}
              </div>
            `}
          </div>
        `;
      }).join("");
    }
  }
}

function calcSavingInterestPreview() {
  const type = $("#savingTypeSelect")?.value || "deposit";
  const months = Number($("#savingDurationMonths")?.value) || 12;
  const rate = (Number($("#savingInterestRate")?.value) || 0) / 100;
  const taxType = $("#savingTaxType")?.value || "normal";

  let principal = 0;
  let preTax = 0;

  if (type === "deposit") {
    principal = Number($("#savingTargetAmount")?.value) || 0;
    preTax = principal * rate * (months / 12);
  } else if (type === "housing") {
    const curPaid = Number($("#savingCurrentPaid")?.value) || 0;
    const monthly = Number($("#savingMonthlyAmount")?.value) || 0;
    principal = curPaid > 0 ? curPaid : monthly;
    preTax = principal * rate;
  } else {
    const monthly = Number($("#savingMonthlyAmount")?.value) || 0;
    principal = monthly * months;
    preTax = monthly * rate * (months * (months + 1) / 24);
  }

  let taxRate = 0.154;
  if (taxType === "preferential") taxRate = 0.014;
  else if (taxType === "tax_free") taxRate = 0.0;

  const tax = Math.floor(preTax * taxRate);
  const afterTax = preTax - tax;
  const maturity = principal + afterTax;

  if ($("#prevTotalPrincipal")) $("#prevTotalPrincipal").textContent = `₩${number(principal, 0)}`;
  if ($("#prevPreTaxInterest")) $("#prevPreTaxInterest").textContent = `₩${number(preTax, 0)}`;
  if ($("#prevTaxAmount")) $("#prevTaxAmount").textContent = `₩${number(tax, 0)}`;
  if ($("#prevMaturityTotal")) $("#prevMaturityTotal").textContent = `₩${number(maturity, 0)}`;
}

function calcBankMinusPreview() {
  const balInput = Number($("#bankBalanceInput")?.value || 0);
  const limitInput = Number($("#bankLimitAmount")?.value || 0);
  const rateInput = Number($("#bankInterestRate")?.value || 0);

  const previewBox = $("#bankMinusPreviewBox");
  if (!previewBox) return;

  const isMinus = balInput < 0;
  if (isMinus || limitInput > 0 || rateInput > 0) {
    previewBox.style.display = "flex";
    // 잔고가 음수일 때만 실제 대출 사용액(부채)
    const debt = isMinus ? Math.abs(balInput) : 0;
    const monthlyInt = (debt > 0 && rateInput > 0) ? Math.round(debt * (rateInput / 100) / 12) : 0;
    const utilPercent = (debt > 0 && limitInput > 0) ? Math.min(100, Math.round((debt / limitInput) * 100)) : 0;

    const intEl = $("#bankMinusMonthlyInterest");
    const utilEl = $("#bankMinusUtilPercent");

    if (intEl) {
      if (debt > 0) {
        intEl.textContent = `₩${number(monthlyInt, 0)}`;
        intEl.style.color = "#fb7185";
      } else {
        intEl.textContent = `₩0 (대출 미사용)`;
        intEl.style.color = "#38bdf8";
      }
    }

    if (utilEl) {
      if (limitInput > 0) {
        if (debt > 0) {
          utilEl.textContent = `${utilPercent}% (사용 ₩${number(debt, 0)} / 한도 ₩${number(limitInput, 0)})`;
          utilEl.style.color = utilPercent >= 80 ? "#fb7185" : "#38bdf8";
        } else {
          utilEl.textContent = `0% (한도 ₩${number(limitInput, 0)} 전액 잔여)`;
          utilEl.style.color = "#38bdf8";
        }
      } else {
        utilEl.textContent = `한도 미설정`;
        utilEl.style.color = "#94a3b8";
      }
    }
  } else {
    previewBox.style.display = "none";
  }
}

function openBankAccountDialog(account = null, fromLoan = false) {
  const dialog = $("#bankAccountDialog");
  const form = $("#bankAccountForm");
  if (!dialog || !form) return;
  form.reset();
  form.querySelector("[name='id']").value = account ? account.id : "";

  const typeRow = form.querySelector(".bank-type-select-row");
  const switcher = form.querySelector(".bank-category-switcher");
  if (typeRow) typeRow.style.display = account ? "none" : "block";
  if (switcher) switcher.value = "free";

  const isMinus = account && (Number(account.balance) < 0 || Number(account.limit_amount) > 0 || fromLoan);
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

function openSavingAccountDialog(saving = null) {
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
  const bankOptions = '<option value="">-- 은행 계좌 선택 --</option>' + 
    rawBankAccounts.map(b => `<option value="${b.id}">${b.bank_name} - ${b.account_name} (${b.owner || '모두'})</option>`).join('');

  if (withdrawSel) withdrawSel.innerHTML = bankOptions;
  if (depositSel) depositSel.innerHTML = bankOptions;

  const isHousing = saving ? (saving.saving_type === 'housing' || !saving.end_date) : false;
  const noMaturityCheck = $("#savingNoMaturityCheck");
  if (noMaturityCheck) noMaturityCheck.checked = isHousing;

  if (saving) {
    form.querySelector("[name='saving_type']").value = saving.saving_type || (isHousing ? "housing" : "deposit");
    form.querySelector("[name='owner']").value = saving.owner || "모두";
    form.querySelector("[name='bank_name']").value = saving.bank_name || "";
    form.querySelector("[name='product_name']").value = saving.product_name || "";
    form.querySelector("[name='start_date']").value = saving.start_date || "";
    form.querySelector("[name='end_date']").value = saving.end_date || "";
    form.querySelector("[name='duration_months']").value = isHousing ? 0 : (saving.duration_months || 12);
    form.querySelector("[name='interest_rate']").value = saving.interest_rate || "";
    form.querySelector("[name='monthly_amount']").value = saving.monthly_amount || "";
    form.querySelector("[name='target_amount']").value = saving.target_amount || "";
    form.querySelector("[name='current_paid_amount']").value = saving.current_paid_amount || "";
    form.querySelector("[name='tax_type']").value = saving.tax_type || "normal";
    form.querySelector("[name='auto_transfer_day']").value = saving.auto_transfer_day || "";
    if (withdrawSel) withdrawSel.value = saving.withdraw_account_id || "";
    if (depositSel) depositSel.value = saving.deposit_account_id || "";
    form.querySelector("[name='memo']").value = saving.memo || "";
  } else {
    form.querySelector("[name='owner']").value = currentOwner !== "모두" ? currentOwner : "모두";
    const todayStr = new Date().toISOString().slice(0, 10);
    form.querySelector("[name='start_date']").value = todayStr;
    const nextYear = new Date();
    nextYear.setFullYear(nextYear.getFullYear() + 1);
    form.querySelector("[name='end_date']").value = nextYear.toISOString().slice(0, 10);
  }

  updateSavingTypeFields();
  calcSavingInterestPreview();
  refreshDialogKoreanHints(dialog);
  dialog.showModal();
}

function updateSavingTypeFields() {
  const type = $("#savingTypeSelect")?.value || "deposit";
  const monthlyLabel = $("#monthlyAmountLabel");
  const targetLabel = $("#targetAmountLabel");
  const noMaturityCheck = $("#savingNoMaturityCheck");
  const endDateInput = $("#savingEndDate");
  const durationInput = $("#savingDurationMonths");
  const durationLabel = $("#savingDurationLabel");

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

  if (document.getElementById('prevLoanBalance')) {
    document.getElementById('prevLoanBalance').textContent = `₩${number(curBal, 0)}`;
  }
  if (document.getElementById('prevLoanRateText')) {
    document.getElementById('prevLoanRateText').textContent = rate.toFixed(2);
  }
  if (document.getElementById('prevLoanInterest')) {
    document.getElementById('prevLoanInterest').textContent = `₩${number(monthlyInterest, 0)}`;
  }
  if (document.getElementById('prevLoanMonthlyPayment')) {
    document.getElementById('prevLoanMonthlyPayment').textContent = `₩${number(monthlyPayment, 0)}`;
  }
}

function refreshLoanOverdraftBankOptions(selectedValue = null) {
  const form = $("#loanAccountForm");
  const label = $("#loanOverdraftBankLabel");
  const select = $("#loanOverdraftBankSelect");
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
  select.innerHTML = '<option value="">-- 자동 상계 사용 안 함 --</option>' +
    eligibleBanks.map(b => `<option value="${b.id}">${html(b.bank_name)} ${html(b.account_name)} (${html(b.owner || '모두')})</option>`).join('');
  select.value = eligibleBanks.some(b => b.id === previousValue) ? previousValue : "";
}

function openLoanAccountDialog(loan = null) {
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
    select.innerHTML = '<option value="">-- 출금 은행 계좌 선택 (선택사항) --</option>' +
      rawBankAccounts.map(b => `<option value="${b.id}">${html(b.bank_name)} ${html(b.account_name)} (${html(b.owner || '모두')})</option>`).join('');
  }

  if (loan) {
    form.querySelector("[name='loan_type']").value = loan.loan_type || "minus";
    form.querySelector("[name='owner']").value = loan.owner || "모두";
    form.querySelector("[name='bank_name']").value = loan.bank_name || "";
    form.querySelector("[name='product_name']").value = loan.product_name || "";
    form.querySelector("[name='limit_amount']").value = loan.limit_amount || "";
    form.querySelector("[name='current_balance']").value = loan.current_balance || "";
    form.querySelector("[name='interest_rate']").value = loan.interest_rate || "";
    form.querySelector("[name='repayment_type']").value = loan.repayment_type || "bullet";
    if (select) select.value = loan.linked_account_id || "";
    refreshLoanOverdraftBankOptions(loan.overdraft_bank_account_id || "");
    form.querySelector("[name='maturity_date']").value = loan.maturity_date || "";
    form.querySelector("[name='memo']").value = loan.memo || "";
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

function openIntegratedBankDialog() {
  if (currentSavingsSubtab === 'savings') {
    openSavingAccountDialog();
  } else if (currentSavingsSubtab === 'loans') {
    openLoanAccountDialog();
  } else {
    openBankAccountDialog();
  }
}

// ── 4-2. 통합 계좌 카테고리 탭 (증권 / 은행 / 보험) ─────────────────────────
let rawInsuranceAccounts = [];
let currentAccountCategory = 'securities'; // 'securities' | 'banking' | 'insurance'

// 손익·배당은 기존 두 panel과 renderer를 공유하며 화면만 전환합니다.
let currentIncomeTab = 'pnl';
function setIncomeTab(tab) {
  currentIncomeTab = tab === 'dividend' ? 'dividend' : 'pnl';
  document.getElementById('realizedPnlPanel')?.classList.toggle('wealth-income-hidden', currentIncomeTab !== 'pnl');
  document.getElementById('dividendPanel')?.classList.toggle('wealth-income-hidden', currentIncomeTab !== 'dividend');
  document.querySelectorAll('#incomeTabs .income-tab').forEach(button => {
    const active = button.dataset.income === currentIncomeTab;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
}

document.getElementById('incomeTabs')?.addEventListener('click', event => {
  const tab = event.target.closest('.income-tab');
  if (tab) setIncomeTab(tab.dataset.income);
});
setIncomeTab('pnl');

const INSURANCE_TYPE_LABELS = {
  protection: "보장성보험",
  savings: "저축성보험",
  national_pension: "국민연금",
  yellow_umbrella: "노란우산공제",
  irp: "개인연금 / IRP",
  etc: "기타 공제",
};

const PAYMENT_STATUS_LABELS = {
  paying: "납입중",
  completed: "납입완료",
  deferred: "거치중",
};

function switchAccountCategory(category) {
  currentAccountCategory = category;
  document.querySelectorAll('.account-cat-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.cat === category);
  });

  const accountsPanel = document.getElementById('accountsPanel');
  if (accountsPanel && accountsPanel.classList.contains('is-collapsed')) {
    toggleSection('accounts');
  }

  const secPanel = document.getElementById('catPanelSecurities');
  const bnkPanel = document.getElementById('catPanelBanking');
  const insPanel = document.getElementById('catPanelInsurance');
  const rePanel = document.getElementById('catPanelRealEstate');

  if (secPanel) secPanel.style.display = category === 'securities' ? 'block' : 'none';
  if (bnkPanel) bnkPanel.style.display = category === 'banking' ? 'block' : 'none';
  if (insPanel) insPanel.style.display = category === 'insurance' ? 'block' : 'none';
  if (rePanel) rePanel.style.display = category === 'real_estate' ? 'block' : 'none';

  const secActs = document.getElementById('securitiesActions');
  const bnkActs = document.getElementById('bankingActions');
  const insActs = document.getElementById('insuranceActions');
  const reActs = document.getElementById('realEstateActions');

  if (secActs) secActs.style.display = category === 'securities' ? 'flex' : 'none';
  if (bnkActs) bnkActs.style.display = category === 'banking' ? 'flex' : 'none';
  if (insActs) insActs.style.display = category === 'insurance' ? 'flex' : 'none';
  if (reActs) reActs.style.display = category === 'real_estate' ? 'flex' : 'none';
}

function renderInsurance(insuranceList, owner = '모두') {
  rawInsuranceAccounts = insuranceList || [];
  renderInsuranceWithOwner(owner);
}

function renderInsuranceWithOwner(owner = '모두') {
  const o = owner || currentOwner || '모두';
  const filtered = o === '모두' 
    ? rawInsuranceAccounts 
    : rawInsuranceAccounts.filter(ins => (ins.owner || '모두') === o);

  const totalMonthly = filtered.reduce((sum, i) => sum + (Number(i.monthly_premium) || 0), 0);
  const totalPaid = filtered.reduce((sum, i) => sum + (Number(i.total_paid_amount) || 0), 0);
  const totalExpected = filtered.reduce((sum, i) => sum + (Number(i.expected_amount) || 0), 0);

  if ($("#totalInsuranceMonthlyVal")) $("#totalInsuranceMonthlyVal").textContent = `₩${number(totalMonthly, 0)}`;
  if ($("#totalInsurancePaidVal")) $("#totalInsurancePaidVal").textContent = `₩${number(totalPaid, 0)}`;
  if ($("#totalInsuranceExpectedVal")) $("#totalInsuranceExpectedVal").textContent = `₩${number(totalExpected, 0)}`;

  if ($("#insuranceTabCount")) $("#insuranceTabCount").textContent = filtered.length;

  const grid = $("#insuranceGrid");
  if (!grid) return;

  if (!filtered.length) {
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1;">등록된 보험·연금·공제 상품이 없습니다. 상단 [+ 보험/연금 추가] 버튼을 눌러보세요.</div>';
    return;
  }

  // 상단 절세 요약 배너 업데이트
  let totalCumulativeYuTaxSaved = 0;
  const yuTaxSaved = filtered.filter(i => (i.insurance_type === 'yellow_umbrella' || (i.product_name || '').includes('노란우산'))).reduce((sum, i) => {
    const monthly = Number(i.monthly_premium) || 0;
    const bracket = i.income_bracket || '40m_to_100m';
    const rate = Number(i.marginal_tax_rate) || 26.4;
    const limits = { under_40m: 5000000, "40m_to_100m": 3000000, over_100m: 2000000 };
    const limit = limits[bracket] || 3000000;
    const deduction = Math.min(monthly * 12, limit);
    const saved = Math.floor(deduction * (rate / 100));

    // 누적 절세액 합산
    const yuList = Array.isArray(i.yearly_contributions) ? i.yearly_contributions : [];
    if (yuList.length > 0) {
      yuList.forEach(y => {
        const isDed = y.is_deductible !== false && String(y.is_deductible) !== 'false';
        if (isDed) {
          totalCumulativeYuTaxSaved += Math.floor(Math.min(Number(y.deposit || 0), limit) * (rate / 100));
        }
      });
    } else {
      totalCumulativeYuTaxSaved += saved;
    }

    return sum + saved;
  }, 0);

  // 증권 계좌 연금/IRP 절세액 합산
  let totalCumulativePensionTaxSaved = 0;
  const secAccounts = (dashboard?.accounts || []).filter(a => o === '모두' || (a.owner || '모두') === o);
  const pensionTaxSaved = secAccounts.reduce((sum, a) => {
    const aName = (a.name || '').toLowerCase();
    const aType = a.account_type || (aName.includes('연금') ? 'pension_savings' : (aName.includes('irp') ? 'irp' : 'general'));
    if (aType === 'pension_savings' || aType === 'irp') {
      const isTaxDeductible = isAccountTaxDeductible(a);
      const dep = Number(a.annual_deposit) || 0;
      const isaTr = Number(a.isa_transfer_amount) || 0;
      const rate = a.income_level === 'high' ? 0.132 : 0.165;
      const baseLimit = aType === 'pension_savings' ? 6000000 : 9000000;
      const baseTarget = isTaxDeductible ? Math.min(dep, baseLimit) : 0;
      const isaTarget = Math.min(isaTr * 0.10, 3000000);
      const refund = Math.floor((baseTarget + isaTarget) * rate);

      const yList = Array.isArray(a.yearly_contributions) ? a.yearly_contributions : [];
      if (yList.length > 0) {
        yList.forEach(y => {
          const isDed = isTaxDeductible && y.is_deductible !== false && String(y.is_deductible) !== 'false';
          if (isDed) {
            totalCumulativePensionTaxSaved += Math.floor(Math.min(Number(y.deposit || 0), baseLimit) * rate);
          }
        });
      } else {
        totalCumulativePensionTaxSaved += isTaxDeductible ? refund : 0;
      }

      return sum + refund;
    }
    return sum;
  }, 0);

  const grandTotalTax = yuTaxSaved + pensionTaxSaved;
  const grandCumulativeTax = totalCumulativeYuTaxSaved + totalCumulativePensionTaxSaved;
  if ($("#grandTotalTaxBenefitVal")) {
    if (grandCumulativeTax > grandTotalTax) {
      $("#grandTotalTaxBenefitVal").innerHTML = `₩${number(grandTotalTax, 0)} <span style="font-size:12px;color:#a78bfa;font-weight:600;">(누적 ₩${number(grandCumulativeTax, 0)})</span>`;
    } else {
      $("#grandTotalTaxBenefitVal").textContent = `₩${number(grandTotalTax, 0)}`;
    }
  }

  // 증권 계좌 연금저축 & IRP 카드 생성
  const secPensionAccounts = (dashboard?.accounts || []).filter(a => {
    if (o !== '모두' && (a.owner || '모두') !== o) return false;
    const aName = (a.name || '').toLowerCase();
    const aType = a.account_type || (aName.includes('연금') ? 'pension_savings' : (aName.includes('irp') ? 'irp' : 'general'));
    return aType === 'pension_savings' || aType === 'irp';
  });

  const pensionCardsHtml = secPensionAccounts.map(a => {
    const aName = (a.name || '').toLowerCase();
    const aType = a.account_type || (aName.includes('연금') ? 'pension_savings' : 'irp');
    const isTaxDeductible = isAccountTaxDeductible(a);
    const dep = Number(a.annual_deposit) || 0;
    const isaTr = Number(a.isa_transfer_amount) || 0;
    const rate = a.income_level === 'high' ? 13.2 : 16.5;
    const baseLimit = aType === 'pension_savings' ? 6000000 : 9000000;
    const baseTarget = isTaxDeductible ? Math.min(dep, baseLimit) : 0;
    const isaTarget = Math.min(isaTr * 0.10, 3000000);
    const totalTarget = baseTarget + isaTarget;
    const refund = Math.floor(totalTarget * (rate / 100));

    const typeLabel = aType === 'pension_savings' ? '연금저축' : '개인형 IRP';
    const badgeClass = isTaxDeductible ? 'pension' : 'non-deductible';
    const statusLabel = isTaxDeductible ? '세액공제 신청' : '세액공제 제외(비공제)';

    const yearlyContributions = Array.isArray(a.yearly_contributions) ? a.yearly_contributions : [];
    let cumulativeTaxSaved = 0;
    let yearlyHistoryHtml = '';

    if (yearlyContributions.length > 0) {
      const yearlyRows = yearlyContributions.map(yc => {
        const yYear = String(yc.year || '').trim();
        const yDep = Number(yc.deposit || 0);
        const yDeductible = isTaxDeductible && yc.is_deductible !== false && String(yc.is_deductible) !== 'false';
        const yTarget = yDeductible ? Math.min(yDep, baseLimit) : 0;
        const ySaved = yDeductible ? Math.floor(yTarget * (rate / 100)) : 0;
        if (yDeductible) cumulativeTaxSaved += ySaved;

        return `
          <div style="display:flex;justify-content:space-between;align-items:center;padding:3px 6px;border-radius:4px;font-size:11.5px;margin-bottom:3px;">
            <span><strong>${html(yYear)}년:</strong> 입금 ₩${number(yDep, 0)}</span>
            <span>➔ ${yDeductible ? `<strong style="color:#4ade80;">절세 ₩${number(ySaved, 0)}</strong>` : '<span style="color:#34d399;font-weight:600;">비공제 (₩0)</span>'}</span>
          </div>
        `;
      }).join('');

      yearlyHistoryHtml = `
        <div class="insurance-yearly-history" style="margin-top:10px;padding:8px 10px;border:1px solid ${isTaxDeductible ? 'rgba(56,189,248,0.25)' : 'rgba(16,185,129,0.25)'};border-radius:6px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-size:11.5px;">
            <span style="font-weight:700;color:${isTaxDeductible ? '#38bdf8' : '#34d399'};">📅 연도별 절세 이력</span>
            <span style="font-weight:700;color:#4ade80;font-size:12px;">누적 절세액: ₩${number(cumulativeTaxSaved, 0)}</span>
          </div>
          ${yearlyRows}
        </div>
      `;
    } else {
      cumulativeTaxSaved = isTaxDeductible ? refund : 0;
    }

    return `
      <div class="saving-card" style="border:1px solid ${isTaxDeductible ? 'rgba(56,189,248,0.35)' : 'rgba(16,185,129,0.35)'};">
        <div class="saving-card-header">
          <div class="saving-card-title-group">
            <div class="saving-badge-row">
              <span class="insurance-type-badge ${badgeClass}" style="${isTaxDeductible ? 'background:rgba(56,189,248,0.15);color:#38bdf8;' : 'background:rgba(16,185,129,0.15);color:#34d399;'}">${typeLabel}</span>
              <span class="payment-status-badge ${badgeClass}" style="${isTaxDeductible ? 'background:rgba(56,189,248,0.15);color:#38bdf8;' : 'background:rgba(16,185,129,0.15);color:#34d399;'}">${statusLabel}</span>
              <span class="saving-owner-badge">${html(a.owner || '모두')}</span>
            </div>
            <h3 class="saving-product-name">${html(a.name)}</h3>
            <span class="saving-bank-name">${html(a.broker)}</span>
          </div>
          <div class="account-row-actions saving-card-actions">
            <button class="account-action-button" data-account-edit-id="${a.id}" title="계좌 정보 수정" type="button">✎</button>
          </div>
        </div>

        <div class="saving-card-details">
          <div class="saving-detail-row">
            <span class="saving-detail-label">올해 납입액</span>
            <span class="saving-detail-val" style="color:#38bdf8;font-weight:700;">₩${number(dep, 0)}</span>
          </div>
          <div class="saving-detail-row">
            <span class="saving-detail-label">연간 납입한도</span>
            <span class="saving-detail-val">₩18,000,000</span>
          </div>
          <div class="saving-detail-row" style="grid-column:1/-1;">
            <span class="saving-detail-label">세액공제 한도</span>
            <span class="saving-detail-val">${isTaxDeductible ? `연 ₩${number(baseLimit, 0)} (소득구간 ${rate}%)` : '<span style="color:#34d399;">비공제 (원금 비과세 인출 대상)</span>'}</span>
          </div>
        </div>

        <div class="saving-interest-box" style="background:${isTaxDeductible ? 'rgba(56,189,248,0.08)' : 'rgba(16,185,129,0.08)'};border-color:${isTaxDeductible ? 'rgba(56,189,248,0.35)' : 'rgba(16,185,129,0.35)'};margin-top:8px;">
          <div class="saving-interest-row">
            <span style="color:${isTaxDeductible ? '#38bdf8' : '#34d399'};">세액공제 대상 금액</span>
            <span style="color:#e2e8f0;font-weight:600;">₩${number(totalTarget, 0)}${isaTarget > 0 ? ` (ISA 전환 추가 ₩${number(isaTarget, 0)})` : ''}</span>
          </div>
          <div class="saving-interest-row maturity-row" style="border-top:1px dashed ${isTaxDeductible ? 'rgba(56,189,248,0.3)' : 'rgba(16,185,129,0.3)'};padding-top:4px;margin-top:4px;">
            <span style="color:${isTaxDeductible ? '#38bdf8' : '#34d399'};">예상 세금 절감(환급)액</span>
            <span style="color:#4ade80;font-size:14px;font-weight:700;">${isTaxDeductible ? `+₩${number(refund, 0)} (${rate}%)` : '₩0 (원금 100% 비과세 인출)'}</span>
          </div>
        </div>

        ${yearlyHistoryHtml}
      </div>
    `;
  }).join('');

  const insuranceCardsHtml = filtered.map(ins => {
    const typeKey = ins.insurance_type || 'protection';
    const typeLabel = INSURANCE_TYPE_LABELS[typeKey] || '보험/공제';
    const statusKey = ins.payment_status || 'paying';
    const statusLabel = PAYMENT_STATUS_LABELS[statusKey] || '납입중';

    const periodText = (ins.start_date || ins.maturity_date)
      ? `${ins.start_date || '가입'} ~ ${ins.maturity_date || '만기'}`
      : '기간 미지정';

    const isYU = typeKey === 'yellow_umbrella' || (ins.product_name || '').includes('노란우산');
    let yuTaxBox = '';
    let yuYearlyRowsHtml = '';
    if (isYU) {
      const monthly = Number(ins.monthly_premium) || 0;
      const bracket = ins.income_bracket || '40m_to_100m';
      const rate = Number(ins.marginal_tax_rate) || 26.4;
      const limits = { under_40m: 5000000, "40m_to_100m": 3000000, over_100m: 2000000 };
      const limit = limits[bracket] || 3000000;
      const deduction = Math.min(monthly * 12, limit);
      const taxSaved = Math.floor(deduction * (rate / 100));

      const yuYearlyList = Array.isArray(ins.yearly_contributions) ? ins.yearly_contributions : [];
      let yuCumulativeSaved = 0;

      if (yuYearlyList.length > 0) {
        const rows = yuYearlyList.map(yc => {
          const yYear = String(yc.year || '').trim();
          const yDep = Number(yc.deposit || 0);
          const yDeductible = yc.is_deductible !== false && String(yc.is_deductible) !== 'false';
          const yTarget = yDeductible ? Math.min(yDep, limit) : 0;
          const ySaved = yDeductible ? Math.floor(yTarget * (rate / 100)) : 0;
          if (yDeductible) yuCumulativeSaved += ySaved;

          return `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:3px 6px;border-radius:4px;font-size:11.5px;margin-bottom:3px;">
            <span><strong>${html(yYear)}년:</strong> 입금 ₩${number(yDep, 0)}</span>
            <span>➔ ${yDeductible ? `<strong style="color:#4ade80;">소득공제 절세 ₩${number(ySaved, 0)}</strong>` : '<span style="color:#34d399;font-weight:600;">비공제 (₩0)</span>'}</span>
          </div>
        `;
        }).join('');

        yuYearlyRowsHtml = `
          <div class="insurance-yearly-history" style="margin-top:10px;padding:8px 10px;border:1px solid rgba(234,179,8,0.3);border-radius:6px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;font-size:11.5px;">
              <span style="font-weight:700;color:#facc15;">📅 연도별 소득공제 이력</span>
              <span style="font-weight:700;color:#4ade80;font-size:12px;">누적 절세액: ₩${number(yuCumulativeSaved, 0)}</span>
            </div>
            ${rows}
          </div>
        `;
      } else {
        yuCumulativeSaved = taxSaved;
      }

      yuTaxBox = `
        <div class="saving-interest-box" style="background:rgba(234,179,8,0.08);border-color:rgba(234,179,8,0.35);margin-top:8px;">
          <div class="saving-interest-row">
            <span style="color:#facc15;">연간 소득공제 대상</span>
            <span class="saving-detail-val" style="font-weight:600;">₩${number(deduction, 0)} (한도 ₩${number(limit, 0)})</span>
          </div>
          <div class="saving-interest-row maturity-row" style="border-top:1px dashed rgba(234,179,8,0.3);padding-top:4px;margin-top:4px;">
            <span style="color:#facc15;">예상 세금 절감(환급)액</span>
            <span style="color:#4ade80;font-size:14px;font-weight:700;">+₩${number(taxSaved, 0)} (${rate}%)</span>
          </div>
        </div>
        ${yuYearlyRowsHtml}
      `;
    }

    return `
      <div class="saving-card ${isYU ? 'yellow-umbrella-card' : ''}">
        <div class="saving-card-header">
          <div class="saving-card-title-group">
            <div class="saving-badge-row">
              <span class="insurance-type-badge ${typeKey}">${typeLabel}</span>
              <span class="payment-status-badge ${statusKey}">${statusLabel}</span>
              <span class="saving-owner-badge">${html(ins.owner || '모두')}</span>
            </div>
            <h3 class="saving-product-name">${html(ins.product_name)}</h3>
            <span class="saving-bank-name">${html(ins.company_name)}</span>
          </div>
          <div class="account-row-actions saving-card-actions">
            <button class="account-action-button" data-insurance-edit-id="${ins.id}" title="수정" type="button">✎</button>
            <button class="mini-delete-button" data-insurance-del-id="${ins.id}" title="삭제" type="button">🗑️</button>
          </div>
        </div>

        <div class="saving-card-details">
          <div class="saving-detail-row">
            <span class="saving-detail-label">월 납입액</span>
            <span class="saving-detail-val" style="color:#38bdf8;">₩${number(ins.monthly_premium || 0, 0)}</span>
          </div>
          <div class="saving-detail-row">
            <span class="saving-detail-label">누적 납입액</span>
            <span class="saving-detail-val">₩${number(ins.total_paid_amount || 0, 0)}</span>
          </div>
          <div class="saving-detail-row" style="grid-column:1/-1;">
            <span class="saving-detail-label">계약 기간</span>
            <span class="saving-detail-val">${html(periodText)}</span>
          </div>
          ${ins.memo ? `
            <div class="saving-detail-row" style="grid-column:1/-1;">
              <span class="saving-detail-label">메모</span>
              <span class="saving-detail-val" style="color:#94a3b8;font-size:11px;">${html(ins.memo)}</span>
            </div>
          ` : ''}
        </div>

        ${yuTaxBox}

        ${(ins.payout_type === 'monthly_pension' || (Number(ins.monthly_payout) || 0) > 0) ? `
          <div class="saving-interest-box" style="margin-top:10px;background:rgba(56,189,248,0.06);border-color:rgba(56,189,248,0.35);">
            <div class="saving-interest-row">
              <span style="color:#7dd3fc;">💎 월 예상 수령액</span>
              <span style="color:#38bdf8;font-weight:700;font-size:13.5px;">월 ₩${number(ins.monthly_payout || 0, 0)}</span>
            </div>
            <div class="saving-interest-row maturity-row" style="border-top:1px dashed rgba(56,189,248,0.3);padding-top:5px;margin-top:5px;">
              <span style="color:#e2e8f0;">총자산 환산액 (${ins.payout_duration_years || 20}년)</span>
              <span style="color:#4ade80;font-size:14.5px;font-weight:800;">₩${number(ins.expected_amount || ins.converted_total_asset || 0, 0)}</span>
            </div>
          </div>
        ` : `
          <div class="saving-interest-box" style="margin-top:${isYU ? '6px' : '10px'};">
            <div class="saving-interest-row maturity-row" style="padding-top:0;border-top:none;">
              <span>예상 수령액 / 해약환급금</span>
              <span style="color:#42d5a3;font-size:14px;">₩${number(ins.expected_amount || 0, 0)}</span>
            </div>
          </div>
        `}
      </div>
    `;
  }).join('');

  grid.innerHTML = (pensionCardsHtml + insuranceCardsHtml) || '<div class="empty">등록된 보험/연금 상품이 없습니다.</div>';
}

function updatePensionPayoutFields() {
  const isPension = $("#payoutTypeMonthlyPension")?.checked;
  const lumpSumGroup = $("#lumpSumAmountGroup");
  const pensionGroup = $("#pensionPayoutGroup");

  if (lumpSumGroup) lumpSumGroup.style.display = isPension ? "none" : "block";
  if (pensionGroup) pensionGroup.style.display = isPension ? "block" : "none";

  if (isPension) {
    const monthly = Number($("#pensionMonthlyPayout")?.value) || 0;
    const years = Number($("#pensionDurationSelect")?.value) || 20;
    const totalMonths = Math.round(years * 12);
    const converted = Math.round(monthly * totalMonths);

    if ($("#pensionDurationText")) {
      $("#pensionDurationText").textContent = `${years}년 (${totalMonths}개월)`;
    }
    if ($("#pensionConvertedTotalText")) {
      $("#pensionConvertedTotalText").textContent = `₩${number(converted, 0)}`;
    }
    // 일시금 필드에도 동기화하여 안전자산 및 호환성 보장
    if ($("#insuranceExpectedAmount")) {
      $("#insuranceExpectedAmount").value = converted > 0 ? converted : "";
    }
  }
}

let yuCurrentYearlyList = [];

function renderYuYearlyFormRows(form = document.getElementById("insuranceAccountForm")) {
  const container = form?.querySelector("#yuYearlyList");
  if (!container) return;

  const bracket = form.querySelector("#yuIncomeBracket")?.value || "40m_to_100m";
  const rate = Number(form.querySelector("#yuMarginalRate")?.value) || 26.4;
  const limits = { under_40m: 5000000, "40m_to_100m": 3000000, over_100m: 2000000 };
  const maxLimit = limits[bracket] || 3000000;

  let cumulativeSaved = 0;

  if (!yuCurrentYearlyList.length) {
    container.innerHTML = `<div style="font-size:11px;color:#94a3b8;padding:8px 4px;text-align:center;">등록된 연도별 납입 이력이 없습니다. [+ 연도 추가]를 눌러 과거 연도별 입금액을 기록해보세요.</div>`;
  } else {
    container.innerHTML = yuCurrentYearlyList.map((yc, idx) => {
      const yr = yc.year || (2024 - idx);
      const dep = Number(yc.deposit || 0);
      const ded = yc.is_deductible !== false && String(yc.is_deductible) !== "false";
      const target = ded ? Math.min(dep, maxLimit) : 0;
      const saved = ded ? Math.floor(target * (rate / 100)) : 0;
      if (ded) cumulativeSaved += saved;

      return `
        <div class="yu-yearly-row" data-index="${idx}" style="display:flex;align-items:center;gap:6px;background:rgba(0,0,0,0.25);border:1px solid rgba(234,179,8,0.25);padding:5px 8px;border-radius:6px;">
          <input type="number" class="yu-yearly-year" value="${yr}" placeholder="연도" style="width:68px;font-size:12px;padding:3px 6px;border-radius:4px;border:1px solid #334155;background:#0f172a;color:#f8fafc;" />
          <span style="font-size:11px;color:#94a3b8;">년</span>
          <input type="number" class="yu-yearly-deposit" value="${dep || ''}" placeholder="납입액" style="flex:1;min-width:70px;font-size:12px;padding:3px 6px;border-radius:4px;border:1px solid #334155;background:#0f172a;color:#f8fafc;" min="0" step="any" />
          <span style="font-size:11px;color:#94a3b8;">원</span>
          <select class="yu-yearly-deductible" style="width:78px;font-size:11.5px;padding:3px 4px;border-radius:4px;border:1px solid #334155;background:#0f172a;color:${ded ? '#facc15' : '#34d399'};font-weight:600;">
            <option value="true" ${yc.is_deductible !== false && String(yc.is_deductible) !== "false" ? "selected" : ""}>공제</option>
            <option value="false" ${yc.is_deductible === false || String(yc.is_deductible) === "false" ? "selected" : ""}>비공제</option>
          </select>
          <span class="yu-yearly-saved-badge" style="min-width:85px;text-align:right;font-size:11.5px;font-weight:700;color:${ded ? '#4ade80' : '#34d399'};">
            ${ded ? `+₩${number(saved, 0)}` : '비공제(₩0)'}
          </span>
          <button type="button" class="yu-yearly-del-btn" data-index="${idx}" style="background:transparent;border:none;color:#f87171;cursor:pointer;font-size:14px;padding:0 4px;" title="삭제">✕</button>
        </div>
      `;
    }).join("");
  }

  const cumEl = form?.querySelector("#yuCumulativeSavedText");
  if (cumEl) cumEl.textContent = `₩${number(cumulativeSaved, 0)}`;
}

function updateYellowUmbrellaFields() {
  const type = $("#insuranceTypeSelect")?.value;
  const taxGroup = $("#yellowUmbrellaTaxGroup");
  const isYU = type === "yellow_umbrella";
  if (taxGroup) taxGroup.style.display = isYU ? "block" : "none";

  if (isYU) {
    const monthly = Number($("#insuranceAccountForm [name='monthly_premium']")?.value) || 0;
    const bracket = $("#yuIncomeBracket")?.value || "40m_to_100m";
    const rate = Number($("#yuMarginalRate")?.value) || 26.4;

    const limits = { under_40m: 5000000, "40m_to_100m": 3000000, over_100m: 2000000 };
    const maxLimit = limits[bracket] || 3000000;
    const annualPaid = monthly * 12;
    const deduction = Math.min(annualPaid, maxLimit);
    const taxSaved = Math.floor(deduction * (rate / 100));

    if ($("#yuDeductionAmountText")) $("#yuDeductionAmountText").textContent = `₩${number(deduction, 0)} (한도 ₩${number(maxLimit, 0)})`;
    if ($("#yuTaxSavedText")) $("#yuTaxSavedText").textContent = `₩${number(taxSaved, 0)} (${rate}%)`;

    renderYuYearlyFormRows($("#insuranceAccountForm"));
  }
}

function openInsuranceAccountDialog(item = null) {
  const dialog = $("#insuranceAccountDialog");
  const form = $("#insuranceAccountForm");
  if (!dialog || !form) return;
  form.reset();
  form.querySelector("[name='id']").value = item ? item.id : "";
  if ($("#insuranceAccountDialogTitle")) {
    $("#insuranceAccountDialogTitle").textContent = item ? "보험 / 연금 / 공제 상품 수정" : "보험 / 연금 / 공제 상품 추가";
  }
  if (item) {
    form.querySelector("[name='insurance_type']").value = item.insurance_type || "protection";
    form.querySelector("[name='owner']").value = item.owner || "모두";
    form.querySelector("[name='company_name']").value = item.company_name || "";
    form.querySelector("[name='product_name']").value = item.product_name || "";
    form.querySelector("[name='payment_status']").value = item.payment_status || "paying";
    form.querySelector("[name='income_bracket']").value = item.income_bracket || "40m_to_100m";
    if (item.marginal_tax_rate) {
      form.querySelector("[name='marginal_tax_rate']").value = String(item.marginal_tax_rate);
    }
    form.querySelector("[name='monthly_premium']").value = item.monthly_premium || "";
    form.querySelector("[name='total_paid_amount']").value = item.total_paid_amount || "";
    form.querySelector("[name='expected_amount']").value = item.expected_amount || "";

    const isMonthlyPension = item.payout_type === "monthly_pension" || (Number(item.monthly_payout) || 0) > 0 || item.insurance_type === "national_pension";
    if (isMonthlyPension) {
      if ($("#payoutTypeMonthlyPension")) $("#payoutTypeMonthlyPension").checked = true;
      if ($("#pensionMonthlyPayout")) $("#pensionMonthlyPayout").value = item.monthly_payout || "";
      if ($("#pensionDurationSelect")) $("#pensionDurationSelect").value = String(item.payout_duration_years || 20);
    } else {
      if ($("#payoutTypeLumpSum")) $("#payoutTypeLumpSum").checked = true;
    }

    form.querySelector("[name='start_date']").value = item.start_date || "";
    form.querySelector("[name='maturity_date']").value = item.maturity_date || "";
    form.querySelector("[name='memo']").value = item.memo || "";

    yuCurrentYearlyList = Array.isArray(item.yearly_contributions)
      ? JSON.parse(JSON.stringify(item.yearly_contributions))
      : [];
  } else {
    form.querySelector("[name='owner']").value = currentOwner !== "모두" ? currentOwner : "모두";
    if ($("#payoutTypeLumpSum")) $("#payoutTypeLumpSum").checked = true;
    if ($("#pensionDurationSelect")) $("#pensionDurationSelect").value = "20";
    yuCurrentYearlyList = [];
  }
  updateYellowUmbrellaFields();
  updatePensionPayoutFields();
  renderYuYearlyFormRows(form);
  refreshDialogKoreanHints(dialog);
  dialog.showModal();
}

// ── 4-3. 부동산 (자가 / 임대 / 임차 / 매도) 자산 관리 ──────────────────────────────
let rawRealEstates = [];
let rawSoldRealEstates = [];
let currentRealEstateSubtab = 'all'; // 'all' | 'own' | 'rental' | 'lease' | 'sold'

const PROPERTY_TYPE_LABELS = {
  own: "🏠 자가",
  rental: "🏢 임대",
  lease: "🔑 임차",
  sold: "🏷️ 매도",
};

function renderRealEstate(reList, owner = '모두', soldList = null) {
  rawRealEstates = reList || [];
  
  // 모든 가용 원천에서 매도 부동산 후보군 통합 수집 및 정밀 감지
  const allCandidateRecords = [
    ...(soldList || []),
    ...((rawDashboard && rawDashboard.sold_real_estates) || []),
    ...((rawDashboard && rawDashboard.realized_pnl_records) || []),
    ...((pnlData && pnlData.records) || [])
  ];
  const registeredNames = (rawRealEstates || []).map(r => (r.name || '').trim()).filter(n => n.length >= 2);
  const reKw = /부동산|아파트|오피스텔|빌라|주택|단지|상가|토지|건물|원룸|분양권|재개발/i;

  const map = new Map();
  allCandidateRecords.forEach(r => {
    if (!r || !r.id) return;
    const name = r.name || '';
    const memo = r.memo || '';
    const isRe = r.asset_type === 'real_estate' || r.code === 'REAL_ESTATE' || r.broker === '부동산' ||
      name.includes('[부동산]') || name.includes('부동산') ||
      registeredNames.some(rn => name.includes(rn)) ||
      reKw.test(name) || (memo && reKw.test(memo) && r.asset_type !== 'stock');
    if (isRe) {
      map.set(r.id, r);
    }
  });
  rawSoldRealEstates = Array.from(map.values()).sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  renderRealEstateWithOwner(owner);
}

function renderRealEstateWithOwner(owner = '모두') {
  const o = owner || currentOwner || '모두';
  const filtered = [];

  rawRealEstates.forEach(r => {
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
    const clone = Object.assign({}, r, { _shareRatio: share });
    filtered.push(clone);
  });

  // 매도 부동산 목록 소유자 필터링
  const filteredSold = [];
  rawSoldRealEstates.forEach(s => {
    let share = 1.0;
    if (o !== '모두') {
      const ownerships = (s.ownerships && s.ownerships.length)
        ? s.ownerships
        : [{ owner: s.owner || '모두', ratio: 100 }];
      let matched = ownerships.find(x => x.owner === o);
      if (!matched && s.owner && s.owner.includes(o)) {
        const m = s.owner.match(new RegExp(`${o}\\s*([0-9.]+)%`));
        if (m) {
          share = parseFloat(m[1]) / 100;
        } else {
          share = 0.5;
        }
      } else if (matched && matched.ratio > 0) {
        share = (matched.ratio || 100) / 100;
      } else if (s.owner === o) {
        share = 1.0;
      } else {
        return;
      }
    }
    const clone = Object.assign({}, s, { _shareRatio: share });
    filteredSold.push(clone);
  });

  const ownList = filtered.filter(r => (r.property_type || 'own') === 'own');
  const rentalList = filtered.filter(r => r.property_type === 'rental');
  const leaseList = filtered.filter(r => r.property_type === 'lease');

  const totalREVal = ownList.concat(rentalList).reduce((sum, r) => sum + ((Number(r.current_price) || 0) * (r._shareRatio || 1.0)), 0);
  const totalPurchaseVal = ownList.concat(rentalList).reduce((sum, r) => sum + ((Number(r.purchase_price) || 0) * (r._shareRatio || 1.0)), 0);
  const totalProfit = totalPurchaseVal > 0 ? (totalREVal - totalPurchaseVal) : 0;
  const totalProfitRate = totalPurchaseVal > 0 ? ((totalProfit / totalPurchaseVal) * 100).toFixed(1) : "0.0";

  const totalTenantDeposit = leaseList.reduce((sum, r) => sum + ((Number(r.deposit_amount) || 0) * (r._shareRatio || 1.0)), 0);
  const totalLandlordDeposit = rentalList.reduce((sum, r) => sum + ((Number(r.deposit_amount) || 0) * (r._shareRatio || 1.0)), 0);
  
  let totalLinkedLoanBalance = 0;
  const loanMap = new Map();
  rawLoanAccounts.forEach(l => loanMap.set(l.id, l));

  filtered.forEach(r => {
    (r.linked_loan_ids || []).forEach(lid => {
      const l = loanMap.get(lid);
      if (l) totalLinkedLoanBalance += ((Number(l.current_balance) || 0) * (r._shareRatio || 1.0));
    });
  });

  const totalREDebt = totalLandlordDeposit + totalLinkedLoanBalance;

  // 매도 부동산 총 실현손익, 양도가, 취득가 계산
  const totalSoldPnl = filteredSold.reduce((sum, s) => sum + ((Number(s.pnl_krw != null ? s.pnl_krw : s.pnl) || 0) * (s._shareRatio || 1.0)), 0);
  const totalSoldPurch = filteredSold.reduce((sum, s) => sum + ((Number(s.purchase_price) || 0) * (s._shareRatio || 1.0)), 0);
  const totalSoldSell = filteredSold.reduce((sum, s) => sum + ((Number(s.sell_price) || 0) * (s._shareRatio || 1.0)), 0);
  const soldProfitRate = totalSoldPurch > 0 ? ((totalSoldPnl / totalSoldPurch) * 100).toFixed(1) : "0.0";

  if ($("#totalRealEstateVal")) $("#totalRealEstateVal").textContent = `₩${number(totalREVal, 0)}`;
  if ($("#totalRealEstateCountSub")) {
    const isShare = o !== '모두' ? ` (${o} 지분 반영)` : '';
    $("#totalRealEstateCountSub").textContent = `보유: ${ownList.length + rentalList.length}건 (자가 ${ownList.length} · 임대 ${rentalList.length})${isShare}`;
  }
  if ($("#totalPurchaseVal")) $("#totalPurchaseVal").textContent = `₩${number(totalPurchaseVal, 0)}`;
  if ($("#totalTenantDepositSub")) {
    $("#totalTenantDepositSub").textContent = `임차 전세보증금: ₩${number(totalTenantDeposit, 0)}`;
  }
  if ($("#totalRealEstateProfitVal")) {
    const pSign = totalProfit >= 0 ? "+" : "";
    $("#totalRealEstateProfitVal").textContent = `${pSign}₩${number(totalProfit, 0)}`;
    $("#totalRealEstateProfitVal").style.color = totalProfit >= 0 ? "#42d5a3" : "#f43f5e";
  }
  if ($("#totalRealEstateRateSub")) {
    const rSign = Number(totalProfitRate) >= 0 ? "+" : "";
    $("#totalRealEstateRateSub").textContent = `수익률: ${rSign}${totalProfitRate}%`;
  }
  if ($("#totalRealEstateDebtVal")) $("#totalRealEstateDebtVal").textContent = `₩${number(totalREDebt, 0)}`;
  if ($("#totalRealEstateDebtSub")) {
    $("#totalRealEstateDebtSub").textContent = `담보·전세대출: ₩${number(totalLinkedLoanBalance, 0)} · 임대보증금: ₩${number(totalLandlordDeposit, 0)}`;
  }

  // 🏷️ 상단 5번째 요약 카드: 부동산 실현손익
  if ($("#totalRealEstateRealizedVal")) {
    const sSign = totalSoldPnl >= 0 ? "+" : "";
    $("#totalRealEstateRealizedVal").textContent = `${sSign}₩${number(totalSoldPnl, 0)}`;
    $("#totalRealEstateRealizedVal").style.color = totalSoldPnl > 0 ? "#42d5a3" : (totalSoldPnl < 0 ? "#f43f5e" : "#f59e0b");
  }
  if ($("#totalRealEstateRealizedSub")) {
    const rateText = totalSoldPurch > 0 ? ` (수익률: ${Number(soldProfitRate) >= 0 ? '+' : ''}${soldProfitRate}%)` : '';
    $("#totalRealEstateRealizedSub").textContent = `매도: ${filteredSold.length}건${rateText}`;
  }

  // 5개 서브탭 카운트 업데이트
  if ($("#reAllCount")) $("#reAllCount").textContent = filtered.length;
  if ($("#reOwnCount")) $("#reOwnCount").textContent = ownList.length;
  if ($("#reRentalCount")) $("#reRentalCount").textContent = rentalList.length;
  if ($("#reLeaseCount")) $("#reLeaseCount").textContent = leaseList.length;
  if ($("#reSoldCount")) $("#reSoldCount").textContent = filteredSold.length;
  if ($("#realEstateTabCount")) $("#realEstateTabCount").textContent = filtered.length;

  // 매도 탭 활성화 시 [➕ 매도 기록 추가] 버튼 노출
  const directBtn = $("#btnDirectAddSoldRe");
  if (directBtn) {
    directBtn.style.display = currentRealEstateSubtab === 'sold' ? 'inline-flex' : 'none';
  }

  let displayList = filtered;
  if (currentRealEstateSubtab === 'own') {
    displayList = ownList;
  } else if (currentRealEstateSubtab === 'rental') {
    displayList = rentalList;
  } else if (currentRealEstateSubtab === 'lease') {
    displayList = leaseList;
  } else if (currentRealEstateSubtab === 'sold') {
    displayList = filteredSold;
  }

  const grid = $("#realEstateGrid");
  if (!grid) return;

  if (currentRealEstateSubtab === 'sold') {
    if (!filteredSold.length) {
      grid.innerHTML = `
        <div class="empty" style="grid-column:1/-1;padding:32px 16px;text-align:center;">
          <p style="font-size:15px;color:#f8fafc;font-weight:700;margin-bottom:6px;">🏷️ 기록된 부동산 매도 내역이 없습니다.</p>
          <p style="font-size:12px;color:#94a3b8;margin-bottom:14px;">보유 부동산 카드의 [🏢] 버튼을 누르거나, 우측 상단의 [➕ 매도 기록 추가] 버튼으로 등록할 수 있습니다.</p>
          <button type="button" class="button secondary compact" onclick="openDirectAddSoldReDialog()" style="font-size:12px;color:#f59e0b;border-color:rgba(245,158,11,0.4);">➕ 매도 기록 직접 추가</button>
        </div>
      `;
      return;
    }

    grid.innerHTML = filteredSold.map(sold => {
      const shareRatio = sold._shareRatio || 1.0;
      const isPartial = shareRatio < 0.999;
      const rawPurch = Number(sold.purchase_price) || 0;
      const rawSell = Number(sold.sell_price) || 0;
      const rawExp = Number(sold.expenses) || 0;
      const rawPnl = Number(sold.pnl_krw != null ? sold.pnl_krw : sold.pnl) || 0;

      const purch = isPartial ? rawPurch * shareRatio : rawPurch;
      const sell = isPartial ? rawSell * shareRatio : rawSell;
      const exp = isPartial ? rawExp * shareRatio : rawExp;
      const pnl = isPartial ? rawPnl * shareRatio : rawPnl;

      const profitSign = pnl >= 0 ? "+" : "";
      const profitColor = pnl > 0 ? "#42d5a3" : (pnl < 0 ? "#f43f5e" : "#94a3b8");
      const profitRate = purch > 0 ? ((pnl / purch) * 100).toFixed(1) : null;

      const titleName = sold.clean_name || (sold.name || '부동산').replace('[부동산]', '').trim() || '부동산 매도';
      const ownerBadgeText = sold.is_joint_ownership
        ? (isPartial ? `🤝 ${o} ${(shareRatio * 100).toFixed(0)}% (공동명의)` : `🤝 ${sold.owner}`)
        : (sold.owner || '모두');

      return `
        <div class="saving-card real-estate-card badge-sold">
          <div class="saving-card-header">
            <div class="saving-card-title-group">
              <div class="saving-badge-row">
                <span class="saving-type-badge badge-sold" style="background:rgba(245,158,11,0.18);color:#f59e0b;border:1px solid rgba(245,158,11,0.35);font-weight:700;">🏷️ 매도 완료</span>
                <span class="saving-owner-badge" title="${html(sold.owner || '')}">${html(ownerBadgeText)}</span>
                <span class="d-day-badge">📅 매도일: ${html(sold.date || '-')}</span>
              </div>
              <h3 class="saving-product-name" style="font-size:15px;margin-top:2px;">${html(titleName)}</h3>
              <span class="saving-bank-name">${html(sold.address || sold.memo || '-')}</span>
            </div>
            <div class="account-row-actions saving-card-actions">
              <button class="account-action-button" data-sold-re-edit="${sold.id}" title="매도 기록 수정" type="button" style="color:#38bdf8;font-size:13px;">✎</button>
              <button class="mini-delete-button" data-sold-re-del="${sold.id}" title="매도 기록 삭제" type="button" style="color:#f43f5e;font-size:13px;">🗑️</button>
            </div>
          </div>

          <div class="saving-card-details">
            <div class="saving-detail-row">
              <span class="saving-detail-label">취득가 (매수가)</span>
              <span class="saving-detail-val">${purch > 0 ? `₩${number(purch, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawPurch, 0)})</small>` : ''}` : '-'}</span>
            </div>
            <div class="saving-detail-row">
              <span class="saving-detail-label">양도가 (매도가)</span>
              <span class="saving-detail-val" style="color:#38bdf8;font-size:13px;font-weight:700;">${sell > 0 ? `₩${number(sell, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawSell, 0)})</small>` : ''}` : '-'}</span>
            </div>
            ${exp > 0 ? `
              <div class="saving-detail-row">
                <span class="saving-detail-label">필요경비 (공제)</span>
                <span class="saving-detail-val" style="color:#fb7185;">-₩${number(exp, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawExp, 0)})</small>` : ''}</span>
              </div>
            ` : ''}
            <div class="saving-detail-row sold-profit-row" style="grid-column:1/-1;padding:8px 10px;border-radius:8px;margin-top:2px;">
              <span class="saving-detail-label" style="font-weight:700;">실현손익 (양도차익)</span>
              <span class="saving-detail-val" style="color:${profitColor};font-size:14px;font-weight:800;">
                ${profitSign}₩${number(pnl, 0)} ${profitRate != null ? `(${profitSign}${profitRate}%)` : ''}
              </span>
            </div>
            ${sold.memo ? `
              <div class="saving-detail-row" style="grid-column:1/-1;">
                <span class="saving-detail-label">비고 / 메모</span>
                <span class="saving-detail-val" style="color:#94a3b8;font-size:11.5px;white-space:normal;word-break:break-word;">${html(sold.memo)}</span>
              </div>
            ` : ''}
          </div>
        </div>
      `;
    }).join("");
    return;
  }

  if (!displayList.length) {
    grid.innerHTML = '<div class="empty" style="grid-column:1/-1;">등록된 부동산 자산이 없습니다. 상단 [🏠 부동산 추가] 버튼을 눌러보세요.</div>';
    return;
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  grid.innerHTML = displayList.map(re => {
    const pType = re.property_type || 'own';
    const typeLabel = PROPERTY_TYPE_LABELS[pType] || "부동산";
    const typeBadgeClass = pType === 'own' ? 'badge-own' : (pType === 'rental' ? 'badge-rental' : 'badge-lease');
    const shareRatio = re._shareRatio || 1.0;
    const isPartial = shareRatio < 0.999;

    const rawPurch = Number(re.purchase_price || 0);
    const rawCurr = Number(re.current_price || 0);
    const rawDep = Number(re.deposit_amount || 0);
    const rawRent = Number(re.monthly_rent || 0);

    const purch = isPartial ? rawPurch * shareRatio : rawPurch;
    const curr = isPartial ? rawCurr * shareRatio : rawCurr;
    const dep = isPartial ? rawDep * shareRatio : rawDep;
    const rent = isPartial ? rawRent * shareRatio : rawRent;

    const profit = (pType !== 'lease' && purch > 0) ? (curr - purch) : 0;
    const profitRate = (pType !== 'lease' && purch > 0) ? ((profit / purch) * 100).toFixed(1) : "0.0";
    const profitSign = profit >= 0 ? "+" : "";
    const profitColor = profit >= 0 ? "#42d5a3" : "#f43f5e";

    let dDayText = "";
    if (re.expiry_date) {
      try {
        const expDt = new Date(re.expiry_date.substring(0, 10));
        const diffDays = Math.round((expDt - today) / (1000 * 60 * 60 * 24));
        dDayText = diffDays <= 0 ? "만기 경과" : `만기 D-${diffDays}`;
      } catch (e) {}
    }

    const connectedLoanItems = (re.linked_loan_ids || []).map(lid => loanMap.get(lid)).filter(Boolean);
    const linkedLoanTotalBal = connectedLoanItems.reduce((acc, l) => acc + Number(l.current_balance || 0) * shareRatio, 0);
    const linkedLoanTotalInterest = connectedLoanItems.reduce((acc, l) => acc + (Number(l.monthly_interest) || Number(l.calc?.monthly_interest) || 0) * shareRatio, 0);

    let netEquity = 0;
    if (pType === 'own') {
      netEquity = curr - linkedLoanTotalBal;
    } else if (pType === 'rental') {
      netEquity = curr - (dep + linkedLoanTotalBal);
    } else {
      netEquity = dep - linkedLoanTotalBal;
    }

    const pyungText = re.exclusive_area > 0 ? ` (약 ${(re.exclusive_area / 3.3058).toFixed(1)}평)` : '';

    // 네이버 부동산 검색 링크: 동·호수를 제외한 깨끗한 단지명으로 검색
    const cleanSearchKeyword = (re.name || '').replace(/\s*\d+[-~_동호].*$/i, '').trim() || re.name || re.address || '';
    const naverLandUrl = `https://m.land.naver.com/search/result/${encodeURIComponent(cleanSearchKeyword)}`;

    // 카드 타이틀에 동·호수 결합 표시
    const titleHtml = re.dong_ho 
      ? `${html(re.name)} <span style="font-size:12.5px;font-weight:normal;opacity:0.85;">(${html(re.dong_ho)})</span>`
      : html(re.name);

    // 소유자 배지 라벨
    const ownerBadgeText = re.is_joint_ownership 
      ? (isPartial ? `🤝 ${o} ${(shareRatio * 100).toFixed(0)}% (공동명의)` : `🤝 ${re.owner}`)
      : (re.owner || '모두');

    return `
      <div class="saving-card real-estate-card ${typeBadgeClass}">
        <div class="saving-card-header">
          <div class="saving-card-title-group">
            <div class="saving-badge-row">
              <span class="saving-type-badge ${typeBadgeClass}">${typeLabel}</span>
              <span class="saving-owner-badge" title="${html(re.owner || '')}">${html(ownerBadgeText)}</span>
              ${dDayText ? `<span class="d-day-badge">${dDayText}</span>` : ''}
            </div>
            <h3 class="saving-product-name">${titleHtml}</h3>
            <span class="saving-bank-name">${html(re.address || '-')}</span>
          </div>
          <div class="account-row-actions saving-card-actions">
            ${pType !== 'lease' ? `<button class="account-action-button" data-re-refresh-kb-id="${re.id}" title="KB부동산 공식 시세로 즉시 갱신" type="button" style="color:#facc15;font-size:12px;">🔄</button>` : ''}
            <a href="${naverLandUrl}" target="_blank" rel="noopener" class="account-action-button" title="네이버 부동산 '${cleanSearchKeyword}' 시세 확인" style="text-decoration:none;display:inline-flex;align-items:center;font-size:12px;">🔍</a>
            ${pType !== 'lease' ? `<button class="account-action-button" data-re-sell-id="${re.id}" title="부동산 매각 및 실현손익 기록" type="button" style="color:#f59e0b;font-size:12px;">🏢</button>` : ''}
            <button class="account-action-button" data-re-edit-id="${re.id}" title="수정" type="button">✎</button>
            <button class="mini-delete-button" data-re-del-id="${re.id}" title="삭제" type="button">🗑️</button>
          </div>
        </div>

        <div class="saving-card-details">
          ${pType !== 'lease' ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">${isPartial ? `${o} 매수가` : '매수가 (취득가)'}</span>
              <span class="saving-detail-val">₩${number(purch, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawPurch, 0)})</small>` : ''}</span>
            </div>
            <div class="saving-detail-row">
              <span class="saving-detail-label">${isPartial ? `${o} 현재 시세` : '현재 시세'}</span>
              <span class="saving-detail-val" style="color:#38bdf8;font-size:13px;">₩${number(curr, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawCurr, 0)})</small>` : ''}</span>
            </div>
            <div class="saving-detail-row" style="grid-column:1/-1;">
              <span class="saving-detail-label">시세 차익 (수익률)</span>
              <span class="saving-detail-val" style="color:${profitColor};font-weight:700;">${profitSign}₩${number(profit, 0)} (${profitSign}${profitRate}%)</span>
            </div>
          ` : `
            <div class="saving-detail-row">
              <span class="saving-detail-label">${isPartial ? `${o} 임차 보증금` : '임차 전세보증금'}</span>
              <span class="saving-detail-val" style="color:#38bdf8;font-size:13px;">₩${number(dep, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawDep, 0)})</small>` : ''}</span>
            </div>
            ${rent > 0 ? `
              <div class="saving-detail-row">
                <span class="saving-detail-label">월세 지출</span>
                <span class="saving-detail-val" style="color:#fb7185;">-₩${number(rent, 0)}</span>
              </div>
            ` : '<div class="saving-detail-row"><span class="saving-detail-label">계약 형태</span><span class="saving-detail-val">올전세</span></div>'}
          `}

          ${pType === 'rental' ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">${isPartial ? `${o} 임대 전세금` : '임대 전세금 (부채)'}</span>
              <span class="saving-detail-val" style="color:#fb7185;font-weight:700;">-₩${number(dep, 0)} ${isPartial ? `<small style="font-size:10px;color:#94a3b8;">(전체 ₩${number(rawDep, 0)})</small>` : ''}</span>
            </div>
            ${rent > 0 ? `
              <div class="saving-detail-row">
                <span class="saving-detail-label">월세 수입</span>
                <span class="saving-detail-val" style="color:#42d5a3;font-weight:700;">+₩${number(rent, 0)}</span>
              </div>
            ` : '<div class="saving-detail-row"><span class="saving-detail-label">임대 형태</span><span class="saving-detail-val">전세 임대</span></div>'}
          ` : ''}

          ${re.exclusive_area > 0 ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">전용면적</span>
              <span class="saving-detail-val">${re.exclusive_area}㎡${pyungText}</span>
            </div>
          ` : ''}

          ${re.contract_date ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">취득/계약일</span>
              <span class="saving-detail-val">${html(re.contract_date)}</span>
            </div>
          ` : ''}

          ${re.expiry_date ? `
            <div class="saving-detail-row">
              <span class="saving-detail-label">만기일</span>
              <span class="saving-detail-val">${html(re.expiry_date)}</span>
            </div>
          ` : ''}

          ${connectedLoanItems.length > 0 ? `
            <div class="saving-detail-row" style="grid-column:1/-1;background:rgba(244,63,94,0.06);padding:6px 8px;border-radius:6px;margin-top:2px;">
              <span class="saving-detail-label" style="color:#fb7185;">연결 대출 (${connectedLoanItems.length}건)</span>
              <span class="saving-detail-val" style="color:#fb7185;font-size:12px;">잔액: -₩${number(linkedLoanTotalBal, 0)} (월이자: ₩${number(linkedLoanTotalInterest, 0)})</span>
            </div>
          ` : ''}

          ${re.memo ? `
            <div class="saving-detail-row" style="grid-column:1/-1;">
              <span class="saving-detail-label">메모</span>
              <span class="saving-detail-val" style="color:#94a3b8;font-size:11px;">${html(re.memo)}</span>
            </div>
          ` : ''}

          ${pType !== 'lease' ? `
            <div style="grid-column:1/-1;margin-top:8px;padding-top:8px;border-top:1px dashed rgba(255,255,255,0.08);display:flex;justify-content:flex-end;">
              <button class="button secondary compact" data-re-sell-id="${re.id}" type="button" style="font-size:11px;padding:4px 10px;color:#f59e0b;border-color:rgba(245,158,11,0.4);background:rgba(245,158,11,0.08);font-weight:600;">
                🏢 매각/실현손익 기록
              </button>
            </div>
          ` : ''}
        </div>

        <div class="saving-interest-box" style="background:rgba(59,130,246,0.08);border-color:rgba(59,130,246,0.25);">
          <div class="saving-interest-row maturity-row" style="padding-top:0;border-top:none;">
            <span style="color:#93c5fd;font-weight:600;">${isPartial ? `${o} 순에퀴티(순자산)` : '부동산 순에퀴티(순자산)'}</span>
            <span style="color:#60a5fa;font-size:15px;font-weight:700;">₩${number(netEquity, 0)}</span>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

function calcRealEstatePreview() {
  const pType = $("#reTypeSelect")?.value || "own";
  const purch = Number($("#rePurchasePrice")?.value || 0);
  const curr = Number($("#reCurrentPrice")?.value || 0);
  const dep = Number($("#reDepositAmount")?.value || 0);

  const selectedLoanId = $("#reLinkedLoansSelect")?.value || "";
  let loanBal = 0;
  if (selectedLoanId) {
    const l = rawLoanAccounts.find(x => x.id === selectedLoanId);
    if (l) loanBal = Number(l.current_balance || 0);
  }

  let netEquity = 0;
  let profit = 0;
  let profitRate = "0.0";

  if (pType === 'own') {
    netEquity = curr - loanBal;
    if (purch > 0) {
      profit = curr - purch;
      profitRate = ((profit / purch) * 100).toFixed(1);
    }
  } else if (pType === 'rental') {
    netEquity = curr - (dep + loanBal);
    if (purch > 0) {
      profit = curr - purch;
      profitRate = ((profit / purch) * 100).toFixed(1);
    }
  } else {
    netEquity = dep - loanBal;
  }

  if ($("#rePreviewEquity")) $("#rePreviewEquity").textContent = `₩${number(netEquity, 0)}`;
  if ($("#rePreviewProfitWrap")) {
    $("#rePreviewProfitWrap").style.display = pType !== 'lease' ? "block" : "none";
    if (pType !== 'lease') {
      const pSign = profit >= 0 ? "+" : "";
      if ($("#rePreviewProfit")) {
        $("#rePreviewProfit").textContent = `${pSign}₩${number(profit, 0)} (${pSign}${profitRate}%)`;
        $("#rePreviewProfit").style.color = profit >= 0 ? "#42d5a3" : "#f43f5e";
      }
    }
  }
}

function updateRealEstateTypeFields() {
  const pType = $("#reTypeSelect")?.value || "own";
  const isLease = pType === "lease";
  const isRental = pType === "rental";

  const purchLabel = $("#rePurchasePriceLabel");
  const currLabel = $("#reCurrentPriceLabel");
  const depLabel = $("#reDepositLabel");
  const rentLabel = $("#reMonthlyRentLabel");
  const depHint = $("#reDepositHint");

  if (purchLabel) purchLabel.style.display = isLease ? "none" : "";
  if (currLabel) currLabel.style.display = isLease ? "none" : "";
  if (depLabel) depLabel.style.display = (isRental || isLease) ? "" : "none";
  if (rentLabel) rentLabel.style.display = (isRental || isLease) ? "" : "none";

  if (depHint) {
    depHint.textContent = isRental ? "세입자에게 받은 전세보증금 (추후 상환할 부채)" : "집주인에게 맡긴 전세보증금 (만기 시 돌려받을 내 자산)";
  }

  calcRealEstatePreview();
}

function renderJointOwnershipRows(ownerships = []) {
  const container = $("#reJointRows");
  if (!container) return;
  const members = (typeof familyMembers !== 'undefined' && familyMembers && familyMembers.length) 
    ? familyMembers 
    : ['아빠', '엄마', '자녀'];

  const rows = (ownerships && ownerships.length) ? ownerships : [
    { owner: members[0] || '아빠', ratio: 50 },
    { owner: members[1] || '엄마', ratio: 50 }
  ];

  container.innerHTML = rows.map(r => `
    <div class="re-joint-row" style="display:flex;align-items:center;gap:8px;">
      <select class="re-joint-owner-select" style="flex:1;">
        ${members.map(m => `<option value="${m}" ${m === r.owner ? 'selected' : ''}>${m}</option>`).join('')}
      </select>
      <div style="display:flex;align-items:center;gap:4px;width:110px;">
        <input type="number" class="re-joint-ratio-input" value="${r.ratio}" min="1" max="100" step="1" style="width:70px;text-align:right;" />
        <span style="font-size:12px;color:#94a3b8;">%</span>
      </div>
      <button type="button" class="mini-delete-button re-joint-del-btn" title="삭제" style="padding:2px 6px;">×</button>
    </div>
  `).join('');

  updateJointTotalRatio();
}

function updateJointTotalRatio() {
  const inputs = document.querySelectorAll('.re-joint-ratio-input');
  let sum = 0;
  inputs.forEach(inp => sum += Number(inp.value || 0));
  const totalEl = $("#reJointTotalRatio");
  if (totalEl) {
    totalEl.textContent = `지분율 합계: ${sum}%`;
    totalEl.style.color = sum === 100 ? "#38bdf8" : "#fb7185";
  }
}

function openRealEstateDialog(reItem = null) {
  const dialog = $("#realEstateDialog");
  const form = $("#realEstateForm");
  if (!dialog || !form) return;
  form.reset();
  form.querySelector("[name='id']").value = reItem ? reItem.id : "";

  if ($("#realEstateDialogTitle")) {
    $("#realEstateDialogTitle").textContent = reItem ? "부동산 자산 수정" : "부동산 자산 추가";
  }

  const loanSelect = $("#reLinkedLoansSelect");
  if (loanSelect) {
    let opts = '<option value="">-- 연결 대출 없음 --</option>';
    rawLoanAccounts.forEach(l => {
      const typeStr = LOAN_TYPE_LABELS[l.loan_type] || "대출";
      opts += `<option value="${l.id}">${l.bank_name} - ${l.product_name} (${typeStr}, 잔액 ₩${number(l.current_balance, 0)})</option>`;
    });
    loanSelect.innerHTML = opts;
  }

  const isJoint = Boolean(reItem?.is_joint_ownership);
  const jointCheck = $("#reIsJointCheck");
  if (jointCheck) jointCheck.checked = isJoint;

  const singleWrap = $("#reSingleOwnerWrap");
  const jointWrap = $("#reJointOwnershipWrap");
  if (singleWrap) singleWrap.style.display = isJoint ? "none" : "block";
  if (jointWrap) jointWrap.style.display = isJoint ? "block" : "none";

  renderJointOwnershipRows(reItem?.ownerships || []);

  if (reItem) {
    form.querySelector("[name='property_type']").value = reItem.property_type || "own";
    form.querySelector("[name='owner']").value = reItem.ownerships?.[0]?.owner || reItem.owner || "모두";
    form.querySelector("[name='name']").value = reItem.name || "";
    form.querySelector("[name='dong_ho']").value = reItem.dong_ho || "";
    form.querySelector("[name='address']").value = reItem.address || "";
    form.querySelector("[name='purchase_price']").value = reItem.purchase_price || "";
    form.querySelector("[name='current_price']").value = reItem.current_price || "";
    form.querySelector("[name='deposit_amount']").value = reItem.deposit_amount || "";
    form.querySelector("[name='monthly_rent']").value = reItem.monthly_rent || "";
    form.querySelector("[name='contract_date']").value = reItem.contract_date || "";
    form.querySelector("[name='expiry_date']").value = reItem.expiry_date || "";
    form.querySelector("[name='exclusive_area']").value = reItem.exclusive_area || "";
    form.querySelector("[name='memo']").value = reItem.memo || "";
    form.querySelector("[name='kb_complex_no']").value = reItem.kb_complex_no || "";

    const linkedIds = reItem.linked_loan_ids || [];
    if (loanSelect) loanSelect.value = linkedIds[0] || "";
  } else {
    form.querySelector("[name='owner']").value = currentOwner !== "모두" ? currentOwner : "모두";
    form.querySelector("[name='kb_complex_no']").value = "";
  }

  const kbBox = $("#reKbResultBox");
  if (kbBox) kbBox.style.display = "none";

  updateRealEstateTypeFields();
  refreshDialogKoreanHints(dialog);
  dialog.showModal();
}

let currentKbTypes = [];

async function fetchKbMarketPrice() {
  const nameInput = $("#reNameInput");
  const areaInput = $("#reExclusiveArea");
  const complexNoInput = $("#reKbComplexNo");
  const btn = $("#reFetchKbBtn");
  const resultBox = $("#reKbResultBox");
  const resultDetail = $("#reKbResultDetail");
  const typeSelectWrap = $("#reKbTypeSelectWrap");
  const typeSelect = $("#reKbTypeSelect");

  const name = (nameInput?.value || "").trim();
  if (!name) {
    alert("단지명(아파트명)을 먼저 입력해 주세요.");
    nameInput?.focus();
    return;
  }

  const area = Number(areaInput?.value || 0);
  const complexNo = (complexNoInput?.value || "").trim();

  if (btn) {
    btn.disabled = true;
    btn.textContent = "⏳ 조회 중...";
  }

  try {
    const res = await api(`/api/real-estates/kb-price?name=${encodeURIComponent(name)}&area=${area}&complex_no=${encodeURIComponent(complexNo)}`);
    if (!res.ok) {
      alert(res.message || "KB시세를 찾을 수 없습니다.");
      return;
    }

    if (complexNoInput) complexNoInput.value = res.complex_no;
    currentKbTypes = res.types || [];

    const matched = res.matched;
    if (resultBox) resultBox.style.display = "block";

    if (matched) {
      if (resultDetail) {
        resultDetail.innerHTML = `
          <strong>단지</strong>: ${html(res.complex_info?.name || name)} 
          <span style="color:#facc15;">[${html(matched.type_display)}]</span><br/>
          <strong>KB 매매 일반평균가</strong>: <span style="font-size:13px;font-weight:700;color:#38bdf8;">₩${number(matched.deal_avg, 0)}</span><br/>
          <small style="color:#94a3b8;">하한가 ₩${number(matched.deal_low, 0)} ~ 상한가 ₩${number(matched.deal_high, 0)} · 전세 ₩${number(matched.lease_avg, 0)}</small>
        `;
      }
      // 현재 시세에 자동 적용
      const currInput = $("#reCurrentPrice");
      if (currInput && (!currInput.value || Number(currInput.value) === 0 || confirm(`조회된 KB 일반평균가(₩${number(matched.deal_avg, 0)})를 현재 시세에 적용할까요?`))) {
        currInput.value = matched.deal_avg;
        updateKoreanCurrencyHint(currInput);
        calcRealEstatePreview();
      }
    }

    // 평형 선택 드롭다운 구성
    if (typeSelect && currentKbTypes.length > 1) {
      typeSelect.innerHTML = currentKbTypes.map((t, idx) => `
        <option value="${idx}" ${t === matched ? 'selected' : ''}>
          ${t.type_display} - 일반가 ₩${number(t.deal_avg, 0)}
        </option>
      `).join('');
      if (typeSelectWrap) typeSelectWrap.style.display = "block";
    } else if (typeSelectWrap) {
      typeSelectWrap.style.display = "none";
    }

  } catch (err) {
    alert("KB시세 조회 실패: " + (err.message || err));
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "🔍 KB시세 조회";
    }
  }
}

// ── 부동산 매각 및 실현손익 기록 다이얼로그 제어 ─────────────────────────
function openRealEstateSellDialog(reItem, editPnlItem = null) {
  const dlg = document.getElementById("realEstateSellDialog");
  if (!dlg) return;

  const titleEl = document.getElementById("reSellDialogTitle");
  const targetIdEl = document.getElementById("reSellTargetId");
  const editPnlIdEl = document.getElementById("reSellEditPnlId");
  const nameEl = document.getElementById("reSellName");
  const addressEl = document.getElementById("reSellAddress");
  const ownerEl = document.getElementById("reSellOwner");
  const dateEl = document.getElementById("reSellDate");
  const purchEl = document.getElementById("reSellPurchasePrice");
  const priceEl = document.getElementById("reSellPrice");
  const expEl = document.getElementById("reSellExpenses");
  const memoEl = document.getElementById("reSellMemo");
  const removeEl = document.getElementById("reSellRemoveFromAssets");
  const removeWrap = document.getElementById("reSellRemoveFromAssetsWrap");
  const submitBtn = document.getElementById("reSellSubmitBtn");

  // 가족 소유자 목록 옵션 갱신
  if (ownerEl) {
    const familyMembers = (rawDashboard && rawDashboard.family_members) || ['아빠', '엄마'];
    const opts = ['모두', ...familyMembers];
    ownerEl.innerHTML = Array.from(new Set(opts)).map(m => `<option value="${m}">${m}</option>`).join('');
  }

  if (editPnlItem) {
    // 1) 기존 매도 기록 수정 모드
    if (titleEl) titleEl.textContent = "🏢 부동산 매도 기록 수정";
    if (submitBtn) submitBtn.textContent = "매도 기록 수정 완료";
    if (targetIdEl) targetIdEl.value = "";
    if (editPnlIdEl) editPnlIdEl.value = editPnlItem.id || "";
    if (nameEl) {
      nameEl.value = editPnlItem.clean_name || (editPnlItem.name || '').replace('[부동산]', '').trim() || "";
      nameEl.readOnly = false;
      nameEl.style.background = "";
      nameEl.style.color = "";
    }
    if (addressEl) addressEl.value = editPnlItem.address || "";
    if (ownerEl) ownerEl.value = editPnlItem.owner || "모두";
    if (dateEl) dateEl.value = editPnlItem.date || new Date().toISOString().slice(0, 10);
    if (purchEl) {
      purchEl.value = editPnlItem.purchase_price || 0;
      purchEl.readOnly = false;
      purchEl.style.background = "";
      purchEl.style.color = "";
    }
    if (priceEl) priceEl.value = editPnlItem.sell_price || 0;
    if (expEl) expEl.value = editPnlItem.expenses || 0;
    if (memoEl) memoEl.value = editPnlItem.memo || "";
    if (removeWrap) removeWrap.style.display = "none";
  } else if (reItem) {
    // 2) 보유 부동산 매각 모드
    if (titleEl) titleEl.textContent = "🏢 부동산 매각 및 실현손익 기록";
    if (submitBtn) submitBtn.textContent = "실현손익에 기록";
    if (targetIdEl) targetIdEl.value = reItem.id || "";
    if (editPnlIdEl) editPnlIdEl.value = "";
    if (nameEl) {
      nameEl.value = reItem.name || "부동산";
      nameEl.readOnly = true;
      nameEl.style.background = "rgba(255,255,255,0.05)";
      nameEl.style.color = "#94a3b8";
    }
    if (addressEl) addressEl.value = reItem.address || "";
    if (ownerEl) ownerEl.value = reItem.owner || "모두";
    if (dateEl) dateEl.value = new Date().toISOString().slice(0, 10);
    if (purchEl) {
      purchEl.value = reItem.purchase_price || 0;
      purchEl.readOnly = true;
      purchEl.style.background = "rgba(255,255,255,0.05)";
      purchEl.style.color = "#94a3b8";
    }
    if (priceEl) priceEl.value = reItem.current_price || reItem.purchase_price || "";
    if (expEl) expEl.value = 0;
    if (memoEl) memoEl.value = "";
    if (removeWrap) removeWrap.style.display = "block";
    if (removeEl) removeEl.checked = true;
  } else {
    // 3) 직접 매도 기록 추가 모드
    if (titleEl) titleEl.textContent = "🏢 부동산 매도 기록 직접 추가";
    if (submitBtn) submitBtn.textContent = "매도 기록 등록";
    if (targetIdEl) targetIdEl.value = "direct";
    if (editPnlIdEl) editPnlIdEl.value = "";
    if (nameEl) {
      nameEl.value = "";
      nameEl.readOnly = false;
      nameEl.style.background = "";
      nameEl.style.color = "";
    }
    if (addressEl) addressEl.value = "";
    if (ownerEl) ownerEl.value = currentOwner || "모두";
    if (dateEl) dateEl.value = new Date().toISOString().slice(0, 10);
    if (purchEl) {
      purchEl.value = "";
      purchEl.readOnly = false;
      purchEl.style.background = "";
      purchEl.style.color = "";
    }
    if (priceEl) priceEl.value = "";
    if (expEl) expEl.value = 0;
    if (memoEl) memoEl.value = "";
    if (removeWrap) removeWrap.style.display = "none";
  }

  // 한글 통화 힌트 업데이트
  if (purchEl && typeof updateKoreanCurrencyHint === 'function') updateKoreanCurrencyHint(purchEl);
  if (priceEl && typeof updateKoreanCurrencyHint === 'function') updateKoreanCurrencyHint(priceEl);
  if (expEl && typeof updateKoreanCurrencyHint === 'function') updateKoreanCurrencyHint(expEl);

  calcRealEstateSellProfit();
  dlg.showModal();
}
window.openRealEstateSellDialog = openRealEstateSellDialog;

function openDirectAddSoldReDialog() {
  openRealEstateSellDialog(null, null);
}
window.openDirectAddSoldReDialog = openDirectAddSoldReDialog;

function calcRealEstateSellProfit() {
  const purch = Number(document.getElementById("reSellPurchasePrice")?.value || 0);
  const sell = Number(document.getElementById("reSellPrice")?.value || 0);
  const exp = Number(document.getElementById("reSellExpenses")?.value || 0);
  const pnl = sell - purch - exp;

  const pnlEl = document.getElementById("reSellPnlPreview");
  const formulaEl = document.getElementById("reSellCalcFormula");

  if (pnlEl) {
    const sign = pnl >= 0 ? "+" : "";
    pnlEl.textContent = `${sign}₩${number(pnl, 0)}`;
    pnlEl.style.color = pnl > 0 ? "#42d5a3" : (pnl < 0 ? "#f43f5e" : "#38bdf8");
  }
  if (formulaEl) {
    formulaEl.textContent = `양도가 ₩${number(sell, 0)} - 취득가 ₩${number(purch, 0)} - 필요경비 ₩${number(exp, 0)}`;
  }
}
window.calcRealEstateSellProfit = calcRealEstateSellProfit;

async function submitRealEstateSell() {
  const reId = document.getElementById("reSellTargetId")?.value;
  const editPnlId = document.getElementById("reSellEditPnlId")?.value;

  const name = document.getElementById("reSellName")?.value?.trim() || "부동산";
  const address = document.getElementById("reSellAddress")?.value?.trim() || "";
  const owner = document.getElementById("reSellOwner")?.value || "모두";
  const sellPrice = Number(document.getElementById("reSellPrice")?.value || 0);
  const purchPrice = Number(document.getElementById("reSellPurchasePrice")?.value || 0);
  const sellDate = document.getElementById("reSellDate")?.value;
  const expenses = Number(document.getElementById("reSellExpenses")?.value || 0);
  const memo = document.getElementById("reSellMemo")?.value?.trim() || "";
  const removeFromAssets = document.getElementById("reSellRemoveFromAssets")?.checked ?? true;

  if (sellPrice <= 0) {
    alert("매도가액(양도가)을 올바르게 입력해 주세요.");
    return;
  }

  try {
    if (editPnlId) {
      // 1) 기존 매도 기록 수정
      const pnlKrw = Math.round(sellPrice - purchPrice - expenses);
      await api(`/api/realized-pnl/${editPnlId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `[부동산] ${name}`,
          code: "REAL_ESTATE",
          asset_type: "real_estate",
          date: sellDate,
          currency: "KRW",
          pnl: pnlKrw,
          pnl_krw: pnlKrw,
          owner: owner,
          memo: memo || `매도가 ₩${number(sellPrice, 0)}, 매수가 ₩${number(purchPrice, 0)}, 필요경비 ₩${number(expenses, 0)}`,
          real_estate_name: name,
          purchase_price: purchPrice,
          sell_price: sellPrice,
          expenses: expenses,
          address: address,
        }),
      });
      toast("부동산 매도 기록이 수정되었습니다.");
    } else {
      // 2) 신규 매각 기록 (보유 부동산 매각 or 직접 매도 추가)
      const targetEndpoint = (reId && reId !== "direct") ? `/api/real-estates/${reId}/sell` : `/api/real-estates/direct/sell`;
      const res = await api(targetEndpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name,
          owner: owner,
          purchase_price: purchPrice,
          sell_price: sellPrice,
          sell_date: sellDate,
          expenses: expenses,
          address: address,
          remove_from_assets: (reId && reId !== "direct") ? removeFromAssets : false,
          memo: memo,
        }),
      });
      toast(res.message || "부동산 매각 실현손익이 기록되었습니다.");
    }

    document.getElementById("realEstateSellDialog")?.close();
    await loadDashboard();
    await loadRealizedPnl(currentOwner);
  } catch (err) {
    alert(`부동산 매각 처리 오류: ${err.message}`);
  }
}
window.submitRealEstateSell = submitRealEstateSell;


// ── 5. 자산 히트맵 (정통 Squarify 면적 트리맵 + 와이드 카드형 뷰) ─────────────
const PERIOD_LABELS = {
  "1D": "일간 (전일 대비)",
  "1W": "주간 (7일 전 대비)",
  "1M": "월간 (1개월 전 대비)",
  "1Y": "연간 (1년 전 대비)",
  "TOTAL": "진입 (매입단가 대비)",
};

const PERIOD_CAPS = {
  "1D": 10,
  "1W": 15,
  "1M": 20,
  "YTD": 50,
  "1Y": 50,
  "TOTAL": 30,
};

function getEffectiveCap(period, capSetting, items = []) {
  if (capSetting && capSetting !== "auto" && !isNaN(Number(capSetting)) && Number(capSetting) > 0) {
    return Number(capSetting);
  }

  if (items && items.length > 0) {
    let maxAbs = 0;
    items.forEach((it) => {
      let r = 0;
      const periodRates = it.period_changes || {};
      if (period === "TOTAL") {
        r = Math.abs(Number(it.rate != null ? it.rate : (it.return_rate || 0)));
      } else if (periodRates[period] != null) {
        r = Math.abs(Number(periodRates[period]));
      } else if (period === "1D") {
        r = Math.abs(Number(it.day_change_rate || 0));
      } else {
        r = Math.abs(Number(it.rate || it.day_change_rate || 0));
      }
      if (!isNaN(r) && r > maxAbs) maxAbs = r;
    });

    if (maxAbs > 0) {
      let cap = Math.ceil(maxAbs);
      if (cap < 3) cap = 3;
      else if (cap <= 25) cap = Math.ceil(maxAbs);
      else if (cap <= 60) cap = Math.ceil(cap / 5) * 5;
      else cap = Math.ceil(cap / 10) * 10;
      return Math.min(200, cap);
    }
  }

  return PERIOD_CAPS[period] || 15;
}

function getHeatmapColor(rate, maxRate = 15, theme = "kr") {
  const clamped = Math.max(-maxRate, Math.min(maxRate, rate));
  const t = Math.pow(Math.abs(clamped) / maxRate, 0.72);

  if (theme === "us") {
    if (clamped >= 0) {
      const r = Math.round(25 + (16 - 25) * t);
      const g = Math.round(45 + (190 - 45) * t);
      const b = Math.round(38 + (120 - 38) * t);
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      const r = Math.round(48 + (235 - 48) * t);
      const g = Math.round(30 + (55 - 30) * t);
      const b = Math.round(38 + (55 - 38) * t);
      return `rgb(${r}, ${g}, ${b})`;
    }
  } else if (theme === "neon") {
    if (clamped >= 0) {
      const r = Math.round(40 + (170 - 40) * t);
      const g = Math.round(28 + (80 - 28) * t);
      const b = Math.round(62 + (250 - 62) * t);
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      const r = Math.round(20 + (8 - 20) * t);
      const g = Math.round(42 + (190 - 42) * t);
      const b = Math.round(60 + (220 - 60) * t);
      return `rgb(${r}, ${g}, ${b})`;
    }
  } else {
    if (clamped >= 0) {
      const r = Math.round(48 + (238 - 48) * t);
      const g = Math.round(40 + (42 - 40) * t);
      const b = Math.round(52 + (68 - 52) * t);
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      const r = Math.round(35 + (35 - 35) * t);
      const g = Math.round(45 + (95 - 45) * t);
      const b = Math.round(58 + (238 - 58) * t);
      return `rgb(${r}, ${g}, ${b})`;
    }
  }
}

function updateHeatmapLegendUI(period, theme, maxCap, items = []) {
  const cap = getEffectiveCap(period, maxCap, items);
  const legLeft = $("#legendCapLeft");
  const legRight = $("#legendCapRight");
  const legBar = $("#legendBar");
  const legText = $("#legendText");
  const tipNote = $("#heatmapTipNote");
  const capSel = document.getElementById("heatmapCapSelect");

  if (capSel) {
    const autoOpt = capSel.querySelector("option[value='auto']");
    if (autoOpt) autoOpt.textContent = `범위: 자동 (±${cap}%)`;
    if (maxCap && capSel.value !== maxCap) capSel.value = maxCap;
  }

  if (legLeft) legLeft.textContent = `-${cap}%`;
  if (legRight) legRight.textContent = `+${cap}%`;
  if (legBar) legBar.className = `legend-bar theme-${theme}`;
  if (legText) {
    if (theme === "us") legText.textContent = "하락(Red) ← 0 → 상승(Green)";
    else if (theme === "neon") legText.textContent = "하락(Cyan) ← 0 → 상승(Violet)";
    else legText.textContent = "하락(Blue) ← 0 → 상승(Red)";
  }
  if (tipNote) tipNote.textContent = `면적 = 포지션 규모 · 색 = ${PERIOD_LABELS[period] || period} 손익률 (범위 ±${cap}%) · 클릭하면 종목 검색`;
}

// ── 정통 Squarify 트리맵 알고리즘 ──
function squarify(items, x, y, width, height) {
  if (!items.length) return [];
  const totalVal = items.reduce((s, it) => s + it.value, 0);
  if (totalVal <= 0) return [];
  const rects = [];
  const sorted = [...items].sort((a, b) => b.value - a.value);

  function layout(children, rect) {
    if (!children.length) return;
    if (children.length === 1) {
      rects.push({ ...children[0], x: rect.x, y: rect.y, w: rect.w, h: rect.h });
      return;
    }
    const isHoriz = rect.w < rect.h;
    const side = isHoriz ? rect.w : rect.h;
    let row = [];
    let rowSum = 0;
    let bestWorst = Infinity;

    for (let i = 0; i < children.length; i++) {
      const nextRow = [...row, children[i]];
      const nextSum = rowSum + children[i].value;
      const curWorst = worst(nextRow, nextSum, side, rect.total, rect.w * rect.h);
      if (row.length === 0 || curWorst <= bestWorst) {
        row = nextRow;
        rowSum = nextSum;
        bestWorst = curWorst;
      } else {
        const remaining = children.slice(i);
        const frac = rowSum / rect.total;
        if (isHoriz) {
          const rowH = rect.h * frac;
          layoutRow(row, { x: rect.x, y: rect.y, w: rect.w, h: rowH }, isHoriz);
          layout(remaining, { x: rect.x, y: rect.y + rowH, w: rect.w, h: rect.h - rowH, total: rect.total - rowSum });
        } else {
          const rowW = rect.w * frac;
          layoutRow(row, { x: rect.x, y: rect.y, w: rowW, h: rect.h }, isHoriz);
          layout(remaining, { x: rect.x + rowW, y: rect.y, w: rect.w - rowW, h: rect.h, total: rect.total - rowSum });
        }
        return;
      }
    }
    layoutRow(row, rect, isHoriz);
  }

  function worst(row, s, side, total, totalArea) {
    if (!row.length || s === 0 || side === 0) return Infinity;
    const rowArea = (s / total) * totalArea;
    const otherSide = rowArea / side;
    if (otherSide === 0) return Infinity;
    let maxRatio = 0;
    for (const item of row) {
      const itemArea = (item.value / total) * totalArea;
      const itemLen = itemArea / otherSide;
      if (itemLen === 0) return Infinity;
      const ratio = Math.max(itemLen / otherSide, otherSide / itemLen);
      if (ratio > maxRatio) maxRatio = ratio;
    }
    return maxRatio;
  }

  function layoutRow(row, rect, isHoriz) {
    if (!row.length) return;
    let offset = isHoriz ? rect.x : rect.y;
    const totalRowVal = row.reduce((s, it) => s + it.value, 0);
    for (const item of row) {
      const frac = totalRowVal > 0 ? item.value / totalRowVal : 1 / row.length;
      if (isHoriz) {
        const w = rect.w * frac;
        rects.push({ ...item, x: offset, y: rect.y, w, h: rect.h });
        offset += w;
      } else {
        const h = rect.h * frac;
        rects.push({ ...item, x: rect.x, y: offset, w: rect.w, h });
        offset += h;
      }
    }
  }

  layout(sorted, { x, y, w: width, h: height, total: totalVal });
  return rects;
}

let lastValidHeatmapWidth = 0;

function renderTreemapContainer(container, items, period = "1D", theme = "kr", capSetting = "auto") {
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<div class="empty">평가금액이 있는 보유종목이 없습니다.</div>';
    return;
  }

  const maxCap = getEffectiveCap(period, capSetting, items);
  const totalVal = items.reduce((s, it) => s + it.value, 0);
  items.forEach((it) => {
    it.weight = totalVal > 0 ? (it.value / totalVal) * 100 : 0;
  });

  if (container.clientWidth > 200) {
    lastValidHeatmapWidth = container.clientWidth;
  }

  let width = container.clientWidth;
  if (!width || width < 200) {
    if (lastValidHeatmapWidth > 200) {
      width = lastValidHeatmapWidth;
    } else {
      const shell = document.querySelector(".shell");
      const shellW = shell ? shell.clientWidth : window.innerWidth;
      width = Math.max(320, shellW - 48);
    }
  }

  const height = Math.max(380, Math.min(540, Math.round(width * 0.46)));
  container.style.position = "relative";
  container.style.height = `${height}px`;

  const tiles = squarify(items, 0, 0, width, height);

  container.innerHTML = tiles.map((tile) => {
    const periodRates = tile.period_changes || {};
    let rateVal = 0;
    if (period === "TOTAL") {
      rateVal = Number(tile.rate || 0);
    } else if (periodRates[period] != null) {
      rateVal = Number(periodRates[period]);
    } else if (period === "1D") {
      rateVal = Number(tile.day_change_rate || 0);
    } else {
      rateVal = Number(tile.rate || 0);
    }

    const color = getHeatmapColor(rateVal, maxCap, theme);
    const sign = rateVal >= 0 ? "+" : "";
    const rateText = `${sign}${number(rateVal, 1)}%`;

    const isTiny = tile.w < 38 || tile.h < 26;
    const isSmall = !isTiny && (tile.w < 62 || tile.h < 42);
    const isMed = !isTiny && !isSmall && (tile.w < 98 || tile.h < 64);

    let inner = "";
    if (isTiny) {
      inner = `<span class="tile-tiny-dot"></span>`;
    } else if (isSmall) {
      inner = `<span class="tile-name small">${html(tile.name)}</span><span class="tile-rate small">${rateText}</span>`;
    } else if (isMed) {
      inner = `<strong class="tile-name med">${html(tile.name)}</strong><span class="tile-rate med">${rateText}</span>`;
    } else {
      inner = `<strong class="tile-name">${html(tile.name)}</strong><span class="tile-rate">${rateText}</span>`;
    }

    const infoStr = encodeURIComponent(JSON.stringify({
      period,
      name: tile.name,
      code: tile.code,
      market: tile.market || tile.currency,
      value: tile.market_value_krw,
      cost: tile.cost_value_krw,
      profit: tile.profit_krw,
      rate: tile.rate,
      selected_rate: rateVal,
      day_change_rate: tile.day_change_rate || 0,
      period_changes: tile.period_changes,
      weight: tile.weight,
    }));

    return `<div class="heatmap-tile" data-symbol="${html(tile.name)}" data-info="${infoStr}" style="left:${tile.x.toFixed(1)}px;top:${tile.y.toFixed(1)}px;width:${tile.w.toFixed(1)}px;height:${tile.h.toFixed(1)}px;background-color:${color};"><div class="heatmap-tile-inner">${inner}</div></div>`;
  }).join("");

  updateHeatmapLegendUI(period, theme, capSetting, items);
  bindHeatmapInteractions(container);
}

function renderHeatmaps(data) {
  const holdings = data?.holdings || [];
  const container = $("#assetHeatmapContainer");
  if (!container) return;

  if (!holdings.length) {
    container.innerHTML = '<div class="empty">보유종목이 없습니다. 증권사 동기화 후 히트맵이 표시됩니다.</div>';
    return;
  }

  const groups = new Map();
  holdings.forEach((item) => {
    const key = `${item.code}|${item.currency}|${item.name}`;
    const group = groups.get(key) || {
      code: item.code,
      name: item.name,
      currency: item.currency,
      market: item.market,
      quantity: 0,
      market_value_krw: 0,
      cost_value_krw: 0,
      profit_krw: 0,
      day_change_rate: Number(item.day_change_rate || 0),
      period_changes: item.period_changes || {
        "1D": Number(item.day_change_rate || 0),
        "1W": Number(item.day_change_rate || 0),
        "1M": Number(item.day_change_rate || 0),
        "YTD": Number(item.day_change_rate || 0),
        "1Y": Number(item.day_change_rate || 0),
        "TOTAL": Number(item.return_rate || 0),
      },
    };
    group.quantity += Number(item.quantity || 0);
    group.market_value_krw += Number(item.market_value_krw || 0);
    group.cost_value_krw += Number(item.cost_value_krw || 0);
    group.profit_krw += Number(item.profit_krw || 0);
    if (item.day_change_rate != null && Number(item.day_change_rate) !== 0) {
      group.day_change_rate = Number(item.day_change_rate);
    }
    if (item.period_changes) {
      group.period_changes = item.period_changes;
    }
    groups.set(key, group);
  });

  const totalVal = [...groups.values()].reduce((s, it) => s + it.market_value_krw, 0);
  const items = [...groups.values()]
    .filter((it) => it.market_value_krw > 0)
    .map((it) => {
      const rate = it.cost_value_krw ? (it.profit_krw / it.cost_value_krw) * 100 : 0;
      return {
        ...it,
        value: it.market_value_krw,
        rate: rate,
        weight: totalVal > 0 ? (it.market_value_krw / totalVal) * 100 : 0,
      };
    })
    .sort((a, b) => b.value - a.value);

  if (heatmapViewMode === 'cards') {
    container.style.height = "auto";
    container.style.position = "static";
    const maxCap = getEffectiveCap(heatmapPeriod, heatmapMaxCap, items);
    updateHeatmapLegendUI(heatmapPeriod, heatmapTheme, heatmapMaxCap, items);

    container.innerHTML = `
      <div class="heatmap-cards-grid">
        ${items.map(it => {
          const periodRates = it.period_changes || {};
          let selRate = 0;
          if (heatmapPeriod === 'TOTAL') selRate = it.rate;
          else if (periodRates[heatmapPeriod] != null) selRate = Number(periodRates[heatmapPeriod]);
          else selRate = Number(it.day_change_rate || 0);

          const bgColor = getHeatmapColor(selRate, maxCap, heatmapTheme);
          const isUp = selRate >= 0;
          const sign = isUp ? '+' : '';

          return `
            <div class="heatmap-card-item" style="background-color:${bgColor};border:1px solid rgba(255,255,255,0.16);cursor:pointer;padding:12px 14px;border-radius:10px;transition:all 0.16s ease;box-shadow:0 2px 6px rgba(0,0,0,0.25);"
              onclick="$('#searchInput').value='${it.name}';renderHoldings(dashboard);">
              <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                <strong style="font-size:13.5px;font-weight:700;color:#ffffff;text-shadow:0 1px 3px rgba(0,0,0,0.55);">${html(it.name)}</strong>
                <span style="font-size:11.5px;color:rgba(255,255,255,0.8);font-weight:600;">${number(it.weight, 1)}%</span>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:baseline;margin-top:8px;">
                <small style="font-size:11.5px;color:rgba(255,255,255,0.85);">${money(it.value)}</small>
                <b style="font-size:14px;font-weight:800;color:#ffffff;text-shadow:0 1px 4px rgba(0,0,0,0.7);">${sign}${number(selRate, 2)}%</b>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } else {
    renderTreemapContainer(container, items, heatmapPeriod, heatmapTheme, heatmapMaxCap);
  }
}

// ── 히트맵 툴팁 바인딩 ──
function bindHeatmapInteractions(container) {
  const tooltipEl = document.getElementById("heatmapTooltip");
  if (!container || !tooltipEl) return;
  
  // 중복 이벤트 리스너 방지 플래그
  if (container._heatmapBound) return;
  container._heatmapBound = true;

  container.addEventListener("mousemove", (e) => {
    const tile = e.target.closest(".heatmap-tile");
    if (!tile || !tile.dataset.info) {
      tooltipEl.style.display = "none";
      return;
    }
    try {
      const rawInfo = tile.dataset.info.startsWith("%") ? decodeURIComponent(tile.dataset.info) : tile.dataset.info;
      const info = JSON.parse(rawInfo);
      const period = info.period || heatmapPeriod || "1D";
      const selRate = Number(info.selected_rate != null ? info.selected_rate : (period === "TOTAL" ? info.rate : (info.period_changes?.[period] || info.day_change_rate || 0)));
      const sign = selRate >= 0 ? "+" : "";
      const rateColor = selRate >= 0 ? "#f43f5e" : "#38bdf8";
      const totalRateColor = (info.rate || 0) >= 0 ? "#f43f5e" : "#38bdf8";
      const periodLabel = PERIOD_LABELS[period] || period;

      tooltipEl.innerHTML = `
        <div class="heatmap-tooltip-title">
          <strong>${html(info.name)}</strong>
          <span>${html(info.code)} · ${html(info.market || 'KRX')}</span>
        </div>
        <div class="heatmap-tooltip-row">
          <span class="label">포지션 규모:</span>
          <span class="val">${money(info.value)} (${number(info.weight, 1)}%)</span>
        </div>
        <div class="heatmap-tooltip-row">
          <span class="label">${periodLabel}:</span>
          <span class="val" style="color:${rateColor};font-weight:700;">${sign}${number(selRate, 2)}%</span>
        </div>
        <div class="heatmap-tooltip-row">
          <span class="label">누적 수익률:</span>
          <span class="val" style="color:${totalRateColor};font-weight:700;">${(info.rate || 0) >= 0 ? "+" : ""}${number(info.rate, 2)}% (${(info.profit || 0) >= 0 ? "+" : ""}${money(info.profit)})</span>
        </div>
      `;
      tooltipEl.style.display = "block";
      const x = Math.min(Math.max(140, e.clientX), window.innerWidth - 140);
      const y = Math.max(70, e.clientY);
      tooltipEl.style.left = `${x}px`;
      tooltipEl.style.top = `${y}px`;
    } catch (err) {
      console.warn("Tooltip info parse error:", err);
      tooltipEl.style.display = "none";
    }
  });

  container.addEventListener("mouseleave", () => {
    if (tooltipEl) tooltipEl.style.display = "none";
  });

  container.addEventListener("click", (e) => {
    const tile = e.target.closest(".heatmap-tile");
    if (!tile || !tile.dataset.symbol) return;
    const search = $("#searchInput");
    if (search) {
      search.value = tile.dataset.symbol;
      if (dashboard) renderHoldings(dashboard);
    }
  });
}

// ── 6. 보유종목 테이블 (정렬 + 섹터 뱃지 + 인터랙티브 차트 모달) ─────────────
function renderHoldings(data) {
  data = data || dashboard || rawDashboard || {};
  const query = $("#searchInput")?.value.trim().toLowerCase() || "";
  const rows = (data.holdings || []).filter((item) => {
    const assetClass = typeof classifyHolding === 'function' ? classifyHolding(item) : '';
    return [item.name, item.code, item.broker, item.account_name, item.sector, assetClass].join(" ").toLowerCase().includes(query);
  });

  const groups = new Map();
  rows.forEach((item) => {
    const key = `${item.code}|${item.currency}|${item.name}`;
    const group = groups.get(key) || {
      ...item,
      quantity: 0,
      market_value_krw: 0,
      cost_value_krw: 0,
      profit_krw: 0,
      day_change_rate: item.day_change_rate || 0,
      sector: item.sector || '기타',
      items: [],
    };
    group.quantity += Number(item.quantity || 0);
    group.market_value_krw += Number(item.market_value_krw || 0);
    group.cost_value_krw += Number(item.cost_value_krw || 0);
    group.profit_krw += Number(item.profit_krw || 0);
    group.items.push(item);
    groups.set(key, group);
  });

  let sorted = [...groups.values()].map(item => {
    const rate = item.cost_value_krw ? (item.profit_krw / item.cost_value_krw) * 100 : 0;
    return { ...item, return_rate: rate };
  });

  sorted.sort((a, b) => {
    let valA = a[holdingSortField];
    let valB = b[holdingSortField];

    if (holdingSortField === 'name' || holdingSortField === 'sector' || holdingSortField === 'account') {
      valA = String(valA || '').toLowerCase();
      valB = String(valB || '').toLowerCase();
      return holdingSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    valA = Number(valA || 0);
    valB = Number(valB || 0);
    return holdingSortOrder === 'asc' ? valA - valB : valB - valA;
  });

  document.querySelectorAll('.sortable-th').forEach(th => {
    th.classList.remove('sort-asc', 'sort-desc');
    if (th.dataset.sort === holdingSortField) {
      th.classList.add(holdingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  });

  const tbody = $("#holdingsBody");
  if (!tbody) return;

  tbody.innerHTML = sorted.map((item) => {
    const dayRate = Number(item.day_change_rate || 0);
    const accounts = item.items.map((detail) => `
      <span class="holding-account-detail">
        ${html(detail.broker)} ${html(detail.account_name)} ${number(detail.quantity, 4)}주
        <button class="mini-edit-button edit-button" data-id="${detail.id}" title="수정" type="button">✎</button>
        <button class="mini-edit-button delete-button" data-id="${detail.id}" title="삭제" type="button">×</button>
      </span>
    `).join("");

    return `
      <tr data-code="${html(item.code)}">
        <td class="holding-name-cell">
          <strong class="holding-name-link" data-code="${html(item.code)}" data-name="${html(item.name)}" data-price="${item.current_price}" data-currency="${item.currency}">
            ${html(item.name)}
          </strong>
          <small>${html(item.code)} · ${html(item.market || item.currency)}</small>
        </td>
        <td>
          <span class="sector-badge">${html(item.sector || '기타')}</span>
        </td>
        <td class="holding-accounts">${accounts}</td>
        <td>${number(item.quantity, 4)}</td>
        <td><strong>${money(item.market_value_krw)}</strong></td>
        <td class="${signClass(item.profit_krw)}">${item.profit_krw >= 0 ? "+" : ""}${money(item.profit_krw)}</td>
        <td class="${signClass(item.return_rate)}">${item.return_rate >= 0 ? "+" : ""}${number(item.return_rate, 2)}%</td>
        <td class="${signClass(dayRate)}">${dayRate >= 0 ? "+" : ""}${number(dayRate, 2)}%</td>
        <td style="text-align:center;">
          <button class="stock-chart-btn" data-code="${html(item.code)}" data-name="${html(item.name)}" data-price="${item.current_price}" data-currency="${item.currency}" title="인터랙티브 차트" type="button">
            📊
          </button>
        </td>
      </tr>
    `;
  }).join("");

  $("#emptyHoldings") && ($("#emptyHoldings").hidden = sorted.length > 0);
  $(".table-wrap") && ($(".table-wrap").hidden = sorted.length === 0);
}

// ── 7. 종목 가격 & 거래량 인터랙티브 차트 모달 ──────────────────────────────
async function openStockChart(code, name, price, currency = 'KRW') {
  currentStockChartCode = code;
  currentStockChartName = name || code;
  currentStockChartPrice = Number(price || 0);
  currentStockChartCurrency = currency || 'KRW';

  const dlg = $("#stockChartDialog");
  if (!dlg) return;

  $("#stockChartTitle").textContent = currentStockChartName;
  $("#stockChartCode").textContent = `${currentStockChartCode} · ${currentStockChartCurrency}`;
  $("#stockChartPrice").textContent = money(currentStockChartPrice, currentStockChartCurrency);
  $("#stockChartChange").textContent = "데이터 조회 중…";
  if (!['1D', '1W', '1M', '1Y'].includes(currentStockChartPeriod)) {
    currentStockChartPeriod = '1M';
  }

  document.querySelectorAll('#stockChartPeriodTabs .heatmap-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.period === currentStockChartPeriod);
  });

  dlg.showModal();
  await loadStockChartData();
}

async function loadStockChartData() {
  const container = $("#stockChartContainer");
  if (!container) return;
  container.innerHTML = '<div class="empty">차트 데이터를 불러오는 중입니다…</div>';

  try {
    const res = await api(`/api/stock-chart/${encodeURIComponent(currentStockChartCode)}?period=${currentStockChartPeriod}`);
    const candles = res?.candles || [];
    if (!candles.length) {
      container.innerHTML = '<div class="empty">조회 가능한 캔들 차트 데이터가 없습니다.</div>';
      return;
    }

    const prices = candles.map(c => c.close);
    const volumes = candles.map(c => c.volume || 0);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const maxVol = Math.max(...volumes, 1);
    const spanPrice = maxPrice - minPrice || (minPrice * 0.02) || 1;

    const w = 680, h = 260, pad = 20;
    const hPriceArea = 170;
    const hVolTop = hPriceArea + 20;
    const hVolArea = h - hVolTop - 15;

    const pricePoints = candles.map((c, idx) => {
      const x = pad + ((w - pad * 2) * idx) / Math.max(candles.length - 1, 1);
      const y = pad + (hPriceArea - pad) * (1 - (c.close - minPrice) / spanPrice);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const pricePath = pricePoints.join(" ");
    const priceAreaPath = `${pricePath} ${(w - pad)},${hPriceArea} ${pad},${hPriceArea}`;

    const barWidth = Math.max(1.5, Math.min(14, (w - pad * 2) / candles.length - 1.5));
    const volBars = candles.map((c, idx) => {
      const x = pad + ((w - pad * 2) * idx) / Math.max(candles.length - 1, 1) - barWidth / 2;
      const volH = Math.max(2, (c.volume / maxVol) * hVolArea);
      const y = h - 15 - volH;
      const isUp = idx === 0 ? true : (c.close >= candles[idx - 1].close);
      const color = isUp ? '#ff5c77' : '#4f9dff';
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${volH.toFixed(1)}" fill="${color}" opacity="0.75" rx="1" />`;
    }).join('');

    const first = candles[0];
    const last = candles[candles.length - 1];
    const diff = last.close - first.close;
    const diffRate = first.close > 0 ? (diff / first.close) * 100 : 0;
    const isGain = diff >= 0;

    $("#stockChartPrice").textContent = money(last.close, currentStockChartCurrency);
    $("#stockChartChange").textContent = `${isGain ? "+" : ""}${money(diff, currentStockChartCurrency)} (${isGain ? "+" : ""}${number(diffRate, 2)}%)`;
    $("#stockChartChange").className = `sub-rate ${signClass(diff)}`;

    let countLabel = `${candles.length}개 거래일`;
    if (currentStockChartPeriod === "1D") countLabel = `${candles.length}개 5분봉 (장중)`;
    else if (currentStockChartPeriod === "1W") countLabel = `${candles.length}개 60분봉 (1주)`;

    container.innerHTML = `
      <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:260px;overflow:visible;">
        <defs>
          <linearGradient id="stockPriceGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#8e70fa" stop-opacity="0.32" />
            <stop offset="100%" stop-color="#8e70fa" stop-opacity="0.0" />
          </linearGradient>
        </defs>
        <polygon points="${priceAreaPath}" fill="url(#stockPriceGrad)" />
        <polyline points="${pricePath}" fill="none" stroke="#8e70fa" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
        <text x="${pad}" y="${pad + 4}" fill="#7182a6" font-size="10">최고 ${money(maxPrice, currentStockChartCurrency)}</text>
        <text x="${pad}" y="${hPriceArea - 4}" fill="#7182a6" font-size="10">최저 ${money(minPrice, currentStockChartCurrency)}</text>
        
        <line x1="${pad}" y1="${hVolTop - 5}" x2="${w - pad}" y2="${hVolTop - 5}" stroke="#1f2c4d" stroke-dasharray="2,2" />
        <text x="${pad}" y="${hVolTop + 8}" fill="#7182a6" font-size="9" font-weight="700">거래량 (VOLUME)</text>
        ${volBars}
      </svg>
      <div style="display:flex;justify-content:space-between;margin-top:6px;font-size:11px;color:#7182a6;">
        <span>${first.date}</span>
        <span>${countLabel}</span>
        <span>${last.date}</span>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `<div class="empty">차트 로드 실패: ${html(err.message)}</div>`;
  }
}

// ── 8. 주식기록 렌더링 (전체주식 콤보 차트 vs 절세계좌 뷰) ───────────────────────────
function renderAssetRecords(records) {
  assetRecords = records || [];
  window.assetRecords = records || [];

  const recordsEyebrow = document.getElementById('recordsEyebrow');
  const recordsHeading = document.getElementById('recordsHeadingText');
  const recordsCollapse = document.querySelector('#recordsPanel .section-collapse-btn');
  const taxView = currentRecordView === 'tax_accounts';
  if (recordsEyebrow) recordsEyebrow.textContent = taxView ? 'TAX-ADVANTAGED ACCOUNTS' : 'STOCK RECORDS';
  if (recordsHeading) recordsHeading.textContent = taxView ? '절세계좌' : '주식기록';
  if (recordsCollapse) {
    recordsCollapse.title = taxView ? '절세계좌 접기/펼치기' : '주식기록 접기/펼치기';
    recordsCollapse.setAttribute('aria-label', taxView ? '절세계좌 접기/펼치기' : '주식기록 접기/펼치기');
  }

  if (taxView) {
    $("#recordsPanel")?.classList.add("is-tax-view");
    const sideSummaryEl = document.querySelector(".record-side-summary");
    if (sideSummaryEl) sideSummaryEl.style.display = "none";
    if ($("#recordPeriodTabs")) $("#recordPeriodTabs").style.display = "none";
    if ($("#snapshotButton")) $("#snapshotButton").style.display = "none";
    if ($("#addRecordButton")) $("#addRecordButton").style.display = "none";
    if ($("#recordCount")) $("#recordCount").style.display = "none";
    renderTaxAccountHoldings(currentOwner);
    return;
  }

  // 전체주식 콤보 차트 뷰 툴바 및 레이아웃 복원
  $("#recordsPanel")?.classList.remove("is-tax-view");
  const sideSummaryEl = document.querySelector(".record-side-summary");
  if (sideSummaryEl) sideSummaryEl.style.display = "";
  if ($("#snapshotButton")) $("#snapshotButton").style.display = "";
  if ($("#addRecordButton")) $("#addRecordButton").style.display = "";
  if ($("#recordPeriodTabs")) $("#recordPeriodTabs").style.display = "";
  if ($("#recordPeriodTabs")) $("#recordPeriodTabs").style.opacity = "1";
  if ($("#recordCount")) $("#recordCount").style.display = "";
  const sideSummarySmall = document.querySelector(".record-side-summary small");
  if (sideSummarySmall) sideSummarySmall.textContent = "저장된 날짜별 자산 추이";

  const rawList = [...records].sort((a, b) => String(a.date || '').localeCompare(String(b.date || '')));
  const filtered = filterRecordsByPeriod(rawList, currentRecordPeriod);
  const wrap = $("#assetChart");

  if (!filtered.length) {
    if (wrap) wrap.innerHTML = '<div class="empty">선택한 기간의 주식기록이 없습니다.</div>';
    $("#assetRecordList") && ($("#assetRecordList").innerHTML = "");
    $("#recordCount") && ($("#recordCount").textContent = "0개 기록");
    return;
  }

  if (currentRecordView === 'bar' || currentRecordView === 'monthly') {
    const values = filtered.map(item => Number(item.total_value_krw || 0));
    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const spanVal = maxVal - (minVal * 0.8) || 1;

    const w = 900, h = 260, pad = 30;
    const hBarArea = 180;
    const barWidth = Math.max(12, Math.min(48, (w - pad * 2) / filtered.length - 8));

    let prevVal = 0;
    const bars = filtered.map((item, idx) => {
      const val = Number(item.total_value_krw || 0);
      const delta = prevVal ? val - prevVal : Number(item.day_profit_krw || 0);
      const deltaRate = prevVal ? (delta / prevVal) * 100 : 0;
      prevVal = val;
      const isGain = delta >= 0;

      const x = pad + ((w - pad * 2) * (idx + 0.5)) / Math.max(filtered.length, 1) - barWidth / 2;
      const barH = Math.max(10, ((val - minVal * 0.8) / spanVal) * (hBarArea - 25));
      const y = hBarArea - barH;

      const sign = delta >= 0 ? "+" : "";
      const deltaText = delta !== 0 ? `${sign}${number(deltaRate, 1)}%` : "-";
      const deltaColor = delta !== 0 ? (isGain ? "#ff5c77" : "#4f9dff") : "#8e9bb5";
      const shortDate = item.date ? item.date.slice(5) : ""; // MM-DD

      return `
        <g class="monthly-bar-group">
          <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="url(#assetBarGrad)" rx="3.5" opacity="0.9">
            <title>${item.date}: ${money(val)} (변동 ${sign}${money(delta)} / ${deltaRate.toFixed(2)}%)</title>
          </rect>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" fill="#f3f5ff" font-size="10" font-weight="700" text-anchor="middle">
            ${money(val)}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 16).toFixed(1)}" fill="#c4d1eb" font-size="10.5" font-weight="700" text-anchor="middle">
            ${shortDate}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 28).toFixed(1)}" fill="${deltaColor}" font-size="9" font-weight="700" text-anchor="middle">
            ${deltaText}
          </text>
        </g>
      `;
    }).join('');

    const first = filtered[0];
    const last = filtered.at(-1);
    const totalDelta = Number(last.total_value_krw || 0) - Number(first.total_value_krw || 0);
    const totalDeltaRate = Number(first.total_value_krw || 0) ? (totalDelta / Number(first.total_value_krw || 0)) * 100 : 0;

    if (wrap) {
      wrap.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:2px 4px 8px;font-size:12px;font-weight:700;">
          <span style="color:#c4b5fd;">📊 총 투자자산 일자별 막대그래프 (${filtered.length}개 기록)</span>
          <span class="${signClass(totalDelta)}" style="font-size:12px;">기간 변동: ${totalDelta >= 0 ? '+' : ''}${money(totalDelta)} (${totalDelta >= 0 ? '+' : ''}${number(totalDeltaRate, 2)}%)</span>
        </div>
        <svg class="record-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:260px;overflow:visible;">
          <defs>
            <linearGradient id="assetBarGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#a78bfa" />
              <stop offset="100%" stop-color="#6366f1" />
            </linearGradient>
          </defs>
          <line x1="${pad}" y1="${hBarArea}" x2="${w - pad}" y2="${hBarArea}" stroke="#283758" stroke-width="1.2" />
          ${bars}
        </svg>
        <div class="record-chart-meta">
          <div><span>기간 시작</span><strong>${html(first.date)}</strong><small>${money(first.total_value_krw)}</small></div>
          <div><span>최근 기록</span><strong>${html(last.date)}</strong><small>${money(last.total_value_krw)}</small></div>
          <div><span>최저 / 최고 자산</span><strong>${money(minVal)} / ${money(maxVal)}</strong><small>해당 기간 ${number(filtered.length, 0)}개 기록</small></div>
        </div>
      `;
    }
  } else {
    const values = filtered.map(item => Number(item.total_value_krw || 0));
    const profits = filtered.map(item => Number(item.day_profit_krw || 0));

    const minVal = Math.min(...values);
    const maxVal = Math.max(...values);
    const spanVal = maxVal - minVal || (minVal * 0.05) || 1;
    const maxAbsProfit = Math.max(...profits.map(Math.abs), 100000);

    const w = 900, h = 280, pad = 24;
    const hLineArea = 160;

    // 막대 차트와 동일하게 그리드 컬럼 중앙에 데이터 포인트와 막대 배치
    const getX = (i) => pad + ((w - pad * 2) * (i + 0.5)) / Math.max(filtered.length, 1);

    const linePoints = filtered.map((pt, i) => {
      const x = getX(i);
      const y = pad + (hLineArea - pad) * (1 - (Number(pt.total_value_krw || 0) - minVal) / spanVal);
      return { x, y, pt };
    });
    const linePath = linePoints.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

    const firstX = linePoints[0].x;
    const lastX = linePoints[linePoints.length - 1].x;
    const lineAreaPath = `${linePath} ${lastX.toFixed(1)},${hLineArea} ${firstX.toFixed(1)},${hLineArea}`;

    const hBarAreaTop = hLineArea + 25;
    const hBarAreaHeight = h - hBarAreaTop - pad;
    const zeroY = hBarAreaTop + (hBarAreaHeight / 2);

    const barWidth = Math.max(3, Math.min(32, (w - pad * 2) / filtered.length - 6));
    const bars = filtered.map((pt, i) => {
      const x = getX(i) - barWidth / 2;
      const p = Number(pt.day_profit_krw || 0);
      const isGain = p >= 0;
      const barH = Math.max(2, (Math.abs(p) / maxAbsProfit) * (hBarAreaHeight / 2 - 4));
      const y = isGain ? (zeroY - barH) : zeroY;
      const color = isGain ? '#ff5c77' : '#4f9dff';
      return `
        <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="${color}" opacity="0.85" rx="1.5">
          <title>${pt.date}: ${isGain ? '+' : ''}${money(p)}</title>
        </rect>
      `;
    }).join('');

    // 데이터가 10개 이하일 때 (일간 2개, 주간 5개 등) 각 지점에 원형 포인트와 수치 라벨 표시
    const pointCircles = filtered.length <= 10 ? linePoints.map(p => {
      const shortDate = p.pt.date ? p.pt.date.slice(5) : '';
      return `
        <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4" fill="#8e70fa" stroke="#0e162b" stroke-width="2">
          <title>${p.pt.date}: ${money(p.pt.total_value_krw)}</title>
        </circle>
        <text x="${p.x.toFixed(1)}" y="${(p.y - 7).toFixed(1)}" fill="#f3f5ff" font-size="10" font-weight="700" text-anchor="middle">
          ${money(p.pt.total_value_krw)}
        </text>
        <text x="${p.x.toFixed(1)}" y="${(hLineArea - 5).toFixed(1)}" fill="#8e9bb5" font-size="9" font-weight="600" text-anchor="middle">
          ${shortDate}
        </text>
      `;
    }).join('') : '';

    const first = filtered[0];
    const last = filtered.at(-1);

    if (wrap) {
      wrap.innerHTML = `
        <div style="display:flex;justify-content:flex-end;gap:14px;margin-bottom:8px;font-size:11px;">
          <span style="display:flex;align-items:center;gap:4px;"><i style="display:inline-block;width:12px;height:3px;background:#8e70fa;border-radius:2px;"></i> 총 자산 (선)</span>
          <span style="display:flex;align-items:center;gap:4px;"><i style="display:inline-block;width:8px;height:8px;background:#ff5c77;border-radius:2px;"></i> 일간 수익 (+)</span>
          <span style="display:flex;align-items:center;gap:4px;"><i style="display:inline-block;width:8px;height:8px;background:#4f9dff;border-radius:2px;"></i> 일간 손실 (-)</span>
        </div>
        <svg class="record-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-label="자산 기록 콤보 차트">
          <defs>
            <linearGradient id="recordComboGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#8e70fa" stop-opacity="0.28" />
              <stop offset="100%" stop-color="#8e70fa" stop-opacity="0.0" />
            </linearGradient>
          </defs>
          <line x1="${pad}" y1="${hLineArea}" x2="${w - pad}" y2="${hLineArea}" stroke="#1f2c4d" stroke-dasharray="3,3" />
          <polygon points="${lineAreaPath}" fill="url(#recordComboGrad)" />
          <polyline points="${linePath}" fill="none" stroke="#8e70fa" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" />
          ${pointCircles}
          <line x1="${pad}" y1="${zeroY}" x2="${w - pad}" y2="${zeroY}" stroke="#334673" stroke-width="1.2" />
          <text x="${pad}" y="${hLineArea + 18}" fill="#7182a6" font-size="10" font-weight="700">일간 손익 (PROFIT / LOSS)</text>
          <text x="${w - pad}" y="${zeroY - 4}" fill="#7182a6" font-size="9" text-anchor="end">0원</text>
          ${bars}
        </svg>
        <div class="record-chart-meta">
          <div><span>기간 시작</span><strong>${html(first.date)}</strong><small>${money(first.total_value_krw)}</small></div>
          <div><span>최근 기록</span><strong>${html(last.date)}</strong><small>${money(last.total_value_krw)}</small></div>
          <div><span>최저 / 최고 자산</span><strong>${money(minVal)} / ${money(maxVal)}</strong><small>해당 기간 ${number(filtered.length, 0)}개 기록</small></div>
        </div>
      `;
    }
  }

  const first = filtered[0];
  const last = filtered.at(-1);
  const delta = Number(last.total_value_krw || 0) - Number(first.total_value_krw || 0);
  const deltaRate = Number(first.total_value_krw || 0) ? delta / Number(first.total_value_krw || 0) * 100 : 0;
  $("#recordSummary") && ($("#recordSummary").textContent = `${money(delta)} (${deltaRate >= 0 ? "+" : ""}${number(deltaRate, 2)}%)`);
  $("#recordSummary") && ($("#recordSummary").className = signClass(delta));
  $("#recordCount") && ($("#recordCount").textContent = `${number(filtered.length, 0)}개 기록`);

  const descRecords = [...filtered].reverse();
  const listEl = $("#assetRecordList");
  if (listEl) {
    listEl.innerHTML = descRecords.map((item) => `
      <div class="record-row">
        <div class="record-row-main">
          <strong>${html(item.date)}</strong>
          <span>${money(item.total_value_krw)} · ${number(item.holding_count, 0)}종목</span>
        </div>
        <div class="record-row-values">
          <b class="${signClass(item.day_profit_krw || 0)}">${Number(item.day_profit_krw || 0) >= 0 ? "+" : ""}${money(item.day_profit_krw || 0)}</b>
          <small>${html(item.memo || item.source || "")}</small>
        </div>
        <div class="record-row-actions">
          <button class="button secondary tiny" data-record-edit="${item.id}" type="button">수정</button>
          <button class="button text danger tiny" data-record-delete="${item.id}" type="button">삭제</button>
        </div>
      </div>
    `).join("");
  }
}

// ── 8-1. 절세계좌 보유종목 및 계좌별 자산 렌더링 ──────────────────────────────
function getTaxCategory(item) {
  if (!item) return 'pension_savings';
  const aType = (item.account_type || '').toLowerCase();
  const aName = (item.name || item.account_name || '').toLowerCase();
  if (aType === 'isa' || aName.includes('isa')) return 'isa';
  if (aType === 'irp' || aName.includes('irp')) return 'irp';
  return 'pension_savings';
}

function calcAccountCumulativeTaxSaved(a) {
  if (!a) return 0;
  const aType = getTaxCategory(a);
  if (aType !== 'pension_savings' && aType !== 'irp') return 0;

  const defaultRate = a.income_level === 'high' ? 0.132 : 0.165;
  const baseLimit = aType === 'pension_savings' ? 6000000 : 9000000;
  const yList = Array.isArray(a.yearly_contributions) ? a.yearly_contributions : [];

  if (yList.length > 0) {
    let sum = 0;
    yList.forEach(y => {
      const isDed = y.is_deductible !== false && String(y.is_deductible) !== 'false';
      if (isDed) {
        const itemRate = y.income_level === 'high' ? 0.132 : (y.income_level === 'low' ? 0.165 : defaultRate);
        sum += Math.floor(Math.min(Number(y.deposit || 0), baseLimit) * itemRate);
      }
    });
    return sum;
  } else {
    if (!isAccountTaxDeductible(a)) return 0;
    const dep = Number(a.annual_deposit) || 0;
    const isaTr = Number(a.isa_transfer_amount) || 0;
    const baseTarget = Math.min(dep, baseLimit);
    const isaTarget = Math.min(isaTr * 0.10, 3000000);
    return Math.floor((baseTarget + isaTarget) * defaultRate);
  }
}

function renderTaxAccountHoldings(owner = currentOwner) {
  $("#recordsPanel")?.classList.add("is-tax-view");
  const sideSummaryEl = document.querySelector(".record-side-summary");
  if (sideSummaryEl) sideSummaryEl.style.display = "none";
  const o = owner || currentOwner || '모두';
  const curData = dashboard || rawDashboard || {};
  const allAccounts = curData.accounts || [];
  const allHoldings = curData.holdings || [];

  // 1. IRP, 연금저축, ISA 계좌 필터링
  const taxAccounts = allAccounts.filter(a => {
    if (!isTaxAdvantagedAccount(a)) return false;
    if (o !== '모두' && (a.owner || '모두') !== o) return false;
    return true;
  });

  const taxAccountIds = new Set(taxAccounts.map(a => a.id));
  const taxAccountMap = new Map(taxAccounts.map(a => [a.id, a]));

  // 2. 해당 계좌들에 속한 보유종목 필터링 및 메타데이터 연결
  const taxHoldings = [];
  allHoldings.forEach(h => {
    let matchedAccount = null;
    if (h.account_id && taxAccountIds.has(h.account_id)) {
      matchedAccount = taxAccountMap.get(h.account_id);
    } else {
      matchedAccount = taxAccounts.find(a => 
        a.name === h.account_name && 
        (a.broker === h.broker || !h.broker) && 
        (a.owner || '모두') === (h.owner || '모두')
      );
    }
    if (!matchedAccount) return;
    if (o !== '모두' && (h.owner || matchedAccount.owner || '모두') !== o) return;

    h._matchedAccountId = matchedAccount.id;
    h._matchedAccount = matchedAccount;
    h._taxCategory = getTaxCategory(matchedAccount);
    taxHoldings.push(h);
  });

  // 카테고리별 분리
  const isaAccounts = taxAccounts.filter(a => getTaxCategory(a) === 'isa');
  const irpAccounts = taxAccounts.filter(a => getTaxCategory(a) === 'irp');
  const pensionAccounts = taxAccounts.filter(a => getTaxCategory(a) === 'pension_savings');

  const isaHoldings = taxHoldings.filter(h => h._taxCategory === 'isa');
  const irpHoldings = taxHoldings.filter(h => h._taxCategory === 'irp');
  const pensionHoldings = taxHoldings.filter(h => h._taxCategory === 'pension_savings');

  // 통계 및 예수금 계산 헬퍼
  const calcHoldingStats = (list) => {
    const market = list.reduce((sum, h) => sum + (Number(h.market_value_krw) || ((Number(h.quantity) || 0) * (Number(h.current_price) || 0))), 0);
    const cost = list.reduce((sum, h) => sum + (Number(h.cost_value_krw) || ((Number(h.quantity) || 0) * (Number(h.avg_price) || 0))), 0);
    const profit = market - cost;
    const profitRate = cost > 0 ? (profit / cost) * 100 : 0;
    return { market, cost, profit, profitRate };
  };

  const getAccountCash = (acct) => {
    if (!acct) return 0;
    if (acct.cash_total_krw !== undefined && acct.cash_total_krw !== null) {
      return Number(acct.cash_total_krw) || 0;
    }
    const krw = Number(acct.cash_krw || acct.cash || 0);
    const usd = Number(acct.cash_usd || 0);
    const usdRate = Number(dashboard?.fx_rates?.USD || dashboard?.summary?.usd_krw_rate || rawDashboard?.summary?.usd_krw_rate || 1400);
    return krw + (usd * usdRate);
  };

  // 전체 통계
  const allStats = calcHoldingStats(taxHoldings);
  const allCash = taxAccounts.reduce((sum, a) => sum + getAccountCash(a), 0);
  const allTotalMarket = allStats.market + allCash;
  const allCumulativeTaxSaved = taxAccounts.reduce((sum, a) => sum + calcAccountCumulativeTaxSaved(a), 0);

  // 카테고리별 통계
  const isaStats = calcHoldingStats(isaHoldings);
  const isaCash = isaAccounts.reduce((sum, a) => sum + getAccountCash(a), 0);
  const isaTotalMarket = isaStats.market + isaCash;

  const irpStats = calcHoldingStats(irpHoldings);
  const irpCash = irpAccounts.reduce((sum, a) => sum + getAccountCash(a), 0);
  const irpTotalMarket = irpStats.market + irpCash;
  const irpCumulativeTaxSaved = irpAccounts.reduce((sum, a) => sum + calcAccountCumulativeTaxSaved(a), 0);

  const pensionStats = calcHoldingStats(pensionHoldings);
  const pensionCash = pensionAccounts.reduce((sum, a) => sum + getAccountCash(a), 0);
  const pensionTotalMarket = pensionStats.market + pensionCash;
  const pensionCumulativeTaxSaved = pensionAccounts.reduce((sum, a) => sum + calcAccountCumulativeTaxSaved(a), 0);

  // 현재 필터 유효성 검사 (계좌 ID가 현재 가족 구성원 계좌에 없는 경우 'all'로 리셋)
  if (currentTaxAccountFilter.startsWith('acc_')) {
    const accId = currentTaxAccountFilter.replace('acc_', '');
    if (!taxAccountIds.has(accId)) {
      currentTaxAccountFilter = 'all';
    }
  }

  // 선택된 필터에 따른 표시 대상 보유종목 및 예수금 결정
  let filteredHoldings = [];
  let filterTitle = '🌿 절세계좌 전체 보유종목';
  let filterSubtitle = 'IRP · 연금저축 · 중개형 ISA 전체 합산';
  let filterBadgeName = '전체';
  let currentFilterCash = 0;

  if (currentTaxAccountFilter === 'isa') {
    filteredHoldings = isaHoldings;
    filterTitle = '🔄 중개형 ISA 보유종목';
    filterSubtitle = `중개형 ISA 계좌 (${isaAccounts.length}개 계좌)`;
    filterBadgeName = 'ISA';
    currentFilterCash = isaCash;
  } else if (currentTaxAccountFilter === 'irp') {
    filteredHoldings = irpHoldings;
    filterTitle = '🛡️ 개인형 IRP 보유종목';
    filterSubtitle = `개인형 IRP 계좌 (${irpAccounts.length}개 계좌)`;
    filterBadgeName = 'IRP';
    currentFilterCash = irpCash;
  } else if (currentTaxAccountFilter === 'pension_savings') {
    filteredHoldings = pensionHoldings;
    filterTitle = '💎 연금저축 보유종목';
    filterSubtitle = `연금저축 계좌 (${pensionAccounts.length}개 계좌)`;
    filterBadgeName = '연금저축';
    currentFilterCash = pensionCash;
  } else if (currentTaxAccountFilter.startsWith('acc_')) {
    const accId = currentTaxAccountFilter.replace('acc_', '');
    const targetAcc = taxAccountMap.get(accId);
    filteredHoldings = taxHoldings.filter(h => h._matchedAccountId === accId);
    if (targetAcc) {
      currentFilterCash = getAccountCash(targetAcc);
      filterTitle = `📁 ${targetAcc.name} 보유종목`;
      filterSubtitle = `${targetAcc.broker || ''} [${targetAcc.owner || '모두'}]`;
      filterBadgeName = targetAcc.name;
    }
  } else {
    currentTaxAccountFilter = 'all';
    filteredHoldings = taxHoldings;
    filterTitle = '🌿 절세계좌 전체 보유종목';
    filterSubtitle = 'IRP · 연금저축 · 중개형 ISA 전체 합산';
    filterBadgeName = '전체';
    currentFilterCash = allCash;
  }

  // 종목 단위 그룹화 (동일 종목을 보유한 계좌들을 하위에 나열)
  const groups = new Map();
  filteredHoldings.forEach((h) => {
    const key = `${h.code || ''}|${h.currency || 'KRW'}|${h.name || ''}`;
    const group = groups.get(key) || {
      code: h.code || '',
      name: h.name || '',
      market: h.market || '',
      currency: h.currency || 'KRW',
      sector: h.sector || '기타',
      current_price: Number(h.current_price || 0),
      day_change_rate: Number(h.day_change_rate || 0),
      quantity: 0,
      market_value_krw: 0,
      cost_value_krw: 0,
      profit_krw: 0,
      items: [],
    };
    const qty = Number(h.quantity || 0);
    const curPrice = Number(h.current_price || 0);
    const avgPrice = Number(h.avg_price || 0);
    const marketVal = Number(h.market_value_krw) || (qty * curPrice);
    const costVal = Number(h.cost_value_krw) || (qty * avgPrice);
    const profitVal = Number(h.profit_krw) || (marketVal - costVal);

    group.quantity += qty;
    group.market_value_krw += marketVal;
    group.cost_value_krw += costVal;
    group.profit_krw += profitVal;
    group.items.push(h);
    groups.set(key, group);
  });

  let sortedGroups = [...groups.values()].map((item) => {
    const rate = item.cost_value_krw ? (item.profit_krw / item.cost_value_krw) * 100 : 0;
    return { ...item, return_rate: rate };
  });

  // 정렬 적용 (종목명, 섹터, 수량, 평가금액, 손익, 수익률, 등락률)
  sortedGroups.sort((a, b) => {
    let valA = a[taxHoldingSortField];
    let valB = b[taxHoldingSortField];

    if (taxHoldingSortField === 'name' || taxHoldingSortField === 'sector') {
      valA = String(valA || '').toLowerCase();
      valB = String(valB || '').toLowerCase();
      return taxHoldingSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    valA = Number(valA || 0);
    valB = Number(valB || 0);
    return taxHoldingSortOrder === 'asc' ? valA - valB : valB - valA;
  });

  const filteredStats = calcHoldingStats(filteredHoldings);
  const filteredTotalMarket = filteredStats.market + currentFilterCash;

  // 상단 사이드 요약 업데이트 (전체변화 카드는 절세계좌 탭에서 제외)
  if ($("#recordCount")) $("#recordCount").textContent = `${sortedGroups.length}개 종목 (${filterBadgeName})`;
  if (sideSummaryEl) sideSummaryEl.style.display = "none";

  // 스냅샷/추가 버튼 숨김/표시
  if ($("#snapshotButton")) $("#snapshotButton").style.display = "none";
  if ($("#addRecordButton")) $("#addRecordButton").style.display = "none";
  if ($("#recordPeriodTabs")) $("#recordPeriodTabs").style.opacity = "0.4";

  const chartWrap = $("#assetChart");
  if (!chartWrap) return;

  if (!taxHoldings.length && allCash === 0) {
    chartWrap.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:300px;color:#94a3b8;text-align:center;">
        <span style="font-size:32px;margin-bottom:8px;">🌿</span>
        <strong style="font-size:15px;color:#cbd5e1;margin-bottom:4px;">${o === '모두' ? '절세계좌(IRP·연금저축·ISA)' : `[${o}] 절세계좌`}에 보유종목이 없습니다.</strong>
        <p style="font-size:12px;margin:0;">계좌 관리에서 IRP, 연금저축, 중개형 ISA 계좌를 등록하고 종목을 추가해보세요.</p>
      </div>
    `;
    if ($("#assetRecordList")) $("#assetRecordList").innerHTML = "";
    return;
  }

  // 우측 종목 리스트 렌더링 (기존보유종목과 동일한 테이블 구조 및 보유계좌 나열)
  let holdingsHtml = '';
  if (!sortedGroups.length && currentFilterCash <= 0) {
    holdingsHtml = `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:260px;color:#94a3b8;text-align:center;">
        <span style="font-size:32px;margin-bottom:8px;">🔍</span>
        <strong style="font-size:15px;color:#cbd5e1;margin-bottom:6px;">${filterTitle}에 등록된 보유종목이 없습니다.</strong>
        <p style="font-size:12px;margin:10px 0 12px;color:#64748b;">좌측 카드에서 다른 절세계좌를 선택하시거나 전체보기를 눌러주세요.</p>
        <button type="button" class="button secondary compact" style="cursor:pointer;" onclick="currentTaxAccountFilter='all';renderTaxAccountHoldings(currentOwner);">🌿 절세계좌 전체 보기</button>
      </div>
    `;
  } else {
    let cashRowHtml = '';
    if (currentFilterCash > 0) {
      let cashAccountLabel = '절세계좌 합산';
      if (currentTaxAccountFilter === 'isa') cashAccountLabel = `ISA (${isaAccounts.length}개 계좌)`;
      else if (currentTaxAccountFilter === 'irp') cashAccountLabel = `IRP (${irpAccounts.length}개 계좌)`;
      else if (currentTaxAccountFilter === 'pension_savings') cashAccountLabel = `연금저축 (${pensionAccounts.length}개 계좌)`;
      else if (currentTaxAccountFilter.startsWith('acc_')) {
        const accId = currentTaxAccountFilter.replace('acc_', '');
        const targetAcc = taxAccountMap.get(accId);
        if (targetAcc) cashAccountLabel = `${targetAcc.broker || ''} ${targetAcc.name}`;
      }

      cashRowHtml = `
        <tr class="tax-cash-table-row" style="background:rgba(56,189,248,0.06);border-bottom:1px solid rgba(56,189,248,0.25);">
          <td class="holding-name-cell" style="text-align:left;">
            <strong style="color:#38bdf8;font-size:13px;display:flex;align-items:center;gap:6px;">
              💵 예수금 (현금 잔고)
            </strong>
            <small style="color:#7dd3fc;">미투자 현금 잔액</small>
          </td>
          <td style="text-align:left;">
            <span class="sector-badge" style="background:rgba(56,189,248,0.18);color:#38bdf8;border:1px solid rgba(56,189,248,0.35);">현금·예수금</span>
          </td>
          <td class="holding-accounts" style="text-align:left;">
            <span class="holding-account-detail" style="background:rgba(56,189,248,0.12);border-color:rgba(56,189,248,0.3);color:#7dd3fc;font-weight:600;">
              ${html(cashAccountLabel)} ₩${number(currentFilterCash, 0)}
            </span>
          </td>
          <td style="color:#64748b;text-align:right;">-</td>
          <td style="text-align:right;"><strong style="color:#38bdf8;font-size:13.5px;font-weight:700;">₩${number(currentFilterCash, 0)}</strong></td>
          <td style="color:#64748b;text-align:right;">-</td>
          <td style="color:#64748b;text-align:right;">-</td>
          <td style="color:#64748b;text-align:right;">-</td>
          <td style="text-align:center;color:#64748b;">-</td>
        </tr>
      `;
    }

    let emptyStockNotice = '';
    if (!sortedGroups.length && currentFilterCash > 0) {
      emptyStockNotice = `
        <tr style="text-align:center;color:#94a3b8;">
          <td colspan="9" style="padding:28px 14px;text-align:center;color:#94a3b8;">
            <div style="font-size:13px;color:#cbd5e1;font-weight:600;margin-bottom:4px;">보유 중인 주식 종목이 없습니다.</div>
            <div style="font-size:11.5px;color:#64748b;">예수금 ₩${number(currentFilterCash, 0)}이 안전하게 보관되어 있습니다.</div>
          </td>
        </tr>
      `;
    }

    const trsHtml = sortedGroups.map((item) => {
      const dayRate = Number(item.day_change_rate || 0);
      const accounts = item.items.map((detail) => {
        const acct = detail._matchedAccount || taxAccountMap.get(detail.account_id) || {};
        const acctName = acct.name || detail.account_name || '절세계좌';
        const acctBroker = acct.broker || detail.broker || '';
        const acctOwner = detail.owner || acct.owner || '';
        const ownerLabel = (o === '모두' && acctOwner) ? ` [${acctOwner}]` : '';

        return `
          <span class="holding-account-detail">
            ${html(acctBroker)} ${html(acctName)}${html(ownerLabel)} ${number(detail.quantity, 0)}주
            <button class="mini-edit-button edit-button" data-id="${detail.id}" title="수정" type="button">✎</button>
            <button class="mini-edit-button delete-button" data-id="${detail.id}" title="삭제" type="button">×</button>
          </span>
        `;
      }).join("");

      return `
        <tr data-code="${html(item.code)}">
          <td class="holding-name-cell" style="text-align:left;">
            <strong class="holding-name-link" data-code="${html(item.code)}" data-name="${html(item.name)}" data-price="${item.current_price}" data-currency="${item.currency}">
              ${html(item.name)}
            </strong>
            <small>${html(item.code)} · ${html(item.market || item.currency || 'KRW')}</small>
          </td>
          <td style="text-align:left;">
            <span class="sector-badge">${html(item.sector || '기타')}</span>
          </td>
          <td class="holding-accounts" style="text-align:left;">${accounts}</td>
          <td>${number(item.quantity, 0)}</td>
          <td><strong>₩${number(item.market_value_krw, 0)}</strong></td>
          <td class="${signClass(item.profit_krw)}">${item.profit_krw >= 0 ? "+" : ""}₩${number(item.profit_krw, 0)}</td>
          <td class="${signClass(item.return_rate)}">${item.return_rate >= 0 ? "+" : ""}${number(item.return_rate, 2)}%</td>
          <td class="${signClass(dayRate)}">${dayRate >= 0 ? "+" : ""}${number(dayRate, 2)}%</td>
          <td style="text-align:center;">
            <button class="stock-chart-btn" data-code="${html(item.code)}" data-name="${html(item.name)}" data-price="${item.current_price}" data-currency="${item.currency}" title="인터랙티브 차트" type="button">
              📊
            </button>
          </td>
        </tr>
      `;
    }).join("");

    holdingsHtml = `
      <div class="table-wrap tax-table-wrap">
        <table class="tax-holdings-table">
          <thead>
            <tr>
              <th data-tax-sort="name" class="sortable-th ${taxHoldingSortField === 'name' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="text-align:left;">종목 <span class="sort-icon"></span></th>
              <th data-tax-sort="sector" class="sortable-th ${taxHoldingSortField === 'sector' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" style="text-align:left;">섹터 <span class="sort-icon"></span></th>
              <th style="text-align:left;">보유계좌</th>
              <th data-tax-sort="quantity" class="sortable-th ${taxHoldingSortField === 'quantity' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">수량 <span class="sort-icon"></span></th>
              <th data-tax-sort="market_value_krw" class="sortable-th ${taxHoldingSortField === 'market_value_krw' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">평가금액 <span class="sort-icon"></span></th>
              <th data-tax-sort="profit_krw" class="sortable-th ${taxHoldingSortField === 'profit_krw' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">평가손익 <span class="sort-icon"></span></th>
              <th data-tax-sort="return_rate" class="sortable-th ${taxHoldingSortField === 'return_rate' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">수익률 <span class="sort-icon"></span></th>
              <th data-tax-sort="day_change_rate" class="sortable-th ${taxHoldingSortField === 'day_change_rate' ? (taxHoldingSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}">등락률 <span class="sort-icon"></span></th>
              <th style="text-align:center;">차트</th>
            </tr>
          </thead>
          <tbody id="taxHoldingsBody">${cashRowHtml}${emptyStockNotice}${trsHtml}</tbody>
        </table>
      </div>
    `;
  }

  // 현재 필터(전체 / 카테고리 / 개별 계좌)의 누적 절세액 산출
  let filterTaxSavedHtml = '';
  if (currentTaxAccountFilter === 'all') {
    filterTaxSavedHtml = `
      <span style="color:#c4b5fd;background:rgba(167,139,250,0.14);border:1px solid rgba(167,139,250,0.3);padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;">
        💎 누적 절세액: <strong style="color:#ddd6fe;font-size:12.5px;">₩${number(allCumulativeTaxSaved, 0)}</strong>
      </span>
    `;
  } else if (currentTaxAccountFilter === 'irp') {
    filterTaxSavedHtml = `
      <span style="color:#c4b5fd;background:rgba(167,139,250,0.14);border:1px solid rgba(167,139,250,0.3);padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;">
        🛡️ 누적 절세액: <strong style="color:#ddd6fe;font-size:12.5px;">₩${number(irpCumulativeTaxSaved, 0)}</strong>
      </span>
    `;
  } else if (currentTaxAccountFilter === 'pension_savings') {
    filterTaxSavedHtml = `
      <span style="color:#34d399;background:rgba(52,211,153,0.14);border:1px solid rgba(52,211,153,0.3);padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;">
        💎 누적 절세액: <strong style="color:#a7f3d0;font-size:12.5px;">₩${number(pensionCumulativeTaxSaved, 0)}</strong>
      </span>
    `;
  } else if (currentTaxAccountFilter === 'isa') {
    filterTaxSavedHtml = `
      <span style="color:#38bdf8;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.25);padding:2px 8px;border-radius:6px;font-size:11.5px;font-weight:700;">
        🔄 ISA 혜택: 비과세 200~400만 + 9.9% 분리과세
      </span>
    `;
  } else if (currentTaxAccountFilter.startsWith('acc_')) {
    const accId = currentTaxAccountFilter.replace('acc_', '');
    const targetAcc = taxAccountMap.get(accId);
    if (targetAcc) {
      const cat = getTaxCategory(targetAcc);
      const isDed = isAccountTaxDeductible(targetAcc);
      const targetTaxSaved = calcAccountCumulativeTaxSaved(targetAcc);

      if (cat === 'isa') {
        filterTaxSavedHtml = `
          <span style="color:#38bdf8;background:rgba(56,189,248,0.12);border:1px solid rgba(56,189,248,0.25);padding:2px 8px;border-radius:6px;font-size:11.5px;font-weight:700;">
            🔄 ISA 비과세 200~400만 + 9.9% 분리과세
          </span>
        `;
      } else if (isDed && targetTaxSaved > 0) {
        filterTaxSavedHtml = `
          <span style="color:#c4b5fd;background:rgba(167,139,250,0.16);border:1px solid rgba(167,139,250,0.35);padding:2px 8px;border-radius:6px;font-size:12px;font-weight:700;">
            💎 누적 절세액: <strong style="color:#ddd6fe;font-size:12.5px;">₩${number(targetTaxSaved, 0)}</strong>
          </span>
        `;
      } else if (!isDed) {
        filterTaxSavedHtml = `
          <span style="color:#34d399;background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.25);padding:2px 8px;border-radius:6px;font-size:11.5px;font-weight:700;">
            🌱 비공제 계좌: 원금 인출 시 비과세
          </span>
        `;
      } else {
        filterTaxSavedHtml = `
          <span style="color:#94a3b8;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);padding:2px 8px;border-radius:6px;font-size:11.5px;font-weight:700;">
            누적 절세액: ₩0
          </span>
        `;
      }
    }
  }

  chartWrap.innerHTML = `
    <div class="tax-table-header" style="display:flex;justify-content:space-between;align-items:center;padding:2px 4px 10px;border-bottom:1px solid rgba(255,255,255,0.08);margin-bottom:8px;flex-wrap:wrap;gap:8px;">
      <div style="display:flex;align-items:center;gap:8px;">
        <span class="tax-filter-title" style="font-size:13.5px;font-weight:700;">${filterTitle} (${sortedGroups.length}개 종목)</span>
        <span style="font-size:11px;color:#94a3b8;">${filterSubtitle}</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;font-size:12px;flex-wrap:wrap;">
        <span style="color:#94a3b8;">총 자산: <strong style="font-size:14px;font-weight:800;">₩${number(filteredTotalMarket, 0)}</strong></span>
        <span style="color:#94a3b8;">(주식 <strong style="font-weight:600;">₩${number(filteredStats.market, 0)}</strong> · <strong style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(currentFilterCash, 0)}</strong>)</span>
        <span class="${signClass(filteredStats.profit)}" style="font-weight:700;">
          ${filteredStats.profit >= 0 ? '+' : ''}₩${number(filteredStats.profit, 0)} (${filteredStats.profit >= 0 ? '+' : ''}${number(filteredStats.profitRate, 2)}%)
        </span>
        ${filterTaxSavedHtml}
      </div>
    </div>
    ${holdingsHtml}
  `;

  // 3. 좌측 사이드 패널: 절세계좌 카드 목록 렌더링
  const recordListEl = $("#assetRecordList");
  if (!recordListEl) return;

  if (!taxAccounts.length) {
    recordListEl.innerHTML = '<div style="color:#94a3b8;font-size:12px;padding:8px;">등록된 절세계좌가 없습니다.</div>';
    return;
  }

  // 3-1. 상단 [전체] 카드 (절세계좌 총액, 수익금액/수익률, 누적 절세액)
  const isAllActive = currentTaxAccountFilter === 'all';
  const allCardHtml = `
    <div class="tax-card record-row ${isAllActive ? 'active-tax-card' : ''}" data-tax-filter="all">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <div style="display:flex;align-items:center;gap:7px;">
          <span style="font-size:16px;">🌿</span>
          <strong class="tax-card-title" style="font-size:13.5px;font-weight:700;">절세계좌 전체</strong>
          ${isAllActive ? '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:#8b5cf6;color:#fff;font-weight:800;">선택됨</span>' : ''}
        </div>
        <span style="font-size:11px;color:#94a3b8;background:rgba(255,255,255,0.06);padding:2px 7px;border-radius:4px;">
          ${taxHoldings.length}개 종목 · ${taxAccounts.length}개 계좌
        </span>
      </div>

      <!-- 절세계좌 총액 -->
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:3px;">
        <span style="font-size:11.5px;color:#94a3b8;">절세계좌 총 자산</span>
        <strong class="tax-card-val" style="font-size:16px;font-weight:800;letter-spacing:-0.3px;">
          ₩${number(allTotalMarket, 0)}
        </strong>
      </div>

      <!-- 자산 구성: 주식 + 예수금 -->
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 7px;border-radius:4px;margin-bottom:5px;">
        <span style="color:#cbd5e1;">주식 ₩${number(allStats.market, 0)}</span>
        <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(allCash, 0)}</span>
      </div>

      <!-- 수익금액 및 수익률 -->
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span style="font-size:11.5px;color:#94a3b8;">수익금액 / 수익률</span>
        <strong class="${signClass(allStats.profit)}" style="font-size:12.5px;font-weight:700;">
          ${allStats.profit >= 0 ? '+' : ''}₩${number(allStats.profit, 0)} (${allStats.profit >= 0 ? '+' : ''}${number(allStats.profitRate, 2)}%)
        </strong>
      </div>

      <!-- 절세금액 누적 -->
      <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 9px;background:rgba(167,139,250,0.12);border:1px solid rgba(167,139,250,0.25);border-radius:6px;font-size:11.5px;">
        <span style="color:#c4b5fd;font-weight:600;">💎 절세금액 누적</span>
        <strong style="color:#a78bfa;font-weight:800;font-size:13px;">
          ₩${number(allCumulativeTaxSaved, 0)}
        </strong>
      </div>
    </div>
  `;

  // 3-2. 카테고리 카드: ISA, IRP, 연금저축
  const isIsaActive = currentTaxAccountFilter === 'isa';
  const isaCardHtml = `
    <div class="tax-card record-row ${isIsaActive ? 'active-tax-card' : ''}" data-tax-filter="isa">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="font-size:15px;">🔄</span>
          <strong class="tax-card-title" style="font-size:13px;font-weight:700;">중개형 ISA</strong>
          ${isIsaActive ? '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:#38bdf8;color:#0f172a;font-weight:800;">선택됨</span>' : ''}
        </div>
        <span style="font-size:11px;color:#38bdf8;background:rgba(56,189,248,0.12);padding:2px 6px;border-radius:4px;font-weight:600;">
          ${isaHoldings.length}개 종목 (${isaAccounts.length}개 계좌)
        </span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px;">
        <span style="font-size:11.5px;color:#94a3b8;">총 자산</span>
        <strong class="tax-card-val" style="font-size:14.5px;font-weight:800;">₩${number(isaTotalMarket, 0)}</strong>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 6px;border-radius:4px;margin-bottom:5px;">
        <span style="color:#cbd5e1;">주식 ₩${number(isaStats.market, 0)}</span>
        <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(isaCash, 0)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:11.5px;color:#94a3b8;">수익 / 수익률</span>
        <span class="${signClass(isaStats.profit)}" style="font-size:12px;font-weight:700;">
          ${isaStats.profit >= 0 ? '+' : ''}₩${number(isaStats.profit, 0)} (${isaStats.profit >= 0 ? '+' : ''}${number(isaStats.profitRate, 2)}%)
        </span>
      </div>
      <div style="font-size:11px;color:#7dd3fc;background:rgba(56,189,248,0.08);padding:4px 8px;border-radius:5px;display:flex;justify-content:space-between;">
        <span>절세 혜택</span>
        <span>비과세 200~400만 + 9.9% 분리과세</span>
      </div>
    </div>
  `;

  const isIrpActive = currentTaxAccountFilter === 'irp';
  const irpCardHtml = `
    <div class="tax-card record-row ${isIrpActive ? 'active-tax-card' : ''}" data-tax-filter="irp">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="font-size:15px;">🛡️</span>
          <strong class="tax-card-title" style="font-size:13px;font-weight:700;">개인형 IRP</strong>
          ${isIrpActive ? '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:#a78bfa;color:#0f172a;font-weight:800;">선택됨</span>' : ''}
        </div>
        <span style="font-size:11px;color:#c4b5fd;background:rgba(167,139,250,0.15);padding:2px 6px;border-radius:4px;font-weight:600;">
          ${irpHoldings.length}개 종목 (${irpAccounts.length}개 계좌)
        </span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px;">
        <span style="font-size:11.5px;color:#94a3b8;">총 자산</span>
        <strong class="tax-card-val" style="font-size:14.5px;font-weight:800;">₩${number(irpTotalMarket, 0)}</strong>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 6px;border-radius:4px;margin-bottom:5px;">
        <span style="color:#cbd5e1;">주식 ₩${number(irpStats.market, 0)}</span>
        <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(irpCash, 0)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:11.5px;color:#94a3b8;">수익 / 수익률</span>
        <span class="${signClass(irpStats.profit)}" style="font-size:12px;font-weight:700;">
          ${irpStats.profit >= 0 ? '+' : ''}₩${number(irpStats.profit, 0)} (${irpStats.profit >= 0 ? '+' : ''}${number(irpStats.profitRate, 2)}%)
        </span>
      </div>
      <div style="font-size:11px;color:#ddd6fe;background:rgba(167,139,250,0.08);padding:4px 8px;border-radius:5px;display:flex;justify-content:space-between;">
        <span>누적 절세액</span>
        <strong style="color:#c4b5fd;">₩${number(irpCumulativeTaxSaved, 0)}</strong>
      </div>
    </div>
  `;

  const isPensionActive = currentTaxAccountFilter === 'pension_savings';
  const pensionCardHtml = `
    <div class="tax-card record-row ${isPensionActive ? 'active-tax-card' : ''}" data-tax-filter="pension_savings">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="font-size:15px;">💎</span>
          <strong class="tax-card-title" style="font-size:13px;font-weight:700;">연금저축</strong>
          ${isPensionActive ? '<span style="font-size:10px;padding:2px 6px;border-radius:4px;background:#34d399;color:#0f172a;font-weight:800;">선택됨</span>' : ''}
        </div>
        <span style="font-size:11px;color:#34d399;background:rgba(52,211,153,0.15);padding:2px 6px;border-radius:4px;font-weight:600;">
          ${pensionHoldings.length}개 종목 (${pensionAccounts.length}개 계좌)
        </span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:2px;">
        <span style="font-size:11.5px;color:#94a3b8;">총 자산</span>
        <strong class="tax-card-val" style="font-size:14.5px;font-weight:800;">₩${number(pensionTotalMarket, 0)}</strong>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 6px;border-radius:4px;margin-bottom:5px;">
        <span style="color:#cbd5e1;">주식 ₩${number(pensionStats.market, 0)}</span>
        <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(pensionCash, 0)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <span style="font-size:11.5px;color:#94a3b8;">수익 / 수익률</span>
        <span class="${signClass(pensionStats.profit)}" style="font-size:12px;font-weight:700;">
          ${pensionStats.profit >= 0 ? '+' : ''}₩${number(pensionStats.profit, 0)} (${pensionStats.profit >= 0 ? '+' : ''}${number(pensionStats.profitRate, 2)}%)
        </span>
      </div>
      <div style="font-size:11px;color:#a7f3d0;background:rgba(16,185,129,0.08);padding:4px 8px;border-radius:5px;display:flex;justify-content:space-between;">
        <span>누적 절세액</span>
        <strong style="color:#34d399;">₩${number(pensionCumulativeTaxSaved, 0)}</strong>
      </div>
    </div>
  `;

  // 3-3. 개별 계좌 상세 카드 목록
  const accountCardsHtml = taxAccounts.map(acct => {
    const acctHoldings = taxHoldings.filter(h => h._matchedAccountId === acct.id);
    const acctStats = calcHoldingStats(acctHoldings);
    const acctCash = getAccountCash(acct);
    const acctTotalMarket = acctStats.market + acctCash;
    const cat = getTaxCategory(acct);
    const isDed = isAccountTaxDeductible(acct);
    const isAcctActive = currentTaxAccountFilter === `acc_${acct.id}`;
    const acctSavedTax = calcAccountCumulativeTaxSaved(acct);

    let typeBadge = '';
    if (cat === 'isa') {
      typeBadge = '<span style="color:#38bdf8;background:rgba(56,189,248,0.12);padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700;">ISA 비과세</span>';
    } else if (cat === 'irp') {
      typeBadge = `<span style="color:${isDed ? '#c4b5fd' : '#34d399'};background:${isDed ? 'rgba(167,139,250,0.15)' : 'rgba(16,185,129,0.15)'};padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700;">IRP ${isDed ? '공제' : '비공제'}</span>`;
    } else {
      typeBadge = `<span style="color:${isDed ? '#38bdf8' : '#34d399'};background:${isDed ? 'rgba(56,189,248,0.12)' : 'rgba(16,185,129,0.12)'};padding:1px 5px;border-radius:3px;font-size:10px;font-weight:700;">연금저축 ${isDed ? '공제' : '비공제'}</span>`;
    }

    let taxSavedRowHtml = '';
    if (cat === 'isa') {
      taxSavedRowHtml = `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:10.5px;color:#7dd3fc;background:rgba(56,189,248,0.08);padding:3px 7px;border-radius:4px;margin-top:4px;">
          <span>절세 혜택</span>
          <span style="color:#38bdf8;font-weight:600;">비과세 200~400만</span>
        </div>
      `;
    } else if (isDed && acctSavedTax > 0) {
      taxSavedRowHtml = `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:11px;color:#ddd6fe;background:rgba(167,139,250,0.09);border:1px solid rgba(167,139,250,0.22);padding:3px 7px;border-radius:4px;margin-top:4px;">
          <span style="color:#c4b5fd;font-weight:600;">💎 누적 절세액</span>
          <strong style="color:#ddd6fe;font-size:12px;font-weight:800;">₩${number(acctSavedTax, 0)}</strong>
        </div>
      `;
    } else if (!isDed) {
      taxSavedRowHtml = `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:10.5px;color:#a7f3d0;background:rgba(16,185,129,0.07);padding:3px 7px;border-radius:4px;margin-top:4px;">
          <span>절세 분류</span>
          <span style="color:#34d399;">비공제 (원금인출 비과세)</span>
        </div>
      `;
    } else {
      taxSavedRowHtml = `
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:10.5px;color:#94a3b8;background:rgba(255,255,255,0.04);padding:3px 7px;border-radius:4px;margin-top:4px;">
          <span>누적 절세액</span>
          <span style="color:#cbd5e1;">₩0</span>
        </div>
      `;
    }

    return `
      <div class="tax-card record-row ${isAcctActive ? 'active-tax-card' : ''}" data-tax-filter="acc_${acct.id}" style="padding:9px 12px !important;margin-bottom:6px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div style="display:flex;align-items:center;gap:6px;">
            <strong class="tax-card-title" style="font-size:12.5px;">${html(acct.name)}</strong>
            ${isAcctActive ? '<span style="font-size:9.5px;padding:1px 5px;border-radius:3px;background:#a78bfa;color:#0f172a;font-weight:800;">선택됨</span>' : ''}
          </div>
          <div style="display:flex;align-items:center;gap:6px;">
            ${typeBadge}
            <button class="account-action-button" data-account-edit-id="${acct.id}" title="계좌 정보 및 예수금 수정" type="button" style="padding:1px 5px;font-size:11px;line-height:1;border-radius:4px;cursor:pointer;">✎</button>
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:baseline;font-size:11.5px;color:#94a3b8;margin-top:3px;">
          <span>${html(acct.broker)} [${html(acct.owner || '모두')}]</span>
          <strong class="tax-card-val" style="font-size:13.5px;font-weight:800;">₩${number(acctTotalMarket, 0)}</strong>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;background:rgba(255,255,255,0.03);padding:3px 6px;border-radius:4px;margin-top:4px;">
          <span style="color:#cbd5e1;">주식 ₩${number(acctStats.market, 0)} (${acctHoldings.length}종목)</span>
          <span style="color:#38bdf8;font-weight:700;">💵 예수금 ₩${number(acctCash, 0)}</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:11px;color:#94a3b8;margin-top:4px;padding-top:2px;">
          <span>평가손익</span>
          <span class="${signClass(acctStats.profit)}" style="font-weight:700;">${acctStats.profit >= 0 ? '+' : ''}₩${number(acctStats.profit, 0)} (${acctStats.profit >= 0 ? '+' : ''}${number(acctStats.profitRate, 2)}%)</span>
        </div>
        ${taxSavedRowHtml}
      </div>
    `;
  }).join('');

  recordListEl.innerHTML = `
    ${allCardHtml}
    <div style="display:flex;flex-direction:column;gap:8px;">
      ${isaCardHtml}
      ${irpCardHtml}
      ${pensionCardHtml}
    </div>
    <div style="font-size:11px;color:#94a3b8;font-weight:700;margin:12px 0 6px 2px;letter-spacing:0.3px;display:flex;justify-content:space-between;align-items:center;">
      <span>계좌별 상세 (${taxAccounts.length}개)</span>
      <span style="font-size:10px;color:#64748b;">클릭하여 단일 계좌 조회</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:4px;">
      ${accountCardsHtml}
    </div>
  `;
}

// ── 9. 대시보드 렌더링 총괄 ──────────────────────────────────────────────────
function render(data) {
  dashboard = data;
  renderSummary(data);
  renderClassifications(data.classifications || []);
  renderAccounts(data.accounts);
  renderSavings(data.savings_accounts || [], data.bank_accounts || [], data.loan_accounts || [], currentOwner);
  renderInsurance(data.insurance_accounts || [], currentOwner);
  renderRealEstate(data.real_estates || [], currentOwner, data.sold_real_estates);
  renderHeatmaps(data);
  renderHoldings(data);
  window.dispatchEvent(new CustomEvent('wealth:portfolio', { detail: {
    accounts: data.accounts || [], holdings: data.holdings || [],
    owner: currentOwner, fxRates: data.fx_rates || {},
  }}));
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  rawDashboard = data;
  dashboard = data;
  try {
    const allRes = await api('/api/asset-records');
    allAssetRecords = allRes.records || [];
  } catch (e) {}
  renderWithOwner(data, currentOwner);
}

async function loadAssetRecords(owner) {
  try {
    const allRes = await api('/api/asset-records');
    allAssetRecords = allRes.records || [];
  } catch (e) {}
  const o = owner || currentOwner || '모두';
  let filtered = [];
  if (o === '모두') {
    const allOwnerRecs = allAssetRecords.filter(r => (r.owner || '모두') === '모두');
    filtered = allOwnerRecs.length > 0 ? allOwnerRecs : allAssetRecords;
  } else {
    filtered = allAssetRecords.filter(r => (r.owner || '모두') === o);
  }
  assetRecords = filtered;
  renderAssetRecords(filtered);
}

// ── 다이얼로그 열기 함수들 ───────────────────────────────────────────────────
function openImport() { $("#importDialog")?.showModal(); }
function openHoldingDialog(record = null) {
  const form = $("#holdingForm");
  if (!form) return;
  form.reset();
  form.dataset.recordId = record ? String(record.id) : "";

  $("#holdingDialogTitle") && ($("#holdingDialogTitle").textContent = record ? "보유종목 수정" : "보유종목 직접 추가");

  // ACCOUNTS 섹션의 등록된 계좌 목록 드롭다운 및 데이터리스트 채우기
  const accounts = dashboard?.accounts || [];
  const acctSel = $("#holdingAccountSelect");
  if (acctSel) {
    acctSel.innerHTML = '<option value="">-- 직접 입력 또는 등록된 계좌 선택 --</option>' +
      accounts.map(a => `
        <option value="${html(a.id)}" data-broker="${html(a.broker)}" data-name="${html(a.name)}" data-owner="${html(a.owner || '모두')}">
          [${html(a.broker)}] ${html(a.name)} (${html(a.owner || '모두')})
        </option>
      `).join('');

    // 현재 수정 중인 레코드의 계좌 매칭
    const matchedAcct = accounts.find(a => a.id === record?.account_id || (a.broker === record?.broker && a.name === record?.account_name));
    if (matchedAcct) {
      acctSel.value = matchedAcct.id;
    } else {
      acctSel.value = "";
    }
  }

  const acctDatalist = $("#holdingAccountDatalist");
  if (acctDatalist) {
    const uniqueNames = [...new Set(accounts.map(a => a.name).filter(Boolean))];
    acctDatalist.innerHTML = uniqueNames.map(name => `<option value="${html(name)}"></option>`).join('');
  }

  populateStockDatalists();
  attachStockAutoFill("holdingForm");

  form.broker.value = record?.broker || "기타 증권사";
  form.account_name.value = record?.account_name || "내 주식 계좌";
  form.code.value = record?.code || "";
  form.name.value = record?.name || "";
  form.quantity.value = record?.quantity ?? "";
  form.avg_price.value = record?.avg_price ?? "";
  form.current_price.value = record?.current_price ?? "";
  form.currency.value = record?.currency || "KRW";
  form.market.value = record?.market || "";
  if (form.sector) form.sector.value = record?.sector || "";
  if (form.owner) {
    const linkedAcct = dashboard?.accounts?.find(a => a.id === record?.account_id);
    form.owner.value = linkedAcct?.owner || record?.owner || "모두";
  }
  $("#holdingDialog")?.showModal();
}

function openAssetRecordDialog(record = null) {
  const form = $("#assetRecordForm");
  if (!form) return;
  form.reset();
  form.dataset.recordId = record?.id || "";
  $("#assetRecordDialogTitle") && ($("#assetRecordDialogTitle").textContent = record ? "자산기록 수정" : "자산기록 추가");
  form.date.value = record?.date || new Date().toISOString().slice(0, 10);
  form.total_value_krw.value = record?.total_value_krw ?? "";
  form.total_cost_krw.value = record?.total_cost_krw ?? "";
  form.profit_krw.value = record?.profit_krw ?? "";
  form.return_rate.value = record?.return_rate ?? "";
  form.day_profit_krw.value = record?.day_profit_krw ?? "";
  form.krw_value_krw.value = record?.krw_value_krw ?? "";
  form.usd_value_krw.value = record?.usd_value_krw ?? "";
  form.holding_count.value = record?.holding_count ?? "";
  form.memo.value = record?.memo ?? "";
  if (form.owner) form.owner.value = record?.owner || currentOwner || "모두";
  $("#assetRecordDialog")?.showModal();
}

function openAccountCashDialog(account) {
  const form = $("#accountCashForm");
  if (!form || !account) return;
  form.reset();
  form.dataset.accountId = account.id;
  $("#accountCashDialogTitle").textContent = `[${account.broker} · ${account.name}] 예수금 입력 / 수정`;
  form.cash_krw.value = account.cash_krw || "";
  form.cash_usd.value = account.cash_usd || "";
  $("#accountCashDialog")?.showModal();
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

  if (!accountCurrentYearlyList || !accountCurrentYearlyList.length) {
    container.innerHTML = `
      <div style="font-size:11.5px;color:#94a3b8;padding:12px 8px;text-align:center;background:rgba(0,0,0,0.2);border-radius:6px;">
        등록된 연도별 납입 이력이 없습니다.<br>
        상단에서 <strong>연도와 납입금액</strong>을 입력 후 <strong>[➕ 연도 추가 / 반영]</strong>을 눌러주세요.
      </div>
    `;
  } else {
    // Sort descending by year
    accountCurrentYearlyList.sort((a, b) => Number(b.year || 0) - Number(a.year || 0));

    container.innerHTML = accountCurrentYearlyList.map((yc, idx) => {
      const yr = String(yc.year || "").trim();
      const dep = Number(yc.deposit || 0);
      const isDed = yc.is_deductible !== false && String(yc.is_deductible) !== "false";
      const incLvl = yc.income_level || defaultIncomeLvl;
      const rate = incLvl === "high" ? 13.2 : 16.5;
      const target = isDed ? Math.min(dep, baseLimit) : 0;
      const saved = isDed ? Math.floor(target * (rate / 100)) : 0;

      cumulativeDeposit += dep;
      if (isDed) cumulativeSaved += saved;

      return `
        <div class="account-yearly-card" data-index="${idx}" data-year="${yr}" style="display:flex;align-items:center;justify-content:space-between;padding:7px 10px;border-radius:6px;gap:8px;">
          <div style="display:flex;align-items:center;gap:8px;flex:1;flex-wrap:wrap;">
            <span style="font-weight:700;font-size:13px;color:#38bdf8;min-width:55px;">${yr}년</span>
            <span class="account-yearly-dep" style="font-size:12.5px;font-weight:600;min-width:90px;">₩${number(dep, 0)}</span>
            <span style="font-size:11px;padding:2px 7px;border-radius:4px;background:${isDed ? 'rgba(56,189,248,0.15)' : 'rgba(52,211,153,0.15)'};color:${isDed ? '#38bdf8' : '#34d399'};font-weight:600;">
              ${isDed ? `🎯 공제 (${rate}%)` : '🌿 비공제'}
            </span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:12px;font-weight:700;color:${isDed ? '#4ade80' : '#94a3b8'};min-width:80px;text-align:right;">
              ${isDed ? `+₩${number(saved, 0)}` : '절세제외(₩0)'}
            </span>
            <button type="button" class="account-yearly-edit-btn" data-index="${idx}" style="border-radius:4px;padding:2px 7px;font-size:11px;cursor:pointer;" title="상단 입력창으로 불러와 수정">수정</button>
            <button type="button" class="account-yearly-del-btn" data-index="${idx}" style="border-radius:4px;padding:2px 7px;font-size:11px;cursor:pointer;" title="삭제">✕</button>
          </div>
        </div>
      `;
    }).join("");
  }

  const cumSavedEl = form?.querySelector("#accountCumulativeSavedText");
  if (cumSavedEl) cumSavedEl.textContent = `₩${number(cumulativeSaved, 0)}`;

  const cumDepEl = form?.querySelector("#accountCumulativeDepositText");
  if (cumDepEl) cumDepEl.textContent = `₩${number(cumulativeDeposit, 0)}`;
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
      if (targetEl) targetEl.textContent = isaTarget > 0 ? ` (ISA 추가 ₩${number(isaTarget, 0)})` : '';
      if (refundEl) refundEl.innerHTML = isaTarget > 0
        ? `+₩${number(Math.floor(isaTarget * (rate / 100)), 0)} <span style="font-size:11px;color:#a7f3d0;">(원금 ₩${number(annualDep, 0)} 비과세)</span>`
        : `<span style="color:#a7f3d0;font-size:12px;">₩0 (원금 비과세 인출 대상)</span>`;
    } else {
      if (targetEl) targetEl.textContent = isaTarget > 0 ? ` (ISA 추가 ₩${number(isaTarget, 0)})` : '';
      if (refundEl) refundEl.textContent = `₩${number(totalRefund, 0)} (${rate}%)`;
    }
  }
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
  const yr = normalizeYear(rawYr);
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
    toast(`[${oldYr}년 ➔ ${yr}년 ₩${number(dep, 0)}] 수정이 반영되었습니다. 하단 [저장]을 눌러 최종 저장하세요.`);
  } else {
    // 기존 연도 확인 (있으면 갱신, 없으면 추가)
    const existingIdx = accountCurrentYearlyList.findIndex(y => normalizeYear(y.year) === yr);
    if (existingIdx >= 0) {
      accountCurrentYearlyList[existingIdx].year = yr;
      accountCurrentYearlyList[existingIdx].deposit = dep;
      accountCurrentYearlyList[existingIdx].is_deductible = isDed;
      accountCurrentYearlyList[existingIdx].income_level = incLvl;
      toast(`[${yr}년 ₩${number(dep, 0)}] 이력이 반영되었습니다. 하단 [저장]을 눌러 최종 저장하세요.`);
    } else {
      accountCurrentYearlyList.push({
        year: yr,
        deposit: dep,
        is_deductible: isDed,
        income_level: incLvl
      });
      toast(`[${yr}년 ₩${number(dep, 0)}] 이력이 목록에 추가되었습니다. 하단 [저장]을 눌러 최종 저장하세요.`);
    }
  }

  // 연도 내림차순 정렬 후 렌더링
  accountCurrentYearlyList.sort((a, b) => Number(b.year || 0) - Number(a.year || 0));
  renderAccountYearlyFormRows(editForm);
  updateAccountTaxBenefitFields(editForm);
  refreshDialogKoreanHints(editForm);
}
window.handleAddAccountYearly = handleAddAccountYearly;

let currentEditingAccountId = null;

function openAccountEditDialog(account) {
  const form = $("#accountEditForm");
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
  if (form.owner) form.owner.value = account.owner || "모두";
  if (form.cash_krw) form.cash_krw.value = account.cash_krw || "";
  if (form.cash_usd) form.cash_usd.value = account.cash_usd || "";

  const aName = (account.name || "").toLowerCase();
  const aType = account.account_type || (aName.includes("연금") ? "pension_savings" : (aName.includes("irp") ? "irp" : (aName.includes("isa") ? "isa" : "general")));
  const typeSelect = form.querySelector(".account-type-select");
  if (typeSelect) typeSelect.value = aType;

  const isTaxDeductible = isAccountTaxDeductible(account);
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
  refreshDialogKoreanHints($("#accountEditDialog"));
  $("#accountEditDialog")?.showModal();
}

// ── 14. 가족 구성원 관리 함수들 ──────────────────────────────────────────────
function renderFamilyMemberList(members) {
  const list = document.getElementById('familyMemberList');
  if (!list) return;
  if (!members.length) {
    list.innerHTML = '<p style="color:var(--muted);font-size:13px;">구성원이 없습니다.</p>';
    return;
  }
  list.innerHTML = members.map(m => `
    <div class="family-member-row" style="display:flex;align-items:center;gap:8px;">
      <input class="family-member-name-input" type="text" value="${m}" data-original="${m}"
        style="flex:1;font-size:13px;" maxlength="20" />
      <button class="button secondary compact family-rename-btn" data-name="${m}" type="button">수정</button>
      <button class="button text danger compact family-delete-btn" data-name="${m}" type="button">삭제</button>
    </div>
  `).join('');
}

async function openFamilyManager() {
  const dlg = document.getElementById('familyManagerDialog');
  if (!dlg) return;
  try {
    const res = await api('/api/family-members');
    renderFamilyMemberList(res.members || []);
  } catch(e) {
    renderFamilyMemberList([]);
  }
  dlg.showModal();
}

async function loadFamilyMembers() {
  try {
    const res = await api('/api/family-members');
    const members = res.members || [];
    renderFamilyTabs(members);
    updateOwnerSelectOptions(members);
  } catch (e) {}
}

function updateOwnerSelectOptions(members) {
  const opts = ['<option value="모두">모두</option>'].concat(members.map(m => `<option value="${m}">${m}</option>`)).join('');
  document.querySelectorAll('select[name="owner"]').forEach(sel => {
    const prev = sel.value;
    sel.innerHTML = opts;
    if ([...sel.options].some(o => o.value === prev)) sel.value = prev;
  });
}

const FAMILY_TAB_CONTAINER_IDS = [
  'topbarFamilyTabs',
  'recordsFamilyTabs',
  'heatmapFamilyTabs',
  'dividendFamilyTabs',
  'pnlFamilyTabs',
  'holdingsFamilyTabs',
  'familyTabs',
  'ledgerFamilyTabs',
];

function renderFamilyTabs(members) {
  const allBtn = '<button type="button" class="family-tab' + (currentOwner === '모두' ? ' active' : '') + '" data-owner="모두">모두</button>';
  const memberBtns = members.map(m =>
    '<button type="button" class="family-tab' + (currentOwner === m ? ' active' : '') + '" data-owner="' + m + '">' + m + '</button>'
  ).join('');
  const inner = allBtn + memberBtns;

  FAMILY_TAB_CONTAINER_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = inner;
  });
}

// ── 전역 클릭 이벤트 위임 ───────────────────────────────────────────────────
document.addEventListener('click', async (e) => {
  // 🔽 섹션 접기 / 펼치기 버튼
  const collapseBtn = e.target.closest('.section-collapse-btn');
  if (collapseBtn) {
    e.preventDefault();
    e.stopPropagation();
    if (typeof toggleSection === 'function') {
      toggleSection(collapseBtn.dataset.section);
    }
    return;
  }

  // 🎨 테마 변경 탭 버튼
  const themeTab = e.target.closest('#themeSwitcherTabs .theme-tab');
  if (themeTab) {
    e.preventDefault();
    if (typeof setAppTheme === 'function') {
      setAppTheme(themeTab.dataset.theme);
    }
    return;
  }

  // 가족 탭 선택 (모든 섹션 전역 연동)
  const familyTab = e.target.closest('.family-tabs .family-tab');
  if (familyTab) {
    selectOwner(familyTab.dataset.owner);
    return;
  }

  // 🔍 자산분류 항목(섹터/자산군) 클릭 시 보유종목 자동 검색 & 스크롤 연동
  const sectorItem = e.target.closest('[data-sector-filter]');
  if (sectorItem) {
    e.preventDefault();
    filterHoldingsByClassification(sectorItem.dataset.sectorFilter);
    return;
  }

  // 👨‍👩‍👧‍👦 가족 구성원 관리 모달 열기 (상단바 & 계좌 섹션)
  if (e.target.closest('#topbarFamilyBtn, #manageFamilyBtn')) {
    await openFamilyManager();
    return;
  }

  // 🗂️ 계좌 3대 카테고리 (증권 / 은행 / 보험) 탭 전환
  const catTab = e.target.closest('.account-cat-tab');
  if (catTab) {
    e.preventDefault();
    switchAccountCategory(catTab.dataset.cat);
    return;
  }

  // ➕ 계좌 추가 모달 열기 (증권 계좌)
  if (e.target.closest('#addAccountBtn')) {
    const form = document.getElementById("accountAddForm");
    if (form) {
      form.reset();
      const ownerSelect = form.querySelector("[name='owner']");
      if (ownerSelect && currentOwner !== "모두") {
        ownerSelect.value = currentOwner;
      }
    }
    document.getElementById("accountAddDialog")?.showModal();
    return;
  }

  // 🏦 통합 은행 계좌 추가 모달 열기 (자유통장 / 예·적금 / 대출)
  if (e.target.closest('#addBankIntegratedBtn')) {
    openIntegratedBankDialog();
    return;
  }

  // 🏦 일반 은행 계좌 추가 모달 열기 (하위 호환)
  if (e.target.closest('#addBankAccountBtn')) {
    openBankAccountDialog();
    return;
  }

  // ➕ 예·적금 추가 모달 열기
  if (e.target.closest('#addSavingBtn')) {
    openSavingAccountDialog();
    return;
  }

  // 💳 대출·마이너스통장 추가 모달 열기
  if (e.target.closest('#addLoanBtn')) {
    openLoanAccountDialog();
    return;
  }

  // ➕ 보험/연금/공제 추가 모달 열기
  if (e.target.closest('#addInsuranceBtn')) {
    openInsuranceAccountDialog();
    return;
  }

  // 🏠 부동산 자산 추가 모달 열기
  if (e.target.closest('#addRealEstateBtn')) {
    openRealEstateDialog();
    return;
  }

  // ✎ 증권/연금/IRP 계좌 정보 수정 모달 열기 (증권 탭, 보험/연금 탭, 절세계좌 탭 어디서든 100% 동작)
  const acctEditBtn = e.target.closest('[data-account-edit-id]');
  if (acctEditBtn) {
    e.preventDefault();
    const aid = acctEditBtn.dataset.accountEditId;
    const acct = (dashboard?.accounts || []).find(a => a.id === aid) || (rawDashboard?.accounts || []).find(a => a.id === aid);
    if (acct) {
      openAccountEditDialog(acct);
    } else {
      console.warn("[openAccountEditDialog] 계좌를 찾을 수 없습니다:", aid);
    }
    return;
  }

  // 보험/연금 수정
  const insEditBtn = e.target.closest('[data-insurance-edit-id]');
  if (insEditBtn) {
    const iid = insEditBtn.dataset.insuranceEditId;
    const ins = rawInsuranceAccounts.find(i => i.id === iid);
    if (ins) openInsuranceAccountDialog(ins);
    return;
  }

  // 보험/연금 삭제
  const insDelBtn = e.target.closest('[data-insurance-del-id]');
  if (insDelBtn) {
    const iid = insDelBtn.dataset.insuranceDelId;
    if (confirm('이 보험/연금 상품을 삭제하시겠습니까?')) {
      try {
        await api(`/api/insurance-accounts/${iid}`, { method: 'DELETE' });
        toast('보험/연금 상품이 삭제되었습니다.');
        await loadDashboard();
      } catch (err) {
        toast(err.message || '삭제 실패', true);
      }
    }
    return;
  }

  // 대출·마이너스통장 수정
  const loanEditBtn = e.target.closest('[data-loan-edit-id]');
  if (loanEditBtn) {
    const lid = loanEditBtn.dataset.loanEditId;
    const loan = rawLoanAccounts.find(l => l.id === lid);
    if (loan) openLoanAccountDialog(loan);
    return;
  }

  // 대출·마이너스통장 삭제
  const loanDelBtn = e.target.closest('[data-loan-del-id]');
  if (loanDelBtn) {
    const lid = loanDelBtn.dataset.loanDelId;
    if (confirm('이 대출·마이너스통장 항목을 삭제하시겠습니까?')) {
      try {
        await api(`/api/loan-accounts/${lid}`, { method: 'DELETE' });
        toast('대출·마이너스통장이 삭제되었습니다.');
        await loadDashboard();
      } catch (err) {
        toast(err.message || '삭제 실패', true);
      }
    }
    return;
  }

  // 🗂️ 은행 서브 탭 전환 (전체 / 자유 / 예적금 / 대출)
  const subtabBtn = e.target.closest('.savings-subtab');
  if (subtabBtn) {
    const subtab = subtabBtn.dataset.subtab;
    currentSavingsSubtab = subtab;
    document.querySelectorAll('.savings-subtab').forEach(b => b.classList.toggle('active', b.dataset.subtab === subtab));
    renderSavingsWithOwner(currentOwner);
    return;
  }

  // 🏷️ 상단 부동산 실현손익 카드 클릭 시 [매도] 서브탭으로 즉시 전환
  if (e.target.closest('#cardRealEstateRealized')) {
    currentRealEstateSubtab = 'sold';
    document.querySelectorAll('.real-estate-subtab').forEach(b => b.classList.toggle('active', b.dataset.subtab === 'sold'));
    renderRealEstateWithOwner(currentOwner);
    return;
  }

  // 🗂️ 부동산 서브 탭 전환 (전체 / 자가보유 / 임대 / 임차 / 매도)
  const reSubtabBtn = e.target.closest('.real-estate-subtab');
  if (reSubtabBtn) {
    const subtab = reSubtabBtn.dataset.subtab;
    currentRealEstateSubtab = subtab;
    document.querySelectorAll('.real-estate-subtab').forEach(b => b.classList.toggle('active', b.dataset.subtab === subtab));
    renderRealEstateWithOwner(currentOwner);
    return;
  }

  // 매도 부동산 기록 수정
  const soldEditBtn = e.target.closest('[data-sold-re-edit]');
  if (soldEditBtn) {
    const sid = soldEditBtn.dataset.soldReEdit;
    const soldItem = rawSoldRealEstates.find(s => s.id === sid);
    if (soldItem) openRealEstateSellDialog(null, soldItem);
    return;
  }

  // 매도 부동산 기록 삭제
  const soldDelBtn = e.target.closest('[data-sold-re-del]');
  if (soldDelBtn) {
    const sid = soldDelBtn.dataset.soldReDel;
    const soldItem = rawSoldRealEstates.find(s => s.id === sid);
    const sName = soldItem ? (soldItem.clean_name || soldItem.name || '부동산') : '이 부동산 매도';
    if (confirm(`'${sName}'의 매도 실현손익 기록을 삭제하시겠습니까?`)) {
      try {
        await api(`/api/realized-pnl/${sid}`, { method: 'DELETE' });
        toast('부동산 매도 실현손익 기록이 삭제되었습니다.');
        await loadDashboard();
        await loadRealizedPnl(currentOwner);
      } catch (err) {
        toast(err.message || '삭제 실패', true);
      }
    }
    return;
  }

  // 부동산 KB시세 즉시 갱신
  const reKbRefreshBtn = e.target.closest('[data-re-refresh-kb-id]');
  if (reKbRefreshBtn) {
    const rid = reKbRefreshBtn.dataset.reRefreshKbId;
    reKbRefreshBtn.disabled = true;
    reKbRefreshBtn.textContent = '⏳';
    try {
      const res = await api(`/api/real-estates/${rid}/refresh-kb-price`, { method: 'POST' });
      toast(res.message || 'KB시세가 갱신되었습니다.');
      await loadDashboard();
    } catch (err) {
      toast(err.message || 'KB시세 갱신 실패', true);
    } finally {
      reKbRefreshBtn.disabled = false;
      reKbRefreshBtn.textContent = '🔄';
    }
    return;
  }

  // 부동산 매각 및 실현손익 기록
  const reSellBtn = e.target.closest('[data-re-sell-id]');
  if (reSellBtn) {
    const rid = reSellBtn.dataset.reSellId;
    const reItem = rawRealEstates.find(r => r.id === rid);
    if (reItem) openRealEstateSellDialog(reItem);
    return;
  }

  // 부동산 수정
  const reEditBtn = e.target.closest('[data-re-edit-id]');
  if (reEditBtn) {
    const rid = reEditBtn.dataset.reEditId;
    const reItem = rawRealEstates.find(r => r.id === rid);
    if (reItem) openRealEstateDialog(reItem);
    return;
  }

  // 부동산 삭제
  const reDelBtn = e.target.closest('[data-re-del-id]');
  if (reDelBtn) {
    const rid = reDelBtn.dataset.reDelId;
    const reItem = rawRealEstates.find(r => r.id === rid);
    const reName = reItem ? reItem.name : '이 부동산 자산';
    if (confirm(`'${reName}'을(를) 삭제하시겠습니까?\n(연결된 대출과의 링크도 함께 해제됩니다.)`)) {
      try {
        await api(`/api/real-estates/${rid}`, { method: 'DELETE' });
        toast('부동산 자산이 삭제되었습니다.');
        await loadDashboard();
      } catch (err) {
        toast(err.message || '삭제 실패', true);
      }
    }
    return;
  }


  // 예·적금 수정
  const savingEditBtn = e.target.closest('[data-saving-edit-id]');
  if (savingEditBtn) {
    const sid = savingEditBtn.dataset.savingEditId;
    const saving = rawSavingsAccounts.find(s => s.id === sid);
    if (saving) openSavingAccountDialog(saving);
    return;
  }

  // 예·적금 삭제
  const savingDelBtn = e.target.closest('[data-saving-del-id]');
  if (savingDelBtn) {
    const sid = savingDelBtn.dataset.savingDelId;
    if (confirm('이 예·적금 상품을 삭제하시겠습니까?')) {
      try {
        await api(`/api/savings-accounts/${sid}`, { method: 'DELETE' });
        toast('예·적금 상품이 삭제되었습니다.');
        await loadDashboard();
      } catch (err) {
        toast(err.message || '삭제 실패', true);
      }
    }
    return;
  }

  // 은행 계좌 수정
  const bankEditBtn = e.target.closest('[data-bank-edit-id]');
  if (bankEditBtn) {
    const bid = bankEditBtn.dataset.bankEditId;
    const bank = rawBankAccounts.find(b => b.id === bid);
    if (bank) openBankAccountDialog(bank);
    return;
  }

  // 은행 계좌 삭제
  const bankDelBtn = e.target.closest('[data-bank-del-id]');
  if (bankDelBtn) {
    const bid = bankDelBtn.dataset.bankDelId;
    if (confirm('이 은행 계좌를 삭제하시겠습니까?')) {
      try {
        await api(`/api/bank-accounts/${bid}`, { method: 'DELETE' });
        toast('은행 계좌가 삭제되었습니다.');
        await loadDashboard();
      } catch (err) {
        toast(err.message || '삭제 실패', true);
      }
    }
    return;
  }

  // 가족 구성원 추가
  if (e.target.closest('#addMemberBtn')) {
    const input = document.getElementById('newMemberName');
    const name = (input?.value || '').trim();
    if (!name) { toast('이름을 입력해 주세요.', true); return; }
    try {
      const res = await api('/api/family-members', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      toast(res.message || '추가했습니다.');
      if (input) input.value = '';
      renderFamilyTabs(res.members || []);
      updateOwnerSelectOptions(res.members || []);
      renderFamilyMemberList(res.members || []);
    } catch(err) { toast(err.message, true); }
    return;
  }

  // 가족 구성원 이름 수정
  const renameBtn = e.target.closest('.family-rename-btn');
  if (renameBtn) {
    const row = renameBtn.closest('.family-member-row');
    const input = row?.querySelector('.family-member-name-input');
    const oldName = renameBtn.dataset.name;
    const newName = (input?.value || '').trim();
    if (!newName || newName === oldName) return;
    try {
      const res = await api(`/api/family-members/${encodeURIComponent(oldName)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName }),
      });
      toast(res.message || '수정했습니다.');
      renderFamilyTabs(res.members || []);
      updateOwnerSelectOptions(res.members || []);
      renderFamilyMemberList(res.members || []);
      await loadDashboard();
    } catch(err) { toast(err.message, true); }
    return;
  }

  // 가족 구성원 삭제
  const deleteMemberBtn = e.target.closest('.family-delete-btn');
  if (deleteMemberBtn) {
    const name = deleteMemberBtn.dataset.name;
    if (!confirm(`'${name}' 구성원을 삭제할까요?\n연결된 계좌는 '모두'로 변경됩니다.`)) return;
    try {
      const res = await api(`/api/family-members/${encodeURIComponent(name)}`, { method: 'DELETE' });
      toast(res.message || '삭제했습니다.');
      renderFamilyTabs(res.members || []);
      updateOwnerSelectOptions(res.members || []);
      renderFamilyMemberList(res.members || []);
      await loadDashboard();
    } catch(err) { toast(err.message, true); }
    return;
  }

  // 절세계좌 보유종목 정렬 헤더 클릭
  const taxTh = e.target.closest('#assetChart [data-tax-sort]');
  if (taxTh) {
    const sortField = taxTh.dataset.taxSort;
    if (taxHoldingSortField === sortField) {
      taxHoldingSortOrder = taxHoldingSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      taxHoldingSortField = sortField;
      taxHoldingSortOrder = 'desc';
    }
    renderTaxAccountHoldings(currentOwner);
    return;
  }

  // 절세계좌 보유종목 수정/삭제 버튼
  const taxEditBtn = e.target.closest('#assetChart .edit-button');
  const taxDelBtn = e.target.closest('#assetChart .delete-button');
  if (taxEditBtn) {
    const item = (dashboard?.holdings || []).find(row => String(row.id) === String(taxEditBtn.dataset.id));
    if (item) openHoldingDialog(item);
    return;
  }
  if (taxDelBtn && confirm("이 보유종목을 삭제할까요?")) {
    await action(taxDelBtn, () => api(`/api/holdings/${taxDelBtn.dataset.id}`, { method: "DELETE" }), () => loadDashboard());
    return;
  }

  // 실현손익 테이블 정렬 헤더 클릭
  const pnlTh = e.target.closest('#pnlMonthlyDetail [data-pnl-sort]');
  if (pnlTh) {
    const sortField = pnlTh.dataset.pnlSort;
    if (currentPnlSortField === sortField) {
      currentPnlSortOrder = currentPnlSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      currentPnlSortField = sortField;
      currentPnlSortOrder = (sortField === 'name' || sortField === 'owner') ? 'asc' : 'desc';
    }
    renderPnlMonthlyDetail(selectedPnlMonth);
    return;
  }

  // 배당금 테이블 정렬 헤더 클릭
  const divTh = e.target.closest('#dividendMonthlyDetail [data-div-sort]');
  if (divTh) {
    const sortField = divTh.dataset.divSort;
    if (currentDivSortField === sortField) {
      currentDivSortOrder = currentDivSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      currentDivSortField = sortField;
      currentDivSortOrder = (sortField === 'name' || sortField === 'owner') ? 'asc' : 'desc';
    }
    renderActualDividendDetail(selectedDividendMonth);
    return;
  }

  // 보유종목 정렬 헤더 클릭
  const th = e.target.closest('.sortable-th');
  if (th && th.dataset.sort) {
    const sortField = th.dataset.sort;
    if (holdingSortField === sortField) {
      holdingSortOrder = holdingSortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      holdingSortField = sortField;
      holdingSortOrder = 'desc';
    }
    if (dashboard) renderHoldings(dashboard);
    return;
  }

  // 종목 차트 버튼 또는 종목명 클릭
  const chartBtn = e.target.closest('.stock-chart-btn, .holding-name-link');
  if (chartBtn) {
    const code = chartBtn.dataset.code;
    const name = chartBtn.dataset.name;
    const price = chartBtn.dataset.price;
    const currency = chartBtn.dataset.currency;
    if (code) openStockChart(code, name, price, currency);
    return;
  }

  // 종목 차트 모달 기간 탭 클릭
  const chartTab = e.target.closest('#stockChartPeriodTabs .heatmap-tab');
  if (chartTab) {
    document.querySelectorAll('#stockChartPeriodTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
    chartTab.classList.add('active');
    currentStockChartPeriod = chartTab.dataset.period || '1M';
    await loadStockChartData();
    return;
  }

  // 자산기록 뷰 전환 탭 (📈 콤보 차트 vs 📊 막대 차트)
  const recordViewTab = e.target.closest('#recordViewTabs .heatmap-tab');
  if (recordViewTab) {
    document.querySelectorAll('#recordViewTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
    recordViewTab.classList.add('active');
    currentRecordView = recordViewTab.dataset.view || 'combo';
    renderAssetRecords(assetRecords);
    return;
  }

  // 자산기록 기간 탭 (1D, 1W, 1M, 1Y, ALL)
  const recordPeriodTab = e.target.closest('#recordPeriodTabs .heatmap-tab');
  if (recordPeriodTab) {
    setDashboardPeriod(recordPeriodTab.dataset.period);
    return;
  }

  // 투자자산 분류 탭 (자산군별 vs 섹터별 / 자산 vs 주식)
  const allocTab = e.target.closest('#allocTabs .heatmap-tab');
  if (allocTab) {
    document.querySelectorAll('#allocTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
    allocTab.classList.add('active');
    currentAllocTab = allocTab.dataset.tab || 'asset_class';
    const curData = dashboard || rawDashboard;
    if (curData) {
      renderSummary(curData);
      renderClassifications(curData.classifications || []);
    }
    return;
  }

  // 히트맵 뷰 전환 탭 (면적형 vs 카드형)
  const hmViewTab = e.target.closest('#heatmapViewTabs .heatmap-tab');
  if (hmViewTab) {
    document.querySelectorAll('#heatmapViewTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
    hmViewTab.classList.add('active');
    heatmapViewMode = hmViewTab.dataset.view || 'treemap';
    localStorage.setItem("heatmap_view_mode", heatmapViewMode);
    if (dashboard) renderHeatmaps(dashboard);
    return;
  }

  // 히트맵 기간 탭 (1D, 1W, 1M, 1Y, TOTAL)
  const hmPeriodTab = e.target.closest('#heatmapPeriodTabs .heatmap-tab');
  if (hmPeriodTab) {
    setDashboardPeriod(hmPeriodTab.dataset.period);
    return;
  }

  // 배당 재조회 버튼
  const divRefreshBtn = e.target.closest('#refreshDividendBtn');
  if (divRefreshBtn) {
    action(divRefreshBtn, () => api("/api/refresh-prices", { method: "POST" }), async () => {
      await loadDashboard();
      await loadMarkets();
      await loadDividends(currentOwner);
    });
    return;
  }

  // 배당 모드 탭 (🔮 예상 vs 💵 실제)
  const divModeTab = e.target.closest('#dividendModeTabs .heatmap-tab');
  if (divModeTab) {
    document.querySelectorAll('#dividendModeTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
    divModeTab.classList.add('active');
    currentDividendMode = divModeTab.dataset.divMode || 'estimated';
    selectedDividendMonth = null;
    const refreshBtn = $("#refreshDividendBtn");
    const addBtn = $("#addDividendBtn");
    const importBtn = $("#importDividendBtn");
    const clearBtn = $("#clearAllDividendBtn");

    if (currentDividendMode === 'estimated') {
      if (refreshBtn) refreshBtn.style.display = 'inline-block';
      if (addBtn) addBtn.style.display = 'none';
      if (importBtn) importBtn.style.display = 'none';
      if (clearBtn) clearBtn.style.display = 'none';
      if (dividendData) renderDividends(dividendData);
      else loadDividends(currentOwner);
    } else {
      if (refreshBtn) refreshBtn.style.display = 'none';
      if (addBtn) addBtn.style.display = 'inline-block';
      if (importBtn) importBtn.style.display = 'inline-block';
      if (clearBtn) clearBtn.style.display = 'inline-block';
      if (actualDividendData) renderActualDividends(actualDividendData);
      else loadActualDividends(currentOwner);
    }
    return;
  }

  // 💾 실제 배당 저장하기 버튼
  if (e.target.closest('#dividendSaveBtn')) {
    e.preventDefault();
    if (typeof saveActualDividendRecord === 'function') {
      saveActualDividendRecord();
    }
    return;
  }

  // 💾 매도 실현손익 저장하기 버튼
  if (e.target.closest('#pnlSaveBtn')) {
    e.preventDefault();
    if (typeof saveRealizedPnlRecord === 'function') {
      saveRealizedPnlRecord();
    }
    return;
  }

  // ➕ 실제 배당 추가 버튼
  if (e.target.closest('#addDividendBtn')) {
    openDividendRecordDialog();
    return;
  }

  // 📂 실제 배당 가져오기 버튼
  if (e.target.closest('#importDividendBtn')) {
    const dlg = document.getElementById("dividendImportDialog");
    if (dlg) dlg.showModal();
    return;
  }

  // 🗑️ 실제 배당 전체 일괄 삭제 버튼
  if (e.target.closest('#clearAllDividendBtn')) {
    if (confirm("정말로 모든 실제 배당금 기록을 일괄 삭제하시겠습니까?\n삭제된 내역은 복구할 수 없습니다.")) {
      const btn = $("#clearAllDividendBtn");
      action(btn, async () => {
        const res = await api("/api/actual-dividends/clear", { method: "POST" });
        toast(res.message || "모든 실제 배당금 기록이 삭제되었습니다.");
        await loadActualDividends(currentOwner);
        if (dashboard) await refresh();
      });
    }
    return;
  }

  // 실제 배당 수정 버튼
  const editActualDivBtn = e.target.closest('.edit-actual-div-btn');
  if (editActualDivBtn) {
    const rId = editActualDivBtn.dataset.id;
    const rec = (actualDividendData?.records || []).find(r => r.id === rId);
    if (rec) openDividendRecordDialog(rec);
    return;
  }

  // 실제 배당 삭제 버튼
  const delActualDivBtn = e.target.closest('.delete-actual-div-btn');
  if (delActualDivBtn) {
    const rId = delActualDivBtn.dataset.id;
    const rec = (actualDividendData?.records || []).find(r => r.id === rId);
    const label = rec ? `${rec.date} ${rec.name} (${money(rec.amount_krw)})` : '배당 기록';
    if (!confirm(`'${label}' 배당 내역을 삭제할까요?`)) return;
    const savedScrollY = window.scrollY || window.pageYOffset || 0;
    const divDetailWrap = document.querySelector("#dividendMonthlyDetail .div-detail-grid, #dividendMonthlyDetail .detail-table-wrap");
    const savedTableScroll = divDetailWrap ? divDetailWrap.scrollTop : 0;
    try {
      const res = await api(`/api/actual-dividends/${rId}`, { method: 'DELETE' });
      toast(res.message || '삭제되었습니다.');
      await loadActualDividends(currentOwner);
      await updateOverviewCardsAllTime(currentOwner);
      window.scrollTo({ top: savedScrollY, behavior: "instant" });
      requestAnimationFrame(() => {
        window.scrollTo({ top: savedScrollY, behavior: "instant" });
        const newWrap = document.querySelector("#dividendMonthlyDetail .div-detail-grid, #dividendMonthlyDetail .detail-table-wrap");
        if (newWrap && savedTableScroll > 0) newWrap.scrollTop = savedTableScroll;
      });
    } catch (err) {
      toast(err.message, true);
    }
    return;
  }

  // 배당 막대 차트 월/연도 선택
  const divBar = e.target.closest('.dividend-bar-group');
  if (divBar) {
    if (divBar.dataset.year) {
      const yr = divBar.dataset.year;
      selectedDividendYear = yr;
      selectedDividendMonth = null;
      const yearSelect = $("#dividendYearSelect");
      if (yearSelect) yearSelect.value = yr;
      loadActualDividends(currentOwner, yr);
      return;
    }
    if (divBar.dataset.month) {
      const m = Number(divBar.dataset.month);
      selectedDividendMonth = selectedDividendMonth === m ? null : m;
      if (currentDividendMode === 'estimated') {
        if (dividendData) renderDividends(dividendData);
      } else {
        if (actualDividendData) renderActualDividends(actualDividendData);
      }
      return;
    }
  }

  // 배당 전체 보기 버튼
  if (e.target.closest('#clearDivMonthBtn')) {
    selectedDividendMonth = null;
    if (currentDividendMode === 'estimated') {
      if (dividendData) renderDividends(dividendData);
    } else {
      if (actualDividendData) renderActualDividends(actualDividendData);
    }
    return;
  }

  // 실현손익 거래유형 탭 (🏢 전체 vs 📦 공모주)
  const pnlTab = e.target.closest('#pnlTradeTypeTabs .heatmap-tab');
  if (pnlTab) {
    document.querySelectorAll('#pnlTradeTypeTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
    pnlTab.classList.add('active');
    currentPnlTradeType = pnlTab.dataset.tradeType || 'all';
    selectedPnlMonth = null;
    loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType);
    return;
  }

  // ➕ 실현손익 추가 버튼
  if (e.target.closest('#addPnlBtn')) {
    openPnlRecordDialog();
    return;
  }

  // 📂 실현손익 가져오기 버튼
  if (e.target.closest('#importPnlBtn')) {
    const dlg = document.getElementById("pnlImportDialog");
    if (dlg) dlg.showModal();
    return;
  }

  // 🗑️ 매도 실현손익 전체 일괄 삭제 버튼
  if (e.target.closest('#clearAllPnlBtn')) {
    if (confirm("정말로 모든 매도 실현손익 기록을 일괄 삭제하시겠습니까?\n삭제된 내역은 복구할 수 없습니다.")) {
      const btn = $("#clearAllPnlBtn");
      action(btn, async () => {
        const res = await api("/api/realized-pnl/clear", { method: "POST" });
        toast(res.message || "모든 매도 실현손익 기록이 삭제되었습니다.");
        await loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType);
        await updateOverviewCardsAllTime(currentOwner);
        if (dashboard) await refresh();
      });
    }
    return;
  }

  // 실현손익 수정 버튼
  const editPnlBtn = e.target.closest('.edit-pnl-btn');
  if (editPnlBtn) {
    const rId = editPnlBtn.dataset.id;
    const rec = (pnlData?.records || []).find(r => r.id === rId);
    if (rec) openPnlRecordDialog(rec);
    return;
  }

  // 실현손익 삭제 버튼
  const delPnlBtn = e.target.closest('.delete-pnl-btn');
  if (delPnlBtn) {
    const rId = delPnlBtn.dataset.id;
    const rec = (pnlData?.records || []).find(r => r.id === rId);
    const label = rec ? `${rec.date} ${rec.name} (${money(rec.pnl_krw)})` : '손익 기록';
    if (!confirm(`'${label}' 매도 실현손익 내역을 삭제할까요?`)) return;
    const savedScrollY = window.scrollY || window.pageYOffset || 0;
    const pnlDetailWrap = document.querySelector("#pnlMonthlyDetail .detail-table-wrap");
    const savedTableScroll = pnlDetailWrap ? pnlDetailWrap.scrollTop : 0;
    try {
      const res = await api(`/api/realized-pnl/${rId}`, { method: 'DELETE' });
      toast(res.message || '삭제되었습니다.');
      await loadDashboard();
      await loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType);
      renderRealEstateWithOwner(currentOwner);
      await updateOverviewCardsAllTime(currentOwner);
      window.scrollTo({ top: savedScrollY, behavior: "instant" });
      requestAnimationFrame(() => {
        window.scrollTo({ top: savedScrollY, behavior: "instant" });
        const newWrap = document.querySelector("#pnlMonthlyDetail .detail-table-wrap");
        if (newWrap && savedTableScroll > 0) newWrap.scrollTop = savedTableScroll;
      });
    } catch (err) {
      toast(err.message, true);
    }
    return;
  }

  // 실현손익 막대 차트 월/연도 선택
  const pnlBar = e.target.closest('.pnl-bar-group');
  if (pnlBar) {
    if (pnlBar.dataset.year) {
      const yr = pnlBar.dataset.year;
      selectedPnlYear = yr;
      selectedPnlMonth = null;
      const yearSelect = $("#pnlYearSelect");
      if (yearSelect) yearSelect.value = yr;
      loadRealizedPnl(currentOwner, yr, currentPnlTradeType);
      return;
    }
    if (pnlBar.dataset.month) {
      const m = Number(pnlBar.dataset.month);
      selectedPnlMonth = selectedPnlMonth === m ? null : m;
      if (pnlData) renderRealizedPnl(pnlData);
      return;
    }
  }

  // 실현손익 전체 보기 버튼
  if (e.target.closest('#clearPnlMonthBtn')) {
    selectedPnlMonth = null;
    if (pnlData) renderRealizedPnl(pnlData);
    return;
  }
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
$("#addButton")?.addEventListener("click", () => openHoldingDialog());
$("#importButton")?.addEventListener("click", openImport);
$("#clearAllHoldingsBtn")?.addEventListener("click", (e) => {
  if (confirm("정말로 모든 보유종목을 일괄 삭제하시겠습니까?\n삭제된 내역은 복구할 수 없습니다.")) {
    action(e.currentTarget, async () => {
      const res = await api("/api/holdings/clear", { method: "POST" });
      toast(res.message || "모든 보유종목이 삭제되었습니다.");
      await refresh();
    });
  }
});
$("#addRecordButton")?.addEventListener("click", () => openAssetRecordDialog());

// 2. 오늘 기록 저장
$("#snapshotButton")?.addEventListener("click", (e) => action(e.currentTarget, async () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const dayStr = String(now.getDate()).padStart(2, '0');
  const today = `${year}-${month}-${dayStr}`;

  const s = dashboard?.summary || {};
  const day = dashboard?.day_change || {};
  const currency = dashboard?.currency_summary || {};

  const payload = {
    date: today,
    total_value_krw: Number(s.total_value_krw || 0),
    total_cost_krw: Number(s.total_cost_krw || 0),
    profit_krw: Number(s.profit_krw || 0),
    return_rate: Number(s.return_rate || 0),
    day_profit_krw: Number(day.change_krw || 0),
    krw_value_krw: Number(currency.KRW?.market_value_krw || 0),
    usd_value_krw: Number(currency.USD?.market_value_krw || 0),
    holding_count: Number(s.holding_count || 0),
    source: "snapshot",
    memo: currentOwner === '모두' ? "오늘 스냅샷" : `${currentOwner} 스냅샷`,
    owner: currentOwner || "모두",
  };

  return await api("/api/asset-records", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}, async () => {
  await loadAssetRecords(currentOwner);
}));

// 3. 투자자산 분류 [자산군별] / [섹터별] (자산 / 주식) 탭 전환
document.getElementById('allocTabs')?.addEventListener('click', (e) => {
  const tab = e.target.closest('.heatmap-tab');
  if (!tab) return;
  document.querySelectorAll('#allocTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  currentAllocTab = tab.dataset.tab || 'asset_class';
  const curData = dashboard || rawDashboard;
  if (curData) {
    renderSummary(curData);
    renderClassifications(curData.classifications || []);
  }
});

// 4. 자산기록 [콤보 차트] / [월별 자산] 뷰 모드 탭
document.getElementById('recordViewTabs')?.addEventListener('click', (e) => {
  const tab = e.target.closest('.heatmap-tab');
  if (!tab) return;
  document.querySelectorAll('#recordViewTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  currentRecordView = tab.dataset.view || 'combo';
  renderAssetRecords(assetRecords);
});

// 5. 자산기록 기간 탭
document.getElementById('recordPeriodTabs')?.addEventListener('click', (e) => {
  const tab = e.target.closest('.heatmap-tab');
  if (!tab) return;
  setDashboardPeriod(tab.dataset.period);
});

// 6. 히트맵 [면적형] / [카드형] 뷰 전환 탭
document.getElementById('heatmapViewTabs')?.addEventListener('click', (e) => {
  const tab = e.target.closest('.heatmap-tab');
  if (!tab) return;
  document.querySelectorAll('#heatmapViewTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  heatmapViewMode = tab.dataset.view || 'treemap';
  localStorage.setItem("heatmap_view_mode", heatmapViewMode);
  if (dashboard) renderHeatmaps(dashboard);
});

// 7. 히트맵 기간 탭 & 셀렉트 박스
document.getElementById('heatmapPeriodTabs')?.addEventListener('click', (e) => {
  const tab = e.target.closest('.heatmap-tab');
  if (!tab) return;
  setDashboardPeriod(tab.dataset.period);
});

document.getElementById('heatmapCapSelect')?.addEventListener('change', (e) => {
  heatmapMaxCap = e.target.value;
  localStorage.setItem("heatmap_max_cap", heatmapMaxCap);
  if (dashboard) renderHeatmaps(dashboard);
});

document.getElementById('heatmapThemeSelect')?.addEventListener('change', (e) => {
  heatmapTheme = e.target.value;
  localStorage.setItem("heatmap_theme", heatmapTheme);
  if (dashboard) renderHeatmaps(dashboard);
});

// 히트맵 인터랙션 바인딩
bindHeatmapInteractions($("#assetHeatmapContainer"));

// 8. 검색창 및 종목 수정/삭제 리스너
$("#searchInput")?.addEventListener("input", () => dashboard && renderHoldings(dashboard));
$("#clearButton")?.addEventListener("click", () => {
  if (confirm("저장된 보유내역을 모두 지울까요?")) {
    action($("#clearButton"), () => api("/api/clear", { method: "POST" }));
  }
});

$("#holdingsBody")?.addEventListener("click", (e) => {
  const edit = e.target.closest(".edit-button");
  const del = e.target.closest(".delete-button");
  if (edit) {
    const item = dashboard?.holdings.find(row => row.id === edit.dataset.id);
    if (item) openHoldingDialog(item);
    return;
  }
  if (del && confirm("이 보유종목을 삭제할까요?")) {
    action(del, () => api(`/api/holdings/${del.dataset.id}`, { method: "DELETE" }));
  }
});

// 9. 계좌 목록 클릭
$("#accountList")?.addEventListener("click", async (e) => {
  const toggleTaxBtn = e.target.closest("[data-toggle-tax-account-id]");
  const cashBtn = e.target.closest("[data-cash-id]");
  const editBtn = e.target.closest("[data-account-edit-id]");
  const delBtn = e.target.closest("[data-account-del-id]");

  if (toggleTaxBtn) {
    const accId = toggleTaxBtn.dataset.toggleTaxAccountId;
    const acct = (dashboard?.accounts || []).find(a => a.id === accId) || (rawDashboard?.accounts || []).find(a => a.id === accId);
    if (acct) {
      const currentDed = isAccountTaxDeductible(acct);
      const newDed = !currentDed;
      const acctName = acct.name || "";
      acct.tax_deductible = newDed;
      if (rawDashboard && Array.isArray(rawDashboard.accounts)) {
        const rAcct = rawDashboard.accounts.find(a => a.id === accId);
        if (rAcct) { rAcct.tax_deductible = newDed; }
      }
      if (dashboard && Array.isArray(dashboard.accounts)) {
        const dAcct = dashboard.accounts.find(a => a.id === accId);
        if (dAcct) { dAcct.tax_deductible = newDed; }
      }
      renderWithOwner(rawDashboard || dashboard, currentOwner);
      try {
        await api(`/api/accounts/${accId}`, {
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
        toast(`[${acctName}] ${newDed ? '🎯 세액공제 신청' : '🌿 세액공제 제외(비공제)'}으로 전환되었습니다.`);
        await loadDashboard();
      } catch (err) {
        alert(`전환 실패: ${err.message}`);
        await loadDashboard();
      }
    }
    return;
  }
  if (cashBtn) {
    const acct = (dashboard?.accounts || []).find(a => a.id === cashBtn.dataset.cashId) || (rawDashboard?.accounts || []).find(a => a.id === cashBtn.dataset.cashId);
    if (acct) openAccountCashDialog(acct);
    return;
  }
  if (editBtn) {
    const acct = (dashboard?.accounts || []).find(a => a.id === editBtn.dataset.accountEditId) || (rawDashboard?.accounts || []).find(a => a.id === editBtn.dataset.accountEditId);
    if (acct) openAccountEditDialog(acct);
    return;
  }
  if (delBtn && confirm("이 계좌를 삭제할까요? 연결된 보유종목도 함께 삭제됩니다.")) {
    await action(delBtn, () => api(`/api/accounts/${delBtn.dataset.accountDelId}`, { method: "DELETE" }));
  }
});

// 10. 자산기록 리스트 수정/삭제 및 절세계좌 필터 클릭
$("#assetRecordList")?.addEventListener("click", async (e) => {
  if (e.target.closest("[data-account-edit-id]")) {
    return;
  }
  if (currentRecordView === 'tax_accounts') {
    const taxCard = e.target.closest("[data-tax-filter]");
    if (taxCard) {
      const filter = taxCard.dataset.taxFilter;
      if (filter) {
        currentTaxAccountFilter = filter;
        renderTaxAccountHoldings(currentOwner);
      }
      return;
    }
  }
  const editButton = e.target.closest("[data-record-edit]");
  const deleteButton = e.target.closest("[data-record-delete]");
  if (editButton) {
    const record = assetRecords.find((item) => item.id === editButton.dataset.recordEdit);
    if (record) openAssetRecordDialog(record);
  }
  if (deleteButton && confirm("이 자산기록을 삭제할까요?")) {
    await action(deleteButton, () => api(`/api/asset-records/${deleteButton.dataset.recordDelete}`, { method: "DELETE" }), () => loadAssetRecords(currentOwner));
  }
});

// 보유종목 추가/수정 팝업 내 등록된 계좌 선택 시 자동 채움
$("#holdingAccountSelect")?.addEventListener("change", (e) => {
  const sel = e.target;
  const form = $("#holdingForm");
  if (!form || !sel) return;
  const opt = sel.selectedOptions[0];
  if (opt && opt.value) {
    if (opt.dataset.broker) form.broker.value = opt.dataset.broker;
    if (opt.dataset.name) form.account_name.value = opt.dataset.name;
    if (opt.dataset.owner && form.owner) form.owner.value = opt.dataset.owner;
  }
});

// 실현손익 추가/수정 팝업 내 등록된 계좌 선택 시 자동 채움
$("#pnlAccountSelect")?.addEventListener("change", (e) => {
  const sel = e.target;
  const form = $("#pnlRecordForm");
  if (!form || !sel) return;
  const opt = sel.selectedOptions[0];
  if (opt && opt.value) {
    const brokerInput = form.querySelector("[name='broker']");
    const accInput = form.querySelector("[name='account_name']");
    const ownerSelect = form.querySelector("[name='owner']");
    if (opt.dataset.broker && brokerInput) brokerInput.value = opt.dataset.broker;
    if (opt.dataset.name && accInput) accInput.value = opt.dataset.name;
    if (opt.dataset.owner && ownerSelect) ownerSelect.value = opt.dataset.owner;
  }
});

// 배당금 추가/수정 팝업 내 등록된 계좌 선택 시 자동 채움
$("#dividendAccountSelect")?.addEventListener("change", (e) => {
  const sel = e.target;
  const form = $("#dividendRecordForm");
  if (!form || !sel) return;
  const opt = sel.selectedOptions[0];
  if (opt && opt.value) {
    const brokerInput = form.querySelector("[name='broker']");
    const accInput = form.querySelector("[name='account_name']");
    const ownerSelect = form.querySelector("[name='owner']");
    if (opt.dataset.broker && brokerInput) brokerInput.value = opt.dataset.broker;
    if (opt.dataset.name && accInput) accInput.value = opt.dataset.name;
    if (opt.dataset.owner && ownerSelect) ownerSelect.value = opt.dataset.owner;
  }
});

// 11. 폼 서브밋 핸들러들
$("#holdingForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  const payload = Object.fromEntries(new FormData(form));
  if (!payload.owner) payload.owner = "모두";
  ["quantity", "avg_price", "current_price"].forEach(key => { payload[key] = Number(payload[key] || 0); });

  // 종목코드가 없고 종목명만 있는 경우 자동 검색 보정
  if (!payload.code && payload.name) {
    try {
      const searchRes = await api(`/api/stock-search?q=${encodeURIComponent(payload.name)}`);
      if (searchRes && searchRes.code) {
        payload.code = searchRes.code;
        if (form.code) form.code.value = searchRes.code;
        if (searchRes.currency && (!payload.currency || payload.currency === "KRW") && searchRes.currency === "USD") {
          payload.currency = searchRes.currency;
          if (form.currency) form.currency.value = searchRes.currency;
        }
      }
    } catch (err) {}
  }

  try {
    const id = form.dataset.recordId;
    const result = await api(id ? `/api/holdings/${id}` : "/api/holdings", {
      method: id ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    form.closest("dialog")?.close();
    toast(result.message);
    await loadDashboard();
  } catch (error) {
    toast(error.message, true);
  }
});

$("#importForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  const file = $("#importFile")?.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const result = await api(`/api/import?broker=${encodeURIComponent($("#importBroker")?.value || "기타 증권사")}`, {
      method: "POST",
      body: formData
    });
    form.closest("dialog")?.close();
    toast(result.message);
    await loadDashboard();
  } catch (error) {
    toast(error.message, true);
  }
});

$("#assetRecordForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.currentTarget;
  const payload = Object.fromEntries(new FormData(form));
  ["total_value_krw", "total_cost_krw", "profit_krw", "return_rate", "day_profit_krw", "krw_value_krw", "usd_value_krw", "holding_count"].forEach(key => {
    payload[key] = Number(payload[key] || 0);
  });
  payload.memo = payload.memo || "";
  payload.owner = payload.owner || currentOwner || "모두";
  try {
    const method = form.dataset.recordId ? "PUT" : "POST";
    const url = form.dataset.recordId ? `/api/asset-records/${form.dataset.recordId}` : "/api/asset-records";
    const result = await api(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    form.closest("dialog")?.close();
    toast(result.message);
    await loadAssetRecords(currentOwner);
  } catch (error) {
    toast(error.message, true);
  }
});

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

let isSavingAccount = false;

async function saveEditAccount() {
  if (isSavingAccount) return;
  const form = document.getElementById("accountEditForm");
  if (!form) return;
  const saveBtn = document.getElementById("accountEditSaveBtn");
  isSavingAccount = true;
  if (saveBtn) busy(saveBtn, true);

  try {
    const accountId = form.querySelector("[name='id']")?.value || currentEditingAccountId || form.dataset.accountId || form.getAttribute("data-account-id");
    if (!accountId) {
      alert("계좌 식별자(ID)를 찾을 수 없습니다. 다시 시도해 주세요.");
      return;
    }
    const existingAcct = (dashboard?.accounts || []).find(a => a.id === accountId) || (rawDashboard?.accounts || []).find(a => a.id === accountId);
    const broker = (form.querySelector("[name='broker']")?.value || "").trim() || (existingAcct?.broker || "");
    const name = (form.querySelector("[name='name']")?.value || "").trim() || (existingAcct?.name || "");
    const owner = (form.querySelector("[name='owner']")?.value || "").trim() || (existingAcct?.owner || "모두");

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
      const normYr = normalizeYear(rawYr) || accountCurrentYearlyList[editingAccountYearlyIndex].year;
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
        const normYr = normalizeYear(item.year);
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
      const topYr = normalizeYear(rawTopYr);
      if (topYr) {
        const existing = yearly_contributions.find(y => normalizeYear(y.year) === topYr);
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
      const usdRate = Number(dashboard?.summary?.usd_krw_rate || rawDashboard?.summary?.usd_krw_rate || 1400);
      acctObj.cash_total_krw = cash_krw + (cash_usd * usdRate);
      acctObj.market_value_krw = Number(acctObj.stock_value_krw || 0) + acctObj.cash_total_krw;
    };

    if (rawDashboard && Array.isArray(rawDashboard.accounts)) {
      updateAcctInMemory(rawDashboard.accounts.find(a => a.id === accountId));
    }
    if (dashboard && Array.isArray(dashboard.accounts)) {
      updateAcctInMemory(dashboard.accounts.find(a => a.id === accountId));
    }

    // 2. 화면 즉시 재렌더링
    if (rawDashboard || dashboard) renderWithOwner(rawDashboard || dashboard, currentOwner);

    // 3. 다이얼로그 즉시 닫기
    document.getElementById("accountEditDialog")?.close();

    // 4. 서버 PUT API 전송
    const res = await api(`/api/accounts/${accountId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        broker,
        name,
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
      toast(`[${name}] ${isDeductible ? '🎯 세액공제 신청' : '🌿 세액공제 제외(비공제)'} (납입 ₩${number(annual_deposit, 0)}) 저장되었습니다.`);
    } else {
      toast(`[${name}] 계좌 정보 및 예수금이 저장되었습니다.`);
    }
    await loadDashboard();
  } catch (err) {
    console.error("계좌 수정 오류:", err);
    alert(`계좌 정보 저장 중 오류가 발생했습니다: ${err.message || err}`);
    toast(err.message || String(err), true);
    await loadDashboard();
  } finally {
    isSavingAccount = false;
    if (saveBtn) busy(saveBtn, false);
  }
}

let isSavingNewAccount = false;

async function saveNewAccount() {
  if (isSavingNewAccount) return;
  const form = document.getElementById("accountAddForm");
  if (!form) return;
  const broker = (form.querySelector("[name='broker']")?.value || "").trim();
  const account_name = (form.querySelector("[name='account_name']")?.value || "").trim();
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
  if (saveBtn) busy(saveBtn, true);

  try {
    const res = await api("/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        broker,
        account_name,
        name: account_name,
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
    toast(`[${account_name}] ${isDeductible ? '🎯 세액공제 신청' : '🌿 세액공제 제외(비공제)'} 계좌가 추가되었습니다.`);
    await loadDashboard();
  } catch (err) {
    console.error("계좌 추가 오류:", err);
    alert(`계좌 추가 중 오류가 발생했습니다: ${err.message}`);
    toast(err.message, true);
  } finally {
    isSavingNewAccount = false;
    if (saveBtn) busy(saveBtn, false);
  }
}

window.saveEditAccount = saveEditAccount;
window.saveNewAccount = saveNewAccount;
window.openAccountEditDialog = openAccountEditDialog;

document.getElementById("accountEditSaveBtn")?.addEventListener("click", (e) => {
  e.preventDefault();
  saveEditAccount();
});
document.getElementById("accountAddSaveBtn")?.addEventListener("click", (e) => {
  e.preventDefault();
  saveNewAccount();
});

$("#accountEditForm")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.target.closest("textarea")) {
    e.preventDefault();
    saveEditAccount();
  }
});
$("#accountAddForm")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.target.closest("textarea")) {
    e.preventDefault();
    saveNewAccount();
  }
});

// ── 종목 사전 및 양방향 자동완성 (종목코드 ↔ 종목명) ─────────────────────────
const POPULAR_STOCKS = [
  // 이자 / 현금성 배당 전용 항목 (종목코드 선택 가능)
  { code: "INTEREST_KRW", name: "원화이자", currency: "KRW" },
  { code: "INTEREST_USD", name: "달러이자", currency: "USD" },
  { code: "INTEREST_RP", name: "RP이자", currency: "KRW" },
  { code: "INTEREST_CASH", name: "예탁금이자", currency: "KRW" },

  { code: "005930", name: "삼성전자", currency: "KRW" },
  { code: "005935", name: "삼성전자우", currency: "KRW" },
  { code: "000660", name: "SK하이닉스", currency: "KRW" },
  { code: "373220", name: "LG에너지솔루션", currency: "KRW" },
  { code: "207940", name: "삼성바이오로직스", currency: "KRW" },
  { code: "005380", name: "현대차", currency: "KRW" },
  { code: "000270", name: "기아", currency: "KRW" },
  { code: "068270", name: "셀트리온", currency: "KRW" },
  { code: "035420", name: "NAVER", currency: "KRW" },
  { code: "035720", name: "카카오", currency: "KRW" },
  { code: "005490", name: "POSCO홀딩스", currency: "KRW" },
  { code: "105560", name: "KB금융", currency: "KRW" },
  { code: "055550", name: "신한지주", currency: "KRW" },
  { code: "086790", name: "하나금융지주", currency: "KRW" },
  { code: "316140", name: "우리금융지주", currency: "KRW" },
  { code: "069500", name: "KODEX 200", currency: "KRW" },
  { code: "360750", name: "TIGER 미국S&P500", currency: "KRW" },
  { code: "133690", name: "TIGER 미국나스닥100", currency: "KRW" },
  { code: "379800", name: "KODEX 미국S&P500TR", currency: "KRW" },
  { code: "379810", name: "KODEX 미국나스닥100TR", currency: "KRW" },
  { code: "360200", name: "ACE 미국S&P500", currency: "KRW" },
  { code: "449450", name: "PLUS 고배당주", currency: "KRW" },
  { code: "AAPL", name: "애플 (Apple)", currency: "USD" },
  { code: "MSFT", name: "마이크로소프트 (Microsoft)", currency: "USD" },
  { code: "NVDA", name: "엔비디아 (NVIDIA)", currency: "USD" },
  { code: "GOOGL", name: "알파벳 A (Google)", currency: "USD" },
  { code: "AMZN", name: "아마존 (Amazon)", currency: "USD" },
  { code: "META", name: "메타 (Meta)", currency: "USD" },
  { code: "TSLA", name: "테슬라 (Tesla)", currency: "USD" },
  { code: "QQQ", name: "인베스코 QQQ (Invesco QQQ)", currency: "USD" },
  { code: "QQQM", name: "인베스코 나스닥100 (QQQM)", currency: "USD" },
  { code: "SPY", name: "SPDR S&P 500 (SPY)", currency: "USD" },
  { code: "IVV", name: "iShares Core S&P 500", currency: "USD" },
  { code: "VOO", name: "Vanguard S&P 500", currency: "USD" },
  { code: "SPYG", name: "SPDR Portfolio S&P 500 Growth", currency: "USD" },
  { code: "SCHD", name: "Schwab US Dividend Equity", currency: "USD" },
  { code: "TLT", name: "iShares 20+ Year Treasury Bond", currency: "USD" },
  { code: "TQQQ", name: "ProShares UltraPro QQQ", currency: "USD" },
  { code: "QLD", name: "ProShares Ultra QQQ", currency: "USD" },
];

const POPULAR_IPO_STOCKS = [
  { code: "394420", name: "리센스메디컬", currency: "KRW" },
  { code: "493280", name: "아이엠바이오로직스", currency: "KRW" },
  { code: "408470", name: "한패스", currency: "KRW" },
  { code: "462870", name: "시프트업", currency: "KRW" },
  { code: "475560", name: "더본코리아", currency: "KRW" },
  { code: "278470", name: "에이피알", currency: "KRW" },
  { code: "443060", name: "HD현대마린솔루션", currency: "KRW" },
  { code: "454910", name: "두산로보틱스", currency: "KRW" },
  { code: "450080", name: "에코프로머티", currency: "KRW" },
  { code: "440110", name: "파두", currency: "KRW" },
];
const RECENT_SEARCHED_STOCKS = new Map();

function getAllKnownStockList() {
  const map = new Map();
  POPULAR_STOCKS.forEach(s => map.set(s.code.toUpperCase(), { ...s }));
  POPULAR_IPO_STOCKS.forEach(s => map.set(s.code.toUpperCase(), { ...s }));
  RECENT_SEARCHED_STOCKS.forEach((s, code) => {
    if (!map.has(code.toUpperCase())) map.set(code.toUpperCase(), { ...s });
  });
  (dashboard?.holdings || []).forEach(h => {
    if (h.code) {
      map.set(h.code.toUpperCase(), {
        code: h.code.toUpperCase(),
        name: h.name || h.code,
        currency: h.currency || (h.code.length === 6 && /^\d+$/.test(h.code) ? "KRW" : "USD"),
      });
    }
  });
  (actualDividendData?.records || []).forEach(r => {
    if (r.code) {
      map.set(r.code.toUpperCase(), {
        code: r.code.toUpperCase(),
        name: r.name || r.code,
        currency: r.currency || "KRW",
      });
    }
  });
  (pnlData?.records || []).forEach(r => {
    if (r.code) {
      map.set(r.code.toUpperCase(), {
        code: r.code.toUpperCase(),
        name: r.name || r.code,
        currency: r.currency || "KRW",
      });
    }
  });
  return [...map.values()];
}

function populateStockDatalists() {
  const list = getAllKnownStockList();
  const codeListEl = document.getElementById("holdingCodeList");
  const nameListEl = document.getElementById("holdingNameList");

  if (codeListEl) {
    codeListEl.innerHTML = list.map(s => `<option value="${s.code}">${s.name} (${s.currency})</option>`).join("");
  }
  if (nameListEl) {
    nameListEl.innerHTML = list.map(s => `<option value="${s.name}">${s.code} · ${s.currency}</option>`).join("");
  }
}

function attachStockAutoFill(formId, updateFieldsFn) {
  const form = document.getElementById(formId);
  if (!form) return;
  const codeInput = form.querySelector("[name='code']");
  const nameInput = form.querySelector("[name='name']");
  const currSelect = form.querySelector("[name='currency']");

  form._stockUpdateFieldsFn = updateFieldsFn;

  // 종목 자동완성 추천 드롭다운 컨테이너 생성/확보
  if (nameInput) {
    if (!nameInput.parentElement.style.position) {
      nameInput.parentElement.style.position = "relative";
    }
    let dropdownEl = nameInput.parentElement.querySelector(".stock-suggestions-dropdown");
    if (!dropdownEl) {
      dropdownEl = document.createElement("div");
      dropdownEl.className = "stock-suggestions-dropdown";
      dropdownEl.style.display = "none";
      nameInput.parentElement.appendChild(dropdownEl);
    }
  }

  function highlightAutofill(inputEl) {
    if (!inputEl) return;
    inputEl.classList.remove("input-autofill-flash");
    void inputEl.offsetWidth; // reflow 강제
    inputEl.classList.add("input-autofill-flash");
    setTimeout(() => {
      inputEl.classList.remove("input-autofill-flash");
    }, 1300);
  }

  function onCodeChanged() {
    const raw = (codeInput?.value || "").trim().toUpperCase();
    if (!raw) return;

    // 이자 코드 즉시 매칭
    const INTEREST_CODES = {
      "INTEREST_KRW": { name: "원화이자", currency: "KRW" },
      "INTEREST_USD": { name: "달러이자", currency: "USD" },
      "INTEREST_RP": { name: "RP이자", currency: "KRW" },
      "INTEREST_CASH": { name: "예탁금이자", currency: "KRW" },
    };
    if (INTEREST_CODES[raw]) {
      const match = INTEREST_CODES[raw];
      if (nameInput && (!nameInput.value || nameInput.value.includes("이자"))) nameInput.value = match.name;
      if (currSelect) currSelect.value = match.currency;
      if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
      return;
    }

    const all = getAllKnownStockList();
    const found = all.find(s => s.code.toUpperCase() === raw || s.code.toUpperCase().replace(/\s+/g, '') === raw.replace(/\s+/g, ''));
    if (found) {
      if (nameInput) {
        nameInput.value = found.name;
        highlightAutofill(nameInput);
      }
      if (currSelect && found.currency) currSelect.value = found.currency;
      if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
    } else if (raw.length >= 2) {
      // 온라인 검색으로 코드 -> 종목명 탐색
      api(`/api/stock-search?q=${encodeURIComponent(raw)}`).then(res => {
        if (res && res.found && res.name) {
          if (nameInput) {
            nameInput.value = res.name;
            highlightAutofill(nameInput);
          }
          if (currSelect && res.currency) currSelect.value = res.currency;
          RECENT_SEARCHED_STOCKS.set(raw, { code: res.code || raw, name: res.name, currency: res.currency || 'KRW' });
          populateStockDatalists();
          if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
        }
      }).catch(() => {});
    }
  }

  let searchTimer = null;
  let activeIndex = -1;
  let currentSuggestions = [];

  function getDropdown() {
    return nameInput?.parentElement?.querySelector(".stock-suggestions-dropdown");
  }

  function hideSuggestions() {
    const dropdown = getDropdown();
    if (dropdown) {
      dropdown.style.display = "none";
      dropdown.innerHTML = "";
    }
    currentSuggestions = [];
    activeIndex = -1;
  }

  function renderSuggestions(list, isIpo) {
    const dropdown = getDropdown();
    if (!dropdown) return;
    currentSuggestions = list || [];
    activeIndex = -1;
    if (!currentSuggestions.length) {
      dropdown.style.display = "none";
      dropdown.innerHTML = "";
      return;
    }

    dropdown.innerHTML = `
      <div class="stock-suggestions-header">
        <span>${isIpo ? '📦 공모주 종목 검색 결과' : '🔍 종목 검색 결과'} (${currentSuggestions.length})</span>
        <span class="stock-suggestions-hint">선택 시 종목코드/통화 자동 완성</span>
      </div>
      <div class="stock-suggestions-list">
        ${currentSuggestions.map((s, idx) => `
          <div class="stock-suggestion-item" data-index="${idx}">
            <div class="stock-suggestion-left">
              <span class="stock-suggestion-icon">${isIpo ? '📦' : '📈'}</span>
              <strong class="stock-suggestion-name">${html(s.name)}</strong>
            </div>
            <div class="stock-suggestion-right">
              <span class="stock-suggestion-code">${html(s.code)}</span>
              <span class="stock-suggestion-curr">${html(s.currency || 'KRW')}</span>
            </div>
          </div>
        `).join('')}
      </div>
    `;
    dropdown.style.display = "block";

    dropdown.querySelectorAll(".stock-suggestion-item").forEach(itemEl => {
      itemEl.addEventListener("mousedown", (e) => {
        e.preventDefault();
        const idx = Number(itemEl.dataset.index);
        selectSuggestion(currentSuggestions[idx]);
      });
      itemEl.addEventListener("mouseenter", () => {
        activeIndex = Number(itemEl.dataset.index);
        updateHighlight();
      });
    });
  }

  function updateHighlight() {
    const dropdown = getDropdown();
    if (!dropdown) return;
    const items = dropdown.querySelectorAll(".stock-suggestion-item");
    items.forEach((it, idx) => {
      if (idx === activeIndex) {
        it.classList.add("selected");
        it.scrollIntoView({ block: "nearest" });
      } else {
        it.classList.remove("selected");
      }
    });
  }

  function selectSuggestion(item) {
    if (!item) return;
    if (nameInput) nameInput.value = item.name;
    if (codeInput) {
      codeInput.value = item.code;
      highlightAutofill(codeInput);
    }
    if (currSelect && item.currency) {
      currSelect.value = item.currency;
    }
    hideSuggestions();

    RECENT_SEARCHED_STOCKS.set(item.code.toUpperCase(), { ...item });
    populateStockDatalists();

    if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
  }

  function onNameChanged(e) {
    const raw = (nameInput?.value || "").trim();
    if (!raw) {
      hideSuggestions();
      return;
    }

    const cleanRaw = raw.toLowerCase().replace(/\s+/g, '');
    const isIpo = (form.querySelector("[name='asset_type']")?.value === "ipo") || (form.querySelector("[name='is_ipo']")?.value === "true");

    // [중요] 이자 관련 키워드 우선 매칭 (화이자 주식 오매칭 완벽 방어)
    const INTEREST_KEYWORDS = {
      "원화이자": { code: "INTEREST_KRW", name: "원화이자", currency: "KRW" },
      "원화예탁금이용료": { code: "INTEREST_KRW", name: "원화이자", currency: "KRW" },
      "달러이자": { code: "INTEREST_USD", name: "달러이자", currency: "USD" },
      "외화이자": { code: "INTEREST_USD", name: "달러이자", currency: "USD" },
      "usd이자": { code: "INTEREST_USD", name: "달러이자", currency: "USD" },
      "rp이자": { code: "INTEREST_RP", name: "RP이자", currency: "KRW" },
      "예탁금이자": { code: "INTEREST_CASH", name: "예탁금이자", currency: "KRW" },
      "예탁금이용료": { code: "INTEREST_CASH", name: "예탁금이자", currency: "KRW" },
      "이자": { code: "INTEREST_KRW", name: "원화이자", currency: "KRW" },
    };

    if (INTEREST_KEYWORDS[cleanRaw]) {
      const match = INTEREST_KEYWORDS[cleanRaw];
      if (codeInput) codeInput.value = match.code;
      if (currSelect) currSelect.value = match.currency;
      hideSuggestions();
      if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
      return;
    }

    // 1. 로컬 저장된 목록에서 즉각 검색
    const all = getAllKnownStockList();
    const localMatches = all.filter(s => {
      const cleanStockName = s.name.toLowerCase().replace(/\s+/g, '');
      const cleanCode = s.code.toLowerCase().replace(/\s+/g, '');
      if (cleanStockName === '화이자' || cleanStockName.startsWith('화이자(')) {
        if (cleanRaw.includes('이자') && cleanRaw !== '화이자') return false;
      }
      return cleanStockName.includes(cleanRaw) || cleanCode.includes(cleanRaw);
    }).slice(0, 6);

    let exactMatch = all.find(s => {
      const cleanStockName = s.name.toLowerCase().replace(/\s+/g, '');
      if (cleanStockName === '화이자' || cleanStockName.startsWith('화이자(')) {
        if (cleanRaw.includes('이자') && cleanRaw !== '화이자') return false;
      }
      return cleanStockName === cleanRaw || s.name === raw;
    });

    if (exactMatch) {
      if (codeInput) {
        codeInput.value = exactMatch.code;
        highlightAutofill(codeInput);
      }
      if (currSelect && exactMatch.currency) currSelect.value = exactMatch.currency;
      if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
    }

    if (localMatches.length > 0 && nameInput === document.activeElement) {
      renderSuggestions(localMatches, isIpo);
    }

    // 2. 온라인 백엔드 검색 디바운스 (180ms) - 리센스메디컬 등 미색인 공모주 즉각 반영
    clearTimeout(searchTimer);
    const delay = (e && (e.type === 'change' || e.type === 'blur')) ? 0 : 180;
    searchTimer = setTimeout(async () => {
      try {
        const res = await api(`/api/stock-search?q=${encodeURIComponent(raw)}`);
        if (!res) return;

        const candidates = [];
        const seenCodes = new Set();

        if (res.suggestions && res.suggestions.length > 0) {
          res.suggestions.forEach(s => {
            if (!seenCodes.has(s.code.toUpperCase())) {
              seenCodes.add(s.code.toUpperCase());
              candidates.push(s);
            }
          });
        }
        localMatches.forEach(s => {
          if (!seenCodes.has(s.code.toUpperCase())) {
            seenCodes.add(s.code.toUpperCase());
            candidates.push(s);
          }
        });

        if (nameInput === document.activeElement && candidates.length > 0) {
          renderSuggestions(candidates.slice(0, 8), isIpo);
        }

        // 검색 성공 시 코드 입력칸 업데이트 (기존 코드와 무관하게 종목명에 맞추어 갱신)
        if (res.found && res.code) {
          if (codeInput) {
            codeInput.value = res.code;
            highlightAutofill(codeInput);
          }
          if (currSelect && res.currency) {
            currSelect.value = res.currency;
          }
          RECENT_SEARCHED_STOCKS.set(res.code.toUpperCase(), {
            code: res.code,
            name: res.name || raw,
            currency: res.currency || 'KRW',
          });
          populateStockDatalists();
          if (typeof form._stockUpdateFieldsFn === 'function') form._stockUpdateFieldsFn();
        }
      } catch (err) {}
    }, delay);
  }

  function onNameKeydown(e) {
    const dropdown = getDropdown();
    if (!dropdown || dropdown.style.display !== "block" || !currentSuggestions.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      activeIndex = (activeIndex + 1) % currentSuggestions.length;
      updateHighlight();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      activeIndex = (activeIndex - 1 + currentSuggestions.length) % currentSuggestions.length;
      updateHighlight();
    } else if (e.key === "Enter" || e.key === "Tab") {
      if (activeIndex >= 0 && activeIndex < currentSuggestions.length) {
        e.preventDefault();
        selectSuggestion(currentSuggestions[activeIndex]);
      } else if (currentSuggestions.length === 1 && e.key === "Enter") {
        e.preventDefault();
        selectSuggestion(currentSuggestions[0]);
      }
    } else if (e.key === "Escape") {
      hideSuggestions();
    }
  }

  if (!codeInput._boundAuto) {
    codeInput._boundAuto = true;
    codeInput.addEventListener("input", onCodeChanged);
    codeInput.addEventListener("change", onCodeChanged);
  }
  if (!nameInput._boundAuto) {
    nameInput._boundAuto = true;
    nameInput.addEventListener("input", onNameChanged);
    nameInput.addEventListener("change", onNameChanged);
    nameInput.addEventListener("keydown", onNameKeydown);
    nameInput.addEventListener("blur", () => {
      setTimeout(hideSuggestions, 250);
    });
  }
}

// ── 분할 날짜 입력 컴포넌트 자동 포커스 이동 및 동기화 (연도 4자리 -> 월 -> 일) ──
function setupAutoAdvancingDateInput(wrapSelector) {
  const wrap = typeof wrapSelector === "string" ? document.querySelector(wrapSelector) : wrapSelector;
  if (!wrap || wrap.dataset.autoAdvancingInit === "true") return;
  wrap.dataset.autoAdvancingInit = "true";

  const yearInput = wrap.querySelector(".date-part-year");
  const monthInput = wrap.querySelector(".date-part-month");
  const dayInput = wrap.querySelector(".date-part-day");
  const triggerBtn = wrap.querySelector(".date-picker-trigger");
  const nativeInput = wrap.querySelector("input[type='date']");

  if (!yearInput || !monthInput || !dayInput || !nativeInput) return;

  const origValDesc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  let isSyncingToNative = false;

  function syncToNative() {
    const y = (yearInput.value || "").trim();
    const m = (monthInput.value || "").trim();
    const d = (dayInput.value || "").trim();
    // 연도 4자리, 월 2자리, 일 2자리가 모두 완전하게 입력되었을 때만 네이티브로 동기화
    // (타이핑 도중 1자리 미완성 상태에서 padStart로 덮어씌워지는 순환 오류 원천 방지)
    if (y.length === 4 && m.length === 2 && d.length === 2) {
      const iso = `${y}-${m}-${d}`;
      isSyncingToNative = true;
      try {
        if (origValDesc) {
          origValDesc.set.call(nativeInput, iso);
        } else {
          nativeInput.value = iso;
        }
        nativeInput.dispatchEvent(new Event("input", { bubbles: true }));
        nativeInput.dispatchEvent(new Event("change", { bubbles: true }));
      } finally {
        isSyncingToNative = false;
      }
    }
  }

  function syncFromNative() {
    if (isSyncingToNative) return;
    const val = origValDesc ? origValDesc.get.call(nativeInput) : nativeInput.value;
    if (val && /^\d{4}-\d{2}-\d{2}$/.test(val)) {
      const [y, m, d] = val.split("-");
      yearInput.value = y;
      monthInput.value = m;
      dayInput.value = d;
    }
  }

  // nativeInput.value 프로퍼티 가로채기를 통해 프로그래밍 방식 값 변경 시에도 분할 입력칸 즉시 동기화
  if (origValDesc) {
    try {
      Object.defineProperty(nativeInput, "value", {
        get() {
          return origValDesc.get.call(this);
        },
        set(newVal) {
          origValDesc.set.call(this, newVal);
          if (!isSyncingToNative) {
            syncFromNative();
          }
        },
        configurable: true
      });
    } catch (e) {
      console.warn("Could not define property on native date input", e);
    }
  }

  function tryDistributeDateString(str) {
    if (!str) return false;
    const clean = str.trim();
    const m = clean.match(/^(\d{4})[-./]?(\d{1,2})[-./]?(\d{1,2})$/);
    if (m) {
      yearInput.value = m[1];
      monthInput.value = m[2].padStart(2, "0");
      dayInput.value = m[3].padStart(2, "0");
      syncToNative();
      dayInput.focus();
      return true;
    }
    return false;
  }

  // 래퍼 영역 클릭 시 빈 칸 또는 연도로 스마트 포커스
  wrap.addEventListener("click", (e) => {
    if (e.target === wrap || e.target.classList.contains("date-part-sep")) {
      if (!yearInput.value) {
        yearInput.focus();
      } else if (!monthInput.value) {
        monthInput.focus();
      } else if (!dayInput.value) {
        dayInput.focus();
      } else {
        yearInput.focus();
        yearInput.select();
      }
    }
  });

  // 포커스 시 전체 선택 (빠른 재입력 편의성)
  yearInput.addEventListener("focus", () => yearInput.select());
  monthInput.addEventListener("focus", () => monthInput.select());
  dayInput.addEventListener("focus", () => dayInput.select());

  // [핵심] 연도(Year): 4자리 숫자 입력 시 자동으로 월(Month) 입력칸으로 이동
  yearInput.addEventListener("input", () => {
    const raw = yearInput.value.replace(/\D/g, "");
    if (raw.length > 4) {
      if (tryDistributeDateString(raw)) return;
      yearInput.value = raw.slice(0, 4);
    } else {
      yearInput.value = raw;
    }
    if (yearInput.value.length === 4) {
      syncToNative();
      monthInput.focus();
      monthInput.select();
    }
  });

  yearInput.addEventListener("blur", () => {
    let raw = yearInput.value.replace(/\D/g, "");
    if (raw.length === 2) {
      yearInput.value = String(2000 + parseInt(raw, 10));
      syncToNative();
    }
  });

  yearInput.addEventListener("keydown", (e) => {
    if (["ArrowRight", "Enter", "/", "-", "."].includes(e.key)) {
      if (yearInput.value.length >= 2) {
        if (yearInput.value.length === 2) {
          yearInput.value = String(2000 + parseInt(yearInput.value, 10));
          syncToNative();
        }
        e.preventDefault();
        monthInput.focus();
        monthInput.select();
      }
    }
  });

  yearInput.addEventListener("paste", (e) => {
    const pasted = (e.clipboardData || window.clipboardData)?.getData("text");
    if (pasted && tryDistributeDateString(pasted)) {
      e.preventDefault();
    }
  });

  // 월(Month): 2자리 입력 시(또는 2~9 한자리 입력 시 0 자동 패딩) 자동으로 일(Day) 입력칸으로 이동
  monthInput.addEventListener("input", () => {
    let raw = monthInput.value.replace(/\D/g, "").slice(0, 2);
    // 2~9 입력 시 02~09로 자동 완성 후 바로 일(day)로 이동
    if (raw.length === 1 && parseInt(raw, 10) >= 2) {
      raw = "0" + raw;
      monthInput.value = raw;
      syncToNative();
      dayInput.focus();
      dayInput.select();
      return;
    }
    monthInput.value = raw;
    // 0 또는 1 입력 시에는 두 번째 자리 입력을 위해 즉시 sync하지 않고 대기
    if (raw.length === 2) {
      let num = parseInt(raw, 10);
      if (num > 12) num = 12;
      if (num < 1) num = 1;
      monthInput.value = String(num).padStart(2, "0");
      syncToNative();
      dayInput.focus();
      dayInput.select();
    }
  });

  monthInput.addEventListener("blur", () => {
    let raw = monthInput.value.replace(/\D/g, "");
    if (raw.length === 1) {
      let num = parseInt(raw, 10);
      if (num >= 1 && num <= 12) {
        monthInput.value = String(num).padStart(2, "0");
        syncToNative();
      }
    }
  });

  monthInput.addEventListener("keydown", (e) => {
    if (e.key === "Backspace" && !monthInput.value) {
      e.preventDefault();
      yearInput.focus();
      yearInput.setSelectionRange(yearInput.value.length, yearInput.value.length);
    } else if (e.key === "ArrowLeft" && monthInput.selectionStart === 0) {
      e.preventDefault();
      yearInput.focus();
      yearInput.setSelectionRange(yearInput.value.length, yearInput.value.length);
    } else if (["ArrowRight", "Enter", "/", "-", "."].includes(e.key)) {
      if (monthInput.value.length >= 1) {
        if (monthInput.value.length === 1) {
          monthInput.value = monthInput.value.padStart(2, "0");
          syncToNative();
        }
        e.preventDefault();
        dayInput.focus();
        dayInput.select();
      }
    }
  });

  // 일(Day): 2자리 입력 시 유효 범위 보정 및 동기화
  dayInput.addEventListener("input", () => {
    let raw = dayInput.value.replace(/\D/g, "").slice(0, 2);
    // 4~9는 어떤 월에도 10자리 수가 될 수 없으므로(31일까지 존재) 04~09로 즉시 패딩
    if (raw.length === 1 && parseInt(raw, 10) >= 4) {
      raw = "0" + raw;
      dayInput.value = raw;
      syncToNative();
      return;
    }
    dayInput.value = raw;
    // 0, 1, 2, 3 입력 시에는 10~31 등 두 번째 자리(예: 25일) 입력을 온전히 받기 위해 대기
    if (raw.length === 2) {
      let num = parseInt(raw, 10);
      const y = parseInt(yearInput.value, 10) || new Date().getFullYear();
      const m = parseInt(monthInput.value, 10) || (new Date().getMonth() + 1);
      const maxDays = new Date(y, m, 0).getDate();
      if (num > maxDays) num = maxDays;
      if (num < 1) num = 1;
      dayInput.value = String(num).padStart(2, "0");
      syncToNative();
    }
  });

  dayInput.addEventListener("blur", () => {
    let raw = dayInput.value.replace(/\D/g, "");
    if (raw.length === 1) {
      let num = parseInt(raw, 10);
      if (num >= 1 && num <= 31) {
        dayInput.value = String(num).padStart(2, "0");
        syncToNative();
      }
    }
  });

  dayInput.addEventListener("keydown", (e) => {
    if (e.key === "Backspace" && !dayInput.value) {
      e.preventDefault();
      monthInput.focus();
      monthInput.setSelectionRange(monthInput.value.length, monthInput.value.length);
    } else if (e.key === "ArrowLeft" && dayInput.selectionStart === 0) {
      e.preventDefault();
      monthInput.focus();
      monthInput.setSelectionRange(monthInput.value.length, monthInput.value.length);
    } else if (e.key === "Enter") {
      let raw = dayInput.value.replace(/\D/g, "");
      if (raw.length === 1) {
        let num = parseInt(raw, 10);
        if (num >= 1 && num <= 31) {
          dayInput.value = String(num).padStart(2, "0");
          syncToNative();
        }
      }
    }
  });

  // 마우스오버 툴팁 안내 (미설정 시 기본 주입)
  if (!yearInput.getAttribute("title")) yearInput.setAttribute("title", "마우스 휠로 연도 조절 가능");
  if (!monthInput.getAttribute("title")) monthInput.setAttribute("title", "마우스 휠로 월 조절 가능");
  if (!dayInput.getAttribute("title")) dayInput.setAttribute("title", "마우스 휠로 일 조절 가능");

  // [핵심] 마우스오버 상태에서 휠 회전 시 연도/월/일 실시간 증감 (모달/페이지 스크롤 방지: passive: false)
  yearInput.addEventListener("wheel", (e) => {
    e.preventDefault();
    let y = parseInt(yearInput.value, 10);
    if (isNaN(y) || y < 1900 || y > 2100) {
      y = new Date().getFullYear();
    }
    const step = e.deltaY < 0 ? 1 : -1;
    y = Math.min(2100, Math.max(1900, y + step));
    yearInput.value = String(y);

    if (!monthInput.value) {
      monthInput.value = String(new Date().getMonth() + 1).padStart(2, "0");
    }
    if (!dayInput.value) {
      dayInput.value = String(new Date().getDate()).padStart(2, "0");
    } else {
      const m = parseInt(monthInput.value, 10) || (new Date().getMonth() + 1);
      const maxDays = new Date(y, m, 0).getDate();
      let d = parseInt(dayInput.value, 10) || 1;
      if (d > maxDays) {
        dayInput.value = String(maxDays).padStart(2, "0");
      }
    }
    syncToNative();
  }, { passive: false });

  monthInput.addEventListener("wheel", (e) => {
    e.preventDefault();
    let m = parseInt(monthInput.value, 10);
    if (isNaN(m) || m < 1 || m > 12) {
      m = new Date().getMonth() + 1;
    }
    const step = e.deltaY < 0 ? 1 : -1;
    m = m + step;
    if (m > 12) m = 1;
    if (m < 1) m = 12;
    monthInput.value = String(m).padStart(2, "0");

    if (!yearInput.value) {
      yearInput.value = String(new Date().getFullYear());
    }
    if (!dayInput.value) {
      dayInput.value = String(new Date().getDate()).padStart(2, "0");
    } else {
      const y = parseInt(yearInput.value, 10) || new Date().getFullYear();
      const maxDays = new Date(y, m, 0).getDate();
      let d = parseInt(dayInput.value, 10) || 1;
      if (d > maxDays) {
        dayInput.value = String(maxDays).padStart(2, "0");
      }
    }
    syncToNative();
  }, { passive: false });

  dayInput.addEventListener("wheel", (e) => {
    e.preventDefault();
    if (!yearInput.value) {
      yearInput.value = String(new Date().getFullYear());
    }
    if (!monthInput.value) {
      monthInput.value = String(new Date().getMonth() + 1).padStart(2, "0");
    }
    const y = parseInt(yearInput.value, 10) || new Date().getFullYear();
    const m = parseInt(monthInput.value, 10) || (new Date().getMonth() + 1);
    const maxDays = new Date(y, m, 0).getDate();

    let d = parseInt(dayInput.value, 10);
    if (isNaN(d) || d < 1 || d > maxDays) {
      d = new Date().getDate();
    }
    const step = e.deltaY < 0 ? 1 : -1;
    d = d + step;
    if (d > maxDays) d = 1;
    if (d < 1) d = maxDays;
    dayInput.value = String(d).padStart(2, "0");
    syncToNative();
  }, { passive: false });

  // 캘린더 피커 버튼 클릭 시 네이티브 날짜 선택 팝업 오픈
  if (triggerBtn) {
    triggerBtn.addEventListener("click", (e) => {
      e.preventDefault();
      if (typeof nativeInput.showPicker === "function") {
        try {
          nativeInput.showPicker();
        } catch (err) {
          nativeInput.focus();
        }
      } else {
        nativeInput.focus();
      }
    });
  }

  nativeInput.addEventListener("change", () => {
    if (!isSyncingToNative) {
      syncFromNative();
    }
  });

  // 초기 로컬 동기화
  syncFromNative();

  wrap._syncFromNative = syncFromNative;
}

// 실제 배당금 기록 저장 함수
let isSubmittingDividend = false;
async function saveActualDividendRecord() {
  if (isSubmittingDividend) return;
  const form = document.getElementById("dividendRecordForm");
  if (!form) return;
  const rId = form.dataset.recordId;
  const dateVal = (form.querySelector("[name='date']")?.value || "").trim();
  const ownerVal = (form.querySelector("[name='owner']")?.value || "모두").trim();
  const brokerVal = (form.querySelector("[name='broker']")?.value || "").trim();
  const accountNameVal = (form.querySelector("[name='account_name']")?.value || "").trim();
  let codeVal = (form.querySelector("[name='code']")?.value || "").trim().toUpperCase();
  const nameVal = (form.querySelector("[name='name']")?.value || "").trim();
  let currVal = (form.querySelector("[name='currency']")?.value || "KRW").toUpperCase();
  const amtInput = form.querySelector("[name='amount']");
  const amtVal = Number(amtInput?.value || 0);
  const fxVal = Number(form.querySelector("[name='fx_rate']")?.value || 1385.0);
  let amtKrwVal = Number(form.querySelector("[name='amount_krw']")?.value || 0);
  if (!amtKrwVal && amtVal) {
    amtKrwVal = currVal === "USD" ? Math.round(amtVal * fxVal) : Math.round(amtVal);
  }
  const memoVal = (form.querySelector("[name='memo']")?.value || "").trim();

  if (!dateVal) {
    toast("입금일을 선택해 주세요.", true);
    return;
  }
  if (!nameVal && !codeVal) {
    toast("종목명 또는 종목코드를 입력해 주세요.", true);
    return;
  }
  if (!codeVal && nameVal) {
    try {
      const searchRes = await api(`/api/stock-search?q=${encodeURIComponent(nameVal)}`);
      if (searchRes && searchRes.code) {
        codeVal = searchRes.code;
        if (form.querySelector("[name='code']")) form.querySelector("[name='code']").value = codeVal;
        if (searchRes.currency && form.querySelector("[name='currency']")) {
          form.querySelector("[name='currency']").value = searchRes.currency;
          currVal = searchRes.currency;
        }
      }
    } catch (e) {}
  }
  if (!amtVal && (amtInput?.value === '' || amtInput?.value == null)) {
    toast("배당금(입금액)을 입력해 주세요.", true);
    return;
  }

  const payload = {
    date: dateVal,
    owner: ownerVal,
    broker: brokerVal,
    account_name: accountNameVal,
    code: codeVal,
    name: nameVal || codeVal,
    currency: currVal,
    amount: amtVal,
    fx_rate: fxVal,
    amount_krw: amtKrwVal,
    memo: memoVal,
  };

  // 현재 스크롤 위치 저장
  const savedScrollY = window.scrollY || window.pageYOffset || 0;
  const divDetailWrap = document.querySelector("#dividendMonthlyDetail .div-detail-grid, #dividendMonthlyDetail .detail-table-wrap");
  const savedTableScroll = divDetailWrap ? divDetailWrap.scrollTop : 0;

  isSubmittingDividend = true;
  try {
    const url = rId ? `/api/actual-dividends/${rId}` : "/api/actual-dividends";
    const method = rId ? "PUT" : "POST";
    const res = await api(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    document.getElementById("dividendRecordDialog")?.close();
    toast(res.message || "배당금이 저장되었습니다.");
    await loadActualDividends(currentOwner, selectedDividendYear);
    await updateOverviewCardsAllTime(currentOwner);
    if (typeof loadDividends === 'function') await loadDividends(currentOwner);

    // 스크롤 위치 복원
    window.scrollTo({ top: savedScrollY, behavior: "instant" });
    requestAnimationFrame(() => {
      window.scrollTo({ top: savedScrollY, behavior: "instant" });
      const newWrap = document.querySelector("#dividendMonthlyDetail .div-detail-grid, #dividendMonthlyDetail .detail-table-wrap");
      if (newWrap && savedTableScroll > 0) newWrap.scrollTop = savedTableScroll;
    });
  } catch (err) {
    toast(err.message, true);
  } finally {
    isSubmittingDividend = false;
  }
}

// 실제 배당금 파일 가져오기 폼 이벤트
const divImportForm = document.getElementById("dividendImportForm");
if (divImportForm) {
  divImportForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById("divImportFileInput");
    if (!fileInput || !fileInput.files.length) {
      toast("가져올 엑셀 또는 CSV 파일을 선택하세요.", true);
      return;
    }
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
      const res = await api("/api/import-dividends", {
        method: "POST",
        body: formData,
      });
      divImportForm.closest("dialog")?.close();
      fileInput.value = "";
      toast(res.message || "배당금 내역을 성공적으로 가져왔습니다.");
      await loadActualDividends(currentOwner);
      await updateOverviewCardsAllTime(currentOwner);
    } catch (err) {
      toast(err.message || "배당 파일 처리 실패", true);
    }
  });
}

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

// PWA 서비스 워커 등록 및 설치 지원
let deferredInstallPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredInstallPrompt = e;
  console.log("[PWA] beforeinstallprompt event fired! PWA is installable.");
  const btn = document.getElementById("pwaInstallButton");
  if (btn) btn.style.display = "inline-flex";
});

window.addEventListener("appinstalled", () => {
  deferredInstallPrompt = null;
  console.log("[PWA] PWA was installed successfully.");
  const btn = document.getElementById("pwaInstallButton");
  if (btn) btn.style.display = "none";
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" })
      .then((reg) => {
        reg.update();
        console.log("[PWA] Service Worker registered with scope:", reg.scope);
      })
      .catch((err) => console.error("[PWA] Service Worker registration failed:", err));
  });
}

function triggerPwaInstall() {
  if (deferredInstallPrompt) {
    deferredInstallPrompt.prompt();
    deferredInstallPrompt.userChoice.then((choiceResult) => {
      if (choiceResult.outcome === "accepted") {
        console.log("[PWA] User accepted install prompt");
      }
      deferredInstallPrompt = null;
    });
  } else {
    alert("현재 브라우저 환경에서는 [메뉴 ⋮] -> [앱 설치] 또는 [홈 화면에 추가]를 이용해 주세요.");
  }
}
window.triggerPwaInstall = triggerPwaInstall;

// ── 15. 배당(분배금) 현황 및 1월~12월 캘린더 ─────────────────────────────────────
// ── 15. 배당(분배금) 현황 및 1월~12월 캘린더 (예상 / 실제 모드 지원) ───────────
let currentDividendMode = 'estimated'; // 'estimated' | 'actual'
let dividendData = null;
let actualDividendData = null;
let selectedDividendMonth = null;
let selectedDividendYear = "2026";

async function loadDividends(owner = currentOwner) {
  try {
    const res = await api(`/api/dividends?owner=${encodeURIComponent(owner)}`);
    dividendData = res;
    if (currentDividendMode === 'estimated') {
      renderDividends(res);
    }
  } catch (err) {
    console.error("배당 정보를 불러오지 못했습니다.", err);
  }
}

async function loadActualDividends(owner = currentOwner, year = selectedDividendYear) {
  try {
    const res = await api(`/api/actual-dividends?owner=${encodeURIComponent(owner)}&year=${encodeURIComponent(year || '')}`);
    actualDividendData = res;
    if (currentDividendMode === 'actual') {
      renderActualDividends(res);
    }
    updateDividendYearOptions(res?.available_years || []);
  } catch (err) {
    console.error("실제 배당 정보를 불러오지 못했습니다.", err);
  }
}

function updateDividendYearOptions(years) {
  const sel = document.getElementById("dividendYearSelect");
  if (!sel) return;
  const currentVal = selectedDividendYear;
  const allYears = Array.from(new Set([new Date().getFullYear().toString(), ...years])).sort().reverse();
  
  const opts = allYears.map(y => `<option value="${y}">${y}년</option>`);
  opts.push('<option value="all">전체 기간</option>');
  sel.innerHTML = opts.join('');
  if (allYears.includes(currentVal) || currentVal === 'all') {
    sel.value = currentVal;
  }
}

function renderDividends(data) {
  if (!data) return;
  const fxUsd = (dashboard?.fx_rates?.USD) || 1385.0;

  $("#divCardLabel1") && ($("#divCardLabel1").textContent = "연간 예상 배당금");
  $("#divCardLabel2") && ($("#divCardLabel2").textContent = "포트폴리오 배당수익률");
  $("#divCardLabel3") && ($("#divCardLabel3").textContent = "월평균 예상 배당금");
  $("#divCardLabel4") && ($("#divCardLabel4").textContent = "배당 지급 종목 수");
  $("#dividendChartTitle") && ($("#dividendChartTitle").textContent = "📊 1월 ~ 12월 월별 예상 배당금 추이");

  // 1. 상단 4대 요약 카드
  const totalAnnual = Number(data.total_annual_dividend_krw || 0);
  const totalAnnualUsd = fxUsd > 0 ? (totalAnnual / fxUsd) : 0;
  const yieldRate = Number(data.portfolio_yield || 0);
  const monthlyAvg = Number(data.monthly_avg_dividend_krw || 0);
  const payingCount = Number(data.dividend_paying_count || 0);
  let totalHoldings = (dashboard?.holdings || []).length;
  if (currentOwner !== '모두') {
    totalHoldings = (dashboard?.holdings || []).filter(h => (h.owner || '모두') === currentOwner).length;
  }

  $("#divTotalAnnual") && ($("#divTotalAnnual").textContent = money(totalAnnual));
  $("#divTotalAnnualUsd") && ($("#divTotalAnnualUsd").textContent = `$${number(totalAnnualUsd, 2)} 환산 포함`);
  $("#divYield") && ($("#divYield").textContent = `${number(yieldRate, 2)}%`);
  $("#divYieldSub") && ($("#divYieldSub").textContent = "총 평가금액 대비");
  $("#divMonthlyAvg") && ($("#divMonthlyAvg").textContent = money(monthlyAvg));
  $("#divPayingCount") && ($("#divPayingCount").textContent = `${payingCount}개`);
  $("#divTotalHoldings") && ($("#divTotalHoldings").textContent = `전체 ${totalHoldings}개 종목 중`);

  // 핵심 요약 패널의 예상 연간 배당금 갱신
  $("#summaryEstimatedDividend") && ($("#summaryEstimatedDividend").textContent = `예상 연간 배당금 ${money(totalAnnual)} (${number(yieldRate, 2)}%)`);

  // 2. 1월~12월 월별 막대그래프 (SVG Bar Chart)
  const schedule = data.monthly_schedule || [];
  const maxMonthly = Math.max(...schedule.map(s => Number(s.total_krw || 0)), 1);

  const w = 900, h = 240, pad = 30;
  const hBarArea = 170;
  const barWidth = 44;

  const bars = schedule.map((item, idx) => {
    const m = item.month;
    const val = Number(item.total_krw || 0);
    const x = pad + ((w - pad * 2) * (idx + 0.5)) / 12 - barWidth / 2;
    const barH = val > 0 ? Math.max(8, (val / maxMonthly) * (hBarArea - 25)) : 2;
    const y = hBarArea - barH;
    const isSelected = selectedDividendMonth === m;

    const itemCount = (item.items || []).length;
    const topText = val > 0 ? money(val) : "-";
    const barFill = isSelected ? "url(#divBarGradActive)" : (val > 0 ? "url(#divBarGrad)" : "#1c263d");

    return `
      <g class="dividend-bar-group" data-month="${m}">
        <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="${barFill}" rx="4" opacity="0.95">
          <title>${m}월 예상 배당금: ${money(val)} (${itemCount}개 종목)</title>
        </rect>
        <text x="${(x + barWidth / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" fill="${val > 0 ? '#f3f5ff' : '#64748b'}" font-size="9.5" font-weight="700" text-anchor="middle">
          ${topText}
        </text>
        <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 16).toFixed(1)}" fill="${isSelected ? '#c4b5fd' : '#94a3b8'}" font-size="11" font-weight="${isSelected ? '700' : '600'}" text-anchor="middle">
          ${m}월
        </text>
        <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 28).toFixed(1)}" fill="${itemCount > 0 ? '#8e70fa' : '#475569'}" font-size="9" font-weight="600" text-anchor="middle">
          ${itemCount > 0 ? itemCount + '종목' : '-'}
        </text>
      </g>
    `;
  }).join('');

  const chartWrap = $("#dividendBarChartWrap");
  if (chartWrap) {
    chartWrap.innerHTML = `
      <svg class="record-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:240px;overflow:visible;">
        <defs>
          <linearGradient id="divBarGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#a78bfa" />
            <stop offset="100%" stop-color="#6366f1" />
          </linearGradient>
          <linearGradient id="divBarGradActive" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#38bdf8" />
            <stop offset="100%" stop-color="#818cf8" />
          </linearGradient>
        </defs>
        <line x1="${pad}" y1="${hBarArea}" x2="${w - pad}" y2="${hBarArea}" stroke="#283758" stroke-width="1.2" />
        ${bars}
      </svg>
    `;
  }

  renderMonthlyDividendDetail(selectedDividendMonth);
}

function renderMonthlyDividendDetail(month = null) {
  const container = $("#dividendMonthlyDetail");
  if (!container || !dividendData) return;

  const schedule = dividendData.monthly_schedule || [];
  let title = "전체 배당 지급 종목 (연간 기준)";
  let items = [];

  if (month && month >= 1 && month <= 12) {
    const monthData = schedule.find(s => s.month === month);
    title = `📅 ${month}월 예상 배당 지급 종목 (${(monthData?.items || []).length}개 종목 · 합계 ${money(monthData?.total_krw || 0)})`;
    items = monthData?.items || [];
  } else {
    title = `📅 전체 배당 지급 종목 (${(dividendData.holding_dividends || []).filter(h => h.annual_payout_krw > 0).length}개 종목 · 연간 합계 ${money(dividendData.total_annual_dividend_krw || 0)})`;
    items = (dividendData.holding_dividends || []).filter(h => h.annual_payout_krw > 0).map(h => ({
      code: h.code,
      name: h.name,
      quantity: h.quantity,
      currency: h.currency,
      payout_krw: h.annual_payout_krw,
      payout_orig: h.annual_payout_orig,
      div_yield: h.div_yield,
      months: h.payout_months,
    }));
  }

  if (!items.length) {
    const emptyMsg = month ? `${month}월에 지급 예정인 배당금 내역이 없습니다.` : `배당(분배금)을 지급하는 보유 종목이 없습니다. (무배당/성장형 종목)`;
    container.innerHTML = `
      <div class="div-detail-header">${title}</div>
      <div class="empty" style="padding:16px;">${emptyMsg}</div>
    `;
    return;
  }

  const cardsHtml = items.map(item => {
    const isUsd = item.currency === 'USD';
    const origText = isUsd ? `$${number(item.payout_orig, 2)}` : money(item.payout_krw);
    const cycleText = item.months ? (item.months.length === 12 ? '월배당' : (item.months.length === 4 ? '분기배당' : `${item.months.join(', ')}월`)) : '';

    return `
      <div class="div-item-card">
        <div class="div-item-info">
          <strong>${html(item.name)}</strong>
          <span>${html(item.code)} · ${number(item.quantity, 2)}주 ${cycleText ? '· ' + cycleText : ''}</span>
        </div>
        <div class="div-item-val">
          <strong>${money(item.payout_krw)}</strong>
          <small>${isUsd ? origText + ' · ' : ''}수익률 ${number(item.div_yield, 2)}%</small>
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = `
    <div class="div-detail-header">
      ${title}
      ${month ? '<button type="button" class="button text compact" id="clearDivMonthBtn" style="font-size:11px;margin-left:auto;">✕ 전체 보기</button>' : ''}
    </div>
    <div class="div-detail-grid">
      ${cardsHtml}
    </div>
  `;
}

function renderActualDividends(data) {
  if (!data) return;
  const fxUsd = (dashboard?.fx_rates?.USD) || 1385.0;
  const isAllYears = (selectedDividendYear === "all" || selectedDividendYear === "전체");

  $("#divCardLabel1") && ($("#divCardLabel1").textContent = isAllYears ? "누적 실제 수령 배당금" : "연간 실제 수령 배당금");
  $("#divCardLabel2") && ($("#divCardLabel2").textContent = "실제 수령 배당수익률");
  $("#divCardLabel3") && ($("#divCardLabel3").textContent = isAllYears ? "연평균 실제 수령액" : "월평균 실제 수령액");
  $("#divCardLabel4") && ($("#divCardLabel4").textContent = "실제 수령 종목 / 건수");
  $("#dividendChartTitle") && ($("#dividendChartTitle").textContent = isAllYears ? "📊 전체 기간 연도별 실제 배당금 입금 추이" : `📊 ${selectedDividendYear}년 1월 ~ 12월 월별 실제 배당금 입금 추이`);

  const totalActual = Number(data.total_actual_dividend_krw || 0);
  const totalActualUsd = fxUsd > 0 ? (totalActual / fxUsd) : 0;
  const totalVal = Number(dashboard?.summary?.total_value_krw || 0);
  const actualYield = totalVal > 0 ? (totalActual / totalVal * 100) : 0;
  
  // 전체 기간일 때는 가용 연도 수로 나눈 연평균, 단일 연도일 때는 12로 나눈 월평균
  const availYearsCount = (data.available_years || []).length || 1;
  const avgAmt = isAllYears ? (totalActual / availYearsCount) : Number(data.monthly_avg_dividend_krw || 0);
  const payingStockCount = Number(data.paying_stock_count || 0);
  const recordCount = Number(data.record_count || 0);

  $("#divTotalAnnual") && ($("#divTotalAnnual").textContent = money(totalActual));
  $("#divTotalAnnualUsd") && ($("#divTotalAnnualUsd").textContent = `$${number(totalActualUsd, 2)} 환산 포함`);
  $("#divYield") && ($("#divYield").textContent = `${number(actualYield, 2)}%`);
  $("#divYieldSub") && ($("#divYieldSub").textContent = "총 투자자산 대비");
  $("#divMonthlyAvg") && ($("#divMonthlyAvg").textContent = money(avgAmt));
  $("#divPayingCount") && ($("#divPayingCount").textContent = `${payingStockCount}종목`);
  $("#divTotalHoldings") && ($("#divTotalHoldings").textContent = `총 ${recordCount}건 입금`);

  const w = 900, h = 240, pad = 30;
  const hBarArea = 170;

  let bars = "";

  if (isAllYears) {
    // ── 전체 기간: 연도별 막대그래프 ──
    const yearlySchedule = data.yearly_schedule || [];
    const maxYearly = Math.max(...yearlySchedule.map(s => Number(s.total_krw || 0)), 1);
    const numYears = Math.max(yearlySchedule.length, 1);
    const barWidth = Math.min(64, Math.max(36, (w - pad * 2) / numYears - 28));

    bars = yearlySchedule.map((item, idx) => {
      const yr = String(item.year);
      const val = Number(item.total_krw || 0);
      const x = pad + ((w - pad * 2) * (idx + 0.5)) / numYears - barWidth / 2;
      const barH = val > 0 ? Math.max(8, (val / maxYearly) * (hBarArea - 25)) : 2;
      const y = hBarArea - barH;
      const itemCount = (item.items || []).length;
      const topText = val > 0 ? money(val) : "-";

      return `
        <g class="dividend-bar-group" data-year="${yr}" style="cursor:pointer;">
          <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="url(#actualDivBarGrad)" rx="5" opacity="0.95">
            <title>${yr}년 실제 배당금: ${money(val)} (${itemCount}건) - 클릭시 해당 연도 보기</title>
          </rect>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" fill="${val > 0 ? '#f43f5e' : '#64748b'}" font-size="10" font-weight="700" text-anchor="middle">
            ${topText}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 16).toFixed(1)}" fill="#cbd5e1" font-size="11.5" font-weight="700" text-anchor="middle">
            ${yr}년
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 29).toFixed(1)}" fill="${itemCount > 0 ? '#fb7185' : '#475569'}" font-size="9" font-weight="600" text-anchor="middle">
            ${itemCount > 0 ? itemCount + '건' : '-'}
          </text>
        </g>
      `;
    }).join("");
  } else {
    // ── 단일 연도: 1월 ~ 12월 월별 막대그래프 ──
    const schedule = data.monthly_schedule || [];
    const maxMonthly = Math.max(...schedule.map(s => Number(s.total_krw || 0)), 1);
    const barWidth = 44;

    bars = schedule.map((item, idx) => {
      const m = item.month;
      const val = Number(item.total_krw || 0);
      const x = pad + ((w - pad * 2) * (idx + 0.5)) / 12 - barWidth / 2;
      const barH = val > 0 ? Math.max(8, (val / maxMonthly) * (hBarArea - 25)) : 2;
      const y = hBarArea - barH;
      const isSelected = selectedDividendMonth === m;

      const itemCount = (item.items || []).length;
      const topText = val > 0 ? money(val) : "-";
      const barFill = isSelected ? "url(#actualDivBarGradActive)" : (val > 0 ? "url(#actualDivBarGrad)" : "#1c263d");

      return `
        <g class="dividend-bar-group" data-month="${m}" style="cursor:pointer;">
          <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="${barFill}" rx="4" opacity="0.95">
            <title>${m}월 실제 입금액: ${money(val)} (${itemCount}건)</title>
          </rect>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(y - 6).toFixed(1)}" fill="${val > 0 ? '#f43f5e' : '#64748b'}" font-size="9.5" font-weight="700" text-anchor="middle">
            ${topText}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 16).toFixed(1)}" fill="${isSelected ? '#f43f5e' : '#94a3b8'}" font-size="11" font-weight="${isSelected ? '700' : '600'}" text-anchor="middle">
            ${m}월
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${(hBarArea + 28).toFixed(1)}" fill="${itemCount > 0 ? '#fb7185' : '#475569'}" font-size="9" font-weight="600" text-anchor="middle">
            ${itemCount > 0 ? itemCount + '건' : '-'}
          </text>
        </g>
      `;
    }).join("");
  }

  const chartWrap = $("#dividendBarChartWrap");
  if (chartWrap) {
    chartWrap.innerHTML = `
      <svg class="record-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:240px;overflow:visible;">
        <defs>
          <linearGradient id="actualDivBarGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#fb7185" />
            <stop offset="100%" stop-color="#e11d48" />
          </linearGradient>
          <linearGradient id="actualDivBarGradActive" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#f43f5e" />
            <stop offset="100%" stop-color="#fda4af" />
          </linearGradient>
        </defs>
        <line x1="${pad}" y1="${hBarArea}" x2="${w - pad}" y2="${hBarArea}" stroke="#283758" stroke-width="1.2" />
        ${bars}
      </svg>
    `;
  }

  renderActualDividendDetail(selectedDividendMonth);
}

function renderActualDividendDetail(month = null) {
  const container = $("#dividendMonthlyDetail");
  if (!container || !actualDividendData) return;

  const records = actualDividendData.records || [];
  let title = "전체 실제 배당금 입금 내역";
  let items = [];

  if (month && month >= 1 && month <= 12) {
    const monthStr = String(month).padStart(2, '0');
    items = records.filter(r => (r.date || '').split('-')[1] === monthStr);
    const sumKrw = items.reduce((acc, cur) => acc + Number(cur.amount_krw || 0), 0);
    title = `📅 ${month}월 실제 배당금 입금 내역 (${items.length}건 · 합계 <span style="color:#f43f5e;">${money(sumKrw)}</span>)`;
  } else {
    items = [...records];
    const sumKrw = items.reduce((acc, cur) => acc + Number(cur.amount_krw || 0), 0);
    title = `📅 전체 실제 배당금 입금 내역 (${items.length}건 · 합계 <span style="color:#f43f5e;">${money(sumKrw)}</span>)`;
  }

  if (!items.length) {
    container.innerHTML = `
      <div class="div-detail-header">
        ${title}
        ${month ? '<button type="button" class="button text compact" id="clearDivMonthBtn" style="font-size:11px;margin-left:auto;">✕ 전체 보기</button>' : ''}
      </div>
      <div class="empty" style="padding:16px;">
        등록된 실제 배당금 내역이 없습니다. 상단의 <strong>[➕ 배당 추가]</strong> 또는 <strong>[📂 가져오기]</strong> 버튼으로 입금 내역을 기록해보세요.
      </div>
    `;
    return;
  }

  // 배당금 내역 컬럼 정렬 (보유종목과 동일 UX)
  items.sort((a, b) => {
    let valA, valB;
    if (currentDivSortField === 'date') {
      valA = a.date || '';
      valB = b.date || '';
      return currentDivSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    } else if (currentDivSortField === 'owner') {
      valA = a.owner || '모두';
      valB = b.owner || '모두';
      return currentDivSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    } else if (currentDivSortField === 'name') {
      valA = a.name || a.code || '';
      valB = b.name || b.code || '';
      return currentDivSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    } else if (currentDivSortField === 'amount') {
      valA = Number(a.amount || 0);
      valB = Number(b.amount || 0);
      return currentDivSortOrder === 'asc' ? valA - valB : valB - valA;
    } else if (currentDivSortField === 'amount_krw') {
      valA = Number(a.amount_krw || 0);
      valB = Number(b.amount_krw || 0);
      return currentDivSortOrder === 'asc' ? valA - valB : valB - valA;
    }
    return 0;
  });

  const rowsHtml = items.map(item => {
    const isUsd = item.currency === 'USD';
    const origAmt = isUsd ? `$${number(item.amount, 2)}` : money(item.amount_krw);
    const fxInfo = isUsd ? `<br><small class="td-fx-info">환율 ${number(item.fx_rate, 1)}원</small>` : '';

    return `
      <tr>
        <td class="center td-date">${html(item.date)}</td>
        <td class="center"><span class="td-owner-badge">${html(item.owner || '모두')}</span></td>
        <td class="td-stock-col">
          <strong class="td-stock-name">${html(item.name || item.code)}</strong>
          <div class="td-stock-code">${html(item.code || '')}</div>
        </td>
        <td class="center"><span class="td-currency">${html(item.currency || 'KRW')}</span></td>
        <td class="num td-orig-amt">${origAmt}${fxInfo}</td>
        <td class="num td-krw-amt pnl-gain-val" style="font-size:13.5px;font-weight:700;">${money(item.amount_krw)}</td>
        <td class="td-memo">${html(item.memo || '-')}</td>
        <td class="center" style="white-space:nowrap;">
          <div class="account-row-actions" style="justify-content:center;">
            <button class="account-action-button edit-actual-div-btn" data-id="${item.id}" title="배당 수정" type="button">✎</button>
            <button class="account-action-button mini-delete-button delete-actual-div-btn" data-id="${item.id}" title="배당 삭제" type="button">🗑️</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <div class="div-detail-header">
      ${title}
      ${month ? '<button type="button" class="button text compact" id="clearDivMonthBtn" style="font-size:11px;margin-left:auto;">✕ 전체 보기</button>' : ''}
    </div>
    <div class="detail-table-wrap">
      <table class="detail-table">
        <thead>
          <tr>
            <th class="center sortable-th ${currentDivSortField === 'date' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="date" style="width:95px;">입금일 <span class="sort-icon"></span></th>
            <th class="center sortable-th ${currentDivSortField === 'owner' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="owner" style="width:75px;">소유자 <span class="sort-icon"></span></th>
            <th class="sortable-th ${currentDivSortField === 'name' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="name">종목명 (코드) <span class="sort-icon"></span></th>
            <th class="center" style="width:60px;">통화</th>
            <th class="sortable-th ${currentDivSortField === 'amount' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="amount" style="text-align:right;width:115px;">입금액 <span class="sort-icon"></span></th>
            <th class="sortable-th ${currentDivSortField === 'amount_krw' ? (currentDivSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-div-sort="amount_krw" style="text-align:right;width:125px;">원화 환산금액 <span class="sort-icon"></span></th>
            <th>메모 / 계좌</th>
            <th class="center" style="width:65px;">관리</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>
  `;
}

async function fetchHistoricalFxRate(dateStr) {
  if (!dateStr) return (dashboard?.fx_rates?.USD) || 1385.0;
  try {
    const res = await api(`/api/historical-fx?date=${encodeURIComponent(dateStr)}`);
    return Number(res.rate || (dashboard?.fx_rates?.USD) || 1385.0);
  } catch (e) {
    return (dashboard?.fx_rates?.USD) || 1385.0;
  }
}

async function openDividendRecordDialog(record = null) {
  const dlg = document.getElementById("dividendRecordDialog");
  const form = document.getElementById("dividendRecordForm");
  if (!dlg || !form) return;

  form.reset();
  form.dataset.recordId = record ? record.id : "";
  $("#dividendDialogTitle") && ($("#dividendDialogTitle").textContent = record ? "실제 배당금 수정" : "실제 배당금 추가");

  // ACCOUNTS 섹션의 등록된 계좌 목록 드롭다운 및 데이터리스트 채우기
  const accounts = dashboard?.accounts || [];
  const acctSel = $("#dividendAccountSelect");
  if (acctSel) {
    acctSel.innerHTML = '<option value="">-- 직접 입력 또는 등록된 계좌 선택 --</option>' +
      accounts.map(a => `
        <option value="${html(a.id)}" data-broker="${html(a.broker)}" data-name="${html(a.name)}" data-owner="${html(a.owner || '모두')}">
          [${html(a.broker)}] ${html(a.name)} (${html(a.owner || '모두')})
        </option>
      `).join('');

    const matchedAcct = accounts.find(a => (record?.broker && a.broker === record.broker && record?.account_name && a.name === record.account_name) || (record?.account_id && a.id === record.account_id));
    acctSel.value = matchedAcct ? matchedAcct.id : "";
  }

  const acctDatalist = $("#divAccountDatalist");
  if (acctDatalist) {
    const uniqueNames = [...new Set(accounts.map(a => a.name).filter(Boolean))];
    acctDatalist.innerHTML = uniqueNames.map(name => `<option value="${html(name)}"></option>`).join('');
  }

  populateStockDatalists();
  attachStockAutoFill("dividendRecordForm", updateDivFormFields);
  setupAutoAdvancingDateInput("#divSplitDateWrap");

  const today = new Date().toISOString().slice(0, 10);
  const targetDate = record ? record.date : today;

  const dateEl = form.querySelector("[name='date']");
  const ownerEl = form.querySelector("[name='owner']");
  const brokerEl = form.querySelector("[name='broker']");
  const accEl = form.querySelector("[name='account_name']");
  const codeEl = form.querySelector("[name='code']");
  const nameEl = form.querySelector("[name='name']");
  const currEl = form.querySelector("[name='currency']");
  const amtEl = form.querySelector("[name='amount']");
  const fxEl = form.querySelector("[name='fx_rate']");
  const amtKrwEl = form.querySelector("[name='amount_krw']");
  const memoEl = form.querySelector("[name='memo']");

  if (dateEl) dateEl.value = targetDate;
  document.getElementById("divSplitDateWrap")?._syncFromNative?.();
  if (ownerEl) ownerEl.value = record ? (record.owner || "모두") : (currentOwner !== "모두" ? currentOwner : "모두");
  if (brokerEl) brokerEl.value = record ? (record.broker || "") : "";
  if (accEl) accEl.value = record ? (record.account_name || "") : "";
  if (codeEl) codeEl.value = record ? record.code : "";
  if (nameEl) nameEl.value = record ? record.name : "";
  if (currEl) currEl.value = record ? record.currency : "KRW";
  if (amtEl) amtEl.value = record ? record.amount : "";
  if (amtKrwEl) amtKrwEl.value = record ? record.amount_krw : "";
  if (memoEl) memoEl.value = record ? (record.memo || "") : "";

  if (record && record.fx_rate) {
    if (fxEl) fxEl.value = record.fx_rate;
  } else {
    const historicalFx = await fetchHistoricalFxRate(targetDate);
    if (fxEl) fxEl.value = historicalFx;
  }

  // 날짜 변경 시 해당 일자의 과거 환율 자동 조회
  if (dateEl && !dateEl.dataset.fxBound) {
    dateEl.dataset.fxBound = "true";
    dateEl.addEventListener("change", async () => {
      if (form.currency.value === "USD") {
        const rate = await fetchHistoricalFxRate(dateEl.value);
        if (form.fx_rate) form.fx_rate.value = rate;
        updateDivFormFields();
      }
    });
  }

  updateDivFormFields();
  dlg.showModal();
}

function updateDivFormFields() {
  const form = document.getElementById("dividendRecordForm");
  if (!form) return;
  const isUsd = form.currency.value === "USD";
  const fxField = document.getElementById("fxRateField");
  const krwField = document.getElementById("amountKrwField");
  if (fxField) fxField.style.display = isUsd ? "flex" : "none";
  if (krwField) krwField.style.display = isUsd ? "flex" : "none";

  const amt = Number(form.amount.value || 0);
  const fx = Number(form.fx_rate.value || (dashboard?.fx_rates?.USD) || 1385.0);
  if (isUsd) {
    form.amount_krw.value = Math.round(amt * fx);
  } else {
    form.amount_krw.value = Math.round(amt);
  }
}

// ── 16. 주식 매도 실현손익 관리 (Realized PnL) ──────────────────────────────
let pnlData = null;
let selectedPnlMonth = null;
let selectedPnlYear = "2026";
let currentPnlTradeType = "all"; // 'all' | 'ipo'

async function loadRealizedPnl(owner = currentOwner, year = selectedPnlYear, tradeType = currentPnlTradeType) {
  try {
    const res = await api(`/api/realized-pnl?owner=${encodeURIComponent(owner)}&year=${encodeURIComponent(year || '')}&trade_type=${encodeURIComponent(tradeType || 'all')}`);
    pnlData = res;
    renderRealizedPnl(res);
    updatePnlYearOptions(res?.available_years || []);

    // 실현손익 내 부동산 매도 기록을 부동산 탭 원장과 즉시 연동
    if (res?.records) {
      const registeredNames = (rawRealEstates || []).map(r => (r.name || '').trim()).filter(n => n.length >= 2);
      const reKw = /부동산|아파트|오피스텔|빌라|주택|단지|상가|토지|건물|원룸|분양권|재개발/i;
      const reRecords = res.records.filter(r => 
        r.asset_type === 'real_estate' || r.code === 'REAL_ESTATE' || r.broker === '부동산' ||
        (r.name && (r.name.includes('[부동산]') || r.name.includes('부동산') || registeredNames.some(rn => r.name.includes(rn)) || reKw.test(r.name)))
      );
      if (reRecords.length > 0) {
        renderRealEstate(rawRealEstates, currentOwner, null);
      }
    }
  } catch (err) {
    console.error("매도 실현손익을 불러오지 못했습니다.", err);
  }
}

function updatePnlYearOptions(years) {
  const sel = document.getElementById("pnlYearSelect");
  if (!sel) return;
  const currentVal = selectedPnlYear;
  const allYears = Array.from(new Set([new Date().getFullYear().toString(), ...years])).sort().reverse();
  
  const opts = allYears.map(y => `<option value="${y}">${y}년</option>`);
  opts.push('<option value="all">전체 기간</option>');
  sel.innerHTML = opts.join('');
  if (allYears.includes(currentVal) || currentVal === 'all') {
    sel.value = currentVal;
  }
}

function renderRealizedPnl(data) {
  if (!data) return;

  const totalPnl = Number(data.total_pnl_krw || 0);
  const totalWin = Number(data.total_win_krw || 0);
  const winCount = Number(data.win_count || 0);
  const totalLoss = Number(data.total_loss_krw || 0);
  const lossCount = Number(data.loss_count || 0);
  const winRate = Number(data.win_rate || 0);
  const recordCount = Number(data.record_count || 0);

  // 1. 4대 요약 카드
  const totalEl = $("#pnlTotal");
  if (totalEl) {
    totalEl.textContent = `${totalPnl > 0 ? '+' : ''}${money(totalPnl)}`;
    totalEl.className = `div-card-val ${totalPnl > 0 ? 'gain' : (totalPnl < 0 ? 'loss' : '')}`;
  }
  $("#pnlTotalCount") && ($("#pnlTotalCount").textContent = `총 ${recordCount}건 매도`);

  $("#pnlTotalWin") && ($("#pnlTotalWin").textContent = `+${money(totalWin)}`);
  $("#pnlWinCount") && ($("#pnlWinCount").textContent = `${winCount}건 실현`);

  $("#pnlTotalLoss") && ($("#pnlTotalLoss").textContent = `${money(totalLoss)}`);
  $("#pnlLossCount") && ($("#pnlLossCount").textContent = `${lossCount}건 실현`);

  const winRateEl = $("#pnlWinRate");
  if (winRateEl) {
    winRateEl.textContent = `${number(winRate, 1)}%`;
    winRateEl.className = `div-card-val ${winRate >= 50 ? 'gain' : ''}`;
  }

  // 2. 양방향 막대그래프 (SVG Bar Chart)
  const isAllYears = (selectedPnlYear === "all" || selectedPnlYear === "전체");
  const w = 900, h = 240, pad = 30;
  const zeroY = 120; // 0원 기준선 중앙
  const maxBarH = 80;

  let bars = "";

  if (isAllYears) {
    const yearlySchedule = data.yearly_schedule || [];
    const maxAbsPnl = Math.max(
      ...yearlySchedule.map(s => Math.abs(Number(s.total_krw || 0))),
      100000
    );
    const numYears = Math.max(yearlySchedule.length, 1);
    const barWidth = Math.min(64, Math.max(36, (w - pad * 2) / numYears - 28));

    bars = yearlySchedule.map((item, idx) => {
      const yr = String(item.year);
      const val = Number(item.total_krw || 0);
      const x = pad + ((w - pad * 2) * (idx + 0.5)) / numYears - barWidth / 2;
      const itemCount = (item.items || []).length;

      let barH = 2, y = zeroY - 1;
      let barFill = "#1c263d";
      let textY = zeroY - 8;

      if (val > 0) {
        barH = Math.max(6, (val / maxAbsPnl) * maxBarH);
        y = zeroY - barH;
        barFill = "url(#pnlGainBarGrad)";
        textY = y - 6;
      } else if (val < 0) {
        barH = Math.max(6, (Math.abs(val) / maxAbsPnl) * maxBarH);
        y = zeroY;
        barFill = "url(#pnlLossBarGrad)";
        textY = y + barH + 12;
      }

      const topText = val !== 0 ? `${val > 0 ? '+' : ''}${money(val)}` : '-';
      const textColor = val > 0 ? '#f43f5e' : (val < 0 ? '#38bdf8' : '#64748b');

      return `
        <g class="pnl-bar-group" data-year="${yr}" style="cursor:pointer;">
          <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="${barFill}" rx="4" opacity="0.95">
            <title>${yr}년 실현손익: ${money(val)} (${itemCount}건) - 클릭시 해당 연도 보기</title>
          </rect>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${textY.toFixed(1)}" fill="${textColor}" font-size="10" font-weight="700" text-anchor="middle">
            ${topText}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="215" fill="#cbd5e1" font-size="11.5" font-weight="700" text-anchor="middle">
            ${yr}년
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="228" fill="${itemCount > 0 ? '#fbbf24' : '#475569'}" font-size="9" font-weight="600" text-anchor="middle">
            ${itemCount > 0 ? itemCount + '건' : '-'}
          </text>
        </g>
      `;
    }).join('');
  } else {
    const schedule = data.monthly_schedule || [];
    const maxAbsPnl = Math.max(
      ...schedule.map(s => Math.abs(Number(s.total_krw || 0))),
      100000
    );
    const barWidth = 44;

    bars = schedule.map((item, idx) => {
      const m = item.month;
      const val = Number(item.total_krw || 0);
      const x = pad + ((w - pad * 2) * (idx + 0.5)) / 12 - barWidth / 2;
      const isSelected = selectedPnlMonth === m;
      const itemCount = (item.items || []).length;

      let barH = 2, y = zeroY - 1;
      let barFill = "#1c263d";
      let textY = zeroY - 8;

      if (val > 0) {
        barH = Math.max(6, (val / maxAbsPnl) * maxBarH);
        y = zeroY - barH;
        barFill = isSelected ? "url(#pnlGainBarGradActive)" : "url(#pnlGainBarGrad)";
        textY = y - 6;
      } else if (val < 0) {
        barH = Math.max(6, (Math.abs(val) / maxAbsPnl) * maxBarH);
        y = zeroY;
        barFill = isSelected ? "url(#pnlLossBarGradActive)" : "url(#pnlLossBarGrad)";
        textY = y + barH + 12;
      }

      const topText = val !== 0 ? `${val > 0 ? '+' : ''}${money(val)}` : '-';
      const textColor = val > 0 ? '#f43f5e' : (val < 0 ? '#38bdf8' : '#64748b');

      return `
        <g class="pnl-bar-group" data-month="${m}" style="cursor:pointer;">
          <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barH.toFixed(1)}" fill="${barFill}" rx="4" opacity="0.95">
            <title>${m}월 실현손익: ${money(val)} (${itemCount}건)</title>
          </rect>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="${textY.toFixed(1)}" fill="${textColor}" font-size="9.5" font-weight="700" text-anchor="middle">
            ${topText}
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="215" fill="${isSelected ? '#f59e0b' : '#94a3b8'}" font-size="11" font-weight="${isSelected ? '700' : '600'}" text-anchor="middle">
            ${m}월
          </text>
          <text x="${(x + barWidth / 2).toFixed(1)}" y="228" fill="${itemCount > 0 ? '#fbbf24' : '#475569'}" font-size="9" font-weight="600" text-anchor="middle">
            ${itemCount > 0 ? itemCount + '건' : '-'}
          </text>
        </g>
      `;
    }).join('');
  }

  const chartWrap = $("#pnlBarChartWrap");
  if (chartWrap) {
    chartWrap.innerHTML = `
      <svg class="record-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:240px;overflow:visible;">
        <defs>
          <linearGradient id="pnlGainBarGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#fb7185" />
            <stop offset="100%" stop-color="#e11d48" />
          </linearGradient>
          <linearGradient id="pnlGainBarGradActive" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#f43f5e" />
            <stop offset="100%" stop-color="#fda4af" />
          </linearGradient>
          <linearGradient id="pnlLossBarGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#0284c7" />
            <stop offset="100%" stop-color="#0369a1" />
          </linearGradient>
          <linearGradient id="pnlLossBarGradActive" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#38bdf8" />
            <stop offset="100%" stop-color="#7dd3fc" />
          </linearGradient>
        </defs>
        <!-- 0원 기준 중심선 -->
        <line x1="${pad}" y1="${zeroY}" x2="${w - pad}" y2="${zeroY}" stroke="#334155" stroke-dasharray="3 3" stroke-width="1.2" />
        <line x1="${pad}" y1="200" x2="${w - pad}" y2="200" stroke="#1e293b" stroke-width="1" />
        ${bars}
      </svg>
    `;
  }

  renderPnlMonthlyDetail(selectedPnlMonth);
}

function renderPnlMonthlyDetail(month = null) {
  const container = $("#pnlMonthlyDetail");
  if (!container || !pnlData) return;

  const allRecords = pnlData.records || [];
  const records = allRecords.filter(r => {
    const at = String(r.asset_type || '').toLowerCase();
    const c = String(r.code || '').toUpperCase();
    const b = String(r.broker || '').trim();
    const n = String(r.name || '');
    return at !== 'real_estate' && c !== 'REAL_ESTATE' && b !== '부동산' && !n.startsWith('[부동산]') && !r.re_id && !r.real_estate_name;
  });
  let title = "전체 매도 실현손익 내역";
  let items = [];

  if (month && month >= 1 && month <= 12) {
    const monthStr = String(month).padStart(2, '0');
    items = records.filter(r => (r.date || '').split('-')[1] === monthStr);
    const sumKrw = items.reduce((acc, cur) => acc + Number(cur.pnl_krw || 0), 0);
    title = `📅 ${month}월 매도 실현손익 내역 (${items.length}건 · 합계 ${sumKrw > 0 ? '+' : ''}${money(sumKrw)})`;
  } else {
    items = [...records];
    const sumKrw = items.reduce((acc, cur) => acc + Number(cur.pnl_krw || 0), 0);
    title = `📅 전체 매도 실현손익 내역 (${items.length}건 · 총합 ${sumKrw > 0 ? '+' : ''}${money(sumKrw)})`;
  }

  if (!items.length) {
    container.innerHTML = `
      <div class="div-detail-header">
        ${title}
        ${month ? '<button type="button" class="button text compact" id="clearPnlMonthBtn" style="font-size:11px;margin-left:auto;">✕ 전체 보기</button>' : ''}
      </div>
      <div class="empty" style="padding:16px;">
        등록된 매도 실현손익 내역이 없습니다. 상단의 <strong>[➕ 손익 추가]</strong> 또는 <strong>[📂 가져오기]</strong> 버튼으로 매도 기록을 등록해보세요.
      </div>
    `;
    return;
  }

  // 매도 실현손익 내역 컬럼 정렬 (보유종목과 동일 UX)
  items.sort((a, b) => {
    let valA, valB;
    if (currentPnlSortField === 'date') {
      valA = a.date || '';
      valB = b.date || '';
      return currentPnlSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    } else if (currentPnlSortField === 'owner') {
      valA = a.owner || '모두';
      valB = b.owner || '모두';
      return currentPnlSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    } else if (currentPnlSortField === 'name') {
      valA = a.name || a.code || '';
      valB = b.name || b.code || '';
      return currentPnlSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    } else if (currentPnlSortField === 'is_ipo') {
      valA = a.is_ipo ? '1' : (a.asset_type === 'real_estate' ? '2' : '0');
      valB = b.is_ipo ? '1' : (b.asset_type === 'real_estate' ? '2' : '0');
      return currentPnlSortOrder === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
    } else if (currentPnlSortField === 'pnl') {
      valA = Number(a.pnl || 0);
      valB = Number(b.pnl || 0);
      return currentPnlSortOrder === 'asc' ? valA - valB : valB - valA;
    } else if (currentPnlSortField === 'pnl_krw') {
      valA = Number(a.pnl_krw || 0);
      valB = Number(b.pnl_krw || 0);
      return currentPnlSortOrder === 'asc' ? valA - valB : valB - valA;
    }
    return 0;
  });

  const rowsHtml = items.map(item => {
    const isUsd = item.currency === 'USD';
    const pnlVal = Number(item.pnl_krw || 0);
    const sign = pnlVal > 0 ? '+' : '';
    const colorClass = pnlVal > 0 ? 'pnl-gain-val' : (pnlVal < 0 ? 'pnl-loss-val' : 'pnl-zero-val');
    const origText = isUsd ? `${Number(item.pnl) > 0 ? '+' : ''}$${number(item.pnl, 2)}` : '';
    const fxPnlVal = Number(item.fx_pnl_krw || 0);
    const fxPnlInfo = (isUsd && fxPnlVal !== 0) ? `<br><small style="color:#c4b5fd;">환차손익 ${fxPnlVal > 0 ? '+' : ''}${money(fxPnlVal)}</small>` : '';
    const fxInfo = isUsd ? `<br><small style="color:#8da0c7;">환율 ${number(item.fx_rate, 1)}원</small>${fxPnlInfo}` : '';

    let typeBadge = '<span class="td-normal-badge">일반거래</span>';
    if (item.asset_type === 'real_estate' || item.code === 'REAL_ESTATE') {
      typeBadge = '<span class="saving-type-badge badge-sold" style="background:rgba(245,158,11,0.18);color:#f59e0b;border:1px solid rgba(245,158,11,0.35);font-size:11px;padding:2px 6px;border-radius:4px;font-weight:700;">🏷️ 부동산</span>';
    } else if (item.is_ipo) {
      typeBadge = '<span class="td-ipo-badge">📦 공모주</span>';
    }

    return `
      <tr>
        <td class="center td-date">${html(item.date)}</td>
        <td class="center"><span class="td-owner-badge">${html(item.owner || '모두')}</span></td>
        <td class="td-stock-col">
          <strong class="td-stock-name">${html(item.name || item.code)}</strong>
          <div class="td-stock-code">${html(item.code || '')}</div>
        </td>
        <td class="center">
          ${typeBadge}
        </td>
        <td class="center"><span class="td-currency">${html(item.currency || 'KRW')}</span></td>
        <td class="num td-orig-amt">${isUsd ? origText : sign + money(item.pnl_krw)}${fxInfo}</td>
        <td class="num ${colorClass}" style="font-size:13.5px;font-weight:700;">${sign}${money(item.pnl_krw)}</td>
        <td class="td-memo">${html(item.memo || '-')}</td>
        <td class="center" style="white-space:nowrap;">
          <div class="account-row-actions" style="justify-content:center;">
            <button class="account-action-button edit-pnl-btn" data-id="${item.id}" title="손익 수정" type="button">✎</button>
            <button class="account-action-button mini-delete-button delete-pnl-btn" data-id="${item.id}" title="손익 삭제" type="button">🗑️</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');

  container.innerHTML = `
    <div class="div-detail-header">
      ${title}
      ${month ? '<button type="button" class="button text compact" id="clearPnlMonthBtn" style="font-size:11px;margin-left:auto;">✕ 전체 보기</button>' : ''}
    </div>
    <div class="detail-table-wrap">
      <table class="detail-table">
        <thead>
          <tr>
            <th class="center sortable-th ${currentPnlSortField === 'date' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="date" style="width:95px;">매도일 <span class="sort-icon"></span></th>
            <th class="center sortable-th ${currentPnlSortField === 'owner' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="owner" style="width:75px;">소유자 <span class="sort-icon"></span></th>
            <th class="sortable-th ${currentPnlSortField === 'name' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="name">종목명 (코드) <span class="sort-icon"></span></th>
            <th class="center sortable-th ${currentPnlSortField === 'is_ipo' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="is_ipo" style="width:85px;">유형 <span class="sort-icon"></span></th>
            <th class="center" style="width:60px;">통화</th>
            <th class="sortable-th ${currentPnlSortField === 'pnl' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="pnl" style="text-align:right;width:115px;">실현손익 <span class="sort-icon"></span></th>
            <th class="sortable-th ${currentPnlSortField === 'pnl_krw' ? (currentPnlSortOrder === 'asc' ? 'sort-asc' : 'sort-desc') : ''}" data-pnl-sort="pnl_krw" style="text-align:right;width:125px;">원화 환산손익 <span class="sort-icon"></span></th>
            <th>메모 / 계좌</th>
            <th class="center" style="width:65px;">관리</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>
  `;
}

function calcPnlReProfit() {
  const form = document.getElementById("pnlRecordForm");
  if (!form) return;
  const purch = Number(form.re_purchase_price?.value || 0);
  const sell = Number(form.re_sell_price?.value || 0);
  const exp = Number(form.re_expenses?.value || 0);
  const pnl = sell - purch - exp;

  const pnlInput = form.pnl;
  const pnlKrwInput = form.pnl_krw;
  if (pnlInput && (sell > 0 || purch > 0)) pnlInput.value = pnl;
  if (pnlKrwInput && (sell > 0 || purch > 0)) pnlKrwInput.value = pnl;

  const formulaEl = document.getElementById("pnlReCalcFormula");
  if (formulaEl) {
    formulaEl.textContent = `양도가 ₩${number(sell, 0)} - 취득가 ₩${number(purch, 0)} - 필요경비 ₩${number(exp, 0)} = ₩${number(pnl, 0)}`;
  }
}
window.calcPnlReProfit = calcPnlReProfit;

function onSelectPnlRealEstate() {
  const form = document.getElementById("pnlRecordForm");
  const sel = document.getElementById("pnlRealEstateSelect");
  if (!form || !sel) return;
  const reId = sel.value;
  if (!reId) return;

  const list = rawRealEstates || rawDashboard?.real_estates || [];
  const target = list.find(r => r.id === reId);
  if (!target) return;

  if (form.name) form.name.value = target.name || "";
  if (form.owner && target.owner) form.owner.value = target.owner;
  const purchPrice = Number(target.purchase_price || target.acquisition_price || target.current_price || 0);
  if (form.re_purchase_price) {
    form.re_purchase_price.value = purchPrice;
    if (typeof updateKoreanCurrencyHint === 'function') updateKoreanCurrencyHint(form.re_purchase_price);
  }
  calcPnlReProfit();
}
window.onSelectPnlRealEstate = onSelectPnlRealEstate;

function togglePnlAssetTypeFields() {
  const form = document.getElementById("pnlRecordForm");
  if (!form) return;
  const assetType = document.getElementById("pnlAssetTypeSelect")?.value || "stock";
  const isIpo = (assetType === "ipo");

  const brokerWrap = document.getElementById("pnlBrokerWrap");
  const acctNameWrap = document.getElementById("pnlAccountNameWrap");
  const codeWrap = document.getElementById("pnlCodeWrap");
  const acctSelWrap = document.getElementById("pnlAccountSelectWrap");
  const ipoWrap = document.getElementById("pnlIpoWrap");
  const currWrap = document.getElementById("pnlCurrencyWrap");
  const nameLabel = document.getElementById("pnlNameLabelText");

  if (brokerWrap) brokerWrap.style.display = "block";
  if (acctNameWrap) acctNameWrap.style.display = "block";
  if (codeWrap) codeWrap.style.display = "block";
  if (acctSelWrap) acctSelWrap.style.display = "block";
  if (currWrap) currWrap.style.display = "block";
  if (ipoWrap) ipoWrap.style.display = isIpo ? "none" : "block";
  if (nameLabel) nameLabel.textContent = isIpo ? "공모주 종목명" : "종목명";

  const nameInput = form.querySelector("[name='name']");
  const codeInput = form.querySelector("[name='code']");
  if (nameInput) {
    nameInput.placeholder = isIpo ? "예: 아이엠바이오로직스, 한패스, 리센스메디컬 (종목명 입력 시 자동 검색)" : "예: 삼성전자, 현대차, NVDA";
  }
  if (codeInput) {
    codeInput.placeholder = isIpo ? "예: 394420 (공모주명 입력 시 자동 완성)" : "예: 005930 (종목명 입력 시 자동 완성)";
  }

  const isIpoEl = form.querySelector("[name='is_ipo']");
  if (isIpoEl) isIpoEl.value = isIpo ? "true" : "false";
}
window.togglePnlAssetTypeFields = togglePnlAssetTypeFields;

async function openPnlRecordDialog(record = null) {
  const dlg = document.getElementById("pnlRecordDialog");
  const form = document.getElementById("pnlRecordForm");
  if (!dlg || !form) return;

  form.reset();
  form.dataset.recordId = record ? record.id : "";
  $("#pnlDialogTitle") && ($("#pnlDialogTitle").textContent = record ? "매도 실현손익 수정" : "매도 실현손익 추가");

  const assetTypeEl = document.getElementById("pnlAssetTypeSelect");
  if (assetTypeEl) {
    if (record) {
      assetTypeEl.value = record.asset_type || (record.is_ipo ? "ipo" : "stock");
    } else {
      assetTypeEl.value = (currentPnlTradeType === "ipo") ? "ipo" : "stock";
    }
  }
  togglePnlAssetTypeFields();

  // ACCOUNTS 섹션의 등록된 계좌 목록 드롭다운 및 데이터리스트 채우기
  const accounts = dashboard?.accounts || [];
  const acctSel = $("#pnlAccountSelect");
  if (acctSel) {
    acctSel.innerHTML = '<option value="">-- 직접 입력 또는 등록된 계좌 선택 --</option>' +
      accounts.map(a => `
        <option value="${html(a.id)}" data-broker="${html(a.broker)}" data-name="${html(a.name)}" data-owner="${html(a.owner || '모두')}">
          [${html(a.broker)}] ${html(a.name)} (${html(a.owner || '모두')})
        </option>
      `).join('');

    const matchedAcct = accounts.find(a => (record?.broker && a.broker === record.broker && record?.account_name && a.name === record.account_name) || (record?.account_id && a.id === record.account_id));
    acctSel.value = matchedAcct ? matchedAcct.id : "";
  }

  const acctDatalist = $("#pnlAccountDatalist");
  if (acctDatalist) {
    const uniqueNames = [...new Set(accounts.map(a => a.name).filter(Boolean))];
    acctDatalist.innerHTML = uniqueNames.map(name => `<option value="${html(name)}"></option>`).join('');
  }

  populateStockDatalists();
  attachStockAutoFill("pnlRecordForm", updatePnlFormFields);
  setupAutoAdvancingDateInput("#pnlSplitDateWrap");

  const today = new Date().toISOString().slice(0, 10);
  const targetDate = record ? record.date : today;

  const dateEl = form.querySelector("[name='date']");
  const ownerEl = form.querySelector("[name='owner']");
  const brokerEl = form.querySelector("[name='broker']");
  const accEl = form.querySelector("[name='account_name']");
  const codeEl = form.querySelector("[name='code']");
  const nameEl = form.querySelector("[name='name']");
  const currEl = form.querySelector("[name='currency']");
  const pnlEl = form.querySelector("[name='pnl']");
  const fxEl = form.querySelector("[name='fx_rate']");
  const pnlKrwEl = form.querySelector("[name='pnl_krw']");
  const isIpoEl = form.querySelector("[name='is_ipo']");
  const memoEl = form.querySelector("[name='memo']");

  if (dateEl) dateEl.value = targetDate;
  document.getElementById("pnlSplitDateWrap")?._syncFromNative?.();
  if (ownerEl) ownerEl.value = record ? (record.owner || "모두") : (currentOwner !== "모두" ? currentOwner : "모두");
  if (brokerEl) brokerEl.value = record ? (record.broker || "") : "";
  if (accEl) accEl.value = record ? (record.account_name || "") : "";
  if (codeEl) codeEl.value = record ? record.code : "";
  if (nameEl) nameEl.value = record ? record.name : "";
  if (currEl) currEl.value = record ? record.currency : "KRW";
  if (pnlEl) pnlEl.value = record ? record.pnl : "";
  if (pnlKrwEl) pnlKrwEl.value = record ? record.pnl_krw : "";
  if (isIpoEl) {
    if (record) {
      isIpoEl.value = record.is_ipo ? "true" : "false";
    } else {
      isIpoEl.value = (currentPnlTradeType === "ipo") ? "true" : "false";
    }
  }
  if (memoEl) memoEl.value = record ? (record.memo || "") : "";

  if (record && record.fx_rate) {
    if (fxEl) fxEl.value = record.fx_rate;
  } else {
    const historicalFx = await fetchHistoricalFxRate(targetDate);
    if (fxEl) fxEl.value = historicalFx;
  }

  // 날짜 변경 시 해당 일자의 과거 환율 자동 조회
  if (dateEl && !dateEl.dataset.fxBound) {
    dateEl.dataset.fxBound = "true";
    dateEl.addEventListener("change", async () => {
      if (form.currency.value === "USD") {
        const rate = await fetchHistoricalFxRate(dateEl.value);
        if (form.fx_rate) form.fx_rate.value = rate;
        updatePnlFormFields();
      }
    });
  }

  updatePnlFormFields();
  calcPnlReProfit();
  dlg.showModal();
}

function updatePnlFormFields() {
  const form = document.getElementById("pnlRecordForm");
  if (!form) return;
  const isUsd = form.currency.value === "USD";
  const fxField = document.getElementById("pnlFxRateField");
  const krwField = document.getElementById("pnlAmountKrwField");
  if (fxField) fxField.style.display = isUsd ? "flex" : "none";
  if (krwField) krwField.style.display = isUsd ? "flex" : "none";

  const pnl = Number(form.pnl.value || 0);
  const fx = Number(form.fx_rate.value || (dashboard?.fx_rates?.USD) || 1385.0);
  if (isUsd) {
    form.pnl_krw.value = Math.round(pnl * fx);
  } else {
    form.pnl_krw.value = Math.round(pnl);
  }
}

// 실현손익 단건 등록 폼 이벤트
let isSubmittingPnl = false;
async function saveRealizedPnlRecord() {
  if (isSubmittingPnl) return;
  const form = document.getElementById("pnlRecordForm");
  if (!form) return;
  const rId = form.dataset.recordId;
  const dateVal = (form.querySelector("[name='date']")?.value || "").trim();
  const ownerVal = (form.querySelector("[name='owner']")?.value || "모두").trim();
  const brokerVal = (form.querySelector("[name='broker']")?.value || "").trim();
  const accountNameVal = (form.querySelector("[name='account_name']")?.value || "").trim();
  let codeVal = (form.querySelector("[name='code']")?.value || "").trim().toUpperCase();
  const nameVal = (form.querySelector("[name='name']")?.value || "").trim();
  let currVal = (form.querySelector("[name='currency']")?.value || "KRW").toUpperCase();
  const pnlInputStr = form.querySelector("[name='pnl']")?.value;
  let pnlVal = Number(pnlInputStr || 0);
  const fxVal = Number(form.querySelector("[name='fx_rate']")?.value || 1385.0);
  let pnlKrwVal = Number(form.querySelector("[name='pnl_krw']")?.value || 0);
  if (!pnlKrwVal && pnlVal) {
    pnlKrwVal = currVal === "USD" ? Math.round(pnlVal * fxVal) : Math.round(pnlVal);
  }

  let assetTypeVal = form.querySelector("[name='asset_type']")?.value || "stock";
  const isIpoVal = (assetTypeVal === "ipo") || (form.querySelector("[name='is_ipo']")?.value === "true");
  const isRealEstate = (assetTypeVal === "real_estate");
  const memoVal = (form.querySelector("[name='memo']")?.value || "").trim();

  let purchVal = Number(form.querySelector("[name='re_purchase_price']")?.value || 0);
  let sellVal = Number(form.querySelector("[name='re_sell_price']")?.value || 0);
  let expVal = Number(form.querySelector("[name='re_expenses']")?.value || 0);

  if (isRealEstate && sellVal > 0 && purchVal > 0 && (!pnlVal || pnlVal === 0)) {
    pnlVal = Math.round(sellVal - purchVal - expVal);
    pnlKrwVal = pnlVal;
  }

  if (!dateVal) {
    toast("매도일을 선택해 주세요.", true);
    return;
  }
  if (isRealEstate) {
    if (!nameVal) {
      toast("부동산 명칭을 입력해 주세요.", true);
      return;
    }
    codeVal = "REAL_ESTATE";
    currVal = "KRW";
  } else {
    if (!nameVal && !codeVal) {
      toast("종목명 또는 종목코드를 입력해 주세요.", true);
      return;
    }
    if (!codeVal && nameVal) {
      try {
        const searchRes = await api(`/api/stock-search?q=${encodeURIComponent(nameVal)}`);
        if (searchRes && searchRes.code) {
          codeVal = searchRes.code;
          if (form.querySelector("[name='code']")) form.querySelector("[name='code']").value = codeVal;
          if (searchRes.currency && form.querySelector("[name='currency']")) {
            form.querySelector("[name='currency']").value = searchRes.currency;
            currVal = searchRes.currency;
          }
        }
      } catch (e) {}
    }
  }

  if (pnlInputStr === '' || pnlInputStr == null) {
    toast("실현손익을 입력해 주세요.", true);
    return;
  }

  const payload = {
    date: dateVal,
    owner: ownerVal,
    broker: isRealEstate ? "부동산" : brokerVal,
    account_name: isRealEstate ? "부동산 자산" : accountNameVal,
    code: codeVal,
    name: nameVal || codeVal,
    asset_type: assetTypeVal,
    currency: currVal,
    pnl: pnlVal,
    fx_rate: fxVal,
    fx_pnl_krw: 0,
    pnl_krw: pnlKrwVal,
    is_ipo: isIpoVal,
    memo: memoVal,
  };

  if (isRealEstate) {
    payload.purchase_price = purchVal;
    payload.sell_price = sellVal;
    payload.expenses = expVal;
    payload.real_estate_name = nameVal;
  }

  // 현재 스크롤 위치 저장 (윈도우 스크롤 및 세부 테이블 스크롤)
  const savedScrollY = window.scrollY || window.pageYOffset || 0;
  const pnlDetailWrap = document.querySelector("#pnlMonthlyDetail .detail-table-wrap");
  const savedTableScroll = pnlDetailWrap ? pnlDetailWrap.scrollTop : 0;

  isSubmittingPnl = true;
  try {
    const url = rId ? `/api/realized-pnl/${rId}` : "/api/realized-pnl";
    const method = rId ? "PUT" : "POST";
    const res = await api(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    document.getElementById("pnlRecordDialog")?.close();
    toast(res.message || "매도 실현손익이 저장되었습니다.");
    await loadDashboard();
    await loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType);
    renderRealEstateWithOwner(currentOwner);
    await updateOverviewCardsAllTime(currentOwner);

    // 스크롤 위치 완벽 복원
    window.scrollTo({ top: savedScrollY, behavior: "instant" });
    requestAnimationFrame(() => {
      window.scrollTo({ top: savedScrollY, behavior: "instant" });
      const newWrap = document.querySelector("#pnlMonthlyDetail .detail-table-wrap");
      if (newWrap && savedTableScroll > 0) newWrap.scrollTop = savedTableScroll;
    });
  } catch (err) {
    toast(err.message, true);
  } finally {
    isSubmittingPnl = false;
  }
}

document.querySelector("#pnlRecordForm [name='code']")?.addEventListener("input", (e) => {
  const form = document.getElementById("pnlRecordForm");
  if (!form) return;
  const val = e.target.value.trim().toUpperCase();
  const match = (dashboard?.holdings || []).find(h => h.code.toUpperCase() === val || h.name === val);
  if (match) {
    const nameEl = form.querySelector("[name='name']");
    const currEl = form.querySelector("[name='currency']");
    if (nameEl) nameEl.value = match.name;
    if (currEl) currEl.value = match.currency || "KRW";
    if (typeof updatePnlFormFields === 'function') updatePnlFormFields();
  }
});

document.querySelector("#pnlRecordForm [name='currency']")?.addEventListener("change", () => {
  if (typeof updatePnlFormFields === 'function') updatePnlFormFields();
});
document.querySelector("#pnlRecordForm [name='pnl']")?.addEventListener("input", () => {
  if (typeof updatePnlFormFields === 'function') updatePnlFormFields();
});
document.querySelector("#pnlRecordForm [name='fx_rate']")?.addEventListener("input", () => {
  if (typeof updatePnlFormFields === 'function') updatePnlFormFields();
});

// 실현손익 파일 가져오기 폼 이벤트
const pnlImportForm = document.getElementById("pnlImportForm");
if (pnlImportForm) {
  pnlImportForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById("pnlImportFileInput");
    if (!fileInput || !fileInput.files.length) {
      toast("가져올 엑셀 또는 CSV 파일을 선택하세요.", true);
      return;
    }
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
      const res = await api("/api/import-realized-pnl", {
        method: "POST",
        body: formData,
      });
      pnlImportForm.closest("dialog")?.close();
      fileInput.value = "";
      toast(res.message || "실현손익 내역을 성공적으로 가져왔습니다.");
      await loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType);
      await updateOverviewCardsAllTime(currentOwner);
    } catch (err) {
      toast(err.message || "실현손익 파일 처리 실패", true);
    }
  });
}

// 배당 연도 셀렉트 변경 이벤트
document.getElementById("dividendYearSelect")?.addEventListener("change", (e) => {
  selectedDividendYear = e.target.value;
  selectedDividendMonth = null;
  loadActualDividends(currentOwner, selectedDividendYear);
});

// 실현손익 연도 셀렉트 변경 이벤트
document.getElementById("pnlYearSelect")?.addEventListener("change", (e) => {
  selectedPnlYear = e.target.value;
  selectedPnlMonth = null;
  loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType);
});

// ── 화면 테마 관리 (Theme Switcher) ────────────────────────────────────────
function setAppTheme(theme) {
  const validThemes = ['purple', 'oled', 'white'];
  if (!validThemes.includes(theme)) theme = 'purple';

  if (theme === 'purple') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', theme);
  }

  document.querySelectorAll('#themeSwitcherTabs .theme-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.theme === theme);
  });

  try {
    localStorage.setItem('app_theme', theme);
  } catch (e) {}
}

function initAppTheme() {
  let savedTheme = 'purple';
  try {
    savedTheme = localStorage.getItem('app_theme') || 'purple';
  } catch (e) {}
  setAppTheme(savedTheme);
}

// ── 섹션 접기 / 펼치기 관리 (Accordion / Collapse) ───────────────────────────
const SECTION_MAP = {
  summary: '#summaryPanel',
  records: '#recordsPanel',
  heatmap: '#assetHeatmapPanel',
  dividend: '#dividendPanel',
  pnl: '#realizedPnlPanel',
  market: '#marketPanel',
  accounts: '#accountsPanel',
  holdings: '#holdingsPanel',
  ledger: '#ledgerSectionPanel'
};

function getCollapsedSections() {
  try {
    const raw = JSON.parse(localStorage.getItem('collapsed_sections') || '[]');
    if (!Array.isArray(raw)) return [];
    const validKeys = Object.keys(SECTION_MAP);
    const cleaned = raw.filter(k => validKeys.includes(k));
    if (cleaned.length !== raw.length) {
      saveCollapsedSections(cleaned);
    }
    return cleaned;
  } catch (e) {
    return [];
  }
}

function saveCollapsedSections(list) {
  try {
    localStorage.setItem('collapsed_sections', JSON.stringify(list));
  } catch (e) {}
}

function toggleSection(sectionKey) {
  if (!sectionKey || !SECTION_MAP[sectionKey]) return;
  let list = getCollapsedSections();
  const selector = SECTION_MAP[sectionKey];
  const panel = selector ? document.querySelector(selector) : null;
  const isCurrentlyCollapsed = panel ? panel.classList.contains('is-collapsed') : list.includes(sectionKey);
  const nextCollapsed = !isCurrentlyCollapsed;

  if (nextCollapsed) {
    if (!list.includes(sectionKey)) list.push(sectionKey);
  } else {
    list = list.filter(k => k !== sectionKey);
  }
  saveCollapsedSections(list);

  applySectionCollapsedState(sectionKey, nextCollapsed);
}

function applySectionCollapsedState(sectionKey, isCollapsed) {
  const selector = SECTION_MAP[sectionKey];
  const panel = selector ? document.querySelector(selector) : null;
  const btn = document.querySelector(`.section-collapse-btn[data-section="${sectionKey}"]`);

  if (btn) {
    btn.classList.toggle('is-collapsed', isCollapsed);
    btn.textContent = isCollapsed ? '▶' : '▼';
  }

  if (panel) {
    panel.classList.toggle('is-collapsed', isCollapsed);
    panel.querySelectorAll('.panel-head select, .panel-head button:not(.section-collapse-btn)').forEach(el => {
      if (el.id === 'syncAccountsButton' || el.id === 'refreshButton') {
        el.disabled = false;
        return;
      }
      el.disabled = isCollapsed;
    });

    // 섹션이 다시 펼쳐질 때 히트맵 리렌더링 (정확한 너비 반영)
    if (!isCollapsed && sectionKey === 'heatmap' && dashboard) {
      requestAnimationFrame(() => {
        renderHeatmaps(dashboard);
      });
    }
  }
}

function initCollapsedSections() {
  const list = getCollapsedSections();
  Object.keys(SECTION_MAP).forEach(key => {
    applySectionCollapsedState(key, list.includes(key));
  });
}

// 창 크기 변경 시 활성화된 히트맵 재계산
let heatmapResizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(heatmapResizeTimer);
  heatmapResizeTimer = setTimeout(() => {
    const p = document.querySelector('#heatmapPanel');
    if (p && !p.classList.contains('is-collapsed') && dashboard) {
      renderHeatmaps(dashboard);
    }
  }, 200);
});

// ── 21. 멀티유저 인증 세션 및 사용자 관리 (Admin) ───────────────────────────
let currentUserProfile = null;

async function initAuthSession() {
  try {
    console.log('[AUTH] 세션 검증 시작...');
    const me = await api('/api/auth/me');
    console.log('[AUTH] 로그인 사용자 정보:', me);
    currentUserProfile = me;
    
    // 1) 초기 비밀번호 상태이면 강제 변경 모달만 띄우고 모든 패널 가림
    if (me.must_change_password) {
      console.warn('[AUTH] 초기 비밀번호 강제 변경 상태 감지');
      const wrapper = document.getElementById('userAssetDashboardWrapper');
      if (wrapper) wrapper.style.display = 'none';
      const adminPanel = document.getElementById('adminMainPanel');
      if (adminPanel) adminPanel.style.display = 'none';

      const forceModal = document.getElementById('forcePasswordModal');
      if (forceModal) {
        if (!forceModal.open) {
          try { forceModal.showModal(); } catch (e) { forceModal.setAttribute('open', ''); }
        }
        forceModal.addEventListener('cancel', (e) => e.preventDefault()); // ESC 닫기 방지
      }
      return false; // 비밀번호 변경 전에는 자산/관리 데이터 로드 중단
    }

    // 2) 정상 계정이면 역할에 따라 화면 분기
    await applyUserRoleView(me);
    return true;
  } catch (err) {
    console.error('[AUTH] 세션 정보 확인 실패:', err);
    return false;
  }
}

async function applyUserRoleView(me) {
  if (!me) return;
  const isAdminUser = (me.username === 'admin');
  window.dispatchEvent(new CustomEvent('wealth:role', { detail: { isAdminUser } }));
  console.log('[AUTH] 화면 뷰 분기 적용 - isAdminUser:', isAdminUser, 'username:', me.username);

  // 상단 사용자명 표시
  const unameEl = document.getElementById('topbarUsername');
  if (unameEl) {
    unameEl.textContent = isAdminUser ? 'admin (시스템 관리자)' : me.username;
  }

  // 상단 타이틀 커스텀
  const brandTitle = document.querySelector('.topbar .title h1');
  const brandEyebrow = document.querySelector('.topbar .title p');
  if (brandTitle) {
    brandTitle.textContent = isAdminUser ? '👑 시스템 관리자 - 사용자 계정 관리' : '자산';
  }
  if (brandEyebrow) {
    brandEyebrow.textContent = isAdminUser ? 'SYSTEM ADMIN CONSOLE' : 'Wealth';
  }

  // 관리자 팝업 버튼: admin 계정(username === 'admin')으로 접속 시에만 노출 (sagesaint 등 계정은 완전 숨김)
  const adminBtn = document.getElementById('adminUserBtn');
  if (adminBtn) {
    const showAdminBtn = Boolean(me && me.username === 'admin');
    adminBtn.style.setProperty('display', showAdminBtn ? 'inline-flex' : 'none', 'important');
  }

  // 증권사 OpenAPI 설정 버튼 (admin은 숨김, 일반 자산 관리 유저에게 표시)
  const openApiBtn = document.getElementById('userOpenApiBtn');
  if (openApiBtn) {
    openApiBtn.style.display = isAdminUser ? 'none' : 'inline-flex';
  }

  // PWA 설치 버튼은 admin일 때 숨김
  const pwaBtn = document.getElementById('pwaInstallButton');
  if (pwaBtn && isAdminUser) {
    pwaBtn.style.display = 'none';
  }

  const assetWrapper = document.getElementById('userAssetDashboardWrapper');
  const adminMainPanel = document.getElementById('adminMainPanel');

  if (isAdminUser) {
    // 👑 admin 계정: 자산 관리 화면은 완전히 제외하고, 사용자 관리 화면만 노출!
    if (assetWrapper) assetWrapper.style.display = 'none';
    if (adminMainPanel) adminMainPanel.style.display = 'block';

    // 관리자 사용자 목록 및 통계 로드
    await refreshAdminUserList();
  } else {
    // 👤 일반 사용자/마스터 사용자(sagesaint 등): 자산 관리 화면 정상 노출
    if (adminMainPanel) adminMainPanel.style.display = 'none';
    if (assetWrapper) assetWrapper.style.display = '';

    // 일반 자산 데이터 로드
    await loadAssetDataForUser();
  }
}

async function loadAssetDataForUser() {
  const o = currentOwner || '모두';
  try { await loadFamilyMembers(); } catch (e) {}
  try { await loadDashboard(); } catch (e) { toast(e.message || "대시보드를 불러오지 못했습니다.", true); }
  try { await loadMarkets(); } catch (e) {}
  try { await loadAssetRecords(o); } catch (e) {}
  try { await loadDividends(o); } catch (e) {}
  try { await loadActualDividends(o, selectedDividendYear); } catch (e) {}
  try { await loadRealizedPnl(o, selectedPnlYear, currentPnlTradeType); } catch (e) {}
  try { await updateOverviewCardsAllTime(o); } catch (e) {}
}

async function handleForcePasswordSubmit(e) {
  if (e) e.preventDefault();
  const p1 = document.getElementById('forceNewPassword')?.value || '';
  const p2 = document.getElementById('forceNewPasswordConfirm')?.value || '';
  if (p1.length < 4) {
    alert('비밀번호는 최소 4자 이상이어야 합니다.');
    return;
  }
  if (p1 !== p2) {
    alert('비밀번호 확인이 일치하지 않습니다.');
    return;
  }
  try {
    await api('/api/auth/force-change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_password: p1 })
    });
    toast('새 비밀번호가 설정되었습니다! 화면으로 접속합니다.');
    const modal = document.getElementById('forcePasswordModal');
    if (modal) {
      try { modal.close(); } catch (e) { modal.removeAttribute('open'); }
    }
    if (currentUserProfile) {
      currentUserProfile.must_change_password = false;
      await applyUserRoleView(currentUserProfile);
    }
  } catch (err) {
    alert(err.message || '비밀번호 변경에 실패했습니다.');
  }
}
window.handleForcePasswordSubmit = handleForcePasswordSubmit;

function openChangePasswordModal() {
  const modal = document.getElementById('changePasswordModal');
  if (modal) {
    document.getElementById('changeOldPassword').value = '';
    document.getElementById('changeNewPassword').value = '';
    document.getElementById('changeNewPasswordConfirm').value = '';
    modal.showModal();
  }
}
window.openChangePasswordModal = openChangePasswordModal;

async function handleChangePasswordSubmit(e) {
  if (e) e.preventDefault();
  const oldP = document.getElementById('changeOldPassword')?.value || '';
  const p1 = document.getElementById('changeNewPassword')?.value || '';
  const p2 = document.getElementById('changeNewPasswordConfirm')?.value || '';
  if (p1.length < 4) {
    alert('새 비밀번호는 최소 4자 이상이어야 합니다.');
    return;
  }
  if (p1 !== p2) {
    alert('새 비밀번호가 일치하지 않습니다.');
    return;
  }
  try {
    await api('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_password: oldP, new_password: p1 })
    });
    toast('비밀번호가 성공적으로 변경되었습니다.');
    const modal = document.getElementById('changePasswordModal');
    if (modal) modal.close();
  } catch (err) {
    alert(err.message || '비밀번호 변경 실패');
  }
}
window.handleChangePasswordSubmit = handleChangePasswordSubmit;

async function openAdminUsersModal() {
  const modal = document.getElementById('adminUsersModal');
  if (!modal) return;
  modal.showModal();
  await refreshAdminUserList();
}
window.openAdminUsersModal = openAdminUsersModal;

async function refreshAdminUserList() {
  const tbodyMain = document.getElementById('adminMainUserListTbody');
  const tbodyDialog = document.getElementById('adminUserListTbody');

  const loadingHtml = '<tr><td colspan="5" class="admin-empty-cell">불러오는 중...</td></tr>';
  if (tbodyMain) tbodyMain.innerHTML = loadingHtml;
  if (tbodyDialog) tbodyDialog.innerHTML = loadingHtml;

  try {
    const res = await api('/api/admin/users');
    const users = res.users || [];
    console.log('[ADMIN] 사용자 목록 수신:', users);

    // 통계 카드 업데이트
    const statTotal = document.getElementById('adminStatTotalUsers');
    const statActive = document.getElementById('adminStatActiveUsers');
    const statPending = document.getElementById('adminStatPendingUsers');

    const totalCount = users.length;
    const pendingCount = users.filter(u => u.must_change_password).length;
    const activeCount = totalCount - pendingCount;

    if (statTotal) statTotal.textContent = `${totalCount}명`;
    if (statActive) statActive.textContent = `${activeCount}명`;
    if (statPending) statPending.textContent = `${pendingCount}명`;

    if (!users.length) {
      const emptyHtml = '<tr><td colspan="5" class="admin-empty-cell">등록된 사용자가 없습니다.</td></tr>';
      if (tbodyMain) tbodyMain.innerHTML = emptyHtml;
      if (tbodyDialog) tbodyDialog.innerHTML = emptyHtml;
      return;
    }

    const rowsHtml = users.map(u => {
      const isSelf = currentUserProfile && currentUserProfile.username === u.username;
      const isAdminRoot = (u.username === 'admin');
      const statusBadge = u.must_change_password 
        ? '<span class="admin-status-badge pending">⚠️ 비번 변경 필요</span>'
        : '<span class="admin-status-badge active">정상 활성</span>';

      const createdAtStr = u.created_at ? u.created_at.substring(0, 10) : '-';

      return `
        <tr class="admin-row">
          <td class="admin-cell-user">
            👤 ${escapeHtml(u.username)}
            ${isSelf ? '<span class="admin-self-badge">(나)</span>' : ''}
          </td>
          <td class="admin-cell-role">
            <span class="admin-role-badge ${u.role === 'admin' ? 'admin' : 'user'}">
              ${escapeHtml(u.role)}
            </span>
          </td>
          <td class="admin-cell-status">${statusBadge}</td>
          <td class="admin-cell-date">${createdAtStr}</td>
          <td class="admin-cell-actions">
            <div style="display:inline-flex;gap:8px;">
              <button type="button" class="button secondary compact admin-btn-reset" onclick="handleAdminResetUserPw('${escapeHtml(u.username)}')" title="초기 4자리 비밀번호로 재설정">
                🔑 비번 초기화(4자리)
              </button>
              ${isAdminRoot ? '' : `<button type="button" class="button secondary compact admin-btn-delete" onclick="handleAdminDeleteUser('${escapeHtml(u.username)}')" title="계정 및 데이터 삭제">
                🗑️ 삭제
              </button>`}
            </div>
          </td>
        </tr>
      `;
    }).join('');

    if (tbodyMain) tbodyMain.innerHTML = rowsHtml;
    if (tbodyDialog) tbodyDialog.innerHTML = rowsHtml;
  } catch (err) {
    console.error('[ADMIN] 사용자 목록 로드 실패:', err);
    const errHtml = `<tr><td colspan="5" class="admin-empty-cell" style="color:#ff718c;">목록 로드 실패: ${escapeHtml(err.message || String(err))}</td></tr>`;
    if (tbodyMain) tbodyMain.innerHTML = errHtml;
    if (tbodyDialog) tbodyDialog.innerHTML = errHtml;
  }
}

async function handleAdminCreateUser(e) {
  if (e) e.preventDefault();
  // 메인 화면 폼 또는 다이얼로그 폼에서 입력값 읽기
  const uname = (document.getElementById('adminMainNewUsername')?.value || document.getElementById('adminNewUsername')?.value || '').trim();
  const pw = (document.getElementById('adminMainNewPassword')?.value || document.getElementById('adminNewPassword')?.value || '').trim();

  if (!uname) {
    alert('사용자 아이디를 입력하세요.');
    return;
  }
  if (pw.length !== 4) {
    alert('초기 비밀번호는 정확히 4자리여야 합니다.');
    return;
  }
  try {
    const res = await api('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: uname, initial_password: pw })
    });
    toast(res.message || '사용자가 등록되었습니다.');

    // 폼 초기화
    if (document.getElementById('adminMainNewUsername')) document.getElementById('adminMainNewUsername').value = '';
    if (document.getElementById('adminMainNewPassword')) document.getElementById('adminMainNewPassword').value = '';
    if (document.getElementById('adminNewUsername')) document.getElementById('adminNewUsername').value = '';
    if (document.getElementById('adminNewPassword')) document.getElementById('adminNewPassword').value = '';

    await refreshAdminUserList();
  } catch (err) {
    alert(err.message || '사용자 생성 실패');
  }
}
window.handleAdminCreateUser = handleAdminCreateUser;

async function handleAdminResetUserPw(username) {
  const newPw = prompt(`[${username}] 계정의 초기 비밀번호(4자리)를 입력하세요:`, '0000');
  if (newPw === null) return;
  const cleanPw = newPw.trim();
  if (cleanPw.length !== 4) {
    alert('초기화 비밀번호는 정확히 4자리여야 합니다.');
    return;
  }
  try {
    const res = await api(`/api/admin/users/${encodeURIComponent(username)}/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_password: cleanPw })
    });
    toast(res.message || '비밀번호가 초기화되었습니다.');
    await refreshAdminUserList();
  } catch (err) {
    alert(err.message || '초기화 실패');
  }
}
window.handleAdminResetUserPw = handleAdminResetUserPw;

async function handleAdminDeleteUser(username) {
  if (!confirm(`정말로 사용자 '${username}' 계정과 해당 자산 데이터를 모두 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return;
  try {
    const res = await api(`/api/admin/users/${encodeURIComponent(username)}`, {
      method: 'DELETE'
    });
    toast(res.message || '사용자 계정이 삭제되었습니다.');
    await refreshAdminUserList();
  } catch (err) {
    alert(err.message || '삭제 실패');
  }
}
window.handleAdminDeleteUser = handleAdminDeleteUser;

// ── USER OPENAPI CONFIGURATION ──────────────────────────────────────────────
async function openUserOpenApiModal() {
  const modal = document.getElementById('userOpenApiModal');
  if (!modal) return;

  const statusMsg = document.getElementById('openapiStatusMsg');
  if (statusMsg) statusMsg.style.display = 'none';

  // 기존 폼 입력값 초기화
  const tossKey = document.getElementById('openapiTossKey');
  const tossSec = document.getElementById('openapiTossSecret');
  const kbKey = document.getElementById('openapiKbKey');
  const kbSec = document.getElementById('openapiKbSecret');
  const nhKey = document.getElementById('openapiNhKey');
  const nhSec = document.getElementById('openapiNhSecret');
  const kisKey = document.getElementById('openapiKisKey');
  const kisSec = document.getElementById('openapiKisSecret');
  const kisAcc = document.getElementById('openapiKisAccountNo');
  const kiwoomKey = document.getElementById('openapiKiwoomKey');
  const kiwoomSec = document.getElementById('openapiKiwoomSecret');
  const kiwoomAcc = document.getElementById('openapiKiwoomAccountNo');

  if (tossKey) tossKey.value = '';
  if (tossSec) tossSec.value = '';
  if (kbKey) kbKey.value = '';
  if (kbSec) kbSec.value = '';
  if (nhKey) nhKey.value = '';
  if (nhSec) nhSec.value = '';
  if (kisKey) kisKey.value = '';
  if (kisSec) kisSec.value = '';
  if (kisAcc) kisAcc.value = '';
  if (kiwoomKey) kiwoomKey.value = '';
  if (kiwoomSec) kiwoomSec.value = '';
  if (kiwoomAcc) kiwoomAcc.value = '';

  modal.showModal();

  try {
    const config = await api('/api/user/openapi-config');
    function updateBadge(badge, isConnected) {
      if (!badge) return;
      if (isConnected) {
        badge.textContent = '연결됨';
        badge.className = 'openapi-badge connected';
        badge.style.background = '';
        badge.style.color = '';
      } else {
        badge.textContent = '미연결';
        badge.className = 'openapi-badge disconnected';
        badge.style.background = '';
        badge.style.color = '';
      }
    }

    // 토스
    const tossBadge = document.getElementById('openapiTossBadge');
    const tossDelBtn = document.getElementById('openapiTossDeleteBtn');
    const tossConfigured = !!(config.toss && config.toss.configured);
    updateBadge(tossBadge, tossConfigured);
    if (tossConfigured) {
      if (tossDelBtn) tossDelBtn.style.display = 'inline-flex';
      if (tossKey) tossKey.value = config.toss.app_key || '';
      if (tossSec) tossSec.placeholder = '******** (등록됨 - 변경 시만 입력)';
    } else {
      if (tossDelBtn) tossDelBtn.style.display = 'none';
      if (tossSec) tossSec.placeholder = 'Client Secret 입력';
    }

    // KB
    const kbBadge = document.getElementById('openapiKbBadge');
    const kbDelBtn = document.getElementById('openapiKbDeleteBtn');
    const kbConfigured = !!(config.kb && config.kb.configured);
    updateBadge(kbBadge, kbConfigured);
    if (kbConfigured) {
      if (kbDelBtn) kbDelBtn.style.display = 'inline-flex';
      if (kbKey) kbKey.value = config.kb.app_key || '';
      if (kbSec) kbSec.placeholder = '******** (등록됨 - 변경 시만 입력)';
    } else {
      if (kbDelBtn) kbDelBtn.style.display = 'none';
      if (kbSec) kbSec.placeholder = 'KB App Secret 입력';
    }

    // NH (나무)
    const nhBadge = document.getElementById('openapiNhBadge');
    const nhDelBtn = document.getElementById('openapiNhDeleteBtn');
    const nhConfigured = !!(config.nh && config.nh.configured);
    updateBadge(nhBadge, nhConfigured);
    if (nhConfigured) {
      if (nhDelBtn) nhDelBtn.style.display = 'inline-flex';
      if (nhKey) nhKey.value = config.nh.app_key || '';
      if (nhSec) nhSec.placeholder = '******** (등록됨 - 변경 시만 입력)';
    } else {
      if (nhDelBtn) nhDelBtn.style.display = 'none';
      if (nhSec) nhSec.placeholder = '나무 App Secret 입력';
    }

    // KIS (한국투자증권)
    const kisBadge = document.getElementById('openapiKisBadge');
    const kisDelBtn = document.getElementById('openapiKisDeleteBtn');
    const kisConfigured = !!(config.kis && config.kis.configured);
    updateBadge(kisBadge, kisConfigured);
    if (kisConfigured) {
      if (kisDelBtn) kisDelBtn.style.display = 'inline-flex';
      if (kisKey) kisKey.value = config.kis.app_key || '';
      if (kisSec) kisSec.placeholder = '******** (등록됨 - 변경 시만 입력)';
      if (kisAcc) kisAcc.value = config.kis.account_no || '';
    } else {
      if (kisDelBtn) kisDelBtn.style.display = 'none';
      if (kisSec) kisSec.placeholder = '한투 App Secret 입력';
      if (kisAcc) kisAcc.value = (config.kis && config.kis.account_no) || '';
    }

    // Kiwoom (키움증권)
    const kiwoomBadge = document.getElementById('openapiKiwoomBadge');
    const kiwoomDelBtn = document.getElementById('openapiKiwoomDeleteBtn');
    const kiwoomConfigured = !!(config.kiwoom && config.kiwoom.configured);
    updateBadge(kiwoomBadge, kiwoomConfigured);
    if (kiwoomConfigured) {
      if (kiwoomDelBtn) kiwoomDelBtn.style.display = 'inline-flex';
      if (kiwoomKey) kiwoomKey.value = config.kiwoom.app_key || '';
      if (kiwoomSec) kiwoomSec.placeholder = '******** (등록됨 - 변경 시만 입력)';
      if (kiwoomAcc) kiwoomAcc.value = config.kiwoom.account_no || '';
    } else {
      if (kiwoomDelBtn) kiwoomDelBtn.style.display = 'none';
      if (kiwoomSec) kiwoomSec.placeholder = '키움 App Secret 입력';
      if (kiwoomAcc) kiwoomAcc.value = (config.kiwoom && config.kiwoom.account_no) || '';
    }
  } catch (err) {
    console.error('[OPENAPI] 설정 조회 실패:', err);
  }
}
window.openUserOpenApiModal = openUserOpenApiModal;

async function handleDeleteBrokerApi(broker) {
  const names = { toss: '토스증권', kb: 'KB증권', nh: '나무증권', kis: '한국투자증권', kiwoom: '키움증권' };
  const bname = names[broker] || broker;
  if (!confirm(`정말로 ${bname} OpenAPI 키와 시크릿을 삭제(연결 해제)하시겠습니까?`)) return;

  try {
    const res = await api(`/api/user/openapi-config/${encodeURIComponent(broker)}`, {
      method: 'DELETE'
    });
    toast(res.message || `${bname} OpenAPI 키가 삭제되었습니다.`);
    await openUserOpenApiModal();
  } catch (err) {
    alert(err.message || '삭제 실패');
  }
}
window.handleDeleteBrokerApi = handleDeleteBrokerApi;

async function handleSaveUserOpenApi(e) {
  if (e) e.preventDefault();
  const btn = document.getElementById('saveUserOpenApiBtn');
  const statusMsg = document.getElementById('openapiStatusMsg');

  const payload = {
    toss: {
      app_key: (document.getElementById('openapiTossKey')?.value || '').trim(),
      app_secret: (document.getElementById('openapiTossSecret')?.value || '').trim(),
    },
    kb: {
      app_key: (document.getElementById('openapiKbKey')?.value || '').trim(),
      app_secret: (document.getElementById('openapiKbSecret')?.value || '').trim(),
    },
    nh: {
      app_key: (document.getElementById('openapiNhKey')?.value || '').trim(),
      app_secret: (document.getElementById('openapiNhSecret')?.value || '').trim(),
    },
    kis: {
      app_key: (document.getElementById('openapiKisKey')?.value || '').trim(),
      app_secret: (document.getElementById('openapiKisSecret')?.value || '').trim(),
      account_no: (document.getElementById('openapiKisAccountNo')?.value || '').trim(),
    },
    kiwoom: {
      app_key: (document.getElementById('openapiKiwoomKey')?.value || '').trim(),
      app_secret: (document.getElementById('openapiKiwoomSecret')?.value || '').trim(),
      account_no: (document.getElementById('openapiKiwoomAccountNo')?.value || '').trim(),
    },
  };

  if (btn) {
    btn.disabled = true;
    btn.textContent = '저장 중...';
  }

  try {
    const res = await api('/api/user/openapi-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    toast(res.message || '증권사 OpenAPI 설정이 안전하게 저장되었습니다.');
    const modal = document.getElementById('userOpenApiModal');
    if (modal) modal.close();
  } catch (err) {
    if (statusMsg) {
      statusMsg.style.display = 'block';
      statusMsg.style.background = 'rgba(255,113,140,0.15)';
      statusMsg.style.color = '#ff718c';
      statusMsg.textContent = '저장 실패: ' + (err.message || String(err));
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '💾 설정 저장';
    }
  }
}
window.handleSaveUserOpenApi = handleSaveUserOpenApi;

function initSavingsListeners() {
  // 🏦 은행 계좌 모달 상단 카테고리 전환기 (자유통장 ↔ 예·적금 ↔ 대출)
  document.querySelectorAll('.bank-category-switcher').forEach(sel => {
    sel.addEventListener('change', (e) => {
      const nextType = e.target.value;
      closeDialog('bankAccountDialog');
      closeDialog('savingAccountDialog');
      closeDialog('loanAccountDialog');
      if (nextType === 'savings') {
        openSavingAccountDialog();
      } else if (nextType === 'loans') {
        openLoanAccountDialog();
      } else {
        openBankAccountDialog();
      }
    });
  });

  const savingForm = $("#savingAccountForm");
  if (savingForm) {
    savingForm.addEventListener("input", () => {
      updateSavingTypeFields();
      calcSavingInterestPreview();
    });
    savingForm.addEventListener("change", () => {
      updateSavingTypeFields();
      calcSavingInterestPreview();
    });
    $("#savingNoMaturityCheck")?.addEventListener("change", () => {
      updateSavingTypeFields();
      calcSavingInterestPreview();
    });

    savingForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(savingForm);
      const isNoMaturity = fd.get("saving_type") === "housing" || Boolean($("#savingNoMaturityCheck")?.checked);
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
        withdraw_account_id: fd.get("withdraw_account_id") || "",
        deposit_account_id: fd.get("deposit_account_id") || "",
        memo: fd.get("memo") || "",
      };

      try {
        await api("/api/savings-accounts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        toast("예·적금 상품이 저장되었습니다.");
        closeDialog("savingAccountDialog");
        await loadDashboard();
      } catch (err) {
        toast(err.message || "예·적금 저장 실패", true);
      }
    });
  }

  const bankForm = $("#bankAccountForm");
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
        await api("/api/bank-accounts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        toast("자유입출금 통장(마통) 정보가 저장되었습니다.");
        closeDialog("bankAccountDialog");
        await loadDashboard();
      } catch (err) {
        toast(err.message || "통장 저장 실패", true);
      }
    });

    ["bankBalanceInput", "bankLimitAmount", "bankInterestRate"].forEach(id => {
      document.getElementById(id)?.addEventListener("input", calcBankMinusPreview);
      document.getElementById(id)?.addEventListener("change", calcBankMinusPreview);
    });
  }

  const insForm = $("#insuranceAccountForm");
  if (insForm) {
    const handleInsuranceFormChange = () => {
      updateYellowUmbrellaFields();
      updatePensionPayoutFields();
    };
    insForm.addEventListener("input", handleInsuranceFormChange);
    insForm.addEventListener("change", handleInsuranceFormChange);

    $("#insuranceTypeSelect")?.addEventListener("change", (e) => {
      if (e.target.value === "national_pension") {
        const pRadio = $("#payoutTypeMonthlyPension");
        if (pRadio) pRadio.checked = true;
        const compInput = insForm.querySelector("[name='company_name']");
        if (compInput && !compInput.value.trim()) compInput.value = "국민연금공단";
        const prodInput = insForm.querySelector("[name='product_name']");
        if (prodInput && !prodInput.value.trim()) prodInput.value = "국민연금 (노령연금)";
        updatePensionPayoutFields();
      }
    });

    insForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(insForm);
      const pType = fd.get("payout_type") || "lump_sum";
      const mPayout = Number(fd.get("monthly_payout")) || 0;
      const pYears = Number(fd.get("payout_duration_years")) || 20;
      const convertedTotal = Math.round(mPayout * 12 * pYears);

      const yu_yearly_contributions = [];
      document.querySelectorAll("#yuYearlyList .yu-yearly-row").forEach(row => {
        const yr = (row.querySelector(".yu-yearly-year")?.value || "").trim();
        const dep = Number(row.querySelector(".yu-yearly-deposit")?.value) || 0;
        const ded = row.querySelector(".yu-yearly-deductible")?.value === "true";
        if (yr) {
          yu_yearly_contributions.push({ year: yr, deposit: dep, is_deductible: ded });
        }
      });

      const payload = {
        id: fd.get("id") || undefined,
        insurance_type: fd.get("insurance_type") || "protection",
        owner: fd.get("owner") || "모두",
        company_name: fd.get("company_name") || "",
        product_name: fd.get("product_name") || "",
        payment_status: fd.get("payment_status") || "paying",
        income_bracket: fd.get("income_bracket") || "40m_to_100m",
        marginal_tax_rate: Number(fd.get("marginal_tax_rate")) || 26.4,
        monthly_premium: Number(fd.get("monthly_premium")) || 0,
        total_paid_amount: Number(fd.get("total_paid_amount")) || 0,
        expected_amount: pType === "monthly_pension" ? convertedTotal : (Number(fd.get("expected_amount")) || 0),
        payout_type: pType,
        monthly_payout: mPayout,
        payout_duration_years: pYears,
        converted_total_asset: pType === "monthly_pension" ? convertedTotal : (Number(fd.get("expected_amount")) || 0),
        start_date: fd.get("start_date") || "",
        maturity_date: fd.get("maturity_date") || "",
        memo: fd.get("memo") || "",
        yearly_contributions: yu_yearly_contributions,
      };

      try {
        await api("/api/insurance-accounts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        toast("보험/연금/공제 상품이 저장되었습니다.");
        closeDialog("insuranceAccountDialog");
        await loadDashboard();
      } catch (err) {
        toast(err.message || "보험/연금 상품 저장 실패", true);
      }
    });

    // 연금/IRP 연도별 이력 관리 이벤트 (상단 입력값 -> 하단 이력에 추가/갱신)
    document.getElementById("addAccountYearlyBtn")?.addEventListener("click", (e) => {
      e.preventDefault();
      handleAddAccountYearly();
    });

    // 연도 입력창 변경 시 해당 연도 기존 이력 데이터 자동 로드 및 정규화
    document.getElementById("accountInputYear")?.addEventListener("change", (e) => {
      const rawYr = (e.target.value || "").trim();
      const yr = normalizeYear(rawYr);
      if (!yr) return;
      e.target.value = yr;
      const match = accountCurrentYearlyList.find(y => normalizeYear(y.year) === yr);
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
      refreshDialogKoreanHints(editForm);
    });

    document.getElementById("accountInputYear")?.addEventListener("blur", (e) => {
      const norm = normalizeYear(e.target.value);
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
          toast(`${removedYr}년 이력이 삭제되었습니다.`);

          // 상단 입력창이 삭제된 연도를 가리키고 있었다면 초기화하여 저장 시 부활 방지
          const editForm = document.getElementById("accountEditForm");
          const yrInput = editForm?.querySelector(".pension-entry-year");
          const depInput = editForm?.querySelector(".pension-annual-deposit");
          if (yrInput && normalizeYear(yrInput.value) === normalizeYear(removedYr)) {
            if (accountCurrentYearlyList.length > 0) {
              yrInput.value = accountCurrentYearlyList[0].year;
              if (depInput) depInput.value = accountCurrentYearlyList[0].deposit || "";
            } else {
              yrInput.value = String(new Date().getFullYear());
              if (depInput) depInput.value = "";
            }
            refreshDialogKoreanHints(editForm);
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
            refreshDialogKoreanHints($("#accountEditDialog"));
            depInput.focus();
            depInput.select();
          }
          if (dedInput) dedInput.value = (item.is_deductible !== false && String(item.is_deductible) !== "false") ? "true" : "false";
          if (incInput) incInput.value = item.income_level || "low";

          setEditingAccountYearlyBtn(item.year || "");
          updateAccountTaxBenefitFields(editForm);
          toast(`[${item.year}년] 수정 모드: 연도나 납입액을 변경한 후 [수정 반영] 또는 하단 [저장]을 눌러주세요.`);
        }
        return;
      }
    });

    // 노란우산공제 연도별 이력 관리 이벤트
    document.getElementById("addYuYearlyBtn")?.addEventListener("click", () => {
      const years = yuCurrentYearlyList.map(y => Number(y.year) || 2024);
      const nextYr = years.length > 0 ? Math.min(...years) - 1 : 2024;
      yuCurrentYearlyList.push({ year: nextYr, deposit: 2400000, is_deductible: true });
      renderYuYearlyFormRows();
    });

    const handleYuYearlyRowChange = (e) => {
      const row = e.target.closest(".yu-yearly-row");
      if (!row) return;
      const idx = Number(row.dataset.index);
      if (yuCurrentYearlyList[idx]) {
        yuCurrentYearlyList[idx].year = row.querySelector(".yu-yearly-year")?.value || "";
        yuCurrentYearlyList[idx].deposit = Number(row.querySelector(".yu-yearly-deposit")?.value) || 0;
        yuCurrentYearlyList[idx].is_deductible = row.querySelector(".yu-yearly-deductible")?.value === "true";
        renderYuYearlyFormRows();
      }
    };
    document.getElementById("yuYearlyList")?.addEventListener("change", handleYuYearlyRowChange);

    document.getElementById("yuYearlyList")?.addEventListener("click", (e) => {
      const delBtn = e.target.closest(".yu-yearly-del-btn");
      if (!delBtn) return;
      const idx = Number(delBtn.dataset.index);
      if (!isNaN(idx)) {
        yuCurrentYearlyList.splice(idx, 1);
        renderYuYearlyFormRows();
      }
    });
  }

  // 증권 계좌 추가 및 수정 폼 실시간 절세 프리뷰 이벤트 바인딩
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

  const loanForm = $("#loanAccountForm");
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
        await api("/api/loan-accounts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        toast("대출·마이너스통장이 저장되었습니다.");
        closeDialog("loanAccountDialog");
        await loadDashboard();
      } catch (err) {
        toast(err.message || "대출·마이너스통장 저장 실패", true);
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

  const reForm = $("#realEstateForm");
  if (reForm) {
    reForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData(reForm);
      const linkedLoanId = fd.get("linked_loan_ids");
      const linkedLoanIds = linkedLoanId ? [linkedLoanId] : [];

      const isJoint = Boolean(document.getElementById("reIsJointCheck")?.checked);
      const ownerships = [];
      if (isJoint) {
        document.querySelectorAll("#reJointRows .re-joint-row").forEach(row => {
          const mOwner = row.querySelector(".re-joint-owner-select")?.value;
          const mRatio = Number(row.querySelector(".re-joint-ratio-input")?.value || 0);
          if (mOwner && mRatio > 0) {
            ownerships.push({ owner: mOwner, ratio: mRatio });
          }
        });
      }

      const payload = {
        id: fd.get("id") || undefined,
        property_type: fd.get("property_type") || "own",
        owner: fd.get("owner") || "모두",
        name: fd.get("name") || "",
        dong_ho: fd.get("dong_ho") || "",
        address: fd.get("address") || "",
        is_joint_ownership: isJoint,
        ownerships: ownerships,
        purchase_price: Number(fd.get("purchase_price")) || 0,
        current_price: Number(fd.get("current_price")) || 0,
        deposit_amount: Number(fd.get("deposit_amount")) || 0,
        monthly_rent: Number(fd.get("monthly_rent")) || 0,
        contract_date: fd.get("contract_date") || "",
        expiry_date: fd.get("expiry_date") || "",
        exclusive_area: Number(fd.get("exclusive_area")) || 0,
        kb_complex_no: fd.get("kb_complex_no") || "",
        linked_loan_ids: linkedLoanIds,
        memo: fd.get("memo") || "",
      };

      try {
        await api("/api/real-estates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        toast("부동산 자산 정보가 저장되었습니다.");
        closeDialog("realEstateDialog");
        await loadDashboard();
      } catch (err) {
        toast(err.message || "부동산 자산 저장 실패", true);
      }
    });

    $("#reTypeSelect")?.addEventListener("change", updateRealEstateTypeFields);
    ["rePurchasePrice", "reCurrentPrice", "reDepositAmount", "reLinkedLoansSelect"].forEach(id => {
      document.getElementById(id)?.addEventListener("input", calcRealEstatePreview);
      document.getElementById(id)?.addEventListener("change", calcRealEstatePreview);
    });

    // KB시세 조회 버튼 리스너
    document.getElementById("reFetchKbBtn")?.addEventListener("click", fetchKbMarketPrice);

    // KB시세 적용 버튼 리스너
    document.getElementById("reApplyKbPriceBtn")?.addEventListener("click", () => {
      const typeSelect = document.getElementById("reKbTypeSelect");
      const currInput = document.getElementById("reCurrentPrice");
      if (typeSelect && currentKbTypes.length && currInput) {
        const selectedIdx = Number(typeSelect.value || 0);
        const selType = currentKbTypes[selectedIdx];
        if (selType && selType.deal_avg > 0) {
          currInput.value = selType.deal_avg;
          updateKoreanCurrencyHint(currInput);
          calcRealEstatePreview();
          toast(`KB시세(₩${number(selType.deal_avg, 0)})가 현재 시세에 적용되었습니다.`);
        }
      }
    });

    // KB 평형 선택 변경 리스너
    document.getElementById("reKbTypeSelect")?.addEventListener("change", (e) => {
      const idx = Number(e.target.value || 0);
      const selType = currentKbTypes[idx];
      const resultDetail = document.getElementById("reKbResultDetail");
      const name = document.getElementById("reNameInput")?.value || "";
      if (selType && resultDetail) {
        resultDetail.innerHTML = `
          <strong>단지</strong>: ${html(name)} 
          <span style="color:#facc15;">[${html(selType.type_display)}]</span><br/>
          <strong>KB 매매 일반평균가</strong>: <span style="font-size:13px;font-weight:700;color:#38bdf8;">₩${number(selType.deal_avg, 0)}</span><br/>
          <small style="color:#94a3b8;">하한가 ₩${number(selType.deal_low, 0)} ~ 상한가 ₩${number(selType.deal_high, 0)} · 전세 ₩${number(selType.lease_avg, 0)}</small>
        `;
      }
    });

    // 공동명의 체크박스 토글 리스너
    document.getElementById("reIsJointCheck")?.addEventListener("change", (e) => {
      const checked = e.target.checked;
      const singleWrap = document.getElementById("reSingleOwnerWrap");
      const jointWrap = document.getElementById("reJointOwnershipWrap");
      if (singleWrap) singleWrap.style.display = checked ? "none" : "block";
      if (jointWrap) jointWrap.style.display = checked ? "block" : "none";
      if (checked) {
        const rows = document.querySelectorAll("#reJointRows .re-joint-row");
        if (!rows.length) renderJointOwnershipRows();
      }
    });

    // 공동명의 행 추가 버튼 리스너
    document.getElementById("reAddJointRowBtn")?.addEventListener("click", () => {
      const container = document.getElementById("reJointRows");
      if (!container) return;
      const members = (typeof familyMembers !== 'undefined' && familyMembers && familyMembers.length) 
        ? familyMembers 
        : ['아빠', '엄마', '자녀'];
      const div = document.createElement("div");
      div.className = "re-joint-row";
      div.style.cssText = "display:flex;align-items:center;gap:8px;";
      div.innerHTML = `
        <select class="re-joint-owner-select" style="flex:1;">
          ${members.map(m => `<option value="${m}">${m}</option>`).join('')}
        </select>
        <div style="display:flex;align-items:center;gap:4px;width:110px;">
          <input type="number" class="re-joint-ratio-input" value="50" min="1" max="100" step="1" style="width:70px;text-align:right;" />
          <span style="font-size:12px;color:#94a3b8;">%</span>
        </div>
        <button type="button" class="mini-delete-button re-joint-del-btn" title="삭제" style="padding:2px 6px;">×</button>
      `;
      container.appendChild(div);
      updateJointTotalRatio();
    });

    // 공동명의 행 삭제 및 지분율 입력 이벤트 위임
    document.getElementById("reJointRows")?.addEventListener("click", (e) => {
      if (e.target.closest(".re-joint-del-btn")) {
        e.target.closest(".re-joint-row")?.remove();
        updateJointTotalRatio();
      }
    });
    document.getElementById("reJointRows")?.addEventListener("input", (e) => {
      if (e.target.classList.contains("re-joint-ratio-input")) {
        updateJointTotalRatio();
      }
    });
  }
}

// ===========================================================================
// 📒 SMART FAMILY HOUSEHOLD LEDGER (스마트 가족 가계부 모듈)
// ===========================================================================
let currentLedgerYear = new Date().getFullYear();
let currentLedgerMonth = new Date().getMonth() + 1;
let rawLedgerData = null;
let currentModule = "wealth"; // "wealth" | "ledger"

function switchMainModule(mod) {
  currentModule = mod;
  const wealthNavBtn = document.getElementById("navTabWealth");
  const ledgerNavBtn = document.getElementById("navTabLedger");
  const wealthWrapper = document.getElementById("userAssetDashboardWrapper");
  const ledgerWrapper = document.getElementById("userLedgerWrapper");

  if (mod === "wealth") {
    if (wealthNavBtn) { wealthNavBtn.className = "button primary"; wealthNavBtn.style.color = "#fff"; }
    if (ledgerNavBtn) { ledgerNavBtn.className = "button secondary"; ledgerNavBtn.style.color = "#94a3b8"; }
    if (wealthWrapper) wealthWrapper.style.display = "block";
    if (ledgerWrapper) ledgerWrapper.style.display = "none";
  } else {
    if (wealthNavBtn) { wealthNavBtn.className = "button secondary"; wealthNavBtn.style.color = "#94a3b8"; }
    if (ledgerNavBtn) { ledgerNavBtn.className = "button primary"; ledgerNavBtn.style.color = "#fff"; }
    if (wealthWrapper) wealthWrapper.style.display = "none";
    if (ledgerWrapper) ledgerWrapper.style.display = "block";
    loadLedger();
  }
}
window.switchMainModule = switchMainModule;

async function loadLedger() {
  try {
    const owner = currentOwner || "모두";
    const res = await api(`/api/ledger?year=${currentLedgerYear}&month=${currentLedgerMonth}&owner=${encodeURIComponent(owner)}`);
    rawLedgerData = res;
    renderLedger(res);
  } catch (err) {
    console.error("가계부 로드 오류:", err);
  }
}

function renderLedger(data) {
  if (!data) return;

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

  // 4. 최근 6개월 추이 막대 그래프 렌더링
  renderLedgerTrend(data.monthly_trend || []);

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

function renderLedgerTrend(trend) {
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
    const isCurrent = t.month === currentLedgerMonth && t.year === currentLedgerYear;

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

function filterLedgerList() {
  if (!rawLedgerData || !rawLedgerData.transactions) return;
  const typeFilter = document.getElementById("ledgerFilterType")?.value || "all";
  const searchQ = (document.getElementById("ledgerSearchInput")?.value || "").toLowerCase().trim();

  const filtered = rawLedgerData.transactions.filter(t => {
    if (typeFilter !== "all" && t.type !== typeFilter) return false;
    if (searchQ) {
      const matchMerchant = (t.merchant || "").toLowerCase().includes(searchQ);
      const matchMemo = (t.memo || "").toLowerCase().includes(searchQ);
      const matchCat = (t.category || "").toLowerCase().includes(searchQ);
      if (!matchMerchant && !matchMemo && !matchCat) return false;
    }
    return true;
  });

  renderLedgerTransactions(filtered);
}
window.filterLedgerList = filterLedgerList;

function updateLedgerCategoryOptions(selectedCat = null) {
  const type = document.getElementById("ledgerTxTypeSelect")?.value || "expense";
  const catSelect = document.getElementById("ledgerTxCategorySelect");
  if (!catSelect) return;

  const defaultCats = {
    expense: ["식비/외식", "주거/통신", "교통/차량", "쇼핑/생활용품", "교육/학습", "의료/건강", "문화/여가", "경조사/선물", "금융/보험/이자", "기타지출"],
    income: ["급여/상여", "사업소득", "배당/금융수익", "용돈/이전소득", "부수입/기타수입"],
    transfer: ["계좌이체/저축", "투자이체", "카드대금결제"]
  };

  const cats = (rawLedgerData?.categories?.[type]) || defaultCats[type] || [];
  catSelect.innerHTML = cats.map(c => `<option value="${html(c)}" ${c === selectedCat ? 'selected' : ''}>${html(c)}</option>`).join("");
}
window.updateLedgerCategoryOptions = updateLedgerCategoryOptions;

function populateLedgerAccountOptions(selectedAccountId = '', filterOwner = '모두') {
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
window.populateLedgerAccountOptions = populateLedgerAccountOptions;

function populateLedgerCardOptions(selectedCardId = '', filterOwner = '모두') {
  const cardSelect = document.getElementById("ledgerTxCardSelect");
  if (!cardSelect) return;

  const cards = rawLedgerData?.cards || [];
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
window.populateLedgerCardOptions = populateLedgerCardOptions;

function onLedgerTxTypeChanged() {
  const form = document.getElementById("ledgerTxForm");
  if (!form) return;
  const typeVal = form.querySelector("[name='type']")?.value || "expense";
  const payMethodTypeLabel = document.getElementById("ledgerTxPayMethodTypeLabel");
  const cardBox = document.getElementById("ledgerTxCardSelectBox");
  const accBox = document.getElementById("ledgerTxAccountSelectBox");
  const accLabel = document.getElementById("ledgerTxAccountSelectLabel");
  const nextBalLabel = document.getElementById("ledgerNextBalanceLabel");

  updateLedgerCategoryOptions();

  if (typeVal === "income") {
    // 💰 수입: 결제수단/카드 숨김, 입금 계좌 표시
    if (payMethodTypeLabel) payMethodTypeLabel.style.display = "none";
    if (cardBox) cardBox.style.display = "none";
    if (accBox) accBox.style.display = "block";
    if (accLabel) accLabel.textContent = "🏦 입금 연동 계좌 선택 (선택 시 잔액 즉시 증가)";
    if (nextBalLabel) nextBalLabel.textContent = "적용 후 예상 잔액 (+입금):";
  } else if (typeVal === "transfer") {
    // 🔄 이체: 결제수단/카드 숨김, 출금 계좌 표시
    if (payMethodTypeLabel) payMethodTypeLabel.style.display = "none";
    if (cardBox) cardBox.style.display = "none";
    if (accBox) accBox.style.display = "block";
    if (accLabel) accLabel.textContent = "🏦 출금 연동 계좌 선택 (선택 시 잔액 즉시 차감)";
    if (nextBalLabel) nextBalLabel.textContent = "적용 후 예상 잔액 (-출금):";
  } else {
    // 💳 지출: 결제 방식(신용카드 vs 계좌) 노출
    if (payMethodTypeLabel) payMethodTypeLabel.style.display = "block";
    onLedgerPayMethodTypeChanged();
    return;
  }
  updateLedgerBalancePreview();
}
window.onLedgerTxTypeChanged = onLedgerTxTypeChanged;

function onLedgerPayMethodTypeChanged() {
  const form = document.getElementById("ledgerTxForm");
  if (!form) return;
  const payMethodType = form.querySelector("[name='pay_method_type']")?.value || "credit_card";
  const cardBox = document.getElementById("ledgerTxCardSelectBox");
  const accBox = document.getElementById("ledgerTxAccountSelectBox");
  const accLabel = document.getElementById("ledgerTxAccountSelectLabel");
  const nextBalLabel = document.getElementById("ledgerNextBalanceLabel");
  const previewBox = document.getElementById("ledgerBalancePreviewBox");

  const owner = form.querySelector("[name='owner']")?.value || currentOwner || "모두";

  if (payMethodType === "credit_card") {
    if (cardBox) cardBox.style.display = "block";
    if (accBox) accBox.style.display = "none";
    if (previewBox) previewBox.style.display = "none";
    populateLedgerCardOptions(form.querySelector("[name='card_id']")?.value, owner);
  } else {
    if (cardBox) cardBox.style.display = "none";
    if (accBox) accBox.style.display = "block";
    if (accLabel) accLabel.textContent = "🏦 출금 연동 계좌 선택 (선택 시 잔액 즉시 차감)";
    if (nextBalLabel) nextBalLabel.textContent = "적용 후 예상 잔액 (-출금):";
    updateLedgerBalancePreview();
  }
}
window.onLedgerPayMethodTypeChanged = onLedgerPayMethodTypeChanged;

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
window.onLedgerTxOwnerChanged = onLedgerTxOwnerChanged;

function onLedgerCardSelectChanged() {
  // 신용카드 선택 변경 시 동작
}
window.onLedgerCardSelectChanged = onLedgerCardSelectChanged;

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
window.updateLedgerBalancePreview = updateLedgerBalancePreview;

function openLedgerTxModal(txId = null) {
  const dialog = document.getElementById("ledgerTxDialog");
  const form = document.getElementById("ledgerTxForm");
  const title = document.getElementById("ledgerTxDialogTitle");
  if (!dialog || !form) return;

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
      dialog.showModal();
      return;
    }
  }

  if (title) title.textContent = "수입 / 지출 내역 등록";
  form.reset();
  form.querySelector("[name='date']").value = new Date().toISOString().slice(0, 10);
  document.getElementById("ledgerTxSplitDateWrap")?._syncFromNative?.();
  form.querySelector("[name='owner']").value = currentOwner || "모두";
  form.querySelector("[name='type']").value = "expense";
  const payMethodTypeSelect = form.querySelector("[name='pay_method_type']");
  if (payMethodTypeSelect) payMethodTypeSelect.value = "credit_card";

  onLedgerTxTypeChanged();
  populateLedgerAccountOptions("", currentOwner || "모두");
  populateLedgerCardOptions("", currentOwner || "모두");
  updateLedgerBalancePreview();
  dialog.showModal();
}
window.openLedgerTxModal = openLedgerTxModal;

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
window.saveLedgerTransaction = saveLedgerTransaction;

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
window.openLedgerCardsModal = openLedgerCardsModal;

async function refreshLedgerCardsList() {
  const listContainer = document.getElementById("ledgerCardsList");
  if (!listContainer) return;

  try {
    const owner = currentOwner || "모두";
    const cards = await api(`/api/ledger/cards?owner=${encodeURIComponent(owner)}`);
    if (rawLedgerData) rawLedgerData.cards = cards;
    renderLedgerCardsList(cards || []);
  } catch (err) {
    console.error("카드 목록 조회 오류:", err);
  }
}

function renderLedgerCardsList(cards) {
  const listContainer = document.getElementById("ledgerCardsList");
  if (!listContainer) return;

  if (!cards || cards.length === 0) {
    listContainer.innerHTML = `<div class="empty" style="grid-column:1/-1;padding:24px 0;"><p style="margin:0;font-size:12.5px;color:#94a3b8;">등록된 신용카드가 없습니다. 아래 폼에서 카드를 추가해 보세요!</p></div>`;
    return;
  }

  listContainer.innerHTML = cards.map(c => {
    const unpaid = Number(c.unpaid_amount || 0);
    const count = Number(c.unpaid_count || 0);
    const hasUnpaid = unpaid > 0;

    return `
      <div class="ledger-credit-card-item">
        <div>
          <div style="display:flex;justify-content:space-between;align-items:flex-start;">
            <div>
              <span class="ledger-card-company-tag">${html(c.card_company)}</span>
              <span class="ledger-card-owner-tag">(${html(c.owner || '모두')})</span>
            </div>
            <div style="display:flex;gap:4px;">
              <button class="account-action-button" onclick="editLedgerCard('${c.id}')" title="카드 정보 수정" type="button">✎</button>
              <button class="account-action-button mini-delete-button" onclick="deleteLedgerCard('${c.id}')" title="카드 삭제" type="button">🗑</button>
            </div>
          </div>
          <h4 class="ledger-card-name">${html(c.card_name)}</h4>
          <p class="ledger-card-meta">
            📅 매월 <strong class="ledger-card-day">${c.payment_day}일</strong> 결제 · 결제계좌: <strong class="ledger-card-acct">${html(c.linked_account_name || '미지정')}</strong>
          </p>
          ${c.memo ? `<p class="ledger-card-memo">${html(c.memo)}</p>` : ''}
        </div>

        <div class="ledger-card-foot">
          <div>
            <span class="ledger-card-unpaid-label">청구 예정액</span>
            <div class="ledger-card-unpaid-val" style="color:${hasUnpaid ? '#f43f5e' : 'inherit'};">₩${number(unpaid, 0)} <span class="ledger-card-unpaid-count">(${count}건)</span></div>
          </div>
          <button class="button compact ${hasUnpaid ? 'primary' : 'secondary'}" type="button" onclick="openLedgerCardPayModal('${c.id}')" ${!hasUnpaid ? 'disabled style="opacity:0.5;"' : ''}>
            💳 결제/정산
          </button>
        </div>
      </div>
    `;
  }).join("");
}

function resetLedgerCardForm() {
  const form = document.getElementById("ledgerCardForm");
  const title = document.getElementById("ledgerCardFormTitle");
  const cancelBtn = document.getElementById("ledgerCardFormCancelBtn");
  if (!form) return;
  form.reset();
  delete form.dataset.cardId;
  if (title) title.textContent = "➕ 신규 카드 등록";
  if (cancelBtn) cancelBtn.style.display = "none";
}
window.resetLedgerCardForm = resetLedgerCardForm;

function editLedgerCard(cardId) {
  const form = document.getElementById("ledgerCardForm");
  const title = document.getElementById("ledgerCardFormTitle");
  const cancelBtn = document.getElementById("ledgerCardFormCancelBtn");
  if (!form || !cardId) return;

  const cards = rawLedgerData?.cards || [];
  const card = cards.find(c => c.id === cardId);
  if (!card) return;

  form.dataset.cardId = card.id;
  form.querySelector("[name='card_company']").value = card.card_company || "현대카드";
  form.querySelector("[name='card_name']").value = card.card_name || "";
  form.querySelector("[name='owner']").value = card.owner || "모두";
  form.querySelector("[name='payment_day']").value = card.payment_day || "14";
  form.querySelector("[name='linked_account_id']").value = card.linked_account_id || "";
  form.querySelector("[name='memo']").value = card.memo || "";

  if (title) title.textContent = "✎ 카드 정보 수정";
  if (cancelBtn) cancelBtn.style.display = "inline-block";
}
window.editLedgerCard = editLedgerCard;

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
window.saveLedgerCard = saveLedgerCard;

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
window.deleteLedgerCard = deleteLedgerCard;

function openLedgerCardPayModal(cardId) {
  const cards = rawLedgerData?.cards || [];
  const card = cards.find(c => c.id === cardId);
  if (!card) return;

  setupAutoAdvancingDateInput("#ledgerPaySplitDateWrap");

  activePayTargetCard = card;
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
window.openLedgerCardPayModal = openLedgerCardPayModal;

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
window.executeCardPayment = executeCardPayment;

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
window.deleteLedgerTransaction = deleteLedgerTransaction;

// 고정지출 모달 관리
function toggleRecurringAccountSelect() {
  const method = document.getElementById("recPayMethod")?.value;
  const grp = document.getElementById("recAccountGroup");
  if (grp) {
    grp.style.display = method === "자동이체" ? "block" : "none";
  }
}
window.toggleRecurringAccountSelect = toggleRecurringAccountSelect;

function populateRecurringAccounts() {
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

function openLedgerRecurringModal() {
  const dialog = document.getElementById("ledgerRecurringDialog");
  const listContainer = document.getElementById("ledgerRecurringList");
  if (!dialog || !listContainer) return;

  populateRecurringAccounts();
  toggleRecurringAccountSelect();

  const recs = rawLedgerData?.recurring || [];
  const now = new Date();
  const curPrefix = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;

  if (recs.length === 0) {
    listContainer.innerHTML = `<div class="empty" style="padding:15px 0;"><p style="margin:0;font-size:12px;color:#94a3b8;">등록된 정기 고정지출이 없습니다.</p></div>`;
  } else {
    listContainer.innerHTML = recs.map(r => {
      const isDeductedThisMonth = (r.last_deducted_date || "").startsWith(curPrefix);
      let statusBadge = "";
      if (r.auto_deduct && r.linked_account_id) {
        if (isDeductedThisMonth) {
          statusBadge = `<span style="color:#4ade80;font-size:11px;font-weight:600;">✅ 당월 자동출금 완료 (${r.last_deducted_date})</span>`;
        } else {
          statusBadge = `<span style="color:#facc15;font-size:11px;font-weight:600;">⏳ 매월 ${r.day_of_month}일 자동출금 대기</span>`;
        }
      } else {
        statusBadge = `<span style="color:#94a3b8;font-size:11px;">수동 납부</span>`;
      }

      const acctBadge = r.linked_account_name ? `
        <span style="display:inline-block;font-size:10px;background:rgba(56,189,248,0.15);color:#38bdf8;border:1px solid rgba(56,189,248,0.3);padding:1px 6px;border-radius:4px;margin-left:4px;">
          🏦 ${html(r.linked_account_name)}
        </span>
      ` : "";

      return `
        <div class="ledger-recurring-item">
          <div>
            <div class="ledger-recurring-title">
              <span>${html(r.name)}</span>
              <span class="saving-owner-badge" style="font-size:10px;padding:1px 5px;">${html(r.owner || '모두')}</span>
              ${acctBadge}
            </div>
            <div class="ledger-recurring-meta">
              <span>매월 ${r.day_of_month}일</span>
              <span>·</span>
              <span>${html(r.category)}</span>
              <span>·</span>
              <span>${html(r.pay_method)}</span>
              <span>·</span>
              ${statusBadge}
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:6px;">
            <strong class="ledger-recurring-amt">₩${number(r.amount, 0)}</strong>
            <button class="account-action-button" onclick="editRecurringItem('${r.id}')" title="수정" type="button" style="padding:3px 7px;font-size:12px;">✎</button>
            <button class="account-action-button mini-delete-button" onclick="deleteRecurringItem('${r.id}')" title="삭제" type="button" style="padding:3px 7px;font-size:12px;">🗑️</button>
          </div>
        </div>
      `;
    }).join("");
  }

  dialog.showModal();
}
window.openLedgerRecurringModal = openLedgerRecurringModal;

function editRecurringItem(recId) {
  const recs = rawLedgerData?.recurring || [];
  const rec = recs.find(r => r.id === recId);
  if (!rec) return;

  const editIdEl = document.getElementById("recEditId");
  const nameEl = document.getElementById("recName");
  const amountEl = document.getElementById("recAmount");
  const dayEl = document.getElementById("recDay");
  const catEl = document.getElementById("recCategory");
  const ownerEl = document.getElementById("recOwner");
  const payMethodEl = document.getElementById("recPayMethod");
  const acctSel = document.getElementById("recAccountSelect");
  const autoDeductEl = document.getElementById("recAutoDeduct");
  const titleEl = document.getElementById("recurringFormTitle");
  const addBtn = document.getElementById("addRecurringBtn");
  const cancelBtn = document.getElementById("cancelRecurringEditBtn");

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
window.editRecurringItem = editRecurringItem;

function cancelRecurringEdit() {
  const editIdEl = document.getElementById("recEditId");
  const nameEl = document.getElementById("recName");
  const amountEl = document.getElementById("recAmount");
  const dayEl = document.getElementById("recDay");
  const catEl = document.getElementById("recCategory");
  const ownerEl = document.getElementById("recOwner");
  const payMethodEl = document.getElementById("recPayMethod");
  const acctSel = document.getElementById("recAccountSelect");
  const autoDeductEl = document.getElementById("recAutoDeduct");
  const titleEl = document.getElementById("recurringFormTitle");
  const addBtn = document.getElementById("addRecurringBtn");
  const cancelBtn = document.getElementById("cancelRecurringEditBtn");

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
window.cancelRecurringEdit = cancelRecurringEdit;

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
window.triggerRecurringProcess = triggerRecurringProcess;

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
window.saveNewRecurringItem = saveNewRecurringItem;

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
window.deleteRecurringItem = deleteRecurringItem;

// 엑셀/텍스트 일괄 가져오기
function openLedgerExcelModal() {
  document.getElementById("ledgerExcelDialog")?.showModal();
}
window.openLedgerExcelModal = openLedgerExcelModal;

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
window.handleLedgerFileSelect = handleLedgerFileSelect;

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
    await loadLedger();
  } catch (err) {
    alert(`엑셀 파일 등록 오류: ${err.message}`);
  } finally {
    if (uploadBtn) busy(uploadBtn, false);
  }
}
window.uploadLedgerFile = uploadLedgerFile;

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
window.processLedgerTextImport = processLedgerTextImport;
window.processLedgerImport = processLedgerTextImport;

function initLedgerListeners() {
  document.getElementById("ledgerPrevMonthBtn")?.addEventListener("click", () => {
    currentLedgerMonth--;
    if (currentLedgerMonth < 1) {
      currentLedgerMonth = 12;
      currentLedgerYear--;
    }
    loadLedger();
  });
  document.getElementById("ledgerNextMonthBtn")?.addEventListener("click", () => {
    currentLedgerMonth++;
    if (currentLedgerMonth > 12) {
      currentLedgerMonth = 1;
      currentLedgerYear++;
    }
    loadLedger();
  });
  document.getElementById("ledgerTodayMonthBtn")?.addEventListener("click", () => {
    const now = new Date();
    currentLedgerYear = now.getFullYear();
    currentLedgerMonth = now.getMonth() + 1;
    loadLedger();
  });

  // 📅 년/월 직접 선택 (HTML5 month picker)
  const monthPicker = document.getElementById("ledgerMonthPicker");
  if (monthPicker) {
    monthPicker.addEventListener("change", (e) => {
      if (e.target.value) {
        const parts = e.target.value.split("-");
        if (parts.length === 2) {
          currentLedgerYear = parseInt(parts[0], 10);
          currentLedgerMonth = parseInt(parts[1], 10);
          loadLedger();
        }
      }
    });
  }
  const monthText = document.getElementById("ledgerCurrentMonthText");
  if (monthText && monthPicker) {
    monthText.setAttribute("title", "클릭하여 월 선택 또는 마우스 휠로 월 이동");
    monthText.addEventListener("wheel", (e) => {
      e.preventDefault();
      if (e.deltaY < 0) {
        currentLedgerMonth++;
        if (currentLedgerMonth > 12) {
          currentLedgerMonth = 1;
          currentLedgerYear++;
        }
        loadLedger();
      } else if (e.deltaY > 0) {
        currentLedgerMonth--;
        if (currentLedgerMonth < 1) {
          currentLedgerMonth = 12;
          currentLedgerYear--;
        }
        loadLedger();
      }
    }, { passive: false });

    monthText.addEventListener("click", () => {
      try {
        if (typeof monthPicker.showPicker === "function") {
          monthPicker.showPicker();
        } else {
          monthPicker.focus();
          monthPicker.click();
        }
      } catch (err) {
        monthPicker.click();
      }
    });
  }
}

// ── APP BOOTSTRAP ─────────────────────────────────────────────────────────────
async function bootstrap() {
  initAppTheme();
  initCollapsedSections();
  initSavingsListeners();
  initLedgerListeners();
  setupAutoAdvancingDateInput("#pnlSplitDateWrap");
  setupAutoAdvancingDateInput("#divSplitDateWrap");
  setupAutoAdvancingDateInput("#ledgerTxSplitDateWrap");
  setupAutoAdvancingDateInput("#ledgerPaySplitDateWrap");
  await initAuthSession();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}

window.addEventListener('wealth:view', ({ detail }) => {
  if (detail === 'invest' && dashboard) requestAnimationFrame(() => renderHeatmaps(dashboard));
  if (detail === 'ledger' && currentUserProfile && currentUserProfile.username !== 'admin') loadLedger();
});
