(() => {
  "use strict";

  // Opt-in synthetic profiling only: bounded memory, fixed labels, no payloads/URLs.
  function create(app) {
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
      if (!assetsReady) return false;
      const profile = app.getUserProfile();
      return !!profile && profile.username !== 'admin' && !profile.must_change_password;
    }
    function visible(id) {
      return canRead() && !!document.getElementById(id)?.getClientRects().length;
    }
    function loadVisible(preparedDividend = null) {
      if (!canRead()) return;
      const scope = JSON.stringify([app.startupReadEpoch, app.currentOwner, app.selectedDividendYear, app.selectedPnlYear,
        app.currentPnlTradeType, app.currentDividendMode, app.ledgerFeature.getYear(), app.ledgerFeature.getMonth(), app.ledgerFeature.isAnnualView(),
        ['marketGrid','recordsPanel','ledgerSectionPanel','dividendPanel','realizedPnlPanel','summaryRealizedPnl'].map(visible)]);
      if (scope !== visibleScope) { visibleScope = scope; visibleRevision++; }
      const key = `${visibleRevision}:${scope}`;
      if (visiblePending.has(key)) return visiblePending.get(key);
      const jobs = [];
      if (visible('marketGrid')) jobs.push(app.loadMarkets());
      if (visible('recordsPanel')) jobs.push(app.loadAssetRecords(app.currentOwner));
      if (visible('ledgerSectionPanel')) jobs.push(app.loadLedger());
      if (visible('dividendPanel')) jobs.push(app.currentDividendMode === 'estimated'
        ? app.loadDividends(app.currentOwner, {reuse:true}) : app.loadActualDividends(app.currentOwner, app.selectedDividendYear, preparedDividend));
      if (visible('realizedPnlPanel')) jobs.push(app.loadRealizedPnl(app.currentOwner, app.selectedPnlYear, app.currentPnlTradeType));
      if (visible('summaryRealizedPnl')) jobs.push(app.updateOverviewCardsAllTime(app.currentOwner));
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
        && app.isDividendEntryPending();
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
  }

  globalThis.WealthStartupReadController = { create };
})();
