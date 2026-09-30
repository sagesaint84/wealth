(() => {
  'use strict';

  const RETIRED_IDS = [
    'kftcOpenBankingCard',
    'openapiKftcSection',
  ];

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

  const observer = new MutationObserver(removeRetiredUi);

  function install() {
    removeRetiredUi();
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();

  window.WealthKftcRetirement = {
    removeRetiredUi,
    retiredIds: [...RETIRED_IDS],
  };
})();
