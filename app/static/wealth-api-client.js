(() => {
  "use strict";

  function create({ getStartup, invalidateLedgerRead }) {
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
      if (!isRead && parsed.pathname.startsWith('/api/ledger')) invalidateLedgerRead();
      const shared = isRead && ['/api/realized-pnl', '/api/actual-dividends', '/api/family-members', '/api/ipo/market', '/api/accounts', '/api/asset-records', '/api/ledger', '/api/market-overview', '/api/dividends'].includes(parsed.pathname);
      const reusable = shared && ((startupIncomeReuse && parsed.searchParams.get('year') === 'all') || parsed.pathname === '/api/ipo/market');
      // Price/snapshot writes do not change realized income or IPO market records.
      if (!isRead && !['/api/refresh-prices', '/api/planning/snapshot-all'].includes(parsed.pathname)) {
        invalidateStartupReads();
      }
      if (reusable && options.cache !== 'no-store' && allTimeReadCache.has(key)) { getStartup()?.count('cache_hit'); return allTimeReadCache.get(key); }
      if (shared && startupReadPending.has(key)) { getStartup()?.count('merged_get'); return startupReadPending.get(key); }
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
      getStartup()?.count('request');
      const address = new URL(url, location.origin);
      getStartup()?.request(address.pathname, address.searchParams.get('year') === 'all');
      const phase = ({'/api/auth/me':'auth', '/api/refresh-prices':'prices', '/api/planning/snapshot-all':'snapshot'})[address.pathname];
      if (phase) getStartup()?.count(`${phase}:start`);
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
      } finally { if (phase) getStartup()?.count(`${phase}:end`); }
    }

    return {
      api, apiRequest, invalidateStartupReads, finishStartupIncomeReads,
      getReadEpoch: () => startupReadEpoch,
      isStartupIncomeReuseEnabled: () => startupIncomeReuse,
      pendingReads: Object.freeze({
        get size() { return startupReadPending.size; },
        has: (key) => startupReadPending.has(key),
      }),
    };
  }

  globalThis.WealthApiClient = { create };
})();
