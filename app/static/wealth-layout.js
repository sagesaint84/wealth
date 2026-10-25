/* Navigation and presentation only. Existing panels, handlers and owner rules are retained. */
(() => {
  'use strict';
  const donutKeyAtPointer = (segments, { x, y, innerRadius, outerRadius }) => {
    const distance = Math.hypot(x, y);
    if (!Number.isFinite(distance) || distance < innerRadius || distance > outerRadius) return null;
    // CSS conic-gradient starts at 12 o'clock and proceeds clockwise.
    const percent = ((Math.atan2(y, x) * 180 / Math.PI + 450) % 360) / 3.6;
    return segments.find(segment => percent >= segment.start && percent < segment.end)?.key || null;
  };
  // Kept small and data-only so the donut geometry can be regression-tested without a DOM.
  window.WealthDonutHitTest = donutKeyAtPointer;
  // Presentation only. Never substitute legacy valuation fields for paid-in
  // principal, nor combine period-based pensions with lump-sum/refund inputs.
  window.WealthInsuranceReturnDisplay = (accounts, owner = '모두') => {
    const items = (accounts || []).filter(item => owner === '모두' || (item.owner || '모두') === owner);
    const limit = '기간·향후 추가 납입·세금 절감액 미반영. 연환산·IRR·확정 수익률이 아닙니다.';
    let included = 0;
    const scope = () => `${!included ? '산정 가능 상품 없음' : included === items.length ? '전체 상품 기준' : '일부 상품 기준'} · ${included}/${items.length}개 상품 산정`;
    const unavailable = reason => ({rate: null, included, total: items.length, scope: scope(), description: `예상 단순수익률 미산정: ${reason}. ${limit}`});
    if (!items.length) return unavailable('대상 상품 없음');
    let paid = 0, expected = 0;
    for (const item of items) {
      if ((item.payout_type && item.payout_type !== 'lump_sum') ||
          ['national_pension', 'irp'].includes(item.insurance_type) ||
          Number(item.monthly_payout) > 0) {
        continue; // National pension/IRP/monthly pensions have a separate analysis.
      }
      if (!Number.isFinite(item.total_paid_amount) || item.total_paid_amount <= 0 ||
          !Number.isFinite(item.expected_amount) || item.expected_amount < 0 ||
          (item.monthly_payout != null && (!Number.isFinite(item.monthly_payout) || item.monthly_payout < 0)) ||
          (item.converted_total_asset != null &&
            (!Number.isFinite(item.converted_total_asset) || item.converted_total_asset !== item.expected_amount))) {
        continue;
      }
      paid += item.total_paid_amount;
      expected += item.expected_amount;
      included += 1;
    }
    if (!included) return unavailable('연금형 또는 누적납입액·예상 수령액 근거 누락/불일치 상품만 존재');
    const rate = (expected - paid) / paid * 100;
    if (!Number.isFinite(paid) || !Number.isFinite(expected) || !Number.isFinite(rate)) return unavailable('비정상 합계');
    return {rate, included, total: items.length, scope: scope(), description: `예상 단순수익률: 일시금/해약환급금 입력액과 누적납입액 비교. ${scope()}. ${limit}`};
  };
  // Display policy only: keep authoritative weights/amounts/rates untouched.
  window.WealthAssetReturnDisplay = (item, property = null, insurance = null) => {
    if (item.name === '보험') return Number.isFinite(insurance?.rate) ? insurance.rate : null;
    if (['현금·예수금', '임차보증금'].includes(item.name)) return null;
    const source = item.name === '부동산' ? property : {
      rate: item.return_rate, profit: item.profit_krw, cost: item.cost_value_krw,
    };
    if (!source || !Number.isFinite(source.rate) || !Number.isFinite(source.profit)
        || !Number.isFinite(source.cost) || source.cost <= 0) return null;
    return source.rate;
  };
  const root = document.getElementById('userAssetDashboardWrapper');
  if (!root) return;
  const routeState = window.WealthWorkspaceRoute;
  // The initial HTML already contains the current workspace and final panel parents.
  const layout = root.querySelector('.wealth-workspace');
  if (!layout) return;
  const page = key => layout.querySelector(`[data-wealth-page="${key}"]`);
  page('settings').insertAdjacentHTML('afterbegin', window.WealthSettingsSurfaceMarkup());
  const move = (id, target) => { const node = document.getElementById(id); if (node) target.append(node); };
  const recordSide = document.getElementById('recordsPanel')?.querySelector('.record-side');
  const recordToolbar = document.getElementById('recordsPanel')?.querySelector('.records-head .toolbar');
  if (recordSide && recordToolbar) {
    const detailHead = document.createElement('div');
    detailHead.className = 'wealth-record-detail-head';
    detailHead.innerHTML = '<strong>기록 상세 보기</strong>';
    detailHead.append(recordToolbar);
    recordSide.prepend(detailHead);
  }
  const assetCategoryTabs = document.createElement('div');
  assetCategoryTabs.id = 'assetCategoryTabs';
  assetCategoryTabs.className = 'account-category-tabs wealth-section-tabs';
  assetCategoryTabs.setAttribute('role', 'tablist');
  assetCategoryTabs.setAttribute('aria-label', '자산 종류 선택');
  assetCategoryTabs.innerHTML = `
    <button type="button" class="account-cat-tab active" data-cat="securities">📈 증권</button>
    <button type="button" class="account-cat-tab" data-cat="banking">🏦 은행</button>
    <button type="button" class="account-cat-tab" data-cat="insurance">🛡️ 연금·보험</button>
    <button type="button" class="account-cat-tab" data-cat="real_estate">🏠 부동산</button>
    <button type="button" class="account-cat-tab" data-cat="tax">🧾 세금</button>`;
  const assetPanels = {securities:'catPanelSecurities',banking:'catPanelBanking',insurance:'catPanelInsurance',real_estate:'catPanelRealEstate',tax:'catPanelTax'};
  const taxPanel=document.createElement('section');taxPanel.id='catPanelTax';taxPanel.setAttribute('role','tabpanel');
  taxPanel.setAttribute('aria-label','세금 정보');document.getElementById('accountsPanel').append(taxPanel);
  assetCategoryTabs.querySelectorAll('button').forEach(button => {
    const active = button.dataset.cat === (window.WealthAssetCategoryState?.current() || 'securities');
    button.setAttribute('role','tab'); button.setAttribute('aria-controls',assetPanels[button.dataset.cat]);
    button.setAttribute('aria-selected',String(active)); button.classList.toggle('active',active);
  });
  page('assets').prepend(assetCategoryTabs);
  const revealAssetTab = button => {
    if (!button || !assetCategoryTabs.getClientRects().length) return;
    const tab = button.getBoundingClientRect(), strip = assetCategoryTabs.getBoundingClientRect();
    if (tab.left < strip.left || tab.right > strip.right) {
      button.scrollIntoView({block:'nearest', inline:'nearest', behavior:'instant'});
    }
  };
  assetCategoryTabs.addEventListener('click', event => revealAssetTab(event.target.closest('button')));
  assetCategoryTabs.addEventListener('focusin', event => revealAssetTab(event.target.closest('button')));
  window.addEventListener('wealth:view', ({detail}) => {
    if (detail === 'assets') revealAssetTab(assetCategoryTabs.querySelector('[aria-selected="true"]'));
  });
  const incomeTabs = document.createElement('div');
  incomeTabs.id = 'incomeTabs';
  incomeTabs.className = 'wealth-section-tabs income-tabs';
  incomeTabs.setAttribute('role', 'tablist');
  incomeTabs.setAttribute('aria-label', '머니 로그 항목 선택');
  incomeTabs.innerHTML = `
    <button type="button" class="income-tab active" data-income="calendar" role="tab" aria-selected="true">📅 캘린더</button>
    <button type="button" class="income-tab" data-income="pnl" role="tab" aria-selected="false">📈 실현손익</button>
    <button type="button" class="income-tab" data-income="dividend" role="tab" aria-selected="false">💰 배당·이자</button>
    <button type="button" class="income-tab" data-income="ledger" role="tab" aria-selected="false">🧾 가계부</button>
    <button type="button" class="income-tab" data-income="ipo" role="tab" aria-selected="false">🔔 공모주</button>`;
  // Select detached tabs before insertion; the core reuses this same route state.
  const initialIncomeTab = routeState.resolve().incomeTab;
  incomeTabs.querySelectorAll('[data-income]').forEach(button => {
    const active = button.dataset.income === initialIncomeTab;
    button.classList.toggle('active', active);
    button.setAttribute('aria-selected', String(active));
  });
  page('income').prepend(incomeTabs);
  const accountsPanel = document.getElementById('accountsPanel');
  function enhanceAccountLists() {
    accountsPanel.querySelectorAll('.mini-delete-button').forEach(button => {
      if (button.closest('.wealth-row-more')) return;
      const more = document.createElement('details');
      more.className = 'wealth-row-more';
      const summary = document.createElement('summary');
      summary.textContent = '⋯';
      summary.setAttribute('aria-label', '추가 작업');
      button.before(more);
      more.append(summary, button);
      button.textContent = '삭제';
      button.setAttribute('aria-label', button.title || '삭제');
    });
    const labels = ['은행', '계좌 이름', '계좌 번호', '소유자', '잔고 (KRW)', '메모', '관리'];
    accountsPanel.querySelectorAll('.banks-table tbody tr').forEach(row => {
      [...row.cells].forEach((cell, index) => { cell.dataset.label = labels[index] || ''; });
    });
  }
  new MutationObserver(enhanceAccountLists).observe(accountsPanel, { childList: true, subtree: true });
  enhanceAccountLists();
  const settingsCard = page('settings').querySelector('.wealth-settings-card');
  const actions = settingsCard.querySelector('.wealth-settings-actions');
  const footer = document.getElementById('appCommonFooter');
  const footerParent = footer?.parentNode;
  if (footer) page('settings').append(footer);
  const danger = document.getElementById('clearButton');
  if (danger) {
    const disclosure = document.createElement('details');
    disclosure.className = 'wealth-danger-zone';
    disclosure.innerHTML = '<summary>데이터 삭제 · 주의가 필요한 작업</summary><p>백업을 먼저 확인하세요. 삭제 시 기존 확인 절차가 진행됩니다.</p>';
    disclosure.append(danger);
    page('settings').append(disclosure);
  }
  window.addEventListener('wealth:role', ({ detail }) => {
    const headerActions = document.querySelector('.topbar-actions');
    if (detail.isAdminUser) {
      if (footer && footerParent) footerParent.append(footer);
      move('topbarFamilyBtn', headerActions);
      if (danger && footer) footer.append(danger);
    } else {
      move('changePwBtn', actions);
      const logout = headerActions?.querySelector('a[href="/logout"]');
      if (logout) actions.append(logout);
    }
  });
  const homeTabs = document.getElementById('homeTabs');
  const homeButtons = [...homeTabs.querySelectorAll('[data-home-tab]')];
  const selectHomeTab = button => {
    if (!button || button.getAttribute('aria-selected') === 'true') return;
    location.hash = button.dataset.homeTab === 'portfolio' ? 'home' : `home/${button.dataset.homeTab}`;
  };
  homeTabs.addEventListener('click', event => selectHomeTab(event.target.closest('[data-home-tab]')));
  homeTabs.addEventListener('keydown', event => {
    const index = homeButtons.indexOf(event.target);
    if (index < 0) return;
    const target = {ArrowRight:(index+1)%3, ArrowLeft:(index+2)%3, Home:0, End:2}[event.key];
    if (target === undefined) return;
    event.preventDefault();
    homeButtons[target].focus({preventScroll:true});
    selectHomeTab(homeButtons[target]);
  });
  let activeView = null;
  function navigate(focus = false) {
    const { requested, key, incomeTab } = routeState.sync();
    layout.querySelectorAll('[data-wealth-page]').forEach(node => { node.hidden = node.dataset.wealthPage !== key; });
    if (focus && activeView !== key) {
      document.getElementById('wealthPageTitle').focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: 'instant' });
    }
    activeView = key;
    if (key === 'income') {
      window.setIncomeTab?.(incomeTab, { updateHash: false });
    }
    window.dispatchEvent(new CustomEvent('wealth:view', { detail: requested === 'ledger' ? 'ledger' : key }));
  }
  window.addEventListener('hashchange', () => navigate(true));
  layout.querySelector('.wealth-skip').addEventListener('click', event => {
    event.preventDefault();
    document.getElementById('wealthPageTitle').focus();
  });
  navigate();
  const won = value => `${Math.round(value).toLocaleString('ko-KR')}원`;
  const signedWon = value => `${Number(value) >= 0 ? '+' : ''}${won(Number(value) || 0)}`;
  const pct = value => `${Number(value) >= 0 ? '+' : ''}${Number(value || 0).toFixed(2)}%`;
  const setText = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
  const setSigned = (id, value, formatter = signedWon) => { const el = document.getElementById(id); if (!el) return; const n = Number(value); el.textContent = formatter(value); el.classList.toggle('is-positive', Number.isFinite(n) && n > 0); el.classList.toggle('is-negative', Number.isFinite(n) && n < 0); };
  const investmentShares = (stock, property) => {
    const total = stock + property;
    if (!Number.isFinite(stock) || !Number.isFinite(property) || !Number.isFinite(total) || total <= 0) return ['—', '—'];
    return [stock, property].map(value => {
      const ratio = value / total * 100;
      return Number.isFinite(ratio) ? `${ratio.toFixed(1)}%` : '—';
    });
  };
  const investmentDetail = (value, share) => `${Number.isFinite(value) ? won(value) : '—'} (${share})`;
  let lastAssetSummary = null;
  window.addEventListener('wealth:summary', ({ detail: s }) => {
    lastAssetSummary = s;
    setText('wealthAssetNetWorth', won(s.netWorth));
    setText('wealthAssetInvest', won(s.invest));
    setText('wealthAssetExpected', won(s.expected));
    setText('wealthAssetRealized', won(s.realized));
    setText('wealthAssetSafe', won(s.safe));
    setText('wealthAssetDebtDetail', won(s.debt));
    const [stockShare, propertyShare] = investmentShares(s.stock, s.property);
    setText('wealthAssetPropertyDetail', investmentDetail(s.property, propertyShare));
    setText('wealthAssetStockDetail', investmentDetail(s.stock, stockShare));
    setSigned('wealthAssetPropertyExpected', s.propertyExpected, value => `${signedWon(value)} (${pct(s.propertyExpectedRate)})`);
    setSigned('wealthAssetStockExpected', s.stockExpected, value => `${signedWon(value)} (${pct(s.stockExpectedRate)})`);
    setSigned('wealthAssetDayDetail', s.dayProfit);
    setText('wealthAssetDayDate', s.dayDate ? `${s.dayDate} 대비` : '전일 대비');
    setSigned('wealthAssetTradeDetail', s.realizedTrade);
    setSigned('wealthAssetDividendDetail', s.dividendInterest);
    setText('wealthAssetYearDetail', signedWon(s.realizedYear));
    setText('wealthAssetMonthDetail', signedWon(s.realizedMonth));
    setText('wealthAssetSafeDetail', won(s.cash));
    setText('wealthAssetDepositDetail', won(s.deposits));
    setText('wealthAssetInsuranceDetail', won(s.insurance));
    const palette = ['#9b8afb','#61c9b2','#6ea6ec','#e7bc71','#c891bd','#5aa9cf','#ef7b8e','#8bbf74','#a9a1d6'];
    const items = (s.classifications || []).filter(item => Number(item.market_value_krw || 0) > 0).map((item, index) => ({ ...item, color: window.WealthColorPreferences.register('asset_category_colors',item,palette[index % palette.length]), colorKey: window.WealthColorPreferences.keyFor('asset_category_colors',item) }));
    const total = items.reduce((sum, item) => sum + Math.max(0, Number(item.market_value_krw || 0)), 0);
    const donut = document.getElementById('homeAssetAllocationDonut');
    const donutLegend = document.getElementById('homeAssetAllocationLegend');
    const legend = document.getElementById('wealthMixLegend');
    donutLegend.replaceChildren(); legend.replaceChildren();
    let cursor = 0;
    const segments = items.map((item, index) => { const share = total > 0 ? Math.max(0, Number(item.market_value_krw || 0)) / total * 100 : 0; const start = cursor; cursor += share; return {...item, key:`asset-${index}`, start, end:cursor}; });
    const paintDonut = active => { const stops=segments.map(segment => `${segment.color}${active && active!==segment.key ? '80' : ''} ${segment.start}% ${segment.end}%`); donut.style.background=stops.length?`conic-gradient(${stops.join(',')})`:'var(--line)'; donut.classList.toggle('has-donut-hover',Boolean(active)); };
    paintDonut(null);
    document.getElementById('homeAssetAllocationTotal').textContent = won(total);
    segments.forEach(item => {
      const row = document.createElement('span'); row.style.setProperty('--mix-color', item.color); row.dataset.donutKey=item.key; row.dataset.colorKey=item.colorKey; row.tabIndex=0;
      const name = document.createElement('span'); name.textContent = item.name;
      const weight = document.createElement('strong'); weight.textContent = `${Number(item.weight || 0).toFixed(1)}%`;
      row.append(name, weight); donutLegend.append(row);
    });
    const activate = key => { paintDonut(key); donutLegend.querySelectorAll('[data-donut-key]').forEach(row=>row.classList.toggle('is-donut-active',row.dataset.donutKey===key)); };
    const fromPointer = event => { const rect=donut.getBoundingClientRect(), x=event.clientX-rect.left-rect.width/2, y=event.clientY-rect.top-rect.height/2, outer=Math.min(rect.width,rect.height)/2; activate(donutKeyAtPointer(segments,{x,y,innerRadius:outer*.42,outerRadius:outer})); };
    donut.onpointermove=fromPointer; donut.onpointerleave=()=>activate(null);
    donutLegend.querySelectorAll('[data-donut-key]').forEach(row=>{row.onpointerenter=()=>activate(row.dataset.donutKey);row.onpointerleave=()=>activate(null);row.onfocus=()=>activate(row.dataset.donutKey);row.onblur=()=>activate(null);});
    items.forEach(item => {
      const label = item.name; const value = Number(item.market_value_krw || 0); const color = item.color;
      const row = document.createElement('div');
      const name = document.createElement('span'); name.textContent = label; name.style.setProperty('--mix-color', color); row.dataset.colorKey=item.colorKey;
      const amount = document.createElement('strong'); amount.textContent = won(value);
      let secondary = `${Number(item.holding_count || 0)}종목 · 비중 ${Number(item.weight || 0).toFixed(1)}%`;
      if (label === '부동산') secondary = `부동산 평가액 · 비중 ${Number(item.weight || 0).toFixed(1)}%`;
      else if (label === '현금·예수금') secondary = `은행 예수금 포함 · 예적금 포함 · 비중 ${Number(item.weight || 0).toFixed(1)}%`;
      else if (label === '보험') secondary = `예상 수령액/해약환급금 등 · 비중 ${Number(item.weight || 0).toFixed(1)}%`;
      const detail = document.createElement('small'); detail.textContent = secondary;
      const metric = document.createElement('b');
      const returnRate = window.WealthAssetReturnDisplay(item, {
        rate: s.propertyExpectedRate, profit: s.propertyExpected, cost: s.propertyPurchaseValue,
      }, s.insuranceReturn);
      metric.textContent = returnRate === null ? '—' : pct(returnRate);
      if (label === '보험' && returnRate === 0) metric.textContent = '0.00%';
      metric.className = returnRate === null ? 'muted' : (returnRate >= 0 ? 'up' : 'down');
      metric.dataset.metric = 'return-rate';
      const metricLabel = label === '보험'
        ? `${returnRate === null ? '수익률 미산정' : `수익률 ${metric.textContent}`} · ${s.insuranceReturn?.description || '예상 단순수익률 미산정: 근거 없음'}`
        : (returnRate === null ? '수익률 미산정' : `수익률 ${metric.textContent}`);
      metric.title = metricLabel;
      metric.setAttribute('aria-label', metricLabel);
      const title = document.createElement('div'); title.append(name, detail);
      const values = document.createElement('div'); values.append(amount, metric);
      if (label === '보험' && s.insuranceReturn) {
        const scopeLabel = document.createElement('small');
        scopeLabel.dataset.insuranceRoiScope = '';
        scopeLabel.textContent = s.insuranceReturn.scope;
        scopeLabel.className = 'insurance-roi-scope';
        values.append(scopeLabel);
      }
      row.append(title, values); legend.append(row);
    });
  });
  window.addEventListener('wealth:colors', () => { if(lastAssetSummary) window.dispatchEvent(new CustomEvent('wealth:summary',{detail:lastAssetSummary})); });
})();

// Settings operational status is an optional UI module. It fails independently
// so dashboard navigation remains available even if the module cannot load.
import('/static/wealth-automation-status.js?v=10.9h1').catch(() => {});
