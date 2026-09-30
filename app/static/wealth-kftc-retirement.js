(() => {
  'use strict';

  const RETIRED_IDS = [
    'kftcOpenBankingCard',
    'openapiKftcSection',
  ];

  function installHideRule() {
    if (document.getElementById('wealthKftcRetirementStyle')) return;
    const style = document.createElement('style');
    style.id = 'wealthKftcRetirementStyle';
    style.textContent = '#kftcOpenBankingCard,#openapiKftcSection{display:none!important}';
    document.head.appendChild(style);
  }

  function removeRetiredUi() {
    RETIRED_IDS.forEach((id) => document.getElementById(id)?.remove());
  }

  function retiredAsync() {
    return Promise.resolve(undefined);
  }

  function retiredAction() {
    return false;
  }

  // Keep dormant backend data untouched, but retire every user-facing KFTC path.
  window.refreshKftcStatus = retiredAsync;
  window.handleStartKftcOAuth = retiredAction;
  window.handleFetchKftcAccounts = retiredAsync;
  window.handlePreviewKftcBalance = retiredAsync;
  window.handleDisconnectKftc = retiredAsync;
  window.refreshUserKftcOpenApiStatus = retiredAsync;
  window.handleSaveUserKftcConfig = retiredAsync;

  installHideRule();
  removeRetiredUi();

  const observer = new MutationObserver(removeRetiredUi);

  function installObserver() {
    removeRetiredUi();
    if (document.body) observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.body) installObserver();
  else document.addEventListener('DOMContentLoaded', installObserver, { once: true });

  window.WealthKftcRetirement = {
    removeRetiredUi,
    retiredIds: [...RETIRED_IDS],
  };
})();
