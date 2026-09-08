/* Navigation and presentation only. Existing panels, handlers and owner rules are retained. */
(() => {
  'use strict';
  const root = document.getElementById('userAssetDashboardWrapper');
  if (!root) return;
  const views = {
    home: ['홈', '가족의 자산을 한눈에', '지금의 자산 현황을 확인하고, 필요한 관리로 이어가세요.'],
    invest: ['투자', '투자 현황', '포트폴리오, 보유종목과 자산 기록을 한곳에서 확인하세요.'],
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
          <article class="wealth-net-card"><div class="wealth-card-top"><span>나의 순자산</span><span class="wealth-live-label" id="wealthOwnerLabel">전체 가족</span></div><strong id="wealthNetWorth">—</strong><p>등록 자산에서 부채를 뺀 금액</p><div class="wealth-net-bottom"><span id="wealthHomeUpdated">자산 정보를 불러오는 중입니다.</span><a href="#invest">상세 현황 <span aria-hidden="true">↗</span></a></div></article>
          <article class="wealth-stat-card"><span class="wealth-stat-icon">${icon('assets')}</span><h3>현금·예적금</h3><strong id="wealthCash">—</strong><p>은행 잔액 · 증권 예수금 · 예적금</p><a href="#assets">계좌 살펴보기 →</a></article>
          <article class="wealth-stat-card"><span class="wealth-stat-icon wealth-debt-icon">${icon('ledger')}</span><h3>총부채</h3><strong id="wealthDebt">—</strong><p>대출 · 음수 잔액 · 임대보증금 반환의무</p><a href="#assets">부채 확인하기 →</a></article>
        </div>
        <div class="wealth-home-secondary"><article class="wealth-composition"><div class="wealth-section-heading"><div><p class="wealth-eyebrow">ASSET MIX</p><h3>어디에 담겨 있나요?</h3></div><a href="#invest">자세히 ↗</a></div><p class="wealth-help">부채 차감 전 등록 자산 기준</p><div id="wealthMix" class="wealth-mix" aria-hidden="true"></div><div id="wealthMixLegend" class="wealth-mix-legend"><p class="wealth-help">자산 정보가 준비되면 구성을 표시합니다.</p></div></article>
        <article class="wealth-shortcuts"><p class="wealth-eyebrow">QUICK ACCESS</p><h3>오늘의 자산 관리</h3><a href="#ledger">${icon('ledger')}<span><strong>수입과 지출 정리</strong><small>가계부 · 카드 · 고정지출</small></span><b aria-hidden="true">↗</b></a><a href="#income">${icon('income')}<span><strong>손익과 배당 확인</strong><small>실현손익 · 배당 내역</small></span><b aria-hidden="true">↗</b></a><a href="#assets">${icon('assets')}<span><strong>자산 정보 관리</strong><small>계좌 · 대출 · 보험 · 부동산</small></span><b aria-hidden="true">↗</b></a></article></div>
        <div id="wealthMarketSlot"></div>
      </section>
      ${Object.keys(views).filter(key => key !== 'home').map(key => `<section data-wealth-page="${key}" aria-label="${views[key][0]}" hidden></section>`).join('')}
    </div>`;
  root.prepend(layout);
  document.body.classList.add('wealth-layout');
  const page = key => layout.querySelector(`[data-wealth-page="${key}"]`);
  const move = (id, target) => { const node = document.getElementById(id); if (node) target.append(node); };
  move('topbarFamilyTabs', document.getElementById('wealthOwnerSlot'));
  move('refreshButton', layout.querySelector('.wealth-owner-bar'));
  move('marketPanel', document.getElementById('wealthMarketSlot'));
  ['summaryPanel', 'assetHeatmapPanel', 'holdingsPanel', 'recordsPanel'].forEach(id => move(id, page('invest')));
  move('accountsPanel', page('assets'));
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
  ['realizedPnlPanel', 'dividendPanel'].forEach(id => move(id, page('income')));
  move('ledgerSectionPanel', page('ledger'));
  const settingsCard = document.createElement('article');
  settingsCard.className = 'wealth-settings-card';
  settingsCard.innerHTML = '<h3>계정과 연결</h3><p class="wealth-help">가족 구성원과 증권사 연결을 설정합니다. 연결 작업은 버튼을 눌렀을 때 실행됩니다.</p><div class="wealth-settings-actions"></div>';
  page('settings').append(settingsCard);
  const actions = settingsCard.querySelector('.wealth-settings-actions');
  // Retain admin/password actions in the global header for the separate admin view.
  ['topbarFamilyBtn', 'userOpenApiBtn', 'syncAccountsButton'].forEach(id => move(id, actions));
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
  navigate();
  const won = value => `${Math.round(value).toLocaleString('ko-KR')}원`;
  window.addEventListener('wealth:summary', ({ detail: s }) => {
    document.getElementById('wealthNetWorth').textContent = won(s.netWorth);
    document.getElementById('wealthCash').textContent = won(s.cash);
    document.getElementById('wealthDebt').textContent = won(s.debt);
    document.getElementById('wealthOwnerLabel').textContent = s.owner === '모두' ? '전체 가족' : s.owner;
    document.getElementById('wealthHomeUpdated').textContent = s.updatedAt ? `자산 반영 ${new Date(s.updatedAt).toLocaleString('ko-KR')}` : '등록된 자산 기준 · 반영 시각 없음';
    const items = [['주식', s.stock, '#9b8afb'], ['현금·예적금', s.cash, '#61c9b2'], ['부동산', s.property, '#6ea6ec'], ['임차보증금', s.deposits, '#e7bc71'], ['보험', s.insurance, '#c891bd']];
    const total = items.reduce((sum, item) => sum + Math.max(0, item[1]), 0);
    const mix = document.getElementById('wealthMix');
    const legend = document.getElementById('wealthMixLegend');
    mix.replaceChildren(); legend.replaceChildren();
    items.forEach(([label, value, color]) => {
      const pct = total > 0 ? Math.max(0, value) / total * 100 : 0;
      const bar = document.createElement('span'); bar.style.width = `${pct}%`; bar.style.background = color; mix.append(bar);
      const row = document.createElement('div');
      const name = document.createElement('span'); name.textContent = label; name.style.setProperty('--mix-color', color);
      const amount = document.createElement('strong'); amount.textContent = won(value);
      const percent = document.createElement('small'); percent.textContent = `${pct.toFixed(1)}%`;
      row.append(name, amount, percent); legend.append(row);
    });
  });
})();
