/* Pure view calculations, shared by browser and dependency-free Node tests. */
(function (root) {
  'use strict';
  function bucketTotals(state, view) {
    const totals = new Map(state.buckets.map(b => [b.id, 0]));
    totals.set('', 0);
    const amount = value => {
      const number = Number(value || 0);
      if (!Number.isFinite(number)) throw new Error('평가액이 유효하지 않습니다. 자산 정보를 확인하세요.');
      return number;
    };
    const add = (id, value) => { const key = totals.has(id) ? id : ''; totals.set(key, totals.get(key) + amount(value)); };
    const ids = new Set(view.accounts.map(a => String(a.id)));
    view.accounts.forEach(a => {
      const usd = amount(a.cash_usd);
      const fx = Number(view.fxRates?.USD);
      if (usd && (!Number.isFinite(fx) || fx <= 0)) throw new Error('USD 환율을 확인할 수 없어 버킷 합계를 계산하지 않았습니다.');
      add(state.accounts[a.id], amount(a.cash_krw) + (usd ? usd * fx : 0));
    });
    view.holdings.filter(h => ids.has(String(h.account_id))).forEach(h => {
      const id = Object.hasOwn(state.holdings, h.id) ? state.holdings[h.id] : state.accounts[h.account_id];
      add(id, h.market_value_krw);
    });
    return { totals, total: [...totals.values()].reduce((a, b) => a + b, 0) };
  }
  function bucketAllocationComparison(state, view) {
    const { totals, total } = bucketTotals(state, view);
    const buckets = state.buckets.map(bucket => ({
      id: String(bucket.id),
      name: String(bucket.name || ''),
      purpose: String(bucket.purpose || ''),
      target: Number(bucket.target || 0),
      value: totals.get(bucket.id) || 0,
    }));
    const targetTotal = buckets.reduce((sum, bucket) => sum + bucket.target, 0);
    const targetConfigured = targetTotal > 0;
    const target = targetConfigured ? buckets.map(bucket => ({
      id: bucket.id, name: bucket.name, value: bucket.target,
    })) : [];
    if (targetConfigured && targetTotal < 100) {
      target.push({ id: '__unallocated__', name: '미배정', value: 100 - targetTotal });
    }
    const current = buckets.map(bucket => ({
      id: bucket.id,
      name: bucket.name,
      value: bucket.value,
      percent: total > 0 ? bucket.value / total * 100 : 0,
    }));
    const unclassified = totals.get('') || 0;
    current.push({
      id: '__unclassified__',
      name: '미분류',
      value: unclassified,
      percent: total > 0 ? unclassified / total * 100 : 0,
    });
    return { buckets, current, target, total, targetTotal, targetConfigured };
  }
  function historyView(history, owner, days, selectedDate, now=Date.now()) {
    const cutoff=now-days*86400000;
    const records=history.filter(r=>r.owner===owner && (!days || Date.parse(r.date+'T23:59:59+09:00')>=cutoff)).sort((a,b)=>a.date.localeCompare(b.date));
    const selected=records.find(r=>r.date===selectedDate) || records.at(-1) || null;
    return {records,selectedDate:selected?.date || '',canEdit:!!selected};
  }
  const model = { bucketTotals, bucketAllocationComparison, historyView };
  if (typeof module !== 'undefined' && module.exports) module.exports = model;
  else root.WealthPlanningModel = model;
})(typeof window !== 'undefined' ? window : this);

// Browser-only loaders. Keep the pure model above dependency-free for Node tests.
if (typeof document !== 'undefined') {
  if (!document.querySelector('script[data-wealth-timeseries-panzoom]')) {
    const script = document.createElement('script');
    script.src = '/static/wealth-timeseries-panzoom.js?v=10.6j2';
    script.async = false;
    script.dataset.wealthTimeseriesPanzoom = '1';
    document.head.append(script);
  }
  if (!document.querySelector('script[data-wealth-ledger-timeseries-history]')) {
    const script = document.createElement('script');
    script.src = '/static/wealth-ledger-timeseries-history.js?v=10.6j4';
    script.async = false;
    script.dataset.wealthLedgerTimeseriesHistory = '1';
    document.head.append(script);
  }

  const loadUnifiedTimeseries = () => {
    if (!window.WealthTimeseriesPeriodCore) return;

    const loadUnified = () => {
      if (document.querySelector('script[data-wealth-timeseries-unified]')) return;
      const script = document.createElement('script');
      script.src = '/static/wealth-timeseries-unified.js?v=10.7g1';
      script.async = false;
      script.dataset.wealthTimeseriesUnified = '1';
      document.head.append(script);
    };

    const loadLabelLayout = () => {
      if (document.querySelector('script[data-wealth-timeseries-label-layout]')) {
        if (window.WealthTimeseriesLabelLayout) loadUnified();
        return;
      }
      const script = document.createElement('script');
      script.src = '/static/wealth-timeseries-label-layout.js?v=10.6k4';
      script.async = false;
      script.dataset.wealthTimeseriesLabelLayout = '1';
      script.addEventListener('load', loadUnified, { once: true });
      script.addEventListener('error', loadUnified, { once: true });
      document.head.append(script);
    };

    let visibleRange = document.querySelector('script[data-wealth-timeseries-visible-range]');
    if (!visibleRange) {
      visibleRange = document.createElement('script');
      visibleRange.src = '/static/wealth-timeseries-visible-range.js?v=10.6k4';
      visibleRange.async = false;
      visibleRange.dataset.wealthTimeseriesVisibleRange = '1';
      visibleRange.addEventListener('load', loadLabelLayout, { once: true });
      visibleRange.addEventListener('error', loadLabelLayout, { once: true });
      document.head.append(visibleRange);
    } else if (window.WealthTimeseriesVisibleRange) {
      loadLabelLayout();
    } else {
      visibleRange.addEventListener('load', loadLabelLayout, { once: true });
      visibleRange.addEventListener('error', loadLabelLayout, { once: true });
    }
  };

  let periodCore = document.querySelector('script[data-wealth-timeseries-period-core]');
  if (!periodCore) {
    periodCore = document.createElement('script');
    periodCore.src = '/static/wealth-timeseries-period-core.js?v=10.6k1';
    periodCore.async = false;
    periodCore.dataset.wealthTimeseriesPeriodCore = '1';
    periodCore.addEventListener('load', loadUnifiedTimeseries, { once: true });
    document.head.append(periodCore);
  } else if (window.WealthTimeseriesPeriodCore) {
    loadUnifiedTimeseries();
  } else {
    periodCore.addEventListener('load', loadUnifiedTimeseries, { once: true });
  }
}
