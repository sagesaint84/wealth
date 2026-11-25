

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
      const pnlView = dashboardOwnerModel.buildRealizedPnlDisplaySummary(pnlRes, [], true);
      totalPnl = pnlView.totalPnlKrw;

      const summaryPnlEl = $("#summaryRealizedPnl");
      if (summaryPnlEl) {
        summaryPnlEl.textContent = `${totalPnl > 0 ? '+' : ''}${money(totalPnl)}`;
        summaryPnlEl.className = `${totalPnl > 0 ? 'gain up' : (totalPnl < 0 ? 'loss down' : '')}`;
      }
      investmentSummaryView.renderRealizedPnlCaption(pnlView);
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

const dashboardOwnerModel = window.WealthDashboardOwnerModel;
const dashboardInputs = {
  get rawDashboard() { return rawDashboard; },
  get allAssetRecords() { return allAssetRecords; },
  get pnlData() { return pnlData; },
  get actualDividendData() { return actualDividendData; },
  get rawLoanAccounts() { return accountFeature.rawLoanAccounts; },
  get rawBankAccounts() { return accountFeature.rawBankAccounts; },
  get rawSavingsAccounts() { return accountFeature.rawSavingsAccounts; },
  get rawInsuranceAccounts() { return insuranceFeature.rawInsuranceAccounts; },
  get rawRealEstates() { return realEstateFeature.rawRealEstates; },
};

Object.assign(window, {
  computeFilteredSummary: dashboardOwnerModel.computeFilteredSummary,
  classifyHolding: dashboardOwnerModel.classifyHolding,
  computeFilteredSectors: dashboardOwnerModel.computeFilteredSectors,
  computeFilteredCurrencySummary: dashboardOwnerModel.computeFilteredCurrencySummary,
  calculateDashboardDebt: dashboardOwnerModel.calculateDashboardDebt,
  finiteRealizedPnlNumber: dashboardOwnerModel.finiteRealizedPnlNumber,
  summarizeRealizedPnlRows: dashboardOwnerModel.summarizeRealizedPnlRows,
  buildRealizedPnlDisplaySummary: dashboardOwnerModel.buildRealizedPnlDisplaySummary,
});

function computeFilteredClassifications(holdings, accounts, fxRates, owner = '모두', rawData = null) {
  return dashboardOwnerModel.computeFilteredClassifications(holdings, accounts, fxRates, owner, rawData, dashboardInputs);
}

function computeFilteredDayChange(holdings, rawDayChange, owner = '모두', currentTotalValue = 0) {
  return dashboardOwnerModel.computeFilteredDayChange(holdings, rawDayChange, owner, currentTotalValue, dashboardInputs);
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

  const filteredData = dashboardOwnerModel.buildOwnerDashboard(src, effectiveOwner, dashboardInputs);
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
  classifyHolding: dashboardOwnerModel.classifyHolding,
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
const investmentSummaryView = window.WealthInvestmentSummaryView.create({ $, money, number });

function renderSummary(data) {
  const owner = currentOwner || '모두';
  const { card, home } = dashboardOwnerModel.buildDashboardSummary(data, owner, dashboardInputs, getKstYearMonth);
  investmentSummaryView.renderSummary(card);
  window.dispatchEvent(new CustomEvent('wealth:summary', { detail: {
    ...home,
    insuranceReturn: window.WealthInsuranceReturnDisplay?.(data.insurance_accounts || dashboardInputs.rawInsuranceAccounts || [], owner),
  }}));
}

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
  buildRealizedPnlDisplaySummary: dashboardOwnerModel.buildRealizedPnlDisplaySummary,
  get currentOwner() { return currentOwner; },
  get dashboard() { return dashboard; },
  finiteRealizedPnlNumber: dashboardOwnerModel.finiteRealizedPnlNumber,
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
