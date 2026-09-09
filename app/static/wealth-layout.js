/* Navigation and presentation only. Existing panels, handlers and owner rules are retained. */
(() => {
  'use strict';
  const root = document.getElementById('userAssetDashboardWrapper');
  if (!root) return;
  const views = {
    home: ['홈', '가족의 자산을 한눈에', '지금의 자산 현황을 확인하고, 필요한 관리로 이어가세요.'],
    invest: ['투자', '주식 현황', '주식 포트폴리오, 보유종목과 투자 기록을 한곳에서 확인하세요.'],
    assets: ['자산·계좌', '자산과 계좌 관리', '증권·은행·보험·부동산과 대출을 관리하세요.'],
    income: ['손익·배당', '투자의 결실', '실현손익과 배당 내역을 확인하세요.'],
    ledger: ['가계부', '생활의 현금 흐름', '수입·지출, 카드와 고정지출을 관리하세요.'],
    settings: ['설정', '나에게 맞는 Wealth', '가족 구성원, 증권사 연결, 테마와 백업을 관리하세요.'],
  };
  const icons = {
    home: '<path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/>',
    invest: '<path d="M4 20V4M4 20h17M8 15l4-5 4 2 5-8"/>',
    assets: '<rect x="3" y="6" width="18" height="15" rx="2"/><path d="M3 10h18M7 6V3h10v3M15 15h3"/>',
    income: '<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    ledger: '<rect x="5" y="3" width="15" height="18" rx="2"/><path d="M3 7h4M3 12h4M3 17h4M11 8h5M11 12h5M11 16h3"/>',
    settings: '<path d="M4 7h16M4 17h16"/><circle cx="8" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',
  };
  const icon = key => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[key]}</svg>`;
  const link = key => `<a href="#${key}" data-wealth-view="${key}">${icon(key)}<span>${views[key][0]}</span></a>`;
  const layout = document.createElement('div');
  layout.className = 'wealth-workspace';
  layout.innerHTML = `
    <a class="wealth-skip" href="#wealthPageTitle">본문으로 건너뛰기</a>
    <nav class="wealth-nav" aria-label="주요 메뉴">
      <div class="wealth-nav-label">MY WEALTH</div>
      ${Object.keys(views).slice(0, 5).map(link).join('')}
      <div class="wealth-nav-bottom">${link('settings')}<small>개인 · 가족 자산관리</small></div>
    </nav>
    <div class="wealth-content">
      <div class="wealth-page-head"><div><p class="wealth-eyebrow">YOUR FINANCIAL OVERVIEW</p><h2 id="wealthPageTitle" tabindex="-1"></h2><p id="wealthPageDescription"></p></div><a class="wealth-settings-link" href="#settings" aria-label="설정 열기">${icon('settings')}</a></div>
      <div class="wealth-owner-bar"><span>조회 범위</span><div id="wealthOwnerSlot"></div></div>
      <section data-wealth-page="home" aria-label="자산 요약">
        <div class="wealth-home-grid">
          <article class="wealth-net-card"><div class="wealth-card-top"><span>나의 순자산</span><span class="wealth-live-label" id="wealthOwnerLabel">전체 가족</span></div><strong id="wealthNetWorth">—</strong><p>등록 자산에서 부채를 뺀 금액</p><div class="wealth-net-bottom"><span id="wealthHomeUpdated">자산 정보를 불러오는 중입니다.</span><a id="wealthNetWorthDetails" href="#homeAssetPortfolioPanel">상세 현황 <span aria-hidden="true">↗</span></a></div></article>
          <article class="wealth-stat-card"><span class="wealth-stat-icon">${icon('assets')}</span><h3>현금·예적금</h3><strong id="wealthCash">—</strong><p>은행 잔액 · 증권 예수금 · 예적금</p><a href="#assets">계좌 살펴보기 →</a></article>
          <article class="wealth-stat-card"><span class="wealth-stat-icon wealth-debt-icon">${icon('ledger')}</span><h3>총부채</h3><strong id="wealthDebt">—</strong><p>대출 · 음수 잔액 · 임대보증금 반환의무</p><a href="#assets">부채 확인하기 →</a></article>
        </div>
        <article class="wealth-composition wealth-home-asset-portfolio" id="homeAssetPortfolioPanel" tabindex="-1"><div class="wealth-section-heading"><div><p class="wealth-eyebrow">ASSET PORTFOLIO</p><h3>자산 포트폴리오</h3></div><a href="#assets">자산 상세보기 ↗</a></div><p class="wealth-help">전체 자산의 핵심 지표와 자산군별 구성을 한눈에 확인하세요.</p><div class="wealth-asset-dashboard"><div id="wealthAssetKpis" class="wealth-asset-kpis" aria-label="자산 포트폴리오 요약"><article class="wealth-asset-kpi tone-net"><span class="wealth-asset-kpi-icon">◆</span><div><span>순자산</span><strong id="wealthAssetNetWorth">—</strong><small id="wealthAssetDebtDetail">총부채 —</small></div></article><article class="wealth-asset-kpi tone-invest"><span class="wealth-asset-kpi-icon">◈</span><div><span>투자자산</span><strong id="wealthAssetInvest">—</strong><small id="wealthAssetInvestDetail">부동산 — · 주식 —</small></div></article><article class="wealth-asset-kpi tone-profit"><span class="wealth-asset-kpi-icon">↗</span><div><span>기대수익</span><strong id="wealthAssetExpected">—</strong><small id="wealthAssetExpectedRate">수익률 —</small><small id="wealthAssetDayDetail">일간 수익 — · 전일 대비</small></div></article><article class="wealth-asset-kpi tone-realized"><span class="wealth-asset-kpi-icon">▤</span><div><span>실현손익</span><strong id="wealthAssetRealized">—</strong><small id="wealthAssetRealizedDetail">매매차익 — · 배당/이자 —</small><small id="wealthAssetRealizedPeriod">연간 — · 월간 —</small></div></article><article class="wealth-asset-kpi tone-safe"><span class="wealth-asset-kpi-icon">◇</span><div><span>안전자산</span><strong id="wealthAssetSafe">—</strong><small id="wealthAssetSafeDetail">예수금 및 예금 —</small><small id="wealthAssetSafeBreakdown">임차보증금 — · 보험 —</small></div></article></div><div class="wealth-asset-allocation"><div class="wealth-asset-allocation-head"><div><span class="wealth-eyebrow">ASSET ALLOCATION</span><h4>전체 자산 구성</h4></div><div id="homeAssetAllocationDonut" class="wealth-asset-donut" role="img" aria-label="전체 자산 구성"><span>전체 자산</span><strong id="homeAssetAllocationTotal">—</strong></div><div id="homeAssetAllocationLegend" class="wealth-asset-donut-legend"></div></div><div id="wealthMixLegend" class="wealth-mix-legend wealth-asset-breakdown"><p class="wealth-help">자산 정보가 준비되면 구성을 표시합니다.</p></div></div></div></article>
        <div class="wealth-home-secondary"><article class="wealth-shortcuts"><p class="wealth-eyebrow">QUICK ACCESS</p><h3>오늘의 자산 관리</h3><a href="#ledger">${icon('ledger')}<span><strong>수입과 지출 정리</strong><small>가계부 · 카드 · 고정지출</small></span><b aria-hidden="true">↗</b></a><a href="#income">${icon('income')}<span><strong>손익과 배당 확인</strong><small>실현손익 · 배당 내역</small></span><b aria-hidden="true">↗</b></a><a href="#assets">${icon('assets')}<span><strong>자산 정보 관리</strong><small>계좌 · 대출 · 보험 · 부동산</small></span><b aria-hidden="true">↗</b></a></article></div>
        <div id="wealthMarketSlot"></div>
      </section>
      ${Object.keys(views).filter(key => key !== 'home').map(key => `<section data-wealth-page="${key}" aria-label="${views[key][0]}" hidden></section>`).join('')}
    </div>`;
  root.prepend(layout);
  // Turn compact legacy secondary strings into explicit label/value rows.
  const splitMetricRows = (card, rows) => {
    if (!card) return;
    const content = card.querySelector(':scope > div:last-child');
    if (!content) return;
    const primary = content.querySelector('strong');
    [...content.querySelectorAll('small')].forEach(node => node.remove());
    rows.forEach(([label, id, initial]) => {
      const row = document.createElement('span');
      row.className = 'wealth-asset-secondary-row';
      const key = document.createElement('em'); key.textContent = label;
      const value = document.createElement('small'); value.id = id; value.textContent = initial;
      row.append(key, value);
      primary?.after(row);
    });
  };
  splitMetricRows(document.querySelector('.wealth-asset-kpi.tone-net'), [['총부채', 'wealthAssetDebtDetail', '—']]);
  splitMetricRows(document.querySelector('.wealth-asset-kpi.tone-invest'), [['부동산', 'wealthAssetPropertyDetail', '—'], ['주식', 'wealthAssetStockDetail', '—']]);
  splitMetricRows(document.querySelector('.wealth-asset-kpi.tone-profit'), [['수익률', 'wealthAssetExpectedRate', '—'], ['일간 수익', 'wealthAssetDayDetail', '—'], ['기준일', 'wealthAssetDayDate', '전일 대비']]);
  splitMetricRows(document.querySelector('.wealth-asset-kpi.tone-realized'), [['매매차익', 'wealthAssetTradeDetail', '—'], ['배당/이자', 'wealthAssetDividendDetail', '—'], ['연간', 'wealthAssetYearDetail', '—'], ['월간', 'wealthAssetMonthDetail', '—']]);
  splitMetricRows(document.querySelector('.wealth-asset-kpi.tone-safe'), [['예수금 및 예금', 'wealthAssetSafeDetail', '—'], ['임차보증금', 'wealthAssetDepositDetail', '—'], ['보험', 'wealthAssetInsuranceDetail', '—']]);
  document.body.classList.add('wealth-layout');
  const page = key => layout.querySelector(`[data-wealth-page="${key}"]`);
  const move = (id, target) => { const node = document.getElementById(id); if (node) target.append(node); };
  move('topbarFamilyTabs', document.getElementById('wealthOwnerSlot'));
  const refreshActions = document.createElement('div');
  refreshActions.className = 'wealth-refresh-actions';
  layout.querySelector('.wealth-owner-bar').append(refreshActions);
  move('refreshButton', refreshActions);
  move('syncAccountsButton', refreshActions);
  document.getElementById('refreshButton').textContent = '시세 갱신';
  document.getElementById('syncAccountsButton').textContent = '계좌 동기화';
  document.getElementById('refreshButton').title = '시세를 갱신합니다. 증권사 잔고 동기화와 별개입니다.';
  document.getElementById('syncAccountsButton').title = '설정된 증권사에서 잔고와 보유종목을 가져옵니다.';
  move('marketPanel', document.getElementById('wealthMarketSlot'));
  ['summaryPanel', 'assetHeatmapPanel', 'holdingsPanel', 'recordsPanel'].forEach(id => move(id, page('invest')));
  // Create page-local navigation exactly where it is used. Keeping these nodes
  // out of the legacy content root prevents orphan tabs if layout relocation fails.
  const assetCategoryTabs = document.createElement('div');
  assetCategoryTabs.id = 'assetCategoryTabs';
  assetCategoryTabs.className = 'account-category-tabs wealth-section-tabs';
  assetCategoryTabs.setAttribute('role', 'tablist');
  assetCategoryTabs.setAttribute('aria-label', '자산 종류 선택');
  assetCategoryTabs.innerHTML = `
    <button type="button" class="account-cat-tab active" data-cat="securities">📈 증권 (<span id="securitiesTabCount">0</span>)</button>
    <button type="button" class="account-cat-tab" data-cat="banking">🏦 은행 (<span id="bankingTabCount">0</span>)</button>
    <button type="button" class="account-cat-tab" data-cat="insurance">🛡️ 보험 (<span id="insuranceTabCount">0</span>)</button>
    <button type="button" class="account-cat-tab" data-cat="real_estate">🏠 부동산 (<span id="realEstateTabCount">0</span>)</button>`;
  page('assets').append(assetCategoryTabs);
  move('accountsPanel', page('assets'));

  const incomeTabs = document.createElement('div');
  incomeTabs.id = 'incomeTabs';
  incomeTabs.className = 'wealth-section-tabs income-tabs';
  incomeTabs.setAttribute('role', 'tablist');
  incomeTabs.setAttribute('aria-label', '손익과 배당 선택');
  incomeTabs.innerHTML = `
    <button type="button" class="income-tab active" data-income="pnl" role="tab" aria-selected="true">실현손익</button>
    <button type="button" class="income-tab" data-income="dividend" role="tab" aria-selected="false">배당·이자</button>`;
  page('income').append(incomeTabs);
  ['realizedPnlPanel', 'dividendPanel'].forEach(id => move(id, page('income')));
  // Preserve delegated edit/delete handlers while placing destructive actions
  // behind an explicit disclosure. Renderers may replace the lists at any time.
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
  move('ledgerSectionPanel', page('ledger'));
  const settingsCard = document.createElement('article');
  settingsCard.className = 'wealth-settings-card';
  settingsCard.innerHTML = '<h3>계정과 연결</h3><p class="wealth-help">가족 구성원과 증권사 연결을 설정합니다. 연결 작업은 버튼을 눌렀을 때 실행됩니다.</p><div class="wealth-settings-actions"></div>';
  page('settings').append(settingsCard);
  const actions = settingsCard.querySelector('.wealth-settings-actions');
  // Retain admin/password actions in the global header for the separate admin view.
  ['topbarFamilyBtn', 'userOpenApiBtn'].forEach(id => move(id, actions));
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
  let activeView = null;
  function navigate(focus = false) {
    const requested = location.hash.slice(1);
    const key = Object.hasOwn(views, requested) ? requested : 'home';
    layout.querySelectorAll('[data-wealth-page]').forEach(node => { node.hidden = node.dataset.wealthPage !== key; });
    layout.querySelectorAll('[data-wealth-view]').forEach(node => {
      if (node.dataset.wealthView === key) node.setAttribute('aria-current', 'page');
      else node.removeAttribute('aria-current');
    });
    document.getElementById('wealthPageTitle').textContent = views[key][1];
    document.getElementById('wealthPageDescription').textContent = views[key][2];
    document.title = `Wealth · ${views[key][0]}`;
    if (focus && activeView !== key) {
      document.getElementById('wealthPageTitle').focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: 'instant' });
    }
    activeView = key;
    layout.dataset.activeView = key;
    // Charts drawn while hidden need their visible dimensions recalculated.
    window.dispatchEvent(new CustomEvent('wealth:view', { detail: key }));
  }
  window.addEventListener('hashchange', () => navigate(true));
  layout.querySelector('.wealth-skip').addEventListener('click', event => {
    event.preventDefault();
    document.getElementById('wealthPageTitle').focus();
  });
  document.getElementById('wealthNetWorthDetails').addEventListener('click', event => {
    event.preventDefault();
    const target = document.getElementById('homeAssetPortfolioPanel');
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    target.focus({ preventScroll: true });
  });
  navigate();
  const won = value => `${Math.round(value).toLocaleString('ko-KR')}원`;
  const signedWon = value => `${Number(value) >= 0 ? '+' : ''}${won(Number(value) || 0)}`;
  const pct = value => `${Number(value) >= 0 ? '+' : ''}${Number(value || 0).toFixed(2)}%`;
  window.addEventListener('wealth:summary', ({ detail: s }) => {
    document.getElementById('wealthNetWorth').textContent = won(s.netWorth);
    document.getElementById('wealthAssetNetWorth').textContent = won(s.netWorth);
    document.getElementById('wealthAssetInvest').textContent = won(s.invest);
    document.getElementById('wealthAssetExpected').textContent = won(s.expected);
    document.getElementById('wealthAssetRealized').textContent = won(s.realized);
    document.getElementById('wealthAssetSafe').textContent = won(s.safe);
    document.getElementById('wealthAssetDebtDetail').textContent = won(s.debt);
    document.getElementById('wealthAssetPropertyDetail').textContent = won(s.property);
    document.getElementById('wealthAssetStockDetail').textContent = won(s.stock);
    document.getElementById('wealthAssetExpectedRate').textContent = pct(s.expectedRate);
    document.getElementById('wealthAssetDayDetail').textContent = signedWon(s.dayProfit);
    document.getElementById('wealthAssetDayDate').textContent = s.dayDate ? `${s.dayDate} 대비` : '전일 대비';
    document.getElementById('wealthAssetTradeDetail').textContent = signedWon(s.realizedTrade);
    document.getElementById('wealthAssetDividendDetail').textContent = signedWon(s.dividendInterest);
    document.getElementById('wealthAssetYearDetail').textContent = signedWon(s.realizedYear);
    document.getElementById('wealthAssetMonthDetail').textContent = signedWon(s.realizedMonth);
    document.getElementById('wealthAssetSafeDetail').textContent = won(s.cash);
    document.getElementById('wealthAssetDepositDetail').textContent = won(s.deposits);
    document.getElementById('wealthAssetInsuranceDetail').textContent = won(s.insurance);
    document.getElementById('wealthCash').textContent = won(s.cash);
    document.getElementById('wealthDebt').textContent = won(s.debt);
    document.getElementById('wealthOwnerLabel').textContent = s.owner === '모두' ? '전체 가족' : s.owner;
    document.getElementById('wealthHomeUpdated').textContent = s.updatedAt ? `자산 반영 ${new Date(s.updatedAt).toLocaleString('ko-KR')}` : '등록된 자산 기준 · 반영 시각 없음';
    const palette = ['#9b8afb','#61c9b2','#6ea6ec','#e7bc71','#c891bd','#5aa9cf','#ef7b8e','#8bbf74','#a9a1d6'];
    const items = (s.classifications || []).filter(item => Number(item.market_value_krw || 0) > 0).map((item, index) => ({ ...item, color: palette[index % palette.length] }));
    const total = items.reduce((sum, item) => sum + Math.max(0, Number(item.market_value_krw || 0)), 0);
    const donut = document.getElementById('homeAssetAllocationDonut');
    const donutLegend = document.getElementById('homeAssetAllocationLegend');
    const legend = document.getElementById('wealthMixLegend');
    donutLegend.replaceChildren(); legend.replaceChildren();
    let cursor = 0;
    const stops = items.map(item => { const share = total > 0 ? Math.max(0, Number(item.market_value_krw || 0)) / total * 100 : 0; const start = cursor; cursor += share; return `${item.color} ${start}% ${cursor}%`; });
    donut.style.background = stops.length ? `conic-gradient(${stops.join(',')})` : 'var(--line)';
    document.getElementById('homeAssetAllocationTotal').textContent = won(total);
    items.slice(0, 6).forEach(item => {
      const row = document.createElement('span'); row.style.setProperty('--mix-color', item.color);
      const name = document.createElement('span'); name.textContent = item.name;
      const weight = document.createElement('strong'); weight.textContent = `${Number(item.weight || 0).toFixed(1)}%`;
      row.append(name, weight); donutLegend.append(row);
    });
    items.forEach(item => {
      const label = item.name; const value = Number(item.market_value_krw || 0); const color = item.color;
      const row = document.createElement('div');
      const name = document.createElement('span'); name.textContent = label; name.style.setProperty('--mix-color', color);
      const amount = document.createElement('strong'); amount.textContent = won(value);
      let secondary = `${Number(item.holding_count || 0)}종목 · ${Number(item.weight || 0).toFixed(1)}%`;
      if (label === '부동산') secondary = `부동산 순에퀴티 · ${Number(item.weight || 0).toFixed(1)}%`;
      else if (label === '현금·예수금') secondary = `은행 예수금 포함 · ${Number(item.weight || 0).toFixed(1)}%`;
      else if (label === '보험') secondary = `예상 수령액/해약환급금 · ${Number(item.weight || 0).toFixed(1)}%`;
      const detail = document.createElement('small'); detail.textContent = secondary;
      const metric = document.createElement('b');
      const showReturn = !['현금·예수금','부동산','보험'].includes(label);
      metric.textContent = showReturn ? pct(item.return_rate) : `${Number(item.weight || 0).toFixed(1)}%`;
      metric.className = showReturn ? (Number(item.profit_krw || 0) >= 0 ? 'up' : 'down') : '';
      const title = document.createElement('div'); title.append(name, detail);
      const values = document.createElement('div'); values.append(amount, metric);
      row.append(title, values); legend.append(row);
    });
  });
})();
