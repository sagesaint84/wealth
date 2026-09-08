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
  function historyView(history, owner, days, selectedDate, now=Date.now()) {
    const cutoff=now-days*86400000;
    const records=history.filter(r=>r.owner===owner && (!days || Date.parse(r.date+'T23:59:59+09:00')>=cutoff)).sort((a,b)=>a.date.localeCompare(b.date));
    const selected=records.find(r=>r.date===selectedDate) || records.at(-1) || null;
    return {records,selectedDate:selected?.date || '',canEdit:!!selected};
  }
  const model = { bucketTotals, historyView };
  if (typeof module !== 'undefined' && module.exports) module.exports = model;
  else root.WealthPlanningModel = model;
})(typeof window !== 'undefined' ? window : this);
