(() => {
  "use strict";

  function create(app) {
    let allAssetRecords = [];
    let assetRecords = [];
    let currentRecordPeriod = 'ALL'; // '1M' | '3M' | '6M' | '1Y' | 'ALL'
    let currentRecordView = window.WealthInvestTabState?.current() === 'tax_accounts' ? 'tax_accounts' : 'combo';
    let currentTaxAccountFilter = 'all'; // 'all' | 'isa' | 'irp' | 'pension_savings' | acc_<id>
    // Stock page is intentionally stock-focused; the former asset/stock UI toggle
    // is no longer user-facing. Asset overview remains on the home page.
    let holdingSortField = 'market_value_krw';
    let holdingSortOrder = 'desc'; // 'asc' | 'desc'
    let taxHoldingSortField = 'market_value_krw';
    let taxHoldingSortOrder = 'desc'; // 'asc' | 'desc'
     // 'asc' | 'desc'
    let heatmapViewMode = localStorage.getItem("heatmap_view_mode") || "treemap"; // 'treemap' | 'cards'
    let heatmapPeriod = localStorage.getItem("heatmap_period") || "1D";
    let heatmapTheme = localStorage.getItem("heatmap_theme") || "kr";
    let heatmapMaxCap = localStorage.getItem("heatmap_max_cap") || "auto";

    let currentMarketPeriod = '1D';
    let currentMarketAllSub = '3Y';

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
      window.WealthApplyPeriodButtonSelection(document.querySelectorAll("#marketPeriodTabs .heatmap-tab"), mktPeriod);
      const selectEl = document.getElementById("marketPeriodSelect");
      if (selectEl && selectEl.value !== currentMarketAllSub) {
        selectEl.value = currentMarketAllSub;
      }
      if (app.marketView.hasData()) {
        app.renderMarkets(app.marketView.getData());
      }

      // 2. 자산기록 탭 동기화
      currentRecordPeriod = recPeriod;
      window.WealthApplyPeriodButtonSelection(document.querySelectorAll("#recordPeriodTabs .heatmap-tab"), recPeriod);
      if (assetRecords) renderAssetRecords(assetRecords);

      // 3. 자산히트맵 탭 동기화
      heatmapPeriod = hmPeriod;
      localStorage.setItem("heatmap_period", heatmapPeriod);
      window.WealthApplyPeriodButtonSelection(document.querySelectorAll("#heatmapPeriodTabs .heatmap-tab"), hmPeriod);
      if (app.dashboard) {
        renderHeatmaps(app.dashboard);
      }
    }

    const sectorView = window.WealthSectorView.create({
      $: app.$, html: app.html, money: app.money, number: app.number, signClass: app.signClass, document, window, renderHoldings,
      getDashboard: () => app.dashboard, getRawDashboard: () => app.rawDashboard,
    });
    function renderClassifications(items) { return sectorView.renderClassifications(items); }
    function filterHoldingsByClassification(name) { return sectorView.filterHoldingsByClassification(name); }

    const PERIOD_LABELS = {
      "1D": "일간 (전일 대비)",
      "1W": "주간 (7일 전 대비)",
      "1M": "월간 (1개월 전 대비)",
      "1Y": "연간 (1년 전 대비)",
      "TOTAL": "진입 (매입단가 대비)",
    };

    const PERIOD_CAPS = window.WealthHeatmapModel.PERIOD_CAPS;

    function getEffectiveCap(period, capSetting, items = []) { return window.WealthHeatmapModel.getEffectiveCap(period, capSetting, items); }

    function getHeatmapColor(rate, maxRate = 15, theme = "kr") { return window.WealthHeatmapModel.getHeatmapColor(rate, maxRate, theme); }

    function updateHeatmapLegendUI(period, theme, maxCap, items = []) {
      heatmapView.renderLegend({
        cap: getEffectiveCap(period, maxCap, items), theme, maxCap,
        periodLabel: PERIOD_LABELS[period] || period,
      });
    }

    // ── 정통 Squarify 트리맵 알고리즘 ──
    function squarify(items, x, y, width, height) { return window.WealthHeatmapModel.squarify(items, x, y, width, height); }

    let lastValidHeatmapWidth = 0;

    function renderTreemapContainer(container, items, period = "1D", theme = "kr", capSetting = "auto") {
      if (!container) return;
      if (!items.length) {
        heatmapView.renderTreemap(container, []);
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


      const tiles = squarify(items, 0, 0, width, height);

      const displayTiles = tiles.map((tile) => {
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
        const rateText = `${sign}${app.number(rateVal, 1)}%`;

        const isTiny = tile.w < 38 || tile.h < 26;
        const isSmall = !isTiny && (tile.w < 62 || tile.h < 42);
        const isMed = !isTiny && !isSmall && (tile.w < 98 || tile.h < 64);

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

        return {
          name: tile.name, rateText, isTiny, isSmall, isMed, infoStr, color,
          left: tile.x.toFixed(1), top: tile.y.toFixed(1),
          width: tile.w.toFixed(1), height: tile.h.toFixed(1),
        };
      });
      heatmapView.renderTreemap(container, displayTiles, height);


      updateHeatmapLegendUI(period, theme, capSetting, items);
      bindHeatmapInteractions(container);
    }

    const heatmapView = window.WealthHeatmapView.create({ document, $: app.$, html: app.html });

    function renderHeatmaps(data) {
      const holdings = data?.holdings || [];
      const container = app.$("#assetHeatmapContainer");
      if (!container) return;
      if (container.closest('[data-wealth-page="invest"]')?.hidden) return;

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
        const maxCap = getEffectiveCap(heatmapPeriod, heatmapMaxCap, items);
        updateHeatmapLegendUI(heatmapPeriod, heatmapTheme, heatmapMaxCap, items);

        const cards = items.map((it) => {
          const periodRates = it.period_changes || {};
          let selectedRate = 0;
          if (heatmapPeriod === 'TOTAL') selectedRate = it.rate;
          else if (periodRates[heatmapPeriod] != null) selectedRate = Number(periodRates[heatmapPeriod]);
          else selectedRate = Number(it.day_change_rate || 0);

          return {
            name: it.name,
            weightText: `${app.number(it.weight, 1)}%`,
            valueText: app.money(it.value),
            rateText: `${selectedRate >= 0 ? '+' : ''}${app.number(selectedRate, 2)}%`,
            backgroundColor: getHeatmapColor(selectedRate, maxCap, heatmapTheme),
          };
        });
        heatmapView.renderCardMode(container, cards, openHeatmapHolding);
      } else {
        renderTreemapContainer(container, items, heatmapPeriod, heatmapTheme, heatmapMaxCap);
      }
    }

    function openHeatmapHolding(symbol) {
      const query = String(symbol || '').trim();
      const tab = document.querySelector('.wealth-invest-tabs button[data-invest="holdings"]');
      const search = app.$("#searchInput");
      if (!query || !tab || !search) return;
      tab.click(); // Reuse the existing tab handler, state, aria and visibility updates.
      search.value = query;
      if (app.dashboard) renderHoldings(app.dashboard);
      heatmapView.renderTooltip(document.getElementById("heatmapTooltip"), null);
      search.focus();
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
          heatmapView.renderTooltip(tooltipEl, null);
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

          const x = Math.min(Math.max(140, e.clientX), window.innerWidth - 140);
          const y = Math.max(70, e.clientY);
          heatmapView.renderTooltip(tooltipEl, {
            name: info.name, code: info.code, market: info.market || 'KRX',
            valueText: app.money(info.value), weightText: app.number(info.weight, 1),
            periodLabel, rateColor, sign, selectedRateText: app.number(selRate, 2),
            totalRateColor, totalSign: (info.rate || 0) >= 0 ? "+" : "",
            totalRateText: app.number(info.rate, 2),
            profitSign: (info.profit || 0) >= 0 ? "+" : "", profitText: app.money(info.profit),
          }, { left: x + "px", top: y + "px" });
        } catch (err) {
          console.warn("Tooltip info parse error:", err);
          heatmapView.renderTooltip(tooltipEl, null);
        }
      });

      container.addEventListener("mouseleave", () => {
        if (tooltipEl) heatmapView.renderTooltip(tooltipEl, null);
      });

      container.addEventListener("click", (e) => {
        const tile = e.target.closest(".heatmap-tile");
        if (!tile || !tile.dataset.symbol) return;
        openHeatmapHolding(tile.dataset.symbol);
      });
      container.addEventListener("keydown", (e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        const tile = e.target.closest(".heatmap-tile");
        if (!tile || !tile.dataset.symbol) return;
        e.preventDefault();
        openHeatmapHolding(tile.dataset.symbol);
      });
    }

    // ── 6. 보유종목 테이블 (정렬 + 섹터 뱃지 + 인터랙티브 차트 모달) ─────────────
    const holdingRows = window.WealthHoldingsRowView.create({ html: app.html, number: app.number, money: app.money, signClass: app.signClass });

    function renderHoldings(data) {
      data = data || app.dashboard || app.rawDashboard || {};
      syncHoldingSignalsContext();
      const query = app.$("#searchInput")?.value.trim().toLowerCase() || "";
      const rows = (data.holdings || []).filter((item) => {
        const assetClass = typeof app.classifyHolding === 'function' ? app.classifyHolding(item) : '';
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

      const tbody = app.$("#holdingsBody");
      if (!tbody) return;

      tbody.innerHTML = sorted.map((item) => {
        const accounts = item.items.map(detail => holdingRows.renderAccountDetail({
          broker: detail.broker, accountName: detail.account_name, quantity: detail.quantity, id: detail.id,
        })).join("");
        return holdingRows.renderRow(item, { accounts });
      }).join("");

      app.$("#emptyHoldings") && (app.$("#emptyHoldings").hidden = sorted.length > 0);
      app.$(".table-wrap") && (app.$(".table-wrap").hidden = sorted.length === 0);
    }

    const holdingSignals = window.WealthHoldingSignals.create({
      $: app.$, api: app.api, html: app.html, number: app.number, document, window, globalThis, currentWealthView: app.currentWealthView,
      getDashboard: () => app.dashboard, getRawDashboard: () => app.rawDashboard,
      getCurrentOwner: () => app.currentOwner, getCurrentUserProfile: () => app.currentUserProfile,
    });
    function syncHoldingSignalsContext() { return holdingSignals.syncHoldingSignalsContext(); }
    async function loadHoldingSignals() { return holdingSignals.loadHoldingSignals(); }

    const stockChartView = window.WealthStockChartView.create({ $: app.$, api: app.api, money: app.money, number: app.number, signClass: app.signClass, html: app.html, document });
    async function openStockChart(code, name, price, currency = 'KRW') {
      return stockChartView.openStockChart(code, name, price, currency);
    }



    // ── 8. 주식기록 렌더링 (전체주식 콤보 차트 vs 절세계좌 뷰) ───────────────────────────
    const stockRecordsView = window.WealthStockRecordsView.create({ $: app.$, window, money: app.money, number: app.number, signClass: app.signClass, html: app.html });

    const assetRecordsScreenController = window.WealthAssetRecordsScreenController.create({ document, $: app.$, stockRecordsView, renderTaxAccountHoldings });

    function renderAssetRecords(records) {
      globalThis.WealthStartup?.count('render');
      assetRecords = records || [];

      assetRecordsScreenController.render(records, currentRecordPeriod, currentRecordView, app.currentOwner);
    }

    const taxAccountsView = window.WealthTaxAccountsView.create({ html: app.html, number: app.number, signClass: app.signClass, holdingRows });

    function renderTaxAccountHoldings(owner = app.currentOwner) {
      app.$("#recordsPanel")?.classList.add("is-tax-view");
      const sideSummaryEl = document.querySelector(".record-side-summary");
      if (sideSummaryEl) sideSummaryEl.style.display = "none";
      const o = owner || app.currentOwner || '모두';
      const curData = app.dashboard || app.rawDashboard || {};
      const allAccounts = curData.accounts || [];
      const allHoldings = curData.holdings || [];

      // 1. IRP, 연금저축, ISA 계좌 필터링
      const taxAccounts = allAccounts.filter(a => {
        if (!app.isTaxAdvantagedAccount(a)) return false;
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
        h._taxCategory = app.getTaxCategory(matchedAccount);
        taxHoldings.push(h);
      });

      // 카테고리별 분리
      const isaAccounts = taxAccounts.filter(a => app.getTaxCategory(a) === 'isa');
      const irpAccounts = taxAccounts.filter(a => app.getTaxCategory(a) === 'irp');
      const pensionAccounts = taxAccounts.filter(a => app.getTaxCategory(a) === 'pension_savings');

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
        const usdRate = Number(app.dashboard?.fx_rates?.USD || app.dashboard?.summary?.usd_krw_rate || app.rawDashboard?.summary?.usd_krw_rate || 1400);
        return krw + (usd * usdRate);
      };

      // 전체 통계
      const allStats = calcHoldingStats(taxHoldings);
      const allCash = taxAccounts.reduce((sum, a) => sum + getAccountCash(a), 0);
      const allTotalMarket = allStats.market + allCash;
      const pensionTaxBenefits = app.calculateOwnerYearPensionTaxBenefits(taxAccounts);
      const allCumulativeTaxSaved = pensionTaxBenefits.cumulative.taxSaved;

      // 카테고리별 통계
      const isaStats = calcHoldingStats(isaHoldings);
      const isaCash = isaAccounts.reduce((sum, a) => sum + getAccountCash(a), 0);
      const isaTotalMarket = isaStats.market + isaCash;

      const irpStats = calcHoldingStats(irpHoldings);
      const irpCash = irpAccounts.reduce((sum, a) => sum + getAccountCash(a), 0);
      const irpTotalMarket = irpStats.market + irpCash;
      const irpCumulativeTaxSaved = pensionTaxBenefits.cumulative.irpTaxSaved;

      const pensionStats = calcHoldingStats(pensionHoldings);
      const pensionCash = pensionAccounts.reduce((sum, a) => sum + getAccountCash(a), 0);
      const pensionTotalMarket = pensionStats.market + pensionCash;
      const pensionCumulativeTaxSaved = pensionTaxBenefits.cumulative.pensionTaxSaved;

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
      if (app.$("#recordCount")) app.$("#recordCount").textContent = `${sortedGroups.length}개 종목 (${filterBadgeName})`;
      if (sideSummaryEl) sideSummaryEl.style.display = "none";

      // 스냅샷/추가 버튼 숨김/표시
      if (app.$("#snapshotButton")) app.$("#snapshotButton").style.display = "none";
      if (app.$("#addRecordButton")) app.$("#addRecordButton").style.display = "none";
      if (app.$("#recordPeriodTabs")) app.$("#recordPeriodTabs").style.opacity = "0.4";

      const chartWrap = app.$("#assetChart");
      if (!chartWrap) return;

      if (!taxHoldings.length && allCash === 0) {
        chartWrap.innerHTML = taxAccountsView.emptyAccounts({ o });
        if (app.$("#assetRecordList")) app.$("#assetRecordList").innerHTML = "";
        return;
      }

      // 우측 종목 리스트 렌더링 (기존보유종목과 동일한 테이블 구조 및 보유계좌 나열)
      let holdingsHtml = '';
      if (!sortedGroups.length && currentFilterCash <= 0) {
        holdingsHtml = taxAccountsView.emptyFilter({ filterTitle });
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

          cashRowHtml = taxAccountsView.cashRow({ cashAccountLabel, currentFilterCash });
        }

        let emptyStockNotice = '';
        if (!sortedGroups.length && currentFilterCash > 0) {
          emptyStockNotice = taxAccountsView.emptyStocksWithCash({ currentFilterCash });
        }

        const holdingRowsData = sortedGroups.map((item) => {
          const accounts = item.items.map((detail) => {
            const acct = detail._matchedAccount || taxAccountMap.get(detail.account_id) || {};
            const acctName = acct.name || detail.account_name || '절세계좌';
            const acctBroker = acct.broker || detail.broker || '';
            const acctOwner = detail.owner || acct.owner || '';
            const ownerLabel = (o === '모두' && acctOwner) ? ` [${acctOwner}]` : '';

            return {
              broker: acctBroker, accountName: acctName, ownerLabel,
              quantity: detail.quantity, id: detail.id,
            };
          });

          return { item, accounts };
        });

        holdingsHtml = taxAccountsView.holdingsTable({ taxHoldingSortField, taxHoldingSortOrder, cashRowHtml, emptyStockNotice, holdingRowsData });
      }

      // 현재 필터(전체 / 카테고리 / 개별 계좌)의 누적 절세액 산출
      let taxBenefit = null;
      if (currentTaxAccountFilter === 'all') {
        taxBenefit = { kind: 'all', amount: allCumulativeTaxSaved };
      } else if (currentTaxAccountFilter === 'irp') {
        taxBenefit = { kind: 'irp', amount: irpCumulativeTaxSaved };
      } else if (currentTaxAccountFilter === 'pension_savings') {
        taxBenefit = { kind: 'pension', amount: pensionCumulativeTaxSaved };
      } else if (currentTaxAccountFilter === 'isa') {
        taxBenefit = { kind: 'isa' };
      } else if (currentTaxAccountFilter.startsWith('acc_')) {
        const accId = currentTaxAccountFilter.replace('acc_', '');
        const targetAcc = taxAccountMap.get(accId);
        if (targetAcc) {
          const cat = app.getTaxCategory(targetAcc);
          const isDed = app.isAccountTaxDeductible(targetAcc);
          const targetTaxSaved = app.calcAccountCumulativeTaxSaved(targetAcc, taxAccounts);

          if (cat === 'isa') {
            taxBenefit = { kind: 'accountIsa' };
          } else if (isDed && targetTaxSaved > 0) {
            taxBenefit = { kind: 'account', amount: targetTaxSaved };
          } else if (!isDed) {
            taxBenefit = { kind: 'nonDeductible' };
          } else {
            taxBenefit = { kind: 'zero' };
          }
        }
      }

      taxAccountsView.chartContent(chartWrap, { filterTitle, sortedGroups, filterSubtitle, filteredTotalMarket, filteredStats, currentFilterCash, taxBenefit, holdingsHtml });

      // 3. 좌측 사이드 패널: 절세계좌 카드 목록 렌더링
      const recordListEl = app.$("#assetRecordList");
      if (!recordListEl) return;

      const accountCards = taxAccounts.map(acct => {
        const acctHoldings = taxHoldings.filter(h => h._matchedAccountId === acct.id);
        const acctStats = calcHoldingStats(acctHoldings);
        const acctCash = getAccountCash(acct);
        const acctTotalMarket = acctStats.market + acctCash;
        const cat = app.getTaxCategory(acct);
        const isDed = app.isAccountTaxDeductible(acct);
        const isAcctActive = currentTaxAccountFilter === `acc_${acct.id}`;
        const acctSavedTax = app.calcAccountCumulativeTaxSaved(acct, taxAccounts);

        const taxRow = cat === 'isa' ? 'isa'
          : !isDed ? 'nonDeductible' : acctSavedTax > 0 ? 'deductible' : 'zero';

        return { isAcctActive, acct, cat, isDed, acctTotalMarket, acctStats, acctHoldings, acctCash, acctSavedTax, taxRow };
      });

      taxAccountsView.cardList(recordListEl, {
        all: { isAllActive: currentTaxAccountFilter === 'all', taxHoldings, taxAccounts, allTotalMarket, allStats, allCash, allCumulativeTaxSaved },
        isa: { isIsaActive: currentTaxAccountFilter === 'isa', isaHoldings, isaAccounts, isaTotalMarket, isaStats, isaCash },
        irp: { isIrpActive: currentTaxAccountFilter === 'irp', irpHoldings, irpAccounts, irpTotalMarket, irpStats, irpCash, irpCumulativeTaxSaved },
        pension: { isPensionActive: currentTaxAccountFilter === 'pension_savings', pensionHoldings, pensionAccounts, pensionTotalMarket, pensionStats, pensionCash, pensionCumulativeTaxSaved },
        accountCards,
      });
    }

    let investmentRenderedData = null;
    function renderInvestmentView(data = app.dashboard) {
      if (!data || app.currentWealthView() !== 'invest' || investmentRenderedData === data) return;
      renderClassifications(data.classifications || []);
      renderHeatmaps(data);
      renderHoldings(data);
      investmentRenderedData = data;
    }

    async function loadAssetRecords(owner) {
      // Keep main's eager record source: DAY summary calculations share these
      // records even when the stock page is hidden.
      const generation = loadAssetRecords.generation = (loadAssetRecords.generation || 0) + 1;
      const o = owner || app.currentOwner || '모두';
      try {
        const allRes = await app.api('/api/asset-records');
        if (generation !== loadAssetRecords.generation || o !== app.currentOwner) { globalThis.WealthStartup?.count('stale_ignored'); return; }
        allAssetRecords = allRes.records || [];
      } catch (e) {}
      if (generation !== loadAssetRecords.generation || o !== app.currentOwner) return;
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
    function openImport() { app.$("#importDialog")?.showModal(); }
    function holdingEligibleAccounts(owner = app.currentOwner) {
      const types = new Set(['general', 'isa', 'pension_savings', 'pension', 'irp']);
      const source = app.rawDashboard?.accounts || app.dashboard?.accounts || [];
      return source.filter(a => a.id && types.has(a.account_type || 'general') &&
        (owner === '모두' || (a.owner || '모두') === owner));
    }
    function fillHoldingAccountOptions(owner, selectedId = '') {
      const accounts = holdingEligibleAccounts(owner);
      const validationMessage = selectedId && !accounts.some(account => account.id === selectedId)
        ? '기존 연결 계좌를 확인한 뒤 등록 계좌를 선택하세요.'
        : '';
      window.WealthHoldingAccountOptionsView.render({ $: app.$, html: app.html, accounts, selectedId, validationMessage });
      return accounts;
    }
    function resolveHoldingDialogAccountSelection(record) {
      const allAccounts = holdingEligibleAccounts('모두');
      const linked = allAccounts.find(a => a.id === record?.account_id);
      const owner = record ? (linked?.owner || record.owner || '모두') : app.currentOwner;
      const legacy = record && !record.account_id ? allAccounts.filter(a =>
        a.broker === record.broker && a.name === record.account_name && (a.owner || '모두') === owner) : [];
      const selectedId = record?.account_id || (legacy.length === 1 ? legacy[0].id : '');
      return { linked, owner, selectedId };
    }
    function openHoldingDialog(record = null) {
      window.WealthHoldingDialogController.open({
        $: app.$, record, resolveAccountSelection: resolveHoldingDialogAccountSelection,
        fillHoldingAccountOptions, populateStockDatalists: app.populateStockDatalists, attachStockAutoFill: app.attachStockAutoFill,
      });
    }

    function openAssetRecordDialog(record = null) {
      assetRecordsScreenController.openRecordDialog(record, {
        getNetWorth: () => record?.net_worth_krw ?? ((Number(record?.total_assets_krw ?? record?.total_value_krw) || 0) - (Number(record?.total_debt_krw) || 0)),
        getOwner: () => record?.owner || app.currentOwner || "모두",
      });
    }

    let heatmapResizeTimer = null;

    function selectSector(e, sectorItem) {
      e.preventDefault();
      filterHoldingsByClassification(sectorItem.dataset.sectorFilter);
    }

    function nextSortOrder(nextField, currentField, order) {
      return nextField !== currentField || order === 'asc' ? 'desc' : 'asc';
    }

    function sortTaxHoldings(taxTh) {
      const sortField = taxTh.dataset.taxSort;
      taxHoldingSortOrder = nextSortOrder(sortField, taxHoldingSortField, taxHoldingSortOrder);
      taxHoldingSortField = sortField;
      renderTaxAccountHoldings(app.currentOwner);
    }

    function editTaxHolding(taxEditBtn) {
      const item = (app.dashboard?.holdings || []).find(row => String(row.id) === String(taxEditBtn.dataset.id));
      if (item) openHoldingDialog(item);
    }

    async function deleteTaxHolding(taxDelBtn) {
      await app.action(taxDelBtn, () => app.api(`/api/holdings/${taxDelBtn.dataset.id}`, { method: "DELETE" }), () => app.loadDashboard());
    }

    function sortHoldings(th) {
      const sortField = th.dataset.sort;
      holdingSortOrder = nextSortOrder(sortField, holdingSortField, holdingSortOrder);
      holdingSortField = sortField;
      if (app.dashboard) renderHoldings(app.dashboard);
    }

    function openHoldingChart(chartBtn) {
      const code = chartBtn.dataset.code;
      const name = chartBtn.dataset.name;
      const price = chartBtn.dataset.price;
      const currency = chartBtn.dataset.currency;
      if (code) openStockChart(code, name, price, currency);
    }

    async function selectChartPeriod(chartTab) {
      await stockChartView.setPeriod(chartTab);
    }

    function bindMarketPeriod() {
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
    }

    function bindSectorColors() {
      window.addEventListener('wealth:colors',()=>{if(app.dashboard || app.rawDashboard)renderClassifications(app.dashboard?.classifications || app.rawDashboard?.classifications || []);});
    }

    function bindHoldingSignals() {
      window.addEventListener('wealth:view', syncHoldingSignalsContext);
      window.addEventListener('wealth:assets-ready', syncHoldingSignalsContext);
    }

    function bindPeriodTabList(id) {
      document.getElementById(id)?.addEventListener('click', (e) => {
        const tab = e.target.closest('.heatmap-tab');
        if (tab) setDashboardPeriod(tab.dataset.period);
      });
    }

    function bindInvestmentControls() {
      app.$("#addButton")?.addEventListener("click", () => openHoldingDialog());
      app.$("#importButton")?.addEventListener("click", openImport);
      app.$("#clearAllHoldingsBtn")?.addEventListener("click", (e) => {
        if (confirm("정말로 모든 보유종목을 일괄 삭제하시겠습니까?\n삭제된 내역은 복구할 수 없습니다.")) {
          app.action(e.currentTarget, () => app.api("/api/holdings/clear", { method: "POST" }), () => app.loadDashboard());
        }
      });
      app.$("#addRecordButton")?.addEventListener("click", () => openAssetRecordDialog());

      // 2. 오늘 주식기록 저장 — 서버 canonical 계산으로 모든 owner를 한 번에 기록
      app.$("#snapshotButton")?.addEventListener("click", (e) => app.action(e.currentTarget, async () => {
        return await app.api("/api/asset-records/snapshot", { method: "POST" });
      }, async () => {
        await loadAssetRecords(app.currentOwner);
      }));

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
      bindPeriodTabList('recordPeriodTabs');

      // 6. 히트맵 [면적형] / [카드형] 뷰 전환 탭
      document.getElementById('heatmapViewTabs')?.addEventListener('click', (e) => {
        const tab = e.target.closest('.heatmap-tab');
        if (!tab) return;
        document.querySelectorAll('#heatmapViewTabs .heatmap-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        heatmapViewMode = tab.dataset.view || 'treemap';
        localStorage.setItem("heatmap_view_mode", heatmapViewMode);
        if (app.dashboard) renderHeatmaps(app.dashboard);
      });

      // 7. 히트맵 기간 탭 & 셀렉트 박스
      bindPeriodTabList('heatmapPeriodTabs');

      document.getElementById('heatmapCapSelect')?.addEventListener('change', (e) => {
        heatmapMaxCap = e.target.value;
        localStorage.setItem("heatmap_max_cap", heatmapMaxCap);
        if (app.dashboard) renderHeatmaps(app.dashboard);
      });

      document.getElementById('heatmapThemeSelect')?.addEventListener('change', (e) => {
        heatmapTheme = e.target.value;
        localStorage.setItem("heatmap_theme", heatmapTheme);
        if (app.dashboard) renderHeatmaps(app.dashboard);
      });

      // 히트맵 인터랙션 바인딩
      bindHeatmapInteractions(app.$("#assetHeatmapContainer"));

      // 8. 검색창 및 종목 수정/삭제 리스너
      app.$("#searchInput")?.addEventListener("input", () => app.dashboard && renderHoldings(app.dashboard));
    }

    function bindHoldingsList() {
      app.$("#holdingsBody")?.addEventListener("click", (e) => {
        const edit = e.target.closest(".edit-button");
        const del = e.target.closest(".delete-button");
        if (edit) {
          const item = app.dashboard?.holdings.find(row => row.id === edit.dataset.id);
          if (item) openHoldingDialog(item);
          return;
        }
        if (del && confirm("이 보유종목을 삭제할까요?")) {
          app.action(del, () => app.api(`/api/holdings/${del.dataset.id}`, { method: "DELETE" }));
        }
      });
    }

    function bindRecordsAndAccountFields() {
      app.$("#assetRecordList")?.addEventListener("click", async (e) => {
        if (e.target.closest("[data-account-edit-id]")) {
          return;
        }
        if (currentRecordView === 'tax_accounts') {
          const taxCard = e.target.closest("[data-tax-filter]");
          if (taxCard) {
            const filter = taxCard.dataset.taxFilter;
            if (filter) {
              currentTaxAccountFilter = filter;
              renderTaxAccountHoldings(app.currentOwner);
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
          await app.action(deleteButton, () => app.api(`/api/asset-records/${deleteButton.dataset.recordDelete}`, { method: "DELETE" }), () => loadAssetRecords(app.currentOwner));
        }
      });

      // 보유종목 추가/수정 팝업 내 등록된 계좌 선택 시 자동 채움
      app.$("#holdingAccountSelect")?.addEventListener("change", (e) => {
        const sel = e.target;
        const form = app.$("#holdingForm");
        if (!form || !sel) return;
        sel.setCustomValidity('');
        const opt = sel.selectedOptions[0];
        if (opt && opt.value) {
          if (opt.dataset.broker) form.broker.value = opt.dataset.broker;
          if (opt.dataset.name) form.account_name.value = opt.dataset.name;
          if (opt.dataset.owner && form.owner) form.owner.value = opt.dataset.owner;
        }
      });

      // Editing a linked identity explicitly switches to manual mode. The server
      // also checks the selected ID against broker/name/owner before any write.
      ['broker', 'account_name'].forEach(name => {
        document.querySelector(`#holdingForm [name="${name}"]`)?.addEventListener('input', () => {
          const select = app.$('#holdingAccountSelect');
          if (select) { select.value = ''; select.setCustomValidity(''); }
        });
      });
      document.querySelector('#holdingForm [name="owner"]')?.addEventListener('change', (event) => {
        const selectedId = app.$('#holdingAccountSelect')?.value;
        fillHoldingAccountOptions(event.target.value || '모두');
        if (selectedId) app.$('#holdingAccountSelect')?.setCustomValidity('소유자에 맞는 등록 계좌를 다시 선택하거나 증권사·계좌명을 직접 입력하세요.');
      });
    }

    function bindHoldingForms() {
      app.$("#holdingForm")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = e.currentTarget;
        if (!form.reportValidity()) return;
        const payload = Object.fromEntries(new FormData(form));
        if (!payload.owner) payload.owner = "모두";
        ["quantity", "avg_price", "current_price"].forEach(key => { payload[key] = Number(payload[key] || 0); });

        // 종목코드가 없고 종목명만 있는 경우 자동 검색 보정
        if (!payload.code && payload.name) {
          try {
            const searchRes = await app.api(`/api/stock-search?q=${encodeURIComponent(payload.name)}`);
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
          const result = await app.api(id ? `/api/holdings/${id}` : "/api/holdings", {
            method: id ? "PUT" : "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          form.closest("dialog")?.close();
          app.toast(result.message);
          await app.loadDashboard();
        } catch (error) {
          app.toast(error.message, true);
        }
      });

      app.$("#importForm")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = e.currentTarget;
        const file = app.$("#importFile")?.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append("file", file);
        try {
          const result = await app.api(`/api/import?broker=${encodeURIComponent(app.$("#importBroker")?.value || "기타 증권사")}`, {
            method: "POST",
            body: formData
          });
          form.closest("dialog")?.close();
          app.toast(result.message);
          await app.loadDashboard();
        } catch (error) {
          app.toast(error.message, true);
        }
      });
    }

    function bindAssetRecordForm() {
      app.$("#assetRecordForm")?.addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = e.currentTarget;
        const payload = Object.fromEntries(new FormData(form));
        const isPresent = v => v !== null && v !== undefined && String(v).trim() !== "" && !Number.isNaN(Number(String(v).replace(/,/g, "")));
        if (!isPresent(payload.total_value_krw) && isPresent(payload.total_assets_krw)) {
          payload.total_value_krw = payload.total_assets_krw;
        }
        if (!isPresent(payload.total_assets_krw) && isPresent(payload.total_value_krw)) {
          payload.total_assets_krw = payload.total_value_krw;
        }
        if (!isPresent(payload.net_worth_krw)) {
          payload.net_worth_krw = (Number(payload.total_assets_krw) || 0) - (Number(payload.total_debt_krw) || 0);
        }
        ["total_value_krw", "total_assets_krw", "total_debt_krw", "net_worth_krw", "total_cost_krw", "profit_krw", "return_rate", "day_profit_krw", "krw_value_krw", "usd_value_krw", "holding_count"].forEach(key => {
          payload[key] = isPresent(payload[key]) ? Number(String(payload[key]).replace(/,/g, "")) : 0;
        });
        payload.memo = payload.memo || "";
        payload.owner = payload.owner || app.currentOwner || "모두";
        try {
          const method = form.dataset.recordId ? "PUT" : "POST";
          const url = form.dataset.recordId ? `/api/asset-records/${form.dataset.recordId}` : "/api/asset-records";
          const result = await app.api(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          form.closest("dialog")?.close();
          app.toast(result.message);
          await loadAssetRecords(app.currentOwner);
        } catch (error) {
          app.toast(error.message, true);
        }
      });
    }

    function bindHeatmapResize() {
      window.addEventListener('resize', () => {
        clearTimeout(heatmapResizeTimer);
        heatmapResizeTimer = setTimeout(() => {
          heatmapResizeTimer = null;
          if (app.dashboard && app.currentWealthView() === 'invest' && window.WealthInvestTabState?.current() === 'heatmap') {
            renderHeatmaps(app.dashboard);
          }
        }, 200);
      });
    }

    return {
      publicActions: {
        setDashboardPeriod,
        renderClassifications,
        filterHoldingsByClassification,
        getEffectiveCap,
        getHeatmapColor,
        updateHeatmapLegendUI,
        squarify,
        renderTreemapContainer,
        renderHeatmaps,
        openHeatmapHolding,
        bindHeatmapInteractions,
        renderHoldings,
        syncHoldingSignalsContext,
        loadHoldingSignals,
        openStockChart,
        renderAssetRecords,
        renderTaxAccountHoldings,
        renderInvestmentView,
        loadAssetRecords,
        openImport,
        holdingEligibleAccounts,
        fillHoldingAccountOptions,
        resolveHoldingDialogAccountSelection,
        openHoldingDialog,
        openAssetRecordDialog,
      },
      actions: {
        selectSector,
        sortTaxHoldings,
        editTaxHolding,
        deleteTaxHolding,
        sortHoldings,
        openHoldingChart,
        selectChartPeriod,
        bindMarketPeriod,
        bindSectorColors,
        bindHoldingSignals,
        bindInvestmentControls,
        bindHoldingsList,
        bindRecordsAndAccountFields,
        bindHoldingForms,
        bindAssetRecordForm,
        bindHeatmapResize,
      },
      legacyState: {
        get currentRecordView() { return currentRecordView; },
        set currentRecordView(value) { currentRecordView = value; },
        get allAssetRecords() { return allAssetRecords; },
        set allAssetRecords(value) { allAssetRecords = value; },
        get assetRecords() { return assetRecords; },
        set assetRecords(value) { assetRecords = value; },
        get currentMarketAllSub() { return currentMarketAllSub; },
        set currentMarketAllSub(value) { currentMarketAllSub = value; },
        get currentMarketPeriod() { return currentMarketPeriod; },
        set currentMarketPeriod(value) { currentMarketPeriod = value; },
      },
    };
  }

  window.WealthInvestmentFeatureController = { create };
})();
