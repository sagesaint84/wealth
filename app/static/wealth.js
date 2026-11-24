

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

// 다이얼로그 닫기 버튼 공통 처리
document.addEventListener("click", (event) => {
  const button = event.target.closest(".dialog .close, .dialog .dialog-actions button[value='cancel']");
  if (!button) return;
  event.preventDefault();
  button.closest("dialog")?.close();
});

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

document.addEventListener('input', (e) => {
  if (e.target && e.target.hasAttribute('data-korean-currency')) {
    updateKoreanCurrencyHint(e.target);
  }
});

const html = window.WealthFormat.escapeHtml;
const escapeHtml = html;
const brokerUI = window.WealthBrokerUI.create({ document, html });
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


function sparkline(points, change) { return marketView.sparkline(points, change); }

// Opt-in synthetic profiling only: bounded memory, fixed labels, no payloads/URLs.
globalThis.WealthStartup = (() => {
  const enabled = globalThis.__WEALTH_SYNTHETIC_PERF__ === true;
  const counters = Object.create(null), events = [];
  let assetsReady = false;
  const visiblePending = new Map();
  let visibleScope = null, visibleRevision = 0;
  const labels = new Set(['auth:start','auth:end','prices:start','prices:end',
    'snapshot:start','snapshot:end','dashboard:visible','request','render',
    'supplementary','aux_request','inactive_request','inactive_skipped','merged_get','cache_hit','stale_ignored']);
  function count(label) {
    if (!enabled || !labels.has(label) || (label === 'dashboard:visible' && counters[label])) return;
    counters[label] = (counters[label] || 0) + 1;
    const time = globalThis.performance?.now?.() ?? 0;
    events.push({label, time});
    if (events.length > 128) events.shift();
    const name = `wealth-startup:${label}`;
    globalThis.performance?.clearMarks?.(name);
    globalThis.performance?.mark?.(name);
  }
  function canRead() {
    return assetsReady && typeof currentUserProfile !== 'undefined' &&
      !!currentUserProfile && currentUserProfile.username !== 'admin' && !currentUserProfile.must_change_password;
  }
  function visible(id) {
    return canRead() && !!document.getElementById(id)?.getClientRects().length;
  }
  function loadVisible(preparedDividend = null) {
    if (!canRead()) return;
    const scope = JSON.stringify([startupReadEpoch, currentOwner, selectedDividendYear, selectedPnlYear,
      currentPnlTradeType, currentDividendMode, ledgerFeature.getYear(), ledgerFeature.getMonth(), ledgerFeature.isAnnualView(),
      ['marketGrid','recordsPanel','ledgerSectionPanel','dividendPanel','realizedPnlPanel','summaryRealizedPnl'].map(visible)]);
    if (scope !== visibleScope) { visibleScope = scope; visibleRevision++; }
    const key = `${visibleRevision}:${scope}`;
    if (visiblePending.has(key)) return visiblePending.get(key);
    const jobs = [];
    if (visible('marketGrid')) jobs.push(loadMarkets());
    if (visible('recordsPanel')) jobs.push(loadAssetRecords(currentOwner));
    if (visible('ledgerSectionPanel')) jobs.push(loadLedger());
    if (visible('dividendPanel')) jobs.push(currentDividendMode === 'estimated'
      ? loadDividends(currentOwner, {reuse:true}) : loadActualDividends(currentOwner, selectedDividendYear, preparedDividend));
    if (visible('realizedPnlPanel')) jobs.push(loadRealizedPnl(currentOwner, selectedPnlYear, currentPnlTradeType));
    if (visible('summaryRealizedPnl')) jobs.push(updateOverviewCardsAllTime(currentOwner));
    const pending = Promise.allSettled(jobs).finally(() => {
      if (visiblePending.get(key) === pending) visiblePending.delete(key);
    });
    visiblePending.set(key, pending);
    return pending;
  }
  function request(path, allTime) {
    if (!enabled) return;
    if (!['/api/auth/me','/api/refresh-prices','/api/planning/snapshot-all','/api/dashboard'].includes(path)) count('aux_request');
    const panels = {
      '/api/ledger':['ledgerSectionPanel'], '/api/asset-records':['recordsPanel'],
      '/api/dividends':['dividendPanel'], '/api/market-overview':['marketGrid'],
      '/api/realized-pnl':allTime ? ['realizedPnlPanel','summaryRealizedPnl'] : ['realizedPnlPanel'],
      '/api/actual-dividends':allTime ? ['dividendPanel','summaryRealizedPnl'] : ['dividendPanel'],
    }[path];
    const explicitDividendEntry = path === '/api/actual-dividends' && allTime
      && typeof setIncomeTab === 'function' && setIncomeTab.pendingTarget === 'dividend';
    if (panels && !panels.some(visible) && !explicitDividendEntry) count('inactive_request');
  }
  function dashboardRendered(data) {
    if (!enabled) return;
    if (data?.summary && Number.isFinite(Number(data.summary.total_value_krw)) &&
        ['wealthAssetNetWorth','wealthNetWorth','totalValue'].some(id => document.getElementById(id)?.getClientRects().length)) count('dashboard:visible');
  }
  return {count, request, dashboardRendered, canRead, visible, loadVisible,
    ready() { assetsReady = true; },
    snapshot() { return {enabled, scope:'core-api-and-visible-render', counters:{...counters}, events:events.map(e => ({...e}))}; }};
})();

const startupReadPending = new Map();
const allTimeReadCache = new Map();
let startupReadEpoch = 0;
let startupIncomeReuse = true;

function invalidateStartupReads() {
  startupReadEpoch++;
  allTimeReadCache.clear();
  startupReadPending.clear();
}

function finishStartupIncomeReads() {
  startupIncomeReuse = false;
  for (const key of allTimeReadCache.keys()) {
    if (!key.startsWith('/api/ipo/market')) allTimeReadCache.delete(key);
  }
}

async function api(url, options = {}) {
  const parsed = new URL(url, location.origin);
  parsed.searchParams.sort();
  const key = parsed.pathname + parsed.search;
  const isRead = !options.method || options.method.toUpperCase() === 'GET';
  if (!isRead && parsed.pathname.startsWith('/api/ledger')) ledgerFeature.invalidateRead();
  const shared = isRead && ['/api/realized-pnl', '/api/actual-dividends', '/api/family-members', '/api/ipo/market', '/api/accounts', '/api/asset-records', '/api/ledger', '/api/market-overview', '/api/dividends'].includes(parsed.pathname);
  const reusable = shared && ((startupIncomeReuse && parsed.searchParams.get('year') === 'all') || parsed.pathname === '/api/ipo/market');
  // Price/snapshot writes do not change realized income or IPO market records.
  if (!isRead && !['/api/refresh-prices', '/api/planning/snapshot-all'].includes(parsed.pathname)) {
    invalidateStartupReads();
  }
  if (reusable && options.cache !== 'no-store' && allTimeReadCache.has(key)) { globalThis.WealthStartup?.count('cache_hit'); return allTimeReadCache.get(key); }
  if (shared && startupReadPending.has(key)) { globalThis.WealthStartup?.count('merged_get'); return startupReadPending.get(key); }
  const epoch = startupReadEpoch;
  const pending = apiRequest(url, options);
  if (!shared) return pending;
  startupReadPending.set(key, pending);
  try {
    const result = await pending;
    if (reusable && epoch === startupReadEpoch && (startupIncomeReuse || parsed.pathname === '/api/ipo/market')) allTimeReadCache.set(key, result);
    return result;
  } finally {
    if (startupReadPending.get(key) === pending) startupReadPending.delete(key);
  }
}

async function apiRequest(url, options = {}) {
  globalThis.WealthStartup?.count('request');
  const address = new URL(url, location.origin);
  globalThis.WealthStartup?.request(address.pathname, address.searchParams.get('year') === 'all');
  const phase = ({'/api/auth/me':'auth', '/api/refresh-prices':'prices', '/api/planning/snapshot-all':'snapshot'})[address.pathname];
  if (phase) globalThis.WealthStartup?.count(`${phase}:start`);
  try {
    options.credentials = options.credentials || 'include';
    const response = await fetch(url, options);
    if (response.status === 401) {
      window.location.href = '/login';
      throw new Error('로그인이 필요합니다.');
    }
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || result.message || "요청을 처리하지 못했습니다.");
    return result;
  } finally { if (phase) globalThis.WealthStartup?.count(`${phase}:end`); }
}

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
        if (prepared.readEpoch !== (typeof startupReadEpoch === 'undefined' ? 0 : startupReadEpoch))
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
  if (loadContent || preparedDividend) {
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
  get startupReadEpoch() { return startupReadEpoch; },
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
  return currentModule === 'ledger' ||
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

// ── 전역 클릭 이벤트 위임 ───────────────────────────────────────────────────
document.addEventListener('click', async (e) => {
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
    investmentFeature.actions.selectSector(e, sectorItem);
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
    accountFeature.actions.openAccountAddDialog();
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
    accountFeature.actions.editAccountFromRow(e, acctEditBtn);
    return;
  }

  const historyButton = e.target.closest('[data-national-history-id]');
  const analysisButton=e.target.closest('[data-national-analysis-id]');
  const importButton=e.target.closest('[data-national-import-id]');
  if(analysisButton||importButton){
    insuranceFeature.actions.openNationalPensionTool(analysisButton, importButton);
    return;
  }
  if (historyButton) {
    insuranceFeature.actions.openNationalPensionHistoryFromRow(historyButton);
    return;
  }
  // 보험/연금 수정
  const insEditBtn = e.target.closest('[data-insurance-edit-id]');
  if (insEditBtn) {
    insuranceFeature.actions.editInsuranceAccount(insEditBtn);
    return;
  }

  // 보험/연금 삭제
  const insDelBtn = e.target.closest('[data-insurance-del-id]');
  if (insDelBtn) {
    await insuranceFeature.actions.deleteInsuranceAccount(insDelBtn);
    return;
  }

  // 대출·마이너스통장 수정
  const loanEditBtn = e.target.closest('[data-loan-edit-id]');
  if (loanEditBtn) {
    accountFeature.actions.editLoanAccount(loanEditBtn);
    return;
  }

  // 대출·마이너스통장 삭제
  const loanDelBtn = e.target.closest('[data-loan-del-id]');
  if (loanDelBtn) {
    await accountFeature.actions.deleteLoanAccount(loanDelBtn);
    return;
  }

  // 🗂️ 은행 서브 탭 전환 (전체 / 자유 / 예적금 / 대출)
  const subtabBtn = e.target.closest('.savings-subtab');
  if (subtabBtn) {
    accountFeature.actions.selectSavingsSubtab(subtabBtn);
    return;
  }

  // 🏷️ 상단 부동산 실현손익 카드 클릭 시 [매도] 서브탭으로 즉시 전환
  if (e.target.closest('#cardRealEstateRealized')) {
    realEstateFeature.actions.showSoldRealEstates();
    return;
  }

  // 🗂️ 부동산 서브 탭 전환 (전체 / 자가보유 / 임대 / 임차 / 매도)
  const reSubtabBtn = e.target.closest('.real-estate-subtab');
  if (reSubtabBtn) {
    realEstateFeature.actions.selectRealEstateSubtab(reSubtabBtn);
    return;
  }

  // 매도 부동산 기록 수정
  const soldEditBtn = e.target.closest('[data-sold-re-edit]');
  if (soldEditBtn) {
    realEstateFeature.actions.editSoldRealEstate(soldEditBtn);
    return;
  }

  // 매도 부동산 기록 삭제
  const soldDelBtn = e.target.closest('[data-sold-re-del]');
  if (soldDelBtn) {
    await realEstateFeature.actions.deleteSoldRealEstate(soldDelBtn);
    return;
  }

  // 부동산 KB시세 즉시 갱신
  const reKbRefreshBtn = e.target.closest('[data-re-refresh-kb-id]');
  if (reKbRefreshBtn) {
    await realEstateFeature.actions.refreshRealEstateKbPrice(reKbRefreshBtn);
    return;
  }

  // 부동산 매각 및 실현손익 기록
  const reSellBtn = e.target.closest('[data-re-sell-id]');
  if (reSellBtn) {
    realEstateFeature.actions.openRealEstateSale(reSellBtn);
    return;
  }

  // 부동산 수정
  const reEditBtn = e.target.closest('[data-re-edit-id]');
  if (reEditBtn) {
    realEstateFeature.actions.editRealEstate(reEditBtn);
    return;
  }

  // 부동산 삭제
  const reDelBtn = e.target.closest('[data-re-del-id]');
  if (reDelBtn) {
    await realEstateFeature.actions.deleteRealEstate(reDelBtn);
    return;
  }


  // 예·적금 수정
  const savingEditBtn = e.target.closest('[data-saving-edit-id]');
  if (savingEditBtn) {
    accountFeature.actions.editSavingAccount(savingEditBtn);
    return;
  }

  // 예·적금 삭제
  const savingDelBtn = e.target.closest('[data-saving-del-id]');
  if (savingDelBtn) {
    await accountFeature.actions.deleteSavingAccount(savingDelBtn);
    return;
  }

  // 은행 계좌 수정
  const bankEditBtn = e.target.closest('[data-bank-edit-id]');
  if (bankEditBtn) {
    accountFeature.actions.editBankAccount(bankEditBtn);
    return;
  }

  // 은행 계좌 삭제
  const bankDelBtn = e.target.closest('[data-bank-del-id]');
  if (bankDelBtn) {
    await accountFeature.actions.deleteBankAccount(bankDelBtn);
    return;
  }

  // 가족 구성원 추가
  if (e.target.closest('#addMemberBtn')) {
    await familyFeature.actions.addFamilyMember();
    return;
  }

  // 가족 구성원 이름 수정
  const renameBtn = e.target.closest('.family-rename-btn');
  if (renameBtn) {
    await familyFeature.actions.renameFamilyMember(renameBtn);
    return;
  }

  // 가족 구성원 삭제
  const deleteMemberBtn = e.target.closest('.family-delete-btn');
  if (deleteMemberBtn) {
    await familyFeature.actions.deleteFamilyMember(deleteMemberBtn);
    return;
  }

  // 절세계좌 보유종목 정렬 헤더 클릭
  const taxTh = e.target.closest('#assetChart [data-tax-sort]');
  if (taxTh) {
    investmentFeature.actions.sortTaxHoldings(taxTh);
    return;
  }

  // 절세계좌 보유종목 수정/삭제 버튼
  const taxEditBtn = e.target.closest('#assetChart .edit-button');
  const taxDelBtn = e.target.closest('#assetChart .delete-button');
  if (taxEditBtn) {
    investmentFeature.actions.editTaxHolding(taxEditBtn);
    return;
  }
  if (taxDelBtn && confirm("이 보유종목을 삭제할까요?")) {
    await investmentFeature.actions.deleteTaxHolding(taxDelBtn);
    return;
  }

  // 실현손익 테이블 정렬 헤더 클릭
  const pnlTh = e.target.closest('#pnlMonthlyDetail [data-pnl-sort]');
  if (pnlTh) {
    incomeFeature.actions.sortPnlDetail(pnlTh);
    return;
  }

  // 배당금 테이블 정렬 헤더 클릭
  const divTh = e.target.closest('#dividendMonthlyDetail [data-div-sort]');
  if (divTh) {
    incomeFeature.actions.sortDividendDetail(divTh);
    return;
  }

  // 보유종목 정렬 헤더 클릭
  const th = e.target.closest('.sortable-th');
  if (th && th.dataset.sort) {
    investmentFeature.actions.sortHoldings(th);
    return;
  }

  // 종목 차트 버튼 또는 종목명 클릭
  const chartBtn = e.target.closest('.stock-chart-btn, .holding-name-link');
  if (chartBtn) {
    investmentFeature.actions.openHoldingChart(chartBtn);
    return;
  }

  // 종목 차트 모달 기간 탭 클릭
  const chartTab = e.target.closest('#stockChartPeriodTabs .heatmap-tab');
  if (chartTab) {
    await investmentFeature.actions.selectChartPeriod(chartTab);
    return;
  }

  // 배당 재조회 버튼
  const divRefreshBtn = e.target.closest('#refreshDividendBtn');
  if (divRefreshBtn) {
    incomeFeature.actions.refreshDividends(divRefreshBtn);
    return;
  }

  // 배당 모드 탭 (🔮 예상 vs 💵 실제)
  const divModeTab = e.target.closest('#dividendModeTabs .heatmap-tab');
  if (divModeTab) {
    incomeFeature.actions.switchDividendMode(divModeTab);
    return;
  }

  // 💾 실제 배당 저장하기 버튼
  if (e.target.closest('#dividendSaveBtn')) {
    incomeFeature.actions.submitDividend(e);
    return;
  }

  // 💾 매도 실현손익 저장하기 버튼
  if (e.target.closest('#pnlSaveBtn')) {
    incomeFeature.actions.submitPnl(e);
    return;
  }

  // ➕ 실제 배당 추가 버튼
  if (e.target.closest('#addDividendBtn')) {
    incomeFeature.actions.addDividend();
    return;
  }

  // 📂 실제 배당 가져오기 버튼
  if (e.target.closest('#importDividendBtn')) {
    incomeFeature.actions.openDividendImport();
    return;
  }

  // 🗑️ 실제 배당 전체 일괄 삭제 버튼
  if (e.target.closest('#clearAllDividendBtn')) {
    incomeFeature.actions.clearDividends();
    return;
  }

  // 실제 배당 수정 버튼
  const editActualDivBtn = e.target.closest('.edit-actual-div-btn');
  if (editActualDivBtn) {
    incomeFeature.actions.editDividend(editActualDivBtn);
    return;
  }

  // 실제 배당 삭제 버튼
  const delActualDivBtn = e.target.closest('.delete-actual-div-btn');
  if (delActualDivBtn) {
    await incomeFeature.actions.deleteDividend(delActualDivBtn);
    return;
  }

  // 배당 막대 차트 월/연도 선택
  const divBar = e.target.closest('.dividend-bar-group');
  if (divBar && incomeFeature.actions.selectDividendBar(divBar)) return;

  // 배당 전체 보기 버튼
  if (e.target.closest('#clearDivMonthBtn')) {
    incomeFeature.actions.clearDividendMonth();
    return;
  }

  // 실현손익 거래유형 탭 (🏢 전체 vs 📦 공모주)
  const pnlTab = e.target.closest('#pnlTradeTypeTabs .heatmap-tab');
  if (pnlTab) {
    incomeFeature.actions.selectPnlType(pnlTab);
    return;
  }

  // ➕ 실현손익 추가 버튼
  if (e.target.closest('#addPnlBtn')) {
    incomeFeature.actions.addPnl();
    return;
  }

  // 📂 실현손익 가져오기 버튼
  if (e.target.closest('#importPnlBtn')) {
    incomeFeature.actions.openPnlImport();
    return;
  }

  // 🗑️ 매도 실현손익 전체 일괄 삭제 버튼
  if (e.target.closest('#clearAllPnlBtn')) {
    incomeFeature.actions.clearPnl();
    return;
  }

  // 실현손익 수정 버튼
  const editPnlBtn = e.target.closest('.edit-pnl-btn');
  if (editPnlBtn) {
    incomeFeature.actions.editPnl(editPnlBtn);
    return;
  }

  // 실현손익 삭제 버튼
  const delPnlBtn = e.target.closest('.delete-pnl-btn');
  if (delPnlBtn) {
    await incomeFeature.actions.deletePnl(delPnlBtn);
    return;
  }

  // 실현손익 막대 차트 월/연도 선택
  const pnlBar = e.target.closest('.pnl-bar-group');
  if (pnlBar && incomeFeature.actions.selectPnlBar(pnlBar)) return;

  // 실현손익 전체 보기 버튼
  if (e.target.closest('#clearPnlMonthBtn')) {
    incomeFeature.actions.clearPnlMonth();
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

incomeFeature.actions.bindEstimatedTooltip();
incomeFeature.actions.bindRecordForms();

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

// 창 크기 변경 시 활성화된 히트맵 재계산

investmentFeature.actions.bindHeatmapResize();

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
  if (loadAssetDataForUser.pending) return loadAssetDataForUser.pending;
  const pending = (async () => {
    let priceRefreshSucceeded = false;
    const familyMembersReady = loadFamilyMembers().catch(() => {});

    // 접속 시 먼저 최신 시세/환율을 반영한다. 성공한 경우에만 당일 자동 스냅샷을 기록한다.
    try {
      await api("/api/refresh-prices", { method: "POST" });
      priceRefreshSucceeded = true;
    } catch (e) {
      toast(e.message || "접속 시 시세 갱신에 실패해 자동 기록을 건너뜁니다.", true);
    }
    try {
      await loadDashboard(priceRefreshSucceeded);
    } catch (e) {
      toast(e.message || "대시보드를 불러오지 못했습니다.", true);
    }

    if (priceRefreshSucceeded) {
      try {
        await api("/api/planning/snapshot-all", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source: "auto" }),
        });
        window.dispatchEvent(new CustomEvent('wealth:planning-refresh'));
      } catch (e) {
        toast(e.message || "접속 시 순자산 자동 기록에 실패했습니다.", true);
      }
    }

    globalThis.WealthStartup?.ready();
    window.dispatchEvent(new CustomEvent('wealth:assets-ready'));
    globalThis.WealthStartup?.count('supplementary');
    // No reads assuming refreshed prices start before both recording steps settle.
    loadAssetDataForUser.supplementary = Promise.allSettled([
      familyMembersReady,
      globalThis.WealthStartup?.loadVisible(),
    ]).finally(finishStartupIncomeReads);
  })();
  loadAssetDataForUser.pending = pending;
  try { await pending; }
  finally { if (loadAssetDataForUser.pending === pending) loadAssetDataForUser.pending = null; }
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
    // Re-read server capability after the pending-password state is cleared.
    await initAuthSession();
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

const adminUsersView = window.WealthAdminUsersView.create({ document, html });
async function refreshAdminUserList() {
  const tables = adminUsersView.getTables();
  adminUsersView.renderStatus(tables, '불러오는 중...');
  try {
    const res = await api('/api/admin/users');
    const users = res.users || [];
    console.log('[ADMIN] 사용자 목록 수신:', users);
    const total = users.length;
    const pending = users.filter(u => u.must_change_password).length;
    adminUsersView.renderCounts({ total, pending, active: total - pending });

    adminUsersView.renderUsers(tables, users.map(u => {
      const isAdminRoot = u.username === 'admin';
      const stored = u.permissions?.system_update === true;
      return {
        id: u.id, username: u.username, role: u.role,
        roleClass: u.role === 'admin' ? 'admin' : 'user',
        isSelf: currentUserProfile && currentUserProfile.username === u.username,
        pending: u.must_change_password,
        createdAt: u.created_at ? u.created_at.substring(0, 10) : '-',
        notice: isAdminRoot ? '관리자 기본 권한' : !u.id ? '식별자 확인 필요' : null,
        stored, disabled: (u.must_change_password || u.active === false) && !stored,
        canDelete: !isAdminRoot,
      };
    }));
  } catch (err) {
    console.error('[ADMIN] 사용자 목록 로드 실패:', err);
    adminUsersView.renderStatus(tables, `목록 로드 실패: ${err.message || String(err)}`, true);
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
const openApiFields = {
  toss: ['Toss', 'Client Secret 입력'], kb: ['Kb', 'KB App Secret 입력'],
  nh: ['Nh', '나무 App Secret 입력'], kis: ['Kis', '한투 App Secret 입력'],
  kiwoom: ['Kiwoom', '키움 App Secret 입력'],
};
let userOpenApiSnapshot = {};

async function loadUserOpenApiSettings(brokers = null) {
  const config = await api('/api/user/openapi-config');
  const selected = brokers || Object.keys(openApiFields);
  for (const broker of selected) {
    const [prefix, secretPlaceholder] = openApiFields[broker];
    const value = config[broker] || {};
    userOpenApiSnapshot[broker] = value; // This endpoint returns masked values only.
    const field = suffix => document.getElementById('openapi' + prefix + suffix);
    const badge = field('Badge');
    if (badge) {
      badge.textContent = value.configured ? '연결됨' : '미연결';
      badge.className = 'openapi-badge ' + (value.configured ? 'connected' : 'disconnected');
    }
    if (field('DeleteBtn')) field('DeleteBtn').style.display = value.has_app_key || value.configured ? 'inline-flex' : 'none';
    if (field('Key')) field('Key').value = value.app_key || '';
    if (field('Secret')) {
      field('Secret').value = '';
      field('Secret').placeholder = value.configured ? '******** (등록됨 - 변경 시만 입력)' : secretPlaceholder;
    }
    if (field('AccountNo')) {
      field('AccountNo').value = '';
      field('AccountNo').placeholder = value.account_no ? value.account_no + ' (등록됨 - 변경 시만 입력)' : '변경할 계좌번호 입력';
    }
  }
  if (!brokers) renderDartOpenApiStatus(config.dart);
}
window.loadUserOpenApiSettings = loadUserOpenApiSettings;

function renderDartOpenApiStatus(dartConfig, updateBadge) {
  const badge = document.getElementById('openapiDartBadge');
  const deleteButton = document.getElementById('openapiDartDeleteBtn');
  const input = document.getElementById('openapiDartKey');
  const configured = !!dartConfig?.configured;
  if (updateBadge) updateBadge(badge, configured);
  else if (badge) {
    badge.textContent = configured ? '연결됨' : '미연결';
    badge.className = `openapi-badge ${configured ? 'connected' : 'disconnected'}`;
  }
  if (deleteButton) deleteButton.style.display = dartConfig?.has_api_key ? 'inline-flex' : 'none';
  if (input) {
    input.value = '';
    input.placeholder = configured ? '******** (등록됨 - 변경 시에만 입력)' : '40자리 OpenDART 인증키 입력';
  }
}

async function refreshDartOpenApiStatus() {
  const config = await api('/api/user/openapi-config');
  renderDartOpenApiStatus(config.dart);
}

async function handleSaveDartApi() {
  const input = document.getElementById('openapiDartKey');
  const key = (input?.value || '').trim();
  if (!key) { toast('OpenDART API Key를 입력하세요.'); return; }
  try {
    await api('/api/user/openapi-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dart: { api_key: key } }),
    });
    if (input) input.value = '';
    toast('OpenDART API Key가 안전하게 저장되었습니다.');
    await refreshDartOpenApiStatus();
  } catch (err) {
    alert(err.message || '저장 실패');
  }
}
window.handleSaveDartApi = handleSaveDartApi;

async function handleDeleteDartApi() {
  if (!confirm('정말로 OpenDART API 키를 삭제하시겠습니까?')) return;
  try {
    const res = await api('/api/user/openapi-config/dart', { method: 'DELETE' });
    toast(res.message || 'OpenDART 설정이 삭제되었습니다.');
    const input = document.getElementById('openapiDartKey');
    if (input) input.value = '';
    await refreshDartOpenApiStatus();
  } catch (err) {
    alert(err.message || '삭제 실패');
  }
}
window.handleDeleteDartApi = handleDeleteDartApi;

async function handleTestDartApi() {
  try {
    const result = await api('/api/user/openapi-config/dart/test', { method: 'POST' });
    if (result.valid) {
      toast(result.message || 'OpenDART 연결을 확인했습니다.');
    } else {
      toast(`OpenDART 연결 확인 실패: ${result.message || result.error_code || 'UNKNOWN_ERROR'}`);
    }
  } catch (err) {
    alert(err.message || '연결 확인 실패');
  }
}
window.handleTestDartApi = handleTestDartApi;

async function handleDeleteBrokerApi(broker) {
  const names = { toss: '토스증권', kb: 'KB증권', nh: '나무증권', kis: '한국투자증권', kiwoom: '키움증권', dart: 'OpenDART' };
  const bname = names[broker] || broker;
  if (!confirm(`정말로 ${bname} OpenAPI 키와 시크릿을 삭제(연결 해제)하시겠습니까?`)) return;

  try {
    const res = await api(`/api/user/openapi-config/${encodeURIComponent(broker)}`, {
      method: 'DELETE'
    });
    toast(res.message || `${bname} OpenAPI 키가 삭제되었습니다.`);
    await loadUserOpenApiSettings([broker]);
  } catch (err) {
    alert(err.message || '삭제 실패');
  }
}
window.handleDeleteBrokerApi = handleDeleteBrokerApi;

async function handleSaveUserOpenApi(e) {
  if (e) e.preventDefault();
  const btn = document.getElementById('saveUserOpenApiBtn');
  const statusMsg = document.getElementById('openapiStatusMsg');

  // Omit untouched broker sections. The backend's blank app_key means delete,
  // so retain its masked key when changing only a secret/account number.
  const payload = {};
  for (const [broker, [prefix]] of Object.entries(openApiFields)) {
    const field = suffix => (document.getElementById('openapi' + prefix + suffix)?.value || '').trim();
    const stored = userOpenApiSnapshot[broker] || {};
    const key = field('Key'), secret = field('Secret'), account = field('AccountNo');
    const changedKey = key && key !== (stored.app_key || '');
    const changedAccount = account && !account.includes('*');
    if (!changedKey && !secret && !changedAccount) continue;
    payload[broker] = {app_key: key || stored.app_key || '', app_secret: secret};
    if (changedAccount) payload[broker].account_no = account;
  }
  if (!Object.keys(payload).length) { toast('변경할 인증정보를 입력해 주세요.'); return; }
  if (statusMsg) statusMsg.style.display = 'none';

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
    await loadUserOpenApiSettings(Object.keys(payload));
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
  getReadEpoch: () => startupReadEpoch,
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

// ── APP BOOTSTRAP ─────────────────────────────────────────────────────────────
function initAppVersion() {
  const metaVer = document.querySelector('meta[name="application-version"]')?.content;
  const verEl = document.getElementById('appVersionDisplay');
  if (verEl && metaVer) {
    verEl.textContent = `앱 버전 v${metaVer}`;
  }
}

async function bootstrap() {
  brokerImports.initializeScreens();
  initAppTheme();
  initAppVersion();
  initSavingsListeners();
  ledgerFeature.initListeners();
  initPnlMonthNavListeners();
  initDividendMonthNavListeners();
  setupAutoAdvancingDateInput("#pnlSplitDateWrap");
  setupAutoAdvancingDateInput("#divSplitDateWrap");
  setupAutoAdvancingDateInput("#ledgerTxSplitDateWrap");
  setupAutoAdvancingDateInput("#ledgerPaySplitDateWrap");
  brokerImports.bindEvents();
  await initAuthSession();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}

window.addEventListener('wealth:view', ({ detail }) => {
  // Hidden subview notifications must not cancel a direct dividend entry.
  const activeView = document.querySelector('.wealth-workspace')?.dataset.activeView;
  if (activeView ? activeView !== 'income' : detail !== 'income' && detail !== 'ledger') setIncomeTab.cancelPending?.();
  globalThis.WealthStartup?.dashboardRendered(rawDashboard);
  void globalThis.WealthStartup?.loadVisible();
  if (detail === 'invest') renderInvestmentView();
  if (detail === 'ledger' && currentUserProfile && currentUserProfile.username !== 'admin') loadLedger();
});
window.addEventListener('wealth:role', ({ detail }) => {
  if (!detail.isAdminUser && currentIncomeTab === 'ledger') loadLedger();
});


// WEALTH_KRX_MARKETPLACE_CONFIG_V1
async function loadKrxMarketplaceConfig() {
  const badge = document.getElementById('openapiKrxBadge');
  const login = document.getElementById('openapiKrxLoginId');
  const password = document.getElementById('openapiKrxPassword');
  const del = document.getElementById('openapiKrxDeleteBtn');
  const msg = document.getElementById('openapiKrxMessage');
  if (!badge || !login || !password) return;
  try {
    const res = await fetch('/api/user/krx-marketplace-config', { cache: 'no-store' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'KRX 설정 조회 실패');
    badge.textContent = data.configured ? '\uC5F0\uACB0\uB428' : '\uBBF8\uC124\uC815';
    badge.className = `openapi-badge ${data.configured ? 'connected' : 'disconnected'}`;
    login.value = '';
    login.placeholder = data.login_id || 'KRX 아이디';
    password.value = '';
    password.placeholder = data.password_configured ? '******** (변경 시에만 입력)' : 'KRX 비밀번호';
    if (del) del.style.display = data.configured || data.login_id_configured ? '' : 'none';
    if (msg) msg.textContent = '자격증명은 이 사용자 전용 data/users/<username>/secrets에 저장됩니다.';
  } catch (err) {
    if (msg) msg.textContent = 'KRX 설정을 불러오지 못했습니다.';
    throw new Error('KRX_CONFIG_LOAD_FAILED');
  }
}

async function saveKrxMarketplaceConfig() {
  const login = document.getElementById('openapiKrxLoginId');
  const password = document.getElementById('openapiKrxPassword');
  const msg = document.getElementById('openapiKrxMessage');
  const payload = {};
  if (login?.value.trim()) payload.login_id = login.value.trim();
  if (password?.value) payload.password = password.value;
  if (!Object.keys(payload).length) { if (msg) msg.textContent = '변경할 아이디 또는 비밀번호를 입력해 주세요.'; return; }
  try {
    const res = await fetch('/api/user/krx-marketplace-config', {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'KRX 설정 저장 실패');
    if (msg) msg.textContent = data.message || '저장되었습니다.';
    await loadKrxMarketplaceConfig();
  } catch (err) { if (msg) msg.textContent = err?.message || 'KRX 설정 저장에 실패했습니다.'; }
}

async function testKrxMarketplaceConfig() {
  const msg = document.getElementById('openapiKrxMessage');
  const badge = document.getElementById('openapiKrxBadge');

  if (msg) msg.textContent = 'KRX login check...';

  try {
    const res = await fetch('/api/user/krx-marketplace-config/test', {
      method: 'POST',
    });
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'KRX connection check failed');
    }

    if (badge) {
      badge.textContent = data.valid
        ? '\uC5F0\uACB0\uB428'
        : '\uC5F0\uACB0 \uC2E4\uD328';
      badge.className = `openapi-badge ${
        data.valid ? 'connected' : 'disconnected'
      }`;
    }

    if (msg) {
      msg.textContent =
        data.message ||
        (data.valid
          ? '\uC5F0\uACB0 \uC815\uC0C1'
          : '\uC5F0\uACB0 \uC2E4\uD328');
    }
  } catch (err) {
    if (badge) {
      badge.textContent = '\uC5F0\uACB0 \uC2E4\uD328';
      badge.className = 'openapi-badge disconnected';
    }

    if (msg) {
      msg.textContent =
        err?.message || 'KRX connection check failed';
    }
  }
}

async function deleteKrxMarketplaceConfig() {
  if (!window.confirm('저장된 KRX Data Marketplace 아이디와 비밀번호를 삭제할까요?')) return;
  const msg = document.getElementById('openapiKrxMessage');
  try {
    const res = await fetch('/api/user/krx-marketplace-config', { method: 'DELETE' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'KRX 설정 삭제 실패');
    if (msg) msg.textContent = data.message || '삭제되었습니다.';
    await loadKrxMarketplaceConfig();
  } catch (err) { if (msg) msg.textContent = err?.message || 'KRX 설정 삭제에 실패했습니다.'; }
}

window.saveKrxMarketplaceConfig = saveKrxMarketplaceConfig;
window.testKrxMarketplaceConfig = testKrxMarketplaceConfig;
window.deleteKrxMarketplaceConfig = deleteKrxMarketplaceConfig;
