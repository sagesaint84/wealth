/* Sector/classification View. Shared donut geometry remains owned by WealthDonutChart. */
(() => {
  'use strict';

  function create({ $, html, money, number, signClass, getDashboard, getRawDashboard,
                    renderHoldings, document, window }) {
// Stock page remains stock-focused; the former asset/stock UI toggle is not user-facing.
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
  const segments = window.WealthDonutChart.segments(validItems.map((item, index) => ({
    ...item, key: `classification:${String(item.name || '')}`,
    colorKey: window.WealthColorPreferences.keyFor('stock_category_colors', item),
    color: window.WealthColorPreferences.register('stock_category_colors', item, SECTOR_COLORS[index % SECTOR_COLORS.length]),
  })), item => total > 0 ? item.market_value_krw / total * 100 : 0);

  const legendHtml = validItems.map((s, idx) => {
    const donutKey = `classification:${String(s.name || '')}`;
    const color = window.WealthColorPreferences.register('stock_category_colors',s,SECTOR_COLORS[idx % SECTOR_COLORS.length]);
    return `
      <div class="sector-legend-item clickable-sector-item" data-sector-filter="${html(s.name)}" data-color-key="${html(window.WealthColorPreferences.keyFor('stock_category_colors',s))}" data-donut-key="${html(donutKey)}" tabindex="0" style="cursor:pointer;" title="${html(s.name)} 관련 종목 검색">
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
      <div class="wealth-asset-donut" aria-label="종목 분류별 주식자산">
        <span>주식자산</span><strong>${html(money(total))}</strong>
      </div>
      <div class="sector-legend-list">
        ${legendHtml}
      </div>
    </div>
  `;
  window.WealthDonutChart.bind(wrap.querySelector('.wealth-asset-donut'), segments, {
    legend: wrap.querySelector('.sector-legend-list'), root: wrap.querySelector('.sector-donut-container'),
    onSelect: item => filterHoldingsByClassification(item.name),
  });
}

// ── 자산 분류 (섹터/자산군) 클릭 시 보유종목 자동 검색 & 스크롤 연동 ─────────────
function filterHoldingsByClassification(name) {
  const dashboard = getDashboard();
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

  const holdingsPanel = document.getElementById('holdingsPanel');

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
  const dashboard = getDashboard();
  const rawDashboard = getRawDashboard();
  const list = $("#classificationList");
  const donutWrap = $("#sectorDonutWrap");
  if (!list) return;

  if (donutWrap) donutWrap.style.display = 'block';
  list.classList.add('sector-mode');
  list.style.display = 'flex';
  list.style.flexDirection = 'column';

    const sectors = dashboard?.sector_classifications || rawDashboard?.sector_classifications || [];
    renderAllocationDonut(sectors, '섹터별 투자자산 데이터가 없습니다.');
    list.innerHTML = sectors.length ? sectors.map((item,index) => `
      <div class="classification-row clickable-sector-row" data-sector-filter="${html(item.name)}" data-color-key="${html(window.WealthColorPreferences.keyFor('stock_category_colors',item))}" style="cursor:pointer;--classification-color:${window.WealthColorPreferences.register('stock_category_colors',item,SECTOR_COLORS[index % SECTOR_COLORS.length])};" title="🔍 클릭하여 '${html(item.name)}' 보유종목 보기">
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

}

    return Object.freeze({ renderClassifications, filterHoldingsByClassification });
  }

  window.WealthSectorView = Object.freeze({ create });
})();
