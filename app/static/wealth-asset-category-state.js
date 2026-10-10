/* Session navigation only; resolve before asset markup can paint. */
(() => {
  'use strict';
  const key = 'wealth_asset_category';
  const categories = ['securities', 'banking', 'insurance', 'real_estate'];
  const valid = value => categories.includes(value) ? value : 'securities';
  let category = 'securities';
  try { category = valid(sessionStorage.getItem(key)); } catch (_) { /* Storage optional. */ }
  const apply = value => {
    category = valid(value);
    document.documentElement.dataset.wealthAssetCategory = category;
    return category;
  };
  apply(category);
  window.WealthAssetCategoryState = {
    current: () => category,
    select: value => {
      apply(value);
      try { sessionStorage.setItem(key, category); } catch (_) { /* Keep navigation usable. */ }
      return category;
    },
  };
})();
