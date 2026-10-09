/* Resolve session-local investment navigation before panel markup is parsed. */
(() => {
  'use strict';
  const key = 'wealth_invest_tab';
  const tabs = ['overview', 'heatmap', 'records', 'buckets', 'tax_accounts', 'holdings'];
  const valid = value => tabs.includes(value) ? value : 'overview';
  let tab = 'overview';
  try { tab = valid(sessionStorage.getItem(key)); } catch (_) { /* Storage may be disabled. */ }
  const apply = value => {
    tab = valid(value);
    document.documentElement.dataset.wealthInvestTab = tab;
    return tab;
  };
  apply(tab);
  window.WealthInvestTabState = {
    current: () => tab,
    select: value => {
      apply(value);
      try { sessionStorage.setItem(key, tab); } catch (_) { /* Keep navigation usable. */ }
      return tab;
    },
  };
})();
